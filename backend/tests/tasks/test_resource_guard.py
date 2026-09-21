# -*- coding: utf-8 -*-
"""
TaskAdmissionController 资源准入回归测试

【覆盖目标】
1. 准入成功 + release 正常释放（running/queued 归零）。
2. 异常释放（task_scope 内 raise）资源不泄漏。
3. 同类去重跳过：A 持有时 B 同 task_code 立即 admitted=False（SKIP_DUPLICATE）。
4. 队列名额满：queued 达 queue_limit 后立即跳过。
5. 等待超时：不同 task_code 但 heavy_sync 占满，超 wait_timeout 后 SKIP_WAIT_TIMEOUT。
6. 不同 task_code 互斥：A release 后 B 才 admitted（跨任务类型资源竞争治理）。
7. 结构化日志含 task_code/admitted/queued_count 字段。
8. release 幂等：未 acquire 的 task_code release 不会归还令牌（防 semaphore 溢出）。

【测试隔离】
每个测试 setup 调 admission_controller.reset_state()，避免进程级单例状态泄漏。
"""

import asyncio

import pytest

from app.tasks.resource_guard import (
    AdmissionOwner,
    SKIP_DUPLICATE,
    SKIP_WAIT_TIMEOUT,
    AdmissionResult,
    admission_controller,
)
from app.tasks.task_profiles import TaskProfile


# 测试用 profile 工厂：可控 queue_limit / wait_timeout
def _profile(
    task_code: str = "test_task",
    queue_limit: int = 1,
    wait_timeout: float = 1.0,
) -> TaskProfile:
    return TaskProfile(
        task_code=task_code,
        heavy_sync=True,
        per_downloader=False,
        queue_limit=queue_limit,
        wait_timeout=wait_timeout,
        description="测试用 profile",
    )


@pytest.fixture(autouse=True)
def _reset_admission():
    """每个测试前重置进程级单例状态，保证隔离。"""
    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


class TestAdmissionBasics:
    """准入/释放基础契约。"""

    async def test_acquire_then_release_clears_state(self):
        """acquire 成功 → release 后 running 与 queued 归零。"""
        profile = _profile()
        result = await admission_controller.acquire("test_task", profile)

        assert result.admitted is True
        assert result.skip_reason is None
        assert "test_task" in admission_controller.running

        admission_controller.release("test_task")
        assert "test_task" not in admission_controller.running
        assert admission_controller.queued_count("test_task") == 0

    async def test_acquire_admit_result_carries_counts(self):
        """AdmissionResult 携带 running_count/queued_count/task_code（日志溯源用）。"""
        result = await admission_controller.acquire("abc", _profile("abc"))
        assert result.task_code == "abc"
        assert result.running_count >= 1
        assert result.queued_count == 0  # 已转 running
        admission_controller.release("abc")


class TestDuplicateSkip:
    """同类去重跳过策略。"""

    async def test_same_task_code_running_skips_immediately(self):
        """A 持有 heavy_sync 时，同 task_code 的 B 立即 admitted=False（不阻塞）。

        关键断言：wait_seconds 接近 0（证明没有阻塞等待）。
        """
        profile = _profile("dup_task", queue_limit=1, wait_timeout=5.0)
        a = await admission_controller.acquire("dup_task", profile)
        assert a.admitted is True

        # B 同 task_code：A 已在 running → 立即跳过
        b = await admission_controller.acquire("dup_task", profile)
        assert b.admitted is False
        assert b.skip_reason == SKIP_DUPLICATE
        # 关键：不阻塞，wait 接近 0（容忍调度抖动 0.2s）
        assert b.wait_seconds < 0.2, f"同类去重应立即跳过，实际等待 {b.wait_seconds}s"

        admission_controller.release("dup_task")

    async def test_queue_limit_full_skips_immediately(self):
        """queued 达 queue_limit，新请求立即跳过（不阻塞）。

        构造（queue_limit 是 per-task-code 的）：
        - A（task_code "X"）持有 heavy_sync 令牌；
        - B（task_code "Y"，与 A 不同）排队等待 heavy_sync，queued["Y"]=1；
        - C（task_code "Y"，与 B 同类）→ queued["Y"] 已达 limit → 立即跳过。
        """
        profile = _profile(queue_limit=1, wait_timeout=5.0)
        a = await admission_controller.acquire("task_x", profile)
        assert a.admitted is True

        # B 不同 task_code → 进入排队等待 heavy_sync
        b_task = asyncio.create_task(admission_controller.acquire("task_y", profile))
        await asyncio.sleep(0.05)  # 让 B 进入排队
        assert admission_controller.queued_count("task_y") == 1

        # C 与 B 同 task_code：queue 已满 → 立即跳过
        c = await admission_controller.acquire("task_y", profile)
        assert c.admitted is False
        assert c.skip_reason == SKIP_DUPLICATE
        assert c.wait_seconds < 0.2

        # 清理：释放 A，B 获得
        admission_controller.release("task_x")
        b_result = await b_task
        assert b_result.admitted is True
        admission_controller.release("task_y")


class TestWaitTimeout:
    """等待超时策略。"""

    async def test_different_task_code_waits_then_times_out(self):
        """不同 task_code 但 heavy_sync 占满，超 wait_timeout 后跳过。

        heavy_sync 默认并发 1（settings.SYNC_HEAVY_CONCURRENCY=1）。
        """
        profile_a = _profile("task_a", wait_timeout=5.0)
        profile_b = _profile("task_b", wait_timeout=0.2)  # B 超时快

        a = await admission_controller.acquire("task_a", profile_a)
        assert a.admitted is True

        # B 不同 task_code，但 heavy_sync 满 → 等 0.2s 后超时
        b = await admission_controller.acquire("task_b", profile_b)
        assert b.admitted is False
        assert b.skip_reason == SKIP_WAIT_TIMEOUT
        assert b.wait_seconds >= 0.15  # 确实等了一段时间
        assert b.wait_seconds < 0.5

        admission_controller.release("task_a")

    async def test_wait_timeout_identifies_holder_context(self):
        """等待超时时带出占用者 task/run/phase/年龄，定位 heavy_sync 真正 holder。"""
        holder_profile = _profile("tracker_holder", wait_timeout=5.0)
        waiter_profile = _profile("info_waiter", wait_timeout=0.05)
        holder = await admission_controller.acquire(
            "tracker_holder",
            holder_profile,
            owner=AdmissionOwner(
                task_id=7,
                task_name="Tracker同步",
                cron_run_id="cron-7-test",
                sync_run_id="sync-test",
            ),
        )
        assert holder.admitted is True
        admission_controller.update_holder_phase("tracker_holder", "tracker_status", sync_run_id="sync-test")

        result = await admission_controller.acquire("info_waiter", waiter_profile)

        assert result.admitted is False
        assert result.skip_reason == SKIP_WAIT_TIMEOUT
        assert result.blocked_by_task_code == "tracker_holder"
        assert result.blocked_by_task_id == 7
        assert result.blocked_by_cron_run_id == "cron-7-test"
        assert result.blocked_by_sync_run_id == "sync-test"
        assert result.blocked_by_phase == "tracker_status"
        assert result.blocked_by_age_seconds is not None
        assert result.blocked_by_age_seconds >= 0
        assert result.blocked_by_pid is not None
        assert result.blocked_by_worker_instance_id

        admission_controller.release("tracker_holder")

    async def test_different_task_code_admits_after_release(self):
        """不同 task_code 互斥：A release 后 B 才 admitted（跨任务竞争治理核心）。

        验证 heavy_sync 是全局令牌，跨 task_code 串行化。
        """
        profile_a = _profile("task_a", wait_timeout=5.0)
        profile_b = _profile("task_b", wait_timeout=5.0)

        a = await admission_controller.acquire("task_a", profile_a)
        assert a.admitted is True

        # B 异步等待
        b_task = asyncio.create_task(admission_controller.acquire("task_b", profile_b))
        await asyncio.sleep(0.05)
        assert not b_task.done()  # B 还在等

        admission_controller.release("task_a")

        b = await asyncio.wait_for(b_task, timeout=1.0)
        assert b.admitted is True
        assert b.skip_reason is None
        admission_controller.release("task_b")


class TestTaskScope:
    """task_scope 上下文管理器。"""

    async def test_scope_admitted_runs_body(self):
        """admitted=True 时进入 body，退出后释放。"""
        profile = _profile("scope_ok")
        async with admission_controller.task_scope("scope_ok", profile) as result:
            assert result.admitted is True
            assert "scope_ok" in admission_controller.running
        # 退出后释放
        assert "scope_ok" not in admission_controller.running

    async def test_scope_skipped_does_not_enter_body_after_yield(self):
        """admitted=False 时 body 内部应主动 return，scope 退出不释放（因未持有）。"""
        profile = _profile("scope_skip", queue_limit=1, wait_timeout=5.0)

        # 先占据令牌
        holder = await admission_controller.acquire("scope_skip", profile)
        assert holder.admitted is True

        # scope 内第二次 acquire 应被跳过
        body_entered = False
        async with admission_controller.task_scope("scope_skip", profile) as result:
            if not result.admitted:
                # 调用方应据此 return
                pass
            else:
                body_entered = True

        assert body_entered is False, "admitted=False 时调用方不该执行任务体"
        # holder 仍持有
        assert "scope_skip" in admission_controller.running

        admission_controller.release("scope_skip")

    async def test_scope_releases_on_exception(self):
        """task_scope 内 raise 时资源必须释放（防泄漏核心断言）。"""
        profile = _profile("scope_exc")

        with pytest.raises(RuntimeError, match="boom"):
            async with admission_controller.task_scope("scope_exc", profile) as result:
                assert result.admitted is True
                raise RuntimeError("boom")

        # 关键：异常后令牌归还，running 清空
        assert "scope_exc" not in admission_controller.running
        # 后续任务能正常获取（证明令牌确实释放）
        again = await admission_controller.acquire("scope_exc", profile)
        assert again.admitted is True
        admission_controller.release("scope_exc")


class TestAcquireExceptionPath:
    """acquire 内部 heavy_sync.acquire() 抛非 TimeoutError 异常时的资源归还。

    覆盖 resource_guard.acquire 的 except Exception 分支（防排队名额泄漏）。
    """

    async def test_acquire_exception_releases_queue_slot(self, monkeypatch):
        """heavy_sync.acquire 抛非超时异常时，排队名额必须归还，异常向上抛。

        场景：mock heavy_sync.acquire 抛 RuntimeError，验证：
        1. 异常被向上抛（调用方感知）。
        2. queued[task_code] 归零（排队名额不泄漏）。
        3. 后续同 task_code 能正常 acquire（名额可用）。
        """
        profile = _profile("exc_path", queue_limit=1, wait_timeout=5.0)

        # mock heavy_sync.acquire 抛非 Timeout 异常
        original_sem = admission_controller._state.heavy_sync

        class FakeSemaphore:
            async def acquire(self):
                raise RuntimeError("simulated downstream failure")

        admission_controller._state.heavy_sync = FakeSemaphore()

        try:
            with pytest.raises(RuntimeError, match="simulated downstream failure"):
                await admission_controller.acquire("exc_path", profile)

            # 关键断言：排队名额已归还（不泄漏）
            assert admission_controller.queued_count("exc_path") == 0
        finally:
            admission_controller._state.heavy_sync = original_sem

        # 恢复真实 semaphore 后，同 task_code 能正常 acquire（名额可用）
        ok = await admission_controller.acquire("exc_path", profile)
        assert ok.admitted is True
        admission_controller.release("exc_path")


class TestReleaseIdempotent:
    """release 幂等性（防 semaphore 计数溢出）。

    核心断言策略：跨 task_code 验证溢出后果。
    heavy_sync 并发=1，正常情况下同一时刻只能有 1 个任务 admitted=True。
    若 release 守卫失效（多归还令牌），第二个不同 task_code 会错误地 admitted=True，
    破坏全局互斥语义——这是测试要抓的可观察后果。
    """

    async def test_double_release_does_not_overreturn_semaphore(self):
        """未在 running 的 task_code release 是 no-op，不让 semaphore 计数超过初始值。

        场景构造：
        1. A（task_code "x"）合法 acquire + release（正常归还 1 个令牌，计数回到 1）。
        2. 对 "x" 再调一次 release（误调，应 no-op）。
        3. 若守卫失效：计数溢出到 2 → B 和 C 两个不同 task_code 同时 admitted=True（破坏互斥）。
        4. 若守卫正常：计数仍为 1 → B admitted=True 后 C 必然 admitted=False（互斥生效）。
        """
        profile = _profile("x", queue_limit=1, wait_timeout=5.0)
        # 步骤 1：A 正常 acquire + release
        a = await admission_controller.acquire("x", profile)
        assert a.admitted is True
        admission_controller.release("x")
        assert "x" not in admission_controller.running

        # 步骤 2：误调 release（守卫应拦截，不让 semaphore 计数超过 1）
        admission_controller.release("x")

        # 步骤 3-4：跨 task_code 验证互斥仍生效
        # B 占住令牌
        b = await admission_controller.acquire("y1", profile)
        assert b.admitted is True
        try:
            # 关键断言：若守卫失效导致 semaphore 计数溢出，C 会错误 admitted=True
            c = await admission_controller.acquire("y2", profile)
            assert c.admitted is False, (
                "release 守卫失效：semaphore 计数溢出，导致两个不同 task_code 同时 admitted=True，"
                "破坏 heavy_sync 全局互斥语义"
            )
        finally:
            admission_controller.release("y1")

    async def test_release_unknown_task_code_is_noop(self):
        """从未 acquire 的 task_code 调 release 是 no-op，不影响 semaphore 计数。"""
        # 直接对未知的 task_code release
        admission_controller.release("never_acquired")

        # semaphore 计数应仍为初始值，能正常 acquire
        profile = _profile("first", wait_timeout=5.0)
        result = await admission_controller.acquire("first", profile)
        assert result.admitted is True
        admission_controller.release("first")


class TestStructuredLog:
    """结构化准入日志 extra 组装契约（阶段 0 基线观测的核心）。

    测试策略：直接断言 _build_log_extra 纯函数返回的 dict，
    而非通过 caplog/spy 截 _log_admission 入参（入参 ≠ extra，会漏报 extra 组装 bug）。
    全量套件中 logging.disable / propagate 改动不影响本测试，因为不经过 logging 路由。
    """

    def test_admitted_path_extra_contains_all_required_fields(self):
        """admitted=True 路径的 extra 必须含运维溯源所需的全部 7 个字段。"""
        from app.tasks.resource_guard import _build_log_extra

        result = AdmissionResult(
            admitted=True,
            skip_reason=None,
            wait_seconds=0.123,
            running_count=1,
            queued_count=0,
            task_code="log_task",
        )
        profile = TaskProfile(
            task_code="log_task",
            heavy_sync=True,
            per_downloader=False,
            queue_limit=1,
            wait_timeout=5.0,
            description="",
        )

        extra = _build_log_extra(result, profile)

        # 关键：逐字段断言（任何字段被误删/拼错都会立即报红）
        assert extra["task_code"] == "log_task"
        assert extra["admitted"] is True
        assert extra["skip_reason"] is None
        assert extra["wait_seconds"] == 0.123
        assert extra["running_count"] == 1
        assert extra["queued_count"] == 0
        assert extra["queue_limit"] == 1
        # 字段集合完整（防有人新增字段后忘了填）
        assert set(extra.keys()) == {
            "task_code",
            "admitted",
            "skip_reason",
            "wait_seconds",
            "running_count",
            "queued_count",
            "queue_limit",
        }

    def test_skipped_path_extra_carries_skip_reason(self):
        """admitted=False 路径的 extra 必须含 skip_reason（运维告警规则依赖此字段）。"""
        from app.tasks.resource_guard import _build_log_extra

        result = AdmissionResult(
            admitted=False,
            skip_reason=SKIP_DUPLICATE,
            wait_seconds=0.001,
            running_count=1,
            queued_count=1,
            task_code="warn_task",
        )
        profile = TaskProfile(
            task_code="warn_task",
            heavy_sync=True,
            per_downloader=False,
            queue_limit=1,
            wait_timeout=5.0,
            description="",
        )

        extra = _build_log_extra(result, profile)

        assert extra["admitted"] is False
        assert extra["skip_reason"] == SKIP_DUPLICATE
        assert extra["task_code"] == "warn_task"
        # queue_limit 来自 profile，不是 result（防字段来源混淆）
        assert extra["queue_limit"] == 1

    def test_build_log_extra_is_pure(self):
        """_build_log_extra 是纯函数：不修改入参，相同入参返回相同结果。"""
        from app.tasks.resource_guard import _build_log_extra

        result = AdmissionResult(admitted=True, task_code="pure", wait_seconds=0.0, running_count=1, queued_count=0)
        profile = TaskProfile(
            task_code="pure",
            heavy_sync=True,
            per_downloader=False,
            queue_limit=1,
            wait_timeout=1.0,
        )

        extra1 = _build_log_extra(result, profile)
        extra2 = _build_log_extra(result, profile)
        assert extra1 == extra2
        # 不修改入参（AdmissionResult 是 dataclass，但验证一下以防意外）
        assert result.task_code == "pure"
        assert profile.queue_limit == 1
