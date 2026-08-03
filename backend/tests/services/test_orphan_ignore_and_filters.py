# -*- coding: utf-8 -*-
"""孤儿文件管理增强测试：忽视态、别名、状态/路径筛选。

覆盖 v1.0.6 增强需求：
1. 下载器别名（nickname）解析注入 downloader_name
2. 置信度列透传
3. 忽视功能：set_ignored 写候选、列表查询注入 is_ignored、定时/手动清理跳过已忽视
4. 状态/路径多条件搜索与分页
"""

from datetime import datetime, timedelta

import pytest

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import normalize_path

pytestmark = pytest.mark.asyncio


def _scan(scan_id: str, *, status: str = "completed", scan_time: datetime | None = None) -> OrphanScanResult:
    record = OrphanScanResult(
        scan_id=scan_id,
        scan_time=scan_time or datetime.utcnow(),
        scan_type="manual",
        status=status,
    )
    record.total_paths_scanned = 1
    record.total_files_scanned = 10
    record.total_orphans = 3
    record.total_orphan_size = 1000
    return record


def _detail(
    scan_id: str,
    path: str,
    size: int,
    *,
    downloader_id: str | None = "dl_001",
    confidence: str = "high",
    deleted: bool = False,
) -> OrphanFile:
    item = OrphanFile(
        scan_id=scan_id,
        file_path=path,
        file_size=size,
        downloader_id=downloader_id,
        confidence=confidence,
        canonical_path=normalize_path(path),
    )
    item.is_deleted = deleted
    return item


def _candidate(path: str, *, downloader_id: str = "dl_001", ignored: bool = False) -> OrphanCurrentCandidate:
    now = datetime.utcnow()
    cand = OrphanCurrentCandidate(
        canonical_path=normalize_path(path),
        downloader_id=downloader_id,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
        status="candidate",
        operation_state="stable",
        confidence="high",
        is_ignored=ignored,
    )
    if ignored:
        cand.ignored_at = now
        cand.ignored_by = "tester"
    return cand


async def _seed(async_orphan_db, details, candidates=None, downloaders=None):
    from app.downloader.models import BtDownloaders

    scan_id = details[0].scan_id if details else "scan_1"
    async_orphan_db.add_all([_scan(scan_id), *details])
    if candidates:
        async_orphan_db.add_all(candidates)
    if downloaders:
        async_orphan_db.add_all(downloaders)
    else:
        # 默认创建一个下载器，nickname 作为别名
        dl = BtDownloaders(downloader_id="dl_001", nickname="主下载器")
        async_orphan_db.add(dl)
    await async_orphan_db.commit()


# ==================== 别名与置信度 ====================


async def test_list_injects_downloader_name_and_confidence(async_orphan_db):
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/a.bin", 100, downloader_id="dl_001", confidence="high"),
            _detail("scan_1", "/data/b.bin", 200, downloader_id="dl_missing", confidence="low"),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20)

    by_path = {item["file_path"]: item for item in result["list"]}
    # 已知下载器展示 nickname
    assert by_path["/data/a.bin"]["downloader_name"] == "主下载器"
    assert by_path["/data/a.bin"]["confidence"] == "high"
    # 未知下载器 nickname 为 None
    assert by_path["/data/b.bin"]["downloader_name"] is None
    assert by_path["/data/b.bin"]["confidence"] == "low"
    # canonical_path 透传
    assert by_path["/data/a.bin"]["canonical_path"] == normalize_path("/data/a.bin")


async def test_list_filters_confidence_and_defaults_to_high_first(async_orphan_db):
    """列表支持置信度筛选，未筛选时高置信度稳定排在低置信度前。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/low-large.bin", 999, confidence="low"),
            _detail("scan_1", "/data/high-small.bin", 100, confidence="high"),
            _detail("scan_1", "/data/high-large.bin", 300, confidence="high"),
        ],
    )

    service = OrphanFileService(async_orphan_db)
    default_result = await service.get_orphan_list(page=1, page_size=20)
    assert [item["file_path"] for item in default_result["list"]] == [
        "/data/high-large.bin",
        "/data/high-small.bin",
        "/data/low-large.bin",
    ]

    low_result = await service.get_orphan_list(confidence="low")
    assert low_result["total"] == 1
    assert [item["file_path"] for item in low_result["list"]] == ["/data/low-large.bin"]


# ==================== 忽视态注入与计数 ====================


async def test_list_injects_ignore_state_and_count(async_orphan_db):
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/ignored.bin", 100),
            _detail("scan_1", "/data/normal.bin", 200),
        ],
        candidates=[
            _candidate("/data/ignored.bin", ignored=True),
            _candidate("/data/normal.bin", ignored=False),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20)

    by_path = {item["file_path"]: item for item in result["list"]}
    assert by_path["/data/ignored.bin"]["is_ignored"] is True
    assert by_path["/data/ignored.bin"]["ignored_by"] == "tester"
    assert by_path["/data/normal.bin"]["is_ignored"] is False
    # ignored_count 仅计未被清理且被忽视的
    assert result["scan_context"]["ignored_count"] == 1


# ==================== 状态筛选 ====================


async def test_status_filter_ignored_only(async_orphan_db):
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/ignored.bin", 100),
            _detail("scan_1", "/data/normal.bin", 200),
            _detail("scan_1", "/data/deleted.bin", 300, deleted=True),
        ],
        candidates=[
            _candidate("/data/ignored.bin", ignored=True),
            _candidate("/data/normal.bin", ignored=False),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(status="ignored")

    paths = [item["file_path"] for item in result["list"]]
    assert paths == ["/data/ignored.bin"]
    assert result["total"] == 1


async def test_status_filter_pending_excludes_ignored_and_deleted(async_orphan_db):
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/ignored.bin", 100),
            _detail("scan_1", "/data/normal.bin", 200),
            _detail("scan_1", "/data/deleted.bin", 300, deleted=True),
        ],
        candidates=[
            _candidate("/data/ignored.bin", ignored=True),
            _candidate("/data/normal.bin", ignored=False),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(status="pending")

    paths = [item["file_path"] for item in result["list"]]
    assert paths == ["/data/normal.bin"]
    assert result["total"] == 1


async def test_status_filter_deleted(async_orphan_db):
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/normal.bin", 200),
            _detail("scan_1", "/data/deleted.bin", 300, deleted=True),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(status="deleted")

    paths = [item["file_path"] for item in result["list"]]
    assert paths == ["/data/deleted.bin"]
    assert result["total"] == 1


# ==================== 路径模糊筛选 ====================


async def test_path_like_filter(async_orphan_db):
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/movie/a.mkv", 100),
            _detail("scan_1", "/data/music/b.mp3", 200),
            _detail("scan_1", "/data/movie/c.bin", 300),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(path_like="movie")

    paths = sorted(item["file_path"] for item in result["list"])
    assert paths == ["/data/movie/a.mkv", "/data/movie/c.bin"]
    assert result["total"] == 2


async def test_path_like_escapes_wildcards(async_orphan_db):
    """用户输入 %/_ 应作字面量匹配，不当作 LIKE 通配符。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/100%_file.bin", 100),
            _detail("scan_1", "/data/normal.bin", 200),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(path_like="100%_file")

    paths = [item["file_path"] for item in result["list"]]
    assert paths == ["/data/100%_file.bin"]


# ==================== 排序：被忽视沉底，待清理在前 ====================


async def test_list_orders_ignored_last_within_mixed_status(async_orphan_db):
    """status=None 混合待清理+已忽视时，已忽视必须排在所有待清理之后。

    组内仍按 file_size DESC：待清理组中大文件在前；已忽视组同样大文件在前。
    """
    await _seed(
        async_orphan_db,
        [
            # 待清理组
            _detail("scan_1", "/data/pending_big.bin", 500),
            _detail("scan_1", "/data/pending_small.bin", 50),
            # 已忽视组（即便文件更大，也必须沉底）
            _detail("scan_1", "/data/ignored_huge.bin", 9999),
            _detail("scan_1", "/data/ignored_tiny.bin", 10),
        ],
        candidates=[
            _candidate("/data/ignored_huge.bin", ignored=True),
            _candidate("/data/ignored_tiny.bin", ignored=True),
            _candidate("/data/pending_big.bin", ignored=False),
            _candidate("/data/pending_small.bin", ignored=False),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20)

    paths = [item["file_path"] for item in result["list"]]
    # 前 2 条为待清理（按大小降序），后 2 条为已忽视（按大小降序）
    assert paths == [
        "/data/pending_big.bin",
        "/data/pending_small.bin",
        "/data/ignored_huge.bin",
        "/data/ignored_tiny.bin",
    ]


async def test_list_orders_pure_pending_unchanged(async_orphan_db):
    """纯待清理（status=pending）场景排序不受 ignored_rank 干扰，仍按大小降序。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/a.bin", 100),
            _detail("scan_1", "/data/b.bin", 300),
            _detail("scan_1", "/data/c.bin", 200),
        ],
        candidates=[
            _candidate("/data/a.bin", ignored=False),
            _candidate("/data/b.bin", ignored=False),
            _candidate("/data/c.bin", ignored=False),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(status="pending")

    paths = [item["file_path"] for item in result["list"]]
    assert paths == ["/data/b.bin", "/data/c.bin", "/data/a.bin"]


# ==================== set_ignored 生命周期 ====================


async def test_set_ignored_marks_candidate(async_orphan_db):
    await _seed(
        async_orphan_db,
        [_detail("scan_1", "/data/a.bin", 100)],
        candidates=[_candidate("/data/a.bin", ignored=False)],
    )

    detail = await async_orphan_db.execute(OrphanFile.__table__.select())
    orphan_id = detail.first().id

    result = await OrphanFileService(async_orphan_db).set_ignored(
        orphan_ids=[orphan_id], ignored=True, operator="alice", scan_id="scan_1"
    )

    assert result["success_count"] == 1
    assert result["failed_count"] == 0

    cand_result = await async_orphan_db.execute(
        OrphanCurrentCandidate.__table__.select().where(
            OrphanCurrentCandidate.canonical_path == normalize_path("/data/a.bin")
        )
    )
    row = cand_result.first()
    assert row.is_ignored == 1  # SQLite Boolean
    assert row.ignored_by == "alice"


async def test_set_ignored_chunks_large_batch(async_orphan_db):
    """大批量忽视应分块查询和 flush，避免 SQLite 参数/批量写入限制。"""
    item_count = 401
    details = [_detail("scan_1", f"/data/batch-{index}.bin", index + 1) for index in range(item_count)]
    candidates = [_candidate(f"/data/batch-{index}.bin") for index in range(item_count)]
    await _seed(async_orphan_db, details, candidates=candidates)

    detail_result = await async_orphan_db.execute(OrphanFile.__table__.select().order_by(OrphanFile.id))
    orphan_ids = [row.id for row in detail_result.fetchall()]

    result = await OrphanFileService(async_orphan_db).set_ignored(
        orphan_ids=orphan_ids,
        ignored=True,
        operator="alice",
        scan_id="scan_1",
    )

    assert result["success_count"] == item_count
    assert result["failed_count"] == 0

    candidate_result = await async_orphan_db.execute(
        OrphanCurrentCandidate.__table__.select().where(
            OrphanCurrentCandidate.canonical_path.in_(
                [normalize_path(f"/data/batch-{index}.bin") for index in range(item_count)]
            )
        )
    )
    rows = candidate_result.fetchall()
    assert len(rows) == item_count
    assert all(row.is_ignored == 1 and row.ignored_by == "alice" for row in rows)


async def test_set_ignored_unignore_clears_fields(async_orphan_db):
    await _seed(
        async_orphan_db,
        [_detail("scan_1", "/data/a.bin", 100)],
        candidates=[_candidate("/data/a.bin", ignored=True)],
    )

    detail = await async_orphan_db.execute(OrphanFile.__table__.select())
    orphan_id = detail.first().id

    result = await OrphanFileService(async_orphan_db).set_ignored(
        orphan_ids=[orphan_id], ignored=False, operator="alice", scan_id="scan_1"
    )

    assert result["success_count"] == 1
    cand_result = await async_orphan_db.execute(
        OrphanCurrentCandidate.__table__.select().where(
            OrphanCurrentCandidate.canonical_path == normalize_path("/data/a.bin")
        )
    )
    row = cand_result.first()
    assert row.is_ignored == 0
    assert row.ignored_by is None
    assert row.ignored_at is None


async def test_set_ignored_rejects_quarantined_candidate(async_orphan_db):
    """已进入清理流水线（quarantined）的候选不可忽视。"""
    cand = _candidate("/data/a.bin", ignored=False)
    cand.status = "quarantined"
    await _seed(
        async_orphan_db,
        [_detail("scan_1", "/data/a.bin", 100)],
        candidates=[cand],
    )

    detail = await async_orphan_db.execute(OrphanFile.__table__.select())
    orphan_id = detail.first().id

    result = await OrphanFileService(async_orphan_db).set_ignored(
        orphan_ids=[orphan_id], ignored=True, operator="alice", scan_id="scan_1"
    )

    assert result["success_count"] == 0
    assert result["failed_count"] == 1
    assert "清理流程" in result["failed_list"][0]["reason"]


# ==================== 清理门禁：已忽视被拒绝 ====================


async def test_cleanup_preview_excludes_ignored(async_orphan_db):
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/ignored.bin", 100),
            _detail("scan_1", "/data/cleanable.bin", 200),
        ],
        candidates=[
            _candidate("/data/ignored.bin", ignored=True),
            _candidate("/data/cleanable.bin", ignored=False),
        ],
    )

    details = (await async_orphan_db.execute(OrphanFile.__table__.select())).fetchall()
    ids_by_path = {row.file_path: row.id for row in details}

    result = await OrphanFileService(async_orphan_db).cleanup_preview(
        orphan_ids=[ids_by_path["/data/ignored.bin"], ids_by_path["/data/cleanable.bin"]],
        scan_id="scan_1",
    )

    # 已忽视项被排除，仅返回可清理项
    paths = {item["file_path"] for item in result["items"]}
    assert paths == {"/data/cleanable.bin"}
    assert result["total_count"] == 1


async def test_cleanup_preview_includes_low_confidence_with_count(async_orphan_db):
    """手动清理放行 low confidence：low 明细进入 preview 的 items，且响应返回 low_confidence_count。

    守护本次修改：cleanup_preview 移除了 SQL 的 confidence=='high' 过滤，并新增 low_confidence_count
    字段供前端警告。若误加回 high 过滤，low 项会被排除、count 恒为 0。
    """
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/low.bin", 100, confidence="low"),
            _detail("scan_1", "/data/high.bin", 200, confidence="high"),
        ],
        candidates=[
            _candidate("/data/low.bin", ignored=False),
            _candidate("/data/high.bin", ignored=False),
        ],
    )

    details = (await async_orphan_db.execute(OrphanFile.__table__.select())).fetchall()
    ids_by_path = {row.file_path: row.id for row in details}

    result = await OrphanFileService(async_orphan_db).cleanup_preview(
        orphan_ids=[ids_by_path["/data/low.bin"], ids_by_path["/data/high.bin"]],
        scan_id="scan_1",
    )

    # low 与 high 都进入 items（手动清理不再按 confidence 过滤）
    paths = {item["file_path"] for item in result["items"]}
    assert paths == {"/data/low.bin", "/data/high.bin"}, "low confidence 明细应进入 preview items"
    assert result["total_count"] == 2
    # low_confidence_count 准确反映 low 项数量
    assert result["low_confidence_count"] == 1, "应统计 1 个 low confidence 项供前端警告"
