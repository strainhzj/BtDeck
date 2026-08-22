# -*- coding: utf-8 -*-
"""孤儿硬链接副本位置的定时预扫描服务。

大文件系统上的整体目录遍历可能耗时数分钟，不能放在交互请求里执行。本服务由
定时任务驱动，按 keyset 游标分轮处理：每轮限量 stat 孤儿明细、只对 ``nlink > 1``
的 inode 做带截止时间的串行遍历，并把结果按 ``(device_id, inode_id)`` 落库；
前端 ``hardlink-copies`` 接口只读库内结果，不再触发任何目录遍历。

扫描范围仅限待清理且未忽视的候选（``status == "candidate" 且未忽视``）：已忽视
候选受保护无需定位副本，quarantined/purged 候选文件已被移动/删除，纳入只会
产生无效 stat；取消忽视或隔离恢复后经 reconcile 重置回 candidate，自动恢复扫描。

每轮 stat 得到的权威 ``st_nlink - 1`` 同步刷回孤儿明细的 ``hardlink_copy_count``
快照列（``_refresh_detail_counts``）：列表副本数与 ``hardlink_copies=located``
筛选都读该列，孤儿全量扫描默认每周才推进，靠本刷新维持每日新鲜度；已忽视
候选不在扫描范围，其明细快照停在上次值。

单轮预算（性能护栏）：

- stat 阶段最多 ``ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE`` 个文件；
- 遍历阶段最多 ``ORPHAN_HARDLINK_SCAN_MAX_TARGETS`` 个 inode，目录间检查
  ``ORPHAN_HARDLINK_SCAN_BUDGET_SECONDS`` 截止时间，超时保留部分结果；
- 单 inode 最多存 ``ORPHAN_HARDLINK_SCAN_MAX_PATHS_PER_TARGET`` 条路径；
- 遍历全程单线程串行（不与其它 IO 并发放大压力），结果分批短事务写库。
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from sqlalchemy import delete, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile
from app.models.orphan_hardlink_copy import OrphanHardlinkCopyResult, OrphanHardlinkScanState
from app.services.orphan_quarantine import (
    collect_runtime_accessible_roots,
    find_hardlink_paths_bounded,
)
from app.tasks.resource_guard import admission_controller

logger = logging.getLogger(__name__)

# keyset 分批读取候选的页大小；单轮 stat 上限由配置控制
_CANDIDATE_PAGE_SIZE = 500
# 结果行分批 flush 大小（与生命周期对账的分批惯例一致）
_WRITE_BATCH_SIZE = 200
# 结果表按身份反查的分片大小（SQLite 绑定变量上限内）
_IDENTITY_LOOKUP_CHUNK = 400

Identity = Tuple[int, int]


class OrphanHardlinkScanService:
    """按轮推进的副本预扫描；每轮严格受 stat/目标数/时间预算约束。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run_round(self) -> Dict[str, Any]:
        """执行一轮预扫描并返回摘要；失败时回滚并记录，不向任务层抛异常。"""
        started = time.monotonic()
        budget = max(float(settings.ORPHAN_HARDLINK_SCAN_BUDGET_SECONDS), 0.0)
        deadline = started + budget
        stat_limit = max(int(settings.ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE), 1)
        walk_limit = max(int(settings.ORPHAN_HARDLINK_SCAN_MAX_TARGETS), 1)
        path_cap = max(int(settings.ORPHAN_HARDLINK_SCAN_MAX_PATHS_PER_TARGET), 1)

        summary: Dict[str, Any] = {
            "status": "success",
            "stat_inspected": 0,
            "stat_failed": 0,
            "distinct_identities": 0,
            "walk_targets": 0,
            "walk_budget_exceeded": False,
            "rows_written": 0,
            "rows_updated": 0,
            "rows_deferred": 0,
            "details_refreshed": 0,
            "cursor_advanced_to": None,
            "cursor_wrapped": False,
            "pruned_rows": 0,
            "duration_seconds": 0.0,
            "error": None,
        }

        try:
            cursor = await self._load_cursor()
            window = await self._stat_window(cursor, stat_limit, deadline)
            summary["stat_inspected"] = window.stat_inspected
            summary["stat_failed"] = window.stat_failed
            summary["distinct_identities"] = len(window.identities)
            summary["cursor_advanced_to"] = window.next_cursor
            summary["cursor_wrapped"] = window.wrapped

            existing_rows = await self._lookup_existing(list(window.identities.keys()))
            walk_targets = self._select_walk_targets(window, existing_rows, walk_limit)
            summary["walk_targets"] = len(walk_targets)

            paths_by_inode: Dict[Identity, List[str]] = {}
            walk_notes: Dict[Identity, str] = {}
            if walk_targets:
                source_paths = [path for identity in walk_targets for path in window.identities[identity]]
                scan_roots = await asyncio.to_thread(collect_runtime_accessible_roots, set(walk_targets), source_paths)
                paths_by_inode, walk_notes = await asyncio.to_thread(
                    find_hardlink_paths_bounded,
                    set(walk_targets),
                    scan_roots,
                    deadline,
                    path_cap,
                )
                summary["walk_budget_exceeded"] = any(note == "budget_exceeded" for note in walk_notes.values())

            written, updated, deferred = await self._write_results(
                window, paths_by_inode, walk_notes, walk_targets, existing_rows
            )
            summary["rows_written"] = written
            summary["rows_updated"] = updated
            summary["rows_deferred"] = deferred
            summary["details_refreshed"] = await self._refresh_detail_counts(window)

            if window.next_cursor is not None:
                await self._store_cursor(window.next_cursor)
            summary["pruned_rows"] = await self._prune_expired()

            await self.db.commit()
        except Exception as exc:  # noqa: BLE001 - 任务层只看摘要，不让异常打断调度
            await self.db.rollback()
            summary["status"] = "failed"
            summary["error"] = str(exc)
            logger.warning("[副本预扫描] 本轮失败: %s", exc, exc_info=True)

        summary["duration_seconds"] = round(time.monotonic() - started, 3)
        level = logging.INFO if summary["status"] == "success" else logging.WARNING
        logger.log(
            level,
            "[副本预扫描] status=%s stat=%s identities=%s walk=%s budget_exceeded=%s "
            "written=%s deferred=%s cursor=%s wrapped=%s pruned=%s %.1fs",
            summary["status"],
            summary["stat_inspected"],
            summary["distinct_identities"],
            summary["walk_targets"],
            summary["walk_budget_exceeded"],
            summary["rows_written"] + summary["rows_updated"],
            summary["rows_deferred"],
            summary["cursor_advanced_to"],
            summary["cursor_wrapped"],
            summary["pruned_rows"],
            summary["duration_seconds"],
        )
        return summary

    # ==================== 阶段实现 ====================

    async def _load_cursor(self) -> int:
        result = await self.db.execute(select(OrphanHardlinkScanState).where(OrphanHardlinkScanState.id == 1))
        state = result.scalar_one_or_none()
        return int(state.last_detail_id) if state is not None else 0

    async def _store_cursor(self, last_detail_id: int) -> None:
        result = await self.db.execute(select(OrphanHardlinkScanState).where(OrphanHardlinkScanState.id == 1))
        state = result.scalar_one_or_none()
        if state is None:
            self.db.add(OrphanHardlinkScanState(id=1, last_detail_id=last_detail_id))
        else:
            state.last_detail_id = last_detail_id
            state.updated_at = datetime.utcnow()

    async def _stat_window(self, cursor: int, stat_limit: int, deadline: float) -> "_StatWindow":
        """keyset 分批加载候选并顺序 stat，收集身份与权威 ``st_nlink - 1``。"""
        identities: Dict[Identity, List[str]] = {}
        copy_counts: Dict[Identity, int] = {}
        detail_ids: Dict[Identity, List[int]] = {}
        stat_inspected = 0
        stat_failed = 0
        current = cursor
        wrapped = False

        while stat_inspected < stat_limit:
            if time.monotonic() > deadline:
                logger.info("[副本预扫描] stat 阶段到达时间预算，保留部分进度")
                break
            page_size = min(_CANDIDATE_PAGE_SIZE, stat_limit - stat_inspected)
            result = await self.db.execute(
                select(OrphanFile.id, OrphanFile.file_path)
                .where(
                    OrphanFile.id > current,
                    OrphanFile.id.in_(
                        select(OrphanCurrentCandidate.current_detail_id).where(
                            OrphanCurrentCandidate.current_detail_id.isnot(None),
                            # 仅扫描待清理且未忽视的候选：已忽视受保护无需定位副本，
                            # quarantined/purged 候选文件已被移动/删除，stat 必然失败
                            # （取消忽视或隔离恢复会经 reconcile 重置回 candidate，自动回到扫描范围）。
                            OrphanCurrentCandidate.status == "candidate",
                            OrphanCurrentCandidate.is_ignored.is_(False),
                        )
                    ),
                )
                .order_by(OrphanFile.id.asc())
                .limit(page_size)
            )
            rows = result.all()
            if not rows:
                # 候选已全部处理：回绕到起点，下一轮从最旧的候选重新覆盖
                wrapped = cursor > 0
                current = 0
                break

            stat_results = await asyncio.to_thread(
                self._stat_paths, [(int(row.id), cast(str, row.file_path)) for row in rows]
            )
            stat_inspected += len(stat_results)
            stat_failed += len(rows) - len(stat_results)
            for item in stat_results:
                identity = cast(Identity, item["identity"])
                identities.setdefault(identity, []).append(cast(str, item["file_path"]))
                detail_ids.setdefault(identity, []).append(int(item["detail_id"]))
                # 同一身份以最后一次 stat 为准（文件系统事实单一）
                copy_counts[identity] = int(item["copy_count"])

            current = int(rows[-1].id)
            if len(rows) < page_size:
                wrapped = cursor > 0
                current = 0
                break

        next_cursor: Optional[int] = current if current != cursor else None
        return _StatWindow(
            identities=identities,
            copy_counts=copy_counts,
            detail_ids=detail_ids,
            stat_inspected=stat_inspected,
            stat_failed=stat_failed,
            next_cursor=next_cursor,
            wrapped=wrapped,
        )

    @staticmethod
    def _stat_paths(targets: Sequence[Tuple[int, str]]) -> List[Dict[str, Any]]:
        """顺序 stat（由调用方放入线程）；不可访问的文件计入失败但不中断本轮。"""
        inspected: List[Dict[str, Any]] = []
        for detail_id, file_path in targets:
            try:
                stat_result = os.stat(file_path)
            except OSError:
                continue
            inspected.append(
                {
                    "detail_id": detail_id,
                    "identity": (int(stat_result.st_dev), int(stat_result.st_ino)),
                    "copy_count": max(int(stat_result.st_nlink) - 1, 0),
                    "file_path": file_path,
                }
            )
        return inspected

    async def _lookup_existing(self, keys: List[Identity]) -> Dict[Identity, OrphanHardlinkCopyResult]:
        rows: Dict[Identity, OrphanHardlinkCopyResult] = {}
        for start in range(0, len(keys), _IDENTITY_LOOKUP_CHUNK):
            # device_id 以字符串落库（Windows st_dev 可超有符号 64 位）
            chunk = [(str(identity[0]), identity[1]) for identity in keys[start : start + _IDENTITY_LOOKUP_CHUNK]]
            result = await self.db.execute(
                select(OrphanHardlinkCopyResult).where(
                    tuple_(OrphanHardlinkCopyResult.device_id, OrphanHardlinkCopyResult.inode_id).in_(chunk)
                )
            )
            for row in result.scalars().all():
                rows[(int(row.device_id), int(row.inode_id))] = row
        return rows

    @staticmethod
    def _select_walk_targets(
        window: "_StatWindow",
        existing_rows: Dict[Identity, OrphanHardlinkCopyResult],
        walk_limit: int,
    ) -> List[Identity]:
        """只有 ``nlink > 1`` 才需要遍历；无结果的最优先，其余按结果新旧排序。"""
        candidates = [identity for identity, copy_count in window.copy_counts.items() if copy_count > 0]

        def sort_key(identity: Identity) -> Tuple[int, float]:
            existing = existing_rows.get(identity)
            if existing is None or existing.scanned_at is None:
                return (0, 0.0)
            return (1, float(existing.scanned_at.replace(tzinfo=None).timestamp()))

        candidates.sort(key=sort_key)
        return candidates[:walk_limit]

    async def _write_results(
        self,
        window: "_StatWindow",
        paths_by_inode: Dict[Identity, List[str]],
        walk_notes: Dict[Identity, str],
        walk_targets: Sequence[Identity],
        existing_rows: Dict[Identity, OrphanHardlinkCopyResult],
    ) -> Tuple[int, int, int]:
        """为已 stat 的身份写入/更新结果行。

        - 已遍历：写入定位路径（包含孤儿源路径本身，展示端按请求文件过滤）；
        - 未遍历且无副本（``nlink == 1``）：写平凡 0 副本结果；
        - 未遍历但有多副本（超出本轮上限/预算）：保留旧结果不覆盖；无旧结果的
          留待后续轮次，前端显示"等待预扫描"。
        """
        walked = set(walk_targets)
        now = datetime.utcnow()
        staged = 0
        written = 0
        updated = 0
        deferred = 0

        for identity, sources in window.identities.items():
            copy_count = int(window.copy_counts.get(identity, 0))
            existing = existing_rows.get(identity)

            if identity in walked:
                paths = paths_by_inode.get(identity, [])
                note = walk_notes.get(identity)
                payload: Dict[str, Any] = {
                    "copy_count": copy_count,
                    "found_count": len(paths),
                    "copies_json": json.dumps(paths, ensure_ascii=False),
                    "truncated": 1 if note == "truncated" else 0,
                    "scan_note": note,
                    "scanned_at": now,
                }
            elif copy_count == 0:
                payload = {
                    "copy_count": 0,
                    "found_count": 0,
                    "copies_json": "[]",
                    "truncated": 0,
                    "scan_note": None,
                    "scanned_at": now,
                }
            else:
                deferred += 1
                continue

            if existing is None:
                self.db.add(
                    OrphanHardlinkCopyResult(
                        device_id=str(identity[0]),
                        inode_id=identity[1],
                        created_at=now,
                        updated_at=now,
                        **payload,
                    )
                )
                written += 1
            else:
                for field, value in payload.items():
                    setattr(existing, field, value)
                existing.updated_at = now
                updated += 1

            staged += 1
            # 分批短事务写库：每批 flush 进入写准入，最终由 run_round 统一 commit
            if staged % _WRITE_BATCH_SIZE == 0:
                async with admission_controller.db_write_scope():
                    await self.db.flush()
        return written, updated, deferred

    async def _refresh_detail_counts(self, window: "_StatWindow") -> int:
        """把 stat 得到的权威 ``st_nlink - 1`` 刷回孤儿明细的快照列。

        列表副本数与 ``hardlink_copies=located`` 筛选都读明细快照列，本刷新让
        它们在每日预扫描节奏内保持新鲜（孤儿全量扫描默认每周才跑一轮）。stat
        失败的明细不触碰（保留旧快照，fail-closed）；仅更新值有变化的行，避免
        稳定明细每轮产生无意义 UPDATE/WAL 写放大。
        """
        refreshed = 0
        for identity, detail_id_list in window.detail_ids.items():
            value = int(window.copy_counts.get(identity, 0))
            for start in range(0, len(detail_id_list), _IDENTITY_LOOKUP_CHUNK):
                chunk = detail_id_list[start : start + _IDENTITY_LOOKUP_CHUNK]
                async with admission_controller.db_write_scope():
                    result = await self.db.execute(
                        update(OrphanFile)
                        .where(
                            OrphanFile.id.in_(chunk),
                            or_(
                                OrphanFile.hardlink_copy_count.is_(None),
                                OrphanFile.hardlink_copy_count != value,
                            ),
                        )
                        .values(hardlink_copy_count=value)
                    )
                refreshed += int(getattr(result, "rowcount", 0) or 0)
        return refreshed

    async def _prune_expired(self) -> int:
        retention_days = max(int(settings.ORPHAN_HARDLINK_SCAN_RESULT_RETENTION_DAYS), 1)
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        result = await self.db.execute(
            select(OrphanHardlinkCopyResult.id).where(OrphanHardlinkCopyResult.scanned_at < cutoff)
        )
        expired_ids = [int(row.id) for row in result.all()]
        for start in range(0, len(expired_ids), _WRITE_BATCH_SIZE):
            chunk = expired_ids[start : start + _WRITE_BATCH_SIZE]
            async with admission_controller.db_write_scope():
                await self.db.execute(delete(OrphanHardlinkCopyResult).where(OrphanHardlinkCopyResult.id.in_(chunk)))
        return len(expired_ids)


class _StatWindow:
    """一轮 stat 阶段的产出（身份→源路径/明细ID、身份→权威副本数、游标进度）。"""

    def __init__(
        self,
        identities: Dict[Identity, List[str]],
        copy_counts: Dict[Identity, int],
        detail_ids: Dict[Identity, List[int]],
        stat_inspected: int,
        stat_failed: int,
        next_cursor: Optional[int],
        wrapped: bool,
    ) -> None:
        self.identities = identities
        self.copy_counts = copy_counts
        self.detail_ids = detail_ids
        self.stat_inspected = stat_inspected
        self.stat_failed = stat_failed
        self.next_cursor = next_cursor
        self.wrapped = wrapped
