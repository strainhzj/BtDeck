"""cron_trigger（按 task_code 触发内置任务）测试。

覆盖：非内置 code 拒绝、任务不存在拒绝、脚本类型拒绝（0-3 永不放行，
即使 BTDECK_ALLOW_CUSTOM_SCRIPTS=True）、禁用/运行中拒绝透传、成功接受。
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import cron_trigger
from app.tasks.cron_trigger import (
    REASON_TASK_NOT_BUILTIN,
    REASON_TASK_NOT_FOUND,
    REASON_TASK_TYPE_NOT_ALLOWED,
    REASON_TRIGGER_REJECTED,
    trigger_task_by_code,
)


def _db_task(task_id=7, task_type=4):
    return SimpleNamespace(id=task_id, task_type=task_type)


def _apply_patches(builtin, db_task=None, start=None, start_raises=None):
    """一次性 patch 内置注册表 / CRUD / 执行器 / SessionLocal 四层，返回 ExitStack。"""
    stack = ExitStack()
    stack.enter_context(patch("app.tasks.cron_trigger.get_task_by_code", return_value=builtin))

    crud = stack.enter_context(patch("app.tasks.cron_trigger.CronTaskCRUD"))
    crud_result = MagicMock()
    crud_result.success = db_task is not None
    crud_result.data = db_task
    crud.get_cron_task_by_code.return_value = crud_result

    db_stack = MagicMock()
    db_stack.__enter__.return_value = MagicMock()
    stack.enter_context(patch("app.tasks.cron_trigger.SessionLocal", return_value=db_stack))

    executor = stack.enter_context(patch("app.tasks.cron_trigger.cron_executor"))
    executor.start_task_immediately = AsyncMock()
    if start_raises is not None:
        executor.start_task_immediately.side_effect = start_raises
    else:
        executor.start_task_immediately.return_value = start
    return stack


class TestTriggerTaskByCode:
    @pytest.mark.asyncio
    async def test_empty_code_rejected(self):
        result = await trigger_task_by_code("")
        assert result["accepted"] is False
        assert result["reason"] == REASON_TASK_NOT_FOUND

    @pytest.mark.asyncio
    async def test_non_builtin_code_rejected(self):
        with _apply_patches(builtin=None):
            result = await trigger_task_by_code("custom_script_task")
        assert result["accepted"] is False
        assert result["reason"] == REASON_TASK_NOT_BUILTIN

    @pytest.mark.asyncio
    async def test_task_not_in_db_rejected(self):
        builtin = {"task_code": "tracker_sync_598b784c", "task_name": "Tracker 同步"}
        with _apply_patches(builtin=builtin, db_task=None):
            result = await trigger_task_by_code("tracker_sync_598b784c")
        assert result["accepted"] is False
        assert result["reason"] == REASON_TASK_NOT_FOUND

    @pytest.mark.asyncio
    async def test_script_task_type_rejected_regardless_of_env_flag(self):
        """task_type 0-3 永不放行——即使允许自定义脚本的开关打开。"""
        builtin = {"task_code": "tracker_sync_598b784c", "task_name": "Tracker 同步"}
        for task_type in (0, 1, 2, 3):
            with _apply_patches(builtin=builtin, db_task=_db_task(task_type=task_type)):
                result = await trigger_task_by_code("tracker_sync_598b784c")
            assert result["accepted"] is False
            assert result["reason"] == REASON_TASK_TYPE_NOT_ALLOWED

    @pytest.mark.asyncio
    async def test_disabled_or_running_rejection_passthrough(self):
        builtin = {"task_code": "tracker_sync_598b784c", "task_name": "Tracker 同步"}
        with _apply_patches(
            builtin=builtin,
            db_task=_db_task(),
            start_raises=ValueError("任务 'Tracker 同步' 处于禁用状态，无法启动。请先启用该任务。"),
        ):
            result = await trigger_task_by_code("tracker_sync_598b784c")
        assert result["accepted"] is False
        assert result["reason"] == REASON_TRIGGER_REJECTED
        assert "禁用状态" in result["message"]

    @pytest.mark.asyncio
    async def test_builtin_internal_task_accepted(self):
        builtin = {"task_code": "torrent_info_sync_ac608e4d", "task_name": "种子信息同步"}
        with _apply_patches(builtin=builtin, db_task=_db_task(task_id=9, task_type=4), start=True):
            result = await trigger_task_by_code("torrent_info_sync_ac608e4d")
        assert result["accepted"] is True
        assert result["task_id"] == 9
        assert result["task_name"] == "种子信息同步"
        assert result["task_code"] == "torrent_info_sync_ac608e4d"
        assert "last_run_id" in result["message"]

    @pytest.mark.asyncio
    async def test_unexpected_error_stable_reason(self):
        builtin = {"task_code": "tracker_sync_598b784c", "task_name": "Tracker 同步"}
        with _apply_patches(builtin=builtin, db_task=_db_task(), start_raises=RuntimeError("boom")):
            result = await trigger_task_by_code("tracker_sync_598b784c")
        assert result["accepted"] is False
        assert result["reason"] == cron_trigger.REASON_TRIGGER_ERROR
        assert "RuntimeError" in result["message"]
