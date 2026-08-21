# -*- coding: utf-8 -*-
"""孤儿硬链接副本预扫描定时任务的性能护栏与结果落库回归。"""

import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.models.orphan_hardlink_copy import OrphanHardlinkCopyResult, OrphanHardlinkScanState
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_hardlink_scan_service import OrphanHardlinkScanService
from app.services.orphan_manifest import normalize_path
from app.services.orphan_quarantine import find_hardlink_paths, find_hardlink_paths_bounded

pytestmark = pytest.mark.asyncio


async def _add_candidate(db, scan, file_path: str, *, status: str = "candidate", ignored: bool = False) -> OrphanFile:
    detail = OrphanFile(
        scan_id=scan.scan_id,
        file_path=file_path,
        file_size=10,
        downloader_id="dl_001",
        canonical_path=normalize_path(file_path),
    )
    db.add(detail)
    await db.flush()
    candidate = OrphanCurrentCandidate(
        canonical_path=normalize_path(file_path),
        downloader_id="dl_001",
        first_seen_at=datetime.utcnow() - timedelta(days=1),
        last_seen_at=datetime.utcnow(),
        status=status,
        operation_state="stable",
        confidence="high",
        current_detail_id=detail.id,
        is_ignored=ignored,
    )
    if ignored:
        candidate.ignored_at = datetime.utcnow()
        candidate.ignored_by = "tester"
    db.add(candidate)
    return detail


async def _make_scan(db) -> OrphanScanResult:
    scan = OrphanScanResult(
        scan_id=f"scan_hl_{datetime.utcnow().timestamp()}",
        scan_time=datetime.utcnow(),
        scan_type="manual",
        status="completed",
    )
    db.add(scan)
    await db.flush()
    return scan


# ==================== 限时遍历护栏 ====================


class TestBoundedWalk:
    def test_expired_deadline_returns_partial_with_budget_note(self, tmp_path):
        """截止时间已过：不抛异常，返回空结果并给全部目标 budget_exceeded。"""
        source = tmp_path / "linked.mkv"
        source.write_bytes(b"x")
        os.link(source, tmp_path / "copy.mkv")
        identity = (int(os.stat(source).st_dev), int(os.stat(source).st_ino))

        found, notes = find_hardlink_paths_bounded({identity}, [str(tmp_path)], deadline=time.monotonic() - 1)

        assert found == {identity: []}
        assert notes == {identity: "budget_exceeded"}

    def test_path_cap_marks_truncated_and_keeps_other_targets(self, tmp_path):
        """单目标路径数达上限被截断，但同轮其它目标不受影响。"""
        first = tmp_path / "first.mkv"
        first.write_bytes(b"x")
        os.link(first, tmp_path / "first-2.mkv")
        os.link(first, tmp_path / "first-3.mkv")
        second = tmp_path / "second.mkv"
        second.write_bytes(b"y")
        os.link(second, tmp_path / "second-2.mkv")

        found, notes = find_hardlink_paths_bounded(
            {
                (int(os.stat(first).st_dev), int(os.stat(first).st_ino)),
                (int(os.stat(second).st_dev), int(os.stat(second).st_ino)),
            },
            [str(tmp_path)],
            max_paths_per_target=3,
        )

        first_identity = (int(os.stat(first).st_dev), int(os.stat(first).st_ino))
        second_identity = (int(os.stat(second).st_dev), int(os.stat(second).st_ino))
        assert len(found[first_identity]) == 3
        assert notes[first_identity] == "truncated"
        assert len(found[second_identity]) == 2
        assert notes.get(second_identity) is None

    def test_unbounded_parity_when_no_limits(self, tmp_path):
        source = tmp_path / "linked.mkv"
        source.write_bytes(b"x")
        os.link(source, tmp_path / "copy.mkv")
        identity = (int(os.stat(source).st_dev), int(os.stat(source).st_ino))

        found, notes = find_hardlink_paths_bounded({identity}, [str(tmp_path)])

        assert found == find_hardlink_paths({identity}, [str(tmp_path)])
        assert notes == {}

    def test_mid_walk_deadline_keeps_completed_root_partial(self, tmp_path):
        """中途截止：已完成扫描根的结果保留，剩余根停止并标记 budget_exceeded。"""
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        source = root_a / "linked.mkv"
        source.write_bytes(b"x")
        os.link(source, root_b / "linked-copy.mkv")
        identity = (int(os.stat(source).st_dev), int(os.stat(source).st_ino))

        # 受控时钟：root_a 目录检查=0.0（未超时），root_b 检查=1.0（超过 0.5 截止）
        ticks = iter([0.0, 1.0])

        def fake_monotonic() -> float:
            return next(ticks, 999.0)

        with patch("app.services.orphan_quarantine.time.monotonic", side_effect=fake_monotonic):
            found, notes = find_hardlink_paths_bounded({identity}, [str(root_a), str(root_b)], deadline=0.5)

        assert found[identity] == [os.path.realpath(str(source))]
        assert notes == {identity: "budget_exceeded"}

    def test_truncated_note_survives_budget_stop(self, tmp_path):
        """已达路径上限的目标即使随后预算截止，note 仍为 truncated。"""
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        source = root_a / "many.mkv"
        source.write_bytes(b"x")
        for index in range(2):
            os.link(source, root_a / f"many-{index}.mkv")
        (root_b / "unused.mkv").write_bytes(b"y")
        identity = (int(os.stat(source).st_dev), int(os.stat(source).st_ino))

        ticks = iter([0.0, 1.0])

        def fake_monotonic() -> float:
            return next(ticks, 999.0)

        with patch("app.services.orphan_quarantine.time.monotonic", side_effect=fake_monotonic):
            found, notes = find_hardlink_paths_bounded(
                {identity}, [str(root_a), str(root_b)], deadline=0.5, max_paths_per_target=2
            )

        assert len(found[identity]) == 2
        assert notes == {identity: "truncated"}


# ==================== 定时任务落库 ====================


class TestScanRound:
    async def test_round_walks_linked_writes_trivial_and_advances_cursor(self, async_orphan_db, tmp_path):
        """多副本身份进入遍历并保留全部物理路径；单链接写平凡 0 副本；游标推进。"""
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        downloads.mkdir()
        library.mkdir()
        linked = downloads / "linked.mkv"
        linked.write_bytes(b"linked")
        stored_copy = library / "linked-copy.mkv"
        os.link(linked, stored_copy)
        solo = downloads / "solo.mkv"
        solo.write_bytes(b"solo")
        gone = downloads / "gone.mkv"

        scan = await _make_scan(async_orphan_db)
        linked_detail = await _add_candidate(async_orphan_db, scan, str(linked))
        solo_detail = await _add_candidate(async_orphan_db, scan, str(solo))
        await _add_candidate(async_orphan_db, scan, str(gone))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with patch(
            "app.services.orphan_hardlink_scan_service.collect_runtime_accessible_roots",
            return_value=[str(downloads), str(library)],
        ):
            summary = await service.run_round()

        assert summary["status"] == "success"
        assert summary["stat_inspected"] == 2
        assert summary["stat_failed"] == 1
        assert summary["walk_targets"] == 1
        assert summary["rows_written"] == 2
        # 从游标 0 单页覆盖全部候选：回绕到 0 且不写游标
        assert summary["cursor_advanced_to"] is None
        assert summary["cursor_wrapped"] is False

        linked_stat = os.stat(linked)
        result_rows = {
            (int(row.device_id), int(row.inode_id)): row
            for row in (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        }
        linked_row = result_rows[(int(linked_stat.st_dev), int(linked_stat.st_ino))]
        assert sorted(linked_row.copies, key=os.path.normcase) == sorted(
            [os.path.realpath(str(linked)), os.path.realpath(str(stored_copy))], key=os.path.normcase
        )
        assert linked_row.copy_count == 1
        assert linked_row.scan_note is None

        solo_stat = os.stat(solo)
        solo_row = result_rows[(int(solo_stat.st_dev), int(solo_stat.st_ino))]
        assert solo_row.copy_count == 0
        assert solo_row.copies == []

        # 接口层立即读到落库结果，且过滤源路径本身
        api = await OrphanFileService(async_orphan_db).get_hardlink_copy_locations([linked_detail.id, solo_detail.id])
        by_id = {item["orphan_id"]: item for item in api["items"]}
        assert by_id[linked_detail.id]["copies"] == [os.path.realpath(str(stored_copy))]
        assert by_id[linked_detail.id]["pending_scan"] is False
        assert by_id[linked_detail.id]["scanned_at"] is not None
        assert by_id[solo_detail.id]["copy_count"] == 0

    async def test_round_refreshes_detail_snapshot_counts(self, async_orphan_db, tmp_path):
        """每轮 stat 的权威 st_nlink-1 同步刷回明细快照列；stat 失败行不动。"""
        downloads = tmp_path / "downloads"
        library = tmp_path / "library"
        downloads.mkdir()
        library.mkdir()
        linked = downloads / "linked.mkv"
        linked.write_bytes(b"linked")
        os.link(linked, library / "linked-copy.mkv")
        solo = downloads / "solo.mkv"
        solo.write_bytes(b"solo")
        gone = downloads / "gone.mkv"

        scan = await _make_scan(async_orphan_db)
        linked_detail = await _add_candidate(async_orphan_db, scan, str(linked))
        linked_detail.hardlink_copy_count = 5  # 过期偏大快照
        solo_detail = await _add_candidate(async_orphan_db, scan, str(solo))
        gone_detail = await _add_candidate(async_orphan_db, scan, str(gone))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with patch(
            "app.services.orphan_hardlink_scan_service.collect_runtime_accessible_roots",
            return_value=[str(downloads), str(library)],
        ):
            summary = await service.run_round()

        assert summary["status"] == "success"
        assert summary["details_refreshed"] == 2  # linked 5→1、solo None→0；gone stat 失败不计数

        await async_orphan_db.refresh(linked_detail)
        await async_orphan_db.refresh(solo_detail)
        await async_orphan_db.refresh(gone_detail)
        assert linked_detail.hardlink_copy_count == 1
        assert solo_detail.hardlink_copy_count == 0
        assert gone_detail.hardlink_copy_count is None

    async def test_walk_limit_defers_extra_targets_keeps_existing_rows(self, async_orphan_db, tmp_path):
        """遍历上限外的多副本身份本轮不遍历；已有旧结果不被覆盖，无结果则等待。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        first = downloads / "first.mkv"
        first.write_bytes(b"x")
        os.link(first, downloads / "first-copy.mkv")
        second = downloads / "second.mkv"
        second.write_bytes(b"y")
        os.link(second, downloads / "second-copy.mkv")

        scan = await _make_scan(async_orphan_db)
        first_detail = await _add_candidate(async_orphan_db, scan, str(first))
        second_detail = await _add_candidate(async_orphan_db, scan, str(second))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with (
            patch(
                "app.services.orphan_hardlink_scan_service.collect_runtime_accessible_roots",
                return_value=[str(downloads)],
            ),
            patch.object(settings, "ORPHAN_HARDLINK_SCAN_MAX_TARGETS", 1),
        ):
            summary = await service.run_round()

        assert summary["walk_targets"] == 1
        assert summary["rows_deferred"] == 1

        rows = (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        assert len(rows) == 1
        api = await OrphanFileService(async_orphan_db).get_hardlink_copy_locations([first_detail.id, second_detail.id])
        pending_flags = {item["orphan_id"]: item["pending_scan"] for item in api["items"]}
        assert sorted(pending_flags.values()) == [False, True]

    async def test_second_round_updates_rows_instead_of_duplicating(self, async_orphan_db, tmp_path):
        """同身份重复预扫描走更新路径，行数不膨胀（幂等收敛）。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        linked = downloads / "linked.mkv"
        linked.write_bytes(b"x")
        os.link(linked, downloads / "copy.mkv")

        scan = await _make_scan(async_orphan_db)
        await _add_candidate(async_orphan_db, scan, str(linked))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        roots_patch = patch(
            "app.services.orphan_hardlink_scan_service.collect_runtime_accessible_roots",
            return_value=[str(downloads)],
        )
        with roots_patch:
            first_summary = await service.run_round()
        assert first_summary["rows_written"] == 1
        assert first_summary["rows_updated"] == 0

        # 游标仍为 0（单候选全覆盖回绕），下一轮自然重扫同批候选
        with roots_patch:
            second_summary = await service.run_round()
        assert second_summary["rows_written"] == 0
        assert second_summary["rows_updated"] == 1
        rows = (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        assert len(rows) == 1

    async def test_cursor_advances_with_stat_limit_and_wraps_next_round(self, async_orphan_db, tmp_path):
        """候选多于单轮 stat 上限时游标保留进度；下一轮覆盖剩余后回绕为 0。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        first = downloads / "first.mkv"
        first.write_bytes(b"x")
        second = downloads / "second.mkv"
        second.write_bytes(b"y")

        scan = await _make_scan(async_orphan_db)
        first_detail = await _add_candidate(async_orphan_db, scan, str(first))
        second_detail = await _add_candidate(async_orphan_db, scan, str(second))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with patch.object(settings, "ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE", 1):
            first_summary = await service.run_round()

        assert first_summary["stat_inspected"] == 1
        assert first_summary["cursor_advanced_to"] == first_detail.id
        state = (await async_orphan_db.execute(select(OrphanHardlinkScanState))).scalar_one()
        assert state.last_detail_id == first_detail.id

        second_summary = await service.run_round()
        assert second_summary["stat_inspected"] == 1
        assert second_summary["cursor_wrapped"] is True
        assert second_summary["cursor_advanced_to"] == 0
        state = (await async_orphan_db.execute(select(OrphanHardlinkScanState))).scalar_one()
        assert state.last_detail_id == 0
        assert second_detail  # 两个候选在两轮内都被覆盖

    async def test_prunes_expired_result_rows(self, async_orphan_db, tmp_path):
        """超过保留期的结果行被清理，控制结果表体积。"""
        stale = tmp_path / "stale.mkv"
        stale.write_bytes(b"s")
        scan = await _make_scan(async_orphan_db)
        await _add_candidate(async_orphan_db, scan, str(stale))
        # 过期行属于已消失的物理身份（不在本轮候选内），才会被保留期清理命中
        async_orphan_db.add(
            OrphanHardlinkCopyResult(
                device_id=999999,
                inode_id=1,
                copy_count=0,
                found_count=0,
                copies_json="[]",
                scanned_at=datetime.utcnow() - timedelta(days=90),
            )
        )
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        summary = await service.run_round()

        assert summary["pruned_rows"] == 1
        rows = (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        assert all(row.scanned_at > datetime.utcnow() - timedelta(days=1) for row in rows)

    async def test_zero_copy_round_never_walks(self, async_orphan_db, tmp_path):
        """全部单链接时只写平凡结果，不进入目录遍历。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        solo = downloads / "solo.mkv"
        solo.write_bytes(b"solo")

        scan = await _make_scan(async_orphan_db)
        await _add_candidate(async_orphan_db, scan, str(solo))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with patch(
            "app.services.orphan_hardlink_scan_service.find_hardlink_paths_bounded",
            wraps=find_hardlink_paths_bounded,
        ) as walk:
            summary = await service.run_round()

        walk.assert_not_called()
        assert summary["walk_targets"] == 0
        assert summary["rows_written"] == 1

    async def test_stat_budget_stops_window_and_keeps_progress(self, async_orphan_db, tmp_path):
        """stat 阶段超预算立即停止；窗口为空、游标不回退，任务不失败。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        files = []
        for index in range(3):
            path = downloads / f"file{index}.mkv"
            path.write_bytes(b"x")
            files.append(path)

        scan = await _make_scan(async_orphan_db)
        details = [await _add_candidate(async_orphan_db, scan, str(path)) for path in files]
        await async_orphan_db.commit()

        # 受控时钟：started=100、后续读取=200，确保首查即超预算（Windows
        # monotonic 分辨率约 15.6ms，真实时钟下内存库整轮可能落在同一 tick）
        first_tick = iter([100.0])

        def fake_monotonic() -> float:
            return next(first_tick, 200.0)

        service = OrphanHardlinkScanService(async_orphan_db)
        with (
            patch.object(settings, "ORPHAN_HARDLINK_SCAN_BUDGET_SECONDS", 0.0),
            patch("app.services.orphan_hardlink_scan_service.time.monotonic", side_effect=fake_monotonic),
        ):
            summary = await service.run_round()

        assert summary["status"] == "success"
        assert summary["stat_inspected"] == 0
        assert summary["cursor_advanced_to"] is None
        assert details  # 候选保持不变，下一轮继续

    async def test_resolved_candidates_and_detached_details_skipped(self, async_orphan_db, tmp_path):
        """resolved 候选与没有候选指针的孤儿明细都不进入 stat 窗口。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        resolved_file = downloads / "resolved.mkv"
        resolved_file.write_bytes(b"r")
        detached_file = downloads / "detached.mkv"
        detached_file.write_bytes(b"d")

        scan = await _make_scan(async_orphan_db)
        await _add_candidate(async_orphan_db, scan, str(resolved_file), status="resolved")
        async_orphan_db.add(
            OrphanFile(
                scan_id=scan.scan_id,
                file_path=str(detached_file),
                file_size=1,
                downloader_id="dl_001",
                canonical_path=normalize_path(str(detached_file)),
            )
        )
        await async_orphan_db.commit()

        summary = await OrphanHardlinkScanService(async_orphan_db).run_round()

        assert summary["status"] == "success"
        assert summary["stat_inspected"] == 0
        assert summary["distinct_identities"] == 0
        rows = (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        assert rows == []

    async def test_missing_results_are_walked_before_fresh_ones(self, async_orphan_db, tmp_path):
        """遍历名额优先给没有结果的身份；已有新鲜结果的旧身份本轮延后。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        covered = downloads / "covered.mkv"
        covered.write_bytes(b"c")
        os.link(covered, downloads / "covered-copy.mkv")
        pending_file = downloads / "pending.mkv"
        pending_file.write_bytes(b"p")
        os.link(pending_file, downloads / "pending-copy.mkv")

        scan = await _make_scan(async_orphan_db)
        covered_detail = await _add_candidate(async_orphan_db, scan, str(covered))
        await _add_candidate(async_orphan_db, scan, str(pending_file))
        covered_stat = os.stat(covered)
        fresh_time = datetime.utcnow()
        async_orphan_db.add(
            OrphanHardlinkCopyResult(
                device_id=str(int(covered_stat.st_dev)),
                inode_id=int(covered_stat.st_ino),
                copy_count=1,
                found_count=2,
                copies_json=json.dumps([str(covered)]),
                scanned_at=fresh_time,
            )
        )
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with (
            patch(
                "app.services.orphan_hardlink_scan_service.collect_runtime_accessible_roots",
                return_value=[str(downloads)],
            ),
            patch.object(settings, "ORPHAN_HARDLINK_SCAN_MAX_TARGETS", 1),
        ):
            summary = await service.run_round()

        assert summary["walk_targets"] == 1
        assert summary["rows_deferred"] == 1
        rows = {
            (row.device_id, row.inode_id): row
            for row in (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        }
        covered_row = rows[(str(int(covered_stat.st_dev)), int(covered_stat.st_ino))]
        assert covered_row.scanned_at == fresh_time  # 旧结果未被覆盖
        api = await OrphanFileService(async_orphan_db).get_hardlink_copy_locations([covered_detail.id])
        assert api["items"][0]["pending_scan"] is False  # 旧结果仍可读

    async def test_budget_notes_flow_into_rows_and_summary(self, async_orphan_db, tmp_path):
        """遍历超预算标记写入行 scan_note 并反映到 summary.walk_budget_exceeded。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        linked = downloads / "linked.mkv"
        linked.write_bytes(b"x")
        os.link(linked, downloads / "linked-copy.mkv")
        identity = (int(os.stat(linked).st_dev), int(os.stat(linked).st_ino))

        scan = await _make_scan(async_orphan_db)
        await _add_candidate(async_orphan_db, scan, str(linked))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with patch(
            "app.services.orphan_hardlink_scan_service.find_hardlink_paths_bounded",
            return_value=({identity: []}, {identity: "budget_exceeded"}),
        ):
            summary = await service.run_round()

        assert summary["walk_budget_exceeded"] is True
        assert summary["rows_written"] == 1
        row = (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalar_one()
        assert row.scan_note == "budget_exceeded"
        assert row.copies == []
        assert row.copy_count == 1  # 权威副本数来自 stat，不因遍历截断而丢失


class TestTaskRegistrationContract:
    """任务注册/包装器/配置默认值契约。"""

    def test_default_registration_importable_and_scheduled_after_purge(self):
        """默认任务表登记的 executor 可导入且指向任务类；凌晨 4 点在隔离清理之后。"""
        import importlib

        from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS

        entries = {task["task_code"]: task for task in DEFAULT_SCHEDULED_TASKS}
        entry = entries["orphan_hardlink_copy_scan"]
        module_path, class_name = entry["executor"].rsplit(".", 1)
        module = importlib.import_module(module_path)
        from app.tasks.scheduler.orphan_hardlink_copy_scan_task import OrphanHardlinkCopyScanTask

        assert getattr(module, class_name) is OrphanHardlinkCopyScanTask
        assert entry["cron_plan"] == "0 4 * * *"
        assert entry["enabled"] is True
        # 任务超时必须大于单轮遍历预算，预算是软停止、timeout 是硬兜底
        assert entry["timeout_seconds"] > settings.ORPHAN_HARDLINK_SCAN_BUDGET_SECONDS

    def test_registered_as_heavy_task_for_admission(self):
        """遍历型任务必须进入 heavy_sync 互斥，防止与同步/清理并发放大 IO。"""
        from app.tasks.task_profiles import get_profile, is_heavy_task

        assert is_heavy_task("orphan_hardlink_copy_scan")
        profile = get_profile("orphan_hardlink_copy_scan")
        assert profile is not None and profile.heavy_sync is True

    def test_budget_settings_defaults_are_sane(self):
        """五项性能护栏默认值必须为正，防止配置项被误删后护栏失效。"""
        assert settings.ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE >= 1
        assert settings.ORPHAN_HARDLINK_SCAN_MAX_TARGETS >= 1
        assert settings.ORPHAN_HARDLINK_SCAN_BUDGET_SECONDS > 0
        assert settings.ORPHAN_HARDLINK_SCAN_MAX_PATHS_PER_TARGET >= 1
        assert settings.ORPHAN_HARDLINK_SCAN_RESULT_RETENTION_DAYS >= 1

    async def test_task_execute_wraps_service_round(self):
        """execute() 打开独立会话调用 run_round，并透传状态与摘要。"""
        from unittest.mock import AsyncMock

        from app.tasks.scheduler import orphan_hardlink_copy_scan_task as task_module

        with (
            patch.object(
                task_module.OrphanHardlinkScanService,
                "run_round",
                new=AsyncMock(return_value={"status": "success", "rows_written": 3}),
            ) as round_mock,
            patch.object(task_module, "AsyncSessionLocal") as session_factory,
        ):
            task = task_module.OrphanHardlinkCopyScanTask()
            result = await task.execute()

        assert result["status"] == "success"
        assert result["task_name"] == task.name
        assert result["scan_result"]["rows_written"] == 3
        round_mock.assert_awaited_once()
        session_factory.assert_called_once()


class TestScanScopeExclusions:
    """预扫描范围仅限待清理且未忽视候选（status=candidate 且 is_ignored=False）。

    已忽视候选受保护无需定位副本；quarantined/purged 候选文件已被移动/删除，
    纳入只会产生无效 stat（线上 stat_failed 的主要来源）。
    """

    async def test_ignored_and_terminal_status_candidates_are_skipped(self, async_orphan_db, tmp_path):
        """已忽视/quarantined/purged 候选不进入 stat 窗口；取消忽视后恢复扫描。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        kept = downloads / "kept.mkv"
        kept.write_bytes(b"k")
        ignored = downloads / "ignored.mkv"
        ignored.write_bytes(b"i")
        quarantined = downloads / "quarantined.mkv"
        purged = downloads / "purged.mkv"

        scan = await _make_scan(async_orphan_db)
        await _add_candidate(async_orphan_db, scan, str(kept))
        await _add_candidate(async_orphan_db, scan, str(ignored), ignored=True)
        await _add_candidate(async_orphan_db, scan, str(quarantined), status="quarantined")
        await _add_candidate(async_orphan_db, scan, str(purged), status="purged")
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        summary = await service.run_round()

        assert summary["status"] == "success"
        # 只有 kept 进入 stat；quarantined/purged 若被纳入会以 stat_failed 形式出现
        assert summary["stat_inspected"] == 1
        assert summary["stat_failed"] == 0
        assert summary["walk_targets"] == 0
        assert summary["rows_written"] == 1

        # 取消忽视（回 candidate 且未忽视）后，下一轮重新纳入并落平凡结果
        ignored_candidate = (
            await async_orphan_db.execute(
                select(OrphanCurrentCandidate).where(
                    OrphanCurrentCandidate.canonical_path == normalize_path(str(ignored))
                )
            )
        ).scalar_one()
        ignored_candidate.is_ignored = False
        await async_orphan_db.commit()

        second = await service.run_round()
        # 游标已回绕：kept 重新覆盖 + 取消忽视的 ignored 重新纳入
        assert second["stat_inspected"] == 2

        rows = (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        ignored_stat = os.stat(ignored)
        kept_stat = os.stat(kept)
        result_identities = {(int(row.device_id), int(row.inode_id)) for row in rows}
        assert (int(ignored_stat.st_dev), int(ignored_stat.st_ino)) in result_identities
        assert (int(kept_stat.st_dev), int(kept_stat.st_ino)) in result_identities
        assert len(rows) == 2

    async def test_excluded_candidates_do_not_consume_stat_attempts_between_cursor_pages(
        self, async_orphan_db, tmp_path
    ):
        """keyset 游标越过被排除候选：不消耗 stat 尝试，stat_failed 只来自在范围内的文件。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        kept_first = downloads / "kept-first.mkv"
        kept_first.write_bytes(b"a")
        ignored = downloads / "ignored.mkv"
        ignored.write_bytes(b"b")
        kept_second = downloads / "kept-second.mkv"
        kept_second.write_bytes(b"c")
        gone = downloads / "gone.mkv"  # 在范围内但文件已消失

        scan = await _make_scan(async_orphan_db)
        first_detail = await _add_candidate(async_orphan_db, scan, str(kept_first))
        await _add_candidate(async_orphan_db, scan, str(ignored), ignored=True)
        second_detail = await _add_candidate(async_orphan_db, scan, str(kept_second))
        gone_detail = await _add_candidate(async_orphan_db, scan, str(gone))
        await async_orphan_db.commit()

        service = OrphanHardlinkScanService(async_orphan_db)
        with patch.object(settings, "ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE", 1):
            first_round = await service.run_round()

        assert first_round["stat_inspected"] == 1
        assert first_round["stat_failed"] == 0
        assert first_round["cursor_advanced_to"] == first_detail.id

        second_round = await service.run_round()
        # 游标之后在范围内的是 kept_second 与 gone（ignored 被跳过）：
        # 若排除失效，ignored 会额外贡献一次成功 stat（stat_inspected 变 2）
        assert second_round["stat_inspected"] == 1
        assert second_round["stat_failed"] == 1
        assert second_round["cursor_wrapped"] is True
        # 明细按加入顺序分配递增 ID：ignored(2) 夹在 kept_second(3) 之前被游标越过
        assert first_detail.id < second_detail.id
        assert gone_detail.id > second_detail.id

    async def test_excluded_candidates_keep_existing_result_rows_until_retention(self, async_orphan_db, tmp_path):
        """被排除候选的既有结果行本轮不被删除/覆盖，仍交给保留期任务清理。"""
        downloads = tmp_path / "downloads"
        downloads.mkdir()
        ignored = downloads / "ignored-linked.mkv"
        ignored.write_bytes(b"x")

        scan = await _make_scan(async_orphan_db)
        await _add_candidate(async_orphan_db, scan, str(ignored), ignored=True)
        scanned_at = datetime.utcnow() - timedelta(days=1)
        async_orphan_db.add(
            OrphanHardlinkCopyResult(
                device_id="11",
                inode_id=999,
                copy_count=1,
                found_count=2,
                copies_json='["/data/a.bin", "/data/b.bin"]',
                truncated=0,
                scan_note=None,
                scanned_at=scanned_at,
            )
        )
        await async_orphan_db.commit()

        summary = await OrphanHardlinkScanService(async_orphan_db).run_round()

        assert summary["status"] == "success"
        assert summary["stat_inspected"] == 0
        rows = (await async_orphan_db.execute(select(OrphanHardlinkCopyResult))).scalars().all()
        assert len(rows) == 1
        assert rows[0].scanned_at == scanned_at
        assert rows[0].found_count == 2
