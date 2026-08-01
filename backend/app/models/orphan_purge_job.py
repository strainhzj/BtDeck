# -*- coding: utf-8 -*-
"""孤儿文件隔离区异步彻底删除任务。"""

import json
from datetime import datetime
from typing import Any, Dict, List, cast

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


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
    canonical_paths_json = Column(Text, nullable=False, comment="待删除规范化路径 JSON 数组")
    operator = Column(String(100), nullable=False, comment="任务提交人")
    total_count = Column(Integer, nullable=False, default=0, comment="待处理数量")
    purged_count = Column(Integer, nullable=False, default=0, comment="成功删除数量")
    failed_count = Column(Integer, nullable=False, default=0, comment="失败数量")
    failed_list_json = Column(Text, nullable=True, comment="失败项 JSON 数组")
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
    def failed_list(self) -> List[Dict[str, Any]]:
        """解析失败项。"""
        if not self.failed_list_json:
            return []
        try:
            value = json.loads(cast(str, self.failed_list_json))
        except (json.JSONDecodeError, TypeError):
            return []
        return value if isinstance(value, list) else []

    def to_dict(self) -> Dict[str, Any]:
        """转换为 API 任务状态。"""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "total_count": self.total_count,
            "purged_count": self.purged_count,
            "failed_count": self.failed_count,
            "failed_list": self.failed_list,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
