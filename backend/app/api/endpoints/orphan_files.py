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
from app.services.audit_service import AuditLogService, extract_audit_info_from_request, get_audit_service
from app.services.orphan_file_service import OrphanFileService
from app.services.orphan_purge_job_service import (
    OrphanPurgeJobService,
    get_orphan_purge_dispatcher,
)
from app.services.orphan_scan_job_service import (
    OrphanScanJobService,
    get_orphan_scan_dispatcher,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["孤儿文件管理"])


# ========== 请求/响应模型 ==========


class OrphanSelectionFilters(BaseModel):
    """“全选当前筛选”使用的列表过滤快照。"""

    downloader_id: Optional[str] = Field(default=None, description="下载器ID筛选（支持逗号分隔多值）")
    min_size: Optional[int] = Field(default=None, ge=0)
    path_like: Optional[str] = None
    path_prefix: Optional[str] = Field(default=None, description="文件路径左匹配（LIKE prefix%）")
    status: Optional[str] = Field(
        default=None,
        description="状态筛选（支持逗号分隔多值，OR 并集）：pending/ignored/deleted",
    )
    confidence: Optional[str] = Field(default=None, description="置信度筛选（支持逗号分隔多值）：high/low")
    hardlink_copies: Optional[str] = Field(
        default=None,
        description="副本筛选快照：located=仅选择有硬链接副本的文件（与列表筛选项同口径）",
    )


class OrphanSelectionRequest(BaseModel):
    """显式 ID 或当前筛选全集选择。"""

    orphan_ids: List[int] = Field(default_factory=list, description="显式选择的孤儿文件ID列表")
    select_all: bool = Field(default=False, description="是否选择当前筛选条件下的全部结果")
    excluded_orphan_ids: List[int] = Field(
        default_factory=list,
        description="全选后由用户取消勾选的孤儿文件ID",
    )
    filters: Optional[OrphanSelectionFilters] = Field(default=None, description="全选时绑定的筛选快照")


class CleanupRequest(OrphanSelectionRequest):
    """清理请求模型"""

    scan_id: str = Field(..., min_length=1, description="预览与清理绑定的扫描批次ID")


class IgnoreRequest(OrphanSelectionRequest):
    """忽视请求模型"""

    scan_id: Optional[str] = Field(default=None, description="绑定的扫描批次ID（限定操作范围）")
    ignored: bool = Field(..., description="True=设为忽视，False=取消忽视")


class PrefixMatchPreviewRequest(BaseModel):
    """左匹配（前缀）预览请求模型"""

    path_prefix: str = Field(..., min_length=1, description="文件路径左匹配前缀")
    scan_id: str = Field(..., min_length=1, description="绑定的扫描批次ID")
    hardlink_copies: Optional[str] = Field(
        default=None,
        description="副本筛选快照：located=预览范围限定有硬链接副本的文件（与列表筛选同口径）",
    )


class QuarantineActionRequest(BaseModel):
    """隔离区操作请求模型（恢复 / 立即彻底删除）"""

    canonical_paths: List[str] = Field(..., min_length=1, description="隔离区候选规范化路径列表")


class HardlinkCopyLocationsRequest(BaseModel):
    """按孤儿明细 ID 批量定位硬链接副本位置。"""

    orphan_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="需要定位副本位置的孤儿文件 ID（文件夹行展开后批量提交）",
    )


class HardlinkCopyDeleteRequest(BaseModel):
    """删除已定位硬链接副本的目录项（仅移除该路径链接，源文件与数据保留）。"""

    orphan_id: int = Field(..., description="副本所属孤儿文件 ID（弹窗条目）")
    copy_paths: List[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="要删除的副本路径（必须与弹窗展示的预扫描结果路径完全一致）",
    )


class OrphanGuardrailReviewRequest(BaseModel):
    """兼容旧客户端的超量扫描复核记录请求。"""

    confirmed_path_mapping: bool = Field(..., description="兼容旧客户端的路径映射确认")
    confirmed_orphan_samples: bool = Field(..., description="兼容旧客户端的孤儿样本确认")
    note: str = Field(..., min_length=8, max_length=2000, description="兼容旧客户端的复核说明")


async def _resolve_selection(
    service: OrphanFileService,
    req: OrphanSelectionRequest,
    *,
    scan_id: Optional[str],
) -> List[int]:
    """把请求选择语义解析为提交时的稳定 ID 快照。"""
    filters = req.filters or OrphanSelectionFilters()
    return await service.resolve_orphan_selection(
        orphan_ids=req.orphan_ids,
        select_all=req.select_all,
        excluded_orphan_ids=req.excluded_orphan_ids,
        scan_id=scan_id,
        downloader_id=filters.downloader_id,
        min_size=filters.min_size,
        path_like=filters.path_like,
        path_prefix=filters.path_prefix,
        status=filters.status,
        confidence=filters.confidence,
        hardlink_copies=filters.hardlink_copies,
    )


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


@router.get("/scans/{scan_id}", response_model=CommonResponse)
async def get_scan_status(
    scan_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """查询单个后台扫描的轻量状态；不读取孤儿明细。"""
    try:
        result = await OrphanScanJobService(db).get_scan(scan_id)
        if result is None:
            return CommonResponse(status="error", msg="扫描任务不存在", code="404", data=None)
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error("查询孤儿扫描状态失败 scan_id=%s: %s", scan_id, e, exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


@router.post("/scans/{scan_id}/guardrail-review", response_model=CommonResponse)
async def review_scan_guardrail(
    scan_id: str,
    req: OrphanGuardrailReviewRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """兼容旧客户端记录超量扫描复核；当前超量提醒不再阻断清理。"""
    try:
        if not req.confirmed_path_mapping or not req.confirmed_orphan_samples:
            raise ValueError("必须同时完成路径映射核查和孤儿样本核查")
        result = await OrphanScanJobService(db).review_guardrail(
            scan_id=scan_id,
            operator=current_user.username,
            note=req.note,
        )
        return CommonResponse(status="success", msg="安全护栏复核完成", code="200", data=result)
    except ValueError as e:
        return CommonResponse(status="error", msg=str(e), code="400", data=None)
    except Exception as e:
        logger.error("复核孤儿扫描护栏失败 scan_id=%s: %s", scan_id, e, exc_info=True)
        return CommonResponse(status="error", msg=f"复核失败: {e}", code="500", data=None)


@router.get("/list", response_model=CommonResponse)
async def get_orphan_list(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(
        default=20,
        ge=1,
        le=1000,
        description="每批加载数量（最大 1000，避免超大响应阻塞列表）",
    ),
    downloader_id: Optional[str] = Query(default=None, description="下载器ID筛选（支持逗号分隔多值）"),
    min_size: Optional[int] = Query(default=None, ge=0, description="最小文件大小（字节）"),
    path_like: Optional[str] = Query(default=None, description="文件路径模糊匹配（包含）"),
    path_prefix: Optional[str] = Query(default=None, description="文件路径左匹配（前缀）"),
    status: Optional[str] = Query(
        default=None,
        description=(
            "状态筛选（支持逗号分隔多值，OR 并集）："
            "pending=待清理，ignored=已忽视，deleted=已清理。"
            "注：pending 与 ignored 同选会退化为“所有未删除文件”"
        ),
    ),
    confidence: Optional[str] = Query(
        default=None,
        description="置信度筛选（支持逗号分隔多值）：high=高置信度，low=低置信度",
    ),
    hardlink_copies: Optional[str] = Query(
        default=None,
        description=(
            "副本筛选：located=仅显示有硬链接副本的文件"
            "（依据扫描时落库的 st_nlink-1 快照列，每日预扫描与每次成功扫描刷新；"
            "尚未生成快照的历史行不命中）"
        ),
    ),
    group_by_folder: bool = Query(
        default=False,
        description="按文件夹（直接父目录）聚合分页：True 时同目录下≥2 个文件折叠为文件夹行，单文件保持原样；分页单位为文件夹组",
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """分页查询孤儿文件列表及同一响应快照中的扫描上下文。

    scan_context 区分最新扫描尝试、页面展示的成功批次、扫描原始统计与
    尚未清理的动态统计；最新 running 不回退，最新 failed 仅只读展示
    最近成功批次。支持按 下载器/路径/状态/置信度/大小 多条件筛选与分页。

    group_by_folder=True 时改走文件夹聚合分页（仅影响列表数据形态，
    scan_context 统计口径不变）；默认 False 保持扁平文件行分页，向后兼容。
    文件行 hardlink_copy_count 为扫描时统计的硬链接副本数快照（发现文件时
    st_nlink-1，每日预扫描与每次成功扫描刷新；NULL=尚未生成快照）；文件夹
    父行不加载子项且 hardlink_copy_count=null，展开后的独立分页接口同样返回
    子文件的快照列。副本位置弹窗仍会实时复核并展示预扫描定位的路径。
    """
    try:
        service = OrphanFileService(db)
        if group_by_folder:
            result = await service.get_orphan_list_grouped(
                page=page,
                page_size=page_size,
                downloader_id=downloader_id,
                min_size=min_size,
                path_like=path_like,
                path_prefix=path_prefix,
                status=status,
                confidence=confidence,
                hardlink_copies=hardlink_copies,
            )
        else:
            result = await service.get_orphan_list(
                page=page,
                page_size=page_size,
                downloader_id=downloader_id,
                min_size=min_size,
                path_like=path_like,
                path_prefix=path_prefix,
                status=status,
                confidence=confidence,
                hardlink_copies=hardlink_copies,
            )
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error(f"查询孤儿文件列表失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


@router.get("/folders/children", response_model=CommonResponse)
async def get_orphan_folder_children(
    folder_path: str = Query(..., min_length=1, description="直接父目录路径（来自文件夹行）"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    downloader_id: Optional[str] = Query(default=None),
    min_size: Optional[int] = Query(default=None, ge=0),
    path_like: Optional[str] = Query(default=None),
    path_prefix: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    confidence: Optional[str] = Query(default=None),
    hardlink_copies: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """展开文件夹后独立分页加载子文件；子文件副本数为扫描时统计的快照列。"""
    try:
        result = await OrphanFileService(db).get_orphan_folder_children(
            folder_path,
            page=page,
            page_size=page_size,
            downloader_id=downloader_id,
            min_size=min_size,
            path_like=path_like,
            path_prefix=path_prefix,
            status=status,
            confidence=confidence,
            hardlink_copies=hardlink_copies,
        )
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error("查询孤儿文件夹子项失败 folder=%s: %s", folder_path, e, exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


@router.post("/hardlink-copies", response_model=CommonResponse)
async def get_hardlink_copy_locations(
    req: HardlinkCopyLocationsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """读取定时预扫描任务落库的硬链接副本位置，不做任何目录遍历。

    返回实时 ``st_nlink - 1`` 总数（廉价 stat 复核）与结果表中最近一轮定位到的
    路径；尚无结果的文件返回 ``pending_scan=true``，由每日
    ``orphan_hardlink_copy_scan`` 任务在预算内逐步覆盖。
    """
    try:
        result = await OrphanFileService(db).get_hardlink_copy_locations(req.orphan_ids)
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error(f"查询硬链接副本位置失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


@router.post("/hardlink-copies/delete", response_model=CommonResponse)
async def delete_hardlink_copies(
    req: HardlinkCopyDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """删除已定位的硬链接副本目录项（tombstone 三段式，逐项 fail-closed）。

    仅移除指向同一 inode 的其它路径链接，源文件与数据保留；源路径、共享
    同一 inode 的其它孤儿、种子目录内副本、隔离区/回收站路径均拒绝删除，
    状态类拒绝以 failed_list 返回（不使用 400）。
    """
    try:
        audit_info = extract_audit_info_from_request(request) if request else {}
        result = await OrphanFileService(db).delete_hardlink_copies(
            orphan_id=req.orphan_id,
            copy_paths=req.copy_paths,
            operator=current_user.username,
            audit_service=audit_service,
            ip_address=audit_info.get("ip_address"),
        )
        if result.get("rejected"):
            msg = str(result.get("error") or "维护操作互斥，本次未执行删除")
        elif result["failed_count"] > 0:
            msg = f"副本删除完成: 成功 {result['success_count']} 个，失败 {result['failed_count']} 个"
        else:
            msg = f"副本删除完成: 成功 {result['success_count']} 个"
        return CommonResponse(status="success", msg=msg, code="200", data=result)
    except Exception as e:
        logger.error(f"删除硬链接副本失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"删除失败: {e}", code="500", data=None)


@router.post("/scan", response_model=CommonResponse)
async def trigger_manual_scan(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """手动触发孤儿文件扫描"""
    try:
        result = await OrphanScanJobService(db).submit_scan(
            scan_type="manual",
            operator=current_user.username,
        )
        get_orphan_scan_dispatcher(request.app).submit(str(result["scan_id"]))
        msg = "扫描任务已提交" if result["accepted"] else "已有扫描任务进行中"
        return CommonResponse(status="success", msg=msg, code="200", data=result)
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
        orphan_ids = await _resolve_selection(service, req, scan_id=req.scan_id)
        result = await service.cleanup_preview(orphan_ids, scan_id=req.scan_id)
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
):
    """提交主动清理任务；实际复核和隔离动作在后台执行。"""
    try:
        audit_info = extract_audit_info_from_request(request) if request else {}
        service = OrphanFileService(db)
        orphan_ids = await _resolve_selection(service, req, scan_id=req.scan_id)
        submission = await OrphanPurgeJobService(db).submit_cleanup_job(
            scan_id=req.scan_id,
            orphan_ids=orphan_ids,
            operator=current_user.username,
            ip_address=audit_info.get("ip_address"),
        )
        if submission.job is not None:
            get_orphan_purge_dispatcher(request.app).submit(str(submission.job.task_id))
        if submission.job is None:
            msg = "所选孤儿文件均已在处理中，本次未重复提交"
        elif submission.skipped_count:
            msg = "主动清理任务已提交，" f"已跳过 {submission.skipped_count} 个处理中项目，完成或失败后将发送通知"
        else:
            msg = "主动清理任务已提交，完成或失败后将发送通知"
        return CommonResponse(
            status="success",
            msg=msg,
            code="200",
            data=submission.to_dict(),
        )
    except Exception as e:
        logger.error(f"提交主动清理任务失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"任务提交失败: {e}", code="500", data=None)


@router.post("/ignore", response_model=CommonResponse)
async def set_orphan_ignored(
    req: IgnoreRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """设置/取消孤儿文件的忽视态。

    被忽视的孤儿受保护：定时任务不自动删除，手动清理也被拒绝，但仍可在列表查询。
    """
    try:
        audit_info = extract_audit_info_from_request(request) if request else {}
        service = OrphanFileService(db)
        orphan_ids = await _resolve_selection(service, req, scan_id=req.scan_id)
        result = await service.set_ignored(
            orphan_ids=orphan_ids,
            ignored=req.ignored,
            operator=current_user.username,
            scan_id=req.scan_id,
            ip_address=audit_info.get("ip_address"),
        )
        action = "忽视" if req.ignored else "取消忽视"
        msg = f"{action}完成: 成功 {result['success_count']} 个"
        if result["failed_count"] > 0:
            msg += f"，失败 {result['failed_count']} 个"
        return CommonResponse(status="success", msg=msg, code="200", data=result)
    except Exception as e:
        logger.error(f"设置孤儿忽视态失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"操作失败: {e}", code="500", data=None)


@router.post("/prefix-match-preview", response_model=CommonResponse)
async def prefix_match_preview(
    req: PrefixMatchPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """左匹配（前缀）预览：统计以 path_prefix 开头的“待清理”孤儿文件数与大小。

    与 cleanup 共用新鲜度门禁（最新扫描 completed + scan_id 最新），stale 时返回
    rejected=True。范围严格限定 status=pending（排除已忽视 / 已清理）；
    hardlink_copies=located 时进一步限定有硬链接副本的文件（与列表筛选同口径）。
    """
    try:
        service = OrphanFileService(db)
        result = await service.prefix_match_preview(req.path_prefix, req.scan_id, hardlink_copies=req.hardlink_copies)
        return CommonResponse(status="success", msg="查询成功", code="200", data=result)
    except Exception as e:
        logger.error(f"左匹配预览失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)


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
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
    audit_service: AuditLogService = Depends(get_audit_service),
):
    """从隔离区恢复文件到原位置（mark_quarantined 的逆操作）。"""
    try:
        audit_info = extract_audit_info_from_request(request) if request else {}
        service = OrphanFileService(db)
        result = await service.restore_quarantined(
            canonical_paths=req.canonical_paths,
            operator=current_user.username,
            audit_service=audit_service,
            ip_address=audit_info.get("ip_address"),
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
        audit_info = extract_audit_info_from_request(request) if request else {}
        submission = await OrphanPurgeJobService(db).submit_purge_job(
            canonical_paths=req.canonical_paths,
            operator=current_user.username,
            ip_address=audit_info.get("ip_address"),
        )
        if submission.job is not None:
            get_orphan_purge_dispatcher(request.app).submit(str(submission.job.task_id))
        if submission.job is None:
            msg = "所选隔离文件均已在处理中，本次未重复提交"
        elif submission.skipped_count:
            msg = "彻底删除任务已提交，" f"已跳过 {submission.skipped_count} 个处理中项目，完成后将发送通知"
        else:
            msg = "彻底删除任务已提交，完成后将发送通知"
        return CommonResponse(
            status="success",
            msg=msg,
            code="200",
            data=submission.to_dict(),
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


@router.get("/cleanup-jobs/{task_id}", response_model=CommonResponse)
async def get_cleanup_job_status(
    task_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(require_authenticated_user),
):
    """查询主动清理任务状态；结果通知仍以通知中心为准。"""
    try:
        job = await OrphanPurgeJobService(db).get_job(task_id)
        if job is None or (job.operation_type or "purge") != "cleanup":
            return CommonResponse(status="error", msg="任务不存在", code="404", data=None)
        return CommonResponse(status="success", msg="查询成功", code="200", data=job.to_dict())
    except Exception as e:
        logger.error(f"查询主动清理任务失败: {e}", exc_info=True)
        return CommonResponse(status="error", msg=f"查询失败: {e}", code="500", data=None)
