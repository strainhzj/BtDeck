"""维护控制器状态机/lease/取消 epoch 测试（database-migration-ui W2-1/W2-7，PLANS §5.1/§6.4）。

覆盖 T03/T07 组件级：
- 准入判定与计数同临界区；维护态拒新准入；lease 持有至 finally；
- 子任务原子继承（父收尾等子；父已收尾拒绝登记）；
- PREPARING 先持久 intent 关门再查重任务（顺序）；不可等待重任务 → 安全撤销+409；
- 排空等待/超时 HELD；未排空不能 FROZEN；目标副作用后禁撤销；
- 取消协作 + worker ACK + 旧 epoch 晚回调拒绝；无漂移重绑/漂移拒绝/COMMITTED 禁重绑；
- 维护启动分支（HELD 进入）/退出；intent 损坏拒绝默认化。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app.services.db_migration.maintenance import (
    _Lease,
    AdmissionRejected,
    MaintenanceController,
    MaintenancePrepareBlocked,
    StaleEpochError,
    TransitionError,
    STATE_FROZEN,
    STATE_HELD,
    STATE_NORMAL,
    STATE_PREPARING,
    STATE_DRAINING,
    STATE_READY_TO_SWITCH,
    STATE_COMMITTED,
    read_intent,
    set_default_controller,
    maintenance_active,
)

AID = "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


class TestAdmissionLease:
    def test_normal_admission_holds_until_release(self, tmp_path):
        c = MaintenanceController(tmp_path)
        assert c.status().state == STATE_NORMAL
        with c.admission_slot("http:/api/v1/x"):
            assert c.active_count() == 1
            assert c.active_kinds() == ["http:/api/v1/x"]
        assert c.active_count() == 0

    def test_maintenance_rejects_new_admission(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        with pytest.raises(AdmissionRejected):
            with c.admission_slot("http:/api/v1/x"):
                pass

    def test_lease_released_on_body_exception(self, tmp_path):
        c = MaintenanceController(tmp_path)
        with pytest.raises(RuntimeError):
            with c.admission_slot("boom"):
                raise RuntimeError("x")
        assert c.active_count() == 0

    def test_child_inheritance_parent_waits(self, tmp_path):
        c = MaintenanceController(tmp_path)
        with c.admission_slot("cron:1") as parent:
            child = c.register_child(parent, "thread:worker")
            child2 = c.register_child(parent, "thread:worker2")
            assert c.active_count() == 3
            child.release()
            assert c.active_count() == 2
            # 父收尾必须等待剩余子 lease（计数不可提前降零）
            done = threading.Event()

            def _release_parent():
                parent.release()
                done.set()

            threading.Thread(target=_release_parent).start()
            assert not done.wait(0.3), "父 lease 未等子 lease 即收尾"
            assert c.active_count() >= 1
            child2.release()
            assert done.wait(2.0)
            assert c.active_count() == 0

    def test_register_child_after_parent_release_rejected(self, tmp_path):
        c = MaintenanceController(tmp_path)
        with c.admission_slot("cron:1") as parent:
            pass
        with pytest.raises(TransitionError, match="父 lease 已收尾"):
            c.register_child(parent, "late")

    def test_drain_waits_for_inflight_leases(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        # 闸门关闭前已准入的在途请求（模拟 HTTP lease）
        lease = _Lease(c, "http:/api/v1/inflight")
        with c._cond:
            c._active.add(lease)
        result: list[bool] = []

        def _drain():
            result.append(c.run_drain(3.0))

        t = threading.Thread(target=_drain)
        t.start()
        time.sleep(0.2)
        assert c.status().state == STATE_DRAINING
        assert t.is_alive(), "有在途 lease 时排空不应提前完成（未排空不能快照）"
        lease.release()  # 请求完成（含 finally 审计）
        t.join(2.0)
        assert result == [True], "计数归零后排空应成功"
        assert c.active_count() == 0

    def test_drain_timeout_goes_held(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        with c._cond:
            c._active.add(_Lease(c, "stuck"))
        assert c.run_drain(0.2) is False
        assert c.status().state == STATE_HELD
        assert c.status().held_reason == "DRAIN_TIMEOUT"
        # 有未收尾准入：不能确认 worker 停 → 保持 HELD，禁止撤销
        with pytest.raises(TransitionError, match="保持 HELD"):
            c.abort_from_held(reason="x")


class TestPrepareOrdering:
    def test_intent_persisted_before_gate_close(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        intent = read_intent(tmp_path)
        assert intent["state"] == STATE_PREPARING
        assert intent["attempt_id"] == AID
        assert c.status().state == STATE_PREPARING

    def test_non_waitable_heavy_task_aborts_prepare_409(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)  # 进入维护（无重任务）
        c.exit_maintenance()
        # 重新走完整准备流：先准入一个不可等待重任务
        with c.admission_slot("cron:99") as _heavy:
            with pytest.raises(MaintenancePrepareBlocked) as exc:
                c.begin_prepare(attempt_id=AID, non_waitable_kinds=("cron:99",))
            assert "cron:99" in str(exc.value)
        # 安全撤销：恢复 NORMAL + intent 清除
        assert c.status().state == STATE_NORMAL
        assert read_intent(tmp_path) is None

    def test_prepare_only_from_normal(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        with pytest.raises(TransitionError):
            c.begin_prepare(attempt_id=AID)

    def test_bad_attempt_id_rejected(self, tmp_path):
        c = MaintenanceController(tmp_path)
        with pytest.raises(TransitionError, match="attempt_id 形态非法"):
            c.begin_prepare(attempt_id="../../etc/passwd")


class TestFrozenAndPipeline:
    def _to_drained(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        assert c.run_drain(1.0) is True
        return c

    def test_frozen_requires_fence_token_and_zero_count(self, tmp_path):
        c = self._to_drained(tmp_path)
        with pytest.raises(TransitionError, match="fence"):
            c.enter_frozen(None)
        c.enter_frozen(object())
        assert c.status().state == STATE_FROZEN

    def test_frozen_rejected_with_active_lease(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        with c._cond:
            c._active.add(_Lease(c, "stuck"))
        assert c.run_drain(0.1) is False
        with pytest.raises(TransitionError):
            c.enter_frozen(object())  # HELD 不能直接 FROZEN

    def test_pipeline_states_sequential(self, tmp_path):
        c = self._to_drained(tmp_path)
        c.enter_frozen(object())
        for st in ("IMPORTING", "VERIFYING", "READY_TO_SWITCH"):
            c.set_pipeline_state(st)
        assert c.status().state == STATE_READY_TO_SWITCH
        with pytest.raises(TransitionError, match="跳步"):
            c.set_pipeline_state("IMPORTING")

    def test_abort_blocked_after_target_side_effects(self, tmp_path):
        c = self._to_drained(tmp_path)
        c.note_target_side_effect()
        with pytest.raises(TransitionError, match="目标副作用"):
            c.abort_prepare(reason="x")

    def test_abort_prepare_ok_without_side_effects(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.begin_prepare(attempt_id=AID)
        c.abort_prepare(reason="user cancel")
        assert c.status().state == STATE_NORMAL
        assert read_intent(tmp_path) is None

    def test_fence_lost_goes_held(self, tmp_path):
        c = self._to_drained(tmp_path)
        c.enter_frozen(object())
        c.note_fence_lost("conn dropped")
        assert c.status().state == STATE_HELD
        assert c.status().held_reason == "FENCE_LOST"


class TestCancelAndEpoch:
    def _frozen(self, tmp_path):
        c = MaintenanceController(tmp_path)
        epoch = c.begin_prepare(attempt_id=AID)
        assert c.run_drain(1.0)
        c.enter_frozen(object())
        return c, epoch

    def test_cancel_request_and_ack(self, tmp_path):
        c, epoch = self._frozen(tmp_path)
        c.request_cancel(reason="user")
        assert c.cancel_requested
        with pytest.raises(RuntimeError, match="取消"):
            c.cancel_check(epoch)
        assert c.ack_cancel(epoch) is True
        assert c.wait_cancel_ack(0.1) is True

    def test_stale_epoch_cancel_check_rejected(self, tmp_path):
        c, epoch = self._frozen(tmp_path)
        with pytest.raises(StaleEpochError):
            c.cancel_check("epoch-old")

    def test_late_ack_with_old_epoch_rejected(self, tmp_path):
        c, epoch = self._frozen(tmp_path)
        c.request_cancel()
        assert c.ack_cancel("epoch-stale") is False
        assert c.wait_cancel_ack(0.1) is False

    def test_rebind_no_drift_ok_and_committed_forbidden(self, tmp_path):
        c, epoch = self._frozen(tmp_path)
        c.note_fence_lost("drain timeout")  # → HELD
        new_epoch = c.enter_rebind(expected_epoch=epoch, drift_check=lambda: True)
        assert new_epoch != epoch
        # 漂移拒绝 → 保持 HELD
        c.note_fence_lost("again")
        with pytest.raises(TransitionError, match="漂移"):
            c.enter_rebind(expected_epoch=new_epoch, drift_check=lambda: False)
        assert c.status().state == STATE_HELD
        # COMMITTED 禁重绑
        c.enter_rebind(expected_epoch=new_epoch, drift_check=lambda: True)
        c.status()  # HELD
        c._held_reason = None
        with c._cond:
            c._state = STATE_READY_TO_SWITCH
        c.mark_committed()
        assert c.status().state == STATE_COMMITTED
        with pytest.raises(TransitionError, match="禁重绑"):
            c.enter_rebind(expected_epoch=c.epoch, drift_check=lambda: True)
        with pytest.raises(TransitionError, match="COMMITTED"):
            c.exit_maintenance()

    def test_rebind_stale_epoch_rejected(self, tmp_path):
        c, epoch = self._frozen(tmp_path)
        c.note_fence_lost("x")
        with pytest.raises(StaleEpochError):
            c.enter_rebind(expected_epoch="epoch-stale", drift_check=lambda: True)


class TestBootBranchAndDefaults:
    def test_enter_maintenance_boot_and_exit(self, tmp_path):
        c = MaintenanceController(tmp_path)
        c.enter_maintenance_boot(attempt_id=AID)
        s = c.status()
        assert s.state == STATE_HELD and s.boot_recovery and s.in_maintenance
        with pytest.raises(AdmissionRejected):
            with c.admission_slot("http:x"):
                pass
        c.exit_maintenance()
        assert c.status().state == STATE_NORMAL

    def test_intent_corrupted_raises(self, tmp_path):
        from app.core.database_protocol import DB_MIGRATION_DIR

        d = tmp_path / DB_MIGRATION_DIR
        d.mkdir(parents=True)
        (d / "maintenance-intent.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(RuntimeError, match="拒绝默认化"):
            read_intent(tmp_path)

    def test_default_controller_sentinel(self, tmp_path):
        c = MaintenanceController(tmp_path)
        set_default_controller(c)
        try:
            assert maintenance_active() is False  # normal 模式不算维护
            c.enter_maintenance_boot()
            assert maintenance_active() is True
        finally:
            set_default_controller(None)
        assert maintenance_active() is False
