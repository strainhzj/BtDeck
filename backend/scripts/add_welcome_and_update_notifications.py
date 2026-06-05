#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
添加欢迎通知和版本更新通知

使用方法:
    python scripts/add_welcome_and_update_notifications.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from sqlalchemy import select
from app.database import get_db
from app.models.notification import Notification


# v1.0.4 版本更新说明（基于 git diff v1.0.3..dev）
VERSION_104_CONTENT = """
## BtDeck v1.0.4 版本更新

### 核心新功能

**1. 通知中心**
- 新增完整的通知管理系统，支持版本更新和系统消息
- 通知列表支持分页查询、按类型筛选（全部/未读/更新/系统）
- 支持标记已读/未读、全部已读、删除通知等操作
- 点击通知条目弹出详情弹窗，支持 Markdown 内容渲染
- 自动检查 GitHub Release 版本更新并推送通知
- 60秒轮询未读通知数量，实时更新角标

**2. 实时速度监控**
- 种子列表新增独立的下载速度和上传速度列
- 下载速度显示 ▼ 图标，上传速度显示 ▲ 图标
- 活跃种子（有速度的种子）自动排序到列表顶部
- 新增专用 API 接口获取活跃种子状态

**3. 活动种子筛选**
- 新增"仅显示活动种子"复选框筛选功能
- 快速筛选出正在下载/上传的种子
- 与现有搜索条件组合使用

**4. 手动刷新功能**
- 种子列表新增手动刷新按钮
- 支持加载状态显示，避免重复点击

### 界面优化

**5. 导航栏优化**
- 导航栏顶部 UI 布局优化
- 新增用户反馈按钮，方便用户提交问题

**6. 种子列表改进**
- 修复种子列表页面样式失效问题
- 优化进度条实时更新逻辑
- 改进种子状态图标显示

### 技术改进

**7. 性能优化**
- qBittorrent 速度接口使用 status_filter 参数减少数据传输
- 修复种子速度监控的线程池泄漏问题
- 优化定时器清理机制，避免内存泄漏

**8. 开发基础设施**
- 新增 Harness 开发基础设施，规范开发流程
- 添加开发约束文档，确保代码质量
- 完善 TypeScript 类型定义

**9. Bug 修复**
- 修复下载队列状态图标显示为问号的问题
- 修复生产环境 API 路径配置问题
- 修复类型安全和定时器清理问题
- 修正活跃种子速度接口单位注释

### API 变更

**新增接口：**
- `GET /api/v1/torrents/active-torrents` - 获取活跃种子列表
- `GET /api/v1/notifications` - 获取通知列表
- `GET /api/v1/notifications/unread-count` - 获取未读通知数量
- `PUT /api/v1/notifications/mark-read` - 标记通知已读
- `PUT /api/v1/notifications/mark-unread` - 标记通知未读
- `PUT /api/v1/notifications/read-all` - 全部标记已读
- `DELETE /api/v1/notifications/{id}` - 删除通知

**数据库变更：**
- 新增 `notification` 表，用于存储系统通知

---
感谢您使用 BtDeck！如有问题或建议，请通过导航栏的反馈按钮提交。
"""


async def add_notifications():
    """添加通知到数据库"""

    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # 检查通知是否已存在
        existing_welcome = await db.execute(
            select(Notification).where(Notification.title == "欢迎使用 BtDeck")
        )
        if existing_welcome.scalar_one_or_none():
            print("[!] 欢迎通知已存在，跳过创建")
            return

        existing_version = await db.execute(
            select(Notification).where(Notification.title == "BtDeck v1.0.4 版本更新")
        )
        if existing_version.scalar_one_or_none():
            print("[!] 版本更新通知已存在，跳过创建")
            return

        # 1. 创建欢迎通知
        welcome_notification = Notification(
            type="system",
            title="欢迎使用 BtDeck",
            content="感谢您使用 BtDeck！这是您的第一条系统通知。通知中心会在这里显示版本更新和系统消息。",
            priority="info",
            is_read=False,
            extra_data=None,
            created_at=datetime.utcnow()
        )
        db.add(welcome_notification)
        await db.commit()
        await db.refresh(welcome_notification)
        print(f"[OK] 欢迎通知创建成功 (ID: {welcome_notification.id})")

        # 2. 创建版本更新通知
        version_notification = Notification(
            type="version_update",
            title="BtDeck v1.0.4 版本更新",
            content=VERSION_104_CONTENT,
            priority="info",
            is_read=False,
            extra_data={
                "version": "1.0.4",
                "previous_version": "1.0.3",
                "release_url": "https://github.com/StrainThomas/BtDeck/releases/tag/v1.0.4"
            },
            created_at=datetime.utcnow()
        )
        db.add(version_notification)
        await db.commit()
        await db.refresh(version_notification)
        print(f"[OK] 版本更新通知创建成功 (ID: {version_notification.id})")

        print("\n[SUCCESS] 通知添加完成！")
        print(f"   - 欢迎通知: ID={welcome_notification.id}")
        print(f"   - 版本更新: ID={version_notification.id}")


if __name__ == "__main__":
    print("[START] 开始添加通知...\n")
    asyncio.run(add_notifications())
