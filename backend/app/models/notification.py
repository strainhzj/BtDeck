# -*- coding: utf-8 -*-
"""
通知模型

系统单向通知信箱，用于版本更新通知、系统消息等。
系统通过后台任务写入通知记录，用户在通知中心查看。

@author: btpManager Team
@file: notification.py
@time: 2026-04-24
"""

from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime
from app.database import Base


class Notification(Base):
    """
    通知表

    Attributes:
        id: 主键（自增）
        type: 通知类型（version_update / system）
        title: 通知标题
        content: 通知内容（支持纯文本）
        priority: 优先级（info / warning / error）
        is_read: 是否已读
        extra_data: JSON扩展数据（如版本号、下载链接等）
        created_at: 创建时间
        read_at: 已读时间（可选）
    """
    __tablename__ = 'notification'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键')
    type = Column(String(30), nullable=False, index=True, comment='通知类型：version_update / system')
    title = Column(String(255), nullable=False, comment='通知标题')
    content = Column(Text, nullable=True, comment='通知内容')
    priority = Column(String(10), nullable=False, default='info', comment='优先级：info / warning / error')
    is_read = Column(Boolean, nullable=False, default=False, index=True, comment='是否已读')
    extra_data = Column(Text, nullable=True, comment='JSON扩展数据')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment='创建时间')
    read_at = Column(DateTime, nullable=True, comment='已读时间')

    def __init__(
        self,
        type: Optional[str] = None,
        title: Optional[str] = None,
        content: Optional[str] = None,
        priority: str = 'info',
        is_read: bool = False,
        extra_data: Optional[Dict[str, Any]] = None,
        **kw: Any
    ):
        super().__init__(**kw)
        if type is not None:
            self.type = type
        if title is not None:
            self.title = title
        if content is not None:
            self.content = content
        self.priority = priority
        self.is_read = is_read
        if extra_data is not None:
            import json
            self.extra_data = json.dumps(extra_data, ensure_ascii=False)

    def to_dict(self) -> Dict[str, Any]:
        """将模型转换为字典"""
        import json
        result = {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'content': self.content,
            'priority': self.priority,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
        }
        if self.extra_data:
            try:
                result['extra_data'] = json.loads(self.extra_data)
            except (json.JSONDecodeError, TypeError):
                result['extra_data'] = None
        else:
            result['extra_data'] = None
        return result
