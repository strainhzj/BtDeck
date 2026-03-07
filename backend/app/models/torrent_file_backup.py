# -*- coding: utf-8 -*-
"""
种子文件备份模型

记录种子文件的本地存储信息，支持种子转移功能。
种子文件按照 {downloader_id}/{year}/{month}/{hash}_{name}.torrent 规则存储。

@author: btpManager Team
@file: torrent_file_backup.py
@time: 2026-02-15
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import Column, String, BigInteger, Integer, Boolean, DateTime, Index, ForeignKey
from sqlalchemy.orm import declarative_base
from app.database import Base


class TorrentFileBackup(Base):
    """
    种子文件备份表

    记录种子文件的本地存储信息，包括文件路径、大小、关联任务等。
    支持种子转移功能时获取种子文件。

    Attributes:
        id: 主键（自增）
        info_hash: 种子的 info_hash（40位十六进制字符串）
        file_path: 种子文件存储路径（相对于后端目录）
        file_size: 文件大小（字节）
        task_name: 关联的任务名称
        uploader_id: 上传用户ID
        downloader_id: 关联的下载器ID
        upload_time: 上传时间
        last_used_time: 最后使用时间（用于转移等操作）
        use_count: 使用次数
        is_deleted: 逻辑删除标记（0=未删除，1=已删除）
        created_at: 创建时间
        updated_at: 更新时间
    """
    __tablename__ = 'torrent_file_backup'

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')

    # 种子标识
    info_hash = Column(String(40), nullable=False, unique=True, index=True, comment='种子的 info_hash（40位十六进制）')

    # 文件信息
    file_path = Column(String(500), nullable=False, comment='种子文件存储路径')
    file_size = Column(BigInteger, nullable=True, comment='文件大小（字节）')

    # 任务关联
    task_name = Column(String(500), nullable=True, comment='关联的任务名称')
    uploader_id = Column(Integer, nullable=True, comment='上传用户ID')
    downloader_id = Column(Integer, ForeignKey('bt_downloaders.downloader_id', ondelete='CASCADE'), nullable=True, index=True, comment='关联的下载器ID')

    # 时间信息
    upload_time = Column(DateTime, nullable=True, comment='上传时间')
    last_used_time = Column(DateTime, nullable=True, comment='最后使用时间')

    # 统计信息
    use_count = Column(Integer, default=0, nullable=False, comment='使用次数')

    # 逻辑删除
    is_deleted = Column(Boolean, default=False, nullable=False, index=True, comment='逻辑删除标记')

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment='更新时间')

    def __init__(
        self,
        info_hash: str,
        file_path: str,
        file_size: Optional[int] = None,
        task_name: Optional[str] = None,
        uploader_id: Optional[int] = None,
        downloader_id: Optional[int] = None,
        upload_time: Optional[datetime] = None,
        last_used_time: Optional[datetime] = None,
        use_count: int = 0,
        is_deleted: bool = False,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """
        初始化 TorrentFileBackup 实例

        Args:
            info_hash: 种子的 info_hash（40位十六进制）
            file_path: 种子文件存储路径
            file_size: 文件大小（字节）
            task_name: 关联的任务名称
            uploader_id: 上传用户ID
            downloader_id: 关联的下载器ID
            upload_time: 上传时间
            last_used_time: 最后使用时间
            use_count: 使用次数
            is_deleted: 逻辑删除标记
            created_at: 创建时间
            updated_at: 更新时间
        """
        self.info_hash = info_hash
        self.file_path = file_path
        self.file_size = file_size
        self.task_name = task_name
        self.uploader_id = uploader_id
        self.downloader_id = downloader_id
        self.upload_time = upload_time
        self.last_used_time = last_used_time
        self.use_count = use_count
        self.is_deleted = is_deleted

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
            'info_hash': self.info_hash,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'task_name': self.task_name,
            'uploader_id': self.uploader_id,
            'downloader_id': self.downloader_id,
            'upload_time': self.upload_time.isoformat() if self.upload_time else None,
            'last_used_time': self.last_used_time.isoformat() if self.last_used_time else None,
            'use_count': self.use_count,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def is_available(self) -> bool:
        """
        判断种子文件是否可用

        Returns:
            True 如果文件未被删除
        """
        return not self.is_deleted

    def increment_use_count(self) -> None:
        """增加使用次数并更新最后使用时间"""
        self.use_count += 1
        self.last_used_time = datetime.utcnow()

    def soft_delete(self) -> None:
        """逻辑删除种子文件备份"""
        self.is_deleted = True
        self.updated_at = datetime.utcnow()
