# -*- coding: utf-8 -*-
"""
种子文件备份管理服务

协调Repository层和文件操作服务，提供完整的种子文件备份业务逻辑。
这是业务逻辑层的封装，处理所有与种子文件备份相关的业务操作。

职责：
- 协调数据库操作和文件操作
- 业务逻辑封装
- 错误处理和日志记录
- 与现有TorrentFileBackupService集成

@author: btpManager Team
@file: torrent_file_backup_manager.py
@time: 2026-02-15
"""

import asyncio
import os
import logging
import re
from typing import Dict, Any, Optional, List, cast
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.torrent_file_backup import TorrentFileBackup
from app.torrents.models import TorrentInfo
from app.repositories.torrent_file_backup_repository import TorrentFileBackupRepository
from app.core.torrent_file_backup import TorrentFileBackupService
from app.core.path_mapping import PathMappingService
from app.tasks.resource_guard import admission_controller

logger = logging.getLogger(__name__)

_TORRENT_HASH_IN_FILENAME = re.compile(r"(?i)([0-9a-f]{40})")


class TorrentFileBackupManagerService:
    """
    种子文件备份管理服务

    提供完整的种子文件备份业务逻辑，协调数据库操作和文件系统操作。
    复用现有的TorrentFileBackupService进行文件操作。
    """

    def __init__(
        self,
        db: Optional[AsyncSession] = None,
        path_mapping_service: Optional[PathMappingService] = None,
        file_backup_service: Optional[TorrentFileBackupService] = None,
    ):
        """
        初始化管理服务

        Args:
            db: 异步数据库会话（可选，默认创建新会话；自建会话由本实例负责关闭）
            path_mapping_service: 路径映射服务（可选）
        """
        # 跟踪是否拥有自建会话的所有权：仅当由本实例创建时，aclose() 才负责关闭，
        # 避免误关闭外部传入的会话（外部会话由其所有者负责生命周期）。
        if db is None:
            self.db = AsyncSessionLocal()
            self._owns_db = True
        else:
            self.db = db
            self._owns_db = False
        self._closed = False  # 跟踪 aclose() 是否已调用，保证幂等

        self.repository = TorrentFileBackupRepository(self.db)
        self.path_mapping_service = path_mapping_service

        # 初始化文件备份服务（复用现有代码）
        self.file_backup_service = file_backup_service or TorrentFileBackupService(
            path_mapping_service=path_mapping_service
        )

    @staticmethod
    def _index_torrent_sources(source_root: Optional[str]) -> Dict[str, str]:
        """一次索引下载器种子目录中的 ``.torrent`` 文件。

        qBittorrent 通常使用 ``<hash>.torrent``，Transmission 常见
        ``<name>.<hash>.torrent``。只扫描配置目录及其 ``.torrents`` 子目录，
        避免把误配成下载数据根目录时递归遍历整个媒体库。
        """
        if not source_root or not os.path.isabs(source_root) or not os.path.isdir(source_root):
            return {}

        candidate_dirs = [source_root, os.path.join(source_root, ".torrents")]
        indexed: Dict[str, str] = {}
        for directory in candidate_dirs:
            if not os.path.isdir(directory):
                continue
            try:
                entries = sorted(os.scandir(directory), key=lambda entry: os.path.normcase(entry.name))
            except OSError:
                continue
            for entry in entries:
                try:
                    if not entry.is_file() or not entry.name.lower().endswith(".torrent"):
                        continue
                except OSError:
                    continue
                match = _TORRENT_HASH_IN_FILENAME.search(entry.name)
                if match:
                    indexed.setdefault(match.group(1).lower(), entry.path)
        return indexed

    def _map_runtime_path(self, path: Optional[str]) -> Optional[str]:
        """把下载器内部路径转换为当前运行环境路径；映射失败时保留原路径。"""
        if not path:
            return None
        mapping = self.path_mapping_service
        if mapping is None:
            return path
        try:
            return mapping.internal_to_external(path)
        except Exception as exc:
            logger.debug("种子文件路径映射失败，保留原路径 path=%s error=%s", path, exc)
            return path

    def _resolve_reconcile_source(
        self,
        torrent: TorrentInfo,
        source_index: Dict[str, str],
    ) -> Optional[str]:
        """按数据库直达路径、映射路径和目录索引依次定位源种子文件。"""
        raw_path = str(torrent.torrent_file or "").strip()
        candidates = [raw_path, self._map_runtime_path(raw_path)]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return source_index.get(str(torrent.hash or "").lower())

    def _existing_project_backup(self, torrent: TorrentInfo) -> Optional[str]:
        """定位旧同步已复制但未写入备份表的项目内种子文件。"""
        from app.core.filename_utils import FilenameUtils

        backup_dir = self.file_backup_service.backup_dir
        if not backup_dir:
            return None
        filename = FilenameUtils.generate_backup_filename(
            cast(str, torrent.info_id), cast(str, torrent.name or torrent.hash)
        )
        candidate = FilenameUtils.safe_path_join(backup_dir, filename)
        return candidate if os.path.isfile(candidate) else None

    async def reconcile_missing_backups(
        self,
        downloader_id: str,
        torrent_save_path: Optional[str],
        batch_size: int = 200,
    ) -> Dict[str, Any]:
        """增量补齐信息同步后缺失的种子文件备份。

        备份表中任何同 hash 记录（包括用户逻辑删除的记录）都视为已处理，避免
        自动任务重新创建用户明确删除的备份。每轮只处理有限批次；文件复制在写锁
        外执行，最终数据库记录与 ``TorrentInfo.backup_file_path`` 在同一短事务提交。
        """
        normalized_id = str(downloader_id)
        limit = max(1, int(batch_size))
        active_filters = (
            TorrentInfo.downloader_id == normalized_id,
            TorrentInfo.dr == 0,
            TorrentInfo.deleted_at.is_(None),
            TorrentInfo.hash.isnot(None),
            func.length(TorrentInfo.hash) == 40,
            ~exists().where(func.lower(TorrentFileBackup.info_hash) == func.lower(TorrentInfo.hash)),
        )
        pending_result = await self.db.execute(select(func.count()).select_from(TorrentInfo).where(*active_filters))
        pending = int(pending_result.scalar_one() or 0)
        stats: Dict[str, Any] = {
            "status": "no_action" if pending == 0 else "pending",
            "pending": pending,
            "attempted": 0,
            "created": 0,
            "reused_existing_file": 0,
            "missing_source": 0,
            "batch_limited": pending > limit,
            "source_root": torrent_save_path or None,
            "skip_reason": None,
        }
        if pending == 0:
            return stats

        rows_result = await self.db.execute(
            select(TorrentInfo)
            .where(*active_filters)
            .order_by(TorrentInfo.added_date.desc(), TorrentInfo.create_time.desc())
            .limit(limit)
        )
        torrents = list(rows_result.scalars().all())
        stats["attempted"] = len(torrents)

        source_index = await asyncio.to_thread(self._index_torrent_sources, torrent_save_path)
        records: List[TorrentFileBackup] = []
        newly_copied_paths: List[str] = []
        now = datetime.utcnow()
        for torrent in torrents:
            backup_path = str(torrent.backup_file_path or "").strip()
            reused_existing = bool(backup_path and os.path.isfile(backup_path))
            if not reused_existing:
                backup_path = self._existing_project_backup(torrent) or ""
                reused_existing = bool(backup_path)

            if not backup_path:
                source_path = self._resolve_reconcile_source(torrent, source_index)
                if not source_path:
                    stats["missing_source"] += 1
                    continue
                copy_result = await asyncio.to_thread(
                    self.file_backup_service.backup_torrent_file_from_path,
                    info_id=cast(str, torrent.info_id),
                    torrent_name=cast(str, torrent.name or torrent.hash),
                    source_file_path=source_path,
                )
                if not copy_result.get("success"):
                    stats["missing_source"] += 1
                    continue
                backup_path = str(copy_result["backup_file_path"])
                newly_copied_paths.append(backup_path)
            else:
                stats["reused_existing_file"] += 1

            try:
                file_size = os.path.getsize(backup_path)
            except OSError:
                if backup_path in newly_copied_paths:
                    try:
                        os.remove(backup_path)
                    except OSError:
                        pass
                    newly_copied_paths.remove(backup_path)
                stats["missing_source"] += 1
                continue
            records.append(
                TorrentFileBackup(
                    info_hash=str(torrent.hash),
                    file_path=backup_path,
                    file_size=file_size,
                    task_name=cast(Optional[str], torrent.name),
                    uploader_id=None,
                    downloader_id=normalized_id,
                    upload_time=cast(datetime, torrent.added_date or torrent.create_time or now),
                    use_count=0,
                    is_deleted=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            torrent.backup_file_path = backup_path

        if not records:
            stats["status"] = "skipped"
            stats["skip_reason"] = (
                "torrent_save_path_unavailable"
                if not torrent_save_path or not os.path.isdir(torrent_save_path)
                else "torrent_source_not_found"
            )
            return stats

        try:
            async with admission_controller.db_write_scope():
                self.db.add_all(records)
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            for copied_path in newly_copied_paths:
                try:
                    os.remove(copied_path)
                except OSError:
                    pass
            raise

        stats["status"] = "success"
        stats["created"] = len(records)
        return stats

    async def aclose(self) -> None:
        """
        异步关闭自建数据库会话。

        仅当 db 由本实例自建时才关闭，避免关闭外部传入的共享会话。
        多次调用安全（幂等）。
        """
        if not self._owns_db or self._closed:
            return
        self._closed = True
        try:
            await self.db.close()
        except Exception as e:
            logger.warning(f"关闭 TorrentFileBackupManagerService 数据库会话失败: {e}", exc_info=True)

    async def backup_torrent_from_downloader(
        self,
        info_hash: str,
        torrent_name: str,
        downloader_type: str,
        downloader_id: str,
        save_path: Optional[str] = None,
        downloader_config: Optional[Dict[str, Any]] = None,
        task_name: Optional[str] = None,
        uploader_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        从下载器备份种子文件

        复用现有的TorrentFileBackupService.backup_torrent_file方法。

        Args:
            info_hash: 种子哈希值
            torrent_name: 种子名称
            downloader_type: 下载器类型（qbittorrent/transmission）
            downloader_id: 下载器ID
            save_path: 保存路径（Transmission需要）
            downloader_config: 下载器配置
            task_name: 任务名称（可选）
            uploader_id: 上传用户ID（可选）

        Returns:
            操作结果字典
            {
                "success": bool,
                "backup": Optional[TorrentFileBackup],
                "backup_file_path": str,
                "source_path": str,
                "error_message": Optional[str]
            }
        """
        result = {"success": False, "backup": None, "backup_file_path": "", "source_path": "", "error_message": None}

        try:
            # 生成info_id（用于文件名）
            info_id = info_hash

            # 准备下载器配置
            if downloader_config is None:
                downloader_config = {}

            # 调用现有的备份服务（在线程池中执行同步操作）
            backup_result = await asyncio.to_thread(
                self.file_backup_service.backup_torrent_file,
                info_id=info_id,
                torrent_hash=info_hash,
                torrent_name=torrent_name,
                downloader_type=downloader_type,
                save_path=save_path,
                downloader_config=downloader_config,
            )

            if not backup_result.get("success"):
                result["error_message"] = backup_result.get("error_message", "备份失败")
                return result

            # 创建数据库记录
            torrent_backup = await self.repository.create(
                info_hash=info_hash,
                file_path=backup_result["backup_file_path"],
                file_size=None,  # 稍后获取文件大小
                task_name=task_name,
                uploader_id=uploader_id,
                downloader_id=downloader_id,
                upload_time=datetime.now(),
            )

            if torrent_backup:
                # 获取文件大小
                try:
                    file_path = backup_result["backup_file_path"]
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        await self.repository.update_file_path(info_hash, file_path, file_size=file_size)
                        torrent_backup.file_size = file_size
                except Exception as e:
                    logger.warning(f"获取文件大小失败: {e}")

                result["success"] = True
                result["backup"] = torrent_backup
                result["backup_file_path"] = backup_result["backup_file_path"]
                result["source_path"] = backup_result["source_path"]
            else:
                result["error_message"] = "创建数据库记录失败"

        except ValueError as e:
            result["error_message"] = str(e)
            logger.warning(f"备份种子文件失败（参数错误）: {e}")
        except Exception as e:
            result["error_message"] = f"备份失败: {str(e)}"
            logger.error(f"备份种子文件异常: {e}")

        return result

    async def backup_torrent_from_path(
        self,
        info_hash: str,
        torrent_name: str,
        source_file_path: str,
        downloader_id: str,
        task_name: Optional[str] = None,
        uploader_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        从指定路径备份种子文件

        复用现有的TorrentFileBackupService.backup_torrent_file_from_path方法。

        Args:
            info_hash: 种子哈希值
            torrent_name: 种子名称
            source_file_path: 源文件路径
            downloader_id: 下载器ID
            task_name: 任务名称（可选）
            uploader_id: 上传用户ID（可选）

        Returns:
            操作结果字典
        """
        result = {
            "success": False,
            "backup": None,
            "backup_file_path": "",
            "source_path": source_file_path,
            "error_message": None,
        }

        try:
            # 生成info_id
            info_id = info_hash

            # 调用现有的备份服务（在线程池中执行同步操作）
            backup_result = await asyncio.to_thread(
                self.file_backup_service.backup_torrent_file_from_path,
                info_id=info_id,
                torrent_name=torrent_name,
                source_file_path=source_file_path,
            )

            if not backup_result.get("success"):
                result["error_message"] = backup_result.get("error_message", "备份失败")
                return result

            # 创建数据库记录
            torrent_backup = await self.repository.create(
                info_hash=info_hash,
                file_path=backup_result["backup_file_path"],
                file_size=None,  # 稍后获取文件大小
                task_name=task_name,
                uploader_id=uploader_id,
                downloader_id=downloader_id,
                upload_time=datetime.now(),
            )

            if torrent_backup:
                # 获取文件大小
                try:
                    file_path = backup_result["backup_file_path"]
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        await self.repository.update_file_path(info_hash, file_path, file_size=file_size)
                        torrent_backup.file_size = file_size
                except Exception as e:
                    logger.warning(f"获取文件大小失败: {e}")

                result["success"] = True
                result["backup"] = torrent_backup
                result["backup_file_path"] = backup_result["backup_file_path"]
            else:
                result["error_message"] = "创建数据库记录失败"

        except ValueError as e:
            result["error_message"] = str(e)
            logger.warning(f"从路径备份种子文件失败（参数错误）: {e}")
        except Exception as e:
            result["error_message"] = f"备份失败: {str(e)}"
            logger.error(f"从路径备份种子文件异常: {e}")

        return result

    async def get_backup_info(self, info_hash: str) -> Dict[str, Any]:
        """
        获取种子文件备份信息

        Args:
            info_hash: 种子哈希值

        Returns:
            操作结果字典
            {
                "success": bool,
                "backup": Optional[TorrentFileBackup],
                "error_message": Optional[str]
            }
        """
        result = {"success": False, "backup": None, "error_message": None}

        try:
            torrent_backup = await self.repository.get_by_info_hash(info_hash)
            if torrent_backup:
                result["success"] = True
                result["backup"] = torrent_backup
            else:
                result["error_message"] = "备份记录不存在"

        except Exception as e:
            result["error_message"] = f"查询失败: {str(e)}"
            logger.error(f"获取备份信息异常: {e}")

        return result

    async def list_backups(
        self, downloader_id: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> Dict[str, Any]:
        """
        列出种子文件备份

        Args:
            downloader_id: 下载器ID（可选，不指定则查询所有）
            page: 页码
            page_size: 每页大小

        Returns:
            操作结果字典
            {
                "success": bool,
                "total": int,
                "page": int,
                "pageSize": int,
                "list": List[TorrentFileBackup],
                "error_message": Optional[str]
            }
        """
        result = {"success": False, "total": 0, "page": page, "pageSize": page_size, "list": [], "error_message": None}

        try:
            skip = (page - 1) * page_size

            if downloader_id:
                # 统计总数
                total = await self.repository.count_by_downloader(downloader_id)
                # 查询列表
                backups = await self.repository.list_by_downloader(downloader_id, skip, page_size)
            else:
                # 统计总数
                total = await self.repository.count_all()
                # 查询列表
                backups = await self.repository.list_all(skip, page_size)

            result["success"] = True
            result["total"] = total
            result["list"] = backups

        except Exception as e:
            result["error_message"] = f"查询失败: {str(e)}"
            logger.error(f"列出备份文件异常: {e}")

        return result

    async def delete_backup(self, info_hash: str, delete_physical_file: bool = False) -> Dict[str, Any]:
        """
        删除种子文件备份

        Args:
            info_hash: 种子哈希值
            delete_physical_file: 是否删除物理文件

        Returns:
            操作结果字典
            {
                "success": bool,
                "deleted_file": bool,
                "error_message": Optional[str]
            }
        """
        result = {"success": False, "deleted_file": False, "error_message": None}

        try:
            # 获取备份记录
            torrent_backup = await self.repository.get_by_info_hash(info_hash)
            if not torrent_backup:
                result["error_message"] = "备份记录不存在"
                return result

            # 删除物理文件
            if delete_physical_file:
                try:
                    # 在线程池中执行同步删除操作
                    deleted = await asyncio.to_thread(
                        self.file_backup_service.delete_backup_file, torrent_backup.file_path
                    )
                    result["deleted_file"] = deleted
                except Exception as e:
                    logger.warning(f"删除物理文件失败: {e}")

            # 逻辑删除数据库记录
            success = await self.repository.soft_delete(info_hash)
            result["success"] = success

            if not success:
                result["error_message"] = "删除数据库记录失败"

        except Exception as e:
            result["error_message"] = f"删除失败: {str(e)}"
            logger.error(f"删除备份文件异常: {e}")

        return result

    async def batch_backup(self, backup_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量备份种子文件

        Args:
            backup_requests: 备份请求列表

        Returns:
            操作结果字典
            {
                "total": int,
                "success_count": int,
                "failed_count": int,
                "success_items": List[TorrentFileBackup],
                "failed_items": List[Dict]
            }
        """
        result = {
            "total": len(backup_requests),
            "success_count": 0,
            "failed_count": 0,
            "success_items": [],
            "failed_items": [],
        }

        for request in backup_requests:
            try:
                # 判断备份类型
                if request.get("source_file_path"):
                    # 从路径备份
                    backup_result = await self.backup_torrent_from_path(
                        info_hash=request["info_hash"],
                        torrent_name=request["torrent_name"],
                        source_file_path=request["source_file_path"],
                        downloader_id=request["downloader_id"],
                        task_name=request.get("task_name"),
                        uploader_id=request.get("uploader_id"),
                    )
                else:
                    # 从下载器备份
                    backup_result = await self.backup_torrent_from_downloader(
                        info_hash=request["info_hash"],
                        torrent_name=request["torrent_name"],
                        downloader_type=request["downloader_type"],
                        downloader_id=request["downloader_id"],
                        save_path=request.get("save_path"),
                        downloader_config=request.get("downloader_config"),
                        task_name=request.get("task_name"),
                        uploader_id=request.get("uploader_id"),
                    )

                if backup_result["success"]:
                    result["success_count"] += 1
                    result["success_items"].append(backup_result["backup"])
                else:
                    result["failed_count"] += 1
                    result["failed_items"].append(
                        {
                            "info_hash": request["info_hash"],
                            "error": backup_result.get("error_message", "Unknown error"),
                        }
                    )

            except Exception as e:
                result["failed_count"] += 1
                result["failed_items"].append({"info_hash": request.get("info_hash", "unknown"), "error": str(e)})

        return result

    async def validate_backup_file(self, info_hash: str) -> Dict[str, Any]:
        """
        验证种子文件完整性

        Args:
            info_hash: 种子哈希值

        Returns:
            验证结果字典
            {
                "success": bool,
                "is_valid": bool,
                "file_exists": bool,
                "file_size": Optional[int],
                "error_message": Optional[str]
            }
        """
        result = {"success": False, "is_valid": False, "file_exists": False, "file_size": None, "error_message": None}

        try:
            # 获取备份记录
            torrent_backup = await self.repository.get_by_info_hash(info_hash)
            if not torrent_backup:
                result["error_message"] = "备份记录不存在"
                return result

            file_path = torrent_backup.file_path

            # 检查文件是否存在
            if not os.path.exists(file_path):
                result["error_message"] = f"文件不存在: {file_path}"
                return result

            result["file_exists"] = True

            # 获取文件大小
            try:
                file_size = os.path.getsize(file_path)
                result["file_size"] = file_size
            except Exception as e:
                result["error_message"] = f"无法获取文件大小: {e}"
                return result

            # 验证文件大小
            if file_size == 0:
                result["error_message"] = "文件大小为0"
                return result

            # 验证文件可读
            try:
                with open(file_path, "rb") as f:
                    # 读取前100字节验证
                    f.read(100)
            except Exception as e:
                result["error_message"] = f"文件读取失败: {e}"
                return result

            result["success"] = True
            result["is_valid"] = True

        except Exception as e:
            result["error_message"] = f"验证失败: {str(e)}"
            logger.error(f"验证备份文件异常: {e}")

        return result

    async def increment_use_count(self, info_hash: str) -> bool:
        """
        增加种子文件使用次数

        Args:
            info_hash: 种子哈希值

        Returns:
            是否成功
        """
        try:
            return await self.repository.increment_use_count(info_hash)
        except Exception as e:
            logger.error(f"增加使用次数异常: {e}")
            return False
