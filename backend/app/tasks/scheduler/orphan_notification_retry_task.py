# -*- coding: utf-8 -*-
"""补发已完成孤儿扫描中尚未成功创建的幂等通知。"""

from typing import Any, Dict

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.notification import Notification
from app.models.orphan_file import OrphanScanResult
from app.services.orphan_notification import notify_scan_completed


class OrphanNotificationRetryTask:
    name = "孤儿扫描通知补偿任务"
    description = "补发 completed 且有孤儿、但缺少 dedupe 通知的扫描结果"
    version = "1.0.0"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        retried = 0
        failed = 0
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
                    select(Notification.id).where(
                        Notification.dedupe_key == f"orphan_scan:{scan.scan_id}"
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue
                notification = await notify_scan_completed(
                    db,
                    scan.scan_id,
                    scan.scan_type,
                    scan.total_orphans,
                    scan.total_orphan_size,
                )
                if notification is None:
                    failed += 1
                else:
                    retried += 1
        return {
            "status": "success" if failed == 0 else "partial",
            "task_name": self.name,
            "retried_count": retried,
            "failed_count": failed,
        }
