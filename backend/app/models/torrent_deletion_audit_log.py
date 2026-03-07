# -*- coding: utf-8 -*-
"""
种子删除审计日志模型

记录每次种子删除操作的详细信息，包括种子信息、操作者信息、
删除原因、验证结果等。支持多类型操作者（管理员、系统定时任务、回收站清理）。

@author: btpManager Team
@file: torrent_deletion_audit_log.py
@time: 2026-02-14
"""

from typing import Any, Dict, Optional
from datetime import datetime
from sqlalchemy import Column, String, BigInteger, Boolean, Integer, Text, DateTime
from sqlalchemy.orm import declarative_base
from app.database import Base
import json
import uuid

# 操作者ID常量
OPERATOR_SYSTEM_SCHEDULER = 0  # 系统定时任务
OPERATOR_RECYCLE_BIN_CLEANER = -1  # 回收站清理任务

# 删除状态常量
DELETION_STATUS_SUCCESS = 'success'
DELETION_STATUS_FAILED = 'failed'
DELETION_STATUS_PARTIAL = 'partial'

# 调用来源常量
CALLER_SOURCE_API = 'API删除'
CALLER_SOURCE_SYSTEM_SCHEDULER = 'SYSTEM_SCHEDULER'
CALLER_SOURCE_RECYCLE_BIN_CLEANER = 'RECYCLE_BIN_CLEANER'

# 下载器类型常量（与其他模型一致）
DOWNLOADER_TYPE_QBITTORRENT = 0
DOWNLOADER_TYPE_TRANSMISSION = 1


class TorrentDeletionAuditLog(Base):
    """
    种子删除审计日志表

    记录每次种子删除操作的详细信息，用于审计追溯和问题排查。
    包含种子信息、操作者信息、删除原因、验证结果（JSON字段）等。

    Attributes:
        id: 主键（自增）
        task_id: 任务批次ID（用于关联同一批次的多条删除记录）
        downloader_id: 下载器ID
        downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）
        torrent_hash: 种子Hash（64字符）
        torrent_name: 种子名称
        torrent_size: 种子大小（字节）
        delete_files: 是否删除文件
        safety_check_level: 安全检查级别（basic/enhanced/strict）
        validation_result: 验证结果JSON（含seed_status、trackers等）
        operator_id: 操作者ID（0=系统定时任务, -1=回收站清理, >0=真实用户ID）
        operator_name: 操作者用户名
        operator_ip: 操作者IP地址
        operator_user_agent: 操作者浏览器/客户端信息
        caller_source: 调用来源（API/SYSTEM_SCHEDULER/RECYCLE_BIN_CLEANER）
        caller_function: 具体调用的函数
        caller_module: 调用模块
        deletion_status: 删除状态（success/failed/partial）
        error_message: 错误信息
        created_at: 创建时间
        deleted_at: 实际删除完成时间（仅成功时设置）
    """
    __tablename__ = 'torrent_deletion_audit_log'

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')

    # 任务批次ID
    task_id = Column(String(64), nullable=False, index=True, comment='任务批次ID')

    # 下载器信息
    downloader_id = Column(Integer, nullable=False, index=True, comment='下载器ID')
    downloader_type = Column(Integer, nullable=False, comment='下载器类型：0=qBittorrent, 1=Transmission')

    # 种子信息
    torrent_hash = Column(String(64), nullable=False, index=True, comment='种子Hash')
    torrent_name = Column(String(255), nullable=True, comment='种子名称')
    torrent_size = Column(BigInteger, nullable=True, comment='种子大小（字节）')

    # 删除配置
    delete_files = Column(Boolean, nullable=False, default=False, comment='是否删除文件')
    safety_check_level = Column(String(20), nullable=True, comment='安全检查级别：basic/enhanced/strict')

    # 验证结果（JSON字段）
    validation_result = Column(Text, nullable=True, comment='验证结果JSON（含seed_status、trackers等）')

    # 操作者信息
    operator_id = Column(Integer, nullable=True, index=True, comment='操作者ID：0=系统定时任务, -1=回收站清理, >0=真实用户ID')
    operator_name = Column(String(100), nullable=True, comment='操作者用户名')
    operator_ip = Column(String(50), nullable=True, comment='操作者IP地址')
    operator_user_agent = Column(String(255), nullable=True, comment='操作者浏览器/客户端信息')

    # 调用来源
    caller_source = Column(String(100), nullable=False, comment='调用来源：API/SYSTEM_SCHEDULER/RECYCLE_BIN_CLEANER')
    caller_function = Column(String(255), nullable=True, comment='具体调用的函数')
    caller_module = Column(String(255), nullable=True, comment='调用模块')

    # 删除状态
    deletion_status = Column(String(20), nullable=False, comment='删除状态：success/failed/partial')
    error_message = Column(Text, nullable=True, comment='错误信息')

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment='创建时间')
    deleted_at = Column(DateTime, nullable=True, comment='实际删除完成时间（仅成功时设置）')

    def __init__(
        self,
        task_id: Optional[str] = None,
        downloader_id: Optional[int] = None,
        downloader_type: Optional[int] = None,
        torrent_hash: Optional[str] = None,
        torrent_name: Optional[str] = None,
        torrent_size: Optional[int] = None,
        delete_files: bool = False,
        safety_check_level: Optional[str] = None,
        validation_result: Optional[Dict[str, Any]] = None,
        operator_id: Optional[int] = None,
        operator_name: Optional[str] = None,
        operator_ip: Optional[str] = None,
        operator_user_agent: Optional[str] = None,
        caller_source: Optional[str] = None,
        caller_function: Optional[str] = None,
        caller_module: Optional[str] = None,
        deletion_status: Optional[str] = None,
        error_message: Optional[str] = None,
        created_at: Optional[datetime] = None,
        deleted_at: Optional[datetime] = None,
        **kw: Any
    ):
        """
        初始化TorrentDeletionAuditLog实例

        Args:
            task_id: 任务批次ID
            downloader_id: 下载器ID
            downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）
            torrent_hash: 种子Hash
            torrent_name: 种子名称
            torrent_size: 种子大小（字节）
            delete_files: 是否删除文件
            safety_check_level: 安全检查级别
            validation_result: 验证结果字典（将序列化为JSON存储）
            operator_id: 操作者ID（0=系统定时任务, -1=回收站清理, >0=真实用户ID）
            operator_name: 操作者用户名
            operator_ip: 操作者IP地址
            operator_user_agent: 操作者浏览器/客户端信息
            caller_source: 调用来源
            caller_function: 具体调用的函数
            caller_module: 调用模块
            deletion_status: 删除状态
            error_message: 错误信息
            created_at: 创建时间
            deleted_at: 实际删除完成时间
        """
        super().__init__(**kw)

        if task_id is not None:
            self.task_id = task_id

        if downloader_id is not None:
            self.downloader_id = downloader_id

        if downloader_type is not None:
            self.downloader_type = downloader_type

        if torrent_hash is not None:
            self.torrent_hash = torrent_hash

        if torrent_name is not None:
            self.torrent_name = torrent_name

        if torrent_size is not None:
            self.torrent_size = torrent_size

        self.delete_files = delete_files

        if safety_check_level is not None:
            self.safety_check_level = safety_check_level

        # 序列化 validation_result字典为JSON字符串
        if validation_result is not None:
            self.validation_result = json.dumps(validation_result, ensure_ascii=False)

        if operator_id is not None:
            self.operator_id = operator_id

        if operator_name is not None:
            self.operator_name = operator_name

        if operator_ip is not None:
            self.operator_ip = operator_ip

        if operator_user_agent is not None:
            self.operator_user_agent = operator_user_agent

        if caller_source is not None:
            self.caller_source = caller_source

        if caller_function is not None:
            self.caller_function = caller_function

        if caller_module is not None:
            self.caller_module = caller_module

        if deletion_status is not None:
            self.deletion_status = deletion_status

        if error_message is not None:
            self.error_message = error_message

        if created_at is not None:
            self.created_at = created_at

        if deleted_at is not None:
            self.deleted_at = deleted_at

    def get_validation_result(self) -> Optional[Dict[str, Any]]:
        """
        获取验证结果字典（从JSON字符串反序列化）

        Returns:
            验证结果字典，如果validation_result为空或无效则返回None
        """
        if not self.validation_result:
            return None
        try:
            return json.loads(self.validation_result)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_validation_result(self, result: Dict[str, Any]) -> None:
        """
        设置验证结果字典（序列化为JSON字符串）

        Args:
            result: 验证结果字典
        """
        self.validation_result = json.dumps(result, ensure_ascii=False)

    def to_dict(self, include_validation: bool = True) -> Dict[str, Any]:
        """
        将模型转换为字典

        Args:
            include_validation: 是否包含完整的validation_result（默认True）

        Returns:
            包含所有模型字段的字典
        """
        result = {
            'id': self.id,
            'task_id': self.task_id,
            'downloader_id': self.downloader_id,
            'downloader_type': self.downloader_type,
            'torrent_hash': self.torrent_hash,
            'torrent_name': self.torrent_name,
            'torrent_size': self.torrent_size,
            'delete_files': self.delete_files,
            'safety_check_level': self.safety_check_level,
            'operator_id': self.operator_id,
            'operator_name': self.operator_name,
            'operator_ip': self.operator_ip,
            'operator_user_agent': self.operator_user_agent,
            'caller_source': self.caller_source,
            'caller_function': self.caller_function,
            'caller_module': self.caller_module,
            'deletion_status': self.deletion_status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }

        # 可选是否包含完整的validation_result
        if include_validation and self.validation_result:
            result['validation_result'] = self.get_validation_result()
        elif include_validation:
            result['validation_result'] = None

        return result

    def is_system_operator(self) -> bool:
        """
        判断操作者是否为系统任务

        Returns:
            True如果是系统任务（定时任务或回收站清理）
        """
        return self.operator_id is not None and self.operator_id <= 0

    def is_successful(self) -> bool:
        """
        判断删除是否成功

        Returns:
            True如果删除状态为success
        """
        return self.deletion_status == DELETION_STATUS_SUCCESS

    def is_failed(self) -> bool:
        """
        判断删除是否失败

        Returns:
            True如果删除状态为failed
        """
        return self.deletion_status == DELETION_STATUS_FAILED

    def is_partial(self) -> bool:
        """
        判断删除是否部分成功

        Returns:
            True如果删除状态为partial
        """
        return self.deletion_status == DELETION_STATUS_PARTIAL
