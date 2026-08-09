# -*- coding: utf-8 -*-
"""
孤儿文件扫描器

扫描下载器磁盘路径，发现不在任何种子文件清单中的孤儿文件。

扫描算法：
1. 筛选有效种子 save_path，并通过对应下载器的显式映射转换为扫描根
2. 构建种子文件清单（实时调下载器 API 获取每个种子的文件列表）
3. 遍历扫描路径（rglob + inode 去重 + 排除模式）
4. 不在文件清单中的磁盘文件 → 孤儿文件

语义重做（v1.0.6+）：
- fail-closed：下载器清单或已选扫描根不完整时，整批扫描失败且不可清理
- 路径映射缺失：记录提醒并跳过该内部路径，不把它误当成 BtDeck 可访问路径
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
import logging
import os
import stat
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, update

from app.core.config import settings
from app.database import AsyncSessionLocal, SessionLocal
from app.models.orphan_file import OrphanFile, OrphanScanResult
from app.tasks.resource_guard import admission_controller
from app.downloader.models import BtDownloaders
from app.services.orphan_manifest import (
    ManifestBuildError,
    PathMappingWarning,
    ScanPathSelection,
    TorrentManifestBuilder,
    collect_scan_path_selection,
    normalize_path,
    resolve_external_path,
)

logger = logging.getLogger(__name__)


class OrphanScanIncompleteError(Exception):
    """扫描不完整异常（fail-closed 触发）。

    任一下载器清单或已选扫描根不完整时抛出，
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
        "confidence",
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
        confidence: str = "high",
    ):
        self.file_path = file_path
        self.file_size = file_size
        self.mtime = mtime
        self.mtime_ns = mtime_ns
        self.device_id = device_id
        self.inode = inode
        self.downloader_id = downloader_id
        # high: 在线下载器精筛判定的孤儿；low: 离线/降级下载器经目录粗筛兜底后的孤儿
        self.confidence = confidence


def _normalize_path(path: str) -> str:
    """规范化路径：normcase + normpath，消除尾斜杠/大小写/分隔符差异。"""
    return normalize_path(path)


class OrphanScanner:
    """孤儿文件扫描器

    用法：
        scanner = OrphanScanner(app=app)
        result = await scanner.scan(scan_type="manual", operator="admin")
    """

    def __init__(
        self,
        app: Any = None,
        lease_handle: Any = None,
        sync_session_factory: Any = None,
        async_session_factory: Any = None,
    ):
        self.app = app
        self.lease_handle = lease_handle
        # 生产默认使用全局工厂；测试可显式注入临时 session factory，避免触碰
        # config/app.db。工厂在实例创建时固定，便于行为测试和后台任务复用。
        self._sync_session_factory = sync_session_factory or SessionLocal
        self._async_session_factory = async_session_factory or AsyncSessionLocal
        # {normalized_external_save_path: {normalized_abs_file_path, ...}}  期望文件集合
        self._expected_files: Dict[str, Set[str]] = {}
        self._manifest_scan_paths: List[Tuple[str, Optional[str]]] = []
        self._scan_path_selection: Optional[ScanPathSelection] = None
        self._scan_warnings: List[PathMappingWarning] = []
        # inode 去重集合（跨平台 (st_dev, st_ino)）
        self._seen_inodes: Set[Tuple[int, int]] = set()
        # 种子文件（expected 命中）的 inode 集合：用于识别硬链接副本。
        # 用户用硬链接把种子文件整理到媒体库时，副本与种子文件共享同一存储块
        # （同 inode），不额外占用磁盘空间，不应判为孤儿。由 _walk_all_roots
        # 预收集，使硬链接识别与扫描顺序无关。
        self._seed_inodes: Set[Tuple[int, int]] = set()
        # 目录级粗筛白名单（离线降级兜底）：normalize_path 后的种子根目录集合
        self._directory_whitelist: Set[str] = set()
        # 精筛不可用、降级为目录粗筛的下载器集合（其范围孤儿标 low confidence）
        self._degraded_downloader_ids: Set[str] = set()

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
        self._manifest_scan_paths = []
        self._scan_path_selection = None
        self._scan_warnings = []
        self._seen_inodes = set()
        self._seed_inodes = set()
        self._directory_whitelist = set()
        self._degraded_downloader_ids = set()

        # 1. 创建扫描批次记录（status=running）
        await self._create_scan_record(scan_id, scan_time, scan_type, operator)

        try:
            # fail-closed：app.state.store 必须存在
            self._assert_store_available()

            # 2. 收集扫描路径（to_thread，同步 DB 读）
            scan_paths = await asyncio.to_thread(self._collect_scan_paths)
            logger.info(f"[孤儿扫描 {scan_id}] 收集到 {len(scan_paths)} 个扫描路径")

            # 3. 构建种子文件清单（call_downloader_api SYNC lane）
            await self._build_torrent_file_map()
            if self._scan_path_selection is not None:
                scan_paths = self._manifest_scan_paths
            skipped_path_count = len(self._scan_warnings)
            if skipped_path_count:
                logger.warning(
                    "[孤儿扫描 %s] %s 个路径因缺少有效映射已记录并跳过；" "任务继续处理其余路径",
                    scan_id,
                    skipped_path_count,
                )
            total_expected = sum(len(v) for v in self._expected_files.values())
            logger.info(f"[孤儿扫描 {scan_id}] 种子文件清单构建完成，共 {total_expected} 个期望文件")

            # 4. 遍历扫描路径（to_thread，文件系统遍历是同步阻塞操作）
            orphans = await asyncio.to_thread(self._walk_all_roots, scan_paths)
            total_orphan_size = sum(o.file_size for o in orphans)
            logger.info(f"[孤儿扫描 {scan_id}] 扫描完成，发现 {len(orphans)} 个孤儿文件")

            # 护栏：孤儿数超阈值时告警（不阻断落库，真实大批量孤儿仍照常入库可清理，
            # 仅提醒核查是否为异常量级，如路径映射失效导致的整目录误判）。
            orphan_count_warning = len(orphans) > settings.ORPHAN_SCAN_MAX_ORPHANS_WARNING
            if orphan_count_warning:
                logger.warning(
                    "[孤儿扫描 %s] 孤儿数 %d 超过护栏阈值 %d（可能是真实大批量数据，"
                    "也可能是路径映射失效导致的误判，请核查）",
                    scan_id,
                    len(orphans),
                    settings.ORPHAN_SCAN_MAX_ORPHANS_WARNING,
                )

            # 5. 明细分批落地、生命周期分批对账、completed 状态最后提交。
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
                scan_roots=[path for path, _ in scan_paths],
            )

            # 6. 通知（total_orphans > 0 时创建，失败不回滚成功扫描；护栏超阈值时附异常提示）
            await self._notify_scan_completed(scan_id, scan_type, len(orphans), total_orphan_size, orphan_count_warning)

            return {
                "scan_id": scan_id,
                "scan_time": scan_time.isoformat(),
                "scan_type": scan_type,
                "total_paths_scanned": len(scan_paths),
                "total_files_scanned": total_files_scanned,
                "total_orphans": len(orphans),
                "total_orphan_size": total_orphan_size,
                "total_paths_skipped": skipped_path_count,
                "degraded_downloader_ids": sorted(self._degraded_downloader_ids),
                "warnings": [warning.to_dict() for warning in self._scan_warnings],
                "orphan_count_warning": orphan_count_warning,
                "status": "completed",
            }

        except Exception as e:
            logger.error(f"[孤儿扫描 {scan_id}] 扫描失败: {e}", exc_info=True)
            await self._fail_scan(scan_id, str(e))
            return {
                "scan_id": scan_id,
                "status": "failed",
                "error": str(e),
                "total_paths_skipped": len(self._scan_warnings),
                "warnings": [warning.to_dict() for warning in self._scan_warnings],
            }

    def _assert_store_available(self) -> None:
        """fail-closed：app.state.store 必须存在且非 None。"""
        if not self.app or not hasattr(self.app.state, "store") or self.app.state.store is None:
            raise OrphanScanIncompleteError("app.state.store 未初始化，无法获取下载器清单")

    # ==================== 路径收集 ====================

    def _collect_scan_paths(self) -> List[Tuple[str, Optional[str]]]:
        """收集扫描路径（同步方法，由 to_thread 调用）。

        只选择启用、未删除种子所属的启用下载器；维护表中明确停用的路径
        也会被排除。内部路径必须命中显式映射，否则记录告警并跳过。

        Returns:
            [(external_path, downloader_id), ...] 去重后的列表（稳定排序）。
            scan_roots 现为多 owner（共享根），这里取 owners 的代表 id 用于
            孤儿归属标记；完整 owner 集合保留在 self._scan_path_selection。
        """
        selection = collect_scan_path_selection(self._sync_session_factory)
        self._scan_path_selection = selection
        self._scan_warnings = list(selection.warnings)
        return [(path, next(iter(owners)) if owners else None) for path, owners in selection.scan_roots]

    def _convert_to_external(self, internal_path: str, downloader: Optional[BtDownloaders]) -> Optional[str]:
        """严格转换内部路径；未命中显式映射时返回 None。"""
        return resolve_external_path(internal_path, downloader)

    # ==================== 种子文件清单构建 ====================

    async def _build_torrent_file_map(self) -> None:
        """构建种子文件清单（精筛 expected + 目录粗筛白名单 + 降级标记）。

        语义重做（v1.0.7+ 跨下载器共享目录修复 + per-seed 精筛）：
        - 精筛作用域 = 全部启用下载器（不再从去重后 scan_roots 推导，消除共享根
          first-writer-wins 导致其他下载器文件漏入 expected 的盲区）。
        - 在线下载器：逐种子拉文件级清单进 expected（per-seed 精筛）。单个种子
          缺映射/清单失败仅该种子降级，其目录进 directory_whitelist（粗筛保护），
          不再因个别种子故障整体降级拖垮其余可映射种子（回归 tr 缺映射 2164 个
          种子致 7792 个可映射种子文件被误判的 5.7 万孤儿）。
        - 离线/inventory 失败下载器：记入降级集合，其文件由 DB 种子目录
          （directory_whitelist）在 _walk_scan_root 做目录粗筛兜底，产出的孤儿
          标 low confidence。
        - 仍 fail-closed 的硬错误（store 未初始化、无启用配置等）由 build 抛出。
        """
        # 扫描路径全量语义：required_downloader_ids=None 遍历全部启用下载器。
        try:
            snapshot = await TorrentManifestBuilder(
                self.app.state.store,
                scan_path_selection=self._scan_path_selection,
                session_factory=self._sync_session_factory,
            ).build(
                required_downloader_ids=None,
            )
        except ManifestBuildError as exc:
            raise OrphanScanIncompleteError(str(exc)) from exc
        self._expected_files = {"__global__": set(snapshot.expected_paths)}
        # scan_roots 现为 (path, owners_set)；_walk_all_roots 需要扁平化为
        # (path, downloader_id) 用于孤儿归属标记（取 owners 的任一代表）。
        self._manifest_scan_paths = [
            (path, next(iter(owners)) if owners else None) for path, owners in snapshot.scan_roots
        ]
        self._scan_warnings = list(snapshot.warnings)
        self._directory_whitelist = set(snapshot.directory_whitelist)
        self._degraded_downloader_ids = set(snapshot.degraded_downloader_ids)
        self._scan_path_selection = ScanPathSelection(
            scan_roots=tuple(snapshot.scan_roots),
            warnings=snapshot.warnings,
        )

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
            raise OrphanScanIncompleteError(f"种子 {torrent_hash[:8]} 文件清单为空（下载器 {downloader_id}）")
        return file_list

    @staticmethod
    def _parse_torrent_files_result(downloader_type: str, result: Any) -> List[str]:
        """解析下载器 API 返回的文件列表（qB/TR 格式不同）。

        qBittorrent: client.torrents.files(hash) → [FileEntry(name=...), ...]
        Transmission: client.get_torrent(hash) → Torrent，其原始 files 字段
        通过 Torrent.get("files") / Torrent.fields 读取。
        """
        return TorrentManifestBuilder._extract_files(result)

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

        硬链接副本识别：开头预收集种子文件（expected）的 inode 到 _seed_inodes。
        用户用硬链接把种子文件整理到媒体库时，副本与种子文件共享同一存储块（同
        inode），不额外占用磁盘空间，不应判孤儿。预收集使该识别与扫描顺序无关
        （旧 inode 去重依赖顺序：副本先扫会被误判）。

        单根降级语义：单个扫描根不存在/非目录时记 warning 并跳过该根，继续扫其余根，
        不让整个扫描失败。扫描根来自 DB 的种子 save_path 映射，单文件种子/已删种子
        的 save_path 在磁盘上可能不是目录，这是正常运维现象（非配置错误），不应让
        一个异常路径瘫痪整个扫描。该根下文件不被扫到 = 保守地不会误判孤儿，安全。

        兜底 fail-closed：若全部扫描根都不存在（扫描范围完全失效），仍抛异常，避免
        基于"什么都没扫到"误判为"无孤儿"。
        """
        orphans: List[OrphanFileItem] = []
        exclude_patterns = self._parse_exclude_patterns()
        skipped_roots: List[str] = []

        # 预收集种子文件 inode（硬链接副本识别）：stat expected 文件路径（不遍历
        # 目录树），收集仍存在的种子文件 inode，供 _walk_scan_root 排除硬链接副本。
        self._collect_seed_file_inodes()

        for root_path, downloader_id in scan_paths:
            if not os.path.isdir(root_path):
                # 单根降级：记 warning 跳过，不 raise（可能是单文件种子/已删种子的
                # save_path 形态，磁盘上非目录）。
                logger.warning(
                    "[孤儿扫描] 扫描根不存在或非目录，跳过该根: %s (downloader=%s)",
                    root_path,
                    downloader_id,
                )
                skipped_roots.append(root_path)
                continue

            orphans.extend(self._walk_scan_root(root_path, downloader_id, exclude_patterns))

        # 兜底：所有扫描根都不存在 → 扫描范围完全失效，fail-closed 避免空扫描被
        # 误判为"无孤儿"。
        if scan_paths and len(skipped_roots) == len(scan_paths):
            raise OrphanScanIncompleteError(
                f"全部 {len(scan_paths)} 个扫描根均不存在或非目录，扫描范围完全失效: {skipped_roots[:3]}"
            )

        return orphans

    def _collect_seed_file_inodes(self) -> None:
        """预收集种子文件（expected 命中路径）的 inode，用于识别硬链接副本。

        直接 os.stat expected 文件路径（不遍历目录树），收集仍存在的种子文件 inode。
        硬链接副本与种子文件共享同一存储块（同 inode），不额外占用磁盘空间。旧
        inode 去重依赖扫描顺序——副本先扫时其 inode 首次出现、又不在 expected，
        被误判孤儿。预收集后，无论原文件/副本哪个先被扫描，硬链接副本都能被识别
        为非孤儿。
        """
        for values in self._expected_files.values():
            for exp_path in values:
                try:
                    st = os.stat(exp_path)
                except OSError:
                    # 种子文件已被移动/删除（expected 路径在磁盘上不存在）→ 无法
                    # 关联硬链接副本；此时副本是磁盘上唯一的该文件，按孤儿判定。
                    continue
                self._seed_inodes.add((st.st_dev, st.st_ino))

    def _walk_scan_root(
        self, root: str, downloader_id: Optional[str], exclude_patterns: List[str]
    ) -> List[OrphanFileItem]:
        """遍历单个扫描根目录。

        语义重做：
        - 规范化路径匹配（normcase+normpath 统一 key）
        - 路径逃逸保护（os.path.commonpath 校验文件在根目录下）
        - 隔离区排除（.btdeck_quarantine 不扫描）
        - 降级种子目录粗筛：文件不在 expected 时，无条件检查 directory_whitelist
          （只含降级种子目录）。文件落在任一降级种子目录下即保护（不判孤儿）——
          修复「降级下载器的文件被在线下载器共享扫描根扫到，因 owner 错位跳过
          粗筛」的跨下载器误判（tr 文件被 qb/tr_kpan 扫描根误判为 high 孤儿）。
          不在白名单的孤儿，confidence 由孤儿归属下载器是否降级决定（降级=low）。
        """
        orphans: List[OrphanFileItem] = []
        root_path = os.path.abspath(root)

        # 合并所有 save_path 的期望集合；父扫描根必须能看到子 save_path 的合法文件。
        expected: Set[str] = set()
        for values in self._expected_files.values():
            expected.update(values)

        quarantine_dir_name = getattr(settings, "ORPHAN_QUARANTINE_DIR_NAME", ".btdeck_quarantine")
        recycle_tag = getattr(settings, "ORPHAN_RECYCLE_BIN_TAG", ".pending_delete") or ""

        try:
            for file_path, stat_info in self._iter_regular_files(root, quarantine_dir_name):

                str_path = str(file_path)
                abs_path = os.path.abspath(str_path)
                normalized_abs = _normalize_path(abs_path)

                # 隔离区 + 回收站路径二次防御（_iter_regular_files 已剪枝目录，此处兜底
                # 历史残留/边界场景）：隔离区按路径分量精确匹配，回收站按路径子串匹配
                # （多文件目录名 TorrentName.pending_delete 是单分量，parts 精确匹配不命中）。
                if quarantine_dir_name in file_path.parts or (recycle_tag and recycle_tag in str_path):
                    continue

                # 排除模式匹配
                if self._matches_patterns(file_path.name, exclude_patterns):
                    continue

                # Level3 单文件改名形态（name.pending_delete.ext / README.pending_delete）：
                # 目录剪枝只拦目录，普通文件在此用 basename 子串判断排除，
                # 对齐 recycle_bin_service.py 的 ".pending_delete" in path 既有逻辑。
                if recycle_tag and recycle_tag in file_path.name:
                    continue

                # 硬链接副本识别：与种子文件共享同一存储块（同 inode）的文件不额外
                # 占用磁盘空间，不应判为孤儿。inode 已由 _walk_all_roots 第一遍
                # 预收集（expected 命中文件），故与扫描顺序无关——副本即使先于原文件
                # 被扫到也能正确排除（回归：用户用硬链接整理种子到媒体库的误判）。
                inode_key = (stat_info.st_dev, stat_info.st_ino)
                if inode_key and inode_key in self._seed_inodes:
                    continue
                # inode 去重（跨平台，独立文件）
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

                # 第一层（精筛）：文件级清单命中 → 非孤儿
                if normalized_abs in expected:
                    continue

                # 第二层（降级种子目录粗筛）：无条件检查。文件若落在任一降级种子目录
                # 下则保护（不判孤儿），避免误删——这正是跨下载器共享目录误判的关键防线。
                # 不再依赖「扫描根 owner 是否 degraded」：降级下载器（如 tr）的文件常被
                # 在线下载器（如 qb/tr_kpan）的共享扫描根扫到，孤儿归属 owner 与文件真正
                # 所属下载器不一致，旧判定会因 owner 在线而跳过粗筛、把降级种子文件误判
                # 为 high 孤儿。粗筛白名单只含降级种子目录，在线下载器真孤儿不误保护。
                if self._in_directory_whitelist(abs_path, normalized_abs):
                    continue
                # 不在降级种子目录 → 孤儿。confidence 由孤儿归属下载器（扫描根 owner）
                # 是否处于降级范围决定：降级下载器无文件级精筛，产物标 low 不可清理；
                # 在线下载器精筛已确认文件不在任何种子清单中，标 high 可清理。
                downloader_id_str = downloader_id if downloader_id else ""
                confidence = "low" if downloader_id_str in self._degraded_downloader_ids else "high"

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
                        confidence=confidence,
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
        """显式 scandir 递归；任何枚举/stat 异常都上抛，避免 pathlib 静默漏目录。

        目录级剪枝（不递归进入）：
        - 隔离区目录（excluded_dir_name，默认 .btdeck_quarantine）精确名匹配
        - Level3 回收站归档目录（TorrentName.pending_delete，endswith 回收站标记）
          回收站标记来自配置 ORPHAN_RECYCLE_BIN_TAG；endswith 覆盖多文件种子改名
          （TorrentName/ → TorrentName.pending_delete/），子文件原名不再被枚举为孤儿。
        """
        recycle_tag = getattr(settings, "ORPHAN_RECYCLE_BIN_TAG", ".pending_delete") or ""
        stack = [os.path.abspath(root)]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            stat_info = os.lstat(entry.path)
                        except OSError as exc:
                            raise OrphanScanIncompleteError(f"获取目录项信息失败 {entry.path}: {exc}") from exc
                        if stat.S_ISDIR(stat_info.st_mode):
                            # 隔离区精确名 + 回收站目录后缀名，命中任一则不递归
                            is_recycle_dir = bool(recycle_tag) and entry.name.endswith(recycle_tag)
                            if entry.name != excluded_dir_name and not is_recycle_dir:
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

    @staticmethod
    def _is_recycle_bin_path(basename: str) -> bool:
        """判断文件/目录名是否属于 Level3 回收站归档（含 .pending_delete 标记）。

        用子串判断（非 glob）覆盖两种 Level3 删除改名形态：
        - 多文件目录：TorrentName.pending_delete（endswith tag）
        - 单文件改名：name.pending_delete.ext 或 README.pending_delete（tag in basename）

        fnmatch 的 ``*.pending_delete`` 模式只匹配以 ``.pending_delete`` 结尾的字符串，
        无法覆盖上述两种形态（详见 recycle_bin_service.py 的 ".pending_delete" in path
        既有判定），故这里用子串判断而非 glob。tag 为空（用户显式清空配置）时返回 False。
        """
        tag = getattr(settings, "ORPHAN_RECYCLE_BIN_TAG", ".pending_delete") or ""
        return bool(tag) and tag in basename

    def _in_directory_whitelist(self, abs_path: str, normalized_abs: str) -> bool:
        """判断文件是否落在目录粗筛白名单任一种子根目录下（离线降级兜底）。

        用 os.path.commonpath 校验：文件的规范化路径若以某白名单目录为前缀
        （commonpath == 该目录）即视为命中。白名单目录按长度倒序匹配，命中即返回。
        """
        if not self._directory_whitelist:
            return False
        for dir_path in self._directory_whitelist:
            try:
                if os.path.commonpath([dir_path, normalized_abs]) == dir_path:
                    return True
            except ValueError:
                # 跨驱动器（Windows）commonpath 抛 ValueError，直接跳过该目录
                continue
        return False

    # ==================== 生命周期对账 + 通知 ====================

    async def _reconcile_lifecycle(
        self,
        scan_id: str,
        scan_time: datetime,
        orphans: List[OrphanFileItem],
        scan_roots: Optional[List[str]] = None,
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
                "confidence": o.confidence,
            }
            for o in orphans
        ]
        if db is not None:
            await OrphanLifecycleService(db).reconcile_candidates(
                scan_id,
                scan_time,
                orphan_dicts,
                scan_roots=scan_roots,
                commit=False,
            )
        else:
            async with self._async_session_factory() as db:
                await OrphanLifecycleService(db).reconcile_candidates(
                    scan_id,
                    scan_time,
                    orphan_dicts,
                    scan_roots=scan_roots,
                    batch_size=settings.ORPHAN_SCAN_COMMIT_BATCH_SIZE,
                )

    async def _notify_scan_completed(
        self,
        scan_id: str,
        scan_type: str,
        orphan_count: int,
        orphan_size: int,
        orphan_count_warning: bool = False,
    ) -> None:
        """扫描完成通知（total_orphans > 0 时创建，失败不回滚成功扫描）。"""
        try:
            from app.services.orphan_notification import notify_scan_completed

            async with self._async_session_factory() as db:
                await notify_scan_completed(
                    db=db,
                    scan_id=scan_id,
                    scan_type=scan_type,
                    orphan_count=orphan_count,
                    orphan_size=orphan_size,
                    orphan_count_warning=orphan_count_warning,
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
        scan_roots: Optional[List[str]] = None,
    ) -> None:
        """落库明细、候选生命周期和 completed 批次状态（分批提交）。

        不再单事务一次性 commit：12 万孤儿单次 commit 会独占 SQLite 写锁
        十余分钟（实测 8-09: 18:54:02→19:05:47 落库 11 分 45 秒），导致 API
        卡死。改为三步分批：
        1. OrphanFile 明细分批写入（每批独立 session + db_write_scope + commit）
        2. 候选对账分批（insert/update 按批 commit；resolved 依赖完整 seen_paths 最后统一）
        3. completed 状态最后单独 commit
        中途崩溃时扫描记录残留 running，由启动恢复标 failed（门禁语义不变）。
        """
        # 1. OrphanFile 明细分批写入（复用 _save_orphan_files 的分批模式）
        await self._save_orphan_files(scan_id, orphans)

        # 2. 候选生命周期对账（分批提交）
        await self._reconcile_lifecycle(
            scan_id,
            scan_time,
            orphans,
            scan_roots=scan_roots,
        )

        # 3. completed 状态最后单独提交
        async with self._async_session_factory() as db:
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
        async with self._async_session_factory() as db:
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

    async def _save_orphan_files(self, scan_id: str, orphans: List[OrphanFileItem]) -> None:
        """批量写入孤儿文件记录（db_write_scope 串行化 + 分批提交）

        只有完整成功的扫描才调用此方法（scan() 在无异常时才走到这里）。
        """
        if not orphans:
            return

        batch_size = settings.ORPHAN_SCAN_COMMIT_BATCH_SIZE
        async with self._async_session_factory() as db:
            for i in range(0, len(orphans), batch_size):
                batch = orphans[i : i + batch_size]
                records = [
                    OrphanFile(
                        scan_id=scan_id,
                        file_path=o.file_path,
                        file_size=o.file_size,
                        mtime=o.mtime,
                        downloader_id=o.downloader_id,
                        confidence=o.confidence,
                        canonical_path=_normalize_path(o.file_path),
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
        async with self._async_session_factory() as db:
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
        """标记批次为 failed，并清理本批次已提交的孤儿明细。

        落库改为分批后，中途失败时前几批 OrphanFile 明细可能已 commit；
        必须按 scan_id 删除，否则成为幽灵明细（failed 批次的孤儿记录残留，
        膨胀 orphan_file 表，且可能被 reconcile_stable_candidate_details 按
        last_seen_scan_id 误关联）。
        """
        async with self._async_session_factory() as db:
            await db.execute(
                update(OrphanScanResult)
                .where(OrphanScanResult.scan_id == scan_id)
                .values(status="failed", error_message=error_msg[:1000])
            )
            await db.execute(delete(OrphanFile).where(OrphanFile.scan_id == scan_id))
            async with admission_controller.db_write_scope():
                await db.commit()
