# -*- coding: utf-8 -*-
"""
通知 API 端点

提供通知列表查询、未读计数、标记已读等接口。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responseVO import CommonResponse
from app.database import get_async_db
from app.auth.dependencies import get_current_user
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=CommonResponse, summary="获取通知列表")
async def get_notifications(
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    type: Optional[str] = Query(None, description="通知类型过滤"),
    is_read: Optional[bool] = Query(None, description="是否已读过滤"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """分页获取通知列表"""
    try:
        service = NotificationService(db)
        result = await service.get_notifications(
            page=page,
            page_size=pageSize,
            type=type,
            is_read=is_read
        )
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error(f"获取通知列表失败: {e}")
        return CommonResponse(status="error", msg=f"查询失败: {str(e)}", code="500", data=None)


@router.get("/unread-count", response_model=CommonResponse, summary="获取未读通知数量")
async def get_unread_count(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """获取未读通知数量"""
    try:
        service = NotificationService(db)
        count = await service.get_unread_count()
        return CommonResponse(status="success", msg="查询成功", code="200", data={"count": count})
    except Exception as e:
        logger.error(f"获取未读数量失败: {e}")
        return CommonResponse(status="error", msg=f"查询失败: {str(e)}", code="500", data=None)


@router.put("/{notification_id}/read", response_model=CommonResponse, summary="标记通知为已读")
async def mark_as_read(
    notification_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """标记单条通知为已读"""
    try:
        service = NotificationService(db)
        success = await service.mark_as_read(notification_id)
        if success:
            return CommonResponse(status="success", msg="标记成功", code="200", data=None)
        return CommonResponse(status="error", msg="通知不存在", code="404", data=None)
    except Exception as e:
        logger.error(f"标记已读失败: {e}")
        return CommonResponse(status="error", msg=f"操作失败: {str(e)}", code="500", data=None)


@router.put("/read-all", response_model=CommonResponse, summary="全部标记为已读")
async def mark_all_as_read(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """标记所有通知为已读"""
    try:
        service = NotificationService(db)
        count = await service.mark_all_as_read()
        return CommonResponse(status="success", msg=f"已标记 {count} 条通知为已读", code="200", data={"count": count})
    except Exception as e:
        logger.error(f"全部已读失败: {e}")
        return CommonResponse(status="error", msg=f"操作失败: {str(e)}", code="500", data=None)


@router.delete("/{notification_id}", response_model=CommonResponse, summary="删除通知")
async def delete_notification(
    notification_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """删除单条通知"""
    try:
        service = NotificationService(db)
        success = await service.delete_notification(notification_id)
        if success:
            return CommonResponse(status="success", msg="删除成功", code="200", data=None)
        return CommonResponse(status="error", msg="通知不存在", code="404", data=None)
    except Exception as e:
        logger.error(f"删除通知失败: {e}")
        return CommonResponse(status="error", msg=f"操作失败: {str(e)}", code="500", data=None)
