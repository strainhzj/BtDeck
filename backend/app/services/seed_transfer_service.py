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
import re
import time
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import AsyncSessionLocal
from app.models.seed_transfer_audit_log import SeedTransferAuditLog
from app.models.setting_templates import DownloaderTypeEnum
from app.torrents.models import TorrentInfo
from app.downloader.models import BtDownloaders
from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

logger = logging.getLogger(__name__)

# 单次转移远程调用超时（秒，P0-04：经 call_downloader_api 的 INTERACTIVE lane 执行）
_TRANSFER_CALL_TIMEOUT = 30.0


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

    def __init__(self, db: Session):
        """
        初始化种子转移服务

        Args:
            db: 同步数据库会话（用于查询下载器信息等）
        """
        self.db = db
        # 注意：历史上 self.async_db 在本类的所有方法中都未被读取（审计日志方法内部均
        # 使用 `async with AsyncSessionLocal()`），属于死代码且会泄漏未归还的 aiosqlite 连接，
        # 故不再保留。原 async_db 参数也已删除（两个调用方均未传入，不存在兼容性问题）。

        # 初始化种子文件备份管理服务（自建会话，由本实例在 aclose() 中负责关闭）
        self.backup_manager = TorrentFileBackupManagerService(path_mapping_service=None)
        # 跟踪 aclose() 是否已调用，保证幂等。
        # 注意：该标志仅保证"串行"重复调用幂等，不保证并发安全。
        # 生产路径每个 HTTP 请求 new 一个 SeedTransferService 实例（不跨请求共享），
        # 故无需 asyncio.Lock；若将来改为跨协程共享，需引入锁保护。
        self._closed = False

    async def aclose(self) -> None:
        """
        异步释放本实例持有的资源（主要是自建的 backup_manager 数据库会话）。

        调用方应在 try/finally 中调用，避免连接泄漏触发 GC 回收时的 SAWarning。
        多次调用安全（串行幂等，非并发安全）。
        """
        if self._closed:
            return
        self._closed = True
        backup_manager = self.backup_manager
        if backup_manager is None:
            return
        try:
            await backup_manager.aclose()
        except Exception as e:
            logger.warning(f"关闭 SeedTransferService 备份管理器失败: {e}", exc_info=True)

    async def transfer_seed(
        self,
        source_downloader_id: int,
        target_downloader_id: int,
        info_hash: str,
        target_path: str,
        delete_source: bool,
        user_id: int,
        username: str,
        app_state: Optional[Any] = None,
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
            "target_path": target_path,
        }

        # info_hash 服务层格式校验（防穿越读取）：部分请求 schema 只限长度
        # 不限字符集，而 info_hash 会拼入本地种子文件路径
        # （save_path / f"{info_hash}.torrent"），含 .. 等字符可读保存目录外文件。
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", info_hash or ""):
            result["error_message"] = "info_hash 格式非法（须为 40/64 位十六进制），拒绝转移"
            return result

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
                transfer_duration=int((time.time() - start_time) * 1000),
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
                transfer_duration=int((time.time() - start_time) * 1000),
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
            transfer_duration=0,
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
                        with open(torrent_backup.file_path, "rb") as f:
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
                        f"种子文件备份不存在，且下载器保存目录也未找到种子文件\n" f"预期路径: {source_torrent_path}"
                    )
                    await self._update_transfer_log(info_hash, "failed", result["error_message"])
                    return result

                # 从源下载器保存目录读取种子文件
                try:
                    with open(source_torrent_path, "rb") as f:
                        torrent_content = f.read()
                    used_fallback = True
                    logger.info(f"从源下载器保存目录成功读取种子文件: {source_torrent_path}")

                    # 从 TorrentInfo 获取种子名称
                    source_torrent_result = await self.db.execute(
                        select(TorrentInfo).where(
                            TorrentInfo.hash == info_hash,
                            TorrentInfo.downloader_id == source_downloader_id,
                            TorrentInfo.dr == 0,
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
                    TorrentInfo.dr == 0,
                )
            )
            source_torrent = source_torrent_result.scalar_one_or_none()

            if source_torrent:
                result["source_path"] = source_torrent.save_path
            else:
                result["source_path"] = "未知"

            # 2. 从缓存获取目标下载器客户端
            if not app_state or not hasattr(app_state, "store"):
                result["error_message"] = "下载器缓存未初始化"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            cached_downloaders = await app_state.store.get_snapshot()
            target_downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == target_downloader_id), None
            )

            if not target_downloader_vo:
                result["error_message"] = f"目标下载器不在缓存中: {target_downloader_id}"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            if hasattr(target_downloader_vo, "fail_time") and target_downloader_vo.fail_time > 0:
                result["error_message"] = "目标下载器当前不可用"
                await self._update_transfer_log(info_hash, "failed", result["error_message"])
                return result

            target_client = target_downloader_vo.client

            # 2.5 目标查重：目标下载器已存在相同 hash 时直接返回 duplicate，
            # 避免 torrents_add 静默失败后 _verify_transfer 按旧种子误判"成功"。
            try:
                existing_on_target = await self._check_target_duplicate(
                    downloader_id=target_downloader_id,
                    target_client=target_client,
                    downloader_type=target_downloader.downloader_type,
                    info_hash=info_hash,
                )
            except Exception as e:
                # 查重失败不阻断转移（竞态由 _verify_transfer 兜底）
                logger.warning(f"目标查重失败（继续转移）: {e}")
                existing_on_target = False

            if existing_on_target:
                result["transfer_status"] = "duplicate"
                result["error_message"] = f"目标下载器已存在相同种子: {info_hash}"
                await self._log_transfer_attempt(
                    user_id=user_id,
                    username=username,
                    source_downloader_id=source_downloader_id,
                    source_downloader_name=result.get("source_downloader_name", ""),
                    target_downloader_id=target_downloader_id,
                    target_downloader_name=result.get("target_downloader_name", ""),
                    torrent_name=result.get("torrent_name") or "",
                    info_hash=info_hash,
                    source_path=result.get("source_path") or "",
                    target_path=target_path,
                    delete_source=delete_source,
                    transfer_status="duplicate",
                    error_message=result["error_message"],
                    transfer_duration=int((time.time() - start_time) * 1000),
                )
                return result

            # 3. 添加种子到目标下载器
            logger.info(f"添加种子到目标下载器 {target_downloader_id}，路径: {target_path}")

            normalized_type = DownloaderTypeEnum.normalize(target_downloader.downloader_type)

            if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                from qbittorrentapi import LoginFailed

                try:
                    from io import BytesIO

                    # P0-04 修复：torrents_add 经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                    add_response = await call_downloader_api(
                        target_downloader_id,
                        DownloadLane.INTERACTIVE,
                        target_client.torrents_add,
                        kwargs={"torrent_files": BytesIO(torrent_content), "save_path": target_path},
                        timeout=_TRANSFER_CALL_TIMEOUT,
                        operation="transfer_qb_add_torrent",
                    )
                    # qB 添加失败返回 "Fails." 字符串而不抛异常：必须检查返回值，
                    # 否则 _verify_transfer 重试 5×5 秒后才报失败（且重复种子场景会误判成功）
                    if isinstance(add_response, str) and "Fails" in add_response:
                        result["error_message"] = f"目标下载器拒绝添加种子: {add_response.strip()}"
                        await self._update_transfer_log(info_hash, "failed", result["error_message"])
                        return result
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

                    # P0-04 修复：add_torrent 经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                    add_result = await call_downloader_api(
                        target_downloader_id,
                        DownloadLane.INTERACTIVE,
                        target_client.add_torrent,
                        args=(BytesIO(torrent_content),),
                        kwargs={"download_dir": target_path},
                        timeout=_TRANSFER_CALL_TIMEOUT,
                        operation="transfer_tr_add_torrent",
                    )
                    # transmission-rpc add_torrent 失败抛异常；成功返回 Torrent 对象。
                    # 返回 None 视为异常（重复种子时返回已有 Torrent 对象，由验证最终确认）。
                    if add_result is None:
                        result["error_message"] = "目标下载器未返回添加结果"
                        await self._update_transfer_log(info_hash, "failed", result["error_message"])
                        return result
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
                downloader_id=target_downloader_id,
                target_client=target_client,
                downloader_type=target_downloader.downloader_type,
                info_hash=info_hash,
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

                    local_backup_manager = TorrentFileBackupManagerService(db=self.db)

                    # 检查是否已存在备份记录
                    existing_backup = await self.db.execute(
                        select(TorrentFileBackup).filter(
                            TorrentFileBackup.info_hash == info_hash,
                            TorrentFileBackup.downloader_id == source_downloader_id,
                            TorrentFileBackup.is_deleted.is_(False),
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
                            info_id, result["torrent_name"] or "unknown"
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
                        await local_backup_manager.repository.create(
                            info_hash=info_hash,
                            file_path=backup_path,
                            file_size=os.path.getsize(backup_path),
                            task_name=result["torrent_name"] or "unknown",
                            uploader_id=1,
                            downloader_id=source_downloader_id,
                            upload_time=datetime.now(),
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
                info_hash, "success", None, result["torrent_name"], result["transfer_duration"]
            )

            logger.info(f"种子转移成功: {info_hash}，耗时 {result['transfer_duration']}ms")

            # 6. 如果不需要删除原种子，直接返回
            if not delete_source:
                return result

            # 7. 如果需要删除原种子，从缓存获取源下载器客户端
            source_downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == source_downloader_id), None
            )

            if not source_downloader_vo:
                result["error_message"] = "源下载器不在缓存中，无法删除原种子"
                await self._update_transfer_log(info_hash, "partial", result["error_message"])
                return result

            if hasattr(source_downloader_vo, "fail_time") and source_downloader_vo.fail_time > 0:
                result["error_message"] = "源下载器当前不可用，无法删除原种子"
                await self._update_transfer_log(info_hash, "partial", result["error_message"])
                return result

            source_client = source_downloader_vo.client

            # 删除原种子（不删除文件）
            delete_result = await self._delete_source_torrent(
                downloader_id=source_downloader_id,
                source_client=source_client,
                downloader_type=source_downloader.downloader_type,
                info_hash=info_hash,
                delete_files=False,
            )

            if not delete_result:
                result["error_message"] = "转移成功，但删除原种子失败"
                result["transfer_status"] = "partial"
                await self._update_transfer_log(info_hash, "partial", result["error_message"])
            else:
                logger.info(f"原种子已删除: {info_hash}")
                await self._update_transfer_log(
                    info_hash, "success", "原种子已删除", result["torrent_name"], result["transfer_duration"]
                )

            return result

        except Exception as e:
            logger.error(f"种子转移异常: {str(e)}")
            result["error_message"] = f"转移失败: {str(e)}"
            await self._update_transfer_log(info_hash, "failed", result["error_message"])
            return result

    async def _verify_transfer(
        self,
        downloader_id: int,
        target_client: Any,
        downloader_type: int,
        info_hash: str,
        max_retries: int = 5,
        retry_interval: int = 5,
    ) -> bool:
        """
        验证种子转移成功

        Args:
            downloader_id: 目标下载器ID（用于 call_downloader_api 限流与日志）
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
                    # 获取种子信息（P0-04 修复：轮询内的 torrents_info 经 INTERACTIVE lane 执行）
                    torrents = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        target_client.torrents_info,
                        kwargs={"torrent_hashes": info_hash},
                        timeout=_TRANSFER_CALL_TIMEOUT,
                        operation="transfer_qb_verify",
                    )

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
                    # 获取种子信息（P0-04 修复：轮询内的 get_torrents 经 INTERACTIVE lane 执行）
                    torrents = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        target_client.get_torrents,
                        args=(info_hash,),
                        timeout=_TRANSFER_CALL_TIMEOUT,
                        operation="transfer_tr_verify",
                    )

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

    async def _check_target_duplicate(
        self,
        downloader_id: int,
        target_client: Any,
        downloader_type: int,
        info_hash: str,
    ) -> bool:
        """转移前查重：目标下载器是否已存在相同 hash 的种子。

        qB torrents_info 对未知 hash 返回空列表；TR get_torrents 对缺失返回空列表，
        都不报错。存在即返回 True（transfer 直接以 duplicate 状态返回，不重复添加）。
        """
        try:
            normalized_type = DownloaderTypeEnum.normalize(downloader_type)
            if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                torrents = await call_downloader_api(
                    downloader_id,
                    DownloadLane.INTERACTIVE,
                    target_client.torrents_info,
                    kwargs={"torrent_hashes": info_hash},
                    timeout=_TRANSFER_CALL_TIMEOUT,
                    operation="transfer_qb_duplicate_check",
                )
                return bool(torrents)
            if normalized_type == DownloaderTypeEnum.TRANSMISSION:
                torrents = await call_downloader_api(
                    downloader_id,
                    DownloadLane.INTERACTIVE,
                    target_client.get_torrents,
                    args=(info_hash,),
                    timeout=_TRANSFER_CALL_TIMEOUT,
                    operation="transfer_tr_duplicate_check",
                )
                return bool(torrents)
            return False
        except Exception as e:
            logger.warning(f"目标查重异常（按不存在处理）: {e}")
            return False

    async def _delete_source_torrent(
        self, downloader_id: int, source_client: Any, downloader_type: int, info_hash: str, delete_files: bool = False
    ) -> bool:
        """
        删除源下载器的种子

        Args:
            downloader_id: 源下载器ID（用于 call_downloader_api 限流与日志）
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
                # P0-04 修复：torrents_delete 经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                await call_downloader_api(
                    downloader_id,
                    DownloadLane.INTERACTIVE,
                    source_client.torrents_delete,
                    kwargs={"delete_files": delete_files, "torrent_hashes": info_hash},
                    timeout=_TRANSFER_CALL_TIMEOUT,
                    operation="transfer_qb_delete_source",
                )
                logger.info(f"已从qBittorrent删除种子 {info_hash}，删除文件: {delete_files}")
                return True

            elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                # P0-04 修复：remove_torrent 经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                await call_downloader_api(
                    downloader_id,
                    DownloadLane.INTERACTIVE,
                    source_client.remove_torrent,
                    kwargs={"delete_data": delete_files, "ids": info_hash},
                    timeout=_TRANSFER_CALL_TIMEOUT,
                    operation="transfer_tr_delete_source",
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
        transfer_duration: Optional[int] = None,
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
                    operation_type="seed_transfer",
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
                    transfer_duration=transfer_duration,
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
        transfer_duration: Optional[int] = None,
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
            if not hasattr(self, "_last_audit_log_id"):
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
