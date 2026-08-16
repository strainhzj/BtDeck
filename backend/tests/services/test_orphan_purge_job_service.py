# -*- coding: utf-8 -*-
"""隔离区彻底删除持久化任务、恢复和通知测试。"""

import asyncio
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


async def test_submit_job_persists_ip_address(async_orphan_db):
    """提交端 IP 持久化到 job 行（后台执行时透传给审计日志）。"""
    service = OrphanPurgeJobService(async_orphan_db)

    cleanup_job = await service.submit_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[1],
        operator="tester",
        ip_address="192.168.5.60",
    )
    purge_job = await service.submit_purge_job(
        ["/data/a.mkv"],
        operator="tester",
        ip_address="10.0.0.9",
    )

    assert cleanup_job.job is not None
    assert cleanup_job.job.ip_address == "192.168.5.60"
    assert purge_job.job is not None
    assert purge_job.job.ip_address == "10.0.0.9"
    # 不传 IP（兼容入口/旧调用方）→ NULL 而非报错
    legacy_job = await service.submit_purge_job(["/data/b.mkv"], operator="tester")
    assert legacy_job.job is not None
    assert legacy_job.job.ip_address is None


async def test_execute_job_passes_ip_to_cleanup_orphans(async_orphan_db):
    """execute_job 把 job 行上的提交端 IP 透传给 cleanup_orphans（审计用）。"""
    job = await OrphanPurgeJobService(async_orphan_db).create_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[1, 2],
        operator="tester",
        ip_address="192.168.5.60",
    )
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock(name="shared_store")))
    dispatcher = OrphanPurgeJobDispatcher(app, session_factory=_session_factory(async_orphan_db))

    with patch.object(
        OrphanFileService,
        "cleanup_orphans",
        AsyncMock(
            return_value={
                "success_count": 2,
                "failed_count": 0,
                "failed_list": [],
                "total_size": 2048,
            }
        ),
    ) as cleanup:
        await dispatcher.execute_job(job.task_id)

    assert cleanup.await_args.kwargs["ip_address"] == "192.168.5.60"


async def test_cleanup_submission_skips_active_items_and_releases_failed_job(async_orphan_db):
    service = OrphanPurgeJobService(async_orphan_db)

    first = await service.submit_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[1, 2],
        operator="tester",
    )
    mixed = await service.submit_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[2, 3],
        operator="tester",
    )
    all_active = await service.submit_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[1, 2, 3],
        operator="tester",
    )

    assert first.accepted_items == [1, 2]
    assert mixed.accepted_items == [3]
    assert mixed.skipped_items == [2]
    assert all_active.job is None
    assert all_active.skipped_items == [1, 2, 3]

    assert first.job is not None
    first.job.status = "failed"
    await async_orphan_db.commit()
    retry = await service.submit_cleanup_job(
        scan_id="scan-latest",
        orphan_ids=[1, 2],
        operator="tester",
    )
    assert retry.accepted_items == [1, 2]
    assert retry.skipped_items == []


async def test_purge_submission_skips_active_paths_and_allows_terminal_retry(async_orphan_db):
    service = OrphanPurgeJobService(async_orphan_db)

    first = await service.submit_purge_job(["/data/a.mkv"], operator="tester")
    mixed = await service.submit_purge_job(
        ["/data/a.mkv", "/data/b.mkv"],
        operator="tester",
    )

    assert mixed.accepted_items == ["/data/b.mkv"]
    assert mixed.skipped_items == ["/data/a.mkv"]
    assert first.job is not None
    first.job.status = "partial"
    await async_orphan_db.commit()

    retry = await service.submit_purge_job(["/data/a.mkv"], operator="tester")
    assert retry.accepted_items == ["/data/a.mkv"]
    assert retry.skipped_items == []


async def test_submission_lock_remains_atomic_when_db_write_governance_is_disabled(
    async_orphan_db,
    monkeypatch,
):
    from app.tasks.resource_guard import settings as resource_settings

    monkeypatch.setattr(resource_settings, "SYNC_DB_WRITE_SCOPE_ENABLED", False)
    factory = _session_factory(async_orphan_db)
    async with factory() as first_db, factory() as second_db:
        first, second = await asyncio.gather(
            OrphanPurgeJobService(first_db).submit_cleanup_job(
                scan_id="scan-latest",
                orphan_ids=[7, 8],
                operator="tester-a",
            ),
            OrphanPurgeJobService(second_db).submit_cleanup_job(
                scan_id="scan-latest",
                orphan_ids=[8, 9],
                operator="tester-b",
            ),
        )

    accepted = first.accepted_items + second.accepted_items
    skipped = first.skipped_items + second.skipped_items
    assert accepted.count(8) == 1
    assert skipped.count(8) == 1
    assert set(accepted) == {7, 8, 9}


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
    # 回归保护：清理通知『释放空间』应使用自适应单位（不再是裸字节数）
    assert "释放空间：1.00 KB" in (notification.content or "")
    cleanup.assert_awaited_once_with(
        orphan_ids=[1, 2],
        operator="tester",
        audit_service=cleanup.await_args.kwargs["audit_service"],
        store=app.state.store,
        scan_id="scan-latest",
        ip_address=None,
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
