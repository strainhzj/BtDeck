"""
种子删除服务 - 多下载器统一删除接口
提供安全的种子删除功能，支持多种下载器类型
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Tuple
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.torrents.models import TorrentInfo
from app.downloader.models import BtDownloaders
from app.core.security import decrypt_tracker_info
import logging

logger = logging.getLogger(__name__)


class DeleteOption(Enum):
    """删除选项枚举"""
    DELETE_ONLY_TORRENT = "delete_only_torrent"  # 仅删除种子任务
    DELETE_FILES_AND_TORRENT = "delete_files_and_torrent"  # 删除文件和种子任务
    DRY_RUN = "dry_run"  # 预演模式，不实际删除


class SafetyCheckLevel(Enum):
    """安全检查级别"""
    BASIC = "basic"  # 基础安全检查
    ENHANCED = "enhanced"  # 增强安全检查
    STRICT = "strict"  # 严格安全检查


@dataclass
class DeleteRequest:
    """删除请求数据结构"""
    torrent_info_ids: List[str]  # 要删除的种子信息ID列表
    delete_option: DeleteOption  # 删除选项
    safety_check_level: SafetyCheckLevel = SafetyCheckLevel.ENHANCED
    force_delete: bool = False  # 是否强制删除（跳过安全确认）
    reason: Optional[str] = None  # 删除原因


@dataclass
class DeleteResult:
    """删除结果数据结构"""
    success_count: int  # 成功删除数量
    failed_count: int  # 删除失败数量
    skipped_count: int  # 跳过删除数量
    total_size_freed: int  # 释放的存储空间（字节）
    deleted_torrents: List[Dict[str, Any]]  # 已删除的种子详情
    failed_torrents: List[Dict[str, Any]]  # 删除失败的种子详情
    skipped_torrents: List[Dict[str, Any]]  # 跳过的种子详情
    safety_warnings: List[str]  # 安全警告信息
    execution_time: float  # 执行时间（秒）


class DownloaderDeleteAdapter(ABC):
    """下载器删除适配器抽象基类"""

    @abstractmethod
    async def delete_torrents(
        self,
        torrent_hashes: List[str],
        delete_option: DeleteOption,
        safety_check_level: SafetyCheckLevel = SafetyCheckLevel.ENHANCED
    ) -> Dict[str, Any]:
        """
        删除种子

        Args:
            torrent_hashes: 种子哈希值列表
            delete_option: 删除选项
            safety_check_level: 安全检查级别

        Returns:
            删除结果字典
        """
        pass

    @abstractmethod
    async def validate_torrents_exist(self, torrent_hashes: List[str]) -> Dict[str, bool]:
        """
        验证种子是否存在

        Args:
            torrent_hashes: 种子哈希值列表

        Returns:
            种子存在性映射 {hash: exists}
        """
        pass

    @abstractmethod
    async def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """
        获取种子信息

        Args:
            torrent_hash: 种子哈希值

        Returns:
            种子信息字典，如果不存在返回None
        """
        pass

    @abstractmethod
    def get_downloader_type(self) -> str:
        """获取下载器类型"""
        pass

    @abstractmethod
    async def add_tag_to_torrent(
        self,
        torrent_hash: str,
        tag: str
    ) -> Tuple[bool, Optional[str]]:
        """
        为种子添加标签（等级4删除使用）

        Args:
            torrent_hash: 种子哈希值
            tag: 要添加的标签

        Returns:
            (成功标志, 错误信息)
        """
        pass

    @abstractmethod
    async def create_marker_file(
        self,
        torrent_hash: str,
        torrent_name: str,
        download_path: str
    ) -> Tuple[bool, Optional[str]]:
        """
        创建标记文件（等级3删除使用）

        Args:
            torrent_hash: 种子哈希值
            torrent_name: 种子名称
            download_path: 下载路径

        Returns:
            (成功标志, 错误信息)
        """
        pass

    @abstractmethod
    async def get_torrent_files(
        self,
        torrent_hash: str
    ) -> Tuple[bool, Optional[List[str]], Optional[str]]:
        """
        获取种子文件列表（用于验证和记录）

        Args:
            torrent_hash: 种子哈希值

        Returns:
            (成功标志, 文件列表, 错误信息)
        """
        pass


class SafetyCheckService:
    """安全检查服务"""

    @staticmethod
    async def check_torrent_safety(
        torrent_info: TorrentInfo,
        check_level: SafetyCheckLevel,
        db: Session
    ) -> List[str]:
        """
        检查种子删除的安全性

        Args:
            torrent_info: 种子信息
            check_level: 检查级别
            db: 数据库会话

        Returns:
            安全警告列表
        """
        warnings = []

        # 基础安全检查
        if torrent_info.status in ["seeding", "checking"]:
            warnings.append(f"种子状态为'{torrent_info.status}'，建议在状态稳定后再删除")

        if torrent_info.ratio and float(torrent_info.ratio) < 1.0:
            warnings.append(f"分享比率{torrent_info.ratio} < 1.0，可能影响分享生态")

        # 增强安全检查
        if check_level in [SafetyCheckLevel.ENHANCED, SafetyCheckLevel.STRICT]:
            # 检查是否正在下载
            if torrent_info.status == "downloading":
                warnings.append("种子正在下载中，删除可能导致文件不完整")

            # 检查文件大小
            if torrent_info.size and torrent_info.size > 50 * 1024 * 1024 * 1024:  # 50GB
                warnings.append(f"种子文件较大({torrent_info.size/1024/1024/1024:.1f}GB)，请确认需要删除")

        # 严格安全检查
        if check_level == SafetyCheckLevel.STRICT:
            # 检查是否为重要种子
            if torrent_info.category in ["important", "system", "backup"]:
                warnings.append(f"种子分类为'{torrent_info.category}'，属于重要类别")

            # 检查标签
            if torrent_info.tags and "keep" in torrent_info.tags.lower():
                warnings.append("种子包含'keep'标签，建议保留")

            # 检查最近完成的任务（7天内）
            from datetime import datetime, timedelta
            if torrent_info.completed_date:
                if (datetime.now() - torrent_info.completed_date).days < 7:
                    warnings.append("种子在7天内完成，可能仍需要验证")

        return warnings


class TorrentDeletionService:
    """种子删除服务主类"""

    def __init__(
        self,
        db: Session,
        audit_service=None,
        async_db_session=None
    ):
        """
        初始化种子删除服务

        Args:
            db: 同步数据库会话
            audit_service: 可选的审计日志服务（异步版本）
            async_db_session: 异步数据库会话（用于审计日志）
        """
        self.db = db
        self.audit_service = audit_service
        self.async_db_session = async_db_session
        self.safety_checker = SafetyCheckService()
        self.adapters: Dict[str, DownloaderDeleteAdapter] = {}

    def register_adapter(self, downloader_type: str, adapter: DownloaderDeleteAdapter):
        """注册下载器适配器"""
        self.adapters[downloader_type] = adapter
        logger.info(f"已注册{downloader_type}下载器删除适配器")

    async def delete_torrents(self, request: DeleteRequest) -> DeleteResult:
        """
        执行种子删除操作

        Args:
            request: 删除请求

        Returns:
            删除结果
        """
        import time
        start_time = time.time()

        result = DeleteResult(
            success_count=0,
            failed_count=0,
            skipped_count=0,
            total_size_freed=0,
            deleted_torrents=[],
            failed_torrents=[],
            skipped_torrents=[],
            safety_warnings=[],
            execution_time=0
        )

        if not request.torrent_info_ids:
            result.safety_warnings.append("没有指定要删除的种子")
            result.execution_time = time.time() - start_time
            return result

        # 查询种子信息
        torrent_infos = self.db.query(TorrentInfo).filter(
            TorrentInfo.info_id.in_(request.torrent_info_ids),
            TorrentInfo.dr == 0  # 未删除的种子
        ).all()

        # 按下载器分组
        downloader_groups = self._group_by_downloader(torrent_infos)

        # 处理每个下载器的种子
        for downloader_id, torrents in downloader_groups.items():
            await self._process_downloader_torrents(
                downloader_id, torrents, request, result
            )

        result.execution_time = time.time() - start_time

        # 记录删除操作日志
        await self._log_deletion_operation(request, result)

        return result

    def _group_by_downloader(self, torrent_infos: List[TorrentInfo]) -> Dict[str, List[TorrentInfo]]:
        """按下载器分组种子"""
        groups = {}
        for torrent in torrent_infos:
            if torrent.downloader_id not in groups:
                groups[torrent.downloader_id] = []
            groups[torrent.downloader_id].append(torrent)
        return groups

    async def _process_downloader_torrents(
        self,
        downloader_id: str,
        torrents: List[TorrentInfo],
        request: DeleteRequest,
        result: DeleteResult
    ):
        """处理单个下载器的种子删除"""
        try:
            # 获取下载器信息
            downloader = self.db.query(BtDownloaders).filter(
                BtDownloaders.downloader_id == downloader_id,
                BtDownloaders.dr == 0
            ).first()

            if not downloader:
                # 跳过无效下载器的种子
                for torrent in torrents:
                    result.skipped_count += 1
                    result.skipped_torrents.append({
                        "info_id": torrent.info_id,
                        "name": torrent.name,
                        "reason": f"下载器{downloader_id}不存在"
                    })
                return

            # 获取对应的适配器
            adapter = self.adapters.get(downloader.downloader_type)
            if not adapter:
                # 跳过不支持的下载器类型
                for torrent in torrents:
                    result.skipped_count += 1
                    result.skipped_torrents.append({
                        "info_id": torrent.info_id,
                        "name": torrent.name,
                        "reason": f"不支持的下载器类型{downloader.downloader_type}"
                    })
                return

            # 执行安全检查
            for torrent in torrents:
                warnings = await self.safety_checker.check_torrent_safety(
                    torrent, request.safety_check_level, self.db
                )

                if warnings and not request.force_delete:
                    # 跳过有安全警告的种子
                    result.skipped_count += 1
                    result.skipped_torrents.append({
                        "info_id": torrent.info_id,
                        "name": torrent.name,
                        "reason": "安全检查未通过",
                        "warnings": warnings
                    })
                    result.safety_warnings.extend(warnings)
                    continue

                result.safety_warnings.extend(warnings)

            # 获取可以安全删除的种子
            safe_torrents = [
                t for t in torrents
                if t.info_id not in [s["info_id"] for s in result.skipped_torrents]
            ]

            if not safe_torrents:
                return

            # 执行删除操作
            await self._execute_deletion(adapter, downloader, safe_torrents, request, result)

        except Exception as e:
            logger.error(f"处理下载器{downloader_id}的种子删除时发生错误: {str(e)}")
            for torrent in torrents:
                result.failed_count += 1
                result.failed_torrents.append({
                    "info_id": torrent.info_id,
                    "name": torrent.name,
                    "reason": f"处理错误: {str(e)}"
                })

    async def _execute_deletion(
        self,
        adapter: DownloaderDeleteAdapter,
        downloader: BtDownloaders,
        torrents: List[TorrentInfo],
        request: DeleteRequest,
        result: DeleteResult
    ):
        """执行实际的删除操作"""
        try:
            if request.delete_option == DeleteOption.DRY_RUN:
                # 预演模式，只模拟不实际删除
                for torrent in torrents:
                    result.success_count += 1
                    result.deleted_torrents.append({
                        "info_id": torrent.info_id,
                        "name": torrent.name,
                        "size": torrent.size,
                        "downloader_name": downloader.nickname,
                        "mode": "dry_run"
                    })
                    if torrent.size:
                        result.total_size_freed += torrent.size
                return

            # 实际删除模式
            torrent_hashes = [t.hash for t in torrents if t.hash]

            # 验证种子存在性
            existence_map = await adapter.validate_torrents_exist(torrent_hashes)
            valid_hashes = [h for h, exists in existence_map.items() if exists]

            if not valid_hashes:
                # 没有种子在下载器中存在 - 执行逻辑删除
                logger.warning(
                    f"下载器 [{downloader.nickname}] 中不存在以下种子，将执行逻辑删除: "
                    f"{[t.name for t in torrents]}"
                )
                for torrent in torrents:
                    result.success_count += 1
                    result.deleted_torrents.append({
                        "info_id": torrent.info_id,
                        "name": torrent.name,
                        "size": torrent.size,
                        "downloader_name": downloader.nickname,
                        "mode": f"{request.delete_option.value}_logical_only"
                    })
                    if torrent.size:
                        result.total_size_freed += torrent.size

                    # 标记数据库中的种子为已删除（逻辑删除）
                    torrent.dr = 1
                    self.db.commit()
                return

            # 调用适配器删除种子
            delete_result = await adapter.delete_torrents(
                valid_hashes, request.delete_option, request.safety_check_level
            )

            # 处理删除结果
            for torrent in torrents:
                if torrent.hash in delete_result.get("success_hashes", []):
                    result.success_count += 1
                    result.deleted_torrents.append({
                        "info_id": torrent.info_id,
                        "name": torrent.name,
                        "size": torrent.size,
                        "downloader_name": downloader.nickname,
                        "mode": request.delete_option.value
                    })
                    if torrent.size:
                        result.total_size_freed += torrent.size

                    # 标记数据库中的种子为已删除
                    torrent.dr = 1
                    self.db.commit()
                else:
                    result.failed_count += 1
                    result.failed_torrents.append({
                        "info_id": torrent.info_id,
                        "name": torrent.name,
                        "reason": delete_result.get("errors", {}).get(torrent.hash, "删除失败")
                    })

        except Exception as e:
            logger.error(f"执行种子删除时发生错误: {str(e)}")
            for torrent in torrents:
                result.failed_count += 1
                result.failed_torrents.append({
                    "info_id": torrent.info_id,
                    "name": torrent.name,
                    "reason": f"删除错误: {str(e)}"
                })

    async def _log_deletion_operation(
        self,
        request: DeleteRequest,
        result: DeleteResult
    ):
        """记录删除操作日志到数据库"""
        # 如果没有审计服务，使用旧方式（仅打印日志）
        if not self.audit_service:
            try:
                log_entry = {
                    "operation_type": "torrent_deletion",
                    "delete_option": request.delete_option.value,
                    "safety_check_level": request.safety_check_level.value,
                    "force_delete": request.force_delete,
                    "reason": request.reason,
                    "results": {
                        "success_count": result.success_count,
                        "failed_count": result.failed_count,
                        "skipped_count": result.skipped_count,
                        "total_size_freed": result.total_size_freed,
                        "execution_time": result.execution_time,
                        "warning_count": len(result.safety_warnings)
                    },
                    "timestamp": datetime.now().isoformat()
                }

                logger.info(f"种子删除操作完成: {log_entry}")
            except Exception as e:
                logger.error(f"记录删除操作日志失败: {str(e)}")
            return

        # 使用审计日志服务记录到数据库
        try:
            from app.services.audit_service import AuditOperationType, AuditOperationResult
            from app.database import AsyncSessionLocal

            # 确定操作类型映射
            delete_option_to_operation_type = {
                "delete_only_torrent": AuditOperationType.DELETE_L2,  # 🔧 修复：等级2删除应记录为DELETE_L2
                "delete_files_and_torrent": AuditOperationType.DELETE_L1,
                "dry_run": AuditOperationType.DELETE_L4
            }

            operation_type = delete_option_to_operation_type.get(
                request.delete_option.value,
                AuditOperationType.DELETE_L4
            )

            # 记录批量删除操作（为每个成功/失败的种子记录一条日志）
            operations_to_log = []

            # 成功删除的种子
            for deleted in result.deleted_torrents:
                operations_to_log.append({
                    "operation_type": operation_type,
                    "torrent_info_id": deleted.get("info_id"),
                    "operation_detail": {
                        "torrent_name": deleted.get("name"),
                        "torrent_size": deleted.get("size"),
                        "downloader_name": deleted.get("downloader_name"),
                        "delete_mode": request.delete_option.value,
                        "safety_check_level": request.safety_check_level.value,
                        "reason": request.reason
                    },
                    "operator": "admin",  # TODO: 从请求上下文获取真实操作者
                    "operation_result": AuditOperationResult.SUCCESS,
                    "downloader_id": deleted.get("downloader_id"),  # TODO: 从deleted中获取downloader_id
                    "ip_address": None,  # TODO: 从请求上下文获取
                    "user_agent": None
                })

            # 失败删除的种子
            for failed_item in result.failed_torrents:
                operations_to_log.append({
                    "operation_type": operation_type,
                    "torrent_info_id": failed_item.get("info_id"),
                    "operation_detail": {
                        "torrent_name": failed_item.get("name"),
                        "error_reason": failed_item.get("reason"),
                        "delete_mode": request.delete_option.value,
                        "safety_check_level": request.safety_check_level.value
                    },
                    "operator": "admin",
                    "operation_result": AuditOperationResult.FAILED,
                    "error_message": failed_item.get("reason"),
                    "downloader_id": None
                })

            # 跳过的种子
            for skipped_item in result.skipped_torrents:
                skip_reason = skipped_item.get("reason", "unknown")
                operations_to_log.append({
                    "operation_type": operation_type,
                    "torrent_info_id": skipped_item.get("info_id"),
                    "operation_detail": {
                        "torrent_name": skipped_item.get("name"),
                        "skip_reason": skip_reason,
                        "warnings": skipped_item.get("warnings", [])
                    },
                    "operator": "admin",
                    "operation_result": AuditOperationResult.FAILED,
                    "error_message": f"跳过删除: {skip_reason}"
                })

            # 使用异步数据库会话批量记录
            if self.async_db_session and operations_to_log:
                logged_count = await self.audit_service.log_batch_operations(
                    operations=operations_to_log,
                    operator="admin"  # TODO: 从请求上下文获取
                )
                logger.info(f"成功记录{logged_count}条删除审计日志到数据库")

        except Exception as e:
            logger.error(f"使用审计日志服务记录失败: {str(e)}")
            # 降级为简单日志记录
            logger.info(f"种子删除操作完成: 成功{result.success_count}, 失败{result.failed_count}, 跳过{result.skipped_count}")


# 适配器工厂
class DownloaderAdapterFactory:
    """下载器适配器工厂"""

    @staticmethod
    def create_adapter(downloader_type: str, client) -> DownloaderDeleteAdapter:
        """
        创建下载器适配器（强制使用缓存连接）

        Args:
            downloader_type: 下载器类型
            client: 已初始化的客户端对象（必须从缓存获取）

        Returns:
            下载器适配器实例

        Raises:
            ValueError: 如果client为None
        """
        if client is None:
            raise ValueError(f"创建{downloader_type}适配器失败：必须传入缓存的客户端连接，下载器可能离线")

        # 延迟导入避免循环依赖
        from app.services.downloader_adapters.qbittorrent import QBittorrentDeleteAdapter
        from app.services.downloader_adapters.transmission import TransmissionDeleteAdapter

        adapters = {
            "qbittorrent": QBittorrentDeleteAdapter,
            "transmission": TransmissionDeleteAdapter,
            # 未来可以扩展更多下载器类型
        }

        adapter_class = adapters.get(downloader_type.lower())
        if not adapter_class:
            raise ValueError(f"不支持的下载器类型: {downloader_type}")

        # 强制使用传入的client对象（从缓存获取）
        return adapter_class(client=client)


# 延迟导入避免循环依赖
from datetime import datetime