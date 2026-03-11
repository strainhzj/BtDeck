# -*- coding: utf-8 -*-
"""
种子转移API的Pydantic模型

定义种子转移相关的请求和响应数据模型。
所有API端点使用这些模型进行参数验证和响应序列化。

@author: btpManager Team
@file: seed_transfer.py
@time: 2026-02-15
"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class SeedTransferRequest(BaseModel):
    """
    单个种子转移请求模型

    用于转移单个种子到目标下载器的请求参数验证。
    """
    source_downloader_id: str = Field(
        ...,
        min_length=1,
        description="源下载器ID（UUID字符串）",
        examples=["300e79ff-eca6-4303-9f98-4207a1c5152a"]
    )

    target_downloader_id: str = Field(
        ...,
        min_length=1,
        description="目标下载器ID（UUID字符串）",
        examples=["400e79ff-eca6-4303-9f98-4207a1c5152a"]
    )

    info_hash: str = Field(
        ...,
        min_length=40,
        max_length=40,
        description="种子的info_hash（40位十六进制字符串）",
        examples=["abc123def456789abc123def456789abc123def456789"]
    )

    target_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="目标保存路径（绝对路径）",
        examples=["/downloads/movies"]
    )

    delete_source: bool = Field(
        False,
        description="是否删除源下载器中的原种子（默认False）"
    )

    @field_validator('info_hash')
    @classmethod
    def validate_info_hash(cls, v: str) -> str:
        """验证info_hash格式（40位十六进制）"""
        if not all(c in '0123456789abcdefABCDEF' for c in v):
            raise ValueError('info_hash必须为40位十六进制字符串')
        return v.lower()

    @field_validator('target_downloader_id')
    @classmethod
    def different_downloaders(cls, v: str, info) -> str:
        """验证源下载器和目标下载器不能相同"""
        if 'source_downloader_id' in info.data and v == info.data['source_downloader_id']:
            raise ValueError('源下载器和目标下载器不能相同')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "source_downloader_id": 1,
                "target_downloader_id": 2,
                "info_hash": "abc123def456789abc123def456789abc123def456789",
                "target_path": "/downloads/movies",
                "delete_source": False
            }
        }


class SeedTransferResponse(BaseModel):
    """
    单个种子转移响应模型

    返回单个种子转移操作的完整结果。
    """
    success: bool = Field(..., description="转移是否成功")
    transfer_status: str = Field(
        ...,
        description="转移状态：success/failed/partial"
    )
    torrent_name: Optional[str] = Field(None, description="种子任务名称")
    source_downloader_id: str = Field(..., description="源下载器ID")
    source_downloader_name: Optional[str] = Field(None, description="源下载器名称")
    target_downloader_id: str = Field(..., description="目标下载器ID")
    target_downloader_name: Optional[str] = Field(None, description="目标下载器名称")
    info_hash: str = Field(..., description="种子info_hash")
    source_path: Optional[str] = Field(None, description="源保存路径")
    target_path: str = Field(..., description="目标保存路径")
    delete_source: bool = Field(..., description="是否删除了原种子")
    transfer_duration: Optional[int] = Field(None, description="转移耗时（毫秒）")
    error_message: Optional[str] = Field(None, description="错误信息（如果失败）")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "transfer_status": "success",
                "torrent_name": "Example Movie",
                "source_downloader_id": 1,
                "source_downloader_name": "Primary Downloader",
                "target_downloader_id": 2,
                "target_downloader_name": "Backup Downloader",
                "info_hash": "abc123def456789abc123def456789abc123def456789",
                "source_path": "/downloads/temp",
                "target_path": "/downloads/movies",
                "delete_source": False,
                "transfer_duration": 2500,
                "error_message": None
            }
        }


class SeedTransferBatchRequest(BaseModel):
    """
    批量种子转移请求模型

    用于批量转移多个种子到目标下载器的请求参数验证。
    """
    source_downloader_id: str = Field(
        ...,
        min_length=1,
        description="源下载器ID（UUID字符串）",
        examples=["300e79ff-eca6-4303-9f98-4207a1c5152a"]
    )

    target_downloader_id: str = Field(
        ...,
        min_length=1,
        description="目标下载器ID（UUID字符串）",
        examples=["400e79ff-eca6-4303-9f98-4207a1c5152a"]
    )

    info_hashes: List[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="要转移的种子info_hash列表（最多50个）"
    )

    target_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="目标保存路径（绝对路径）",
        examples=["/downloads/movies"]
    )

    delete_source: bool = Field(
        False,
        description="是否删除源下载器中的原种子（默认False）"
    )

    @field_validator('info_hashes')
    @classmethod
    def validate_info_hashes(cls, v: List[str]) -> List[str]:
        """验证info_hash列表格式"""
        for info_hash in v:
            if len(info_hash) != 40:
                raise ValueError(f'info_hash长度必须为40位: {info_hash}')
            if not all(c in '0123456789abcdefABCDEF' for c in info_hash):
                raise ValueError(f'info_hash必须为十六进制字符串: {info_hash}')
        return [h.lower() for h in v]

    @field_validator('target_downloader_id')
    @classmethod
    def different_downloaders(cls, v: str, info) -> str:
        """验证源下载器和目标下载器不能相同"""
        if 'source_downloader_id' in info.data and v == info.data['source_downloader_id']:
            raise ValueError('源下载器和目标下载器不能相同')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "source_downloader_id": 1,
                "target_downloader_id": 2,
                "info_hashes": [
                    "abc123def456789abc123def456789abc123def456789",
                    "def456789abc123def456789abc123def456789abc123"
                ],
                "target_path": "/downloads/movies",
                "delete_source": False
            }
        }


class SeedTransferBatchResponse(BaseModel):
    """
    批量种子转移响应模型

    返回批量种子转移操作的完整结果。
    """
    total_count: int = Field(..., ge=0, description="总数")
    success_count: int = Field(..., ge=0, description="成功数量")
    failed_count: int = Field(..., ge=0, description="失败数量")
    results: List[SeedTransferResponse] = Field(
        default_factory=list,
        description="每个种子的转移结果"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_count": 3,
                "success_count": 2,
                "failed_count": 1,
                "results": [
                    {
                        "success": True,
                        "transfer_status": "success",
                        "torrent_name": "Example 1",
                        "source_downloader_id": 1,
                        "source_downloader_name": "Primary",
                        "target_downloader_id": 2,
                        "target_downloader_name": "Backup",
                        "info_hash": "abc123...",
                        "source_path": "/downloads/temp",
                        "target_path": "/downloads/movies",
                        "delete_source": False,
                        "transfer_duration": 2500,
                        "error_message": None
                    },
                    {
                        "success": True,
                        "transfer_status": "success",
                        "torrent_name": "Example 2",
                        "source_downloader_id": 1,
                        "source_downloader_name": "Primary",
                        "target_downloader_id": 2,
                        "target_downloader_name": "Backup",
                        "info_hash": "def456...",
                        "source_path": "/downloads/temp",
                        "target_path": "/downloads/movies",
                        "delete_source": False,
                        "transfer_duration": 2300,
                        "error_message": None
                    },
                    {
                        "success": False,
                        "transfer_status": "failed",
                        "torrent_name": "Example 3",
                        "source_downloader_id": 1,
                        "source_downloader_name": "Primary",
                        "target_downloader_id": 2,
                        "target_downloader_name": "Backup",
                        "info_hash": "ghi789...",
                        "source_path": None,
                        "target_path": "/downloads/movies",
                        "delete_source": False,
                        "transfer_duration": 500,
                        "error_message": "种子文件备份中未找到该种子"
                    }
                ]
            }
        }
