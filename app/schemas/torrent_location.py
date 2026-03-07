# -*- coding: utf-8 -*-
"""
种子位置修改请求/响应模型

定义修改种子保存路径的API请求和响应格式。

@author: btpManager Team
@file: torrent_location.py
@time: 2026-03-04
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class SetLocationRequest(BaseModel):
    """修改种子保存路径请求"""
    downloader_id: str = Field(..., description="下载器ID")
    hashes: List[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="种子hash列表"
    )
    target_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="目标路径（绝对路径）"
    )
    move_files: bool = Field(..., description="是否移动已下载的文件")
    operator: Optional[str] = Field("admin", description="操作人")

    class Config:
        json_schema_extra = {
            "example": {
                "downloader_id": "uuid-string",
                "hashes": ["hash1", "hash2"],
                "target_path": "/new/download/path",
                "move_files": True,
                "operator": "admin"
            }
        }


class SetLocationResponse(BaseModel):
    """修改路径响应"""
    success: bool = Field(..., description="是否成功")
    moved_count: int = Field(..., description="成功修改的种子数量")
    failed_count: int = Field(..., description="失败的种子数量")
    error_message: Optional[str] = Field(None, description="错误信息")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "moved_count": 2,
                "failed_count": 0,
                "error_message": None
            }
        }
