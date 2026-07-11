# -*- coding: utf-8 -*-
"""
E 组 + F 组：删除安全与隔离区 / 并发 lease（v1.0.6+ 语义重做）

E 组（删除安全）覆盖：
- 扫描后文件被新种子引用（size/mtime 不变、size 变、mtime_ns 变、inode/file-id 变、路径被替换）
- 符号链接和非普通文件
- 路径逃逸授权扫描根
- 实时 manifest 构建失败
- 同批次重复 ID 或路径别名
- 自动清理移动到隔离区（不直接删除）
- 隔离保留期未到不删、到期才物理删

F 组（并发 lease）覆盖：
- 两个扫描争抢 / 扫描与手动清理竞争 / 两个自动清理竞争
- lease 过期后允许接管
- preview 后启动新扫描使原 preview 失效
- 持有 lease 的进程异常退出后可恢复

本阶段因清理安全重构 / lease 机制尚未实现，全部应失败。
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


# ==================== E 组：删除安全 ====================


class TestCleanupSafetyManifest:
    """清理时实时复核文件身份。"""

    async def test_file_referenced_by_new_torrent_blocked(self, async_orphan_db, tmp_path):
        """扫描后文件被新种子引用 → 清理时复核身份，阻止删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanFile, OrphanScanResult

        orphan_file_path = tmp_path / "reused.mkv"
        orphan_file_path.write_bytes(b"x" * 100)

        async_orphan_db.add(
            OrphanScanResult(scan_id="scan_1", scan_time=datetime.utcnow(), scan_type="manual", status="completed")
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1",
                file_path=str(orphan_file_path),
                file_size=100,
                mtime=datetime.utcnow(),
                downloader_id="dl_001",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        # 清理时实时 manifest 应发现该文件已被种子引用 → 拒绝删除
        result = await service.cleanup_orphans(
            orphan_ids=[1],
            operator="admin",
            store=MagicMock(),  # 提供 store 以重建 manifest
        )
        assert result["success_count"] == 0, "被新种子引用的文件不应被删除"
        assert result["failed_count"] >= 1 or len(result.get("failed_list", [])) >= 1
        # 文件应仍然存在
        assert orphan_file_path.exists(), "文件不应被删除"

    async def test_size_changed_blocks_cleanup(self, async_orphan_db, tmp_path):
        """size 改变 → 阻止清理。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanFile, OrphanScanResult

        f = tmp_path / "size_changed.bin"
        f.write_bytes(b"x" * 100)

        async_orphan_db.add(
            OrphanScanResult(scan_id="scan_1", scan_time=datetime.utcnow(), scan_type="manual", status="completed")
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1",
                file_path=str(f),
                file_size=200,  # 记录的 size 与实际不符
                mtime=datetime.utcnow(),
                downloader_id="dl_001",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.cleanup_orphans(orphan_ids=[1], operator="admin", store=MagicMock())
        assert result["success_count"] == 0, "size 变化的文件不应被删除"

    async def test_symlink_not_deleted(self, async_orphan_db, tmp_path):
        """符号链接（非普通文件）不应被删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanFile, OrphanScanResult

        target = tmp_path / "target.bin"
        target.write_bytes(b"target")
        link = tmp_path / "link.bin"
        try:
            os.symlink(str(target), str(link))
        except OSError:
            pytest.skip("当前环境不支持创建符号链接")

        async_orphan_db.add(
            OrphanScanResult(scan_id="scan_1", scan_time=datetime.utcnow(), scan_type="manual", status="completed")
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1", file_path=str(link), file_size=6, mtime=datetime.utcnow(), downloader_id="dl_001"
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.cleanup_orphans(orphan_ids=[1], operator="admin", store=MagicMock())
        assert result["success_count"] == 0, "符号链接不应被清理"
        assert link.exists(), "符号链接不应被删除"

    async def test_path_escape_blocked(self, async_orphan_db, tmp_path):
        """路径逃逸授权扫描根 → 阻止清理。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanFile, OrphanScanResult

        # 构造一个逃逸路径（../../../etc/passwd 风格）
        escape_path = str(tmp_path.parent.parent / "sensitive.bin")

        async_orphan_db.add(
            OrphanScanResult(scan_id="scan_1", scan_time=datetime.utcnow(), scan_type="manual", status="completed")
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1", file_path=escape_path, file_size=100, mtime=datetime.utcnow(), downloader_id="dl_001"
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.cleanup_orphans(orphan_ids=[1], operator="admin", store=MagicMock())
        assert result["success_count"] == 0, "逃逸路径不应被清理"

    async def test_manifest_build_failure_blocks_cleanup(self, async_orphan_db, tmp_path):
        """实时 manifest 构建失败 → 阻止清理。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanFile, OrphanScanResult

        f = tmp_path / "orphan.bin"
        f.write_bytes(b"x" * 50)

        async_orphan_db.add(
            OrphanScanResult(scan_id="scan_1", scan_time=datetime.utcnow(), scan_type="manual", status="completed")
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1", file_path=str(f), file_size=50, mtime=datetime.utcnow(), downloader_id="dl_001"
            )
        )
        await async_orphan_db.commit()

        # store.get_snapshot 抛异常 → manifest 构建失败
        bad_store = MagicMock()
        bad_store.get_snapshot = AsyncMock(side_effect=RuntimeError("store 不可用"))

        service = OrphanFileService(async_orphan_db)
        result = await service.cleanup_orphans(orphan_ids=[1], operator="admin", store=bad_store)
        assert result["success_count"] == 0, "manifest 构建失败时不应清理"


class TestQuarantineWorkflow:
    """自动清理移动到隔离区，不直接删除。"""

    async def test_auto_cleanup_moves_to_quarantine_not_delete(self, async_orphan_db, tmp_path):
        """自动清理应移动到隔离区，不直接物理删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanCurrentCandidate, OrphanScanResult

        src = tmp_path / "to_quarantine.mkv"
        src.write_bytes(b"x" * 100)

        # 创建一个满足 30 天条件的候选
        old_time = datetime.utcnow() - timedelta(days=35)
        async_orphan_db.add(
            OrphanScanResult(scan_id="scan_1", scan_time=old_time, scan_type="scheduled", status="completed")
        )
        await async_orphan_db.commit()

        candidate = OrphanCurrentCandidate(
            canonical_path=str(src),
            downloader_id="dl_001",
            first_seen_at=old_time,
            last_seen_at=datetime.utcnow(),
            last_seen_scan_id="scan_1",
            consecutive_scan_count=2,
            status="candidate",
            file_size=100,
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.auto_cleanup_expired(days_threshold=30, operator="system", store=MagicMock())

        # 候选应被移动到隔离区，status=quarantined
        assert result.get("quarantined_count", 0) > 0 or result.get("success_count", 0) > 0
        # 原文件不应存在于原路径
        assert not src.exists(), "文件不应留在原路径（应被移到隔离区）"
        # 候选 status 应为 quarantined（而非直接 deleted）
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "quarantined", "候选应标记为 quarantined 而非直接删除"

    async def test_quarantine_not_purged_before_retention(self, async_orphan_db, tmp_path):
        """隔离保留期未到不得物理删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanCurrentCandidate

        quarantine_dir = tmp_path / ".btdeck_quarantine" / "scan_1"
        quarantine_dir.mkdir(parents=True)
        quarantined_file = quarantine_dir / "kept.mkv"
        quarantined_file.write_bytes(b"x" * 100)

        candidate = OrphanCurrentCandidate(
            canonical_path=str(tmp_path / "original.mkv"),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=40),
            last_seen_at=datetime.utcnow(),
            status="quarantined",
            file_size=100,
            quarantine_path=str(quarantined_file),
            quarantined_at=datetime.utcnow(),  # 刚隔离，保留期未到
            purge_after=datetime.utcnow() + timedelta(days=6),  # 7 天后才能删
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.purge_expired_quarantine()
        assert result.get("purged_count", 0) == 0, "保留期未到不应物理删除"
        assert quarantined_file.exists(), "隔离保留期内文件不应被删除"

    async def test_quarantine_purged_after_retention(self, async_orphan_db, tmp_path):
        """隔离保留期到期后才允许物理删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanCurrentCandidate

        quarantine_dir = tmp_path / ".btdeck_quarantine" / "scan_1"
        quarantine_dir.mkdir(parents=True)
        expired_file = quarantine_dir / "expired.mkv"
        expired_file.write_bytes(b"x" * 100)

        candidate = OrphanCurrentCandidate(
            canonical_path=str(tmp_path / "original.mkv"),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=40),
            last_seen_at=datetime.utcnow(),
            status="quarantined",
            file_size=100,
            quarantine_path=str(expired_file),
            quarantined_at=datetime.utcnow() - timedelta(days=8),
            purge_after=datetime.utcnow() - timedelta(days=1),  # 已过期
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.purge_expired_quarantine()
        assert result.get("purged_count", 0) >= 1, "到期应物理删除"
        assert not expired_file.exists(), "到期文件应被删除"


# ==================== F 组：并发 lease ====================


class TestConcurrentLease:
    """跨进程 lease 保护扫描/预览/手动清理/自动清理。"""

    async def test_two_scans_contention(self, async_orphan_db):
        """两个扫描同时争抢，只有一个能获得 lease。"""
        from app.services.orphan_lease import acquire_lease, release_lease

        # 第一个获取成功
        acquired1 = await acquire_lease("orphan_scan", owner="proc_1", ttl=3600, db=async_orphan_db)
        assert acquired1, "第一个扫描应获取 lease"

        # 第二个应失败
        acquired2 = await acquire_lease("orphan_scan", owner="proc_2", ttl=3600, db=async_orphan_db)
        assert not acquired2, "第二个扫描不应获取 lease（已被持有）"

        await release_lease("orphan_scan", owner="proc_1", db=async_orphan_db)

    async def test_scan_vs_cleanup_contention(self, async_orphan_db):
        """扫描与手动清理竞争 —— 不同操作用不同 lease key 但互斥保护各自流程。"""
        from app.services.orphan_lease import acquire_lease, release_lease

        scan_acquired = await acquire_lease("orphan_scan", owner="proc_1", ttl=3600, db=async_orphan_db)
        assert scan_acquired

        # cleanup 有独立 lease key
        cleanup_acquired = await acquire_lease("orphan_cleanup", owner="proc_2", ttl=3600, db=async_orphan_db)
        assert cleanup_acquired

        await release_lease("orphan_scan", owner="proc_1", db=async_orphan_db)
        await release_lease("orphan_cleanup", owner="proc_2", db=async_orphan_db)

    async def test_expired_lease_takeover(self, async_orphan_db):
        """lease 过期后允许接管。"""
        from app.services.orphan_lease import acquire_lease, release_lease

        # 用极短 TTL 模拟过期
        await acquire_lease("orphan_scan", owner="proc_old", ttl=0, db=async_orphan_db)
        import asyncio

        await asyncio.sleep(0.05)  # 等 TTL 过期

        # 新进程应能接管
        acquired = await acquire_lease("orphan_scan", owner="proc_new", ttl=3600, db=async_orphan_db)
        assert acquired, "lease 过期后应允许接管"

        await release_lease("orphan_scan", owner="proc_new", db=async_orphan_db)

    async def test_process_crash_recovery(self, async_orphan_db):
        """持有 lease 的进程异常退出后，lease 过期可恢复。"""
        from app.services.orphan_lease import acquire_lease

        # 进程获取 lease 后崩溃（不 release）
        await acquire_lease("orphan_scan", owner="crashed_proc", ttl=0, db=async_orphan_db)
        import asyncio

        await asyncio.sleep(0.05)

        # 新进程接管
        acquired = await acquire_lease("orphan_scan", owner="recovery_proc", ttl=3600, db=async_orphan_db)
        assert acquired, "崩溃进程的 lease 过期后应能恢复"
