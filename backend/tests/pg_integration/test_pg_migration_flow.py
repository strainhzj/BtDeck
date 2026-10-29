# -*- coding: utf-8 -*-
"""真 PG 迁移控制面链路（database-migration-ui W5-1，PLANS §11 T18/T19/T12 实库实证）。

需要真实 PostgreSQL（regression pg-integration job 提供 DB_TYPE=postgresql +
BTDECK_PG_TEST_ADMIN_DSN；本地无 PG 时整文件 skip——skip 不计通过，证据以
CI 实际执行为准）。

覆盖：
- test-connection 实库三态：可达+版本+空库 / 错凭据拒 / 非空库 targetEmpty=false；
- discard 实库（§6.5）：授权双确认 → 逐对象 DROP 无 CASCADE；外部内容拒；
  清理后非空隔离拒重建；
- activation 提交→ACK 全链路实库：PREPARED（候选/前代持久）→ COMMITTED
  （config.yaml 原子发布）→ 目标 ACK 写真 PG receipt（activated_at）→
  ACTIVATED_ACK 幂等重放；RESTART_PENDING 清除；
- handoff 同库交接计划（PG active）：env 候三态 match/unspecified/mismatch。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

from app.services.db_migration.activation import SWITCH_MODE_B, ActivationService
from app.services.db_migration.discard import DiscardError, DiscardTargetService
from app.services.db_migration.handoff import HandoffError, plan_handoff_same_db
from app.services.db_migration.journal import Journal, make_manifest_payload

pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "sqlite") != "postgresql" or not os.getenv("BTDECK_PG_TEST_ADMIN_DSN", ""),
    reason="PG 迁移链路集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)

ATTEMPT = "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
DB_ID = "66666666-2222-3333-4444-555555555555"


@pytest.fixture
def pg_url(fresh_pg_db: str) -> Iterator[str]:
    """指向本用例专属库的完整 DSN（admin 凭据直连）。

    admin DSN 自带管理库名（CI 为 /postgres）——必须经 make_url 替换 database
    分量，字符串拼接会产生 "postgres/btdeck_test_x" 形态的非法库名。
    """
    from sqlalchemy.engine.url import make_url

    url = make_url(os.environ["BTDECK_PG_TEST_ADMIN_DSN"]).set(database=fresh_pg_db)
    yield url.render_as_string(hide_password=False)
    engine = create_engine(url, poolclass=NullPool)
    with engine.begin() as conn:
        for table in ("t_a", "t_b", "t_foreign", "bt_database_migration_receipts"):
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))
    engine.dispose()


def _dsn_parts() -> Dict[str, Any]:
    u = make_url(os.environ["BTDECK_PG_TEST_ADMIN_DSN"])
    return {
        "host": u.host or "localhost",
        "port": u.port or 5432,
        "user": u.username or "",
        "password": u.password or "",
    }


def _attempt(tmp_path: Path) -> Journal:
    journal = Journal(str(tmp_path))
    journal.write_control(lambda c: {**c, "pending_attempt": ATTEMPT}, deployment_id="d1")
    journal.write_manifest(
        ATTEMPT,
        make_manifest_payload(
            attempt_id=ATTEMPT,
            direction="sqlite-to-pg",
            operation_kind="MIGRATE",
            epoch="epoch-1",
            source={"dialect": "sqlite", "database_id": "src"},
            target={"dialect": "postgresql", "database_id": DB_ID, **_dsn_parts()},
            tool_version="2.0.0",
            digest_version="btdeck-canonical-v1",
            objects=["t_a", "t_b"],
        ),
    )
    manifest = journal.read_manifest(ATTEMPT)
    manifest["ownership_nonce"] = "nonce-1"
    journal.write_manifest(ATTEMPT, manifest, expect_state_version=manifest["state_version"])
    return journal


class TestTestConnectionRealPg:
    @pytest.mark.asyncio
    async def test_reachable_version_and_empty(self, fresh_pg_db: str) -> None:
        from app.api.endpoints.database import TestConnectionRequest, test_connection

        parts = _dsn_parts()
        resp = await test_connection(
            TestConnectionRequest(
                dialect="postgresql",
                postgresql={**parts, "database": fresh_pg_db, "sslmode": "disable"},
            )
        )
        assert resp.status == "success"
        data = resp.data  # type: ignore[attr-defined]
        assert data["reachable"] is True
        assert data["versionOk"] is True  # CI 提供 PG≥16
        assert data["targetEmpty"] is True

    @pytest.mark.asyncio
    async def test_bad_credentials_rejected(self, fresh_pg_db: str) -> None:
        from app.api.endpoints.database import TestConnectionRequest, test_connection

        parts = _dsn_parts()
        resp = await test_connection(
            TestConnectionRequest(
                dialect="postgresql",
                postgresql={**parts, "password": "definitely-wrong", "database": fresh_pg_db, "sslmode": "disable"},
            )
        )
        assert resp.status == "error"
        assert "连接失败" in (resp.msg or "")

    @pytest.mark.asyncio
    async def test_non_empty_target(self, fresh_pg_db: str, pg_url: str) -> None:
        from app.api.endpoints.database import TestConnectionRequest, test_connection

        engine = create_engine(pg_url, poolclass=NullPool)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t_probe (k TEXT)"))
        engine.dispose()
        parts = _dsn_parts()
        resp = await test_connection(
            TestConnectionRequest(
                dialect="postgresql",
                postgresql={**parts, "database": fresh_pg_db, "sslmode": "disable"},
            )
        )
        assert resp.status == "success"
        assert resp.data["targetEmpty"] is False  # type: ignore[attr-defined]


class TestDiscardRealPg:
    @staticmethod
    def _owner_check(conn: Any, objects: List[str]) -> List[str]:
        """清单对象 marker 核验：无 btdeck 专属 COMMENT 视为外部内容。"""
        foreign: List[str] = []
        for obj in objects:
            comment = conn.execute(text("SELECT obj_description(:t::regclass, 'pg_class')"), {"t": obj}).scalar()
            if (comment or "") != "btdeck-migration":
                foreign.append(obj)
        return foreign

    def test_foreign_content_rejected_then_clean_discard(self, tmp_path: Path, pg_url: str) -> None:
        _attempt(tmp_path)
        engine = create_engine(pg_url, poolclass=NullPool)
        with engine.begin() as conn:
            for t in ("t_a", "t_b"):
                conn.execute(text(f'CREATE TABLE "{t}" (k TEXT PRIMARY KEY)'))
        svc = DiscardTargetService(str(tmp_path))
        token = f"discard:{ATTEMPT}:{DB_ID[:8]}"
        plan = svc.authorize(ATTEMPT, ownership_nonce="nonce-1", database_id=DB_ID, confirm_token=token)
        assert plan["objects"] == ["t_a", "t_b"]
        # 外部内容（无 marker）→ 拒绝且不动库
        with pytest.raises(DiscardError, match="外部|拒绝"):
            svc.discard_pg(ATTEMPT, engine=engine, objects=plan["objects"], listed_owner_check=self._owner_check)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM t_a")).scalar() == 0  # 表仍在
        # 打 marker → 逐对象 DROP、禁 CASCADE、库复归空
        with engine.begin() as conn:
            for t in ("t_a", "t_b"):
                conn.execute(text(f"COMMENT ON TABLE \"{t}\" IS 'btdeck-migration'"))
        result = svc.discard_pg(ATTEMPT, engine=engine, objects=plan["objects"], listed_owner_check=self._owner_check)
        assert result["empty"] is True and result["discarded_objects"] == ["t_a", "t_b"]
        assert _attempt.__name__  # 静默 lint：保持引用
        engine.dispose()

    def test_leftover_after_discard_isolated(self, tmp_path: Path, pg_url: str) -> None:
        _attempt(tmp_path)
        engine = create_engine(pg_url, poolclass=NullPool)
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE "t_a" (k TEXT)'))
            conn.execute(text('CREATE TABLE "t_b" (k TEXT)'))
            conn.execute(text("CREATE TABLE t_foreign (k TEXT)"))  # 非清单对象
            for t in ("t_a", "t_b"):
                conn.execute(text(f"COMMENT ON TABLE \"{t}\" IS 'btdeck-migration'"))
        svc = DiscardTargetService(str(tmp_path))
        with pytest.raises(DiscardError, match="非空|隔离"):
            svc.discard_pg(
                ATTEMPT,
                engine=engine,
                objects=["t_a", "t_b"],
                listed_owner_check=self._owner_check,
            )
        engine.dispose()


class TestActivationRealPg:
    def test_commit_and_target_ack_roundtrip(
        self, tmp_path: Path, pg_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.database as database_module

        journal = _attempt(tmp_path)
        # 目标库建 receipt 表（activated_at 为空 → 待 ACK）
        engine = create_engine(pg_url, poolclass=NullPool)
        with engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE bt_database_migration_receipts " "(attempt_id TEXT PRIMARY KEY, activated_at TEXT)")
            )
            conn.execute(text("INSERT INTO bt_database_migration_receipts VALUES (:aid, NULL)"), {"aid": ATTEMPT})
        monkeypatch.setattr(database_module, "build_database_url", lambda: pg_url, raising=True)
        svc = ActivationService(str(tmp_path), yaml_path=str(tmp_path / "config.yaml"))
        # PREPARED：候选/前代先持久
        prepared = svc.prepare_switch(
            ATTEMPT,
            mode=SWITCH_MODE_B,
            candidate_active={"dialect": "postgresql", "expected_database_id": DB_ID},
            identity={"generation": "g1"},
        )
        assert prepared.commit_phase == "PREPARED"
        # COMMITTED：fsync 决定先于发布；发布 RESTART_PENDING
        committed = svc.commit_switch(ATTEMPT)
        assert committed["configPublished"] is True and committed["restartScheduled"] is False
        assert (journal.read_control() or {}).get("restart_pending") is True
        # 目标 ACK（真 PG receipt）先 → 本地 ACTIVATED_ACK 后 → 清 RESTART_PENDING
        done = svc.complete_activation()
        assert done["commitPhase"] == "ACTIVATED_ACK"
        assert (journal.read_control() or {}).get("restart_pending") is False
        with engine.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT activated_at IS NOT NULL FROM bt_database_migration_receipts WHERE attempt_id = :a"),
                    {"a": ATTEMPT},
                ).scalar()
                is True
            )
        # 幂等重放
        replay = svc.complete_activation()
        assert replay.get("idempotent") is True
        engine.dispose()

    def test_handoff_plan_pg_env_states(
        self, fresh_pg_db: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import yaml as _yaml

        from app.core.config import settings

        parts = _dsn_parts()
        monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path), raising=False)
        active = {
            "version": 1,
            "generation": "11111111-2222-3333-4444-555555555555",
            "dialect": "postgresql",
            "sqlite_path": None,
            "postgresql": {
                "host": parts["host"],
                "port": parts["port"],
                "user": parts["user"],
                "database": fresh_pg_db,
                "sslmode": "disable",
            },
            "expected_database_id": DB_ID,
            "receipt_attempt_id": ATTEMPT,
            "revision_at_import": "rev1",
            "switched_at": "2026-10-28T00:00:00+00:00",
            "switched_by": "admin",
        }
        (tmp_path / "config.yaml").write_text(_yaml.dump({"database": {"active": active}}), encoding="utf-8")
        # env 未声明 → unspecified（待填）
        monkeypatch.delenv("DB_TYPE", raising=False)
        plan = plan_handoff_same_db(str(tmp_path))
        assert plan["envCandidate"]["state"] == "unspecified"
        # env 指向同一当前服务库 → match
        monkeypatch.setenv("DB_TYPE", "postgresql")
        monkeypatch.setenv("DB_HOST", str(parts["host"]))
        monkeypatch.setenv("DB_PORT", str(parts["port"]))
        monkeypatch.setenv("DB_NAME", fresh_pg_db)
        plan = plan_handoff_same_db(str(tmp_path))
        assert plan["envCandidate"]["state"] == "match"
        assert plan["kind"] == "HANDOFF_SAME_DB"
        # env 异库 → 拒（引导新迁移）
        monkeypatch.setenv("DB_NAME", "other-db")
        with pytest.raises(HandoffError, match="不同数据库|异库"):
            plan_handoff_same_db(str(tmp_path))
