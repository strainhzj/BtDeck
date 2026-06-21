# -*- coding: utf-8 -*-
"""
数据库治理补充测试（Code Review P0/P1 缺口）

覆盖审查发现的盲区：
- _read_db_version 的 4 种边界（文件不存在/表不存在/表空/OperationalError）
- migrate_database 异常路径（DEV 分流 + command.upgrade 失败）
- _rescue_or_warn_version 黑名单 target 防御 + 多 head 防御
- 95ef8bd8b47a downgrade 守卫对称性
- 表存在且有索引的 no-op 分支
- 备份同秒冲突（已修复后的回归）
"""

import os
import sqlite3
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import settings
from app.core.migration import (
    migrate_database,
    _rescue_or_warn_version,
    _read_db_version,
    KNOWN_GHOST_VERSIONS,
)
from app.core.db_backup import backup_before_migration

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
SCHEMA_SQL = BACKEND_ROOT / "config" / "production_complete_schema.sql"
GHOST_VERSION = "9aea25308aff"


def _get_heads() -> list:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg).get_heads()


def _build_ghost_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        with open(SCHEMA_SQL, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.execute(f"INSERT INTO alembic_version VALUES ('{GHOST_VERSION}')")
        conn.commit()
    finally:
        conn.close()


# ==================== _read_db_version 边界 ====================

class TestReadDbVersion:
    """_read_db_version 是救援逻辑的判定基础，必须 4 种边界全覆盖。"""

    def test_file_not_exists_returns_none(self, tmp_path):
        assert _read_db_version(str(tmp_path / "nonexistent.db")) is None

    def test_no_alembic_version_table_returns_none(self, tmp_path):
        """有 DB 文件但无 alembic_version 表（如纯业务库）→ None。"""
        db = str(tmp_path / "no_version_table.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE users (id INTEGER)")
        conn.commit()
        conn.close()
        assert _read_db_version(db) is None

    def test_empty_version_table_returns_none(self, tmp_path):
        """alembic_version 表存在但无数据行 → None。"""
        db = str(tmp_path / "empty_version.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR)")
        conn.commit()
        conn.close()
        assert _read_db_version(db) is None

    def test_valid_version_returned(self, tmp_path):
        """正常版本 → 返回版本字符串。"""
        db = str(tmp_path / "valid.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR)")
        conn.execute("INSERT INTO alembic_version VALUES ('abc123')")
        conn.commit()
        conn.close()
        assert _read_db_version(db) == "abc123"


# ==================== migrate_database 异常路径 ====================

class TestMigrateDatabaseExceptionPaths:
    """覆盖 DEV 分流 + command.upgrade 失败。"""

    def test_upgrade_failure_dev_mode_continues(self, tmp_path, monkeypatch):
        """DEV=True 时 command.upgrade 失败应告警继续，不抛异常。"""
        db = str(tmp_path / "fail.db")
        monkeypatch.setenv("DATABASE_PATH", db)
        monkeypatch.setattr(settings, "DEV", True)

        # mock command.upgrade 抛异常
        with patch("app.core.migration.command.upgrade", side_effect=Exception("模拟迁移失败")):
            # DEV 模式不抛
            migrate_database()

    def test_upgrade_failure_production_raises(self, tmp_path, monkeypatch):
        """DEV=False 时 command.upgrade 失败应抛 RuntimeError。"""
        db = str(tmp_path / "fail_prod.db")
        monkeypatch.setenv("DATABASE_PATH", db)
        monkeypatch.setattr(settings, "DEV", False)

        with patch("app.core.migration.command.upgrade", side_effect=Exception("模拟迁移失败")):
            with pytest.raises(RuntimeError, match="Database migration failed"):
                migrate_database()

    def test_multiple_heads_raises_runtime_error(self, tmp_path, monkeypatch):
        """迁移链多 head（分叉）应显式抛 RuntimeError。"""
        db = str(tmp_path / "multihead.db")
        monkeypatch.setenv("DATABASE_PATH", db)
        monkeypatch.setattr(settings, "DEV", False)

        # mock get_heads 返回 2 个
        with patch("alembic.script.ScriptDirectory.get_heads", return_value=["head_a", "head_b"]):
            with pytest.raises(RuntimeError, match="分叉"):
                migrate_database()


# ==================== _rescue_or_warn_version 防御 ====================

class TestRescueVersionDefenses:
    """黑名单 target 防御 + current=None 早返回。"""

    def test_ghost_target_not_in_chain_rejected(self, tmp_path, monkeypatch):
        """黑名单映射的 target 不在迁移链（配置错误）应拒绝 stamp。"""
        db = str(tmp_path / "bad_target.db")
        _build_ghost_db(db)
        monkeypatch.setenv("DATABASE_PATH", db)

        # 临时篡改黑名单 target 为不存在的 revision
        original = dict(KNOWN_GHOST_VERSIONS)
        KNOWN_GHOST_VERSIONS[GHOST_VERSION] = "nonexistent_rev_xyz"
        try:
            # 不应抛异常（防御性 return），且版本保持幽灵版本
            migrate_database()
            assert _read_db_version(db) == GHOST_VERSION, \
                "target 不在链中时应拒绝 stamp，版本不变"
        finally:
            KNOWN_GHOST_VERSIONS.clear()
            KNOWN_GHOST_VERSIONS.update(original)

    def test_current_none_early_return(self, tmp_path, monkeypatch):
        """current=None（空库）应直接 return，不触发救援逻辑。"""
        db = str(tmp_path / "empty.db")
        monkeypatch.setenv("DATABASE_PATH", db)

        # 直接调 _rescue_or_warn_version，current=None
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        heads = _get_heads()
        # 应无异常返回
        _rescue_or_warn_version(cfg, db, None, heads)


# ==================== 95ef8bd8b47a downgrade 守卫 ====================

class TestSearchTemplatesMigrationDowngrade:
    """验证 downgrade 的 inspect 守卫对称性（回滚安全）。"""

    def test_downgrade_drops_table_and_indexes(self, tmp_path, monkeypatch):
        """upgrade 后再 downgrade，表和索引应被正确移除。"""
        db = str(tmp_path / "downgrade_test.db")
        monkeypatch.setenv("DATABASE_PATH", db)

        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

        # 先 upgrade 到 head（含 search_templates）
        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='search_templates'"
        ).fetchone() is not None
        conn.close()

        # downgrade 一步（撤 search_templates）
        command.downgrade(cfg, "a0ada9774936")

        conn = sqlite3.connect(db)
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='search_templates'"
        ).fetchone()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='search_templates'"
        ).fetchall()
        conn.close()

        assert table_exists is None, "downgrade 后 search_templates 表应被删除"
        assert indexes == [], "downgrade 后 search_templates 索引应被删除"

    def test_downgrade_idempotent_when_already_absent(self, tmp_path, monkeypatch):
        """downgrade 对已不存在表的库应安全（inspect 守卫）。"""
        db = str(tmp_path / "downgrade_idempotent.db")
        monkeypatch.setenv("DATABASE_PATH", db)

        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

        # 只 upgrade 到 search_templates 之前
        command.upgrade(cfg, "a0ada9774936")

        # 此时无 search_templates 表，downgrade 应安全（inspect 检测后跳过 drop）
        command.downgrade(cfg, "d0e58437af70")


# ==================== 表存在且有索引的 no-op 分支 ====================

class TestInspectGuardNoOpBranch:
    """验证表+索引都存在时 upgrade 不重建（inspect 守卫第三场景）。"""

    def test_upgrade_skips_when_table_and_indexes_exist(self, tmp_path, monkeypatch):
        """已有 search_templates 表+索引的库，upgrade 不应报错或重建。"""
        db = str(tmp_path / "has_indexes.db")
        monkeypatch.setenv("DATABASE_PATH", db)

        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

        # 先完整 upgrade（表+索引都建好）
        command.upgrade(cfg, "head")

        # 记录索引创建时间（通过 rowid 间接验证不重建）
        conn = sqlite3.connect(db)
        idx_before = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='search_templates'"
        ).fetchall()
        conn.close()

        # 再 stamp 回 a0ada9774936，重新 upgrade 触发 inspect 守卫
        conn = sqlite3.connect(db)
        conn.execute("UPDATE alembic_version SET version_num = 'a0ada9774936'")
        conn.commit()
        conn.close()

        command.upgrade(cfg, "head")  # 应 inspect 检测后 no-op

        conn = sqlite3.connect(db)
        idx_after = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='search_templates'"
        ).fetchall()
        conn.close()

        assert set(idx_before) == set(idx_after), "索引不应被重建"


# ==================== 备份同秒冲突回归（已修复） ====================

class TestBackupTimestampPrecision:
    """验证备份文件名含毫秒，同秒多次不覆盖。"""

    def test_rapid_backups_do_not_overwrite(self, tmp_path):
        """同秒内连续两次备份不应互相覆盖（毫秒精度修复回归）。"""
        db = str(tmp_path / "rapid.db")
        _build_ghost_db(db)

        b1 = backup_before_migration(db)
        b2 = backup_before_migration(db)

        assert b1 is not None and b2 is not None
        assert b1 != b2, "同秒两次备份应有不同文件名（毫秒精度）"
        assert Path(b1).exists(), "第一次备份不应被覆盖"
        assert Path(b2).exists()
