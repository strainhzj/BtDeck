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
from app.services.orphan_purge_job_service import (
    OrphanPurgeJobService,
    get_orphan_purge_dispatcher,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["孤儿文件管理"])


# ========== 请求/响应模型 ==========


class CleanupRequest(BaseModel):
    """清理请求模型"""

    scan_id: str = Field(..., min_length=1, description="预览与清理绑定的扫描批次ID")
    orphan_ids: List[int] = Field(..., description="孤儿文件ID列表")


class IgnoreRequest(BaseModel):
    """忽视请求模型"""

    scan_id: Optional[str] = Field(default=None, description="绑定的扫描批次ID（限定操作范围）")
    orphan_ids: List[int] = Field(..., description="孤儿文件ID列表")
    ignored: bool = Field(..., description="True=设为忽视，False=取消忽视")


class QuarantineActionRequest(BaseModel):
    """隔离区操作请求模型（恢复 / 立即彻底删除）"""

    canonical_paths: List[str] = Field(..., min_length=1, description="隔离区候选规范化路径列表")


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
    page_size: int = Query(default=20, ge=1, le=100000, description="每页数量（最大 10 万，与前端页大小输入上限对齐）"),
    downloader_id: Optional[str] = Query(default=None, description="下载器ID筛选"),
    min_size: Optional[int] = Query(default=None, ge=0, description="最小文件大小（字节）"),
    path_like: Optional[str] = Query(default=None, description="文件路径模糊匹配"),
    status: Optional[str] = Query(
        default=None,
        description="状态筛选：pending=待清理，ignored=已忽视，deleted=已清理",
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """分页查询孤儿文件列表及同一响应快照中的扫描上下文。

    scan_context 区分最新扫描尝试、页面展示的成功批次、扫描原始统计与
    尚未清理的动态统计；最新 running 不回退，最新 failed 仅只读展示
    最近成功批次。支持按 下载器/路径/状态/大小 多条件筛选与分页。
    """
    try:
        service = OrphanFileService(db)
        result = await service.get_orphan_list(
            page=page,
            page_size=page_size,
            downloader_id=downloader_id,
            min_size=min_size,
            path_like=path_like,
            status=status,
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
    request: Request,
    req: CleanupRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """清理预览（返回选中文件的数和总大小）"""
    try:
        service = OrphanFileService(db)
        result = await service.cleanup_preview(req.orphan_ids, scan_id=req.scan_id)
        return CommonResponse(status="success", msg="预览成功", code="200", data=result)
    except Exception as e:
        logger.error(f"清理预览失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"预览失败: {e}", code="500", data=None)


@router.post("/cleanup", response_model=CommonResponse)
async def cleanup_orphans(
    request: Request,
    req: CleanupRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """手动清理选中的孤儿文件（安全隔离 + 审计日志）"""
    try:
        service = OrphanFileService(db)
        result = await service.cleanup_orphans(
            orphan_ids=req.orphan_ids,
            operator=current_user.username,
            audit_service=audit_service,
            store=request.app.state.store,
            scan_id=req.scan_id,
        )
        msg = f"清理完成: 成功 {result['success_count']} 个"
        if result["failed_count"] > 0:
            msg += f"，失败 {result['failed_count']} 个"
        return CommonResponse(status="success", msg=msg, code="200", data=result)
    except Exception as e:
        logger.error(f"手动清理孤儿文件失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"清理失败: {e}", code="500", data=None)


@router.post("/ignore", response_model=CommonResponse)
async def set_orphan_ignored(
    req: IgnoreRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """设置/取消孤儿文件的忽视态。

    被忽视的孤儿受保护：定时任务不自动删除，手动清理也被拒绝，但仍可在列表查询。
    """
    try:
        service = OrphanFileService(db)
        result = await service.set_ignored(
            orphan_ids=req.orphan_ids,
            ignored=req.ignored,
            operator=current_user.username,
            scan_id=req.scan_id,
        )
        action = "忽视" if req.ignored else "取消忽视"
        msg = f"{action}完成: 成功 {result['success_count']} 个"
        if result["failed_count"] > 0:
            msg += f"，失败 {result['failed_count']} 个"
        return CommonResponse(status="success", msg=msg, code="200", data=result)
    except Exception as e:
        logger.error(f"设置孤儿忽视态失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"操作失败: {e}", code="500", data=None)


@router.get("/quarantine", response_model=CommonResponse)
async def get_quarantine_list(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100000, description="每页数量"),
    downloader_id: Optional[str] = Query(default=None, description="下载器ID筛选"),
    path_like: Optional[str] = Query(default=None, description="文件路径模糊匹配"),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """查询隔离区文件列表（status=quarantined 的候选）。"""
    try:
        service = OrphanFileService(db)
        result = await service.get_quarantine_list(
            page=page,
            page_size=page_size,
            downloader_id=downloader_id,
            path_like=path_like,
        )
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error(f"查询隔离区列表失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


@router.post("/restore", response_model=CommonResponse)
async def restore_quarantined(
    req: QuarantineActionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """从隔离区恢复文件到原位置（mark_quarantined 的逆操作）。"""
    try:
        service = OrphanFileService(db)
        result = await service.restore_quarantined(
            canonical_paths=req.canonical_paths,
            operator=current_user.username,
            audit_service=audit_service,
        )
        msg = f"恢复完成: 成功 {result['restored_count']} 个"
        if result["failed_count"] > 0:
            msg += f"，失败 {result['failed_count']} 个"
        return CommonResponse(status="success", msg=msg, code="200", data=result)
    except Exception as e:
        logger.error(f"隔离区恢复失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"操作失败: {e}", code="500", data=None)


@router.post("/purge", response_model=CommonResponse)
async def purge_quarantine_now(
    request: Request,
    req: QuarantineActionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """提交隔离区彻底删除任务并立即返回，结果由通知中心异步送达。"""
    try:
        job = await OrphanPurgeJobService(db).create_job(
            canonical_paths=req.canonical_paths,
            operator=current_user.username,
        )
        get_orphan_purge_dispatcher(request.app).submit(str(job.task_id))
        return CommonResponse(
            status="success",
            msg="彻底删除任务已提交，完成后将发送通知",
            code="200",
            data=job.to_dict(),
        )
    except Exception as e:
        logger.error(f"提交隔离区彻底删除任务失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"任务提交失败: {e}", code="500", data=None)


@router.get("/purge-jobs/{task_id}", response_model=CommonResponse)
async def get_purge_job_status(
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """查询隔离区彻底删除任务状态。"""
    try:
        job = await OrphanPurgeJobService(db).get_job(task_id)
        if job is None:
            return CommonResponse(status="error", msg="任务不存在", code="404", data=None)
        return CommonResponse(status="success", msg="查询成功", code="200", data=job.to_dict())
    except Exception as e:
        logger.error(f"查询隔离区彻底删除任务失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)
