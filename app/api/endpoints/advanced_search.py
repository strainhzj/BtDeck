#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级搜索API端点 - 任务1.1.2
支持13字段全字段搜索和多选排除功能
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Form, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.responseVO import CommonResponse
from app.api.models.advanced_search import (
    EnhancedAdvancedSearchRequest, AdvancedSearchResponse, SearchTemplateCreate,
    SearchTemplateUpdate, SearchTemplateResponse, SearchTemplateDelete,
    SearchStatisticsResponse, TorrentDeleteRequest
)
from app.services.advanced_search import AdvancedSearchService
from app.auth import utils
from app.core.json_parser import safe_json_parse_with_validator

logger = logging.getLogger(__name__)
router = APIRouter()

# 实例化高级搜索服务
def get_advanced_search_service(db: Session = Depends(get_db)) -> AdvancedSearchService:
    return AdvancedSearchService(db)

@router.post("/advanced-search", response_model=CommonResponse)
async def advanced_search_torrents(
    req: Request,
    request: EnhancedAdvancedSearchRequest,
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    高级搜索种子接口
    支持13字段全字段搜索和多选排除功能
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        # 验证token有效性
        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败，失败原因：" + str(user_info),
                code="401",
                data=None
            )

        logger.info(f"User {user_info.get('sub', user_info.get('username'))} performing advanced search")

        # 添加调试日志：记录搜索请求
        logger.info(f"搜索请求参数: name={request.name}, condition_groups={request.condition_groups}")

        # 执行高级搜索
        result = service.search_torrents(request, user_info['user_id'])

        # 添加调试日志：记录搜索结果
        logger.info(f"搜索结果: total={result.get('total', 0)}, data_count={len(result.get('data', []))}")

        # 构建符合前端期望的响应格式
        # 前端期望：response.data.data (种子列表), response.data.total (总数)
        return CommonResponse(
            status=result.get('status', 'success'),
            msg=result.get('msg', '搜索成功'),
            code=result.get('code', '200'),
            data={
                'data': result.get('data', []),
                'total': result.get('total', 0),
                'page': result.get('page', 1),
                'limit': result.get('limit', 20),
                'total_pages': result.get('total_pages', 0)
            }
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in advanced search: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Advanced search failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"搜索失败: {str(e)}",
            code="500",
            data=None
        )

@router.post("/search-templates", response_model=CommonResponse)
async def create_search_template(
    req: Request,
    request: SearchTemplateCreate,
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    创建搜索模板接口
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        logger.info(f"User {user_info.get('sub', user_info.get('username', 'unknown'))} creating search template: {request.name}")

        # 创建搜索模板
        result = service.create_search_template(request, user_info['user_id'])

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '创建模板失败'),
            code=result.get('code', '500'),
            data=result.get('data', {})
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in create search template: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Create search template failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"创建模板失败: {str(e)}",
            code="500",
            data=None
        )

@router.get("/search-templates", response_model=CommonResponse)
async def get_search_templates(
    req: Request,
    user_id: str = Query(..., description="用户ID，为空时使用当前用户"),
    is_public: bool = Query(False, description="是否获取公开模板"),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    获取搜索模板列表接口
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        # 如果未指定user_id，使用当前用户
        target_user_id = user_id if user_id else user_info['user_id']

        logger.info(f"Getting search templates for user: {target_user_id}, public: {is_public}")

        # 获取搜索模板列表
        result = service.get_search_templates(target_user_id, is_public)

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '获取模板失败'),
            code=result.get('code', '500'),
            data=result.get('data', {})
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in get search templates: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Get search templates failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"获取模板失败: {str(e)}",
            code="500",
            data=None
        )

@router.put("/search-templates/{template_id}", response_model=CommonResponse)
async def update_search_template(
    req: Request,
    template_id: str,
    request: SearchTemplateUpdate,
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    更新搜索模板接口
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        logger.info(f"User {user_info.get('sub', user_info.get('username', 'unknown'))} updating search template: {template_id}")

        # 更新搜索模板
        result = service.update_search_template(template_id, request, user_info['user_id'])

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '更新模板失败'),
            code=result.get('code', '500'),
            data=result.get('data', {})
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in update search template: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Update search template failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"更新模板失败: {str(e)}",
            code="500",
            data=None
        )

@router.delete("/search-templates/{template_id}", response_model=CommonResponse)
async def delete_search_template(
    req: Request,
    template_id: str,
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    删除搜索模板接口
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        logger.info(f"User {user_info.get('sub', user_info.get('username', 'unknown'))} deleting search template: {template_id}")

        # 删除搜索模板
        result = service.delete_search_template(template_id, user_info['user_id'])

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '删除模板失败'),
            code=result.get('code', '500'),
            data=result.get('data', {})
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in delete search template: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Delete search template failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"删除模板失败: {str(e)}",
            code="500",
            data=None
        )

@router.post("/search-templates/{template_id}/apply", response_model=CommonResponse)
async def apply_search_template(
    req: Request,
    template_id: str,
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    应用搜索模板接口
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        logger.info(f"User {user_info.get('sub', user_info.get('username', 'unknown'))} applying search template: {template_id}")

        # 应用搜索模板
        result = service.apply_search_template(template_id, user_info['user_id'])

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '应用模板失败'),
            code=result.get('code', '500'),
            data=result.get('data', {})
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in apply search template: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Apply search template failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"应用模板失败: {str(e)}",
            code="500",
            data=None
        )

@router.post("/torrents/batch-delete", response_model=CommonResponse)
async def batch_delete_torrents(
    req: Request,
    request: TorrentDeleteRequest,
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    批量删除种子接口
    支持多下载器类型和删除数据文件选项
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        logger.info(f"User {user_info.get('sub', user_info.get('username', 'unknown'))} batch deleting {len(request.torrent_ids)} torrents")

        # 批量删除种子
        result = service.delete_torrents_batch(request, user_info['user_id'])

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '批量删除失败'),
            code=result.get('code', '500'),
            data=result.get('data', {})
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in batch delete torrents: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Batch delete torrents failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"批量删除失败: {str(e)}",
            code="500",
            data=None
        )

@router.get("/search-statistics", response_model=CommonResponse)
async def get_search_statistics(
    req: Request,
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    获取搜索统计信息接口
    字段分布统计、操作符使用统计、搜索性能统计
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        logger.info(f"User {user_info.get('sub', user_info.get('username', 'unknown'))} getting search statistics")

        # 获取搜索统计
        result = service.get_search_statistics()

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '获取统计失败'),
            code=result.get('code', '500'),
            data=result.get('data', {})
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in search statistics: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Get search statistics failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"获取统计失败: {str(e)}",
            code="500",
            data=None
        )

@router.get("/search-preview", response_model=CommonResponse)
async def preview_advanced_search(
    req: Request,
    # 基础参数
    name: Optional[str] = Query(None, description="种子名称"),
    tags: Optional[str] = Query(None, description="标签"),
    category: Optional[str] = Query(None, description="分类"),
    status: Optional[str] = Query(None, description="状态"),
    downloader_name: Optional[str] = Query(None, description="下载器名称"),
    # 高级条件（简化版本用于预览）
    conditions_json: Optional[str] = Query(None, description="JSON格式的搜索条件"),
    limit: int = Query(5, ge=1, le=20, description="预览记录数限制"),
    db: Session = Depends(get_db),
    service: AdvancedSearchService = Depends(get_advanced_search_service)
):
    """
    高级搜索预览接口
    用于在不执行完整搜索的情况下预览搜索结果
    """
    try:
        # 验证token
        token = req.headers.get("x-access-token")
        if not token:
            return CommonResponse(
                status="error",
                msg="未提供访问令牌",
                code="401",
                data=None
            )

        user_info = utils.verify_access_token(token)
        if not user_info:
            return CommonResponse(
                status="error",
                msg="token验证失败",
                code="401",
                data=None
            )

        # 构建简化搜索请求
        search_request = EnhancedAdvancedSearchRequest(
            page=1,
            limit=limit,
            sort_by="added_time",
            sort_order="desc",
            name=name,
            tags=tags,
            category=category,
            status=status,
            downloader_name=downloader_name
        )

        # 如果提供了JSON条件，尝试解析
        if conditions_json:
            # 使用安全解析函数
            def is_list(obj: Any) -> bool:
                return isinstance(obj, list)

            conditions = safe_json_parse_with_validator(
                conditions_json,
                is_list,
                default=None,
                log_errors=True,
                error_context="(预览搜索条件)"
            )

            if conditions:
                # 简化条件为单个条件组
                search_request.condition_groups = [{
                    'logic': 'AND',
                    'conditions': [condition for condition in conditions if isinstance(condition, dict)]
                }]
            else:
                logger.warning(f"Invalid conditions format in preview: {conditions_json}")

        # 执行预览搜索
        logger.info(f"User {user_info.get('sub', user_info.get('username', 'unknown'))} previewing advanced search")

        result = service.search_torrents(search_request, user_info['user_id'])

        # 只返回预览数据，移除复杂字段以减少响应大小
        preview_data = []
        for torrent in result.get('data', []):
            preview_item = {
                'info_id': torrent.get('info_id'),
                'name': torrent.get('name'),
                'size': torrent.get('size'),
                'status': torrent.get('status'),
                'category': torrent.get('category'),
                'tags': torrent.get('tags'),
                'downloader_name': torrent.get('downloader_name'),
                'added_date': torrent.get('added_date')
            }
            preview_data.append(preview_item)

        return CommonResponse(
            status=result.get('status', 'failed'),
            msg=result.get('msg', '预览搜索失败'),
            code=result.get('code', '500'),
            data={
                'total': result.get('total', 0),
                'data': preview_data
            }
        )

    except HTTPException as e:
        logger.error(f"HTTP exception in search preview: {str(e)}")
        raise e

    except Exception as e:
        logger.error(f"Search preview failed: {str(e)}")
        return CommonResponse(
            status="error",
            msg=f"预览搜索失败: {str(e)}",
            code="500",
            data=None
        )