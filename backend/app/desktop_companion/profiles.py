# -*- coding: utf-8 -*-
"""服务器 profile 模型与持久化（dual-mode-client task .6 桌面对齐）。

字段与安卓端 com.btdeck.companion.data.ServerProfile 一致（JSON 编码键名对齐），
持久化为 CONFIG_PATH/companion_servers.json（原子写：临时文件 + os.replace）。
健康状态沿用安卓五态；trustedCertFingerprints 为安卓 WebView 指纹信任流程
专用，桌面端内嵌 WebView 的证书 UX 由渲染引擎承载，不落此字段。
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

HEALTH_UNKNOWN = "UNKNOWN"
HEALTH_READY = "READY"
HEALTH_NOT_READY = "NOT_READY"
HEALTH_UNREACHABLE = "UNREACHABLE"
HEALTH_TLS_ERROR = "TLS_ERROR"

_VALID_HEALTH_STATES = {
    HEALTH_UNKNOWN,
    HEALTH_READY,
    HEALTH_NOT_READY,
    HEALTH_UNREACHABLE,
    HEALTH_TLS_ERROR,
}

HEALTH_LABELS: dict[str, str] = {
    HEALTH_UNKNOWN: "未测试",
    HEALTH_READY: "就绪",
    HEALTH_NOT_READY: "未就绪",
    HEALTH_UNREACHABLE: "不可达",
    HEALTH_TLS_ERROR: "证书错误",
}


@dataclass
class ServerProfile:
    display_name: str
    base_url: str
    cleartext_allowed: bool = False
    health_state: str = HEALTH_UNKNOWN
    server_version: Optional[str] = None
    last_health_checked_at: int = 0
    last_connected_at: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "displayName": self.display_name,
            "baseUrl": self.base_url,
            "cleartextAllowed": self.cleartext_allowed,
            "healthState": self.health_state,
            "serverVersion": self.server_version,
            "lastHealthCheckedAt": self.last_health_checked_at,
            "lastConnectedAt": self.last_connected_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ServerProfile":
        health_state = data.get("healthState", HEALTH_UNKNOWN)
        if health_state not in _VALID_HEALTH_STATES:
            # 向前兼容：未知状态值回退 UNKNOWN，不因旧数据污染而崩
            health_state = HEALTH_UNKNOWN
        profile_id = data.get("id")
        return cls(
            id=profile_id if isinstance(profile_id, str) and profile_id else uuid.uuid4().hex,
            display_name=str(data.get("displayName", "")),
            base_url=str(data.get("baseUrl", "")),
            cleartext_allowed=bool(data.get("cleartextAllowed", False)),
            health_state=health_state,
            server_version=data.get("serverVersion"),
            last_health_checked_at=int(data.get("lastHealthCheckedAt", 0) or 0),
            last_connected_at=int(data.get("lastConnectedAt", 0) or 0),
        )


class ServerProfileStore:
    """JSON 文件存储；单进程桌面场景，不做并发锁（与安卓 SharedPreferences 对齐）。"""

    def __init__(self, path: Path):
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load_all(self) -> list[ServerProfile]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取服务器列表失败（%s）：%s", self._path, exc)
            return []
        if not isinstance(raw, list):
            return []
        return [ServerProfile.from_json(item) for item in raw if isinstance(item, dict)]

    def upsert(self, profile: ServerProfile) -> None:
        profiles = [item for item in self.load_all() if item.id != profile.id]
        profiles.append(profile)
        self._save(profiles)

    def remove(self, profile_id: str) -> bool:
        profiles = self.load_all()
        remaining = [item for item in profiles if item.id != profile_id]
        if len(remaining) == len(profiles):
            return False
        self._save(remaining)
        return True

    def _save(self, profiles: list[ServerProfile]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = json.dumps([profile.to_json() for profile in profiles], ensure_ascii=False, indent=2)
        temp_path.write_text(payload, encoding="utf-8")
        os.replace(temp_path, self._path)
