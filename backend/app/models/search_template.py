# -*- coding: utf-8 -*-
"""
搜索模板 ORM 模型（第四轨归位）

历史背景：search_templates 表原由 advanced_search.py 的 _ensure_table_exists()
用原生 SQL 按需自建，独立于 Alembic 和 create_all（第四轨）。
四轨治理后，该表由 Alembic 迁移统一管理，本模型为其 ORM 映射。

字段定义严格匹配 advanced_search.py:812-824 的 CREATE TABLE 与
config/production_complete_schema.sql:233-244（三方一致）。

注意：conditions 字段用 Column(Text) 存储字符串化 JSON，应用层负责
json.dumps/loads 序列化。禁止改用 Column(JSON)——现有数据是字符串化 JSON，
Column(JSON) 读取时会二次解析报错。

@author: BtDeck Team
@file: search_template.py
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class SearchTemplate(Base):
    """搜索模板表（高级搜索的查询条件预设）。

    Attributes:
        id: 模板唯一标识（UUID）
        user_id: 所属用户 ID（系统预设为 "system"）
        name: 模板名称
        description: 模板描述
        conditions: 查询条件（JSON 字符串，应用层序列化）
        is_default: 是否系统预设（1=预设，0=用户自定义）
        is_public: 是否公开可见
        usage_count: 使用次数
        created_time: 创建时间
        updated_time: 更新时间
    """

    __tablename__ = "search_templates"

    id = Column(String(36), primary_key=True, comment="模板唯一标识（UUID）")
    user_id = Column(String(36), nullable=False, index=True, comment="所属用户 ID")
    name = Column(String(100), nullable=False, comment="模板名称")
    description = Column(String(500), nullable=True, comment="模板描述")
    conditions = Column(Text, nullable=False, comment="查询条件（JSON 字符串）")
    is_default = Column(Integer, nullable=False, default=0, comment="是否系统预设：1=预设，0=用户自定义")
    is_public = Column(Integer, nullable=False, default=0, index=True, comment="是否公开可见")
    usage_count = Column(Integer, nullable=False, default=0, comment="使用次数")
    created_time = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_time = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    def __init__(
        self,
        id: Optional[str] = None,
        user_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        conditions: Optional[str] = None,
        is_default: int = 0,
        is_public: int = 0,
        usage_count: int = 0,
        **kw: Any,
    ):
        super().__init__(**kw)
        if id is not None:
            self.id = id
        if user_id is not None:
            self.user_id = user_id
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if conditions is not None:
            self.conditions = conditions
        self.is_default = is_default
        self.is_public = is_public
        self.usage_count = usage_count

    def to_dict(self) -> Dict[str, Any]:
        """将模型转换为字典（conditions 保持字符串形态，由调用方按需解析）。"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "conditions": self.conditions,
            "is_default": self.is_default,
            "is_public": self.is_public,
            "usage_count": self.usage_count,
            "created_time": self.created_time.isoformat() if self.created_time else None,
            "updated_time": self.updated_time.isoformat() if self.updated_time else None,
        }
