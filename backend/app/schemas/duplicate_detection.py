"""
重复检测相关的Pydantic模型定义

定义重复检测API的请求和响应模型
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TorrentInfo(BaseModel):
    """任务信息"""
    downloader_id: str = Field(..., description="下载器ID")
    torrent_name: str = Field(..., description="任务名称")
    torrent_size: int = Field(..., description="任务大小（字节）")
    hash: str = Field(..., description="任务hash值")

    model_config = {"from_attributes": True}


class DuplicateDetectionStart(BaseModel):
    """启动重复检测请求"""
    # 目前不需要参数，后续可以扩展（如指定下载器列表）
    pass


class DuplicateDetectionProgress(BaseModel):
    """检测进度响应"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    progress: int = Field(..., ge=0, le=100, description="进度百分比（0-100）")
    message: Optional[str] = Field(None, description="进度消息")

    model_config = {"from_attributes": True}


class DuplicateDetectionResult(BaseModel):
    """检测结果响应"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    success: bool = Field(..., description="是否成功")
    total_downloaders: int = Field(..., ge=0, description="总下载器数量")
    scanned_downloaders: int = Field(..., ge=0, description="成功扫描的下载器数量")
    total_torrents: int = Field(..., ge=0, description="总任务数量")
    duplicate_count: int = Field(..., ge=0, description="重复任务组数")
    duplicates: Dict[str, List[TorrentInfo]] = Field(
        default_factory=dict,
        description="重复任务字典，key为hash值，value为任务列表"
    )
    error: Optional[str] = Field(None, description="错误信息（仅在失败时）")

    model_config = {"from_attributes": True}


class DuplicateDetectionStartResponse(BaseModel):
    """启动重复检测的响应（返回任务ID）"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="初始任务状态")
    success: bool = Field(default=True, description="启动是否成功")
    total_downloaders: int = Field(default=0, description="总下载器数量")
    scanned_downloaders: int = Field(default=0, description="成功扫描的下载器数量")
    total_torrents: int = Field(default=0, description="总任务数量")
    duplicate_count: int = Field(default=0, description="重复任务组数")
    duplicates: Dict[str, List[TorrentInfo]] = Field(
        default_factory=dict,
        description="重复任务字典（初始为空）"
    )
