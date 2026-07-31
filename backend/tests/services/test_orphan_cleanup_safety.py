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

    async def test_cleanup_rejects_low_confidence_candidate(self, async_orphan_db, tmp_path):
        """low confidence 候选（离线降级目录粗筛产出）不允许清理，需等下载器上线
        经精筛复核提升为 high 后才可清理。

        回归本案：tr_lpan/tr 映射缺失产出的孤儿是误判，必须阻止其进入清理流程。
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
                file_size=100,
                mtime=datetime.utcnow(),
                downloader_id="dl_001",
                confidence="low",
            )
        )
        # low confidence 候选：离线降级目录粗筛产出
        async_orphan_db.add(
            OrphanCurrentCandidate(
                canonical_path=canonical,
                downloader_id="dl_001",
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                last_seen_scan_id="scan_low",
                status="candidate",
                operation_state="stable",
                file_size=100,
                confidence="low",
            )
        )
        await async_orphan_db.commit()

        # mock manifest：文件不在 expected，路径授权通过（隔离场景），但 confidence=low
        service = OrphanFileService(async_orphan_db)
        manifest = ManifestSnapshot(
            expected_paths=set(),
            scan_roots=[(str(tmp_path), frozenset({"dl_001"}))],
            downloader_ids={"dl_001"},
        )
        with patch.object(
            OrphanFileService, "_build_realtime_manifest", return_value=manifest
        ):
            result = await service.cleanup_orphans(
                orphan_ids=[1],
                operator="admin",
                store=MagicMock(),
                scan_id="scan_low",
                _lease_acquired=True,
            )

        assert result["success_count"] == 0, "low confidence 候选不应被清理"
        assert any(
            "低置信度" in (item.get("reason") or "")
            for item in result.get("failed_list", [])
        ), "应返回低置信度拒绝原因"
        assert f.exists(), "文件不应被删除"
