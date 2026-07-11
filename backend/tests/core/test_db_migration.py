# -*- coding: utf-8 -*-
"""
数据库迁移链完整性测试（四轨治理安全网）

验证目标：
1. Alembic 迁移链能从空库独立建起完整 schema（不依赖 create_all / schema 快照）
2. 已有 head 库 upgrade 是幂等的（无副作用）
3. 幽灵版本（9aea25308aff）能被正确识别（为 migrate_database 的救援逻辑奠基）
4. env.py 与应用消费同一个 DATABASE_PATH（防串库）

注意：migrate_database() / _rescue_or_warn_version() / _backup_before_migration()
的完整行为测试在阶段3 实现后补充到本文件。
本阶段先覆盖"迁移链本身是否健全"——这是删除 create_all / schema 快照的前提。
"""

import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

# backend/ 目录（alembic.ini 所在位置）
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@pytest.fixture(autouse=True)
def _clean_database_path_env():
    """自动清理 DATABASE_PATH 环境变量，防止跨测试污染（测试隔离）。"""
    import os

    old = os.environ.pop("DATABASE_PATH", None)
    yield
    if old is not None:
        os.environ["DATABASE_PATH"] = old
    else:
        os.environ.pop("DATABASE_PATH", None)


# 已知的迁移链 revision（与 alembic/versions/ 保持一致，变更时同步更新）
# 链：e2a02abcf912(base,21表) → d0e58437af70(+1) → a0ada9774936(+1) → 95ef8bd8b47a(+search_templates) → c3f1a8b7d902(+orphan_file_tables) → b075727f7182(+orphan_lifecycle: candidate+lease+dedupe_key)
EXPECTED_HEAD = "b075727f7182"
PREV_HEAD = "c3f1a8b7d902"  # orphan_lifecycle 归位前的 head（v1.0.6 孤儿文件表）
GHOST_VERSION = "9aea25308aff"  # init_schema_from_production 写入的历史幽灵版本


def _make_alembic_config(db_path: str) -> Config:
    """构造指向指定 DB 的 Alembic Config（编程式调用）。"""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # 关键：设 DATABASE_PATH 环境变量，env.py 会优先读它（防串库）
    os.environ["DATABASE_PATH"] = str(db_path)
    return cfg


def _table_count(db_path: str) -> int:
    """统计业务表数量（排除 sqlite 内部表和 alembic_version）。"""
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        ).fetchone()[0]
        return count
    finally:
        conn.close()


def _read_version(db_path: str):
    """读取 alembic_version；无表返回 None。"""
    if not Path(db_path).exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        # 检查 alembic_version 表是否存在
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if not has_table:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


# ==================== 迁移链完整性 ====================


class TestMigrationChainIntegrity:
    """验证 Alembic 迁移链本身的健全性。"""

    def test_migration_chain_has_single_head(self):
        """迁移链应为单 head（无分叉）。"""
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        sd = ScriptDirectory.from_config(cfg)
        heads = sd.get_heads()
        assert len(heads) == 1, f"迁移链应只有 1 个 head，实际 {len(heads)}: {heads}"
        assert heads[0] == EXPECTED_HEAD, f"head 应为 {EXPECTED_HEAD}，实际 {heads[0]}"

    def test_ghost_version_not_in_chain(self):
        """幽灵版本 9aea25308aff 不应在迁移链中（验证它是历史遗留）。"""
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        sd = ScriptDirectory.from_config(cfg)
        valid_revs = {r.revision for r in sd.walk_revisions()}
        assert GHOST_VERSION not in valid_revs, f"幽灵版本 {GHOST_VERSION} 不应在迁移链中，否则它就不是幽灵了"

    def test_empty_db_upgrade_head_builds_full_schema(self, tmp_path):
        """空库 alembic upgrade head 应建起完整 schema（26 张业务表）。

        这是删除 create_all 的核心前提：迁移链能独立承担建库。
        """
        db_path = tmp_path / "empty.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, "head")

        assert db_path.exists(), "upgrade 后数据库文件应存在"
        assert _read_version(str(db_path)) == EXPECTED_HEAD
        count = _table_count(str(db_path))
        # base(e2a02abcf912) 建 21 表 + d0e58437af70 加 1 + a0ada9774936 加 1 + 95ef8bd8b47a 加 search_templates = 24
        # + c3f1a8b7d902 加 orphan_scan_result + orphan_file = 26
        # + b075727f7182 加 orphan_current_candidate + orphan_operation_lease = 28
        assert count == 28, f"空库 upgrade 应建 28 张业务表（含 orphan_lifecycle），实际 {count}"

    def test_upgrade_head_is_idempotent(self, tmp_path):
        """已有 head 库再次 upgrade 应幂等（version 不变、表数不变）。"""
        db_path = tmp_path / "idempotent.db"
        cfg = _make_alembic_config(str(db_path))

        # 首次建库
        command.upgrade(cfg, "head")
        version_before = _read_version(str(db_path))
        count_before = _table_count(str(db_path))

        # 再次 upgrade（应 no-op）
        command.upgrade(cfg, "head")
        version_after = _read_version(str(db_path))
        count_after = _table_count(str(db_path))

        assert version_before == version_after == EXPECTED_HEAD
        assert count_before == count_after


# ==================== 串库防护 ====================


class TestDatabasePathRouting:
    """验证 env.py 根据 DATABASE_PATH 环境变量路由到正确库（防串库）。

    这是 B3（阶段3+4 同批）的测试基础：env.py 必须与 config.py 消费同一来源。
    """

    def test_upgrade_writes_to_specified_database_path(self, tmp_path):
        """设 DATABASE_PATH 后，upgrade 应写到该路径，不污染真实 app.db。"""
        from app.core.config import settings

        target_db = tmp_path / "routed.db"
        cfg = _make_alembic_config(str(target_db))
        command.upgrade(cfg, "head")

        # 目标库应已建表
        assert target_db.exists()
        assert _table_count(str(target_db)) == 28

        # 真实 app.db 的 version 不应被改动
        real_db = str(settings.DATABASE_PATH)
        if Path(real_db).exists():
            # app.db version 应保持原值（不因本次测试的 upgrade 而变）
            # 注意：这里只验证 app.db 仍可读且 version 非空，不硬编码具体值
            real_version = _read_version(real_db)
            assert real_version is not None, "真实 app.db 不应被测试污染到丢失 version"
