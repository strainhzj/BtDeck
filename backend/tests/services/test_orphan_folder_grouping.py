# -*- coding: utf-8 -*-
"""孤儿文件按文件夹（直接父目录）聚合分页测试。

覆盖：
- 分组正确性（cnt>=2 折叠、cnt=1 原样）
- Windows ``\\`` 与 Unix ``/`` 分隔符统一
- 分页（按文件夹组，total=组数，不重叠）
- 组间排序（组内最大文件降序 + 父目录字典序）
- 组内排序（confidence/ignored/file_size/id 稳定）
- 筛选叠加（downloader_id/status/path_like 与分组共存）
- scan_context 文件级统计与扁平模式一致

使用局部独立 fixture（挂载 bt_orphan_parent_dir 自定义函数），
不污染共享 conftest.async_orphan_db。
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import normalize_path

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def grouped_db():
    """异步内存 SQLite + 注册 bt_orphan_parent_dir 自定义函数。

    局部独立 fixture，不影响共享 async_orphan_db。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # bt_orphan_parent_dir 由 service 内 ensure_folder_grouping_functions(session)
    # 在查询前注册（aiosqlite 下 connect 事件不生效，与 bt_regexp 同因），此处无需挂监听器。

    # 延迟 import 确保所有相关 ORM 模型已注册到 Base.metadata
    from app.models.orphan_file import OrphanFile, OrphanScanResult  # noqa: F401
    from app.downloader.models import BtDownloaders  # noqa: F401
    from app.models.notification import Notification  # noqa: F401
    from app.torrents.models import TorrentInfo  # noqa: F401
    from app.torrents.audit_models import TorrentAuditLog  # noqa: F401
    from app.tasks.cron_models import CronTask  # noqa: F401
    from app.models.setting_templates import SettingTemplate  # noqa: F401
    from app.auth.models import User  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


def _scan(scan_id: str, *, status: str = "completed") -> OrphanScanResult:
    record = OrphanScanResult(
        scan_id=scan_id,
        scan_time=datetime(2026, 7, 30, 10, 0, 0),
        scan_type="manual",
        status=status,
    )
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
    return OrphanCurrentCandidate(
        canonical_path=normalize_path(path),
        downloader_id=downloader_id,
        first_seen_at=now - timedelta(days=1),
        last_seen_at=now,
        status="candidate",
        operation_state="stable",
        confidence="high",
        is_ignored=ignored,
    )


# ==================== 分组正确性 ====================


async def test_grouping_two_files_same_dir_become_folder_row(grouped_db):
    """同目录 >=2 个文件折叠为文件夹行，单文件保持原样。"""
    grouped_db.add(_scan("scan_completed"))
    grouped_db.add_all(
        [
            _detail("scan_completed", "/data/movie/a.mp4", 100),
            _detail("scan_completed", "/data/movie/b.mp4", 200),
            _detail("scan_completed", "/data/alone.mp4", 50),
        ]
    )
    await grouped_db.commit()

    result = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=20)
    lst = result["list"]
    # 2 个组：/data/movie（2 文件）+ /data（1 文件）
    assert len(lst) == 2
    folder_rows = [r for r in lst if r.get("_is_folder")]
    file_rows = [r for r in lst if not r.get("_is_folder")]
    assert len(folder_rows) == 1
    assert len(file_rows) == 1

    folder = folder_rows[0]
    assert folder["folder_path"] == "/data/movie"
    assert folder["child_count"] == 2
    # 父列表不加载目录全部子项；展开后由独立分页接口获取。
    assert folder["children"] == []
    assert folder["child_ids"] == []
    assert folder["children_loaded"] is False
    assert folder["total_size"] == 300
    assert folder["folder_key"] == "folder:/data/movie"
    assert folder["all_pending"] is True
    assert folder["has_low_confidence"] is False

    children = await OrphanFileService(grouped_db).get_orphan_folder_children("/data/movie", page=1, page_size=20)
    # 子页按 file_size DESC 稳定排序：b.mp4(200) 在前、a.mp4(100) 在后。
    assert children["total"] == 2
    assert [item["id"] for item in children["list"]] == [2, 1]

    # 单文件原样（OrphanFileItem，无 _is_folder / children 等字段）
    single = file_rows[0]
    assert single["file_path"] == "/data/alone.mp4"
    assert "_is_folder" not in single


async def test_grouping_windows_backslash_unified_with_slash(grouped_db):
    """Windows 反斜杠路径按直接父目录分组（统一为 /）。"""
    grouped_db.add(_scan("scan_completed"))
    grouped_db.add_all(
        [
            _detail("scan_completed", r"C:\downloads\movie\a.mp4", 100),
            _detail("scan_completed", r"C:\downloads\movie\b.mp4", 200),
        ]
    )
    await grouped_db.commit()

    result = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=20)
    lst = result["list"]
    assert len(lst) == 1
    folder = lst[0]
    assert folder["folder_path"] == "C:/downloads/movie"
    assert folder["child_count"] == 2


# ==================== 分页 ====================


async def test_grouping_pagination_by_folder_group(grouped_db):
    """分页单位为文件夹组，total=组数，页间不重叠。"""
    grouped_db.add(_scan("scan_completed"))
    # 25 个不同目录，每个目录 2 个文件 → 25 个文件夹组
    details = []
    for index in range(1, 26):
        details.append(_detail("scan_completed", f"/data/d{index}/a.bin", index * 10))
        details.append(_detail("scan_completed", f"/data/d{index}/b.bin", index * 10 + 1))
    grouped_db.add_all(details)
    await grouped_db.commit()

    page1 = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=10)
    page2 = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=2, page_size=10)
    page3 = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=3, page_size=10)

    assert page1["total"] == 25
    assert len(page1["list"]) == 10
    assert len(page2["list"]) == 10
    assert len(page3["list"]) == 5

    # 页间不重叠：folder_path 集合不相交
    p1_paths = {r["folder_path"] for r in page1["list"]}
    p2_paths = {r["folder_path"] for r in page2["list"]}
    p3_paths = {r["folder_path"] for r in page3["list"]}
    assert p1_paths.isdisjoint(p2_paths)
    assert p1_paths.isdisjoint(p3_paths)
    assert p2_paths.isdisjoint(p3_paths)


# ==================== 组间排序 ====================


async def test_grouping_inter_group_order_by_max_size_then_path(grouped_db):
    """组间排序：组内最大文件降序、父目录字典序升序。"""
    grouped_db.add(_scan("scan_completed"))
    grouped_db.add_all(
        [
            # /data/big 组最大文件 500
            _detail("scan_completed", "/data/big/a.bin", 500),
            _detail("scan_completed", "/data/big/b.bin", 100),
            # /data/mid 组最大文件 300
            _detail("scan_completed", "/data/mid/a.bin", 300),
            _detail("scan_completed", "/data/mid/b.bin", 200),
            # /data/aaa 组最大文件 300（与 mid 同，按路径字典序 aaa < mid）
            _detail("scan_completed", "/data/aaa/a.bin", 300),
            _detail("scan_completed", "/data/aaa/b.bin", 250),
        ]
    )
    await grouped_db.commit()

    result = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=20)
    paths = [r["folder_path"] for r in result["list"]]
    # big(500) > mid(300) 与 aaa(300) 同级，aaa 字典序在前
    assert paths == ["/data/big", "/data/aaa", "/data/mid"]


# ==================== 组内排序 ====================


async def test_grouping_intra_group_stable_order(grouped_db):
    """组内排序：confidence 高优先、已忽视沉底、file_size DESC、id ASC。"""
    grouped_db.add(_scan("scan_completed"))
    grouped_db.add_all(
        [
            _detail("scan_completed", "/data/g/low1.bin", 100, confidence="low"),
            _detail("scan_completed", "/data/g/high1.bin", 200, confidence="high"),
            _detail("scan_completed", "/data/g/high2.bin", 300, confidence="high"),
        ]
    )
    # high2 忽视 → 沉底
    grouped_db.add(_candidate("/data/g/high2.bin", ignored=True))
    await grouped_db.commit()

    result = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=20)
    folder = next(r for r in result["list"] if r.get("_is_folder"))
    assert folder["children"] == []
    children = await OrphanFileService(grouped_db).get_orphan_folder_children("/data/g", page=1, page_size=20)
    child_paths = [c["file_path"] for c in children["list"]]
    # 组内排序键：confidence_rank(高=0,低=1) → ignored_rank(非忽视=0,已忽视=1) → file_size DESC → id ASC
    # high1: confidence=high(0), ignored=0, size=200
    # high2: confidence=high(0), ignored=1(已忽视), size=300
    # low1:  confidence=low(1), size=100
    # 第一键 confidence_rank：high1/high2(0) 在 low1(1) 之前
    # 同 confidence 下按 ignored_rank：high1(0) 在 high2(1) 之前
    # 故顺序：high1, high2, low1
    assert child_paths == ["/data/g/high1.bin", "/data/g/high2.bin", "/data/g/low1.bin"]
    assert folder["all_ignored"] is False  # 含非忽视项，all_ignored=False
    assert folder["has_low_confidence"] is True


# ==================== 筛选叠加 ====================


async def test_grouping_with_downloader_and_path_filter(grouped_db):
    """筛选条件与分组共存：downloader_id + path_like 仅影响组内成员。"""
    grouped_db.add(_scan("scan_completed"))
    grouped_db.add_all(
        [
            _detail("scan_completed", "/data/m/dl1_a.bin", 100, downloader_id="dl_001"),
            _detail("scan_completed", "/data/m/dl1_b.bin", 200, downloader_id="dl_001"),
            _detail("scan_completed", "/data/m/dl2_a.bin", 300, downloader_id="dl_002"),
        ]
    )
    await grouped_db.commit()

    # 仅 dl_001 + 路径含 movie 不命中（路径是 /data/m/）→ 用 path_like="dl1"
    result = await OrphanFileService(grouped_db).get_orphan_list_grouped(
        page=1, page_size=20, downloader_id="dl_001", path_like="dl1"
    )
    lst = result["list"]
    # dl_001 的 2 个文件同属 /data/m → 1 个文件夹组
    assert len(lst) == 1
    folder = lst[0]
    assert folder["child_count"] == 2
    assert all(c["downloader_id"] == "dl_001" for c in folder["children"])


# ==================== scan_context 统计口径 ====================


async def test_grouping_scan_context_remains_file_level(grouped_db):
    """折叠模式 scan_context 统计仍是文件级（与扁平模式一致）。"""
    grouped_db.add(_scan("scan_completed"))
    grouped_db.add_all(
        [
            _detail("scan_completed", "/data/m/a.bin", 100),
            _detail("scan_completed", "/data/m/b.bin", 200),
            _detail("scan_completed", "/data/alone.bin", 50),
        ]
    )
    await grouped_db.commit()

    grouped_result = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=20)
    flat_result = await OrphanFileService(grouped_db).get_orphan_list(page=1, page_size=20)

    # scan_context 的 remaining/ignored 统计口径一致（文件级）
    assert grouped_result["scan_context"]["remaining_count"] == flat_result["scan_context"]["remaining_count"]
    assert grouped_result["scan_context"]["remaining_size"] == flat_result["scan_context"]["remaining_size"]
    assert grouped_result["scan_context"]["ignored_count"] == flat_result["scan_context"]["ignored_count"]
    # 但 total 不同：折叠=组数(2)，扁平=文件数(3)
    assert grouped_result["total"] == 2
    assert flat_result["total"] == 3


async def test_grouping_empty_when_no_scan(grouped_db):
    """无扫描记录时返回空列表 + 空 scan_context。"""
    result = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=20)
    assert result["total"] == 0
    assert result["list"] == []
    assert result["scan_context"]["display_scan"] is None


# ==================== 聚合状态字段 ====================


async def test_grouping_aggregate_all_ignored(grouped_db):
    """组内全部已忽视 → all_ignored=True。"""
    grouped_db.add(_scan("scan_completed"))
    grouped_db.add_all(
        [
            _detail("scan_completed", "/data/ig/a.bin", 100),
            _detail("scan_completed", "/data/ig/b.bin", 200),
        ]
    )
    grouped_db.add_all(
        [
            _candidate("/data/ig/a.bin", ignored=True),
            _candidate("/data/ig/b.bin", ignored=True),
        ]
    )
    await grouped_db.commit()

    result = await OrphanFileService(grouped_db).get_orphan_list_grouped(page=1, page_size=20, status="ignored")
    folder = next(r for r in result["list"] if r.get("_is_folder"))
    assert folder["all_ignored"] is True
    assert folder["all_pending"] is False
