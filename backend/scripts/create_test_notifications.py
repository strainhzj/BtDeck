# -*- coding: utf-8 -*-
"""
创建测试通知数据

运行方式：
    cd BtDeck
    python scripts/create_test_notifications.py
"""

import asyncio
from datetime import datetime, timedelta
from app.database import AsyncSessionLocal
from app.models.notification import Notification


async def create_test_notifications():
    """创建测试通知数据"""

    async with AsyncSessionLocal() as db:
        # 清空现有通知（可选）
        # from sqlalchemy import delete
        # await db.execute(delete(Notification))
        # await db.commit()

        # 测试数据列表
        test_notifications = [
            {
                "type": "version_update",
                "title": "BtDeck v1.1.0 版本更新",
                "content": "新版本包含以下改进：\n- 新增通知中心功能\n- 优化下载器连接稳定性\n- 修复种子列表排序问题",
                "priority": "info",
                "is_read": False,
                "extra_data": {
                    "version": "1.1.0",
                    "current_version": "1.0.4",
                    "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.1.0",
                    "published_at": "2026-04-24T10:00:00Z"
                },
                "created_at": datetime.utcnow() - timedelta(hours=2)
            },
            {
                "type": "system",
                "title": "系统维护通知",
                "content": "系统将于 2026-04-25 凌晨 2:00-4:00 进行服务器维护，届时服务可能短暂中断。",
                "priority": "warning",
                "is_read": False,
                "extra_data": None,
                "created_at": datetime.utcnow() - timedelta(hours=5)
            },
            {
                "type": "system",
                "title": "下载器连接异常",
                "content": "检测到 qBittorrent 下载器连接超时，请检查网络连接或下载器配置。",
                "priority": "error",
                "is_read": False,
                "extra_data": {
                    "downloader": "qBittorrent",
                    "error_code": "TIMEOUT"
                },
                "created_at": datetime.utcnow() - timedelta(days=1)
            },
            {
                "type": "version_update",
                "title": "BtDeck v1.0.5 版本更新",
                "content": "修复了种子速度监控的线程泄漏问题，建议所有用户升级。",
                "priority": "info",
                "is_read": True,
                "extra_data": {
                    "version": "1.0.5",
                    "current_version": "1.0.4",
                    "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.0.5"
                },
                "created_at": datetime.utcnow() - timedelta(days=2),
                "read_at": datetime.utcnow() - timedelta(days=1)
            },
            {
                "type": "system",
                "title": "欢迎使用 BtDeck",
                "content": "感谢您使用 BtDeck！这是您的第一条系统通知。通知中心会在这里显示版本更新和系统消息。",
                "priority": "info",
                "is_read": True,
                "extra_data": None,
                "created_at": datetime.utcnow() - timedelta(days=3),
                "read_at": datetime.utcnow() - timedelta(days=2)
            },
            {
                "type": "system",
                "title": "数据备份完成",
                "content": "定时任务：种子配置数据已自动备份完成。",
                "priority": "info",
                "is_read": False,
                "extra_data": {
                    "backup_type": "auto",
                    "backup_size": "2.5MB"
                },
                "created_at": datetime.utcnow() - timedelta(minutes=30)
            },
            {
                "type": "version_update",
                "title": "BtDeck v1.0.4 版本更新",
                "content": "新增实时速度监控功能，支持 qBittorrent 和 Transmission。",
                "priority": "info",
                "is_read": True,
                "extra_data": {
                    "version": "1.0.4",
                    "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.0.4"
                },
                "created_at": datetime.utcnow() - timedelta(days=5),
                "read_at": datetime.utcnow() - timedelta(days=4)
            },
            {
                "type": "system",
                "title": "API 密钥即将过期",
                "content": "您的 API 密钥将在 7 天后过期，请及时更新以避免服务中断。",
                "priority": "warning",
                "is_read": False,
                "extra_data": {
                    "expire_date": "2026-05-01"
                },
                "created_at": datetime.utcnow() - timedelta(hours=12)
            }
        ]

        # 创建通知记录
        import json

        for data in test_notifications:
            notification = Notification(
                type=data["type"],
                title=data["title"],
                content=data["content"],
                priority=data["priority"],
                is_read=data["is_read"],
                extra_data=json.dumps(data["extra_data"], ensure_ascii=False) if data["extra_data"] else None
            )
            # 手动设置 created_at 和 read_at
            if "created_at" in data:
                notification.created_at = data["created_at"]
            if "read_at" in data:
                notification.read_at = data["read_at"]

            db.add(notification)

        await db.commit()

        unread_count = sum(1 for n in test_notifications if not n['is_read'])
        read_count = sum(1 for n in test_notifications if n['is_read'])
        version_count = sum(1 for n in test_notifications if n['type'] == 'version_update')
        system_count = sum(1 for n in test_notifications if n['type'] == 'system')

        print(f"[OK] Successfully created {len(test_notifications)} test notifications")
        print(f"   - Unread: {unread_count}")
        print(f"   - Read: {read_count}")
        print(f"   - Version updates: {version_count}")
        print(f"   - System notifications: {system_count}")


if __name__ == "__main__":
    print("=== 创建测试通知数据 ===")
    asyncio.run(create_test_notifications())
