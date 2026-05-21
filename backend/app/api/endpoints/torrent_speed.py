"""
种子速度接口 - 轻量级实时速度查询

通过 app.state.store 缓存获取下载器连接，
并发调用所有下载器获取种子级实时速度数据。
"""
import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from fastapi import APIRouter, Depends, Request
from qbittorrentapi import APIError as QbAPIError, Client as qbClient
from transmission_rpc import Client as trClient, TransmissionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responseVO import CommonResponse
from app.auth.dependencies import verify_token_dependency
from app.database import AsyncSessionLocal
from app.torrents.models import TorrentInfo

logger = logging.getLogger(__name__)
router = APIRouter()

# 专用线程池，避免阻塞默认 executor
_speed_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="speed_poll")

# 单个下载器调用超时（秒）- 可通过环境变量配置
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
            result.append({
                "hash": t.get("hash", ""),
                "downloadSpeed": dl_speed,
                "uploadSpeed": ul_speed,
                "progress": progress_percent,
                "num_seeds": t.get("num_seeds", 0),
                "num_leechs": t.get("num_leechs", 0),
            })
    return result


# Transmission 轻量级查询：仅获取速度相关字段，避免拉取全部数据
_TR_SPEED_FIELDS = ["hashString", "rateDownload", "rateUpload", "progress", "peersSendingToUs", "peersGettingFromUs"]


def _fetch_tr_speeds_sync(client: trClient) -> List[Dict[str, Any]]:
    """从 Transmission 获取所有种子的实时速度（仅获取速度字段，极快）"""
    torrents = client.get_torrents(arguments=_TR_SPEED_FIELDS)
    result = []
    for t in torrents:
        # transmission_rpc 的 Torrent 属性名是 snake_case（rate_download），不是 camelCase（rateDownload）
        dl_speed = getattr(t, "rate_download", 0) or 0
        ul_speed = getattr(t, "rate_upload", 0) or 0
        if dl_speed > 0 or ul_speed > 0:
            # Transmission的progress字段是0-1的小数，需要转换为百分比
            progress_raw = getattr(t, "progress", 0) or 0
            progress_percent = round(progress_raw * 100, 2) if progress_raw else 0
            result.append({
                "hash": getattr(t, "hashString", ""),
                "downloadSpeed": dl_speed,
                "uploadSpeed": ul_speed,
                "progress": progress_percent,
                "num_seeds": getattr(t, "peers_sending_to_us", 0) or 0,
                "num_leechs": getattr(t, "peers_getting_from_us", 0) or 0,
            })
    return result


async def _call_with_timeout(func, *args) -> List[Dict[str, Any]]:
    """在线程池中执行同步函数，带超时保护"""
    loop = asyncio.get_event_loop()
    future = loop.run_in_executor(_speed_executor, func, *args)
    return await asyncio.wait_for(future, timeout=_DOWNLOADER_TIMEOUT)


def _supplement_qb_sync(client: qbClient, hashes: List[str]) -> List[Dict[str, Any]]:
    """批量补查 qBittorrent 中消失种子的最新状态"""
    hash_str = "|".join(hashes)
    torrents = client.torrents_info(hashes=hash_str)
    result = []
    for t in torrents:
        progress_raw = t.get("progress", 0)
        progress_percent = round(progress_raw * 100, 2) if progress_raw else 0
        result.append({
            "hash": t.get("hash", ""),
            "downloadSpeed": t.get("dlspeed", 0),
            "uploadSpeed": t.get("upspeed", 0),
            "progress": progress_percent,
            "num_seeds": t.get("num_seeds", 0),
            "num_leechs": t.get("num_leechs", 0),
            "status": t.get("state", ""),
        })
    return result


def _supplement_tr_sync(client: trClient, hashes: List[str]) -> List[Dict[str, Any]]:
    """批量补查 Transmission 中消失种子的最新状态"""
    fields = [
        "hashString", "rateDownload", "rateUpload", "progress",
        "peersSendingToUs", "peersGettingFromUs", "status",
    ]
    # Transmission 不支持按 hash 批量查询，需要获取所有再过滤
    hash_set = set(hashes)
    all_torrents = client.get_torrents(arguments=fields)
    result = []
    for t in all_torrents:
        h = getattr(t, "hashString", "")
        if h not in hash_set:
            continue
        progress_raw = getattr(t, "progress", 0) or 0
        progress_percent = round(progress_raw * 100, 2) if progress_raw else 0
        result.append({
            "hash": h,
            "downloadSpeed": getattr(t, "rate_download", 0) or 0,
            "uploadSpeed": getattr(t, "rate_upload", 0) or 0,
            "progress": progress_percent,
            "num_seeds": getattr(t, "peers_sending_to_us", 0) or 0,
            "num_leechs": getattr(t, "peers_getting_from_us", 0) or 0,
            "status": getattr(t, "status", ""),
        })
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
                data = await _call_with_timeout(_supplement_qb_sync, client, hashes)
            elif dl_type == 1 and isinstance(client, trClient):
                data = await _call_with_timeout(_supplement_tr_sync, client, hashes)
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
                TorrentInfo.status == 'downloading',
                TorrentInfo.dr == 0  # 未删除
            )
            result = await db.execute(stmt)
            torrents_to_update = result.scalars().all()

            if not torrents_to_update:
                return

            # 批量更新
            for torrent in torrents_to_update:
                torrent.progress = 100.0
                torrent.status = 'completed'
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


@router.get("/active-torrents", summary="获取所有活跃种子的实时速度和进度")
async def get_active_torrents(
    request: Request,
    auth_error=Depends(verify_token_dependency),
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
    if auth_error:
        return auth_error

    try:
        cached_downloaders = await request.app.state.store.get_snapshot()

        if not cached_downloaders:
            return CommonResponse(
                status="success",
                msg="暂无在线下载器",
                code="200",
                data=[]
            )

        async def _process_downloader(downloader: Any) -> List[Dict[str, Any]]:
            """处理单个下载器，返回活跃种子速度列表（含超时保护）"""
            if getattr(downloader, "fail_time", 0) > 0:
                return []

            client = getattr(downloader, "client", None)
            if client is None:
                return []

            nickname = getattr(downloader, "nickname", "unknown")
            try:
                if isinstance(client, qbClient):
                    return await _call_with_timeout(_fetch_qb_speeds_sync, client)
                elif isinstance(client, trClient):
                    return await _call_with_timeout(_fetch_tr_speeds_sync, client)
                else:
                    logger.warning(f"不支持的客户端类型: {type(client)}")
                    return []
            except asyncio.TimeoutError:
                logger.warning(f"获取下载器 {nickname} 速度超时({_DOWNLOADER_TIMEOUT}s)，跳过")
                return []
            except (QbAPIError, TransmissionError) as e:
                # 分类捕获：客户端API异常（网络、认证、协议错误）
                logger.warning(f"下载器 {nickname} API错误: {e}", exc_info=True)
                return []
            except Exception as e:
                # 未知异常：记录完整堆栈便于调试
                logger.error(f"下载器 {nickname} 未知错误: {e}", exc_info=True)
                return []

        # 并发调用所有下载器
        results = await asyncio.gather(
            *[_process_downloader(d) for d in cached_downloaders]
        )

        # 扁平化结果，同时标记种子所属下载器
        active_torrents: List[Dict[str, Any]] = []
        for downloader, torrent_list in zip(cached_downloaders, results):
            dl_id = getattr(downloader, "downloader_id", "")
            dl_type = getattr(downloader, "downloader_type", -1)
            for t in torrent_list:
                t["downloader_id"] = dl_id
                t["downloader_type"] = dl_type
            active_torrents.extend(torrent_list)

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
        completed_hashes = [
            t["hash"] for t in active_torrents
            if t.get("progress", 0) >= 100
        ]
        if completed_hashes:
            asyncio.create_task(_update_completed_torrents(completed_hashes))

        return CommonResponse(
            status="success",
            msg="获取速度数据成功",
            code="200",
            data=active_torrents
        )

    except Exception as e:
        logger.error(f"获取活跃种子速度失败: {e}")
        return CommonResponse(
            status="error",
            msg=f"获取速度数据失败: {str(e)}",
            code="500",
            data=None
        )
