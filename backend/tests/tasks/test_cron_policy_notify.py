# -*- coding: utf-8 -*-
"""cron 加载期安全策略与拦截通知回归测试（W2）。

保护点（防回归）：
1. load_all_tasks 只调度通过策略的任务（0-3 脚本受 BTDECK_ALLOW_CUSTOM_SCRIPTS
   管控、type=4 仅允许 app.tasks. 白名单）——若未来有人绕过
   _is_task_allowed_by_policy 直接把全部 enabled 任务加入调度器，
   历史恶意任务会重新被执行；
2. 被拦截任务必须落告警日志 + 系统通知（dedupe 幂等），用户可感知修复。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.tasks.cron_executor import CronTaskExecutor


class _FakeSession:
    """load_all_tasks 的 AsyncSession 替身（仅需可关闭）。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def close(self):
        pass


class TestLoadAllTasksPolicy:
    """load_all_tasks 只调度合规任务。"""

    async def test_evil_tasks_not_scheduled(self):
        executor = CronTaskExecutor()
        evil_tasks = [
            {"task_id": 1, "task_name": "script1", "task_type": 0, "executor": "rm -rf /", "cron_plan": "* * * * *"},
            {
                "task_id": 2,
                "task_name": "rce",
                "task_type": 4,
                "executor": '__import__("os").system("x")',
                "cron_plan": "* * * * *",
            },
        ]
        result = SimpleNamespace(success=True, data=evil_tasks)

        with (
            patch("app.tasks.cron_executor.AsyncSessionLocal", new=lambda: _FakeSession()),
            patch("app.tasks.cron_executor.AsyncCronTaskCRUD.get_enabled_tasks", new=AsyncMock(return_value=result)),
            patch.object(executor, "add_task_to_scheduler", new=AsyncMock(return_value=True)) as add_mock,
            patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False),
            patch.object(executor, "_notify_policy_rejected_tasks", new=AsyncMock()) as notify_mock,
        ):
            await executor.load_all_tasks()

        assert add_mock.await_count == 0, "不合规任务不得加入调度器"
        assert notify_mock.await_count == 1, "被拦截任务必须产生拦截通知"

    async def test_builtin_tasks_scheduled(self):
        executor = CronTaskExecutor()
        good_tasks = [
            {
                "task_id": 3,
                "task_name": "sync",
                "task_type": 4,
                "executor": "app.tasks.scheduler.downloader_cache_sync.CachedDownloaderSyncTask",
                "cron_plan": "*/5 * * * *",
            }
        ]
        result = SimpleNamespace(success=True, data=good_tasks)

        with (
            patch("app.tasks.cron_executor.AsyncSessionLocal", new=lambda: _FakeSession()),
            patch("app.tasks.cron_executor.AsyncCronTaskCRUD.get_enabled_tasks", new=AsyncMock(return_value=result)),
            patch.object(executor, "add_task_to_scheduler", new=AsyncMock(return_value=True)) as add_mock,
        ):
            await executor.load_all_tasks()

        assert add_mock.await_count == 1, "合规内置任务应正常调度"

    async def test_script_types_blocked_when_flag_off_scheduled_when_on(self):
        executor = CronTaskExecutor()
        script_task = {"task_id": 4, "task_name": "sh", "task_type": 0, "executor": "echo hi", "cron_plan": "* * * * *"}
        result = SimpleNamespace(success=True, data=[script_task])

        with (
            patch("app.tasks.cron_executor.AsyncSessionLocal", new=lambda: _FakeSession()),
            patch("app.tasks.cron_executor.AsyncCronTaskCRUD.get_enabled_tasks", new=AsyncMock(return_value=result)),
            patch.object(executor, "add_task_to_scheduler", new=AsyncMock(return_value=True)) as add_mock,
            patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", False),
        ):
            await executor.load_all_tasks()
        assert add_mock.await_count == 0, "开关关闭时脚本任务不得加载"

        with (
            patch("app.tasks.cron_executor.AsyncSessionLocal", new=lambda: _FakeSession()),
            patch("app.tasks.cron_executor.AsyncCronTaskCRUD.get_enabled_tasks", new=AsyncMock(return_value=result)),
            patch.object(executor, "add_task_to_scheduler", new=AsyncMock(return_value=True)) as add_mock,
            patch.object(settings, "BTDECK_ALLOW_CUSTOM_SCRIPTS", True),
        ):
            await executor.load_all_tasks()
        assert add_mock.await_count == 1, "开关开启时脚本任务可加载"


class TestNotifyPolicyRejected:
    """被拦截任务产生告警通知（dedupe 幂等）。"""

    async def test_notification_created_per_rejected_task(self):
        executor = CronTaskExecutor()
        rejected = [
            {"task_id": 11, "task_name": "bad1", "task_type": 0},
            {"task_id": 12, "task_name": "bad2", "task_type": 4},
        ]
        fake_service = MagicMock()
        fake_service.create_notification = AsyncMock(return_value=None)

        with patch("app.services.notification_service.NotificationService", return_value=fake_service) as svc_cls:
            await executor._notify_policy_rejected_tasks(db=None, rejected=rejected)

        assert svc_cls.call_count == 1
        assert fake_service.create_notification.await_count == 2
        # 每条通知携带任务 ID 的 dedupe 键（重启不重复打扰）
        for i, call in enumerate(fake_service.create_notification.await_args_list):
            kwargs = call.kwargs
            assert kwargs["dedupe_key"] == f"cron_policy_blocked:{rejected[i]['task_id']}"
            assert kwargs["priority"] == "warning"
            assert "安全策略" in kwargs["title"]
