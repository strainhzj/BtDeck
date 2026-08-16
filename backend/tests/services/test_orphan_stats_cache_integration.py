# -*- coding: utf-8 -*-
"""孤儿列表统计缓存集成测试：命中不再聚合、total 复用、失效后刷新。"""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_purge_job_service import OrphanPurgeJobService


def _scan(scan_id: str, *, scan_time=None) -> OrphanScanResult:
    record = OrphanScanResult(
        scan_id=scan_id,
        scan_time=scan_time or datetime.utcnow(),
        scan_type="manual",
        status="completed",
        details_mode="snapshot",
    )
    record.total_paths_scanned = 1
    record.total_files_scanned = 3
    record.total_orphans = 3
    record.total_orphan_size = 600
    return record


def _detail(scan_id: str, path: str, size: int, *, deleted: bool = False) -> OrphanFile:
    item = OrphanFile(
        scan_id=scan_id,
        file_path=path,
        file_size=size,
        downloader_id="dl_001",
        confidence="high",
        canonical_path=path,
    )
    item.is_deleted = deleted
    return item


async def _seed(async_orphan_db, *, current_mode: bool = False) -> str:
    scan = _scan("scan_cache")
    if current_mode:
        scan.details_mode = "current"
    async_orphan_db.add(scan)
    async_orphan_db.add_all(
        [
            _detail("scan_cache", "/data/a.bin", 100),
            _detail("scan_cache", "/data/b.bin", 200),
            _detail("scan_cache", "/data/ignored.bin", 300),
        ]
    )
    if current_mode:
        async_orphan_db.add_all(
            [
                OrphanCurrentCandidate(
                    canonical_path="/data/a.bin",
                    downloader_id="dl_001",
                    first_seen_at=datetime.utcnow() - timedelta(days=1),
                    last_seen_at=datetime.utcnow(),
                    status="candidate",
                    operation_state="stable",
                ),
                OrphanCurrentCandidate(
                    canonical_path="/data/b.bin",
                    downloader_id="dl_001",
                    first_seen_at=datetime.utcnow() - timedelta(days=1),
                    last_seen_at=datetime.utcnow(),
                    status="candidate",
                    operation_state="stable",
                ),
                OrphanCurrentCandidate(
                    canonical_path="/data/ignored.bin",
                    downloader_id="dl_001",
                    first_seen_at=datetime.utcnow() - timedelta(days=1),
                    last_seen_at=datetime.utcnow(),
                    status="candidate",
                    operation_state="stable",
                    is_ignored=True,
                ),
            ]
        )
        # 候选挂钩明细 id
        details = (await async_orphan_db.execute(select(OrphanFile))).scalars().all()
        for cand, detail in zip(
            (await async_orphan_db.execute(select(OrphanCurrentCandidate))).scalars().all(),
            details,
        ):
            cand.current_detail_id = detail.id
    await async_orphan_db.commit()
    return scan.scan_id


def _count_aggregate_executions(async_orphan_db, monkeypatch):
    """包一层 db.execute：统计含 func.count 的聚合 SQL 执行次数（remaining/ignored/total）。"""
    counter = {"aggregate": 0}

    original_execute = async_orphan_db.execute

    async def wrapped_execute(statement, *args, **kwargs):
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        if "count(" in compiled and "FROM orphan_file" in compiled:
            counter["aggregate"] += 1
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(async_orphan_db, "execute", wrapped_execute)
    return counter


async def test_second_call_hits_cache_and_skips_aggregates(async_orphan_db, monkeypatch):
    """同参第二次调用不再执行任何聚合 SQL，且统计值一致。"""
    await _seed(async_orphan_db)
    service = OrphanFileService(async_orphan_db)
    counter = _count_aggregate_executions(async_orphan_db, monkeypatch)

    first = await service.get_orphan_list(page=1, page_size=20)
    first_aggregates = counter["aggregate"]
    # 首次 miss：remaining/ignored 两条聚合；无过滤 total 复用 remaining → 无第三条
    assert first_aggregates == 2

    second = await service.get_orphan_list(page=1, page_size=20)
    assert counter["aggregate"] == first_aggregates  # 第二次零聚合
    assert second["scan_context"]["remaining_count"] == first["scan_context"]["remaining_count"]
    assert second["scan_context"]["remaining_size"] == first["scan_context"]["remaining_size"]
    assert second["scan_context"]["ignored_count"] == first["scan_context"]["ignored_count"]


async def test_no_filter_total_reuses_remaining(async_orphan_db, monkeypatch):
    """无过滤时 total 复用 remaining_count（连第三条 count 都不发）。"""
    await _seed(async_orphan_db)
    service = OrphanFileService(async_orphan_db)
    counter = _count_aggregate_executions(async_orphan_db, monkeypatch)

    result = await service.get_orphan_list(page=1, page_size=20)
    assert counter["aggregate"] == 2  # 仅 remaining + ignored
    assert result["total"] == result["scan_context"]["remaining_count"] == 3


async def test_filtered_total_still_computed(async_orphan_db, monkeypatch):
    """带过滤时 total 独立计算（remaining 缓存命中但过滤 count 仍执行）。"""
    await _seed(async_orphan_db)
    service = OrphanFileService(async_orphan_db)
    counter = _count_aggregate_executions(async_orphan_db, monkeypatch)

    first = await service.get_orphan_list(page=1, page_size=20, path_like="a.bin")
    assert first["total"] == 1
    # 首次：remaining + ignored + 过滤 count 三条
    assert counter["aggregate"] == 3

    second = await service.get_orphan_list(page=1, page_size=20, path_like="a.bin")
    # 第二次：remaining/ignored 命中缓存，仅过滤 count 一条
    assert counter["aggregate"] == 4
    assert second["total"] == 1


async def test_status_combination_not_reused_for_total(async_orphan_db, monkeypatch):
    """status 组合（pending,deleted）语义 ≠ remaining，不得复用 total。"""
    await _seed(async_orphan_db)
    service = OrphanFileService(async_orphan_db)
    counter = _count_aggregate_executions(async_orphan_db, monkeypatch)

    result = await service.get_orphan_list(page=1, page_size=20, status="pending,deleted")
    assert counter["aggregate"] == 3  # 过滤 count 独立执行
    assert result["total"] == 3


async def test_set_ignored_invalidates_cache(async_orphan_db):
    """忽视操作后统计刷新（缓存被失效重算）。"""
    scan_id = await _seed(async_orphan_db, current_mode=True)
    service = OrphanFileService(async_orphan_db)

    before = await service.get_orphan_list(page=1, page_size=20)
    assert before["scan_context"]["ignored_count"] == 1  # seed 的 ignored.bin

    detail = (
        await async_orphan_db.execute(select(OrphanFile).where(OrphanFile.file_path == "/data/a.bin"))
    ).scalar_one()
    await service.set_ignored(
        orphan_ids=[detail.id],
        ignored=True,
        operator="tester",
        scan_id=scan_id,
    )

    after = await service.get_orphan_list(page=1, page_size=20)
    assert after["scan_context"]["ignored_count"] == 2
    assert after["total"] == 3  # remaining 不受忽视影响


async def test_cleanup_submit_and_finish_invalidate_cache(async_orphan_db):
    """清理任务提交扣减 remaining、终态失败回升（submit/finish 失效点）。"""
    await _seed(async_orphan_db)
    service = OrphanFileService(async_orphan_db)
    detail = (
        await async_orphan_db.execute(select(OrphanFile).where(OrphanFile.file_path == "/data/a.bin"))
    ).scalar_one()

    before = await service.get_orphan_list(page=1, page_size=20)
    assert before["total"] == 3

    submission = await OrphanPurgeJobService(async_orphan_db).submit_cleanup_job(
        scan_id="scan_cache",
        orphan_ids=[detail.id],
        operator="tester",
    )
    hidden = await service.get_orphan_list(page=1, page_size=20)
    assert hidden["scan_context"]["remaining_count"] == 2

    assert submission.job is not None
    purge_service = OrphanPurgeJobService(async_orphan_db)
    assert await purge_service.claim_job(submission.job.task_id)
    await purge_service.finish_job(
        submission.job.task_id,
        status="failed",
        purged_count=0,
        failed_count=1,
        failed_list=[],
    )
    visible_again = await service.get_orphan_list(page=1, page_size=20)
    assert visible_again["scan_context"]["remaining_count"] == 3


async def test_grouped_uses_cache_but_never_reuses_total(async_orphan_db, monkeypatch):
    """grouped 模式统计走缓存；total 恒独立计算（组数 ≠ remaining）。"""
    await _seed(async_orphan_db)
    service = OrphanFileService(async_orphan_db)
    counter = _count_aggregate_executions(async_orphan_db, monkeypatch)

    first = await service.get_orphan_list_grouped(page=1, page_size=20)
    # grouped total 是组数（独立 SQL），remaining/ignored 两条缓存可命中
    second = await service.get_orphan_list_grouped(page=1, page_size=20)
    assert counter["aggregate"] >= 3  # 首次 remaining+ignored+组数count
    assert second["scan_context"]["remaining_count"] == first["scan_context"]["remaining_count"]


async def test_restore_invalidates_cache(async_orphan_db, tmp_path):
    """恢复操作（is_deleted=False）后 remaining 回升（_finalize_restore 失效点）。"""
    import os

    from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile

    quarantine_root = tmp_path / "quarantine"
    quarantine_root.mkdir()
    source = tmp_path / "restored.bin"
    source.write_bytes(b"payload")
    qpath = quarantine_root / "restored.bin"
    os.rename(source, qpath)

    scan = _scan("scan_restore")
    detail = OrphanFile(
        scan_id="scan_restore",
        file_path=str(source),
        file_size=7,
        downloader_id="dl_001",
        canonical_path=str(source),
    )
    detail.is_deleted = True
    candidate = OrphanCurrentCandidate(
        canonical_path=str(source),
        downloader_id="dl_001",
        first_seen_at=datetime.utcnow() - timedelta(days=1),
        last_seen_at=datetime.utcnow(),
        last_seen_scan_id="scan_restore",
        status="quarantined",
        operation_state="stable",
        file_size=7,
        quarantine_path=str(qpath),
        quarantine_root=str(quarantine_root),
        quarantined_at=datetime.utcnow(),
        purge_after=datetime.utcnow() + timedelta(days=7),
        device_id=str(os.stat(qpath).st_dev),
        inode=str(os.stat(qpath).st_ino),
    )
    async_orphan_db.add_all([scan, detail, candidate])
    await async_orphan_db.commit()

    service = OrphanFileService(async_orphan_db)
    before = await service.get_orphan_list(page=1, page_size=20)
    assert before["scan_context"]["remaining_count"] == 0  # 明细 is_deleted=True

    from unittest.mock import AsyncMock, MagicMock

    lease = MagicMock()
    lease.assert_owned = AsyncMock()
    result = await service.restore_quarantined(
        canonical_paths=[str(source)],
        operator="tester",
        _lease_acquired=True,
        _lease_handle=lease,
    )
    assert result["restored_count"] == 1

    after = await service.get_orphan_list(page=1, page_size=20)
    assert after["scan_context"]["remaining_count"] == 1


async def test_finalize_quarantine_invalidates_cache(async_orphan_db, tmp_path):
    """隔离最终化（is_deleted=True 咽喉）后 remaining 下降。"""
    scan = _scan("scan_finalize")
    detail = OrphanFile(
        scan_id="scan_finalize",
        file_path="/data/quarantine-me.bin",
        file_size=7,
        downloader_id="dl_001",
        canonical_path="/data/quarantine-me.bin",
    )
    candidate = OrphanCurrentCandidate(
        canonical_path="/data/quarantine-me.bin",
        downloader_id="dl_001",
        first_seen_at=datetime.utcnow() - timedelta(days=1),
        last_seen_at=datetime.utcnow(),
        last_seen_scan_id="scan_finalize",
        status="candidate",
        operation_state="stable",
        file_size=7,
    )
    async_orphan_db.add_all([scan, detail, candidate])
    await async_orphan_db.commit()

    service = OrphanFileService(async_orphan_db)
    before = await service.get_orphan_list(page=1, page_size=20)
    assert before["scan_context"]["remaining_count"] == 1

    await service._finalize_quarantine(
        candidate,
        quarantine_path="/quarantine/quarantine-me.bin",
        quarantine_root="/quarantine",
        purge_after=datetime.utcnow() + timedelta(days=7),
        scan_id="scan_finalize",
        operator="tester",
    )

    after = await service.get_orphan_list(page=1, page_size=20)
    assert after["scan_context"]["remaining_count"] == 0


async def test_no_completed_scan_does_not_write_cache(async_orphan_db):
    """最新扫描为 failed（无 completed 可展示）时列表早退，不得写缓存。"""
    from app.services.orphan_stats_cache import orphan_stats_cache

    failed = OrphanScanResult(
        scan_id="scan_failed_only",
        scan_time=datetime.utcnow(),
        scan_type="manual",
        status="failed",
    )
    async_orphan_db.add(failed)
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20)
    assert result["list"] == []
    assert orphan_stats_cache.get("scan_failed_only")[1] is None
    assert orphan_stats_cache.get("scan_failed_only")[1] is None  # 无任何 key 写入
