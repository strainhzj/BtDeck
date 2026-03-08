"""
种子按等级删除服务

支持4个删除等级:
- Level 1: 删除任务和数据（原有功能）
- Level 2: 删除任务保留数据（原有功能）
- Level 3: 移到回收站（创建标记文件+删除下载器任务+数据库标记）
- Level 4: 添加"待删除"标签

重构说明：现在使用统一的适配器模式（DownloaderDeleteAdapter），
与等级2删除保持一致，提升代码可维护性和扩展性。

Author: Task 5 Implementation
Date: 2025-01-31
Updated: 2025-02-26 - 统一使用适配器模式
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import Request

from app.torrents.models import TorrentInfo
from app.downloader.models import BtDownloaders
from app.core.file_operations import FileOperationService
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.models.setting_templates import DownloaderTypeEnum

logger = logging.getLogger(__name__)


class TorrentDeletionByLevelService:
    """种子按等级删除服务"""

    # 等级4标签名称
    LEVEL4_TAG = "pending_delete"

    def __init__(self, db: Session, request: Request = None):
        """
        初始化删除服务

        Args:
            db: 数据库会话
            request: FastAPI Request 对象（用于访问 app.state.store）
        """
        self.db = db
        self.request = request
        self._adapters = {}  # 适配器缓存

    def _get_adapter(self, downloader: BtDownloaders):
        """
        获取下载器适配器（使用缓存）

        Args:
            downloader: 下载器对象

        Returns:
            下载器适配器实例

        Raises:
            ValueError: 如果无法获取适配器
        """
        # 检查缓存
        if downloader.downloader_id in self._adapters:
            return self._adapters[downloader.downloader_id]

        # 检查 request 和 app.state.store
        if not self.request:
            raise ValueError("Request 对象未初始化")

        app = self.request.app
        if not hasattr(app.state, 'store'):
            raise ValueError("app.state.store 未初始化")

        # 获取缓存的下载器列表
        cached_downloaders = app.state.store.get_snapshot_sync()

        # 从缓存中查找对应的下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
            None
        )

        if not downloader_vo:
            raise ValueError(f"下载器不在缓存中 [downloader_id={downloader.downloader_id}]")

        # 检查下载器是否有效
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            raise ValueError(f"下载器已失效 [downloader_id={downloader.downloader_id}, nickname={downloader_vo.nickname}]")

        # 获取缓存的客户端连接
        client = downloader_vo.client
        if not client:
            raise ValueError(f"下载器客户端连接不存在 [downloader_id={downloader.downloader_id}]")

        # 确定下载器类型
        normalized_type = DownloaderTypeEnum.normalize(downloader.downloader_type)

        if normalized_type == DownloaderTypeEnum.QBITTORRENT:
            downloader_type_str = 'qbittorrent'
        elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
            downloader_type_str = 'transmission'
        else:
            raise ValueError(f"不支持的下载器类型: {downloader.downloader_type}")

        # 使用工厂创建适配器
        from app.services.torrent_deletion_service import DownloaderAdapterFactory
        adapter = DownloaderAdapterFactory.create_adapter(
            downloader_type=downloader_type_str,
            client=client
        )

        # 缓存适配器
        self._adapters[downloader.downloader_id] = adapter

        return adapter

    @staticmethod
    def _add_tag_to_string(existing_tags: Optional[str], new_tag: str, separator: str = ",") -> str:
        """
        将新标签添加到现有标签字符串中（自动去重）

        Args:
            existing_tags: 现有标签字符串（逗号分隔）
            new_tag: 要添加的新标签
            separator: 标签分隔符，默认为逗号

        Returns:
            更新后的标签字符串
        """
        if not existing_tags:
            return new_tag
        
        # 分割现有标签并去除空白
        tag_list = [tag.strip() for tag in existing_tags.split(separator) if tag.strip()]
        
        # 如果新标签不存在，则添加
        if new_tag not in tag_list:
            tag_list.append(new_tag)
        
        # 重新组合为字符串
        return separator.join(tag_list)

    async def delete_by_level(
        self,
        torrent_info_id: str,
        delete_level: int,
        operator: str = "admin",
        audit_service=None
    ) -> Dict[str, Any]:
        """
        按等级删除种子

        Args:
            torrent_info_id: 种子信息ID
            delete_level: 删除等级 (1-4)
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            删除结果字典
        """
        try:
            # 查询种子信息
            torrent = self.db.query(TorrentInfo).filter(
                TorrentInfo.info_id == torrent_info_id,
                TorrentInfo.dr == 0
            ).first()

            if not torrent:
                return {
                    "success": False,
                    "error": "种子不存在",
                    "operation": "query_torrent"
                }

            # 根据删除等级执行不同的删除逻辑
            if delete_level == 1:
                return await self._delete_level1(
                    torrent, operator, audit_service
                )
            elif delete_level == 2:
                return await self._delete_level2(
                    torrent, operator, audit_service
                )
            elif delete_level == 3:
                return await self._delete_level3(
                    torrent, operator, audit_service
                )
            elif delete_level == 4:
                return await self._delete_level4(
                    torrent, operator, audit_service
                )
            else:
                return {
                    "success": False,
                    "error": f"不支持的删除等级: {delete_level}",
                    "operation": "validate_level"
                }

        except Exception as e:
            logger.error(f"按等级删除失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "operation": "delete_by_level"
            }

    async def delete_batch_by_level(
        self,
        torrent_info_ids: List[str],
        delete_level: int,
        operator: str = "admin",
        audit_service=None
    ) -> Dict[str, Any]:
        """
        批量按等级删除种子

        等级3特殊处理：如果备份失败，自动降级为等级4删除

        Args:
            torrent_info_ids: 种子信息ID列表
            delete_level: 删除等级 (1-4)
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            批量删除结果字典
        """
        total = len(torrent_info_ids)
        level3_success = []  # 等级3删除成功
        level4_downgraded = []  # 降级到等级4的种子
        level4_success = []  # 等级4删除成功
        failed = []  # 完全失败的种子

        for torrent_id in torrent_info_ids:
            result = await self.delete_by_level(
                torrent_id, delete_level, operator, audit_service
            )

            # 等级3特殊处理：检查是否需要降级
            if delete_level == 3 and result.get("downgrade_to_level4"):
                # 自动降级为等级4
                logger.info(
                    f"种子 {torrent_id} 备份失败，自动降级为等级4删除: "
                    f"{result.get('message', '')}"
                )

                # 执行等级4删除
                level4_result = await self.delete_by_level(
                    torrent_id, 4, operator, audit_service
                )

                if level4_result.get("success"):
                    level4_downgraded.append({
                        "torrent_id": torrent_id,
                        "torrent_name": result.get("torrent_name", ""),
                        "reason": result.get("message", "备份失败")
                    })
                    level4_success.append(torrent_id)
                else:
                    failed.append({
                        "torrent_id": torrent_id,
                        "message": f"降级到等级4也失败: {level4_result.get('error', '未知错误')}"
                    })

            elif result.get("success"):
                if delete_level == 3:
                    level3_success.append(torrent_id)
                elif delete_level == 4:
                    level4_success.append(torrent_id)
            else:
                failed.append({
                    "torrent_id": torrent_id,
                    "message": result.get("error", "未知错误")
                })

        return {
            "success": len(failed) == 0,
            "total": total,
            "level1_success": [],
            "level2_success": [],
            "level3_success": level3_success,
            "level4_downgraded": level4_downgraded,
            "level4_success": level4_success,
            "failed": failed
        }

    async def _delete_level1(
        self,
        torrent: TorrentInfo,
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        等级1删除: 删除任务和数据（使用适配器模式）

        步骤:
        1. 使用适配器删除种子（删除数据文件）
        2. 更新数据库标记dr=1

        Args:
            torrent: 种子信息
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            删除结果
        """
        try:
            # 获取下载器信息
            downloader = self.db.query(BtDownloaders).filter(
                BtDownloaders.downloader_id == torrent.downloader_id
            ).first()

            if not downloader:
                return {
                    "success": False,
                    "error": "下载器不存在",
                    "operation": "query_downloader"
                }

            # 刷新下载器对象，确保读取到最新配置
            self.db.refresh(downloader)

            # 获取适配器
            try:
                adapter = self._get_adapter(downloader)
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"获取适配器失败: {str(e)}",
                    "operation": "get_adapter"
                }

            # 使用适配器删除种子（删除数据文件）
            from app.services.torrent_deletion_service import DeleteOption, SafetyCheckLevel

            delete_result = await adapter.delete_torrents(
                torrent_hashes=[torrent.hash],
                delete_option=DeleteOption.DELETE_FILES_AND_TORRENT,
                safety_check_level=SafetyCheckLevel.ENHANCED
            )

            if not delete_result.get("success", False):
                error_msg = delete_result.get("error", "未知错误")
                return {
                    "success": False,
                    "error": f"适配器删除失败: {error_msg}",
                    "operation": "adapter_delete"
                }

            # 更新数据库：软删除
            torrent.dr = 1
            torrent.update_time = datetime.now()
            torrent.update_by = operator
            self.db.commit()

            # 记录审计日志
            if audit_service:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L1,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail={
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": downloader.nickname,
                        "torrent_name": torrent.name,
                        "torrent_hash": torrent.hash,
                        "delete_files": True
                    },
                    old_value={"status": "active", "dr": 0},
                    new_value={"status": "deleted", "dr": 1},
                    operation_result=AuditOperationResult.SUCCESS,
                    downloader_id=torrent.downloader_id
                )

            return {
                "success": True,
                "operation": "delete_level1",
                "message": "已删除种子和数据文件"
            }

        except Exception as e:
            logger.error(f"等级1删除失败: {str(e)}", exc_info=True)

            # 记录失败的审计日志
            if audit_service:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L1,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail={
                        "error": str(e),
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": downloader.nickname if downloader else None,
                        "torrent_name": torrent.name
                    },
                    operation_result=AuditOperationResult.FAILED,
                    error_message=str(e),
                    downloader_id=torrent.downloader_id
                )

            return {
                "success": False,
                "error": str(e),
                "operation": "delete_level1"
            }

    async def _delete_level2(
        self,
        torrent: TorrentInfo,
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        等级2删除: 删除任务保留数据（使用适配器模式）

        步骤:
        1. 使用适配器删除种子（不删除数据文件）
        2. 更新数据库标记dr=1

        Args:
            torrent: 种子信息
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            删除结果
        """
        try:
            # 获取下载器信息
            downloader = self.db.query(BtDownloaders).filter(
                BtDownloaders.downloader_id == torrent.downloader_id
            ).first()

            if not downloader:
                return {
                    "success": False,
                    "error": "下载器不存在",
                    "operation": "query_downloader"
                }

            # 刷新下载器对象，确保读取到最新配置
            self.db.refresh(downloader)

            # 获取适配器
            try:
                adapter = self._get_adapter(downloader)
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"获取适配器失败: {str(e)}",
                    "operation": "get_adapter"
                }

            # 使用适配器删除种子（不删除数据文件）
            from app.services.torrent_deletion_service import DeleteOption, SafetyCheckLevel

            delete_result = await adapter.delete_torrents(
                torrent_hashes=[torrent.hash],
                delete_option=DeleteOption.DELETE_ONLY_TORRENT,
                safety_check_level=SafetyCheckLevel.ENHANCED
            )

            if not delete_result.get("success", False):
                error_msg = delete_result.get("error", "未知错误")
                return {
                    "success": False,
                    "error": f"适配器删除失败: {error_msg}",
                    "operation": "adapter_delete"
                }

            # 更新数据库：软删除
            torrent.dr = 1
            torrent.update_time = datetime.now()
            torrent.update_by = operator
            self.db.commit()

            # 记录审计日志
            if audit_service:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L2,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail={
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": downloader.nickname,
                        "torrent_name": torrent.name,
                        "torrent_hash": torrent.hash,
                        "delete_files": False
                    },
                    old_value={"status": "active", "dr": 0},
                    new_value={"status": "deleted", "dr": 1},
                    operation_result=AuditOperationResult.SUCCESS,
                    downloader_id=torrent.downloader_id
                )

            return {
                "success": True,
                "operation": "delete_level2",
                "message": "已删除种子任务，保留数据文件"
            }

        except Exception as e:
            logger.error(f"等级2删除失败: {str(e)}", exc_info=True)

            # 记录失败的审计日志
            if audit_service:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L2,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail={
                        "error": str(e),
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": downloader.nickname if downloader else None,
                        "torrent_name": torrent.name
                    },
                    operation_result=AuditOperationResult.FAILED,
                    error_message=str(e),
                    downloader_id=torrent.downloader_id
                )

            return {
                "success": False,
                "error": str(e),
                "operation": "delete_level2"
            }

    async def _delete_level4(
        self,
        torrent: TorrentInfo,
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        等级4删除: 添加"待删除"标签

        Args:
            torrent: 种子信息
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            删除结果
        """
        try:
            # 获取下载器信息
            downloader = self.db.query(BtDownloaders).filter(
                BtDownloaders.downloader_id == torrent.downloader_id
            ).first()

            if not downloader:
                return {
                    "success": False,
                    "error": "下载器不存在",
                    "operation": "query_downloader"
                }

            # 🔧 修复：强制刷新下载器对象，确保读取到最新的路径映射配置
            # 问题描述：SQLAlchemy 的 identity map 可能返回缓存的旧对象
            # 解决方案：使用 refresh() 强制从数据库重新读取数据
            self.db.refresh(downloader)

            logger.info(
                f"[路径映射刷新] downloader_id={downloader.downloader_id}, "
                f"path_mapping配置={'已配置' if downloader.path_mapping else '未配置'}"
            )

            # 使用适配器添加标签（支持qBittorrent和Transmission）
            try:
                adapter = self._get_adapter(downloader)
                success, message = await adapter.add_tag_to_torrent(
                    torrent_hash=torrent.hash,
                    tag=self.LEVEL4_TAG
                )
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"获取适配器失败: {str(e)}",
                    "operation": "get_adapter"
                }

            if not success:
                return {
                    "success": False,
                    "error": message,
                    "operation": "add_tag"
                }

            # 🔧 新增：同步更新数据库标签
            old_tags = torrent.tags
            db_update_success = True
            db_update_error = None

            try:
                # 使用辅助函数追加标签（自动去重）
                torrent.tags = self._add_tag_to_string(torrent.tags, self.LEVEL4_TAG)
                # 提交数据库变更
                self.db.commit()
                logger.info(f"数据库标签更新成功: info_id={torrent.info_id}, old_tags={old_tags}, new_tags={torrent.tags}")
            except Exception as db_error:
                db_update_success = False
                db_update_error = str(db_error)
                logger.error(f"数据库标签更新失败: info_id={torrent.info_id}, error={db_update_error}", exc_info=True)
                # 回滚数据库会话，避免影响其他操作
                self.db.rollback()

            # 记录审计日志
            if audit_service:
                # 构建操作详情
                operation_detail = {
                    "tag": self.LEVEL4_TAG,
                    "downloader_id": torrent.downloader_id,
                    "downloader_name": downloader.nickname,
                    "torrent_name": torrent.name,
                    "torrent_hash": torrent.hash,
                    "downloader_tag_updated": True
                }

                # 如果数据库更新也成功，在审计日志中注明
                if db_update_success:
                    operation_detail["database_tag_updated"] = True
                    operation_detail["old_tags"] = old_tags
                    operation_detail["new_tags"] = torrent.tags

                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L4,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail=operation_detail,
                    old_value={"tags": old_tags},
                    new_value={"tags": torrent.tags},
                    operation_result=AuditOperationResult.SUCCESS,
                    downloader_id=torrent.downloader_id
                )

            # 构建返回消息
            message = "已添加待删除标签"
            if not db_update_success:
                message += "（数据库标签更新失败，但不影响下载器标签）"

            return {
                "success": True,
                "operation": "delete_level4",
                "tag": self.LEVEL4_TAG,
                "message": message,
                "db_update_success": db_update_success,
                "db_update_error": db_update_error
            }

        except Exception as e:
            logger.error(f"等级4删除失败: {str(e)}", exc_info=True)

            # 记录失败的审计日志
            if audit_service:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L4,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail={
                        "error": str(e),
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": downloader.nickname if downloader else None,
                        "torrent_name": torrent.name
                    },
                    operation_result=AuditOperationResult.FAILED,
                    error_message=str(e),
                    downloader_id=torrent.downloader_id
                )

            return {
                "success": False,
                "error": str(e),
                "operation": "delete_level4"
            }

    async def _delete_level3(
        self,
        torrent: TorrentInfo,
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        等级3删除: 移到回收站

        步骤:
        1. 创建标记文件
        2. 从下载器删除任务
        3. 更新数据库标记deleted_at
        4. 记录审计日志

        Args:
            torrent: 种子信息
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            删除结果
        """
        try:
            # 获取下载器信息
            downloader = self.db.query(BtDownloaders).filter(
                BtDownloaders.downloader_id == torrent.downloader_id
            ).first()

            if not downloader:
                return {
                    "success": False,
                    "error": "下载器不存在",
                    "operation": "query_downloader"
                }

            # 🔧 修复：强制刷新下载器对象，确保读取到最新的路径映射配置
            # 问题描述：SQLAlchemy 的 identity map 可能返回缓存的旧对象
            # 解决方案：使用 refresh() 强制从数据库重新读取数据
            self.db.refresh(downloader)

            logger.info(
                f"[路径映射刷新] downloader_id={downloader.downloader_id}, "
                f"path_mapping配置={'已配置' if downloader.path_mapping else '未配置'}"
            )

            # 步骤1: 创建标记文件
            file_op_service = downloader.file_operations_service
            if not file_op_service:
                return {
                    "success": False,
                    "error": "文件操作服务不可用",
                    "operation": "get_file_service"
                }

            # 验证路径映射配置：等级3删除功能必须配置 path_mapping（JSON格式）
            if not downloader.path_mapping:
                return {
                    "success": False,
                    "error": (
                        "等级3删除功能必须配置路径映射（path_mapping）。"
                        "请先在下载器设置中配置路径映射后再执行此操作。"
                    ),
                    "operation": "validate_path_mapping",
                    "help": "前往下载器设置页面，配置路径映射（path_mapping字段）"
                }

            # P0-2 修复: 验证 torrent.save_path 和 torrent.name 不为 None
            if not torrent.save_path:
                return {
                    "success": False,
                    "error": "种子保存路径为空，无法创建标记文件",
                    "operation": "validate_save_path"
                }

            if not torrent.name:
                return {
                    "success": False,
                    "error": "种子名称为空，无法创建标记文件",
                    "operation": "validate_torrent_name"
                }

            marker_result = await file_op_service.create_marker_file(
                directory_path=torrent.save_path,
                torrent_name=torrent.name,
                torrent_uuid=torrent.info_id,
                downloader_id=torrent.downloader_id
            )

            if not marker_result.get("success"):
                error_msg = marker_result.get("error", "创建标记文件失败")
                logger.error(f"等级3删除失败: {error_msg}")

                # 根据用户要求,失败时不执行后续操作
                return {
                    "success": False,
                    "error": error_msg,
                    "operation": "create_marker",
                    "fallback": marker_result.get("fallback", False)
                }

            # ========== 步骤1.5: 备份种子文件（降级处理） ==========
            backup_success = False
            backup_file_path = torrent.backup_file_path
            backup_error_message = None

            # 检查是否需要备份：backup_file_path为空或文件不存在
            need_backup = (
                not torrent.backup_file_path or
                not os.path.exists(torrent.backup_file_path)
            )

            if need_backup:
                try:
                    from app.core.torrent_file_backup import TorrentFileBackupService

                    # 🔥 使用新的备份方法：从下载器的 torrent_save_path 备份
                    # 不再需要路径映射服务
                    backup_service = TorrentFileBackupService()

                    # 在线程池中执行同步备份操作
                    loop = asyncio.get_event_loop()
                    backup_result = await loop.run_in_executor(
                        None,
                        backup_service.backup_torrent_file_from_downloader_save_path,
                        torrent.info_id,
                        torrent.hash,
                        torrent.name,
                        downloader.torrent_save_path  # 🔥 使用下载器的 torrent_save_path
                    )

                    if backup_result['success']:
                        backup_success = True
                        backup_file_path = backup_result['backup_file_path']
                        logger.info(f"等级3删除时种子文件备份成功: {torrent.name}")
                    else:
                        # 🔥 备份失败，返回降级标记
                        backup_error_message = backup_result.get('error_message', 'Unknown error')
                        logger.warning(
                            f"等级3删除时种子文件备份失败，降级为等级4: {torrent.name}, "
                            f"原因: {backup_error_message}"
                        )

                        # 删除已创建的标记文件（回滚）
                        try:
                            await file_op_service.delete_marker_file(
                                directory_path=torrent.save_path,
                                torrent_name=torrent.name
                            )
                            logger.info(f"已回滚标记文件: {torrent.name}")
                        except Exception as rollback_error:
                            logger.error(f"回滚标记文件失败: {str(rollback_error)}")

                        # 返回降级标记
                        return {
                            "success": False,
                            "downgrade_to_level4": True,  # 🔥 降级标记
                            "torrent_id": torrent.info_id,
                            "torrent_name": torrent.name,
                            "message": f"种子文件备份失败: {backup_error_message}",
                            "operation": "backup_torrent_file"
                        }

                except Exception as backup_err:
                    # 🔥 备份异常，返回降级标记
                    backup_error_message = str(backup_err)
                    logger.warning(
                        f"等级3删除时种子文件备份异常，降级为等级4: {torrent.name}, "
                        f"错误: {backup_error_message}"
                    )

                    # 删除已创建的标记文件（回滚）
                    try:
                        await file_op_service.delete_marker_file(
                            directory_path=torrent.save_path,
                            torrent_name=torrent.name
                        )
                        logger.info(f"已回滚标记文件: {torrent.name}")
                    except Exception as rollback_error:
                        logger.error(f"回滚标记文件失败: {str(rollback_error)}")

                    # 返回降级标记
                    return {
                        "success": False,
                        "downgrade_to_level4": True,  # 🔥 降级标记
                        "torrent_id": torrent.info_id,
                        "torrent_name": torrent.name,
                        "message": f"种子文件备份异常: {backup_error_message}",
                        "operation": "backup_torrent_file"
                    }
            else:
                backup_success = True
                logger.debug(f"种子文件已存在备份，跳过: {torrent.name}")

            # ========== 步骤1.6: 获取文件列表（用于回收站清理） ==========
            # 使用适配器获取种子文件列表（支持qBittorrent和Transmission）
            original_file_list = None
            try:
                adapter = self._get_adapter(downloader)
                get_files_success, file_list, files_error = await adapter.get_torrent_files(
                    torrent_hash=torrent.hash
                )
                if get_files_success:
                    import json
                    original_file_list = json.dumps(file_list, ensure_ascii=False)
                    logger.info(f"获取文件列表成功: {len(file_list)} 个文件")
                else:
                    logger.warning(f"获取文件列表失败: {files_error}，继续删除但不记录文件列表")
            except ValueError as e:
                logger.warning(f"获取适配器失败: {str(e)}，跳过文件列表获取")
            except Exception as e:
                logger.warning(f"获取文件列表异常: {str(e)}，继续删除但不记录文件列表")

            # ========== 步骤1.7: 移动种子文件到回收站 ==========
            # 自动检测单文件或多文件种子，并执行相应的移动操作
            # - 单文件：movie.mkv -> movie.pending_delete.mkv（直接重命名）
            # - 多文件：创建新文件夹 [文件夹名].pending_delete，移动所有内容
            move_result = await self._move_torrent_files_for_recycle(
                file_op_service=file_op_service,
                save_path=torrent.save_path,
                torrent_name=torrent.name
            )

            if not move_result.get("success"):
                # 移动失败，回滚操作
                logger.warning(
                    f"移动种子失败 ({move_result.get('torrent_type', 'unknown')}): "
                    f"{move_result.get('error')}, 回滚标记文件"
                )
                try:
                    # 删除标记文件
                    await file_op_service.delete_marker_file(
                        directory_path=torrent.save_path,
                        torrent_name=torrent.name
                    )
                except Exception as rollback_error:
                    logger.error(f"回滚标记文件失败: {str(rollback_error)}")

                return {
                    "success": False,
                    "error": f"移动种子失败: {move_result.get('error')}",
                    "operation": "move_torrent",
                    "torrent_type": move_result.get("torrent_type"),
                    "rolled_back": True
                }

            # 步骤2: 从下载器删除任务（不删除数据文件）
            delete_success, delete_error = await self._delete_from_downloader(
                downloader, torrent, delete_data=False
            )

            if not delete_success:
                # 删除失败，需要回滚：恢复文件位置 + 删除标记文件
                logger.warning(f"从下载器删除失败,回滚文件移动和标记文件: {delete_error}")

                # 回滚1: 恢复文件移动
                try:
                    rollback_result = await self._rollback_file_move(move_result)
                    if rollback_result.get("success"):
                        logger.info(f"回滚成功: 文件位置已恢复")
                    else:
                        logger.warning(f"回滚文件移动失败: {rollback_result.get('error')}")
                except Exception as restore_error:
                    logger.error(f"回滚文件移动异常: {str(restore_error)}")

                # 回滚2: 删除标记文件
                try:
                    await file_op_service.delete_marker_file(
                        directory_path=torrent.save_path,
                        torrent_name=torrent.name
                    )
                except Exception as marker_error:
                    logger.error(f"回滚标记文件失败: {str(marker_error)}")

                return {
                    "success": False,
                    "error": f"从下载器删除失败: {delete_error}",
                    "operation": "delete_from_downloader",
                    "rolled_back": True
                }

            # 步骤3: 更新数据库
            torrent.soft_delete(save_original_filename=True)

            # 更新backup_file_path（如果备份成功）
            if backup_success and backup_file_path:
                torrent.backup_file_path = backup_file_path

            # 更新original_file_list（如果获取成功）
            if original_file_list:
                torrent.original_file_list = original_file_list

            torrent.update_time = datetime.now()
            torrent.update_by = operator

            self.db.commit()

            # 记录审计日志
            if audit_service:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L3,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail={
                        "save_path": torrent.save_path,
                        "torrent_name": torrent.name,
                        "original_filename": torrent.original_filename,
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": downloader.nickname,
                        "marker_file_created": marker_result.get("success", False),
                        "backup_file_created": backup_success,
                        "backup_file_path": backup_file_path if backup_success else None,
                        "file_list_obtained": original_file_list is not None,
                        "file_count": len(original_file_list) if original_file_list else 0,
                        "torrent_moved": True,
                        "torrent_type": move_result.get("torrent_type"),
                        "is_directory": move_result.get("is_directory"),
                        "original_name": move_result.get("original_name"),
                        "new_name": move_result.get("new_name"),
                        "new_path": move_result.get("new_path"),
                        "moved_count": move_result.get("moved_count", 1)
                    },
                    old_value={
                        "status": "active",
                        "deleted_at": None,
                        "torrent_name": move_result.get("original_name")
                    },
                    new_value={
                        "status": "in_recycle_bin",
                        "deleted_at": torrent.deleted_at.isoformat(),
                        "torrent_name": move_result.get("new_name")
                    },
                    operation_result=AuditOperationResult.SUCCESS,
                    downloader_id=torrent.downloader_id
                )

            return {
                "success": True,
                "operation": "delete_level3",
                "deleted_at": torrent.deleted_at.isoformat(),
                "original_filename": torrent.original_filename,
                "torrent_moved": True,
                "torrent_type": move_result.get("torrent_type"),
                "is_directory": move_result.get("is_directory"),
                "original_name": move_result.get("original_name"),
                "new_name": move_result.get("new_name"),
                "message": f"已移至回收站 ({move_result.get('torrent_type')})"
            }

        except Exception as e:
            logger.error(f"等级3删除失败: {str(e)}", exc_info=True)

            # 记录失败的审计日志
            if audit_service:
                await audit_service.log_operation(
                    operation_type=AuditOperationType.DELETE_L3,
                    operator=operator,
                    torrent_info_id=torrent.info_id,
                    operation_detail={
                        "error": str(e),
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": downloader.nickname if downloader else None,
                        "torrent_name": torrent.name
                    },
                    operation_result=AuditOperationResult.FAILED,
                    error_message=str(e),
                    downloader_id=torrent.downloader_id
                )

            return {
                "success": False,
                "error": str(e),
                "operation": "delete_level3"
            }

    async def _add_tag_qbittorrent(
        self,
        downloader: BtDownloaders,
        torrent_hash: str,
        tag: str
    ) -> Tuple[bool, str]:
        """
        为qBittorrent种子添加标签（使用 app.state.store 缓存的客户端连接）

        Args:
            downloader: 下载器信息
            torrent_hash: 种子哈希值
            tag: 标签名称

        Returns:
            (成功标志, 错误消息)
        """
        # 步骤1: 获取 app 对象并检查缓存初始化
        if not self.request:
            return False, "Request 对象未初始化"

        app = self.request.app if hasattr(self.request, 'app') else None
        if not app:
            return False, "无法获取 app 对象"

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            return False, "下载器缓存未初始化"

        # 步骤2: 从缓存获取下载器
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
            None
        )

        # 步骤3: 检查下载器是否在缓存中
        if not downloader_vo:
            return False, f"下载器不在缓存中 [downloader_id={downloader.downloader_id}]"

        # 步骤4: 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            return False, f"下载器已失效 [downloader_id={downloader.downloader_id}, nickname={downloader_vo.nickname}]"

        # 步骤5: 获取并验证客户端连接
        client = downloader_vo.client
        if not client:
            return False, f"下载器客户端连接不存在 [downloader_id={downloader.downloader_id}]"

        try:
            # 创建标签（如果不存在）
            try:
                client.torrent_tags.create_tags(tags=tag)
            except Exception as e:
                # 标签可能已存在,忽略错误
                logger.debug(f"创建标签可能失败(可能已存在): {str(e)}")

            # 为种子添加标签
            client.torrents_add_tags(
                torrent_hashes=[torrent_hash],
                tags=[tag]
            )

            logger.info(f"qBittorrent种子 {torrent_hash} 已添加标签: {tag}")
            return True, ""

        except Exception as e:
            error_msg = f"qBittorrent添加标签失败: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    async def _add_label_transmission(
        self,
        downloader: BtDownloaders,
        torrent_hash: str,
        label: str
    ) -> Tuple[bool, str]:
        """
        为Transmission种子添加标签（使用 app.state.store 缓存的客户端连接）

        Args:
            downloader: 下载器信息
            torrent_hash: 种子哈希值（SHA1），Transmission API必需参数
            label: 标签名称

        Returns:
            (成功标志, 错误消息)
        """
        # 步骤1: 获取 app 对象并检查缓存初始化
        if not self.request:
            return False, "Request 对象未初始化"

        app = self.request.app if hasattr(self.request, 'app') else None
        if not app:
            return False, "无法获取 app 对象"

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            return False, "下载器缓存未初始化"

        # 步骤2: 从缓存获取下载器
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
            None
        )

        # 步骤3: 检查下载器是否在缓存中
        if not downloader_vo:
            return False, f"下载器不在缓存中 [downloader_id={downloader.downloader_id}]"

        # 步骤4: 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            return False, f"下载器已失效 [downloader_id={downloader.downloader_id}, nickname={downloader_vo.nickname}]"

        # 步骤5: 获取并验证客户端连接
        client = downloader_vo.client
        if not client:
            return False, f"下载器客户端连接不存在 [downloader_id={downloader.downloader_id}]"

        try:
            # 🔥 重要：先获取现有标签，再追加新标签（避免覆盖现有标签）
            # 问题：直接使用 labels=[label] 会覆盖所有现有标签
            # 解决：获取现有标签列表，追加新标签后一起设置

            # 步骤1: 获取种子信息（包含现有标签）
            torrent_info = client.get_torrent(torrent_hash)

            # 步骤2: 提取现有标签列表
            existing_labels = list(torrent_info.labels) if torrent_info.labels else []

            # 步骤3: 追加新标签（自动去重）
            if label not in existing_labels:
                existing_labels.append(label)
                logger.debug(f"Transmission标签追加: {torrent_hash}, 原标签: {existing_labels[:-1]}, 新标签: {label}")
            else:
                logger.info(f"Transmission标签已存在: {torrent_hash}, label: {label}")
                return True, ""

            # 步骤4: 设置更新后的标签列表
            client.change_torrent(
                ids=[torrent_hash],
                labels=existing_labels
            )

            logger.info(f"Transmission种子 {torrent_hash} 已添加label: {label}, 完整标签列表: {existing_labels}")
            return True, ""

        except Exception as e:
            error_msg = f"Transmission添加label失败: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    async def _delete_from_downloader(
        self,
        downloader: BtDownloaders,
        torrent: TorrentInfo,
        delete_data: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        从下载器删除种子

        Args:
            downloader: 下载器信息
            torrent: 种子信息
            delete_data: 是否删除数据文件

        Returns:
            (成功标志, 错误消息)
        """
        try:
            # 🔧 修复：使用属性方法判断下载器类型（支持整数0/1和字符串）
            if downloader.is_qbittorrent:
                return await self._delete_from_qbittorrent(
                    downloader, torrent.hash, delete_data
                )
            elif downloader.is_transmission:
                # 🔥 重要：Transmission需要使用 hash（SHA1哈希值），而不是 torrent_id（数字ID）
                # 错误示例：ids="1924" -> ❌ torrent ids 1924 is not valid torrent id
                # 正确示例：ids="17d79018082cb1fe4c51782207e909b6b18b7c41" -> ✅ 成功
                return await self._delete_from_transmission(
                    downloader, torrent.hash, delete_data
                )
            else:
                return False, f"不支持的下载器类型: {downloader.downloader_type} (type: {type(downloader.downloader_type).__name__})"

        except Exception as e:
            error_msg = f"从下载器删除失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def _delete_from_qbittorrent(
        self,
        downloader: BtDownloaders,
        torrent_hash: str,
        delete_data: bool
    ) -> Tuple[bool, Optional[str]]:
        """从qBittorrent删除种子（使用 app.state.store 缓存的客户端连接）"""
        # 步骤1: 获取 app 对象并检查缓存初始化
        if not self.request:
            return False, "Request 对象未初始化"

        app = self.request.app if hasattr(self.request, 'app') else None
        if not app:
            return False, "无法获取 app 对象"

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            return False, "下载器缓存未初始化"

        # 步骤2: 从缓存获取下载器
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
            None
        )

        # 步骤3: 检查下载器是否在缓存中
        if not downloader_vo:
            return False, f"下载器不在缓存中 [downloader_id={downloader.downloader_id}]"

        # 步骤4: 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            return False, f"下载器已失效 [downloader_id={downloader.downloader_id}, nickname={downloader_vo.nickname}]"

        # 步骤5: 获取并验证客户端连接
        client = downloader_vo.client
        if not client:
            return False, f"下载器客户端连接不存在 [downloader_id={downloader.downloader_id}]"

        try:
            client.torrents_delete(
                torrent_hashes=torrent_hash,
                delete_files=delete_data
            )

            logger.info(f"qBittorrent种子 {torrent_hash} 已删除, 删除数据: {delete_data}")
            return True, None

        except Exception as e:
            error_msg = f"qBittorrent删除失败: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    async def _delete_from_transmission(
        self,
        downloader: BtDownloaders,
        torrent_hash: str,
        delete_data: bool
    ) -> Tuple[bool, Optional[str]]:
        """从Transmission删除种子（使用 app.state.store 缓存的客户端连接）

        Args:
            downloader: 下载器信息
            torrent_hash: 种子哈希值（SHA1），Transmission API必需参数
            delete_data: 是否删除数据文件
        """
        # 步骤1: 获取 app 对象并检查缓存初始化
        if not self.request:
            return False, "Request 对象未初始化"

        app = self.request.app if hasattr(self.request, 'app') else None
        if not app:
            return False, "无法获取 app 对象"

        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            return False, "下载器缓存未初始化"

        # 步骤2: 从缓存获取下载器
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
            None
        )

        # 步骤3: 检查下载器是否在缓存中
        if not downloader_vo:
            return False, f"下载器不在缓存中 [downloader_id={downloader.downloader_id}]"

        # 步骤4: 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            return False, f"下载器已失效 [downloader_id={downloader.downloader_id}, nickname={downloader_vo.nickname}]"

        # 步骤5: 获取并验证客户端连接
        client = downloader_vo.client
        if not client:
            return False, f"下载器客户端连接不存在 [downloader_id={downloader.downloader_id}]"

        try:
            client.remove_torrent(
                ids=torrent_hash,  # ✅ 使用SHA1哈希值
                delete_data=delete_data
            )

            logger.info(f"Transmission种子 {torrent_hash} 已删除, 删除数据: {delete_data}")
            return True, None

        except Exception as e:
            error_msg = f"Transmission删除失败: {str(e)}"
            logger.error(error_msg)
            return False, error_msg


    # ========== 新增方法：获取种子文件列表 ==========
    
    async def _get_torrent_files_from_qbittorrent(
        self,
        downloader: BtDownloaders,
        torrent_hash: str
    ) -> Tuple[bool, Optional[List[str]], Optional[str]]:
        """
        从 qBittorrent 获取种子文件列表（使用 app.state.store 缓存的客户端连接）
        
        Args:
            downloader: 下载器信息
            torrent_hash: 种子哈希值
        
        Returns:
            (成功标志, 相对路径列表, 错误消息)
        """
        # 步骤1: 获取 app 对象并检查缓存初始化
        if not self.request:
            return False, None, "Request 对象未初始化"
        
        app = self.request.app if hasattr(self.request, 'app') else None
        if not app:
            return False, None, "无法获取 app 对象"
        
        # 检查缓存是否已初始化（避免 AttributeError）
        if not hasattr(app.state, 'store'):
            return False, None, "下载器缓存未初始化"
        
        # 步骤2: 从缓存获取下载器
        cached_downloaders = app.state.store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
            None
        )
        
        # 步骤3: 检查下载器是否在缓存中
        if not downloader_vo:
            return False, None, f"下载器不在缓存中 [downloader_id={downloader.downloader_id}]"
        
        # 步骤4: 检查下载器是否有效（fail_time=0 表示有效）
        if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
            return False, None, f"下载器已失效 [downloader_id={downloader.downloader_id}, nickname={downloader_vo.nickname}]"
        
        # 步骤5: 获取并验证客户端连接
        client = downloader_vo.client
        if not client:
            return False, None, f"下载器客户端连接不存在 [downloader_id={downloader.downloader_id}]"
        
        try:
            # 调用 qBittorrent API 获取文件列表
            torrent_files = client.torrents.files(torrent_hashes=[torrent_hash])
            
            if not torrent_files or not torrent_files[0]:
                return False, None, f"种子 {torrent_hash} 没有文件信息"
            
            # 提取相对路径列表
            file_list = [f.name for f in torrent_files[0]]
            
            logger.info(
                f"qBittorrent种子 {torrent_hash} 文件列表获取成功，"
                f"共 {len(file_list)} 个文件"
            )
            return True, file_list, None
            
        except Exception as e:
            error_msg = f"qBittorrent获取文件列表失败: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg


    async def _move_torrent_files_for_recycle(
        self,
        file_op_service: FileOperationService,
        save_path: str,
        torrent_name: str
    ) -> Dict[str, Any]:
        """
        移动种子文件到回收站（根据类型自动处理）

        - 单文件：直接重命名 (movie.mkv -> movie.pending_delete.mkv)
        - 多文件：创建新文件夹并移动所有内容

        Args:
            file_op_service: 文件操作服务
            save_path: 种子保存路径
            torrent_name: 种子名称

        Returns:
            {
                "success": bool,
                "original_path": str,
                "new_path": str,
                "is_directory": bool,
                "original_name": str,
                "new_name": str,
                "torrent_type": str,  # "single_file" 或 "multi_file"
                "error": str (可选)
            }
        """
        try:
            # 🔥 重要：路径转换流程
            # 步骤1: 标准化路径（移除末尾分隔符，避免 os.path.join() 混用路径分隔符）
            save_path = save_path.rstrip('/\\')

            # 步骤2: 将内部路径（容器内）转换为外部路径（实际文件系统）
            # 示例：/Downloads/kpan/Downloads -> //192.168.5.51/pt3/Downloads
            save_path = file_op_service.convert_to_external_path(save_path)

            logger.info(
                f"[路径转换] 内部路径已转换为外部路径: {save_path}"
            )

            # 判断种子类型
            is_single_file = file_op_service.is_single_file_torrent(torrent_name)
            torrent_type = "single_file" if is_single_file else "multi_file"

            logger.info(
                f"[文件移动] 种子类型: {torrent_type}, "
                f"种子名称: {torrent_name}, "
                f"保存路径: {save_path}"
            )

            if is_single_file:
                # ========== 单文件种子：直接重命名 ==========
                original_path = os.path.join(save_path, torrent_name)
                name_without_ext, ext = os.path.splitext(torrent_name)
                new_name = f"{name_without_ext}.pending_delete{ext}"
                new_path = os.path.join(save_path, new_name)

                logger.info(f"[单文件重命名] {torrent_name} -> {new_name}")

                # 检查原文件是否存在
                if not os.path.exists(original_path):
                    return {
                        "success": False,
                        "error": f"单文件不存在: {original_path}",
                        "torrent_type": torrent_type
                    }

                # 检查目标是否已存在
                if os.path.exists(new_path):
                    return {
                        "success": False,
                        "error": f"目标文件已存在: {new_path}",
                        "torrent_type": torrent_type
                    }

                # 执行重命名
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, os.rename, original_path, new_path)

                logger.info(f"[单文件重命名成功] {torrent_name} -> {new_name}")

                return {
                    "success": True,
                    "original_path": original_path,
                    "new_path": new_path,
                    "is_directory": False,
                    "original_name": torrent_name,
                    "new_name": new_name,
                    "torrent_type": torrent_type
                }

            else:
                # ========== 多文件种子：创建新文件夹并移动所有内容 ==========
                original_folder = os.path.join(save_path, torrent_name)
                new_folder_name = f"{torrent_name}.pending_delete"
                new_folder = os.path.join(save_path, new_folder_name)

                logger.info(f"[多文件移动] {torrent_name}/ -> {new_folder_name}/")

                # 检查原文件夹是否存在
                if not os.path.exists(original_folder):
                    return {
                        "success": False,
                        "error": f"原文件夹不存在: {original_folder}",
                        "torrent_type": torrent_type
                    }

                # 检查目标文件夹是否已存在
                if os.path.exists(new_folder):
                    return {
                        "success": False,
                        "error": f"目标文件夹已存在: {new_folder}",
                        "torrent_type": torrent_type
                    }

                # 创建新文件夹
                os.makedirs(new_folder, exist_ok=True)
                logger.info(f"[创建新文件夹] {new_folder}")

                # 移动所有内容（保留子文件夹结构）
                moved_count = 0
                failed_files = []

                for item in os.listdir(original_folder):
                    src_path = os.path.join(original_folder, item)
                    dst_path = os.path.join(new_folder, item)

                    try:
                        # 使用 shutil.move 来移动文件和文件夹
                        import shutil
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, shutil.move, src_path, dst_path)
                        moved_count += 1
                        logger.debug(f"[移动文件] {item} 成功")
                    except Exception as e:
                        failed_files.append(f"{item}: {str(e)}")
                        logger.error(f"[移动文件失败] {item}: {str(e)}")

                # 检查是否有失败的文件
                if failed_files:
                    return {
                        "success": False,
                        "error": f"部分文件移动失败: {'; '.join(failed_files[:5])}",
                        "torrent_type": torrent_type,
                        "moved_count": moved_count,
                        "failed_count": len(failed_files)
                    }

                logger.info(
                    f"[多文件移动成功] {torrent_name}/ -> {new_folder_name}/, "
                    f"共移动 {moved_count} 个项目"
                )

                return {
                    "success": True,
                    "original_path": original_folder,
                    "new_path": new_folder,
                    "is_directory": True,
                    "original_name": torrent_name,
                    "new_name": new_folder_name,
                    "torrent_type": torrent_type,
                    "moved_count": moved_count
                }

        except Exception as e:
            logger.error(f"[文件移动失败] {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "torrent_type": torrent_type if 'torrent_type' in locals() else "unknown"
            }

    async def _rollback_file_move(
        self,
        move_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        回滚文件移动操作

        Args:
            move_result: move_torrent_files_for_recycle 的返回值

        Returns:
            {"success": bool, "error": str (可选)}
        """
        try:
            if not move_result.get("success"):
                return {"success": True}  # 没有成功移动，不需要回滚

            is_directory = move_result.get("is_directory", False)
            original_path = move_result.get("original_path")
            new_path = move_result.get("new_path")

            if is_directory:
                # ========== 多文件：移回所有内容 ==========
                logger.info(f"[回滚多文件移动] {new_path} -> {original_path}")

                # 移回所有内容
                moved_count = 0
                for item in os.listdir(new_path):
                    src_path = os.path.join(new_path, item)
                    dst_path = os.path.join(original_path, item)

                    try:
                        import shutil
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, shutil.move, src_path, dst_path)
                        moved_count += 1
                    except Exception as e:
                        logger.error(f"[回滚移动失败] {item}: {str(e)}")

                # 删除新文件夹
                try:
                    os.rmdir(new_path)
                except Exception as e:
                    logger.warning(f"[删除空文件夹失败] {new_path}: {str(e)}")

                logger.info(f"[回滚多文件成功] 移回 {moved_count} 个项目")

            else:
                # ========== 单文件：重命名回原名 ==========
                logger.info(f"[回滚单文件重命名] {new_path} -> {original_path}")

                import shutil
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, shutil.move, new_path, original_path)

                logger.info(f"[回滚单文件成功]")

            return {"success": True}

        except Exception as e:
            logger.error(f"[回滚文件移动失败] {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
