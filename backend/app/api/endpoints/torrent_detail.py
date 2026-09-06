"""
种子详情明细端点（TrackerDetailCard 文件/Peers 页签数据源）。

- GET /torrents/detail/{torrent_hash}/files：种子文件列表（名称/大小/进度）
- GET /torrents/detail/{torrent_hash}/peers：种子 Peer 列表（地址/客户端/进度/速度）

沿用 torrent_status.py 的成熟模式：app.state.store 缓存快照取客户端 +
call_downloader_api(INTERACTIVE) 线程池执行；qB/TR 原始字段在此归一化为统一
VO（progress 一律 0~1，速度单位 bytes/s）。

Transmission 访问约束（transmission-rpc 7.x，同 orphan_manifest.py 先例）：
Torrent 对象的 RPC 原始字段保存在 Container.fields 中，必须经 .get() 读取；
禁止使用 Torrent.peers 属性（库注解为 -> int 的注解缺陷）与 get_files()
（其内部额外读取 priorities/wanted 字段，仅请求 files 时会 KeyError）。
"""

import logging

from fastapi import APIRouter, Depends, Query, Request
from qbittorrentapi import NotFound404Error

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user
from app.models.setting_templates import DownloaderTypeEnum
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

logger = logging.getLogger(__name__)
router = APIRouter()

# 单次下载器 API 调用超时（秒）：详情明细是用户点开卡片的交互查询，取值介于
# 速度轮询（3s）与状态控制（30s）之间；TR 侧 get_torrent 单请求可能携带大
# peers/files 表，慢链路下放宽至 20s。
_QB_DETAIL_CALL_TIMEOUT = 15.0
_TR_DETAIL_CALL_TIMEOUT = 20.0

# 下载器侧「种子不存在」的异常类型：qB 对未知 hash 抛 NotFound404Error，
# transmission-rpc 的 get_torrent 抛 KeyError（client.py 查不到 id 时）。
_TORRENT_NOT_FOUND_ERRORS = (NotFound404Error, KeyError)


async def _resolve_cached_downloader(request, downloader_id):
    """从缓存快照解析下载器 VO；失败时返回 (None, 错误信封)，成功返回 (vo, None)。"""
    app = request.app
    if not hasattr(app.state, "store"):
        return None, CommonResponse(status="error", msg="下载器缓存未初始化", code="500", data=None)

    cached_downloaders = await app.state.store.get_snapshot()
    downloader_vo = next((d for d in cached_downloaders if d.downloader_id == downloader_id), None)
    if not downloader_vo:
        return None, CommonResponse(
            status="error",
            msg=f"下载器不在缓存中 [downloader_id={downloader_id}]",
            code="404",
            data=None,
        )

    if hasattr(downloader_vo, "fail_time") and downloader_vo.fail_time > 0:
        return None, CommonResponse(
            status="error",
            msg=f"下载器已失效 [downloader_id={downloader_id}, nickname={downloader_vo.nickname}]",
            code="503",
            data=None,
        )

    if not downloader_vo.client:
        return None, CommonResponse(
            status="error",
            msg=f"下载器客户端连接不存在 [downloader_id={downloader_id}]",
            code="500",
            data=None,
        )

    return downloader_vo, None


def _build_list_data(items, page, page_size):
    """按 api-response-format.md 列表强制格式组装 data（total/page/pageSize/list）。"""
    total = len(items)
    start = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "list": items[start : start + page_size],
    }


def _to_int(value, default=0):
    """防御性整数转换（qB/TR 字段缺省或类型异常时兜底）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0.0):
    """防御性浮点转换（progress 等字段缺省或类型异常时兜底）。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_qb_files(raw_files):
    """qB torrents_files 响应 → 统一文件 VO（name/size/progress，progress 0~1）。"""
    items = []
    for entry in raw_files or []:
        items.append(
            {
                "name": str(entry.get("name", "") or ""),
                "size": _to_int(entry.get("size", 0)),
                "progress": _to_float(entry.get("progress", 0.0)),
            }
        )
    return items


def _normalize_tr_files(torrent):
    """TR get_torrent(arguments=['files']) → 统一文件 VO。

    必须读原始字段 torrent.get('files')（name/length/bytesCompleted），
    禁用 get_files()（额外依赖 priorities/wanted 字段）。
    """
    items = []
    for entry in torrent.get("files") or []:
        size = _to_int(entry.get("length", 0))
        completed = _to_int(entry.get("bytesCompleted", 0))
        progress = (completed / size) if size > 0 else 0.0
        items.append(
            {
                "name": str(entry.get("name", "") or ""),
                "size": size,
                "progress": progress,
            }
        )
    return items


def _normalize_qb_peers(sync_response):
    """qB sync_torrent_peers(rid=0) 响应 → 统一 Peer VO。

    rid=0 每次返回全量快照，无状态端点不维护增量；peers 为
    "ip:port" -> 字段 的映射，字段用 .get() 防御（country 在新版
    libtorrent 移除 GeoIP 后可能为空）。
    """
    peers_map = (sync_response or {}).get("peers") or {}
    items = []
    for peer in peers_map.values():
        items.append(
            {
                "ip": str(peer.get("ip", "") or ""),
                "port": _to_int(peer.get("port", 0)),
                "client": str(peer.get("client", "") or ""),
                "progress": _to_float(peer.get("progress", 0.0)),
                "down_speed": _to_int(peer.get("dl_speed", 0)),
                "up_speed": _to_int(peer.get("up_speed", 0)),
                "flags": str(peer.get("flags", "") or ""),
                "country": str(peer.get("country", "") or ""),
            }
        )
    return items


def _normalize_tr_peers(torrent):
    """TR get_torrent(arguments=['peers']) → 统一 Peer VO。

    原始键名映射：address→ip、clientName→client、flagStr→flags、
    rateToClient→down_speed、rateToPeer→up_speed；TR 无 country 字段恒为空。
    """
    items = []
    for peer in torrent.get("peers") or []:
        items.append(
            {
                "ip": str(peer.get("address", "") or ""),
                "port": _to_int(peer.get("port", 0)),
                "client": str(peer.get("clientName", "") or ""),
                "progress": _to_float(peer.get("progress", 0.0)),
                "down_speed": _to_int(peer.get("rateToClient", 0)),
                "up_speed": _to_int(peer.get("rateToPeer", 0)),
                "flags": str(peer.get("flagStr", "") or ""),
                "country": "",
            }
        )
    return items


@router.get("/detail/{torrent_hash}/files")
async def get_torrent_files_detail(
    torrent_hash: str,
    request: Request,
    downloader_id: str = Query(..., description="所属下载器主键"),
    page: int = Query(1, ge=1, description="页码（从1开始；默认全量）"),
    page_size: int = Query(100000, ge=1, le=100000, description="每页条数（默认全量，供大种子裁剪）"),
    _user=Depends(require_authenticated_user),
):
    """获取种子文件列表（详情卡片「文件」页签数据源，字段：name/size/progress）"""
    downloader_vo, error = await _resolve_cached_downloader(request, downloader_id)
    if error is not None:
        return error

    client = downloader_vo.client
    try:
        if downloader_vo.downloader_type == DownloaderTypeEnum.QBITTORRENT:
            raw_files = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                client.torrents_files,
                kwargs={"torrent_hash": torrent_hash},
                timeout=_QB_DETAIL_CALL_TIMEOUT,
                operation="detail_fetch_files",
            )
            items = _normalize_qb_files(raw_files)
        elif downloader_vo.downloader_type == DownloaderTypeEnum.TRANSMISSION:
            torrent = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                client.get_torrent,
                args=(torrent_hash,),
                kwargs={"arguments": ["files"]},
                timeout=_TR_DETAIL_CALL_TIMEOUT,
                operation="detail_fetch_files",
            )
            items = _normalize_tr_files(torrent)
        else:
            return CommonResponse(
                status="error",
                msg=f"不支持的下载器类型: {downloader_vo.downloader_type}",
                code="500",
                data=None,
            )
    except _TORRENT_NOT_FOUND_ERRORS as exc:
        logger.info(f"种子不存在 [downloader_id={downloader_id}, hash={torrent_hash}]: {type(exc).__name__}")
        return CommonResponse(
            status="error",
            msg=f"种子不存在或已被删除 [{torrent_hash}]",
            code="404",
            data=None,
        )
    except Exception as exc:
        logger.exception(f"获取种子文件列表失败 [downloader_id={downloader_id}, hash={torrent_hash}]")
        return CommonResponse(
            status="error",
            msg=f"获取文件列表失败: {type(exc).__name__}: {exc}",
            code="500",
            data=None,
        )

    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data=_build_list_data(items, page, page_size),
    )


@router.get("/detail/{torrent_hash}/peers")
async def get_torrent_peers_detail(
    torrent_hash: str,
    request: Request,
    downloader_id: str = Query(..., description="所属下载器主键"),
    _user=Depends(require_authenticated_user),
):
    """获取种子 Peer 列表（详情卡片「Peers」页签数据源，字段：ip/port/client/progress/down_speed/up_speed/flags/country）"""
    downloader_vo, error = await _resolve_cached_downloader(request, downloader_id)
    if error is not None:
        return error

    client = downloader_vo.client
    try:
        if downloader_vo.downloader_type == DownloaderTypeEnum.QBITTORRENT:
            sync_response = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                client.sync_torrent_peers,
                kwargs={"torrent_hash": torrent_hash, "rid": 0},
                timeout=_QB_DETAIL_CALL_TIMEOUT,
                operation="detail_fetch_peers",
            )
            items = _normalize_qb_peers(sync_response)
        elif downloader_vo.downloader_type == DownloaderTypeEnum.TRANSMISSION:
            torrent = await call_downloader_api(
                downloader_id,
                DownloadLane.INTERACTIVE,
                client.get_torrent,
                args=(torrent_hash,),
                kwargs={"arguments": ["peers"]},
                timeout=_TR_DETAIL_CALL_TIMEOUT,
                operation="detail_fetch_peers",
            )
            items = _normalize_tr_peers(torrent)
        else:
            return CommonResponse(
                status="error",
                msg=f"不支持的下载器类型: {downloader_vo.downloader_type}",
                code="500",
                data=None,
            )
    except _TORRENT_NOT_FOUND_ERRORS as exc:
        logger.info(f"种子不存在 [downloader_id={downloader_id}, hash={torrent_hash}]: {type(exc).__name__}")
        return CommonResponse(
            status="error",
            msg=f"种子不存在或已被删除 [{torrent_hash}]",
            code="404",
            data=None,
        )
    except Exception as exc:
        logger.exception(f"获取种子Peer列表失败 [downloader_id={downloader_id}, hash={torrent_hash}]")
        return CommonResponse(
            status="error",
            msg=f"获取Peer列表失败: {type(exc).__name__}: {exc}",
            code="500",
            data=None,
        )

    return CommonResponse(
        status="success",
        msg="获取成功",
        code="200",
        data=_build_list_data(items, 1, len(items)),
    )
