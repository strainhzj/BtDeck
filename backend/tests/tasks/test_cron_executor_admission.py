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

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import OUTCOME_SKIPPED
from app.tasks.cron_executor import CronTaskExecutor


def _make_executor_with_app() -> CronTaskExecutor:
    """构造带 mock app 的 CronTaskExecutor（避免真 FastAPI 实例）。"""
    executor = CronTaskExecutor()
    executor.app = MagicMock()
    return executor


def _inject_fake_task_class(monkeypatch, module_path: str, class_name: str, execute_mock):
    """向 sys.modules 注入一个伪模块 + 伪任务类，execute 由测试控制。

    让 cron_executor._run_python_internal_class 通过 __import__ 能加载到这个伪类。
    """
    fake_module = types.ModuleType(module_path)
    fake_task_class = MagicMock()
    fake_task_class.return_value = MagicMock(execute=execute_mock)
    setattr(fake_module, class_name, fake_task_class)
    monkeypatch.setitem(sys.modules, module_path, fake_module)
    return fake_task_class


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
        _inject_fake_task_class(monkeypatch, "fake_module_xyz", "FakeTask", execute_mock)

        executor = _make_executor_with_app()
        task = {
            "task_id": 1,
            "task_code": "nonexistent_lightweight",  # 未登记 → 轻量任务
            "task_type": 4,
            "executor": "fake_module_xyz.FakeTask",
        }

        result = await executor._run_python_internal_class(task)
        assert result["success"] is True
        execute_mock.assert_awaited_once()


class TestHeavyTaskAdmission:
    """重型任务接入 admission 行为。"""

    async def test_heavy_task_admitted_runs_execute(self, monkeypatch):
        """admitted=True 时 execute 被调用，且在 task_scope 内。"""
        execute_mock = AsyncMock(return_value={"status": "ok"})
        _inject_fake_task_class(monkeypatch, "fake_module_heavy_ok", "HeavyTask", execute_mock)

        executor = _make_executor_with_app()
        # 使用真实注册表中的重型 task_code
        task = {
            "task_id": 1,
            "task_code": "torrent_info_sync_ac608e4d",
            "task_type": 4,
            "executor": "fake_module_heavy_ok.HeavyTask",
        }

        result = await executor._run_python_internal_class(task)
        assert result["success"] is True
        execute_mock.assert_awaited_once()

    async def test_heavy_task_skipped_does_not_call_execute(self, monkeypatch):
        """admitted=False 时返回 skipped，execute **不被调用**（核心防回归）。"""
        execute_mock = AsyncMock(return_value={"status": "ok"})
        _inject_fake_task_class(monkeypatch, "fake_module_heavy_skip", "HeavyTask", execute_mock)

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
            "executor": "fake_module_heavy_skip.HeavyTask",
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
        _inject_fake_task_class(monkeypatch, "fake_module_log", "Task", execute_mock)

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
            "executor": "fake_module_log.Task",
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
        _inject_fake_task_class(monkeypatch, "fake_module_light", "LightTask", execute_mock)

        # 监视 admission_controller.task_scope 是否被调
        from app.tasks.resource_guard import admission_controller

        executor = _make_executor_with_app()
        task = {
            "task_id": 4,
            "task_code": "some_random_light_task_code",  # 未登记
            "task_type": 4,
            "executor": "fake_module_light.LightTask",
        }

        with patch.object(admission_controller, "task_scope", new=MagicMock()) as scope_mock:
            result = await executor._run_python_internal_class(task)

        assert result["success"] is True
        execute_mock.assert_awaited_once()
        # admission_controller.task_scope 不应被进入
        scope_mock.assert_not_called()
