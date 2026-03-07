"""
标签管理 Pydantic 数据模型

定义标签管理API的请求和响应数据模型，实现数据验证。
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime


# ==================== 请求模型 ====================

class TagCreateRequest(BaseModel):
    """创建标签请求"""
    downloader_id: str = Field(..., description="下载器ID")
    tag_name: str = Field(..., min_length=1, max_length=255, description="标签名称")
    tag_type: str = Field(..., description="标签类型(category/tag)")
    color: Optional[str] = Field(None, description="颜色代码(HEX格式，如#FF5733)")

    @field_validator('tag_type')
    @classmethod
    def validate_tag_type(cls, v: str) -> str:
        """验证标签类型"""
        if v not in ('category', 'tag'):
            raise ValueError('tag_type必须是category或tag')
        return v

    @field_validator('color')
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        """验证颜色格式"""
        if v is not None:
            if not v.startswith('#'):
                raise ValueError('颜色代码必须以#开头')
            if len(v) != 7:
                raise ValueError('颜色代码必须是7位HEX格式(如#FF5733)')
            # 验证是否为有效的HEX颜色
            hex_part = v[1:]
            try:
                int(hex_part, 16)
            except ValueError:
                raise ValueError('颜色代码必须是有效的HEX格式')
        return v


class TagUpdateRequest(BaseModel):
    """更新标签请求"""
    tag_name: Optional[str] = Field(None, min_length=1, max_length=255, description="标签名称")
    tag_type: Optional[str] = Field(None, description="标签类型(category/tag)")
    color: Optional[str] = Field(None, description="颜色代码(HEX格式)")

    @field_validator('tag_type')
    @classmethod
    def validate_tag_type(cls, v: Optional[str]) -> Optional[str]:
        """验证标签类型"""
        if v is not None and v not in ('category', 'tag'):
            raise ValueError('tag_type必须是category或tag')
        return v

    @field_validator('color')
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        """验证颜色格式"""
        if v is not None:
            if not v.startswith('#'):
                raise ValueError('颜色代码必须以#开头')
            if len(v) != 7:
                raise ValueError('颜色代码必须是7位HEX格式(如#FF5733)')
            hex_part = v[1:]
            try:
                int(hex_part, 16)
            except ValueError:
                raise ValueError('颜色代码必须是有效的HEX格式')
        return v


class AssignTagsRequest(BaseModel):
    """分配标签请求（单个种子）"""
    downloader_id: str = Field(..., description="下载器ID")
    torrent_hash: str = Field(..., description="种子哈希值")
    tag_ids: List[str] = Field(..., min_length=1, description="标签ID列表")

    @field_validator('tag_ids')
    @classmethod
    def validate_tag_ids(cls, v: List[str]) -> List[str]:
        """验证标签ID列表不为空"""
        if not v:
            raise ValueError('tag_ids不能为空')
        return v


class BatchAssignTagsRequest(BaseModel):
    """批量分配标签请求"""
    downloader_id: str = Field(..., description="下载器ID")
    assignments: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="分配任务列表，示例:[{\"torrent_hash\": \"abc\", \"tag_ids\": [\"tag1\", \"tag2\"]}, ...]"
    )

    @field_validator('assignments')
    @classmethod
    def validate_assignments(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证分配任务列表"""
        for idx, assignment in enumerate(v):
            if 'torrent_hash' not in assignment:
                raise ValueError(f'assignments[{idx}]缺少torrent_hash字段')
            if 'tag_ids' not in assignment or not assignment['tag_ids']:
                raise ValueError(f'assignments[{idx}]缺少或空tag_ids字段')
        return v


class RemoveTagsRequest(BaseModel):
    """移除标签请求"""
    torrent_hash: str = Field(..., description="种子哈希值")
    tag_ids: List[str] = Field(..., min_length=1, description="要移除的标签ID列表")

    @field_validator('tag_ids')
    @classmethod
    def validate_tag_ids(cls, v: List[str]) -> List[str]:
        """验证标签ID列表不为空"""
        if not v:
            raise ValueError('tag_ids不能为空')
        return v


# ==================== 响应模型 ====================


class DeleteTagRequest(BaseModel):
    """删除标签请求（支持种子转移）"""
    target_category: Optional[str] = Field(
        None,
        description="目标分类名称（仅分类删除时使用，空字符串表示未分类）"
    )

class TagResponse(BaseModel):
    """标签响应"""
    tag_id: str
    downloader_id: str
    tag_name: str
    tag_type: str
    color: Optional[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TagListResponse(BaseModel):
    """标签列表响应（带分页）"""
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    pageSize: int = Field(..., description="每页记录数")
    list: List[TagResponse] = Field(..., description="标签列表")


class AssignTagsResponse(BaseModel):
    """分配标签响应"""
    assigned_count: int = Field(..., description="成功分配的标签数")
    total_count: int = Field(..., description="请求分配的标签总数")
    message: str = Field(..., description="操作结果消息")


class BatchAssignResponse(BaseModel):
    """批量分配响应"""
    success_count: int = Field(..., description="成功分配数")
    failed_count: int = Field(..., description="失败数")
    total_assignments: int = Field(..., description="总分配任务数")
    message: str = Field(..., description="操作结果消息")


class RemoveTagsResponse(BaseModel):
    """移除标签响应"""
    removed_count: int = Field(..., description="成功移除的标签数")
    failed_count: int = Field(..., description="失败数")
    message: str = Field(..., description="操作结果消息")


class CategorySupportResponse(BaseModel):
    """分类支持检查响应"""
    supported: bool = Field(..., description="是否支持分类功能")
    require_fallback: bool = Field(..., description="是否需要降级策略")
    downloader_type: int = Field(..., description="下载器类型(0=qBittorrent, 1=Transmission)")
    message: str = Field(..., description="提示信息")
