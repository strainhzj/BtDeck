# -*- coding: utf-8 -*-
"""
孤儿文件管理服务

提供孤儿文件查询、清理预览、手动清理、自动清理超期等功能。
文件删除参考 recycle_bin_service.py 的 manual_cleanup 范式：
路径转换 + UNC 兼容 + os.remove + 审计日志。

@file: orphan_file_service.py
@time: 2026-07-10
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.file_operations import FileOperationService
from app.models.orphan_file import OrphanFile, OrphanScanResult
from app.tasks.resource_guard import admission_controller
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType

logger = logging.getLogger(__name__)


class OrphanFileService:
    """孤儿文件管理服务（异步）"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 查询 ====================

    async def get_latest_scan_result(self) -> Optional[Dict[str, Any]]:
        """获取最新扫描批次结果"""
        result = await self.db.execute(select(OrphanScanResult).order_by(OrphanScanResult.scan_time.desc()).limit(1))
        record = result.scalar_one_or_none()
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
        """分页查询孤儿文件列表。

        Returns:
            {"total": int, "page": int, "pageSize": int, "list": [...]}
        """
        # 基础查询条件
        conditions = []
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

        # 分页查询（取最新扫描批次的孤儿文件优先）
        list_query = select(OrphanFile).order_by(OrphanFile.file_size.desc())
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
        }

    # ==================== 清理预览 ====================

    async def cleanup_preview(self, orphan_ids: List[int]) -> Dict[str, Any]:
        """清理预览（返回文件数 + 总大小）"""
        result = await self.db.execute(
            select(OrphanFile).where(
                OrphanFile.id.in_(orphan_ids),
                OrphanFile.is_deleted == False,  # noqa: E712
            )
        )
        items = result.scalars().all()

        total_size = sum(item.file_size for item in items)
        return {
            "total_count": len(items),
            "total_size": total_size,
            "items": [{"id": item.id, "file_path": item.file_path, "file_size": item.file_size} for item in items],
        }

    # ==================== 手动清理 ====================

    async def cleanup_orphans(
        self,
        orphan_ids: List[int],
        operator: str,
        audit_service: Any = None,
    ) -> Dict[str, Any]:
        """手动清理选中的孤儿文件（物理删除 + 标记 + 审计日志）。

        Args:
            orphan_ids: 孤儿文件 ID 列表
            operator: 操作者用户名
            audit_service: 审计日志服务（可选，传入则记录审计）

        Returns:
            {"success_count": int, "failed_count": int, "failed_list": [...]}
        """
        result = await self.db.execute(
            select(OrphanFile).where(
                OrphanFile.id.in_(orphan_ids),
                OrphanFile.is_deleted == False,  # noqa: E712
            )
        )
        items = result.scalars().all()

        success_count = 0
        failed_list: List[Dict[str, Any]] = []
        deleted_size = 0

        for item in items:
            try:
                # 物理删除文件（支持 UNC 路径兼容）
                file_exists, actual_path = FileOperationService._check_file_exists_with_fallback(item.file_path)
                if file_exists:
                    os.remove(actual_path)
                    logger.info(f"[孤儿清理] 删除文件: {actual_path}")
                else:
                    logger.debug(f"[孤儿清理] 文件不存在（可能已被删除）: {item.file_path}")

                # 标记为已删除
                item.is_deleted = True
                item.deleted_at = datetime.utcnow()
                item.deleted_by = operator
                deleted_size += item.file_size
                success_count += 1

            except Exception as e:
                logger.error(f"[孤儿清理] 删除文件失败 {item.file_path}: {e}")
                failed_list.append({"id": item.id, "file_path": item.file_path, "reason": str(e)})

        # 提交 DB 变更（db_write_scope 串行化）
        async with admission_controller.db_write_scope():
            await self.db.commit()

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

    # ==================== 自动清理超期 ====================

    async def auto_cleanup_expired(self, days_threshold: int, operator: str = "system") -> Dict[str, Any]:
        """自动清理超期孤儿文件（定时任务调用）。

        查询 mtime < (now - days_threshold) 且 is_deleted=False 的孤儿文件，
        物理删除 + 标记 + 审计日志。

        Args:
            days_threshold: 超期天数阈值
            operator: 操作者（默认 system）

        Returns:
            {"success_count": int, "failed_count": int, "total_size": int}
        """
        threshold = datetime.utcnow() - timedelta(days=days_threshold)

        # 查询超期未删除的孤儿文件
        result = await self.db.execute(
            select(OrphanFile).where(
                OrphanFile.is_deleted == False,  # noqa: E712
                OrphanFile.mtime.isnot(None),
                OrphanFile.mtime < threshold,
            )
        )
        items = result.scalars().all()

        if not items:
            logger.info(f"[孤儿自动清理] 无超期孤儿文件（阈值 {days_threshold} 天）")
            return {"success_count": 0, "failed_count": 0, "total_size": 0}

        logger.info(f"[孤儿自动清理] 发现 {len(items)} 个超期孤儿文件，开始清理")

        success_count = 0
        failed_count = 0
        deleted_size = 0

        for item in items:
            try:
                file_exists, actual_path = FileOperationService._check_file_exists_with_fallback(item.file_path)
                if file_exists:
                    os.remove(actual_path)

                item.is_deleted = True
                item.deleted_at = datetime.utcnow()
                item.deleted_by = operator
                deleted_size += item.file_size
                success_count += 1

            except Exception as e:
                logger.error(f"[孤儿自动清理] 删除文件失败 {item.file_path}: {e}")
                failed_count += 1

        # 提交 DB 变更
        async with admission_controller.db_write_scope():
            await self.db.commit()

        # 审计日志（用单独 session，避免与主 session 冲突）
        try:
            from app.services.audit_service import AuditLogService
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as audit_db:
                audit_service = AuditLogService(audit_db)
                await audit_service.log_operation(
                    operation_type=AuditOperationType.ORPHAN_AUTO_CLEANUP.value,
                    operator=operator,
                    operation_detail={
                        "action": "auto_cleanup_expired",
                        "days_threshold": days_threshold,
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "total_size": deleted_size,
                    },
                    operation_result=AuditOperationResult.SUCCESS if not failed_count else AuditOperationResult.PARTIAL,
                    error_message=f"失败 {failed_count} 个" if failed_count else None,
                )
                await audit_db.commit()
        except Exception as e:
            logger.warning(f"[孤儿自动清理] 审计日志记录失败: {e}")

        logger.info(
            f"[孤儿自动清理] 完成: 成功 {success_count}，失败 {failed_count}，"
            f"释放 {deleted_size / (1024**2):.2f} MB"
        )

        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "total_size": deleted_size,
        }

    # ==================== 触发扫描 ====================

    async def trigger_scan(self, scan_type: str, operator: str, app: Any = None) -> Dict[str, Any]:
        """触发扫描（手动/定时）"""
        from app.services.orphan_scanner import OrphanScanner

        scanner = OrphanScanner(app=app)
        result = await scanner.scan(scan_type=scan_type, operator=operator)

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
