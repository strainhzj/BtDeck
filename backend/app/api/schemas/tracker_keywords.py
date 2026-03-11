"""
Tracker关键词API相关的Pydantic模型

用于关键词CRUD操作的数据验证和序列化
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TrackerKeywordCreate(BaseModel):
    """创建关键词请求模型"""
    keyword_type: str = Field(..., description="关键词类型: candidate/ignored/success/failed", pattern="^(candidate|ignored|success|failed)$")
    keyword: str = Field(..., min_length=1, max_length=200, description="关键词内容")
    language: Optional[str] = Field(None, max_length=10, description="语言代码")
    priority: int = Field(100, ge=1, le=1000, description="优先级(1-1000)")
    enabled: bool = Field(True, description="是否启用")
    category: Optional[str] = Field(None, max_length=50, description="分类")
    description: Optional[str] = Field(None, max_length=200, description="描述")

    model_config = {"json_schema_extra": {"examples": [{
        "keyword_type": "success",
        "keyword": "success",
        "language": "en_US",
        "priority": 100,
        "enabled": True,
        "description": "通用成功标识"
    }]}}


class TrackerKeywordUpdate(BaseModel):
    """更新关键词请求模型"""
    keyword_type: Optional[str] = Field(None, pattern="^(candidate|ignored|success|failed)$")
    keyword: Optional[str] = Field(None, min_length=1, max_length=200)
    language: Optional[str] = Field(None, max_length=10)
    priority: Optional[int] = Field(None, ge=1, le=1000)
    enabled: Optional[bool] = None
    category: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=200)


class TrackerKeywordResponse(BaseModel):
    """关键词响应模型 - 使用别名映射数据库字段"""
    keyword_id: str = Field(alias="keywordId")
    keyword_type: str = Field(alias="keywordType")
    keyword: str = Field(alias="keyword")
    language: Optional[str] = Field(alias="language")
    priority: int = Field(alias="priority")
    enabled: bool = Field(alias="enabled")
    category: Optional[str] = Field(alias="category")
    description: Optional[str] = Field(alias="description")
    create_time: datetime = Field(alias="createTime")
    update_time: datetime = Field(alias="updateTime")

    model_config = {"from_attributes": True, "populate_by_name": True}


class BatchOperationRequest(BaseModel):
    """批量操作请求模型"""
    keyword_ids: list[str] = Field(..., min_length=1, max_length=100, description="关键词ID列表")
