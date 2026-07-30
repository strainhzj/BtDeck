# -*- coding: utf-8 -*-
"""路径映射目录可用性验证。

外部路径属于 BtDeck 运行环境，使用本地文件系统探测；内部路径属于下载器，
必须通过 ``app.state.store`` 中的缓存客户端验证，禁止重新创建下载器连接。
"""

import asyncio
import os
import posixpath
import re
import stat
from dataclasses import dataclass
from numbers import Real
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

EXTERNAL_PATH_TIMEOUT_SECONDS = 5.0
DOWNLOADER_PATH_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class DirectoryProbe:
    """单侧目录探测结果。"""

    path: str
    valid: bool
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "valid": self.valid, "message": self.message}


@dataclass(frozen=True)
class MappingEntry:
    """验证所需的最小映射字段。"""

    name: str
    internal: str
    external: str


def _mapping_entry(mapping: Any, index: int) -> MappingEntry:
    """兼容 Pydantic 模型与普通 mapping。"""
    if isinstance(mapping, Mapping):
        name = mapping.get("name")
        internal = mapping.get("internal")
        external = mapping.get("external")
    else:
        name = getattr(mapping, "name", None)
        internal = getattr(mapping, "internal", None)
        external = getattr(mapping, "external", None)
    return MappingEntry(
        name=str(name or f"映射#{index + 1}"),
        internal=str(internal or ""),
        external=str(external or ""),
    )


def _safe_error(exc: BaseException) -> str:
    """输出稳定且有界的错误摘要。"""
    message = str(exc).strip() or type(exc).__name__
    return message[:300]


def _stat_directory(path: str) -> DirectoryProbe:
    """在 BtDeck 运行环境中执行一次目录 stat。"""
    try:
        path_stat = os.stat(path)
    except FileNotFoundError:
        return DirectoryProbe(path=path, valid=False, message=f"外部路径不存在: {path}")
    except NotADirectoryError:
        return DirectoryProbe(path=path, valid=False, message=f"外部路径不是目录: {path}")
    except PermissionError as exc:
        return DirectoryProbe(
            path=path,
            valid=False,
            message=f"外部路径无访问权限: {path} ({_safe_error(exc)})",
        )
    except (OSError, ValueError) as exc:
        return DirectoryProbe(
            path=path,
            valid=False,
            message=f"外部路径不可访问: {path} ({_safe_error(exc)})",
        )

    if not stat.S_ISDIR(path_stat.st_mode):
        return DirectoryProbe(path=path, valid=False, message=f"外部路径不是目录: {path}")
    required_access = os.R_OK | os.W_OK
    if os.name != "nt":
        required_access |= os.X_OK
    if not os.access(path, required_access):
        return DirectoryProbe(
            path=path,
            valid=False,
            message=f"外部路径缺少 BtDeck 所需的读写权限: {path}",
        )
    return DirectoryProbe(path=path, valid=True, message=f"外部路径可访问: {path}")


async def _probe_external_directory(path: str) -> DirectoryProbe:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_stat_directory, path),
            timeout=EXTERNAL_PATH_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return DirectoryProbe(
            path=path,
            valid=False,
            message=f"外部路径访问超时（{EXTERNAL_PATH_TIMEOUT_SECONDS:g}秒）: {path}",
        )


def _normalize_remote_path(path: str) -> str:
    """统一远程路径分隔符，同时保留 UNC 双斜杠语义。"""
    raw = str(path or "").strip().replace("\\", "/")
    if not raw:
        return ""
    normalized = posixpath.normpath(raw)
    if raw.startswith("//") and not normalized.startswith("//"):
        normalized = "/" + normalized
    return normalized


def _is_case_insensitive_path(path: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:", path)) or path.startswith("//")


def _path_contains(root: str, child: str) -> bool:
    """判断 ``child`` 是否等于或位于 ``root`` 下，避免字符串前缀误判。"""
    normalized_root = _normalize_remote_path(root)
    normalized_child = _normalize_remote_path(child)
    if not normalized_root or not normalized_child:
        return False

    if _is_case_insensitive_path(normalized_root) or _is_case_insensitive_path(normalized_child):
        normalized_root = normalized_root.casefold()
        normalized_child = normalized_child.casefold()

    if normalized_root == normalized_child:
        return True
    prefix = normalized_root if normalized_root.endswith("/") else normalized_root + "/"
    return normalized_child.startswith(prefix)


def _read_value(value: Any, *names: str) -> Any:
    """读取 qBittorrent API 的 dict-like 或对象式响应。"""
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        try:
            candidate = getattr(value, name)
        except (AttributeError, KeyError, TypeError):
            continue
        if candidate is not None:
            return candidate
    return None


def _is_non_negative_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and float(value) >= 0


def _find_cached_downloader(app_state: Any, downloader_id: str) -> Tuple[Optional[Any], Optional[str]]:
    store = getattr(app_state, "store", None)
    if store is None:
        return None, "下载器缓存未初始化"
    try:
        downloaders = store.get_snapshot_sync()
    except Exception as exc:  # noqa: BLE001 - 缓存实现异常需归一化为验证失败
        return None, f"读取下载器缓存失败: {_safe_error(exc)}"
    try:
        downloader_iterator = iter(downloaders)
    except TypeError:
        return None, "下载器缓存快照无效"

    downloader = next(
        (item for item in downloader_iterator if str(getattr(item, "downloader_id", "")) == str(downloader_id)),
        None,
    )
    if downloader is None:
        return None, f"下载器不在缓存中: {downloader_id}"

    try:
        fail_time = int(getattr(downloader, "fail_time", 0) or 0)
    except (TypeError, ValueError):
        return None, f"下载器缓存状态无效: {downloader_id}"
    if fail_time > 0:
        return None, f"下载器当前不可用（连续失败 {fail_time} 次）: {downloader_id}"
    if getattr(downloader, "client", None) is None:
        return None, f"下载器缓存中没有可用客户端: {downloader_id}"
    return downloader, None


async def _probe_transmission_paths(
    downloader_id: str,
    client: Any,
    entries: Sequence[MappingEntry],
) -> List[DirectoryProbe]:
    free_space = getattr(client, "free_space", None)
    if not callable(free_space):
        return [
            DirectoryProbe(
                path=entry.internal,
                valid=False,
                message=f"下载器内部路径不可用: {entry.internal}（Transmission 客户端不支持 free_space）",
            )
            for entry in entries
        ]

    results: List[DirectoryProbe] = []
    for entry in entries:
        try:
            available_bytes = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                free_space,
                args=(entry.internal,),
                timeout=DOWNLOADER_PATH_TIMEOUT_SECONDS,
                operation="validate_transmission_path",
            )
        except Exception as exc:  # noqa: BLE001 - RPC 错误即该目录无法确认
            results.append(
                DirectoryProbe(
                    path=entry.internal,
                    valid=False,
                    message=f"下载器内部路径不可用: {entry.internal} ({_safe_error(exc)})",
                )
            )
            continue

        if not _is_non_negative_number(available_bytes):
            results.append(
                DirectoryProbe(
                    path=entry.internal,
                    valid=False,
                    message=f"下载器内部路径不可用: {entry.internal}（未返回有效磁盘空间）",
                )
            )
            continue
        results.append(
            DirectoryProbe(
                path=entry.internal,
                valid=True,
                message=f"下载器内部路径可访问: {entry.internal}",
            )
        )
    return results


def _torrent_values(sync_data: Any) -> List[Any]:
    torrents = _read_value(sync_data, "torrents")
    if isinstance(torrents, Mapping):
        return list(torrents.values())
    if isinstance(torrents, Sequence) and not isinstance(torrents, (str, bytes, bytearray)):
        return list(torrents)
    return []


async def _load_qbittorrent_path_evidence(
    downloader_id: str,
    client: Any,
) -> Tuple[Optional[str], Any, List[str]]:
    """一次验证周期只加载一次 qB 默认路径与主数据。"""
    errors: List[str] = []
    default_path: Optional[str] = None
    sync_data: Any = None

    default_save_path = getattr(client, "app_default_save_path", None)
    if callable(default_save_path):
        try:
            raw_default = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                default_save_path,
                timeout=DOWNLOADER_PATH_TIMEOUT_SECONDS,
                operation="validate_qbittorrent_default_path",
            )
            if isinstance(raw_default, str) and raw_default.strip():
                default_path = raw_default.strip()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"读取 qBittorrent 默认保存路径失败: {_safe_error(exc)}")
    else:
        errors.append("qBittorrent 客户端不支持 app_default_save_path")

    sync_maindata = getattr(client, "sync_maindata", None)
    if callable(sync_maindata):
        try:
            sync_data = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                sync_maindata,
                args=(0,),
                timeout=DOWNLOADER_PATH_TIMEOUT_SECONDS,
                operation="validate_qbittorrent_paths",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"读取 qBittorrent 路径状态失败: {_safe_error(exc)}")
    else:
        errors.append("qBittorrent 客户端不支持 sync_maindata")

    return default_path, sync_data, errors


def _probe_qbittorrent_path(
    entry: MappingEntry,
    default_path: Optional[str],
    sync_data: Any,
    rpc_errors: Sequence[str],
) -> DirectoryProbe:
    """用 qB API 已报告的磁盘空间与实际种子保存路径提供存在性证据。"""
    server_state = _read_value(sync_data, "server_state")
    free_space = _read_value(server_state, "free_space_on_disk", "freeSpaceOnDisk")
    if default_path and _path_contains(entry.internal, default_path) and _is_non_negative_number(free_space):
        return DirectoryProbe(
            path=entry.internal,
            valid=True,
            message=f"下载器内部路径可访问: {entry.internal}（qBittorrent 默认保存路径）",
        )

    matching_torrents: List[Any] = []
    for torrent in _torrent_values(sync_data):
        save_path = _read_value(torrent, "save_path", "savePath", "download_path", "downloadPath")
        if isinstance(save_path, str) and _path_contains(entry.internal, save_path):
            matching_torrents.append(torrent)

    unusable_states = {"missingfiles", "missing_files", "error", "unknown"}
    if matching_torrents:
        usable_torrent = None
        for torrent in matching_torrents:
            state = str(_read_value(torrent, "state") or "").replace(" ", "").casefold()
            if state and state not in unusable_states:
                usable_torrent = torrent
                break
        if usable_torrent is not None:
            return DirectoryProbe(
                path=entry.internal,
                valid=True,
                message=f"下载器内部路径可访问: {entry.internal}（qBittorrent 现有种子路径）",
            )
        return DirectoryProbe(
            path=entry.internal,
            valid=False,
            message=f"下载器内部路径不可用: {entry.internal}（路径下种子均处于文件缺失或错误状态）",
        )

    detail = f"；{'；'.join(rpc_errors)}" if rpc_errors else ""
    return DirectoryProbe(
        path=entry.internal,
        valid=False,
        message=(
            f"下载器内部路径不可用: {entry.internal}"
            "（qBittorrent 未报告该目录的可用磁盘空间或现有种子路径，无法确认目录存在）"
            f"{detail}"
        ),
    )


async def _probe_qbittorrent_paths(
    downloader_id: str,
    client: Any,
    entries: Sequence[MappingEntry],
) -> List[DirectoryProbe]:
    default_path, sync_data, rpc_errors = await _load_qbittorrent_path_evidence(downloader_id, client)
    return [_probe_qbittorrent_path(entry, default_path, sync_data, rpc_errors) for entry in entries]


async def validate_path_mapping_directories(
    app_state: Any,
    downloader_id: str,
    downloader_type: int,
    mappings: Sequence[Any],
) -> Dict[str, Any]:
    """验证每条映射的内部与外部目录；任一侧失败即整体验证失败。"""
    entries = [_mapping_entry(mapping, index) for index, mapping in enumerate(mappings)]
    external_results = await asyncio.gather(*(_probe_external_directory(entry.external) for entry in entries))

    cached_downloader, cache_error = _find_cached_downloader(app_state, downloader_id)
    downloader_available = cached_downloader is not None
    if cached_downloader is None:
        internal_results = [
            DirectoryProbe(
                path=entry.internal,
                valid=False,
                message=f"下载器内部路径不可用: {entry.internal}（{cache_error}）",
            )
            for entry in entries
        ]
    else:
        client = cached_downloader.client
        if downloader_type == 0:
            internal_results = await _probe_qbittorrent_paths(downloader_id, client, entries)
        elif downloader_type == 1:
            internal_results = await _probe_transmission_paths(downloader_id, client, entries)
        else:
            downloader_available = False
            internal_results = [
                DirectoryProbe(
                    path=entry.internal,
                    valid=False,
                    message=f"下载器内部路径不可用: {entry.internal}（不支持的下载器类型 {downloader_type}）",
                )
                for entry in entries
            ]

    path_checks: List[Dict[str, Any]] = []
    errors: List[str] = []
    for entry, internal, external in zip(entries, internal_results, external_results):
        mapping_valid = internal.valid and external.valid
        path_checks.append(
            {
                "name": entry.name,
                "valid": mapping_valid,
                "internal": internal.to_dict(),
                "external": external.to_dict(),
            }
        )
        if not internal.valid:
            errors.append(f"映射“{entry.name}”: {internal.message}")
        if not external.valid:
            errors.append(f"映射“{entry.name}”: {external.message}")

    return {
        "downloader_available": downloader_available,
        "internal_paths_valid": all(result.valid for result in internal_results),
        "external_paths_valid": all(result.valid for result in external_results),
        "path_checks": path_checks,
        "errors": errors,
    }
