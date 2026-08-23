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
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models import OUTCOME_SKIPPED
from app.services.sync_observability import EVENT_TASK_LIFECYCLE
from app.tasks.cron_executor import CronTaskExecutor


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
        """长执行内部类发射 start/heartbeat/timeout_warning/end，且不取消执行。"""

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
