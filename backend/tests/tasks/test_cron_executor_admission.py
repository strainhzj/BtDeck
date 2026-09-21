# -*- coding: utf-8 -*-
"""
CronTaskExecutor 资源治理接入契约测试

【覆盖目标】
- _run_python_internal_class 接受 task dict（不再是 executor 字符串）。
- 重型 task_code（已登记）→ 进入 admission_controller.task_scope；
  admitted=False 时返回 skipped 且**不调 execute**。
- 轻量 task_code（未登记）→ 不经过 admission，直接调 execute。

【接入点】
cron_executor.py::_run_python_internal_class 是 sync-resource-governance 阶段 0+1
的资源治理挂载点。若有人改回旧签名或去掉 admission 包裹，此测试立即报红。
"""

import asyncio
import logging
import sys
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models import OUTCOME_SKIPPED
from app.services.sync_observability import EVENT_TASK_LIFECYCLE
from app.tasks.cron_executor import CronTaskExecutor, TaskExecutionTimeoutError


def _make_executor_with_app() -> CronTaskExecutor:
    """构造带 mock app 的 CronTaskExecutor（避免真 FastAPI 实例）。"""
    executor = CronTaskExecutor()
    executor.app = MagicMock()
    return executor


def _inject_fake_task_class(monkeypatch, module_path: str, class_name: str, execute_mock):
    """向 sys.modules 注入一个伪模块 + 伪任务类，execute 由测试控制。

    让 cron_executor._run_python_internal_class 通过 __import__ 能加载到这个伪类。
    必须是真实 class：白名单修复后解析目标经 inspect.isclass 校验，
    MagicMock 实例（非类）会被拒绝。
    """

    class _Fake:
        def __init__(self, *args, **kwargs):
            pass

        # 类属性 execute 在实例上可访问；AsyncMock 满足
        # asyncio.iscoroutinefunction → 走 await 调用路径
        execute = execute_mock

    fake_module = types.ModuleType(module_path)
    setattr(fake_module, class_name, _Fake)
    monkeypatch.setitem(sys.modules, module_path, fake_module)
    return _Fake


@pytest.fixture(autouse=True)
def _reset_admission():
    """每个测试前重置 admission_controller 状态。"""
    from app.tasks.resource_guard import admission_controller

    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


class TestRunPythonInternalClassSignature:
    """_run_python_internal_class 接受 task dict 契约。"""

    async def test_accepts_task_dict_and_extracts_executor(self, monkeypatch):
        """签名必须是 _run_python_internal_class(task: Dict)，从 task['executor'] 取路径。"""
        execute_mock = AsyncMock(return_value={"status": "ok"})
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_xyz", "FakeTask", execute_mock)

        executor = _make_executor_with_app()
        task = {
            "task_id": 1,
            "task_code": "nonexistent_lightweight",  # 未登记 → 轻量任务
            "task_type": 4,
            "executor": "app.tasks.fake_module_xyz.FakeTask",
        }

        result = await executor._run_python_internal_class(task)
        assert result["success"] is True
        execute_mock.assert_awaited_once()


class TestHeavyTaskAdmission:
    """重型任务接入 admission 行为。"""

    async def test_heavy_task_admitted_runs_execute(self, monkeypatch):
        """admitted=True 时 execute 被调用，且在 task_scope 内。"""
        execute_mock = AsyncMock(return_value={"status": "ok"})
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_heavy_ok", "HeavyTask", execute_mock)

        executor = _make_executor_with_app()
        # 使用真实注册表中的重型 task_code
        task = {
            "task_id": 1,
            "task_code": "torrent_info_sync_ac608e4d",
            "task_type": 4,
            "executor": "app.tasks.fake_module_heavy_ok.HeavyTask",
        }

        result = await executor._run_python_internal_class(task)
        assert result["success"] is True
        execute_mock.assert_awaited_once()

    async def test_heavy_task_skipped_does_not_call_execute(self, monkeypatch):
        """admitted=False 时返回 skipped，execute **不被调用**（核心防回归）。"""
        execute_mock = AsyncMock(return_value={"status": "ok"})
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_heavy_skip", "HeavyTask", execute_mock)

        # 强制 admission 返回 admitted=False（构造同类去重场景）
        from app.tasks.resource_guard import admission_controller
        from app.tasks.task_profiles import get_profile

        task_code = "torrent_info_sync_ac608e4d"
        profile = get_profile(task_code)
        holder = await admission_controller.acquire(task_code, profile)
        assert holder.admitted is True  # 占据令牌

        executor = _make_executor_with_app()
        task = {
            "task_id": 2,
            "task_code": task_code,
            "task_type": 4,
            "executor": "app.tasks.fake_module_heavy_skip.HeavyTask",
        }

        result = await executor._run_python_internal_class(task)

        # ★ 核心断言：skipped=True（区分资源治理跳过 vs 真失败），
        # success=True（避免 task_log 误判故障/告警），且 execute 未被调用
        assert result.get("skipped") is True
        assert result["success"] is True
        assert "[ADMISSION_SKIP]" in result["log_detail"]
        # ★ W3-4：结果 dict 携带六态 outcome 与跳过原因机器码（落库契约）
        assert result["outcome"] == OUTCOME_SKIPPED
        assert result["skip_reason"] == "resource_busy"
        execute_mock.assert_not_called()

        # 清理
        admission_controller.release(task_code)

    async def test_heavy_task_skipped_log_carries_reason(self, monkeypatch):
        """skipped 日志含 task_code/reason/字段（运维溯源）。"""
        execute_mock = AsyncMock()
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_log", "Task", execute_mock)

        from app.tasks.resource_guard import admission_controller
        from app.tasks.task_profiles import get_profile

        task_code = "tracker_reannounce"
        profile = get_profile(task_code)
        holder = await admission_controller.acquire(task_code, profile)
        assert holder.admitted is True  # 占据令牌

        executor = _make_executor_with_app()
        task = {
            "task_id": 3,
            "task_code": task_code,
            "task_type": 4,
            "executor": "app.tasks.fake_module_log.Task",
        }

        result = await executor._run_python_internal_class(task)
        # skipped=True 区分资源治理跳过；success=True 避免误判故障
        assert result.get("skipped") is True
        assert result["success"] is True
        # 日志含 task_code 与 reason + 机器可解析标记
        assert "[ADMISSION_SKIP]" in result["log_detail"]
        assert task_code in result["log_detail"]
        assert "duplicate_heavy_task_pending" in result["log_detail"]
        # W3-4：准入跳过落库契约（outcome=skipped + 稳定机器码 resource_busy）
        assert result["outcome"] == OUTCOME_SKIPPED
        assert result["skip_reason"] == "resource_busy"

        admission_controller.release(task_code)


class TestLightTaskBypass:
    """轻量任务（未登记）不走 admission。"""

    async def test_light_task_does_not_touch_admission(self, monkeypatch):
        """轻量 task_code 直接调 execute，不经过 admission_controller。"""
        execute_mock = AsyncMock(return_value={"status": "ok"})
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_light", "LightTask", execute_mock)

        # 监视 admission_controller.task_scope 是否被调
        from app.tasks.resource_guard import admission_controller

        executor = _make_executor_with_app()
        task = {
            "task_id": 4,
            "task_code": "some_random_light_task_code",  # 未登记
            "task_type": 4,
            "executor": "app.tasks.fake_module_light.LightTask",
        }

        with patch.object(admission_controller, "task_scope", new=MagicMock()) as scope_mock:
            result = await executor._run_python_internal_class(task)

        assert result["success"] is True
        execute_mock.assert_awaited_once()
        # admission_controller.task_scope 不应被进入
        scope_mock.assert_not_called()


class TestInternalClassResultPropagation:
    """内部类业务终态必须进入 Cron task_logs，而不是统一伪造 success。"""

    async def test_failed_business_result_is_not_reported_as_cron_success(self, monkeypatch):
        execute_mock = AsyncMock(
            return_value={
                "status": "error",
                "message": "扫描未完成",
                "execution_log": ["扫描已提交", "扫描终态 status=failed"],
            }
        )
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_orphan_result", "Task", execute_mock)

        executor = _make_executor_with_app()
        result = await executor._run_python_internal_class(
            {
                "task_id": 5,
                "task_code": "some_random_light_task_code",
                "task_type": 4,
                "executor": "app.tasks.fake_module_orphan_result.Task",
            }
        )

        assert result["success"] is False
        assert result["outcome"] == "failed"
        assert "扫描终态 status=failed" in result["log_detail"]

    async def test_execution_context_phase_is_included_in_task_log_detail(self, monkeypatch):
        class PhaseTask:
            def set_execution_context(self, *, execution_logger=None, timeout_seconds=None):
                self.execution_logger = execution_logger

            async def execute(self, **kwargs):
                self.execution_logger("扫描已提交")
                self.execution_logger("扫描终态 status=completed")
                return {"status": "success", "message": "扫描与自动清理已完成"}

        fake_module = types.ModuleType("app.tasks.fake_module_phase")
        fake_module.PhaseTask = PhaseTask
        monkeypatch.setitem(sys.modules, "app.tasks.fake_module_phase", fake_module)

        executor = _make_executor_with_app()
        result = await executor._run_python_internal_class(
            {
                "task_id": 6,
                "task_code": "some_random_light_task_code",
                "task_type": 4,
                "executor": "app.tasks.fake_module_phase.PhaseTask",
            }
        )

        assert result["success"] is True
        assert "扫描已提交" in result["log_detail"]
        assert "扫描终态 status=completed" in result["log_detail"]

    async def test_task_lifecycle_emits_heartbeat_and_timeout_warning(self, monkeypatch):
        """开关关闭时长执行内部类只发射 start/heartbeat/timeout_warning/end，不取消执行。"""

        async def slow_execute(**kwargs):
            await asyncio.sleep(0.08)
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=slow_execute)
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_observe", "ObserveTask", execute_mock)

        executor = _make_executor_with_app()
        task = {
            "task_id": 9,
            "task_name": "观测测试任务",
            "task_code": "observe_light_task",
            "task_type": 4,
            "timeout_seconds": 0.02,
            "executor": "app.tasks.fake_module_observe.ObserveTask",
        }

        with (
            patch.object(settings, "CRON_TASK_TIMEOUT_ENFORCE", False),
            patch.object(settings, "SYNC_TASK_OBSERVABILITY_INTERVAL_SECONDS", 0.01),
            patch("app.tasks.cron_executor.log_event") as mock_log,
        ):
            result = await executor._run_python_internal_class(task)

        assert result["success"] is True
        execute_mock.assert_awaited_once()
        lifecycle_calls = [call for call in mock_log.call_args_list if call.args[0] == EVENT_TASK_LIFECYCLE]
        states = [call.kwargs.get("state") for call in lifecycle_calls]
        assert states[0] == "start"
        assert "timeout_warning" in states
        assert "end" in states
        assert all(call.kwargs.get("task_code") == "observe_light_task" for call in lifecycle_calls)


class TestTimeoutEnforcement:
    """cron 层超时强制终止（2026-08-25）：超 timeout_seconds 的执行被 wait_for 终止。

    回归锚点：生产案例 cron-7-20260825111000（Tracker 状态同步）挂 8.75h，
    旧实现 timeout_seconds 仅观测打标不终止。若有人移除 wait_for 或穿透
    分支，这些测试立即报红。
    """

    def _timeout_task(self, timeout_seconds, module_name: str) -> dict:
        return {
            "task_id": 91,
            "task_name": "超时强杀测试任务",
            "task_code": f"timeout_light_{module_name}",
            "task_type": 4,
            "timeout_seconds": timeout_seconds,
            "executor": f"app.tasks.fake_module_{module_name}.Task",
        }

    async def test_async_task_killed_after_timeout_and_error_penetrates(self, monkeypatch):
        """async 执行超 timeout_seconds：wait_for 终止 + TaskExecutionTimeoutError
        穿透 _run_python_internal_class 的通用 except Exception 兜底（否则会被
        吞成普通失败 dict，下游无法识别超时语义）。"""

        async def slow_execute(**kwargs):
            await asyncio.sleep(0.5)
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=slow_execute)
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_timeout_kill", "Task", execute_mock)

        executor = _make_executor_with_app()
        task = self._timeout_task(0.02, "timeout_kill")

        with (
            patch.object(settings, "CRON_TASK_TIMEOUT_ENFORCE", True),
            patch.object(settings, "SYNC_TASK_OBSERVABILITY_INTERVAL_SECONDS", 0.01),
            patch("app.tasks.cron_executor.log_event") as mock_log,
        ):
            with pytest.raises(TaskExecutionTimeoutError):
                await executor._run_python_internal_class(task)

        states = [call.kwargs.get("state") for call in mock_log.call_args_list if call.args[0] == EVENT_TASK_LIFECYCLE]
        assert "timeout_killed" in states

    async def test_zero_or_negative_timeout_not_enforced(self, monkeypatch):
        """timeout_seconds<=0 归一为 None：不强制终止（wait_for(timeout=0) 立即取消不合理）。"""

        async def quick_execute(**kwargs):
            await asyncio.sleep(0.05)
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=quick_execute)
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_timeout_zero", "Task", execute_mock)

        executor = _make_executor_with_app()
        # 开关显式开启，但 timeout<=0 应归一不强制
        with patch.object(settings, "CRON_TASK_TIMEOUT_ENFORCE", True):
            for raw_timeout in (0, -1):
                execute_mock.reset_mock()
                task = self._timeout_task(raw_timeout, "timeout_zero")
                result = await executor._run_python_internal_class(task)
                assert result["success"] is True, f"timeout={raw_timeout} 不应触发强制终止"
                execute_mock.assert_awaited_once()

    async def test_task_body_timeout_before_deadline_not_misread(self, monkeypatch):
        """任务体在预算内自身抛 TimeoutError：走通用异常路径，不转译为强制超时。"""

        async def fail_fast(**kwargs):
            raise asyncio.TimeoutError("remote call timeout")

        execute_mock = AsyncMock(side_effect=fail_fast)
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_timeout_body", "Task", execute_mock)

        executor = _make_executor_with_app()
        task = self._timeout_task(30, "timeout_body")

        result = await executor._run_python_internal_class(task)
        # 被通用兜底捕获为普通失败（elapsed < timeout，非强制超时）
        assert result["success"] is False
        assert "Python内部类执行异常" in result["log_detail"]

    async def test_thread_mode_timeout_abandons_wait(self, monkeypatch):
        """thread 模式超时：协程层面放弃等待并抛 TaskExecutionTimeoutError
        （底层线程继续跑完是既有设计，不在此断言线程终止）。"""

        def slow_sync_execute(**kwargs):
            time.sleep(0.3)
            return {"status": "ok"}

        class _SyncTask:
            def __init__(self, *args, **kwargs):
                pass

            def execute(self, **kwargs):
                return slow_sync_execute(**kwargs)

        fake_module = types.ModuleType("app.tasks.fake_module_timeout_thread")
        fake_module.Task = _SyncTask
        monkeypatch.setitem(sys.modules, "app.tasks.fake_module_timeout_thread", fake_module)

        executor = _make_executor_with_app()
        task = self._timeout_task(0.02, "timeout_thread")

        with patch.object(settings, "CRON_TASK_TIMEOUT_ENFORCE", True):
            with pytest.raises(TaskExecutionTimeoutError):
                await executor._run_python_internal_class(task)

    async def test_heavy_task_timeout_releases_heavy_sync(self, monkeypatch):
        """【回归锚点：生产事故】重型任务（task_scope 持锁）超时被杀后 heavy_sync
        令牌必须释放——生产案例 cron-7-20260825111000 令牌被占 8.75h，连锁
        堵死 4 个重型任务。task_scope 的 finally（release 为纯同步代码）在
        取消传播中完整执行。"""
        from app.tasks.resource_guard import admission_controller
        from app.tasks.task_profiles import get_profile

        task_code = "torrent_info_sync_ac608e4d"  # 真实注册表中的重型 code

        async def slow_execute(**kwargs):
            await asyncio.sleep(0.5)
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=slow_execute)
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_timeout_heavy", "Task", execute_mock)

        executor = _make_executor_with_app()
        task = {
            "task_id": 92,
            "task_name": "重型超时任务",
            "task_code": task_code,
            "task_type": 4,
            "timeout_seconds": 0.02,
            "executor": "app.tasks.fake_module_timeout_heavy.Task",
        }

        with (
            patch.object(settings, "CRON_TASK_TIMEOUT_ENFORCE", True),
            patch.object(settings, "SYNC_TASK_OBSERVABILITY_INTERVAL_SECONDS", 0.01),
        ):
            with pytest.raises(TaskExecutionTimeoutError):
                await executor._run_python_internal_class(task)

        # 令牌已释放：running 无残留，下一个同类任务可立即 admitted
        assert task_code not in admission_controller.running
        holder = await admission_controller.acquire(task_code, get_profile(task_code))
        assert holder.admitted is True, "超时强杀后 heavy_sync 令牌应可立即重新获取"
        admission_controller.release(task_code)

    async def test_enforce_enabled_regular_exception_path_unchanged(self, monkeypatch):
        """强杀开启不影响普通异常路径：RuntimeError 仍走通用兜底为普通失败。"""

        async def fail_execute(**kwargs):
            raise RuntimeError("boom")

        execute_mock = AsyncMock(side_effect=fail_execute)
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_timeout_regexc", "Task", execute_mock)

        executor = _make_executor_with_app()
        task = self._timeout_task(30, "timeout_regexc")

        with patch.object(settings, "CRON_TASK_TIMEOUT_ENFORCE", True):
            result = await executor._run_python_internal_class(task)

        assert result["success"] is False
        assert "Python内部类执行异常" in result["log_detail"]
        assert "boom" in result["log_detail"]

    async def test_missing_timeout_config_not_enforced(self, monkeypatch):
        """未配置 timeout_seconds（None）不强制终止，与开关关闭时旧语义一致。"""

        async def slow_execute(**kwargs):
            await asyncio.sleep(0.06)
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=slow_execute)
        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_timeout_unset", "Task", execute_mock)

        executor = _make_executor_with_app()
        task = self._timeout_task(None, "timeout_unset")
        task.pop("timeout_seconds")  # 完全未配置（键不存在）

        with patch.object(settings, "CRON_TASK_TIMEOUT_ENFORCE", True):
            result = await executor._run_python_internal_class(task)

        assert result["success"] is True
        execute_mock.assert_awaited_once()


class TestProgressStallObservation:
    """心跳进度停滞告警 + faulthandler 全线程栈自动转储（2026-08-25）。

    回归锚点：生产案例 8.75h 期间仅剩静默心跳，无任何现场证据；修复后停滞
    超阈值的心跳自动提级 WARNING 并转储线程栈（每次运行至多一次）。
    """

    TASK_STALL = {"task_id": 31, "task_name": "停滞观测任务", "task_code": "stall_light_task"}

    async def _run_observed(self, monkeypatch, execute_mock, execution_state, *, threshold):
        executor = _make_executor_with_app()
        with (
            patch.object(settings, "SYNC_TASK_PROGRESS_STALL_WARNING_SECONDS", threshold),
            patch.object(settings, "SYNC_TASK_OBSERVABILITY_INTERVAL_SECONDS", 0.01),
            patch("app.tasks.cron_executor.log_event") as mock_log,
            patch("app.tasks.cron_executor.faulthandler.dump_traceback") as mock_dump,
        ):
            result = await executor._execute_internal_method_observed(
                execute_mock, self.TASK_STALL, "stall_light_task", execution_state
            )
        heartbeats = [
            call
            for call in mock_log.call_args_list
            if call.args[0] == EVENT_TASK_LIFECYCLE and call.kwargs.get("state") == "heartbeat"
        ]
        stalled = [call for call in heartbeats if call.kwargs.get("progress_stalled") is True]
        return result, heartbeats, stalled, mock_dump

    async def test_stalled_heartbeat_warns_and_dumps_once(self, monkeypatch):
        """进度停滞超阈值：心跳提级 WARNING + progress_stalled=True，线程栈
        转储整次运行至多一次（节流防日志风暴）。"""

        async def slow_execute(**kwargs):
            await asyncio.sleep(0.12)
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=slow_execute)
        # last_progress_monotonic 指向 999s 前：任意时刻 last_progress_ms 均超 0.05s 阈值
        execution_state = {"last_progress_monotonic": time.monotonic() - 999.0}

        result, heartbeats, stalled, mock_dump = await self._run_observed(
            monkeypatch, execute_mock, execution_state, threshold=0.05
        )

        assert result == {"status": "ok"}
        assert heartbeats, "应发射心跳事件"
        assert stalled, "停滞心跳应携带 progress_stalled=True"
        assert all(call.kwargs.get("level") == logging.WARNING for call in stalled)
        assert mock_dump.call_count == 1, "线程栈转储应节流为整次运行至多一次"
        # progress_stalled 仅应出现在心跳事件上
        assert all(call.kwargs.get("state") == "heartbeat" for call in stalled)

    async def test_progress_updates_suppress_stall_warning(self, monkeypatch):
        """执行期间进度持续推进（模拟 execution_logger 注入）：不触发停滞告警。"""
        execution_state = {"last_progress_monotonic": time.monotonic()}

        async def executing_with_progress(**kwargs):
            # 模拟任务体周期性上报进度（record_execution_event 的效果）
            await asyncio.sleep(0.06)
            execution_state["last_progress_monotonic"] = time.monotonic()
            await asyncio.sleep(0.06)
            execution_state["last_progress_monotonic"] = time.monotonic()
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=executing_with_progress)
        # 阈值 0.5s >> 进度推进间隔 0.06s：任意心跳时刻 last_progress_ms < 0.5s
        result, heartbeats, stalled, mock_dump = await self._run_observed(
            monkeypatch, execute_mock, execution_state, threshold=0.5
        )

        assert result == {"status": "ok"}
        assert heartbeats, "应发射心跳事件"
        assert not stalled, "进度持续推进时不应触发停滞告警"
        mock_dump.assert_not_called()

    async def test_stall_warning_disabled_by_zero_threshold(self, monkeypatch):
        """阈值 0 关闭：即使停滞也不告警不转储。"""
        execution_state = {"last_progress_monotonic": time.monotonic() - 999.0}

        async def slow_execute(**kwargs):
            await asyncio.sleep(0.08)
            return {"status": "ok"}

        execute_mock = AsyncMock(side_effect=slow_execute)
        result, heartbeats, stalled, mock_dump = await self._run_observed(
            monkeypatch, execute_mock, execution_state, threshold=0
        )

        assert result == {"status": "ok"}
        assert not stalled, "阈值 0 应完全关闭停滞告警"
        mock_dump.assert_not_called()


class TestSyncExecuteOffloaded:
    """B-3 卫生项：同步 execute 必须经 asyncio.to_thread 执行。

    直接在事件循环线程上跑同步任务体会阻塞整个 API（含 active-torrents
    1s 轮询），制造全局假超时。当前全部内置任务为 async execute（分支
    不可达），此测试为未来新增同步任务封死回归路径。
    """

    async def test_sync_execute_runs_off_event_loop(self, monkeypatch):
        """同步 execute 在非事件循环线程执行，结果正常归一化。"""
        import threading

        executed_threads = []

        def _sync_execute(self_inner, app=None, **kwargs):
            executed_threads.append(threading.current_thread())
            return {"status": "ok"}

        _inject_fake_task_class(monkeypatch, "app.tasks.fake_module_sync", "SyncTask", _sync_execute)

        executor = _make_executor_with_app()
        task = {
            "task_id": 1,
            "task_code": "nonexistent_lightweight",  # 未登记 → 轻量任务路径
            "task_type": 4,
            "executor": "app.tasks.fake_module_sync.SyncTask",
        }

        result = await executor._run_python_internal_class(task)
        assert result["success"] is True
        assert len(executed_threads) == 1
        # 核心断言：执行线程不是事件循环主线程（to_thread 生效）
        assert executed_threads[0] is not threading.main_thread(), "同步 execute 必须经 to_thread 移出事件循环线程"
