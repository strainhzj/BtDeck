# -*- coding: utf-8 -*-
"""
孤儿文件扫描器

扫描下载器磁盘路径，发现不在任何种子文件清单中的孤儿文件。

扫描算法：
1. 收集扫描路径（种子 save_path distinct + 下载器 path_mapping external）
2. 构建种子文件清单（实时调下载器 API 获取每个种子的文件列表）
3. 遍历扫描路径（rglob + inode 去重 + 排除模式）
4. 不在文件清单中的磁盘文件 → 孤儿文件

治理合规：
- 文件系统遍历（同步阻塞）经 to_thread 移出事件循环
- 下载器 API 调用经 call_downloader_api(INTERACTIVE lane) 受 per-downloader 限流
- DB commit 经 db_write_scope 串行化写者

@file: orphan_scanner.py
@time: 2026-07-10
"""

import asyncio
import fnmatch
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select, update

from app.core.config import settings
from app.database import AsyncSessionLocal, SessionLocal
from app.models.orphan_file import OrphanFile, OrphanScanResult
from app.tasks.resource_guard import admission_controller
from app.torrents.models import TorrentInfo
from app.downloader.models import BtDownloaders

logger = logging.getLogger(__name__)


class OrphanFileItem:
    """扫描发现的孤儿文件（内存中间结构，写入 DB 前使用）"""

    __slots__ = ("file_path", "file_size", "mtime", "downloader_id")

    def __init__(self, file_path: str, file_size: int, mtime: Optional[datetime], downloader_id: Optional[str]):
        self.file_path = file_path
        self.file_size = file_size
        self.mtime = mtime
        self.downloader_id = downloader_id


class OrphanScanner:
    """孤儿文件扫描器

    用法：
        scanner = OrphanScanner(app=app)
        result = await scanner.scan(scan_type="manual", operator="admin")
    """

    def __init__(self, app: Any = None):
        self.app = app
        # {external_save_path: {abs_file_path, ...}}  期望文件集合（种子文件清单）
        self._expected_files: Dict[str, Set[str]] = {}
        # inode 去重集合（跨平台 (st_dev, st_ino)）
        self._seen_inodes: Set[Tuple[int, int]] = set()

    async def scan(self, scan_type: str = "manual", operator: Optional[str] = None) -> Dict[str, Any]:
        """主扫描入口（异步）。

        Args:
            scan_type: "manual" 或 "scheduled"
            operator: 触发者（用户名或 system）

        Returns:
            扫描结果摘要字典
        """
        scan_id = str(uuid.uuid4())
        scan_time = datetime.utcnow()

        # 1. 创建扫描批次记录（status=running）
        await self._create_scan_record(scan_id, scan_time, scan_type, operator)

        try:
            # 2. 收集扫描路径（to_thread，同步 DB 读）
            scan_paths = await asyncio.to_thread(self._collect_scan_paths)
            logger.info(f"[孤儿扫描 {scan_id}] 收集到 {len(scan_paths)} 个扫描路径")

            if not scan_paths:
                await self._complete_scan(scan_id, 0, 0, 0, 0)
                return {"scan_id": scan_id, "total_paths": 0, "total_orphans": 0, "message": "无扫描路径"}

            # 3. 构建种子文件清单（call_downloader_api INTERACTIVE lane）
            await self._build_torrent_file_map()
            total_expected = sum(len(v) for v in self._expected_files.values())
            logger.info(f"[孤儿扫描 {scan_id}] 种子文件清单构建完成，共 {total_expected} 个期望文件")

            # 4. 遍历扫描路径（to_thread，文件系统遍历是同步阻塞操作）
            orphans = await asyncio.to_thread(self._walk_all_roots, scan_paths)
            total_orphan_size = sum(o.file_size for o in orphans)
            logger.info(f"[孤儿扫描 {scan_id}] 扫描完成，发现 {len(orphans)} 个孤儿文件")

            # 5. 批量写入孤儿文件记录（db_write_scope 串行化）
            await self._save_orphan_files(scan_id, orphans)

            # 6. 更新批次状态为 completed
            total_files_scanned = total_expected + len(orphans)
            await self._complete_scan(
                scan_id,
                len(scan_paths),
                total_files_scanned,
                len(orphans),
                total_orphan_size,
            )

            return {
                "scan_id": scan_id,
                "scan_time": scan_time.isoformat(),
                "scan_type": scan_type,
                "total_paths_scanned": len(scan_paths),
                "total_files_scanned": total_files_scanned,
                "total_orphans": len(orphans),
                "total_orphan_size": total_orphan_size,
                "status": "completed",
            }

        except Exception as e:
            logger.error(f"[孤儿扫描 {scan_id}] 扫描失败: {e}", exc_info=True)
            await self._fail_scan(scan_id, str(e))
            return {"scan_id": scan_id, "status": "failed", "error": str(e)}

    # ==================== 路径收集 ====================

    def _collect_scan_paths(self) -> List[Tuple[str, Optional[str]]]:
        """收集扫描路径（同步方法，由 to_thread 调用）。

        来源：
        1. torrent_info.save_path distinct（dr=0 种子），经路径映射转外部路径
        2. BtDownloaders.path_mapping JSON 的 external 字段

        Returns:
            [(external_path, downloader_id), ...] 去重后的列表
        """
        db = SessionLocal()
        try:
            path_set: Dict[str, Optional[str]] = {}  # {external_path: downloader_id}

            # 来源 1: 种子 save_path
            torrents = db.execute(
                select(TorrentInfo.save_path, TorrentInfo.downloader_id)
                .where(TorrentInfo.dr == 0, TorrentInfo.save_path.isnot(None))
                .distinct()
            ).all()

            # 按下载器分组 save_path，用对应下载器的路径映射服务转换
            downloader_cache: Dict[str, Optional[BtDownloaders]] = {}

            for save_path, downloader_id in torrents:
                if not save_path:
                    continue
                # 获取下载器配置（缓存）
                if downloader_id not in downloader_cache:
                    dl = db.execute(
                        select(BtDownloaders).where(BtDownloaders.downloader_id == downloader_id)
                    ).scalar_one_or_none()
                    downloader_cache[downloader_id] = dl

                dl = downloader_cache.get(downloader_id)
                external_path = self._convert_to_external(save_path, dl)
                if external_path and os.path.isabs(external_path):
                    path_set[external_path] = downloader_id

            # 来源 2: 下载器 path_mapping JSON 的 external 字段
            downloaders = (
                db.execute(
                    select(BtDownloaders).where(BtDownloaders.enabled == True, BtDownloaders.dr == 0)  # noqa: E712
                )
                .scalars()
                .all()
            )

            for dl in downloaders:
                external_paths = self._extract_external_paths_from_mapping(dl)
                for ep in external_paths:
                    if ep and os.path.isabs(ep):
                        path_set[ep] = dl.downloader_id

            return [(path, did) for path, did in path_set.items()]

        finally:
            db.close()

    def _convert_to_external(self, internal_path: str, downloader: Optional[BtDownloaders]) -> str:
        """内部路径转外部路径（使用下载器的路径映射服务）"""
        if not internal_path:
            return internal_path
        if downloader:
            mapping_service = downloader.path_mapping_service
            if mapping_service:
                try:
                    return mapping_service.internal_to_external(internal_path)
                except Exception as e:
                    logger.warning(f"路径映射转换失败 {internal_path}: {e}")
        return internal_path

    def _extract_external_paths_from_mapping(self, downloader: BtDownloaders) -> List[str]:
        """从下载器 path_mapping JSON 解析 external 路径列表"""
        if not downloader.path_mapping:
            return []
        try:
            config = json.loads(downloader.path_mapping)
            mappings = config.get("mappings", [])
            return [m.get("external", "") for m in mappings if m.get("external")]
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"解析 path_mapping JSON 失败 downloader={downloader.downloader_id}: {e}")
            return []

    # ==================== 种子文件清单构建 ====================

    async def _build_torrent_file_map(self) -> None:
        """构建种子文件清单（expected_files 集合）。

        对每个下载器的每个种子调 get_torrent_files(hash) 获取相对路径列表，
        拼接绝对路径加入 expected_files 集合。
        """
        from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
        from app.services.torrent_deletion_service import DownloaderAdapterFactory
        from app.models.setting_templates import DownloaderTypeEnum

        if not self.app or not hasattr(self.app.state, "store"):
            logger.warning("[孤儿扫描] app.state.store 未初始化，跳过文件清单构建")
            return

        # 获取缓存的下载器列表
        cached_downloaders = await self.app.state.store.get_snapshot()
        if not cached_downloaders:
            logger.warning("[孤儿扫描] 无可用下载器缓存")
            return

        # 按下载器分组种子
        db = SessionLocal()
        try:
            # 构建 downloader_id → BtDownloaders 映射（用于路径转换）
            dl_map: Dict[str, Optional[BtDownloaders]] = {}
            all_downloaders = (
                db.execute(
                    select(BtDownloaders).where(BtDownloaders.enabled == True, BtDownloaders.dr == 0)  # noqa: E712
                )
                .scalars()
                .all()
            )
            for dl in all_downloaders:
                dl_map[dl.downloader_id] = dl

            # 查所有未删除种子（按 downloader_id 分组）
            torrents = db.execute(
                select(TorrentInfo.hash, TorrentInfo.save_path, TorrentInfo.downloader_id, TorrentInfo.name).where(
                    TorrentInfo.dr == 0
                )
            ).all()

            # 按 downloader_id 分组
            torrents_by_dl: Dict[str, List[Tuple[str, str, str]]] = {}
            for hash_val, save_path, downloader_id, name in torrents:
                if not hash_val or not save_path:
                    continue
                torrents_by_dl.setdefault(downloader_id, []).append((hash_val, save_path, name))

        finally:
            db.close()

        # 对每个下载器，获取其所有种子的文件清单
        for downloader_id, torrent_list in torrents_by_dl.items():
            # 从缓存取客户端连接
            dl_vo = next((d for d in cached_downloaders if d.downloader_id == downloader_id), None)
            if not dl_vo or not getattr(dl_vo, "client", None):
                logger.warning(f"[孤儿扫描] 下载器 {downloader_id} 无可用客户端连接，跳过")
                continue

            # 获取下载器配置和类型
            dl_config = dl_map.get(downloader_id)
            if not dl_config:
                continue

            try:
                normalized_type = DownloaderTypeEnum.normalize(dl_config.downloader_type)
                if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                    downloader_type_str = "qbittorrent"
                elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                    downloader_type_str = "transmission"
                else:
                    continue
            except Exception:
                continue

            client = dl_vo.client
            adapter = DownloaderAdapterFactory.create_adapter(downloader_type=downloader_type_str, client=client)

            # 转换 save_path 为外部路径
            external_save_path = self._convert_to_external(torrent_list[0][1], dl_config)

            if external_save_path not in self._expected_files:
                self._expected_files[external_save_path] = set()

            # 逐种子获取文件清单（经 call_downloader_api 受 per-downloader 限流）
            for hash_val, save_path, name in torrent_list:
                try:
                    success, file_list, err_msg = await call_downloader_api(
                        downloader_id,
                        DownloadLane.INTERACTIVE,
                        adapter.get_torrent_files,
                        args=(hash_val,),
                        timeout=settings.DOWNLOADER_API_TIMEOUT_SECONDS,
                        operation=f"get_torrent_files_{hash_val[:8]}",
                    )

                    if not success or not file_list:
                        logger.debug(f"[孤儿扫描] 获取文件清单失败 {hash_val[:8]}: {err_msg}")
                        continue

                    # 拼接绝对路径并加入期望集合
                    for rel_path in file_list:
                        abs_path = os.path.abspath(os.path.join(external_save_path, rel_path))
                        self._expected_files[external_save_path].add(abs_path)

                except Exception as e:
                    logger.warning(f"[孤儿扫描] 获取种子 {hash_val[:8]} 文件清单异常: {e}")
                    continue

    # ==================== 文件系统遍历 ====================

    def _walk_all_roots(self, scan_paths: List[Tuple[str, Optional[str]]]) -> List[OrphanFileItem]:
        """遍历所有扫描根目录（同步方法，由 to_thread 调用）。

        Args:
            scan_paths: [(external_path, downloader_id), ...]

        Returns:
            孤儿文件列表
        """
        orphans: List[OrphanFileItem] = []
        exclude_patterns = self._parse_exclude_patterns()

        for root_path, downloader_id in scan_paths:
            if not os.path.isdir(root_path):
                logger.debug(f"[孤儿扫描] 路径不存在或非目录: {root_path}")
                continue

            orphans.extend(self._walk_scan_root(root_path, downloader_id, exclude_patterns))

        return orphans

    def _walk_scan_root(
        self, root: str, downloader_id: Optional[str], exclude_patterns: List[str]
    ) -> List[OrphanFileItem]:
        """遍历单个扫描根目录。

        inode 去重 + 排除模式匹配 + 不在 expected_files 中 → 孤儿文件。
        """
        orphans: List[OrphanFileItem] = []
        root_path = os.path.abspath(root)

        # 找到该路径对应的期望文件集合
        expected = self._expected_files.get(root_path) or self._expected_files.get(root)
        if expected is None:
            # 尝试匹配（路径可能有尾部斜杠差异）
            for key, val in self._expected_files.items():
                if os.path.normpath(key) == os.path.normpath(root_path):
                    expected = val
                    break
        expected = expected or set()

        try:
            for file_path in Path(root).rglob("*"):
                if not file_path.is_file():
                    continue

                str_path = str(file_path)
                abs_path = os.path.abspath(str_path)

                # 排除模式匹配
                if self._matches_patterns(file_path.name, exclude_patterns):
                    continue

                # inode 去重（跨平台）
                inode_key = self._get_file_identifier(str_path)
                if inode_key:
                    if inode_key in self._seen_inodes:
                        continue
                    self._seen_inodes.add(inode_key)

                # 检查是否在种子文件清单中
                if abs_path in expected:
                    continue

                # 孤儿文件
                try:
                    stat_info = file_path.stat()
                    orphans.append(
                        OrphanFileItem(
                            file_path=abs_path,
                            file_size=stat_info.st_size,
                            mtime=datetime.fromtimestamp(stat_info.st_mtime),
                            downloader_id=downloader_id,
                        )
                    )
                except OSError as e:
                    logger.warning(f"[孤儿扫描] 获取文件信息失败 {abs_path}: {e}")

        except PermissionError as e:
            logger.warning(f"[孤儿扫描] 路径访问权限不足 {root}: {e}")
        except Exception as e:
            logger.error(f"[孤儿扫描] 遍历路径异常 {root}: {e}", exc_info=True)

        return orphans

    @staticmethod
    def _get_file_identifier(file_path: str) -> Optional[Tuple[int, int]]:
        """获取文件唯一标识符（跨平台 inode 去重）。

        Windows 和 Linux 均使用 (st_dev, st_ino)，用于识别硬链接重复。
        """
        try:
            stat_info = os.stat(file_path)
            return (stat_info.st_dev, stat_info.st_ino)
        except OSError:
            return None

    @staticmethod
    def _parse_exclude_patterns() -> List[str]:
        """解析排除模式配置（分号分隔）"""
        raw = settings.ORPHAN_EXCLUDE_PATTERNS
        return [p.strip() for p in raw.split(";") if p.strip()]

    @staticmethod
    def _matches_patterns(filename: str, patterns: List[str]) -> bool:
        """检查文件名是否匹配任一排除模式（fnmatch 语法）"""
        return any(fnmatch.fnmatch(filename, pat) for pat in patterns)

    # ==================== DB 操作 ====================

    async def _create_scan_record(
        self, scan_id: str, scan_time: datetime, scan_type: str, operator: Optional[str]
    ) -> None:
        """创建扫描批次记录（status=running）"""
        async with AsyncSessionLocal() as db:
            record = OrphanScanResult(
                scan_id=scan_id, scan_time=scan_time, scan_type=scan_type, operator=operator, status="running"
            )
            db.add(record)
            async with admission_controller.db_write_scope():
                await db.commit()

    async def _save_orphan_files(self, scan_id: str, orphans: List[OrphanFileItem]) -> None:
        """批量写入孤儿文件记录（db_write_scope 串行化 + 分批提交）"""
        if not orphans:
            return

        batch_size = settings.SYNC_DB_COMMIT_BATCH_SIZE
        async with AsyncSessionLocal() as db:
            for i in range(0, len(orphans), batch_size):
                batch = orphans[i : i + batch_size]
                records = [
                    OrphanFile(
                        scan_id=scan_id,
                        file_path=o.file_path,
                        file_size=o.file_size,
                        mtime=o.mtime,
                        downloader_id=o.downloader_id,
                    )
                    for o in batch
                ]
                db.add_all(records)
                async with admission_controller.db_write_scope():
                    await db.commit()

    async def _complete_scan(
        self,
        scan_id: str,
        total_paths: int,
        total_files: int,
        total_orphans: int,
        total_orphan_size: int,
    ) -> None:
        """更新批次状态为 completed"""
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(OrphanScanResult)
                .where(OrphanScanResult.scan_id == scan_id)
                .values(
                    total_paths_scanned=total_paths,
                    total_files_scanned=total_files,
                    total_orphans=total_orphans,
                    total_orphan_size=total_orphan_size,
                    status="completed",
                )
            )
            async with admission_controller.db_write_scope():
                await db.commit()

    async def _fail_scan(self, scan_id: str, error_msg: str) -> None:
        """更新批次状态为 failed"""
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(OrphanScanResult)
                .where(OrphanScanResult.scan_id == scan_id)
                .values(status="failed", error_message=error_msg[:1000])
            )
            async with admission_controller.db_write_scope():
                await db.commit()
