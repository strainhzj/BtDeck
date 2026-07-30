# -*- coding: utf-8 -*-
"""孤儿文件扫描/清理共用的实时下载器 manifest 构建器。"""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

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
    """从数据库筛选并成功映射后的本次扫描范围。"""

    scan_roots: Tuple[Tuple[str, str], ...] = ()
    warnings: Tuple[PathMappingWarning, ...] = ()


@dataclass(frozen=True)
class ManifestSnapshot:
    expected_paths: Set[str]
    scan_roots: List[Tuple[str, str]]
    downloader_ids: Set[str]
    warnings: Tuple[PathMappingWarning, ...] = ()


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
    return normalized_path == normalized_prefix or normalized_path.startswith(
        normalized_prefix + "/"
    )


def resolve_external_path(
    internal_path: str, config: Optional[BtDownloaders]
) -> Optional[str]:
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
                if isinstance(item, dict)
                and item.get("internal")
                and item.get("external")
            )

        get_rules = getattr(service, "get_rules", None)
        if callable(get_rules):
            rules = get_rules() or []
            sources.extend(
                str(item.get("source"))
                for item in rules
                if isinstance(item, dict)
                and item.get("source")
                and item.get("target")
            )

        if not any(
            _mapping_prefix_matches(internal_path, source) for source in sources
        ):
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


def collect_scan_path_selection(
    session_factory: Any = SessionLocal,
) -> ScanPathSelection:
    """筛选有效 torrent_info 路径并转换成 BtDeck 可访问的扫描根。"""

    db = session_factory()
    try:
        rows = db.execute(
            select(
                TorrentInfo.save_path,
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
            .distinct()
        ).all()

        downloader_ids = {str(row[1]) for row in rows if row[1]}
        maintained_paths: Dict[Tuple[str, str], bool] = {}
        if downloader_ids:
            maintenance_rows = db.execute(
                select(
                    DownloaderPathMaintenance.downloader_id,
                    DownloaderPathMaintenance.path_value,
                    DownloaderPathMaintenance.is_enabled,
                ).where(
                    DownloaderPathMaintenance.downloader_id.in_(downloader_ids)
                )
            ).all()
            for downloader_id, path_value, is_enabled in maintenance_rows:
                if not path_value:
                    continue
                key = (
                    str(downloader_id),
                    _normalize_internal_path(str(path_value)),
                )
                maintained_paths[key] = maintained_paths.get(key, False) or bool(
                    is_enabled
                )

        candidates: Dict[Tuple[str, str], Tuple[str, BtDownloaders]] = {}
        for save_path, downloader_id, config in rows:
            if not save_path or not downloader_id:
                continue
            key = (
                str(downloader_id),
                _normalize_internal_path(str(save_path)),
            )
            if key in maintained_paths and not maintained_paths[key]:
                logger.info(
                    "[孤儿扫描] 跳过已停用维护路径 downloader=%s path=%s",
                    downloader_id,
                    save_path,
                )
                continue
            candidates[key] = (str(save_path), config)

        roots: Dict[str, str] = {}
        warnings: Dict[Tuple[str, str], PathMappingWarning] = {}
        for (downloader_id, _), (internal_path, config) in sorted(
            candidates.items(), key=lambda item: item[0]
        ):
            external_path = resolve_external_path(internal_path, config)
            if external_path is None:
                warning = PathMappingWarning(
                    downloader_id=downloader_id,
                    internal_path=internal_path,
                )
                warnings[(downloader_id, internal_path)] = warning
                logger.warning(
                    "[孤儿扫描][%s] %s", warning.code, warning.message
                )
                continue
            roots.setdefault(normalize_path(external_path), downloader_id)

        return ScanPathSelection(
            scan_roots=tuple(sorted(roots.items(), key=lambda item: item[0])),
            warnings=tuple(
                warnings[key]
                for key in sorted(warnings, key=lambda item: (item[0], item[1]))
            ),
        )
    finally:
        db.close()


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

    async def build(
        self, required_downloader_ids: Optional[Set[str]] = None
    ) -> ManifestSnapshot:
        """构建实时下载器文件清单。

        Args:
            required_downloader_ids: 作用域下载器集合。
                - 清理路径传入候选所属下载器：只遍历这些下载器的白名单，
                  A 的清理不受 B 配置缺失影响。
                - 扫描路径传入扫描根涉及的下载器：fail-closed 只作用于这些下载器。
                - None/空集合：遍历全部启用下载器（扫描全量语义）。

        fail-closed 语义：作用域内任一缺少有效路径映射的种子 save_path → 抛
        ManifestBuildError（整批失败），避免该种子文件被误判孤儿。作用域外下载器
        （如刚添加、路径未配映射且不落任何扫描根）不受影响，避免破坏性变更。
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
            raise ManifestBuildError(
                f"候选所属下载器未启用或不存在: {sorted(missing_required)}"
            )
        # 作用域过滤：required 非空时只遍历这些下载器（清理路径：只复核候选所属
        # 下载器的白名单，A 的清理不受 B 配置缺失影响）。required 为空（None 或空
        # 集合）时遍历全部启用下载器，保持扫描路径「扫全部」语义与既有行为不变。
        scoped_configs = [
            config
            for config in configs
            if not required or str(config.downloader_id) in required
        ]
        unknown_cached = {value for value in cached_ids - config_ids if value}
        if unknown_cached:
            raise ManifestBuildError(
                f"共享缓存含无启用配置的下载器: {sorted(unknown_cached)}"
            )
        expected: Set[str] = set()
        selection = self.scan_path_selection
        if selection is None:
            selection = await asyncio.to_thread(
                collect_scan_path_selection, self.session_factory
            )
        roots: Dict[str, str] = dict(selection.scan_roots)
        warnings: Dict[Tuple[str, str], PathMappingWarning] = {
            (
                warning.downloader_id,
                _normalize_internal_path(warning.internal_path),
            ): warning
            for warning in selection.warnings
        }
        protected_ids: Set[str] = set()

        for config in scoped_configs:
            downloader_id = str(config.downloader_id)
            vo = next(
                (
                    item
                    for item in cached
                    if str(getattr(item, "downloader_id", "")) == downloader_id
                ),
                None,
            )
            if vo is None:
                raise ManifestBuildError(f"下载器 {downloader_id} 不在共享缓存中")
            client = getattr(vo, "client", None)
            if client is None:
                raise ManifestBuildError(f"下载器 {downloader_id} 无可用客户端")
            if (getattr(vo, "fail_time", 0) or 0) > 0:
                raise ManifestBuildError(f"下载器 {downloader_id} 当前不可用")

            downloader_type = self._resolve_type(config)
            inventory = await self._fetch_inventory(
                downloader_id, downloader_type, client
            )
            protected_ids.add(downloader_id)

            for torrent in inventory:
                torrent_hash, save_path, embedded_files = self._torrent_identity(
                    downloader_type, torrent
                )
                if not torrent_hash or not save_path:
                    raise ManifestBuildError(
                        f"下载器 {downloader_id} 返回缺少 hash/save_path 的种子"
                    )
                external_root = resolve_external_path(save_path, config)
                if external_root is None:
                    # fail-closed：作用域内下载器的种子 save_path 缺映射时，其文件
                    # 不进白名单；若这些文件物理落在其它扫描根子树下会被误判孤儿。
                    # 作用域已由 required_downloader_ids 限定（清理路径只覆盖候选
                    # 所属下载器，扫描路径覆盖扫描根涉及的下载器），整批失败而非
                    # 静默跳过。错误消息含定位信息，引导用户补全 internal→external
                    # 映射后重试。
                    raise ManifestBuildError(
                        f"下载器 {downloader_id} 的种子 {torrent_hash[:8]} "
                        f"save_path={save_path} 未找到有效路径映射，"
                        "请在该下载器设置中补全 internal→external 映射后重试"
                    )

                files = embedded_files
                if files is None:
                    files = await self._fetch_files(
                        downloader_id, downloader_type, client, torrent_hash
                    )
                if not files:
                    raise ManifestBuildError(f"种子 {torrent_hash[:8]} 文件清单为空")
                for rel_path in files:
                    expected.add(normalize_path(os.path.join(external_root, rel_path)))

        return ManifestSnapshot(
            expected_paths=expected,
            scan_roots=sorted(roots.items(), key=lambda item: item[0]),
            downloader_ids=protected_ids,
            warnings=tuple(
                warnings[key]
                for key in sorted(warnings, key=lambda item: (item[0], item[1]))
            ),
        )

    def _load_configs(self) -> List[BtDownloaders]:
        db = self.session_factory()
        try:
            return list(
                db.execute(
                    select(BtDownloaders).where(
                        BtDownloaders.enabled.is_(True), BtDownloaders.dr == 0
                    )
                )
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
            raise ManifestBuildError(
                f"未知下载器类型: {config.downloader_type}"
            ) from exc
        if normalized == DownloaderTypeEnum.QBITTORRENT:
            return "qbittorrent"
        if normalized == DownloaderTypeEnum.TRANSMISSION:
            return "transmission"
        raise ManifestBuildError(f"未知下载器类型: {config.downloader_type}")

    async def _fetch_inventory(
        self, downloader_id: str, downloader_type: str, client: Any
    ) -> List[Any]:
        if downloader_type == "qbittorrent":
            method = getattr(client, "torrents_info", None) or getattr(
                getattr(client, "torrents", None), "info", None
            )
            kwargs = None
        else:
            method = getattr(client, "get_torrents", None)
            kwargs = {"arguments": ["hashString", "downloadDir", "name", "files"]}
        if method is None:
            raise ManifestBuildError(
                f"下载器 {downloader_id} 不支持实时 torrent inventory"
            )
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
            raise ManifestBuildError(
                f"下载器 {downloader_id} inventory 获取失败: {exc}"
            ) from exc
        if result is None:
            raise ManifestBuildError(f"下载器 {downloader_id} inventory 返回 None")
        if isinstance(result, (str, bytes, bytearray, dict)):
            raise ManifestBuildError(
                f"下载器 {downloader_id} inventory 返回不可迭代对象: "
                f"{type(result).__name__}"
            )
        try:
            return list(result)
        except TypeError as exc:
            raise ManifestBuildError(
                f"下载器 {downloader_id} inventory 返回不可迭代对象: "
                f"{type(result).__name__}"
            ) from exc

    async def _fetch_files(
        self, downloader_id: str, downloader_type: str, client: Any, torrent_hash: str
    ) -> List[str]:
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
            raise ManifestBuildError(
                f"种子 {torrent_hash[:8]} 文件清单获取失败: {exc}"
            ) from exc
        try:
            return self._extract_files(result)
        except ManifestBuildError as exc:
            raise ManifestBuildError(
                f"种子 {torrent_hash[:8]} 文件清单解析失败: {exc}"
            ) from exc

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
            raise ManifestBuildError(
                f"文件清单返回不可迭代对象: {type(raw).__name__}"
            )
        if isinstance(raw, dict):
            items = raw.values()
        else:
            try:
                items = iter(raw)
            except TypeError as exc:
                raise ManifestBuildError(
                    f"文件清单返回不可迭代对象: {type(raw).__name__}"
                ) from exc
        result: List[str] = []
        for item in items:
            name = (
                item.get("name")
                if isinstance(item, dict)
                else getattr(item, "name", None)
            )
            if name:
                result.append(str(name))
        return result

    @classmethod
    def _torrent_identity(
        cls, downloader_type: str, torrent: Any
    ) -> Tuple[str, str, Optional[List[str]]]:
        if isinstance(torrent, dict):
            torrent_hash = torrent.get("hash") or torrent.get("hashString")
            save_path = (
                torrent.get("save_path")
                or torrent.get("downloadDir")
                or torrent.get("download_dir")
            )
        else:
            torrent_hash = getattr(torrent, "hash", None) or getattr(
                torrent, "hashString", None
            )
            save_path = (
                getattr(torrent, "save_path", None)
                or getattr(torrent, "download_dir", None)
                or getattr(torrent, "downloadDir", None)
            )
        raw_files = cls._raw_files(torrent)
        files = (
            cls._extract_files(raw_files)
            if raw_files is not _MISSING_FILES
            else None
        )
        return str(torrent_hash or ""), str(save_path or ""), files
