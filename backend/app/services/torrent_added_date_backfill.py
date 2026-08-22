# -*- coding: utf-8 -*-
"""
存量 added_date 回填服务（verified-bugfix-remediation W3-3）

对 torrent_info 中 added_date IS NULL 的行，按下载器分批从下载器拉取
added_on（qB）/ addedDate（TR）回填。作为后台任务在应用启动后执行
（lifecycle yield 前 create_task），受 INFO_SYNC_STARTUP_BACKFILL_ENABLED
开关控制（默认关闭）。

- 分批经 call_downloader_api（SYNC lane）执行，不阻塞事件循环
- 只处理当前仍为 NULL 的行：W3-1 首轮快照水合已填充的行天然跳过（去重）
- 下载器返回无 added_on/addedDate 或下载器不可用时跳过（12h 全量快照兜底）
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.downloader.models import BtDownloaders
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api
from app.torrents.models import TorrentInfo

logger = logging.getLogger(__name__)

# 与 fetch_qb_torrent_details 的 _QB_DETAIL_BATCH_SIZE 对齐
_BACKFILL_BATCH = 100


def _safe_epoch(value: Any) -> Optional[int]:
    """将下载器返回的时间戳转为有效 int（0/None/非法返回 None）。"""
    if value is None:
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0 or timestamp > 2147483647:
        return None
    return timestamp


async def _backfill_qb(db, client: Any, downloader_id: str, hashes: List[str], downloader_name: str) -> int:
    """qB 分支：torrents_info 分页拉取 added_on 回填。"""
    updated = 0
    for offset in range(0, len(hashes), _BACKFILL_BATCH):
        batch = hashes[offset : offset + _BACKFILL_BATCH]
        try:
            torrents = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                client.torrents_info,
                kwargs={"torrent_hashes": batch},
                timeout=30,
                operation="backfill_qb_added_on",
            )
        except Exception as e:  # noqa: BLE001 - best-effort，下载器异常跳过该批
            logger.warning(f"[ADDED_DATE_BACKFILL] {downloader_name} 批次获取失败，跳过: {e}")
            continue

        by_hash = {
            str(getattr(t, "hash", "") or "").strip().lower(): t for t in (torrents or []) if getattr(t, "hash", None)
        }
        for torrent_hash in batch:
            torrent = by_hash.get(torrent_hash.strip().lower())
            if not torrent:
                continue
            ts = _safe_epoch(getattr(torrent, "added_on", None))
            if ts is None:
                continue
            result = await db.execute(
                select(TorrentInfo).where(
                    TorrentInfo.hash == torrent_hash,
                    TorrentInfo.downloader_id == downloader_id,
                    TorrentInfo.added_date.is_(None),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                continue
            row.added_date = datetime.fromtimestamp(ts)
            updated += 1
        await db.commit()
    return updated


async def _backfill_tr(db, client: Any, downloader_id: str, hashes: List[str], downloader_name: str) -> int:
    """TR 分支：get_torrents 拉取 addedDate 回填。"""
    updated = 0
    for offset in range(0, len(hashes), _BACKFILL_BATCH):
        batch = hashes[offset : offset + _BACKFILL_BATCH]
        try:
            torrents = await call_downloader_api(
                downloader_id,
                DownloadLane.SYNC,
                client.get_torrents,
                kwargs={"ids": batch, "fields": ["hashString", "addedDate"]},
                timeout=30,
                operation="backfill_tr_added_date",
            )
        except Exception as e:  # noqa: BLE001 - best-effort
            logger.warning(f"[ADDED_DATE_BACKFILL] {downloader_name} 批次获取失败，跳过: {e}")
            continue

        by_hash = {
            str(getattr(t, "hashString", "") or "").strip().lower(): t
            for t in (torrents or [])
            if getattr(t, "hashString", None)
        }
        for torrent_hash in batch:
            torrent = by_hash.get(torrent_hash.strip().lower())
            if not torrent:
                continue
            ts = _safe_epoch(getattr(torrent, "addedDate", None))
            if ts is None:
                continue
            result = await db.execute(
                select(TorrentInfo).where(
                    TorrentInfo.hash == torrent_hash,
                    TorrentInfo.downloader_id == downloader_id,
                    TorrentInfo.added_date.is_(None),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                continue
            row.added_date = datetime.fromtimestamp(ts)
            updated += 1
        await db.commit()
    return updated


async def backfill_torrent_added_dates(app) -> None:
    """回填 added_date 为空的行（qB/TR 分流，best-effort，异常不冒泡）。"""
    try:
        if not hasattr(app.state, "store") or app.state.store is None:
            logger.warning("[ADDED_DATE_BACKFILL] 下载器缓存未初始化，跳过")
            return

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(TorrentInfo.downloader_id, TorrentInfo.hash).where(
                        TorrentInfo.added_date.is_(None),
                        TorrentInfo.dr == 0,
                    )
                )
            ).all()
            if not rows:
                logger.info("[ADDED_DATE_BACKFILL] 无空 added_date 行，跳过")
                return

            by_downloader: Dict[str, List[str]] = {}
            for downloader_id, torrent_hash in rows:
                by_downloader.setdefault(downloader_id, []).append(torrent_hash)

            snapshot = await app.state.store.get_snapshot()
            vo_by_id = {str(d.downloader_id): d for d in snapshot}
            downloader_rows = {
                str(d.downloader_id): d for d in (await db.execute(select(BtDownloaders))).scalars().all()
            }

            total_updated = 0
            for downloader_id, hashes in by_downloader.items():
                vo = vo_by_id.get(downloader_id)
                downloader = downloader_rows.get(downloader_id)
                if not vo or not downloader or getattr(vo, "client", None) is None:
                    logger.warning(
                        f"[ADDED_DATE_BACKFILL] 下载器 {downloader_id} 不可用（缓存缺失），跳过 {len(hashes)} 行"
                    )
                    continue
                try:
                    downloader_type: Any = int(downloader.downloader_type)
                except (TypeError, ValueError):
                    downloader_type = downloader.downloader_type

                name = getattr(downloader, "nickname", downloader_id)
                if downloader_type == 0:
                    updated = await _backfill_qb(db, vo.client, downloader_id, hashes, name)
                elif downloader_type == 1:
                    updated = await _backfill_tr(db, vo.client, downloader_id, hashes, name)
                else:
                    logger.warning(f"[ADDED_DATE_BACKFILL] {name} 未知下载器类型 {downloader_type}，跳过")
                    continue
                total_updated += updated
                logger.info(f"[ADDED_DATE_BACKFILL] {name} 回填 {updated}/{len(hashes)} 行")

            logger.info(f"[ADDED_DATE_BACKFILL] 完成，共回填 {total_updated} 行")
    except Exception as e:  # noqa: BLE001 - 后台任务异常不冒泡
        logger.error(f"[ADDED_DATE_BACKFILL] 回填任务失败: {e}")
