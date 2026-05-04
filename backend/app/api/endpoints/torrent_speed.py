"""
种子速度接口 - 轻量级实时速度查询

通过 app.state.store 缓存获取下载器连接，
并发调用所有下载器获取种子级实时速度数据。
"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from qbittorrentapi import Client as qbClient
from transmission_rpc import Client as trClient, TransmissionError

from app.api.responseVO import CommonResponse
from app.auth.dependencies import verify_token_dependency

logger = logging.getLogger(__name__)
router = APIRouter()

# 专用线程池，避免阻塞默认 executor
_speed_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="speed_poll")

# 单个下载器调用超时（秒）- 可通过环境变量配置
_DOWNLOADER_TIMEOUT = float(os.getenv("SPEED_API_TIMEOUT", "3.0"))


def _fetch_qb_speeds_sync(client: qbClient) -> List[Dict[str, Any]]:
    """从 qBittorrent 获取活跃种子的实时速度（仅获取活跃种子，减少数据量）"""
    torrents = client.torrents_info(status_filter="active")
    result = []
    for t in torrents:
        dl_speed = t.get("dlspeed", 0)
        ul_speed = t.get("upspeed", 0)
        if dl_speed > 0 or ul_speed > 0:
            result.append({
                "hash": t.get("hash", ""),
                "downloadSpeed": dl_speed,
                "uploadSpeed": ul_speed,
                "num_seeds": t.get("num_seeds", 0),
                "num_leechs": t.get("num_leechs", 0),
            })
    return result


# Transmission 轻量级查询：仅获取速度相关字段，避免拉取全部数据
_TR_SPEED_FIELDS = ["hashString", "rateDownload", "rateUpload", "peersSendingToUs", "peersGettingFromUs"]


def _fetch_tr_speeds_sync(client: trClient) -> List[Dict[str, Any]]:
    """从 Transmission 获取所有种子的实时速度（仅获取速度字段，极快）"""
    torrents = client.get_torrents(arguments=_TR_SPEED_FIELDS)
    result = []
    for t in torrents:
        # transmission_rpc 的 Torrent 属性名是 snake_case（rate_download），不是 camelCase（rateDownload）
        dl_speed = getattr(t, "rate_download", 0) or 0
        ul_speed = getattr(t, "rate_upload", 0) or 0
        if dl_speed > 0 or ul_speed > 0:
            result.append({
                "hash": getattr(t, "hashString", ""),
                "downloadSpeed": dl_speed,
                "uploadSpeed": ul_speed,
                "num_seeds": getattr(t, "peers_sending_to_us", 0) or 0,
                "num_leechs": getattr(t, "peers_getting_from_us", 0) or 0,
            })
    return result


async def _call_with_timeout(func, *args) -> List[Dict[str, Any]]:
    """在线程池中执行同步函数，带超时保护"""
    loop = asyncio.get_event_loop()
    future = loop.run_in_executor(_speed_executor, func, *args)
    return await asyncio.wait_for(future, timeout=_DOWNLOADER_TIMEOUT)


@router.get("/active-torrents", summary="获取所有活跃种子的实时速度")
async def get_active_torrents(
    request: Request,
    auth_error=Depends(verify_token_dependency),
):
    """
    轻量级接口：返回所有下载器中有速度的种子实时数据。
    用于前端 1 秒轮询，仅返回 downloadSpeed > 0 或 uploadSpeed > 0 的种子。
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
            except (qbClient.APIError, TransmissionError) as e:
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

        # 扁平化结果
        active_torrents: List[Dict[str, Any]] = []
        for torrent_list in results:
            active_torrents.extend(torrent_list)

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
