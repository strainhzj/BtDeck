# -*- coding: utf-8 -*-
"""MoviePilot 整理历史同步与关联服务（feature moviepilot-integration-20260908）。

职责：

- **握手注册**：插件携带其持久化 UUID 首次握手即注册实例（绑定首个完成
  握手的认证用户；其他有效账号冒名握手被拒绝，除非绑定账号已不存在/停用）；
- **幂等同步**：按 ``(instance_id, history_id)`` 唯一身份 upsert——内容
  SHA-256 相同 skip、不同 update、缺失 insert。重新整理与历史字段更新由此
  天然覆盖，不依赖"最大历史 ID"增量语义；
- **下载器映射解析**：实例配置 MP 下载器名 → BtDeck downloader_id；映射
  变更后全量重解析该实例历史行的冗余列（bt_downloader_id/association_status）；
- **双向关联查询**：

  - 正向：种子任务 (bt_downloader_id, hash) → 媒体库文件与源文件清单；
  - 反向：媒体/源路径 → 关联历史 → （linked 行）torrent_info 任务快照。

安全边界：本服务及其调用方**只读** MoviePilot 镜像数据，不产生任何针对
生产任务（暂停/删除/移动）或 MoviePilot 侧的写操作；历史消失不做删除推断。
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_, tuple_
from sqlalchemy.orm import Session

from app.auth.models import User
from app.downloader.models import BtDownloaders
from app.models.moviepilot_instance import MoviePilotInstance
from app.models.moviepilot_transfer_history import (
    ASSOCIATION_LINKED,
    ASSOCIATION_UNMAPPED,
    ASSOCIATION_UNASSOCIATED,
    MoviePilotTransferHistory,
    parse_mp_date,
)
from app.services.moviepilot_settings_service import MoviePilotSettingsService
from app.torrents.models import TorrentInfo

logger = logging.getLogger(__name__)

# 集成协议版本（握手/同步载荷均携带，不匹配即拒绝）
MOVIEPILOT_PROTOCOL_VERSION = 1
# 单批最大条数（防超大载荷长事务）
MAX_SYNC_BATCH_ITEMS = 200
# 单批返回的逐条错误上限（防错误清单本身爆炸）
MAX_SYNC_ERROR_ENTRIES = 20
# 反查路径最小长度（防过短前缀全表扫描）
MIN_REVERSE_LOOKUP_PATH_LEN = 3

# 列宽上限（超出截断，防超长字符串撑爆列）
_LEN_PATH = 1024
_LEN_TITLE = 255
_LEN_ERRMSG = 2048


class MoviePilotIntegrationDisabledError(RuntimeError):
    """全局集成开关关闭，HTTP 侧映射 403。"""


class MoviePilotInstanceDisabledError(RuntimeError):
    """实例已被管理员禁用，HTTP 侧映射 403。"""


class MoviePilotInstanceNotFoundError(RuntimeError):
    """实例未注册（须先握手），HTTP 侧映射 404。"""


class MoviePilotInstanceBindingError(RuntimeError):
    """实例已绑定其他有效集成账号，HTTP 侧映射 403。"""


class MoviePilotSyncPayloadError(ValueError):
    """同步载荷非法（协议版本/批量超限/必填缺失），HTTP 侧映射 400。"""


class MoviePilotMappingError(ValueError):
    """下载器映射配置非法（指向不存在的 BtDeck 下载器），HTTP 侧映射 400。"""


@dataclass
class SyncBatchResult:
    """一批同步的处理结果（计入实例统计与审计详情）。"""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors,
        }


def _trunc(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit]


def _canonical_content(item: Dict[str, Any]) -> str:
    """构造参与内容哈希的规范 JSON（决定 skip/update 的字段集，变更须慎重）。"""
    keys = (
        "historyId",
        "srcStorage",
        "srcPath",
        "destStorage",
        "destPath",
        "transferMode",
        "mediaType",
        "title",
        "year",
        "seasons",
        "episodes",
        "tmdbId",
        "doubanId",
        "mediaSource",
        "mediaId",
        "mpDownloader",
        "downloadHash",
        "status",
        "errmsg",
        "recordedAt",
    )
    canonical = {key: item.get(key) for key in keys}
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(item: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_content(item).encode("utf-8")).hexdigest()


def _raw_snapshot(item: Dict[str, Any]) -> str:
    """原始关键字段留档（fileitem 与文件清单概要，不含哈希参与字段）。"""
    files = item.get("files")
    files_list = files if isinstance(files, list) else []
    snapshot = {
        "srcFileitem": item.get("srcFileitem"),
        "destFileitem": item.get("destFileitem"),
        "files": files_list[:50],
        "filesTruncated": len(files_list) > 50,
        "filesCount": len(files_list),
    }
    return json.dumps(snapshot, ensure_ascii=False)


class MoviePilotIntegrationService:
    """MoviePilot 实例注册/同步/关联查询（同步 Session）。"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------ 握手

    def handshake(self, username: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理握手：开关校验 → 实例 upsert → 绑定校验 → 返回协议信息。"""
        self._require_integration_enabled()
        instance_id = str(payload.get("instanceId") or "").strip()
        if not instance_id or len(instance_id) > 64:
            raise MoviePilotSyncPayloadError("instanceId 缺失或超长（≤64 字符）")

        instance = self._get_instance(instance_id)
        created = instance is None
        if instance is None:
            instance = MoviePilotInstance(instance_id=instance_id, bound_username=username)
            self.db.add(instance)
        else:
            self._check_instance_usable(instance, username)

        instance.name = _trunc(str(payload.get("instanceName") or instance.name or ""), 128) or ""
        protocol_version = payload.get("protocolVersion")
        if isinstance(protocol_version, int) and not isinstance(protocol_version, bool):
            instance.protocol_version = protocol_version
        instance.plugin_version = _trunc(payload.get("pluginVersion"), 32)
        instance.moviepilot_version = _trunc(payload.get("moviepilotVersion"), 64)
        instance.last_handshake_at = datetime.now()
        instance.last_error = None
        self.db.commit()

        logger.info(
            "MoviePilot 实例握手%s: instance=%s name=%r user=%s",
            "（新注册）" if created else "",
            instance_id,
            instance.name,
            username,
        )
        return {
            "status": "ok",
            "created": created,
            "protocolVersion": MOVIEPILOT_PROTOCOL_VERSION,
            "serverTime": datetime.now().isoformat(),
            "instance": instance.to_dict(),
        }

    # ------------------------------------------------------------ 同步

    def sync_transfer_history(self, username: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """批量幂等同步整理历史；整批单事务提交，逐条非法只记错误不中断。"""
        self._require_integration_enabled()
        instance = self._require_instance_and_binding(payload, username)

        protocol_version = payload.get("protocolVersion")
        if protocol_version != MOVIEPILOT_PROTOCOL_VERSION:
            raise MoviePilotSyncPayloadError(
                f"不支持的协议版本 {protocol_version!r}（服务端支持 {MOVIEPILOT_PROTOCOL_VERSION}）"
            )
        items = payload.get("items")
        if not isinstance(items, list):
            raise MoviePilotSyncPayloadError("items 必须为数组")
        if len(items) > MAX_SYNC_BATCH_ITEMS:
            raise MoviePilotSyncPayloadError(f"单批最多 {MAX_SYNC_BATCH_ITEMS} 条（收到 {len(items)}）")

        result = SyncBatchResult()
        for raw_item in items:
            if not isinstance(raw_item, dict):
                result.failed += 1
                self._append_item_error(result, None, "条目必须是对象")
                continue
            try:
                self._upsert_history_item(instance, raw_item, result)
            except MoviePilotSyncPayloadError as exc:
                result.failed += 1
                self._append_item_error(result, raw_item.get("historyId"), str(exc))
            except Exception:  # noqa: BLE001 - 单条意外异常不拖垮整批
                result.failed += 1
                self._append_item_error(result, raw_item.get("historyId"), "服务端处理该条目时发生内部错误")
                logger.exception(
                    "MoviePilot 历史条目处理失败: instance=%s historyId=%r",
                    instance.instance_id,
                    raw_item.get("historyId"),
                )

        instance.last_sync_at = datetime.now()
        instance.last_sync_stats = json.dumps(
            {
                "inserted": result.inserted,
                "updated": result.updated,
                "skipped": result.skipped,
                "failed": result.failed,
            },
            ensure_ascii=False,
        )
        instance.synced_history_count = (
            self.db.query(func.count(MoviePilotTransferHistory.id))
            .filter(MoviePilotTransferHistory.instance_id == instance.instance_id)
            .scalar()
            or 0
        )
        if result.failed:
            instance.last_error = f"最近一批有 {result.failed} 条失败（其余已入库）"
        else:
            instance.last_error = None
        self.db.commit()

        response = result.to_dict()
        response["syncedHistoryCount"] = instance.synced_history_count
        return response

    # ------------------------------------------------------------ 实例管理

    def list_instances(self) -> List[Dict[str, Any]]:
        instances = (
            self.db.query(MoviePilotInstance)
            .order_by(MoviePilotInstance.created_at.asc(), MoviePilotInstance.id.asc())
            .all()
        )
        return [row.to_dict() for row in instances]

    def update_instance(self, instance_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """更新实例（名称/启用/映射）；映射变更后重解析该实例全部历史行。"""
        instance = self._get_instance(instance_id)
        if instance is None:
            raise MoviePilotInstanceNotFoundError(f"实例不存在: {instance_id}")

        name = payload.get("name")
        if name is not None:
            instance.name = _trunc(str(name), 128) or ""
        enabled = payload.get("enabled")
        if enabled is not None:
            if not isinstance(enabled, bool):
                raise MoviePilotSyncPayloadError("enabled 必须为布尔值")
            instance.enabled = enabled

        mapping_changed = False
        mapping = payload.get("downloaderMapping")
        if mapping is not None:
            normalized = self._validate_mapping(mapping)
            instance.downloader_mapping = json.dumps(normalized, ensure_ascii=False)
            mapping_changed = True
        self.db.commit()

        if mapping_changed:
            self._re_resolve_instance(instance)
        self.db.refresh(instance)
        return instance.to_dict()

    def delete_instance(self, instance_id: str) -> Dict[str, Any]:
        """删除实例及其全部历史镜像（显式管理动作，不用于"历史消失"推断）。"""
        instance = self._get_instance(instance_id)
        if instance is None:
            raise MoviePilotInstanceNotFoundError(f"实例不存在: {instance_id}")
        deleted_histories = (
            self.db.query(MoviePilotTransferHistory)
            .filter(MoviePilotTransferHistory.instance_id == instance_id)
            .delete()
        )
        self.db.delete(instance)
        self.db.commit()
        logger.info("MoviePilot 实例已删除: instance=%s（连带 %s 条历史镜像）", instance_id, deleted_histories)
        return {"instanceId": instance_id, "deletedHistories": deleted_histories}

    # ------------------------------------------------------------ 关联查询

    def get_associations_for_torrent(
        self, bt_downloader_id: str, download_hash: str, page: int, page_size: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """正向：种子任务 (bt_downloader_id, hash) → 整理历史（媒体/源文件）。

        严格按解析出的 bt_downloader_id 过滤——同一 hash 存在于多个下载器时
        不跨下载器串联。
        """
        query = self.db.query(MoviePilotTransferHistory).filter(
            MoviePilotTransferHistory.download_hash == download_hash,
            MoviePilotTransferHistory.bt_downloader_id == bt_downloader_id,
        )
        total = query.count()
        rows = (
            query.order_by(
                MoviePilotTransferHistory.recorded_at.desc(),
                MoviePilotTransferHistory.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        names = self._instance_names()
        return [self._history_view(row, names.get(row.instance_id)) for row in rows], total

    def reverse_lookup(self, path: str, mode: str, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        """反向：媒体库/源路径（精确或目录前缀）→ 关联历史 → 任务快照。"""
        normalized = (path or "").strip().rstrip("/")
        if len(normalized) < MIN_REVERSE_LOOKUP_PATH_LEN:
            raise MoviePilotSyncPayloadError(f"路径过短（≥{MIN_REVERSE_LOOKUP_PATH_LEN} 字符）")
        if mode not in ("src", "dest", "both"):
            raise MoviePilotSyncPayloadError("mode 必须为 src/dest/both")

        conditions = []
        if mode in ("src", "both"):
            conditions.append(self._path_condition(MoviePilotTransferHistory.src_path, normalized))
        if mode in ("dest", "both"):
            conditions.append(self._path_condition(MoviePilotTransferHistory.dest_path, normalized))
        query = self.db.query(MoviePilotTransferHistory).filter(or_(*conditions))
        total = query.count()
        rows = (
            query.order_by(
                MoviePilotTransferHistory.recorded_at.desc(),
                MoviePilotTransferHistory.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        names = self._instance_names()
        tasks = self._tasks_for_rows(rows)
        items = []
        for row in rows:
            view = self._history_view(row, names.get(row.instance_id))
            view["task"] = tasks.get((row.download_hash, row.bt_downloader_id))
            items.append(view)
        return items, total

    # ------------------------------------------------------------ 内部

    def _require_integration_enabled(self) -> None:
        if not MoviePilotSettingsService(self.db).get_settings().effective_enabled:
            raise MoviePilotIntegrationDisabledError("MoviePilot 集成未启用（请在 BtDeck 设置中开启）")

    def _get_instance(self, instance_id: str) -> Optional[MoviePilotInstance]:
        return self.db.query(MoviePilotInstance).filter(MoviePilotInstance.instance_id == instance_id).first()

    def _require_instance_and_binding(self, payload: Dict[str, Any], username: str) -> MoviePilotInstance:
        instance_id = str(payload.get("instanceId") or "").strip()
        instance = self._get_instance(instance_id) if instance_id else None
        if instance is None:
            raise MoviePilotInstanceNotFoundError("实例未注册，请先完成握手")
        self._check_instance_usable(instance, username)
        return instance

    def _check_instance_usable(self, instance: MoviePilotInstance, username: str) -> None:
        """实例可用性：未禁用 + 绑定账号一致（或原绑定账号已失效）。"""
        if not instance.enabled:
            raise MoviePilotInstanceDisabledError(f"实例已被管理员禁用: {instance.instance_id}")
        bound = instance.bound_username
        if bound and bound != username:
            bound_user = self.db.query(User).filter(User.username == bound).first()
            if bound_user is not None and bound_user.is_active:
                raise MoviePilotInstanceBindingError(f"实例已绑定集成账号 {bound}，拒绝以 {username} 写入")
            # 绑定账号已不存在/停用：允许改绑（凭证轮换场景）
            instance.bound_username = username

    def _upsert_history_item(self, instance: MoviePilotInstance, item: Dict[str, Any], result: SyncBatchResult) -> None:
        history_id = item.get("historyId")
        if not isinstance(history_id, int) or isinstance(history_id, bool) or history_id < 0:
            raise MoviePilotSyncPayloadError("historyId 必须为非负整数")

        normalized = self._normalized_fields(item)
        content_hash = _content_hash({**item, **normalized, "historyId": history_id})

        row = (
            self.db.query(MoviePilotTransferHistory)
            .filter(
                MoviePilotTransferHistory.instance_id == instance.instance_id,
                MoviePilotTransferHistory.history_id == history_id,
            )
            .first()
        )
        if row is not None and row.content_hash == content_hash:
            result.skipped += 1
            return

        bt_downloader_id, association = self._resolve_association(
            instance, normalized["mpDownloader"], normalized["downloadHash"]
        )
        now = datetime.now()
        if row is None:
            row = MoviePilotTransferHistory(
                instance_id=instance.instance_id,
                history_id=history_id,
                content_hash=content_hash,
                association_status=association,
            )
            self.db.add(row)
            row.first_synced_at = now
            result.inserted += 1
        else:
            result.updated += 1
        row.src_storage = normalized["srcStorage"]
        row.src_path = normalized["srcPath"]
        row.dest_storage = normalized["destStorage"]
        row.dest_path = normalized["destPath"]
        row.transfer_mode = normalized["transferMode"]
        row.media_type = normalized["mediaType"]
        row.title = normalized["title"]
        row.year = normalized["year"]
        row.seasons = normalized["seasons"]
        row.episodes = normalized["episodes"]
        row.tmdb_id = normalized["tmdbId"]
        row.douban_id = normalized["doubanId"]
        row.media_source = normalized["mediaSource"]
        row.media_id = normalized["mediaId"]
        row.mp_downloader = normalized["mpDownloader"]
        row.download_hash = normalized["downloadHash"]
        row.bt_downloader_id = bt_downloader_id
        row.association_status = association
        row.status = normalized["status"]
        row.errmsg = normalized["errmsg"]
        row.mp_recorded_at = _trunc(item.get("recordedAt"), 32)
        row.recorded_at = parse_mp_date(row.mp_recorded_at)
        row.content_hash = content_hash
        row.raw_snapshot = _raw_snapshot(item)
        row.last_synced_at = now

    def _normalized_fields(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """字段归一（截断到列宽 + 类型收敛）；status/downloadHash 宽松处理。"""
        status = item.get("status")
        if status is not None and not isinstance(status, bool):
            status = None
        tmdb_id = item.get("tmdbId")
        if isinstance(tmdb_id, bool) or not isinstance(tmdb_id, int):
            tmdb_id = None
        download_hash = _trunc(item.get("downloadHash"), 64) or None
        return {
            "srcStorage": _trunc(item.get("srcStorage"), 32),
            "srcPath": _trunc(item.get("srcPath"), _LEN_PATH),
            "destStorage": _trunc(item.get("destStorage"), 32),
            "destPath": _trunc(item.get("destPath"), _LEN_PATH),
            "transferMode": _trunc(item.get("transferMode"), 32),
            "mediaType": _trunc(item.get("mediaType"), 16),
            "title": _trunc(item.get("title"), _LEN_TITLE),
            "year": _trunc(item.get("year"), 8),
            "seasons": _trunc(item.get("seasons"), 32),
            "episodes": _trunc(item.get("episodes"), 255),
            "tmdbId": tmdb_id,
            "doubanId": _trunc(item.get("doubanId"), 32),
            "mediaSource": _trunc(item.get("mediaSource"), 32),
            "mediaId": _trunc(item.get("mediaId"), 64),
            "mpDownloader": _trunc(item.get("mpDownloader"), 128),
            "downloadHash": download_hash,
            "status": status,
            "errmsg": _trunc(item.get("errmsg"), _LEN_ERRMSG),
        }

    def _resolve_association(
        self, instance: MoviePilotInstance, mp_downloader: Optional[str], download_hash: Optional[str]
    ) -> Tuple[Optional[str], str]:
        """按实例映射解析冗余关联列；hash 缺失优先判 unassociated。"""
        if not download_hash:
            return None, ASSOCIATION_UNASSOCIATED
        mapping = instance.parsed_mapping()
        if not mp_downloader or mp_downloader not in mapping:
            return None, ASSOCIATION_UNMAPPED
        return mapping[mp_downloader], ASSOCIATION_LINKED

    def _validate_mapping(self, mapping: Any) -> Dict[str, str]:
        """校验映射：MP 名 → 存在的 BtDeck 下载器 id（未删除）。"""
        if not isinstance(mapping, dict):
            raise MoviePilotMappingError("downloaderMapping 必须为对象")
        normalized: Dict[str, str] = {}
        for mp_name, bt_id in mapping.items():
            key = str(mp_name or "").strip()
            value = str(bt_id or "").strip()
            if not key or not value:
                raise MoviePilotMappingError("映射键值均不能为空")
            if len(key) > 128 or len(value) > 64:
                raise MoviePilotMappingError("映射键值超长")
            normalized[key] = value
        if normalized:
            existing = {
                row.downloader_id
                for row in self.db.query(BtDownloaders.downloader_id).filter(BtDownloaders.dr == 0).all()
            }
            unknown = sorted(set(normalized.values()) - existing)
            if unknown:
                raise MoviePilotMappingError(f"映射指向不存在的 BtDeck 下载器: {unknown}")
        return normalized

    def _re_resolve_instance(self, instance: MoviePilotInstance) -> int:
        """映射变更后重解析该实例全部历史行；分块提交避免长事务。"""
        chunk = 500
        resolved = 0
        last_id = 0
        while True:
            rows = (
                self.db.query(MoviePilotTransferHistory)
                .filter(
                    MoviePilotTransferHistory.instance_id == instance.instance_id,
                    MoviePilotTransferHistory.id > last_id,
                )
                .order_by(MoviePilotTransferHistory.id.asc())
                .limit(chunk)
                .all()
            )
            if not rows:
                break
            for row in rows:
                bt_downloader_id, association = self._resolve_association(
                    instance, row.mp_downloader, row.download_hash
                )
                row.bt_downloader_id = bt_downloader_id
                row.association_status = association
                resolved += 1
            last_id = rows[-1].id
            self.db.commit()
        logger.info("MoviePilot 实例映射重解析完成: instance=%s rows=%s", instance.instance_id, resolved)
        return resolved

    def _instance_names(self) -> Dict[str, str]:
        rows = self.db.query(MoviePilotInstance.instance_id, MoviePilotInstance.name).all()
        return {row.instance_id: row.name or row.instance_id for row in rows}

    @staticmethod
    def _path_condition(column: Any, normalized_path: str) -> Any:
        return or_(column == normalized_path, column.like(normalized_path + "/%"))

    def _tasks_for_rows(
        self, rows: Sequence[MoviePilotTransferHistory]
    ) -> Dict[Tuple[Optional[str], Optional[str]], Dict[str, Any]]:
        """批量取 linked 行对应的 torrent_info 任务快照（同 hash 多下载器不串联）。"""
        pairs = sorted(
            {
                (row.download_hash, row.bt_downloader_id)
                for row in rows
                if row.association_status == ASSOCIATION_LINKED and row.download_hash and row.bt_downloader_id
            }
        )
        if not pairs:
            return {}
        torrents = (
            self.db.query(TorrentInfo)
            .filter(
                tuple_(TorrentInfo.hash, TorrentInfo.downloader_id).in_(pairs),
                TorrentInfo.dr == 0,
            )
            .all()
        )
        tasks: Dict[Tuple[Optional[str], Optional[str]], Dict[str, Any]] = {}
        for torrent in torrents:
            if not torrent.hash or not torrent.downloader_id:
                continue
            tasks[(torrent.hash, torrent.downloader_id)] = {
                "infoId": torrent.info_id,
                "name": torrent.name,
                "status": torrent.status,
                "downloaderId": torrent.downloader_id,
                "downloaderName": torrent.downloader_name,
                "savePath": torrent.save_path,
                "size": torrent.size,
            }
        return tasks

    def _history_view(self, row: MoviePilotTransferHistory, instance_name: Optional[str]) -> Dict[str, Any]:
        view = row.to_dict()
        view["instanceName"] = instance_name
        return view

    @staticmethod
    def _append_item_error(result: SyncBatchResult, history_id: Any, message: str) -> None:
        if len(result.errors) < MAX_SYNC_ERROR_ENTRIES:
            result.errors.append({"historyId": history_id, "error": _trunc(message, 512)})


__all__ = [
    "ASSOCIATION_LINKED",
    "ASSOCIATION_UNMAPPED",
    "ASSOCIATION_UNASSOCIATED",
    "MAX_SYNC_BATCH_ITEMS",
    "MOVIEPILOT_PROTOCOL_VERSION",
    "MoviePilotIntegrationDisabledError",
    "MoviePilotIntegrationService",
    "MoviePilotInstanceBindingError",
    "MoviePilotInstanceDisabledError",
    "MoviePilotInstanceNotFoundError",
    "MoviePilotMappingError",
    "MoviePilotSyncPayloadError",
    "SyncBatchResult",
]
