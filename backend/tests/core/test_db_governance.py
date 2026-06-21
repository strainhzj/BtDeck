# -*- coding: utf-8 -*-
"""
数据库四轨治理结果验证测试

验证 migrate_database() 及配套逻辑的核心行为，确保治理目标达成：
1. 幽灵版本（9aea25308aff）自动救援 + 备份
2. 未知版本（回滚场景）拒绝自动 stamp（只告警）
3. 已是 head 的库 no-op 且不备份
4. 迁移前备份生成 + 保留份数 + WAL 处理
5. search_templates 第四轨归位（表 + 索引完整性）
6. 配置层一致性（DATABASE_PATH 环境变量双源）
"""

import os
import sqlite3
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import settings
from app.core.migration import (
    migrate_database,
    _rescue_or_warn_version,
    _read_db_version,
    _build_alembic_config,
    KNOWN_GHOST_VERSIONS,
)
from app.core.db_backup import backup_before_migration, prune_old_backups, BACKUP_KEEP

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
GHOST_VERSION = "9aea25308aff"
SCHEMA_SQL = BACKEND_ROOT / "config" / "production_complete_schema.sql"


@pytest.fixture(autouse=True)
def _clean_database_path_env():
    """自动清理 DATABASE_PATH 环境变量，防止跨测试污染（测试隔离）。"""
    old = os.environ.pop("DATABASE_PATH", None)
    yield
    if old is not None:
        os.environ["DATABASE_PATH"] = old
    else:
        os.environ.pop("DATABASE_PATH", None)


def _get_heads() -> list:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg).get_heads()


def _build_ghost_db(db_path: str) -> None:
    """用 production schema 快照建库并写入幽灵版本（模拟 frozen 历史库）。"""
    conn = sqlite3.connect(db_path)
    try:
        with open(SCHEMA_SQL, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.execute(
            f"INSERT INTO alembic_version (version_num) VALUES ('{GHOST_VERSION}')"
        )
        conn.commit()
    finally:
        conn.close()


def _table_count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        ).fetchone()[0]
    finally:
        conn.close()


def _get_indexes(db_path: str, table: str) -> set:
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table}'"
        ).fetchall()}
    finally:
        conn.close()


# ==================== 场景1：幽灵版本救援 ====================

class TestGhostVersionRescue:
    """验证 9aea25308aff 幽灵版本库的自动救援。"""

    def test_ghost_version_is_in_blacklist(self):
        """幽灵版本必须在黑名单中（否则救援逻辑不会触发）。"""
        assert GHOST_VERSION in KNOWN_GHOST_VERSIONS, (
            f"{GHOST_VERSION} 必须在 KNOWN_GHOST_VERSIONS 中"
        )

    def test_ghost_version_blacklist_maps_to_valid_revision(self):
        """黑名单映射的目标版本必须在迁移链中。"""
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        sd = ScriptDirectory.from_config(cfg)
        valid_revs = {r.revision for r in sd.walk_revisions()}
        for ghost, target in KNOWN_GHOST_VERSIONS.items():
            assert target in valid_revs, (
                f"幽灵版本 {ghost} 的映射目标 {target} 必须在迁移链中"
            )

    def test_ghost_db_migration_rescues_and_upgrades(self, tmp_path):
        """幽灵库 migrate_database 后：版本推进到 head，search_templates 索引补建。"""
        db_path = str(tmp_path / "ghost.db")
        _build_ghost_db(db_path)
        os.environ["DATABASE_PATH"] = db_path

        migrate_database()

        heads = _get_heads()
        final_version = _read_db_version(db_path)
        assert final_version == heads[0], (
            f"幽灵库救援后版本应为 {heads[0]}，实际 {final_version}"
        )
        assert final_version != GHOST_VERSION

        # search_templates 索引应被补建（schema 快照缺索引）
        indexes = _get_indexes(db_path, "search_templates")
        assert "idx_search_templates_user_id" in indexes
        assert "idx_search_templates_is_public" in indexes

    def test_ghost_db_migration_creates_backup(self, tmp_path):
        """幽灵库升级必须生成备份（B2：备份在救援前）。"""
        db_path = str(tmp_path / "ghost.db")
        _build_ghost_db(db_path)
        os.environ["DATABASE_PATH"] = db_path

        migrate_database()

        backups = list(tmp_path.glob("*.pre-migration-*"))
        assert len(backups) >= 1, "幽灵库升级应触发迁移前备份"

        # 备份的版本应仍是幽灵版本（备份在 stamp 前）
        backup_conn = sqlite3.connect(str(backups[0]))
        backup_version = backup_conn.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        backup_conn.close()
        assert backup_version == GHOST_VERSION, (
            "备份应在救援前生成，故版本应仍是幽灵版本"
        )


# ==================== 场景4：回滚（未知版本告警） ====================

class TestRollbackScenario:
    """验证版本回滚场景下未知版本的处理。"""

    def test_unknown_version_not_auto_stamped(self, tmp_path):
        """未知版本（模拟回滚后的未来版本）不应被自动 stamp。

        这是 B1 修正的核心：避免静默降级制造 version/schema 不一致。
        """
        db_path = str(tmp_path / "future.db")
        _build_ghost_db(db_path)
        # 改成不在黑名单的虚构未来版本
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM alembic_version")
        conn.execute("INSERT INTO alembic_version VALUES ('zzzz_future_v106')")
        conn.commit()
        conn.close()
        os.environ["DATABASE_PATH"] = db_path

        migrate_database()  # DEV 模式失败不终止

        final_version = _read_db_version(db_path)
        assert final_version == "zzzz_future_v106", (
            "未知版本不应被自动 stamp（B1 黑名单），应保持原值"
        )

    def test_known_version_in_chain_upgrades_normally(self, tmp_path):
        """迁移链内的落后版本应正常 upgrade（不是幽灵也不是未知）。

        用全新空库模拟"落后版本"：先只 upgrade 到中间版本，再 upgrade 到 head。
        """
        db_path = str(tmp_path / "staged.db")
        os.environ["DATABASE_PATH"] = db_path

        # 先只升级到中间版本（模拟一个落后库）
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        command.upgrade(cfg, "d0e58437af70")  # 中间版本
        assert _read_db_version(db_path) == "d0e58437af70"

        # 再用 migrate_database 升级到 head
        migrate_database()
        heads = _get_heads()
        assert _read_db_version(db_path) == heads[0]


# ==================== 幂等性与 no-op ====================

class TestIdempotency:
    """验证 head 库的 no-op 行为。"""

    def test_head_db_migration_is_noop_no_backup(self, tmp_path):
        """已是 head 的库 migrate 应 no-op 且不生成备份。"""
        db_path = str(tmp_path / "head.db")
        os.environ["DATABASE_PATH"] = db_path

        migrate_database()  # 首次建库
        heads = _get_heads()
        version_before = _read_db_version(db_path)
        assert version_before == heads[0]

        migrate_database()  # 再次（应 no-op）
        assert _read_db_version(db_path) == heads[0]

        # no-op 不应产生新备份
        backups = list(tmp_path.glob("*.pre-migration-*"))
        assert len(backups) == 0, "head 库 no-op 不应备份"


# ==================== 备份逻辑 ====================

class TestBackupLogic:
    """验证迁移前备份的生成、保留份数、WAL 处理。"""

    def test_backup_preserves_data(self, tmp_path):
        """备份应保留升级前的完整数据。"""
        db_path = str(tmp_path / "data.db")
        _build_ghost_db(db_path)

        backup_path = backup_before_migration(db_path)
        assert backup_path is not None
        assert Path(backup_path).exists()

        # 备份应能正常打开且数据完整
        conn = sqlite3.connect(backup_path)
        table_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        assert table_count > 20, "备份应包含全部表"

    def test_backup_prune_keeps_only_n(self, tmp_path):
        """备份清理应只保留最近 BACKUP_KEEP 份。"""
        db_path = str(tmp_path / "prune.db")
        _build_ghost_db(db_path)

        # 生成超过 BACKUP_KEEP 份备份
        for i in range(BACKUP_KEEP + 3):
            # 每次用不同时间戳（手动造文件）
            fake = f"{db_path}.pre-migration-2026010{i}-000000"
            shutil.copy2(db_path, fake)

        removed = prune_old_backups(db_path, keep=BACKUP_KEEP)
        remaining = list(tmp_path.glob("*.pre-migration-*"))
        assert len(remaining) == BACKUP_KEEP, (
            f"应保留 {BACKUP_KEEP} 份，实际 {len(remaining)}"
        )

    def test_backup_failure_does_not_crash(self, tmp_path):
        """备份失败不应阻塞（只告警）。"""
        # 指向不存在的路径触发备份失败
        result = backup_before_migration(str(tmp_path / "nonexistent.db"))
        assert result is None  # 失败返回 None


# ==================== 配置一致性 ====================

class TestConfigConsistency:
    """验证 DB URL 双源一致性（B3：config.py 与 env.py 消费同一来源）。"""

    def test_database_path_reads_env_var(self, monkeypatch):
        """config.py 的 DATABASE_PATH 应读取 DATABASE_PATH 环境变量。"""
        monkeypatch.setenv("DATABASE_PATH", "/tmp/test_consistency.db")
        assert str(settings.DATABASE_PATH) == "/tmp/test_consistency.db" or \
               str(settings.DATABASE_PATH).replace("\\", "/") == "/tmp/test_consistency.db"

    def test_build_alembic_config_sets_env_var(self, tmp_path):
        """_build_alembic_config 应设置 DATABASE_PATH 环境变量（防 env.py 串库）。"""
        target = str(tmp_path / "cfg.db")
        os.environ.pop("DATABASE_PATH", None)
        _build_alembic_config(target)
        assert os.environ.get("DATABASE_PATH") == target


# ==================== search_templates 第四轨归位 ====================

class TestSearchTemplatesTrackClosure:
    """验证 search_templates 第四轨已彻底归位 Alembic。"""

    def test_search_templates_in_migration_chain(self):
        """search_templates 必须有对应的 alembic 迁移。"""
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        sd = ScriptDirectory.from_config(cfg)
        # 遍历所有迁移，确认有 create search_templates 的操作
        found = False
        for rev in sd.walk_revisions():
            rev_path = BACKEND_ROOT / "alembic" / "versions" / f"{rev.revision}_*.py"
            matches = list(BACKEND_ROOT.glob(f"alembic/versions/{rev.revision}_*.py"))
            if matches:
                content = matches[0].read_text(encoding="utf-8")
                if "search_templates" in content:
                    found = True
                    break
        assert found, "应存在含 search_templates 的迁移"

    def test_no_ensure_table_exists_in_code(self):
        """_ensure_table_exists 方法应已从生产代码删除。"""
        from app.services.advanced_search import SearchTemplateModel
        assert not hasattr(SearchTemplateModel, '_ensure_table_exists'), (
            "_ensure_table_exists 应已删除（第四轨归位，表由 Alembic 管理）"
        )

    def test_orm_model_registered_in_metadata(self):
        """SearchTemplate ORM 模型应注册到 Base.metadata。"""
        from app.database import Base
        assert 'search_templates' in Base.metadata.tables, (
            "SearchTemplate 应注册到 Base.metadata（autogenerate 依赖）"
        )


# ==================== create_all 移除验证 ====================

class TestCreateAllRemoval:
    """验证 create_all 已从 init_db 移除。"""

    def test_init_db_has_no_create_all_call(self):
        """init_db 不应再调用 Base.metadata.create_all。"""
        db_path = BACKEND_ROOT / "app" / "database.py"
        content = db_path.read_text(encoding="utf-8")
        # 确认没有实际调用（注释提及不算）
        lines = content.splitlines()
        for line in lines:
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            assert "Base.metadata.create_all(bind=engine)" not in stripped, (
                "init_db 不应再调用 create_all（表结构由 Alembic 管理）"
            )

    def test_schema_snapshot_removed_from_startup(self):
        """ensure_database_initialized 应已从 main.py 启动路径移除。"""
        main_path = BACKEND_ROOT / "app" / "main.py"
        content = main_path.read_text(encoding="utf-8")
        assert "ensure_database_initialized" not in content, (
            "main.py 不应再调用 ensure_database_initialized（schema 快照已下线）"
        )
