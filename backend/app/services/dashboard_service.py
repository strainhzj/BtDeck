import json
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
        system_stats = await self._get_system_stats()
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

    async def _get_system_stats(self) -> Dict[str, Any]:
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

        # 所有在线下载器速度之和（缓存单位为 KB/s，转 bytes/s 输出，与前端 formatSpeed 一致）
        total_download_speed = 0
        total_upload_speed = 0
        if hasattr(self.app.state, "store") and self.app.state.store is not None:
            cached_downloaders = await self.app.state.store.get_snapshot()
            for downloader in cached_downloaders:
                if getattr(downloader, "fail_time", 0) != 0:
                    continue
                total_download_speed += int(getattr(downloader, "download_speed", 0) or 0) * 1024
                total_upload_speed += int(getattr(downloader, "upload_speed", 0) or 0) * 1024

        return {
            "uptime": uptime,
            "uptime_display": uptime_display,
            "version": "1.0.0",
            "total_download_speed": total_download_speed,
            "total_upload_speed": total_upload_speed,
        }

    async def _get_downloader_list(self) -> List[Dict[str, Any]]:
        if not hasattr(self.app.state, "store") or self.app.state.store is None:
            return []

        cached_downloaders = await self.app.state.store.get_snapshot()
        downloader_list = []

        for downloader in cached_downloaders:
            downloading = 0
            seeding = 0
            paused = 0
            torrent_stats = getattr(downloader, "torrent_stats", None)
            if isinstance(torrent_stats, dict):
                downloading = int(torrent_stats.get("downloading", 0) or 0)
                seeding = int(torrent_stats.get("seeding", 0) or 0)
                paused = int(torrent_stats.get("paused", 0) or 0)
            else:
                downloading = int(getattr(downloader, "downloading_count", 0) or 0)
                seeding = int(getattr(downloader, "seeding_count", 0) or 0)
                paused = int(getattr(downloader, "paused_count", 0) or 0)

            downloader_list.append(
                {
                    "downloader_id": str(getattr(downloader, "downloader_id", "")),
                    "nickname": getattr(downloader, "nickname", "") or "Unknown",
                    "downloader_type": int(getattr(downloader, "downloader_type", 0) or 0),
                    "status": "online" if getattr(downloader, "fail_time", 0) == 0 else "offline",
                    "downloading": downloading,
                    "seeding": seeding,
                    "paused": paused,
                    # 缓存速度单位为 KB/s，转 bytes/s 输出（与前端 formatSpeed 一致）
                    "download_speed": int(getattr(downloader, "download_speed", 0) or 0) * 1024,
                    "upload_speed": int(getattr(downloader, "upload_speed", 0) or 0) * 1024,
                }
            )

        return downloader_list

    async def _get_recent_activities(self) -> List[Dict[str, Any]]:
        query = """
        SELECT operation_time, operation_type, torrent_name, downloader_name, operation_detail
        FROM torrent_audit_log
        ORDER BY operation_time DESC
        LIMIT 10
        """
        result = await self.db.execute(text(query))
        rows = result.fetchall()

        activities: List[Dict[str, Any]] = []
        now = datetime.now()

        for row in rows:
            operation_time, op_type, torrent_name, downloader_name, operation_detail = row

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
            raw_category = AuditOperationType.get_category(op_type) if op_type else None

            if raw_category not in {"torrent", "tracker", "tag", "downloader", "scheduled_task"}:
                category = "system"
            else:
                category = raw_category

            detail_dict = self._parse_operation_detail(operation_detail)

            # 孤儿文件类操作没有种子/下载器关联，走专用文案，避免"未知下载器 种子 未知种子"
            if raw_category == "orphan_files" and op_type:
                action_detail = self._build_orphan_action_detail(op_type, action, detail_dict)
            else:
                # 组合详细的操作描述
                downloader_display = downloader_name if downloader_name else "未知下载器"
                torrent_display = torrent_name if torrent_name else "未知种子"
                action_detail = f"{action} {downloader_display} 种子 {torrent_display}"

            activities.append(
                {
                    "time": time_str,
                    "source": "系统",
                    "action": action_detail,
                    "type": category,
                    "torrent_name": torrent_name,
                    "downloader_name": downloader_name,
                }
            )

        return activities

    @staticmethod
    def _parse_operation_detail(operation_detail: Any) -> Dict[str, Any]:
        """安全解析审计日志 operation_detail JSON，失败返回空字典。"""
        if not operation_detail:
            return {}
        if isinstance(operation_detail, dict):
            return operation_detail
        try:
            parsed = json.loads(operation_detail)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}

    @staticmethod
    def _build_orphan_action_detail(op_type: str, action: str, detail: Dict[str, Any]) -> str:
        """构建孤儿文件类操作的日志描述。

        清理类操作优先展示被清理文件/目录名（"孤儿文件清理文件 <名>"）；
        历史日志无 cleaned_files 时回退计数字段，其余孤儿操作按各自计数字段展示。
        """
        if op_type in (AuditOperationType.ORPHAN_CLEANUP.value, AuditOperationType.ORPHAN_AUTO_CLEANUP.value):
            cleaned_files = detail.get("cleaned_files") or []
            if cleaned_files:
                shown = cleaned_files[:10]
                suffix = f" 等{len(cleaned_files)}个" if len(cleaned_files) > len(shown) else ""
                return f"{action}文件 {'、'.join(shown)}{suffix}"
            count = int(detail.get("success_count", detail.get("quarantined_count", 0)) or 0)
            return f"{action}（成功 {count} 个）" if count else action

        field_map = {
            AuditOperationType.ORPHAN_IGNORE.value: "success_count",
            AuditOperationType.ORPHAN_RESTORE.value: "restored_count",
            AuditOperationType.ORPHAN_PURGE.value: "purged_count",
            AuditOperationType.ORPHAN_SCAN.value: "total_orphans",
        }
        field = field_map.get(op_type)
        if field:
            count = int(detail.get(field, 0) or 0)
            if count:
                return f"{action}（成功 {count} 个）"
        return action
