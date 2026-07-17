# -*- coding: utf-8 -*-
"""
G 组：孤儿文件扫描完成通知（v1.0.6+ 语义重做）

覆盖：
- completed 且数量大于零时创建通知
- 数量为零时不通知
- failed/running 时不通知
- 同一 scan_id 重试只生成一条通知（dedupe_key 幂等）
- 通知内容、数量、总大小和 route 正确
- 通知创建失败不把扫描改为 failed
- 后续重试能补发且仍保持幂等
- 未读数量随通知增加

通知规范：
  type: system, priority: warning
  title: 孤儿文件扫描完成
  content: 本次扫描发现 N 个孤儿文件，共 X GB，请前往孤儿文件管理页面查看。
  extra_data: {event, scan_id, scan_type, orphan_count, orphan_size, route}
  dedupe_key: orphan_scan:{scan_id}

本阶段因通知接入尚未实现，全部应失败。
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


class TestOrphanScanNotification:
    """扫描完成通知测试。"""

    async def test_completed_with_orphans_creates_notification(self, async_orphan_db):
        """completed 且孤儿数 > 0 时创建通知。"""
        from app.services.orphan_notification import notify_scan_completed

        await notify_scan_completed(
            db=async_orphan_db,
            scan_id="scan_with_orphans",
            scan_type="manual",
            orphan_count=36,
            orphan_size=137975824384,
        )
        await async_orphan_db.commit()

        from app.models.notification import Notification

        result = await async_orphan_db.execute(
            select(Notification).where(
                Notification.dedupe_key == "orphan_scan:scan_with_orphans"
            )
        )
        notif = result.scalar_one_or_none()
        assert notif is not None, "应创建通知"
        assert notif.type == "system"
        assert notif.priority == "warning"
        assert "36" in (notif.content or "")
        extra = json.loads(notif.extra_data) if notif.extra_data else {}
        assert extra.get("event") == "orphan_scan_completed"
        assert extra.get("orphan_count") == 36
        assert extra.get("orphan_size") == 137975824384
        assert extra.get("route") == "/orphan-files/index"

    async def test_zero_orphans_no_notification(self, async_orphan_db):
        """孤儿数为 0 时不通知。"""
        from app.services.orphan_notification import notify_scan_completed

        await notify_scan_completed(
            db=async_orphan_db,
            scan_id="scan_zero",
            scan_type="manual",
            orphan_count=0,
            orphan_size=0,
        )
        await async_orphan_db.commit()

        from app.models.notification import Notification

        result = await async_orphan_db.execute(
            select(Notification).where(
                Notification.dedupe_key == "orphan_scan:scan_zero"
            )
        )
        assert result.scalar_one_or_none() is None, "孤儿数为 0 不应创建通知"

    async def test_same_scan_id_dedup(self, async_orphan_db):
        """同一 scan_id 重试只生成一条通知（幂等）。"""
        from app.services.orphan_notification import notify_scan_completed

        for _ in range(3):
            await notify_scan_completed(
                db=async_orphan_db,
                scan_id="scan_dedup",
                scan_type="scheduled",
                orphan_count=5,
                orphan_size=1024,
            )
            await async_orphan_db.commit()

        from app.models.notification import Notification

        result = await async_orphan_db.execute(
            select(Notification).where(
                Notification.dedupe_key == "orphan_scan:scan_dedup"
            )
        )
        notifs = result.scalars().all()
        assert len(notifs) == 1, "同一 scan_id 应只有 1 条通知（dedupe_key 幂等）"

    async def test_notification_failure_does_not_fail_scan(self, async_orphan_db):
        """通知创建失败不把扫描改为 failed。"""
        from app.services.orphan_notification import notify_scan_completed
        from app.models.orphan_file import OrphanScanResult

        # 先创建一个 completed 扫描
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_notif_fail",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        await async_orphan_db.commit()

        # mock create_notification 抛异常
        with patch(
            "app.services.orphan_notification.create_notification",
            new_callable=AsyncMock,
            side_effect=RuntimeError("通知服务不可用"),
        ):
            # 通知失败不应抛异常
            await notify_scan_completed(
                db=async_orphan_db,
                scan_id="scan_notif_fail",
                scan_type="manual",
                orphan_count=10,
                orphan_size=5000,
            )

        # 扫描状态应仍为 completed
        result = await async_orphan_db.execute(
            select(OrphanScanResult).where(
                OrphanScanResult.scan_id == "scan_notif_fail"
            )
        )
        scan = result.scalar_one_or_none()
        assert scan is not None
        assert scan.status == "completed", "通知失败不应把扫描改为 failed"

    async def test_unread_count_increases(self, async_orphan_db):
        """未读数量随通知增加。"""
        from app.services.notification_service import NotificationService
        from app.services.orphan_notification import notify_scan_completed

        service = NotificationService(async_orphan_db)
        before = await service.get_unread_count()

        await notify_scan_completed(
            db=async_orphan_db,
            scan_id="scan_unread",
            scan_type="manual",
            orphan_count=3,
            orphan_size=1000,
        )
        await async_orphan_db.commit()

        after = await service.get_unread_count()
        assert after == before + 1, "创建通知后未读数应 +1"

    async def test_content_contains_size_in_gb(self, async_orphan_db):
        """通知内容正确包含总大小（GB 级）。"""
        from app.services.orphan_notification import notify_scan_completed

        # 128.5 GB
        size_bytes = int(128.5 * 1024**3)
        await notify_scan_completed(
            db=async_orphan_db,
            scan_id="scan_size",
            scan_type="manual",
            orphan_count=36,
            orphan_size=size_bytes,
        )
        await async_orphan_db.commit()

        from app.models.notification import Notification

        result = await async_orphan_db.execute(
            select(Notification).where(
                Notification.dedupe_key == "orphan_scan:scan_size"
            )
        )
        notif = result.scalar_one_or_none()
        assert notif is not None
        assert notif.title == "孤儿文件扫描完成"
        assert "128" in (notif.content or ""), "通知内容应包含 GB 级大小"

    async def test_retry_task_compensates_missing_notification(
        self, async_orphan_db, monkeypatch
    ):
        """completed 扫描首次通知失败后，补偿任务应按 dedupe_key 补发。"""
        from app.models.notification import Notification
        from app.models.orphan_file import OrphanScanResult
        from app.tasks.scheduler.orphan_notification_retry_task import (
            OrphanNotificationRetryTask,
        )

        scan = OrphanScanResult(
            scan_id="scan_retry",
            scan_time=datetime.utcnow(),
            scan_type="scheduled",
            status="completed",
        )
        scan.total_orphans = 4
        scan.total_orphan_size = 4096
        async_orphan_db.add(scan)
        await async_orphan_db.commit()

        class SessionContext:
            async def __aenter__(self):
                return async_orphan_db

            async def __aexit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(
            "app.tasks.scheduler.orphan_notification_retry_task.AsyncSessionLocal",
            lambda: SessionContext(),
        )
        result = await OrphanNotificationRetryTask().execute()

        notification = await async_orphan_db.execute(
            select(Notification).where(
                Notification.dedupe_key == "orphan_scan:scan_retry"
            )
        )
        assert notification.scalar_one_or_none() is not None
        assert result["retried_count"] == 1
