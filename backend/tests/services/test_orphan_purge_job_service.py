# -*- coding: utf-8 -*-
"""隔离区彻底删除持久化任务、恢复和通知测试。"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.notification import Notification
from app.models.orphan_purge_job import OrphanPurgeJob
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_purge_job_service import (
    OrphanPurgeJobDispatcher,
    OrphanPurgeJobService,
    get_orphan_purge_dispatcher,
)

pytestmark = pytest.mark.asyncio


def _session_factory(db: AsyncSession):
    return async_sessionmaker(bind=db.bind, class_=AsyncSession, expire_on_commit=False)


async def test_create_job_is_persistent_and_deduplicates_paths(async_orphan_db):
    service = OrphanPurgeJobService(async_orphan_db)

    job = await service.create_job(
        ["/data/a.mkv", "/data/a.mkv", "/data/b.mkv", "   "],
        operator="tester",
    )

    assert job.status == "pending"
    assert job.total_count == 2
    assert job.canonical_paths == ["/data/a.mkv", "/data/b.mkv"]
    persisted = await async_orphan_db.get(OrphanPurgeJob, job.task_id)
    assert persisted is not None


async def test_create_cleanup_job_persists_ids_and_scan_binding(async_orphan_db):
    service = OrphanPurgeJobService(async_orphan_db)

    job = await service.create_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[1, 1, 2],
        operator="tester",
    )

    assert job.operation_type == "cleanup"
    assert job.scan_id == "scan-latest"
    assert job.orphan_ids == [1, 2]
    assert job.canonical_paths == []
    assert job.total_count == 2


async def test_dispatcher_completes_job_and_creates_notification(async_orphan_db):
    job = await OrphanPurgeJobService(async_orphan_db).create_job(["/data/a.mkv"], operator="tester")
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock(name="shared_store")))
    dispatcher = OrphanPurgeJobDispatcher(app, session_factory=_session_factory(async_orphan_db))

    purge_result = {
        "purged_count": 1,
        "failed_count": 0,
        "failed_list": [],
    }
    with (
        patch.object(OrphanFileService, "purge_quarantine_now", AsyncMock(return_value=purge_result)) as purge,
        patch.object(
            OrphanFileService,
            "prune_recorded_empty_quarantine_dirs",
            AsyncMock(return_value={"root_count": 0, "removed_dir_count": 0}),
        ),
    ):
        await dispatcher.execute_job(job.task_id)

    await async_orphan_db.refresh(job)
    notification = (
        await async_orphan_db.execute(
            select(Notification).where(Notification.dedupe_key == f"orphan_purge:{job.task_id}")
        )
    ).scalar_one()
    assert job.status == "completed"
    assert job.purged_count == 1
    assert job.notification_sent_at is not None
    assert notification.priority == "info"
    assert json.loads(notification.extra_data)["event"] == "orphan_purge_completed"
    purge.assert_awaited_once()
    assert purge.await_args.kwargs["store"] is app.state.store


async def test_dispatcher_completes_cleanup_job_and_creates_notification(async_orphan_db):
    job = await OrphanPurgeJobService(async_orphan_db).create_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[1, 2],
        operator="tester",
    )
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock(name="shared_store")))
    dispatcher = OrphanPurgeJobDispatcher(app, session_factory=_session_factory(async_orphan_db))

    cleanup_result = {
        "success_count": 1,
        "failed_count": 1,
        "failed_list": [{"id": 2, "file_path": "/data/b.bin", "reason": "stale"}],
        "total_size": 1024,
    }
    with patch.object(
        OrphanFileService,
        "cleanup_orphans",
        AsyncMock(return_value=cleanup_result),
    ) as cleanup:
        await dispatcher.execute_job(job.task_id)

    await async_orphan_db.refresh(job)
    notification = (
        await async_orphan_db.execute(
            select(Notification).where(Notification.dedupe_key == f"orphan_cleanup:{job.task_id}")
        )
    ).scalar_one()
    assert job.status == "partial"
    assert job.purged_count == 1
    assert job.total_size == 1024
    assert job.notification_sent_at is not None
    assert notification.priority == "warning"
    assert json.loads(notification.extra_data)["event"] == "orphan_cleanup_completed"
    assert "主动清理" in notification.title
    cleanup.assert_awaited_once_with(
        orphan_ids=[1, 2],
        operator="tester",
        audit_service=cleanup.await_args.kwargs["audit_service"],
        store=app.state.store,
        scan_id="scan-latest",
    )


async def test_dispatcher_cleanup_failure_is_persisted_and_notified(async_orphan_db):
    job = await OrphanPurgeJobService(async_orphan_db).create_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[7],
        operator="tester",
    )
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanPurgeJobDispatcher(app, session_factory=_session_factory(async_orphan_db))

    with patch.object(
        OrphanFileService,
        "cleanup_orphans",
        AsyncMock(
            return_value={
                "rejected": True,
                "error": "scan_id 已过期",
                "success_count": 0,
                "failed_count": 1,
                "failed_list": [{"id": 7, "reason": "scan_id 已过期"}],
                "total_size": 0,
            }
        ),
    ):
        await dispatcher.execute_job(job.task_id)

    await async_orphan_db.refresh(job)
    notification = (
        await async_orphan_db.execute(
            select(Notification).where(Notification.dedupe_key == f"orphan_cleanup:{job.task_id}")
        )
    ).scalar_one()
    assert job.status == "failed"
    assert job.failed_count == 1
    assert "scan_id 已过期" in (job.error_message or "")
    assert notification.priority == "error"
    assert "scan_id 已过期" in notification.content


async def test_dispatcher_failure_is_persisted_and_notified(async_orphan_db):
    paths = ["/data/a.mkv", "/data/b.mkv"]
    job = await OrphanPurgeJobService(async_orphan_db).create_job(paths, operator="tester")
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanPurgeJobDispatcher(app, session_factory=_session_factory(async_orphan_db))

    with patch.object(
        OrphanFileService,
        "purge_quarantine_now",
        AsyncMock(side_effect=RuntimeError("manifest unavailable")),
    ):
        await dispatcher.execute_job(job.task_id)

    await async_orphan_db.refresh(job)
    notification = (
        await async_orphan_db.execute(
            select(Notification).where(Notification.dedupe_key == f"orphan_purge:{job.task_id}")
        )
    ).scalar_one()
    assert job.status == "failed"
    assert job.failed_count == 2
    assert len(job.failed_list) == 2
    assert "manifest unavailable" in (job.error_message or "")
    assert notification.priority == "error"


async def test_failure_notification_exposes_recorded_quarantine_path(async_orphan_db):
    """删除失败通知必须同时呈现原路径和实际隔离路径，避免误判删除目标。"""
    canonical_path = "/Downloads/ipan/Downloads/Seven.Samurai.mkv"
    quarantine_path = "/data/.btdeck_quarantine/scan/uuid/Seven.Samurai.mkv"
    job = await OrphanPurgeJobService(async_orphan_db).create_job([canonical_path], operator="tester")
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanPurgeJobDispatcher(app, session_factory=_session_factory(async_orphan_db))
    failed_list = [
        {
            "canonical_path": canonical_path,
            "quarantine_path": quarantine_path,
            "reason": "隔离文件身份复核失败",
        }
    ]

    with (
        patch.object(
            OrphanFileService,
            "purge_quarantine_now",
            AsyncMock(return_value={"purged_count": 0, "failed_count": 1, "failed_list": failed_list}),
        ),
        patch.object(
            OrphanFileService,
            "prune_recorded_empty_quarantine_dirs",
            AsyncMock(return_value={"root_count": 0, "removed_dir_count": 0}),
        ),
    ):
        await dispatcher.execute_job(job.task_id)

    notification = (
        await async_orphan_db.execute(
            select(Notification).where(Notification.dedupe_key == f"orphan_purge:{job.task_id}")
        )
    ).scalar_one()
    assert canonical_path in notification.content
    assert quarantine_path in notification.content
    assert "隔离文件身份复核失败" in notification.content
    extra_data = json.loads(notification.extra_data)
    assert extra_data["failed_list"][0]["quarantine_path"] == quarantine_path


async def test_startup_recovery_requeues_running_job(async_orphan_db):
    job = await OrphanPurgeJobService(async_orphan_db).create_job(["/data/a.mkv"], operator="tester")
    job.status = "running"
    await async_orphan_db.commit()
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanPurgeJobDispatcher(app, session_factory=_session_factory(async_orphan_db))
    submit = MagicMock(return_value=True)

    with (
        patch.object(dispatcher, "submit", submit),
        patch.object(
            OrphanFileService,
            "prune_recorded_empty_quarantine_dirs",
            AsyncMock(return_value={"root_count": 0, "removed_dir_count": 0}),
        ),
    ):
        result = await dispatcher.recover_pending_jobs()

    await async_orphan_db.refresh(job)
    assert result["recovered_count"] == 1
    assert job.status == "pending"
    submit.assert_called_once_with(job.task_id)


async def test_result_notification_is_idempotent(async_orphan_db):
    service = OrphanPurgeJobService(async_orphan_db)
    job = await service.create_job(["/data/a.mkv"], operator="tester")
    assert await service.claim_job(job.task_id)
    await service.finish_job(
        job.task_id,
        status="completed",
        purged_count=1,
        failed_count=0,
        failed_list=[],
    )

    assert await service.notify_job_result(job.task_id)
    assert await service.notify_job_result(job.task_id)
    count = (
        await async_orphan_db.execute(
            select(func.count(Notification.id)).where(Notification.dedupe_key == f"orphan_purge:{job.task_id}")
        )
    ).scalar_one()
    assert count == 1


async def test_closed_dispatcher_is_recreated_for_next_lifespan():
    app = SimpleNamespace(state=SimpleNamespace())
    first = get_orphan_purge_dispatcher(app)
    await first.shutdown()

    second = get_orphan_purge_dispatcher(app)

    assert second is not first
    assert not second.closed
    await second.shutdown()
