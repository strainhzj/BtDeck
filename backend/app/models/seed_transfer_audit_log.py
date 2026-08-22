# -*- coding: utf-8 -*-
"""
种子转移审计日志模型

记录种子转移操作的详细信息，用于审计追溯和问题排查。
包括源下载器、目标下载器、路径信息、操作结果等。

@author: btpManager Team
@file: seed_transfer_audit_log.py
@time: 2026-02-15
"""

from typing import Optional, cast
from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

# 操作类型常量
OPERATOR_TYPE_SEED_TRANSFER = "seed_transfer"

# 转移状态常量
TRANSFER_STATUS_SUCCESS = "success"
TRANSFER_STATUS_FAILED = "failed"


class SeedTransferAuditLog(Base):
    """
    种子转移审计日志表

    记录种子转移操作的详细信息，用于审计追溯。
    包含源下载器、目标下载器、路径信息、操作结果等。

    Attributes:
        id: 主键（自增）
        operation_type: 操作类型（seed_transfer）
        operation_time: 操作时间
        user_id: 操作用户ID
        username: 操作用户名
        source_downloader_id: 源下载器ID
        source_downloader_name: 源下载器昵称
        target_downloader_id: 目标下载器ID
        target_downloader_name: 目标下载器昵称
        torrent_name: 种子名称
        info_hash: 种子的 info_hash
        source_path: 源路径
        target_path: 目标路径
        delete_source: 是否删除原种子
        transfer_status: 转移状态（success/failed）
        error_message: 错误信息（如果失败）
        transfer_duration: 转移耗时（毫秒）
        created_at: 创建时间
    """

    __tablename__ = "seed_transfer_audit_log"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")

    # 操作信息
    operation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=OPERATOR_TYPE_SEED_TRANSFER, comment="操作类型：seed_transfer"
    )
    operation_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True, comment="操作时间")

    # 操作者信息
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True, comment="操作用户ID")
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="操作用户名")

    # 源下载器信息
    source_downloader_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="源下载器ID")
    source_downloader_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="源下载器昵称")

    # 目标下载器信息
    target_downloader_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="目标下载器ID")
    target_downloader_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="目标下载器昵称")

    # 种子信息
    torrent_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="种子名称")
    info_hash: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True, comment="种子的 info_hash")

    # 路径信息
    source_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="源路径")
    target_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="目标路径")

    # 操作配置
    delete_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否删除原种子")

    # 转移结果
    transfer_status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="转移状态：success/failed"
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息（如果失败）")

    # 性能统计
    transfer_duration: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="转移耗时（毫秒）")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    def __init__(
        self,
        operation_type: str = OPERATOR_TYPE_SEED_TRANSFER,
        operation_time: Optional[datetime] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        source_downloader_id: Optional[int] = None,
        source_downloader_name: Optional[str] = None,
        target_downloader_id: Optional[int] = None,
        target_downloader_name: Optional[str] = None,
        torrent_name: Optional[str] = None,
        info_hash: Optional[str] = None,
        source_path: Optional[str] = None,
        target_path: Optional[str] = None,
        delete_source: bool = False,
        transfer_status: Optional[str] = None,
        error_message: Optional[str] = None,
        transfer_duration: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ):
        """
        初始化 SeedTransferAuditLog 实例

        Args:
            operation_type: 操作类型（seed_transfer）
            operation_time: 操作时间
            user_id: 操作用户ID
            username: 操作用户名
            source_downloader_id: 源下载器ID
            source_downloader_name: 源下载器昵称
            target_downloader_id: 目标下载器ID
            target_downloader_name: 目标下载器昵称
            torrent_name: 种子名称
            info_hash: 种子的 info_hash
            source_path: 源路径
            target_path: 目标路径
            delete_source: 是否删除原种子
            transfer_status: 转移状态
            error_message: 错误信息
            transfer_duration: 转移耗时（毫秒）
            created_at: 创建时间
        """
        self.operation_type = operation_type
        # 列为 NOT NULL；None 由调用方保证不出现（cast 仅类型层，不改运行时行为）
        self.operation_time = cast(datetime, operation_time)
        self.user_id = user_id
        self.username = username
        self.source_downloader_id = source_downloader_id
        self.source_downloader_name = source_downloader_name
        self.target_downloader_id = target_downloader_id
        self.target_downloader_name = target_downloader_name
        self.torrent_name = torrent_name
        self.info_hash = info_hash
        self.source_path = source_path
        self.target_path = target_path
        self.delete_source = delete_source
        self.transfer_status = cast(str, transfer_status)
        self.error_message = error_message
        self.transfer_duration = transfer_duration

        if created_at is not None:
            self.created_at = created_at

    def to_dict(self) -> dict:
        """
        将模型转换为字典

        Returns:
            包含所有模型字段的字典
        """
        return {
            "id": self.id,
            "operation_type": self.operation_type,
            "operation_time": self.operation_time.isoformat() if self.operation_time else None,
            "user_id": self.user_id,
            "username": self.username,
            "source_downloader_id": self.source_downloader_id,
            "source_downloader_name": self.source_downloader_name,
            "target_downloader_id": self.target_downloader_id,
            "target_downloader_name": self.target_downloader_name,
            "torrent_name": self.torrent_name,
            "info_hash": self.info_hash,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "delete_source": self.delete_source,
            "transfer_status": self.transfer_status,
            "error_message": self.error_message,
            "transfer_duration": self.transfer_duration,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def is_successful(self) -> bool:
        """
        判断转移是否成功

        Returns:
            True 如果转移状态为 success
        """
        return self.transfer_status == TRANSFER_STATUS_SUCCESS

    def is_failed(self) -> bool:
        """
        判断转移是否失败

        Returns:
            True 如果转移状态为 failed
        """
        return self.transfer_status == TRANSFER_STATUS_FAILED

    def mark_success(self, duration_ms: Optional[int] = None) -> None:
        """
        标记转移成功

        Args:
            duration_ms: 转移耗时（毫秒）
        """
        self.transfer_status = TRANSFER_STATUS_SUCCESS
        self.error_message = None
        if duration_ms is not None:
            self.transfer_duration = duration_ms

    def mark_failed(self, error_message: str, duration_ms: Optional[int] = None) -> None:
        """
        标记转移失败

        Args:
            error_message: 错误信息
            duration_ms: 转移耗时（毫秒）
        """
        self.transfer_status = TRANSFER_STATUS_FAILED
        self.error_message = error_message
        if duration_ms is not None:
            self.transfer_duration = duration_ms
