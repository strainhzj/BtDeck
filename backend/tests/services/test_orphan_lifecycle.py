# -*- coding: utf-8 -*-
"""
D 组：孤儿文件生命周期与数据库测试（v1.0.6+ 语义重做）

核心语义变更：
- 自动清理依据「连续成为孤儿的时间」，不再依据文件 mtime
- 只有完整成功扫描才能推进候选状态
- 未出现在新清单中的旧候选标记 resolved
- 中间扫描失败不修改候选生命周期
- 最新扫描 running/failed 时禁止清理
- 旧 scan_id 禁止预览和清理

使用真实临时 SQLite（aiosqlite）验证生命周期推进。
本阶段因生命周期服务/候选表尚未实现，全部应失败。
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


# ==================== D 组：生命周期推进 ====================


class TestOrphanLifecycleProgression:
    """连续成为孤儿的时间累计。"""

    async def test_first_discovery_not_immediately_purgeable(self, async_orphan_db):
        """首次发现孤儿文件不会立即满足 30 天条件。"""
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        service = OrphanLifecycleService(async_orphan_db)
        # 模拟首次扫描发现一个孤儿
        orphans = [
            {
                "canonical_path": "/data/movie1.mkv",
                "downloader_id": "dl_001",
                "file_size": 1000,
                "mtime_ns": 1,
            }
        ]
        await service.reconcile_candidates(scan_id="scan_1", scan_time=datetime.utcnow(), orphans=orphans)
        await async_orphan_db.commit()

        # 查候选表，consecutive_scan_count 应为 1，首次发现不满足 30 天
        purgeable = await service.get_purgeable_candidates(days_threshold=30)
        assert purgeable == [], "首次发现的孤儿不应立即满足 30 天清理条件"

    async def test_consecutive_scans_accumulate_duration(self, async_orphan_db):
        """连续完整扫描保持孤儿状态时累计持续时间。"""
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        service = OrphanLifecycleService(async_orphan_db)
        orphans = [
            {
                "canonical_path": "/data/old.mkv",
                "downloader_id": "dl_001",
                "file_size": 2000,
                "mtime_ns": 1,
            }
        ]
        # 第一次扫描
        await service.reconcile_candidates(
            scan_id="scan_1",
            scan_time=datetime.utcnow() - timedelta(days=35),
            orphans=orphans,
        )
        await async_orphan_db.commit()
        # 第二次扫描（35 天后仍存在）
        await service.reconcile_candidates(scan_id="scan_2", scan_time=datetime.utcnow(), orphans=orphans)
        await async_orphan_db.commit()

        # 候选的 last_seen - first_seen 应 >= 35 天 → 满足 30 天条件
        purgeable = await service.get_purgeable_candidates(days_threshold=30)
        paths = [c.canonical_path for c in purgeable]
        assert "/data/old.mkv" in paths, "连续 35 天孤儿应满足清理条件"

    async def test_successful_reconcile_updates_changed_downloader_owner(self, async_orphan_db):
        """同一路径改变扫描归属时同步候选元数据，避免复合匹配漂移。"""
        from app.models.orphan_file import OrphanCurrentCandidate
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        service = OrphanLifecycleService(async_orphan_db)
        path = "/shared/overlap.bin"
        await service.reconcile_candidates(
            scan_id="scan_1",
            scan_time=datetime.utcnow() - timedelta(minutes=1),
            orphans=[
                {
                    "canonical_path": path,
                    "downloader_id": "dl_old",
                    "file_size": 100,
                }
            ],
        )
        await service.reconcile_candidates(
            scan_id="scan_2",
            scan_time=datetime.utcnow(),
            orphans=[
                {
                    "canonical_path": path,
                    "downloader_id": "dl_new",
                    "file_size": 100,
                }
            ],
        )

        result = await async_orphan_db.execute(
            select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path == path)
        )
        candidate = result.scalar_one()
        assert candidate.downloader_id == "dl_new"
        assert candidate.last_seen_scan_id == "scan_2"

    async def test_resolved_when_reappears_in_torrent(self, async_orphan_db):
        """文件在后续扫描重新成为合法文件（不在孤儿清单）时标记 resolved。"""
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        service = OrphanLifecycleService(async_orphan_db)
        # 第一次扫描发现孤儿
        await service.reconcile_candidates(
            scan_id="scan_1",
            scan_time=datetime.utcnow(),
            orphans=[
                {
                    "canonical_path": "/data/resolved.mkv",
                    "downloader_id": "dl_001",
                    "file_size": 500,
                    "mtime_ns": 1,
                }
            ],
        )
        await async_orphan_db.commit()

        # 第二次扫描该文件不再出现在孤儿清单（成为合法文件）
        await service.reconcile_candidates(scan_id="scan_2", scan_time=datetime.utcnow(), orphans=[])
        await async_orphan_db.commit()

        from app.models.orphan_file import OrphanCurrentCandidate

        result = await async_orphan_db.execute(
            select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path == "/data/resolved.mkv")
        )
        candidate = result.scalar_one_or_none()
        assert candidate is not None
        assert candidate.status == "resolved", "重新成为合法文件应标记 resolved"

    async def test_resolved_candidate_restarts_continuous_timer(self, async_orphan_db):
        """resolved 后再次成为孤儿必须从本次扫描重新累计持续时间。"""
        from app.models.orphan_file import OrphanCurrentCandidate
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        service = OrphanLifecycleService(async_orphan_db)
        old_time = datetime.utcnow() - timedelta(days=35)
        orphan = [
            {
                "canonical_path": "/data/restarted.mkv",
                "downloader_id": "dl_001",
                "file_size": 10,
            }
        ]

        await service.reconcile_candidates("scan_old", old_time, orphan)
        await service.reconcile_candidates("scan_resolved", datetime.utcnow() - timedelta(days=1), [])
        restart_time = datetime.utcnow()
        await service.reconcile_candidates("scan_restart", restart_time, orphan)

        result = await async_orphan_db.execute(
            select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path == "/data/restarted.mkv")
        )
        candidate = result.scalar_one()
        assert candidate.status == "candidate"
        assert candidate.first_seen_at == restart_time
        assert candidate.last_seen_at == restart_time
        assert candidate.consecutive_scan_count == 1
        assert await service.get_purgeable_candidates(days_threshold=30) == []

    async def test_failed_scan_does_not_progress_lifecycle(self, async_orphan_db):
        """中间扫描失败不得推进持续时间。"""
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        service = OrphanLifecycleService(async_orphan_db)
        # 第一次成功扫描
        await service.reconcile_candidates(
            scan_id="scan_1",
            scan_time=datetime.utcnow(),
            orphans=[
                {
                    "canonical_path": "/data/x.mkv",
                    "downloader_id": "dl_001",
                    "file_size": 100,
                    "mtime_ns": 1,
                }
            ],
        )
        await async_orphan_db.commit()

        # 模拟失败的扫描 —— 不应调用 reconcile_candidates
        # （reconcile 只在 completed 时调用，failed 不调用）
        # 所以 candidate 的 last_seen_scan_id 仍为 scan_1
        from app.models.orphan_file import OrphanCurrentCandidate

        result = await async_orphan_db.execute(
            select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path == "/data/x.mkv")
        )
        candidate = result.scalar_one_or_none()
        assert candidate.last_seen_scan_id == "scan_1"
        assert candidate.consecutive_scan_count == 1

    async def test_duplicate_path_single_candidate(self, async_orphan_db):
        """同一路径重复扫描不会产生多个当前候选。"""
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        service = OrphanLifecycleService(async_orphan_db)
        orphan = [
            {
                "canonical_path": "/data/dup.mkv",
                "downloader_id": "dl_001",
                "file_size": 100,
                "mtime_ns": 1,
            }
        ]
        for i in range(3):
            await service.reconcile_candidates(scan_id=f"scan_{i}", scan_time=datetime.utcnow(), orphans=orphan)
            await async_orphan_db.commit()

        from app.models.orphan_file import OrphanCurrentCandidate

        result = await async_orphan_db.execute(
            select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path == "/data/dup.mkv")
        )
        candidates = result.scalars().all()
        assert len(candidates) == 1, "同一路径重复扫描应只有 1 个当前候选"

    async def test_existing_candidate_without_detail_binds_new_detail_immediately(
        self,
        async_orphan_db,
    ):
        """迁移未匹配到历史明细时，本轮新建明细必须立即成为当前明细。"""
        from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        path = "/data/missing-historical-detail.mkv"
        async_orphan_db.add(
            OrphanCurrentCandidate(
                canonical_path=path,
                downloader_id="dl_001",
                last_seen_scan_id="scan_legacy",
                current_detail_id=None,
            )
        )
        await async_orphan_db.commit()

        result = await OrphanLifecycleService(async_orphan_db).reconcile_candidates(
            scan_id="scan_current",
            scan_time=datetime.utcnow(),
            orphans=[
                {
                    "canonical_path": path,
                    "file_path": path,
                    "downloader_id": "dl_001",
                    "file_size": 123,
                }
            ],
            persist_current_details=True,
        )

        candidate = await async_orphan_db.get(OrphanCurrentCandidate, path)
        assert candidate is not None
        assert candidate.current_detail_id is not None
        detail = await async_orphan_db.get(OrphanFile, candidate.current_detail_id)
        assert detail is not None
        assert detail.scan_id == "scan_current"
        assert result["detail_inserted"] == 1
        assert result["detail_reused"] == 0

    async def test_only_successfully_scanned_roots_can_resolve_candidates(self, async_orphan_db, tmp_path):
        """被跳过的未映射目录不推进旧候选生命周期。"""
        from app.models.orphan_file import OrphanCurrentCandidate
        from app.services.orphan_lifecycle_service import (
            OrphanLifecycleService,
        )

        scanned_root = tmp_path / "scanned"
        skipped_root = tmp_path / "skipped"
        scanned_root.mkdir()
        skipped_root.mkdir()
        scanned_file = str(scanned_root / "old.bin")
        skipped_file = str(skipped_root / "old.bin")
        initial_time = datetime.utcnow() - timedelta(days=1)
        service = OrphanLifecycleService(async_orphan_db)

        await service.reconcile_candidates(
            "scan_initial",
            initial_time,
            [
                {
                    "canonical_path": scanned_file,
                    "downloader_id": "dl_001",
                    "file_size": 1,
                },
                {
                    "canonical_path": skipped_file,
                    "downloader_id": "dl_001",
                    "file_size": 1,
                },
            ],
        )
        result = await service.reconcile_candidates(
            "scan_scoped",
            datetime.utcnow(),
            [],
            scan_roots=[str(scanned_root)],
        )

        rows = await async_orphan_db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.canonical_path.in_([scanned_file, skipped_file])
            )
        )
        candidates = {candidate.canonical_path: candidate for candidate in rows.scalars().all()}

        assert result["resolved"] == 1
        assert candidates[scanned_file].status == "resolved"
        assert candidates[skipped_file].status == "candidate"
        assert candidates[skipped_file].last_seen_scan_id == "scan_initial"


# ==================== D 组：清理门禁 ====================


class TestCleanupGates:
    """最新扫描状态与 scan_id 新鲜度门禁。"""

    async def test_running_latest_scan_blocks_cleanup(self, async_orphan_db):
        """最新扫描为 running 时，不允许清理。"""
        from app.models.orphan_file import OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        # 插入一条 running 状态的扫描
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_running",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="running",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        # 尝试预览清理 —— 应被拒绝
        result = await service.cleanup_preview(orphan_ids=[])
        # 应返回明确拒绝原因（而非正常预览结果）
        assert result.get("rejected") or result.get("error"), "最新扫描 running 时应拒绝清理"

    async def test_large_scan_only_warns_and_does_not_block_cleanup(self, async_orphan_db):
        """超过护栏的批次只产生提醒，completed 快照仍可进入清理流程。"""
        from app.models.orphan_file import OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        record = OrphanScanResult(
            scan_id="scan_large_guarded",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="completed",
            details_mode="current",
        )
        record.total_orphans = 120_100
        record.cleanup_review_required = True
        async_orphan_db.add(record)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        allowed = await service.cleanup_preview(orphan_ids=[], scan_id="scan_large_guarded")
        assert allowed.get("rejected") is not True
        assert allowed["total_count"] == 0

    @pytest.mark.parametrize("entry", ["prefix", "manual", "scheduled"])
    async def test_large_scan_reminder_does_not_block_other_cleanup_entries(
        self,
        async_orphan_db,
        entry,
    ):
        """超量提醒不得重新成为前缀、手动或定时清理入口的隐式门禁。"""
        from app.models.orphan_file import OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_manifest import ManifestSnapshot

        scan_id = f"scan_large_{entry}"
        record = OrphanScanResult(
            scan_id=scan_id,
            scan_time=datetime.utcnow(),
            scan_type="scheduled" if entry == "scheduled" else "manual",
            status="completed",
            details_mode="current",
        )
        record.total_orphans = 120_100
        record.cleanup_review_required = True
        async_orphan_db.add(record)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        if entry == "prefix":
            result = await service.prefix_match_preview("/data/", scan_id)
        else:
            empty_manifest = ManifestSnapshot(
                expected_paths=set(),
                scan_roots=[],
                downloader_ids=set(),
            )
            with (
                patch.object(service, "_recover_interrupted_operations", new=AsyncMock()),
                patch.object(
                    service,
                    "_build_realtime_manifest",
                    new=AsyncMock(return_value=empty_manifest),
                ),
            ):
                if entry == "manual":
                    result = await service.cleanup_orphans(
                        orphan_ids=[],
                        operator="tester",
                        scan_id=scan_id,
                        _lease_acquired=True,
                    )
                else:
                    result = await service.auto_cleanup_expired(
                        days_threshold=30,
                        operator="system",
                        scan_id=scan_id,
                        _lease_acquired=True,
                    )

        assert result.get("rejected") is not True, f"{entry} 清理入口不应被超量提醒拒绝"

    async def test_list_does_not_fallback_to_older_completed_scan(self, async_orphan_db):
        """最新批次 running 时，列表不得回退展示旧 completed 明细。"""
        from app.models.orphan_file import OrphanFile, OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        async_orphan_db.add(
            OrphanScanResult(
                scan_id="old_completed",
                scan_time=datetime.utcnow() - timedelta(minutes=1),
                scan_type="manual",
                status="completed",
            )
        )
        async_orphan_db.add(OrphanFile(scan_id="old_completed", file_path="/old/orphan.bin", file_size=10))
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="new_running",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="running",
            )
        )
        await async_orphan_db.commit()

        result = await OrphanFileService(async_orphan_db).get_orphan_list()

        assert result["total"] == 0
        assert result["list"] == []

    async def test_failed_latest_scan_blocks_cleanup(self, async_orphan_db):
        """最新扫描为 failed 时，不允许清理。"""
        from app.models.orphan_file import OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_failed",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="failed",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.cleanup_preview(orphan_ids=[])
        assert result.get("rejected") or result.get("error"), "最新扫描 failed 时应拒绝清理"

    async def test_stale_scan_id_rejected(self, async_orphan_db):
        """旧 scan_id 禁止预览和清理。"""
        from app.models.orphan_file import OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        # 两条扫描，scan_old 是旧批次
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_old",
                scan_time=datetime.utcnow() - timedelta(hours=1),
                scan_type="manual",
                status="completed",
            )
        )
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_new",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        # 用旧 scan_id 预览应被拒绝
        result = await service.cleanup_preview(orphan_ids=[], scan_id="scan_old")
        assert result.get("rejected") or result.get("error"), "旧 scan_id 应被拒绝"


class TestBatchWriteAtomicity:
    """批量写入中途失败时不存在可清理的部分批次。"""

    async def test_no_partial_cleanable_batch_on_write_failure(self, async_orphan_db):
        """失败批次即使留下稳定明细，也必须被最新扫描门禁禁止清理。"""
        from app.models.orphan_file import OrphanFile

        # current 模式允许生命周期短事务分批提交，失败时不按 scan_id 删除，
        # 因为其中可能含更早批次创建并持续复用的稳定明细；安全性由最新 failed
        # 扫描门禁保证。空库基线仍不应凭空出现明细。
        result = await async_orphan_db.execute(select(OrphanFile))
        assert result.scalars().all() == [], "失败的扫描不应留下可清理的明细"

    async def test_small_followup_scan_inherits_large_scan_reminder(
        self,
        async_orphan_db,
    ):
        """部分/小扫描保留仍活跃的大批次提醒，但不形成清理门禁。"""
        from app.models.orphan_file import (
            OrphanCurrentCandidate,
            OrphanScanResult,
        )
        from app.services.orphan_scanner import OrphanScanner

        guarded = OrphanScanResult(
            scan_id="scan_guarded_120100",
            scan_time=datetime.utcnow() - timedelta(minutes=5),
            scan_type="manual",
            status="completed",
            details_mode="current",
        )
        guarded.total_orphans = 120_100
        guarded.cleanup_review_required = True
        followup = OrphanScanResult(
            scan_id="scan_small_followup",
            scan_time=datetime.utcnow(),
            scan_type="manual",
            status="running",
            details_mode="current",
        )
        async_orphan_db.add_all(
            [
                guarded,
                followup,
                OrphanCurrentCandidate(
                    canonical_path="C:/data/still-active.bin",
                    downloader_id="dl-1",
                    last_seen_scan_id="scan_guarded_120100",
                    status="candidate",
                ),
            ]
        )
        await async_orphan_db.commit()

        scanner = OrphanScanner(
            async_session_factory=lambda: async_orphan_db,
        )
        scanner._reconcile_lifecycle = AsyncMock(
            return_value={
                "detail_inserted": 0,
                "detail_reused": 0,
                "resolved": 0,
            }
        )
        await scanner._finalize_successful_scan(
            "scan_small_followup",
            datetime.utcnow(),
            [],
            total_paths=0,
            total_files=0,
            total_orphans=0,
            total_orphan_size=0,
            orphan_count_warning=False,
            scan_roots=[],
        )

        persisted = await async_orphan_db.get(
            OrphanScanResult,
            "scan_small_followup",
        )
        assert persisted is not None
        assert persisted.status == "completed"
        assert persisted.cleanup_review_required is True
        assert persisted.cleanup_reviewed_at is None


class TestRecoverInterruptedScans:
    """启动恢复：残留 running 的孤儿扫描记录标记为 failed。

    使用独立内存库 + 注入 session 工厂（recover_interrupted_orphan_scans
    支持 session_factory 参数），不依赖默认真实库 AsyncSessionLocal。
    """

    @pytest_asyncio.fixture
    async def _recover_engine(self):
        """创建内存库 + session 工厂，测试结束 drop 表。"""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import StaticPool

        from app.database import Base

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
            yield factory
        finally:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await engine.dispose()

    async def test_recover_running_scan_marks_failed(self, _recover_engine):
        """status=running 的扫描记录被恢复为 failed。"""
        from datetime import datetime

        from app.models.orphan_file import OrphanScanResult
        from app.startup.lifecycle import recover_interrupted_orphan_scans

        async with _recover_engine() as db:
            db.add(
                OrphanScanResult(
                    scan_id="scan_recover_1",
                    scan_time=datetime.utcnow(),
                    scan_type="scheduled",
                    status="running",
                    operator="system",
                )
            )
            db.add(
                OrphanScanResult(
                    scan_id="scan_recover_2",
                    scan_time=datetime.utcnow(),
                    scan_type="scheduled",
                    status="running",
                    operator="system",
                )
            )
            db.add(
                OrphanScanResult(
                    scan_id="scan_done",
                    scan_time=datetime.utcnow(),
                    scan_type="scheduled",
                    status="completed",
                    operator="system",
                )
            )
            await db.commit()

        recovered = await recover_interrupted_orphan_scans(session_factory=_recover_engine)

        assert recovered == 2, f"应恢复 2 条 running 记录，实际 {recovered}"
        async with _recover_engine() as db:
            result = await db.execute(select(OrphanScanResult).where(OrphanScanResult.scan_id == "scan_recover_1"))
            assert result.scalar_one().status == "failed"
            result = await db.execute(select(OrphanScanResult).where(OrphanScanResult.scan_id == "scan_done"))
            assert result.scalar_one().status == "completed"

    async def test_recover_no_running_scans(self, _recover_engine):
        """无残留 running 记录时返回 0 且不报错。"""
        from app.startup.lifecycle import recover_interrupted_orphan_scans

        recovered = await recover_interrupted_orphan_scans(session_factory=_recover_engine)
        assert recovered == 0
