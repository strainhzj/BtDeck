# -*- coding: utf-8 -*-
"""
下载器设置模型

用于存储每个下载器的速度限制、认证信息和高级配置
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from app.database import Base
import enum
import logging

logger = logging.getLogger(__name__)


class SpeedUnitEnum(enum.IntEnum):
    """速度单位枚举"""
    KB_PER_SEC = 0  # KB/s
    MB_PER_SEC = 1  # MB/s


class DownloaderSetting(Base):
    """
    下载器配置表

    存储每个下载器的速度、认证、高级参数配置
    """
    __tablename__ = "downloader_settings"

    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 外键：关联到 bt_downloaders 表
    downloader_id = Column(
        String,
        ForeignKey('bt_downloaders.downloader_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='下载器ID，关联bt_downloaders表'
    )

    # 速度限制配置
    dl_speed_limit = Column(
        Integer,
        nullable=False,
        default=0,
        comment='全局下载速度限制，数值含义取决于 dl_speed_unit，0表示不限速'
    )

    ul_speed_limit = Column(
        Integer,
        nullable=False,
        default=0,
        comment='全局上传速度限制，数值含义取决于 ul_speed_unit，0表示不限速'
    )

    dl_speed_unit = Column(
        SQLEnum(SpeedUnitEnum),
        nullable=False,
        default=SpeedUnitEnum.KB_PER_SEC,
        comment='下载速度单位：0=KB/s, 1=MB/s'
    )

    ul_speed_unit = Column(
        SQLEnum(SpeedUnitEnum),
        nullable=False,
        default=SpeedUnitEnum.KB_PER_SEC,
        comment='上传速度单位：0=KB/s, 1=MB/s'
    )

    # 分时段速度配置
    enable_schedule = Column(
        Boolean,
        nullable=False,
        default=False,
        comment='是否启用分时段限速'
    )

    # 认证信息（可选，用于覆盖下载器的默认认证）
    username = Column(
        String(100),
        nullable=True,
        comment='下载器用户名（可选，用于覆盖默认配置）'
    )

    password = Column(
        String(255),
        nullable=True,
        comment='下载器密码（SM4加密，可选，用于覆盖默认配置）'
    )

    # 高级配置（JSON格式，存储下载器特有选项）
    advanced_settings = Column(
        Text,
        nullable=True,
        comment='高级配置（JSON格式），存储下载器特有选项'
    )

    # 配置选项
    override_local = Column(
        Boolean,
        nullable=False,
        default=False,
        comment='是否覆盖下载器本地配置'
    )

    # 时间戳
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        comment='创建时间'
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
        comment='更新时间'
    )

    # 关系定义
    # 关联到下载器（多对一）
    # downloader = relationship("BtDownloaders", back_populates="settings")

    # 关联到分时段速度规则（一对多）
    speed_schedule_rules = relationship(
        "SpeedScheduleRule",
        back_populates="downloader_setting",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    def __init__(
        self,
        downloader_id=None,
        dl_speed_limit=0,
        ul_speed_limit=0,
        dl_speed_unit=SpeedUnitEnum.KB_PER_SEC,
        ul_speed_unit=SpeedUnitEnum.KB_PER_SEC,
        enable_schedule=False,
        username=None,
        password=None,
        advanced_settings=None,
        override_local=False,
        **kwargs
    ):
        super().__init__(**kwargs)
        if downloader_id is not None:
            self.downloader_id = downloader_id
        if dl_speed_limit is not None:
            self.dl_speed_limit = dl_speed_limit
        if ul_speed_limit is not None:
            self.ul_speed_limit = ul_speed_limit
        if dl_speed_unit is not None:
            self.dl_speed_unit = dl_speed_unit
        if ul_speed_unit is not None:
            self.ul_speed_unit = ul_speed_unit
        if enable_schedule is not None:
            self.enable_schedule = enable_schedule
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password
        if advanced_settings is not None:
            self.advanced_settings = advanced_settings
        if override_local is not None:
            self.override_local = override_local

    def to_dict(self):
        """
        转换为字典格式

        Returns:
            dict: 模型数据的字典表示
        """
        return {
            "id": self.id,
            "downloader_id": self.downloader_id,
            "dl_speed_limit": self.dl_speed_limit,
            "ul_speed_limit": self.ul_speed_limit,
            "dl_speed_unit": self.dl_speed_unit.value if self.dl_speed_unit else None,
            "ul_speed_unit": self.ul_speed_unit.value if self.ul_speed_unit else None,
            "enable_schedule": self.enable_schedule,
            "username": self.username,
            "password": self.password,  # 注意：这是加密后的密码
            "advanced_settings": self.advanced_settings,
            "override_local": self.override_local,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return (
            f"<DownloaderSetting(id={self.id}, "
            f"downloader_id={self.downloader_id}, "
            f"dl_speed_limit={self.dl_speed_limit}, "
            f"ul_speed_limit={self.ul_speed_limit})>"
        )
