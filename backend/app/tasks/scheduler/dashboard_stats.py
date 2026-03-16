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
                    torrents = await self._get_downloader_torrents(downloader)
                    downloading, seeding, paused = self._count_torrent_states(torrents)

                    total_downloading += downloading
                    total_seeding += seeding
                    total_paused += paused

                    # DownloaderCheckVO is a strict Pydantic model. Persist per-downloader
                    # stats on existing declared fields instead of adding dynamic attributes.
                    downloader.downloading_count = downloading
                    downloader.seeding_count = seeding

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

    async def _get_downloader_torrents(self, downloader: Any) -> List[Any]:
        client = getattr(downloader, "client", None)
        if client is None:
            return []

        downloader_type = int(getattr(downloader, "downloader_type", 0) or 0)
        if downloader_type == 0:
            return await asyncio.to_thread(client.torrents_info)

        return await asyncio.to_thread(client.get_torrents)

    def _count_torrent_states(self, torrents: List[Any]) -> tuple[int, int, int]:
        downloading = 0
        seeding = 0
        paused = 0

        for torrent in torrents:
            state = ""
            if isinstance(torrent, dict):
                state = str(torrent.get("state", "")).lower()
            elif hasattr(torrent, "state"):
                state = str(getattr(torrent, "state", "")).lower()
            elif hasattr(torrent, "status"):
                state = str(getattr(torrent, "status", "")).lower()

            if "downloading" in state or "stalled" in state or "dl" in state:
                downloading += 1
            elif "seeding" in state or "queued" in state or "up" in state:
                seeding += 1
            elif "paused" in state or "stopped" in state or "idle" in state:
                paused += 1

        return downloading, seeding, paused
