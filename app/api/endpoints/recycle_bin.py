"""
回收站API端点

提供回收站的列表查询、种子还原、清理预览、手动清理等API接口。
支持基础还原和手动补充还原（带文件上传）。
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, Request
from pydantic import BaseModel, Field

from app.api.responseVO import CommonResponse
from app.database import get_async_db
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.services.recycle_bin_service import RecycleBinService
from app.services.audit_service import get_audit_service, AuditLogService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(tags=["回收站管理"])


# ========== 请求/响应模型 ==========


class RestoreRequest(BaseModel):
    """还原请求模型"""
    torrent_ids: List[str] = Field(..., description="种子ID列表")


class CleanupPreviewRequest(BaseModel):
    """清理预览请求模型"""
    days: int = Field(default=30, ge=1, le=365, description="天数（清理N天前的数据）")


class CleanupRequest(BaseModel):
    """手动清理请求模型"""
    torrent_ids: List[str] = Field(..., description="种子ID列表")


class ManualRestoreRequest(BaseModel):
    """手动补充还原请求模型"""
    torrent_ids: List[str] = Field(..., description="种子ID列表")


# ========== API端点 ==========


@router.get("/bin", response_model=CommonResponse)
async def get_recycle_bin_list(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(default=None, description="搜索关键词"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)
):
    """
    查询回收站列表

    查询所有deleted_at不为NULL且dr=0的种子记录，支持分页和搜索。

    Args:
        page: 页码（从1开始）
        page_size: 每页数量
        search: 搜索关键词（按名称搜索）
        db: 数据库会话
        current_user: 当前用户

    Returns:
        CommonResponse: 包含分页数据的响应
        {
            "code": "200",
            "msg": "查询成功",
            "data": {
                "total": int,
                "page": int,
                "pageSize": int,
                "list": List[Dict]
            },
            "status": "success"
        }
    """
    try:
        service = RecycleBinService(db)
        result = service.get_recycle_bin_list(
            page=page,
            page_size=page_size,
            search=search
        )

        return CommonResponse(
            status="success",
            msg="查询成功",
            code="200",
            data=result
        )

    except Exception as e:
        logger.error(f"查询回收站列表失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"查询失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/restore", response_model=CommonResponse)
async def restore_torrents(
    req: RestoreRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    audit_service: AuditLogService = Depends(get_audit_service)
):
    """
    批量还原种子

    从回收站还原种子到下载器，包括：
    1. 删除.waiting-delete标记文件
    2. 重新添加种子到下载器
    3. 清除deleted_at字段
    4. 记录审计日志

    Args:
        request: 还原请求
        db: 数据库会话
        current_user: 当前用户
        audit_service: 审计日志服务

    Returns:
        CommonResponse: 包含还原结果的响应
        {
            "code": "200",
            "msg": "还原完成",
            "data": {
                "success_count": int,
                "failed_count": int,
                "skipped_count": int,
                "success_list": List[Dict],
                "failed_list": List[Dict]
            },
            "status": "success"
        }
    """
    try:
        service = RecycleBinService(db)

        result = await service.restore_torrents(
            torrent_ids=req.torrent_ids,
            operator=current_user.username,
            audit_service=audit_service,
            request=request
        )

        # 根据结果确定消息
        if result["failed_count"] == 0:
            msg = f"还原成功：共{result['success_count']}个种子"
        elif result["success_count"] == 0:
            msg = f"还原失败：共{result['failed_count']}个种子"
        else:
            msg = f"还原部分成功：成功{result['success_count']}个，失败{result['failed_count']}个"

        return CommonResponse(
            status="success",
            msg=msg,
            code="200",
            data=result
        )

    except Exception as e:
        logger.error(f"还原种子失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"还原失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/restore-manual", response_model=CommonResponse)
async def restore_torrents_with_file(
    torrent_id: str = Form(..., description="种子ID"),
    torrent_file: UploadFile = File(..., description="种子文件"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    audit_service: AuditLogService = Depends(get_audit_service)
):
    """
    手动补充还原（单个种子，带文件上传）

    当种子文件备份不存在时，允许用户手动上传种子文件进行还原。

    Args:
        torrent_id: 种子ID
        torrent_file: 用户上传的种子文件
        db: 数据库会话
        current_user: 当前用户
        audit_service: 审计日志服务

    Returns:
        CommonResponse: 还原结果
    """
    try:
        # TODO: 实现手动文件上传还原逻辑
        # 1. 保存上传的文件到临时位置
        # 2. 调用restore_torrents逻辑
        # 3. 更新backup_file_path字段

        return CommonResponse(
            status="error",
            msg="功能开发中，请稍后再试",
            code="501",
            data=None
        )

    except Exception as e:
        logger.error(f"手动还原失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"手动还原失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/cleanup-preview", response_model=CommonResponse)
async def cleanup_preview(
    request: CleanupPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(get_current_user)
):
    """
    清理预览

    查询指定天数之前的回收站种子，计算总大小，用于清理前确认。

    Args:
        request: 清理预览请求
        db: 数据库会话
        current_user: 当前用户

    Returns:
        CommonResponse: 包含预览数据的响应
        {
            "code": "200",
            "msg": "预览成功",
            "data": {
                "total_count": int,
                "total_size": int,
                "torrent_list": List[Dict]
            },
            "status": "success"
        }
    """
    try:
        service = RecycleBinService(db)
        result = service.cleanup_preview(days=request.days)

        return CommonResponse(
            status="success",
            msg=f"预览成功：共{result['total_count']}个种子，总大小{result['total_size']}字节",
            code="200",
            data=result
        )

    except Exception as e:
        logger.error(f"清理预览失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"预览失败: {str(e)}",
            code="500",
            data=None
        )


@router.post("/cleanup", response_model=CommonResponse)
async def manual_cleanup(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
    audit_service: AuditLogService = Depends(get_audit_service)
):
    """
    手动清理回收站种子

    永久删除回收站中的种子记录，包括：
    1. 删除.waiting-delete标记文件（降级处理）
    2. 设置dr=1（逻辑删除）
    3. 记录审计日志

    Args:
        request: 清理请求
        db: 数据库会话
        current_user: 当前用户
        audit_service: 审计日志服务

    Returns:
        CommonResponse: 包含清理结果的响应
        {
            "code": "200",
            "msg": "清理成功",
            "data": {
                "success_count": int,
                "failed_count": int,
                "success_list": List[Dict],
                "failed_list": List[Dict]
            },
            "status": "success"
        }
    """
    try:
        service = RecycleBinService(db)

        result = await service.manual_cleanup(
            torrent_ids=request.torrent_ids,
            operator=current_user.username,
            audit_service=audit_service
        )

        # 根据结果确定消息
        if result["failed_count"] == 0:
            msg = f"清理成功：共{result['success_count']}个种子"
        elif result["success_count"] == 0:
            msg = f"清理失败：共{result['failed_count']}个种子"
        else:
            msg = f"清理部分成功：成功{result['success_count']}个，失败{result['failed_count']}个"

        return CommonResponse(
            status="success",
            msg=msg,
            code="200",
            data=result
        )

    except Exception as e:
        logger.error(f"清理回收站失败: {str(e)}", exc_info=True)
        return CommonResponse(
            status="error",
            msg=f"清理失败: {str(e)}",
            code="500",
            data=None
        )
