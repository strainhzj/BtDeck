# -*- coding: utf-8 -*-
"""
种子标签管理模型

包含TorrentTag（统一标签表）和TorrentTagRelation（种子-标签关联表）两个模型。
支持qBittorrent的分类/标签和Transmission的标签统一管理。

@Time    : 2026-02-11
@Author  : btpManager Team
@File    : torrent_tags.py
"""

from typing import Any, Optional, Dict
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class TorrentTag(Base):
    """
    统一标签表

    存储qBittorrent的分类和标签，以及Transmission的标签。
    通过tag_type字段区分类型：'category'表示qBittorrent的分类，'tag'表示通用标签。

    Attributes:
        tag_id: 标签唯一标识符（UUID）
        downloader_id: 所属下载器ID
        tag_name: 标签名称
        tag_type: 标签类型（'category' | 'tag'）
        color: 标签颜色（HEX格式，如'#FF5733'）
        created_at: 创建时间
        updated_at: 更新时间
        dr: 软删除标记（0=未删除，1=已删除）
    """
    __tablename__ = "torrent_tags"

    # 主键：使用String(36)存储UUID
    tag_id = Column(String(36), primary_key=True, index=True, comment="标签唯一标识符")

    # 外键：关联下载器（使用String类型，与BtDownloaders.downloader_id一致）
    downloader_id = Column(String(36), nullable=False, index=True, comment="所属下载器ID")

    # 标签名称
    tag_name = Column(String(255), nullable=False, comment="标签名称")

    # 标签类型：'category'表示qBittorrent分类，'tag'表示通用标签
    tag_type = Column(String(50), nullable=False, index=True, comment="标签类型：category/tag")

    # 标签颜色：HEX颜色码，如'#FF5733'
    color = Column(String(7), nullable=True, comment="标签颜色（HEX格式）")

    # 审计字段：创建时间
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    # 审计字段：更新时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间")

    # 软删除标记：0=未删除，1=已删除
    dr = Column(Integer, default=0, nullable=False, comment="软删除标记")

    def __init__(
        self,
        tag_id: Optional[str] = None,
        downloader_id: Optional[str] = None,
        tag_name: Optional[str] = None,
        tag_type: Optional[str] = None,
        color: Optional[str] = None,
        dr: int = 0,
        **kw: Any
    ):
        """
        初始化TorrentTag实例

        Args:
            tag_id: 标签ID（如未提供则自动生成UUID）
            downloader_id: 下载器ID
            tag_name: 标签名称
            tag_type: 标签类型（'category' | 'tag'）
            color: 标签颜色（HEX格式）
            dr: 软删除标记
        """
        super().__init__(**kw)

        if tag_id is None:
            self.tag_id = str(uuid.uuid4())
        else:
            self.tag_id = tag_id

        if downloader_id is not None:
            self.downloader_id = downloader_id

        if tag_name is not None:
            self.tag_name = tag_name

        if tag_type is not None:
            self.tag_type = tag_type

        if color is not None:
            self.color = color

        self.dr = dr

    def to_dict(self) -> Dict[str, Any]:
        """
        将模型转换为字典

        Returns:
            包含所有模型字段的字典
        """
        return {
            "tag_id": self.tag_id,
            "downloader_id": self.downloader_id,
            "tag_name": self.tag_name,
            "tag_type": self.tag_type,
            "color": self.color,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "dr": self.dr,
        }


class TorrentTagRelation(Base):
    """
    种子-标签关联表

    实现种子和标签的多对多关联关系。
    使用UNIQUE约束确保同一种子不会被分配相同的标签两次。

    Attributes:
        relation_id: 关联记录唯一标识符（UUID）
        downloader_id: 下载器ID
        torrent_hash: 种子hash值
        tag_id: 标签ID（外键关联torrent_tags.tag_id）
        assigned_at: 分配时间
        dr: 软删除标记
    """
    __tablename__ = "torrent_tag_relations"

    # 主键：使用String(36)存储UUID
    relation_id = Column(String(36), primary_key=True, index=True, comment="关联记录唯一标识符")

    # 下载器ID：用于快速查询某下载器的所有关联
    downloader_id = Column(String(36), nullable=False, index=True, comment="下载器ID")

    # 种子hash值：用于快速查询某种子的所有标签
    torrent_hash = Column(String(64), nullable=False, index=True, comment="种子hash值")

    # 外键：关联标签表
    tag_id = Column(
        String(36),
        ForeignKey("torrent_tags.tag_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="标签ID"
    )

    # 分配时间
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="分配时间")

    # 软删除标记：0=未删除，1=已删除
    dr = Column(Integer, default=0, nullable=False, comment="软删除标记")

    # UNIQUE约束：防止重复关联（同一种子不能有相同的标签）
    __table_args__ = (
        UniqueConstraint("torrent_hash", "tag_id", name="uk_torrent_tag"),
    )

    def __init__(
        self,
        relation_id: Optional[str] = None,
        downloader_id: Optional[str] = None,
        torrent_hash: Optional[str] = None,
        tag_id: Optional[str] = None,
        dr: int = 0,
        **kw: Any
    ):
        """
        初始化TorrentTagRelation实例

        Args:
            relation_id: 关联ID（如未提供则自动生成UUID）
            downloader_id: 下载器ID
            torrent_hash: 种子hash值
            tag_id: 标签ID
            dr: 软删除标记
        """
        super().__init__(**kw)

        if relation_id is None:
            self.relation_id = str(uuid.uuid4())
        else:
            self.relation_id = relation_id

        if downloader_id is not None:
            self.downloader_id = downloader_id

        if torrent_hash is not None:
            self.torrent_hash = torrent_hash

        if tag_id is not None:
            self.tag_id = tag_id

        self.dr = dr

    def to_dict(self) -> Dict[str, Any]:
        """
        将模型转换为字典

        Returns:
            包含所有模型字段的字典
        """
        return {
            "relation_id": self.relation_id,
            "downloader_id": self.downloader_id,
            "torrent_hash": self.torrent_hash,
            "tag_id": self.tag_id,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "dr": self.dr,
        }
