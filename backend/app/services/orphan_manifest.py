# -*- coding: utf-8 -*-
"""孤儿文件扫描/清理共用的实时下载器 manifest 构建器。"""

import asyncio
import logging
import os
import time
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
        expected_paths: 在线下载器可精筛种子的「文件级」精确白名单（per-seed 精筛）。
            单个种子缺映射/清单失败只让该种子降级，其余种子文件仍并入 expected。
        directory_whitelist: 「降级种子」目录级粗筛白名单（离线降级兜底）。
            只含精筛失败的种子目录（per-seed 缺映射/清单失败种子 + inventory 级
            失败下载器的 DB 种子目录），由 save_path + name 构造。精筛成功种子的
            目录不在白名单——其文件已被 expected 文件级覆盖，避免粗筛误保护在线
            下载器的真孤儿。
        scan_roots: 与 ScanPathSelection.scan_roots 同结构（多 owner）。
        downloader_ids: 「文件级判定可靠」的在线下载器集合（允许清理授权依据）。
            下载器有任一 per-seed 降级种子即退出此集合（其文件无法完整精筛，
            清理授权不可靠）。
        degraded_downloader_ids: 有降级种子的下载器集合（离线/inventory 失败/
            部分种子缺映射/清单失败），产出的孤儿标 low confidence 不可清理。
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
    """「降级种子」目录级粗筛白名单（离线降级兜底专用）。

    磁盘文件规范化路径若 commonpath 命中任一目录，即视为落在某个降级种子目录下，
    在下载器离线/映射缺失时保护其不被误判孤儿（无条件粗筛判定，不依赖扫描根 owner）。
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
    downloader_ids: Optional[Set[str]] = None,
) -> DirectoryWhitelist:
    """构建「降级下载器」种子的「目录级」粗筛白名单（离线降级兜底专用）。

    对指定下载器集合内每个有效种子的 save_path：
    1. 优先经 resolve_external_path 转 external_root；映射缺失时用原 save_path 兜底
       （离线下载器的文件物理上仍可能落在别的在线下载器扫描根子树下，需保护）。
    2. 保守加入两个候选目录，覆盖单文件/多文件两种种子形态：
       - external_root 本身（多文件种子的保存根；单文件种子的直接目录）
       - join(external_root, name)（多文件种子的种子子目录）
       多加入只会让更多文件被保护（不误删），符合粗筛「宁可放过」语义。

    Args:
        downloader_ids: 仅收集这些下载器的种子目录；None = 全部下载器。
            精筛成功下载器的种子目录不进白名单（其文件已被 expected 文件级覆盖），
            避免目录粗筛把在线下载器的真孤儿误保护。

    Returns:
        DirectoryWhitelist(dirs)：规范化目录路径集合。
    """
    candidates = _load_torrent_path_candidates(session_factory)
    dirs: Set[str] = set()
    for cand in candidates:
        if downloader_ids is not None and cand.downloader_id not in downloader_ids:
            continue
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

        精筛/降级语义（per-seed）：
        - 在线下载器（有 client + fail_time=0 + inventory 成功）：逐种子精筛，可映射且
          文件清单成功的种子文件并入 expected_paths（精筛）。
        - 单个种子缺映射/清单失败/清单为空：仅该种子降级，其目录进 directory_whitelist
          （粗筛保护），不影响其余种子——不再因个别种子故障整体降级（回归 tr 缺映射
          2164 个种子拖垮 7792 个可映射种子的误判）。
        - 离线/无 client/inventory 拉取失败：该下载器整体降级，其文件由 DB 种子目录
          （directory_whitelist）在扫描阶段做目录级粗筛兜底，产出的孤儿标 low confidence。
        - 仍 fail-closed 的硬错误（store 未初始化、无任何启用配置、required 含未知
          下载器、共享缓存含无配置下载器）：整批 raise。
        """
        build_started = time.monotonic()
        _required_log = {str(value) for value in (required_downloader_ids or set())}
        logger.info(
            "[孤儿清单] build 开始 required下载器=%d scope=%s",
            len(_required_log),
            "全量" if not _required_log else "收窄",
        )
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
        # inventory 级失败（离线/无 client/fail_time/inventory 拉取失败）的下载器：
        # 其文件完全没有文件级清单，只能靠 DB 种子目录粗筛兜底。
        inventory_failed_ids: Set[str] = set()
        # per-seed 降级（缺映射/文件清单失败/清单为空）的种子目录：粗筛白名单组成部分，
        # 用于保护这些种子不被共享目录在线下载器扫描根误判孤儿。
        degraded_seed_dirs: Set[str] = set()

        for config in scoped_configs:
            downloader_id = str(config.downloader_id)
            degraded = self._try_precise_filter(config, cached, expected, protected_ids)
            if degraded is not None:
                degraded_downloader_ids.add(downloader_id)
                inventory_failed_ids.add(downloader_id)
                logger.warning(
                    "[孤儿清单] 下载器 %s 精筛不可用，降级为目录粗筛: %s",
                    downloader_id,
                    degraded,
                )
                continue
            # 同步预检通过 → 异步拉取文件级清单（精筛）。per-seed 语义：单个种子
            # 缺映射/清单失败只让该种子降级（目录进 degraded_seed_dirs），其余种子
            # 仍精筛进 expected，不再因个别种子拖垮整个下载器。
            await self._build_precise_expected(
                config,
                cached,
                expected,
                protected_ids,
                degraded_downloader_ids,
                degraded_seed_dirs,
                inventory_failed_ids,
            )

        # 目录粗筛白名单（离线降级兜底）= per-seed 降级种子目录 ∪ inventory 级失败
        # 下载器的 DB 种子目录。精筛成功下载器的种子目录不进白名单（其文件已被
        # expected 文件级覆盖），避免目录粗筛把在线下载器的真孤儿误保护。
        if inventory_failed_ids:
            db_whitelist = await asyncio.to_thread(
                collect_torrent_directory_whitelist,
                self.session_factory,
                downloader_ids=inventory_failed_ids,
            )
        else:
            db_whitelist = DirectoryWhitelist()
        directory_whitelist = set(db_whitelist.dirs) | degraded_seed_dirs

        logger.info(
            "[孤儿清单] build 完成 耗时=%.2fs expected=%d 精筛覆盖下载器=%d 降级下载器=%d 白名单目录=%d",
            time.monotonic() - build_started,
            len(expected),
            len(protected_ids),
            len(degraded_downloader_ids),
            len(directory_whitelist),
        )
        return ManifestSnapshot(
            expected_paths=expected,
            scan_roots=[(path, frozenset(owners)) for path, owners in sorted(roots.items(), key=lambda item: item[0])],
            downloader_ids=protected_ids,
            directory_whitelist=directory_whitelist,
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
        degraded_seed_dirs: Set[str],
        inventory_failed_ids: Set[str],
    ) -> None:
        """对一个在线下载器拉取文件级清单并入 expected（per-seed 精筛）。

        同步预检已由 _try_precise_filter 完成；本方法继续执行异步 inventory 拉取。
        per-seed 语义：每个种子独立判定——
        - 映射成功 + 文件清单成功：文件并入 expected（精筛保护）。
        - 缺映射/文件清单失败/清单为空：仅该种子降级，其目录（save_path 兜底或
          external_root）加入 degraded_seed_dirs 由目录粗筛白名单保护，不影响其余种子。
        - inventory 拉取失败（下载器级）：整体降级，下载器记入 inventory_failed_ids，
          其文件由 DB 种子目录粗筛兜底。
        """
        downloader_id = str(config.downloader_id)
        vo = next(
            (item for item in cached if str(getattr(item, "downloader_id", "")) == downloader_id),
            None,
        )
        client = getattr(vo, "client", None) if vo is not None else None

        # 提前初始化，供下方 _seed_degrade 闭包以 nonlocal 引用（mypy 要求绑定在前）。
        seed_degraded = False

        def _degrade(reason: str) -> None:
            degraded_downloader_ids.add(downloader_id)
            logger.warning(
                "[孤儿清单] 下载器 %s 精筛不可用，降级为目录粗筛: %s",
                downloader_id,
                reason,
            )

        def _seed_degrade(directory: str, reason: str) -> None:
            """单个种子降级：目录加入粗筛白名单，下载器标记有降级种子。"""
            nonlocal seed_degraded
            seed_degraded = True
            if directory:
                degraded_seed_dirs.add(normalize_path(directory))
            degraded_downloader_ids.add(downloader_id)
            logger.warning(
                "[孤儿清单] 下载器 %s 种子降级为目录粗筛: %s",
                downloader_id,
                reason,
            )

        try:
            downloader_type = self._resolve_type(config)
            _inv_started = time.monotonic()
            inventory = await self._fetch_inventory(downloader_id, downloader_type, client)
            logger.info(
                "[孤儿清单] inventory 拉取 downloader=%s 耗时=%.2fs 种子数=%d",
                downloader_id,
                time.monotonic() - _inv_started,
                len(inventory),
            )
        except ManifestBuildError as exc:
            _degrade(f"inventory 拉取失败: {exc}")
            inventory_failed_ids.add(downloader_id)
            return

        # 本地缓冲：成功种子的文件清单并入 expected；任一种子降级则该下载器整体
        # 退出 downloader_ids（文件级判定不完整，清理授权不可靠）。
        local_expected: Set[str] = set()

        # 单遍遍历 inventory：解析身份 → 分类。得到「需远程拉取」清单，
        # 同时就地处理「缺 hash/save_path / 缺映射 / embedded 已有文件」这三类（不涉及并发）。
        pending_fetch: List[Tuple[str, str]] = []  # (torrent_hash, external_root)
        for torrent in inventory:
            torrent_hash, save_path, embedded_files = self._torrent_identity(downloader_type, torrent)
            if not torrent_hash or not save_path:
                seed_degraded = True
                degraded_downloader_ids.add(downloader_id)
                logger.warning(
                    "[孤儿清单] 下载器 %s 种子缺 hash/save_path，无法精筛: %s",
                    downloader_id,
                    torrent_hash,
                )
                continue
            external_root = resolve_external_path(save_path, config)
            if external_root is None:
                # 缺映射：用内部 save_path 兜底进粗筛白名单（与
                # collect_torrent_directory_whitelist 的映射缺失兜底一致）。
                _seed_degrade(save_path, f"种子 {torrent_hash[:8]} save_path={save_path} 缺映射")
                continue
            if embedded_files is not None:
                # Transmission 一次带回 files，无需远程拉取，直接汇合。
                self._merge_seed_files(torrent_hash, external_root, embedded_files, local_expected, _seed_degrade)
                continue
            # qBittorrent：需逐种子 _fetch_files（远程调用，原串行是超时主因）。
            pending_fetch.append((torrent_hash, external_root))

        # 对需远程拉取的种子有界并发 gather。
        # worker 只返回纯数据元组，绝不写共享状态（避免 asyncio 交错下的逻辑竞态）。
        # 注意：真实远程并发受 downloader_api_runtime 的 per-downloader Semaphore
        # （DOWNLOADER_IO_CONCURRENCY，默认 2）钳制，asyncio 层 Semaphore 仅作协程数量护栏，
        # 理论加速上限约 2x；大下载器（数千种子）仍可能较慢（治本需 manifest 缓存或异步化）。
        if pending_fetch:
            concurrency = max(1, min(len(pending_fetch), settings.ORPHAN_SCAN_BATCH_SIZE))
            semaphore = asyncio.Semaphore(concurrency)

            async def _fetch_one(t_hash: str, ext_root: str) -> Tuple[str, str, Optional[List[str]], Optional[str]]:
                async with semaphore:
                    try:
                        files = await self._fetch_files(downloader_id, downloader_type, client, t_hash)
                        return t_hash, ext_root, files, None
                    except ManifestBuildError as exc:
                        # 单种子失败降级为 reason（与原串行 _seed_degrade 语义一致）。
                        return t_hash, ext_root, None, f"种子 {t_hash[:8]} 文件清单拉取失败: {exc}"

            _gather_started = time.monotonic()
            results = await asyncio.gather(
                *[_fetch_one(h, root) for h, root in pending_fetch],
                return_exceptions=True,
            )
            logger.info(
                "[孤儿清单] 并发拉取 downloader=%s pending=%d 协程并发=%d 真实远程并发=%d 耗时=%.2fs",
                downloader_id,
                len(pending_fetch),
                concurrency,
                settings.DOWNLOADER_IO_CONCURRENCY,
                time.monotonic() - _gather_started,
            )
        else:
            results = []

        # 串行汇合 gather 结果（主协程串行写共享集合，语义与原串行实现一致）。
        for result in results:
            # return_exceptions=True：非预期异常（非 ManifestBuildError 的）归一为降级，避免拖垮整批。
            if isinstance(result, BaseException):
                seed_degraded = True
                degraded_downloader_ids.add(downloader_id)
                logger.warning("[孤儿清单] 下载器 %s 文件清单并发拉取异常: %s", downloader_id, result)
                continue
            t_hash, ext_root, files, degrade_reason = result
            if degrade_reason is not None:
                _seed_degrade(ext_root, degrade_reason)
                continue
            self._merge_seed_files(t_hash, ext_root, files, local_expected, _seed_degrade)

        expected.update(local_expected)
        # 仅当该下载器所有种子都成功精筛（无 per-seed 降级）时才记录为精筛覆盖
        # downloader_id：清理授权依赖此集合判断候选所属下载器文件级判定是否可靠。
        if not seed_degraded:
            protected_ids.add(downloader_id)

    def _merge_seed_files(
        self,
        torrent_hash: str,
        external_root: str,
        files: Optional[List[str]],
        local_expected: Set[str],
        seed_degrade_fn: Any,
    ) -> None:
        """汇合单个种子的文件清单到 local_expected（embedded 与拉取结果共用）。

        seed_degrade_fn 为调用方的 _seed_degrade 闭包，清单为空时触发单种子降级。
        """
        if not files:
            seed_degrade_fn(external_root, f"种子 {torrent_hash[:8]} 文件清单为空")
            return
        for rel_path in files:
            local_expected.add(normalize_path(os.path.join(external_root, rel_path)))

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
