"""数据库迁移协议元数据测试（database-migration-ui W1-1）。

覆盖 PLANS/database-migration-ui.md §3.2/§3.3 的 W1-1 层验收：
- 协议常量模块纯导入（无引擎副作用——早期引导可消费）
- business_tables() 分类：42 业务表 + 3 协议表 = 45（与 test_db_migration 口径一致）
- 新 revision e9f0a1b2c3d4：建三表 + 存量库身份 seed + 幂等不重生成
- downgrade 受限：receipt/events 存在行时拒绝（禁止静默丢活跃凭据）；空协议表可回滚
- 迁移工具/基线不复制源协议行（见 test_migrate_sqlite_to_pg / test_pg_baseline）
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[2]

from app.core.database_protocol import (
    DIGEST_VERSION_CANONICAL_V1,
    EVENTS_TABLE,
    IDENTITY_TABLE,
    PROTOCOL_SCHEMA_VERSION,
    PROTOCOL_TABLE_NAMES,
    RECEIPT_STATUSES,
    RECEIPT_TABLE,
    is_protocol_table,
    is_valid_attempt_id,
)


def _cfg(db_path: str) -> Config:
    import os

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    os.environ["DATABASE_PATH"] = db_path
    return cfg


class TestProtocolConstantsPurity:
    """常量模块必须无引擎副作用（早期引导/CLI 可在引擎前消费）。"""

    def test_constants_module_imports_without_app_database(self):
        """子进程导入纯常量模块，不得加载 app.database（引擎/settings）。"""
        code = (
            "import sys; import app.core.database_protocol as p; "
            "assert 'app.database' not in sys.modules, 'protocol 模块不得触发引擎导入'; "
            "assert 'app.core.config' not in sys.modules, 'protocol 模块不得触发 settings'; "
            "print(p.DIGEST_VERSION_CANONICAL_V1)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_ROOT),
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(BACKEND_ROOT)},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == DIGEST_VERSION_CANONICAL_V1

    def test_constants_and_attempt_id_rules(self):
        assert PROTOCOL_TABLE_NAMES == frozenset({IDENTITY_TABLE, RECEIPT_TABLE, EVENTS_TABLE})
        assert is_protocol_table(IDENTITY_TABLE) and not is_protocol_table("torrent_info")
        assert PROTOCOL_SCHEMA_VERSION == "1"
        assert len(RECEIPT_STATUSES) == 5
        # attempt_id 形态（防目录穿越：仅允许前缀+UUID）
        assert is_valid_attempt_id("sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")
        assert is_valid_attempt_id("pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")
        assert is_valid_attempt_id("handoff/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0")
        for bad in ("sqlite-to-pg/../../etc", "sqlite-to-pg/", "../x", "sqlite-to-pg/not-a-uuid"):
            assert not is_valid_attempt_id(bad), bad


class TestBusinessTableClassification:
    """业务表分类 = sorted_tables − 协议三表（§3.2 显式版本化清单）。"""

    def test_business_tables_excludes_protocol(self):
        from app.core.model_registry import register_all_models
        from app.database import Base
        from app.models.database_migration import business_tables

        register_all_models()
        total = Base.metadata.sorted_tables
        business = business_tables()
        assert len(total) == 45, f"全表应 45（42 业务 + 3 协议），实际 {len(total)}"
        assert len(business) == 42, f"业务表应 42，实际 {len(business)}"
        assert {t.name for t in total} - {t.name for t in business} == set(PROTOCOL_TABLE_NAMES)


class TestProtocolRevision:
    """e9f0a1b2c3d4：建表 + 身份 seed + 幂等 + 受限 downgrade。"""

    def test_upgrade_creates_tables_and_seeds_identity(self, tmp_path):
        db = tmp_path / "protocol.db"
        command.upgrade(_cfg(str(db)), "head")

        conn = sqlite3.connect(db)
        try:
            for table in (IDENTITY_TABLE, RECEIPT_TABLE, EVENTS_TABLE):
                exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                assert exists, f"{table} 未创建"

            rows = conn.execute(f"SELECT id, database_id, schema_version, created_at FROM {IDENTITY_TABLE}").fetchall()
            assert len(rows) == 1, "身份表必须单例"
            row = rows[0]
            assert row[0] == 1
            # uuid4 形态：36 字符 8-4-4-4-12
            parts = row[1].split("-")
            assert [len(p) for p in parts] == [8, 4, 4, 4, 12], f"database_id 非 UUID: {row[1]}"
            assert row[2] == PROTOCOL_SCHEMA_VERSION
            assert row[3]  # created_at 已写
        finally:
            conn.close()

    def test_identity_seed_idempotent_across_reupgrade(self, tmp_path):
        """重复 upgrade 幂等：database_id 一经生成保持稳定（不重生成）。"""
        db = tmp_path / "idem.db"
        cfg = _cfg(str(db))
        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db)
        try:
            first = conn.execute(f"SELECT database_id FROM {IDENTITY_TABLE}").fetchone()[0]
        finally:
            conn.close()
        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db)
        try:
            second = conn.execute(f"SELECT database_id FROM {IDENTITY_TABLE}").fetchone()[0]
            count = conn.execute(f"SELECT COUNT(*) FROM {IDENTITY_TABLE}").fetchone()[0]
        finally:
            conn.close()
        assert first == second and count == 1

    def test_legacy_head_upgrade_seeds_identity(self, tmp_path):
        """存量库（停在 c9e0f1a2b3c4）升级到新 head 补建三表并生成身份。"""
        db = tmp_path / "legacy.db"
        cfg = _cfg(str(db))
        command.upgrade(cfg, "c9e0f1a2b3c4")
        conn = sqlite3.connect(db)
        try:
            assert not conn.execute(
                f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{IDENTITY_TABLE}'"
            ).fetchone()
        finally:
            conn.close()

        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db)
        try:
            assert conn.execute(f"SELECT COUNT(*) FROM {IDENTITY_TABLE}").fetchone()[0] == 1
        finally:
            conn.close()

    def test_downgrade_drops_tables_when_no_receipts(self, tmp_path):
        db = tmp_path / "drop.db"
        cfg = _cfg(str(db))
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "c9e0f1a2b3c4")
        conn = sqlite3.connect(db)
        try:
            for table in PROTOCOL_TABLE_NAMES:
                assert not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone(), f"{table} 应回滚删除"
        finally:
            conn.close()

    def test_downgrade_refuses_with_receipt_rows(self, tmp_path):
        """receipt/events 存在行时拒绝降级（禁止静默丢活跃/未完成凭据）。"""
        db = tmp_path / "guard.db"
        cfg = _cfg(str(db))
        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                f"INSERT INTO {RECEIPT_TABLE} (attempt_id, operation_kind, target_database_id, "
                "ownership_nonce, revision_at_import, digest_version, schema_fingerprint, "
                "origin_epoch, eligible_epoch, status, created_at, updated_at) "
                "VALUES ('sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0', 'MIGRATE', "
                "'11111111-2222-3333-4444-555555555555', 'nonce', 'c9e0f1a2b3c4', "
                f"'{DIGEST_VERSION_CANONICAL_V1}', 'fp', 'e1', 'e1', 'IMPORTING', "
                "datetime('now'), datetime('now'))"
            )
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(RuntimeError, match="拒绝降级"):
            command.downgrade(cfg, "c9e0f1a2b3c4")

        conn = sqlite3.connect(db)
        try:
            for table in PROTOCOL_TABLE_NAMES:
                assert conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone(), f"{table} 应保留"
            # ABANDONED（已放弃）同样拒绝——历史凭据不可静默删除
            conn.execute(f"UPDATE {RECEIPT_TABLE} SET status='ABANDONED'")
            conn.commit()
        finally:
            conn.close()
        with pytest.raises(RuntimeError, match="拒绝降级"):
            command.downgrade(cfg, "c9e0f1a2b3c4")

    def test_events_only_rows_also_refuse_downgrade(self, tmp_path):
        """仅 events 有行（receipt 已清理的异常态）同样拒绝降级。"""
        db = tmp_path / "events-only.db"
        cfg = _cfg(str(db))
        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                f"INSERT INTO {EVENTS_TABLE} (event_id, attempt_id, seq, summary, created_at) "
                "VALUES ('ev-1', 'handoff/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0', 1, 'x', datetime('now'))"
            )
            conn.commit()
        finally:
            conn.close()
        with pytest.raises(RuntimeError, match="拒绝降级"):
            command.downgrade(cfg, "c9e0f1a2b3c4")
