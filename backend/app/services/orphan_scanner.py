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


class OrphanScanIncompleteError(Exception):
    """扫描不完整异常（fail-closed 触发）。

    任一下载器清单/路径映射/扫描根不完整时抛出，
    由 scan() 外层 try/except 捕获并标记批次为 failed。
    """


class OrphanFileItem:
    """扫描发现的孤儿文件（内存中间结构，写入 DB 前使用）"""

    __slots__ = ("file_path", "file_size", "mtime", "downloader_id")

    def __init__(self, file_path: str, file_size: int, mtime: Optional[datetime], downloader_id: Optional[str]):
        self.file_path = file_path
        self.file_size = file_size
        self.mtime = mtime
        self.downloader_id = downloader_id


def _normalize_path(path: str) -> str:
    """规范化路径：normcase + normpath，消除尾斜杠/大小写/分隔符差异。"""
    return os.path.normcase(os.path.normpath(path))


class OrphanScanner:
    """孤儿文件扫描器

    用法：
        scanner = OrphanScanner(app=app)
        result = await scanner.scan(scan_type="manual", operator="admin")
    """

    def __init__(self, app: Any = None):
        self.app = app
        # {normalized_external_save_path: {normalized_abs_file_path, ...}}  期望文件集合
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

        # 扫描开始时清空实例状态（连续两次扫描不互相污染）
        self._expected_files = {}
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
                raise OrphanScanIncompleteError("未收集到任何扫描路径（无下载器清单或路径映射）")

            # 3. 构建种子文件清单（call_downloader_api SYNC lane）
            await self._build_torrent_file_map()
            total_expected = sum(len(v) for v in self._expected_files.values())
            logger.info(f"[孤儿扫描 {scan_id}] 种子文件清单构建完成，共 {total_expected} 个期望文件")

            # 4. 遍历扫描路径（to_thread，文件系统遍历是同步阻塞操作）
            orphans = await asyncio.to_thread(self._walk_all_roots, scan_paths)
            total_orphan_size = sum(o.file_size for o in orphans)
            logger.info(f"[孤儿扫描 {scan_id}] 扫描完成，发现 {len(orphans)} 个孤儿文件")

            # 5. 批量写入孤儿文件记录（db_write_scope 串行化）—— 只有完整成功后才保存
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

            # 7. 生命周期对账（只有完整成功扫描才推进候选状态）
            await self._reconcile_lifecycle(scan_id, scan_time, orphans)

            # 8. 通知（total_orphans > 0 时创建，失败不回滚成功扫描）
            await self._notify_scan_completed(scan_id, scan_type, len(orphans), total_orphan_size)

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
        if not self.app or not hasattr(self.app.state, "store") or self.app.state.store is None:
            raise OrphanScanIncompleteError("app.state.store 未初始化，无法获取下载器清单")

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
            path_set: Dict[str, Optional[str]] = {}  # {normalized_external_path: downloader_id}

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
                    path_set[_normalize_path(external_path)] = downloader_id

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
                        path_set[_normalize_path(ep)] = dl.downloader_id

            # 稳定排序（结果与输入顺序无关）
            return sorted([(path, did) for path, did in path_set.items()], key=lambda x: x[0])

        finally:
            db.close()

    def _convert_to_external(self, internal_path: str, downloader: Optional[BtDownloaders]) -> str:
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

    def _extract_external_paths_from_mapping(self, downloader: BtDownloaders) -> List[str]:
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
            logger.warning(f"解析 path_mapping JSON 失败 downloader={downloader.downloader_id}: {e}")
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
        # 已在 _assert_store_available 确认 store 存在
        cached_downloaders = await self.app.state.store.get_snapshot()
        if not cached_downloaders:
            raise OrphanScanIncompleteError("store.get_snapshot() 返回空，无可用下载器清单")

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

        # fail-closed：有种子记录但下载器清单不完整 → 失败
        if torrents_by_dl:
            missing_dl_ids = [did for did in torrents_by_dl if did not in dl_map]
            if missing_dl_ids:
                raise OrphanScanIncompleteError(f"以下下载器在 BtDownloaders 表中不存在但有种子记录: {missing_dl_ids}")

        # 对每个下载器，获取其所有种子的文件清单
        for downloader_id, torrent_list in torrents_by_dl.items():
            # 从缓存取客户端连接
            dl_vo = next((d for d in cached_downloaders if d.downloader_id == downloader_id), None)
            # fail-closed：下载器 VO 缺失 → 失败（不静默跳过）
            if not dl_vo:
                raise OrphanScanIncompleteError(f"下载器 {downloader_id} 在 store 快照中不存在")
            # fail-closed：缺 client → 失败
            client = getattr(dl_vo, "client", None)
            if not client:
                raise OrphanScanIncompleteError(f"下载器 {downloader_id} 无可用客户端连接")
            # fail-closed：fail_time > 0 → 失败
            fail_time = getattr(dl_vo, "fail_time", 0) or 0
            if fail_time > 0:
                raise OrphanScanIncompleteError(f"下载器 {downloader_id} 不可用（fail_time={fail_time}）")

            # 获取下载器配置和类型
            dl_config = dl_map.get(downloader_id)
            if not dl_config:
                raise OrphanScanIncompleteError(f"下载器 {downloader_id} 配置缺失")

            # 确定下载器类型（不强制走 DeleteAdapter，允许直接调共享客户端）
            downloader_type_str = self._resolve_downloader_type(dl_config)
            if downloader_type_str is None:
                raise OrphanScanIncompleteError(
                    f"下载器 {downloader_id} 类型未知（downloader_type={dl_config.downloader_type}）"
                )

            # fail-closed：逐种子获取文件清单，任一失败即整批失败
            for hash_val, save_path, name in torrent_list:
                file_list = await self._fetch_torrent_files(downloader_id, downloader_type_str, client, hash_val)
                # 每个种子独立转换 save_path（修复「同一下载器两个 save_path」bug）
                external_save_path = self._convert_to_external(save_path, dl_config)
                normalized_root = _normalize_path(external_save_path)

                if normalized_root not in self._expected_files:
                    self._expected_files[normalized_root] = set()

                # 拼接绝对路径并加入期望集合（规范化 key）
                for rel_path in file_list:
                    abs_path = os.path.abspath(os.path.join(external_save_path, rel_path))
                    self._expected_files[normalized_root].add(_normalize_path(abs_path))

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
        from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

        # 统一通过共享客户端获取文件清单（经 call_downloader_api 受 per-downloader 限流）
        # 使用 DownloadLane.SYNC（扫描是重型周期任务）
        if downloader_type == "qbittorrent":
            method = client.torrents.files
        else:  # transmission
            method = client.get_torrent

        try:
            result = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                method,
                args=(torrent_hash,),
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
            raise OrphanScanIncompleteError(f"种子 {torrent_hash[:8]} 文件清单为空（下载器 {downloader_id}）")
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
            # TR 返回 dict，含 files 列表
            if isinstance(result, dict):
                raw_files = result.get("files", [])
                return [f.get("name", "") for f in raw_files if f.get("name")]
            return []

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

    def _walk_all_roots(self, scan_paths: List[Tuple[str, Optional[str]]]) -> List[OrphanFileItem]:
        """遍历所有扫描根目录（同步方法，由 to_thread 调用）。

        fail-closed：扫描根不存在 → 抛 OrphanScanIncompleteError（不静默跳过返回空）。
        """
        orphans: List[OrphanFileItem] = []
        exclude_patterns = self._parse_exclude_patterns()

        for root_path, downloader_id in scan_paths:
            # fail-closed：扫描根必须存在且是目录
            if not os.path.isdir(root_path):
                raise OrphanScanIncompleteError(f"扫描根不存在或非目录: {root_path}")

            orphans.extend(self._walk_scan_root(root_path, downloader_id, exclude_patterns))

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
        normalized_root = _normalize_path(root_path)

        # 找到该路径对应的期望文件集合（规范化 key 匹配）
        expected = self._expected_files.get(normalized_root) or set()

        quarantine_dir_name = getattr(settings, "ORPHAN_QUARANTINE_DIR_NAME", ".btdeck_quarantine")

        try:
            for file_path in Path(root).rglob("*"):
                if not file_path.is_file():
                    continue

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
                inode_key = self._get_file_identifier(str_path)
                if inode_key:
                    if inode_key in self._seen_inodes:
                        continue
                    self._seen_inodes.add(inode_key)

                # 路径逃逸保护：文件必须在扫描根目录下
                try:
                    if os.path.commonpath([root_path, abs_path]) != root_path:
                        logger.warning(f"[孤儿扫描] 路径逃逸授权扫描根，跳过: {abs_path}")
                        continue
                except ValueError:
                    # 不同驱动器（Windows）commonpath 抛 ValueError
                    logger.warning(f"[孤儿扫描] 跨驱动器路径，跳过: {abs_path}")
                    continue

                # 检查是否在种子文件清单中（规范化 key 匹配）
                if normalized_abs in expected:
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

    # ==================== 生命周期对账 + 通知 ====================

    async def _reconcile_lifecycle(self, scan_id: str, scan_time: datetime, orphans: List[OrphanFileItem]) -> None:
        """生命周期对账：只有完整成功扫描才推进候选状态。

        将本次发现的孤儿转为候选 dict，调 OrphanLifecycleService.reconcile_candidates。
        failed 扫描不会走到这里（scan() 异常分支直接 _fail_scan）。
        """
        try:
            from app.services.orphan_lifecycle_service import OrphanLifecycleService

            orphan_dicts = [
                {
                    "canonical_path": _normalize_path(o.file_path),
                    "downloader_id": o.downloader_id or "",
                    "file_size": o.file_size,
                    "mtime_ns": int(o.mtime.timestamp() * 1e9) if o.mtime else None,
                }
                for o in orphans
            ]
            async with AsyncSessionLocal() as db:
                service = OrphanLifecycleService(db)
                await service.reconcile_candidates(scan_id, scan_time, orphan_dicts)
        except Exception as e:
            logger.warning(f"[孤儿扫描 {scan_id}] 生命周期对账失败（不影响扫描结果）: {e}", exc_info=True)

    async def _notify_scan_completed(self, scan_id: str, scan_type: str, orphan_count: int, orphan_size: int) -> None:
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
            logger.warning(f"[孤儿扫描 {scan_id}] 通知创建失败（不影响扫描结果）: {e}", exc_info=True)

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
