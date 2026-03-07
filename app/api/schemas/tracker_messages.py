"""
Tracker消息记录API相关的Pydantic模型

用于消息记录查询、添加到关键词池、批量操作的数据验证和序列化
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TrackerMessageResponse(BaseModel):
    """消息记录响应模型 - 使用别名映射数据库字段"""
    log_id: str = Field(alias="logId")
    tracker_host: str = Field(alias="trackerHost")
    msg: str = Field(alias="msg")
    first_seen: datetime = Field(alias="firstSeen")
    last_seen: datetime = Field(alias="lastSeen")
    occurrence_count: int = Field(alias="occurrenceCount")
    sample_torrents: Optional[str] = Field(None, alias="sampleTorrents")
    sample_urls: Optional[str] = Field(None, alias="sampleUrls")
    is_processed: bool = Field(alias="isProcessed")
    keyword_type: Optional[str] = Field(None, alias="keywordType")

    model_config = {"from_attributes": True, "populate_by_name": True}


class AddToPoolRequest(BaseModel):
    """添加到关键词池请求"""
    keyword_type: str = Field(..., pattern="^(candidate|ignored|success|failed)$", description="添加到哪个池")
    language: Optional[str] = Field(None, max_length=10, description="语言代码")
    priority: int = Field(100, ge=1, le=1000, description="优先级")
    description: Optional[str] = Field(None, max_length=200, description="描述")


class BatchOperationRequest(BaseModel):
    """批量操作请求模型"""
    ids: list[str] = Field(..., min_length=1, max_length=100, description="消息ID列表")


class BatchAddToPoolRequest(BaseModel):
    """批量添加消息到关键词池请求（合并版本）"""
    log_ids: list[str] = Field(..., min_length=1, max_length=100, description="消息ID列表", alias="log_ids")
    keyword_type: str = Field(..., pattern="^(candidate|ignored|success|failed)$", description="添加到哪个池")
    language: Optional[str] = Field(None, max_length=10, description="语言代码")
    priority: int = Field(100, ge=1, le=1000, description="优先级")
    description: Optional[str] = Field(None, max_length=200, description="描述")

    model_config = {"populate_by_name": True}


class BatchDeleteMessagesRequest(BaseModel):
    """批量删除消息请求（使用log_ids字段）"""
    log_ids: list[str] = Field(..., min_length=1, max_length=100, description="消息ID列表", alias="log_ids")

    model_config = {"populate_by_name": True}


class MatchTestRequest(BaseModel):
    """匹配测试请求"""
    msg: str = Field(..., min_length=1, description="测试的消息")
    originalStatus: str = Field("未联系", description="原始状态")
    language: Optional[str] = Field(None, description="语言代码")


class MatchTestResponse(BaseModel):
    """匹配测试响应"""
    originalStatus: str
    finalStatus: str
    matchedKeywords: list[str]  # 匹配到的关键词列表
    matchType: str  # "success" 或 "failure" 或 "none"

    # 添加computed property用于兼容
    @property
    def matched(self) -> bool:
        """是否匹配到关键词 (兼容旧版本测试代码)"""
        return len(self.matchedKeywords) > 0

    # 添加computed property用于兼容
    @property
    def judgment_result(self) -> str:
        """判断结果 (兼容旧版本测试代码)"""
        return self.matchType

    model_config = {"from_attributes": True}
