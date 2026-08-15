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

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import ManifestSnapshot, normalize_path
from app.services.orphan_quarantine import (
    find_hardlink_copies,
    find_hardlink_paths,
    get_hardlink_copy_count,
)

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

    async def test_list_and_folder_rows_include_copy_count(self, async_orphan_db, tmp_path):
        """扁平行返回实时数量，文件夹行汇总子文件；不可访问文件不误报为 0。"""
        data_dir = tmp_path / "data"
        library_dir = tmp_path / "library"
        missing_dir = tmp_path / "missing"
        data_dir.mkdir()
        library_dir.mkdir()

        linked = data_dir / "linked.mkv"
        linked.write_bytes(b"linked")
        os.link(linked, library_dir / "linked-copy.mkv")

        solo = data_dir / "solo.mkv"
        solo.write_bytes(b"solo")
        missing = missing_dir / "gone.mkv"

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
                    file_path=str(linked),
                    file_size=6,
                    downloader_id="dl_001",
                    canonical_path=normalize_path(str(linked)),
                ),
                OrphanFile(
                    scan_id=scan.scan_id,
                    file_path=str(solo),
                    file_size=4,
                    downloader_id="dl_001",
                    canonical_path=normalize_path(str(solo)),
                ),
                OrphanFile(
                    scan_id=scan.scan_id,
                    file_path=str(missing),
                    file_size=7,
                    downloader_id="dl_001",
                    canonical_path=normalize_path(str(missing)),
                ),
            ]
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        flat_result = await service.get_orphan_list(page=1, page_size=20)
        by_path = {item["file_path"]: item for item in flat_result["list"]}
        assert by_path[str(linked)]["hardlink_copy_count"] == 1
        assert by_path[str(solo)]["hardlink_copy_count"] == 0
        assert by_path[str(missing)]["hardlink_copy_count"] is None

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
        assert child_counts == {str(linked): 1, str(solo): 0}


class TestHardlinkCopyLocations:
    """点击副本数量时按需定位当前运行环境可访问的其它硬链接路径。"""

    async def test_returns_found_and_unlocated_copy_counts(self, async_orphan_db, tmp_path):
        """旧映射目录之外但运行环境可访问的副本也必须被整体扫描定位。"""
        source_root = tmp_path / "downloads"
        other_root = tmp_path / "library"
        outside_root = tmp_path / "outside"
        source_root.mkdir()
        other_root.mkdir()
        outside_root.mkdir()

        linked = source_root / "linked.mkv"
        linked.write_bytes(b"linked")
        configured_copy = other_root / "linked-copy.mkv"
        os.link(linked, configured_copy)
        outside_copy = outside_root / "linked-outside.mkv"
        os.link(linked, outside_copy)

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
        async_orphan_db.add_all([linked_detail, solo_detail, missing_detail])
        await async_orphan_db.commit()

        runtime_roots = [str(source_root), str(other_root), str(outside_root)]
        service = OrphanFileService(async_orphan_db)
        with patch(
            "app.services.orphan_file_service.collect_runtime_accessible_roots",
            return_value=runtime_roots,
        ):
            result = await service.get_hardlink_copy_locations(
                [linked_detail.id, solo_detail.id, missing_detail.id, 999999]
            )

        assert result["requested_count"] == 4
        assert result["resolved_count"] == 3
        assert result["missing_orphan_ids"] == [999999]
        assert result["total_copy_count"] == 2
        assert result["total_found_count"] == 2
        assert result["total_unlocated_count"] == 0
        assert result["unknown_count"] == 1
        assert result["searched_root_count"] == 3
        assert result["search_error"] is None

        by_id = {item["orphan_id"]: item for item in result["items"]}
        linked_item = by_id[linked_detail.id]
        assert linked_item["copy_count"] == 2
        assert linked_item["found_count"] == 2
        assert linked_item["unlocated_count"] == 0
        assert linked_item["copies"] == sorted(
            [os.path.realpath(configured_copy), os.path.realpath(outside_copy)],
            key=os.path.normcase,
        )
        assert linked_item["error"] is None

        assert by_id[solo_detail.id]["copy_count"] == 0
        assert by_id[solo_detail.id]["copies"] == []
        assert by_id[missing_detail.id]["copy_count"] is None
        assert by_id[missing_detail.id]["unlocated_count"] is None
        assert by_id[missing_detail.id]["error"] == "源文件不可访问，无法重新核对副本位置"

    async def test_multiple_positive_sources_share_one_bulk_scan(self, async_orphan_db, tmp_path):
        """文件夹批量查询去重 ID，并把多个 inode 合并为一次配置目录遍历。"""
        source_root = tmp_path / "downloads"
        copy_root = tmp_path / "library"
        source_root.mkdir()
        copy_root.mkdir()

        first = source_root / "first.mkv"
        first.write_bytes(b"first")
        first_copy = copy_root / "first-copy.mkv"
        os.link(first, first_copy)

        second = source_root / "second.mkv"
        second.write_bytes(b"second")
        second_copy = copy_root / "second-copy.mkv"
        os.link(second, second_copy)

        scan = OrphanScanResult(
            scan_id="scan_hardlink_bulk_locations",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="completed",
        )
        first_detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(first),
            file_size=5,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(first)),
        )
        second_detail = OrphanFile(
            scan_id=scan.scan_id,
            file_path=str(second),
            file_size=6,
            downloader_id="dl_001",
            canonical_path=normalize_path(str(second)),
        )
        async_orphan_db.add_all([scan, first_detail, second_detail])
        await async_orphan_db.commit()

        runtime_roots = [str(source_root), str(copy_root)]
        service = OrphanFileService(async_orphan_db)
        with (
            patch(
                "app.services.orphan_file_service.collect_runtime_accessible_roots",
                return_value=runtime_roots,
            ),
            patch(
                "app.services.orphan_file_service.find_hardlink_paths",
                wraps=find_hardlink_paths,
            ) as bulk_lookup,
        ):
            result = await service.get_hardlink_copy_locations([first_detail.id, first_detail.id, second_detail.id])

        bulk_lookup.assert_called_once()
        target_inodes, scan_roots = bulk_lookup.call_args.args
        expected_inodes = {
            (int(os.stat(first).st_dev), int(os.stat(first).st_ino)),
            (int(os.stat(second).st_dev), int(os.stat(second).st_ino)),
        }
        assert target_inodes == expected_inodes
        assert set(scan_roots) == set(runtime_roots)

        assert result["requested_count"] == 2
        assert result["resolved_count"] == 2
        assert result["total_copy_count"] == 2
        assert result["total_found_count"] == 2
        assert result["total_unlocated_count"] == 0
        by_id = {item["orphan_id"]: item for item in result["items"]}
        assert by_id[first_detail.id]["copies"] == [os.path.realpath(first_copy)]
        assert by_id[second_detail.id]["copies"] == [os.path.realpath(second_copy)]

    async def test_scan_failure_keeps_live_count_as_unlocated(self, async_orphan_db, tmp_path):
        """配置目录扫描失败时不伪造路径，实时副本总数全部转为未定位并返回错误。"""
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
        with (
            patch(
                "app.services.orphan_file_service.collect_runtime_accessible_roots",
                return_value=[str(source_root)],
            ),
            patch(
                "app.services.orphan_file_service.find_hardlink_paths",
                side_effect=OSError("storage offline"),
            ) as bulk_lookup,
        ):
            result = await service.get_hardlink_copy_locations([detail.id])

        bulk_lookup.assert_called_once()
        expected_error = "当前运行环境可访问目录扫描失败，未能完整定位副本位置"
        assert result["search_error"] == expected_error
        assert result["searched_root_count"] == 1
        assert result["total_copy_count"] == 1
        assert result["total_found_count"] == 0
        assert result["total_unlocated_count"] == 1
        assert result["items"][0]["copies"] == []
        assert result["items"][0]["unlocated_count"] == 1
        assert result["items"][0]["error"] == expected_error

    async def test_zero_copy_does_not_scan_configured_roots(self, async_orphan_db, tmp_path):
        """列表变更为零副本时直接返回，不做无意义的目录遍历。"""
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
        with patch("app.services.orphan_file_service.collect_runtime_accessible_roots") as collect_roots:
            result = await service.get_hardlink_copy_locations([detail.id])

        collect_roots.assert_not_called()
        assert result["total_copy_count"] == 0
        assert result["total_found_count"] == 0
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
