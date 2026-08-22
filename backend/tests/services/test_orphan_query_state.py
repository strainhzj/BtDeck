# -*- coding: utf-8 -*-
"""孤儿文件页面权威读模型与存量对账回归测试。"""

from datetime import datetime, timedelta

import pytest

from app.models.orphan_file import (
    OrphanCurrentCandidate,
    OrphanFile,
    OrphanScanResult,
)
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import normalize_path
from app.services.orphan_purge_job_service import OrphanPurgeJobService

pytestmark = pytest.mark.asyncio


def _scan(
    scan_id: str,
    *,
    status: str,
    scan_time: datetime,
    error_message: str | None = None,
) -> OrphanScanResult:
    record = OrphanScanResult(
        scan_id=scan_id,
        scan_time=scan_time,
        scan_type="manual",
        status=status,
    )
    record.error_message = error_message
    record.total_paths_scanned = 3
    record.total_files_scanned = 20
    record.total_orphans = 4
    record.total_orphan_size = 1000
    return record


def _detail(
    scan_id: str,
    path: str,
    size: int,
    *,
    downloader_id: str | None = "dl_001",
    deleted: bool = False,
) -> OrphanFile:
    item = OrphanFile(
        scan_id=scan_id,
        file_path=path,
        file_size=size,
        downloader_id=downloader_id,
        canonical_path=normalize_path(path),
    )
    item.is_deleted = deleted
    return item


async def test_failed_latest_falls_back_to_completed_read_only(async_orphan_db):
    now = datetime.utcnow()
    completed = _scan("scan_completed", status="completed", scan_time=now - timedelta(hours=1))
    failed = _scan(
        "scan_failed",
        status="failed",
        scan_time=now,
        error_message="下载器不可用",
    )
    async_orphan_db.add_all(
        [
            completed,
            failed,
            _detail("scan_completed", "/data/a.bin", 100),
            _detail("scan_completed", "/data/b.bin", 200, deleted=True),
            _detail("scan_completed", "/data/c.bin", 300),
        ]
    )
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20)

    assert [item["file_path"] for item in result["list"]] == [
        "/data/c.bin",
        "/data/a.bin",
    ]
    assert result["total"] == 2
    context = result["scan_context"]
    assert context["latest_attempt"]["scan_id"] == "scan_failed"
    assert context["latest_attempt"]["error_message"] == "下载器不可用"
    assert context["display_scan"]["scan_id"] == "scan_completed"
    assert context["remaining_count"] == 2
    assert context["remaining_size"] == 400
    assert context["cleanup_allowed"] is False
    assert context["cleanup_block_reason"]


async def test_running_latest_keeps_existing_empty_contract(async_orphan_db):
    now = datetime.utcnow()
    async_orphan_db.add_all(
        [
            _scan(
                "scan_completed",
                status="completed",
                scan_time=now - timedelta(hours=1),
            ),
            _scan("scan_running", status="running", scan_time=now),
            _detail("scan_completed", "/data/old.bin", 100),
        ]
    )
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).get_orphan_list()

    assert result["list"] == []
    assert result["total"] == 0
    assert result["scan_context"]["latest_attempt"]["scan_id"] == "scan_running"
    assert result["scan_context"]["display_scan"] is None
    assert result["scan_context"]["remaining_count"] == 0
    assert result["scan_context"]["remaining_size"] == 0
    assert result["scan_context"]["cleanup_allowed"] is False


async def test_no_scan_returns_explicit_empty_context(async_orphan_db):
    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=2, page_size=10)

    assert result == {
        "total": 0,
        "page": 2,
        "pageSize": 10,
        "list": [],
        "scan_context": {
            "latest_attempt": None,
            "display_scan": None,
            "remaining_count": 0,
            "remaining_size": 0,
            "ignored_count": 0,
            "cleanup_allowed": False,
            "cleanup_block_reason": "无任何扫描记录",
        },
    }


async def test_filters_do_not_change_remaining_aggregate(async_orphan_db):
    now = datetime.utcnow()
    async_orphan_db.add_all(
        [
            _scan("scan_completed", status="completed", scan_time=now),
            _detail("scan_completed", "/data/a.bin", 100, downloader_id="dl_001"),
            _detail("scan_completed", "/data/b.bin", 300, downloader_id="dl_002"),
            _detail(
                "scan_completed",
                "/data/deleted.bin",
                500,
                downloader_id="dl_001",
                deleted=True,
            ),
        ]
    )
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).get_orphan_list(
        downloader_id="dl_001",
        min_size=50,
        include_deleted=True,
    )

    assert result["total"] == 2
    assert {item["file_path"] for item in result["list"]} == {
        "/data/a.bin",
        "/data/deleted.bin",
    }
    assert result["scan_context"]["remaining_count"] == 2
    assert result["scan_context"]["remaining_size"] == 400


async def test_same_size_pagination_uses_id_tiebreaker(async_orphan_db):
    now = datetime.utcnow()
    async_orphan_db.add(_scan("scan_completed", status="completed", scan_time=now))
    async_orphan_db.add_all([_detail("scan_completed", f"/data/{index}.bin", 100) for index in range(1, 4)])
    await async_orphan_db.commit()

    service = OrphanFileService(async_orphan_db)
    first = await service.get_orphan_list(page=1, page_size=2)
    second = await service.get_orphan_list(page=2, page_size=2)

    ids = [item["id"] for item in first["list"] + second["list"]]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids)) == 3


async def test_completed_snapshot_preview_remains_compatible(async_orphan_db):
    now = datetime.utcnow()
    detail = _detail("scan_completed", "/data/preview.bin", 123)
    async_orphan_db.add_all(
        [
            _scan("scan_completed", status="completed", scan_time=now),
            detail,
        ]
    )
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).cleanup_preview(
        [detail.id],
        scan_id="scan_completed",
    )

    assert result["total_count"] == 1
    assert result["total_size"] == 123
    assert result["items"][0]["id"] == detail.id


async def test_active_cleanup_job_hides_detail_until_terminal_failure(async_orphan_db):
    now = datetime.utcnow()
    detail = _detail("scan_completed", "/data/in-flight.bin", 123)
    async_orphan_db.add_all(
        [
            _scan("scan_completed", status="completed", scan_time=now),
            detail,
        ]
    )
    await async_orphan_db.commit()

    submission = await OrphanPurgeJobService(async_orphan_db).submit_cleanup_job(
        scan_id="scan_completed",
        orphan_ids=[detail.id],
        operator="tester",
    )
    hidden = await OrphanFileService(async_orphan_db).get_orphan_list()
    preview = await OrphanFileService(async_orphan_db).cleanup_preview(
        [detail.id],
        scan_id="scan_completed",
    )

    assert hidden["total"] == 0
    assert hidden["scan_context"]["remaining_count"] == 0
    assert preview["total_count"] == 0

    assert submission.job is not None
    # 终态转换必须走真实任务流（claim → finish_job，触发统计缓存失效）：
    # failed 时 id 离开 active 集、remaining 回升；不能直接改 ORM 字段绕过。
    purge_service = OrphanPurgeJobService(async_orphan_db)
    assert await purge_service.claim_job(submission.job.task_id)
    finished = await purge_service.finish_job(
        submission.job.task_id,
        status="failed",
        purged_count=0,
        failed_count=1,
        failed_list=[],
    )
    assert finished
    visible_again = await OrphanFileService(async_orphan_db).get_orphan_list()
    assert visible_again["total"] == 1
    assert visible_again["list"][0]["id"] == detail.id


async def test_active_purge_job_hides_quarantine_item_until_terminal_failure(async_orphan_db):
    now = datetime.utcnow()
    path = normalize_path("/data/quarantined.bin")
    async_orphan_db.add(
        OrphanCurrentCandidate(
            canonical_path=path,
            downloader_id="dl_001",
            status="quarantined",
            file_size=123,
            quarantine_path="/quarantine/quarantined.bin",
            quarantine_root="/quarantine",
            quarantined_at=now,
            purge_after=now + timedelta(days=7),
            operation_state="stable",
        )
    )
    await async_orphan_db.commit()

    submission = await OrphanPurgeJobService(async_orphan_db).submit_purge_job(
        [path],
        operator="tester",
    )
    hidden = await OrphanFileService(async_orphan_db).get_quarantine_list()
    assert hidden["total"] == 0

    assert submission.job is not None
    submission.job.status = "failed"
    await async_orphan_db.commit()
    visible_again = await OrphanFileService(async_orphan_db).get_quarantine_list()
    assert visible_again["total"] == 1
    assert visible_again["list"][0]["canonical_path"] == path


async def test_reconcile_stable_candidates_is_idempotent_and_exact(async_orphan_db, tmp_path):
    now = datetime.utcnow()
    path = tmp_path / "orphan.bin"
    other_path = tmp_path / "other.bin"
    canonical = normalize_path(str(path))
    quarantined_at = now - timedelta(days=1)
    async_orphan_db.add_all(
        [
            _scan("scan_target", status="completed", scan_time=now),
            _scan(
                "scan_other",
                status="completed",
                scan_time=now - timedelta(hours=1),
            ),
            _detail(
                "scan_target",
                str(path),
                10,
                downloader_id=None,
            ),
            _detail(
                "scan_target",
                str(other_path),
                20,
                downloader_id=None,
            ),
            _detail(
                "scan_other",
                str(path),
                10,
                downloader_id=None,
            ),
            OrphanCurrentCandidate(
                canonical_path=canonical,
                downloader_id="",
                last_seen_scan_id="scan_target",
                status="quarantined",
                quarantine_path=str(tmp_path / "quarantine" / "orphan.bin"),
                quarantined_at=quarantined_at,
                operation_state="stable",
            ),
        ]
    )
    await async_orphan_db.commit()

    service = OrphanFileService(async_orphan_db)
    first = await service.reconcile_stable_candidate_details()
    second = await service.reconcile_stable_candidate_details()
    result = await service.get_orphan_list(include_deleted=True)

    target = next(item for item in result["list"] if item["file_path"] == str(path))
    untouched = next(item for item in result["list"] if item["file_path"] == str(other_path))
    assert first["updated_count"] == 1
    assert second["updated_count"] == 0
    assert target["is_deleted"] is True
    assert target["deleted_by"] == "system:reconciliation"
    assert target["deleted_at"] == quarantined_at.isoformat()
    assert untouched["is_deleted"] is False

    other_batch = await async_orphan_db.execute(OrphanFile.__table__.select().where(OrphanFile.scan_id == "scan_other"))
    assert other_batch.one().is_deleted is False
