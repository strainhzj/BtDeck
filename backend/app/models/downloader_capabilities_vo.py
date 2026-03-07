# -*- coding: utf-8 -*-
"""
下载器能力响应VO类

为下载器能力查询接口提供统一的响应格式，包含下载器类型名称转换
"""
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field, ConfigDict


class DownloaderCapabilitiesVO(BaseModel):
    """下载器能力VO，包含下载器类型名称转换"""

    model_config = ConfigDict(
        populate_by_name=True,  # 允许使用别名或字段名
        alias_generator=lambda field_name: field_name,  # 不自动生成别名
        by_alias=False  # 默认使用字段名而非别名
    )

    downloader_id: Optional[str] = Field(None, alias="downloaderId", description="下载器ID", example="d2f6192e-b197-4632-b4eb-bb7604446c07")
    downloader_type: Optional[int] = Field(None, alias="downloaderType", description="下载器类型(0=qBittorrent, 1=Transmission)", example=0)
    downloaderTypeName: Optional[str] = Field(None, alias="downloaderTypeName", description="下载器类型名称", example="qbittorrent")
    capabilities: Optional[Dict[str, Any]] = Field(None, description="下载器支持的功能列表")

    def __init__(
        self,
        downloader_id: Optional[str] = None,
        downloader_type: Optional[int] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        **kw: Any
    ):
        """
        初始化DownloaderCapabilitiesVO

        Args:
            downloader_id: 下载器ID
            downloader_type: 下载器类型枚举值(0/1)
            capabilities: 能力列表字典（蛇形命名，将自动转换为驼峰命名）
        """
        # 转换枚举值为字符串名称
        downloader_type_name = None
        if downloader_type is not None:
            if downloader_type == 0 or downloader_type == "0":
                downloader_type_name = "qbittorrent"
            elif downloader_type == 1 or downloader_type == "1":
                downloader_type_name = "transmission"
            else:
                # 如果已经是字符串，直接使用
                downloader_type_name = downloader_type if isinstance(downloader_type, str) else str(downloader_type)

        # 转换 capabilities 字段的键名（蛇形命名 -> 驼峰命名）
        converted_capabilities = None
        if capabilities:
            converted_capabilities = self._convert_capabilities_keys(capabilities)

        super().__init__(
            downloaderId=downloader_id,
            downloaderType=downloader_type,
            downloaderTypeName=downloader_type_name,
            capabilities=converted_capabilities,
            **kw
        )

    @staticmethod
    def _convert_capabilities_keys(capabilities: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 capabilities 字典的键名从蛇形命名转换为驼峰命名

        Args:
            capabilities: 原始 capabilities 字典（蛇形命名）

        Returns:
            Dict[str, Any]: 转换后的 capabilities 字典（驼峰命名）
        """
        # 字段名映射表（蛇形命名 -> 驼峰命名）
        key_mapping = {
            "transfer_speed": "transferSpeed",
            "authentication": "authentication",
            "connection_limits": "connectionLimits",
            "queue_settings": "queueSettings",
            "schedule_speed": "supports_speed_scheduling",  # ⚠️ 特殊映射：schedule_speed -> supports_speed_scheduling
            "download_paths": "downloadPaths",
            "port_settings": "portSettings",
            "advanced_settings": "advancedSettings",
            "peer_limits": "peerLimits"
        }

        converted = {}
        for key, value in capabilities.items():
            # 使用映射表转换键名，如果映射表中不存在则保持原样
            new_key = key_mapping.get(key, key)
            converted[new_key] = value

        return converted
