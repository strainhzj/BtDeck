"""
种子速度接口 - 轻量级实时速度查询

通过 app.state.store 缓存获取下载器连接，
并发调用所有下载器获取种子级实时速度数据。
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, Request
from qbittorrentapi import APIError as QbAPIError, Client as qbClient
from transmission_rpc import Client as trClient, TransmissionError
from sqlalchemy import select

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user
from app.database import AsyncSessionLocal
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.torrents.models import TorrentInfo

logger = logging.getLogger(__name__)
router = APIRouter()

# 单个下载器调用超时（秒）- 可通过环境变量配置
# 经 DownloaderApiRuntime INTERACTIVE lane 调用，复用 per-downloader 限流与 timeout 语义，
# 避免 cron 同步期间速度接口成为旁路压力源（sync-resource-governance code review 修复）。
_DOWNLOADER_TIMEOUT = float(os.getenv("SPEED_API_TIMEOUT", "3.0"))

# TTL 队列配置
_TTL_SECONDS = 60  # 种子从活跃列表消失后保留观察的时长（秒）
_MAX_SUPPLEMENT_COUNT = 20  # 单次补查的最大种子数


class _TTLQueue:
    """带 TTL 的种子跟踪队列，记录有下载速度的种子"""

    def __init__(self, ttl: int):
        self._ttl = ttl
        # key: (downloader_id, hash), value: {last_time, downloader_id, hash, downloader_type}
        self._store: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def put(self, downloader_id: str, downloader_type: int, torrent_hash: str) -> None:
        """添加或刷新种子的 TTL"""
        key = (downloader_id, torrent_hash)
        self._store[key] = {
            "last_time": time.monotonic(),
            "downloader_id": downloader_id,
            "downloader_type": downloader_type,
            "hash": torrent_hash,
        }

    def cleanup(self) -> None:
        """清理过期记录"""
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now - v["last_time"] > self._ttl]
        for k in expired:
            del self._store[k]

    def get_disappeared(self, active_keys: Set[Tuple[str, str]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取活跃列表中已消失但仍在 TTL 内的种子，按 downloader_id 分组返回。
        限制每组最多 _MAX_SUPPLEMENT_COUNT 个，避免对下载器造成过大压力。
        """
        now = time.monotonic()
        result: Dict[str, List[Dict[str, Any]]] = {}
        for key, entry in self._store.items():
            if key in active_keys:
                continue
            if now - entry["last_time"] > self._ttl:
                continue
            dl_id = entry["downloader_id"]
            if dl_id not in result:
                result[dl_id] = []
            if len(result[dl_id]) < _MAX_SUPPLEMENT_COUNT:
                result[dl_id].append(entry)
        return result


# 全局 TTL 队列实例
_ttl_queue = _TTLQueue(_TTL_SECONDS)


# 活动种子集合缓存的有效期（秒）。略大于前端 1 秒轮询间隔，容忍偶尔漏轮询。
_ACTIVE_KEYS_TTL = 5.0


class ActiveSnapshotStatus(str, Enum):
    """活动集合是否可作为列表过滤的权威快照。"""

    NOT_READY = "not_ready"
    EXPIRED = "expired"
    PARTIAL = "partial"
    READY_EMPTY = "ready_empty"
    READY = "ready"


@dataclass(frozen=True)
class ActiveKeysSnapshot:
    """活动集合缓存的一次原子读取结果。"""

    keys: FrozenSet[Tuple[str, str]]
    status: ActiveSnapshotStatus

    @property
    def ready(self) -> bool:
        return self.status in (ActiveSnapshotStatus.READY, ActiveSnapshotStatus.READY_EMPTY)


class _ActiveKeysCache:
    """活动种子 (downloader_id, hash) 集合缓存。

    由 active-torrents 端点（前端每秒轮询）写入，供 getList 的 active_only 过滤读取，
    使列表查询接口无需为每次翻页实时遍历下载器（避免与轮询争抢 per-downloader 限流）。

    写入口径：downloadSpeed>0 OR uploadSpeed>0（与 _fetch_*_speeds_sync、前端
    deriveVisibleTorrentList 一致），源数据不含 supplement 补查结果（其速度可能为0）。
    """

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._keys: Set[Tuple[str, str]] = set()
        self._updated_at: float = 0.0
        self._last_refresh_complete: Optional[bool] = None
        self._lock = Lock()

    def update_complete(self, keys: Set[Tuple[str, str]]) -> None:
        """写入一次覆盖全部下载器的权威快照；空集也是有效快照。"""
        with self._lock:
            self._keys = set(keys)
            self._updated_at = time.monotonic()
            self._last_refresh_complete = True

    def mark_partial(self) -> None:
        """标记最近一次刷新不完整，保留旧值但禁止其参与活动过滤。"""
        with self._lock:
            self._last_refresh_complete = False

    def reset(self) -> None:
        """清空状态，供测试与进程生命周期管理使用。"""
        with self._lock:
            self._keys = set()
            self._updated_at = 0.0
            self._last_refresh_complete = None

    def snapshot(self) -> ActiveKeysSnapshot:
        """原子读取快照；未就绪、过期和部分刷新都不会伪装成权威空集。"""
        with self._lock:
            keys = frozenset(self._keys)
            updated_at = self._updated_at
            last_refresh_complete = self._last_refresh_complete

        if last_refresh_complete is False:
            return ActiveKeysSnapshot(frozenset(), ActiveSnapshotStatus.PARTIAL)
        if last_refresh_complete is None or updated_at == 0.0:
            return ActiveKeysSnapshot(frozenset(), ActiveSnapshotStatus.NOT_READY)
        if (time.monotonic() - updated_at) > self._ttl:
            return ActiveKeysSnapshot(frozenset(), ActiveSnapshotStatus.EXPIRED)
        status = ActiveSnapshotStatus.READY if keys else ActiveSnapshotStatus.READY_EMPTY
        return ActiveKeysSnapshot(keys, status)


# 全局活动集合缓存实例
_active_keys_cache = _ActiveKeysCache(_ACTIVE_KEYS_TTL)


def get_active_keys_snapshot() -> ActiveKeysSnapshot:
    """供 getList 同步读取活动种子集合（getList 保持同步端点，故此入口为同步）。"""
    return _active_keys_cache.snapshot()


def _fetch_qb_speeds_sync(client: qbClient) -> List[Dict[str, Any]]:
    """从 qBittorrent 获取活跃种子的实时速度（仅获取活跃种子，减少数据量）"""
    torrents = client.torrents_info(status_filter="active")
    result = []
    for t in torrents:
        dl_speed = t.get("dlspeed", 0)
        ul_speed = t.get("upspeed", 0)
        if dl_speed > 0 or ul_speed > 0:
            # qBittorrent的progress字段是0-1的小数，需要转换为百分比
            progress_raw = t.get("progress", 0)
            progress_percent = round(progress_raw * 100, 2) if progress_raw else 0
            result.append(
                {
                    "hash": t.get("hash", ""),
                    "downloadSpeed": dl_speed,
                    "uploadSpeed": ul_speed,
                    "progress": progress_percent,
                    "num_seeds": t.get("num_seeds", 0),
                    "num_leechs": t.get("num_leechs", 0),
                }
            )
    return result


# Transmission 轻量级查询：仅获取速度相关字段，避免拉取全部数据
_TR_SPEED_FIELDS = ["hashString", "rateDownload", "rateUpload", "percentDone", "peersSendingToUs", "peersGettingFromUs"]


def _fetch_tr_speeds_sync(client: trClient) -> List[Dict[str, Any]]:
    """从 Transmission 获取所有种子的实时速度（仅获取速度字段，极快）"""
    torrents = client.get_torrents(arguments=_TR_SPEED_FIELDS)
    result = []
    for t in torrents:
        # transmission_rpc 的 Torrent 属性名是 snake_case（rate_download），不是 camelCase（rateDownload）
        dl_speed = getattr(t, "rate_download", 0) or 0
        ul_speed = getattr(t, "rate_upload", 0) or 0
        if dl_speed > 0 or ul_speed > 0:
            # percentDone 返回 0-1 小数，通过 percent_done 属性安全访问
            progress_raw = getattr(t, "percent_done", 0) or 0
            progress_percent = round(progress_raw * 100, 2) if progress_raw else 0
            result.append(
                {
                    "hash": getattr(t, "hashString", ""),
                    "downloadSpeed": dl_speed,
                    "uploadSpeed": ul_speed,
                    "progress": progress_percent,
                    "num_seeds": getattr(t, "peers_sending_to_us", 0) or 0,
                    "num_leechs": getattr(t, "peers_getting_from_us", 0) or 0,
                }
            )
    return result


async def _call_with_timeout(downloader_id: str, operation: str, func, *args) -> List[Dict[str, Any]]:
    """通过 DownloaderApiRuntime INTERACTIVE lane 执行同步函数，带超时与 per-downloader 限流。

    接入 runtime 的目的（sync-resource-governance code review 修复）：
    - 复用 per-downloader semaphore，避免前端 1 秒轮询在同步期间绕过限流打满同一下载器。
    - 复用 timeout 线程级语义（asyncio.wait_for 超时后底层线程仍受 semaphore 约束）。
    """
    return await call_downloader_api(
        downloader_id,
        DownloadLane.INTERACTIVE,
        func,
        args=args,
        timeout=_DOWNLOADER_TIMEOUT,
        operation=operation,
    )


def _supplement_qb_sync(client: qbClient, hashes: List[str]) -> List[Dict[str, Any]]:
    """批量补查 qBittorrent 中消失种子的最新状态"""
    hash_str = "|".join(hashes)
    torrents = client.torrents_info(hashes=hash_str)
    result = []
    for t in torrents:
        progress_raw = t.get("progress", 0)
        progress_percent = round(progress_raw * 100, 2) if progress_raw else 0
        result.append(
            {
                "hash": t.get("hash", ""),
                "downloadSpeed": t.get("dlspeed", 0),
                "uploadSpeed": t.get("upspeed", 0),
                "progress": progress_percent,
                "num_seeds": t.get("num_seeds", 0),
                "num_leechs": t.get("num_leechs", 0),
                "status": t.get("state", ""),
            }
        )
    return result


def _supplement_tr_sync(client: trClient, hashes: List[str]) -> List[Dict[str, Any]]:
    """批量补查 Transmission 中消失种子的最新状态"""
    fields = [
        "hashString",
        "rateDownload",
        "rateUpload",
        "percentDone",
        "peersSendingToUs",
        "peersGettingFromUs",
        "status",
    ]
    # Transmission 不支持按 hash 批量查询，需要获取所有再过滤
    hash_set = set(hashes)
    all_torrents = client.get_torrents(arguments=fields)
    result = []
    for t in all_torrents:
        h = getattr(t, "hashString", "")
        if h not in hash_set:
            continue
        progress_raw = getattr(t, "percent_done", 0) or 0
        progress_percent = round(progress_raw * 100, 2) if progress_raw else 0
        result.append(
            {
                "hash": h,
                "downloadSpeed": getattr(t, "rate_download", 0) or 0,
                "uploadSpeed": getattr(t, "rate_upload", 0) or 0,
                "progress": progress_percent,
                "num_seeds": getattr(t, "peers_sending_to_us", 0) or 0,
                "num_leechs": getattr(t, "peers_getting_from_us", 0) or 0,
                "status": getattr(t, "status", ""),
            }
        )
    return result


async def _supplement_disappeared(
    disappeared_by_dl: Dict[str, List[Dict[str, Any]]],
    cached_downloaders: List[Any],
) -> List[Dict[str, Any]]:
    """对消失的种子执行批量补查，返回最新状态列表"""
    if not disappeared_by_dl:
        return []

    # 构建 downloader_id -> client 映射
    dl_map: Dict[str, Dict[str, Any]] = {}
    for d in cached_downloaders:
        dl_id = getattr(d, "downloader_id", None)
        if dl_id and getattr(d, "fail_time", 0) == 0:
            dl_map[dl_id] = {
                "client": getattr(d, "client", None),
                "downloader_type": getattr(d, "downloader_type", -1),
                "nickname": getattr(d, "nickname", "unknown"),
            }

    supplement_results: List[Dict[str, Any]] = []
    for dl_id, entries in disappeared_by_dl.items():
        dl_info = dl_map.get(dl_id)
        if not dl_info or not dl_info["client"]:
            continue

        client = dl_info["client"]
        dl_type = dl_info["downloader_type"]
        nickname = dl_info["nickname"]
        hashes = [e["hash"] for e in entries]

        try:
            if dl_type == 0 and isinstance(client, qbClient):
                data = await _call_with_timeout(dl_id, "qb_supplement_speeds", _supplement_qb_sync, client, hashes)
            elif dl_type == 1 and isinstance(client, trClient):
                data = await _call_with_timeout(dl_id, "tr_supplement_speeds", _supplement_tr_sync, client, hashes)
            else:
                continue
            supplement_results.extend(data)
        except asyncio.TimeoutError:
            logger.warning(f"补查下载器 {nickname} 消失种子超时({_DOWNLOADER_TIMEOUT}s)")
        except Exception as e:
            logger.warning(f"补查下载器 {nickname} 消失种子失败: {e}")

    return supplement_results


async def _update_completed_torrents(completed_hashes: List[str]) -> None:
    """
    更新已完成的种子到数据库

    检测进度达到100%且当前状态为downloading的种子，更新为completed状态。

    Args:
        completed_hashes: 进度达到100%的种子hash列表
    """
    if not completed_hashes:
        return

    try:
        async with AsyncSessionLocal() as db:
            # 查询当前状态为downloading的种子
            stmt = select(TorrentInfo).where(
                TorrentInfo.hash.in_(completed_hashes),
                TorrentInfo.status == "downloading",
                TorrentInfo.dr == 0,  # 未删除
            )
            result = await db.execute(stmt)
            torrents_to_update = result.scalars().all()

            if not torrents_to_update:
                return

            # 批量更新
            for torrent in torrents_to_update:
                torrent.progress = 100.0
                torrent.status = "completed"
                torrent.completed_date = datetime.now()
                torrent.update_time = datetime.now()

            await db.commit()
            logger.info(f"已更新 {len(torrents_to_update)} 个种子为完成状态")

    except Exception as e:
        logger.error(f"更新已完成种子到数据库失败: {e}", exc_info=True)


async def _sync_torrents_to_db(torrent_data: List[Dict[str, Any]]) -> None:
    """
    将补查到的种子最新进度和状态同步到数据库。

    避免搜索按钮查询数据库时出现进度回退。
    如果进度达到100%，同时更新为completed状态。
    """
    if not torrent_data:
        return

    try:
        hashes = [t["hash"] for t in torrent_data if t.get("hash")]
        if not hashes:
            return

        async with AsyncSessionLocal() as db:
            stmt = select(TorrentInfo).where(
                TorrentInfo.hash.in_(hashes),
                TorrentInfo.dr == 0,
            )
            result = await db.execute(stmt)
            db_torrents = result.scalars().all()

            # 构建 hash -> 补查数据 的映射
            data_map = {t["hash"]: t for t in torrent_data}

            updated = 0
            for torrent in db_torrents:
                new_data = data_map.get(torrent.hash)
                if not new_data:
                    continue

                new_progress = new_data.get("progress", 0)

                # 只在进度有变化时更新，减少写操作
                if torrent.progress == new_progress and torrent.status not in ("downloading",):
                    continue

                torrent.progress = new_progress
                torrent.update_time = datetime.now()
                updated += 1

                # 进度达到100%时更新为completed
                if new_progress >= 100 and torrent.status == "downloading":
                    torrent.status = "completed"
                    torrent.completed_date = datetime.now()

            if updated > 0:
                await db.commit()
                logger.info(f"已同步 {updated} 个消失种子的进度到数据库")

    except Exception as e:
        logger.error(f"同步消失种子进度到数据库失败: {e}", exc_info=True)


@dataclass
class _DownloaderSpeedResult:
    torrents: List[Dict[str, Any]]
    complete: bool


@dataclass
class _ActiveSpeedGatherResult:
    torrents: List[Dict[str, Any]]
    complete: bool


async def _process_downloader_speeds(downloader: Any) -> _DownloaderSpeedResult:
    """处理单个下载器，返回活跃种子速度列表（含超时保护）。

    抽自 get_active_torrents 端点，供 _gather_active_speeds 复用。
    """
    if getattr(downloader, "fail_time", 0) > 0:
        return _DownloaderSpeedResult([], False)

    client = getattr(downloader, "client", None)
    if client is None:
        return _DownloaderSpeedResult([], False)

    nickname = getattr(downloader, "nickname", "unknown")
    downloader_id = getattr(downloader, "downloader_id", "")
    try:
        if isinstance(client, qbClient):
            torrents = await _call_with_timeout(downloader_id, "qb_active_speeds", _fetch_qb_speeds_sync, client)
            return _DownloaderSpeedResult(torrents, True)
        elif isinstance(client, trClient):
            torrents = await _call_with_timeout(downloader_id, "tr_active_speeds", _fetch_tr_speeds_sync, client)
            return _DownloaderSpeedResult(torrents, True)
        else:
            logger.warning(f"不支持的客户端类型: {type(client)}")
            return _DownloaderSpeedResult([], False)
    except asyncio.TimeoutError:
        logger.warning(f"获取下载器 {nickname} 速度超时({_DOWNLOADER_TIMEOUT}s)，跳过")
        return _DownloaderSpeedResult([], False)
    except (QbAPIError, TransmissionError) as e:
        # 分类捕获：客户端API异常（网络、认证、协议错误）
        logger.warning(f"下载器 {nickname} API错误: {e}", exc_info=True)
        return _DownloaderSpeedResult([], False)
    except Exception as e:
        # 未知异常：记录完整堆栈便于调试
        logger.error(f"下载器 {nickname} 未知错误: {e}", exc_info=True)
        return _DownloaderSpeedResult([], False)


async def _gather_active_speeds(cached_downloaders: List[Any]) -> _ActiveSpeedGatherResult:
    """并发收集所有在线下载器的活跃种子速度，扁平化并标记所属下载器。

    抽自 get_active_torrents 端点，仅负责"snapshot → 并发取速 → 扁平化打标签"，
    不含 TTL 队列 / supplement 补查 / 异步写 DB 等副作用（这些仍由端点处理）。
    返回的每个条目口径为 downloadSpeed>0 OR uploadSpeed>0（来自 _fetch_*_speeds_sync）。
    """
    results = await asyncio.gather(*[_process_downloader_speeds(d) for d in cached_downloaders])

    active_torrents: List[Dict[str, Any]] = []
    for downloader, result in zip(cached_downloaders, results):
        dl_id = getattr(downloader, "downloader_id", "")
        dl_type = getattr(downloader, "downloader_type", -1)
        for t in result.torrents:
            t["downloader_id"] = dl_id
            t["downloader_type"] = dl_type
        active_torrents.extend(result.torrents)
    return _ActiveSpeedGatherResult(
        torrents=active_torrents,
        complete=all(result.complete for result in results),
    )


@router.get("/active-torrents", summary="获取所有活跃种子的实时速度和进度")
async def get_active_torrents(
    request: Request,
    _user=Depends(require_authenticated_user),
):
    """
    轻量级接口：返回所有下载器中有速度的种子实时数据。
    用于前端 1 秒轮询，仅返回 downloadSpeed > 0 或 uploadSpeed > 0 的种子。

    返回字段：
    - hash: 种子哈希值
    - downloadSpeed: 下载速度（bytes/s）
    - uploadSpeed: 上传速度（bytes/s）
    - progress: 下载进度（百分比，0-100）
    - num_seeds: 连接的种子数
    - num_leechs: 连接的下载者数
    """
    try:
        cached_downloaders = await request.app.state.store.get_snapshot()

        if not cached_downloaders:
            _active_keys_cache.update_complete(set())
            return CommonResponse(status="success", msg="暂无在线下载器", code="200", data=[])

        # 扁平化收集所有下载器的活跃种子速度（含 downloader_id/downloader_type 标签）
        gathered = await _gather_active_speeds(cached_downloaders)
        active_torrents = gathered.torrents

        # ---- 活动集合缓存：供 getList 的 active_only 过滤读取 ----
        # 口径 downloadSpeed>0 OR uploadSpeed>0（与 _fetch_*_speeds_sync、前端
        # deriveVisibleTorrentList 一致）。仅用扁平化结果，不含后续 supplement 补查数据
        # （其速度可能为0，会污染过滤集合）。列顺序固定 (downloader_id, hash)。
        refreshed_keys = {
            (t.get("downloader_id", ""), t["hash"])
            for t in active_torrents
            if t.get("downloader_id", "") and (t.get("downloadSpeed", 0) > 0 or t.get("uploadSpeed", 0) > 0)
        }
        if gathered.complete:
            _active_keys_cache.update_complete(refreshed_keys)
        else:
            _active_keys_cache.mark_partial()

        # ---- TTL 队列：按种子实际所属下载器记录 ----
        active_keys: Set[Tuple[str, str]] = set()
        for t in active_torrents:
            if t.get("downloadSpeed", 0) > 0:
                dl_id = t.get("downloader_id", "")
                dl_type = t.get("downloader_type", -1)
                if dl_id:
                    active_keys.add((dl_id, t["hash"]))
                    _ttl_queue.put(dl_id, dl_type, t["hash"])

        # ---- 检测消失的种子并补查 ----
        _ttl_queue.cleanup()
        disappeared_by_dl = _ttl_queue.get_disappeared(active_keys)

        supplement_data: List[Dict[str, Any]] = []
        if disappeared_by_dl:
            supplement_data = await _supplement_disappeared(disappeared_by_dl, cached_downloaders)

        # 合并补查结果到返回数据
        if supplement_data:
            active_torrents.extend(supplement_data)

        # ---- 异步同步数据库（进度+状态） ----
        # 1. 补查到的消失种子：同步进度和状态到数据库
        if supplement_data:
            asyncio.create_task(_sync_torrents_to_db(supplement_data))
        # 2. 活跃种子中进度100%的：更新为completed
        completed_hashes = [t["hash"] for t in active_torrents if t.get("progress", 0) >= 100]
        if completed_hashes:
            asyncio.create_task(_update_completed_torrents(completed_hashes))

        if gathered.complete:
            return CommonResponse(status="success", msg="获取速度数据成功", code="200", data=active_torrents)
        return CommonResponse(
            status="partial",
            msg="部分下载器速度获取失败，活动快照尚未就绪",
            code="206",
            data=active_torrents,
        )

    except Exception as e:
        _active_keys_cache.mark_partial()
        logger.error(f"获取活跃种子速度失败: {e}")
        return CommonResponse(status="error", msg=f"获取速度数据失败: {str(e)}", code="500", data=None)
