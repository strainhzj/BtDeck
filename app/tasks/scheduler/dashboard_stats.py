import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DashboardStatsJob:
    """Dashboard statistics background job."""

    name = "dashboard_stats"
    description = "Dashboard torrent stats pre-cache"
    version = "1.0.0"
    author = "btpmanager"
    category = "dashboard"

    default_interval = 60

    def __init__(self, app: Optional[Any] = None):
        self.app = app
        self.last_execution_time: Optional[datetime] = None
        self.execution_count = 0

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
                    downloading = getattr(downloader, 'downloading_count', 0) or 0
                    seeding = getattr(downloader, 'seeding_count', 0) or 0
                    paused = 0  # 暂不支持从缓存读取paused统计

                    total_downloading += downloading
                    total_seeding += seeding
                    total_paused += paused

                except Exception as exc:
                    logger.warning(f"获取下载器 {getattr(downloader, 'nickname', '')} 种子统计失败: {exc}")
                    continue

            stats = {
                "active": total_downloading + total_seeding,
                "downloading": total_downloading,
                "seeding": total_seeding,
                "paused": total_paused,
            }
            self.app.state.torrent_stats = stats

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

    # ✅ 移除了 _get_downloader_torrents() 和 _count_torrent_states() 方法
    # 现在直接从 downloader 对象的缓存属性读取统计值
    # 这些值由状态更新任务（initialization.py）使用精确的状态匹配逻辑维护
