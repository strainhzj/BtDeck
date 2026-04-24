# -*- coding: utf-8 -*-
"""
通知服务

提供通知的 CRUD 操作和版本更新检查逻辑。
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """通知服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_notifications(
        self,
        page: int = 1,
        page_size: int = 20,
        type: Optional[str] = None,
        is_read: Optional[bool] = None
    ) -> Dict[str, Any]:
        """分页获取通知列表"""
        query = select(Notification).order_by(Notification.created_at.desc())
        count_query = select(func.count(Notification.id))

        if type is not None:
            query = query.where(Notification.type == type)
            count_query = count_query.where(Notification.type == type)
        if is_read is not None:
            query = query.where(Notification.is_read == is_read)
            count_query = count_query.where(Notification.is_read == is_read)

        # 总数
        total = (await self.db.execute(count_query)).scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await self.db.execute(query)
        notifications = result.scalars().all()

        return {
            "total": total,
            "page": page,
            "pageSize": page_size,
            "list": [n.to_dict() for n in notifications]
        }

    async def get_unread_count(self) -> int:
        """获取未读通知数量"""
        query = select(func.count(Notification.id)).where(Notification.is_read == False)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def mark_as_read(self, notification_id: int) -> bool:
        """标记单条通知为已读"""
        stmt = (
            update(Notification)
            .where(Notification.id == notification_id)
            .values(is_read=True, read_at=datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def mark_all_as_read(self) -> int:
        """标记所有通知为已读"""
        stmt = (
            update(Notification)
            .where(Notification.is_read == False)
            .values(is_read=True, read_at=datetime.utcnow())
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def delete_notification(self, notification_id: int) -> bool:
        """删除单条通知"""
        stmt = delete(Notification).where(Notification.id == notification_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def create_notification(
        self,
        type: str,
        title: str,
        content: Optional[str] = None,
        priority: str = 'info',
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """创建通知"""
        notification = Notification(
            type=type,
            title=title,
            content=content,
            priority=priority,
            extra_data=extra_data
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def check_version_update(self, current_version: str, github_repo: str = "StrainThomas/BtDeck") -> Optional[Notification]:
        """
        检查 GitHub Release 是否有新版本，如有则创建通知。

        Args:
            current_version: 当前版本号（如 "1.0.3"）
            github_repo: GitHub 仓库（owner/repo 格式）

        Returns:
            如果有新版本且通知创建成功，返回 Notification 对象；否则返回 None
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{github_repo}/releases/latest",
                    headers={"Accept": "application/vnd.github+json"}
                )

                if resp.status_code != 200:
                    logger.debug(f"GitHub API 返回 {resp.status_code}，跳过版本检查")
                    return None

                release = resp.json()
                latest_tag = release.get("tag_name", "").lstrip("v")

                if not latest_tag:
                    return None

                # 比较版本号（简单字符串比较，适用于语义化版本）
                if latest_tag <= current_version:
                    return None

                # 检查是否已存在相同版本的通知（通过 title 去重）
                existing = await self.db.execute(
                    select(Notification).where(
                        Notification.type == "version_update",
                        Notification.title == f"BtDeck v{latest_tag} 版本更新"
                    )
                )
                if existing.scalar_one_or_none():
                    logger.debug(f"版本 {latest_tag} 通知已存在，跳过")
                    return None

                # 创建版本更新通知
                release_url = release.get("html_url", "")
                release_body = release.get("body", "")[:500]  # 截取前500字符

                notification = await self.create_notification(
                    type="version_update",
                    title=f"BtDeck v{latest_tag} 版本更新",
                    content=release_body,
                    priority="info",
                    extra_data={
                        "version": latest_tag,
                        "current_version": current_version,
                        "release_url": release_url,
                        "published_at": release.get("published_at", "")
                    }
                )
                logger.info(f"已创建版本更新通知: v{latest_tag}")
                return notification

        except Exception as e:
            logger.warning(f"版本更新检查失败: {e}")
            return None
