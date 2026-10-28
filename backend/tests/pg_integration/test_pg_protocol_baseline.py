"""真实 PostgreSQL 协议基线集成测试（database-migration-ui W1-2）。

门控与基建复用 test_pg_smoke（DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN，
CI postgres:16 service 注入；本地无 PG 自动 skip——skip 不登记为验收通过，
W1 验收证据以 CI pg-integration job 实际执行为准）。

覆盖（PLANS §3.3 / 验收 T02/T14 的真 PG 侧）：
- 基线同事务 create_all + stamp + 目标自身 identity（真 PG 事务性 DDL）
- 迁移基线 ownership：IMPORTING receipt 持久 + marker；finalize VERIFIED + 清 marker
- 方言强断言在真 PG 引擎上自然放行（误收 sqlite 引擎的拒绝由单测覆盖）
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

_ADMIN_DSN = os.getenv("BTDECK_PG_TEST_ADMIN_DSN", "")
pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "sqlite") != "postgresql" or not _ADMIN_DSN,
    reason="PG 集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]

from app.core import pg_baseline
from app.core.database_protocol import RECEIPT_STATUS_VERIFIED
from tests.pg_integration.test_pg_smoke import _make_cfg


def _ownership(attempt_id: str) -> dict:
    return {
        "attempt_id": attempt_id,
        "operation_kind": "MIGRATE",
        "source_database_id": "11111111-1111-1111-1111-111111111111",
        "ownership_nonce": f"nonce-{uuid.uuid4().hex[:12]}",
        "revision_at_import": "rev-w1",
        "schema_fingerprint": "fp-w1",
        "origin_epoch": "epoch-w1",
        "eligible_epoch": "epoch-w1",
        "deployment_id": "deploy-w1",
    }


class TestProtocolBaselineOnRealPG:
    def test_plain_baseline_identity(self, fresh_pg_db: str) -> None:
        """普通新装：identity 单例生成、无 receipt（真 PG 事务性 DDL）。"""
        from sqlalchemy import text

        head = "c9e0f1a2b3c4"  # 历史锚点（任意合法 stamp 目标；head 语义由链测试覆盖）
        assert pg_baseline.initialize_pg_baseline(_make_cfg(), head) is True
        engine = pg_baseline.pg_sync_engine()
        try:
            with engine.connect() as conn:
                database_id = pg_baseline.read_database_identity(conn)
                receipts = conn.execute(text("SELECT COUNT(*) FROM bt_database_migration_receipt")).scalar()
        finally:
            engine.dispose()
        assert database_id and len(database_id) == 36
        assert receipts == 0

    def test_migration_baseline_receipt_and_finalize(self, fresh_pg_db: str) -> None:
        """迁移基线：IMPORTING receipt+marker 同事务持久；finalize 原子 VERIFIED+清 marker。"""
        from sqlalchemy import inspect

        attempt_id = f"sqlite-to-pg/{uuid.uuid4()}"
        marker = {
            "migration_id": f"sqlite-{uuid.uuid4().hex[:8]}",
            "source_digest": "digest-w1",
            "tool_version": "2.0.0",
            "checkpoint": {"completed": {}},
        }
        assert pg_baseline.initialize_pg_baseline(
            _make_cfg(), "c9e0f1a2b3c4", import_state=marker, ownership=_ownership(attempt_id)
        )
        engine = pg_baseline.pg_sync_engine()
        try:
            with engine.connect() as conn:
                database_id = pg_baseline.read_database_identity(conn)
                receipt = pg_baseline.read_receipt(conn, attempt_id)
                assert receipt is not None and receipt["status"] == "IMPORTING"
                assert receipt["target_database_id"] == database_id
                assert inspect(conn).has_table(pg_baseline.IMPORT_STATE_TABLE)

            with engine.begin() as conn:
                pg_baseline.finalize_receipt_verified(
                    conn,
                    attempt_id,
                    table_counts={"users": 0},
                    table_digests={"users": "sha256-0"},
                    schema_fingerprint="fp-w1",
                )
            with engine.connect() as conn:
                receipt = pg_baseline.read_receipt(conn, attempt_id)
                assert receipt["status"] == RECEIPT_STATUS_VERIFIED
                assert receipt["table_counts"] == {"users": 0}
                assert not inspect(conn).has_table(pg_baseline.IMPORT_STATE_TABLE)

            # ownership 核对（正确 nonce/目标通过；错误拒绝由单测覆盖）
            with engine.connect() as conn:
                ok = pg_baseline.verify_receipt_ownership(
                    conn,
                    attempt_id,
                    ownership_nonce=receipt["ownership_nonce"],
                    target_database_id=database_id,
                )
                assert ok["status"] == RECEIPT_STATUS_VERIFIED
        finally:
            engine.dispose()
