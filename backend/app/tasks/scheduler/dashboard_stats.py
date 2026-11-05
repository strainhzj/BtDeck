import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.downloader.torrent_stats_cache import DOWNLOADING_STATES, PAUSED_STATES, SEEDING_STATES
from app.services.report_service import _normalize_host

logger = logging.getLogger(__name__)

# 五桶固定键序（与报表 _status_bucket 一致：error 优先 → 四主桶 → other）
STATUS_BUCKET_KEYS = ("error", "downloading", "seeding", "paused", "other")

# 站点分布聚合节流：tracker_host 无索引、JOIN 行数≈种子×tracker 数，
# 独立于 60s job 主循环降频执行（仪表盘一期 W1 / M-4）
SITE_BUCKET_INTERVAL_SECONDS = 300

# 站点分布 Top N + 其他（显示名直接用 host，站点别名映射不在一期范围）
SITE_BUCKET_TOP_N = 8


# 五桶 SQL：CASE 优先级与 report_service._status_bucket 完全一致——
# status='error'（大小写不敏感）或 has_tracker_error 优先判 error 桶，
# 其余按 DOWNLOADING/SEEDING/PAUSED 状态集合归属，NULL status 落 other。
# 状态集合经 expanding bindparam 参数化（BTD305 禁 f-string 拼 SQL；集合为
# torrent_stats_cache 模块常量，展开占位符双方言 SQLite/PG 均支持）。
_STATUS_BUCKET_SQL = text(
    "SELECT bucket, COUNT(*) AS cnt FROM ("
    "SELECT CASE"
    " WHEN LOWER(status) = 'error' OR has_tracker_error THEN 'error'"
    " WHEN LOWER(status) IN :downloading_states THEN 'downloading'"
    " WHEN LOWER(status) IN :seeding_states THEN 'seeding'"
    " WHEN LOWER(status) IN :paused_states THEN 'paused'"
    " ELSE 'other' END AS bucket"
    " FROM torrent_info WHERE dr = 0 AND deleted_at IS NULL"
    ") GROUP BY bucket"
).bindparams(
    bindparam("downloading_states", expanding=True),
    bindparam("seeding_states", expanding=True),
    bindparam("paused_states", expanding=True),
)

# 执行参数：排序保证展开顺序确定性（集合无序，便于日志/调试对拍）
_STATUS_BUCKET_PARAMS = {
    "downloading_states": sorted(DOWNLOADING_STATES),
    "seeding_states": sorted(SEEDING_STATES),
    "paused_states": sorted(PAUSED_STATES),
}

# 站点行源：DISTINCT (info_id, tracker_host) 先去重——一种子同 host 多 tracker 只计一次、
# 辅种副本（同 info_id 跨下载器多行）只计一次；host 去端口归一在 Python 侧复用
# report_service._normalize_host 保证口径一致。与报表 D14 的差异：D14 为文件口径
# （_dedupe_by_file 主种去重）且计入体积；siteBuckets 仅按 info_id 去重计数、无体积。
_SITE_PAIR_SQL = text(
    "SELECT DISTINCT ti.info_id AS info_id, t.tracker_host AS host"
    " FROM tracker_info t JOIN torrent_info ti ON t.torrent_info_id = ti.info_id"
    " WHERE t.dr = 0 AND ti.dr = 0 AND ti.deleted_at IS NULL"
)

# 定时任务启用计数（决策 #1）：enabled 为独立 Boolean 列（非 task_status 执行态），
# = TRUE 双方言通用（SQLite TRUE→1）
_ENABLED_TASK_SQL = text("SELECT COUNT(*) FROM cron_task WHERE dr = 0 AND enabled = TRUE")


class DashboardStatsJob:
    """Dashboard statistics background job."""

    name = "dashboard_stats"
    description = "Dashboard torrent stats pre-cache"
    version = "2.0.0"
    author = "btpmanager"
    category = "dashboard"

    default_interval = 60

    def __init__(self, app: Optional[Any] = None):
        self.app = app
        self.last_execution_time: Optional[datetime] = None
        self.execution_count = 0
        # 站点分布 5min 节流缓存（job 为长驻单实例，节流状态放实例属性）
        self._site_buckets_cache: Optional[List[Dict[str, Any]]] = None
        self._last_site_bucket_at: Optional[datetime] = None

    def set_app(self, app: Any):
        self.app = app

    async def execute(self, **kwargs) -> Dict[str, Any]:
        if self.app is None and "app" in kwargs:
            self.app = kwargs["app"]

        if self.app is None or not hasattr(self.app.state, "store") or self.app.state.store is None:
            return {
                "task_name": self.name,
                "status": "skipped",
                "message": "Downloader cache not initialized",
            }

        self.last_execution_time = datetime.now()
        self.execution_count += 1

        try:
            cached_downloaders = await self.app.state.store.get_snapshot()
            online_downloaders = [d for d in cached_downloaders if getattr(d, "fail_time", 0) == 0]

            total_downloading = 0
            total_seeding = 0
            total_paused = 0

            for downloader in online_downloaders:
                try:
                    # ✅ 修复：从缓存读取统计值，不再重新计算和修改
                    # 这些值由状态更新任务（initialization.py）维护，使用精确的状态匹配
                    downloading = getattr(downloader, "downloading_count", 0) or 0
                    seeding = getattr(downloader, "seeding_count", 0) or 0
                    paused = getattr(downloader, "paused_count", 0) or 0

                    total_downloading += downloading
                    total_seeding += seeding
                    total_paused += paused

                except Exception as exc:
                    logger.warning(f"获取下载器 {getattr(downloader, 'nickname', '')} 种子统计失败: {exc}")
                    continue

            # DB 聚合段（W1：五桶/站点/任务启用计数）独立降级——DB 异常不影响主缓存统计
            status_buckets: Dict[str, int] = {k: 0 for k in STATUS_BUCKET_KEYS}
            site_buckets: List[Dict[str, Any]] = self._site_buckets_cache or []
            enabled_tasks = 0
            try:
                async with AsyncSessionLocal() as db:
                    status_buckets = await self.aggregate_status_buckets(db)
                    enabled_tasks = await self.count_enabled_tasks(db)
                    now = datetime.now()
                    if (
                        self._site_buckets_cache is None
                        or self._last_site_bucket_at is None
                        or (now - self._last_site_bucket_at).total_seconds() >= SITE_BUCKET_INTERVAL_SECONDS
                    ):
                        self._site_buckets_cache = await self.aggregate_site_buckets(db)
                        self._last_site_bucket_at = now
                    site_buckets = self._site_buckets_cache or []
            except Exception as exc:
                logger.warning(f"仪表盘 DB 聚合降级（保留缓存统计与旧站点数据）: {exc}")

            stats = {
                "active": total_downloading + total_seeding,
                "downloading": total_downloading,
                "seeding": total_seeding,
                "paused": total_paused,
                # W1 新增段（响应键保持 snake_case 前端契约）
                "statusBuckets": status_buckets,
                "siteBuckets": site_buckets,
            }
            self.app.state.torrent_stats = stats
            self.app.state.dashboard_task_stats = {"enabled": enabled_tasks}

            return {
                "task_name": self.name,
                "status": "success",
                "message": f"统计完成: {stats['active']} 个活跃种子",
                "stats": stats,
            }

        except Exception as exc:
            logger.error(f"仪表盘统计失败: {exc}")
            return {
                "task_name": self.name,
                "status": "failed",
                "message": f"统计失败: {str(exc)}",
            }

    async def aggregate_status_buckets(self, db: AsyncSession) -> Dict[str, int]:
        """五桶状态分布（ torrents.statusBuckets，口径=报表 _status_bucket）。"""
        result = await db.execute(_STATUS_BUCKET_SQL, _STATUS_BUCKET_PARAMS)
        buckets: Dict[str, int] = {k: 0 for k in STATUS_BUCKET_KEYS}
        for row in result.fetchall():
            if row.bucket in buckets:
                buckets[row.bucket] = int(row.cnt or 0)
        return buckets

    async def aggregate_site_buckets(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """站点分布轻聚合（torrents.siteBuckets）：host 去端口归一、按种子去重计数、TopN+其他。

        去重必须在归一之后：SQL DISTINCT (info_id, host) 只能消同 URL 原始重复，
        同种子挂同站不同端口（a.com / a.com:8080）归一后仍须只计一次。
        """
        result = await db.execute(_SITE_PAIR_SQL)
        pairs: set = set()
        for row in result.fetchall():
            host = _normalize_host(row.host)
            if not host:
                continue
            pairs.add((str(row.info_id), host))
        counts: Dict[str, int] = {}
        for _, host in pairs:
            counts[host] = counts.get(host, 0) + 1
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        buckets: List[Dict[str, Any]] = [{"host": h, "count": c} for h, c in ordered[:SITE_BUCKET_TOP_N]]
        rest = sum(c for _, c in ordered[SITE_BUCKET_TOP_N:])
        if rest:
            buckets.append({"host": "other", "count": rest})
        return buckets

    async def count_enabled_tasks(self, db: AsyncSession) -> int:
        """定时任务启用计数（决策 #1：KPI 显示"已启用"口径，非 task_status 执行态）。"""
        result = await db.execute(_ENABLED_TASK_SQL)
        row = result.fetchone()
        return int(row[0] or 0) if row else 0

    # ✅ 移除了 _get_downloader_torrents() 和 _count_torrent_states() 方法
    # 现在直接从 downloader 对象的缓存属性读取统计值
    # 这些值由状态更新任务（initialization.py）使用精确的状态匹配逻辑维护
