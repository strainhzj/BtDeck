# -*- coding: utf-8 -*-
"""MoviePilot 集成实例模型（feature moviepilot-integration-20260908）。

一行代表一个已握手注册的 MoviePilot 实例（由插件生成并持久化的 UUID 作为
跨库稳定身份）。实例行承载：

- 握手元数据（协议/插件/宿主版本、最后握手时间）；
- 集成账号绑定（首个完成握手的认证用户，防其他账号冒名续写）；
- MoviePilot 下载器 → BtDeck 下载器映射（JSON，MP 侧下载器名 →
  ``bt_downloaders.downloader_id``）；
- 同步状态可见性（最后同步时间/计数/错误，供设置页展示）。

注意：实例被删除时其整理历史一并删除（显式管理动作，见服务层）；
"MoviePilot 侧历史消失"不触发任何本地清理。
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MoviePilotInstance(Base):
    """MoviePilot 集成实例表（moviepilot_instance）。"""

    __tablename__ = "moviepilot_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    instance_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True, comment="插件生成的实例 UUID（跨库稳定身份）"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="实例展示名（插件侧配置）")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否允许该实例握手/同步")
    protocol_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="握手携带的集成协议版本")
    plugin_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="BtDeckBridge 插件版本")
    moviepilot_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="MoviePilot 宿主版本")
    downloader_mapping: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="MP 下载器名 → BtDeck downloader_id 的 JSON 映射"
    )
    bound_username: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="绑定的集成账号（首个握手成功的认证用户）"
    )
    last_handshake_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后握手时间")
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最后成功同步批次时间")
    last_sync_stats: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="最后同步批次统计 JSON（inserted/updated/skipped/failed）"
    )
    synced_history_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="已同步整理历史条数（去重后）"
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="最后一次握手/同步错误（成功后清空）"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    def __init__(
        self,
        instance_id: str,
        name: str = "",
        enabled: bool = True,
        protocol_version: Optional[int] = None,
        plugin_version: Optional[str] = None,
        moviepilot_version: Optional[str] = None,
        downloader_mapping: Optional[str] = None,
        bound_username: Optional[str] = None,
    ):
        self.instance_id = instance_id
        self.name = name
        self.enabled = enabled
        self.protocol_version = protocol_version
        self.plugin_version = plugin_version
        self.moviepilot_version = moviepilot_version
        self.downloader_mapping = downloader_mapping
        self.bound_username = bound_username

    def parsed_mapping(self) -> Dict[str, str]:
        """解析下载器映射 JSON；损坏时返回空映射（不抛错，未映射行保持 unmapped）。"""
        if not self.downloader_mapping:
            return {}
        try:
            data = json.loads(self.downloader_mapping)
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and k and v}

    def to_dict(self) -> Dict[str, Any]:
        stats: Dict[str, Any]
        if self.last_sync_stats:
            try:
                stats = json.loads(self.last_sync_stats)
            except (TypeError, ValueError):
                stats = {}
        else:
            stats = {}
        return {
            "id": self.id,
            "instanceId": self.instance_id,
            "name": self.name,
            "enabled": self.enabled,
            "protocolVersion": self.protocol_version,
            "pluginVersion": self.plugin_version,
            "moviepilotVersion": self.moviepilot_version,
            "downloaderMapping": self.parsed_mapping(),
            "boundUsername": self.bound_username,
            "lastHandshakeAt": self.last_handshake_at.isoformat() if self.last_handshake_at else None,
            "lastSyncAt": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "lastSyncStats": stats,
            "syncedHistoryCount": self.synced_history_count,
            "lastError": self.last_error,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
