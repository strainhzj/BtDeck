"""journal 仓储测试（database-migration-ui W3-1，PLANS §4.2/§7；评审修正落实）。

覆盖：
- 原子写纪律：tmp→fsync→replace→父目录 fsync；中断不产生半成品（monkeypatch
  + 真实子进程 SIGKILL 中途杀写者，T04 实际中断要求）；
- 部署互斥锁：进程内重入、跨进程互斥（子进程持锁 → JournalConflict）；
- control 代次 CAS / manifest state_version CAS 冲突；
- commit_phase 单向（回退/跳级拒；同值幂等）；
- intent 兼容投影与权威分离：journal COMMITTED 而 intent 残留 PREPARING →
  stale_intent + committed_pending_restart（绝不放回 NORMAL）；controller
  exit_maintenance 被 journal 守卫拒绝；
- 审计归档：快照令牌（回放期间追加不丢尾部）、cursor 推进；
- 损坏 fail-closed；目录权限 0700/文件 0600。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.services.db_migration.journal import (
    COMMIT_PHASE_ACTIVATED_ACK,
    COMMIT_PHASE_COMMITTED,
    COMMIT_PHASE_NONE,
    COMMIT_PHASE_PREPARED,
    CommitPhaseError,
    Journal,
    JournalConflict,
    JournalCorrupted,
    atomic_write_json,
    deployment_lock,
    make_manifest_payload,
)
from app.services.db_migration.local_audit import MaintenanceLocalAudit
from app.services.db_migration.maintenance import MaintenanceController

ATTEMPT = "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def _make_manifest(attempt: str = ATTEMPT, epoch: str = "epoch-1") -> dict:
    return make_manifest_payload(
        attempt_id=attempt,
        direction="sqlite-to-pg",
        operation_kind="MIGRATE",
        epoch=epoch,
        source={"dialect": "sqlite", "database_id": "src-id"},
        target={"dialect": "postgresql", "database_id": "tgt-id"},
        tool_version="2.0.0",
        digest_version="btdeck-canonical-v1",
        objects=["public.torrents"],
    )


@pytest.fixture
def journal(tmp_path) -> Journal:
    j = Journal(tmp_path)
    j.write_control(lambda c: c, deployment_id="deploy-1")
    return j


class TestAtomicDiscipline:
    def test_replace_failure_leaves_old_intact_and_no_tmp(self, tmp_path, monkeypatch):
        target = tmp_path / "control.json"
        target.write_text(json.dumps({"generation": "g1"}), encoding="utf-8")
        real_replace = os.replace

        def boom(src, dst, *a, **kw):  # noqa: ANN001
            raise OSError("ENOSPC: replace failed")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            atomic_write_json(target, {"generation": "g2"})
        monkeypatch.setattr(os, "replace", real_replace)
        assert json.loads(target.read_text(encoding="utf-8"))["generation"] == "g1"
        assert list(tmp_path.glob(".*tmp*")) == []

    def test_fsync_called_on_file_and_parent(self, tmp_path, monkeypatch):
        calls: list[str] = []
        real_fsync = os.fsync

        def spy(fd, *a, **kw):  # noqa: ANN001
            calls.append(str(fd))
            return real_fsync(fd)

        monkeypatch.setattr(os, "fsync", spy)
        from app.services.db_migration.journal import atomic_write_json

        atomic_write_json(tmp_path / "x.json", {"a": 1})
        assert len(calls) >= 2  # 文件 + 父目录

    def test_subprocess_sigkill_midwrite_recovers_old_or_new(self, tmp_path):
        """T04 实际中断：子进程循环写 control，父进程随机 SIGKILL，终态必为完整 JSON。"""
        target = tmp_path / "control.json"
        target.write_text(json.dumps({"generation": "g0"}), encoding="utf-8")
        script = textwrap.dedent(
            """
            import json, sys, time
            sys.path.insert(0, {root!r})
            from app.services.db_migration.journal import atomic_write_json
            i = 0
            while True:
                atomic_write_json({target!r}, {{"generation": "g%d" % i}})
                i += 1
            """.format(
                root=str(Path(__file__).resolve().parents[2]), target=str(target)
            )
        )
        proc = subprocess.Popen([sys.executable, "-c", script])
        import signal
        import time as _t

        _t.sleep(0.15)
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=5)
        data = json.loads(target.read_text(encoding="utf-8"))  # 要么旧值要么新值，绝无半行
        assert data["generation"].startswith("g")
        # SIGKILL 窗口可能残留 tmp 点文件（finally 未及运行）——必须可辨识
        # （点前缀+随机后缀，绝不与正式文件名混潜），且不影响后续写入
        for residue in tmp_path.glob(".*tmp*"):
            assert residue.name.startswith(".") and ".tmp" in residue.name
        atomic_write_json(target, {"generation": "g-final"})
        assert json.loads(target.read_text(encoding="utf-8"))["generation"] == "g-final"


class TestDeploymentLock:
    def test_reentrant_in_process(self, tmp_path):
        with deployment_lock(tmp_path):
            with deployment_lock(tmp_path):
                pass

    def test_cross_process_exclusive(self, tmp_path):
        holder = textwrap.dedent(
            """
            import fcntl, os, sys, time
            path = sys.argv[1]
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            print("held", flush=True)
            time.sleep(3)
            """
        )
        lock_path = tmp_path / "db-migration" / ".journal.lock"
        lock_path.parent.mkdir(parents=True)
        proc = subprocess.Popen([sys.executable, "-c", holder, str(lock_path)], stdout=subprocess.PIPE)
        assert proc.stdout.readline().decode().strip() == "held"
        with pytest.raises(JournalConflict):
            with deployment_lock(tmp_path):
                pass
        proc.kill()
        proc.wait(timeout=5)


class TestControlCas:
    def test_generation_cas_conflict(self, journal):
        with pytest.raises(JournalConflict):
            journal.write_control(lambda c: {**c, "restart_pending": True}, expect_generation="wrong-gen")

    def test_generation_cas_success_bumps(self, journal):
        gen = journal.read_control()["generation"]
        out = journal.write_control(lambda c: {**c, "restart_pending": True}, expect_generation=gen)
        assert out["restart_pending"] is True

    def test_corrupt_control_fail_closed(self, journal):
        journal.control_path.write_text("{broken", encoding="utf-8")
        with pytest.raises(JournalCorrupted):
            journal.write_control(lambda c: c)

    def test_missing_control_requires_deployment_id(self, tmp_path):
        with pytest.raises(Exception):
            Journal(tmp_path).write_control(lambda c: c)


class TestManifestCas:
    def test_write_and_state_version_bump(self, journal):
        first = journal.write_manifest(ATTEMPT, _make_manifest())
        assert first["state_version"] == 1
        payload = _make_manifest()
        payload["progress"] = {"phase": "import", "done": 1}
        second = journal.write_manifest(ATTEMPT, payload, expect_state_version=1)
        assert second["state_version"] == 2

    def test_state_version_conflict(self, journal):
        journal.write_manifest(ATTEMPT, _make_manifest())
        with pytest.raises(JournalConflict):
            journal.write_manifest(ATTEMPT, _make_manifest(), expect_state_version=99)

    def test_attempt_id_mismatch_rejected(self, journal):
        payload = _make_manifest()
        payload["attempt_id"] = "sqlite-to-pg/11111111-2222-3333-4444-555555555555"
        with pytest.raises(Exception):
            journal.write_manifest(ATTEMPT, payload)

    def test_path_traversal_rejected(self, journal):
        with pytest.raises(Exception):
            journal.manifest_path("../evil/uuid")


class TestCommitPhase:
    def test_forward_and_idempotent(self, journal):
        journal.write_manifest(ATTEMPT, _make_manifest())
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_PREPARED)
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_PREPARED, new=COMMIT_PHASE_COMMITTED)
        # 幂等重放
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_COMMITTED, new=COMMIT_PHASE_COMMITTED)
        manifest = journal.read_manifest(ATTEMPT)
        assert manifest["commit_phase"] == COMMIT_PHASE_COMMITTED

    def test_backward_rejected(self, journal):
        journal.write_manifest(ATTEMPT, _make_manifest())
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_PREPARED)
        with pytest.raises(CommitPhaseError):
            journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_PREPARED, new=COMMIT_PHASE_NONE)

    def test_skip_rejected(self, journal):
        journal.write_manifest(ATTEMPT, _make_manifest())
        with pytest.raises(CommitPhaseError):
            journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_ACTIVATED_ACK)

    def test_mismatch_rejected(self, journal):
        journal.write_manifest(ATTEMPT, _make_manifest())
        with pytest.raises(CommitPhaseError):
            journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_COMMITTED, new=COMMIT_PHASE_ACTIVATED_ACK)


class TestIntentAuthority:
    def _commit(self, journal: Journal) -> None:
        journal.write_manifest(ATTEMPT, _make_manifest())
        journal.write_control(lambda c: {**c, "pending_attempt": ATTEMPT})
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_PREPARED)
        journal.advance_commit_phase(ATTEMPT, expected=COMMIT_PHASE_PREPARED, new=COMMIT_PHASE_COMMITTED)

    def test_committed_with_stale_intent_never_normal(self, journal):
        """评审修正核心：journal 已 COMMITTED、intent 残留 PREPARING → 绝不放回 NORMAL。"""
        self._commit(journal)
        # 崩溃窗口：intent 投影仍是 PREPARING（controller 未来得及更新）
        journal.write_intent_projection({"version": 1, "state": "PREPARING", "attempt_id": ATTEMPT, "epoch": "epoch-1"})
        authority = journal.evaluate_intent_authority()
        assert authority.committed_pending_restart is True
        assert authority.may_return_normal is False
        assert authority.verdict == "stale_intent"

    def test_no_intent_committed_still_blocks_normal(self, journal):
        self._commit(journal)
        authority = journal.evaluate_intent_authority()
        assert authority.committed_pending_restart is True
        assert authority.verdict == "no_intent"

    def test_preparing_pending_consistent(self, journal, tmp_path):
        journal.write_manifest(ATTEMPT, _make_manifest())
        journal.write_control(lambda c: {**c, "pending_attempt": ATTEMPT})
        journal.write_intent_projection({"version": 1, "state": "DRAINING", "attempt_id": ATTEMPT, "epoch": "epoch-1"})
        authority = journal.evaluate_intent_authority()
        assert authority.committed_pending_restart is False
        assert authority.may_return_normal is True

    def test_controller_exit_guarded_by_journal(self, journal, tmp_path):
        """controller 运行视图不得撤销 journal 持久 COMMITTED 决定。"""
        self._commit(journal)
        controller = MaintenanceController(str(tmp_path))
        controller.enter_maintenance_boot(attempt_id=ATTEMPT)
        with pytest.raises(Exception, match="COMMITTED"):
            controller.exit_maintenance()

    def test_controller_exit_allowed_without_commit(self, tmp_path):
        controller = MaintenanceController(str(tmp_path))
        controller.enter_maintenance_boot()
        controller.exit_maintenance()  # 无 journal 证据 → 正常退出
        assert controller.status().state == "NORMAL"


class TestControllerIntentProjection:
    def test_intent_written_via_journal_format_compatible(self, tmp_path):
        controller = MaintenanceController(str(tmp_path))
        controller.begin_prepare(attempt_id=ATTEMPT, non_waitable_kinds=[])
        intent_path = tmp_path / "db-migration" / "maintenance-intent.json"
        assert intent_path.exists()
        data = json.loads(intent_path.read_text(encoding="utf-8"))
        assert data["state"] == "PREPARING"
        assert data["attempt_id"] == ATTEMPT
        controller.abort_prepare(reason="test")
        assert not intent_path.exists()


class TestAuditArchiveToken:
    def test_snapshot_and_clear_if_unchanged(self, tmp_path):
        audit = MaintenanceLocalAudit(str(tmp_path))
        audit.audit_event("gate_change", action="boot", outcome="ok")
        rows, token = audit.snapshot_for_archive()
        assert len(rows) == 1
        assert audit.clear_if_unchanged(token) is True
        assert not audit.path.exists()

    def test_clear_refused_when_appended_during_archive(self, tmp_path):
        """评审修正：归档事务期间新追加 → 不清理（不丢尾部）。"""
        audit = MaintenanceLocalAudit(str(tmp_path))
        audit.audit_event("gate_change", action="boot", outcome="ok")
        rows, token = audit.snapshot_for_archive()
        # 归档事务期间新事件追加
        audit.audit_event("gate_change", action="resume", outcome="ok")
        assert audit.clear_if_unchanged(token) is False
        remaining = audit.replay_events()
        assert len(remaining) == 2  # 尾部保留，下轮 cursor 归档

    def test_journal_archive_cursor_roundtrip(self, tmp_path):
        journal = Journal(str(tmp_path))
        assert journal.read_archive_cursor() is None
        journal.advance_archive_cursor("event-9")
        assert journal.read_archive_cursor() == "event-9"


class TestPermissionsAndDiagnose:
    def test_permissions_0700_0600(self, journal, tmp_path):
        journal.write_manifest(ATTEMPT, _make_manifest())
        base = tmp_path / "db-migration"
        assert (base.stat().st_mode & 0o777) == 0o700
        assert (base / "control.json").stat().st_mode & 0o777 == 0o600
        attempt_dir = base / "attempts" / ATTEMPT.rsplit("/", 1)[1]
        assert attempt_dir.stat().st_mode & 0o777 == 0o700
        assert (attempt_dir / "manifest.json").stat().st_mode & 0o777 == 0o600

    def test_diagnose_report(self, journal):
        journal.write_manifest(ATTEMPT, _make_manifest())
        journal.write_control(lambda c: {**c, "pending_attempt": ATTEMPT})
        report = journal.diagnose()
        assert report["control"]["ok"] is True
        assert report["control"]["pending_attempt"] == ATTEMPT
        assert report["intent_authority"]["commit_phase"] == COMMIT_PHASE_NONE
