import logging
import time
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.torrents.audit_enums import AuditOperationType

logger = logging.getLogger(__name__)


class DashboardService:
    """Dashboard data aggregation service."""

    def __init__(self, db: AsyncSession, app: Any):
        self.db = db
        self.app = app

    async def get_dashboard_data(self) -> Dict[str, Any]:
        downloaders_stats = await self._get_downloaders_stats()
        torrents_stats = await self._get_torrents_stats()
        tasks_stats = await self._get_tasks_stats()
        system_stats = self._get_system_stats()
        downloader_list = await self._get_downloader_list()
        activities = await self._get_recent_activities()

        return {
            "downloaders": downloaders_stats,
            "torrents": torrents_stats,
            "tasks": tasks_stats,
            "system": system_stats,
            "downloader_list": downloader_list,
            "activities": activities,
        }

    async def _get_downloaders_stats(self) -> Dict[str, int]:
        if not hasattr(self.app.state, "store") or self.app.state.store is None:
            return {"total": 0, "online": 0, "offline": 0}

        cached_downloaders = await self.app.state.store.get_snapshot()
        total = len(cached_downloaders)
        online = sum(1 for d in cached_downloaders if getattr(d, "fail_time", 0) == 0)
        offline = total - online
        return {"total": total, "online": online, "offline": offline}

    async def _get_torrents_stats(self) -> Dict[str, int]:
        if hasattr(self.app.state, "torrent_stats"):
            return self.app.state.torrent_stats
        return {"active": 0, "downloading": 0, "seeding": 0, "paused": 0}

    async def _get_tasks_stats(self) -> Dict[str, int]:
        query = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN task_status = 1 THEN 1 ELSE 0 END) as running
        FROM cron_task
        WHERE dr = 0
        """
        result = await self.db.execute(text(query))
        row = result.fetchone()
        total = int(row[0] or 0) if row else 0
        running = int(row[1] or 0) if row else 0
        stopped = max(total - running, 0)
        return {"total": total, "running": running, "stopped": stopped}

    def _get_system_stats(self) -> Dict[str, Any]:
        start_time = getattr(self.app.state, "start_time", None)
        if start_time is None:
            start_time = time.time()

        uptime = int(time.time() - start_time)
        days = uptime // 86400
        hours = (uptime % 86400) // 3600
        minutes = (uptime % 3600) // 60

        if days > 0:
            uptime_display = f"{days}天{hours}小时"
        elif hours > 0:
            uptime_display = f"{hours}小时{minutes}分钟"
        else:
            uptime_display = f"{minutes}分钟"

        return {
            "uptime": uptime,
            "uptime_display": uptime_display,
            "version": "1.0.0",
        }

    async def _get_downloader_list(self) -> List[Dict[str, Any]]:
        if not hasattr(self.app.state, "store") or self.app.state.store is None:
            return []

        cached_downloaders = await self.app.state.store.get_snapshot()
        downloader_list = []

        for downloader in cached_downloaders:
            downloading = 0
            seeding = 0
            torrent_stats = getattr(downloader, "torrent_stats", None)
            if isinstance(torrent_stats, dict):
                downloading = int(torrent_stats.get("downloading", 0) or 0)
                seeding = int(torrent_stats.get("seeding", 0) or 0)
            else:
                downloading = int(getattr(downloader, "downloading_count", 0) or 0)
                seeding = int(getattr(downloader, "seeding_count", 0) or 0)

            downloader_list.append({
                "downloader_id": str(getattr(downloader, "downloader_id", "")),
                "nickname": getattr(downloader, "nickname", "") or "Unknown",
                "downloader_type": int(getattr(downloader, "downloader_type", 0) or 0),
                "status": "online" if getattr(downloader, "fail_time", 0) == 0 else "offline",
                "downloading": downloading,
                "seeding": seeding,
            })

        return downloader_list

    async def _get_recent_activities(self) -> List[Dict[str, Any]]:
        query = """
        SELECT operation_time, operation_type, torrent_name, downloader_name
        FROM torrent_audit_log
        ORDER BY operation_time DESC
        LIMIT 10
        """
        result = await self.db.execute(text(query))
        rows = result.fetchall()

        activities: List[Dict[str, Any]] = []
        now = datetime.now()

        for row in rows:
            operation_time, op_type, torrent_name, downloader_name = row

            time_str = "--"
            if operation_time:
                if isinstance(operation_time, str):
                    try:
                        operation_time = datetime.fromisoformat(operation_time)
                    except ValueError:
                        operation_time = None
                if isinstance(operation_time, datetime):
                    delta = now - operation_time
                    if delta.total_seconds() < 60:
                        time_str = f"{int(delta.total_seconds())}秒前"
                    elif delta.total_seconds() < 3600:
                        time_str = f"{int(delta.total_seconds() // 60)}分钟前"
                    elif delta.total_seconds() < 86400:
                        time_str = f"{int(delta.total_seconds() // 3600)}小时前"
                    else:
                        time_str = f"{delta.days}天前"

            action = AuditOperationType.get_display_name(op_type) if op_type else "系统操作"
            category = AuditOperationType.get_category(op_type) if op_type else None

            if category not in {"torrent", "tracker", "tag", "downloader", "scheduled_task"}:
                category = "system"

            # 组合详细的操作描述
            downloader_display = downloader_name if downloader_name else "未知下载器"
            torrent_display = torrent_name if torrent_name else "未知种子"
            action_detail = f"{action} {downloader_display} 种子 {torrent_display}"

            activities.append({
                "time": time_str,
                "source": "系统",
                "action": action_detail,
                "type": category,
                "torrent_name": torrent_name,
                "downloader_name": downloader_name,
            })

        return activities
