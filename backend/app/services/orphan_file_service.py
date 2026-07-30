# -*- coding: utf-8 -*-
"""
孤儿文件管理服务（v1.0.6+ 语义重做）

提供孤儿文件查询、清理预览、手动清理、自动清理超期等功能。

语义重做：
- 最新扫描 running/failed 时禁止清理（preview 与 cleanup 相同新鲜度规则）
- 旧 scan_id 禁止预览和清理（stale ID 返回明确拒绝原因）
- 手动清理删除前重建实时 manifest 复核文件身份（size/mtime_ns/inode/路径逃逸/符号链接）
- 自动清理先移入隔离区（不直接删除），保留期到期后独立任务物理删除
- 不提供 force 绕过

@file: orphan_file_service.py
@time: 2026-07-10
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orphan_file import OrphanCurrentCandidate, OrphanFile, OrphanScanResult
from app.services.orphan_lifecycle_service import OrphanLifecycleService
from app.services.orphan_manifest import (
    ManifestSnapshot,
    TorrentManifestBuilder,
    normalize_path,
)
from app.services.orphan_quarantine import (
    build_quarantine_path,
    compute_purge_after,
    quarantine_file,
    resolve_quarantine_root,
    verify_file_identity,
)
from app.tasks.resource_guard import admission_controller
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType

logger = logging.getLogger(__name__)


class OrphanFileService:
    """孤儿文件管理服务（异步）"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 新鲜度门禁 ====================

    async def _get_latest_scan(self, *, status: Optional[str] = None) -> Optional[OrphanScanResult]:
        """按统一稳定顺序获取最新扫描记录。"""
        query = select(OrphanScanResult)
        if status is not None:
            query = query.where(OrphanScanResult.status == status)
        result = await self.db.execute(
            query.order_by(
                OrphanScanResult.scan_time.desc(),
                OrphanScanResult.created_at.desc(),
                OrphanScanResult.scan_id.desc(),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _evaluate_cleanup_snapshot(
        latest_attempt: Optional[OrphanScanResult],
        scan_id: Optional[str],
    ) -> Dict[str, Any]:
        """纯判定扫描快照是否仍具备清理资格。"""
        if latest_attempt is None:
            return {
                "allowed": False,
                "reason": "无任何扫描记录",
                "latest_scan_id": None,
            }
        if latest_attempt.status != "completed":
            return {
                "allowed": False,
                "reason": (f"最新扫描状态为 {latest_attempt.status}（非 completed），禁止清理"),
                "latest_scan_id": latest_attempt.scan_id,
            }
        if not scan_id:
            return {
                "allowed": False,
                "reason": "scan_id 必填，预览和清理必须绑定明确扫描快照",
                "latest_scan_id": latest_attempt.scan_id,
            }
        if scan_id != latest_attempt.scan_id:
            return {
                "allowed": False,
                "reason": (
                    f"scan_id {scan_id} 不是最新扫描批次" f"（最新为 {latest_attempt.scan_id}），stale ID 拒绝清理"
                ),
                "latest_scan_id": latest_attempt.scan_id,
            }
        return {
            "allowed": True,
            "reason": None,
            "latest_scan_id": latest_attempt.scan_id,
        }

    async def _check_cleanup_allowed(self, scan_id: Optional[str] = None) -> Dict[str, Any]:
        """检查是否允许清理（preview 与 cleanup 共用相同新鲜度规则）。

        规则：
        - 最新扫描必须 status=completed（running/failed 禁止清理）
        - 如提供 scan_id，必须等于最新扫描的 scan_id（stale ID 拒绝）

        Returns:
            {"allowed": bool, "reason": str, "latest_scan_id": str}
        """
        latest = await self._get_latest_scan()
        return self._evaluate_cleanup_snapshot(latest, scan_id)

    async def _build_realtime_manifest(
        self, store: Any, required_downloader_ids: Optional[set] = None
    ) -> Optional[ManifestSnapshot]:
        """重建实时文件清单（用于清理前复核文件是否仍被种子引用）。

        复用 OrphanScanner 的文件清单构建逻辑（不写 DB）。
        返回当前所有种子引用的规范化路径集合。

        Args:
            store: app.state.store

        Returns:
            规范化路径集合（None 表示 manifest 构建失败 → 调用方 fail-closed）
        """
        try:
            return await TorrentManifestBuilder(store).build(required_downloader_ids=required_downloader_ids)
        except Exception as e:
            logger.warning(f"[孤儿清理] 实时 manifest 构建失败: {e}")
            return None

    @staticmethod
    def _identity_complete(candidate: OrphanCurrentCandidate) -> bool:
        return all(
            value is not None
            for value in (
                candidate.file_size,
                candidate.mtime_ns,
                candidate.device_id,
                candidate.inode,
            )
        )

    @staticmethod
    def _candidate_inode(candidate: OrphanCurrentCandidate) -> tuple[int, int]:
        return int(candidate.device_id), int(candidate.inode)

    @staticmethod
    def _path_authorized(candidate: OrphanCurrentCandidate, manifest: ManifestSnapshot) -> bool:
        if candidate.downloader_id not in manifest.downloader_ids:
            return False
        candidate_path = os.path.realpath(candidate.canonical_path)
        for root, downloader_id in manifest.scan_roots:
            if downloader_id != candidate.downloader_id:
                continue
            try:
                if os.path.commonpath([candidate_path, os.path.realpath(root)]) == os.path.realpath(root):
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _owning_root(candidate: OrphanCurrentCandidate, manifest: ManifestSnapshot) -> Optional[str]:
        matches = []
        candidate_path = os.path.realpath(candidate.canonical_path)
        for root, downloader_id in manifest.scan_roots:
            if downloader_id != candidate.downloader_id:
                continue
            try:
                if os.path.commonpath([candidate_path, os.path.realpath(root)]) == os.path.realpath(root):
                    matches.append(root)
            except ValueError:
                continue
        return max(matches, key=len) if matches else None

    # ==================== 查询 ====================

    async def get_latest_scan_result(self) -> Optional[Dict[str, Any]]:
        """获取最新扫描批次结果"""
        record = await self._get_latest_scan()
        if not record:
            return None
        return record.to_dict()

    async def get_orphan_list(
        self,
        page: int = 1,
        page_size: int = 20,
        downloader_id: Optional[str] = None,
        min_size: Optional[int] = None,
        include_deleted: bool = False,
    ) -> Dict[str, Any]:
        """分页查询孤儿文件列表与同一批次的页面扫描上下文。

        Returns:
            分页字段与 scan_context。扫描原始量保留在 display_scan，
            remaining_* 表示该展示批次尚未清理的全量。
        """
        latest_attempt = await self._get_latest_scan()
        display_scan: Optional[OrphanScanResult] = None
        if latest_attempt is not None:
            if latest_attempt.status == "completed":
                display_scan = latest_attempt
            elif latest_attempt.status == "failed":
                display_scan = await self._get_latest_scan(status="completed")

        gate = self._evaluate_cleanup_snapshot(
            latest_attempt,
            display_scan.scan_id if display_scan is not None else None,
        )
        scan_context = {
            "latest_attempt": latest_attempt.to_dict() if latest_attempt is not None else None,
            "display_scan": display_scan.to_dict() if display_scan is not None else None,
            "remaining_count": 0,
            "remaining_size": 0,
            "cleanup_allowed": gate["allowed"],
            "cleanup_block_reason": gate["reason"],
        }
        if display_scan is None:
            return {
                "total": 0,
                "page": page,
                "pageSize": page_size,
                "list": [],
                "scan_context": scan_context,
            }

        remaining_result = await self.db.execute(
            select(
                func.count(OrphanFile.id),
                func.coalesce(func.sum(OrphanFile.file_size), 0),
            ).where(
                OrphanFile.scan_id == display_scan.scan_id,
                OrphanFile.is_deleted == False,  # noqa: E712
            )
        )
        remaining_count, remaining_size = remaining_result.one()
        scan_context["remaining_count"] = int(remaining_count or 0)
        scan_context["remaining_size"] = int(remaining_size or 0)

        conditions = [OrphanFile.scan_id == display_scan.scan_id]
        if not include_deleted:
            conditions.append(OrphanFile.is_deleted == False)  # noqa: E712
        if downloader_id:
            conditions.append(OrphanFile.downloader_id == downloader_id)
        if min_size is not None:
            conditions.append(OrphanFile.file_size >= min_size)

        # 总数
        count_query = select(func.count(OrphanFile.id))
        for cond in conditions:
            count_query = count_query.where(cond)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        list_query = select(OrphanFile).order_by(OrphanFile.file_size.desc(), OrphanFile.id.asc())
        for cond in conditions:
            list_query = list_query.where(cond)
        offset = (page - 1) * page_size
        list_query = list_query.offset(offset).limit(page_size)

        result = await self.db.execute(list_query)
        items = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "list": [item.to_dict() for item in items],
            "scan_context": scan_context,
        }

    async def reconcile_stable_candidate_details(self) -> Dict[str, int]:
        """幂等补齐历史 stable 隔离候选对应的扫描明细。

        仅按候选的 last_seen_scan_id、下载器身份和规范化路径更新该批次仍未
        清理的 OrphanFile；无法匹配时只记录诊断，不跨批次猜测。
        """
        candidate_result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.status.in_(["quarantined", "purged"]),
                OrphanCurrentCandidate.operation_state == "stable",
                OrphanCurrentCandidate.last_seen_scan_id.isnot(None),
            )
        )
        candidates = candidate_result.scalars().all()
        reconciliation_plan: List[tuple[List[int], datetime]] = []
        unmatched_count = 0
        reconciliation_time = datetime.utcnow()

        for candidate in candidates:
            detail_result = await self.db.execute(
                select(OrphanFile).where(
                    OrphanFile.scan_id == candidate.last_seen_scan_id,
                    OrphanFile.is_deleted == False,  # noqa: E712
                )
            )
            candidate_downloader = candidate.downloader_id or ""
            candidate_path = normalize_path(candidate.canonical_path)
            matching_ids = [
                detail.id
                for detail in detail_result.scalars().all()
                if (detail.downloader_id or "") == candidate_downloader
                and normalize_path(detail.file_path) == candidate_path
            ]
            if not matching_ids:
                unmatched_count += 1
                logger.warning(
                    "[孤儿存量对账] 未找到明细: scan_id=%s downloader_id=%s path=%s",
                    candidate.last_seen_scan_id,
                    candidate.downloader_id,
                    candidate.canonical_path,
                )
                continue
            reconciliation_plan.append(
                (
                    matching_ids,
                    candidate.quarantined_at or reconciliation_time,
                )
            )

        updated_count = 0
        if reconciliation_plan:
            try:
                async with admission_controller.db_write_scope():
                    for detail_ids, deleted_at in reconciliation_plan:
                        update_result = await self.db.execute(
                            update(OrphanFile)
                            .where(
                                OrphanFile.id.in_(detail_ids),
                                OrphanFile.is_deleted == False,  # noqa: E712
                            )
                            .values(
                                is_deleted=True,
                                deleted_at=deleted_at,
                                deleted_by="system:reconciliation",
                            )
                        )
                        updated_count += int(update_result.rowcount or 0)
                    await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise

        logger.info(
            "[孤儿存量对账] candidates=%d updated=%d unmatched=%d",
            len(candidates),
            updated_count,
            unmatched_count,
        )
        return {
            "candidate_count": len(candidates),
            "updated_count": updated_count,
            "unmatched_count": unmatched_count,
        }

    # ==================== 清理预览 ====================

    async def cleanup_preview(self, orphan_ids: List[int], scan_id: Optional[str] = None) -> Dict[str, Any]:
        """清理预览（返回文件数 + 总大小）。

        新鲜度门禁：最新扫描必须 completed；scan_id 必须是最新批次（否则 stale 拒绝）。
        """
        gate = await self._check_cleanup_allowed(scan_id)
        if not gate["allowed"]:
            return {
                "rejected": True,
                "reason": gate["reason"],
                "error": gate["reason"],
                "total_count": 0,
                "total_size": 0,
                "items": [],
            }

        result = await self.db.execute(
            select(OrphanFile).where(
                OrphanFile.id.in_(orphan_ids),
                OrphanFile.scan_id == scan_id,
                OrphanFile.is_deleted == False,  # noqa: E712
            )
        )
        items = result.scalars().all()

        total_size = sum(item.file_size for item in items)
        return {
            "total_count": len(items),
            "total_size": total_size,
            "items": [
                {
                    "id": item.id,
                    "file_path": item.file_path,
                    "file_size": item.file_size,
                }
                for item in items
            ],
        }

    # ==================== 手动清理 ====================

    async def cleanup_orphans(
        self,
        orphan_ids: List[int],
        operator: str,
        audit_service: Any = None,
        store: Any = None,
        scan_id: Optional[str] = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """手动清理选中的孤儿文件（安全隔离 + 标记 + 审计日志）。

        语义重做：
        - 新鲜度门禁：最新扫描必须 completed；scan_id 必须最新（stale 拒绝）
        - 删除前实时复核文件身份（size/mtime_ns/inode/符号链接/路径逃逸）
        - 不提供 force 绕过

        Args:
            orphan_ids: 孤儿文件 ID 列表
            operator: 操作者用户名
            audit_service: 审计日志服务（可选）
            store: app.state.store（用于实时 manifest 复核）
            scan_id: 调用方传入的 scan_id（stable ID 校验）

        Returns:
            {"success_count": int, "failed_count": int, "failed_list": [...]}
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("manual_cleanup") as lease_handle:
                    return await self.cleanup_orphans(
                        orphan_ids=orphan_ids,
                        operator=operator,
                        audit_service=audit_service,
                        store=store,
                        scan_id=scan_id,
                        _lease_acquired=True,
                        _lease_handle=lease_handle,
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "success_count": 0,
                    "failed_count": len(orphan_ids),
                    "failed_list": [{"id": oid, "reason": str(exc)} for oid in orphan_ids],
                    "rejected": True,
                    "error": str(exc),
                    "total_size": 0,
                }

        # 新鲜度门禁
        gate = await self._check_cleanup_allowed(scan_id)
        if not gate["allowed"]:
            return {
                "success_count": 0,
                "failed_count": len(orphan_ids),
                "failed_list": [{"id": oid, "reason": gate["reason"]} for oid in orphan_ids],
                "rejected": True,
                "error": gate["reason"],
                "total_size": 0,
            }

        await self._recover_interrupted_operations(
            store=store,
            lease_handle=_lease_handle,
        )

        # 恢复可能已经最终化选中项，必须重新读取当前工作集。
        result = await self.db.execute(
            select(OrphanFile).where(
                OrphanFile.id.in_(orphan_ids),
                OrphanFile.scan_id == scan_id,
                OrphanFile.is_deleted == False,  # noqa: E712
            )
        )
        items = result.scalars().all()

        success_count = 0
        failed_list: List[Dict[str, Any]] = []
        deleted_size = 0

        # 实时 manifest 复核：store 提供时必须成功构建（fail-closed）
        # manifest 构建失败 → 无法确认文件是否仍被种子引用 → 拒绝所有清理
        candidate_result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.canonical_path.in_([normalize_path(item.file_path) for item in items]),
                OrphanCurrentCandidate.status == "candidate",
                OrphanCurrentCandidate.operation_state == "stable",
            )
        )
        candidates = {
            ((candidate.downloader_id or ""), candidate.canonical_path): candidate
            for candidate in candidate_result.scalars().all()
        }
        manifest = await self._build_realtime_manifest(
            store, {candidate.downloader_id for candidate in candidates.values()}
        )
        if manifest is None:
            reason = "实时 manifest 构建失败，无法确认文件是否仍被种子引用（fail-closed）"
            logger.warning(f"[孤儿清理] {reason}")
            return {
                "success_count": 0,
                "failed_count": len(items),
                "failed_list": [{"id": i.id, "file_path": i.file_path, "reason": reason} for i in items],
                "total_size": 0,
            }

        for item in items:
            try:
                canonical = normalize_path(item.file_path)
                if canonical in manifest.expected_paths:
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "文件当前已被种子引用",
                        }
                    )
                    continue

                candidate = candidates.get(((item.downloader_id or ""), canonical))
                if candidate is None:
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "当前候选状态不存在或已失效",
                        }
                    )
                    continue

                if not self._path_authorized(candidate, manifest):
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "文件不属于实时 manifest 授权扫描根",
                        }
                    )
                    continue
                if not self._identity_complete(candidate):
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "候选文件身份字段不完整，需重新扫描",
                        }
                    )
                    continue

                # 删除前实时复核文件身份（fail-closed：不匹配则拒绝删除）
                ok, reason = verify_file_identity(
                    item.file_path,
                    expected_size=item.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    failed_list.append({"id": item.id, "file_path": item.file_path, "reason": reason})
                    logger.warning(f"[孤儿清理] 文件身份复核失败，拒绝删除: {reason}")
                    continue

                # 手动清理同样进入隔离区，避免不可逆 TOCTOU 删除。
                actual_path = item.file_path
                if not os.path.exists(actual_path):
                    failed_list.append(
                        {
                            "id": item.id,
                            "file_path": item.file_path,
                            "reason": "文件不存在",
                        }
                    )
                    continue
                owning_root = self._owning_root(candidate, manifest)
                quarantine_root = resolve_quarantine_root(owning_root, scan_id=scan_id)
                await self._quarantine_candidate(
                    candidate,
                    actual_path,
                    quarantine_root,
                    scan_id=scan_id,
                    operator=operator,
                    lease_handle=_lease_handle,
                )

                deleted_size += item.file_size
                success_count += 1

            except Exception as e:
                logger.error(f"[孤儿清理] 隔离文件失败 {item.file_path}: {e}")
                failed_list.append({"id": item.id, "file_path": item.file_path, "reason": str(e)})

        # 审计日志
        if audit_service and success_count > 0:
            try:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ORPHAN_CLEANUP.value,
                    operator=operator,
                    operation_detail={
                        "action": "manual_cleanup",
                        "success_count": success_count,
                        "failed_count": len(failed_list),
                        "total_size": deleted_size,
                    },
                    operation_result=AuditOperationResult.SUCCESS if not failed_list else AuditOperationResult.PARTIAL,
                    error_message=f"失败 {len(failed_list)} 个" if failed_list else None,
                )
            except Exception as e:
                logger.warning(f"[孤儿清理] 审计日志记录失败: {e}")

        return {
            "success_count": success_count,
            "failed_count": len(failed_list),
            "failed_list": failed_list,
            "total_size": deleted_size,
        }

    # ==================== 自动清理超期（移入隔离区） ====================

    async def auto_cleanup_expired(
        self,
        days_threshold: int,
        operator: str = "system",
        store: Any = None,
        scan_id: Optional[str] = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """自动清理超期孤儿文件（定时任务调用）。

        语义重做：
        - 按 OrphanCurrentCandidate 的「连续成为孤儿的时间」筛选（不再用 mtime）
        - 先移入隔离区（不直接删除），记录 quarantine_path + purge_after
        - 独立的 purge_expired_quarantine 负责到期物理删除

        Args:
            days_threshold: 连续孤儿天数阈值
            operator: 操作者（默认 system）
            store: app.state.store
            scan_id: 本次扫描 ID（必须传入）

        Returns:
            {"quarantined_count": int, "failed_count": int, "total_size": int}
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("auto_cleanup") as lease_handle:
                    return await self.auto_cleanup_expired(
                        days_threshold=days_threshold,
                        operator=operator,
                        store=store,
                        scan_id=scan_id,
                        _lease_acquired=True,
                        _lease_handle=lease_handle,
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "quarantined_count": 0,
                    "failed_count": 0,
                    "total_size": 0,
                    "rejected": True,
                    "error": str(exc),
                }

        lifecycle = OrphanLifecycleService(self.db)
        gate = await self._check_cleanup_allowed(scan_id)
        if not gate["allowed"]:
            return {
                "quarantined_count": 0,
                "failed_count": 0,
                "total_size": 0,
                "rejected": True,
                "error": gate["reason"],
            }

        await self._recover_interrupted_operations(
            store=store,
            lease_handle=_lease_handle,
        )

        # 恢复会改变候选状态，必须在恢复后获取可清理集合。
        purgeable = await lifecycle.get_purgeable_candidates(days_threshold)
        manifest = await self._build_realtime_manifest(store, {candidate.downloader_id for candidate in purgeable})
        if manifest is None:
            return {
                "quarantined_count": 0,
                "failed_count": 0,
                "total_size": 0,
                "rejected": True,
                "error": "实时 manifest 构建失败",
            }

        if not purgeable:
            logger.info(f"[孤儿自动清理] 无满足 {days_threshold} 天条件的候选")
            return {"quarantined_count": 0, "failed_count": 0, "total_size": 0}

        logger.info(f"[孤儿自动清理] 发现 {len(purgeable)} 个满足条件的候选，移入隔离区")

        quarantined_count = 0
        failed_count = 0
        total_size = 0

        for candidate in purgeable:
            try:
                if normalize_path(candidate.canonical_path) in manifest.expected_paths:
                    logger.warning(f"[孤儿自动清理] 文件已被种子引用，跳过: {candidate.canonical_path}")
                    failed_count += 1
                    continue
                if not self._path_authorized(candidate, manifest) or not self._identity_complete(candidate):
                    logger.warning(f"[孤儿自动清理] 路径未授权或身份字段不完整: {candidate.canonical_path}")
                    failed_count += 1
                    continue
                # 推导扫描根（canonical_path 所在的下载器扫描根）
                scan_root = self._owning_root(candidate, manifest)
                quarantine_root = resolve_quarantine_root(scan_root, scan_id=scan_id)

                # 隔离前复核文件身份
                ok, reason = verify_file_identity(
                    candidate.canonical_path,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    failed_count += 1
                    logger.warning(f"[孤儿自动清理] 复核失败，跳过: {reason}")
                    continue

                # 移入隔离区
                await self._quarantine_candidate(
                    candidate,
                    candidate.canonical_path,
                    quarantine_root,
                    scan_id=scan_id,
                    operator=operator,
                    lease_handle=_lease_handle,
                )

                quarantined_count += 1
                total_size += candidate.file_size

            except Exception as e:
                logger.error(f"[孤儿自动清理] 隔离失败 {candidate.canonical_path}: {e}")
                failed_count += 1

        # 审计日志
        try:
            from app.services.audit_service import AuditLogService
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as audit_db:
                audit_service = AuditLogService(audit_db)
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ORPHAN_AUTO_CLEANUP.value,
                    operator=operator,
                    operation_detail={
                        "action": "auto_cleanup_to_quarantine",
                        "days_threshold": days_threshold,
                        "quarantined_count": quarantined_count,
                        "failed_count": failed_count,
                        "total_size": total_size,
                    },
                    operation_result=(
                        AuditOperationResult.SUCCESS if not failed_count else AuditOperationResult.PARTIAL
                    ),
                    error_message=f"失败 {failed_count} 个" if failed_count else None,
                )
                await audit_db.commit()
        except Exception as e:
            logger.warning(f"[孤儿自动清理] 审计日志记录失败: {e}")

        logger.info(
            f"[孤儿自动清理] 完成: 隔离 {quarantined_count}，失败 {failed_count}，"
            f"共 {total_size / (1024**2):.2f} MB"
        )

        return {
            "quarantined_count": quarantined_count,
            "success_count": quarantined_count,  # 向后兼容字段
            "failed_count": failed_count,
            "total_size": total_size,
        }

    # ==================== 隔离区到期物理删除 ====================

    async def purge_expired_quarantine(
        self,
        store: Any = None,
        _lease_acquired: bool = False,
        _lease_handle: Any = None,
    ) -> Dict[str, Any]:
        """物理删除隔离保留期到期的文件（独立清理任务）。

        只删 status=quarantined AND purge_after < now AND 路径仍在隔离区内的文件。
        """
        if not _lease_acquired:
            from app.services.orphan_lease import (
                OrphanLeaseBusyError,
                orphan_maintenance_scope,
            )

            try:
                async with orphan_maintenance_scope("quarantine_purge") as lease_handle:
                    return await self.purge_expired_quarantine(
                        store=store, _lease_acquired=True, _lease_handle=lease_handle
                    )
            except OrphanLeaseBusyError as exc:
                return {
                    "purged_count": 0,
                    "failed_count": 0,
                    "rejected": True,
                    "error": str(exc),
                }

        now = datetime.utcnow()
        await self._recover_interrupted_operations(
            store=store,
            lease_handle=_lease_handle,
        )

        # 恢复可能已物理删除或回退候选，后续只处理最新工作集。
        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.status == "quarantined",
                OrphanCurrentCandidate.operation_state == "stable",
                OrphanCurrentCandidate.purge_after.isnot(None),
                OrphanCurrentCandidate.purge_after < now,
            )
        )
        candidates = result.scalars().all()
        manifest = await self._build_realtime_manifest(store, {candidate.downloader_id for candidate in candidates})
        if manifest is None:
            return {
                "purged_count": 0,
                "failed_count": 0,
                "rejected": True,
                "error": "实时 manifest 构建失败",
            }

        purged_count = 0
        failed_count = 0

        for candidate in candidates:
            try:
                current_manifest = await self._build_realtime_manifest(store, {candidate.downloader_id})
                if current_manifest is None:
                    failed_count += 1
                    continue
                manifest = current_manifest
                qpath = candidate.quarantine_path
                if not qpath or not os.path.exists(qpath):
                    # 文件已不在隔离区（可能已被手动清理）
                    await self._mark_purged(candidate.canonical_path)
                    continue

                if (
                    normalize_path(qpath) in manifest.expected_paths
                    or normalize_path(candidate.canonical_path) in manifest.expected_paths
                ):
                    logger.warning(f"[隔离清理] 文件当前已被种子引用，跳过: {qpath}")
                    failed_count += 1
                    continue
                if not self._path_authorized(candidate, manifest) or not self._identity_complete(candidate):
                    failed_count += 1
                    continue

                # 二次验证：路径仍在预写的精确隔离根内（防路径篡改）。
                quarantine_root = candidate.quarantine_root
                if not quarantine_root:
                    logger.warning(f"[隔离清理] 路径不在隔离区内，跳过: {qpath}")
                    failed_count += 1
                    continue
                if os.path.commonpath([os.path.realpath(qpath), os.path.realpath(quarantine_root)]) != os.path.realpath(
                    quarantine_root
                ):
                    failed_count += 1
                    continue

                ok, reason = verify_file_identity(
                    qpath,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    logger.warning(f"[隔离清理] 文件身份变化，跳过: {reason}")
                    failed_count += 1
                    continue

                tombstone_path = build_quarantine_path(qpath, quarantine_root)
                await self._commit_candidate_state(
                    candidate.canonical_path,
                    operation_state="purge_pending",
                    operation_target_path=tombstone_path,
                    operation_error=None,
                )
                await _lease_handle.assert_owned()
                quarantine_file(
                    qpath,
                    quarantine_root,
                    dest_path=tombstone_path,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                await _lease_handle.assert_owned()
                delete_manifest = await self._build_realtime_manifest(store, {candidate.downloader_id})
                if delete_manifest is None or not self._path_authorized(candidate, delete_manifest):
                    raise OSError("tombstone 删除前无法获得完整授权 manifest")
                if (
                    normalize_path(candidate.canonical_path) in delete_manifest.expected_paths
                    or normalize_path(tombstone_path) in delete_manifest.expected_paths
                ):
                    raise OSError("tombstone 删除前文件已被种子引用")
                ok, reason = verify_file_identity(
                    tombstone_path,
                    expected_size=candidate.file_size,
                    expected_mtime_ns=candidate.mtime_ns,
                    expected_inode=self._candidate_inode(candidate),
                )
                if not ok:
                    raise OSError(reason)
                await _lease_handle.assert_owned()
                os.remove(tombstone_path)
                await _lease_handle.assert_owned()
                await self._mark_purged(candidate.canonical_path)
                purged_count += 1
                logger.info(f"[隔离清理] 物理删除: {qpath}")

            except Exception as e:
                logger.error(f"[隔离清理] 删除失败 {candidate.quarantine_path}: {e}")
                failed_count += 1

        return {"purged_count": purged_count, "failed_count": failed_count}

    async def _mark_purged(self, canonical_path: str) -> None:
        """标记候选为已物理删除。"""
        try:
            async with admission_controller.db_write_scope():
                updated = await OrphanLifecycleService(self.db).mark_purged(
                    canonical_path,
                    commit=False,
                )
                if not updated:
                    raise RuntimeError(f"候选不存在，无法标记 purged: {canonical_path}")
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def _matching_undeleted_details(
        self,
        candidate: OrphanCurrentCandidate,
        scan_id: str,
    ) -> List[OrphanFile]:
        """按批次、下载器身份和规范化路径定位所有未清理明细。"""
        detail_result = await self.db.execute(
            select(OrphanFile).where(
                OrphanFile.scan_id == scan_id,
                OrphanFile.is_deleted == False,  # noqa: E712
            )
        )
        candidate_downloader = candidate.downloader_id or ""
        candidate_path = normalize_path(candidate.canonical_path)
        return [
            detail
            for detail in detail_result.scalars().all()
            if (detail.downloader_id or "") == candidate_downloader
            and normalize_path(detail.file_path) == candidate_path
        ]

    async def _finalize_quarantine(
        self,
        candidate: OrphanCurrentCandidate,
        *,
        quarantine_path: str,
        quarantine_root: str,
        purge_after: datetime,
        scan_id: Optional[str],
        operator: str,
    ) -> int:
        """在同一最终事务中稳定候选并标记对应扫描明细。"""
        effective_scan_id = scan_id or candidate.last_seen_scan_id
        if not effective_scan_id:
            raise RuntimeError("候选缺少 last_seen_scan_id，无法最终化隔离")

        details = await self._matching_undeleted_details(candidate, effective_scan_id)
        if not details:
            raise RuntimeError("隔离最终化找不到同批次、同下载器、同路径的未清理明细")

        finalized_at = datetime.utcnow()
        detail_ids = [detail.id for detail in details]
        try:
            async with admission_controller.db_write_scope():
                candidate_updated = await OrphanLifecycleService(self.db).mark_quarantined(
                    canonical_path=candidate.canonical_path,
                    quarantine_path=quarantine_path,
                    quarantine_root=quarantine_root,
                    purge_after=purge_after,
                    quarantined_at=finalized_at,
                    commit=False,
                )
                if not candidate_updated:
                    raise RuntimeError(f"候选不存在，无法最终化隔离: {candidate.canonical_path}")
                detail_update = await self.db.execute(
                    update(OrphanFile)
                    .where(
                        OrphanFile.id.in_(detail_ids),
                        OrphanFile.is_deleted == False,  # noqa: E712
                    )
                    .values(
                        is_deleted=True,
                        deleted_at=finalized_at,
                        deleted_by=operator,
                    )
                )
                if int(detail_update.rowcount or 0) != len(detail_ids):
                    raise RuntimeError("隔离最终化期间扫描明细发生并发变化")
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return len(detail_ids)

    async def _commit_candidate_state(self, canonical_path: str, **values: Any) -> None:
        """提交不涉及扫描明细的候选恢复状态。"""
        try:
            async with admission_controller.db_write_scope():
                result = await self.db.execute(
                    update(OrphanCurrentCandidate)
                    .where(OrphanCurrentCandidate.canonical_path == canonical_path)
                    .values(**values)
                )
                if not result.rowcount:
                    raise RuntimeError(f"候选不存在: {canonical_path}")
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def _quarantine_candidate(
        self,
        candidate: OrphanCurrentCandidate,
        source_path: str,
        quarantine_root: str,
        *,
        scan_id: Optional[str],
        operator: str,
        lease_handle: Any,
    ) -> str:
        """用预写操作状态跨越数据库与文件系统之间的崩溃窗口。"""
        if lease_handle is None:
            raise RuntimeError("隔离操作缺少维护租约")
        await lease_handle.assert_owned()

        os.makedirs(quarantine_root, exist_ok=True)
        target_path = build_quarantine_path(source_path, quarantine_root)
        purge_after = compute_purge_after(datetime.utcnow())
        candidate.operation_state = "quarantine_pending"
        candidate.operation_target_path = target_path
        candidate.operation_error = None
        candidate.quarantine_root = quarantine_root
        candidate.purge_after = purge_after
        try:
            async with admission_controller.db_write_scope():
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        quarantine_path = quarantine_file(
            source_path,
            quarantine_root,
            dest_path=target_path,
            expected_size=candidate.file_size,
            expected_mtime_ns=candidate.mtime_ns,
            expected_inode=self._candidate_inode(candidate),
        )
        await lease_handle.assert_owned()
        await self._finalize_quarantine(
            candidate,
            quarantine_path=quarantine_path,
            quarantine_root=quarantine_root,
            purge_after=purge_after,
            scan_id=scan_id,
            operator=operator,
        )
        return quarantine_path

    async def _recover_interrupted_operations(
        self,
        manifest: Optional[ManifestSnapshot] = None,
        store: Any = None,
        lease_handle: Any = None,
    ) -> Dict[str, int]:
        """恢复上次进程在 rename/remove 与最终 DB 提交之间中断的操作。"""
        result = await self.db.execute(
            select(OrphanCurrentCandidate).where(
                OrphanCurrentCandidate.operation_state.in_(["quarantine_pending", "purge_pending"])
            )
        )
        candidates = result.scalars().all()
        if not candidates:
            return {"recovered": 0, "failed": 0}

        pending_candidates = [(str(candidate.canonical_path), str(candidate.downloader_id)) for candidate in candidates]
        required_downloader_ids = {downloader_id for _, downloader_id in pending_candidates}
        if manifest is None or not required_downloader_ids.issubset(manifest.downloader_ids):
            manifest = await self._build_realtime_manifest(
                store,
                required_downloader_ids,
            )
        if manifest is None or not required_downloader_ids.issubset(manifest.downloader_ids):
            reason = "恢复 manifest 未覆盖全部 pending 下载器，保持 pending"
            try:
                async with admission_controller.db_write_scope():
                    await self.db.execute(
                        update(OrphanCurrentCandidate)
                        .where(OrphanCurrentCandidate.operation_state.in_(["quarantine_pending", "purge_pending"]))
                        .values(operation_error=reason)
                    )
                    await self.db.commit()
            except Exception:
                await self.db.rollback()
                raise
            logger.error("[孤儿操作恢复] %s", reason)
            return {"recovered": 0, "failed": len(pending_candidates)}

        recovered = 0
        failed = 0

        for canonical_path, _ in pending_candidates:
            candidate = await self.db.get(OrphanCurrentCandidate, canonical_path)
            if candidate is None or candidate.operation_state not in (
                "quarantine_pending",
                "purge_pending",
            ):
                continue
            try:
                if candidate.operation_state == "purge_pending":
                    original = candidate.quarantine_path
                    target = candidate.operation_target_path
                    original_exists = bool(original and os.path.exists(original))
                    target_exists = bool(target and os.path.exists(target))
                    if original_exists and target_exists:
                        raise OSError("purge 恢复发现原路径和 tombstone 同时存在")
                    if target_exists:
                        refreshed = await self._build_realtime_manifest(
                            store,
                            {candidate.downloader_id},
                        )
                        if refreshed is None or not self._path_authorized(candidate, refreshed):
                            raise OSError("purge 恢复无法获得完整授权 manifest")
                        if (
                            normalize_path(candidate.canonical_path) in refreshed.expected_paths
                            or normalize_path(target) in refreshed.expected_paths
                        ):
                            raise OSError("原路径已重新被种子引用，tombstone 转人工处理")
                        ok, reason = verify_file_identity(
                            target,
                            expected_size=candidate.file_size,
                            expected_mtime_ns=candidate.mtime_ns,
                            expected_inode=self._candidate_inode(candidate),
                        )
                        if not ok:
                            raise OSError(reason)
                        if lease_handle is None:
                            raise OSError("purge 恢复缺少维护租约")
                        await lease_handle.assert_owned()
                        os.remove(target)
                        await lease_handle.assert_owned()
                        await self._mark_purged(candidate.canonical_path)
                    elif original_exists:
                        await self._commit_candidate_state(
                            candidate.canonical_path,
                            status="quarantined",
                            operation_state="stable",
                            operation_target_path=None,
                            operation_error=None,
                        )
                    else:
                        await self._mark_purged(candidate.canonical_path)
                    recovered += 1
                    continue

                source = candidate.canonical_path
                target = candidate.operation_target_path
                root = candidate.quarantine_root
                if target and os.path.exists(target):
                    ok, reason = verify_file_identity(
                        target,
                        expected_size=candidate.file_size,
                        expected_mtime_ns=candidate.mtime_ns,
                        expected_inode=self._candidate_inode(candidate),
                    )
                    if not ok:
                        raise OSError(reason)
                    if os.path.exists(source):
                        source_stat = os.stat(source)
                        target_stat = os.stat(target)
                        if (source_stat.st_dev, source_stat.st_ino) == (
                            target_stat.st_dev,
                            target_stat.st_ino,
                        ):
                            if lease_handle is None:
                                raise OSError("硬链接恢复缺少维护租约")
                            await lease_handle.assert_owned()
                            if normalize_path(source) in manifest.expected_paths:
                                os.unlink(target)
                                await lease_handle.assert_owned()
                                await self._commit_candidate_state(
                                    candidate.canonical_path,
                                    status="resolved",
                                    operation_state="stable",
                                    operation_target_path=None,
                                    operation_error=None,
                                )
                                recovered += 1
                                continue
                            os.unlink(source)
                            await lease_handle.assert_owned()
                        else:
                            raise OSError("隔离恢复发现源路径和目标路径身份不同，转人工处理")
                    await self._finalize_quarantine(
                        candidate,
                        quarantine_path=target,
                        quarantine_root=root or os.path.dirname(target),
                        purge_after=candidate.purge_after or compute_purge_after(datetime.utcnow()),
                        scan_id=candidate.last_seen_scan_id,
                        operator="system:recovery",
                    )
                elif normalize_path(source) in manifest.expected_paths and os.path.exists(source):
                    await self._commit_candidate_state(
                        candidate.canonical_path,
                        status="resolved",
                        operation_state="stable",
                        operation_target_path=None,
                        operation_error=None,
                    )
                elif target and root and os.path.exists(source):
                    if not self._path_authorized(candidate, manifest):
                        raise OSError("隔离恢复路径不属于授权扫描根")
                    if lease_handle is None:
                        raise OSError("隔离恢复缺少维护租约")
                    await lease_handle.assert_owned()
                    quarantine_file(
                        source,
                        root,
                        dest_path=target,
                        expected_size=candidate.file_size,
                        expected_mtime_ns=candidate.mtime_ns,
                        expected_inode=self._candidate_inode(candidate),
                    )
                    await lease_handle.assert_owned()
                    await self._finalize_quarantine(
                        candidate,
                        quarantine_path=target,
                        quarantine_root=root,
                        purge_after=candidate.purge_after or compute_purge_after(datetime.utcnow()),
                        scan_id=candidate.last_seen_scan_id,
                        operator="system:recovery",
                    )
                else:
                    raise OSError("隔离恢复时源路径与目标路径均不存在")
                recovered += 1
            except Exception as exc:
                # 保留 pending，后续维护任务继续恢复；错误原因用于诊断。
                await self.db.rollback()
                try:
                    await self._commit_candidate_state(
                        canonical_path,
                        operation_error=str(exc)[:1000],
                    )
                except Exception as error_commit_exc:
                    logger.error(
                        "[孤儿操作恢复] 记录恢复错误失败 %s: %s",
                        canonical_path,
                        error_commit_exc,
                    )
                failed += 1
                logger.error(f"[孤儿操作恢复] {canonical_path}: {exc}")

        return {"recovered": recovered, "failed": failed}

    # ==================== 触发扫描 ====================

    async def trigger_scan(self, scan_type: str, operator: str, app: Any = None) -> Dict[str, Any]:
        """触发扫描（手动/定时）"""
        from app.services.orphan_scanner import OrphanScanner
        from app.services.orphan_lease import (
            OrphanLeaseBusyError,
            orphan_maintenance_scope,
        )

        try:
            async with orphan_maintenance_scope("scan") as lease_handle:
                scanner = OrphanScanner(app=app, lease_handle=lease_handle)
                result = await scanner.scan(scan_type=scan_type, operator=operator)
        except OrphanLeaseBusyError as exc:
            return {"status": "busy", "error": str(exc)}

        # 审计日志
        try:
            await self.db.execute(select(1))  # 确保 session 可用
            from app.services.audit_service import AuditLogService

            audit_service = AuditLogService(self.db)
            await audit_service.log_operation(
                operation_type=AuditOperationType.ORPHAN_SCAN.value,
                operator=operator,
                operation_detail={
                    "scan_id": result.get("scan_id"),
                    "scan_type": scan_type,
                    "total_orphans": result.get("total_orphans", 0),
                    "status": result.get("status"),
                },
                operation_result=(
                    AuditOperationResult.SUCCESS if result.get("status") == "completed" else AuditOperationResult.FAILED
                ),
            )
        except Exception as e:
            logger.warning(f"[孤儿扫描] 审计日志记录失败: {e}")

        return result
