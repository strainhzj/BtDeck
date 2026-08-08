# -*- coding: utf-8 -*-
"""
Tracker Reannounce 核心服务

提供 tracker 汇报的执行逻辑，供 API 和定时任务共用。
- 支持按下载器分批执行（每批500个）
- 适配 qBittorrent（hash）和 Transmission（torrent_id）
- 统一错误处理和结果返回
- 添加并发控制,防止重复执行
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from app.models.setting_templates import DownloaderTypeEnum
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

logger = logging.getLogger(__name__)

# 每批最大种子数
BATCH_SIZE = 500

# 单次 reannounce 远程调用超时（秒，P0-04：经 call_downloader_api 的 INTERACTIVE lane 执行）
_REANNOUNCE_CALL_TIMEOUT = 30.0

# 并发锁字典(按下载器ID隔离)
_reannounce_locks: Dict[str, asyncio.Lock] = {}

# 全局锁字典访问锁
_locks_lock = asyncio.Lock()


def _to_transmission_id(torrent_id) -> Optional[int]:
    """把 torrent_info.torrent_id（text 形式的数字）转为 int。

    transmission_rpc 的 _parse_torrent_id 规则：int(>=0) 或 str(40 位 hex) 才合法。
    本库 torrent_id 列存为 text（如 '103'），需转成 int 才能通过校验。
    非数字脏数据返回 None（跳过该条，不阻断整批）。
    """
    if torrent_id is None:
        return None
    try:
        tid = int(torrent_id)
    except (TypeError, ValueError):
        logger.warning(f"Transmission torrent_id 无法转为整数，已跳过: {torrent_id!r}")
        return None
    return tid if tid >= 0 else None


async def execute_reannounce(
    app,
    downloader_id: str,
    torrent_records: List,
    trigger_type: str = "manual",
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    执行 tracker 汇报

    Args:
        app: FastAPI app 实例（用于获取下载器缓存）
        downloader_id: 下载器ID
        torrent_records: 种子记录列表（ORM 对象，需有 hash/torrent_id/downloader_id 属性）
        trigger_type: 触发类型 "manual" | "scheduled"
        db: 数据库 session（已废弃保留向后兼容，本函数内部不使用 db；
            调用方应在网络 IO 之外自行管理 session 生命周期）

    Returns:
        {"success_count": N, "failed_count": N, "trigger_type": str, "failed_items": [...]}
    """
    result = {
        "success_count": 0,
        "failed_count": 0,
        "trigger_type": trigger_type,
        "failed_items": [],
    }

    if not torrent_records:
        return result

    # 获取或创建该下载器的锁
    async with _locks_lock:
        if downloader_id not in _reannounce_locks:
            _reannounce_locks[downloader_id] = asyncio.Lock()
        lock = _reannounce_locks[downloader_id]

    # 尝试获取锁(非阻塞模式)
    if lock.locked():
        logger.warning(f"Tracker汇报正在进行中,跳过此次请求 [downloader_id={downloader_id}]")
        result["failed_count"] = len(torrent_records)
        result["failed_items"] = [{"error": "操作正在进行中，请稍后再试"}]
        return result

    # 使用锁执行汇报
    async with lock:
        # ========== 获取下载器 ==========
        downloader_vo, err = _get_downloader_from_cache(app, downloader_id)
        if err:
            result["failed_count"] = len(torrent_records)
            result["failed_items"] = [{"error": err}]
            return result

        client = downloader_vo.client
        downloader_type = downloader_vo.downloader_type

        # ========== 分批执行 ==========
        for i in range(0, len(torrent_records), BATCH_SIZE):
            batch = torrent_records[i : i + BATCH_SIZE]

            try:
                if downloader_type == DownloaderTypeEnum.QBITTORRENT:
                    # qBittorrent: 使用 hash
                    hashes = [r.hash for r in batch if r.hash]
                    if hashes:
                        # P0-04 修复：经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                        await call_downloader_api(
                            downloader_id,
                            DownloadLane.INTERACTIVE,
                            client.torrents_reannounce,
                            kwargs={"torrent_hashes": hashes},
                            timeout=_REANNOUNCE_CALL_TIMEOUT,
                            operation="qb_reannounce",
                        )
                    result["success_count"] += len(hashes)

                elif downloader_type == DownloaderTypeEnum.TRANSMISSION:
                    # Transmission: 使用 torrent_id（transmission_rpc 要求 int 或 40 位 hex；
                    # torrent_info.torrent_id 在库里存为 text 形式的数字，必须转 int，
                    # 否则 transmission_rpc 会抛 "is not valid torrent id, should be a hex str for sha1 hash"）
                    ids = []
                    for r in batch:
                        tid = _to_transmission_id(r.torrent_id)
                        if tid is not None:
                            ids.append(tid)
                    if ids:
                        # P0-04 修复：经 INTERACTIVE lane 线程池执行，不阻塞事件循环
                        await call_downloader_api(
                            downloader_id,
                            DownloadLane.INTERACTIVE,
                            client.reannounce_torrent,
                            args=(ids,),
                            timeout=_REANNOUNCE_CALL_TIMEOUT,
                            operation="tr_reannounce",
                        )
                    result["success_count"] += len(ids)

                else:
                    raise ValueError(f"不支持的下载器类型: {downloader_type}")

            except Exception as e:
                error_detail = f"{type(e).__name__}: {str(e)}"
                logger.error(f"Tracker汇报失败 [downloader={downloader_id}, batch={i//BATCH_SIZE+1}]: {error_detail}")
                result["failed_count"] += len(batch)
                result["failed_items"].append(
                    {
                        "batch": i // BATCH_SIZE + 1,
                        "error": error_detail,
                        "count": len(batch),
                    }
                )

        logger.info(
            f"Tracker汇报完成 [trigger={trigger_type}, downloader={downloader_id}]: "
            f"成功 {result['success_count']}, 失败 {result['failed_count']}"
        )
        return result


async def execute_reannounce_all_downloaders(
    app,
    db: Session,
    trigger_type: str = "manual",
) -> Dict[str, Any]:
    """
    对所有有效下载器执行 tracker 汇报

    Returns:
        {"total_downloaders": N, "results": [{downloader_id, ...}], "total_success": N, "total_failed": N}
    """
    from app.torrents.models import TorrentInfo as torrentInfoModel

    cached_downloaders = _get_all_downloaders(app)
    if not cached_downloaders:
        return {"total_downloaders": 0, "results": [], "total_success": 0, "total_failed": 0}

    results = []
    total_success = 0
    total_failed = 0

    for dl_vo in cached_downloaders:
        if dl_vo.fail_time > 0:
            continue

        # 查询该下载器下所有未删除的种子
        torrent_records = (
            db.query(torrentInfoModel)
            .filter(
                torrentInfoModel.downloader_id == dl_vo.downloader_id,
                torrentInfoModel.dr == 0,
            )
            .all()
        )

        if not torrent_records:
            continue

        dl_result = await execute_reannounce(
            app=app,
            db=db,
            downloader_id=dl_vo.downloader_id,
            torrent_records=torrent_records,
            trigger_type=trigger_type,
        )
        results.append(
            {
                "downloader_id": dl_vo.downloader_id,
                "downloader_name": dl_vo.nickname,
                **dl_result,
            }
        )
        total_success += dl_result["success_count"]
        total_failed += dl_result["failed_count"]

    return {
        "total_downloaders": len(cached_downloaders),
        "results": results,
        "total_success": total_success,
        "total_failed": total_failed,
    }


def _get_downloader_from_cache(app, downloader_id: str):
    """从缓存获取下载器，返回 (downloader_vo, error_msg)"""
    if not hasattr(app.state, "store"):
        return None, "下载器缓存未初始化"

    cached_downloaders = app.state.store.get_snapshot_sync()
    downloader_vo = next(
        (d for d in cached_downloaders if d.downloader_id == downloader_id),
        None,
    )

    if not downloader_vo:
        return None, f"下载器不在缓存中 [id={downloader_id}]"
    if downloader_vo.fail_time > 0:
        return None, f"下载器已失效 [id={downloader_id}, name={downloader_vo.nickname}]"
    if not downloader_vo.client:
        return None, f"下载器客户端连接不存在 [id={downloader_id}]"

    return downloader_vo, None


def _get_all_downloaders(app) -> list:
    """获取所有下载器列表"""
    if not hasattr(app.state, "store"):
        return []
    return app.state.store.get_snapshot_sync()
