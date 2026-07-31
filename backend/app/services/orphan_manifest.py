# -*- coding: utf-8 -*-
"""孤儿文件扫描/清理共用的实时下载器 manifest 构建器。"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from sqlalchemy import select

from app.core.config import settings
from app.database import SessionLocal
from app.downloader.models import BtDownloaders
from app.models.downloader_path_maintenance import DownloaderPathMaintenance
from app.models.setting_templates import DownloaderTypeEnum
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.torrents.models import TorrentInfo

_MISSING_FILES = object()
logger = logging.getLogger(__name__)


class ManifestBuildError(RuntimeError):
    """实时下载器清单不完整；调用方必须 fail-closed。"""


def normalize_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


@dataclass(frozen=True)
class PathMappingWarning:
    """运行时路径映射缺失告警；仅随任务结果返回，不新增持久化结构。"""

    downloader_id: str
    internal_path: str
    code: str = "path_mapping_not_found"

    @property
    def message(self) -> str:
        return (
            f"下载器 {self.downloader_id} 的内部路径 {self.internal_path} "
            "未找到 BtDeck 可访问的有效映射，已跳过；请在下载器设置中补全路径映射，"
            "本任务不会自动修复"
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "downloader_id": self.downloader_id,
            "internal_path": self.internal_path,
            "message": self.message,
        }


@dataclass(frozen=True)
class ScanPathSelection:
    """从数据库筛选并成功映射后的本次扫描范围。

    scan_roots 的每个元素为 (normalized_external_root, owners)：
    owners 是所有把某 save_path 映射到该 external 根的 downloader_id 集合。
    多个下载器共享同一物理目录时，owners 会保留全部，避免 first-writer-wins
    丢掉共享根的其他下载器（其文件本应进 expected 白名单）。
    """

    scan_roots: Tuple[Tuple[str, FrozenSet[str]], ...] = ()
    warnings: Tuple[PathMappingWarning, ...] = ()


@dataclass(frozen=True)
class ManifestSnapshot:
    """实时下载器清单快照。

    Attributes:
        expected_paths: 在线下载器种子的「文件级」精确白名单（精筛）。
        directory_whitelist: 全部有效种子「目录级」粗筛白名单（离线降级兜底）。
            由 save_path + name 构造，每个种子保守加入两个候选目录。
        scan_roots: 与 ScanPathSelection.scan_roots 同结构（多 owner）。
        downloader_ids: 本次成功拉到文件清单的在线下载器集合（精筛来源）。
        degraded_downloader_ids: 离线/映射缺失/清单拉取失败的下载器集合
            （其文件走粗筛降级判定，产出的孤儿标 low confidence）。
        warnings: 路径映射缺失告警。
    """

    expected_paths: Set[str]
    scan_roots: List[Tuple[str, FrozenSet[str]]]
    downloader_ids: Set[str]
    directory_whitelist: Set[str] = frozenset()  # type: ignore[assignment]
    degraded_downloader_ids: Set[str] = frozenset()  # type: ignore[assignment]
    warnings: Tuple[PathMappingWarning, ...] = ()


@dataclass(frozen=True)
class DirectoryWhitelist:
    """全部有效种子的「目录级」粗筛白名单（离线降级兜底专用）。

    磁盘文件规范化路径若 commonpath 命中任一目录，即视为落在某个种子目录下，
    在下载器离线/映射缺失时保护其不被误判孤儿。
    """

    dirs: Set[str] = frozenset()  # type: ignore[assignment]


def _normalize_internal_path(path: str) -> str:
    normalized = str(path).strip().replace("\\", "/")
    if normalized == "/":
        return normalized
    if len(normalized) == 3 and normalized[1] == ":" and normalized.endswith("/"):
        return normalized
    return normalized.rstrip("/")


def _mapping_prefix_matches(path: str, prefix: str) -> bool:
    normalized_path = _normalize_internal_path(path)
    normalized_prefix = _normalize_internal_path(prefix)
    if not normalized_path or not normalized_prefix:
        return False
    if normalized_prefix == "/":
        return normalized_path.startswith("/")
    if normalized_prefix.endswith("/"):
        return normalized_path.startswith(normalized_prefix)
    return normalized_path == normalized_prefix or normalized_path.startswith(normalized_prefix + "/")


def resolve_external_path(internal_path: str, config: Optional[BtDownloaders]) -> Optional[str]:
    """严格解析下载器内部路径；没有命中显式规则时返回 None。"""

    if not internal_path or config is None:
        return None
    try:
        service = config.path_mapping_service
        if service is None:
            return None

        # 仅把「带有效 external/target」的显式映射纳入前缀匹配初筛。
        # external 为空（如系统自动发现后未回填）的映射既不能真正转换路径，
        # 也会让 PathMappingService 未命中分支原样返回输入路径；若放它通过，
        # 下游会把下载器内部绝对路径误当成 BtDeck 可访问的扫描根。
        sources: List[str] = []
        get_mappings = getattr(service, "get_mappings", None)
        if callable(get_mappings):
            mappings = get_mappings() or []
            sources.extend(
                str(item.get("internal"))
                for item in mappings
                if isinstance(item, dict) and item.get("internal") and item.get("external")
            )

        get_rules = getattr(service, "get_rules", None)
        if callable(get_rules):
            rules = get_rules() or []
            sources.extend(
                str(item.get("source"))
                for item in rules
                if isinstance(item, dict) and item.get("source") and item.get("target")
            )

        if not any(_mapping_prefix_matches(internal_path, source) for source in sources):
            return None

        mapped = service.internal_to_external(internal_path)
        if not mapped or not os.path.isabs(mapped):
            return None
        return str(mapped)
    except Exception as exc:
        logger.warning(
            "[孤儿扫描] 路径映射解析失败 downloader=%s path=%s: %s",
            getattr(config, "downloader_id", ""),
            internal_path,
            exc,
        )
        return None


@dataclass(frozen=True)
class _TorrentPathCandidate:
    """单个有效种子的路径候选（collect 阶段共用）。

    一个 (downloader_id, normalized save_path) 维度对应一行；同一 save_path 下
    若有多个种子，name 会不同，directory whitelist 需要每个 name 都参与，因此
    候选以 (downloader_id, save_path, name) 为粒度，不在此处去重 name。
    """

    downloader_id: str
    save_path: str
    name: str
    config: BtDownloaders


def _load_torrent_path_candidates(
    session_factory: Any,
) -> List[_TorrentPathCandidate]:
    """加载有效种子的路径候选（扫描根选择与目录粗筛白名单共用）。

    筛选规则：
    - 种子未删除（dr=0）、启用、未软删除、save_path 非空
    - 所属下载器启用、未删除
    - 维护路径表（DownloaderPathMaintenance）中明确停用的 (downloader, path) 排除

    返回按 (downloader_id, save_path, name) 排序的候选列表，不去重 name。
    """
    db = session_factory()
    try:
        rows = db.execute(
            select(
                TorrentInfo.save_path,
                TorrentInfo.name,
                TorrentInfo.downloader_id,
                BtDownloaders,
            )
            .join(
                BtDownloaders,
                BtDownloaders.downloader_id == TorrentInfo.downloader_id,
            )
            .where(
                TorrentInfo.dr == 0,
                TorrentInfo.enabled.is_(True),
                TorrentInfo.deleted_at.is_(None),
                TorrentInfo.save_path.isnot(None),
                BtDownloaders.enabled.is_(True),
                BtDownloaders.dr == 0,
            )
        ).all()

        downloader_ids = {str(row[2]) for row in rows if row[2]}
        maintained_paths: Dict[Tuple[str, str], bool] = {}
        if downloader_ids:
            maintenance_rows = db.execute(
                select(
                    DownloaderPathMaintenance.downloader_id,
                    DownloaderPathMaintenance.path_value,
                    DownloaderPathMaintenance.is_enabled,
                ).where(DownloaderPathMaintenance.downloader_id.in_(downloader_ids))
            ).all()
            for downloader_id, path_value, is_enabled in maintenance_rows:
                if not path_value:
                    continue
                key = (
                    str(downloader_id),
                    _normalize_internal_path(str(path_value)),
                )
                maintained_paths[key] = maintained_paths.get(key, False) or bool(is_enabled)

        candidates: List[_TorrentPathCandidate] = []
        for save_path, name, downloader_id, config in rows:
            if not save_path or not downloader_id:
                continue
            dl_id = str(downloader_id)
            pair_key = (dl_id, _normalize_internal_path(str(save_path)))
            if pair_key in maintained_paths and not maintained_paths[pair_key]:
                logger.info(
                    "[孤儿扫描] 跳过已停用维护路径 downloader=%s path=%s",
                    dl_id,
                    save_path,
                )
                continue
            # 同一下载器同一 save_path 的候选只构造一次用于扫描根去重；
            # name 维度的展开由 directory whitelist 消费方按需处理。
            candidates.append(
                _TorrentPathCandidate(
                    downloader_id=dl_id,
                    save_path=str(save_path),
                    name=str(name or ""),
                    config=config,
                )
            )
        candidates.sort(key=lambda c: (c.downloader_id, c.save_path, c.name))
        return candidates
    finally:
        db.close()


def collect_scan_path_selection(
    session_factory: Any = SessionLocal,
) -> ScanPathSelection:
    """筛选有效 torrent_info 路径并转换成 BtDeck 可访问的扫描根。

    共享根保留所有 owner：多个下载器把各自 save_path 映射到同一 external 物理路径
    时，scan_roots 该根的 owners 集合含全部相关 downloader_id（不再 first-writer-wins）。
    映射缺失的 save_path 仍记录 PathMappingWarning 并不进扫描根（但其文件由
    collect_torrent_directory_whitelist 的目录粗筛在离线降级时兜底保护）。
    """
    candidates = _load_torrent_path_candidates(session_factory)

    # 同一 (downloader, save_path) 在扫描根去重维度只需一个代表（与历史行为一致）。
    dedup_pairs: Dict[Tuple[str, str], _TorrentPathCandidate] = {}
    for cand in candidates:
        key = (cand.downloader_id, _normalize_internal_path(cand.save_path))
        dedup_pairs.setdefault(key, cand)

    roots: Dict[str, Set[str]] = {}
    warnings: Dict[Tuple[str, str], PathMappingWarning] = {}
    for (_, _), cand in sorted(dedup_pairs.items(), key=lambda item: item[0]):
        external_path = resolve_external_path(cand.save_path, cand.config)
        if external_path is None:
            warning = PathMappingWarning(
                downloader_id=cand.downloader_id,
                internal_path=cand.save_path,
            )
            warnings[(cand.downloader_id, cand.save_path)] = warning
            logger.warning("[孤儿扫描][%s] %s", warning.code, warning.message)
            continue
        normalized_root = normalize_path(external_path)
        roots.setdefault(normalized_root, set()).add(cand.downloader_id)

    scan_roots: Tuple[Tuple[str, FrozenSet[str]], ...] = tuple(
        (path, frozenset(owners)) for path, owners in sorted(roots.items(), key=lambda item: item[0])
    )
    return ScanPathSelection(
        scan_roots=scan_roots,
        warnings=tuple(warnings[key] for key in sorted(warnings, key=lambda item: (item[0], item[1]))),
    )


def collect_torrent_directory_whitelist(
    session_factory: Any = SessionLocal,
) -> DirectoryWhitelist:
    """构建全部有效种子的「目录级」粗筛白名单（离线降级兜底专用）。

    对每个有效种子的 save_path：
    1. 优先经 resolve_external_path 转 external_root；映射缺失时用原 save_path 兜底
       （离线下载器的文件物理上仍可能落在别的在线下载器扫描根子树下，需保护）。
    2. 保守加入两个候选目录，覆盖单文件/多文件两种种子形态：
       - external_root 本身（多文件种子的保存根；单文件种子的直接目录）
       - join(external_root, name)（多文件种子的种子子目录）
       多加入只会让更多文件被保护（不误删），符合粗筛「宁可放过」语义。

    Returns:
        DirectoryWhitelist(dirs)：规范化目录路径集合。
    """
    candidates = _load_torrent_path_candidates(session_factory)
    dirs: Set[str] = set()
    for cand in candidates:
        external_root = resolve_external_path(cand.save_path, cand.config)
        if external_root is None:
            # 映射缺失兜底：用原 save_path 作为目录根，避免离线下载器文件被误判。
            external_root = cand.save_path
        if not external_root:
            continue
        normalized_root = normalize_path(external_root)
        dirs.add(normalized_root)
        if cand.name:
            seed_dir = normalize_path(os.path.join(external_root, cand.name))
            if seed_dir != normalized_root:
                dirs.add(seed_dir)
    return DirectoryWhitelist(dirs=dirs)


class TorrentManifestBuilder:
    """以下载器实时 inventory 为权威构建文件清单。"""

    def __init__(
        self,
        store: Any,
        scan_path_selection: Optional[ScanPathSelection] = None,
        session_factory: Any = SessionLocal,
    ):
        self.store = store
        self.scan_path_selection = scan_path_selection
        self.session_factory = session_factory

    async def build(self, required_downloader_ids: Optional[Set[str]] = None) -> ManifestSnapshot:
        """构建下载器文件清单（精筛）+ 目录粗筛白名单 + 离线降级标记。

        Args:
            required_downloader_ids: 清理路径复核时传入候选所属下载器集合，收窄
                精筛复核范围（A 的清理不受 B 离线影响）。None/空 = 扫描路径全量语义，
                遍历全部启用下载器。

        精筛/降级语义：
        - 在线下载器（有 client + fail_time=0 + inventory 成功）：拉文件级清单加入
          expected_paths（精筛）。
        - 离线/无 client/映射缺失/inventory 失败：不抛 ManifestBuildError，记入
          degraded_downloader_ids；其文件由 directory_whitelist 在扫描阶段做目录级
          粗筛兜底，产出的孤儿标 low confidence。
        - 仍 fail-closed 的硬错误（store 未初始化、无任何启用配置、required 含未知
          下载器、共享缓存含无配置下载器）：整批 raise。
        """
        if self.store is None or not hasattr(self.store, "get_snapshot"):
            raise ManifestBuildError("app.state.store 未初始化")
        cached = await self.store.get_snapshot()
        if not isinstance(cached, (list, tuple)):
            raise ManifestBuildError("store.get_snapshot() 未返回列表")

        configs = await asyncio.to_thread(self._load_configs)
        if not configs:
            raise ManifestBuildError("未找到启用且未删除的下载器配置")
        config_ids = {str(config.downloader_id) for config in configs}
        cached_ids = {str(getattr(item, "downloader_id", "")) for item in cached}
        required = {str(value) for value in (required_downloader_ids or set())}
        missing_required = required - config_ids
        if missing_required:
            raise ManifestBuildError(f"候选所属下载器未启用或不存在: {sorted(missing_required)}")
        # 作用域过滤：required 非空时只精筛复核这些下载器（清理路径）；required 为空
        # 时遍历全部启用下载器（扫描路径全量语义）。
        scoped_configs = [config for config in configs if not required or str(config.downloader_id) in required]
        unknown_cached = {value for value in cached_ids - config_ids if value}
        if unknown_cached:
            raise ManifestBuildError(f"共享缓存含无启用配置的下载器: {sorted(unknown_cached)}")
        expected: Set[str] = set()
        selection = self.scan_path_selection
        if selection is None:
            selection = await asyncio.to_thread(collect_scan_path_selection, self.session_factory)
        # selection.scan_roots 现为 (normalized_root, owners_set)；去重合并 owners。
        roots: Dict[str, Set[str]] = {}
        for root_path, owners in selection.scan_roots:
            roots.setdefault(root_path, set()).update(owners)
        warnings: Dict[Tuple[str, str], PathMappingWarning] = {
            (
                warning.downloader_id,
                _normalize_internal_path(warning.internal_path),
            ): warning
            for warning in selection.warnings
        }
        protected_ids: Set[str] = set()
        degraded_downloader_ids: Set[str] = set()

        for config in scoped_configs:
            downloader_id = str(config.downloader_id)
            degraded = self._try_precise_filter(config, cached, expected, protected_ids)
            if degraded is not None:
                degraded_downloader_ids.add(downloader_id)
                logger.warning(
                    "[孤儿清单] 下载器 %s 精筛不可用，降级为目录粗筛: %s",
                    downloader_id,
                    degraded,
                )
                continue
            # 同步预检通过 → 异步拉取文件级清单（精筛）。拉取过程中任一环节失败
            # 也会在该方法内把下载器记入 degraded_downloader_ids（不 raise）。
            await self._build_precise_expected(config, cached, expected, protected_ids, degraded_downloader_ids)

        # 目录粗筛白名单（离线降级兜底）：覆盖全部有效种子，不受下载器在线状态影响。
        directory_whitelist = await asyncio.to_thread(collect_torrent_directory_whitelist, self.session_factory)

        return ManifestSnapshot(
            expected_paths=expected,
            scan_roots=[(path, frozenset(owners)) for path, owners in sorted(roots.items(), key=lambda item: item[0])],
            downloader_ids=protected_ids,
            directory_whitelist=set(directory_whitelist.dirs),
            degraded_downloader_ids=degraded_downloader_ids,
            warnings=tuple(warnings[key] for key in sorted(warnings, key=lambda item: (item[0], item[1]))),
        )

    def _try_precise_filter(
        self,
        config: BtDownloaders,
        cached: Any,
        expected: Set[str],
        protected_ids: Set[str],
    ) -> Optional[str]:
        """同步预检下载器是否可精筛；不可精筛返回降级原因（不抛异常）。

        预检项（任一不满足即降级，返回原因字符串）：
        - 不在共享缓存 / 无 client / fail_time>0（离线）
        - inventory 拉取或文件清单解析失败

        本方法只做不涉及 await 的预检（缓存/client/fail_time）。涉及下载器 API 的
        inventory 拉取是异步的，由调用方在循环中处理；这里把可同步判定的离线条件
        提前短路，避免对已知离线的下载器发起无意义的 API 调用。

        Returns:
            None 表示通过同步预检（调用方继续异步 inventory）；非 None 字符串表示
            降级原因。
        """
        downloader_id = str(config.downloader_id)
        vo = next(
            (item for item in cached if str(getattr(item, "downloader_id", "")) == downloader_id),
            None,
        )
        if vo is None:
            return "不在共享缓存中"
        client = getattr(vo, "client", None)
        if client is None:
            return "无可用客户端"
        if (getattr(vo, "fail_time", 0) or 0) > 0:
            return "当前不可用（fail_time>0）"
        return None

    async def _build_precise_expected(
        self,
        config: BtDownloaders,
        cached: Any,
        expected: Set[str],
        protected_ids: Set[str],
        degraded_downloader_ids: Set[str],
    ) -> None:
        """对一个在线下载器拉取文件级清单并入 expected（精筛）。

        同步预检已由 _try_precise_filter 完成；本方法继续执行异步 inventory 拉取。
        采用「全部成功才合并」策略：先收集到本地缓冲集合，任一环节失败则整体降级
        （本地缓冲丢弃，不污染 expected），保证降级状态一致性——降级下载器的文件
        全部交由 directory_whitelist 兜底，不会出现「部分进 expected、部分降级」。
        """
        downloader_id = str(config.downloader_id)
        vo = next(
            (item for item in cached if str(getattr(item, "downloader_id", "")) == downloader_id),
            None,
        )
        client = getattr(vo, "client", None) if vo is not None else None

        def _degrade(reason: str) -> None:
            degraded_downloader_ids.add(downloader_id)
            logger.warning(
                "[孤儿清单] 下载器 %s 精筛不可用，降级为目录粗筛: %s",
                downloader_id,
                reason,
            )

        try:
            downloader_type = self._resolve_type(config)
            inventory = await self._fetch_inventory(downloader_id, downloader_type, client)
        except ManifestBuildError as exc:
            _degrade(f"inventory 拉取失败: {exc}")
            return

        # 本地缓冲：全部种子文件清单成功才合并到 expected，保证降级一致性。
        local_expected: Set[str] = set()
        for torrent in inventory:
            torrent_hash, save_path, embedded_files = self._torrent_identity(downloader_type, torrent)
            if not torrent_hash or not save_path:
                _degrade("返回缺少 hash/save_path 的种子")
                return
            external_root = resolve_external_path(save_path, config)
            if external_root is None:
                # 在线但 save_path 缺映射：整体降级（文件走目录粗筛兜底），不 fail-closed。
                _degrade(f"种子 {torrent_hash[:8]} save_path={save_path} 缺映射")
                return

            files = embedded_files
            if files is None:
                try:
                    files = await self._fetch_files(downloader_id, downloader_type, client, torrent_hash)
                except ManifestBuildError as exc:
                    _degrade(f"种子 {torrent_hash[:8]} 文件清单拉取失败: {exc}")
                    return
            if not files:
                _degrade(f"种子 {torrent_hash[:8]} 文件清单为空")
                return
            for rel_path in files:
                local_expected.add(normalize_path(os.path.join(external_root, rel_path)))
        # 全部种子成功 → 合并到全局 expected，标记该下载器为精筛覆盖。
        expected.update(local_expected)
        protected_ids.add(downloader_id)

    def _load_configs(self) -> List[BtDownloaders]:
        db = self.session_factory()
        try:
            return list(
                db.execute(select(BtDownloaders).where(BtDownloaders.enabled.is_(True), BtDownloaders.dr == 0))
                .scalars()
                .all()
            )
        finally:
            db.close()

    @staticmethod
    def _resolve_type(config: BtDownloaders) -> str:
        try:
            normalized = DownloaderTypeEnum.normalize(config.downloader_type)
        except Exception as exc:
            raise ManifestBuildError(f"未知下载器类型: {config.downloader_type}") from exc
        if normalized == DownloaderTypeEnum.QBITTORRENT:
            return "qbittorrent"
        if normalized == DownloaderTypeEnum.TRANSMISSION:
            return "transmission"
        raise ManifestBuildError(f"未知下载器类型: {config.downloader_type}")

    async def _fetch_inventory(self, downloader_id: str, downloader_type: str, client: Any) -> List[Any]:
        if downloader_type == "qbittorrent":
            method = getattr(client, "torrents_info", None) or getattr(getattr(client, "torrents", None), "info", None)
            kwargs = None
        else:
            method = getattr(client, "get_torrents", None)
            kwargs = {"arguments": ["hashString", "downloadDir", "name", "files"]}
        if method is None:
            raise ManifestBuildError(f"下载器 {downloader_id} 不支持实时 torrent inventory")
        try:
            result = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                method,
                kwargs=kwargs,
                timeout=settings.DOWNLOADER_API_TIMEOUT_SECONDS,
                operation="orphan_manifest_inventory",
            )
        except Exception as exc:
            raise ManifestBuildError(f"下载器 {downloader_id} inventory 获取失败: {exc}") from exc
        if result is None:
            raise ManifestBuildError(f"下载器 {downloader_id} inventory 返回 None")
        if isinstance(result, (str, bytes, bytearray, dict)):
            raise ManifestBuildError(f"下载器 {downloader_id} inventory 返回不可迭代对象: " f"{type(result).__name__}")
        try:
            return list(result)
        except TypeError as exc:
            raise ManifestBuildError(
                f"下载器 {downloader_id} inventory 返回不可迭代对象: " f"{type(result).__name__}"
            ) from exc

    async def _fetch_files(self, downloader_id: str, downloader_type: str, client: Any, torrent_hash: str) -> List[str]:
        if downloader_type == "qbittorrent":
            method = client.torrents.files
            args = (torrent_hash,)
            kwargs = None
        else:
            method = client.get_torrent
            args = (torrent_hash,)
            kwargs = {"arguments": ["files"]}
        try:
            result = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                method,
                args=args,
                kwargs=kwargs,
                timeout=settings.DOWNLOADER_API_TIMEOUT_SECONDS,
                operation=f"orphan_manifest_files_{torrent_hash[:8]}",
            )
        except Exception as exc:
            raise ManifestBuildError(f"种子 {torrent_hash[:8]} 文件清单获取失败: {exc}") from exc
        try:
            return self._extract_files(result)
        except ManifestBuildError as exc:
            raise ManifestBuildError(f"种子 {torrent_hash[:8]} 文件清单解析失败: {exc}") from exc

    @staticmethod
    def _raw_files(value: Any) -> Any:
        """读取不同客户端对象中携带的原始 files 字段。

        transmission-rpc 7.x 的 Torrent 不暴露 ``.files`` 属性；RPC 原始
        字段保存在 Container.fields 中，并通过 ``get("files")`` 读取。
        旧客户端/测试替身可能仍以 ``.files`` 属性或方法暴露该字段。
        """
        if isinstance(value, dict):
            return value["files"] if "files" in value else _MISSING_FILES

        getter = getattr(value, "get", None)
        if callable(getter):
            try:
                raw = getter("files", _MISSING_FILES)
            except TypeError:
                try:
                    raw = getter("files")
                except (AttributeError, KeyError):
                    raw = _MISSING_FILES
            except (AttributeError, KeyError):
                raw = _MISSING_FILES
            if raw is not _MISSING_FILES:
                return raw

        fields = getattr(value, "fields", None)
        if isinstance(fields, dict) and "files" in fields:
            return fields["files"]

        return getattr(value, "files", _MISSING_FILES)

    @classmethod
    def _extract_files(cls, value: Any) -> List[str]:
        raw = cls._raw_files(value)
        if raw is _MISSING_FILES:
            raw = value
        if callable(raw):
            raw = raw()
        if raw is None:
            return []
        if isinstance(raw, (str, bytes, bytearray)):
            raise ManifestBuildError(f"文件清单返回不可迭代对象: {type(raw).__name__}")
        if isinstance(raw, dict):
            items = raw.values()
        else:
            try:
                items = iter(raw)
            except TypeError as exc:
                raise ManifestBuildError(f"文件清单返回不可迭代对象: {type(raw).__name__}") from exc
        result: List[str] = []
        for item in items:
            name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            if name:
                result.append(str(name))
        return result

    @classmethod
    def _torrent_identity(cls, downloader_type: str, torrent: Any) -> Tuple[str, str, Optional[List[str]]]:
        if isinstance(torrent, dict):
            torrent_hash = torrent.get("hash") or torrent.get("hashString")
            save_path = torrent.get("save_path") or torrent.get("downloadDir") or torrent.get("download_dir")
        else:
            torrent_hash = getattr(torrent, "hash", None) or getattr(torrent, "hashString", None)
            save_path = (
                getattr(torrent, "save_path", None)
                or getattr(torrent, "download_dir", None)
                or getattr(torrent, "downloadDir", None)
            )
        raw_files = cls._raw_files(torrent)
        files = cls._extract_files(raw_files) if raw_files is not _MISSING_FILES else None
        return str(torrent_hash or ""), str(save_path or ""), files
