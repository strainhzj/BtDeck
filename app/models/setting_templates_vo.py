# -*- coding: utf-8 -*-
"""
配置模板响应VO类

为配置模板相关接口提供统一的响应格式，包含下载器类型名称转换
"""
from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.setting_templates import DownloaderTypeEnum


class SettingTemplateVO(BaseModel):
    """配置模板VO，包含下载器类型名称转换"""

    id: Optional[int] = Field(None, description="模板ID", example=1)
    name: Optional[str] = Field(None, description="模板名称", example="qBittorrent标准模板")
    description: Optional[str] = Field(None, description="模板描述", example="适用于qBittorrent的标准配置模板")
    downloaderType: Optional[int] = Field(None, alias="downloaderType", description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    downloaderTypeName: Optional[str] = Field(None, alias="downloaderTypeName", description="下载器类型名称", example="qbittorrent")
    template_config: Optional[dict] = Field(None, alias="templateConfig", description="模板配置(JSON对象)")
    is_system_default: Optional[bool] = Field(None, alias="isSystemDefault", description="是否系统默认模板", example=False)
    created_by: Optional[int] = Field(None, alias="createdBy", description="创建者用户ID")
    created_at: Optional[str] = Field(None, alias="createdAt", description="创建时间(ISO格式)", example="2026-02-05T10:30:00")
    updated_at: Optional[str] = Field(None, alias="updatedAt", description="更新时间(ISO格式)", example="2026-02-05T10:30:00")
    path_mapping: Optional[dict] = Field(None, alias="pathMapping", description="路径映射配置")

    def __init__(
        self,
        id: Optional[int] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        downloader_type: Optional[int] = None,
        template_config: Optional[dict] = None,
        is_system_default: Optional[bool] = None,
        created_by: Optional[int] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        path_mapping: Optional[dict] = None,
        **kw: Any
    ):
        """
        初始化SettingTemplateVO

        Args:
            id: 模板ID
            name: 模板名称
            description: 模板描述
            downloader_type: 下载器类型枚举值(0/1)
            template_config: 模板配置字典
            is_system_default: 是否系统默认
            created_by: 创建者ID
            created_at: 创建时间
            updated_at: 更新时间
            path_mapping: 路径映射配置
        """
        # 使用统一的类型转换方法
        downloader_type_name = None
        if downloader_type is not None:
            downloader_type_int = DownloaderTypeEnum.normalize(downloader_type)
            downloader_type_name = DownloaderTypeEnum(downloader_type_int).to_name()

        # 格式化时间
        created_at_str = created_at.isoformat() if created_at else None
        updated_at_str = updated_at.isoformat() if updated_at else None

        super().__init__(
            id=id,
            name=name,
            description=description,
            downloaderType=downloader_type,
            downloaderTypeName=downloader_type_name,
            templateConfig=template_config,
            isSystemDefault=is_system_default,
            createdBy=created_by,
            createdAt=created_at_str,
            updatedAt=updated_at_str,
            pathMapping=path_mapping,
            **kw
        )
