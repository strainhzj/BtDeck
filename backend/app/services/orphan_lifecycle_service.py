# -*- coding: utf-8 -*-
"""
孤儿文件生命周期服务（v1.0.6+ 语义重做）

管理 OrphanCurrentCandidate 表的生命周期推进：
- 只有完整成功扫描才能推进候选状态（reconcile_candidates）
- 新发现 → insert candidate（first_seen_at=now，count=1）
- 已存在 → 更新 last_seen/count/status=candidate
- 未出现在新清单中的旧 candidate → status=resolved
- failed 扫描不调用此方法（不修改候选生命周期）

自动清理依据「连续成为孤儿的时间」（last_seen_at - first_seen_at），
不再依据文件 mtime。

@file: orphan_lifecycle_service.py
@time: 2026-07-11
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile
from app.tasks.resource_guard import admission_controller

logger = logging.getLogger(__name__)


def _path_in_scan_roots(path: str, scan_roots: Sequence[str]) -> bool:
    candidate_path = os.path.normcase(os.path.realpath(os.path.abspath(path)))
    for root in scan_roots:
        normalized_root = os.path.normcase(os.path.realpath(os.path.abspath(root)))
        try:
            if os.path.commonpath([candidate_path, normalized_root]) == normalized_root:
                return True
        except ValueError:
            continue
    return False


class OrphanLifecycleService:
    """孤儿文件生命周期服务（异步）

    用法：
        service = OrphanLifecycleService(db)
        await service.reconcile_candidates(scan_id, scan_time, orphans)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _execute_lifecycle_update(
        self,
        statement: Any,
        *,
        commit: bool,
    ) -> Any:
        """Execute one lifecycle update inside the governed write transaction."""
        if not commit:
            return await self.db.execute(statement)
        try:
            async with admission_controller.db_write_scope():
                result = await self.db.execute(statement)
                await self.db.commit()
                return result
        except Exception:
            await self.db.rollback()
            raise

    async def reconcile_candidates(
        self,
        scan_id: str,
        scan_time: datetime,
        orphans: List[Dict[str, Any]],
        *,
        scan_roots: Optional[Sequence[str]] = None,
        commit: bool = True,
        batch_size: Optional[int] = None,
        persist_current_details: bool = False,
    ) -> Dict[str, int]:
        """对账候选状态（仅在完整成功扫描后调用）。

        语义：
        - 新发现的孤儿路径 → insert candidate
        - 已存在的 candidate → 更新 last_seen_at + scan_id + count+1 + status=candidate
        - 未出现在本次清单中的旧 candidate（status=candidate）→ status=resolved

        Args:
            scan_id: 本次扫描批次 ID
            scan_time: 本次扫描时间
            orphans: 本次扫描发现的孤儿列表，每项含 canonical_path/downloader_id/file_size/mtime_ns
            scan_roots: 本次成功扫描的根目录；未传保持全量对账兼容语义，
                空列表表示没有目录成功扫描，不推进任何旧候选
            batch_size: 非 None 时按批 commit（每批独立事务，避免大批量候选单事务
                独占写锁）；resolved 标记仍依赖完整 seen_paths，在最后统一处理，
                不随批提交（计数语义不变）

        Returns:
            {"inserted": int, "updated": int, "resolved": int}
        """
        # canonical_path 是稳定身份；重叠扫描根即使产出重复项，也只推进一次生命周期。
        orphan_by_path = {str(orphan["canonical_path"]): orphan for orphan in orphans}
        normalized_orphans = list(orphan_by_path.values())
        seen_paths = set(orphan_by_path)
        effective_batch_size = max(
            1,
            int(batch_size or settings.ORPHAN_SCAN_COMMIT_BATCH_SIZE),
        )
        inserted = 0
        updated = 0
        resolved = 0
        owner_reassigned = 0
        detail_inserted = 0
        detail_reused = 0

        @asynccontextmanager
        async def _batch_transaction() -> AsyncIterator[None]:
            """把单批查询、ORM 变更、flush/commit 作为同一受治理短事务。

            SQLite WAL 读事务若在释放治理锁后再升级为写事务，期间其它写者提交
            可能导致 ``SQLITE_BUSY_SNAPSHOT``。因此不能把查询和提交拆成两个
            ``db_write_scope``；每批整体持锁，批次之间再释放以让交互写入穿插。
            ``commit=False`` 表示调用方已拥有更外层事务/治理边界。
            """
            if not commit:
                yield
                return
            try:
                async with admission_controller.db_write_scope():
                    yield
                    await self.db.flush()
                    await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise

        # 查询、变更、提交都按批进行。尤其不再把 12 万候选一次性加载进 ORM identity map。
        for start in range(0, len(normalized_orphans), effective_batch_size):
            batch = normalized_orphans[start : start + effective_batch_size]
            paths = [str(orphan["canonical_path"]) for orphan in batch]
            async with _batch_transaction():
                candidate_result = await self.db.execute(
                    select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path.in_(paths))
                )
                candidates = {
                    str(candidate.canonical_path): candidate for candidate in candidate_result.scalars().all()
                }

                details_by_id: Dict[int, OrphanFile] = {}
                fallback_details: Dict[str, OrphanFile] = {}
                if persist_current_details:
                    detail_ids = [
                        int(candidate.current_detail_id)
                        for candidate in candidates.values()
                        if candidate.current_detail_id is not None
                    ]
                    if detail_ids:
                        detail_result = await self.db.execute(select(OrphanFile).where(OrphanFile.id.in_(detail_ids)))
                        details_by_id = {int(detail.id): detail for detail in detail_result.scalars().all()}

                    missing_paths = [
                        path
                        for path, candidate in candidates.items()
                        if candidate.current_detail_id is None or int(candidate.current_detail_id) not in details_by_id
                    ]
                    if missing_paths:
                        fallback_result = await self.db.execute(
                            select(OrphanFile)
                            .where(OrphanFile.canonical_path.in_(missing_paths))
                            .order_by(OrphanFile.id.desc())
                        )
                        for detail in fallback_result.scalars().all():
                            path = str(detail.canonical_path or "")
                            if path and path not in fallback_details:
                                fallback_details[path] = detail

                for orphan in batch:
                    path = str(orphan["canonical_path"])
                    candidate = candidates.get(path)
                    current_detail: Optional[OrphanFile] = None
                    if candidate is not None and candidate.current_detail_id is not None:
                        current_detail = details_by_id.get(int(candidate.current_detail_id))
                    if current_detail is None:
                        current_detail = fallback_details.get(path)

                    # purged/quarantined 的旧明细代表上一轮清理结果；同路径重新出现必须新建明细。
                    needs_new_detail = bool(
                        persist_current_details
                        and (
                            current_detail is None
                            or bool(current_detail.is_deleted)
                            or (candidate is not None and candidate.status in ("quarantined", "purged"))
                        )
                    )
                    if needs_new_detail:
                        current_detail = OrphanFile(
                            scan_id=scan_id,
                            file_path=str(orphan.get("file_path") or path),
                            file_size=int(orphan.get("file_size") or 0),
                            mtime=orphan.get("mtime"),
                            downloader_id=orphan.get("downloader_id") or None,
                            confidence=str(orphan.get("confidence") or "high"),
                            canonical_path=path,
                        )
                        self.db.add(current_detail)
                        detail_inserted += 1
                    elif persist_current_details and current_detail is not None:
                        # 已扫描过的孤儿只更新发生变化的元数据，避免 12 万条稳定
                        # 明细在每轮扫描中再次产生无意义 UPDATE/WAL 写放大。
                        detail_values = {
                            "file_path": str(orphan.get("file_path") or path),
                            "file_size": int(orphan.get("file_size") or 0),
                            "mtime": orphan.get("mtime"),
                            "downloader_id": orphan.get("downloader_id") or None,
                            "confidence": str(orphan.get("confidence") or "high"),
                            "canonical_path": path,
                        }
                        for field, value in detail_values.items():
                            if getattr(current_detail, field) != value:
                                setattr(current_detail, field, value)
                        detail_reused += 1

                    if candidate is None:
                        candidate = OrphanCurrentCandidate(
                            canonical_path=path,
                            downloader_id=orphan.get("downloader_id") or "",
                            first_seen_at=scan_time,
                            last_seen_at=scan_time,
                            last_seen_scan_id=scan_id,
                            consecutive_scan_count=1,
                            status="candidate",
                            file_size=orphan.get("file_size", 0),
                            confidence=orphan.get("confidence", "high"),
                            mtime_ns=orphan.get("mtime_ns"),
                            device_id=orphan.get("device_id"),
                            inode=orphan.get("inode"),
                        )
                        if persist_current_details and current_detail is not None:
                            candidate.current_detail = current_detail
                        self.db.add(candidate)
                        inserted += 1
                        continue

                    if (
                        persist_current_details
                        and current_detail is not None
                        and (candidate.current_detail_id is None or candidate.current_detail_id != current_detail.id)
                    ):
                        candidate.current_detail = current_detail
                    current_downloader_id = orphan.get("downloader_id") or ""
                    if candidate.downloader_id != current_downloader_id:
                        candidate.downloader_id = current_downloader_id
                        owner_reassigned += 1
                    if candidate.status != "candidate":
                        candidate.first_seen_at = scan_time
                        candidate.consecutive_scan_count = 1
                        candidate.is_ignored = False
                        candidate.ignored_at = None
                        candidate.ignored_by = None
                    else:
                        candidate.consecutive_scan_count = int(candidate.consecutive_scan_count or 0) + 1
                    candidate.last_seen_at = scan_time
                    candidate.last_seen_scan_id = scan_id
                    candidate.status = "candidate"
                    candidate.operation_state = "stable"
                    candidate.operation_target_path = None
                    candidate.operation_error = None
                    candidate.file_size = orphan.get("file_size", candidate.file_size)
                    candidate.confidence = orphan.get("confidence", "high")
                    if orphan.get("mtime_ns") is not None:
                        candidate.mtime_ns = orphan["mtime_ns"]
                    if orphan.get("device_id") is not None:
                        candidate.device_id = str(orphan["device_id"])
                    if orphan.get("inode") is not None:
                        candidate.inode = str(orphan["inode"])
                    updated += 1

        # resolved 同样用 canonical_path keyset 分页。seen 项已写入本 scan_id，
        # 因而无需构造一个 12 万参数的 NOT IN 子句。
        if scan_roots is None or len(scan_roots) > 0:
            cursor: Optional[str] = None
            while True:
                page: List[OrphanCurrentCandidate] = []
                async with _batch_transaction():
                    resolved_query = select(OrphanCurrentCandidate).where(
                        OrphanCurrentCandidate.status == "candidate",
                        or_(
                            OrphanCurrentCandidate.last_seen_scan_id.is_(None),
                            OrphanCurrentCandidate.last_seen_scan_id != scan_id,
                        ),
                    )
                    if cursor is not None:
                        resolved_query = resolved_query.where(OrphanCurrentCandidate.canonical_path > cursor)
                    resolved_result = await self.db.execute(
                        resolved_query.order_by(OrphanCurrentCandidate.canonical_path.asc()).limit(effective_batch_size)
                    )
                    page = list(resolved_result.scalars().all())
                    if page:
                        cursor = str(page[-1].canonical_path)
                        for candidate in page:
                            path = str(candidate.canonical_path)
                            in_successful_scope = scan_roots is None or _path_in_scan_roots(path, scan_roots)
                            if path not in seen_paths and in_successful_scope:
                                candidate.status = "resolved"
                                resolved += 1
                if not page:
                    break

        logger.info(
            "[孤儿生命周期] scan_id=%s 对账完成: 新增 %d，更新 %d，归属修正 %d，标记 resolved %d",
            scan_id,
            inserted,
            updated,
            owner_reassigned,
            resolved,
        )
        return {
            "inserted": inserted,
            "updated": updated,
            "resolved": resolved,
            "detail_inserted": detail_inserted,
            "detail_reused": detail_reused,
        }

    async def get_purgeable_candidates(self, days_threshold: int) -> List[OrphanCurrentCandidate]:
        """获取满足清理条件的候选（连续成为孤儿的时间 > days_threshold 天）。

        清理依据「连续成为孤儿的时间」（last_seen_at - first_seen_at），不再依据 mtime。
        只返回 status=candidate 且 confidence='high' 的候选——low confidence（离线降级
        目录粗筛产出）仅展示不清理，需等下载器上线经精筛复核提升为 high 后才可清理。

        Args:
            days_threshold: 连续孤儿天数阈值

        Returns:
            满足条件的候选列表
        """
        cutoff = datetime.utcnow() - timedelta(days=days_threshold)
        purgeable: List[OrphanCurrentCandidate] = []
        cursor: Optional[str] = None
        batch_size = max(1, int(settings.ORPHAN_SCAN_COMMIT_BATCH_SIZE))
        while True:
            query = select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.status == "candidate",
                OrphanCurrentCandidate.operation_state == "stable",
                OrphanCurrentCandidate.confidence == "high",
                # 被用户忽视的候选受保护，定时任务不自动删除。
                OrphanCurrentCandidate.is_ignored == False,  # noqa: E712
                OrphanCurrentCandidate.first_seen_at < cutoff,
            )
            if cursor is not None:
                query = query.where(OrphanCurrentCandidate.canonical_path > cursor)
            async with admission_controller.db_write_scope():
                result = await self.db.execute(
                    query.order_by(OrphanCurrentCandidate.canonical_path.asc()).limit(batch_size)
                )
                page = list(result.scalars().all())
                # 全局与测试会话均 expire_on_commit=False；用只读 commit 结束每页
                # WAL 快照，同时保持返回候选为当前 session 的 persistent 实例。
                # 不能 rollback（会 expire 属性），也不能 expunge（隔离预写需持久化）。
                await self.db.commit()
            if not page:
                break
            cursor = str(page[-1].canonical_path)
            # 二次校验：last_seen_at - first_seen_at >= days_threshold
            for candidate in page:
                duration = (candidate.last_seen_at - candidate.first_seen_at).total_seconds() / 86400
                if duration >= days_threshold:
                    purgeable.append(candidate)
        return purgeable

    async def mark_quarantined(
        self,
        canonical_path: str,
        quarantine_path: str,
        purge_after: datetime,
        quarantine_root: Optional[str] = None,
        *,
        quarantined_at: Optional[datetime] = None,
        commit: bool = True,
    ) -> bool:
        """标记候选为已隔离。

        Args:
            canonical_path: 规范化路径
            quarantine_path: 隔离区路径
            purge_after: 允许物理删除时间

        Returns:
            是否成功更新
        """
        now = quarantined_at or datetime.utcnow()
        result = await self._execute_lifecycle_update(
            update(OrphanCurrentCandidate)
            .where(OrphanCurrentCandidate.canonical_path == canonical_path)
            .values(
                status="quarantined",
                quarantine_path=quarantine_path,
                quarantine_root=quarantine_root,
                quarantined_at=now,
                purge_after=purge_after,
                # 每次进入隔离态重置延后计数（语义：本次隔离周期的硬链接跳过次数）
                purge_delay_count=0,
                operation_state="stable",
                operation_target_path=None,
                operation_error=None,
            ),
            commit=commit,
        )
        return result.rowcount > 0

    async def mark_purged(self, canonical_path: str, *, commit: bool = True) -> bool:
        """标记候选为已物理删除。"""
        result = await self._execute_lifecycle_update(
            update(OrphanCurrentCandidate)
            .where(OrphanCurrentCandidate.canonical_path == canonical_path)
            .values(
                status="purged",
                operation_state="stable",
                operation_target_path=None,
                operation_error=None,
            ),
            commit=commit,
        )
        return result.rowcount > 0

    async def mark_restored(self, canonical_path: str, *, commit: bool = True) -> bool:
        """标记候选为已恢复（隔离区还原到原位置）。

        mark_quarantined 的逆操作：status 从 quarantined 回到 candidate，
        清空所有隔离字段，保持 operation_state=stable。
        """
        result = await self._execute_lifecycle_update(
            update(OrphanCurrentCandidate)
            .where(OrphanCurrentCandidate.canonical_path == canonical_path)
            .values(
                status="candidate",
                quarantine_path=None,
                quarantine_root=None,
                quarantined_at=None,
                purge_after=None,
                operation_state="stable",
                operation_target_path=None,
                operation_error=None,
            ),
            commit=commit,
        )
        return result.rowcount > 0
