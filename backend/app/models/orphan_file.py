# -*- coding: utf-8 -*-
"""
孤儿文件管理模型

管理孤儿文件扫描批次结果与孤儿文件明细。
孤儿文件 = 扫描路径下存在、但不在任何种子文件清单中的磁盘文件。

@file: orphan_file.py
@time: 2026-07-10
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Text, ForeignKey, UniqueConstraint

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


class OrphanCurrentCandidate(Base):
    """孤儿文件当前候选（语义重做 v1.0.6+）

    独立的当前候选表，取代把历史 OrphanFile 明细当作当前状态的做法。
    按「连续成为孤儿的时间」管理生命周期，自动清理依据此表的持续时间而非文件 mtime。

    只有完整成功扫描才能推进状态（reconcile_candidates）。
    未出现在新清单中的旧候选标记 resolved。failed 扫描不修改候选生命周期。

    Attributes:
        canonical_path: 规范化路径（normcase+normpath，主键）
        downloader_id: 关联下载器 ID
        first_seen_at: 首次发现为孤儿的时间
        last_seen_at: 最后一次在完整成功扫描中确认为孤儿的时间
        last_seen_scan_id: 最后一次确认的扫描批次 ID
        consecutive_scan_count: 连续确认为孤儿的完整成功扫描次数
        status: candidate/resolved/quarantined/purged
        file_size: 文件大小（字节）
        mtime_ns: 文件修改时间（纳秒）
        device_id: 设备 ID（st_dev）
        inode: inode（st_ino）
        quarantine_path: 隔离区路径
        quarantined_at: 移入隔离区时间
        purge_after: 允许物理删除时间（quarantined_at + 保留期）
    """

    __tablename__ = "orphan_current_candidate"
    __table_args__ = (UniqueConstraint("downloader_id", "canonical_path", name="uq_orphan_candidate_dl_path"),)

    canonical_path = Column(String(600), primary_key=True, comment="规范化路径（normcase+normpath）")
    downloader_id = Column(String(36), nullable=False, comment="关联下载器ID")
    first_seen_at = Column(DateTime, nullable=False, comment="首次发现时间")
    last_seen_at = Column(DateTime, nullable=False, comment="最后一次确认时间")
    last_seen_scan_id = Column(String(36), nullable=True, comment="最后一次确认的扫描批次ID")
    consecutive_scan_count = Column(Integer, default=1, nullable=False, comment="连续确认扫描次数")
    status = Column(String(20), nullable=False, default="candidate", comment="candidate/resolved/quarantined/purged")
    file_size = Column(BigInteger, default=0, nullable=False, comment="文件大小（字节）")
    mtime_ns = Column(BigInteger, nullable=True, comment="文件修改时间（纳秒）")
    device_id = Column(BigInteger, nullable=True, comment="设备ID（st_dev）")
    inode = Column(BigInteger, nullable=True, comment="inode（st_ino）")
    quarantine_path = Column(String(600), nullable=True, comment="隔离区路径")
    quarantined_at = Column(DateTime, nullable=True, comment="移入隔离区时间")
    purge_after = Column(DateTime, nullable=True, index=True, comment="允许物理删除时间")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间")

    def __init__(
        self,
        canonical_path: str,
        downloader_id: str,
        first_seen_at: Optional[datetime] = None,
        last_seen_at: Optional[datetime] = None,
        last_seen_scan_id: Optional[str] = None,
        consecutive_scan_count: int = 1,
        status: str = "candidate",
        file_size: int = 0,
        mtime_ns: Optional[int] = None,
        device_id: Optional[int] = None,
        inode: Optional[int] = None,
        quarantine_path: Optional[str] = None,
        quarantined_at: Optional[datetime] = None,
        purge_after: Optional[datetime] = None,
    ):
        now = datetime.utcnow()
        self.canonical_path = canonical_path
        self.downloader_id = downloader_id
        self.first_seen_at = first_seen_at or now
        self.last_seen_at = last_seen_at or now
        self.last_seen_scan_id = last_seen_scan_id
        self.consecutive_scan_count = consecutive_scan_count
        self.status = status
        self.file_size = file_size
        self.mtime_ns = mtime_ns
        self.device_id = device_id
        self.inode = inode
        self.quarantine_path = quarantine_path
        self.quarantined_at = quarantined_at
        self.purge_after = purge_after

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "canonical_path": self.canonical_path,
            "downloader_id": self.downloader_id,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "last_seen_scan_id": self.last_seen_scan_id,
            "consecutive_scan_count": self.consecutive_scan_count,
            "status": self.status,
            "file_size": self.file_size,
            "mtime_ns": self.mtime_ns,
            "device_id": self.device_id,
            "inode": self.inode,
            "quarantine_path": self.quarantine_path,
            "quarantined_at": self.quarantined_at.isoformat() if self.quarantined_at else None,
            "purge_after": self.purge_after.isoformat() if self.purge_after else None,
        }


class OrphanOperationLease(Base):
    """孤儿文件操作跨进程 lease（v1.0.6+）

    保护扫描/预览/清理互斥。lease 表由迁移 b075727f7182 创建。

    Attributes:
        lease_key: PK（如 orphan_scan / orphan_cleanup）
        owner: 持有者标识（进程ID+UUID）
        acquired_at: 获取时间
        expires_at: 过期时间
    """

    __tablename__ = "orphan_operation_lease"

    lease_key = Column(String(60), primary_key=True, comment="租约键")
    owner = Column(String(100), nullable=False, comment="持有者标识")
    acquired_at = Column(DateTime, nullable=False, comment="获取时间")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")

    def __init__(
        self,
        lease_key: str,
        owner: str,
        acquired_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ):
        self.lease_key = lease_key
        self.owner = owner
        self.acquired_at = acquired_at or datetime.utcnow()
        self.expires_at = expires_at or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_key": self.lease_key,
            "owner": self.owner,
            "acquired_at": self.acquired_at.isoformat() if self.acquired_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
