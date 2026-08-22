# -*- coding: utf-8 -*-
"""孤儿文件自动清理忽视态边界回归测试。

本文件是「数据安全底线」的守护测试：被用户忽视的孤儿文件(is_ignored=True)
在任何情况下都不能被定时自动清理任务删除/隔离。覆盖三层防御纵深：

1. SQL 过滤层：get_purgeable_candidates 的 is_ignored==False 子句排除已忽视候选。
2. 服务 E2E 层：auto_cleanup_expired 端到端运行时，已忽视候选不被隔离、文件不移动、
   候选状态不变；与同批可清理候选共存时只清理后者。
3. 防御纵深层：即便绕过 SQL 过滤（直接注入已忽视候选到工作集），循环内的 is_ignored
   守卫仍会拒绝隔离——保证即使 SQL 子句被误删，数据安全底线不破。

另覆盖：
- reconcile_candidates 的 resolved→candidate 重新出现时 is_ignored 重置（避免忽视粘住）。
- purge_expired_quarantine 不误伤已忽视候选（已忽视候选永不进入 quarantined 态）。
- cleanup_orphans(手动清理) 已忽视项被循环守卫拒绝（补齐与 preview 对称的端到端断言）。
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_lifecycle_service import OrphanLifecycleService

pytestmark = pytest.mark.asyncio


# ==================== 公共辅助 ====================


def _empty_manifest(root, downloader_id="dl_001"):
    """构造一个空的实时 manifest（无文件被种子引用，单一扫描根）。"""
    from app.services.orphan_manifest import ManifestSnapshot

    return ManifestSnapshot(
        expected_paths=set(),
        scan_roots=[(str(root), frozenset({downloader_id}))],
        downloader_ids={downloader_id},
    )


def _make_fake_lease():
    """构造隔离所需的 lease 句柄 mock。

    _quarantine_candidate 会 await lease_handle.assert_owned() 校验归属，
    必须是 AsyncMock。无 pending 候选时不会被调用。
    """
    lease = MagicMock()
    lease.assert_owned = AsyncMock()
    return lease


def _seed_completed_scan(db, scan_id="scan_1", *, days_ago=35):
    """写入一条 completed 扫描批次（满足清理新鲜度门禁）。"""
    db.add(
        OrphanScanResult(
            scan_id=scan_id,
            scan_time=datetime.utcnow() - timedelta(days=days_ago),
            scan_type="scheduled",
            status="completed",
        )
    )


def _make_candidate(
    path,
    *,
    ignored=False,
    downloader_id="dl_001",
    status="candidate",
    operation_state="stable",
    confidence="high",
    stat=None,
    first_seen_at=None,
    last_seen_at=None,
    scan_id="scan_1",
):
    """构造一个满足 35 天阈值的候选。

    默认 first_seen_at=35天前、last_seen_at=now，使 (last-first)>=30 天的二次校验通过。
    若提供 stat（os.stat 结果），则填入 file_size/mtime_ns/device_id/inode 身份字段。
    """
    now = datetime.utcnow()
    cand = OrphanCurrentCandidate(
        canonical_path=str(path),
        downloader_id=downloader_id,
        first_seen_at=first_seen_at or (now - timedelta(days=35)),
        last_seen_at=last_seen_at or now,
        last_seen_scan_id=scan_id,
        consecutive_scan_count=2,
        status=status,
        operation_state=operation_state,
        confidence=confidence,
        is_ignored=ignored,
    )
    if ignored:
        cand.ignored_at = now
        cand.ignored_by = "tester"
    if stat is not None:
        cand.file_size = stat.st_size
        cand.mtime_ns = stat.st_mtime_ns
        cand.device_id = str(stat.st_dev)
        cand.inode = str(stat.st_ino)
    else:
        cand.file_size = 100
    return cand


async def _refresh(db, obj):
    """提交后刷新 ORM 对象（fixture 用 expire_on_commit=False，但显式刷新更稳妥）。"""
    await db.refresh(obj)


# ==================== 1. SQL 过滤层 ====================


class TestGetPurgeableCandidatesIgnoresFilter:
    """get_purgeable_candidates 必须排除 is_ignored=True 的候选。"""

    async def test_ignored_candidate_excluded_from_purgeable(self, async_orphan_db):
        """被忽视的候选即使满足天数阈值，也不进入可清理集合。"""
        ignored = _make_candidate("/data/ignored.mkv", ignored=True)
        cleanable = _make_candidate("/data/cleanable.mkv", ignored=False)
        async_orphan_db.add_all([ignored, cleanable])
        await async_orphan_db.commit()

        purgeable = await OrphanLifecycleService(async_orphan_db).get_purgeable_candidates(days_threshold=30)
        paths = {c.canonical_path for c in purgeable}

        assert "/data/cleanable.mkv" in paths, "未忽视候选应可清理"
        assert "/data/ignored.mkv" not in paths, "已忽视候选绝不可清理"

    async def test_all_ignored_yields_empty_purgeable(self, async_orphan_db):
        """全部被忽视时，可清理集合必须为空。"""
        async_orphan_db.add_all(
            [
                _make_candidate("/data/a.mkv", ignored=True),
                _make_candidate("/data/b.mkv", ignored=True),
            ]
        )
        await async_orphan_db.commit()

        purgeable = await OrphanLifecycleService(async_orphan_db).get_purgeable_candidates(days_threshold=30)
        assert purgeable == [], "全部已忽视时不应有任何可清理候选"

    async def test_ignored_candidate_kept_after_unignore(self, async_orphan_db):
        """取消忽视后，候选重新进入可清理集合（忽视态可逆）。"""
        candidate = _make_candidate("/data/revived.mkv", ignored=True)
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        # 忽视态：不可清理
        assert await OrphanLifecycleService(async_orphan_db).get_purgeable_candidates(30) == []

        # 取消忽视
        candidate.is_ignored = False
        candidate.ignored_at = None
        candidate.ignored_by = None
        await async_orphan_db.commit()

        purgeable = await OrphanLifecycleService(async_orphan_db).get_purgeable_candidates(30)
        assert any(c.canonical_path == "/data/revived.mkv" for c in purgeable), "取消忽视后应可清理"


class TestGetPurgeableCandidatesConfidenceFilter:
    """get_purgeable_candidates 必须排除 low confidence 候选（自动清理安全底线）。

    与手动清理(cleanup_orphans 放行 low)对偶：自动清理(定时任务)仍只清理 high confidence，
    low（离线降级目录粗筛产出）需等下载器上线精筛复核提升为 high 后才可自动清理。
    本类守护 orphan_lifecycle_service.get_purgeable_candidates 的 confidence=='high' 子句，
    防止该安全限制被误删。
    """

    async def test_low_confidence_excluded_even_if_meeting_threshold(self, async_orphan_db):
        """low confidence 候选满足天数/状态/未忽视，仍不得进入可清理集合。"""
        low = _make_candidate("/data/low.mkv", confidence="low")
        high = _make_candidate("/data/high.mkv", confidence="high")
        async_orphan_db.add_all([low, high])
        await async_orphan_db.commit()

        purgeable = await OrphanLifecycleService(async_orphan_db).get_purgeable_candidates(days_threshold=30)
        paths = {c.canonical_path for c in purgeable}

        assert "/data/high.mkv" in paths, "high confidence 候选应可自动清理"
        assert "/data/low.mkv" not in paths, "low confidence 候选绝不可自动清理（离线粗筛有误判风险）"

    async def test_all_low_yields_empty_purgeable(self, async_orphan_db):
        """全部 low confidence 时，可清理集合必须为空。"""
        async_orphan_db.add_all(
            [
                _make_candidate("/data/low_a.mkv", confidence="low"),
                _make_candidate("/data/low_b.mkv", confidence="low"),
            ]
        )
        await async_orphan_db.commit()

        purgeable = await OrphanLifecycleService(async_orphan_db).get_purgeable_candidates(days_threshold=30)
        assert purgeable == [], "全部 low confidence 时不应有任何可清理候选"


# ==================== 2. 服务 E2E 层 ====================


class TestAutoCleanupExpiredIgnoresProtection:
    """auto_cleanup_expired 端到端：已忽视候选不被隔离，文件不被移动。"""

    async def test_ignored_candidate_not_quarantined_file_preserved(self, async_orphan_db, tmp_path):
        """核心安全断言：已忽视候选运行自动清理后，文件仍在原处、候选状态不变。"""
        src = tmp_path / "protected.mkv"
        src.write_bytes(b"x" * 100)
        stat = src.stat()

        _seed_completed_scan(async_orphan_db)
        candidate = _make_candidate(src, ignored=True, stat=stat)
        async_orphan_db.add(candidate)
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
                _lease_acquired=True,
                _lease_handle=_make_fake_lease(),
            )

        # 未隔离任何文件
        assert result["quarantined_count"] == 0
        # 文件未被移动（仍在原路径）
        assert src.exists(), "被忽视的文件绝不能被移动/删除"
        # 候选仍为 candidate + 忽视态保留
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "candidate"
        assert candidate.is_ignored is True
        assert candidate.quarantine_path is None
        assert candidate.operation_state == "stable"

    async def test_mixed_batch_only_cleans_non_ignored(self, async_orphan_db, tmp_path):
        """同一批次：已忽视候选被跳过，未忽视候选被正常隔离。"""
        ignored_src = tmp_path / "ignored.bin"
        cleanable_src = tmp_path / "cleanable.bin"
        ignored_src.write_bytes(b"x" * 100)
        cleanable_src.write_bytes(b"y" * 200)
        cleanable_stat = cleanable_src.stat()

        _seed_completed_scan(async_orphan_db)
        ignored_cand = _make_candidate(ignored_src, ignored=True, stat=ignored_src.stat())
        cleanable_cand = _make_candidate(cleanable_src, ignored=False, stat=cleanable_stat)
        # 可清理候选需要配套的 OrphanFile 明细（隔离最终化按同批次/同下载器/同路径找明细）
        cleanable_detail = OrphanFile(
            scan_id="scan_1",
            file_path=str(cleanable_src),
            file_size=200,
            mtime=datetime.fromtimestamp(cleanable_stat.st_mtime),
            downloader_id="dl_001",
            confidence="high",
            canonical_path=str(cleanable_src),
        )
        async_orphan_db.add_all([ignored_cand, cleanable_cand, cleanable_detail])
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(tmp_path)),
        ):
            result = await service.auto_cleanup_expired(
                days_threshold=30,
                store=MagicMock(),
                scan_id="scan_1",
                _lease_acquired=True,
                _lease_handle=_make_fake_lease(),
            )

        assert result["quarantined_count"] == 1, "仅未忽视候选应被隔离"
        # 忽视文件保留，可清理文件被移走
        assert ignored_src.exists(), "已忽视文件必须保留原处"
        assert not cleanable_src.exists(), "未忽视候选应被移入隔离区"
        await async_orphan_db.refresh(ignored_cand)
        await async_orphan_db.refresh(cleanable_cand)
        assert ignored_cand.status == "candidate" and ignored_cand.is_ignored is True
        assert cleanable_cand.status == "quarantined"

    async def test_no_ignored_in_purgeable_short_circuits(self, async_orphan_db):
        """全部候选被忽视时，auto_cleanup_expired 走「无可清理」分支，零隔离。"""
        _seed_completed_scan(async_orphan_db)
        async_orphan_db.add_all(
            [
                _make_candidate("/data/a.mkv", ignored=True),
                _make_candidate("/data/b.mkv", ignored=True),
            ]
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest("/tmp")),
        ):
            result = await service.auto_cleanup_expired(
                days_threshold=30,
                store=MagicMock(),
                scan_id="scan_1",
                _lease_acquired=True,
            )

        assert result["quarantined_count"] == 0
        assert result["failed_count"] == 0


# ==================== 3. 防御纵深层（绕过 SQL 后循环守卫仍拦截）====================


class TestAutoCleanupDefenseInDepth:
    """即便 SQL 过滤被旁路，循环内的 is_ignored 守卫仍拒绝隔离已忽视候选。

    这是数据安全底线的第二道防线：防止未来改动误删 is_ignored==False 子句后，
    被忽视的文件被静默隔离/删除。
    """

    async def test_injected_ignored_candidate_blocked_in_loop(self, async_orphan_db, tmp_path):
        """绕过 get_purgeable_candidates（直接注入已忽视候选到工作集），循环守卫仍拒绝。"""
        src = tmp_path / "force_injected.mkv"
        src.write_bytes(b"x" * 100)
        stat = src.stat()

        _seed_completed_scan(async_orphan_db)
        candidate = _make_candidate(src, ignored=True, stat=stat)
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        manifest = _empty_manifest(tmp_path)

        # 直接 mock get_purgeable_candidates 返回包含已忽视候选的工作集，
        # 模拟「SQL 过滤被误删」的最坏情况，验证循环内守卫仍是有效防线。
        with (
            patch.object(OrphanLifecycleService, "get_purgeable_candidates", AsyncMock(return_value=[candidate])),
            patch.object(service, "_build_realtime_manifest", AsyncMock(return_value=manifest)),
        ):
            result = await service.auto_cleanup_expired(
                days_threshold=30,
                store=MagicMock(),
                scan_id="scan_1",
                _lease_acquired=True,
                _lease_handle=_make_fake_lease(),
            )

        # 循环守卫拒绝隔离，计入 failed，文件保留
        assert result["quarantined_count"] == 0
        assert result["failed_count"] == 1
        assert src.exists(), "即便 SQL 被旁路，循环守卫仍须保留被忽视文件"
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "candidate", "被忽视候选不得被改为 quarantined"
        assert candidate.is_ignored is True


# ==================== 4. 生命周期：resolved→candidate 重置 is_ignored ====================


class TestReconcileResetsIgnoreOnReappearance:
    """文件被种子引用(resolved)后又重新成为孤儿时，忽视标记应重置（避免粘住）。"""

    async def test_resolved_then_reappears_clears_ignore(self, async_orphan_db):
        """已忽视的候选被种子引用(resolved)→再次成为孤儿(candidate)，is_ignored 应重置。"""
        now = datetime.utcnow()
        # 初始：一个已忽视的 candidate
        candidate = _make_candidate("/data/revive.mkv", ignored=True)
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()
        assert candidate.is_ignored is True

        # 第一次扫描：文件不在孤儿清单 → 标记 resolved（被种子引用）
        service = OrphanLifecycleService(async_orphan_db)
        await service.reconcile_candidates(
            scan_id="scan_resolved",
            scan_time=now,
            orphans=[],
            scan_roots=["/data"],
        )
        await async_orphan_db.commit()
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "resolved"
        # resolved 阶段 is_ignored 保留（用户标记不因种子引用而丢失）
        assert candidate.is_ignored is True

        # 第二次扫描：文件重新成为孤儿 → resolved→candidate，is_ignored 应重置
        await service.reconcile_candidates(
            scan_id="scan_reappears",
            scan_time=now,
            orphans=[
                {
                    "canonical_path": "/data/revive.mkv",
                    "downloader_id": "dl_001",
                    "file_size": 100,
                    "confidence": "high",
                }
            ],
            scan_roots=["/data"],
        )
        await async_orphan_db.commit()
        await async_orphan_db.refresh(candidate)

        assert candidate.status == "candidate", "重新成为孤儿应回到 candidate"
        assert candidate.is_ignored is False, "重新出现应清除忽视标记，重新评估"
        assert candidate.ignored_at is None
        assert candidate.ignored_by is None
        assert candidate.consecutive_scan_count == 1, "连续计数应重置"

    async def test_persistently_orphaned_keeps_ignore(self, async_orphan_db):
        """持续是孤儿(未经历 resolved)的候选，再次扫描不应清除忽视标记。"""
        now = datetime.utcnow()
        candidate = _make_candidate("/data/persistent.mkv", ignored=True)
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanLifecycleService(async_orphan_db)
        # 再次扫描，文件仍是孤儿（candidate→candidate 更新分支）
        await service.reconcile_candidates(
            scan_id="scan_again",
            scan_time=now,
            orphans=[
                {
                    "canonical_path": "/data/persistent.mkv",
                    "downloader_id": "dl_001",
                    "file_size": 100,
                }
            ],
            scan_roots=["/data"],
        )
        await async_orphan_db.commit()
        await async_orphan_db.refresh(candidate)

        assert candidate.status == "candidate"
        assert candidate.is_ignored is True, "未经历 resolved 的持续孤儿，忽视标记应保留"


# ==================== 5. purge_expired_quarantine 不误伤已忽视候选 ====================


class TestPurgeExpiredQuarantineDoesNotTouchIgnored:
    """purge_expired_quarantine 只处理 quarantined 态；已忽视候选(始终 candidate)永不被 purge。"""

    async def test_ignored_candidate_never_purged(self, async_orphan_db, tmp_path):
        """已忽视候选不会被物理删除任务触及（它从不进入 quarantined 态）。"""
        src = tmp_path / "never_purge.mkv"
        src.write_bytes(b"x" * 100)

        _seed_completed_scan(async_orphan_db)
        candidate = _make_candidate(src, ignored=True, stat=src.stat())
        # 模拟一个「过期」的 purge_after，验证即便如此也不被 purge（因为不是 quarantined）
        candidate.purge_after = datetime.utcnow() - timedelta(days=1)
        async_orphan_db.add(candidate)
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(tmp_path)),
        ):
            result = await service.purge_expired_quarantine(
                store=MagicMock(),
                _lease_acquired=True,
                _lease_handle=_make_fake_lease(),
            )

        assert result["purged_count"] == 0
        assert src.exists(), "已忽视候选绝不被物理删除"
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "candidate"


# ==================== 6. 手动清理循环守卫（与 preview 对称的 E2E）====================


class TestManualCleanupIgnoresProtection:
    """cleanup_orphans(手动清理) 循环守卫拒绝已忽视候选（补齐 preview 之外的 E2E 断言）。"""

    async def test_manual_cleanup_blocks_ignored_candidate(self, async_orphan_db, tmp_path):
        """手动清理选中已忽视项时，该项被拒绝并计入 failed_list，文件保留。"""
        from app.services.orphan_manifest import normalize_path

        src = tmp_path / "manual_protected.mkv"
        src.write_bytes(b"x" * 100)
        stat = src.stat()

        _seed_completed_scan(async_orphan_db)
        # 手动清理按 normalize_path(file_path)==canonical_path 匹配候选，
        # 故候选 canonical_path 必须用规范化路径。
        candidate = OrphanCurrentCandidate(
            canonical_path=normalize_path(str(src)),
            downloader_id="dl_001",
            first_seen_at=datetime.utcnow() - timedelta(days=35),
            last_seen_at=datetime.utcnow(),
            last_seen_scan_id="scan_1",
            consecutive_scan_count=2,
            status="candidate",
            operation_state="stable",
            confidence="high",
            file_size=100,
            mtime_ns=stat.st_mtime_ns,
            device_id=str(stat.st_dev),
            inode=str(stat.st_ino),
            is_ignored=True,
        )
        candidate.ignored_at = datetime.utcnow()
        candidate.ignored_by = "tester"
        detail = OrphanFile(
            scan_id="scan_1",
            file_path=str(src),
            file_size=100,
            mtime=datetime.fromtimestamp(stat.st_mtime),
            downloader_id="dl_001",
            confidence="high",
            canonical_path=normalize_path(str(src)),
        )
        async_orphan_db.add_all([candidate, detail])
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        with patch.object(
            service,
            "_build_realtime_manifest",
            AsyncMock(return_value=_empty_manifest(tmp_path)),
        ):
            result = await service.cleanup_orphans(
                orphan_ids=[detail.id],
                operator="alice",
                store=MagicMock(),
                scan_id="scan_1",
                _lease_acquired=True,
                _lease_handle=_make_fake_lease(),
            )

        assert result["success_count"] == 0
        assert result["failed_count"] == 1
        assert any(
            "忽视" in item["reason"] for item in result["failed_list"]
        ), f"应因忽视被拒，实际 failed_list: {result['failed_list']}"
        assert src.exists(), "手动清理也不得移动/删除被忽视文件"
        await async_orphan_db.refresh(candidate)
        assert candidate.status == "candidate"
        assert candidate.is_ignored is True
