# -*- coding: utf-8 -*-
"""cron 执行层安全测试：恶意 executor 不执行、无 exec 回落。

安全背景：历史实现中 type=4 的 executor 若无法按类路径解析
（ImportError/AttributeError）会回落到 exec() 任意代码执行——认证后 RCE。
修复后执行层（_run_task_script / _run_python_internal_class）在解析前
做白名单闸门，类路径解析失败按执行失败返回，绝不执行代码。

用标记目录法验证：payload 中的 makedirs 若被执行则会留下痕迹目录。
"""

from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.tasks.cron_executor import CronTaskExecutor, is_internal_class_executor_allowed


class TestIsInternalClassExecutorAllowed:
    """白名单纯函数：严格类路径 + app.tasks. 前缀。"""

    def test_builtin_paths_allowed(self):
        assert is_internal_class_executor_allowed("app.tasks.scheduler.downloader_cache_sync.CachedDownloaderSyncTask")
        assert is_internal_class_executor_allowed("app.tasks.scheduler.tracker_message_logger.TrackerMessageLogger")

    def test_payloads_rejected(self):
        payloads = [
            '__import__("os").system("echo pwned")',
            "__import__('os').makedirs('x')",
            'os.system("echo pwned")',
            "import os\nos.system('id')",
            "print(1)",
            "app/os.py",
            "",
        ]
        for p in payloads:
            assert is_internal_class_executor_allowed(p) is False, f"payload 须被拒绝: {p[:40]}"

    def test_prefix_forgery_rejected(self):
        assert is_internal_class_executor_allowed("evils.app.tasks.Evil") is False
        assert is_internal_class_executor_allowed("app.tasksevil.Evil") is False


class TestRunTaskScriptGate:
    """_run_task_script 执行层闸门：覆盖调度触发与"立即启动"两条路径。"""

    async def test_script_types_blocked_by_default(self):
        executor = CronTaskExecutor()
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            for task_type in (0, 1, 2, 3):
                result = await executor._run_task_script({"task_type": task_type, "executor": "echo hi"})
                assert result["success"] is False
                assert "BTDECK_ALLOW_CUSTOM_SCRIPTS" in result["log_detail"]

    async def test_type4_evil_executor_blocked_without_execution(self, tmp_path):
        """恶意 executor 在任何解析/执行前被拒，标记目录不会创建。"""
        marker = tmp_path / "pwned_marker"
        executor = CronTaskExecutor()
        task = {
            "task_type": 4,
            "executor": f'__import__("os").makedirs(r"{marker}")',
            "task_code": "test_code",
        }
        result = await executor._run_task_script(task)
        assert result["success"] is False
        assert "app.tasks." in result["log_detail"]
        assert not marker.exists(), "恶意代码不得被执行（标记目录不应存在）"

    async def test_type4_unresolvable_class_path_fails(self):
        """格式合法但模块不存在：按失败返回，不回落到代码执行（exec 已删除）。"""
        executor = CronTaskExecutor()
        result = await executor._run_task_script(
            {
                "task_type": 4,
                "executor": "app.tasks.scheduler.nonexistent_module.NonexistentTask",
                "task_code": "test_code",
            }
        )
        assert result["success"] is False
        assert "解析失败" in result["log_detail"]


class TestRunPythonInternalClassGate:
    """_run_python_internal_class 直调：白名单闸门 + 解析失败不执行。"""

    async def test_gate_rejects_code_strings(self, tmp_path):
        marker = tmp_path / "pwned3"
        executor = CronTaskExecutor()
        for payload in (
            f'__import__("os").makedirs(r"{marker}")',
            'os.system("echo x")',
            "print(1)",
        ):
            result = await executor._run_python_internal_class({"executor": payload, "task_code": "t"})
            assert result["success"] is False, f"payload 须被拒: {payload[:40]}"
            assert "app.tasks." in result["log_detail"]
        assert not marker.exists()

    async def test_non_class_attribute_fails(self):
        """白名单格式但解析目标不是类（如模块函数）→ 失败，不执行。"""
        executor = CronTaskExecutor()
        result = await executor._run_python_internal_class(
            {"executor": "app.tasks.cron_executor.is_internal_class_executor_allowed", "task_code": "t"}
        )
        assert result["success"] is False


class TestLoadPolicy:
    """加载期策略：0-3 受开关管控，4 白名单。"""

    def test_policy_type4(self):
        assert CronTaskExecutor._is_task_allowed_by_policy(
            {"task_type": 4, "executor": "app.tasks.scheduler.tag_sync.TagSync"}
        )
        assert not CronTaskExecutor._is_task_allowed_by_policy({"task_type": 4, "executor": "os.system('x')"})
        assert not CronTaskExecutor._is_task_allowed_by_policy({"task_type": 4, "executor": ""})

    def test_policy_script_types_follow_flag(self):
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False):
            assert not CronTaskExecutor._is_task_allowed_by_policy({"task_type": 0, "executor": "x"})
        with patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", True):
            assert CronTaskExecutor._is_task_allowed_by_policy({"task_type": 0, "executor": "x"})

    def test_policy_builtin_56_allowed(self):
        assert CronTaskExecutor._is_task_allowed_by_policy({"task_type": 5, "executor": "{}"})
        assert CronTaskExecutor._is_task_allowed_by_policy({"task_type": 6, "executor": "{}"})


def test_executor_module_has_no_exec_engine():
    """exec 回落引擎已删除：模块不再暴露任意代码执行方法。"""
    import app.tasks.cron_executor as mod

    assert not hasattr(mod.CronTaskExecutor, "_execute_sync_python_code")
    assert not hasattr(mod.CronTaskExecutor, "_execute_async_python_code")
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "exec(" not in source, "cron_executor 源码不应再包含 exec() 调用"
