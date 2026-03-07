# -*- coding: utf-8 -*-
"""
种子位置修改核心服务

实现修改种子保存路径的核心业务逻辑，包括：
- 参数验证
- 下载器适配器获取
- 调用SDK修改路径
- 记录审计日志

@author: btpManager Team
@file: torrent_location_service.py
@time: 2026-03-04
"""

import logging
import re
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import AsyncSessionLocal
from app.downloader.models import BtDownloaders
from app.models.seed_transfer_audit_log import SeedTransferAuditLog
from app.services.downloader_adapters.qbittorrent_location import QBittorrentLocationAdapter
from app.services.downloader_adapters.transmission_location import TransmissionLocationAdapter

logger = logging.getLogger(__name__)


class TorrentLocationService:
    """
    种子位置修改核心服务

    职责：
    - 参数验证
    - 获取下载器适配器
    - 调用SDK修改路径
    - 记录审计日志
    """

    def __init__(self, db: Session, async_db: Optional[AsyncSessionLocal] = None):
        """
        初始化种子位置修改服务

        Args:
            db: 同步数据库会话（用于查询下载器信息等）
            async_db: 异步数据库会话（可选，用于审计日志等）
        """
        self.db = db
        self.async_db = async_db

    async def set_location(
        self,
        downloader_id: str,
        hashes: list,
        target_path: str,
        move_files: bool,
        user_id: int,
        username: str,
        app_state: Any = None
    ) -> Dict[str, Any]:
        """
        修改种子保存路径

        Args:
            downloader_id: 下载器ID
            hashes: 种子hash列表
            target_path: 目标路径
            move_files: 是否移动文件
            user_id: 操作用户ID
            username: 操作用户名
            app_state: FastAPI的app.state（用于访问下载器缓存）

        Returns:
            操作结果字典:
            {
                "success": bool,
                "moved_count": int,
                "failed_count": int,
                "error_message": Optional[str]
            }
        """
        result = {
            "success": False,
            "moved_count": 0,
            "failed_count": len(hashes),
            "error_message": None
        }

        downloader = None
        try:
            # 1. 参数验证
            validation_error = self._validate_request(
                downloader_id, hashes, target_path
            )
            if validation_error:
                result["error_message"] = validation_error
                return result

            # 2. 获取下载器信息
            downloader = await self._get_downloader(downloader_id)
            if not downloader:
                result["error_message"] = f"下载器不存在: {downloader_id}"
                return result

            # 3. 获取适配器
            adapter = self._get_adapter(downloader, app_state)
            if not adapter:
                result["error_message"] = f"无法创建下载器适配器，类型: {downloader.downloader_type}"
                return result

            # 4. 调用适配器修改路径
            adapter_result = await adapter.set_location(hashes, target_path, move_files)

            # 5. 更新结果
            result.update(adapter_result)

            # 6. 记录审计日志
            await self._log_audit(
                user_id=user_id,
                username=username,
                downloader_id=downloader_id,
                downloader_name=downloader.nickname,
                torrent_count=len(hashes),
                target_path=target_path,
                move_files=move_files,
                success=result["success"],
                moved_count=result["moved_count"],
                error_message=result["error_message"]
            )

        except Exception as e:
            result["error_message"] = f"服务器错误: {str(e)}"
            logger.error(f"修改种子路径异常: {e}", exc_info=True)

            # 记录失败日志
            await self._log_audit(
                user_id=user_id,
                username=username,
                downloader_id=downloader_id,
                downloader_name=downloader.nickname if downloader else "",
                torrent_count=len(hashes),
                target_path=target_path,
                move_files=move_files,
                success=False,
                moved_count=0,
                error_message=str(e)
            )

        return result

    def _validate_request(
        self,
        downloader_id: str,
        hashes: list,
        target_path: str
    ) -> Optional[str]:
        """
        验证请求参数

        Args:
            downloader_id: 下载器ID
            hashes: 种子hash列表
            target_path: 目标路径

        Returns:
            验证错误信息，None表示验证通过
        """
        if not downloader_id:
            return "下载器ID不能为空"

        if not hashes or len(hashes) == 0:
            return "种子hash列表不能为空"

        if len(hashes) > 100:
            return "单次最多支持100个种子"

        if not target_path or len(target_path.strip()) == 0:
            return "目标路径不能为空"

        # 验证路径格式（简单检查）
        is_windows_abs = re.match(r"^[A-Za-z]:[\\/]", target_path) is not None
        if not (target_path.startswith(('/', '\\', '.', '~')) or is_windows_abs):
            return "目标路径必须是绝对路径"

        return None

    async def _get_downloader(self, downloader_id: str) -> Optional[BtDownloaders]:
        """
        获取下载器信息

        Args:
            downloader_id: 下载器ID

        Returns:
            下载器对象，不存在返回None
        """
        try:
            result = self.db.execute(
                select(BtDownloaders).where(
                    BtDownloaders.downloader_id == downloader_id,
                    BtDownloaders.dr == 0
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"查询下载器失败: {e}")
            return None

    def _get_adapter(
        self,
        downloader: BtDownloaders,
        app_state: Any = None
    ):
        """
        获取下载器适配器

        Args:
            downloader: 下载器对象
            app_state: FastAPI的app.state（用于访问下载器缓存）

        Returns:
            适配器对象，失败返回None
        """
        try:
            # 从缓存获取下载器客户端
            if not app_state or not hasattr(app_state, 'store'):
                logger.error("app_state或app.state.store未初始化")
                return None

            cached_downloaders = app_state.store.get_snapshot_sync()
            downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
                None
            )

            if not downloader_vo or downloader_vo.fail_time > 0:
                logger.error(f"下载器不可用: {downloader.nickname}")
                return None

            client = downloader_vo.client

            # 根据下载器类型创建适配器
            if downloader.downloader_type == 0:  # qBittorrent
                return QBittorrentLocationAdapter(client=client)
            elif downloader.downloader_type == 1:  # Transmission
                return TransmissionLocationAdapter(client=client)
            else:
                logger.error(f"不支持的下载器类型: {downloader.downloader_type}")
                return None

        except Exception as e:
            logger.error(f"创建适配器失败: {e}")
            return None

    async def _log_audit(
        self,
        user_id: int,
        username: str,
        downloader_id: str,
        downloader_name: str,
        torrent_count: int,
        target_path: str,
        move_files: bool,
        success: bool,
        moved_count: int,
        error_message: Optional[str] = None
    ):
        """
        记录审计日志

        Args:
            user_id: 用户ID
            username: 用户名
            downloader_id: 下载器ID
            downloader_name: 下载器名称
            torrent_count: 种子数量
            target_path: 目标路径
            move_files: 是否移动文件
            success: 是否成功
            moved_count: 成功修改的数量
            error_message: 错误信息
        """
        try:
            audit_log = SeedTransferAuditLog(
                user_id=user_id,
                username=username,
                operation_type='set_location',  # 新增操作类型
                source_downloader_id=downloader_id,
                source_downloader_name=downloader_name,
                target_downloader_id=downloader_id,  # 同一下载器
                target_downloader_name=downloader_name,
                torrent_count=torrent_count,
                target_path=target_path,
                move_files=move_files,
                transfer_status='success' if success else 'failed',
                error_message=error_message,
                created_at=datetime.utcnow()
            )

            if self.async_db is not None:
                self.async_db.add(audit_log)
                await self.async_db.commit()
            else:
                async with AsyncSessionLocal() as session:
                    session.add(audit_log)
                    await session.commit()

            logger.info(f"审计日志已记录: {username} 修改了 {torrent_count} 个种子路径")

        except Exception as e:
            logger.error(f"记录审计日志失败: {e}")
