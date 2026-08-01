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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _empty_manifest(root, downloader_id="dl_001"):
    from app.services.orphan_manifest import ManifestSnapshot

    return ManifestSnapshot(
        expected_paths=set(),
        scan_roots=[(str(root), downloader_id)],
        downloader_ids={downloader_id},
    )


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
            OrphanScanResult(
                scan_id="scan_1",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
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
            OrphanScanResult(
                scan_id="scan_1",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
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
            OrphanScanResult(
                scan_id="scan_1",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1",
                file_path=str(link),
                file_size=6,
                mtime=datetime.utcnow(),
                downloader_id="dl_001",
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
            OrphanScanResult(
                scan_id="scan_1",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1",
                file_path=escape_path,
                file_size=100,
                mtime=datetime.utcnow(),
                downloader_id="dl_001",
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
            OrphanScanResult(
                scan_id="scan_1",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_1",
                file_path=str(f),
                file_size=50,
                mtime=datetime.utcnow(),
                downloader_id="dl_001",
            )
        )
        await async_orphan_db.commit()

        # store.get_snapshot 抛异常 → manifest 构建失败
        bad_store = MagicMock()
        bad_store.get_snapshot = AsyncMock(side_effect=RuntimeError("store 不可用"))

        service = OrphanFileService(async_orphan_db)
        result = await service.cleanup_orphans(orphan_ids=[1], operator="admin", store=bad_store)
        assert result["success_count"] == 0, "manifest 构建失败时不应清理"

    async def test_cleanup_rejects_candidate_outside_authorized_root(self, async_orphan_db, tmp_path):
        """即使 DB 候选身份完整，路径不属于实时扫描根也必须拒绝。"""
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import normalize_path

        authorized_root = tmp_path / "authorized"
        authorized_root.mkdir()
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"payload")
        stat = outside.stat()
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_auth",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        detail = OrphanFile(
            scan_id="scan_auth",
            file_path=str(outside),
            file_size=stat.st_size,
            mtime=datetime.utcnow(),
            downloader_id="dl_001",
        )
        async_orphan_db.add(detail)
        async_orphan_db.add(
            OrphanCurrentCandidate(
                canonical_path=normalize_path(str(outside)),
                downloader_id="dl_001",
                last_seen_scan_id="scan_auth",
                file_size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                device_id=stat.st_dev,
                inode=stat.st_ino,
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(authorized_root)),
        ):
            result = await service.cleanup_orphans(
                [detail.id],
                "admin",
                store=MagicMock(),
                scan_id="scan_auth",
                _lease_acquired=True,
            )

        assert result["success_count"] == 0
        assert "授权扫描根" in result["failed_list"][0]["reason"]
        assert outside.exists()

    async def test_auto_cleanup_rejects_replaced_inode(self, async_orphan_db, tmp_path):
        """替换文件即使 size/mtime 相同，inode 不同也不得被自动隔离。"""
        from app.models.orphan_file import OrphanCurrentCandidate, OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        path = tmp_path / "replaced.bin"
        path.write_bytes(b"old-data")
        old = path.stat()
        candidate = OrphanCurrentCandidate(
            canonical_path=str(path),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=40),
            last_seen_at=datetime.utcnow(),
            last_seen_scan_id="scan_replace",
            consecutive_scan_count=2,
            file_size=old.st_size,
            mtime_ns=old.st_mtime_ns,
            device_id=old.st_dev,
            inode=old.st_ino,
        )
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_replace",
                scan_time=datetime.utcnow(),
                scan_type="scheduled",
                status="completed",
            )
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        path.unlink()
        path.write_bytes(b"new-data")
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(tmp_path)),
        ):
            result = await service.auto_cleanup_expired(
                30, store=MagicMock(), scan_id="scan_replace", _lease_acquired=True
            )

        assert result["quarantined_count"] == 0
        assert result["failed_count"] == 1
        assert path.exists()


class TestQuarantineWorkflow:
    """自动清理移动到隔离区，不直接删除。"""

    async def test_auto_cleanup_moves_to_quarantine_not_delete(self, async_orphan_db, tmp_path):
        """自动清理应移动到隔离区，不直接物理删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )

        src = tmp_path / "to_quarantine.mkv"
        src.write_bytes(b"x" * 100)
        src_stat = src.stat()

        # 创建一个满足 30 天条件的候选
        old_time = datetime.utcnow() - timedelta(days=35)
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_1",
                scan_time=old_time,
                scan_type="scheduled",
                status="completed",
            )
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
            mtime_ns=src_stat.st_mtime_ns,
            device_id=src_stat.st_dev,
            inode=src_stat.st_ino,
        )
        async_orphan_db.add_all(
            [
                candidate,
                OrphanFile(
                    scan_id="scan_1",
                    file_path=str(src),
                    file_size=100,
                    mtime=datetime.fromtimestamp(src_stat.st_mtime),
                    downloader_id="dl_001",
                ),
            ]
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(tmp_path)),
        ):
            result = await service.auto_cleanup_expired(
                days_threshold=30,
                operator="system",
                store=MagicMock(),
                scan_id="scan_1",
            )

        # 候选应被移动到隔离区，status=quarantined
        assert result.get("quarantined_count", 0) > 0 or result.get("success_count", 0) > 0
        # 原文件不应存在于原路径
        assert not src.exists(), "文件不应留在原路径（应被移到隔离区）"
        # 候选 status 应为 quarantined（而非直接 deleted）
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "quarantined", "候选应标记为 quarantined 而非直接删除"
        detail = await async_orphan_db.get(OrphanFile, 1)
        assert detail.is_deleted is True
        assert detail.deleted_by == "system"
        assert detail.deleted_at == candidate.quarantined_at

    async def test_quarantine_not_purged_before_retention(self, async_orphan_db, tmp_path):
        """隔离保留期未到不得物理删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanCurrentCandidate

        quarantine_dir = tmp_path / ".btdeck_quarantine" / "scan_1"
        quarantine_dir.mkdir(parents=True)
        quarantined_file = quarantine_dir / "kept.mkv"
        quarantined_file.write_bytes(b"x" * 100)
        kept_stat = quarantined_file.stat()

        candidate = OrphanCurrentCandidate(
            canonical_path=str(tmp_path / "original.mkv"),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=40),
            last_seen_at=datetime.utcnow(),
            status="quarantined",
            file_size=100,
            mtime_ns=kept_stat.st_mtime_ns,
            device_id=kept_stat.st_dev,
            inode=kept_stat.st_ino,
            quarantine_path=str(quarantined_file),
            quarantine_root=str(quarantine_dir),
            quarantined_at=datetime.utcnow(),  # 刚隔离，保留期未到
            purge_after=datetime.utcnow() + timedelta(days=6),  # 7 天后才能删
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(tmp_path)),
        ):
            result = await service.purge_expired_quarantine(store=MagicMock())
        assert not result.get("rejected"), "保留期测试必须实际通过实时清单门禁"
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
        expired_stat = expired_file.stat()

        candidate = OrphanCurrentCandidate(
            canonical_path=str(tmp_path / "original.mkv"),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=40),
            last_seen_at=datetime.utcnow(),
            status="quarantined",
            file_size=100,
            mtime_ns=expired_stat.st_mtime_ns,
            device_id=expired_stat.st_dev,
            inode=expired_stat.st_ino,
            quarantine_path=str(expired_file),
            quarantine_root=str(quarantine_dir),
            quarantined_at=datetime.utcnow() - timedelta(days=8),
            purge_after=datetime.utcnow() - timedelta(days=1),  # 已过期
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(tmp_path)),
        ):
            result = await service.purge_expired_quarantine(store=MagicMock())
        assert not result.get("rejected"), "到期清除测试必须实际通过实时清单门禁"
        assert result.get("purged_count", 0) >= 1, "到期应物理删除"
        assert not expired_file.exists(), "到期文件应被删除"
        assert not quarantine_dir.exists(), "文件删除后应同步清理空 scan_id 目录"

    async def test_expired_purge_does_not_reauthorize_with_downloader_mapping(self, async_orphan_db, tmp_path):
        """到期物理删除只使用隔离记录，不应重新走下载器路径授权。"""
        from app.services.orphan_file_service import OrphanFileService

        candidate, _canonical, quarantine_path, quarantine_root, _, _ = _make_quarantined_candidate(
            async_orphan_db,
            tmp_path,
            filename="expired-with-stale-mapping.mkv",
        )
        candidate.canonical_path = str(tmp_path / "Downloads" / "ipan" / "Downloads" / "expired-with-stale-mapping.mkv")
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        manifest_builder = AsyncMock(side_effect=AssertionError("到期隔离删除不应构建下载器 manifest"))
        path_authorizer = MagicMock(side_effect=AssertionError("到期隔离删除不应使用原始路径授权"))
        with (
            patch.object(service, "_build_realtime_manifest", manifest_builder),
            patch.object(OrphanFileService, "_path_authorized", path_authorizer),
        ):
            result = await service.purge_expired_quarantine(store=MagicMock())

        assert result["purged_count"] == 1
        assert not os.path.exists(quarantine_path)
        assert not os.path.exists(quarantine_root)
        manifest_builder.assert_not_awaited()
        path_authorizer.assert_not_called()

    async def test_recovers_crash_after_atomic_move(self, async_orphan_db, tmp_path):
        """rename 已完成但最终 DB 提交前崩溃时，下次维护应完成候选状态。"""
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )
        from app.services.orphan_file_service import OrphanFileService

        root = tmp_path / ".btdeck_quarantine" / "scan_1"
        root.mkdir(parents=True)
        target = root / "journaled.bin"
        target.write_bytes(b"payload")
        target_stat = target.stat()
        candidate = OrphanCurrentCandidate(
            canonical_path=str(tmp_path / "original.bin"),
            downloader_id="dl_001",
            last_seen_scan_id="scan_1",
            status="candidate",
            file_size=7,
            mtime_ns=target_stat.st_mtime_ns,
            device_id=target_stat.st_dev,
            inode=target_stat.st_ino,
            quarantine_root=str(root),
            purge_after=datetime.utcnow() + timedelta(days=7),
            operation_state="quarantine_pending",
            operation_target_path=str(target),
        )
        async_orphan_db.add_all(
            [
                OrphanScanResult(
                    scan_id="scan_1",
                    scan_time=datetime.utcnow(),
                    scan_type="manual",
                    status="completed",
                ),
                OrphanFile(
                    scan_id="scan_1",
                    file_path=str(tmp_path / "original.bin"),
                    file_size=7,
                    downloader_id="dl_001",
                ),
                candidate,
            ]
        )
        await async_orphan_db.commit()

        result = await OrphanFileService(async_orphan_db)._recover_interrupted_operations(_empty_manifest(tmp_path))

        await async_orphan_db.refresh(candidate)
        assert result == {"recovered": 1, "failed": 0}
        assert candidate.status == "quarantined"
        assert candidate.quarantine_path == str(target)
        assert candidate.operation_state == "stable"
        detail = await async_orphan_db.get(OrphanFile, 1)
        assert detail.is_deleted is True
        assert detail.deleted_by == "system:recovery"

    async def test_recovers_crash_after_physical_purge(self, async_orphan_db, tmp_path):
        """remove 已完成但最终 DB 提交前崩溃时，下次维护应标记 purged。"""
        from app.models.orphan_file import OrphanCurrentCandidate
        from app.services.orphan_file_service import OrphanFileService

        missing = tmp_path / ".btdeck_quarantine" / "scan_1" / "missing.bin"
        candidate = OrphanCurrentCandidate(
            canonical_path=str(tmp_path / "original.bin"),
            downloader_id="dl_001",
            status="quarantined",
            file_size=7,
            quarantine_path=str(missing),
            operation_state="purge_pending",
            operation_target_path=str(missing),
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        result = await OrphanFileService(async_orphan_db)._recover_interrupted_operations(_empty_manifest(tmp_path))

        await async_orphan_db.refresh(candidate)
        assert result == {"recovered": 1, "failed": 0}
        assert candidate.status == "purged"
        assert candidate.operation_state == "stable"

    async def test_recovers_purge_pending_from_recorded_quarantine_path_without_manifest(
        self, async_orphan_db, tmp_path
    ):
        """purge_pending 恢复只处理已记录的 tombstone，不应依赖下载器映射。"""
        from app.models.orphan_file import OrphanCurrentCandidate
        from app.services.orphan_file_service import OrphanFileService

        quarantine_root = tmp_path / ".btdeck_quarantine" / "scan_recovery"
        operation_dir = quarantine_root / ("c" * 32)
        operation_dir.mkdir(parents=True)
        original_path = operation_dir / "original.bin"
        tombstone_path = operation_dir / "tombstone.bin"
        tombstone_path.write_bytes(b"recovery")
        tombstone_stat = tombstone_path.stat()
        candidate = OrphanCurrentCandidate(
            canonical_path=str(tmp_path / "Downloads" / "ipan" / "Downloads" / "original.bin"),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=20),
            last_seen_at=datetime.utcnow(),
            status="quarantined",
            file_size=tombstone_stat.st_size,
            mtime_ns=tombstone_stat.st_mtime_ns,
            device_id=tombstone_stat.st_dev,
            inode=tombstone_stat.st_ino,
            quarantine_path=str(original_path),
            quarantine_root=str(quarantine_root),
            operation_state="purge_pending",
            operation_target_path=str(tombstone_path),
        )
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        manifest_builder = AsyncMock(side_effect=AssertionError("purge_pending 恢复不应构建下载器 manifest"))
        with patch.object(service, "_build_realtime_manifest", manifest_builder):
            result = await service._recover_interrupted_operations(
                store=MagicMock(),
                lease_handle=lease,
            )

        await async_orphan_db.refresh(candidate)
        assert result == {"recovered": 1, "failed": 0}
        assert candidate.status == "purged"
        assert candidate.operation_state == "stable"
        assert not tombstone_path.exists()
        assert not quarantine_root.exists()
        manifest_builder.assert_not_awaited()

    async def test_final_commit_failure_keeps_recoverable_pending(self, async_orphan_db, tmp_path):
        """文件已移动但最终提交失败时，候选保持 pending 且明细未删除。"""
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import normalize_path

        source = tmp_path / "commit-failure.bin"
        source.write_bytes(b"payload")
        stat = source.stat()
        root = tmp_path / ".btdeck_quarantine" / "scan_commit"
        candidate = OrphanCurrentCandidate(
            canonical_path=normalize_path(str(source)),
            downloader_id="dl_001",
            last_seen_scan_id="scan_commit",
            file_size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            device_id=stat.st_dev,
            inode=stat.st_ino,
        )
        detail = OrphanFile(
            scan_id="scan_commit",
            file_path=str(source),
            file_size=stat.st_size,
            downloader_id="dl_001",
        )
        async_orphan_db.add_all(
            [
                OrphanScanResult(
                    scan_id="scan_commit",
                    scan_time=datetime.utcnow(),
                    status="completed",
                ),
                detail,
                candidate,
            ]
        )
        await async_orphan_db.commit()
        candidate_path = candidate.canonical_path
        detail_id = detail.id

        original_commit = async_orphan_db.commit
        commit_count = 0

        async def commit_pending_then_fail():
            nonlocal commit_count
            commit_count += 1
            if commit_count == 1:
                await original_commit()
                return
            raise RuntimeError("final commit failed")

        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        with patch.object(
            async_orphan_db,
            "commit",
            side_effect=commit_pending_then_fail,
        ):
            with pytest.raises(RuntimeError, match="final commit failed"):
                await service._quarantine_candidate(
                    candidate,
                    str(source),
                    str(root),
                    scan_id="scan_commit",
                    operator="admin",
                    lease_handle=lease,
                )

        session_factory = async_sessionmaker(
            async_orphan_db.bind,
            expire_on_commit=False,
        )
        async with session_factory() as verification_db:
            persisted_candidate = (
                await verification_db.execute(
                    select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path == candidate_path)
                )
            ).scalar_one()
            persisted_detail = await verification_db.get(OrphanFile, detail_id)

        assert persisted_candidate.operation_state == "quarantine_pending"
        assert persisted_candidate.status == "candidate"
        assert persisted_detail.is_deleted is False
        assert not source.exists()
        assert os.path.exists(persisted_candidate.operation_target_path)

    async def test_lease_loss_after_move_keeps_pending(self, async_orphan_db, tmp_path):
        """rename 后失去 lease 时不得最终化候选或扫描明细。"""
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import normalize_path

        source = tmp_path / "lease-loss.bin"
        source.write_bytes(b"payload")
        stat = source.stat()
        candidate = OrphanCurrentCandidate(
            canonical_path=normalize_path(str(source)),
            downloader_id="dl_001",
            last_seen_scan_id="scan_lease",
            file_size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            device_id=stat.st_dev,
            inode=stat.st_ino,
        )
        detail = OrphanFile(
            scan_id="scan_lease",
            file_path=str(source),
            file_size=stat.st_size,
            downloader_id="dl_001",
        )
        async_orphan_db.add_all(
            [
                OrphanScanResult(
                    scan_id="scan_lease",
                    scan_time=datetime.utcnow(),
                    status="completed",
                ),
                detail,
                candidate,
            ]
        )
        await async_orphan_db.commit()

        lease = MagicMock()
        lease.assert_owned = AsyncMock(side_effect=[None, RuntimeError("lease lost after move")])
        with pytest.raises(RuntimeError, match="lease lost"):
            await OrphanFileService(async_orphan_db)._quarantine_candidate(
                candidate,
                str(source),
                str(tmp_path / ".btdeck_quarantine" / "scan_lease"),
                scan_id="scan_lease",
                operator="admin",
                lease_handle=lease,
            )

        await async_orphan_db.refresh(candidate)
        await async_orphan_db.refresh(detail)
        assert candidate.operation_state == "quarantine_pending"
        assert candidate.status == "candidate"
        assert detail.is_deleted is False
        assert not source.exists()
        assert os.path.exists(candidate.operation_target_path)

    async def test_resolved_recovery_does_not_mark_detail_deleted(self, async_orphan_db, tmp_path):
        """pending 源文件重新被种子引用时只 resolved，不标记扫描明细。"""
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import normalize_path

        source = tmp_path / "referenced-again.bin"
        source.write_bytes(b"payload")
        stat = source.stat()
        target = tmp_path / ".btdeck_quarantine" / "scan_resolved" / source.name
        candidate = OrphanCurrentCandidate(
            canonical_path=normalize_path(str(source)),
            downloader_id="dl_001",
            last_seen_scan_id="scan_resolved",
            file_size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            device_id=stat.st_dev,
            inode=stat.st_ino,
            quarantine_root=str(target.parent),
            operation_state="quarantine_pending",
            operation_target_path=str(target),
        )
        detail = OrphanFile(
            scan_id="scan_resolved",
            file_path=str(source),
            file_size=stat.st_size,
            downloader_id="dl_001",
        )
        async_orphan_db.add_all(
            [
                OrphanScanResult(
                    scan_id="scan_resolved",
                    scan_time=datetime.utcnow(),
                    status="completed",
                ),
                detail,
                candidate,
            ]
        )
        await async_orphan_db.commit()
        manifest = _empty_manifest(tmp_path)
        manifest.expected_paths.add(normalize_path(str(source)))

        result = await OrphanFileService(async_orphan_db)._recover_interrupted_operations(manifest)

        await async_orphan_db.refresh(candidate)
        await async_orphan_db.refresh(detail)
        assert result == {"recovered": 1, "failed": 0}
        assert candidate.status == "resolved"
        assert candidate.operation_state == "stable"
        assert detail.is_deleted is False

    async def test_recovery_rebuilds_manifest_for_all_pending_downloaders(self, async_orphan_db, tmp_path):
        """窄 manifest 不覆盖 pending 下载器时必须按全部下载器重建。"""
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot, normalize_path

        scan = OrphanScanResult(
            scan_id="scan_multi",
            scan_time=datetime.utcnow(),
            status="completed",
        )
        async_orphan_db.add(scan)
        for downloader_id in ("dl_a", "dl_b"):
            source = tmp_path / downloader_id / "source.bin"
            target = tmp_path / "quarantine" / downloader_id / "source.bin"
            target.parent.mkdir(parents=True)
            target.write_bytes(downloader_id.encode())
            stat = target.stat()
            async_orphan_db.add_all(
                [
                    OrphanFile(
                        scan_id="scan_multi",
                        file_path=str(source),
                        file_size=stat.st_size,
                        downloader_id=downloader_id,
                    ),
                    OrphanCurrentCandidate(
                        canonical_path=normalize_path(str(source)),
                        downloader_id=downloader_id,
                        last_seen_scan_id="scan_multi",
                        file_size=stat.st_size,
                        mtime_ns=stat.st_mtime_ns,
                        device_id=stat.st_dev,
                        inode=stat.st_ino,
                        quarantine_root=str(target.parent),
                        purge_after=datetime.utcnow() + timedelta(days=7),
                        operation_state="quarantine_pending",
                        operation_target_path=str(target),
                    ),
                ]
            )
        await async_orphan_db.commit()

        complete_manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[
                (str(tmp_path / "dl_a"), "dl_a"),
                (str(tmp_path / "dl_b"), "dl_b"),
            ],
            downloader_ids={"dl_a", "dl_b"},
        )
        narrow_manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path / "dl_a"), "dl_a")],
            downloader_ids={"dl_a"},
        )
        service = OrphanFileService(async_orphan_db)
        manifest_builder = AsyncMock(return_value=complete_manifest)
        with patch.object(
            service,
            "_build_realtime_manifest",
            manifest_builder,
        ):
            result = await service._recover_interrupted_operations(
                narrow_manifest,
                store=MagicMock(),
            )

        assert result == {"recovered": 2, "failed": 0}
        manifest_builder.assert_awaited_once()
        assert manifest_builder.await_args.args[1] == {"dl_a", "dl_b"}


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
        """扫描与手动清理竞争时共用维护 lease，二者必须互斥。"""
        from app.services.orphan_lease import (
            ORPHAN_MAINTENANCE_LEASE,
            acquire_lease,
            release_lease,
        )

        scan_acquired = await acquire_lease(ORPHAN_MAINTENANCE_LEASE, owner="proc_1", ttl=3600, db=async_orphan_db)
        assert scan_acquired

        cleanup_acquired = await acquire_lease(ORPHAN_MAINTENANCE_LEASE, owner="proc_2", ttl=3600, db=async_orphan_db)
        assert not cleanup_acquired

        await release_lease(ORPHAN_MAINTENANCE_LEASE, owner="proc_1", db=async_orphan_db)

    async def test_atomic_contention_across_two_sqlite_sessions(self, tmp_path):
        """两个独立 DB session 同时争抢同一 lease，恰好一个成功。"""
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.models.orphan_file import OrphanOperationLease
        from app.services.orphan_lease import ORPHAN_MAINTENANCE_LEASE, acquire_lease

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lease.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(OrphanOperationLease.__table__.create)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as first, session_factory() as second:
            acquired = await asyncio.gather(
                acquire_lease(ORPHAN_MAINTENANCE_LEASE, owner="proc_1", ttl=3600, db=first),
                acquire_lease(ORPHAN_MAINTENANCE_LEASE, owner="proc_2", ttl=3600, db=second),
            )

        await engine.dispose()
        assert sum(bool(value) for value in acquired) == 1

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

    # ==================== v1.0.7+ confidence 门槛 ====================

    async def test_cleanup_allows_low_confidence_when_manifest_authorizes(self, async_orphan_db, tmp_path):
        """手动清理放行 low confidence 候选（manifest 授权 + 身份复核通过即可隔离）。

        需求变更：低置信度（离线降级目录粗筛产出）有误判风险，但用户可在前端警告
        确认后主动删除。仅自动清理（get_purgeable_candidates）仍排除 low。
        清理安全底线不变——实时 manifest 复核（expected_paths/路径授权/身份复核）照常拦截。
        """
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanFile,
            OrphanScanResult,
        )
        from app.services.orphan_manifest import ManifestSnapshot, normalize_path

        f = tmp_path / "low_confidence_orphan.bin"
        f.write_bytes(b"x" * 100)
        stat = f.stat()
        canonical = normalize_path(str(f))

        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_low",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        async_orphan_db.add(
            OrphanFile(
                scan_id="scan_low",
                file_path=str(f),
                file_size=stat.st_size,
                mtime=datetime.utcnow(),
                downloader_id="dl_001",
                confidence="low",
            )
        )
        # low confidence 候选：离线降级目录粗筛产出；补全身份字段以通过实时复核。
        async_orphan_db.add(
            OrphanCurrentCandidate(
                canonical_path=canonical,
                downloader_id="dl_001",
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                last_seen_scan_id="scan_low",
                status="candidate",
                operation_state="stable",
                file_size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                device_id=stat.st_dev,
                inode=stat.st_ino,
                confidence="low",
            )
        )
        await async_orphan_db.commit()

        # mock manifest：文件不在 expected（未被种子引用），路径授权通过，confidence=low。
        service = OrphanFileService(async_orphan_db)
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.cleanup_orphans(
                orphan_ids=[1],
                operator="admin",
                store=MagicMock(),
                scan_id="scan_low",
                _lease_acquired=True,
                _lease_handle=lease,
            )

        assert result["success_count"] == 1, "low confidence 在 manifest 授权时应被放行清理"
        assert not any(
            "低置信度" in (item.get("reason") or "") for item in result.get("failed_list", [])
        ), "手动清理不再以低置信度拒绝"
        assert not f.exists(), "文件应已被移入隔离区"


class TestAuthorizeLowConfidence:
    """低置信度分流复核（_authorize_low_confidence）单元测试。

    覆盖三个分支：
    1. downloader 已重新上线（在 manifest.downloader_ids）→ 走标准精筛授权
    2. downloader 仍离线 + 文件不在白名单目录内 → 放行（fail-closed 不拒绝）
    3. downloader 仍离线 + 文件落在白名单目录内 → 拒绝（fail-closed 保护）

    采用纯静态方法测试（staticmethod 无需实例化 service，无需 DB）。
    """

    @staticmethod
    def _make_candidate(canonical_path, downloader_id="dl_001", confidence="low"):
        """构造一个最小 OrphanCurrentCandidate 替身（仅需 downloader_id/canonical_path/confidence）。"""
        from types import SimpleNamespace

        return SimpleNamespace(
            canonical_path=canonical_path,
            downloader_id=downloader_id,
            confidence=confidence,
        )

    def test_online_downloader_uses_standard_path_authorized(self, tmp_path):
        """分支1：downloader 已上线精筛成功（在 downloader_ids）→ 走 _path_authorized。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        candidate = self._make_candidate(str(tmp_path / "orphan.bin"), "dl_001")
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        assert OrphanFileService._authorize_low_confidence(candidate, manifest) is True

    def test_offline_downloader_file_outside_whitelist_allows(self, tmp_path):
        """分支2：downloader 离线 + 文件不在白名单目录内 → 放行。

        典型场景：low 候选的 downloader 仍离线，但文件确实是孤儿（不在任何已知种子目录下）。
        """
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        orphan_file = tmp_path / "real_orphan.bin"
        orphan_file.write_bytes(b"x")
        # 白名单目录指向另一个位置（种子目录），不覆盖孤儿文件
        seed_dir = tmp_path / "downloads" / "seeds"
        seed_dir.mkdir(parents=True)
        candidate = self._make_candidate(str(orphan_file), "dl_offline")
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_offline"}))],
            downloader_ids=set(),  # downloader 离线，不在精筛覆盖集
            directory_whitelist={str(seed_dir)},
        )
        assert OrphanFileService._authorize_low_confidence(candidate, manifest) is True

    def test_offline_downloader_file_in_whitelist_rejects(self, tmp_path):
        """分支3：downloader 离线 + 文件落在白名单目录内 → 拒绝（fail-closed 保护）。

        典型场景：文件恰好落在某个已知种子的目录下，可能仍被引用 → 拒绝删除。
        """
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        seed_dir = tmp_path / "downloads" / "seeds"
        seed_dir.mkdir(parents=True)
        orphan_in_seed_dir = seed_dir / "maybe_orphan.bin"
        orphan_in_seed_dir.write_bytes(b"x")
        candidate = self._make_candidate(str(orphan_in_seed_dir), "dl_offline")
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_offline"}))],
            downloader_ids=set(),  # downloader 离线
            directory_whitelist={str(seed_dir)},
        )
        assert OrphanFileService._authorize_low_confidence(candidate, manifest) is False

    def test_offline_downloader_empty_whitelist_allows(self, tmp_path):
        """边界：downloader 离线 + 白名单为空 → 放行（无已知种子目录需保护）。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        orphan_file = tmp_path / "orphan.bin"
        orphan_file.write_bytes(b"x")
        candidate = self._make_candidate(str(orphan_file), "dl_offline")
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_offline"}))],
            downloader_ids=set(),
            directory_whitelist=set(),
        )
        assert OrphanFileService._authorize_low_confidence(candidate, manifest) is True


def _make_quarantined_candidate(async_orphan_db, tmp_path, *, filename="quarantined_file.mkv", content=b"x" * 100):
    """构造一个已隔离状态的候选 + 文件（直接置入隔离区目录，模拟 cleanup 后的状态）。

    返回 (candidate, canonical_path, quarantine_path, quarantine_root, stat)。
    """
    from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult

    # 原位置（尚不存在）+ 隔离区目录
    canonical = str(tmp_path / filename)
    quarantine_root = str(tmp_path / ".btdeck_quarantine" / "scan_test")
    import os

    os.makedirs(quarantine_root, exist_ok=True)
    # 文件直接放到隔离区内的一个 uuid 子目录（模拟 build_quarantine_path 结构）
    quarantine_path = os.path.join(quarantine_root, "abcdef1234567890", filename)
    os.makedirs(os.path.dirname(quarantine_path), exist_ok=True)
    with open(quarantine_path, "wb") as f:
        f.write(content)
    q_stat = os.stat(quarantine_path)

    old_time = datetime.utcnow() - timedelta(days=10)
    # scan_id 唯一约束：基于 filename 生成，避免同测试多次调用冲突
    scan_id = f"scan_q_{filename}"
    async_orphan_db.add(
        OrphanScanResult(
            scan_id=scan_id,
            scan_time=old_time,
            scan_type="manual",
            status="completed",
        )
    )
    candidate = OrphanCurrentCandidate(
        canonical_path=canonical,
        downloader_id="dl_001",
        first_seen_at=old_time,
        last_seen_at=datetime.utcnow(),
        last_seen_scan_id=scan_id,
        consecutive_scan_count=2,
        status="quarantined",
        operation_state="stable",
        file_size=q_stat.st_size,
        mtime_ns=q_stat.st_mtime_ns,
        device_id=q_stat.st_dev,
        inode=q_stat.st_ino,
        quarantine_path=quarantine_path,
        quarantine_root=quarantine_root,
        quarantined_at=datetime.utcnow(),
        purge_after=datetime.utcnow() + timedelta(days=7),
    )
    # OrphanFile 明细标记为 is_deleted=True（隔离时 _finalize_quarantine 的状态）
    detail = OrphanFile(
        scan_id=scan_id,
        file_path=canonical,
        file_size=q_stat.st_size,
        mtime=datetime.utcnow(),
        downloader_id="dl_001",
        canonical_path=canonical,
    )
    detail.is_deleted = True
    detail.deleted_at = datetime.utcnow()
    detail.deleted_by = "admin"
    async_orphan_db.add(detail)
    async_orphan_db.add(candidate)
    return candidate, canonical, quarantine_path, quarantine_root, q_stat, scan_id


class TestQuarantineManagement:
    """隔离区管理：恢复 / 立即彻底删除 / 列表查询。"""

    async def test_get_quarantine_list_returns_only_quarantined(self, async_orphan_db, tmp_path):
        """列表查询只返回 status=quarantined 的候选。"""
        from app.services.orphan_file_service import OrphanFileService

        _make_quarantined_candidate(async_orphan_db, tmp_path, filename="file_a.mkv")
        _make_quarantined_candidate(async_orphan_db, tmp_path, filename="file_b.mkv")
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.get_quarantine_list(page=1, page_size=20)
        assert result["total"] == 2
        assert len(result["list"]) == 2
        assert all(item["quarantine_path"] for item in result["list"])

    async def test_restore_moves_file_back_and_rolls_back_status(self, async_orphan_db, tmp_path):
        """恢复：文件回到原位 + candidate.status=candidate + is_deleted=False。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.models.orphan_file import OrphanFile
        from sqlalchemy import select

        candidate, canonical, quarantine_path, quarantine_root, _, scan_id = _make_quarantined_candidate(
            async_orphan_db, tmp_path, filename="to_restore.mkv"
        )
        await async_orphan_db.commit()

        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        result = await service.restore_quarantined(
            canonical_paths=[canonical],
            operator="admin",
            _lease_acquired=True,
            _lease_handle=lease,
        )
        assert result["restored_count"] == 1, f"应恢复1个，实际: {result}"
        import os

        assert os.path.exists(canonical), "文件应回到原位"
        assert not os.path.exists(quarantine_path), "隔离区文件应已移走"
        assert not os.path.exists(quarantine_root), "恢复后应清理空操作目录和空 scan_id 目录"

        # 候选状态回滚
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "candidate", "候选应回到 candidate 态"
        assert candidate.quarantine_path is None, "隔离字段应清空"
        # 明细 is_deleted 回滚
        detail = (await async_orphan_db.execute(select(OrphanFile).where(OrphanFile.scan_id == scan_id))).scalar_one()
        assert detail.is_deleted is False, "明细 is_deleted 应回滚为 False"

    async def test_restore_rejects_when_original_path_occupied(self, async_orphan_db, tmp_path):
        """恢复失败-原位被占用：原位置已有文件 → 拒绝恢复（防覆盖）。"""
        from app.services.orphan_file_service import OrphanFileService

        candidate, canonical, quarantine_path, _, _, _ = _make_quarantined_candidate(
            async_orphan_db, tmp_path, filename="occupied.mkv"
        )
        await async_orphan_db.commit()
        # 原位放一个文件
        import os

        with open(canonical, "wb") as f:
            f.write(b"existing")

        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        result = await service.restore_quarantined(
            canonical_paths=[canonical],
            operator="admin",
            _lease_acquired=True,
            _lease_handle=lease,
        )
        assert result["restored_count"] == 0
        assert result["failed_count"] == 1
        assert "原位置已被占用" in result["failed_list"][0]["reason"]
        # 隔离区文件仍在
        assert os.path.exists(quarantine_path)

    async def test_purge_now_physically_deletes(self, async_orphan_db, tmp_path):
        """立即删除：文件物理删除 + candidate.status=purged（mock manifest 授权通过）。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        candidate, canonical, quarantine_path, quarantine_root, _, _ = _make_quarantined_candidate(
            async_orphan_db, tmp_path, filename="to_purge.mkv"
        )
        await async_orphan_db.commit()

        # mock manifest：文件未被引用，路径授权通过
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=lease,
            )
        assert result["purged_count"] == 1, f"应删除1个，实际: {result}"
        import os

        assert not os.path.exists(quarantine_path), "隔离区文件应已物理删除"
        assert not os.path.exists(quarantine_root), "彻底删除后不应留下原目录或 tombstone 空目录"
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "purged"

    async def test_purge_uses_recorded_quarantine_path_when_original_mapping_is_unavailable(
        self, async_orphan_db, tmp_path
    ):
        """隔离后删除只使用记录的隔离路径，不因原始路径映射变化而拼接错误路径。

        原始文件路径可能来自下载器内部路径映射，例如误形成
        ``/Downloads/ipan/Downloads/...``；文件已经移动到
        ``.btdeck_quarantine`` 后，物理删除不应再次用该原始路径做 scan_root
        授权。否则会在当前映射无法覆盖原路径时误报“路径未授权”。
        """
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        candidate, _canonical, quarantine_path, quarantine_root, _, _ = _make_quarantined_candidate(
            async_orphan_db,
            tmp_path,
            filename="Seven.Samurai.1954.mkv",
        )
        # 模拟历史/当前路径映射产生的重复前缀；当前 manifest 的扫描根不再覆盖
        # 这个原始路径，但数据库中记录的隔离物理路径仍然有效。
        candidate.canonical_path = str(tmp_path / "Downloads" / "ipan" / "Downloads" / "Seven.Samurai.1954.mkv")
        await async_orphan_db.commit()

        # 即使当前下载器已降级、实时 manifest 不再包含该下载器，已隔离文件也
        # 必须只按 quarantine_path/quarantine_root 完成物理删除。
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[],
            downloader_ids=set(),
        )
        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[candidate.canonical_path],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=lease,
            )

        assert result["purged_count"] == 1, f"应删除隔离区文件，实际: {result}"
        assert not os.path.exists(quarantine_path)
        assert not os.path.exists(quarantine_root)
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "purged"

    async def test_purge_repairs_legacy_missing_quarantine_identity(self, async_orphan_db, tmp_path):
        """旧版隔离记录缺少身份字段时，按已记录隔离文件补齐后再删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        candidate, canonical, quarantine_path, quarantine_root, q_stat, _ = _make_quarantined_candidate(
            async_orphan_db,
            tmp_path,
            filename="legacy-identity.mkv",
        )
        candidate.mtime_ns = None
        candidate.device_id = None
        candidate.inode = None
        await async_orphan_db.commit()

        # 旧记录的下载器可以不在实时精筛结果中；隔离区删除不依赖它。
        manifest = ManifestSnapshot(expected_paths=set(), scan_roots=[], downloader_ids=set())
        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=lease,
            )

        assert result["purged_count"] == 1, f"旧版记录应可安全清理，实际: {result}"
        assert not os.path.exists(quarantine_path)
        assert not os.path.exists(quarantine_root)
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "purged"
        assert candidate.mtime_ns == q_stat.st_mtime_ns
        assert candidate.device_id == str(q_stat.st_dev)
        assert candidate.inode == str(q_stat.st_ino)

    async def test_purge_rejects_quarantine_path_outside_recorded_root(self, async_orphan_db, tmp_path):
        """隔离记录被篡改到根目录外时必须拒绝删除。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        candidate, canonical, _quarantine_path, quarantine_root, _, _ = _make_quarantined_candidate(
            async_orphan_db,
            tmp_path,
            filename="outside-root.mkv",
        )
        outside_path = tmp_path / "outside-root-target.mkv"
        outside_path.write_bytes(b"must-stay")
        candidate.quarantine_path = str(outside_path)
        await async_orphan_db.commit()

        manifest = ManifestSnapshot(expected_paths=set(), scan_roots=[], downloader_ids=set())
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=MagicMock(assert_owned=AsyncMock()),
            )

        await async_orphan_db.refresh(candidate)
        assert result["purged_count"] == 0
        assert result["failed_count"] == 1
        assert "quarantine_path" in result["failed_list"][0]["reason"]
        assert outside_path.exists()
        assert candidate.status == "quarantined"
        assert os.path.exists(quarantine_root)

    async def test_purge_shared_root_does_not_add_empty_operation_directory(self, async_orphan_db, tmp_path):
        """同一 scan_id 尚有其它文件时，删除一个文件不得让 UUID 目录数量增加。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        first, first_path, _, root, _, _ = _make_quarantined_candidate(async_orphan_db, tmp_path, filename="first.mkv")
        _, _, second_quarantine_path, _, _, _ = _make_quarantined_candidate(
            async_orphan_db, tmp_path, filename="second.mkv"
        )
        await async_orphan_db.commit()
        operation_dirs_before = {entry.name for entry in os.scandir(root) if entry.is_dir()}

        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await OrphanFileService(async_orphan_db).purge_quarantine_now(
                canonical_paths=[first_path],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=lease,
            )

        operation_dirs_after = {entry.name for entry in os.scandir(root) if entry.is_dir()}
        await async_orphan_db.refresh(first)
        assert result["purged_count"] == 1
        assert first.status == "purged"
        assert os.path.exists(second_quarantine_path)
        assert operation_dirs_after == operation_dirs_before

    async def test_purge_prewrite_failure_reclaims_new_empty_tombstone_dir(self, async_orphan_db, tmp_path):
        """journal 预写失败时，build_quarantine_path 新建的空目录必须立即回收。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        _, canonical, quarantine_path, root, _, _ = _make_quarantined_candidate(
            async_orphan_db, tmp_path, filename="prewrite-failure.mkv"
        )
        await async_orphan_db.commit()
        operation_dirs_before = {entry.name for entry in os.scandir(root) if entry.is_dir()}
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        with (
            patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest),
            patch.object(service, "_commit_candidate_state", AsyncMock(side_effect=RuntimeError("db failed"))),
        ):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=lease,
            )

        operation_dirs_after = {entry.name for entry in os.scandir(root) if entry.is_dir()}
        assert result["failed_count"] == 1
        assert os.path.exists(quarantine_path)
        assert operation_dirs_after == operation_dirs_before

    async def test_historical_prune_only_removes_empty_uuid_dirs(self, async_orphan_db, tmp_path):
        """历史清理只移除记录根下的空 UUID 目录，不影响非空隔离文件。"""
        from app.services.orphan_file_service import OrphanFileService

        _, _, quarantine_path, root, _, _ = _make_quarantined_candidate(async_orphan_db, tmp_path, filename="kept.mkv")
        empty_uuid_dir = os.path.join(root, "a" * 32)
        os.mkdir(empty_uuid_dir)
        await async_orphan_db.commit()

        result = await OrphanFileService(async_orphan_db).prune_recorded_empty_quarantine_dirs(_lease_acquired=True)

        assert result["removed_dir_count"] == 1
        assert not os.path.exists(empty_uuid_dir)
        assert os.path.exists(quarantine_path)

    async def test_empty_directory_prune_refuses_path_outside_recorded_root(self, tmp_path):
        """空目录回收不得越过数据库记录的隔离根。"""
        from app.services.orphan_quarantine import prune_empty_quarantine_parents

        recorded_root = tmp_path / "recorded-root"
        outside_dir = tmp_path / "outside" / ("b" * 32)
        recorded_root.mkdir()
        outside_dir.mkdir(parents=True)

        removed = prune_empty_quarantine_parents(
            str(outside_dir / "missing.mkv"),
            str(recorded_root),
        )

        assert removed == 0
        assert recorded_root.exists()
        assert outside_dir.exists()

    async def test_purge_now_rejects_when_referenced_by_torrent(self, async_orphan_db, tmp_path):
        """立即删除保留安全检查：文件被种子引用 → 拒绝删除（fail-closed）。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot, normalize_path

        candidate, canonical, quarantine_path, _, _, _ = _make_quarantined_candidate(
            async_orphan_db, tmp_path, filename="referenced.mkv"
        )
        await async_orphan_db.commit()

        # mock manifest：canonical_path 在 expected_paths 中（被种子引用）
        manifest = ManifestSnapshot(
            expected_paths={normalize_path(canonical)},
            scan_roots=[(str(tmp_path), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        lease = MagicMock()
        lease.assert_owned = AsyncMock()
        service = OrphanFileService(async_orphan_db)
        with patch.object(OrphanFileService, "_build_realtime_manifest", return_value=manifest):
            result = await service.purge_quarantine_now(
                canonical_paths=[canonical],
                operator="admin",
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=lease,
            )
        assert result["purged_count"] == 0, "被种子引用时应拒绝删除"
        assert result["failed_count"] == 1
        import os

        assert os.path.exists(quarantine_path), "文件不应被删除"
