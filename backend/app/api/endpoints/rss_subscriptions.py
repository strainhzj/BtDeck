# -*- coding: utf-8 -*-
"""
RSS 订阅 API 接口（feature rss-subscription-2026-09-24 Phase 1）

提供订阅源 CRUD、手动刷新、文章分页查询、文章推送下载器的 REST API。
遵循统一响应格式规范（分页 list/total/pageSize）；失败路径 data.reasonCode
携带稳定标识（RSS_*），动态 str(e) 只进日志。
android-server 伴侣形态不支持外网抓取（对齐主机能力矩阵门控惯例）。
"""

import logging
from typing import Dict, List, Optional

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
from app.services.rss_rule_service import RssRuleService
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
    refresh_interval_minutes: Optional[int] = Field(
        default=None,
        description="刷新间隔覆盖（分钟，5-1440；显式 null=恢复全局节奏）",
        alias="refreshIntervalMinutes",
    )

    class Config:
        populate_by_name = True


class RssModeUpdateRequest(BaseModel):
    """切换 RSS 模式请求（Phase 2）"""

    downloader_id: str = Field(..., description="下载器ID", max_length=36, alias="downloaderId")
    mode: str = Field(..., description="RSS 模式：btdeck/qb_native", max_length=20)

    class Config:
        populate_by_name = True


class RssRuleCreateRequest(BaseModel):
    """创建自动下载规则请求（Phase 2）"""

    downloader_id: str = Field(..., description="归属下载器ID", max_length=36, alias="downloaderId")
    name: str = Field(..., description="规则名称", max_length=200)
    include_keywords: str = Field(
        ..., description="命中关键词（逗号分隔，任一命中）", max_length=5000, alias="includeKeywords"
    )
    exclude_keywords: Optional[str] = Field(
        default=None, description="排除关键词（逗号分隔，全不命中）", max_length=5000, alias="excludeKeywords"
    )
    use_regex: Optional[bool] = Field(default=False, description="是否按正则匹配", alias="useRegex")
    target_downloader_id: Optional[str] = Field(
        default=None, description="推送目标下载器覆盖（缺省=归属下载器）", max_length=36, alias="targetDownloaderId"
    )
    save_path: Optional[str] = Field(default=None, description="保存路径", max_length=500, alias="savePath")
    tags: Optional[str] = Field(default=None, description="标签（逗号分隔；qB=tags，TR=labels）", max_length=200)
    feed_ids: Optional[List[str]] = Field(
        default=None, description="关联订阅源ID列表（空/缺省=归属下载器全部源）", alias="feedIds"
    )
    enabled: Optional[bool] = Field(default=True, description="是否启用")

    class Config:
        populate_by_name = True


class RssRuleUpdateRequest(BaseModel):
    """更新自动下载规则请求（部分更新；显式 null 语义字段单独说明）"""

    name: Optional[str] = Field(default=None, description="规则名称", max_length=200)
    include_keywords: Optional[str] = Field(
        default=None, description="命中关键词（逗号分隔）", max_length=5000, alias="includeKeywords"
    )
    exclude_keywords: Optional[str] = Field(
        default=None,
        description="排除关键词（显式 null=清除排除）",
        max_length=5000,
        alias="excludeKeywords",
    )
    use_regex: Optional[bool] = Field(default=None, description="是否按正则匹配", alias="useRegex")
    target_downloader_id: Optional[str] = Field(
        default=None,
        description="推送目标下载器覆盖（显式 null=回退归属下载器）",
        max_length=36,
        alias="targetDownloaderId",
    )
    save_path: Optional[str] = Field(
        default=None, description="保存路径（显式 null=清除）", max_length=500, alias="savePath"
    )
    tags: Optional[str] = Field(default=None, description="标签（显式 null=清除）", max_length=200)
    feed_ids: Optional[List[str]] = Field(
        default=None, description="关联订阅源ID列表（显式空列表=全部源）", alias="feedIds"
    )
    enabled: Optional[bool] = Field(default=None, description="是否启用")

    class Config:
        populate_by_name = True


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
    fields = request_body.model_fields_set
    result = service.update_feed(
        feed_id,
        request_body.name,
        request_body.url,
        request_body.enabled,
        refresh_interval_minutes=request_body.refresh_interval_minutes,
        refresh_interval_provided="refresh_interval_minutes" in fields or "refreshIntervalMinutes" in fields,
    )
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


# ==============================================================================
# Phase 2：模式切换 + 自动下载规则（feature rss-subscription-phase2-2026-09-24）
# ==============================================================================


@router.get("/mode", summary="获取下载器 RSS 模式", response_model=CommonResponse, tags=["RSS订阅"])
async def get_rss_mode(
    downloader_id: str = Query(..., alias="downloaderId", description="下载器ID"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    service = RssRuleService(db)
    result = service.get_mode(downloader_id)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_MODE_GET_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.put("/mode", summary="切换下载器 RSS 模式", response_model=CommonResponse, tags=["RSS订阅"])
async def update_rss_mode(
    request_body: RssModeUpdateRequest,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssRuleService(db)
    result = service.set_mode(request_body.downloader_id, request_body.mode)
    if not result.ok:
        await _write_audit(
            request,
            user_info.username,
            AuditOperationType.RSS_MODE_SWITCH,
            {"downloader_id": request_body.downloader_id, "mode": request_body.mode},
            request_body.downloader_id,
            result=AuditOperationResult.FAILED,
        )
        return _rss_error(result.reason_code or "RSS_MODE_UPDATE_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_MODE_SWITCH,
        {"downloader_id": request_body.downloader_id, "mode": request_body.mode},
        request_body.downloader_id,
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.get("/rules", summary="获取下载器的 RSS 自动下载规则列表", response_model=CommonResponse, tags=["RSS订阅"])
async def list_rss_rules(
    downloader_id: str = Query(..., alias="downloaderId", description="下载器ID"),
    page: int = Query(1, ge=1, description="页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页数量"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    service = RssRuleService(db)
    result = service.list_rules(downloader_id, page=page, page_size=pageSize)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_RULE_LIST_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


@router.post(
    "/rules", summary="新增 RSS 自动下载规则（创建后立即回填匹配推送）", response_model=CommonResponse, tags=["RSS订阅"]
)
async def create_rss_rule(
    request_body: RssRuleCreateRequest,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssRuleService(db, store=getattr(request.app.state, "store", None))
    result = service.create_rule(
        request_body.downloader_id,
        request_body.name,
        request_body.include_keywords,
        exclude_keywords=request_body.exclude_keywords,
        use_regex=bool(request_body.use_regex),
        target_downloader_id=request_body.target_downloader_id,
        save_path=request_body.save_path,
        tags=request_body.tags,
        feed_ids=request_body.feed_ids,
        enabled=request_body.enabled is not False,
    )
    if not result.ok:
        await _write_audit(
            request,
            user_info.username,
            AuditOperationType.RSS_RULE_ADD,
            {"downloader_id": request_body.downloader_id, "rule_name": request_body.name},
            request_body.downloader_id,
            result=AuditOperationResult.FAILED,
        )
        return _rss_error(result.reason_code or "RSS_RULE_CREATE_FAILED", result.msg, result.code)
    rule = result.data.get("rule", {})
    # 回填：对存量 pending 匹配并自动推送（保存即生效，对齐 qB 直觉）
    backfill = _project_backfill(await service.apply_rule_to_pending(_rule_or_none(db, rule.get("ruleId"))))
    rule["lastMatchedAt"] = _refresh_rule_projection(db, rule.get("ruleId"), rule)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_RULE_ADD,
        {
            "downloader_id": request_body.downloader_id,
            "rule_id": rule.get("ruleId"),
            "rule_name": rule.get("name"),
            "backfill": backfill,
        },
        request_body.downloader_id,
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data={"rule": rule, "backfill": backfill})


@router.put(
    "/rules/{rule_id}",
    summary="更新 RSS 自动下载规则（更新后立即回填匹配推送）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def update_rss_rule(
    rule_id: str,
    request_body: RssRuleUpdateRequest,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssRuleService(db, store=getattr(request.app.state, "store", None))
    fields = request_body.model_fields_set
    result = service.update_rule(
        rule_id,
        name=request_body.name,
        include_keywords=request_body.include_keywords,
        exclude_keywords=request_body.exclude_keywords,
        use_regex=request_body.use_regex,
        target_downloader_id=request_body.target_downloader_id,
        save_path=request_body.save_path,
        tags=request_body.tags,
        feed_ids=request_body.feed_ids,
        enabled=request_body.enabled,
        target_provided="target_downloader_id" in fields or "targetDownloaderId" in fields,
        exclude_provided="exclude_keywords" in fields or "excludeKeywords" in fields,
    )
    if not result.ok:
        await _write_audit(
            request,
            user_info.username,
            AuditOperationType.RSS_RULE_UPDATE,
            {"rule_id": rule_id, "rule_name": request_body.name},
            None,
            result=AuditOperationResult.FAILED,
        )
        return _rss_error(result.reason_code or "RSS_RULE_UPDATE_FAILED", result.msg, result.code)
    rule = result.data.get("rule", {})
    backfill = _project_backfill(await service.apply_rule_to_pending(_rule_or_none(db, rule.get("ruleId"))))
    rule["lastMatchedAt"] = _refresh_rule_projection(db, rule.get("ruleId"), rule)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_RULE_UPDATE,
        {"rule_id": rule_id, "rule_name": rule.get("name"), "backfill": backfill},
        None,
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data={"rule": rule, "backfill": backfill})


@router.delete("/rules/{rule_id}", summary="删除 RSS 自动下载规则", response_model=CommonResponse, tags=["RSS订阅"])
async def delete_rss_rule(
    rule_id: str,
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    if resolve_platform() == PLATFORM_ANDROID_SERVER:
        return _unsupported_platform_error()
    service = RssRuleService(db)
    # 先取事实供审计（删除后不可查）
    existing = service._get_rule(rule_id)
    if existing is None:
        return _rss_error("RSS_RULE_NOT_FOUND", "规则不存在", "404")
    result = service.delete_rule(rule_id)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_RULE_DELETE_FAILED", result.msg, result.code)
    await _write_audit(
        request,
        user_info.username,
        AuditOperationType.RSS_RULE_DELETE,
        {"rule_id": rule_id, "rule_name": existing.name, "downloader_id": existing.downloader_id},
        existing.downloader_id,
    )
    return CommonResponse(status="success", msg=result.msg, code=result.code, data={})


@router.post(
    "/rules/{rule_id}/match-preview",
    summary="规则匹配预览（只读，不推送）",
    response_model=CommonResponse,
    tags=["RSS订阅"],
)
async def rss_rule_match_preview(
    rule_id: str,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    service = RssRuleService(db)
    result = service.match_preview(rule_id)
    if not result.ok:
        return _rss_error(result.reason_code or "RSS_RULE_PREVIEW_FAILED", result.msg, result.code)
    return CommonResponse(status="success", msg=result.msg, code=result.code, data=result.data)


def _project_backfill(backfill: Dict[str, int]) -> Dict[str, int]:
    """回填计数投影（snake_case → camelCase，API 契约一致性）。"""
    return {
        "matched": backfill.get("matched", 0),
        "pushed": backfill.get("pushed", 0),
        "failed": backfill.get("failed", 0),
        "skippedMode": backfill.get("skipped_mode", 0),
    }


def _rule_or_none(db: Session, rule_id: Optional[str]):
    """按 ID 取未删规则 ORM（回填推送用；取不到返回 None 由调用方跳过）。"""
    if not rule_id:
        return None
    from app.models.rss_subscription import RssRule

    return db.query(RssRule).filter(RssRule.rule_id == rule_id).filter(RssRule.dr == 0).first()


def _refresh_rule_projection(db: Session, rule_id: Optional[str], rule: dict) -> Optional[str]:
    """回填后刷新投影中的命中统计字段（best-effort）。"""
    orm_rule = _rule_or_none(db, rule_id)
    if orm_rule is None:
        return None
    rule["matchCount"] = orm_rule.match_count or 0
    return orm_rule.last_matched_at.strftime("%Y-%m-%d %H:%M:%S") if orm_rule.last_matched_at else None
