"""
清理任务执行器

提供自动化清理任务功能，支持清理等级3（回收站）和等级4（待删除标签）数据。
支持预览、批量清理、审计日志记录等完整功能。

重构说明（Task 6）：
- cleanup_level4 已重构使用 TorrentDeletionService 统一入口
- 移除直接调用 SDK 删除方法（qbClient、trClient），确保审计日志统一记录
- cleanup_level3 保持原有逻辑（仅处理数据库标记，不涉及下载器删除）
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.torrents.models import TorrentInfo
from app.downloader.models import BtDownloaders
from app.core.file_operations import FileOperationService
from app.core.path_mapping import PathMappingService
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult

from app.services.torrent_deletion_service import (
    TorrentDeletionService,
    DeleteRequest,
    DeleteOption,
    SafetyCheckLevel
)
logger = logging.getLogger(__name__)


class CleanupTaskExecutor:
    """清理任务执行器

    执行清理任务，支持：
    - 等级3清理：回收站数据（deleted_at超过阈值）
    - 等级4清理：待删除标签数据（tags包含pending_delete）
    - 预览功能：清理前预览将要清理的数据
    - 审计日志：记录所有清理操作
    - 并发控制：防止多个清理任务同时执行
    """

    # 类级别的锁，防止并发执行
    _cleanup_lock = asyncio.Lock()

    def __init__(self, db: Session):
        """
        初始化清理任务执行器

        Args:
            db: 数据库会话
        """
        self.db = db

    @staticmethod
    def _sanitize_torrent_name(name: str) -> str:
        """
        脱敏处理种子名称（用于日志输出）

        Args:
            name: 原始种子名称

        Returns:
            脱敏后的种子名称
        """
        if not name:
            return "<空名称>"

        # 如果名称太长，截取前30个字符
        if len(name) > 30:
            return name[:30] + "..."

        return name

    async def execute_cleanup_task(
        self,
        task_config: Dict[str, Any],
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        执行清理任务的主方法

        Args:
            task_config: 任务配置
                {
                    "cleanup_level_3": bool,  # 是否清理等级3
                    "cleanup_level_4": bool,  # 是否清理等级4
                    "days_threshold": int     # 天数阈值（等级3）
                }
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            清理结果
            {
                "level3_cleaned": int,         # 等级3清理数量
                "level4_cleaned": int,         # 等级4清理数量
                "total_size_freed": int,       # 释放的总空间（字节）
                "errors": List[str]            # 错误信息列表
            }
        """
        # 使用类级别锁，防止多个清理任务同时执行
        async with CleanupTaskExecutor._cleanup_lock:
            result = {
                "level3_cleaned": 0,
                "level4_cleaned": 0,
                "total_size_freed": 0,
                "errors": []
            }

            try:
                logger.info(f"开始执行清理任务，操作人: {operator}, 配置: {task_config}")

                # 清理等级3（回收站）
                if task_config.get("cleanup_level_3", False):
                    logger.info("开始清理等级3数据（回收站）")
                    level3_result = await self.cleanup_level3(
                        days_threshold=task_config.get("days_threshold", 30),
                        operator=operator,
                        audit_service=audit_service
                    )
                    result["level3_cleaned"] = level3_result.get("success_count", 0)
                    result["total_size_freed"] += level3_result.get("size_freed", 0)
                    result["errors"].extend(level3_result.get("errors", []))

                # 清理等级4（待删除标签）
                if task_config.get("cleanup_level_4", False):
                    logger.info("开始清理等级4数据（待删除标签）")
                    level4_result = await self.cleanup_level4(
                        operator=operator,
                        audit_service=audit_service
                    )
                    result["level4_cleaned"] = level4_result.get("success_count", 0)
                    result["total_size_freed"] += level4_result.get("size_freed", 0)
                    result["errors"].extend(level4_result.get("errors", []))

                logger.info(f"清理任务执行完成: {result}")
                return result

            except Exception as e:
                error_msg = f"清理任务执行异常: {str(e)}"
                logger.error(error_msg, exc_info=True)
                result["errors"].append(error_msg)
                return result

    async def preview_cleanup(self, task_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        预览将要清理的数据

        Args:
            task_config: 任务配置
                {
                    "cleanup_level_3": bool,
                    "cleanup_level_4": bool,
                    "days_threshold": int
                }

        Returns:
            预览结果
            {
                "level3_count": int,          # 等级3数量
                "level4_count": int,          # 等级4数量
                "total_count": int,           # 总数量
                "total_size_gb": float,       # 总大小（GB）
                "level3_items": List[Dict],   # 等级3项目列表
                "level4_items": List[Dict]    # 等级4项目列表
            }
        """
        try:
            result = {
                "level3_count": 0,
                "level4_count": 0,
                "total_count": 0,
                "total_size_gb": 0.0,
                "level3_items": [],
                "level4_items": []
            }

            # 查询等级3种子
            if task_config.get("cleanup_level_3", False):
                level3_torrents = self._query_level3_torrents(
                    days_threshold=task_config.get("days_threshold", 30)
                )
                result["level3_count"] = len(level3_torrents)
                result["level3_items"] = [
                    {
                        "info_id": t.info_id,
                        "name": t.name,
                        "size": t.size,
                        "deleted_at": t.deleted_at.isoformat() if t.deleted_at else None,
                        "save_path": t.save_path
                    }
                    for t in level3_torrents
                ]

            # 查询等级4种子
            if task_config.get("cleanup_level_4", False):
                level4_torrents = self._query_level4_torrents()
                result["level4_count"] = len(level4_torrents)
                result["level4_items"] = [
                    {
                        "info_id": t.info_id,
                        "name": t.name,
                        "size": t.size,
                        "tags": t.tags,
                        "save_path": t.save_path
                    }
                    for t in level4_torrents
                ]

            # 计算总数和总大小
            result["total_count"] = result["level3_count"] + result["level4_count"]
            total_size = (
                sum(item.get("size", 0) for item in result["level3_items"]) +
                sum(item.get("size", 0) for item in result["level4_items"])
            )
            result["total_size_gb"] = round(total_size / (1024**3), 2)

            logger.info(f"清理预览完成: {result}")
            return result

        except Exception as e:
            logger.error(f"清理预览失败: {str(e)}", exc_info=True)
            return {
                "level3_count": 0,
                "level4_count": 0,
                "total_count": 0,
                "total_size_gb": 0.0,
                "level3_items": [],
                "level4_items": []
            }

    async def cleanup_level3(
        self,
        days_threshold: int,
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        清理等级3（回收站）数据

        步骤：
        1. 查询 deleted_at 超过阈值天的种子
        2. 删除 .waiting-delete 标记文件
        3. 设置 dr=1
        4. 记录审计日志

        Args:
            days_threshold: 天数阈值
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            清理结果
            {
                "success_count": int,
                "failed_count": int,
                "size_freed": int,
                "errors": List[str]
            }
        """
        result = {
            "success_count": 0,
            "failed_count": 0,
            "size_freed": 0,
            "errors": []
        }

        # 收集所有要处理的种子
        torrents_to_process = []

        try:
            # 查询符合条件的种子
            torrents = self._query_level3_torrents(days_threshold)

            if not torrents:
                logger.info(f"没有符合条件的等级3种子（阈值: {days_threshold}天）")
                return result

            logger.info(f"找到 {len(torrents)} 个等级3种子需要清理")

            # 第一阶段：预处理和收集
            for torrent in torrents:
                try:
                    # 获取下载器信息
                    downloader = self.db.query(BtDownloaders).filter(
                        BtDownloaders.downloader_id == torrent.downloader_id,
                        BtDownloaders.dr == 0
                    ).first()

                    # 删除 .waiting-delete 标记文件（降级处理）
                    if downloader and torrent.save_path:
                        try:
                            file_op_service = FileOperationService(
                                path_mapping_service=self._get_path_mapping_service(downloader)
                            )
                            await file_op_service.delete_marker_file(
                                directory_path=torrent.save_path,
                                torrent_name=torrent.name
                            )
                        except Exception as e:
                            logger.warning(f"删除标记文件失败（降级）: {self._sanitize_torrent_name(torrent.name)}, {e}")

                    # 收集待处理的种子
                    torrents_to_process.append(torrent)

                except Exception as e:
                    result["failed_count"] += 1
                    error_msg = f"预处理等级3种子异常: {torrent.info_id}, {str(e)}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # 第二阶段：批量更新数据库
            for torrent in torrents_to_process:
                try:
                    torrent.dr = 1
                    torrent.update_time = datetime.now()
                    torrent.update_by = operator

                    # 统计释放空间
                    result["size_freed"] += torrent.size or 0
                    result["success_count"] += 1

                except Exception as e:
                    result["failed_count"] += 1
                    error_msg = f"更新等级3种子状态异常: {torrent.info_id}, {str(e)}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg, exc_info=True)

            # 统一提交所有更改
            if torrents_to_process:
                try:
                    self.db.commit()
                    logger.info(f"等级3种子数据库批量提交成功: {len(torrents_to_process)} 个")
                except Exception as e:
                    self.db.rollback()
                    error_msg = f"等级3种子数据库提交失败: {str(e)}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg, exc_info=True)
                    # 回滚统计数据
                    result["success_count"] -= len(torrents_to_process)
                    result["failed_count"] += len(torrents_to_process)
                    return result

            # 第三阶段：记录审计日志（可失败，不影响数据库状态）
            if audit_service:
                for torrent in torrents_to_process:
                    try:
                        await audit_service.log_operation(
                            operation_type=AuditOperationType.CLEANUP_L3,
                            operator=operator,
                            torrent_info_id=torrent.info_id,
                            operation_detail={
                                "torrent_name": torrent.name,
                                "downloader_id": torrent.downloader_id,
                                "deleted_at": torrent.deleted_at.isoformat() if torrent.deleted_at else None,
                                "days_threshold": days_threshold
                            },
                            old_value={"status": "in_recycle_bin"},
                            new_value={"status": "deleted"},
                            operation_result=AuditOperationResult.SUCCESS,
                            downloader_id=torrent.downloader_id
                        )
                    except Exception as e:
                        logger.warning(f"记录审计日志失败: {torrent.info_id}, {e}")

            logger.info(f"等级3种子清理完成: 成功{result['success_count']}, 失败{result['failed_count']}")

        except Exception as e:
            self.db.rollback()
            error_msg = f"清理等级3数据失败: {str(e)}"
            result["errors"].append(error_msg)
            logger.error(error_msg, exc_info=True)

        return result

    async def cleanup_level4(
        self,
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        清理等级4（待删除标签）数据

        步骤：
        1. 查询 tags 包含 "pending_delete" 的种子
        2. 使用 TorrentDeletionService 统一删除入口
        3. 记录审计日志（由 TorrentDeletionService 自动处理）

        Args:
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            清理结果
            {
                "success_count": int,
                "failed_count": int,
                "size_freed": int,
                "errors": List[str]
            }
        """
        result = {
            "success_count": 0,
            "failed_count": 0,
            "size_freed": 0,
            "errors": []
        }

        try:
            # 查询符合条件的种子
            torrents = self._query_level4_torrents()

            if not torrents:
                logger.info("没有符合条件的等级4种子（待删除标签）")
                return result

            logger.info(f"找到 {len(torrents)} 个等级4种子需要清理")

            # 使用 TorrentDeletionService 统一删除入口
            # 创建删除服务实例
            deletion_service = TorrentDeletionService(
                db=self.db,
                audit_service=audit_service
            )

            # 创建删除请求
            delete_request = DeleteRequest(
                torrent_info_ids=[t.info_id for t in torrents],
                delete_option=DeleteOption.DELETE_FILES_AND_TORRENT,
                safety_check_level=SafetyCheckLevel.BASIC,  # 清理任务使用基础检查
                force_delete=True,  # 强制删除，跳过安全确认
                reason=f"等级4清理任务: 待删除标签自动清理"
            )

            # 执行删除
            delete_result = await deletion_service.delete_torrents(delete_request)

            # 转换结果格式
            result["success_count"] = delete_result.success_count
            result["failed_count"] = delete_result.failed_count
            result["size_freed"] = delete_result.total_size_freed

            # 收集错误信息
            for failed_torrent in delete_result.failed_torrents:
                error_msg = f"{failed_torrent.get('name', 'Unknown')}: {failed_torrent.get('reason', 'Unknown error')}"
                result["errors"].append(error_msg)

            # 收集安全警告（如果有）
            if delete_result.safety_warnings:
                logger.warning(f"等级4清理安全警告: {delete_result.safety_warnings}")

            logger.info(f"等级4种子清理完成: 成功{result['success_count']}, 失败{result['failed_count']}, 释放空间{result['size_freed']}字节")

        except Exception as e:
            error_msg = f"清理等级4数据失败: {str(e)}"
            result["errors"].append(error_msg)
            logger.error(error_msg, exc_info=True)

        return result


    def _get_path_mapping_service(self, downloader: BtDownloaders) -> Optional[PathMappingService]:
        """
        获取路径映射服务

        Args:
            downloader: 下载器信息

        Returns:
            路径映射服务实例或None
        """
        if downloader.path_mapping:
            try:
                return PathMappingService(downloader.path_mapping)
            except Exception as e:
                logger.warning(f"加载路径映射服务失败: {e}")
        return None
