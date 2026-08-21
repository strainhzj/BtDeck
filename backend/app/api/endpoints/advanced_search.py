#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级搜索API端点 - 任务1.1.2
支持13字段全字段搜索和多选排除功能
"""

import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.responseVO import CommonResponse
from app.api.models.advanced_search import (
    EnhancedAdvancedSearchRequest,
    SearchTemplateCreate,
    SearchTemplateUpdate,
    TorrentDeleteRequest,
)
from app.services.advanced_search import AdvancedSearchService
from app.services.sqlite_search_runtime import RegexSearchTimeout
from app.auth.dependencies import require_authenticated_user, AuthenticatedUserInfo
from app.core.json_parser import safe_json_parse_with_validator

logger = logging.getLogger(__name__)
router = APIRouter()


def _raise_if_unprocessable(result: dict[str, Any]) -> None:
    """Keep condition-validation failures at the HTTP boundary."""
    if str(result.get("code")) == "422":
        raise HTTPException(
            status_code=422,
            detail={
                "status": result.get("status", "failed"),
                "msg": result.get("msg", "Invalid search conditions"),
                "code": "422",
                "data": result.get("data"),
            },
        )


# 实例化高级搜索服务
def get_advanced_search_service(db: Session = Depends(get_db)) -> AdvancedSearchService:
    return AdvancedSearchService(db)


@router.post("/advanced-search", response_model=CommonResponse)
async def advanced_search_torrents(
    request: EnhancedAdvancedSearchRequest,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    高级搜索种子接口
    支持13字段全字段搜索和多选排除功能

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    # 业务校验：token 有效但 payload 缺 user_id（旧 token）时拒绝
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    logger.info(f"User {user_info.username} performing advanced search")

    # 添加调试日志：记录搜索请求
    logger.info(f"搜索请求参数: name={request.name}, condition_groups={request.condition_groups}")

    # 执行高级搜索
    try:
        result = service.search_torrents(request, str(user_info.user_id))
    except RegexSearchTimeout as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "error",
                "msg": str(exc),
                "code": "422",
                "data": None,
            },
        ) from exc

    # 添加调试日志：记录搜索结果
    logger.info(f"搜索结果: total={result.get('total', 0)}, data_count={len(result.get('data', []))}")

    return CommonResponse(
        status=result.get("status", "success"),
        msg=result.get("msg", "搜索成功"),
        code=result.get("code", "200"),
        data={
            "list": result.get("data", []),
            "total": result.get("total", 0),
            "page": result.get("page", 1),
            "pageSize": result.get("limit", 20),
        },
    )


@router.post("/search-templates", response_model=CommonResponse)
async def create_search_template(
    request: SearchTemplateCreate,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    创建搜索模板接口

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    logger.info(f"User {user_info.username} creating search template: {request.name}")

    # 创建搜索模板
    result = service.create_search_template(request, str(user_info.user_id))
    _raise_if_unprocessable(result)

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "创建模板失败"),
        code=result.get("code", "500"),
        data=result.get("data", {}),
    )


@router.get("/search-templates", response_model=CommonResponse)
async def get_search_templates(
    user_id: Optional[str] = Query(None, description="已废弃，忽略客户端传入值，始终使用当前用户"),
    is_public: bool = Query(False, description="是否获取公开模板"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    获取搜索模板列表接口

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    target_user_id = str(user_info.user_id)
    if user_id and user_id != target_user_id:
        logger.warning(
            "Ignoring client-supplied search template user_id=%s for authenticated user_id=%s",
            user_id,
            target_user_id,
        )

    logger.info(f"Getting search templates for user: {target_user_id}, public: {is_public}")

    # 获取搜索模板列表
    result = service.get_search_templates(target_user_id, is_public)

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "获取模板失败"),
        code=result.get("code", "500"),
        data=result.get("data", {}),
    )


@router.put("/search-templates/{template_id}", response_model=CommonResponse)
async def update_search_template(
    template_id: str,
    request: SearchTemplateUpdate,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    更新搜索模板接口

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    logger.info(f"User {user_info.username} updating search template: {template_id}")

    # 更新搜索模板
    result = service.update_search_template(
        template_id,
        request.model_dump(exclude_unset=True),
        str(user_info.user_id),
    )
    _raise_if_unprocessable(result)

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "更新模板失败"),
        code=result.get("code", "500"),
        data=result.get("data", {}),
    )


@router.delete("/search-templates/{template_id}", response_model=CommonResponse)
async def delete_search_template(
    template_id: str,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    删除搜索模板接口

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    logger.info(f"User {user_info.username} deleting search template: {template_id}")

    # 删除搜索模板
    result = service.delete_search_template(template_id, str(user_info.user_id))

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "删除模板失败"),
        code=result.get("code", "500"),
        data=result.get("data", {}),
    )


@router.post("/search-templates/{template_id}/apply", response_model=CommonResponse)
async def apply_search_template(
    template_id: str,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    应用搜索模板接口

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    logger.info(f"User {user_info.username} applying search template: {template_id}")

    # 应用搜索模板
    result = service.apply_search_template(template_id, str(user_info.user_id))
    _raise_if_unprocessable(result)

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "应用模板失败"),
        code=result.get("code", "500"),
        data=result.get("data", {}),
    )


@router.post("/torrents/batch-delete", response_model=CommonResponse)
async def batch_delete_torrents(
    request: TorrentDeleteRequest,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    批量删除种子接口
    支持多下载器类型和删除数据文件选项

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    logger.info(f"User {user_info.username} batch deleting {len(request.torrent_ids)} torrents")

    # 批量删除种子
    result = await service.delete_torrents_batch(request, str(user_info.user_id))

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "批量删除失败"),
        code=result.get("code", "500"),
        data=result.get("data", {}),
    )


@router.get("/search-statistics", response_model=CommonResponse)
async def get_search_statistics(
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    获取搜索统计信息接口
    字段分布统计、操作符使用统计、搜索性能统计

    认证：由 require_authenticated_user 统一处理。
    """
    logger.info(f"User {user_info.username} getting search statistics")

    # 获取搜索统计
    result = service.get_search_statistics()

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "获取统计失败"),
        code=result.get("code", "500"),
        data=result.get("data", {}),
    )


@router.get("/search-preview", response_model=CommonResponse)
async def preview_advanced_search(
    # 基础参数
    name: Optional[str] = Query(None, description="种子名称"),
    tags: Optional[str] = Query(None, description="标签"),
    category: Optional[str] = Query(None, description="分类"),
    status: Optional[str] = Query(None, description="状态"),
    downloader_name: Optional[str] = Query(None, description="下载器名称"),
    # 高级条件（简化版本用于预览）
    conditions_json: Optional[str] = Query(None, description="JSON格式的搜索条件"),
    limit: int = Query(5, ge=1, le=20, description="预览记录数限制"),
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service),
):
    """
    高级搜索预览接口
    用于在不执行完整搜索的情况下预览搜索结果

    认证：由 require_authenticated_user 统一处理；旧 token 缺 user_id 时拒绝（HTTP 401）。
    """
    if not user_info.user_id:
        raise HTTPException(
            status_code=401, detail={"status": "error", "msg": "无效的访问令牌", "code": "401", "data": None}
        )

    request_data = dict(
        page=1,
        limit=limit,
        sort_by="added_time",
        sort_order="desc",
        name=name,
        tags=tags,
        category=category,
        status=status,
        downloader_name=downloader_name,
    )

    if conditions_json:

        def is_list(obj: Any) -> bool:
            return isinstance(obj, list)

        conditions = safe_json_parse_with_validator(
            conditions_json, is_list, default=None, log_errors=True, error_context="(预览搜索条件)"
        )

        if not conditions:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "error",
                    "msg": "预览搜索条件不是有效的非空数组",
                    "code": "422",
                    "data": None,
                },
            )
        request_data["condition_groups"] = [{"logic": "AND", "conditions": conditions}]
        request_data["between_group_logics"] = []

    try:
        search_request = EnhancedAdvancedSearchRequest.model_validate(request_data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "error",
                "msg": "预览搜索条件无效",
                "code": "422",
                "data": exc.errors(include_url=False),
            },
        ) from exc

    # 执行预览搜索
    logger.info(f"User {user_info.username} previewing advanced search")

    try:
        result = service.search_torrents(search_request, str(user_info.user_id))
    except RegexSearchTimeout as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "status": "error",
                "msg": str(exc),
                "code": "422",
                "data": None,
            },
        ) from exc

    # 只返回预览数据，移除复杂字段以减少响应大小
    preview_data = []
    for torrent in result.get("data", []):
        preview_item = {
            "info_id": torrent.get("info_id"),
            "name": torrent.get("name"),
            "size": torrent.get("size"),
            "status": torrent.get("status"),
            "category": torrent.get("category"),
            "tags": torrent.get("tags"),
            "downloader_name": torrent.get("downloader_name"),
            "added_date": torrent.get("added_date"),
        }
        preview_data.append(preview_item)

    return CommonResponse(
        status=result.get("status", "failed"),
        msg=result.get("msg", "预览搜索失败"),
        code=result.get("code", "500"),
        data={"total": result.get("total", 0), "data": preview_data},
    )
