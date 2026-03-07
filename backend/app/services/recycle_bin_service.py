"""
回收站服务

提供回收站的列表查询、种子还原、清理预览、手动清理等功能。
支持批量操作和详细的操作结果记录。
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO

from app.torrents.models import TorrentInfo, TrackerInfo as trackerInfoModel
from app.downloader.models import BtDownloaders
from app.core.file_operations import FileOperationService
from app.core.path_mapping import PathMappingService
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from qbittorrentapi import Client as qbClient
from transmission_rpc import Client as trClient, TransmissionError

logger = logging.getLogger(__name__)


class RecycleBinService:
    """回收站服务"""

    def __init__(self, db_async: AsyncSession):
        """
        初始化回收站服务

        内部创建同步 Session，保持所有方法使用同步模式。

        Args:
            db_async: 异步数据库会话（用于获取同步会话）
        """
        from app.database import SessionLocal
        self.db = SessionLocal()  # 创建同步会话

    def get_recycle_bin_list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询回收站列表

        Args:
            page: 页码（从1开始）
            page_size: 每页数量
            search: 搜索关键词（按名称搜索）

        Returns:
            查询结果字典
            {
                "total": int,
                "page": int,
                "pageSize": int,
                "list": List[Dict]
            }
        """
        try:
            # 构建查询条件：deleted_at不为NULL且dr=0（仅显示可还原的种子）
            query = self.db.query(TorrentInfo).filter(
                and_(
                    TorrentInfo.deleted_at.isnot(None),  # 在回收站中
                    TorrentInfo.dr == 0  # 只显示可还原的种子（dr=0）
                )
            )

            # 添加搜索条件
            if search:
                search_pattern = f"%{search}%"
                query = query.filter(TorrentInfo.name.like(search_pattern))

            # 按删除时间倒序排列
            query = query.order_by(TorrentInfo.deleted_at.desc())

            # 计算总数
            total = query.count()

            # 分页查询
            offset = (page - 1) * page_size
            torrents = query.offset(offset).limit(page_size).all()

            # 转换为字典列表
            torrent_list = []
            for torrent in torrents:
                torrent_dict = torrent.to_dict()
                # 添加删除时间格式化
                torrent_dict['deleted_at_formatted'] = torrent.get_deleted_at_formatted()
                # 添加是否可还原标记
                torrent_dict['can_restore'] = self._check_can_restore(torrent)
                torrent_list.append(torrent_dict)

            return {
                "total": total,
                "page": page,
                "pageSize": page_size,
                "list": torrent_list
            }

        except Exception as e:
            logger.error(f"查询回收站列表失败: {str(e)}", exc_info=True)
            return {
                "total": 0,
                "page": page,
                "pageSize": page_size,
                "list": []
            }

    def _check_can_restore(self, torrent: TorrentInfo) -> bool:
        """
        检查种子是否可以还原

        Args:
            torrent: 种子信息

        Returns:
            是否可以还原
        """
        # 检查是否有备份文件
        if torrent.backup_file_path and os.path.exists(torrent.backup_file_path):
            return True

        # TODO: 可以添加更多检查，比如下载器是否可用等
        return False

    async def restore_torrents(
        self,
        torrent_ids: List[str],
        operator: str,
        audit_service=None,
        request=None
    ) -> Dict[str, Any]:
        """
        批量还原种子

        步骤：
        1. 重命名文件/文件夹（移除.pending_delete后缀）
        2. 从备份文件读取种子数据并重新添加到下载器（跳过哈希校验）
        3. 清除deleted_at字段
        4. 记录审计日志

        回滚机制：
        如果步骤2失败，自动回滚步骤1的文件名修改

        Args:
            torrent_ids: 种子ID列表
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            还原结果字典
            {
                "success_count": int,
                "failed_count": int,
                "skipped_count": int,
                "success_list": List[Dict],
                "failed_list": List[Dict]
            }
        """
        result = {
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "success_list": [],
            "failed_list": []
        }

        for torrent_id in torrent_ids:
            try:
                # 查询种子信息（包含 dr=0 和 dr=1）
                torrent = self.db.query(TorrentInfo).filter(
                    TorrentInfo.info_id == torrent_id
                ).first()

                if not torrent:
                    result["failed_count"] += 1
                    result["failed_list"].append({
                        "torrent_id": torrent_id,
                        "reason": "种子不存在"
                    })
                    continue

                # 检查是否在回收站
                if not torrent.deleted_at:
                    result["skipped_count"] += 1
                    logger.warning(f"种子不在回收站中，跳过: {torrent.name}")
                    continue

                # 检查是否有备份文件
                if not torrent.backup_file_path or not os.path.exists(torrent.backup_file_path):
                    result["failed_count"] += 1
                    result["failed_list"].append({
                        "torrent_id": torrent_id,
                        "torrent_name": torrent.name,
                        "reason": "种子文件备份不存在，请手动提供种子文件"
                    })
                    logger.error(f"种子文件备份不存在: {torrent.backup_file_path}")
                    continue

                # 获取下载器信息
                downloader = self.db.query(BtDownloaders).filter(
                    BtDownloaders.downloader_id == torrent.downloader_id
                ).first()

                if not downloader:
                    result["failed_count"] += 1
                    result["failed_list"].append({
                        "torrent_id": torrent_id,
                        "torrent_name": torrent.name,
                        "reason": "下载器不存在"
                    })
                    continue

                # 步骤1: 智能还原种子名称（移除.pending_delete后缀）
                file_op_service = FileOperationService(
                    path_mapping_service=self._get_path_mapping_service(downloader)
                )

                # 用于回滚的信息
                restore_info = {
                    "renamed": False,
                    "original_path": None,
                    "restored_path": None,
                    "is_directory": None
                }

                if torrent.original_filename:
                    # 检测种子类型（单文件或多文件）
                    is_single_file = file_op_service.is_single_file_torrent(torrent.original_filename)

                    # 构建当前的完整路径（带.pending_delete后缀）
                    if is_single_file:
                        # 单文件种子：original_filename.mkv -> original_filename.pending_delete.mkv
                        name_without_ext, ext = os.path.splitext(torrent.original_filename)
                        current_name = f"{name_without_ext}.pending_delete{ext}"
                    else:
                        # 多文件种子：[文件夹名] -> [文件夹名].pending_delete
                        current_name = f"{torrent.original_filename}.pending_delete"

                    current_path = os.path.join(torrent.save_path, current_name)

                    # 尝试智能还原种子名称（支持单文件和多文件）
                    restore_result = await file_op_service.restore_torrent_from_recycle(
                        current_path=current_path,
                        original_name=torrent.original_filename,
                        is_directory=not is_single_file  # 单文件=False, 多文件=True
                    )

                    if restore_result.get("success"):
                        # 记录还原信息，用于失败时回滚
                        restore_info["renamed"] = True
                        restore_info["original_path"] = restore_result.get("original_path")
                        restore_info["restored_path"] = restore_result.get("new_path")
                        restore_info["is_directory"] = restore_result.get("is_directory")

                        logger.info(
                            f"种子名称还原成功 ({restore_result.get('torrent_type')}): "
                            f"{current_name} -> {torrent.original_filename}"
                        )
                    else:
                        logger.warning(
                            f"种子名称还原失败（{restore_result.get('torrent_type', 'unknown')}）"
                            f"（降级）: {restore_result.get('error')}, 继续还原流程"
                        )

                # 步骤2: 读取种子文件并重新添加到下载器
                restore_result = await self._restore_torrent_to_downloader(
                    torrent=torrent,
                    downloader=downloader,
                    app=request.app if request else None
                )

                if not restore_result["success"]:
                    # 还原失败，执行回滚
                    if restore_info["renamed"]:
                        rollback_success = await self._rollback_file_rename(restore_info)
                        if rollback_success:
                            logger.info(f"文件名回滚成功: {torrent.name}")
                        else:
                            logger.error(f"文件名回滚失败: {torrent.name}")

                    # 构建详细错误信息
                    error_detail = restore_result.get("error", "重新添加到下载器失败")
                    if restore_info["renamed"]:
                        error_detail += f"（已回滚文件名修改）"

                    result["failed_count"] += 1
                    result["failed_list"].append({
                        "torrent_id": torrent_id,
                        "torrent_name": torrent.name,
                        "reason": error_detail
                    })
                    continue

                # 步骤4: 清除deleted_at字段
                torrent.restore_from_recycle_bin()
                torrent.update_time = datetime.now()
                torrent.update_by = operator
                self.db.commit()

                # 记录审计日志
                if audit_service:
                    operation_detail = {
                        "torrent_name": torrent.name,
                        "downloader_id": torrent.downloader_id,
                        "downloader_name": torrent.downloader_name,
                        "file_restored": restore_info["renamed"]
                    }

                    # 如果文件还原成功，记录到审计日志
                    if restore_info["renamed"]:
                        operation_detail["previous_filename"] = f"{torrent.original_filename}.pending_delete"
                        operation_detail["restored_filename"] = torrent.original_filename
                        operation_detail["is_directory"] = restore_info["is_directory"]

                    await audit_service.log_operation(
                        operation_type=AuditOperationType.RESTORE,
                        operator=operator,
                        torrent_info_id=torrent.info_id,
                        operation_detail=operation_detail,
                        old_value={"status": "in_recycle_bin"},
                        new_value={"status": "active"},
                        operation_result=AuditOperationResult.SUCCESS,
                        downloader_id=torrent.downloader_id
                    )

                result["success_count"] += 1
                result["success_list"].append({
                    "torrent_id": torrent_id,
                    "torrent_name": torrent.name
                })
                logger.info(f"种子还原成功: {torrent.name}")

            except Exception as e:
                result["failed_count"] += 1
                result["failed_list"].append({
                    "torrent_id": torrent_id,
                    "reason": f"还原异常: {str(e)}"
                })
                logger.error(f"还原种子异常: {torrent_id}, 错误: {e}", exc_info=True)

        return result

    async def _restore_torrent_to_downloader(
        self,
        torrent: TorrentInfo,
        downloader: BtDownloaders,
        app=None
    ) -> Dict[str, Any]:
        """
        重新添加种子到下载器

        Args:
            torrent: 种子信息
            downloader: 下载器信息
            app: FastAPI应用实例（用于访问缓存的客户端连接）

        Returns:
            操作结果
        """
        try:
            # 步骤1：检查 app 对象和缓存初始化（CLAUDE.md 第16条规范）
            if not app:
                return {
                    "success": False,
                    "error": "app对象未提供，无法获取缓存的客户端连接"
                }

            if not hasattr(app.state, 'store'):
                return {
                    "success": False,
                    "error": "下载器缓存未初始化（app.state.store不存在）"
                }

            # 步骤2：从缓存获取下载器
            cached_downloaders = app.state.store.get_snapshot_sync()
            downloader_vo = next(
                (d for d in cached_downloaders if d.downloader_id == downloader.downloader_id),
                None
            )

            # 步骤3：验证下载器是否在缓存中
            if not downloader_vo:
                return {
                    "success": False,
                    "error": f"下载器不在缓存中 [downloader_id={downloader.downloader_id}]"
                }

            # 步骤4：验证下载器是否有效（fail_time=0 表示有效）
            if hasattr(downloader_vo, 'fail_time') and downloader_vo.fail_time > 0:
                return {
                    "success": False,
                    "error": f"下载器已失效 [downloader_id={downloader.downloader_id}, nickname={downloader_vo.nickname}]"
                }

            # 步骤5：获取缓存的客户端连接
            client = downloader_vo.client

            # 步骤6：验证客户端是否存在
            if not client:
                return {
                    "success": False,
                    "error": f"下载器客户端连接不存在 [downloader_id={downloader.downloader_id}]"
                }

            # 步骤7：读取种子文件内容
            def read_torrent_file():
                with open(torrent.backup_file_path, "rb") as f:
                    return f.read()

            file_data = await asyncio.to_thread(read_torrent_file)
            file_bytes = BytesIO(file_data)

            # 步骤8：使用缓存的客户端执行操作
            if downloader.is_qbittorrent:
                # 使用缓存的qBittorrent客户端
                client.torrents_add(
                    torrent_files=file_bytes,
                    save_path=torrent.save_path,
                    is_stopped=True,  # 还原后默认暂停，让用户手动开始
                    skip_checking=True  # 跳过哈希校验
                )

                # 等待qBittorrent处理种子
                await self._wait_for_qb_torrent(client, torrent.hash)

                return {"success": True}

            elif downloader.is_transmission:
                # 使用缓存的Transmission客户端
                # 注意：Transmission的add_torrent()不支持skip_checking参数
                client.add_torrent(
                    file_bytes,
                    paused=True,  # 还原后默认暂停
                    download_dir=torrent.save_path
                )

                # 等待Transmission处理种子
                await self._wait_for_tr_torrent(client, torrent.hash)

                return {"success": True}

            else:
                return {
                    "success": False,
                    "error": f"不支持的下载器类型: {downloader.downloader_type}"
                }

        except Exception as e:
            logger.error(f"重新添加种子到下载器失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _wait_for_qb_torrent(
        self,
        qb_client: qbClient,
        torrent_hash: str,
        max_retries: int = 30
    ) -> bool:
        """等待qBittorrent处理种子"""
        for _ in range(max_retries):
            await asyncio.sleep(1)
            try:
                torrents = qb_client.torrents_info(torrent_hashes=torrent_hash)
                if torrents and len(torrents) > 0:
                    return True
            except Exception:
                continue
        return False

    async def _wait_for_tr_torrent(
        self,
        tr_client: trClient,
        torrent_hash: str,
        max_retries: int = 30
    ) -> bool:
        """等待Transmission处理种子"""
        for _ in range(max_retries):
            await asyncio.sleep(1)
            try:
                torrent = tr_client.get_torrent(torrent_hash)
                if torrent:
                    return True
            except Exception:
                continue
        return False

    async def _rollback_file_rename(
        self,
        restore_info: Dict[str, Any]
    ) -> bool:
        """
        回滚文件名修改

        将已重命名的文件/文件夹改回带.pending_delete后缀的名称

        Args:
            restore_info: 还原信息字典
                {
                    "renamed": bool,
                    "original_path": str,  # 重命名前的路径（带后缀）
                    "restored_path": str,  # 重命名后的路径（无后缀）
                    "is_directory": bool
                }

        Returns:
            回滚是否成功
        """
        try:
            if not restore_info.get("renamed"):
                return True

            original_path = restore_info.get("original_path")
            restored_path = restore_info.get("restored_path")

            if not original_path or not restored_path:
                logger.warning("回滚失败: 缺少路径信息")
                return False

            # 在线程池中执行重命名操作
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                os.rename,
                restored_path,
                original_path
            )

            logger.info(f"文件名回滚成功: {restored_path} -> {original_path}")
            return True

        except Exception as e:
            logger.error(f"文件名回滚失败: {str(e)}", exc_info=True)
            return False

    def _get_path_mapping_service(self, downloader: BtDownloaders) -> Optional[PathMappingService]:
        """获取路径映射服务"""
        if downloader.path_mapping:
            try:
                return PathMappingService(downloader.path_mapping)
            except Exception as e:
                logger.warning(f"加载路径映射服务失败: {e}")
        return None

    def cleanup_preview(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        清理预览

        查询指定天数之前的回收站种子，计算总大小

        Args:
            days: 天数（清理N天前的数据）

        Returns:
            预览结果
            {
                "total_count": int,
                "total_size": int,
                "torrent_list": List[Dict]
            }
        """
        try:
            # 计算截止时间
            cutoff_time = datetime.now() - timedelta(days=days)

            # 查询符合条件的种子（仅 dr=0 可还原的种子）
            torrents = self.db.query(TorrentInfo).filter(
                and_(
                    TorrentInfo.deleted_at < cutoff_time,
                    TorrentInfo.dr == 0  # 只预览可还原的种子（dr=0）
                )
            ).all()

            # 计算总大小
            total_size = sum(t.size or 0 for t in torrents)

            # 构建预览列表
            torrent_list = []
            for torrent in torrents:
                torrent_list.append({
                    "info_id": torrent.info_id,
                    "name": torrent.name,
                    "size": torrent.size,
                    "deleted_at": torrent.deleted_at.isoformat() if torrent.deleted_at else None,
                    "save_path": torrent.save_path
                })

            return {
                "total_count": len(torrents),
                "total_size": total_size,
                "torrent_list": torrent_list
            }

        except Exception as e:
            logger.error(f"清理预览失败: {str(e)}", exc_info=True)
            return {
                "total_count": 0,
                "total_size": 0,
                "torrent_list": []
            }

    async def manual_cleanup(
        self,
        torrent_ids: List[str],
        operator: str,
        audit_service=None
    ) -> Dict[str, Any]:
        """
        手动清理回收站种子

        步骤：
        1. 删除.waiting-delete标记文件
        2. 设置dr=1（逻辑删除）
        3. 记录审计日志

        Args:
            torrent_ids: 种子ID列表
            operator: 操作人
            audit_service: 审计日志服务

        Returns:
            清理结果
            {
                "success_count": int,
                "failed_count": int,
                "success_list": List[Dict],
                "failed_list": List[Dict]
            }
        """
        result = {
            "success_count": 0,
            "failed_count": 0,
            "success_list": [],
            "failed_list": []
        }

        for torrent_id in torrent_ids:
            try:
                # 查询种子信息（包含 dr=0 和 dr=1）
                torrent = self.db.query(TorrentInfo).filter(
                    TorrentInfo.info_id == torrent_id
                ).first()

                if not torrent:
                    result["failed_count"] += 1
                    result["failed_list"].append({
                        "torrent_id": torrent_id,
                        "reason": "种子不存在"
                    })
                    continue

                # 获取下载器信息
                downloader = self.db.query(BtDownloaders).filter(
                    BtDownloaders.downloader_id == torrent.downloader_id
                ).first()

                # 步骤1: 精确删除种子文件 + 清理空文件夹
                if downloader and torrent.save_path:
                    try:
                        file_op_service = FileOperationService(
                            path_mapping_service=self._get_path_mapping_service(downloader)
                        )

                        # ========== 1.1 读取原始文件列表 ==========
                        import json
                        original_file_list = None
                        if torrent.original_file_list:
                            try:
                                original_file_list = json.loads(torrent.original_file_list)
                                logger.info(f"读取文件列表成功: {len(original_file_list)} 个文件")
                            except Exception as e:
                                logger.warning(f"解析文件列表失败: {e}")

                        # ========== 1.2 转换路径（内部路径 -> 外部路径）==========
                        # 后续所有文件操作都需要使用外部路径
                        external_save_path = file_op_service._convert_path(torrent.save_path)

                        # ========== 1.3 精确删除种子文件（在.pending_delete文件夹中）==========
                        if original_file_list:
                            # 删除种子任务下载的文件（相对路径列表）
                            deleted_files = []
                            failed_files = []

                            for file_rel_path in original_file_list:
                                # 构建完整路径（在.pending_delete文件夹中）
                                if torrent.original_filename:
                                    # 多文件种子: /save_path/name.pending_delete/relpath
                                    file_full_path = os.path.join(
                                        external_save_path,
                                        f"{torrent.original_filename}.pending_delete",
                                        file_rel_path
                                    )
                                else:
                                    # 单文件种子: /save_path/name.pending_delete.ext
                                    file_full_path = os.path.join(
                                        external_save_path,
                                        file_rel_path
                                    )

                                try:
                                    if os.path.exists(file_full_path):
                                        os.remove(file_full_path)
                                        deleted_files.append(file_rel_path)
                                        logger.debug(f"删除文件成功: {file_rel_path}")
                                    else:
                                        logger.debug(f"文件不存在，跳过: {file_rel_path}")
                                except Exception as e:
                                    failed_files.append(f"{file_rel_path}: {str(e)}")
                                    logger.warning(f"删除文件失败: {file_rel_path}, {e}")

                            logger.info(
                                f"精确删除完成: 成功 {len(deleted_files)} 个, "
                                f"失败 {len(failed_files)} 个"
                            )

                        # ========== 1.4 清理空文件夹 ==========
                        if torrent.original_filename:
                            # 递归检查文件夹是否为空
                            def is_folder_empty(folder_path):
                                """递归检查文件夹是否为空（没有文件）"""
                                if not os.path.exists(folder_path):
                                    return True
                                for root, dirs, files in os.walk(folder_path):
                                    if files:  # 有文件
                                        return False
                                return True

                            # 检查并删除 .pending_delete 文件夹（如果为空）
                            pending_delete_folder = os.path.join(
                                external_save_path,
                                f"{torrent.original_filename}.pending_delete"
                            )

                            if is_folder_empty(pending_delete_folder):
                                try:
                                    import shutil
                                    shutil.rmtree(pending_delete_folder)
                                    logger.info(f"删除空.pending_delete文件夹: {pending_delete_folder}")
                                except Exception as e:
                                    logger.debug(f"删除空.pending_delete文件夹失败: {pending_delete_folder}, {e}")
                            else:
                                logger.debug(f".pending_delete文件夹非空，保留: {pending_delete_folder}")

                            # 检查并删除原文件夹（如果为空）
                            # 注意：这里只删除该种子任务创建的原文件夹，不影响其他种子任务
                            original_folder = os.path.join(
                                external_save_path,
                                torrent.original_filename
                            )

                            if os.path.exists(original_folder) and is_folder_empty(original_folder):
                                try:
                                    os.rmdir(original_folder)
                                    logger.info(f"删除空原文件夹: {original_folder}")
                                except Exception as e:
                                    logger.debug(f"删除空原文件夹失败: {original_folder}, {e}")

                        # ========== 1.5 删除标记文件（只删除标记文件，不删除文件夹）==========
                        await file_op_service.delete_marker_file(
                            directory_path=torrent.save_path,
                            torrent_name=torrent.name,
                            torrent_original_filename=torrent.original_filename,
                            delete_pending_delete_folder=False  # 只删除标记文件
                        )

                    except Exception as e:
                        logger.warning(f"清理文件失败（降级）: {torrent.name}, {e}")

                # 步骤2: 设置dr=1（逻辑删除）
                torrent.dr = 1
                torrent.update_time = datetime.now()
                torrent.update_by = operator
                self.db.commit()

                # 步骤3: 记录审计日志
                if audit_service:
                    await audit_service.log_operation(
                        operation_type=AuditOperationType.CLEANUP_L3,
                        operator=operator,
                        torrent_info_id=torrent.info_id,
                        operation_detail={
                            "torrent_name": torrent.name,
                            "downloader_id": torrent.downloader_id
                        },
                        old_value={"status": "in_recycle_bin"},
                        new_value={"status": "deleted"},
                        operation_result=AuditOperationResult.SUCCESS,
                        downloader_id=torrent.downloader_id
                    )

                result["success_count"] += 1
                result["success_list"].append({
                    "torrent_id": torrent_id,
                    "torrent_name": torrent.name
                })
                logger.info(f"回收站种子清理成功: {torrent.name}")

            except Exception as e:
                result["failed_count"] += 1
                result["failed_list"].append({
                    "torrent_id": torrent_id,
                    "reason": f"清理异常: {str(e)}"
                })
                logger.error(f"清理种子异常: {torrent_id}, 错误: {e}", exc_info=True)

        return result
