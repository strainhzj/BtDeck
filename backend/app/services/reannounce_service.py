# -*- coding: utf-8 -*-
"""
Tracker Reannounce 核心服务

提供 tracker 汇报的执行逻辑，供 API 和定时任务共用。
- 支持按下载器分批执行（每批500个）
- 适配 qBittorrent（hash）和 Transmission（torrent_id）
- 统一错误处理和结果返回
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 每批最大种子数
BATCH_SIZE = 500


async def execute_reannounce(
    app,
    db: Session,
    downloader_id: str,
    torrent_records: List,
    trigger_type: str = "manual",
) -> Dict[str, Any]:
    """
    执行 tracker 汇报

    Args:
        app: FastAPI app 实例（用于获取下载器缓存）
        db: 数据库 session
        downloader_id: 下载器ID
        torrent_records: 种子记录列表（ORM 对象，需有 hash/torrent_id/downloader_id 属性）
        trigger_type: 触发类型 "manual" | "scheduled"

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
            if downloader_type == 0:
                # qBittorrent: 使用 hash
                hashes = [r.hash for r in batch if r.hash]
                if hashes:
                    client.torrents_reannounce(torrent_hashes=hashes)
                result["success_count"] += len(hashes)

            elif downloader_type == 1:
                # Transmission: 使用 torrent_id
                ids = [r.torrent_id for r in batch if r.torrent_id is not None]
                if ids:
                    client.reannounce_torrent(ids)
                result["success_count"] += len(ids)

            else:
                raise ValueError(f"不支持的下载器类型: {downloader_type}")

        except Exception as e:
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.error(f"Tracker汇报失败 [downloader={downloader_id}, batch={i//BATCH_SIZE+1}]: {error_detail}")
            result["failed_count"] += len(batch)
            result["failed_items"].append({
                "batch": i // BATCH_SIZE + 1,
                "error": error_detail,
                "count": len(batch),
            })

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
        torrent_records = db.query(torrentInfoModel).filter(
            torrentInfoModel.downloader_id == dl_vo.downloader_id,
            torrentInfoModel.dr == 0,
        ).all()

        if not torrent_records:
            continue

        dl_result = await execute_reannounce(
            app=app,
            db=db,
            downloader_id=dl_vo.downloader_id,
            torrent_records=torrent_records,
            trigger_type=trigger_type,
        )
        results.append({
            "downloader_id": dl_vo.downloader_id,
            "downloader_name": dl_vo.nickname,
            **dl_result,
        })
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
    if not hasattr(app.state, 'store'):
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
    if not hasattr(app.state, 'store'):
        return []
    return app.state.store.get_snapshot_sync()
