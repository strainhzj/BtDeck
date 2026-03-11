#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级搜索API模型 - 任务1.1.2
支持13字段全字段搜索和多选排除功能
"""

from typing import List, Dict, Any, Optional, Union, Literal
from pydantic import BaseModel, Field, validator
from datetime import datetime
import re

class SearchCondition(BaseModel):
    """搜索条件基类"""
    field: str = Field(..., description="搜索字段", example="name")
    operator: str = Field(..., description="操作符", example="contains")
    value: Union[str, List[str], int, float, bool, List[int], List[float]] = Field(..., description="搜索值", example="电影")

    @validator('operator')
    def validate_operator(cls, v):
        allowed_operators = {
            'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains',
            'not_contains', 'starts_with', 'ends_with', 'not_starts_with',
            'not_ends_with', 'in', 'not_in', 'is_null', 'is_not_null'
        }
        if v not in allowed_operators:
            raise ValueError(f'Invalid operator: {v}. Allowed: {allowed_operators}')
        return v

class MultiSelectCondition(SearchCondition):
    """多选排除条件"""
    mode: Literal['include', 'exclude'] = Field('include', description="模式：包含或排除", example="include")
    separator: str = Field(',', description="多值分隔符", example=",")

    @validator('value')
    def validate_multi_value(cls, v, values):
        if values.get('mode') == 'exclude' and not isinstance(v, list):
            # 对于排除模式，确保值是列表
            if isinstance(v, str):
                return [item.strip() for item in v.split(values.get('separator', ','))]
        return v

class SearchTemplate(BaseModel):
    """搜索模板"""
    id: Optional[str] = None
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(None, max_length=500, description="模板描述")
    conditions: List[Dict[str, Any]] = Field(..., description="搜索条件JSON")
    is_default: bool = Field(False, description="是否默认模板")
    is_public: bool = Field(False, description="是否公开模板")
    usage_count: int = Field(0, description="使用次数")
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None

class SearchGroup(BaseModel):
    """搜索条件组"""
    logic: Literal['AND', 'OR'] = Field('AND', description="组内逻辑关系")
    conditions: List[SearchCondition] = Field(..., description="组内条件列表")

class EnhancedAdvancedSearchRequest(BaseModel):
    """增强高级搜索请求"""
    # 基础分页参数
    page: int = Field(1, ge=1, le=1000, description="页码", example=1)
    limit: int = Field(20, ge=1, le=100, description="每页数量", example=20)
    sort_by: str = Field("added_time", description="排序字段", example="added_time")
    sort_order: Literal['asc', 'desc'] = Field("desc", description="排序方向", example="desc")

    # 基础过滤条件
    downloader_id: Optional[str] = Field(None, description="下载器ID", example="")
    downloader_name: Optional[str] = Field(None, description="下载器名称", example="")
    name: Optional[str] = Field(None, description="种子名称", example="")
    tags: Optional[str] = Field(None, description="标签", example="")
    category: Optional[str] = Field(None, description="分类", example="")
    status: Optional[str] = Field(None, description="状态", example="")

    # 数值范围过滤
    size_min: Optional[str] = Field(None, description="种子大小最小值", example="1GB")
    size_max: Optional[str] = Field(None, description="种子大小最大值", example="10GB")
    ratio_min: Optional[float] = Field(None, ge=0, description="分享比率最小值", example=0.5)
    ratio_max: Optional[float] = Field(None, ge=0, description="分享比率最大值", example=2.0)

    # 日期范围过滤
    added_date_min: Optional[str] = Field(None, description="添加时间最小值", example="2025-01-01")
    added_date_max: Optional[str] = Field(None, description="添加时间最大值", example="2025-12-31")
    completed_date_min: Optional[str] = Field(None, description="完成时间最小值", example="2025-01-01")
    completed_date_max: Optional[str] = Field(None, description="完成时间最大值", example="2025-12-31")

    # 高级搜索条件组
    condition_groups: Optional[List[SearchGroup]] = Field(None, description="条件组列表")
    between_group_logics: Optional[List[Literal['AND', 'OR']]] = Field(None, description="条件组之间的逻辑关系列表")

    # 多选排除字段
    status_multi: Optional[MultiSelectCondition] = Field(None, description="状态多选条件")
    category_multi: Optional[MultiSelectCondition] = Field(None, description="分类多选条件")
    tags_multi: Optional[MultiSelectCondition] = Field(None, description="标签多选条件")
    downloader_multi: Optional[MultiSelectCondition] = Field(None, description="下载器多选条件")

class SearchTemplateCreate(BaseModel):
    """创建搜索模板请求"""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(None, max_length=500, description="模板描述")
    conditions: Dict[str, Any] = Field(..., description="搜索条件")
    is_public: bool = Field(False, description="是否公开模板")

class SearchTemplateUpdate(BaseModel):
    """更新搜索模板请求"""
    id: str = Field(..., description="模板ID")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(None, max_length=500, description="模板描述")
    conditions: Optional[Dict[str, Any]] = Field(None, description="搜索条件")
    is_public: Optional[bool] = Field(None, description="是否公开模板")

class SearchTemplateResponse(BaseModel):
    """搜索模板响应"""
    id: str = Field(..., description="模板ID")
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., description="模板名称")
    description: Optional[str] = Field(None, description="模板描述")
    conditions: Dict[str, Any] = Field(..., description="搜索条件")
    is_default: bool = Field(..., description="是否默认模板")
    is_public: bool = Field(..., description="是否公开模板")
    usage_count: int = Field(..., description="使用次数")
    created_time: datetime = Field(..., description="创建时间")
    updated_time: Optional[datetime] = Field(None, description="更新时间")

class SearchTemplateDelete(BaseModel):
    """删除搜索模板请求"""
    template_id: str = Field(..., description="模板ID")

class AdvancedSearchResponse(BaseModel):
    """高级搜索响应"""
    total: int = Field(..., description="总记录数", example=1000)
    page: int = Field(..., description="当前页码", example=1)
    limit: int = Field(..., description="每页数量", example=20)
    total_pages: int = Field(..., description="总页数", example=50)
    data: List[Dict[str, Any]] = Field(..., description="搜索结果列表")

class TorrentDeleteRequest(BaseModel):
    """批量删除种子请求"""
    torrent_ids: List[str] = Field(..., min_items=1, max_items=100, description="种子ID列表")
    delete_data: bool = Field(True, description="是否删除数据文件", example=True)
    id_recycle: bool = Field(False, description="是否进入回收箱", example=False)

class SearchStatisticsResponse(BaseModel):
    """搜索统计响应"""
    field_distribution: Dict[str, int] = Field(..., description="字段分布统计")
    operator_usage: Dict[str, int] = Field(..., description="操作符使用统计")
    search_performance: Dict[str, float] = Field(..., description="搜索性能统计")

# 字段映射定义
SEARCH_FIELDS = {
    'info_id': {'name': '种子ID', 'type': 'string', 'searchable': True},
    'downloader_id': {'name': '下载器ID', 'type': 'string', 'searchable': True},
    'downloader_name': {'name': '下载器名称', 'type': 'string', 'searchable': True},
    'torrent_id': {'name': '种子内部ID', 'type': 'string', 'searchable': True},
    'hash': {'name': '哈希值', 'type': 'string', 'searchable': True},
    'name': {'name': '种子名称', 'type': 'string', 'searchable': True},
    'save_path': {'name': '保存路径', 'type': 'string', 'searchable': True},
    'size': {'name': '种子大小', 'type': 'float', 'searchable': True, 'range_filter': True},
    'status': {'name': '状态', 'type': 'string', 'searchable': True, 'multi_select': True},
    'torrent_file': {'name': '种子文件', 'type': 'string', 'searchable': False},
    'added_date': {'name': '添加时间', 'type': 'datetime', 'searchable': True, 'range_filter': True},
    'completed_date': {'name': '完成时间', 'type': 'datetime', 'searchable': True, 'range_filter': True},
    'ratio': {'name': '分享比率', 'type': 'float', 'searchable': True, 'range_filter': True},
    'ratio_limit': {'name': '比率限制', 'type': 'string', 'searchable': False},
    'tags': {'name': '标签', 'type': 'string', 'searchable': True, 'multi_select': True},
    'category': {'name': '分类', 'type': 'string', 'searchable': True, 'multi_select': True},
    'super_seeding': {'name': '超级做种', 'type': 'string', 'searchable': True},
    'enabled': {'name': '启用状态', 'type': 'boolean', 'searchable': True},
    'dr': {'name': '删除状态', 'type': 'integer', 'searchable': False}
}

# 操作符映射定义
SEARCH_OPERATORS = {
    # 字符串操作符
    'eq': '=',
    'ne': '!=',
    'contains': 'LIKE',
    'not_contains': 'NOT LIKE',
    'starts_with': 'LIKE',
    'ends_with': 'LIKE',
    'not_starts_with': 'NOT LIKE',
    'not_ends_with': 'NOT LIKE',
    'in': 'IN',
    'not_in': 'NOT IN',
    'is_null': 'IS NULL',
    'is_not_null': 'IS NOT NULL',
    # 数值操作符
    'gt': '>',
    'gte': '>=',
    'lt': '<',
    'lte': '<='
}

# 状态映射
STATUS_MAPPING = {
    'downloading': '下载中',
    'stalled': '暂停',
    'completed': '已完成',
    'seeding': '做种中',
    'paused': '已暂停',
    'error': '错误',
    'checking': '检查中',
    'moving': '移动中',
    'unknown': '未知'
}

# 分类映射
CATEGORY_MAPPING = {
    'movies': '电影',
    'tv': '电视剧',
    'music': '音乐',
    'games': '游戏',
    'software': '软件',
    'anime': '动漫',
    ' documentaries': '纪录片',
    'other': '其他'
}

def validate_size_string(size_str: Optional[str]) -> Optional[int]:
    """验证大小字符串并转换为字节"""
    if not size_str:
        return None

    # 匹配数字和单位
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?B?)$', size_str.strip(), re.IGNORECASE)
    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2).upper() if match.group(2) else 'B'

    # 转换为字节
    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    return int(number * multipliers.get(unit, 1))

def validate_date_string(date_str: Optional[str]) -> Optional[datetime]:
    """验证日期字符串"""
    if not date_str:
        return None

    # 尝试多种日期格式
    formats = [
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d',
        '%Y/%m/%d %H:%M:%S'
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None