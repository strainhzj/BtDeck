# -*- coding: utf-8 -*-
"""
孤儿文件管理模型

管理孤儿文件扫描批次结果与孤儿文件明细。
孤儿文件 = 扫描路径下存在、但不在任何种子文件清单中的磁盘文件。

@file: orphan_file.py
@time: 2026-07-10
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Text, ForeignKey

from app.database import Base


class OrphanScanResult(Base):
    """孤儿文件扫描批次结果

    每次扫描（手动/定时）产生一条记录，记录扫描概况。
    明细写入 OrphanFile 表。

    Attributes:
        scan_id: 扫描批次 ID（UUID 字符串，主键）
        scan_time: 扫描开始时间
        scan_type: 扫描类型（manual=手动触发，scheduled=定时触发）
        total_paths_scanned: 扫描的路径数量
        total_files_scanned: 扫描的文件总数
        total_orphans: 发现的孤儿文件数量
        total_orphan_size: 孤儿文件总大小（字节）
        status: 扫描状态（running/completed/failed）
        error_message: 失败时的错误信息
        operator: 触发者（用户名或 system）
        created_at / updated_at: 时间戳
    """

    __tablename__ = "orphan_scan_result"

    scan_id = Column(String(36), primary_key=True, comment="扫描批次ID（UUID）")
    scan_time = Column(DateTime, nullable=False, index=True, comment="扫描开始时间")
    scan_type = Column(String(20), nullable=False, comment="扫描类型：manual=手动，scheduled=定时")
    total_paths_scanned = Column(Integer, default=0, nullable=False, comment="扫描的路径数量")
    total_files_scanned = Column(Integer, default=0, nullable=False, comment="扫描的文件总数")
    total_orphans = Column(Integer, default=0, nullable=False, comment="发现的孤儿文件数量")
    total_orphan_size = Column(BigInteger, default=0, nullable=False, comment="孤儿文件总大小（字节）")
    status = Column(String(20), nullable=False, default="running", comment="扫描状态：running/completed/failed")
    error_message = Column(Text, nullable=True, comment="失败时的错误信息")
    operator = Column(String(100), nullable=True, comment="触发者（用户名或system）")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间")

    def __init__(
        self,
        scan_id: str,
        scan_time: Optional[datetime] = None,
        scan_type: str = "manual",
        operator: Optional[str] = None,
        status: str = "running",
    ):
        self.scan_id = scan_id
        self.scan_time = scan_time or datetime.utcnow()
        self.scan_type = scan_type
        self.operator = operator
        self.status = status

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "scan_id": self.scan_id,
            "scan_time": self.scan_time.isoformat() if self.scan_time else None,
            "scan_type": self.scan_type,
            "total_paths_scanned": self.total_paths_scanned,
            "total_files_scanned": self.total_files_scanned,
            "total_orphans": self.total_orphans,
            "total_orphan_size": self.total_orphan_size,
            "status": self.status,
            "error_message": self.error_message,
            "operator": self.operator,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OrphanFile(Base):
    """孤儿文件明细

    每个被判定为孤儿的磁盘文件产生一条记录。

    Attributes:
        id: 主键（自增）
        scan_id: 所属扫描批次（FK → orphan_scan_result.scan_id）
        file_path: 文件绝对路径（外部路径，已路径映射转换）
        file_size: 文件大小（字节）
        mtime: 文件修改时间
        downloader_id: 关联的下载器 ID（路径所属下载器，可为空）
        is_deleted: 是否已清理
        deleted_at: 清理时间
        deleted_by: 清理操作者
        created_at: 记录创建时间
    """

    __tablename__ = "orphan_file"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    scan_id = Column(
        String(36), ForeignKey("orphan_scan_result.scan_id"), nullable=False, index=True, comment="所属扫描批次ID"
    )
    file_path = Column(String(500), nullable=False, comment="文件绝对路径（外部路径）")
    file_size = Column(BigInteger, default=0, nullable=False, comment="文件大小（字节）")
    mtime = Column(DateTime, nullable=True, comment="文件修改时间")
    downloader_id = Column(String(36), nullable=True, index=True, comment="关联下载器ID")

    is_deleted = Column(Boolean, default=False, nullable=False, comment="是否已清理")
    deleted_at = Column(DateTime, nullable=True, comment="清理时间")
    deleted_by = Column(String(100), nullable=True, comment="清理操作者")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    def __init__(
        self,
        scan_id: str,
        file_path: str,
        file_size: int = 0,
        mtime: Optional[datetime] = None,
        downloader_id: Optional[str] = None,
    ):
        self.scan_id = scan_id
        self.file_path = file_path
        self.file_size = file_size
        self.mtime = mtime
        self.downloader_id = downloader_id

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "mtime": self.mtime.isoformat() if self.mtime else None,
            "downloader_id": self.downloader_id,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "deleted_by": self.deleted_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
