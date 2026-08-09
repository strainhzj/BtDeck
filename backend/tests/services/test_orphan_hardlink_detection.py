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

from app.models.orphan_file import OrphanCurrentCandidate
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import ManifestSnapshot, normalize_path
from app.services.orphan_quarantine import find_hardlink_copies

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
