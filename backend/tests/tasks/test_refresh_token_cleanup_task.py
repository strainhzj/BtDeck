# -*- coding: utf-8 -*-
"""refresh_token_cleanup 任务装配回归（令牌机制对抗审计修复 F3）。

保护点：
1. 种子条目存在于 DEFAULT_SCHEDULED_TASKS 且 cron/enabled/executor 正确
   ——种子经 init_db 增量块对存量库生效，条目被误删/改名则清理静默消失
2. executor 字符串路径可动态导入且类形正确（cron_executor 按字符串
   rsplit 动态导入，路径拼写错误要到运行期才暴露）
3. 不登记 task_profiles（未注册=轻量放行是设计语义，登记反而错误）
"""

import importlib

from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS
from app.tasks.task_profiles import TASK_PROFILES

EXPECTED = {
    "task_code": "refresh_token_cleanup",
    "executor": "app.tasks.scheduler.refresh_token_cleanup_task.RefreshTokenCleanupTask",
    "cron_plan": "30 4 * * *",
}


def _seed_entry():
    return next(t for t in DEFAULT_SCHEDULED_TASKS if t["task_code"] == EXPECTED["task_code"])


class TestSeedWiring:
    def test_seed_entry_present_with_expected_wiring(self):
        entry = _seed_entry()
        assert entry["executor"] == EXPECTED["executor"]
        assert entry["cron_plan"] == EXPECTED["cron_plan"]
        assert entry["enabled"] is True
        assert entry["timeout_seconds"] >= 60

    def test_executor_path_dynamically_importable(self):
        """cron_executor 用 rsplit('.', 1) 动态导入 executor 字符串，此处同法验证。"""
        module_path, class_name = EXPECTED["executor"].rsplit(".", 1)
        module = importlib.import_module(module_path)
        task_class = getattr(module, class_name)

        assert task_class.name
        assert task_class.description
        assert task_class.version
        assert hasattr(task_class, "execute")
        import inspect

        assert inspect.iscoroutinefunction(task_class.execute)

    def test_not_registered_as_heavy_task(self):
        """清理任务行量极小必须保持轻量：未注册即轻量放行，登记进 TASK_PROFILES 反而是错误。"""
        assert EXPECTED["task_code"] not in TASK_PROFILES
