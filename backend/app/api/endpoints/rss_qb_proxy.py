# -*- coding: utf-8 -*-
"""
qB 原生 RSS 代理 API 接口（feature rss-subscription-phase2-2026-09-24）

把 qBittorrent 自身 RSS（订阅源/文件夹/下载规则/偏好/文章）透传给前端。
qB 为事实源，BtDeck 不落库。统一响应格式；失败路径 data.reasonCode
（RSS_QB_*）。android-server 伴侣形态拒写（写操作与外网刷新）。
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, Field

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user, AuthenticatedUserInfo
from app.core.platform_capabilities import PLATFORM_ANDROID_SERVER, resolve_platform
from app.database import AsyncSessionLocal
from app.services.audit_service import get_audit_service
from app.services.audit_context import AuditContext
from app.services.rss_qb_proxy_service import RssQbProxyService
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType

logger = logging.getLogger(__name__)

router = APIRouter()


def _qb_error(reason_code: str, msg: str, code: str) -> CommonResponse:
    """错误响应（reasonCode 契约，对齐 rss_subscriptions/_rss_error 形态）。"""
    return CommonResponse(status="error", msg=msg, code=code, data={"reasonCode": reason_code})


def _unsupported_platform_error() -> CommonResponse:
    return _qb_error("RSS_PLATFORM_UNSUPPORTED", "当前运行形态不支持 RSS 订阅功能", "400")


async def _write_audit(
    request: Request,
    operator: str,
    operation_type: AuditOperationType,
    operation_detail: dict,
    downloader_id: str,
    result: str = AuditOperationResult.SUCCESS,
) -> None:
    """best-effort 审计日志（失败不影响主业务，对齐 rss_subscriptions 模式）。"""
    try:
        audit_context = AuditContext.from_request(request)
        audit_fields: dict = dict(audit_context.as_dict())
        async with AsyncSessionLocal() as async_db:
            audit_service = await get_audit_service(async_db)
            await audit_service.log_operation(
                operation_type=operation_type,
                operator=operator,
                operation_detail=operation_detail,
                operation_result=result,
                downloader_id=downloader_id,
                **audit_fields,
            )
    except Exception:
        logger.exception("qB RSS 代理审计日志写入失败 [operation=%s]", operation_type)


def _audit_failed(
    request: Request,
    operator: str,
    operation_type: AuditOperationType,
    detail: dict,
    downloader_id: str,
):
    """失败审计 helper（返回可 await 的协程）。"""
    return _write_audit(request, operator, operation_type, detail, downloader_id, result=AuditOperationResult.FAILED)


# ==============================================================================
# 请求模型
# ==============================================================================


class QbFeedAddRequest(BaseModel):
    """添加 qB 订阅源"""

    path: str = Field(..., description="源路径（可含文件夹层级，如 Folder\\FeedName）", max_length=500)
    url: str = Field(..., description="源地址（http/https）", max_length=1000)


class QbFolderAddRequest(BaseModel):
    """添加 qB 文件夹"""

    path: str = Field(..., description="文件夹路径（可含多级）", max_length=500)


class QbFeedUrlUpdateRequest(BaseModel):
    """修改 qB 订阅源地址"""

    url: str = Field(..., description="新源地址（http/https）", max_length=1000)


class QbItemMoveRequest(BaseModel):
    """移动 qB RSS 项"""

    origin_path: str = Field(..., description="原路径", max_length=500, alias="originPath")
    dest_path: str = Field(..., description="目标路径", max_length=500, alias="destPath")

    class Config:
        populate_by_name = True


class QbRefreshRequest(BaseModel):
    """刷新 qB RSS 项（path 为空 = 全部）"""

    path: Optional[str] = Field(default=None, description="项路径（空=刷新全部）", max_length=500)


class QbMarkReadRequest(BaseModel):
    """标记已读（articleId 为空 = 整源已读）"""

    path: str = Field(..., description="项路径", max_length=500)
    article_id: Optional[str] = Field(default=None, description="文章ID（空=整源）", max_length=100, alias="articleId")

    class Config:
        populate_by_name = True


class QbRuleSetRequest(BaseModel):
    """设置 qB 下载规则（ruleDef 透传 + 轻校验）"""

    name: str = Field(..., description="规则名称", max_length=200)
    rule_def: Dict[str, Any] = Field(..., description="规则定义（qB ruleDef 透传）", alias="ruleDef")


class QbRuleRenameRequest(BaseModel):
    """重命名 qB 下载规则"""

    new_name: str = Field(..., description="新名称", max_length=200, alias="newName")

    class Config:
        populate_by_name = True


class QbPreferencesUpdateRequest(BaseModel):
    """更新 qB RSS 偏好（白名单四键，全部可选）"""

    rss_processing_enabled: Optional[bool] = Field(
        default=None, description="启用 RSS 处理", alias="rssProcessingEnabled"
    )
    rss_auto_downloading_enabled: Optional[bool] = Field(
        default=None, description="启用自动下载", alias="rssAutoDownloadingEnabled"
    )
    rss_refresh_interval: Optional[int] = Field(
        default=None, description="刷新间隔（分钟，1-9999）", alias="rssRefreshInterval"
    )
    rss_max_articles_per_feed: Optional[int] = Field(
        default=None, description="每源文章上限（1-5000）", alias="rssMaxArticlesPerFeed"
    )

    class Config:
        populate_by_name = True


# ==============================================================================
# 源/文件夹
# ==============================================================================


@router.get("/{downloader_id}/feeds", summary="获取 qB 原生 RSS 源树", response_model=CommonResponse, tags=["RSS订阅"])
async def list_qb_feeds(
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.list_feeds(downloader_id)
    if not result.ok:
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.post("/{downloader_id}/feeds", summary="添加 qB 原生订阅源", response_model=CommonResponse, tags=["RSS订阅"])
async def add_qb_feed(
    request_body: QbFeedAddRequest,
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.add_feed(downloader_id, request_body.path, request_body.url)
    if not result.ok:
        await _audit_failed(
            request,
            user_info.username,
            AuditOperationType.RSS_QB_FEED_ADD,
            {"path": request_body.path, "url": request_body.url},
            downloader_id,
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_QB_FEED_ADD,
        {"path": request_body.path, "url": request_body.url},
        downloader_id,
    )
    return CommonResponse(status="success", msg="订阅源已添加", code=result.code, data={})


@router.post(
    "/{downloader_id}/folders", summary="添加 qB 原生 RSS 文件夹", response_model=CommonResponse, tags=["RSS订阅"]
)
async def add_qb_folder(
    request_body: QbFolderAddRequest,
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.add_folder(downloader_id, request_body.path)
    if not result.ok:
        await _audit_failed(
            request,
            user_info.username,
            AuditOperationType.RSS_QB_FEED_ADD,
            {"path": request_body.path, "folder": True},
            downloader_id,
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_QB_FEED_ADD,
        {"path": request_body.path, "folder": True},
        downloader_id,
    )
    return CommonResponse(status="success", msg="文件夹已添加", code=result.code, data={})


@router.put(
    "/{downloader_id}/feeds/url", summary="修改 qB 原生订阅源地址", response_model=CommonResponse, tags=["RSS订阅"]
)
async def update_qb_feed_url(
    request_body: QbFeedUrlUpdateRequest,
    request: Request,
    path: str = Query(..., description="源路径"),
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.set_feed_url(downloader_id, path, request_body.url)
    if not result.ok:
        await _audit_failed(
            request,
            user_info.username,
            AuditOperationType.RSS_QB_FEED_UPDATE,
            {"path": path, "url": request_body.url},
            downloader_id,
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_QB_FEED_UPDATE,
        {"path": path, "url": request_body.url},
        downloader_id,
    )
    return CommonResponse(status="success", msg="订阅源地址已更新", code=result.code, data={})


@router.delete(
    "/{downloader_id}/items",
    summary="删除 qB 原生 RSS 项（源或文件夹）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def delete_qb_item(
    request: Request,
    path: str = Query(..., description="项路径"),
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.remove_item(downloader_id, path)
    if not result.ok:
        await _audit_failed(
            request, user_info.username, AuditOperationType.RSS_QB_FEED_DELETE, {"path": path}, downloader_id
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request, user_info.username, AuditOperationType.RSS_QB_FEED_DELETE, {"path": path}, downloader_id
    )
    return CommonResponse(status="success", msg="项目已删除", code=result.code, data={})


@router.post(
    "/{downloader_id}/items/move", summary="移动 qB 原生 RSS 项", response_model=CommonResponse, tags=["RSS订阅"]
)
async def move_qb_item(
    request_body: QbItemMoveRequest,
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.move_item(downloader_id, request_body.origin_path, request_body.dest_path)
    if not result.ok:
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg="项目已移动", code=result.code, data={})


@router.post(
    "/{downloader_id}/items/refresh",
    summary="刷新 qB 原生 RSS 项（空=全部）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def refresh_qb_item(
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    request_body: QbRefreshRequest = None,  # type: ignore[assignment]
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    path = request_body.path if request_body is not None else None
    result = await service.refresh_item(downloader_id, path)
    if not result.ok:
        await _audit_failed(
            request, user_info.username, AuditOperationType.RSS_QB_FEED_REFRESH, {"path": path}, downloader_id
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request, user_info.username, AuditOperationType.RSS_QB_FEED_REFRESH, {"path": path}, downloader_id
    )
    return CommonResponse(status="success", msg="刷新已触发", code=result.code, data={})


@router.post(
    "/{downloader_id}/items/mark-read",
    summary="标记 qB 原生 RSS 已读（单篇或整源）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def mark_qb_read(
    request_body: QbMarkReadRequest,
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.mark_as_read(downloader_id, request_body.path, request_body.article_id)
    if not result.ok:
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg="已标记为已读", code=result.code, data={})


# ==============================================================================
# 文章
# ==============================================================================


@router.get(
    "/{downloader_id}/articles", summary="获取 qB 原生订阅源文章列表", response_model=CommonResponse, tags=["RSS订阅"]
)
async def list_qb_articles(
    request: Request,
    path: str = Query(..., description="源路径"),
    onlyUnread: bool = Query(False, description="仅未读"),
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.list_articles(downloader_id, path, only_unread=onlyUnread)
    if not result.ok:
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


# ==============================================================================
# 规则
# ==============================================================================


@router.get(
    "/{downloader_id}/rules", summary="获取 qB 原生 RSS 下载规则", response_model=CommonResponse, tags=["RSS订阅"]
)
async def list_qb_rules(
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.list_rules(downloader_id)
    if not result.ok:
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.post(
    "/{downloader_id}/rules", summary="设置 qB 原生 RSS 下载规则", response_model=CommonResponse, tags=["RSS订阅"]
)
async def set_qb_rule(
    request_body: QbRuleSetRequest,
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.set_rule(downloader_id, request_body.name, request_body.rule_def)
    if not result.ok:
        await _audit_failed(
            request,
            user_info.username,
            AuditOperationType.RSS_QB_RULE_ADD,
            {"rule_name": request_body.name},
            downloader_id,
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_QB_RULE_ADD,
        {"rule_name": request_body.name},
        downloader_id,
    )
    return CommonResponse(status="success", msg="规则已保存", code=result.code, data={})


@router.put(
    "/{downloader_id}/rules/rename",
    summary="重命名 qB 原生 RSS 下载规则",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def rename_qb_rule(
    request_body: QbRuleRenameRequest,
    request: Request,
    name: str = Query(..., description="原规则名"),
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.rename_rule(downloader_id, name, request_body.new_name)
    if not result.ok:
        await _audit_failed(
            request,
            user_info.username,
            AuditOperationType.RSS_QB_RULE_UPDATE,
            {"rule_name": name, "new_name": request_body.new_name},
            downloader_id,
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_QB_RULE_UPDATE,
        {"rule_name": name, "new_name": request_body.new_name},
        downloader_id,
    )
    return CommonResponse(status="success", msg="规则已重命名", code=result.code, data={})


@router.delete(
    "/{downloader_id}/rules", summary="删除 qB 原生 RSS 下载规则", response_model=CommonResponse, tags=["RSS订阅"]
)
async def delete_qb_rule(
    request: Request,
    name: str = Query(..., description="规则名"),
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.remove_rule(downloader_id, name)
    if not result.ok:
        await _audit_failed(
            request, user_info.username, AuditOperationType.RSS_QB_RULE_DELETE, {"rule_name": name}, downloader_id
        )
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(
        request, user_info.username, AuditOperationType.RSS_QB_RULE_DELETE, {"rule_name": name}, downloader_id
    )
    return CommonResponse(status="success", msg="规则已删除", code=result.code, data={})


@router.get(
    "/{downloader_id}/rules/matching",
    summary="获取 qB 原生规则命中文章（预览）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def qb_rule_matching(
    request: Request,
    name: str = Query(..., description="规则名"),
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.matching_articles(downloader_id, name)
    if not result.ok:
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


# ==============================================================================
# 偏好（白名单）
# ==============================================================================


@router.get(
    "/{downloader_id}/preferences",
    summary="获取 qB 原生 RSS 偏好（白名单四键）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def get_qb_preferences(
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    result = await service.get_preferences(downloader_id)
    if not result.ok:
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.put(
    "/{downloader_id}/preferences",
    summary="更新 qB 原生 RSS 偏好（白名单四键）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def update_qb_preferences(
    request_body: QbPreferencesUpdateRequest,
    request: Request,
    downloader_id: str = Path(..., description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssQbProxyService(store=getattr(request.app.state, "store", None))
    updates = {
        "rssProcessingEnabled": request_body.rss_processing_enabled,
        "rssAutoDownloadingEnabled": request_body.rss_auto_downloading_enabled,
        "rssRefreshInterval": request_body.rss_refresh_interval,
        "rssMaxArticlesPerFeed": request_body.rss_max_articles_per_feed,
    }
    result = await service.update_preferences(downloader_id, updates)
    if not result.ok:
        await _audit_failed(request, user_info.username, AuditOperationType.RSS_QB_PREF_UPDATE, updates, downloader_id)
        return _qb_error(result.reason_code or "RSS_QB_PROXY_FAILED", result.msg, result.code)
    await _write_audit(request, user_info.username, AuditOperationType.RSS_QB_PREF_UPDATE, updates, downloader_id)
    return CommonResponse(status="success", msg="偏好已更新", code=result.code, data=result.data)
