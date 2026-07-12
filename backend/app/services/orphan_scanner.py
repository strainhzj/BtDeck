# -*- coding: utf-8 -*-
"""
孤儿文件扫描器

扫描下载器磁盘路径，发现不在任何种子文件清单中的孤儿文件。

扫描算法：
1. 收集扫描路径（种子 save_path distinct + 下载器 path_mapping external）
2. 构建种子文件清单（实时调下载器 API 获取每个种子的文件列表）
3. 遍历扫描路径（rglob + inode 去重 + 排除模式）
4. 不在文件清单中的磁盘文件 → 孤儿文件

语义重做（v1.0.6+）：
- fail-closed：任一下载器清单、路径映射或扫描根不完整，整批扫描失败且不可清理
- 扫描开始时清空实例状态（连续两次扫描不互相污染）
- 使用 DownloadLane.SYNC 而非 INTERACTIVE（扫描是重型周期任务）
- 允许直接调用共享客户端（不强制走 DeleteAdapter）
- 每个种子独立转换 save_path（修复「同一下载器两个 save_path」bug）
- 使用规范化的全局 expected path 集合（normcase+normpath 统一 key）
- 扫描根规范化、稳定排序和安全归属（防路径逃逸）

治理合规：
- 文件系统遍历（同步阻塞）经 to_thread 移出事件循环
- 下载器 API 调用经 call_downloader_api(SYNC lane) 受 per-downloader 限流
- DB commit 经 db_write_scope 串行化写者

@file: orphan_scanner.py
@time: 2026-07-10
"""

import asyncio
import fnmatch
import json
import logging
import os
import stat
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
from app.services.orphan_manifest import (
    ManifestBuildError,
    TorrentManifestBuilder,
    normalize_path,
)

logger = logging.getLogger(__name__)


class OrphanScanIncompleteError(Exception):
    """扫描不完整异常（fail-closed 触发）。

    任一下载器清单/路径映射/扫描根不完整时抛出，
    由 scan() 外层 try/except 捕获并标记批次为 failed。
    """


class OrphanFileItem:
    """扫描发现的孤儿文件（内存中间结构，写入 DB 前使用）"""

    __slots__ = (
        "file_path",
        "file_size",
        "mtime",
        "mtime_ns",
        "device_id",
        "inode",
        "downloader_id",
    )

    def __init__(
        self,
        file_path: str,
        file_size: int,
        mtime: Optional[datetime],
        downloader_id: Optional[str],
        mtime_ns: Optional[int] = None,
        device_id: Optional[int] = None,
        inode: Optional[int] = None,
    ):
        self.file_path = file_path
        self.file_size = file_size
        self.mtime = mtime
        self.mtime_ns = mtime_ns
        self.device_id = device_id
        self.inode = inode
        self.downloader_id = downloader_id


def _normalize_path(path: str) -> str:
    """规范化路径：normcase + normpath，消除尾斜杠/大小写/分隔符差异。"""
    return normalize_path(path)


class OrphanScanner:
    """孤儿文件扫描器

    用法：
        scanner = OrphanScanner(app=app)
        result = await scanner.scan(scan_type="manual", operator="admin")
    """

    def __init__(self, app: Any = None, lease_handle: Any = None):
        self.app = app
        self.lease_handle = lease_handle
        # {normalized_external_save_path: {normalized_abs_file_path, ...}}  期望文件集合
        self._expected_files: Dict[str, Set[str]] = {}
        self._manifest_scan_paths: List[Tuple[str, Optional[str]]] = []
        # inode 去重集合（跨平台 (st_dev, st_ino)）
        self._seen_inodes: Set[Tuple[int, int]] = set()

    async def scan(
        self, scan_type: str = "manual", operator: Optional[str] = None
    ) -> Dict[str, Any]:
        """主扫描入口（异步）。

        Args:
            scan_type: "manual" 或 "scheduled"
            operator: 触发者（用户名或 system）

        Returns:
            扫描结果摘要字典
        """
        scan_id = str(uuid.uuid4())
        scan_time = datetime.utcnow()

        # 扫描开始时清空实例状态（连续两次扫描不互相污染）
        self._expected_files = {}
        self._manifest_scan_paths = []
        self._seen_inodes = set()

        # 1. 创建扫描批次记录（status=running）
        await self._create_scan_record(scan_id, scan_time, scan_type, operator)

        try:
            # fail-closed：app.state.store 必须存在
            self._assert_store_available()

            # 2. 收集扫描路径（to_thread，同步 DB 读）
            scan_paths = await asyncio.to_thread(self._collect_scan_paths)
            logger.info(f"[孤儿扫描 {scan_id}] 收集到 {len(scan_paths)} 个扫描路径")

            # fail-closed：无扫描路径不是「0 孤儿」，而是失败
            if not scan_paths:
                raise OrphanScanIncompleteError(
                    "未收集到任何扫描路径（无下载器清单或路径映射）"
                )

            # 3. 构建种子文件清单（call_downloader_api SYNC lane）
            await self._build_torrent_file_map()
            if self._manifest_scan_paths:
                scan_paths = self._manifest_scan_paths
            total_expected = sum(len(v) for v in self._expected_files.values())
            logger.info(
                f"[孤儿扫描 {scan_id}] 种子文件清单构建完成，共 {total_expected} 个期望文件"
            )

            # 4. 遍历扫描路径（to_thread，文件系统遍历是同步阻塞操作）
            orphans = await asyncio.to_thread(self._walk_all_roots, scan_paths)
            total_orphan_size = sum(o.file_size for o in orphans)
            logger.info(
                f"[孤儿扫描 {scan_id}] 扫描完成，发现 {len(orphans)} 个孤儿文件"
            )

            # 5. 明细、生命周期与 completed 状态在同一事务中落地。
            total_files_scanned = total_expected + len(orphans)
            if self.lease_handle is not None:
                await self.lease_handle.assert_owned()
            await self._finalize_successful_scan(
                scan_id,
                scan_time,
                orphans,
                len(scan_paths),
                total_files_scanned,
                len(orphans),
                total_orphan_size,
            )

            # 6. 通知（total_orphans > 0 时创建，失败不回滚成功扫描）
            await self._notify_scan_completed(
                scan_id, scan_type, len(orphans), total_orphan_size
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

    def _assert_store_available(self) -> None:
        """fail-closed：app.state.store 必须存在且非 None。"""
        if (
            not self.app
            or not hasattr(self.app.state, "store")
            or self.app.state.store is None
        ):
            raise OrphanScanIncompleteError(
                "app.state.store 未初始化，无法获取下载器清单"
            )

    # ==================== 路径收集 ====================

    def _collect_scan_paths(self) -> List[Tuple[str, Optional[str]]]:
        """收集扫描路径（同步方法，由 to_thread 调用）。

        fail-closed：路径映射转换异常时抛出（不静默跳过）。

        来源：
        1. torrent_info.save_path distinct（dr=0 种子），经路径映射转外部路径
        2. BtDownloaders.path_mapping JSON 的 external 字段

        Returns:
            [(external_path, downloader_id), ...] 去重后的列表（稳定排序）
        """
        db = SessionLocal()
        try:
            path_set: Dict[
                str, Optional[str]
            ] = {}  # {normalized_external_path: downloader_id}

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
                        select(BtDownloaders).where(
                            BtDownloaders.downloader_id == downloader_id
                        )
                    ).scalar_one_or_none()
                    downloader_cache[downloader_id] = dl

                dl = downloader_cache.get(downloader_id)
                external_path = self._convert_to_external(save_path, dl)
                if external_path and os.path.isabs(external_path):
                    path_set[_normalize_path(external_path)] = downloader_id

            # 来源 2: 下载器 path_mapping JSON 的 external 字段
            downloaders = (
                db.execute(
                    select(BtDownloaders).where(
                        BtDownloaders.enabled.is_(True), BtDownloaders.dr == 0
                    )
                )
                .scalars()
                .all()
            )

            for dl in downloaders:
                external_paths = self._extract_external_paths_from_mapping(dl)
                for ep in external_paths:
                    if ep and os.path.isabs(ep):
                        path_set[_normalize_path(ep)] = dl.downloader_id

            # 稳定排序（结果与输入顺序无关）
            return sorted(
                [(path, did) for path, did in path_set.items()], key=lambda x: x[0]
            )

        finally:
            db.close()

    def _convert_to_external(
        self, internal_path: str, downloader: Optional[BtDownloaders]
    ) -> str:
        """内部路径转外部路径（使用下载器的路径映射服务）。

        fail-closed：路径映射服务存在但转换抛异常时，向上抛出（不静默返回原路径）。
        """
        if not internal_path:
            return internal_path
        if downloader:
            mapping_service = downloader.path_mapping_service
            if mapping_service:
                # 不吞异常：转换失败应导致整批扫描失败（fail-closed）
                return mapping_service.internal_to_external(internal_path)
        return internal_path

    def _extract_external_paths_from_mapping(
        self, downloader: BtDownloaders
    ) -> List[str]:
        """从下载器 path_mapping JSON 解析 external 路径列表。

        注意：JSON 解析失败返回空列表（path_mapping 为空/无效是合法状态，不触发 fail-closed）。
        """
        if not downloader.path_mapping:
            return []
        try:
            config = json.loads(downloader.path_mapping)
            mappings = config.get("mappings", [])
            return [m.get("external", "") for m in mappings if m.get("external")]
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(
                f"解析 path_mapping JSON 失败 downloader={downloader.downloader_id}: {e}"
            )
            return []

    # ==================== 种子文件清单构建 ====================

    async def _build_torrent_file_map(self) -> None:
        """构建种子文件清单（expected_files 集合）。

        语义重做：
        - 使用 DownloadLane.SYNC（重型周期任务走 sync lane）
        - 不强制走 DownloaderDeleteAdapter：允许正确实现直接调用共享客户端
        - 每个种子独立转换 save_path（修复「同一下载器两个 save_path」bug）
        - 使用规范化的全局 expected path 集合（normcase+normpath）
        - fail-closed：任一种子清单获取失败 → 抛 OrphanScanIncompleteError（不 continue）
        - fail-closed：任一可用下载器缺 client / fail_time>0 → 抛异常（不静默跳过）
        """
        # 统一以下载器实时 inventory 为权威；DB 仅用于下载器配置和路径映射。
        try:
            snapshot = await TorrentManifestBuilder(self.app.state.store).build()
        except ManifestBuildError as exc:
            raise OrphanScanIncompleteError(str(exc)) from exc
        self._expected_files = {"__global__": set(snapshot.expected_paths)}
        self._manifest_scan_paths = [
            (path, downloader_id) for path, downloader_id in snapshot.scan_roots
        ]

    async def _fetch_torrent_files(
        self, downloader_id: str, downloader_type: str, client: Any, torrent_hash: str
    ) -> List[str]:
        """获取单个种子的文件相对路径列表。

        fail-closed：获取失败/超时/异常/返回空 → 抛 OrphanScanIncompleteError。
        允许直接调用共享客户端（不强制走 DeleteAdapter）。

        Args:
            downloader_id: 下载器 ID
            downloader_type: "qbittorrent" / "transmission"
            client: 共享客户端连接（从 store 缓存获取）
            torrent_hash: 种子哈希

        Returns:
            文件相对路径列表
        """
        from app.services.downloader_api_runtime import (
            DownloadLane,
            call_downloader_api,
        )

        # 统一通过共享客户端获取文件清单（经 call_downloader_api 受 per-downloader 限流）
        # 使用 DownloadLane.SYNC（扫描是重型周期任务）
        if downloader_type == "qbittorrent":
            method = client.torrents.files
            call_kwargs = None
        else:  # transmission
            method = client.get_torrent
            call_kwargs = {"arguments": ["files"]}

        try:
            result = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                method,
                args=(torrent_hash,),
                kwargs=call_kwargs,
                timeout=settings.DOWNLOADER_API_TIMEOUT_SECONDS,
                operation=f"get_torrent_files_{torrent_hash[:8]}",
            )
        except asyncio.TimeoutError as e:
            raise OrphanScanIncompleteError(
                f"获取种子 {torrent_hash[:8]} 文件清单超时（下载器 {downloader_id}）"
            ) from e
        except Exception as e:
            raise OrphanScanIncompleteError(
                f"获取种子 {torrent_hash[:8]} 文件清单异常（下载器 {downloader_id}）: {e}"
            ) from e

        # 解析返回（qB/TR 客户端返回格式不同）
        file_list = self._parse_torrent_files_result(downloader_type, result)
        if not file_list:
            raise OrphanScanIncompleteError(
                f"种子 {torrent_hash[:8]} 文件清单为空（下载器 {downloader_id}）"
            )
        return file_list

    @staticmethod
    def _parse_torrent_files_result(downloader_type: str, result: Any) -> List[str]:
        """解析下载器 API 返回的文件列表（qB/TR 格式不同）。

        qBittorrent: client.torrents.files(hash) → [FileEntry(name=...), ...]
        Transmission: client.get_torrent(hash) → {"files": [{"name": ...}, ...]}
        """
        if result is None:
            return []
        if downloader_type == "qbittorrent":
            # qB 返回文件对象列表，每个有 .name 属性
            files = []
            for f in result:
                name = getattr(f, "name", None)
                if name:
                    files.append(name)
            return files
        else:  # transmission
            # TR 返回 Torrent 对象（.files）或兼容 dict
            if isinstance(result, dict):
                raw_files = result.get("files", [])
                return [f.get("name", "") for f in raw_files if f.get("name")]
            raw_files = getattr(result, "files", [])
            if callable(raw_files):
                raw_files = raw_files()
            return [getattr(f, "name", "") for f in raw_files if getattr(f, "name", "")]

    @staticmethod
    def _resolve_downloader_type(dl_config: BtDownloaders) -> Optional[str]:
        """解析下载器类型字符串。

        Returns:
            "qbittorrent" / "transmission" / None（未知类型）
        """
        try:
            from app.models.setting_templates import DownloaderTypeEnum

            normalized_type = DownloaderTypeEnum.normalize(dl_config.downloader_type)
            if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                return "qbittorrent"
            elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                return "transmission"
        except Exception:
            pass
        return None

    # ==================== 文件系统遍历 ====================

    def _walk_all_roots(
        self, scan_paths: List[Tuple[str, Optional[str]]]
    ) -> List[OrphanFileItem]:
        """遍历所有扫描根目录（同步方法，由 to_thread 调用）。

        fail-closed：扫描根不存在 → 抛 OrphanScanIncompleteError（不静默跳过返回空）。
        """
        orphans: List[OrphanFileItem] = []
        exclude_patterns = self._parse_exclude_patterns()

        for root_path, downloader_id in scan_paths:
            # fail-closed：扫描根必须存在且是目录
            if not os.path.isdir(root_path):
                raise OrphanScanIncompleteError(f"扫描根不存在或非目录: {root_path}")

            orphans.extend(
                self._walk_scan_root(root_path, downloader_id, exclude_patterns)
            )

        return orphans

    def _walk_scan_root(
        self, root: str, downloader_id: Optional[str], exclude_patterns: List[str]
    ) -> List[OrphanFileItem]:
        """遍历单个扫描根目录。

        语义重做：
        - 规范化路径匹配（normcase+normpath 统一 key）
        - 路径逃逸保护（os.path.commonpath 校验文件在根目录下）
        - 隔离区排除（.btdeck_quarantine 不扫描）
        """
        orphans: List[OrphanFileItem] = []
        root_path = os.path.abspath(root)

        # 合并所有 save_path 的期望集合；父扫描根必须能看到子 save_path 的合法文件。
        expected: Set[str] = set()
        for values in self._expected_files.values():
            expected.update(values)

        quarantine_dir_name = getattr(
            settings, "ORPHAN_QUARANTINE_DIR_NAME", ".btdeck_quarantine"
        )

        try:
            for file_path, stat_info in self._iter_regular_files(root, quarantine_dir_name):

                str_path = str(file_path)
                abs_path = os.path.abspath(str_path)
                normalized_abs = _normalize_path(abs_path)

                # 隔离区排除（不在隔离区内的文件才扫描）
                if quarantine_dir_name in file_path.parts:
                    continue

                # 排除模式匹配
                if self._matches_patterns(file_path.name, exclude_patterns):
                    continue

                # inode 去重（跨平台）
                inode_key = (stat_info.st_dev, stat_info.st_ino)
                if inode_key:
                    if inode_key in self._seen_inodes:
                        continue
                    self._seen_inodes.add(inode_key)

                # 路径逃逸保护：文件必须在扫描根目录下
                try:
                    if os.path.commonpath([root_path, abs_path]) != root_path:
                        logger.warning(
                            f"[孤儿扫描] 路径逃逸授权扫描根，跳过: {abs_path}"
                        )
                        continue
                except ValueError:
                    # 不同驱动器（Windows）commonpath 抛 ValueError
                    logger.warning(f"[孤儿扫描] 跨驱动器路径，跳过: {abs_path}")
                    continue

                # 检查是否在种子文件清单中（规范化 key 匹配）
                if normalized_abs in expected:
                    continue

                # 孤儿文件
                orphans.append(
                    OrphanFileItem(
                        file_path=abs_path,
                        file_size=stat_info.st_size,
                        mtime=datetime.fromtimestamp(stat_info.st_mtime),
                        downloader_id=downloader_id,
                        mtime_ns=stat_info.st_mtime_ns,
                        device_id=stat_info.st_dev,
                        inode=stat_info.st_ino,
                    )
                )

        except PermissionError as e:
            raise OrphanScanIncompleteError(f"路径访问权限不足 {root}: {e}") from e
        except OrphanScanIncompleteError:
            raise
        except Exception as e:
            raise OrphanScanIncompleteError(f"遍历路径异常 {root}: {e}") from e

        return orphans

    @staticmethod
    def _iter_regular_files(root: str, excluded_dir_name: str):
        """显式 scandir 递归；任何枚举/stat 异常都上抛，避免 pathlib 静默漏目录。"""
        stack = [os.path.abspath(root)]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            stat_info = os.lstat(entry.path)
                        except OSError as exc:
                            raise OrphanScanIncompleteError(
                                f"获取目录项信息失败 {entry.path}: {exc}"
                            ) from exc
                        if stat.S_ISDIR(stat_info.st_mode):
                            if entry.name != excluded_dir_name:
                                stack.append(entry.path)
                            continue
                        if stat.S_ISREG(stat_info.st_mode):
                            yield Path(entry.path), stat_info
            except OrphanScanIncompleteError:
                raise
            except OSError as exc:
                raise OrphanScanIncompleteError(f"枚举目录失败 {current}: {exc}") from exc

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

    # ==================== 生命周期对账 + 通知 ====================

    async def _reconcile_lifecycle(
        self,
        scan_id: str,
        scan_time: datetime,
        orphans: List[OrphanFileItem],
        db: Any = None,
    ) -> None:
        """生命周期对账：只有完整成功扫描才推进候选状态。

        将本次发现的孤儿转为候选 dict，调 OrphanLifecycleService.reconcile_candidates。
        failed 扫描不会走到这里（scan() 异常分支直接 _fail_scan）。
        """
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        orphan_dicts = [
            {
                "canonical_path": _normalize_path(o.file_path),
                "downloader_id": o.downloader_id or "",
                "file_size": o.file_size,
                "mtime_ns": o.mtime_ns,
                "device_id": o.device_id,
                "inode": o.inode,
            }
            for o in orphans
        ]
        if db is not None:
            await OrphanLifecycleService(db).reconcile_candidates(
                scan_id, scan_time, orphan_dicts, commit=False
            )
        else:
            async with AsyncSessionLocal() as db:
                await OrphanLifecycleService(db).reconcile_candidates(
                    scan_id, scan_time, orphan_dicts
                )

    async def _notify_scan_completed(
        self, scan_id: str, scan_type: str, orphan_count: int, orphan_size: int
    ) -> None:
        """扫描完成通知（total_orphans > 0 时创建，失败不回滚成功扫描）。"""
        try:
            from app.services.orphan_notification import notify_scan_completed

            async with AsyncSessionLocal() as db:
                await notify_scan_completed(
                    db=db,
                    scan_id=scan_id,
                    scan_type=scan_type,
                    orphan_count=orphan_count,
                    orphan_size=orphan_size,
                )
        except Exception as e:
            logger.warning(
                f"[孤儿扫描 {scan_id}] 通知创建失败（不影响扫描结果）: {e}",
                exc_info=True,
            )

    # ==================== DB 操作 ====================

    async def _finalize_successful_scan(
        self,
        scan_id: str,
        scan_time: datetime,
        orphans: List[OrphanFileItem],
        total_paths: int,
        total_files: int,
        total_orphans: int,
        total_orphan_size: int,
    ) -> None:
        """原子写入明细、候选生命周期和 completed 批次状态。"""
        async with AsyncSessionLocal() as db:
            records = [
                OrphanFile(
                    scan_id=scan_id,
                    file_path=o.file_path,
                    file_size=o.file_size,
                    mtime=o.mtime,
                    downloader_id=o.downloader_id,
                )
                for o in orphans
            ]
            db.add_all(records)
            await self._reconcile_lifecycle(scan_id, scan_time, orphans, db=db)
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

    async def _create_scan_record(
        self, scan_id: str, scan_time: datetime, scan_type: str, operator: Optional[str]
    ) -> None:
        """创建扫描批次记录（status=running）"""
        async with AsyncSessionLocal() as db:
            record = OrphanScanResult(
                scan_id=scan_id,
                scan_time=scan_time,
                scan_type=scan_type,
                operator=operator,
                status="running",
            )
            db.add(record)
            async with admission_controller.db_write_scope():
                await db.commit()

    async def _save_orphan_files(
        self, scan_id: str, orphans: List[OrphanFileItem]
    ) -> None:
        """批量写入孤儿文件记录（db_write_scope 串行化 + 分批提交）

        只有完整成功的扫描才调用此方法（scan() 在无异常时才走到这里）。
        """
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
