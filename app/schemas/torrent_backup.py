# -*- coding: utf-8 -*-
"""
种子文件备份API的Pydantic模型

定义种子文件备份相关的请求和响应数据模型。
所有API端点使用这些模型进行参数验证和响应序列化。

@author: btpManager Team
@file: torrent_backup.py
@time: 2026-02-15
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class TorrentFileBackupCreate(BaseModel):
    """
    创建种子文件备份请求模型

    用于手动触发种子文件备份的请求参数验证。
    """
    info_hash: str = Field(
        ...,
        min_length=40,
        max_length=40,
        description="种子的info_hash（40位十六进制字符串）",
        examples=["abc123def456789abc123def456789abc123def456789"]
    )

    torrent_name: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="种子文件名称",
        examples=["example.torrent"]
    )

    downloader_id: int = Field(
        ...,
        gt=0,
        description="下载器ID",
        examples=[1]
    )

    task_name: Optional[str] = Field(
        None,
        max_length=500,
        description="关联的任务名称（可选）",
        examples=["我的下载任务"]
    )

    uploader_id: Optional[int] = Field(
        None,
        gt=0,
        description="上传用户ID（可选）",
        examples=[1]
    )

    # 可选：直接从路径备份
    source_file_path: Optional[str] = Field(
        None,
        max_length=1000,
        description="源文件路径（如果从路径备份）",
        examples=["/path/to/torrent/file.torrent"]
    )


class TorrentFileBackupResponse(BaseModel):
    """
    种子文件备份响应模型

    返回单个种子文件备份的完整信息。
    """
    id: int = Field(..., description="主键ID")
    info_hash: str = Field(..., description="种子的info_hash")
    file_path: str = Field(..., description="种子文件存储路径")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    task_name: Optional[str] = Field(None, description="关联的任务名称")
    uploader_id: Optional[int] = Field(None, description="上传用户ID")
    downloader_id: Optional[int] = Field(None, description="关联的下载器ID")
    upload_time: Optional[datetime] = Field(None, description="上传时间")
    last_used_time: Optional[datetime] = Field(None, description="最后使用时间")
    use_count: int = Field(..., description="使用次数")
    is_deleted: bool = Field(..., description="逻辑删除标记")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "info_hash": "abc123def456789abc123def456789abc123def456789",
                "file_path": "backup/torrents/1_2026_02/example.torrent",
                "file_size": 102400,
                "task_name": "我的下载任务",
                "uploader_id": 1,
                "downloader_id": 1,
                "upload_time": "2026-02-15T12:00:00",
                "last_used_time": "2026-02-15T14:30:00",
                "use_count": 5,
                "is_deleted": False,
                "created_at": "2026-02-15T10:00:00",
                "updated_at": "2026-02-15T14:30:00"
            }
        }


class TorrentFileBackupListResponse(BaseModel):
    """
    种子文件备份列表响应模型

    返回种子文件备份列表（支持分页）。
    遵循项目统一的分页响应格式。
    """
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    pageSize: int = Field(..., ge=1, le=100, description="每页记录数")
    list: List[TorrentFileBackupResponse] = Field(
        default_factory=list,
        description="种子文件备份列表"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total": 100,
                "page": 1,
                "pageSize": 20,
                "list": [
                    {
                        "id": 1,
                        "info_hash": "abc123...",
                        "file_path": "backup/torrents/...",
                        "file_size": 102400,
                        "task_name": "任务1",
                        "downloader_id": 1,
                        "upload_time": "2026-02-15T12:00:00",
                        "use_count": 5,
                        "is_deleted": False,
                        "created_at": "2026-02-15T10:00:00",
                        "updated_at": "2026-02-15T14:30:00"
                    }
                ]
            }
        }


class TorrentFileBackupDelete(BaseModel):
    """
    删除种子文件备份请求模型

    用于删除种子文件备份的请求参数验证。
    """
    info_hash: str = Field(
        ...,
        min_length=40,
        max_length=40,
        description="要删除的种子的info_hash"
    )

    delete_physical_file: bool = Field(
        False,
        description="是否同时删除物理文件（默认仅逻辑删除）"
    )


class TorrentFileBackupBatchCreate(BaseModel):
    """
    批量创建种子文件备份请求模型

    用于批量备份种子文件。
    """
    backup_requests: List[TorrentFileBackupCreate] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="备份请求列表（最多50个）"
    )


class TorrentFileBackupBatchResponse(BaseModel):
    """
    批量备份响应模型

    返回批量备份操作的结果。
    """
    total: int = Field(..., ge=0, description="总数")
    success_count: int = Field(..., ge=0, description="成功数量")
    failed_count: int = Field(..., ge=0, description="失败数量")
    success_items: List[TorrentFileBackupResponse] = Field(
        default_factory=list,
        description="成功的备份项"
    )
    failed_items: List[dict] = Field(
        default_factory=list,
        description="失败的备份项（包含info_hash和错误信息）"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total": 10,
                "success_count": 8,
                "failed_count": 2,
                "success_items": [],
                "failed_items": [
                    {
                        "info_hash": "abc123...",
                        "error": "文件不存在"
                    }
                ]
            }
        }
