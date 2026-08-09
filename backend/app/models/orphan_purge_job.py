# -*- coding: utf-8 -*-
"""孤儿文件隔离区异步彻底删除任务。"""

import json
from datetime import datetime
from typing import Any, Dict, List, cast

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base
from app.utils.datetime_utils import serialize_utc_datetime


class OrphanPurgeJob(Base):
    """持久化的隔离区彻底删除任务。"""

    __tablename__ = "orphan_purge_job"

    task_id = Column(String(36), primary_key=True, comment="任务 UUID")
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="pending/running/completed/partial/failed",
    )
    operation_type = Column(
        String(20),
        nullable=False,
        default="purge",
        server_default="purge",
        index=True,
        comment="purge/cleanup",
    )
    canonical_paths_json = Column(Text, nullable=False, comment="待删除规范化路径 JSON 数组")
    scan_id = Column(String(36), nullable=True, index=True, comment="主动清理绑定的扫描批次")
    orphan_ids_json = Column(Text, nullable=True, comment="主动清理的孤儿文件 ID JSON 数组")
    operator = Column(String(100), nullable=False, comment="任务提交人")
    total_count = Column(Integer, nullable=False, default=0, comment="待处理数量")
    purged_count = Column(Integer, nullable=False, default=0, comment="成功删除数量")
    failed_count = Column(Integer, nullable=False, default=0, comment="失败数量")
    total_size = Column(Integer, nullable=False, default=0, server_default="0", comment="成功处理的文件总大小")
    failed_list_json = Column(Text, nullable=True, comment="失败项 JSON 数组")
    hardlink_notes_json = Column(
        Text,
        nullable=True,
        comment="成功删除但存在其它硬链接副本的诊断 JSON 数组（路径+is_seed）",
    )
    error_message = Column(Text, nullable=True, comment="任务级异常")
    notification_sent_at = Column(DateTime, nullable=True, comment="结果通知成功写入时间")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True, comment="创建时间")
    started_at = Column(DateTime, nullable=True, comment="首次开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )

    @property
    def canonical_paths(self) -> List[str]:
        """解析待删除路径；坏数据按空列表 fail-closed。"""
        try:
            value = json.loads(cast(str, self.canonical_paths_json) or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []

    @property
    def orphan_ids(self) -> List[int]:
        """Parse the orphan IDs captured by an asynchronous cleanup job."""
        try:
            value = json.loads(cast(str, self.orphan_ids_json) or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(value, list):
            return []

        result: List[int] = []
        for item in value:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    @property
    def failed_list(self) -> List[Dict[str, Any]]:
        """解析失败项。"""
        if not self.failed_list_json:
            return []
        try:
            value = json.loads(cast(str, self.failed_list_json))
        except (json.JSONDecodeError, TypeError):
            return []
        return value if isinstance(value, list) else []

    @property
    def hardlink_notes(self) -> List[Dict[str, Any]]:
        """解析硬链接副本诊断项（成功删除但存在其它副本）。"""
        if not self.hardlink_notes_json:
            return []
        try:
            value = json.loads(cast(str, self.hardlink_notes_json))
        except (json.JSONDecodeError, TypeError):
            return []
        return value if isinstance(value, list) else []

    def to_dict(self) -> Dict[str, Any]:
        """转换为 API 任务状态。"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "operation_type": self.operation_type or "purge",
            "scan_id": self.scan_id,
            "total_count": self.total_count,
            "purged_count": self.purged_count,
            "success_count": self.purged_count,
            "failed_count": self.failed_count,
            "total_size": self.total_size or 0,
            "failed_list": self.failed_list,
            "hardlink_notes": self.hardlink_notes,
            "error_message": self.error_message,
            "created_at": serialize_utc_datetime(self.created_at),
            "started_at": serialize_utc_datetime(self.started_at),
            "completed_at": serialize_utc_datetime(self.completed_at),
        }
