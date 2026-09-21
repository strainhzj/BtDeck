"""下载器手动同步后台任务生命周期回归。"""

import asyncio
import uuid

import pytest

from app.core.background_task_manager import BackgroundTaskManager, TaskStatus


pytestmark = pytest.mark.asyncio


def _downloader_id(label: str) -> str:
    return f"test-{label}-{uuid.uuid4().hex}"


async def test_create_task_if_idle_atomically_reuses_pending_task() -> None:
    """同一下载器的并发提交只能创建一个 pending/running 任务。"""
    manager = BackgroundTaskManager()
    downloader_id = _downloader_id("dedupe")

    first, first_created = await manager.create_task_if_idle(
        "sync", downloader_id, "测试下载器"
    )
    duplicate, duplicate_created = await manager.create_task_if_idle(
        "sync", downloader_id, "测试下载器"
    )

    assert first_created is True
    assert duplicate_created is False
    assert duplicate is first

    await manager.update_task_status(first.task_id, TaskStatus.SUCCESS)
    replacement, replacement_created = await manager.create_task_if_idle(
        "sync", downloader_id, "测试下载器"
    )
    assert replacement_created is True
    assert replacement.task_id != first.task_id


async def test_execute_task_maps_structured_failure_to_failed_terminal_state() -> None:
    """协程正常返回 failed 结果时不得错误标成 TaskStatus.SUCCESS。"""
    manager = BackgroundTaskManager()
    task, created = await manager.create_task_if_idle(
        "sync", _downloader_id("failed"), "失败下载器"
    )
    assert created is True

    async def failed_result():
        return {
            "status": "failed",
            "outcome": "failed",
            "message": "下载器 RPC 不可用",
        }

    result = await manager.execute_task(task.task_id, failed_result())
    stored = manager.get_task(task.task_id)

    assert result["status"] == "failed"
    assert stored is not None
    assert stored.status == TaskStatus.FAILED
    assert stored.result == result
    assert stored.error == "下载器 RPC 不可用"


async def test_task_runner_is_retained_until_background_execution_finishes() -> None:
    """fire-and-forget runner 必须有强引用，并在完成后自动释放。"""
    manager = BackgroundTaskManager()
    task, created = await manager.create_task_if_idle(
        "sync", _downloader_id("runner"), "长任务下载器"
    )
    assert created is True
    started = asyncio.Event()
    release = asyncio.Event()

    async def controlled_result():
        started.set()
        await release.wait()
        return {"status": "success", "outcome": "success", "message": "ok"}

    runner = manager.start_task_runner(
        task.task_id, manager.execute_task(task.task_id, controlled_result())
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)

    assert manager._runner_tasks.get(task.task_id) is runner
    assert manager.get_task(task.task_id).status == TaskStatus.RUNNING

    release.set()
    await asyncio.wait_for(runner, timeout=1.0)
    await asyncio.sleep(0)

    assert task.task_id not in manager._runner_tasks
    assert manager.get_task(task.task_id).status == TaskStatus.SUCCESS
    assert manager.get_task(task.task_id).progress == 100
