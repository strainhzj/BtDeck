# -*- coding: utf-8 -*-
"""
配置模板模型

用于存储可复用的下载器配置模板
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.downloader_settings import SpeedUnitEnum
import enum
import logging
import json

logger = logging.getLogger(__name__)


class DownloaderTypeEnum(enum.IntEnum):
    """下载器类型枚举（整数类型）"""
    QBITTORRENT = 0  # qBittorrent
    TRANSMISSION = 1  # Transmission

    @classmethod
    def from_value(cls, value: int) -> 'DownloaderTypeEnum':
        """从整数值获取枚举

        Args:
            value: 下载器类型整数值 (0, 1)

        Returns:
            DownloaderTypeEnum: 对应的枚举值

        Raises:
            ValueError: 如果值无效
        """
        try:
            return cls(value)
        except ValueError:
            valid_values = [e.value for e in cls]
            raise ValueError(
                f"无效的下载器类型: '{value}'. "
                f"有效值为: {valid_values} (0=qBittorrent, 1=Transmission)"
            )

    def is_qbittorrent(self) -> bool:
        """是否为qBittorrent类型

        Returns:
            bool: 是qBittorrent返回True
        """
        return self == DownloaderTypeEnum.QBITTORRENT

    def is_transmission(self) -> bool:
        """是否为Transmission类型

        Returns:
            bool: 是Transmission返回True
        """
        return self == DownloaderTypeEnum.TRANSMISSION

    def to_name(self) -> str:
        """转换为类型名称字符串

        Returns:
            str: "qbittorrent" 或 "transmission"
        """
        return "qbittorrent" if self == DownloaderTypeEnum.QBITTORRENT else "transmission"


class SettingTemplate(Base):
    """
    配置模板表

    存储可复用的下载器配置模板，支持快速应用到多个下载器
    """
    __tablename__ = "setting_templates"

    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 模板基本信息
    name = Column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment='模板名称，如"qBittorrent标准模板"'
    )

    description = Column(
        String(500),
        nullable=True,
        comment='模板描述'
    )

    # 下载器类型（使用Integer存储枚举值）
    downloader_type = Column(
        Integer,
        nullable=False,
        index=True,
        comment='下载器类型：0=qBittorrent, 1=Transmission'
    )

    # 模板配置（JSON格式，结构与downloader_settings相同）
    template_config = Column(
        Text,
        nullable=False,
        comment='模板配置（JSON格式），包含速度、认证、高级设置等'
    )

    # 模板元数据
    is_system_default = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment='是否为系统默认模板'
    )

    created_by = Column(
        Integer,
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        comment='创建者用户ID（系统默认模板为NULL）'
    )

    # 路径映射配置（可选）
    path_mapping = Column(
        Text,
        nullable=True,
        comment='路径映射配置（JSON格式）'
    )

    # 时间戳
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        index=True,
        comment='创建时间'
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        index=True,
        comment='更新时间'
    )

    # 关系定义
    # 关联到创建用户（多对一，可选）
    # creator = relationship("User", back_populates="templates")

    # 唯一约束
    __table_args__ = (
        UniqueConstraint('name', name='uq_setting_templates_name'),
    )

    def __init__(
        self,
        name=None,
        description=None,
        downloader_type=None,
        template_config=None,
        is_system_default=False,
        created_by=None,
        path_mapping=None,
        **kwargs
    ):
        super().__init__(**kwargs)
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if downloader_type is not None:
            self.downloader_type = downloader_type
        if template_config is not None:
            # 如果传入字典，转换为JSON字符串
            if isinstance(template_config, dict):
                self.template_config = json.dumps(template_config, ensure_ascii=False)
            else:
                self.template_config = template_config
        if is_system_default is not None:
            self.is_system_default = is_system_default
        if created_by is not None:
            self.created_by = created_by
        if path_mapping is not None:
            # 如果传入字典或对象，转换为JSON字符串
            if isinstance(path_mapping, dict):
                self.path_mapping = json.dumps(path_mapping, ensure_ascii=False)
            elif hasattr(path_mapping, 'json'):
                # Pydantic模型对象
                self.path_mapping = path_mapping.json()
            else:
                self.path_mapping = path_mapping

    def get_config_dict(self):
        """
        获取模板配置的字典形式

        Returns:
            dict: 模板配置的字典表示
        """
        if not self.template_config:
            return {}
        try:
            return json.loads(self.template_config)
        except json.JSONDecodeError as e:
            logger.error(f"解析模板配置失败: {e}")
            return {}

    def set_config_dict(self, config_dict):
        """
        设置模板配置（从字典转换为JSON字符串）

        Args:
            config_dict (dict): 配置字典
        """
        if config_dict:
            self.template_config = json.dumps(config_dict, ensure_ascii=False)
        else:
            self.template_config = None

    def to_dict(self):
        """
        转换为字典格式

        Returns:
            dict: 模型数据的字典表示
        """
        # downloader_type 现在直接是整数类型
        downloader_type_value = self.downloader_type

        # 转换为字符串名称
        downloader_type_name = None
        if downloader_type_value is not None:
            if downloader_type_value == 0:
                downloader_type_name = "qbittorrent"
            elif downloader_type_value == 1:
                downloader_type_name = "transmission"
            else:
                downloader_type_name = str(downloader_type_value)

        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "downloaderType": downloader_type_value,
            "downloaderTypeName": downloader_type_name,
            "template_config": self.get_config_dict(),
            "is_system_default": self.is_system_default,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        # 添加path_mapping字段（如果存在）
        if self.path_mapping:
            try:
                result["path_mapping"] = json.loads(self.path_mapping)
            except json.JSONDecodeError:
                logger.warning(f"path_mapping JSON解析失败，返回原始字符串")
                result["path_mapping"] = self.path_mapping
        else:
            result["path_mapping"] = None

        return result

    def __repr__(self):
        return (
            f"<SettingTemplate(id={self.id}, "
            f"name={self.name}, "
            f"downloader_type={self.downloader_type}, "
            f"is_system_default={self.is_system_default})>"
        )
