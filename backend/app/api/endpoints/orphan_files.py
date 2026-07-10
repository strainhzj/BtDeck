# -*- coding: utf-8 -*-
"""
孤儿文件管理 API 端点

提供孤儿文件的扫描触发、列表查询、清理预览、手动清理等接口。
认证统一使用 require_authenticated_user（v1.0.5-audit 后端认证统一）。
响应格式统一 CommonResponse，分页字段 total/page/pageSize/list。
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user
from app.database import get_async_db
from app.services.audit_service import AuditLogService, get_audit_service
from app.services.orphan_file_service import OrphanFileService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["孤儿文件管理"])


# ========== 请求/响应模型 ==========


class CleanupRequest(BaseModel):
    """清理请求模型"""

    orphan_ids: List[int] = Field(..., description="孤儿文件ID列表")


# ========== API 端点 ==========


@router.get("/latest", response_model=CommonResponse)
async def get_latest_scan(
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """获取最新扫描批次结果"""
    try:
        service = OrphanFileService(db)
        result = await service.get_latest_scan_result()
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error(f"获取最新扫描结果失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


@router.get("/list", response_model=CommonResponse)
async def get_orphan_list(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    downloader_id: Optional[str] = Query(default=None, description="下载器ID筛选"),
    min_size: Optional[int] = Query(default=None, ge=0, description="最小文件大小（字节）"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """分页查询孤儿文件列表"""
    try:
        service = OrphanFileService(db)
        result = await service.get_orphan_list(
            page=page,
            page_size=page_size,
            downloader_id=downloader_id,
            min_size=min_size,
        )
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error(f"查询孤儿文件列表失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


@router.post("/scan", response_model=CommonResponse)
async def trigger_manual_scan(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """手动触发孤儿文件扫描"""
    try:
        service = OrphanFileService(db)
        result = await service.trigger_scan(
            scan_type="manual",
            operator=current_user.username,
            app=request.app,
        )
        return CommonResponse(status="success", msg="扫描完成", code="200", data=result)
    except Exception as e:
        logger.error(f"手动扫描失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"扫描失败: {e}", code="500", data=None)


@router.post("/cleanup-preview", response_model=CommonResponse)
async def cleanup_preview(
    req: CleanupRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """清理预览（返回选中文件的数和总大小）"""
    try:
        service = OrphanFileService(db)
        result = await service.cleanup_preview(req.orphan_ids)
        return CommonResponse(status="success", msg="预览成功", code="200", data=result)
    except Exception as e:
        logger.error(f"清理预览失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"预览失败: {e}", code="500", data=None)


@router.post("/cleanup", response_model=CommonResponse)
async def cleanup_orphans(
    req: CleanupRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """手动清理选中的孤儿文件（物理删除 + 审计日志）"""
    try:
        service = OrphanFileService(db)
        result = await service.cleanup_orphans(
            orphan_ids=req.orphan_ids,
            operator=current_user.username,
            audit_service=audit_service,
        )
        msg = f"清理完成: 成功 {result['success_count']} 个"
        if result["failed_count"] > 0:
            msg += f"，失败 {result['failed_count']} 个"
        return CommonResponse(status="success", msg=msg, code="200", data=result)
    except Exception as e:
        logger.error(f"手动清理孤儿文件失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"清理失败: {e}", code="500", data=None)
