# -*- coding: utf-8 -*-
"""
孤儿文件扫描完成通知（v1.0.6+ 语义重做）

扫描完成并提交批次及生命周期对账后：
1. 如果 total_orphans == 0，结束（不通知）
2. 使用 dedupe_key=orphan_scan:{scan_id} 创建通知（幂等）
3. 通知失败只记录错误，不回滚成功扫描

通知规范：
  type: system
  priority: warning
  title: 孤儿文件扫描完成
  content: 本次扫描发现 N 个孤儿文件，共 X GB，请前往孤儿文件管理页面查看。
  extra_data: {event, scan_id, scan_type, orphan_count, orphan_size, route}
  dedupe_key: orphan_scan:{scan_id}

@file: orphan_notification.py
@time: 2026-07-11
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

NOTIF_TITLE = "孤儿文件扫描完成"
NOTIF_ROUTE = "/orphan-files/index"
NOTIF_EVENT = "orphan_scan_completed"


def _format_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读的大小（GB/MB/KB）。"""
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024 ** 3):.1f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


async def create_notification(
    db: AsyncSession,
    type: str,
    title: str,
    content: Optional[str] = None,
    priority: str = "info",
    extra_data: Optional[Dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> Notification:
    """模块级通知创建便捷函数（委托 NotificationService）。

    暴露为模块级以便测试 mock（patch app.services.orphan_notification.create_notification）。
    """
    service = NotificationService(db)
    return await service.create_notification(
        type=type,
        title=title,
        content=content,
        priority=priority,
        extra_data=extra_data,
        dedupe_key=dedupe_key,
    )


async def notify_scan_completed(
    db: AsyncSession,
    scan_id: str,
    scan_type: str,
    orphan_count: int,
    orphan_size: int,
) -> Optional[Notification]:
    """扫描完成后创建通知（幂等，失败不回滚）。

    语义：
    - orphan_count == 0 → 不通知，返回 None
    - orphan_count > 0 → 用 dedupe_key=orphan_scan:{scan_id} 创建通知
    - 通知创建失败（含去重命中）只记 error，不抛异常（不回滚成功扫描）

    Args:
        db: 异步 DB session
        scan_id: 扫描批次 ID
        scan_type: 扫描类型（manual/scheduled）
        orphan_count: 孤儿文件数量
        orphan_size: 孤儿文件总大小（字节）

    Returns:
        创建的通知对象（orphan_count==0 或失败时返回 None）
    """
    # 1. orphan_count == 0 → 结束
    if orphan_count == 0:
        logger.debug(f"[孤儿通知] scan_id={scan_id} 孤儿数为 0，不创建通知")
        return None

    dedupe_key = f"orphan_scan:{scan_id}"
    size_str = _format_size(orphan_size)
    content = f"本次扫描发现 {orphan_count} 个孤儿文件，共 {size_str}，请前往孤儿文件管理页面查看。"

    extra_data = {
        "event": NOTIF_EVENT,
        "scan_id": scan_id,
        "scan_type": scan_type,
        "orphan_count": orphan_count,
        "orphan_size": orphan_size,
        "route": NOTIF_ROUTE,
    }

    try:
        notif = await create_notification(
            db=db,
            type="system",
            title=NOTIF_TITLE,
            content=content,
            priority="warning",
            extra_data=extra_data,
            dedupe_key=dedupe_key,
        )
        logger.info(f"[孤儿通知] scan_id={scan_id} 通知已创建: {orphan_count} 个孤儿，共 {size_str}")
        return notif
    except Exception as e:
        # 通知失败只记录错误，不回滚成功扫描（幂等重试时 DB 唯一约束兜底）
        logger.error(f"[孤儿通知] scan_id={scan_id} 通知创建失败: {e}", exc_info=True)
        return None
