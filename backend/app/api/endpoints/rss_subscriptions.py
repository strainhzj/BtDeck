# -*- coding: utf-8 -*-
"""
RSS 订阅 API 接口（feature rss-subscription-2026-09-24 Phase 1）

提供订阅源 CRUD、手动刷新、文章分页查询、文章推送下载器的 REST API。
遵循统一响应格式规范（分页 list/total/pageSize）；失败路径 data.reasonCode
携带稳定标识（RSS_*），动态 str(e) 只进日志。
android-server 伴侣形态不支持外网抓取（对齐主机能力矩阵门控惯例）。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.responseVO import CommonResponse
from app.auth.dependencies import require_authenticated_user, AuthenticatedUserInfo
from app.core.platform_capabilities import PLATFORM_ANDROID_SERVER, resolve_platform
from app.database import AsyncSessionLocal, get_db
from app.services.audit_service import get_audit_service
from app.services.audit_context import AuditContext
from app.services.rss_feed_service import RssFeedService
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType

logger = logging.getLogger(__name__)

router = APIRouter()


def _rss_error(reason_code: str, msg: str, code: str) -> CommonResponse:
    """错误响应（reasonCode 契约，对齐 cron_tasks/_tasks_error 形态）。"""
    return CommonResponse(status="error", msg=msg, code=code, data={"reasonCode": reason_code})


def _unsupported_platform_error() -> CommonResponse:
    return _rss_error("RSS_PLATFORM_UNSUPPORTED", "当前运行形态不支持 RSS 订阅功能", "400")


class RssFeedCreateRequest(BaseModel):
    """创建订阅源请求"""

    downloader_id: str = Field(..., description="绑定的下载器ID", max_length=36, alias="downloaderId")
    name: str = Field(..., description="订阅源名称", max_length=200)
    url: str = Field(..., description="订阅源地址（http/https）", max_length=1000)

    class Config:
        populate_by_name = True


class RssFeedUpdateRequest(BaseModel):
    """更新订阅源请求（部分更新）"""

    name: Optional[str] = Field(default=None, description="订阅源名称", max_length=200)
    url: Optional[str] = Field(default=None, description="订阅源地址（http/https）", max_length=1000)
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class RssArticleAddRequest(BaseModel):
    """推送文章到下载器请求"""

    downloader_id: Optional[str] = Field(
        default=None,
        description="目标下载器ID（缺省为订阅源绑定下载器；按类型路由 Phase 2 预留）",
        max_length=36,
        alias="downloaderId",
    )
    save_path: Optional[str] = Field(default=None, description="保存路径", max_length=500, alias="savePath")
    tags: Optional[str] = Field(default=None, description="标签（逗号分隔；qB=tags，TR=labels）", max_length=500)

    class Config:
        populate_by_name = True


async def _write_audit(
    request: Request,
    operator: str,
    operation_type: AuditOperationType,
    operation_detail: dict,
    downloader_id: Optional[str],
    result: str = AuditOperationResult.SUCCESS,
) -> None:
    """best-effort 审计日志（失败不影响主业务，对齐 torrent_add_service 审计模式）。"""
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
        logger.exception("RSS 审计日志写入失败 [operation=%s]", operation_type)


@router.get("/feeds", summary="获取下载器的 RSS 订阅源列表", response_model=CommonResponse, tags=["RSS订阅"])
async def list_rss_feeds(
    downloader_id: str = Query(..., alias="downloaderId", description="下载器ID"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    service = RssFeedService(db)
    result = service.list_feeds(downloader_id, page=page, page_size=pageSize)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_FEED_LIST_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.post("/feeds", summary="新增 RSS 订阅源", response_model=CommonResponse, tags=["RSS订阅"])
async def create_rss_feed(
    request_body: RssFeedCreateRequest,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssFeedService(db)
    result = service.create_feed(request_body.downloader_id, request_body.name, request_body.url)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_FEED_CREATE_FAILED", result.msg, result.code)
    feed = result.data.get("feed", {})
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_FEED_ADD,
        {
            "feed_id": feed.get("feedId"),
            "feed_name": feed.get("name"),
            "feed_url": feed.get("url"),
            "downloader_id": request_body.downloader_id,
        },
        request_body.downloader_id,
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.put("/feeds/{feed_id}", summary="更新 RSS 订阅源", response_model=CommonResponse, tags=["RSS订阅"])
async def update_rss_feed(
    feed_id: str,
    request_body: RssFeedUpdateRequest,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssFeedService(db)
    result = service.update_feed(feed_id, request_body.name, request_body.url, request_body.enabled)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_FEED_UPDATE_FAILED", result.msg, result.code)
    feed = result.data.get("feed", {})
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_FEED_UPDATE,
        {"feed_id": feed.get("feedId"), "feed_name": feed.get("name"), "feed_url": feed.get("url")},
        feed.get("downloaderId"),
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.delete("/feeds/{feed_id}", summary="删除 RSS 订阅源", response_model=CommonResponse, tags=["RSS订阅"])
async def delete_rss_feed(
    feed_id: str,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssFeedService(db)
    # 先取事实供审计（删除后不可查）
    existing = service._get_feed(feed_id)
    if existing is None:
        return _rss_error("RSS_FEED_NOT_FOUND", "订阅源不存在", "404")
    result = service.delete_feed(feed_id)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_FEED_DELETE_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_FEED_DELETE,
        {"feed_id": feed_id, "feed_name": existing.name, "feed_url": existing.url},
        existing.downloader_id,
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data={})


@router.post("/feeds/{feed_id}/refresh", summary="手动刷新 RSS 订阅源", response_model=CommonResponse, tags=["RSS订阅"])
async def refresh_rss_feed(
    feed_id: str,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssFeedService(db, store=getattr(request.app.state, "store", None))
    result = await service.refresh_feed(feed_id)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_FEED_REFRESH_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_FEED_REFRESH,
        {"feed_id": feed_id, "new_count": result.data.get("newCount")},
        None,
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.get("/feeds/{feed_id}/articles", summary="获取订阅源文章列表", response_model=CommonResponse, tags=["RSS订阅"])
async def list_rss_articles(
    feed_id: str,
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选：pending/added"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    service = RssFeedService(db)
    result = service.list_articles(feed_id, status=status, page=page, page_size=pageSize)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_ARTICLE_LIST_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.post("/articles/{article_id}/add", summary="推送文章到下载器", response_model=CommonResponse, tags=["RSS订阅"])
async def add_rss_article(
    article_id: str,
    request_body: RssArticleAddRequest,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssFeedService(db, store=getattr(request.app.state, "store", None))
    result = await service.add_article_to_downloader(
        article_id,
        downloader_id=request_body.downloader_id,
        save_path=request_body.save_path,
        tags=request_body.tags,
    )
    if not result.ok:
        await _write_audit(
            request,
            user_info.username,
            AuditOperationType.RSS_ARTICLE_ADD,
            {"article_id": article_id, "downloader_id": request_body.downloader_id},
            request_body.downloader_id,
            result=AuditOperationResult.FAILED,
        )
        return _rss_error(result.reason_code or "RSS_ADD_FAILED", result.msg, result.code)
    article = result.data.get("article", {})
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_ARTICLE_ADD,
        {
            "article_id": article_id,
            "article_title": article.get("title"),
            "downloader_id": result.data.get("downloaderId"),
            "save_path": request_body.save_path,
            "tags": request_body.tags,
        },
        result.data.get("downloaderId"),
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)
