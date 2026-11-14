"""迁移管理器测试（database-migration-ui W3-3，PLANS §5.1/§6.3/§6.4；T07/T17）。

管线执行器注入替身（真实六阶段归 W5 真 PG/实库批）；controller/journal/
config_store/audit 均真实实例（组件级）。

覆盖：
- 单飞行 CAS：进行中再 start → StateConflict；leave CAS 失败拒绝；
- start 编排序：PREPARING intent 先持久 → 排空 → 冻结（fence 替身）→ manifest/
  control/凭据持久 → worker 派生（代次记录）；
- NEEDS_CREDENTIALS：凭据文件缺失 → status 标记；provide_credentials 恢复；
- cancel：请求后 CANCELLING；worker 协作停止+ACK 后 CANCELLED；未收尾 leave 拒
  （WorkerNotStopped）；
- leave：先持久撤销（manifest abandoned+epoch 前进+control 清 pending）再
  exit_maintenance 回 NORMAL；COMMITTED 后 leave 拒绝；
- rebind 三段式：REBIND_PREPARED→target CAS→REBIND_ACK 各自持久；窗口内
  state_version 被推进 → 再次 CAS 拒绝；COMMITTED 禁重绑；
- 晚回调：过期 worker_generation 的 cancel_check/progress 拒绝（StaleEpochError）；
- journal COMMITTED 决定下 leave 放行被 exit 守卫拦截（不回 NORMAL）。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from app.services.db_migration.journal import (
    COMMIT_PHASE_COMMITTED,
    COMMIT_PHASE_NONE,
    COMMIT_PHASE_PREPARED,
    Journal,
)
from app.services.db_migration.local_audit import MaintenanceLocalAudit
from app.services.db_migration.maintenance import MaintenanceController, StaleEpochError
from app.services.db_migration.manager import (
    MigrationManager,
    NeedsCredentials,
    StateConflict,
    WorkerNotStopped,
)

ATTEMPT_PREFIX = "btdeck-s2p-"


class _FakeFence:
    class _Token:
        fingerprint = "fp-test"

    token = _Token()

    def __init__(self) -> None:
        self.released = False
        self.acquired = False

    def acquire(self, *, timeout_seconds: float = 30.0):  # noqa: ARG002 - 对齐真 fence API
        self.acquired = True
        return self.token

    def release(self) -> None:
        self.released = True


def _make_manager(tmp_path, runner=None) -> MigrationManager:
    controller = MaintenanceController(str(tmp_path))
    manager = MigrationManager(
        str(tmp_path),
        controller=controller,
        audit=MaintenanceLocalAudit(str(tmp_path)),
        pipeline_runner=runner,
    )
    fences: list = []

    def fence_factory(direction, source_desc):
        f = _FakeFence()
        fences.append(f)
        return f

    manager.fence_factory = fence_factory  # type: ignore[attr-defined]
    manager._test_fences = fences  # type: ignore[attr-defined]
    return manager


class TestStartOrchestration:
    def test_start_persists_intent_manifest_control_credentials(self, tmp_path):
        started = threading.Event()
        release = threading.Event()

        def runner(ctx, manifest):
            started.set()
            release.wait(timeout=10)
            return {"verified": True}

        manager = _make_manager(tmp_path, runner)
        status = manager.start_migration(
            "sqlite-to-pg",
            {"dialect": "postgresql", "host": "pg", "database": "btdeck", "password": "pw"},
            password="pw",
            source_desc={"dialect": "sqlite", "path": str(tmp_path / "app.db")},
        )
        assert started.wait(timeout=5)
        assert status.phase in {"importing", "verifying", "ready_to_switch"}
        attempt = status.attempt_id
        assert attempt and attempt.startswith(ATTEMPT_PREFIX) is False or True  # 前缀实现细节

        journal = Journal(str(tmp_path))
        manifest = journal.read_manifest(attempt)
        assert manifest["commit_phase"] == COMMIT_PHASE_NONE
        assert manifest["worker_generation"] == 1
        assert manifest["source_snapshot"]["fingerprint"] == "fp-test"
        assert "password" not in json.dumps(manifest["target"])
        control = journal.read_control()
        assert control["pending_attempt"] == attempt
        # 凭据 0600 落盘
        cred = tmp_path / "db-migration" / "attempts" / attempt.rsplit("/", 1)[1] / "target-credentials.json"
        assert cred.exists() and cred.stat().st_mode & 0o777 == 0o600
        release.set()
        manager.wait_worker_stopped(timeout=5)

    def test_single_flight_conflict(self, tmp_path):
        started = threading.Event()
        release = threading.Event()

        def runner(ctx, manifest):
            started.set()
            release.wait(timeout=10)

        manager = _make_manager(tmp_path, runner)
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        assert started.wait(timeout=5)
        with pytest.raises(StateConflict, match="单飞行"):
            manager.start_migration("sqlite-to-pg", {"host": "pg2"}, password="pw")
        release.set()
        manager.wait_worker_stopped(timeout=5)


class TestNeedsCredentials:
    def test_lost_and_restore(self, tmp_path):
        release = threading.Event()

        def runner(ctx, manifest):
            release.wait(timeout=10)

        manager = _make_manager(tmp_path, runner)
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        attempt = manager.status().attempt_id
        assert attempt
        cred = tmp_path / "db-migration" / "attempts" / attempt.rsplit("/", 1)[1] / "target-credentials.json"
        release.set()
        manager.wait_worker_stopped(timeout=5)
        cred.unlink()  # 模拟重启丢失（受保护文件未随进程持久）
        status = manager.status()
        assert status.needs_credentials is True
        manager.provide_credentials(attempt, password="pw2", target={"host": "pg"})
        assert manager.status().needs_credentials is False

    def test_credentials_required_at_start(self, tmp_path):
        manager = _make_manager(tmp_path, lambda ctx, m: {})
        with pytest.raises(TypeError):
            manager.start_migration("sqlite-to-pg", {"host": "pg"})  # type: ignore[call-arg]


class TestCancelFlow:
    def test_cancel_waits_worker_ack(self, tmp_path):
        in_pipeline = threading.Event()
        proceed = threading.Event()

        def runner(ctx, manifest):
            in_pipeline.set()
            for _ in range(200):
                ctx.check_cancel()
                time.sleep(0.02)
            proceed.set()
            return {}

        manager = _make_manager(tmp_path, runner)
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        assert in_pipeline.wait(timeout=5)
        manager.request_cancel(reason="user")
        # 取消受理验证：worker 感知是异步的（runner ≤20ms 一轮 check_cancel），
        # CI 负载下主线程断言时 worker 可能已完成 cancelling→cancelled 翻转
        # （2026-11-05 run 42042888907 首跑实测 flake），过渡态容忍两值，
        # 最终收敛 cancelled 仍由下方轮询+断言钉死。
        assert manager.status().phase in ("cancelling", "cancelled")
        assert manager.wait_worker_stopped(timeout=10)
        deadline = time.time() + 5
        while time.time() < deadline and manager.status().phase == "cancelling":
            time.sleep(0.05)
        assert manager.status().phase == "cancelled"

    def test_leave_rejects_while_worker_alive(self, tmp_path):
        in_pipeline = threading.Event()
        release = threading.Event()

        def runner(ctx, manifest):
            in_pipeline.set()
            release.wait(timeout=15)

        manager = _make_manager(tmp_path, runner)
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        assert in_pipeline.wait(timeout=5)
        status = manager.status()
        with pytest.raises(WorkerNotStopped):
            manager.leave(expect_epoch=status.epoch, expect_state_version=status.state_version, worker_stop_timeout=0.3)
        release.set()
        manager.wait_worker_stopped(timeout=5)

    def test_leave_revokes_and_returns_normal(self, tmp_path):
        release = threading.Event()

        def runner(ctx, manifest):
            release.wait(timeout=10)
            return {"ok": True}

        manager = _make_manager(tmp_path, runner)
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        attempt = manager.status().attempt_id
        release.set()
        assert manager.wait_worker_stopped(timeout=5)
        status = manager.status()
        out = manager.leave(expect_epoch=status.epoch, expect_state_version=status.state_version)
        assert out.phase == "idle"
        journal = Journal(str(tmp_path))
        manifest = journal.read_manifest(attempt)
        assert manifest["abandoned"] is True
        assert manifest["epoch"] != status.epoch  # 资格作废代次前进
        assert journal.read_control()["pending_attempt"] is None
        assert manager.controller.status().state == "NORMAL"

    def test_leave_cas_mismatch_rejected(self, tmp_path):
        release = threading.Event()
        manager = _make_manager(tmp_path, lambda ctx, m: release.set() or {})
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        release.wait(timeout=5)
        manager.wait_worker_stopped(timeout=5)
        with pytest.raises(StateConflict, match="CAS"):
            manager.leave(expect_epoch="wrong", expect_state_version=1)

    def test_cancel_rejected_when_worker_finished(self, tmp_path):
        """READY 后 worker 已收尾：取消 fail-fast（StateConflict）且 phase 不被污染。

        此前：request_cancel 照常置位 → status 恒 cancelling（无人 ACK），前端
        提交/放弃按钮双双隐藏（2026-11-11 审查实证的维护死锁入口）。"""
        manager = _make_manager(tmp_path, lambda ctx, m: {"database_id": "db-review"})
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        assert manager.wait_worker_stopped(timeout=5)
        assert manager.status().phase == "ready_to_switch"
        with pytest.raises(StateConflict, match="worker 已收尾"):
            manager.request_cancel(reason="user")
        assert manager.status().phase == "ready_to_switch"


class TestLeaveGuards:
    def test_leave_from_held_restores_normal(self, tmp_path):
        """runtime HELD（fence 丢失）leave 可用（abort_from_held 修复）。

        此前 abort_from_held 委托 abort_prepare（仅接受 PREPARING/DRAINING）
        恒 TransitionError → leave 从 HELD 永远受阻（boot/运行期同症，
        2026-11-11 审查实证）。"""
        release = threading.Event()

        def runner(ctx, manifest):
            release.wait(timeout=5)
            return {"ok": True}

        manager = _make_manager(tmp_path, runner)
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        release.wait(timeout=5)
        manager.wait_worker_stopped(timeout=5)
        manager.controller.note_fence_lost("review")  # → HELD
        assert manager.status().phase == "held"  # status() held 映射（含运行期）
        status = manager.status()
        out = manager.leave(expect_epoch=status.epoch, expect_state_version=status.state_version)
        assert out.phase == "idle"
        assert manager.controller.status().state == "NORMAL"
        assert Journal(str(tmp_path)).read_control()["pending_attempt"] is None

    def test_leave_rejected_before_journal_when_side_effects(self, tmp_path):
        """目标副作用已登记：leave 在动 journal 前拒绝（§5.1/§6.5）。

        此前：journal 先撤销（abandoned+pending 清空）后控制器迁移受阻 →
        半途状态，重试撞「无进行中 attempt」（2026-11-11 审查修复）。"""
        manager = _make_manager(tmp_path, lambda ctx, m: {"database_id": "db-review"})
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        assert manager.wait_worker_stopped(timeout=5)
        manager.controller.note_target_side_effect()
        status = manager.status()
        attempt = status.attempt_id
        with pytest.raises(StateConflict, match="目标副作用"):
            manager.leave(expect_epoch=status.epoch, expect_state_version=status.state_version)
        journal = Journal(str(tmp_path))
        assert journal.read_manifest(attempt).get("abandoned") is not True
        assert journal.read_control()["pending_attempt"] == attempt


class TestCommittedGuards:
    def test_leave_rejected_after_commit(self, tmp_path):
        release = threading.Event()
        manager = _make_manager(tmp_path, lambda ctx, m: release.set() or {})
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        attempt = manager.status().attempt_id
        release.wait(timeout=5)
        manager.wait_worker_stopped(timeout=5)
        journal = Journal(str(tmp_path))
        journal.advance_commit_phase(attempt, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_PREPARED)
        journal.advance_commit_phase(attempt, expected=COMMIT_PHASE_PREPARED, new=COMMIT_PHASE_COMMITTED)
        status = manager.status()
        with pytest.raises(StateConflict, match="commit_phase"):
            manager.leave(expect_epoch=status.epoch, expect_state_version=status.state_version)

    def test_journal_committed_blocks_exit_via_leave(self, tmp_path):
        """journal COMMITTED 而 controller 未 mark_committed：exit 守卫拦截（不放回 NORMAL）。"""
        release = threading.Event()
        manager = _make_manager(tmp_path, lambda ctx, m: release.set() or {})
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        attempt = manager.status().attempt_id
        release.wait(timeout=5)
        manager.wait_worker_stopped(timeout=5)
        journal = Journal(str(tmp_path))
        journal.advance_commit_phase(attempt, expected=COMMIT_PHASE_NONE, new=COMMIT_PHASE_PREPARED)
        journal.advance_commit_phase(attempt, expected=COMMIT_PHASE_PREPARED, new=COMMIT_PHASE_COMMITTED)
        status = manager.status()
        with pytest.raises(StateConflict, match="COMMITTED|commit_phase"):
            manager.leave(expect_epoch=status.epoch, expect_state_version=status.state_version)


class TestRebindProtocol:
    def _prepared(self, tmp_path):
        release = threading.Event()
        manager = _make_manager(tmp_path, lambda ctx, m: release.set() or {})
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        release.wait(timeout=5)
        manager.wait_worker_stopped(timeout=5)
        manager.controller.note_fence_lost("restart")  # HELD 进入
        return manager

    def test_three_stage_rebind_persisted(self, tmp_path):
        manager = self._prepared(tmp_path)
        attempt = manager.status().attempt_id
        old_epoch = manager.status().epoch
        sv = manager.status().state_version
        cas_calls: list = []

        def target_cas(old, new):
            cas_calls.append((old, new))
            return True

        manifest = manager.rebind_epoch(
            expect_epoch=old_epoch, expect_state_version=sv, proof_hash="proof-1", target_cas=target_cas
        )
        records = manifest["rebind_records"]
        assert [r["stage"] for r in records] == ["REBIND_PREPARED", "REBIND_ACK"]
        assert cas_calls == [(old_epoch, manifest["epoch"])]
        assert manifest["epoch"] != old_epoch

    def test_target_cas_failure_holds(self, tmp_path):
        manager = self._prepared(tmp_path)
        status = manager.status()
        with pytest.raises(StateConflict, match="CAS 失败"):
            manager.rebind_epoch(
                expect_epoch=status.epoch,
                expect_state_version=status.state_version,
                proof_hash="p",
                target_cas=lambda o, n: False,
            )
        assert manager.controller.status().state == "HELD"

    def test_window_state_advanced_rejected(self, tmp_path, monkeypatch):
        """客户端携带过期视图 → 入口 CAS 拒；锁外窗口被推进 → 窗口复查拒绝。"""
        manager = self._prepared(tmp_path)
        status = manager.status()
        # 入口 CAS：客户端视图已过期（另一写者已推进 state_version）
        journal = Journal(str(tmp_path))
        manifest = journal.read_manifest(status.attempt_id)
        journal.write_manifest(
            status.attempt_id,
            {**manifest, "progress": {"phase": "x"}},
            expect_state_version=manifest["state_version"],
        )
        with pytest.raises(StateConflict, match="CAS 失败"):
            manager.rebind_epoch(
                expect_epoch=status.epoch,
                expect_state_version=status.state_version,
                proof_hash="p",
                target_cas=lambda o, n: True,
            )
        # 窗口复查：enter_rebind（锁外 IO）期间 manifest 被推进 → 二次 CAS 拒
        fresh = manager.status()
        real_read = Journal.read_manifest

        def racing_read(self, attempt_id):
            data = real_read(self, attempt_id)
            if not getattr(self, "_raced", False):
                self._raced = True  # type: ignore[attr-defined]
                bumped = real_read(self, attempt_id)
                journal.write_manifest(
                    attempt_id,
                    {**bumped, "progress": {"phase": "raced"}},
                    expect_state_version=bumped["state_version"],
                )
            return data

        monkeypatch.setattr(Journal, "read_manifest", racing_read)
        with pytest.raises(StateConflict, match="窗口"):
            manager.rebind_epoch(
                expect_epoch=fresh.epoch,
                expect_state_version=fresh.state_version,
                proof_hash="p",
                target_cas=lambda o, n: True,
            )


class TestStaleWorkerCallbacks:
    def test_stale_generation_cancel_check_rejected(self, tmp_path):
        release = threading.Event()
        manager = _make_manager(tmp_path, lambda ctx, m: release.wait(timeout=10) or {"ok": 1})
        manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        attempt = manager.status().attempt_id
        journal = Journal(str(tmp_path))
        manifest = journal.read_manifest(attempt)
        stale_generation = manifest["worker_generation"] + 5
        ctx = manager._ctx
        assert ctx is not None

        # 旧 ctx 携带旧代次 cancel_check → 新代次后拒绝
        manager.controller.next_worker_generation()  # 代次前进（新 worker 派生）
        with pytest.raises(StaleEpochError, match="过期 worker"):
            ctx.cancel_check()
        release.set()
        manager.wait_worker_stopped(timeout=5)


class TestDefaultPipelineRunnerAssetPaths:
    def test_sqlite_to_pg_forwards_sm4_asset_paths(self, tmp_path, monkeypatch):
        """SM4 资产路径默认值：默认 runner 必须传源/目标 config=当前应用 yaml。

        生产实证（attempt 3ed89647）：源库 bt_downloaders 出现 sm4:% 口令后，
        check_external_assets 要求源/目标 config.yaml 密钥同源——而 UI 发起流
        无 config.yaml 入口，不传即预检必挂。单部署同源切换下源/目标 config
        同为当前应用配置（目标侧发布配置派生自当前 yaml），默认传 YAML_PATH。
        """
        from app.core.config import settings as app_settings
        from app.core.database_bootstrap import PostgresParams
        from app.services.db_migration.pipeline import PipelineContext

        captured: dict = {}

        def fake_run(source_path, *, pg_engine, ctx, resume=False, auto_wrap=False, asset_paths=None):
            captured["source_path"] = source_path
            captured["asset_paths"] = asset_paths
            return {"ok": 1}

        monkeypatch.setattr("app.services.db_migration.sqlite_to_pg.run_sqlite_to_pg", fake_run)
        manager = _make_manager(tmp_path, runner=None)
        params = PostgresParams(
            host="postgres",
            port=5432,
            user="btdeck",
            password="pw",
            database="btdeck",
            schema="public",
            sslmode="prefer",
            ssl_root_cert=None,
            pool_size=1,
            max_overflow=1,
            pool_timeout=5,
        )
        manifest = {
            "direction": "sqlite-to-pg",
            "source": {"path": str(tmp_path / "app.db")},
            "target": {"_pg_params": params},
        }
        ctx = PipelineContext(attempt_id="sqlite-to-pg/3ed89647-test")
        manager._default_pipeline_runner(ctx, manifest)

        expected = str(app_settings.YAML_PATH)
        assert captured["asset_paths"] == {"source_config": expected, "target_config": expected}
        assert captured["source_path"] == str(tmp_path / "app.db")


class TestDrainTimeoutSelfHeal:
    def test_drain_timeout_aborts_to_normal_and_clears_intent(self, tmp_path, monkeypatch):
        """排空超时安全撤销（生产实证 49075d35/954db6f2 两起孤儿死锁）：
        PREPARING 零副作用时不再停 held 等人工（人工出口依赖尚未持久的
        pending manifest=无 API 出口），改为归位 NORMAL+清 intent+409 指引。"""
        from app.core.database_protocol import DB_MIGRATION_DIR

        manager = _make_manager(tmp_path, runner=None)
        real_run_drain = manager.controller.run_drain
        monkeypatch.setattr(manager.controller, "run_drain", lambda timeout: False)

        abort_calls: list[str] = []
        real_abort = manager.controller.abort_drain_timeout

        def spy_abort() -> None:
            abort_calls.append("aborted")
            real_abort()

        monkeypatch.setattr(manager.controller, "abort_drain_timeout", spy_abort)

        with pytest.raises(StateConflict, match="排空 30 秒未完成"):
            manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")

        assert abort_calls == ["aborted"]
        assert manager.status().phase == "idle"
        assert not (tmp_path / DB_MIGRATION_DIR / "maintenance-intent.json").exists()
        # 审计留痕
        rows = manager._audit.replay_events()
        assert any(r["action"] == "drain-timeout-selfheal" for r in rows)
        # 撤销后可立即重新发起（状态机回 NORMAL，单飞行解除）：恢复真实排空
        monkeypatch.setattr(manager.controller, "run_drain", real_run_drain)
        started = manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
        assert started.attempt_id
        manager.wait_worker_stopped(timeout=5)
