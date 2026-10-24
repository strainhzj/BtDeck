# -*- coding: utf-8 -*-
"""速度时间采样任务（统计报表 W1，PLANS/statistics-reports.md §3.2）。

三职责（由 lifecycle 的 run_speed_sampler_loop 驱动，60s 一轮）：
1. 采样（每轮）：以 DB 有效下载器清单（bt_downloaders enabled=1 AND dr=0）为基准，
   与 store.get_snapshot() 按 downloader_id 对齐——在缓存且 is_online=True 记实时速度
   online=1；不在缓存（含被 downloader_cache_sync 300s 剔除者）或 is_online=False 仍记
   online=0、速度 0 行（缓存缺失≠已删除，恢复在线自动回缓存）。每轮 add_all 单次
   commit，commit 包 db_write_scope()。
2. hourly 聚合（每 5min 检查）：对"已完整结束且 hourly 不存在该 (downloader_id, hour)"
   的分组聚合（avg 分母=online_count、MAX、COUNT），INSERT OR IGNORE 幂等。
3. 清理（每日）：raw < now-14d；hourly < now-730d。

治理合规（sync-db-write-governance）：
- db_write_scope 只包裹写入 + commit（采样基准读取在临界区外）；
- 本任务为 append-only 时序写入，每轮数据必然"变化"（新时间戳行），
  不适用 2.1 状态变更检测条款（tests/tasks/test_speed_sampler.py 注明理由）；
- SYNC_DB_COMMIT_BATCH_SIZE=200 对每轮下载器数（≪200）天然满足单 commit。

在线判定用 is_online（_set_online_status 维护）；fail_time 为过时字段——
断网时可能仍为 0，禁止作为采样依据。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import AsyncSessionLocal
from app.models.speed_sample import DownloaderSpeedHourly, DownloaderSpeedSample
from app.tasks.resource_guard import admission_controller

logger = logging.getLogger(__name__)

# 采样基准：bt_downloaders 有效清单（与 downloader_cache_sync 步骤1 同口径）
_BASE_LIST_SQL = text("SELECT downloader_id FROM bt_downloaders WHERE enabled = 1 AND dr = 0")

# 已完整结束小时 → 聚合（未落入 hourly 的分组）；窗口 14d 对齐 raw 保留期，
# 覆盖后端停机数日后重启的补聚合场景。datetime() 归一两侧存储格式
# （含/不含微秒后缀的 ISO 字符串）再做等值比较。
_AGGREGATE_SQL = text(
    """
    SELECT s.downloader_id AS downloader_id,
           s.stat_hour AS stat_hour,
           s.dl_sum AS dl_sum,
           s.max_dl AS max_dl,
           s.ul_sum AS ul_sum,
           s.max_ul AS max_ul,
           s.sample_count AS sample_count,
           s.online_count AS online_count
    FROM (
        SELECT downloader_id,
               strftime('%Y-%m-%d %H:00:00', sampled_at) AS stat_hour,
               SUM(CASE WHEN online = 1 THEN download_speed ELSE 0 END) AS dl_sum,
               MAX(download_speed) AS max_dl,
               SUM(CASE WHEN online = 1 THEN upload_speed ELSE 0 END) AS ul_sum,
               MAX(upload_speed) AS max_ul,
               COUNT(*) AS sample_count,
               SUM(CASE WHEN online = 1 THEN 1 ELSE 0 END) AS online_count
        FROM downloader_speed_sample
        WHERE sampled_at < :hour_floor AND sampled_at >= :window_start
        GROUP BY downloader_id, strftime('%Y-%m-%d %H:00:00', sampled_at)
    ) s
    LEFT JOIN downloader_speed_hourly h
        ON h.downloader_id = s.downloader_id AND datetime(h.stat_hour) = datetime(s.stat_hour)
    WHERE h.id IS NULL
    """
)

_CLEAN_RAW_SQL = text("DELETE FROM downloader_speed_sample WHERE sampled_at < :cutoff")
_CLEAN_HOURLY_SQL = text("DELETE FROM downloader_speed_hourly WHERE stat_hour < :cutoff")


def _to_kb_bytes(value: Any) -> int:
    """缓存 KB/s → bytes/s（对齐 dashboard_service：int 截断 × 1024）。"""
    try:
        return int(value or 0) * 1024
    except (TypeError, ValueError):
        return 0


class SpeedSamplerJob:
    """速度时间采样后台任务（60s 采样 + 5min 聚合检查 + 每日清理）。"""

    name = "speed_sampler"
    description = "Downloader speed time sampling (raw + hourly aggregation)"
    version = "1.0.0"
    author = "btpmanager"
    category = "statistics"

    default_interval = 60
    aggregate_interval = 300  # 聚合检查周期（5min）
    cleanup_interval = 86400  # 清理周期（每日）
    raw_retention_days = 14
    hourly_retention_days = 730

    def __init__(self, app: Optional[Any] = None):
        self.app = app
        self.execution_count = 0
        self._last_aggregate_at: Optional[datetime] = None
        self._last_cleanup_at: Optional[datetime] = None

    def set_app(self, app: Any) -> None:
        self.app = app

    # ------------------------------------------------------------------
    # 采样（每轮）
    # ------------------------------------------------------------------
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """采样一轮：DB 基准清单对齐缓存快照，逐下载器落一行（含离线行）。"""
        if self.app is None and "app" in kwargs:
            self.app = kwargs["app"]

        if self.app is None or not hasattr(self.app.state, "store") or self.app.state.store is None:
            return {"task_name": self.name, "status": "skipped", "message": "Downloader cache not initialized"}

        self.execution_count += 1

        snapshot = await self.app.state.store.get_snapshot()
        cached_map = {
            str(getattr(vo, "downloader_id")): vo for vo in snapshot if getattr(vo, "downloader_id", None) is not None
        }

        now = datetime.now()
        rows = []
        async with AsyncSessionLocal() as db:
            base_rows = (await db.execute(_BASE_LIST_SQL)).fetchall()
            for (downloader_id,) in base_rows:
                dl_id = str(downloader_id)
                vo = cached_map.get(dl_id)
                # 在线判定只认 is_online；fail_time 为过时字段禁止使用
                online = vo is not None and getattr(vo, "is_online", False) is True
                if online:
                    dl_speed = _to_kb_bytes(getattr(vo, "download_speed", 0))
                    ul_speed = _to_kb_bytes(getattr(vo, "upload_speed", 0))
                else:
                    dl_speed = 0
                    ul_speed = 0
                rows.append(
                    DownloaderSpeedSample(
                        downloader_id=dl_id,
                        sampled_at=now,
                        download_speed=dl_speed,
                        upload_speed=ul_speed,
                        online=online,
                    )
                )

            if rows:
                # 每轮 add_all 单次 commit；写入+commit 包 db_write_scope（2.3）
                db.add_all(rows)
                async with admission_controller.db_write_scope():
                    await db.commit()

        return {
            "task_name": self.name,
            "status": "success",
            "message": f"sampled {len(rows)} downloaders ({sum(1 for r in rows if r.online)} online)",
        }

    # ------------------------------------------------------------------
    # hourly 聚合（每 5min 检查，幂等）
    # ------------------------------------------------------------------
    async def maybe_aggregate(self) -> Dict[str, Any]:
        """聚合节流：距上次聚合不足 5min 直接返回。"""
        now = datetime.now()
        if (
            self._last_aggregate_at is not None
            and (now - self._last_aggregate_at).total_seconds() < self.aggregate_interval
        ):
            return {"task_name": self.name, "status": "throttled", "message": "aggregate interval not reached"}
        self._last_aggregate_at = now
        return await self._aggregate_hourly(now)

    async def _aggregate_hourly(self, now: datetime) -> Dict[str, Any]:
        """对已完整结束且未聚合过的小时分组聚合，INSERT OR IGNORE。"""
        hour_floor = now.replace(minute=0, second=0, microsecond=0)
        window_start = hour_floor - timedelta(days=self.raw_retention_days)

        async with AsyncSessionLocal() as db:
            agg_rows = (
                await db.execute(
                    _AGGREGATE_SQL,
                    {
                        "hour_floor": hour_floor.strftime("%Y-%m-%d %H:%M:%S"),
                        "window_start": window_start.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
            ).fetchall()

            if not agg_rows:
                return {
                    "task_name": self.name,
                    "status": "success",
                    "message": "no pending hour groups",
                    "aggregated": 0,
                }

            values = []
            for r in agg_rows:
                online_count = int(r.online_count or 0)
                # avg 分母 = online_count（在线期间均值）；全离线小时输出 0
                avg_dl = int(r.dl_sum or 0) // online_count if online_count else 0
                avg_ul = int(r.ul_sum or 0) // online_count if online_count else 0
                stat_hour = datetime.strptime(str(r.stat_hour), "%Y-%m-%d %H:%M:%S")
                values.append(
                    {
                        "downloader_id": str(r.downloader_id),
                        "stat_hour": stat_hour,
                        "avg_download_speed": avg_dl,
                        "max_download_speed": int(r.max_dl or 0),
                        "avg_upload_speed": avg_ul,
                        "max_upload_speed": int(r.max_ul or 0),
                        "sample_count": int(r.sample_count or 0),
                        "online_count": online_count,
                    }
                )

            stmt = (
                sqlite_insert(DownloaderSpeedHourly)
                .values(values)
                .on_conflict_do_nothing(index_elements=["downloader_id", "stat_hour"])
            )
            async with admission_controller.db_write_scope():
                await db.execute(stmt)
                await db.commit()

        return {
            "task_name": self.name,
            "status": "success",
            "message": f"aggregated {len(values)} hour groups",
            "aggregated": len(values),
        }

    # ------------------------------------------------------------------
    # 清理（每日）
    # ------------------------------------------------------------------
    async def maybe_cleanup(self) -> Dict[str, Any]:
        """清理节流：距上次清理不足 24h 直接返回。"""
        now = datetime.now()
        if self._last_cleanup_at is not None and (now - self._last_cleanup_at).total_seconds() < self.cleanup_interval:
            return {"task_name": self.name, "status": "throttled", "message": "cleanup interval not reached"}
        self._last_cleanup_at = now
        return await self._cleanup_expired(now)

    async def _cleanup_expired(self, now: datetime) -> Dict[str, Any]:
        """raw < now-14d、hourly < now-730d 物理删除（append-only 时序数据）。"""
        raw_cutoff = (now - timedelta(days=self.raw_retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        hourly_cutoff = (now - timedelta(days=self.hourly_retention_days)).strftime("%Y-%m-%d %H:%M:%S")

        async with AsyncSessionLocal() as db:
            raw_result = await db.execute(_CLEAN_RAW_SQL, {"cutoff": raw_cutoff})
            hourly_result = await db.execute(_CLEAN_HOURLY_SQL, {"cutoff": hourly_cutoff})
            async with admission_controller.db_write_scope():
                await db.commit()

        raw_deleted = getattr(raw_result, "rowcount", 0)
        hourly_deleted = getattr(hourly_result, "rowcount", 0)
        return {
            "task_name": self.name,
            "status": "success",
            "message": f"cleaned raw<{raw_deleted}> hourly<{hourly_deleted}>",
            "raw_deleted": raw_deleted,
            "hourly_deleted": hourly_deleted,
        }
