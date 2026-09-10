# -*- coding: utf-8 -*-
"""MoviePilot 集成全局开关服务（feature moviepilot-integration-20260908）。

复用 ``configs`` 表版本化 JSON 键模式（``mcp_settings_service`` 先例，字段
收敛为单一 ``enabled`` 开关）：

- **fail-closed 加载**：记录缺失/JSON 损坏/未知 schemaVersion/字段非法一律
  回落到"集成关闭"默认态；
- **revision CAS**：PUT 携带 ``expectedRevision``，不一致抛
  ``MoviePilotSettingsRevisionConflict``（HTTP 409），一致则 revision+1；
- 集成面（握手/同步）在 ``effective_enabled=False`` 时整体拒绝（HTTP 403）。

与 MCP 不同点：无逐能力开关与 kill switch 环境变量——本集成只读入镜像、
不暴露任何写操作面，全局开关即完整管控面。
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.auth.models import Config
from app.data.default_moviepilot_settings import (
    MOVIEPILOT_CONFIG_KEY,
    MOVIEPILOT_CONFIG_SCHEMA_VERSION,
    MOVIEPILOT_SETTINGS_DESCRIPTION,
    default_moviepilot_settings,
)

logger = logging.getLogger(__name__)


class MoviePilotSettingsStateError(ValueError):
    """配置载荷非法，HTTP 侧映射 400。"""


class MoviePilotSettingsRevisionConflict(RuntimeError):
    """expectedRevision 与库中 revision 不一致（CAS 冲突），HTTP 侧映射 409。"""

    def __init__(self, current_revision: int):
        super().__init__(f"配置已被其他会话修改（当前 revision={current_revision}）")
        self.current_revision = current_revision


@dataclass(frozen=True)
class MoviePilotIntegrationSettings:
    """原子配置快照值对象。"""

    enabled: bool
    revision: int = 0
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    @property
    def effective_enabled(self) -> bool:
        return self.enabled

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schemaVersion": MOVIEPILOT_CONFIG_SCHEMA_VERSION,
            "enabled": self.enabled,
            "revision": self.revision,
            "updatedAt": self.updated_at,
            "updatedBy": self.updated_by,
        }


class MoviePilotSettingsService:
    """moviepilot.integration.v1 的读写与 fail-closed 解析（同步 Session）。"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ 读

    def get_settings(self) -> MoviePilotIntegrationSettings:
        """读取生效配置；任何解析失败回落默认关闭。"""
        row = self.db.query(Config).filter(Config.key == MOVIEPILOT_CONFIG_KEY).first()
        payload: Optional[Dict[str, Any]] = None
        if row is not None and row.value:
            try:
                candidate = json.loads(row.value)
                payload = candidate if isinstance(candidate, dict) else None
            except (TypeError, json.JSONDecodeError) as exc:
                logger.warning("MoviePilot 集成配置 JSON 损坏，fail-closed 回落默认关闭: %s", exc)
                payload = None
        return self._to_settings(payload)

    # ------------------------------------------------------------------ 写

    def update_settings(self, enabled: bool, expected_revision: int, updated_by: str) -> MoviePilotIntegrationSettings:
        """CAS 更新并返回新快照；库中无记录时当前 revision 视为 0。"""
        if not isinstance(enabled, bool):
            raise MoviePilotSettingsStateError("enabled 必须为布尔值")
        row = self.db.query(Config).filter(Config.key == MOVIEPILOT_CONFIG_KEY).first()
        current_revision = self._stored_revision(row)
        if expected_revision != current_revision:
            raise MoviePilotSettingsRevisionConflict(current_revision)

        payload = default_moviepilot_settings()
        payload.update(
            {
                "enabled": enabled,
                "revision": current_revision + 1,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "updatedBy": updated_by,
            }
        )
        if row is None:
            self.db.add(
                Config(
                    key=MOVIEPILOT_CONFIG_KEY,
                    value=json.dumps(payload, ensure_ascii=False),
                    description=MOVIEPILOT_SETTINGS_DESCRIPTION,
                )
            )
        else:
            row.value = json.dumps(payload, ensure_ascii=False)
            if not row.description:
                row.description = MOVIEPILOT_SETTINGS_DESCRIPTION
        self.db.commit()
        return self._to_settings(payload)

    # ------------------------------------------------------------------ 内部

    def _to_settings(self, payload: Optional[Dict[str, Any]]) -> MoviePilotIntegrationSettings:
        parsed = self._parse_structured(payload)
        if parsed is None:
            return MoviePilotIntegrationSettings(enabled=False)
        enabled, revision, updated_at, updated_by = parsed
        return MoviePilotIntegrationSettings(
            enabled=enabled,
            revision=revision,
            updated_at=updated_at,
            updated_by=updated_by,
        )

    def _parse_structured(
        self, payload: Optional[Dict[str, Any]]
    ) -> Optional[Tuple[bool, int, Optional[str], Optional[str]]]:
        """结构校验；非法返回 None（不信任部分字段）。"""
        if payload is None:
            return None
        if payload.get("schemaVersion") != MOVIEPILOT_CONFIG_SCHEMA_VERSION:
            logger.warning(
                "MoviePilot 集成配置 schemaVersion 未知（%r），fail-closed 回落默认关闭",
                payload.get("schemaVersion"),
            )
            return None
        enabled = payload.get("enabled")
        revision = payload.get("revision")
        if not isinstance(enabled, bool):
            return None
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            return None
        updated_at = payload.get("updatedAt")
        updated_by = payload.get("updatedBy")
        return (
            enabled,
            revision,
            updated_at if isinstance(updated_at, str) else None,
            updated_by if isinstance(updated_by, str) else None,
        )

    def _stored_revision(self, row: Optional[Config]) -> int:
        """库中当前 revision（无记录/不可解析=0，与 GET 默认态一致）。"""
        if row is None or not row.value:
            return 0
        try:
            payload = json.loads(row.value)
        except (TypeError, json.JSONDecodeError):
            return 0
        revision = payload.get("revision") if isinstance(payload, dict) else None
        if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0:
            return revision
        return 0
