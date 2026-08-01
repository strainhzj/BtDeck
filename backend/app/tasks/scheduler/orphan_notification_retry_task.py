# -*- coding: utf-8 -*-
"""补发孤儿扫描和彻底删除任务中尚未成功创建的幂等通知。"""

from typing import Any, Dict

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.notification import Notification
from app.models.orphan_file import OrphanScanResult
from app.services.orphan_notification import notify_scan_completed
from app.services.orphan_purge_job_service import OrphanPurgeJobService


class OrphanNotificationRetryTask:
    name = "孤儿文件通知补偿任务"
    description = "补发孤儿扫描结果与彻底删除任务结果通知"
    version = "1.0.0"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        retried = 0
        failed = 0
        purge_retried = 0
        purge_failed = 0
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(OrphanScanResult)
                .where(
                    OrphanScanResult.status == "completed",
                    OrphanScanResult.total_orphans > 0,
                )
                .order_by(OrphanScanResult.scan_time.asc())
                .limit(100)
            )
            for scan in result.scalars().all():
                existing = await db.execute(
                    select(Notification.id).where(Notification.dedupe_key == f"orphan_scan:{scan.scan_id}")
                )
                if existing.scalar_one_or_none() is not None:
                    continue
                notification = await notify_scan_completed(
                    db,
                    str(scan.scan_id),
                    str(scan.scan_type),
                    int(scan.total_orphans or 0),
                    int(scan.total_orphan_size or 0),
                )
                if notification is None:
                    failed += 1
                else:
                    retried += 1
            purge_service = OrphanPurgeJobService(db)
            for task_id in await purge_service.get_unsent_notification_task_ids(limit=100):
                try:
                    if await purge_service.notify_job_result(task_id):
                        purge_retried += 1
                    else:
                        purge_failed += 1
                except Exception:
                    purge_failed += 1
        return {
            "status": "success" if failed == 0 and purge_failed == 0 else "partial",
            "task_name": self.name,
            "retried_count": retried,
            "failed_count": failed,
            "purge_retried_count": purge_retried,
            "purge_failed_count": purge_failed,
        }
