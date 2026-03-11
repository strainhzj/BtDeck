# -*- coding: utf-8 -*-
"""
下载器路径维护模型

管理每个下载器的路径信息，包括默认路径和在用路径列表。
支持种子转移时的路径选择。

@author: btpManager Team
@file: downloader_path_maintenance.py
@time: 2026-02-15
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base
from app.database import Base


class DownloaderPathMaintenance(Base):
    """
    下载器路径维护表

    管理每个下载器的路径信息，包括默认路径和在用路径列表。
    用于种子转移时选择目标路径。

    Attributes:
        id: 主键（自增）
        downloader_id: 下载器ID
        path_type: 路径类型（default=默认路径，active=在用路径）
        path_value: 路径值（绝对路径）
        is_enabled: 是否启用
        torrent_count: 使用该路径的种子数量
        last_updated_time: 最后更新时间
        created_at: 创建时间
        updated_at: 更新时间
    """
    __tablename__ = 'downloader_path_maintenance'

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')

    # 下载器关联（使用字符串类型以匹配 bt_downloaders 的 UUID）
    downloader_id = Column(
        String(36),
        nullable=False,
        index=True,
        comment='下载器ID（UUID字符串）'
    )

    # 路径类型和值
    path_type = Column(String(20), nullable=False, index=True, comment='路径类型：default=默认路径，active=在用路径')
    path_value = Column(String(500), nullable=False, comment='路径值（绝对路径）')

    # 状态
    is_enabled = Column(Boolean, default=True, nullable=False, comment='是否启用')

    # 统计信息
    torrent_count = Column(Integer, default=0, nullable=False, comment='使用该路径的种子数量')
    last_updated_time = Column(DateTime, nullable=True, comment='最后更新时间')

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment='更新时间')

    # 唯一约束：同一下载器的 path_type + path_value 组合必须唯一
    __table_args__ = (
        UniqueConstraint('downloader_id', 'path_type', 'path_value', name='uq_downloader_path_type_value'),
    )

    def __init__(
        self,
        downloader_id: str,
        path_type: str,
        path_value: str,
        is_enabled: bool = True,
        torrent_count: int = 0,
        last_updated_time: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """
        初始化 DownloaderPathMaintenance 实例

        Args:
            downloader_id: 下载器ID
            path_type: 路径类型（default/active）
            path_value: 路径值（绝对路径）
            is_enabled: 是否启用
            torrent_count: 使用该路径的种子数量
            last_updated_time: 最后更新时间
            created_at: 创建时间
            updated_at: 更新时间
        """
        self.downloader_id = downloader_id
        self.path_type = path_type
        self.path_value = path_value
        self.is_enabled = is_enabled
        self.torrent_count = torrent_count
        self.last_updated_time = last_updated_time

        if created_at is not None:
            self.created_at = created_at

        if updated_at is not None:
            self.updated_at = updated_at

    def to_dict(self) -> dict:
        """
        将模型转换为字典

        Returns:
            包含所有模型字段的字典
        """
        return {
            'id': self.id,
            'downloader_id': self.downloader_id,
            'path_type': self.path_type,
            'path_value': self.path_value,
            'is_enabled': self.is_enabled,
            'torrent_count': self.torrent_count,
            'last_updated_time': self.last_updated_time.isoformat() if self.last_updated_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def is_enabled_path(self) -> bool:
        """
        判断路径是否启用

        Returns:
            True 如果路径启用
        """
        return self.is_enabled

    def is_default_path(self) -> bool:
        """
        判断是否为默认路径

        Returns:
            True 如果是默认路径
        """
        return self.path_type == 'default'

    def is_active_path(self) -> bool:
        """
        判断是否为在用路径

        Returns:
            True 如果是在用路径
        """
        return self.path_type == 'active'

    def update_torrent_count(self, count: int) -> None:
        """
        更新种子数量和最后更新时间

        Args:
            count: 新的种子数量
        """
        self.torrent_count = count
        self.last_updated_time = datetime.utcnow()

    def disable(self) -> None:
        """禁用路径"""
        self.is_enabled = False
        self.updated_at = datetime.utcnow()

    def enable(self) -> None:
        """启用路径"""
        self.is_enabled = True
        self.updated_at = datetime.utcnow()
