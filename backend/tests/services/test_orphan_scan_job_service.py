# -*- coding: utf-8 -*-
"""孤儿后台扫描任务提交、恢复、执行与兼容复核记录测试。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.orphan_file import OrphanScanResult
from app.services.orphan_scan_job_service import (
    OrphanScanDispatcher,
    OrphanScanJobService,
    get_orphan_scan_dispatcher,
)

pytestmark = pytest.mark.asyncio


def _session_factory(db: AsyncSession):
    return async_sessionmaker(bind=db.bind, class_=AsyncSession, expire_on_commit=False)


async def test_submit_scan_persists_queued_task_and_deduplicates_active_scan(
    async_orphan_db,
):
    service = OrphanScanJobService(async_orphan_db)

    first = await service.submit_scan(scan_type="manual", operator="tester")
    second = await service.submit_scan(scan_type="manual", operator="other")

    assert first["accepted"] is True
    assert first["scan_id"] == first["task_id"]
    assert first["status"] == "queued"
    assert second == {
        "scan_id": first["scan_id"],
        "task_id": first["scan_id"],
        "status": "queued",
        "accepted": False,
    }
    record = await async_orphan_db.get(OrphanScanResult, first["scan_id"])
    assert record is not None
    assert record.details_mode == "current"
    assert record.operator == "tester"


async def test_recover_pending_scans_resubmits_only_queued(async_orphan_db):
    queued = OrphanScanResult(
        scan_id="scan-queued",
        scan_type="manual",
        operator="tester",
        status="queued",
        details_mode="current",
    )
    completed = OrphanScanResult(
        scan_id="scan-completed",
        scan_type="manual",
        operator="tester",
        status="completed",
        details_mode="current",
    )
    async_orphan_db.add_all([queued, completed])
    await async_orphan_db.commit()
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanScanDispatcher(
        app,
        session_factory=_session_factory(async_orphan_db),
    )
    submit = MagicMock(return_value=True)

    with patch.object(dispatcher, "submit", submit):
        recovered = await dispatcher.recover_pending_scans()

    assert recovered == 1
    submit.assert_called_once_with("scan-queued")


async def test_dispatcher_executes_precreated_scan_id_without_creating_new_record(
    async_orphan_db,
):
    record = OrphanScanResult(
        scan_id="scan-worker",
        scan_type="manual",
        operator="tester",
        status="queued",
        details_mode="current",
    )
    async_orphan_db.add(record)
    await async_orphan_db.commit()
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanScanDispatcher(
        app,
        session_factory=_session_factory(async_orphan_db),
    )

    @asynccontextmanager
    async def fake_lease_scope(operation):
        assert operation == "scan"
        yield MagicMock(name="lease")

    scan = AsyncMock(
        return_value={
            "scan_id": "scan-worker",
            "status": "completed",
            "total_orphans": 0,
        }
    )
    with (
        patch(
            "app.services.orphan_scan_job_service.orphan_maintenance_scope",
            fake_lease_scope,
        ),
        patch("app.services.orphan_scanner.OrphanScanner.scan", scan),
        patch.object(dispatcher, "_audit_result", AsyncMock()) as audit,
    ):
        execution = await dispatcher.execute_scan("scan-worker")

    scan.assert_awaited_once_with(
        scan_type="manual",
        operator="tester",
        scan_id="scan-worker",
        create_record=False,
    )
    audit.assert_awaited_once()
    assert execution["status"] == "completed"
    assert execution["scan_result"]["scan_id"] == "scan-worker"
    assert execution["cleanup_result"] is None


async def test_execute_scan_invalidates_stats_cache(async_orphan_db):
    """扫描执行后 scan_context 统计缓存被清空（开始前 + 落库后两处失效）。"""
    from app.services.orphan_stats_cache import orphan_stats_cache

    orphan_stats_cache.set("scan-worker-cache", 0, (111, 222, 3))

    record = OrphanScanResult(
        scan_id="scan-worker-cache",
        scan_type="manual",
        operator="tester",
        status="queued",
        details_mode="current",
    )
    async_orphan_db.add(record)
    await async_orphan_db.commit()
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanScanDispatcher(
        app,
        session_factory=_session_factory(async_orphan_db),
    )

    @asynccontextmanager
    async def fake_lease_scope(operation):
        assert operation == "scan"
        yield MagicMock(name="lease")

    scan = AsyncMock(
        return_value={
            "scan_id": "scan-worker-cache",
            "status": "completed",
            "total_orphans": 0,
        }
    )
    with (
        patch(
            "app.services.orphan_scan_job_service.orphan_maintenance_scope",
            fake_lease_scope,
        ),
        patch("app.services.orphan_scanner.OrphanScanner.scan", scan),
        patch.object(dispatcher, "_audit_result", AsyncMock()),
    ):
        execution = await dispatcher.execute_scan("scan-worker-cache")

    assert execution["status"] == "completed"
    # 扫描开始即全清（epoch 推进），旧值不回写
    assert orphan_stats_cache.get("scan-worker-cache")[1] is None


async def test_execute_scan_failed_path_also_invalidates_cache(async_orphan_db):
    """扫描失败路径同样失效缓存（避免 failed 回退展示旧批次时统计 stale）。"""
    from app.services.orphan_stats_cache import orphan_stats_cache

    orphan_stats_cache.set("scan-worker-fail", 0, (111, 222, 3))

    record = OrphanScanResult(
        scan_id="scan-worker-fail",
        scan_type="manual",
        operator="tester",
        status="queued",
        details_mode="current",
    )
    async_orphan_db.add(record)
    await async_orphan_db.commit()
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanScanDispatcher(
        app,
        session_factory=_session_factory(async_orphan_db),
    )

    @asynccontextmanager
    async def fake_lease_scope(operation):
        assert operation == "scan"
        yield MagicMock(name="lease")

    scan = AsyncMock(
        return_value={
            "scan_id": "scan-worker-fail",
            "status": "failed",
            "error": "boom",
        }
    )
    with (
        patch(
            "app.services.orphan_scan_job_service.orphan_maintenance_scope",
            fake_lease_scope,
        ),
        patch("app.services.orphan_scanner.OrphanScanner.scan", scan),
        patch.object(dispatcher, "_audit_result", AsyncMock()),
    ):
        execution = await dispatcher.execute_scan("scan-worker-fail")

    assert execution["status"] == "failed"
    assert orphan_stats_cache.get("scan-worker-fail")[1] is None


async def test_wait_for_completion_returns_the_same_dispatcher_result():
    """Cron 等待的是 submit 创建的同一个后台 task，而非重新发起扫描。"""
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanScanDispatcher(app)
    expected = {
        "scan_id": "scan-wait",
        "status": "completed",
        "scan_result": {"scan_id": "scan-wait", "status": "completed"},
        "cleanup_result": {"quarantined_count": 3, "failed_count": 0},
    }
    with patch.object(dispatcher, "execute_scan", AsyncMock(return_value=expected)):
        assert dispatcher.submit("scan-wait") is True
        result = await dispatcher.wait_for_completion("scan-wait", timeout_seconds=1)

    assert result == expected
    await dispatcher.shutdown()


async def test_scheduled_cleanup_failure_is_logged_without_rewriting_completed_scan(
    async_orphan_db,
):
    """定时扫描已成功后的清理异常必须显式记录，且不伪造扫描失败。"""
    record = OrphanScanResult(
        scan_id="scan-scheduled-cleanup-error",
        scan_type="scheduled",
        operator="system",
        status="queued",
        details_mode="current",
    )
    async_orphan_db.add(record)
    await async_orphan_db.commit()
    app = SimpleNamespace(state=SimpleNamespace(store=MagicMock()))
    dispatcher = OrphanScanDispatcher(
        app,
        session_factory=_session_factory(async_orphan_db),
    )

    @asynccontextmanager
    async def fake_lease_scope(operation):
        assert operation == "scan"
        yield MagicMock(name="lease")

    async def completed_scan(**kwargs):
        async_orphan_db.expire_all()
        stored = await async_orphan_db.get(
            OrphanScanResult,
            "scan-scheduled-cleanup-error",
        )
        stored.status = "completed"
        await async_orphan_db.commit()
        return {
            "scan_id": "scan-scheduled-cleanup-error",
            "status": "completed",
            "total_orphans": 3,
        }

    cleanup = AsyncMock(side_effect=RuntimeError("cleanup 崩溃"))
    with (
        patch(
            "app.services.orphan_scan_job_service.orphan_maintenance_scope",
            fake_lease_scope,
        ),
        patch(
            "app.services.orphan_scanner.OrphanScanner.scan",
            AsyncMock(side_effect=completed_scan),
        ),
        patch.object(dispatcher, "_audit_result", AsyncMock()),
        patch(
            "app.services.orphan_file_service.OrphanFileService.auto_cleanup_expired",
            cleanup,
        ),
        patch("app.services.orphan_scan_job_service.logger.error") as error_log,
    ):
        execution = await dispatcher.execute_scan("scan-scheduled-cleanup-error")

    async_orphan_db.expire_all()
    stored = await async_orphan_db.get(
        OrphanScanResult,
        "scan-scheduled-cleanup-error",
    )
    assert stored.status == "completed"
    cleanup.assert_awaited_once()
    assert any("定时扫描后自动清理失败" in str(call.args[0]) for call in error_log.call_args_list)
    assert execution["status"] == "completed"
    assert execution["cleanup_result"]["rejected"] is True


async def test_review_guardrail_only_allows_latest_completed_guarded_scan(
    async_orphan_db,
):
    record = OrphanScanResult(
        scan_id="scan-guarded",
        scan_type="manual",
        operator="tester",
        status="completed",
        details_mode="current",
    )
    record.total_orphans = 120_100
    record.cleanup_review_required = True
    async_orphan_db.add(record)
    await async_orphan_db.commit()

    result = await OrphanScanJobService(async_orphan_db).review_guardrail(
        scan_id="scan-guarded",
        operator="reviewer",
        note="已核查全部映射并抽样二十条孤儿文件",
    )

    await async_orphan_db.refresh(record)
    assert result["task_id"] == "scan-guarded"
    assert record.cleanup_reviewed_at is not None
    assert record.cleanup_reviewed_by == "reviewer"
    assert "二十条" in (record.cleanup_review_note or "")


async def test_closed_dispatcher_is_recreated_for_next_lifespan():
    app = SimpleNamespace(state=SimpleNamespace())
    first = get_orphan_scan_dispatcher(app)
    await first.shutdown()

    second = get_orphan_scan_dispatcher(app)

    assert second is not first
    assert not second.closed
    await second.shutdown()
