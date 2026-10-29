# -*- coding: utf-8 -*-
"""维护状态机与操作级 lease（database-migration-ui W2-1/W2-7，PLANS §5.1/§6.4）。

可证明停写的准入/排空屏障：

- 状态机 ``NORMAL → PREPARING → DRAINING → FROZEN → IMPORTING → VERIFYING →
  READY_TO_SWITCH``（+ ``HELD`` 降级态、``COMMITTED`` 终态、``ABANDONED`` 放弃态）。
  维护启动分支（W2-2 lifespan 只读引导）直接以 HELD 进入——重启后必须重新取
  fence 并核源内容，不能认为旧锁仍在（§5.2）。
- 准入判定与 lease 计数共享同一 ``threading`` 临界区（cron 调度线程与事件循环
  混合环境，``asyncio.Lock`` 覆盖不了线程侧）；PREPARING **先持久 intent 关闭
  新普通准入，再检查不可等待重任务**（顺序不可倒置，§5.1），命中则安全撤销
  本次准备（无目标副作用前提）并抛 ``MaintenancePrepareBlocked``（API 层 409）。
- lease 自入口（HTTP/MCP/cron/后台循环）持有，直至远端动作、所有 DB 事务、
  finally、通知、审计完成；子任务在脱离父执行流前经 ``register_child`` 原子
  继承计数——父 lease 收尾前等待全部子 lease 释放，计数不可提前降零。
- 排空超时 → HELD（未冻结、未快照；无目标副作用可撤销准备，否则必须人工/
  控制面恢复，禁止抢先恢复业务）；只有计数为零 + fence 取得（W2-4 传入
  fence 令牌）才进入 FROZEN。
- 取消与 epoch（§6.4）：``request_cancel`` 协作取消 + worker ``ack_cancel``
  确认（阻塞等待 ACK）；epoch 前进后晚到的回调/ACK 一律拒绝；HELD/ABANDONED
  下无漂移可重绑（``enter_rebind``，漂移拒绝），COMMITTED 终态禁重绑。

本模块不 import 任何 app 数据库/引擎模块（与 database_protocol 同纪律），
供 lifespan 早期分支与 CLI 共用。
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set

from app.core.database_protocol import (
    DB_MIGRATION_DIR,
    is_valid_attempt_id,
)

# ---------------------------------------------------------------------------
# 状态机常量（§5.1；字符串持久化进 intent/本地审计，禁止改值）
# ---------------------------------------------------------------------------

STATE_NORMAL = "NORMAL"
STATE_PREPARING = "PREPARING"
STATE_DRAINING = "DRAINING"
STATE_FROZEN = "FROZEN"
STATE_IMPORTING = "IMPORTING"
STATE_VERIFYING = "VERIFYING"
STATE_READY_TO_SWITCH = "READY_TO_SWITCH"
STATE_HELD = "HELD"
STATE_COMMITTED = "COMMITTED"
STATE_ABANDONED = "ABANDONED"

#: 维护态集合：期间一切新普通准入被拒（HELD 也拒——禁止抢先恢复业务，§5.1）
MAINTENANCE_STATES = frozenset(
    {
        STATE_PREPARING,
        STATE_DRAINING,
        STATE_FROZEN,
        STATE_IMPORTING,
        STATE_VERIFYING,
        STATE_READY_TO_SWITCH,
        STATE_HELD,
        STATE_ABANDONED,
        STATE_COMMITTED,
    }
)

INTENT_FILENAME = "maintenance-intent.json"

_HELD_DRAIN_TIMEOUT = "DRAIN_TIMEOUT"
_HELD_FENCE_LOST = "FENCE_LOST"
_HELD_UNKNOWN_WRITER = "UNKNOWN_WRITER"
_HELD_BOOT_RECOVERY = "BOOT_RECOVERY"


class AdmissionRejected(RuntimeError):
    """维护态下新普通准入被拒（HTTP 层译 503 / cron 层跳过本轮）。"""

    def __init__(self, state: str) -> None:
        super().__init__(f"维护模式（state={state}）拒绝新业务准入")
        self.state = state


class MaintenancePrepareBlocked(RuntimeError):
    """存在不可等待重任务，本次准备安全撤销（API 层译 409，§5.1）。"""

    def __init__(self, blockers: Sequence[str]) -> None:
        super().__init__(f"存在不可等待的重任务，拒绝进入维护: {', '.join(blockers)}")
        self.blockers = list(blockers)


class TransitionError(RuntimeError):
    """非法状态迁移/操作（含 COMMITTED 禁重绑、漂移拒绝）。"""


class StaleEpochError(TransitionError):
    """携带旧 epoch 的回调/ACK/操作——一律拒绝（§6.4 晚回调拒绝）。"""


@dataclass(frozen=True)
class MaintenanceStatus:
    """只读快照（状态接口/health/审计用；无凭据无指纹明文）。"""

    state: str
    mode: str  # normal | maintenance
    attempt_id: Optional[str]
    epoch: str
    active_leases: int
    active_kinds: List[str]
    held_reason: Optional[str]
    cancel_requested: bool
    target_side_effects: bool
    boot_recovery: bool

    @property
    def in_maintenance(self) -> bool:
        return self.mode == "maintenance"


@dataclass(eq=False)
class _Lease:
    controller: "MaintenanceController"
    kind: str
    children: "Set[_Lease]" = field(default_factory=set)
    released: bool = False

    def release(self) -> None:
        """释放 lease：先等全部子 lease 收尾（计数不可提前降零，§5.1）。"""
        # cond 基于同线程可重入 RLock：嵌套 wait_released 安全；Condition.wait
        # 在等待时会完整释放 RLock 全部重入层级。
        with self.controller._cond:
            if self.released:
                return
            while self.children:
                child = next(iter(self.children))
                child.wait_released()
                self.children.discard(child)
            self.released = True
            self.controller._active.discard(self)
            self.controller._cond.notify_all()

    def wait_released(self, timeout: Optional[float] = None) -> bool:
        with self.controller._cond:
            deadline = None if timeout is None else time.monotonic() + timeout
            while not self.released:
                if deadline is None:
                    self.controller._cond.wait()
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    self.controller._cond.wait(remaining)
            return True


class MaintenanceController:
    """单进程维护控制器（lifespan 构造并挂 ``app.state.maintenance``）。"""

    def __init__(self, config_dir: os.PathLike[str] | str | None = None) -> None:
        self._cond = threading.Condition(threading.RLock())
        self._state = STATE_NORMAL
        self._mode = "normal"  # normal | maintenance（boot 分支直接进 maintenance）
        self._active: Set[_Lease] = set()
        self._attempt_id: Optional[str] = None
        self._epoch: str = f"epoch-{uuid.uuid4().hex[:16]}"
        self._held_reason: Optional[str] = None
        self._cancel_requested = False
        self._cancel_ack_event = threading.Event()
        self._target_side_effects = False
        self._boot_recovery = False
        self._worker_generation = 0  # W3-3：worker 代次（晚回调拒绝过期 worker）
        self._config_dir: Optional[os.PathLike[str] | str] = config_dir
        self._intent_path: Optional[Path] = (
            Path(config_dir) / DB_MIGRATION_DIR / INTENT_FILENAME if config_dir is not None else None
        )

    # ------------------------------------------------------------------
    # 准入 lease（§5.1：判定与计数同临界区）
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def admission_slot(self, kind: str = "generic") -> Iterator[_Lease]:
        """普通业务准入：维护态一律拒绝；持有至调用方 finally 完成。"""
        with self._cond:
            if self._state in MAINTENANCE_STATES or self._mode == "maintenance":
                raise AdmissionRejected(self._state)
            lease = _Lease(self, kind)
            self._active.add(lease)
        try:
            yield lease
        finally:
            lease.release()

    def register_child(self, parent: _Lease, kind: Optional[str] = None) -> _Lease:
        """子线程/子任务在脱离父执行流前原子继承计数（§5.1）。

        必须在父 lease 仍持有时调用；返回的子 lease 独立 ``release()``，
        父 lease 收尾会等待全部子 lease。
        """
        with self._cond:
            if parent.released or parent not in self._active:
                raise TransitionError("父 lease 已收尾，禁止再登记子工作（先登记后脱离父执行流）")
            child = _Lease(self, kind or f"{parent.kind}:child")
            parent.children.add(child)
            self._active.add(child)
            return child

    def active_count(self) -> int:
        with self._cond:
            return len(self._active)

    def active_kinds(self) -> List[str]:
        with self._cond:
            return sorted(lease.kind for lease in self._active)

    # ------------------------------------------------------------------
    # 状态机（§5.1）
    # ------------------------------------------------------------------

    def begin_prepare(
        self,
        *,
        attempt_id: str,
        non_waitable_kinds: Sequence[str] = (),
        now: Optional[float] = None,
    ) -> str:
        """NORMAL → PREPARING：先持久 intent 关门，再查不可等待重任务。

        顺序不可倒置（§5.1）：intent 落盘成功才关门；存在不可等待重任务则
        安全撤销（恢复 NORMAL + 清 intent）并抛 ``MaintenancePrepareBlocked``。
        返回本次维护 epoch。
        """
        if not is_valid_attempt_id(attempt_id):
            raise TransitionError(f"attempt_id 形态非法: {attempt_id!r}")
        with self._cond:
            if self._state != STATE_NORMAL or self._mode != "normal":
                raise TransitionError(f"当前 state={self._state}，只有 NORMAL 可进入维护准备")
            # 1) 先持久 intent（fail-closed：写失败不关门）
            self._persist_intent(STATE_PREPARING, attempt_id, now=now)
            # 2) 关闭新普通准入
            self._attempt_id = attempt_id
            self._epoch = f"epoch-{uuid.uuid4().hex[:16]}"
            self._state = STATE_PREPARING
            self._mode = "maintenance"
            # 3) 再检查重任务（不可等待 → 安全撤销本次准备）
            blockers = sorted({k for k in self.active_kinds() for bad in non_waitable_kinds if k.startswith(bad)})
            if blockers:
                self._state = STATE_NORMAL
                self._mode = "normal"
                self._attempt_id = None
                self._clear_intent()
                raise MaintenancePrepareBlocked(blockers)
            self._cond.notify_all()
            return self._epoch

    def run_drain(self, timeout: float) -> bool:
        """PREPARING → DRAINING 并等待计数归零；超时 → HELD（不快照不冻结）。

        返回 True 表示计数为零（调用方随后取 fence 并 ``enter_frozen``）；
        False 表示 HELD（未冻结；无目标副作用可 ``abort_from_held`` 撤销，
        否则保持 HELD 等控制面恢复——禁止抢先恢复业务）。
        """
        deadline = time.monotonic() + timeout
        with self._cond:
            if self._state != STATE_PREPARING:
                raise TransitionError(f"只有 PREPARING 可进入排空（当前 {self._state}）")
            self._state = STATE_DRAINING
            self._cond.notify_all()
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._state = STATE_HELD
                    self._held_reason = _HELD_DRAIN_TIMEOUT
                    self._cond.notify_all()
                    return False
                self._cond.wait(remaining)
            return True

    def enter_frozen(self, fence_token: Any) -> None:
        """DRAINING(计数零) → FROZEN：fence 令牌由 W2-4 SourceFence 提供。

        令牌仅做存在性登记（真实锁在 fence 连接上）；指纹核验/锁丢失检测
        由 fence 模块 ``verify`` 驱动 ``note_fence_lost``。
        """
        with self._cond:
            if self._state != STATE_DRAINING:
                raise TransitionError(f"只有 DRAINING 可进入 FROZEN（当前 {self._state}）")
            if self._active:
                raise TransitionError("计数未归零，禁止进入 FROZEN（未排空不能快照，T03）")
            if fence_token is None:
                raise TransitionError("缺少源 fence 令牌（先取保护锁并固定指纹，§5.1）")
            self._state = STATE_FROZEN
            self._cond.notify_all()

    def set_pipeline_state(self, state: str) -> None:
        """FROZEN → IMPORTING → VERIFYING → READY_TO_SWITCH（管线阶段推进）。"""
        order = [STATE_FROZEN, STATE_IMPORTING, STATE_VERIFYING, STATE_READY_TO_SWITCH]
        with self._cond:
            if state not in order or self._state not in order:
                raise TransitionError(f"非法管线阶段迁移 {self._state} → {state}")
            if order.index(state) != order.index(self._state) + 1:
                raise TransitionError(f"管线阶段必须顺序推进（{self._state} → {state} 跳步）")
            self._state = state
            self._cond.notify_all()

    def note_target_side_effect(self) -> None:
        """管线首个目标副作用前登记（此后撤销准备被禁止，§5.1）。"""
        with self._cond:
            self._target_side_effects = True

    def abort_prepare(self, *, reason: str) -> None:
        """PREPARING/DRAINING → NORMAL：安全撤销（仅限零目标副作用）。"""
        with self._cond:
            if self._state not in (STATE_PREPARING, STATE_DRAINING):
                raise TransitionError(f"当前 {self._state} 不可安全撤销准备")
            if self._target_side_effects:
                raise TransitionError("已存在目标副作用，禁止撤销（保持 HELD 由控制面处置）")
            self._state = STATE_NORMAL
            self._mode = "normal"
            self._attempt_id = None
            self._cancel_requested = False
            self._cancel_ack_event.clear()
            self._clear_intent()
            self._cond.notify_all()

    def abort_from_held(self, *, reason: str) -> None:
        """HELD → NORMAL：仅限零目标副作用且计数已归零（不能确认 worker 停则保持 HELD）。"""
        with self._cond:
            if self._state != STATE_HELD:
                raise TransitionError(f"只有 HELD 可从保持态撤销（当前 {self._state}）")
            if self._target_side_effects:
                raise TransitionError("已存在目标副作用，禁止从 HELD 撤销（转 ABANDONED/discard 流程）")
            if self._active:
                raise TransitionError("仍有未收尾准入（不能确认 worker 已停，保持 HELD，§5.1）")
            self._held_reason = None
            self.abort_prepare(reason=reason)

    def abort_from_frozen(self, *, reason: str = "") -> None:
        """FROZEN → NORMAL：放弃回源（leave；W3-3）。

        前置由调用方（manager.leave）保证：worker 已安全收尾（线程 join+ACK）、
        journal 已持久撤销 switch_eligible 并推进 epoch（资格作废）。此处仅当
        目标无不可放弃副作用争议且准入计数为零时放行；否则保持 FROZEN。
        """
        with self._cond:
            if self._state != STATE_FROZEN:
                raise TransitionError(f"只有 FROZEN 可放弃回源（当前 {self._state}）")
            if self._target_side_effects:
                raise TransitionError("已存在目标副作用，禁止直接回源（转 discard/ABANDONED 流程）")
            if self._active:
                raise TransitionError("仍有未收尾准入（保持 FROZEN，§5.1）")
            self._state = STATE_PREPARING  # 借道 abort_prepare 的 NORMAL 收尾
            self.abort_prepare(reason=reason or "leave-from-frozen")

    def note_fence_lost(self, detail: str = "") -> None:
        """锁丢失/漏写/未知 writer → HELD（不继续宣称冻结，§5.2）。"""
        with self._cond:
            if self._mode != "maintenance":
                return
            if self._state in (STATE_COMMITTED, STATE_ABANDONED):
                return
            self._state = STATE_HELD
            self._held_reason = _HELD_FENCE_LOST
            self._cond.notify_all()

    def note_unknown_writer(self, detail: str = "") -> None:
        with self._cond:
            if self._mode != "maintenance" or self._state in (STATE_COMMITTED, STATE_ABANDONED):
                return
            self._state = STATE_HELD
            self._held_reason = _HELD_UNKNOWN_WRITER
            self._cond.notify_all()

    # ------------------------------------------------------------------
    # 维护启动分支（W2-2：重启后直接以 HELD 进入，须重新取 fence 核源）
    # ------------------------------------------------------------------

    def enter_maintenance_boot(self, *, attempt_id: Optional[str] = None, reason: str = _HELD_BOOT_RECOVERY) -> None:
        with self._cond:
            if self._state != STATE_NORMAL or self._mode != "normal":
                raise TransitionError("controller 已在维护态，禁止重复进入维护启动")
            if attempt_id is not None and not is_valid_attempt_id(attempt_id):
                raise TransitionError(f"attempt_id 形态非法: {attempt_id!r}")
            self._mode = "maintenance"
            self._state = STATE_HELD
            self._held_reason = reason or _HELD_BOOT_RECOVERY
            self._boot_recovery = True
            self._attempt_id = attempt_id
            # intent 文件保持现状：boot 分支的持久事实由 control/manifest 承载，
            # 重启即恢复不重写 intent（避免覆盖崩溃现场的时序证据）。
            self._cond.notify_all()

    def exit_maintenance(self, *, to_state: str = STATE_NORMAL) -> None:
        """维护退出（正常退出或放弃后回业务；COMMITTED 除外——提交流程重启）。

        评审修正（W3-1）：journal 权威（manifest commit_phase ∈ COMMITTED/
        ACTIVATED_ACK）存在时**禁止回 NORMAL**——持久提交决定只能被幂等 redo
        或新代次交接消费，不能被运行视图/残留 intent 撤销。
        """
        with self._cond:
            if self._state == STATE_COMMITTED:
                raise TransitionError("COMMITTED 终态不可经本方法退出（进程将由提交流程重启）")
            if to_state == STATE_NORMAL and self._journal_committed_pending_restart():
                raise TransitionError("journal 已持久 COMMITTED 决定（等待重启幂等 redo），禁止放回 NORMAL")
            self._state = to_state
            if to_state == STATE_NORMAL:
                self._mode = "normal"
                self._attempt_id = None
                self._cancel_requested = False
                self._cancel_ack_event.clear()
                self._boot_recovery = False
                self._clear_intent()
            self._cond.notify_all()

    def _journal_committed_pending_restart(self) -> bool:
        """读 journal 权威（无 config_dir/无证据 → False；损坏 → True 保守拒回）。"""
        if self._config_dir is None:
            return False
        try:
            from app.services.db_migration.journal import Journal

            return Journal(self._config_dir).evaluate_intent_authority().committed_pending_restart
        except Exception:
            return True  # 受管证据损坏 fail-closed：宁保持维护不回业务

    # ------------------------------------------------------------------
    # 取消与 epoch（§6.4，W2-7）
    # ------------------------------------------------------------------

    def next_worker_generation(self) -> int:
        """派生 worker 时自增并返回代次（cancel/progress/checkpoint 回调携带）。"""
        with self._cond:
            self._worker_generation += 1
            return self._worker_generation

    @property
    def worker_generation(self) -> int:
        with self._cond:
            return self._worker_generation

    @property
    def epoch(self) -> str:
        with self._cond:
            return self._epoch

    @property
    def attempt_id(self) -> Optional[str]:
        with self._cond:
            return self._attempt_id

    def request_cancel(self, *, reason: str = "") -> None:
        """协作取消请求（维护态内有效；worker 在批/表边界检查并收尾）。"""
        with self._cond:
            if self._mode != "maintenance" or self._state in (STATE_NORMAL, STATE_COMMITTED, STATE_ABANDONED):
                raise TransitionError(f"当前 {self._state} 不可请求取消")
            self._cancel_requested = True
            self._cond.notify_all()

    def cancel_check(self, epoch: Optional[str] = None) -> None:
        """W1 PipelineContext.cancel_check 的控制器实现（含 epoch 拒晚回调）。"""
        with self._cond:
            if epoch is not None and epoch != self._epoch:
                raise StaleEpochError(f"取消检查携带旧 epoch（{epoch} ≠ {self._epoch}）——拒绝")
            if self._cancel_requested:
                raise _ControllerCancellation(self._epoch)

    @property
    def cancel_requested(self) -> bool:
        with self._cond:
            return self._cancel_requested

    def wait_cancel_ack(self, timeout: Optional[float] = None) -> bool:
        """阻塞等待 worker 取消 ACK（lease 释放/收尾完成即 ACK，§6.4）。"""
        return self._cancel_ack_event.wait(timeout)

    def ack_cancel(self, epoch: Optional[str] = None) -> bool:
        """worker 取消确认；旧 epoch 的晚到 ACK 一律拒绝并返回 False。"""
        with self._cond:
            if epoch is not None and epoch != self._epoch:
                return False
            if not self._cancel_requested:
                return False
            self._cancel_ack_event.set()
            self._cond.notify_all()
            return True

    def enter_rebind(
        self,
        *,
        expected_epoch: str,
        drift_check: Callable[[], bool],
    ) -> str:
        """无漂移重绑：HELD/ABANDONED 下源未漂移才允许新冻结继承资格（§6.4）。

        ``drift_check`` 由调用方提供（W2-4 fence 重新取锁 + 指纹对拍）；漂移
        （返回 False）→ 保持 HELD 并抛 ``TransitionError``。COMMITTED 禁重绑。
        返回新 epoch（资格代次前进）。
        """
        with self._cond:
            if expected_epoch != self._epoch:
                raise StaleEpochError(f"重绑请求携带旧 epoch（{expected_epoch} ≠ {self._epoch}）——拒绝")
            if self._state == STATE_COMMITTED:
                raise TransitionError("COMMITTED 终态禁重绑（§6.4）")
            if self._state not in (STATE_HELD, STATE_ABANDONED):
                raise TransitionError(f"只有 HELD/ABANDONED 可重绑（当前 {self._state}）")
        # drift_check 可能有 IO（锁/指纹）——锁外执行，再回锁内提交
        if not drift_check():
            with self._cond:
                if self._state not in (STATE_COMMITTED, STATE_ABANDONED):
                    self._state = STATE_HELD
                    self._held_reason = "REBIND_DRIFT"
                raise TransitionError("源内容漂移，拒绝重绑（保持 HELD，人工/控制面处置）")
        with self._cond:
            self._epoch = f"epoch-{uuid.uuid4().hex[:16]}"
            self._held_reason = None
            self._cancel_requested = False
            self._cancel_ack_event.clear()
            self._cond.notify_all()
            return self._epoch

    def mark_committed(self) -> None:
        """READY_TO_SWITCH → COMMITTED（W3 提交流程调用；此后禁重绑/禁退出）。"""
        with self._cond:
            if self._state != STATE_READY_TO_SWITCH:
                raise TransitionError(f"只有 READY_TO_SWITCH 可提交（当前 {self._state}）")
            self._state = STATE_COMMITTED
            self._cond.notify_all()

    def mark_abandoned(self) -> None:
        """放弃本次目标（W3 discard 流程）：→ ABANDONED（可经 rebind 复用或退出）。"""
        with self._cond:
            if self._state in (STATE_NORMAL, STATE_COMMITTED):
                raise TransitionError(f"当前 {self._state} 不可放弃")
            self._state = STATE_ABANDONED
            self._cond.notify_all()

    # ------------------------------------------------------------------
    # 视图
    # ------------------------------------------------------------------

    def status(self) -> MaintenanceStatus:
        with self._cond:
            return MaintenanceStatus(
                state=self._state,
                mode=self._mode,
                attempt_id=self._attempt_id,
                epoch=self._epoch,
                active_leases=len(self._active),
                active_kinds=sorted(lease.kind for lease in self._active),
                held_reason=self._held_reason,
                cancel_requested=self._cancel_requested,
                target_side_effects=self._target_side_effects,
                boot_recovery=self._boot_recovery,
            )

    # ------------------------------------------------------------------
    # intent 持久化（§4.2 布局下的 W2 过渡文件；W3 journal 仓储吸收）
    # ------------------------------------------------------------------

    def _persist_intent(self, state: str, attempt_id: str, *, now: Optional[float] = None) -> None:
        if self._intent_path is None:
            return
        payload = {
            "version": 1,
            "state": state,
            "attempt_id": attempt_id,
            "epoch": self._epoch,
            "recorded_at": time.time() if now is None else now,
            "pid": os.getpid(),
        }
        # W3-1：intent 是 journal 的兼容投影（同路径同格式），写入经 journal
        # 统一纪律（锁+原子写）；权威事实在 control/manifest。
        from app.services.db_migration.journal import Journal

        assert self._config_dir is not None  # _intent_path 非 None 的前提
        Journal(self._config_dir).write_intent_projection(payload)

    def _clear_intent(self) -> None:
        if self._intent_path is None:
            return
        from app.services.db_migration.journal import Journal

        assert self._config_dir is not None
        Journal(self._config_dir).clear_intent_projection()


class _ControllerCancellation(RuntimeError):
    """控制器协作取消信号（pipeline 译为 W1 MigrationCancelled）。"""

    def __init__(self, epoch: str) -> None:
        super().__init__(f"维护控制面已请求取消（epoch={epoch}）")
        self.epoch = epoch


#: 公开别名（manager/管线分类用；下划线名保留兼容 W2 测试）
ControllerCancellation = _ControllerCancellation


def read_intent(config_dir: os.PathLike[str] | str) -> Optional[Dict[str, Any]]:
    """只读 intent 文件（boot 分支判定 PREPARING 崩溃残留；损坏 → 抛错拒绝默认化）。"""
    path = Path(config_dir) / DB_MIGRATION_DIR / INTENT_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"{path} 解析失败（维护 intent 损坏，拒绝默认化）: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} 必须为 JSON 对象")
    return data


# ---------------------------------------------------------------------------
# 进程级默认控制器（HTTP/MCP/cron/TaskLogger 钩子经此取控制器；lifespan 设置）
# ---------------------------------------------------------------------------

_default_lock = threading.Lock()
_default_controller: Optional[MaintenanceController] = None


def set_default_controller(controller: Optional[MaintenanceController]) -> None:
    """lifespan 装载/卸载（None=进程未初始化，钩子直接放行）。"""
    global _default_controller
    with _default_lock:
        _default_controller = controller


def get_default_controller() -> Optional[MaintenanceController]:
    return _default_controller


@contextlib.contextmanager
def try_admission(kind: str) -> Iterator[Optional[_Lease]]:
    """钩子统一入口：无控制器/正常态 → 放行（yield lease 或 None）。

    维护态 → AdmissionRejected（调用方决定跳过本轮/返回 503）；本上下文
    管理器自身不吞该异常（需在 ``with`` 外由调用方处理）。用法::

        try:
            with try_admission("cron:12") as lease:
                ...
        except AdmissionRejected:
            ...  # 维护中：跳过本轮（零写）
    """
    controller = get_default_controller()
    if controller is None:
        yield None
        return
    with controller.admission_slot(kind) as lease:
        yield lease


def maintenance_active() -> bool:
    """无引擎依赖的哨兵查询（TaskLogger/关闭回写路径用，T06）。"""
    controller = get_default_controller()
    return controller is not None and controller.status().in_maintenance
