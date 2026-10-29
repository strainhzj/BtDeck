"""activation/handoff/discard/restart 测试（W3-6/7/5/8；T04/T10/T11/T16 本地面）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.db_migration.activation import (
    SWITCH_MODE_B,
    ActivationError,
    ActivationService,
)
from app.services.db_migration.discard import DiscardError, DiscardTargetService
from app.services.db_migration.handoff import HandoffError, handoff_same_db_ack_sqlite, plan_handoff_same_db
from app.services.db_migration.journal import (
    COMMIT_PHASE_ACTIVATED_ACK,
    COMMIT_PHASE_COMMITTED,
    COMMIT_PHASE_NONE,
    COMMIT_PHASE_PREPARED,
    Journal,
    make_manifest_payload,
)
from app.services.db_migration.restart_adapter import hosting_capability

ATTEMPT = "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
DB_ID = "66666666-2222-3333-4444-555555555555"


def _prepared_attempt(tmp_path: Path) -> Journal:
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
            target={"dialect": "postgresql", "database_id": DB_ID, "host": "pg"},
            tool_version="2.0.0",
            digest_version="btdeck-canonical-v1",
            objects=["public.torrents"],
        ),
    )
    return journal


class TestActivationCommitProtocol:
    def _service(self, tmp_path, ack_calls=None, exits=None):
        ack_calls = ack_calls if ack_calls is not None else []
        exits = exits if exits is not None else []
        return ActivationService(
            str(tmp_path),
            yaml_path=str(tmp_path / "config.yaml"),
            target_ack_writer=lambda aid, gen: ack_calls.append((aid, gen)),
            restart_scheduler=lambda info: exits.append(info) or True,
        )

    def test_prepare_commit_order_and_idempotent_redo(self, tmp_path):
        _prepared_attempt(tmp_path)
        svc = self._service(tmp_path)
        # 1. PREPARED：候选/前代先持久
        prepared = svc.prepare_switch(
            ATTEMPT, mode=SWITCH_MODE_B,
            candidate_active={"dialect": "postgresql", "expected_database_id": DB_ID},
            identity={"generation": "g1"},
        )
        assert prepared.commit_phase == COMMIT_PHASE_PREPARED
        manifest = svc.manifest(ATTEMPT)
        assert manifest["candidate_config_digest"] and manifest["prior_config_digest"]
        # 候选 0600
        cand = Path(manifest.get("candidate_path") or tmp_path / "db-migration" / "attempts"
                    / ATTEMPT.rsplit("/", 1)[1] / "candidate-config.yaml")
        assert cand.exists() and cand.stat().st_mode & 0o777 == 0o600
        # 2. COMMIT：先 COMMITTED 再发布 config + RESTART_PENDING
        acks: list = []
        exits: list = []
        result = ActivationService(
            str(tmp_path), yaml_path=str(tmp_path / "config.yaml"),
            target_ack_writer=lambda a, g: acks.append(g),
            restart_scheduler=lambda i: exits.append(i) or True,
        ).commit_switch(ATTEMPT)
        assert result["commitPhase"] == COMMIT_PHASE_COMMITTED
        assert result["configPublished"] is True
        control = Journal(str(tmp_path)).read_control()
        assert control["restart_pending"] is True and control["pending_attempt"] == ATTEMPT
        import yaml as _yaml

        published = _yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
        assert published["database"]["active"]["dialect"] == "postgresql"
        # COMMITTED 决定已持久（manifest 单向推进）
        assert Journal(str(tmp_path)).read_manifest(ATTEMPT)["commit_phase"] == COMMIT_PHASE_COMMITTED
        # 3. 幂等 redo：config_published 不再重写
        redo = ActivationService(
            str(tmp_path), yaml_path=str(tmp_path / "config.yaml"),
            target_ack_writer=lambda a, g: None, restart_scheduler=lambda i: False,
        )
        outcome = redo.redo_pending_activation()
        assert outcome and outcome["awaitingTargetAck"] is True

    def test_commit_before_prepare_rejected(self, tmp_path):
        _prepared_attempt(tmp_path)
        svc = self._service(tmp_path)
        with pytest.raises(ActivationError, match="尚未 PREPARED"):
            svc.commit_switch(ATTEMPT)

    def test_complete_activation_target_ack_first(self, tmp_path):
        _prepared_attempt(tmp_path)
        svc = self._service(tmp_path)
        svc.prepare_switch(ATTEMPT, mode=SWITCH_MODE_B, candidate_active={"dialect": "postgresql"}, identity={})
        order: list = []

        def ack(aid, gen):
            order.append("target-ack")

        svc2 = ActivationService(
            str(tmp_path), yaml_path=str(tmp_path / "config.yaml"),
            target_ack_writer=ack, restart_scheduler=lambda i: False,
        )
        svc2.commit_switch(ATTEMPT)

        def archive(aid):
            order.append("archive")
            return 0

        out = ActivationService(
            str(tmp_path), yaml_path=str(tmp_path / "config.yaml"),
            target_ack_writer=lambda a, g: order.append("target-ack"),
            restart_scheduler=lambda i: False,
        ).complete_activation(ATTEMPT, archive_audit=archive)
        assert out["commitPhase"] == COMMIT_PHASE_ACTIVATED_ACK
        assert order == ["target-ack", "archive"]  # 目标 ACK 先于本地/归档
        assert Journal(str(tmp_path)).read_control()["restart_pending"] is False
        # 幂等重放
        again = ActivationService(
            str(tmp_path), yaml_path=str(tmp_path / "config.yaml"),
            target_ack_writer=lambda a, g: order.append("unexpected"),
            restart_scheduler=lambda i: False,
        ).complete_activation(ATTEMPT)
        assert again.get("idempotent") is True and order == ["target-ack", "archive"]

    def test_complete_requires_committed(self, tmp_path):
        _prepared_attempt(tmp_path)
        svc = self._service(tmp_path)
        with pytest.raises(ActivationError):
            svc.complete_activation(ATTEMPT)


class TestHandoffSameDb:
    def test_plan_requires_active(self, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path), raising=False)
        with pytest.raises(HandoffError, match="无受管 active"):
            plan_handoff_same_db(str(tmp_path))

    def test_env_mismatch_rejected(self, tmp_path, monkeypatch):
        import yaml as _yaml

        from app.core.config import settings

        monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path), raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            _yaml.dump(
                {
                    "database": {
                        "active": {
                            "version": 1,
                            "generation": "11111111-2222-3333-4444-555555555555",
                            "dialect": "sqlite",
                            "sqlite_path": str(tmp_path / "final.sqlite"),
                            "postgresql": None,
                            "expected_database_id": DB_ID,
                            "receipt_attempt_id": ATTEMPT,
                            "revision_at_import": "rev1",
                            "switched_at": "2026-10-28T00:00:00+00:00",
                            "switched_by": "admin",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("DB_TYPE", "postgresql")
        monkeypatch.setenv("DB_HOST", "other")
        with pytest.raises(HandoffError, match="不同数据库|mismatch|异库"):
            plan_handoff_same_db(str(tmp_path))

    def test_ack_sqlite_single_connection_cas(self, tmp_path):
        import sqlite3

        db = tmp_path / "h.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE bt_database_migration_receipts (attempt_id TEXT, status TEXT, activation_generation TEXT, created_at TEXT)")
        conn.execute("INSERT INTO bt_database_migration_receipts VALUES ('a1','ACTIVATED','g-old','2026-01-01')")
        conn.commit()
        conn.close()
        # 旧代次不符 → False（保持维护）
        assert handoff_same_db_ack_sqlite(str(db), expected_old_generation="g-wrong", new_generation="g-new") is False
        assert handoff_same_db_ack_sqlite(str(db), expected_old_generation="g-old", new_generation="g-new") is True
        # 幂等：已是新代次直接成功
        assert handoff_same_db_ack_sqlite(str(db), expected_old_generation="g-old", new_generation="g-new") is True


class TestDiscard:
    def test_authorize_double_confirm_and_locks(self, tmp_path):
        journal = _prepared_attempt(tmp_path)
        manifest = journal.read_manifest(ATTEMPT)
        manifest["ownership_nonce"] = "nonce-1"
        journal.write_manifest(ATTEMPT, manifest, expect_state_version=manifest["state_version"])
        svc = DiscardTargetService(str(tmp_path))
        token = f"discard:{ATTEMPT}:{DB_ID[:8]}"
        ok = svc.authorize(ATTEMPT, ownership_nonce="nonce-1", database_id=DB_ID, confirm_token=token)
        assert ok["objects"] == ["public.torrents"]
        with pytest.raises(DiscardError, match="nonce"):
            svc.authorize(ATTEMPT, ownership_nonce="bad", database_id=DB_ID, confirm_token=token)
        with pytest.raises(DiscardError, match="确认"):
            svc.authorize(ATTEMPT, ownership_nonce="nonce-1", database_id=DB_ID, confirm_token="wrong")
        with pytest.raises(DiscardError, match="database_id"):
            svc.authorize(ATTEMPT, ownership_nonce="nonce-1", database_id="other-id", confirm_token=token)

    def test_committed_rejects_discard(self, tmp_path):
        journal = _prepared_attempt(tmp_path)
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_PREPARED)
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_PREPARED, new=COMMIT_PHASE_COMMITTED)
        svc = DiscardTargetService(str(tmp_path))
        with pytest.raises(DiscardError, match="禁 discard"):
            svc.authorize(ATTEMPT, ownership_nonce="n", database_id=DB_ID, confirm_token="x")

    def test_sqlite_only_owned_artifacts(self, tmp_path):
        journal = _prepared_attempt(tmp_path)
        staging = tmp_path / "db-migration" / "attempts" / ATTEMPT.rsplit("/", 1)[1] / "staging.sqlite"
        staging.parent.mkdir(parents=True, exist_ok=True)
        staging.write_bytes(b"staged")
        svc = DiscardTargetService(str(tmp_path))
        out = svc.discard_sqlite(ATTEMPT, staging_path=str(staging), final_path=None)
        assert out["removed"] == [str(staging)]
        # 非专属路径拒绝
        evil = tmp_path / "app.db"
        evil.write_bytes(b"src")
        with pytest.raises(DiscardError, match="非本次专属"):
            svc.discard_sqlite(ATTEMPT, staging_path=str(evil), final_path=None)


class TestRestartAdapter:
    def test_capability_matrix(self, monkeypatch):
        monkeypatch.delenv("BTD_MIGRATION_MANAGED_RESTART", raising=False)
        cap = hosting_capability()
        assert cap["autoRestartCapable"] is False  # 默认无 opt-in → 不自动退出
        monkeypatch.setenv("BTD_MIGRATION_MANAGED_RESTART", "1")
        cap = hosting_capability(opt_in=True)
        assert cap["optIn"] is True
        # hosting unknown/pid1 由环境决定——只验证 opt-in 门控逻辑生效
        assert cap["autoRestartCapable"] == (cap["hosting"] in {"systemd", "docker"} and not cap["pid1Self"])
