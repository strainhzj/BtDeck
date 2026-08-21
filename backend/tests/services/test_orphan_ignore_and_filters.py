# -*- coding: utf-8 -*-
"""孤儿文件管理增强测试：忽视态、别名、状态/路径筛选。

覆盖 v1.0.6 增强需求：
1. 下载器别名（nickname）解析注入 downloader_name
2. 置信度列透传
3. 忽视功能：set_ignored 写候选、列表查询注入 is_ignored、定时/手动清理跳过已忽视
4. 状态/路径多条件搜索与分页
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

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
    hardlink_copy_count: int | None = None,
) -> OrphanFile:
    item = OrphanFile(
        scan_id=scan_id,
        file_path=path,
        file_size=size,
        downloader_id=downloader_id,
        confidence=confidence,
        canonical_path=normalize_path(path),
        hardlink_copy_count=hardlink_copy_count,
    )
    item.is_deleted = deleted
    return item


def _candidate(
    path: str,
    *,
    downloader_id: str = "dl_001",
    ignored: bool = False,
    device_id: str | None = None,
    inode: str | None = None,
) -> OrphanCurrentCandidate:
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
        device_id=device_id,
        inode=inode,
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


async def test_list_filters_confidence_supports_multi_value(async_orphan_db):
    """置信度筛选支持逗号分隔多值（单值仍走 == 分支，多值走 in_）。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/low.bin", 100, confidence="low"),
            _detail("scan_1", "/data/high.bin", 200, confidence="high"),
            _detail("scan_1", "/data/low2.bin", 300, confidence="low"),
        ],
    )

    service = OrphanFileService(async_orphan_db)
    # 多值 in_：high,low → 命中全部
    both = await service.get_orphan_list(confidence="high,low")
    assert both["total"] == 3
    # 单值仍走 == 分支（回归保护）
    only_low = await service.get_orphan_list(confidence="low")
    assert only_low["total"] == 2
    # 去重：重复值不应改变结果
    deduped = await service.get_orphan_list(confidence="low,low")
    assert deduped["total"] == 2


async def test_list_filters_downloader_id_supports_multi_value(async_orphan_db):
    """下载器筛选支持逗号分隔多值。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/a.bin", 100, downloader_id="dl_001"),
            _detail("scan_1", "/data/b.bin", 200, downloader_id="dl_002"),
            _detail("scan_1", "/data/c.bin", 300, downloader_id="dl_003"),
        ],
    )

    service = OrphanFileService(async_orphan_db)
    both = await service.get_orphan_list(downloader_id="dl_001,dl_002")
    assert both["total"] == 2
    assert {item["file_path"] for item in both["list"]} == {"/data/a.bin", "/data/b.bin"}
    # 单值仍走 == 分支（回归保护）
    one = await service.get_orphan_list(downloader_id="dl_003")
    assert one["total"] == 1
    assert one["list"][0]["file_path"] == "/data/c.bin"


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


async def test_status_filter_supports_multi_value_union(async_orphan_db):
    """status 支持逗号分隔多值（OR 并集）；含 pending 的组合会退化为“所有未删除文件”。"""
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

    service = OrphanFileService(async_orphan_db)

    # 不矛盾的组合：ignored+deleted → 已忽视 ∪ 已删除
    ignored_deleted = await service.get_orphan_list(status="ignored,deleted")
    assert ignored_deleted["total"] == 2
    assert {item["file_path"] for item in ignored_deleted["list"]} == {
        "/data/ignored.bin",
        "/data/deleted.bin",
    }

    # pending + deleted（OR 并集）：(未删除 AND 不在忽视集) OR 已删除 = normal + deleted
    pending_deleted = await service.get_orphan_list(status="pending,deleted")
    assert pending_deleted["total"] == 2
    assert {item["file_path"] for item in pending_deleted["list"]} == {
        "/data/normal.bin",
        "/data/deleted.bin",
    }

    # pending + ignored（OR 退化）：(未删除 AND 不在忽视集) OR (未删除 AND 在忽视集)
    #   = 未删除 AND (不在忽视集 OR 在忽视集) = 未删除 AND 恒真 = 所有未删除文件
    pending_ignored = await service.get_orphan_list(status="pending,ignored")
    assert pending_ignored["total"] == 2
    assert {item["file_path"] for item in pending_ignored["list"]} == {
        "/data/normal.bin",
        "/data/ignored.bin",
    }

    # 去重：重复值不应改变结果
    deduped = await service.get_orphan_list(status="deleted,deleted")
    assert deduped["total"] == 1
    assert deduped["list"][0]["file_path"] == "/data/deleted.bin"


async def test_status_filter_multi_value_edge_cases(async_orphan_db):
    """status 多值的边界场景回归保护：三态全选/空串/纯逗号/含未知值/单值仍走原路径。"""
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

    service = OrphanFileService(async_orphan_db)

    # 三态全选：OR 退化为“所有文件”（含已删除）
    all_three = await service.get_orphan_list(status="pending,ignored,deleted")
    assert all_three["total"] == 3

    # 空串/纯逗号/纯空白：split 后无可用值 → 等价于无 status 筛选（默认排除已删除）
    for empty_status in ["", ",", " , ", ",,"]:
        result = await service.get_orphan_list(status=empty_status)
        assert result["total"] == 2, f"空串类 status={empty_status!r} 应等价于无筛选"

    # 含未知值：未知值被静默忽略，已知值正常过滤
    with_unknown = await service.get_orphan_list(status="pending,foobar")
    # pending + 未知 → 等同 pending 单值（normal）
    assert with_unknown["total"] == 1
    assert with_unknown["list"][0]["file_path"] == "/data/normal.bin"

    # 单值字符串仍走原 == 路径（回归保护，不因多值改造破坏单值）
    single_deleted = await service.get_orphan_list(status="deleted")
    assert single_deleted["total"] == 1
    assert single_deleted["list"][0]["file_path"] == "/data/deleted.bin"


async def test_resolve_select_all_matches_list_under_multi_value_filters(async_orphan_db):
    """全选当前筛选在多值过滤下必须与列表结果一致（list 与 resolve 同走 _build_orphan_conditions）。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/a.bin", 100, downloader_id="dl_001", confidence="high"),
            _detail("scan_1", "/data/b.bin", 200, downloader_id="dl_002", confidence="low"),
            _detail("scan_1", "/data/c.bin", 300, downloader_id="dl_001", confidence="low"),
            _detail("scan_1", "/data/ignored.bin", 400, downloader_id="dl_001", confidence="high"),
        ],
        candidates=[
            _candidate("/data/a.bin"),
            _candidate("/data/b.bin"),
            _candidate("/data/c.bin"),
            _candidate("/data/ignored.bin", ignored=True),
        ],
    )
    rows = (await async_orphan_db.execute(OrphanFile.__table__.select())).fetchall()
    ids_by_path = {row.file_path: row.id for row in rows}

    service = OrphanFileService(async_orphan_db)

    # 多值 confidence=high,low + 多值 downloader_id=dl_001,dl_002
    multi_filters = dict(confidence="high,low", downloader_id="dl_001,dl_002")
    list_result = await service.get_orphan_list(**multi_filters)
    list_ids = {item["id"] for item in list_result["list"]}

    selected_ids = set(
        await service.resolve_orphan_selection(
            orphan_ids=[],
            select_all=True,
            excluded_orphan_ids=[],
            scan_id="scan_1",
            **multi_filters,
        )
    )

    # 全选解析的 ID 集合必须与列表返回的 ID 集合完全一致
    assert selected_ids == list_ids, "多值过滤下 list 与 resolve 结果不一致"
    # 确实命中了预期的 4 个文件（未删除的全部）
    assert selected_ids == {
        ids_by_path["/data/a.bin"],
        ids_by_path["/data/b.bin"],
        ids_by_path["/data/c.bin"],
        ids_by_path["/data/ignored.bin"],
    }


async def test_resolve_select_all_uses_list_filters_and_exclusions(async_orphan_db):
    """全选必须解析当前筛选全集，并保留用户取消勾选的排除项。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/movie/a.bin", 100, confidence="high"),
            _detail("scan_1", "/data/movie/b.bin", 200, confidence="high"),
            _detail("scan_1", "/data/movie/low.bin", 300, confidence="low"),
            _detail("scan_1", "/data/music/ignored.bin", 400, confidence="high"),
        ],
        candidates=[
            _candidate("/data/movie/a.bin"),
            _candidate("/data/movie/b.bin"),
            _candidate("/data/movie/low.bin"),
            _candidate("/data/music/ignored.bin", ignored=True),
        ],
    )
    rows = (await async_orphan_db.execute(OrphanFile.__table__.select())).fetchall()
    ids_by_path = {row.file_path: row.id for row in rows}

    selected_ids = await OrphanFileService(async_orphan_db).resolve_orphan_selection(
        orphan_ids=[],
        select_all=True,
        excluded_orphan_ids=[ids_by_path["/data/movie/b.bin"]],
        scan_id="scan_1",
        path_like="movie",
        status="pending",
        confidence="high",
    )

    assert selected_ids == [ids_by_path["/data/movie/a.bin"]]


async def test_set_ignored_chunks_large_select_all_snapshot(async_orphan_db):
    """跨越单块上限的全选 ID 快照不会触发 SQLite 绑定变量上限。"""
    details = [_detail("scan_1", f"/data/bulk/{index}.bin", index + 1) for index in range(520)]
    candidates = [_candidate(detail.file_path) for detail in details]
    await _seed(async_orphan_db, details, candidates=candidates)
    rows = (await async_orphan_db.execute(OrphanFile.__table__.select())).fetchall()
    orphan_ids = [int(row.id) for row in rows]

    result = await OrphanFileService(async_orphan_db).set_ignored(
        orphan_ids=orphan_ids,
        ignored=True,
        operator="bulk-user",
        scan_id="scan_1",
    )

    assert result["success_count"] == 520
    assert result["failed_count"] == 0


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


# ==================== 左匹配（前缀 path_prefix） ====================


async def test_path_prefix_matches_left_anchored_only(async_orphan_db):
    """path_prefix 必须只命中以前缀开头的路径，子串相同但前缀不匹配的不命中。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/leak/a.bin", 100),
            _detail("scan_1", "/data/leak/sub/b.bin", 200),
            _detail("scan_1", "/data/other/leak_c.bin", 300),  # 子串含 leak 但非前缀
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(path_prefix="/data/leak/")

    paths = sorted(item["file_path"] for item in result["list"])
    assert paths == ["/data/leak/a.bin", "/data/leak/sub/b.bin"]
    assert result["total"] == 2


async def test_path_prefix_escapes_wildcards(async_orphan_db):
    """前缀中的 %/_ 应作字面量，不当作 LIKE 通配符。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/100%_dir/file.bin", 100),
            _detail("scan_1", "/data/100A_dir/file.bin", 200),
        ],
    )

    result = await OrphanFileService(async_orphan_db).get_orphan_list(path_prefix="/data/100%_dir")

    paths = [item["file_path"] for item in result["list"]]
    assert paths == ["/data/100%_dir/file.bin"]


async def test_prefix_match_preview_counts_pending_only_and_size(async_orphan_db):
    """prefix_match_preview 必须只统计待清理项（排除已忽视/已清理），并返回正确大小与低置信度数。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_1", "/data/leak/a.bin", 100, confidence="high"),
            _detail("scan_1", "/data/leak/b.bin", 200, confidence="low"),
            _detail("scan_1", "/data/leak/ignored.bin", 400, confidence="high"),
            _detail("scan_1", "/data/leak/deleted.bin", 800, deleted=True),
            _detail("scan_1", "/data/other/c.bin", 50, confidence="high"),
        ],
        candidates=[
            _candidate("/data/leak/a.bin"),
            _candidate("/data/leak/b.bin"),
            _candidate("/data/leak/ignored.bin", ignored=True),
        ],
    )

    result = await OrphanFileService(async_orphan_db).prefix_match_preview("/data/leak/", "scan_1")

    assert result.get("rejected") is not True
    assert result["count"] == 2  # a.bin + b.bin（排除 ignored 与 deleted）
    assert result["total_size"] == 300
    assert result["low_confidence_count"] == 1  # b.bin


async def test_prefix_match_preview_rejects_stale_scan(async_orphan_db):
    """scan_id 非最新批次时，preview 应返回 rejected=True 而非误导性计数。"""
    await _seed(
        async_orphan_db,
        [
            _detail("scan_old", "/data/leak/a.bin", 100),
            _detail("scan_latest", "/data/leak/a.bin", 100),
        ],
    )
    # _seed 只为每个 detail 建 scan；显式补一个最新 completed scan
    async_orphan_db.add(_scan("scan_latest"))
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).prefix_match_preview("/data/leak/", "scan_old")

    assert result["rejected"] is True
    assert result["count"] == 0


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


async def test_set_ignored_uses_canonical_path_and_repairs_changed_owner(async_orphan_db):
    """路径是候选主键；扫描归属变化不能让忽视操作误判候选不存在。"""
    candidate = _candidate("/data/a.bin", downloader_id="dl_old", ignored=False)
    candidate.last_seen_scan_id = "scan_1"
    await _seed(
        async_orphan_db,
        [_detail("scan_1", "/data/a.bin", 100, downloader_id="dl_new")],
        candidates=[candidate],
    )

    detail = await async_orphan_db.execute(OrphanFile.__table__.select())
    orphan_id = detail.first().id

    result = await OrphanFileService(async_orphan_db).set_ignored(
        orphan_ids=[orphan_id], ignored=True, operator="alice", scan_id="scan_1"
    )

    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    candidate_result = await async_orphan_db.execute(
        OrphanCurrentCandidate.__table__.select().where(
            OrphanCurrentCandidate.canonical_path == normalize_path("/data/a.bin")
        )
    )
    row = candidate_result.first()
    assert row.is_ignored == 1
    assert row.downloader_id == "dl_new"


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

    with patch("app.services.orphan_file_service.logger.warning") as warning_log:
        result = await OrphanFileService(async_orphan_db).set_ignored(
            orphan_ids=[orphan_id], ignored=True, operator="alice", scan_id="scan_1"
        )

    assert result["success_count"] == 0
    assert result["failed_count"] == 1
    assert "清理流程" in result["failed_list"][0]["reason"]
    assert "failed_reasons" in str(warning_log.call_args)
    assert "清理流程" in str(warning_log.call_args)


async def test_set_ignored_commit_failure_logs_exception_and_returns_reason(async_orphan_db):
    await _seed(
        async_orphan_db,
        [_detail("scan_1", "/data/a.bin", 100)],
        candidates=[_candidate("/data/a.bin", ignored=False)],
    )
    detail = await async_orphan_db.execute(OrphanFile.__table__.select())
    orphan_id = detail.first().id

    with (
        patch.object(
            async_orphan_db,
            "commit",
            new=AsyncMock(side_effect=RuntimeError("simulated commit failure")),
        ),
        patch("app.services.orphan_file_service.logger.exception") as exception_log,
    ):
        result = await OrphanFileService(async_orphan_db).set_ignored(
            orphan_ids=[orphan_id], ignored=True, operator="alice", scan_id="scan_1"
        )

    assert result["success_count"] == 0
    assert result["failed_count"] == 1
    assert result["failed_list"][0]["reason"] == "数据库提交失败，请查看后端日志"
    assert "simulated commit failure" in str(exception_log.call_args)


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


# ==================== 副本筛选（hardlink_copies=located，快照列语义） ====================


async def _seed_copy_count_samples(async_orphan_db):
    """四类样本：快照>0（命中）、快照=0、快照=NULL（未知）、已删除。"""
    from app.downloader.models import BtDownloaders

    details = [
        _detail("scan_1", "/data/located.bin", 100, hardlink_copy_count=2),
        _detail("scan_1", "/data/no-copies.bin", 200, hardlink_copy_count=0),
        _detail("scan_1", "/data/pending.bin", 300, hardlink_copy_count=None),
        _detail("scan_1", "/data/deleted.bin", 400, hardlink_copy_count=3, deleted=True),
    ]
    async_orphan_db.add_all([_scan("scan_1"), *details, BtDownloaders(downloader_id="dl_001", nickname="主下载器")])
    await async_orphan_db.commit()


async def test_list_filters_hardlink_copies_located(async_orphan_db):
    """located 筛选仅保留快照列 hardlink_copy_count > 0 的未删除文件。"""
    await _seed_copy_count_samples(async_orphan_db)

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20, hardlink_copies="located")

    assert result["total"] == 1
    assert [item["file_path"] for item in result["list"]] == ["/data/located.bin"]


async def test_list_returns_hardlink_copy_count_snapshot(async_orphan_db):
    """列表行直出明细快照列，不再对文件做实时 stat。"""
    await _seed_copy_count_samples(async_orphan_db)

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20)

    counts = {item["file_path"]: item["hardlink_copy_count"] for item in result["list"]}
    assert counts == {
        "/data/located.bin": 2,
        "/data/no-copies.bin": 0,
        "/data/pending.bin": None,
    }


async def test_list_hardlink_copies_filter_ignores_unknown_values(async_orphan_db):
    """未识别的 hardlink_copies 取值不追加条件（与 status/confidence 宽松口径一致）。"""
    await _seed_copy_count_samples(async_orphan_db)

    result = await OrphanFileService(async_orphan_db).get_orphan_list(page=1, page_size=20, hardlink_copies="bogus")

    assert result["total"] == 3


async def test_list_hardlink_copies_filter_combines_with_ignored_status(async_orphan_db):
    """located 与 status=ignored 正交：已忽视但快照有副本的文件仍可被筛出。"""
    details = [_detail("scan_1", "/data/ignored-located.bin", 100, hardlink_copy_count=1)]
    candidates = [_candidate("/data/ignored-located.bin", ignored=True)]
    async_orphan_db.add_all([_scan("scan_1"), *details, *candidates])
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).get_orphan_list(
        page=1, page_size=20, status="ignored", hardlink_copies="located"
    )

    assert result["total"] == 1
    assert [item["file_path"] for item in result["list"]] == ["/data/ignored-located.bin"]


async def test_grouped_and_folder_children_share_located_filter(async_orphan_db):
    """文件夹聚合与子项展开与扁平列表共用 located 过滤口径。"""
    await _seed_copy_count_samples(async_orphan_db)

    grouped = await OrphanFileService(async_orphan_db).get_orphan_list_grouped(
        page=1, page_size=20, hardlink_copies="located"
    )
    assert grouped["total"] == 1
    assert grouped["list"][0]["file_path"] == "/data/located.bin"

    children = await OrphanFileService(async_orphan_db).get_orphan_folder_children(
        "/data", page=1, page_size=20, hardlink_copies="located"
    )
    assert children["total"] == 1
    assert [item["file_path"] for item in children["list"]] == ["/data/located.bin"]


async def test_resolve_orphan_selection_applies_located_filter(async_orphan_db):
    """全选当前筛选快照透传 located：只选择快照有副本的文件（口径与列表一致）。"""
    await _seed_copy_count_samples(async_orphan_db)
    details = (await async_orphan_db.execute(OrphanFile.__table__.select())).fetchall()
    ids_by_path = {row.file_path: row.id for row in details}

    ids = await OrphanFileService(async_orphan_db).resolve_orphan_selection(
        orphan_ids=[],
        select_all=True,
        excluded_orphan_ids=[],
        scan_id="scan_1",
        hardlink_copies="located",
    )

    assert ids == [ids_by_path["/data/located.bin"]]


async def test_prefix_match_preview_applies_located_filter(async_orphan_db):
    """快捷前缀预览透传 located：统计范围限定有副本的待清理文件。"""
    details = [
        _detail("scan_1", "/data/prefix/located.bin", 100, hardlink_copy_count=2),
        _detail("scan_1", "/data/prefix/plain.bin", 200, hardlink_copy_count=0),
        _detail("scan_1", "/other/plain.bin", 300, hardlink_copy_count=1),
    ]
    async_orphan_db.add_all([_scan("scan_1"), *details])
    await async_orphan_db.commit()

    scoped = await OrphanFileService(async_orphan_db).prefix_match_preview(
        "/data/prefix/", "scan_1", hardlink_copies="located"
    )
    assert scoped["count"] == 1

    unscoped = await OrphanFileService(async_orphan_db).prefix_match_preview("/data/prefix/", "scan_1")
    assert unscoped["count"] == 2


async def test_list_hardlink_copies_located_combines_with_confidence_filter(async_orphan_db):
    """located 与置信度筛选 AND 叠加：只返回同时满足两个条件的行。"""
    details = [
        _detail("scan_1", "/data/located-high.bin", 100, confidence="high", hardlink_copy_count=1),
        _detail("scan_1", "/data/located-low.bin", 200, confidence="low", hardlink_copy_count=1),
        _detail("scan_1", "/data/unlocated-high.bin", 300, confidence="high", hardlink_copy_count=0),
    ]
    async_orphan_db.add_all([_scan("scan_1"), *details])
    await async_orphan_db.commit()

    result = await OrphanFileService(async_orphan_db).get_orphan_list(
        page=1, page_size=20, hardlink_copies="located", confidence="high"
    )

    assert result["total"] == 1
    assert [item["file_path"] for item in result["list"]] == ["/data/located-high.bin"]
