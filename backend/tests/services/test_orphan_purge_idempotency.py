# -*- coding: utf-8 -*-
"""
H 组：隔离区"立即彻底删除"幂等与 manifest 预构建测试。

覆盖 v1.0.7 两个已知问题（生产事故 2026-08-08 排查结论）：
1. 重跑无幂等：进程崩溃 → 重启恢复任务重跑时，已 purged 的候选被误报为
   "候选不存在或非 quarantined 稳定态"，任务终态失真（partial 而非 completed）。
   → 修复：purged 候选视为幂等成功；真不存在/状态不符必须区分并附实际状态。
2. 逐文件重建 manifest：_purge_single_candidate 每文件构建 2 次全量 manifest，
   N 文件 = 2N 次下载器全量 API 调用，是"1.5~2 分钟/文件"的性能放大器。
   → 修复：manifest 按 downloader_id 在循环外预构建一次，循环内复用。
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.orphan_file import OrphanCurrentCandidate
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_manifest import ManifestSnapshot

pytestmark = pytest.mark.asyncio


def _empty_manifest(root, downloader_id="dl_001"):
    """空 manifest：文件未被任何种子引用，路径授权通过。"""
    return ManifestSnapshot(
        expected_paths=set(),
        scan_roots=[(str(root), frozenset({downloader_id}))],
        downloader_ids={downloader_id},
    )


def _make_quarantined(async_orphan_db, tmp_path, filename):
    """构造一个已隔离候选 + 隔离区实体文件（模拟 cleanup 后状态）。

    返回 (candidate, canonical_path, quarantine_path)。
    """
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
        downloader_id="dl_001",
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


def _purged_candidate(async_orphan_db, tmp_path, filename):
    """构造一个已物理删除（purged）的候选，无实体文件。"""
    old_time = datetime.utcnow() - timedelta(days=10)
    canonical = str(tmp_path / filename)
    async_orphan_db.add(
        OrphanCurrentCandidate(
            canonical_path=canonical,
            downloader_id="dl_001",
            first_seen_at=old_time,
            last_seen_at=old_time,
            status="purged",
        )
    )
    return canonical


# ==================== 修复 1：重跑幂等 ====================


class TestPurgeNowIdempotency:
    """立即彻底删除对已 purged 候选必须幂等成功，不再误报失败。"""

    async def test_already_purged_candidate_is_idempotent_success(self, async_orphan_db, tmp_path):
        """重启重跑场景：候选已是 purged → 视为删除成功（purged_count 计入，无失败）。"""
        canonical = _purged_candidate(async_orphan_db, tmp_path, "already-gone.mkv")
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.purge_quarantine_now(
            canonical_paths=[canonical],
            operator="admin",
            store=MagicMock(),
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["purged_count"] == 1, f"已 purged 候选应幂等成功: {result}"
        assert result["failed_count"] == 0, f"不应产生失败: {result}"
        assert result["failed_list"] == []

    async def test_mixed_batch_counts_idempotent_as_purged(self, async_orphan_db, tmp_path):
        """混合批次（1 已删 + 1 隔离中）→ 全部计入 purged_count，任务可收敛为 completed。"""
        purged_canonical = _purged_candidate(async_orphan_db, tmp_path, "gone.mkv")
        candidate, canonical, quarantine_path = _make_quarantined(async_orphan_db, tmp_path, "still-there.mkv")
        await async_orphan_db.commit()

        manifest = _empty_manifest(tmp_path)
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[purged_canonical, canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["purged_count"] == 2, f"两个文件都应计入删除成功: {result}"
        assert result["failed_count"] == 0, f"不应产生失败: {result}"
        assert not os.path.exists(quarantine_path)

    async def test_missing_candidate_reports_distinct_reason(self, async_orphan_db, tmp_path):
        """真不存在的路径仍报失败，但原因必须区分"不存在"，而非笼统的稳定态文案。"""
        service = OrphanFileService(async_orphan_db)
        result = await service.purge_quarantine_now(
            canonical_paths=["/never/existed/on/disk.mkv"],
            operator="admin",
            store=MagicMock(),
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["purged_count"] == 0
        assert result["failed_count"] == 1
        reason = result["failed_list"][0]["reason"]
        assert "候选不存在" in reason, f"应明确候选不存在: {reason}"
        assert "非 quarantined 稳定态" not in reason, f"不应使用旧的笼统文案: {reason}"

    async def test_restored_candidate_reports_actual_status(self, async_orphan_db, tmp_path):
        """候选已被恢复（status=candidate）→ 失败原因必须附实际状态，便于用户判断。"""
        old_time = datetime.utcnow() - timedelta(days=10)
        canonical = str(tmp_path / "restored-back.mkv")
        async_orphan_db.add(
            OrphanCurrentCandidate(
                canonical_path=canonical,
                downloader_id="dl_001",
                first_seen_at=old_time,
                last_seen_at=old_time,
                status="candidate",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.purge_quarantine_now(
            canonical_paths=[canonical],
            operator="admin",
            store=MagicMock(),
            _lease_acquired=True,
            _lease_handle=_lease(),
        )

        assert result["failed_count"] == 1
        reason = result["failed_list"][0]["reason"]
        assert "candidate" in reason, f"失败原因应包含实际状态: {reason}"
        assert "候选不存在" not in reason, f"候选存在时不应报不存在: {reason}"


# ==================== 修复 2：manifest 预构建 ====================


class TestPurgeNowManifestHoisting:
    """manifest 必须按 downloader 预构建一次，禁止逐文件重建。"""

    async def test_manifest_built_once_per_downloader_for_many_files(self, async_orphan_db, tmp_path):
        """同下载器 2 个文件 → 仅构建 1 次 manifest（修复前是 2N=4 次）。"""
        _c1, canonical1, _ = _make_quarantined(async_orphan_db, tmp_path, "first.mkv")
        _c2, canonical2, _ = _make_quarantined(async_orphan_db, tmp_path, "second.mkv")
        await async_orphan_db.commit()

        manifest = _empty_manifest(tmp_path)
        service = OrphanFileService(async_orphan_db)
        builder = AsyncMock(return_value=manifest)
        with patch.object(OrphanFileService, "_build_realtime_manifest", builder):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical1, canonical2],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["purged_count"] == 2, f"两个文件都应删除: {result}"
        assert result["failed_count"] == 0, f"不应产生失败: {result}"
        assert builder.await_count == 1, f"manifest 应只构建 1 次，实际 {builder.await_count} 次"
        assert builder.await_args.args[1] == {"dl_001"}

    async def test_manifest_built_once_per_downloader_for_different_downloaders(self, async_orphan_db, tmp_path):
        """不同下载器各 1 个文件 → 构建 2 次（每个 downloader 一次）。"""
        _c1, canonical1, _ = _make_quarantined(async_orphan_db, tmp_path, "dl1.mkv")
        _c2, canonical2, _ = _make_quarantined(async_orphan_db, tmp_path, "dl2.mkv")
        _c2.downloader_id = "dl_002"
        await async_orphan_db.commit()

        manifest1 = _empty_manifest(tmp_path, downloader_id="dl_001")
        manifest2 = _empty_manifest(tmp_path, downloader_id="dl_002")

        service = OrphanFileService(async_orphan_db)
        builder = AsyncMock(side_effect=lambda store, ids: manifest1 if "dl_001" in ids else manifest2)
        with patch.object(OrphanFileService, "_build_realtime_manifest", builder):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical1, canonical2],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=_lease(),
            )

        assert result["purged_count"] == 2, f"两个文件都应删除: {result}"
        assert builder.await_count == 2, f"manifest 应按 downloader 各构建 1 次，实际 {builder.await_count} 次"
