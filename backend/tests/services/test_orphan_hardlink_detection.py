# -*- coding: utf-8 -*-
"""
I 组：隔离区删除的硬链接副本检测与处理。

背景：孤儿被隔离后，原文件可能与种子文件或媒体库副本共享同一 inode（硬链接）。
此时删除隔离副本不会释放磁盘空间。本组覆盖：
1. find_hardlink_copies：在扫描根下枚举同 inode 的其它路径，排除自身与无关项；
2. 立即删除（mode=purge_now）：nlink>1 时照常删除 + 返回副本诊断（路径 + is_seed）；
3. 到期删除（mode=purge_expired）：nlink>1 时跳过不删，候选保持 quarantined；
4. 平台兜底：inode 不可靠时立即删除照删（缺诊断），到期删除保守跳过。
"""

import json
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.models.orphan_hardlink_copy import OrphanHardlinkCopyResult
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import ManifestSnapshot, normalize_path
from app.services.orphan_quarantine import (
    find_hardlink_copies,
    find_hardlink_paths,
    get_hardlink_copy_count,
)
from app.utils.datetime_utils import serialize_utc_datetime

pytestmark = pytest.mark.asyncio


def _empty_manifest(root, downloader_id="dl_001"):
    return ManifestSnapshot(
        expected_paths=set(),
        scan_roots=[(str(root), frozenset({downloader_id}))],
        downloader_ids={downloader_id},
    )


def _make_quarantined(async_orphan_db, tmp_path, filename, *, downloader_id="dl_001"):
    """构造已隔离候选 + 隔离区实体文件。返回 (candidate, canonical_path, quarantine_path)。"""
    canonical = str(tmp_path / filename)
    quarantine_root = str(tmp_path / ".btdeck_quarantine" / "scan_test")
    os.makedirs(quarantine_root, exist_ok=True)
    quarantine_path = os.path.join(quarantine_root, "abcdef1234567890", filename)
    os.makedirs(os.path.dirname(quarantine_path), exist_ok=True)
    with open(quarantine_path, "wb") as f:
        f.write(b"x" * 100)
    q_stat = os.stat(quarantine_path)

    old_time = datetime.utcnow() - timedelta(days=10)
    candidate = OrphanCurrentCandidate(
        canonical_path=canonical,
        downloader_id=downloader_id,
        first_seen_at=old_time,
        last_seen_at=datetime.utcnow(),
        status="quarantined",
        file_size=100,
        mtime_ns=q_stat.st_mtime_ns,
        device_id=str(q_stat.st_dev),
        inode=str(q_stat.st_ino),
        quarantine_path=quarantine_path,
        quarantine_root=quarantine_root,
        quarantined_at=old_time,
        purge_after=datetime.utcnow() + timedelta(days=3),
    )
    async_orphan_db.add(candidate)
    return candidate, canonical, quarantine_path


def _lease():
    lease = MagicMock()
    lease.assert_owned = AsyncMock()
    return lease


# ==================== find_hardlink_copies 单测 ====================


class TestFindHardlinkCopies:
    """硬链接副本枚举工具。"""

    def test_finds_other_hardlink_copies_excluding_self(self, tmp_path):
        """同 inode 的其它路径必须全部返回，排除被删文件自身与无关文件。"""
        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)
        (scan_root / "sorted").mkdir(parents=True)

        target = scan_root / "media" / "movie.mkv"
        target.write_bytes(b"payload")
        # 创建两个硬链接副本
        copy1 = scan_root / "sorted" / "movie-copy.mkv"
        os.link(target, copy1)
        copy2 = scan_root / "media" / "movie-dup.mkv"
        os.link(target, copy2)
        # 无关文件（不同 inode）
        (scan_root / "unrelated.mkv").write_bytes(b"other")

        st = os.stat(target)
        copies = find_hardlink_copies(
            target_inode=(st.st_dev, st.st_ino),
            scan_roots=[str(scan_root)],
            exclude_path=str(target),
        )

        found = {os.path.abspath(p) for p in copies}
        assert found == {
            os.path.abspath(str(copy1)),
            os.path.abspath(str(copy2)),
        }, f"应返回两个硬链接副本，实际: {found}"

    def test_no_copies_returns_empty(self, tmp_path):
        """nlink=1（唯一链接）→ 无副本。"""
        scan_root = tmp_path / "scan_root"
        scan_root.mkdir()
        only = scan_root / "only.mkv"
        only.write_bytes(b"x")
        st = os.stat(only)
        copies = find_hardlink_copies(
            target_inode=(st.st_dev, st.st_ino),
            scan_roots=[str(scan_root)],
            exclude_path=str(only),
        )
        assert copies == []

    def test_ignores_paths_outside_scan_roots(self, tmp_path):
        """扫描根范围之外的硬链接不返回（按候选所属 downloader scan_roots 限定）。"""
        scan_root = tmp_path / "scan_root"
        outside_root = tmp_path / "outside"
        scan_root.mkdir(parents=True)
        outside_root.mkdir(parents=True)

        target = scan_root / "in.mkv"
        target.write_bytes(b"payload")
        outside_copy = outside_root / "out.mkv"
        os.link(target, outside_copy)

        st = os.stat(target)
        copies = find_hardlink_copies(
            target_inode=(st.st_dev, st.st_ino),
            scan_roots=[str(scan_root)],
            exclude_path=str(target),
        )
        assert copies == [], "扫描根外的硬链接不应返回"

    def test_bulk_lookup_returns_each_inode_once_across_overlapping_roots(self, tmp_path):
        """批量定位一次处理多个 inode，重叠扫描根不得产生重复路径。"""
        scan_root = tmp_path / "scan_root"
        nested_root = scan_root / "nested"
        nested_root.mkdir(parents=True)

        first = scan_root / "first.mkv"
        first.write_bytes(b"first")
        first_copy = nested_root / "first-copy.mkv"
        os.link(first, first_copy)

        second = nested_root / "second.mkv"
        second.write_bytes(b"second")
        second_copy = scan_root / "second-copy.mkv"
        os.link(second, second_copy)

        first_stat = os.stat(first)
        second_stat = os.stat(second)
        first_inode = (first_stat.st_dev, first_stat.st_ino)
        second_inode = (second_stat.st_dev, second_stat.st_ino)

        found = find_hardlink_paths(
            target_inodes={first_inode, second_inode},
            scan_roots=[str(scan_root), str(nested_root)],
        )

        assert set(found[first_inode]) == {
            os.path.realpath(first),
            os.path.realpath(first_copy),
        }
        assert set(found[second_inode]) == {
            os.path.realpath(second),
            os.path.realpath(second_copy),
        }


class TestHardlinkCopyCount:
    """孤儿列表展示所需的硬链接副本数量。"""

    def test_counts_other_directory_entries_excluding_self(self, tmp_path):
        """副本数等于 st_nlink - 1；唯一链接明确返回 0。"""
        target = tmp_path / "target.mkv"
        target.write_bytes(b"payload")

        assert get_hardlink_copy_count(str(target)) == 0

        os.link(target, tmp_path / "copy-1.mkv")
        assert get_hardlink_copy_count(str(target)) == 1

        os.link(target, tmp_path / "copy-2.mkv")
        assert get_hardlink_copy_count(str(target)) == 2

    async def test_list_and_folder_rows_include_copy_count(self, async_orphan_db, monkeypatch):
        """扁平行/子文件行直出明细快照列；列表链路不再触发文件系统 stat。"""
        linked = "D:/data/linked.mkv"
        solo = "D:/data/solo.mkv"
        missing = "D:/missing/gone.mkv"

        # 性能契约：列表链路不得触碰文件系统（副本数来自扫描时落库的快照列）
        def _no_stat(*args, **kwargs):  # pragma: no cover - 触发即失败
            raise AssertionError("列表链路不应执行实时 stat")

        monkeypatch.setattr(
            "app.services.orphan_file_service.get_hardlink_copy_count",
            _no_stat,
        )

        scan = OrphanScanResult(
            scan_id="scan_hardlink_count",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="completed",
        )
        scan.total_paths_scanned = 1
        scan.total_files_scanned = 3
        scan.total_orphans = 3
        scan.total_orphan_size = 17
        async_orphan_db.add(scan)
        async_orphan_db.add_all(
            [
                OrphanFile(
                    scan_id=scan.scan_id,
                    file_path=linked,
                    file_size=6,
                    downloader_id="dl_001",
                    canonical_path=normalize_path(linked),
                    hardlink_copy_count=1,
                ),
                OrphanFile(
                    scan_id=scan.scan_id,
                    file_path=solo,
                    file_size=4,
                    downloader_id="dl_001",
                    canonical_path=normalize_path(solo),
                    hardlink_copy_count=0,
                ),
                OrphanFile(
                    scan_id=scan.scan_id,
                    file_path=missing,
                    file_size=7,
                    downloader_id="dl_001",
                    canonical_path=normalize_path(missing),
                    hardlink_copy_count=None,
                ),
            ]
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        flat_result = await service.get_orphan_list(page=1, page_size=20)
        by_path = {item["file_path"]: item for item in flat_result["list"]}
        assert by_path[linked]["hardlink_copy_count"] == 1
        assert by_path[solo]["hardlink_copy_count"] == 0
        assert by_path[missing]["hardlink_copy_count"] is None

        grouped_result = await service.get_orphan_list_grouped(page=1, page_size=20)
        folder = next(item for item in grouped_result["list"] if item.get("_is_folder"))
        assert folder["hardlink_copy_count"] is None
        assert folder["children"] == []

        children_result = await service.get_orphan_folder_children(
            folder["folder_path"],
            page=1,
            page_size=20,
        )
        child_counts = {item["file_path"]: item["hardlink_copy_count"] for item in children_result["list"]}
        assert child_counts == {linked: 1, solo: 0}


class TestHardlinkCopyLocations:
    """点击副本数量时只读定时预扫描落库结果；接口层不做任何目录遍历。"""

    def test_service_module_no_longer_imports_traversal(self):
        """性能契约：交互链路（服务与端点）不得引入整体遍历函数（遍历只在定时任务内）。"""
        import app.api.endpoints.orphan_files as orphan_endpoint_module
        import app.services.orphan_file_service as orphan_file_service_module

        assert not hasattr(orphan_file_service_module, "collect_runtime_accessible_roots")
        assert not hasattr(orphan_file_service_module, "find_hardlink_paths")
        assert not hasattr(orphan_endpoint_module, "collect_runtime_accessible_roots")
        assert not hasattr(orphan_endpoint_module, "find_hardlink_paths")

    async def test_reads_stored_results_with_live_count_and_pending_scan(self, async_orphan_db, tmp_path):
        """已预扫描的身份返回过滤自身后的路径与扫描时间；未覆盖的标记待预扫描。"""
        source_root = tmp_path / "downloads"
        other_root = tmp_path / "library"
        source_root.mkdir()
        other_root.mkdir()

        linked = source_root / "linked.mkv"
        linked.write_bytes(b"linked")
        stored_copy = other_root / "linked-copy.mkv"
        os.link(linked, stored_copy)
        pending = source_root / "pending.mkv"
        pending.write_bytes(b"pending")
        os.link(pending, other_root / "pending-copy.mkv")
        solo = source_root / "solo.mkv"
        solo.write_bytes(b"solo")
        missing = source_root / "gone.mkv"

        scan = OrphanScanResult(
            scan_id="scan_hardlink_locations",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="completed",
        )
        async_orphan_db.add(scan)
        linked_detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(linked),
            file_size=6,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(linked)),
        )
        pending_detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(pending),
            file_size=7,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(pending)),
        )
        solo_detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(solo),
            file_size=4,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(solo)),
        )
        missing_detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(missing),
            file_size=4,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(missing)),
        )
        linked_stat = os.stat(linked)
        scanned_at = datetime.utcnow()
        async_orphan_db.add_all(
            [
                linked_detail,
                pending_detail,
                solo_detail,
                missing_detail,
                # 预扫描落库结果：存储层保留源路径本身，展示端按请求文件过滤
                OrphanHardlinkCopyResult(
                    device_id=str(int(linked_stat.st_dev)),
                    inode_id=int(linked_stat.st_ino),
                    copy_count=1,
                    found_count=2,
                    copies_json=json.dumps([os.path.realpath(str(linked)), os.path.realpath(str(stored_copy))]),
                    scanned_at=scanned_at,
                ),
            ]
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.get_hardlink_copy_locations(
            [linked_detail.id, pending_detail.id, solo_detail.id, missing_detail.id, 999999]
        )

        assert result["requested_count"] == 5
        assert result["resolved_count"] == 4
        assert result["missing_orphan_ids"] == [999999]
        assert result["total_copy_count"] == 2
        assert result["total_found_count"] == 1
        assert result["total_unlocated_count"] == 1
        assert result["unknown_count"] == 1
        assert result["scanned_count"] == 1
        assert result["pending_scan_count"] == 1
        assert result["search_error"] is None

        by_id = {item["orphan_id"]: item for item in result["items"]}
        linked_item = by_id[linked_detail.id]
        assert linked_item["copy_count"] == 1
        assert linked_item["found_count"] == 1
        assert linked_item["unlocated_count"] == 0
        assert linked_item["copies"] == [os.path.realpath(str(stored_copy))]
        assert linked_item["pending_scan"] is False
        assert linked_item["result_truncated"] is False
        assert linked_item["scanned_at"] == serialize_utc_datetime(scanned_at)
        assert linked_item["error"] is None

        pending_item = by_id[pending_detail.id]
        assert pending_item["copy_count"] == 1
        assert pending_item["copies"] == []
        assert pending_item["pending_scan"] is True
        assert pending_item["scanned_at"] is None
        assert pending_item["unlocated_count"] == 1

        assert by_id[solo_detail.id]["copy_count"] == 0
        assert by_id[solo_detail.id]["copies"] == []
        assert by_id[solo_detail.id]["pending_scan"] is False
        assert by_id[missing_detail.id]["copy_count"] is None
        assert by_id[missing_detail.id]["unlocated_count"] is None
        assert by_id[missing_detail.id]["error"] == "源文件不可访问，无法重新核对副本位置"

    async def test_result_read_failure_keeps_live_count_as_unlocated(self, async_orphan_db, tmp_path):
        """结果表读取失败时不伪造路径，实时副本总数全部转为未定位并返回错误。"""
        source_root = tmp_path / "downloads"
        source_root.mkdir()
        source = source_root / "linked.mkv"
        source.write_bytes(b"linked")
        os.link(source, source_root / "linked-copy.mkv")

        scan = OrphanScanResult(
            scan_id="scan_hardlink_location_failure",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="completed",
        )
        detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(source),
            file_size=6,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(source)),
        )
        async_orphan_db.add_all([scan, detail])
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            OrphanFileService,
            "_load_hardlink_copy_results",
            side_effect=RuntimeError("db offline"),
        ):
            result = await service.get_hardlink_copy_locations([detail.id])

        expected_error = "副本定位结果读取失败，请稍后重试"
        assert result["search_error"] == expected_error
        assert result["total_copy_count"] == 1
        assert result["total_found_count"] == 0
        assert result["total_unlocated_count"] == 1
        assert result["items"][0]["copies"] == []
        assert result["items"][0]["unlocated_count"] == 1
        assert result["items"][0]["error"] == expected_error

    async def test_zero_copy_skips_result_lookup(self, async_orphan_db, tmp_path):
        """列表变更为零副本时不查结果表，直接返回实时 0。"""
        source = tmp_path / "solo.mkv"
        source.write_bytes(b"solo")
        scan = OrphanScanResult(
            scan_id="scan_zero_copy_location",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="completed",
        )
        detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(source),
            file_size=4,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(source)),
        )
        async_orphan_db.add_all([scan, detail])
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_load_hardlink_copy_results") as load_results:
            result = await service.get_hardlink_copy_locations([detail.id])

        load_results.assert_not_called()
        assert result["total_copy_count"] == 0
        assert result["total_found_count"] == 0
        assert result["pending_scan_count"] == 0
        assert result["items"][0]["copies"] == []


# ==================== 立即删除 mode=purge_now：副本诊断 ====================


class TestPurgeNowHardlinkDiagnostic:
    """立即删除照常删除，但 nlink>1 时返回副本路径与种子标识。"""

    async def test_purge_now_with_copies_returns_diagnostic(self, async_orphan_db, tmp_path):
        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)

        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "linked.mkv")
        # 在扫描根内建一个硬链接副本（模拟媒体库整理），模拟删除时 nlink=2
        seed_copy = scan_root / "media" / "linked.mkv"
        os.link(quarantine_path, seed_copy)
        await async_orphan_db.commit()

        # manifest：seed_copy 路径在 expected_paths 中 → is_seed=True
        manifest = ManifestSnapshot(
            expected_paths={normalize_path(str(seed_copy))},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["purged_count"] == 1, f"照常删除: {result}"
        notes = result.get("hardlink_notes", [])
        assert len(notes) == 1, f"应返回1条副本诊断: {notes}"
        note = notes[0]
        assert note["canonical_path"] == canonical
        assert note["remaining_count"] == 1
        copies = note["copies"]
        assert len(copies) == 1
        assert copies[0]["is_seed"] is True
        assert os.path.exists(str(seed_copy)), "副本不应被删"
        assert not os.path.exists(quarantine_path), "隔离副本应已删"

    async def test_purge_now_without_copies_no_diagnostic(self, async_orphan_db, tmp_path):
        """nlink=1 时无副本诊断字段。"""
        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "solo.mkv")
        await async_orphan_db.commit()

        manifest = _empty_manifest(tmp_path)
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["purged_count"] == 1
        assert result.get("hardlink_notes", []) == [], "无副本不应产生诊断"


# ==================== 到期删除 mode=purge_expired：副本跳过 ====================


class TestPurgeExpiredHardlinkSkip:
    """到期删除遇硬链接副本必须跳过（不删），候选保持 quarantined。"""

    async def test_purge_expired_skips_file_with_copies(self, async_orphan_db, tmp_path):
        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)

        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "expire-linked.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)  # 已到期
        seed_copy = scan_root / "media" / "expire-linked.mkv"
        os.link(quarantine_path, seed_copy)
        await async_orphan_db.commit()

        manifest = ManifestSnapshot(
            expected_paths={normalize_path(str(seed_copy))},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_expired_quarantine(store=MagicMock())

        # 未删，未误报为成功
        assert result.get("purged_count", 0) == 0, "存在副本的到期删除应跳过，不得物理删除"
        assert os.path.exists(quarantine_path), "副本存在时隔离文件必须保留"
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "quarantined", "候选应保持 quarantined，等待用户决策"
        # 跳过信息应在 skipped_hardlink 中可查
        skipped = result.get("skipped_hardlink", [])
        assert len(skipped) == 1, f"应记录1条跳过详情: {skipped}"
        skipped_reasons = " ".join(str(item.get("reason", "")) for item in skipped)
        assert "硬链接" in skipped_reasons or "副本" in skipped_reasons, f"跳过原因应说明硬链接副本: {result}"
        # 延后逻辑：purge_after 应被延后到未来（打破每日重试循环）
        await async_orphan_db.refresh(candidate)
        assert candidate.purge_after is not None, "跳过后 purge_after 应被延后"
        assert (
            candidate.purge_after > datetime.utcnow()
        ), f"跳过后 purge_after 应延后到未来，实际: {candidate.purge_after}"

    async def test_purge_expired_deletes_when_no_copies(self, async_orphan_db, tmp_path):
        """无副本的到期文件正常删除（回归保护）。"""
        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "expire-solo.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        await async_orphan_db.commit()

        manifest = _empty_manifest(tmp_path)
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_expired_quarantine(store=MagicMock())

        assert result.get("purged_count", 0) == 1, "无副本应正常删除"
        assert not os.path.exists(quarantine_path)


# ==================== 到期跳过：purge_after 延后（打破每日重试循环） ====================


class TestPurgeExpiredDelayRetry:
    """到期删除遇副本跳过后，purge_after 延后 N 天；副本清除后仍会正常删除。"""

    async def test_purge_after_delayed_by_configured_days(self, async_orphan_db, tmp_path):
        """跳过时按 ORPHAN_HARDLINK_PURGE_DELAY_DAYS 延后（默认 7 天）。"""
        from app.core.config import settings

        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)

        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "delay-default.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)  # 已到期
        seed_copy = scan_root / "media" / "delay-default.mkv"
        os.link(quarantine_path, seed_copy)
        await async_orphan_db.commit()

        delay_days = settings.ORPHAN_HARDLINK_PURGE_DELAY_DAYS
        manifest = ManifestSnapshot(
            expected_paths={normalize_path(str(seed_copy))},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_expired_quarantine(store=MagicMock())

        assert result.get("purged_count", 0) == 0
        await async_orphan_db.refresh(candidate)
        # 延后窗口：now + delay_days 附近（允许几秒误差）
        expected_low = datetime.utcnow() + timedelta(days=delay_days - 0.01)
        expected_high = datetime.utcnow() + timedelta(days=delay_days + 0.01)
        assert candidate.purge_after is not None
        assert (
            expected_low <= candidate.purge_after <= expected_high
        ), f"purge_after 应按 {delay_days} 天延后，实际: {candidate.purge_after}"
        assert candidate.status == "quarantined"
        # 延后计数递增：1 次跳过 → purge_delay_count=1
        assert candidate.purge_delay_count == 1, f"延后计数应递增为 1，实际: {candidate.purge_delay_count}"

    async def test_purge_after_delay_custom_days(self, async_orphan_db, tmp_path, monkeypatch):
        """自定义 ORPHAN_HARDLINK_PURGE_DELAY_DAYS 时按自定义天数延后。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "ORPHAN_HARDLINK_PURGE_DELAY_DAYS", 3)

        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)

        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "delay-custom.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        seed_copy = scan_root / "media" / "delay-custom.mkv"
        os.link(quarantine_path, seed_copy)
        await async_orphan_db.commit()

        manifest = ManifestSnapshot(
            expected_paths={normalize_path(str(seed_copy))},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_expired_quarantine(store=MagicMock())

        assert result.get("purged_count", 0) == 0
        await async_orphan_db.refresh(candidate)
        expected_low = datetime.utcnow() + timedelta(days=2.99)
        expected_high = datetime.utcnow() + timedelta(days=3.01)
        assert candidate.purge_after is not None
        assert expected_low <= candidate.purge_after <= expected_high, f"自定义延后 3 天，实际: {candidate.purge_after}"

    async def test_delayed_candidate_not_selected_within_window(self, async_orphan_db, tmp_path):
        """延后后，下一次到期任务（延后窗口内）不再选中该候选（打破每日重试）。"""
        from sqlalchemy import select

        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)

        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "delay-window.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)  # 已到期
        seed_copy = scan_root / "media" / "delay-window.mkv"
        os.link(quarantine_path, seed_copy)
        await async_orphan_db.commit()

        manifest = ManifestSnapshot(
            expected_paths={normalize_path(str(seed_copy))},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            await service.purge_expired_quarantine(store=MagicMock())

        # 模拟第二天重跑：purge_after 已延后到未来，查询不应再选中该候选
        result = await async_orphan_db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.canonical_path == canonical,
                OrphanCurrentCandidate.status == "quarantined",
                OrphanCurrentCandidate.purge_after < datetime.utcnow(),
            )
        )
        assert result.scalars().all() == [], "延后窗口内不应再选中该候选（purge_after 已在未来）"

    async def test_purge_after_delayed_then_deleted_after_copy_removed(self, async_orphan_db, tmp_path):
        """副本被清除、延后到期后，候选仍会正常删除（延后不永久阻塞删除）。"""
        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)

        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "delay-clear.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        seed_copy = scan_root / "media" / "delay-clear.mkv"
        os.link(quarantine_path, seed_copy)
        await async_orphan_db.commit()

        manifest = ManifestSnapshot(
            expected_paths={normalize_path(str(seed_copy))},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            await service.purge_expired_quarantine(store=MagicMock())

        # 副本被清除 + 延后到期 → 再次到期任务应正常删除
        os.remove(str(seed_copy))
        await async_orphan_db.refresh(candidate)
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        await async_orphan_db.commit()

        # 用无副本 manifest 重跑到期删除
        manifest_no_copy = _empty_manifest(tmp_path)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest_no_copy):
            result = await service.purge_expired_quarantine(store=MagicMock())

        assert result.get("purged_count", 0) == 1, f"副本清除 + 延后到期后应正常删除: {result}"
        assert not os.path.exists(quarantine_path), "隔离文件应已物理删除"

    async def test_purge_delay_count_accumulates_across_runs(self, async_orphan_db, tmp_path):
        """连续两次跳过 → purge_delay_count 累加到 2（SQL 表达式原子递增）。"""
        scan_root = tmp_path / "scan_root"
        (scan_root / "media").mkdir(parents=True)

        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "delay-accumulate.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        seed_copy = scan_root / "media" / "delay-accumulate.mkv"
        os.link(quarantine_path, seed_copy)
        await async_orphan_db.commit()

        manifest = ManifestSnapshot(
            expected_paths={normalize_path(str(seed_copy))},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        service = OrphanFileService(async_orphan_db)

        # 第一次跳过 → count=1
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            await service.purge_expired_quarantine(store=MagicMock())
        await async_orphan_db.refresh(candidate)
        assert candidate.purge_delay_count == 1, f"第一次跳过 count 应为 1: {candidate.purge_delay_count}"

        # 模拟次日再次到期 → 第二次跳过 → count=2（SQL 原子递增，非对象 read-modify-write）
        await async_orphan_db.refresh(candidate)
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        await async_orphan_db.commit()
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            await service.purge_expired_quarantine(store=MagicMock())
        await async_orphan_db.refresh(candidate)
        assert candidate.purge_delay_count == 2, f"第二次跳过 count 应为 2: {candidate.purge_delay_count}"
        assert candidate.status == "quarantined"

    async def test_purge_delay_count_unchanged_without_copies(self, async_orphan_db, tmp_path):
        """无副本正常删除时 count 不变（仍为 0）。"""
        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "delay-no-copy.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        await async_orphan_db.commit()

        manifest = _empty_manifest(tmp_path)
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_expired_quarantine(store=MagicMock())

        assert result.get("purged_count", 0) == 1, "无副本应正常删除"
        await async_orphan_db.refresh(candidate)
        assert candidate.purge_delay_count == 0, f"无副本删除 count 应保持 0: {candidate.purge_delay_count}"


# ==================== 硬链接副本删除（弹窗交互） ====================


class _DeleteFixture:
    """delete_hardlink_copies 测试数据快照。"""

    scan_seq = 0

    def __init__(self, detail, source, copies, stored):
        self.detail = detail
        self.source = source
        self.copies = copies
        self.stored = stored


async def _make_delete_fixture(
    async_orphan_db,
    tmp_path,
    *,
    copy_names=("copy-a.mkv",),
    candidate_status="candidate",
    operation_state="stable",
    with_prescan=True,
):
    """构造候选态孤儿 + 真实硬链接副本 + 预扫描结果行。

    copies_json 按存储层语义包含源路径本身（展示端按请求文件过滤）。
    """
    source_dir = tmp_path / "downloads"
    copy_dir = tmp_path / "library"
    source_dir.mkdir(parents=True, exist_ok=True)
    copy_dir.mkdir(parents=True, exist_ok=True)

    source = source_dir / "source.mkv"
    source.write_bytes(b"payload")
    copies = []
    for name in copy_names:
        copy_path = copy_dir / name
        os.link(source, copy_path)
        copies.append(copy_path)

    _DeleteFixture.scan_seq += 1
    scan = OrphanScanResult(
        scan_id=f"scan_hardlink_delete_{_DeleteFixture.scan_seq}",
        scan_time=datetime.utcnow(),
        scan_type="manual",
        status="completed",
    )
    source_stat = os.stat(source)
    detail = OrphanFile(
        scan_id=scan.scan_id,
        file_path=str(source),
        file_size=7,
        downloader_id="dl_001",
        canonical_path=normalize_path(str(source)),
    )
    candidate = OrphanCurrentCandidate(
        canonical_path=normalize_path(str(source)),
        downloader_id="dl_001",
        first_seen_at=datetime.utcnow() - timedelta(days=1),
        last_seen_at=datetime.utcnow(),
        status=candidate_status,
        operation_state=operation_state,
        file_size=7,
        mtime_ns=source_stat.st_mtime_ns,
        device_id=str(source_stat.st_dev),
        inode=str(source_stat.st_ino),
    )
    async_orphan_db.add_all([scan, detail, candidate])

    stored = None
    if with_prescan:
        stored = OrphanHardlinkCopyResult(
            device_id=str(source_stat.st_dev),
            inode_id=int(source_stat.st_ino),
            copy_count=len(copies),
            found_count=len(copies) + 1,
            copies_json=json.dumps([os.path.realpath(str(source))] + [os.path.realpath(str(c)) for c in copies]),
            truncated=0,
            scan_note=None,
            scanned_at=datetime.utcnow(),
        )
        async_orphan_db.add(stored)
    await async_orphan_db.commit()
    return _DeleteFixture(detail, source, copies, stored)


def _empty_whitelist(monkeypatch, dirs=None):
    """隔离真实 DB：种子目录白名单替换为受控集合。"""
    from app.services.orphan_manifest import DirectoryWhitelist

    controlled = DirectoryWhitelist(dirs=set(dirs or []))
    monkeypatch.setattr(
        "app.services.orphan_file_service.collect_torrent_directory_whitelist",
        lambda session_factory, downloader_ids=None: controlled,
    )
    return controlled


class TestHardlinkCopyDelete:
    """弹窗删除副本：逐路径 fail-closed，tombstone 三段式，共享 inode/种子目录拒绝。"""

    async def test_delete_refreshes_sibling_details_sharing_inode(self, async_orphan_db, tmp_path, monkeypatch):
        """删除副本后共享同一 inode 的全部孤儿明细快照列同步刷新（防兄弟行残留偏大）。"""
        from sqlalchemy import select

        fixture = await _make_delete_fixture(async_orphan_db, tmp_path, copy_names=("a.mkv", "b.mkv"))
        _empty_whitelist(monkeypatch)

        source_stat = os.stat(fixture.source)
        sibling = tmp_path / "downloads" / "sibling.mkv"
        os.link(fixture.source, sibling)
        sibling_detail = OrphanFile(
            scan_id=fixture.detail.scan_id,
            file_path=str(sibling),
            file_size=7,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(sibling)),
            hardlink_copy_count=3,
        )
        sibling_candidate = OrphanCurrentCandidate(
            canonical_path=normalize_path(str(sibling)),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=1),
            last_seen_at=datetime.utcnow(),
            status="candidate",
            operation_state="stable",
            file_size=7,
            device_id=str(source_stat.st_dev),
            inode=str(source_stat.st_ino),
        )
        fixture.detail.hardlink_copy_count = 3
        async_orphan_db.add_all([sibling_detail, sibling_candidate])
        await async_orphan_db.flush()
        sibling_candidate.current_detail_id = sibling_detail.id
        source_candidate = (
            await async_orphan_db.execute(
                select(OrphanCurrentCandidate).where(
                    OrphanCurrentCandidate.canonical_path == normalize_path(str(fixture.source))
                )
            )
        ).scalar_one()
        source_candidate.current_detail_id = fixture.detail.id
        await async_orphan_db.commit()

        copy_a = os.path.realpath(str(fixture.copies[0]))
        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_a],
            operator="tester",
            audit_service=AsyncMock(),
            _lease_acquired=True,
            _lease_handle=_lease(),
        )
        assert result["success_count"] == 1

        # 删除前 4 个链接（源 + a + b + sibling），删 a 后剩 3 个 → 副本数 2；
        # 两个明细（含共享 inode 的兄弟）都被刷成同一个权威值。
        await async_orphan_db.refresh(fixture.detail)
        await async_orphan_db.refresh(sibling_detail)
        assert fixture.detail.hardlink_copy_count == 2
        assert sibling_detail.hardlink_copy_count == 2

    async def test_deletes_copy_updates_result_row_and_audits(self, async_orphan_db, tmp_path, monkeypatch):
        """happy path：副本目录项被删、源文件与数据完好、结果行/审计同步更新。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path, copy_names=("a.mkv", "b.mkv"))
        _empty_whitelist(monkeypatch)
        copy_a = os.path.realpath(str(fixture.copies[0]))
        source_real = os.path.realpath(str(fixture.source))
        audit_service = AsyncMock()

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_a],
            operator="tester",
            audit_service=audit_service,
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 1
        assert result["failed_count"] == 0
        assert result["copy_count"] == 1  # 2 副本删 1 个
        assert not os.path.exists(copy_a)
        assert os.path.exists(source_real)
        with open(source_real, "rb") as f:
            assert f.read() == b"payload"
        assert os.stat(source_real).st_nlink == 2  # 源 + 剩余副本

        stored = fixture.stored
        await async_orphan_db.refresh(stored)
        assert json.loads(stored.copies_json) == [source_real, os.path.realpath(str(fixture.copies[1]))]
        assert stored.found_count == 2
        assert stored.copy_count == 1

        audit_service.log_operation.assert_awaited_once()
        kwargs = audit_service.log_operation.await_args.kwargs
        assert kwargs["operation_type"] == "orphan_hardlink_copy_delete"
        assert kwargs["operation_detail"]["deleted_paths"] == [copy_a]

    async def test_rejects_shared_inode_candidate_paths(self, async_orphan_db, tmp_path, monkeypatch):
        """共享同一 inode 的其它孤儿源路径不可作为副本删除（防删孤儿 B 本身）。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        _empty_whitelist(monkeypatch)
        copy_real = os.path.realpath(str(fixture.copies[0]))
        # 孤儿 B：同身份候选，canonical_path 指向弹窗中的"副本"路径
        source_stat = os.stat(fixture.source)
        async_orphan_db.add(
            OrphanCurrentCandidate(
                canonical_path=normalize_path(copy_real),
                downloader_id="dl_002",
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                status="candidate",
                operation_state="stable",
                file_size=7,
                mtime_ns=source_stat.st_mtime_ns,
                device_id=str(source_stat.st_dev),
                inode=str(source_stat.st_ino),
            )
        )
        await async_orphan_db.commit()

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_real],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        assert "孤儿文件" in result["failed_list"][0]["reason"]
        assert os.path.exists(copy_real), "同 inode 孤儿源路径必须原样保留"

    async def test_rejects_paths_not_in_stored_results(self, async_orphan_db, tmp_path, monkeypatch):
        """请求路径必须与返回前端的 copies 原始字符串一致（防任意路径注入）。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        _empty_whitelist(monkeypatch)
        unrelated = tmp_path / "unrelated.mkv"
        unrelated.write_bytes(b"unrelated")

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [str(unrelated)],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        assert "不一致" in result["failed_list"][0]["reason"]
        assert os.path.exists(unrelated)
        assert os.path.exists(str(fixture.copies[0])), "无关路径被拒不得影响真实副本"

    async def test_rejects_seed_directory_copies(self, async_orphan_db, tmp_path, monkeypatch):
        """副本位于种子目录（save 根或种子子目录）内时拒绝删除。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        copy_real = os.path.realpath(str(fixture.copies[0]))
        _empty_whitelist(monkeypatch, dirs=[normalize_path(str(tmp_path / "library"))])

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_real],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        assert "种子目录" in result["failed_list"][0]["reason"]
        assert os.path.exists(copy_real)

    async def test_seed_whitelist_failure_fails_closed(self, async_orphan_db, tmp_path, monkeypatch):
        """种子目录白名单加载失败时整体拒绝（fail-closed）。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        copy_real = os.path.realpath(str(fixture.copies[0]))

        def _boom(session_factory, downloader_ids=None):
            raise RuntimeError("db down")

        monkeypatch.setattr("app.services.orphan_file_service.collect_torrent_directory_whitelist", _boom)

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_real],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        assert "白名单加载失败" in result["failed_list"][0]["reason"]
        assert os.path.exists(copy_real)

    async def test_rejects_quarantine_and_recycle_markers(self, async_orphan_db, tmp_path, monkeypatch):
        """隔离区/回收站标记路径拒绝（纵深防御，标记检查先于文件系统访问）。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        _empty_whitelist(monkeypatch)
        fake_quarantine = str(tmp_path / ".btdeck_quarantine" / "x" / "a.mkv")
        fake_recycle = str(tmp_path / "downloads" / "movie.pending_delete" / "a.mkv")
        stored = fixture.stored
        stored.copies_json = json.dumps([os.path.realpath(str(fixture.source)), fake_quarantine, fake_recycle])
        await async_orphan_db.commit()

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [fake_quarantine, fake_recycle],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        reasons = [item["reason"] for item in result["failed_list"]]
        assert any("隔离区" in reason for reason in reasons)
        assert any("回收站" in reason for reason in reasons)

    async def test_identity_mismatch_keeps_file(self, async_orphan_db, tmp_path, monkeypatch):
        """副本被替换为普通文件时身份校验失败，替换文件必须原样保留。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        _empty_whitelist(monkeypatch)
        copy_path = fixture.copies[0]
        copy_real = os.path.realpath(str(copy_path))
        os.remove(copy_path)
        copy_path.write_bytes(b"replaced")  # 同路径新文件（不同 inode）

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_real],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        assert "身份" in result["failed_list"][0]["reason"]
        assert os.path.exists(copy_path)
        with open(copy_path, "rb") as f:
            assert f.read() == b"replaced"

    async def test_inaccessible_source_fails_all(self, async_orphan_db, tmp_path, monkeypatch):
        """源文件不可访问时无法校验身份，全部拒绝。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        _empty_whitelist(monkeypatch)
        copy_real = os.path.realpath(str(fixture.copies[0]))
        os.remove(fixture.source)
        os.remove(fixture.copies[0])

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_real],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        assert "源文件不可访问" in result["failed_list"][0]["reason"]

    async def test_candidate_state_gate(self, async_orphan_db, tmp_path, monkeypatch):
        """quarantined / purge_pending 候选一律拒绝（与清理流水线互斥）。"""
        quarantined = await _make_delete_fixture(async_orphan_db, tmp_path / "q", candidate_status="quarantined")
        pending = await _make_delete_fixture(async_orphan_db, tmp_path / "p", operation_state="purge_pending")
        _empty_whitelist(monkeypatch)

        service = OrphanFileService(async_orphan_db)
        result_q = await service.delete_hardlink_copies(
            quarantined.detail.id,
            [str(quarantined.copies[0])],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )
        result_p = await service.delete_hardlink_copies(
            pending.detail.id,
            [str(pending.copies[0])],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert "状态不允许" in result_q["failed_list"][0]["reason"]
        assert "状态不允许" in result_p["failed_list"][0]["reason"]
        assert os.path.exists(str(quarantined.copies[0]))
        assert os.path.exists(str(pending.copies[0]))

    async def test_missing_prescan_row_rejected(self, async_orphan_db, tmp_path, monkeypatch):
        """无预扫描结果行（pending_scan）时不可删除。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path, with_prescan=False)
        _empty_whitelist(monkeypatch)

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [str(fixture.copies[0])],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 0
        assert "预扫描" in result["failed_list"][0]["reason"]

    async def test_partial_batch_and_dedup(self, async_orphan_db, tmp_path, monkeypatch):
        """批量部分失败互不影响；重复路径去重后只删一次。"""
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path, copy_names=("a.mkv", "b.mkv"))
        _empty_whitelist(monkeypatch)
        copy_a = os.path.realpath(str(fixture.copies[0]))
        not_stored = str(tmp_path / "library" / "not-stored.mkv")

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id,
            [copy_a, not_stored, copy_a],
            operator="tester",
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["success_count"] == 1
        assert result["failed_count"] == 1
        assert not os.path.exists(copy_a)
        assert os.path.exists(os.path.realpath(str(fixture.copies[1])))

    async def test_lease_busy_returns_rejected(self, async_orphan_db, tmp_path, monkeypatch):
        """维护租约被占时整体拒绝并标记 rejected。"""
        from contextlib import asynccontextmanager

        from app.services.orphan_lease import OrphanLeaseBusyError

        @asynccontextmanager
        async def _busy_scope(operation, ttl=None, db=None):
            raise OrphanLeaseBusyError("另一个孤儿文件维护操作正在运行")
            yield  # pragma: no cover

        monkeypatch.setattr("app.services.orphan_lease.orphan_maintenance_scope", _busy_scope)
        fixture = await _make_delete_fixture(async_orphan_db, tmp_path)
        copy_real = os.path.realpath(str(fixture.copies[0]))

        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            fixture.detail.id, [copy_real], operator="tester"
        )

        assert result["rejected"] is True
        assert result["success_count"] == 0
        assert "维护操作" in result["failed_list"][0]["reason"]
        assert os.path.exists(copy_real)

    async def test_empty_request_returns_empty(self, async_orphan_db):
        """空路径列表直接返回空结果，不触碰文件系统。"""
        result = await OrphanFileService(async_orphan_db).delete_hardlink_copies(
            1, [], operator="tester", _lease_acquired=True, _lease_handle=_lease()
        )
        assert result == {
            "orphan_id": 1,
            "file_path": None,
            "copy_count": None,
            "success_count": 0,
            "failed_count": 0,
            "failed_list": [],
        }
