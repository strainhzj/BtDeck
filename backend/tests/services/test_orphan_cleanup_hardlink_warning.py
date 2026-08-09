# -*- coding: utf-8 -*-
"""
J 组：清理阶段（candidate→隔离）的硬链接副本预警。

设计（用户确认选 B）：清理是可恢复操作（7 天保留期 + 可恢复），故清理遇硬链接
副本应**照常隔离、不阻断**，但在清理结果中尽早返回 hardlink_notes，让用户在后续
彻底删除前知情。复用 _detect_hardlink_copies 的 cleanup_warn 模式（与 purge_now
同走返回路径，永不抛异常）。
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import ManifestSnapshot, normalize_path

pytestmark = pytest.mark.asyncio


def _manifest_with_seed(root, seed_paths, downloader_id="dl_001"):
    """expected_paths 含 seed_paths 的 manifest（用于 is_seed 判定与 scan_roots）。"""
    return ManifestSnapshot(
        expected_paths={normalize_path(p) for p in seed_paths},
        scan_roots=[(str(root), frozenset({downloader_id}))],
        downloader_ids={downloader_id},
    )


async def _seed_candidate(async_orphan_db, tmp_path, filename, *, downloader_id="dl_001"):
    """构造待清理数据：completed 扫描 + OrphanFile 明细 + candidate 候选 + 原位文件。

    返回 (orphan_id, canonical_path, file_path)。
    """
    file_path = tmp_path / filename
    file_path.write_bytes(b"x" * 100)
    f_stat = file_path.stat()
    canonical = str(file_path)
    old_time = datetime.utcnow() - timedelta(days=40)

    async_orphan_db.add(
        OrphanScanResult(
            scan_id="scan_cleanup",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="completed",
        )
    )
    async_orphan_db.add(
        OrphanFile(
            scan_id="scan_cleanup",
            file_path=canonical,
            canonical_path=canonical,
            file_size=100,
            mtime=datetime.utcnow(),
            downloader_id=downloader_id,
        )
    )
    async_orphan_db.add(
        OrphanCurrentCandidate(
            canonical_path=canonical,
            downloader_id=downloader_id,
            first_seen_at=old_time,
            last_seen_at=datetime.utcnow(),
            last_seen_scan_id="scan_cleanup",
            consecutive_scan_count=2,
            status="candidate",
            file_size=100,
            mtime_ns=f_stat.st_mtime_ns,
            device_id=str(f_stat.st_dev),
            inode=str(f_stat.st_ino),
            confidence="high",
        )
    )
    await async_orphan_db.commit()
    return 1, canonical, str(file_path)


def _lease():
    lease = MagicMock()
    lease.assert_owned = AsyncMock()
    return lease


# ==================== 手动清理 cleanup_orphans ====================


class TestCleanupHardlinkWarning:
    """清理遇硬链接副本：照常隔离 + 结果返回 hardlink_notes。"""

    async def test_manual_cleanup_warns_but_still_quarantines(self, async_orphan_db, tmp_path):
        """手动清理含硬链接副本的文件：隔离成功（success_count=1）+ hardlink_notes 非空。"""
        orphan_id, canonical, file_path = await _seed_candidate(async_orphan_db, tmp_path, "linked.mkv")
        # 在扫描根内建一个硬链接副本（媒体库整理）
        copy_path = str(tmp_path / "media" / "linked.mkv")
        os.makedirs(os.path.dirname(copy_path), exist_ok=True)
        os.link(file_path, copy_path)

        manifest = _manifest_with_seed(tmp_path, [copy_path])
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.cleanup_orphans(
                orphan_ids=[orphan_id],
                operator="admin",
                store=MagicMock(),
                audit_service=AsyncMock(),
                scan_id="scan_cleanup",
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["success_count"] == 1, f"清理应照常隔离: {result}"
        notes = result.get("hardlink_notes", [])
        assert len(notes) == 1, f"应返回1条硬链接预警: {notes}"
        note = notes[0]
        assert note["canonical_path"] == canonical
        assert note["remaining_count"] == 1
        assert note["copies"][0]["is_seed"] is True, "副本在 expected_paths 中应为种子文件"
        # 副本仍在，原文件已移入隔离区
        assert os.path.exists(copy_path), "硬链接副本不应被破坏"
        assert not os.path.exists(file_path), "原文件应已移入隔离区"

    async def test_manual_cleanup_no_hardlink_no_warning(self, async_orphan_db, tmp_path):
        """无硬链接副本的清理不产生 hardlink_notes。"""
        orphan_id, canonical, file_path = await _seed_candidate(async_orphan_db, tmp_path, "solo.mkv")
        manifest = _manifest_with_seed(tmp_path, [])
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.cleanup_orphans(
                orphan_ids=[orphan_id],
                operator="admin",
                store=MagicMock(),
                audit_service=AsyncMock(),
                scan_id="scan_cleanup",
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["success_count"] == 1, f"清理应成功: {result}"
        assert result.get("hardlink_notes", []) == [], "无副本不应产生预警"


# ==================== 自动清理 auto_cleanup_expired ====================


class TestAutoCleanupHardlinkWarning:
    """自动清理（满 30 天）同样应在隔离前预警。"""

    async def test_auto_cleanup_warns_but_still_quarantines(self, async_orphan_db, tmp_path):
        orphan_id, canonical, file_path = await _seed_candidate(async_orphan_db, tmp_path, "auto-linked.mkv")
        copy_path = str(tmp_path / "sorted" / "auto-linked.mkv")
        os.makedirs(os.path.dirname(copy_path), exist_ok=True)
        os.link(file_path, copy_path)

        manifest = _manifest_with_seed(tmp_path, [])  # 副本不在 expected_paths → 非种子
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.auto_cleanup_expired(
                days_threshold=30,
                operator="system",
                store=MagicMock(),
                scan_id="scan_cleanup",
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["quarantined_count"] == 1, f"自动清理应照常隔离: {result}"
        notes = result.get("hardlink_notes", [])
        assert len(notes) == 1, f"应返回1条硬链接预警: {notes}"
        assert notes[0]["copies"][0]["is_seed"] is False, "副本不在 expected_paths 应为普通副本"
        assert os.path.exists(copy_path), "硬链接副本不应被破坏"
