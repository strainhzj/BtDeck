# -*- coding: utf-8 -*-
"""孤儿文件扫描/清理共用的实时下载器 manifest 构建器。"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import select

from app.core.config import settings
from app.database import SessionLocal
from app.downloader.models import BtDownloaders
from app.models.setting_templates import DownloaderTypeEnum
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api


class ManifestBuildError(RuntimeError):
    """实时下载器清单不完整；调用方必须 fail-closed。"""


def normalize_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


@dataclass(frozen=True)
class ManifestSnapshot:
    expected_paths: Set[str]
    scan_roots: List[Tuple[str, str]]
    downloader_ids: Set[str]


class TorrentManifestBuilder:
    """以下载器实时 inventory 为权威构建文件清单。"""

    def __init__(self, store: Any):
        self.store = store

    async def build(
        self, required_downloader_ids: Optional[Set[str]] = None
    ) -> ManifestSnapshot:
        if self.store is None or not hasattr(self.store, "get_snapshot"):
            raise ManifestBuildError("app.state.store 未初始化")
        cached = await self.store.get_snapshot()
        if not isinstance(cached, (list, tuple)):
            raise ManifestBuildError("store.get_snapshot() 未返回列表")

        configs = await asyncio.to_thread(self._load_configs)
        config_ids = {str(config.downloader_id) for config in configs}
        cached_ids = {str(getattr(item, "downloader_id", "")) for item in cached}
        required = {str(value) for value in (required_downloader_ids or set())}
        missing_required = required - config_ids
        if missing_required:
            raise ManifestBuildError(
                f"候选所属下载器未启用或不存在: {sorted(missing_required)}"
            )
        unknown_cached = {value for value in cached_ids - config_ids if value}
        if unknown_cached:
            raise ManifestBuildError(
                f"共享缓存含无启用配置的下载器: {sorted(unknown_cached)}"
            )
        expected: Set[str] = set()
        roots: Dict[str, str] = {}
        protected_ids: Set[str] = set()

        for config in configs:
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

            for mapped_root in self._mapping_roots(config):
                roots[normalize_path(mapped_root)] = downloader_id

            for torrent in inventory:
                torrent_hash, save_path, embedded_files = self._torrent_identity(
                    downloader_type, torrent
                )
                if not torrent_hash or not save_path:
                    raise ManifestBuildError(
                        f"下载器 {downloader_id} 返回缺少 hash/save_path 的种子"
                    )
                external_root = self._to_external(save_path, config)
                normalized_root = normalize_path(external_root)
                roots[normalized_root] = downloader_id

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
        )

    @staticmethod
    def _load_configs() -> List[BtDownloaders]:
        db = SessionLocal()
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
        return list(result)

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
        return self._extract_files(result)

    @staticmethod
    def _extract_files(value: Any) -> List[str]:
        raw = (
            value.get("files", [])
            if isinstance(value, dict)
            else getattr(value, "files", value)
        )
        if callable(raw):
            raw = raw()
        result: List[str] = []
        for item in raw or []:
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
            files = cls._extract_files(torrent) if "files" in torrent else None
        else:
            torrent_hash = getattr(torrent, "hash", None) or getattr(
                torrent, "hashString", None
            )
            save_path = (
                getattr(torrent, "save_path", None)
                or getattr(torrent, "download_dir", None)
                or getattr(torrent, "downloadDir", None)
            )
            files_attr = getattr(torrent, "files", None)
            files = cls._extract_files(torrent) if files_attr is not None else None
        return str(torrent_hash or ""), str(save_path or ""), files

    @staticmethod
    def _to_external(path: str, config: BtDownloaders) -> str:
        service = config.path_mapping_service
        mapped = service.internal_to_external(path) if service else path
        if not mapped or not os.path.isabs(mapped):
            raise ManifestBuildError(f"路径无法映射为绝对路径: {path}")
        return mapped

    @staticmethod
    def _mapping_roots(config: BtDownloaders) -> Iterable[str]:
        if not config.path_mapping:
            return []
        try:
            data = json.loads(config.path_mapping)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ManifestBuildError(
                f"下载器 {config.downloader_id} path_mapping 无效"
            ) from exc
        roots = [
            item.get("external")
            for item in data.get("mappings", [])
            if item.get("external")
        ]
        for root in roots:
            if not os.path.isabs(root):
                raise ManifestBuildError(
                    f"下载器 {config.downloader_id} external root 非绝对路径: {root}"
                )
        return roots
