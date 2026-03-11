# -*- coding: utf-8 -*-
"""
种子转移核心服务

实现种子转移的核心业务逻辑，包括：
- 从备份读取种子文件
- 添加种子到目标下载器
- 验证转移成功（轮询机制）
- 删除原种子（带确认）
- 记录审计日志

@author: btpManager Team
@file: seed_transfer_service.py
@time: 2026-02-15
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import AsyncSessionLocal
from app.models.torrent_file_backup import TorrentFileBackup
from app.models.seed_transfer_audit_log import SeedTransferAuditLog
from app.models.setting_templates import DownloaderTypeEnum
from app.torrents.models import TorrentInfo
from app.downloader.models import BtDownloaders
from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService
from app.core.torrent_status_mapper import TorrentStatusMapper
from qbittorrentapi import Client as QBittorrentClient


logger = logging.getLogger(__name__)


class SeedTransferService:
    """
    种子转移核心服务

    职责：
    - 从备份读取种子文件
    - 添加种子到目标下载器
    - 验证转移成功（轮询机制）
    - 删除原种子（带确认）
    - 记录审计日志
    """

    def __init__(
        self,
        db: Session,
        async_db: Optional[AsyncSessionLocal] = None
    ):
        """
        初始化种子转移服务

        Args:
            db: 同步数据库会话（用于查询下载器信息等）
            async_db: 异步数据库会话（可选，用于审计日志等）
        """
        self.db = db
        self.async_db = async_db or AsyncSessionLocal()

        # 初始化种子文件备份管理服务
        self.backup_manager = TorrentFileBackupManagerService(
            path_mapping_service=None
        )

    async def transfer_seed(
        self,
        source_downloader_id: int,
        target_downloader_id: int,
        info_hash: str,
        target_path: str,
        delete_source: bool,
        user_id: int,
        username: str,
        app_state: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        转移种子

        Args:
            source_downloader_id: 源下载器ID
            target_downloader_id: 目标下载器ID
            info_hash: 种子的info_hash
            target_path: 目标路径
            delete_source: 是否删除原种子
            user_id: 操作用户ID
            username: 操作用户名
            app_state: FastAPI的app.state（用于访问下载器缓存）

        Returns:
            转移结果字典
            {
                "success": bool,
                "transfer_id": Optional[int],
                "transfer_status": str,  # "success" | "failed" | "partial"
                "torrent_name": Optional[str],
                "target_downloader_name": Optional[str],
                "source_downloader_name": Optional[str],
                "delete_source": bool,
                "require_confirmation": bool,  # 是否需要用户确认删除
                "transfer_duration": Optional[int],  # 毫秒
                "error_message": Optional[str],
                "source_path": Optional[str],
                "target_path": str
            }
        """
        start_time = time.time()
        result = {
            "success": False,
            "transfer_id": None,
            "transfer_status": "failed",
            "torrent_name": None,
            "target_downloader_name": None,
            "source_downloader_name": None,
            "delete_source": delete_source,
            "require_confirmation": False,
            "transfer_duration": None,
            "error_message": None,
            "source_path": None,
            "target_path": target_path
        }

        # 获取源和目标下载器信息
        source_downloader_result = await self.db.execute(
            select(BtDownloaders).where(BtDownloaders.downloader_id == source_downloader_id)
        )
        source_downloader = source_downloader_result.scalar_one_or_none()

        target_downloader_result = await self.db.execute(
            select(BtDownloaders).where(BtDownloaders.downloader_id == target_downloader_id)
        )
        target_downloader = target_downloader_result.scalar_one_or_none()

        if not source_downloader:
            result["error_message"] = f"源下载器不存在: {source_downloader_id}"
            await self._log_transfer_attempt(
                user_id=user_id,
                username=username,
                source_downloader_id=source_downloader_id,
                source_downloader_name="",
                target_downloader_id=target_downloader_id,
                target_downloader_name=target_downloader.nickname if target_downloader else "",
                torrent_name="",
                info_hash=info_hash,
                source_path="",
                target_path=target_path,
                delete_source=delete_source,
                transfer_status="failed",
                error_message=result["error_message"],
                transfer_duration=int((time.time() - start_time) * 1000)
            )
            return result

        if not target_downloader:
            result["error_message"] = f"目标下载器不存在: {target_downloader_id}"
            await self._log_transfer_attempt(
                user_id=user_id,
                username=username,
                source_downloader_id=source_downloader_id,
                source_downloader_name=source_downloader.nickname,
                target_downloader_id=target_downloader_id,
                target_downloader_name="",
                torrent_name="",
                info_hash=info_hash,
                source_path="",
                target_path=target_path,
                delete_source=delete_source,
                transfer_status="failed",
                error_message=result["error_message"],
                transfer_duration=int((time.time() - start_time) * 1000)
            )
            return result

        result["source_downloader_name"] = source_downloader.nickname
        result["target_downloader_name"] = target_downloader.nickname

        # 记录审计日志（操作开始）
        await self._log_transfer_attempt(
            user_id=user_id,
            username=username,
            source_downloader_id=source_downloader_id,
            source_downloader_name=source_downloader.nickname,
            target_downloader_id=target_downloader_id,
            target_downloader_name=target_downloader.nickname,
            torrent_name="",
            info_hash=info_hash,
            source_path="",
            target_path=target_path,
            delete_source=delete_source,
            transfer_status="pending",
            error_message=None,
            transfer_duration=0
        )

        try:
            # 1. 从备份获取种子文件
            logger.info(f"开始转移种子 {info_hash}，从下载器 {source_downloader_id} 到 {target_downloader_id}")

            backup_result = await self.backup_manager.get_backup_info(info_hash)
            torrent_backup = None
            torrent_content = None
            used_fallback = False  # 标记是否使用了降级方案
            source_torrent_path = None  # 保存源种子文件路径（用于创建备份）

            if backup_result["success"]:
                torrent_backup = backup_result["backup"]
                result["torrent_name"] = torrent_backup.task_name or "未知"

                # 读取种子文件内容
                if Path(torrent_backup.file_path).exists():
                    try:
                        with open(torrent_backup.file_path, 'rb') as f:
                            torrent_content = f.read()
                        logger.info(f"从备份目录成功读取种子文件: {torrent_backup.file_path}")
                    except Exception as e:
                        logger.warning(f"读取备份种子文件失败: {e}，尝试降级方案")
                        torrent_content = None
                else:
                    logger.warning(f"备份种子文件不存在: {torrent_backup.file_path}，尝试降级方案")
                    torrent_content = None

            # 降级方案：从下载器保存目录获取种子文件
            if torrent_content is None:
                logger.info(f"尝试降级方案：从源下载器保存目录获取种子文件 {info_hash}")

                # 检查源下载器是否配置了 torrent_save_path
                if not source_downloader.torrent_save_path or not source_downloader.torrent_save_path.strip():
                    result["error_message"] = (
                        "种子文件备份中未找到该种子，且源下载器未配置种子保存目录(torrent_save_path)，无法转移"
                    )
                    await self._update_transfer_log(info_hash, "failed", result["error_message"])
                    return result

                # 构建源下载器种子文件路径
                source_torrent_path = str(Path(source_downloader.torrent_save_path) / f"{info_hash}.torrent")

                if not Path(source_torrent_path).exists():
                    result["error_message"] = (
                        f"种子文件备份不存在，且下载器保存目录也未找到种子文件\n"
                        f"预期路径: {source_torrent_path}"
                    )
                    await self._update_transfer_log(info_hash, "failed", result["error_message"])
                    return result

                # 从源下载器保存目录读取种子文件
                try:
                    with open(source_torrent_path, 'rb') as f:
                        torrent_content = f.read()
                    used_fallback = True
                    logger.info(f"从源下载器保存目录成功读取种子文件: {source_torrent_path}")

                    # 从 TorrentInfo 获取种子名称
                    source_torrent_result = await self.db.execute(
                        select(TorrentInfo).where(
                            TorrentInfo.hash == info_hash,
                            TorrentInfo.downloader_id == source_downloader_id,
                            TorrentInfo.dr == 0
                        )
                    )
                    source_torrent = source_torrent_result.scalar_one_or_none()
                    result["torrent_name"] = source_torrent.name if source_torrent else "未知"

                except Exception as e:
                    result["error_message"] = f"从源下载器保存目录读取种子文件失败: {str(e)}"
                    await self._update_transfer_log(info_hash, "failed", result["error_message"])
                    return result

            # 获取源种子的保存路径
            source_torrent_result = await self.db.execute(
                select(TorrentInfo).where(
                    TorrentInfo.hash == info_hash,
                    TorrentInfo.downloader_id == source_downloader_id,
                    TorrentInfo.dr == 0
                )
            )
            source_torrent = source_torrent_result.scalar_one_or_none()

            if source_torrent:
                result["source_path"] = source_torrent.save_path
            else:
                result["source_path"] = "未知"

            # 2. 从缓存获取目标下载器客户端
            if not app_state or not hasattr(app_state, 'store'):
                result["error_message"] = "下载器缓存未初始化"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            cached_downloaders = await app_state.store.get_snapshot()
            target_downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == target_downloader_id),
                None
            )

            if not target_downloader_vo:
                result["error_message"] = f"目标下载器不在缓存中: {target_downloader_id}"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            if hasattr(target_downloader_vo, 'fail_time') and target_downloader_vo.fail_time > 0:
                result["error_message"] = "目标下载器当前不可用"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            target_client = target_downloader_vo.client

            # 3. 添加种子到目标下载器
            logger.info(f"添加种子到目标下载器 {target_downloader_id}，路径: {target_path}")

            normalized_type = DownloaderTypeEnum.normalize(target_downloader.downloader_type)

            if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                from qbittorrentapi import LoginFailed
                try:
                    from io import BytesIO
                    target_client.torrents_add(
                        torrent_files=BytesIO(torrent_content),
                        save_path=target_path
                    )
                except LoginFailed as e:
                    result["error_message"] = f"目标下载器登录失败: {str(e)}"
                    await self._update_transfer_log(info_hash, "failed", result["error_message"])
                    return result
                except Exception as e:
                    result["error_message"] = f"添加种子到qBittorrent失败: {str(e)}"
                    await self._update_transfer_log(info_hash, "failed", result["error_message"])
                    return result

            elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                try:
                    from io import BytesIO
                    target_client.add_torrent(BytesIO(torrent_content), download_dir=target_path)
                except Exception as e:
                    result["error_message"] = f"添加种子到Transmission失败: {str(e)}"
                    await self._update_transfer_log(info_hash, "failed", result["error_message"])
                    return result
            else:
                result["error_message"] = f"不支持的下载器类型: {target_downloader.downloader_type}"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            # 4. 验证种子添加成功（轮询状态）
            logger.info(f"验证种子 {info_hash} 在目标下载器中的状态")
            verified = await self._verify_transfer(
                target_client=target_client,
                downloader_type=target_downloader.downloader_type,
                info_hash=info_hash
            )

            if not verified:
                result["error_message"] = "种子添加成功，但验证超时，请手动检查目标下载器"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            logger.info(f"种子 {info_hash} 验证成功")

            # 5. 更新备份使用记录
            await self.backup_manager.increment_use_count(info_hash)

            # 5.1 如果使用了降级方案，创建备份记录
            if used_fallback and source_torrent_path:
                logger.info(f"使用了降级方案，创建备份记录: {info_hash}")
                try:
                    from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService
                    from app.models.torrent_file_backup import TorrentFileBackup

                    backup_manager = TorrentFileBackupManagerService(db=self.db)

                    # 检查是否已存在备份记录
                    existing_backup = await self.db.execute(
                        select(TorrentFileBackup).filter(
                            TorrentFileBackup.info_hash == info_hash,
                            TorrentFileBackup.downloader_id == source_downloader_id,
                            TorrentFileBackup.is_deleted == False
                        )
                    )
                    existing_record = existing_backup.scalar_one_or_none()

                    if not existing_record:
                        # 创建备份记录
                        import os
                        from app.core.filename_utils import FilenameUtils

                        # 生成备份文件名
                        info_id = result.get("torrent_name", info_hash)[:50]  # 使用种子名称作为info_id
                        backup_filename = FilenameUtils.generate_backup_filename(
                            info_id,
                            result["torrent_name"] or "unknown"
                        )

                        # 构建备份文件路径（复制到备份目录）
                        from app.core.config import settings
                        backup_dir = os.path.join(settings.BASE_DIR, "backup", "torrents")
                        backup_path = os.path.join(backup_dir, backup_filename)

                        # 复制文件到备份目录
                        import shutil
                        os.makedirs(backup_dir, exist_ok=True)
                        shutil.copy2(source_torrent_path, backup_path)

                        # 创建数据库记录
                        await backup_manager.repository.create(
                            info_hash=info_hash,
                            file_path=backup_path,
                            file_size=os.path.getsize(backup_path),
                            task_name=result["torrent_name"] or "unknown",
                            uploader_id=1,
                            downloader_id=source_downloader_id,
                            upload_time=datetime.now()
                        )
                        await self.db.commit()
                        logger.info(f"成功创建备份记录并复制文件: {backup_path}")
                    else:
                        logger.info(f"备份记录已存在，跳过创建: {info_hash}")

                except Exception as backup_err:
                    # 备份失败不影响转移结果，只记录警告
                    logger.warning(f"创建备份记录失败（不影响转移）: {backup_err}")

            # 转移成功
            result["success"] = True
            result["transfer_status"] = "success"

            # 如果需要删除原种子，标记需要确认
            if delete_source:
                result["require_confirmation"] = True
            else:
                result["require_confirmation"] = False

            result["transfer_duration"] = int((time.time() - start_time) * 1000)

            # 更新审计日志为成功
            await self._update_transfer_log(
                info_hash,
                "success",
                None,
                result["torrent_name"],
                result["transfer_duration"]
            )

            logger.info(f"种子转移成功: {info_hash}，耗时 {result['transfer_duration']}ms")

            # 6. 如果不需要删除原种子，直接返回
            if not delete_source:
                return result

            # 7. 如果需要删除原种子，从缓存获取源下载器客户端
            source_downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == source_downloader_id),
                None
            )

            if not source_downloader_vo:
                result["error_message"] = "源下载器不在缓存中，无法删除原种子"
                await self._update_transfer_log(info_hash, "partial", result["error_message"])
                return result

            if hasattr(source_downloader_vo, 'fail_time') and source_downloader_vo.fail_time > 0:
                result["error_message"] = "源下载器当前不可用，无法删除原种子"
                await self._update_transfer_log(info_hash, "partial", result["error_message"])
                return result

            source_client = source_downloader_vo.client

            # 删除原种子（不删除文件）
            delete_result = await self._delete_source_torrent(
                source_client=source_client,
                downloader_type=source_downloader.downloader_type,
                info_hash=info_hash,
                delete_files=False
            )

            if not delete_result:
                result["error_message"] = "转移成功，但删除原种子失败"
                result["transfer_status"] = "partial"
                await self._update_transfer_log(info_hash, "partial", result["error_message"])
            else:
                logger.info(f"原种子已删除: {info_hash}")
                await self._update_transfer_log(
                    info_hash,
                    "success",
                    "原种子已删除",
                    result["torrent_name"],
                    result["transfer_duration"]
                )

            return result

        except Exception as e:
            logger.error(f"种子转移异常: {str(e)}")
            result["error_message"] = f"转移失败: {str(e)}"
            await self._update_transfer_log(info_hash, "failed", result["error_message"])
            return result

    async def _verify_transfer(
        self,
        target_client: Any,
        downloader_type: int,
        info_hash: str,
        max_retries: int = 5,
        retry_interval: int = 5
    ) -> bool:
        """
        验证种子转移成功

        Args:
            target_client: 目标下载器客户端
            downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）
            info_hash: 种子哈希值
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）

        Returns:
            是否验证成功
        """
        logger.info(f"开始验证种子 {info_hash}，最多重试 {max_retries} 次，间隔 {retry_interval} 秒")

        normalized_type = DownloaderTypeEnum.normalize(downloader_type)

        for i in range(max_retries):
            await asyncio.sleep(retry_interval)

            try:
                if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                    # 获取种子信息
                    torrents = target_client.torrents_info(torrent_hashes=info_hash)

                    if not torrents or len(torrents) == 0:
                        logger.warning(f"第 {i+1} 次验证：未找到种子 {info_hash}")
                        continue

                    torrent = torrents[0]
                    state = torrent.state

                    # 转换状态
                    converted_state = TorrentStatusMapper.convert_qbittorrent_status(state)

                    logger.info(f"第 {i+1} 次验证：种子状态 = {state} (转换后: {converted_state})")

                    # 检查状态是否为 downloading 或 seeding
                    if converted_state in ["downloading", "seeding"]:
                        logger.info(f"验证成功：种子状态为 {converted_state}")
                        return True

                elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                    # 获取种子信息
                    torrents = target_client.get_torrents(info_hash)

                    if not torrents or len(torrents) == 0:
                        logger.warning(f"第 {i+1} 次验证：未找到种子 {info_hash}")
                        continue

                    torrent = torrents[0]
                    status = torrent.status

                    # 转换状态
                    converted_status = TorrentStatusMapper.convert_transmission_status(status)

                    logger.info(f"第 {i+1} 次验证：种子状态 = {status} (转换后: {converted_status})")

                    # 检查状态是否为 downloading 或 seeding
                    if converted_status in ["downloading", "seeding"]:
                        logger.info(f"验证成功：种子状态为 {converted_status}")
                        return True

            except Exception as e:
                logger.warning(f"第 {i+1} 次验证失败: {str(e)}")
                continue

        logger.warning(f"验证失败：已重试 {max_retries} 次")
        return False

    async def _delete_source_torrent(
        self,
        source_client: Any,
        downloader_type: int,
        info_hash: str,
        delete_files: bool = False
    ) -> bool:
        """
        删除源下载器的种子

        Args:
            source_client: 源下载器客户端
            downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）
            info_hash: 种子哈希值
            delete_files: 是否删除文件

        Returns:
            是否删除成功
        """
        try:
            normalized_type = DownloaderTypeEnum.normalize(downloader_type)

            if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                source_client.torrents_delete(
                    delete_files=delete_files,
                    torrent_hashes=info_hash
                )
                logger.info(f"已从qBittorrent删除种子 {info_hash}，删除文件: {delete_files}")
                return True

            elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                source_client.remove_torrent(
                    delete_data=delete_files,
                    ids=info_hash
                )
                logger.info(f"已从Transmission删除种子 {info_hash}，删除文件: {delete_files}")
                return True

        except Exception as e:
            logger.error(f"删除原种子失败: {str(e)}")
            return False

        return False

    async def _log_transfer_attempt(
        self,
        user_id: int,
        username: str,
        source_downloader_id: int,
        source_downloader_name: str,
        target_downloader_id: int,
        target_downloader_name: str,
        torrent_name: str,
        info_hash: str,
        source_path: str,
        target_path: str,
        delete_source: bool,
        transfer_status: str,
        error_message: Optional[str] = None,
        transfer_duration: Optional[int] = None
    ):
        """
        记录转移审计日志（操作开始时）

        Args:
            user_id: 操作用户ID
            username: 操作用户名
            source_downloader_id: 源下载器ID
            source_downloader_name: 源下载器名称
            target_downloader_id: 目标下载器ID
            target_downloader_name: 目标下载器名称
            torrent_name: 种子名称
            info_hash: 种子哈希值
            source_path: 源路径
            target_path: 目标路径
            delete_source: 是否删除原种子
            transfer_status: 转移状态
            error_message: 错误信息（可选）
            transfer_duration: 转移耗时（毫秒，可选）
        """
        try:
            async with AsyncSessionLocal() as async_db:
                audit_log = SeedTransferAuditLog(
                    operation_type='seed_transfer',
                    operation_time=datetime.now(),
                    user_id=user_id,
                    username=username,
                    source_downloader_id=source_downloader_id,
                    source_downloader_name=source_downloader_name,
                    target_downloader_id=target_downloader_id,
                    target_downloader_name=target_downloader_name,
                    torrent_name=torrent_name,
                    info_hash=info_hash,
                    source_path=source_path,
                    target_path=target_path,
                    delete_source=delete_source,
                    transfer_status=transfer_status,
                    error_message=error_message,
                    transfer_duration=transfer_duration
                )

                async_db.add(audit_log)
                await async_db.commit()

                # 保存日志ID用于后续更新
                self._last_audit_log_id = audit_log.id

                logger.info(f"记录转移审计日志: {info_hash} -> 状态: {transfer_status}")

        except Exception as e:
            logger.error(f"记录审计日志失败: {str(e)}")

    async def _update_transfer_log(
        self,
        info_hash: str,
        transfer_status: str,
        error_message: Optional[str] = None,
        torrent_name: Optional[str] = None,
        transfer_duration: Optional[int] = None
    ):
        """
        更新转移审计日志（操作结束时）

        Args:
            info_hash: 种子哈希值
            transfer_status: 转移状态
            error_message: 错误信息（可选）
            torrent_name: 种子名称（可选）
            transfer_duration: 转移耗时（可选）
        """
        try:
            if not hasattr(self, '_last_audit_log_id'):
                logger.warning("没有找到之前的审计日志记录")
                return

            async with AsyncSessionLocal() as async_db:
                audit_log_result = await async_db.execute(
                    select(SeedTransferAuditLog).where(SeedTransferAuditLog.id == self._last_audit_log_id)
                )
                audit_log = audit_log_result.scalar_one_or_none()

                if audit_log:
                    audit_log.transfer_status = transfer_status
                    if error_message:
                        audit_log.error_message = error_message
                    if torrent_name:
                        audit_log.torrent_name = torrent_name
                    if transfer_duration is not None:
                        audit_log.transfer_duration = transfer_duration

                    await async_db.commit()
                    logger.info(f"更新转移审计日志: {info_hash} -> 状态: {transfer_status}")

        except Exception as e:
            logger.error(f"更新审计日志失败: {str(e)}")
