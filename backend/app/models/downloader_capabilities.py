# -*- coding: utf-8 -*-
"""
下载器能力配置模型

提供下载器能力配置的数据库模型，支持持久化存储和查询
"""
from typing import Any, Optional, Dict
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, func
from sqlalchemy.orm import relationship
from app.database import Base
import json


class DownloaderCapabilities(Base):
    """下载器能力配置表

    持久化存储每个下载器的功能开关配置，支持用户自定义和离线使用

    设计原则：
    - 用户优先：用户配置的能力开关优先于下载器实际能力
    - 降级友好：下载器离线时使用数据库配置，在线时自动同步
    - 灵活扩展：使用JSON存储扩展能力，便于后续新增功能
    """

    __tablename__ = "downloader_capabilities"

    # ========== 主键和外键 ==========
    id = Column(Integer, primary_key=True, index=True, comment='主键ID')
    downloader_id = Column(String, nullable=False, unique=True, index=True, comment='下载器ID，关联bt_downloaders表')
    downloader_setting_id = Column(Integer, nullable=True, index=True, comment='下载器配置ID（可选），关联downloader_settings表')

    # ========== 核心能力开关 ==========
    supports_speed_scheduling = Column(
        Boolean, nullable=False, server_default='0',
        comment='是否支持分时段限速（应用层实现）'
    )
    supports_transfer_speed = Column(
        Boolean, nullable=False, server_default='1',
        comment='是否支持传输速度控制'
    )
    supports_connection_limits = Column(
        Boolean, nullable=False, server_default='1',
        comment='是否支持连接限制'
    )
    supports_queue_settings = Column(
        Boolean, nullable=False, server_default='1',
        comment='是否支持队列设置'
    )
    supports_download_paths = Column(
        Boolean, nullable=False, server_default='0',
        comment='是否支持路径设置（Transmission支持）'
    )
    supports_port_settings = Column(
        Boolean, nullable=False, server_default='1',
        comment='是否支持端口设置'
    )
    supports_advanced_settings = Column(
        Boolean, nullable=False, server_default='1',
        comment='是否支持高级设置'
    )
    supports_peer_limits = Column(
        Boolean, nullable=False, server_default='0',
        comment='是否支持Peer限制'
    )

    # ========== 扩展能力配置（JSON格式） ==========
    extended_capabilities = Column(
        Text, nullable=True,
        comment='扩展能力配置（JSON格式），用于存储未来新增的能力开关'
    )

    # ========== 同步状态 ==========
    synced_from_downloader = Column(
        Boolean, nullable=False, server_default='0',
        comment='是否已从下载器同步过能力'
    )
    last_sync_at = Column(
        DateTime, nullable=True,
        comment='最后一次同步时间'
    )
    manual_override = Column(
        Boolean, nullable=False, server_default='0',
        comment='是否为用户手动覆盖（手动覆盖后不再自动同步）'
    )

    # ========== 审计字段 ==========
    created_at = Column(
        DateTime, nullable=False, server_default=func.now(),
        comment='创建时间'
    )
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now(),
        comment='更新时间'
    )

    def __init__(
        self,
        downloader_id: str,
        downloader_setting_id: Optional[int] = None,
        supports_speed_scheduling: bool = False,
        supports_transfer_speed: bool = True,
        supports_connection_limits: bool = True,
        supports_queue_settings: bool = True,
        supports_download_paths: bool = False,
        supports_port_settings: bool = True,
        supports_advanced_settings: bool = True,
        supports_peer_limits: bool = False,
        extended_capabilities: Optional[str] = None,
        synced_from_downloader: bool = False,
        manual_override: bool = False,
        **kw: Any
    ):
        """初始化下载器能力配置

        Args:
            downloader_id: 下载器ID
            downloader_setting_id: 下载器配置ID（可选）
            supports_speed_scheduling: 是否支持分时段限速
            supports_transfer_speed: 是否支持传输速度控制
            supports_connection_limits: 是否支持连接限制
            supports_queue_settings: 是否支持队列设置
            supports_download_paths: 是否支持路径设置
            supports_port_settings: 是否支持端口设置
            supports_advanced_settings: 是否支持高级设置
            supports_peer_limits: 是否支持Peer限制
            extended_capabilities: 扩展能力配置（JSON字符串）
            synced_from_downloader: 是否已从下载器同步
            manual_override: 是否为手动覆盖
        """
        super().__init__(**kw)
        self.downloader_id = downloader_id
        self.downloader_setting_id = downloader_setting_id
        self.supports_speed_scheduling = supports_speed_scheduling
        self.supports_transfer_speed = supports_transfer_speed
        self.supports_connection_limits = supports_connection_limits
        self.supports_queue_settings = supports_queue_settings
        self.supports_download_paths = supports_download_paths
        self.supports_port_settings = supports_port_settings
        self.supports_advanced_settings = supports_advanced_settings
        self.supports_peer_limits = supports_peer_limits
        self.extended_capabilities = extended_capabilities
        self.synced_from_downloader = synced_from_downloader
        self.manual_override = manual_override

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式

        Returns:
            Dict[str, Any]: 包含所有字段的字典
        """
        result = {
            "id": self.id,
            "downloader_id": self.downloader_id,
            "downloader_setting_id": self.downloader_setting_id,
            "supports_speed_scheduling": self.supports_speed_scheduling,
            "supports_transfer_speed": self.supports_transfer_speed,
            "supports_connection_limits": self.supports_connection_limits,
            "supports_queue_settings": self.supports_queue_settings,
            "supports_download_paths": self.supports_download_paths,
            "supports_port_settings": self.supports_port_settings,
            "supports_advanced_settings": self.supports_advanced_settings,
            "supports_peer_limits": self.supports_peer_limits,
            "extended_capabilities": self.extended_capabilities,
            "synced_from_downloader": self.synced_from_downloader,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "manual_override": self.manual_override,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        # 解析扩展能力配置
        if self.extended_capabilities:
            try:
                result["extended_capabilities_parsed"] = json.loads(self.extended_capabilities)
            except json.JSONDecodeError:
                result["extended_capabilities_parsed"] = {}

        return result

    def get_capabilities_dict(self) -> Dict[str, bool]:
        """获取能力字典（兼容原有格式）

        Returns:
            Dict[str, bool]: 能力字典，键为能力名称（驼峰命名），值为是否支持
        """
        capabilities = {
            "transferSpeed": self.supports_transfer_speed,
            "authentication": True,  # 所有下载器都支持认证
            "connectionLimits": self.supports_connection_limits,
            "queueSettings": self.supports_queue_settings,
            "supports_speed_scheduling": self.supports_speed_scheduling,  # ⚠️ 前端期望的字段名
            "downloadPaths": self.supports_download_paths,
            "portSettings": self.supports_port_settings,
            "advancedSettings": self.supports_advanced_settings,
            "peerLimits": self.supports_peer_limits,
        }

        # 合并扩展能力配置
        if self.extended_capabilities:
            try:
                extended = json.loads(self.extended_capabilities)
                capabilities.update(extended)
            except json.JSONDecodeError as e:
                import logging
                logging.warning(f"解析扩展能力配置失败: {e}")

        return capabilities

    def update_from_downloader_capabilities(
        self,
        downloader_capabilities: Dict[str, bool],
        force: bool = False
    ) -> None:
        """从下载器能力更新配置

        Args:
            downloader_capabilities: 从下载器获取的能力字典（蛇形命名）
            force: 是否强制更新（忽略manual_override标记）

        注意：
        - 如果 manual_override=True，则不会自动更新
        - 除非 force=True 强制更新
        """
        # 检查是否为手动覆盖
        if self.manual_override and not force:
            import logging
            logging.info(f"下载器 {self.downloader_id} 的能力配置为手动覆盖，跳过自动同步")
            return

        # 映射规则：蛇形命名 → 模型字段
        field_mapping = {
            "schedule_speed": "supports_speed_scheduling",
            "transfer_speed": "supports_transfer_speed",
            "connection_limits": "supports_connection_limits",
            "queue_settings": "supports_queue_settings",
            "download_paths": "supports_download_paths",
            "port_settings": "supports_port_settings",
            "advanced_settings": "supports_advanced_settings",
            "peer_limits": "supports_peer_limits",
        }

        # 更新核心能力开关
        for key, value in downloader_capabilities.items():
            if key in field_mapping:
                field_name = field_mapping[key]
                setattr(self, field_name, value)

        # 更新同步状态
        self.synced_from_downloader = True
        self.last_sync_at = datetime.now()

    def set_manual_override(self, override: bool = True) -> None:
        """设置手动覆盖标记

        Args:
            override: 是否为手动覆盖
        """
        self.manual_override = override
