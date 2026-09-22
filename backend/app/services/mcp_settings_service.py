"""MCP 运行时配置服务（feature mcp-service-capabilities-2026-08-28 W1）。

职责（计划 §4.2）：

- 复用 ``configs`` 表的 ``mcp.runtime.v1`` 键（首个版本化 JSON 键）读写配置；
- **fail-closed 加载**：记录缺失、JSON 损坏、schemaVersion 未知、结构/字段
  非法一律回落到"全局关闭 + 全部能力关闭"的默认态（G1）；
- **revision CAS**：PUT 携带 ``expectedRevision``，与库中当前 revision 比较，
  不一致抛 ``McpSettingsRevisionConflict``（HTTP 409），一致则 revision+1、
  记录 updatedAt/updatedBy 后提交（G2 热更新基线）；
- **环境 kill switch 覆盖**：``BTDECK_MCP_FORCE_DISABLED=True`` 时
  ``effective_enabled`` 恒为 False，优先级最高且 UI 不可覆盖（允许落库，
  便于紧急处置后恢复原意图配置）。

本服务只依赖同步 ``Session`` 与 ``app.mcp.contracts``（能力目录单一事实源），
不 import FastAPI/Request —— W2 的 MCP runtime 与 HTTP 控制面共用同一实例语义。
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.auth.models import Config
from app.core.config import settings as app_settings
from app.data.default_mcp_settings import MCP_SETTINGS_DESCRIPTION, default_mcp_settings
from app.mcp.contracts import CAPABILITY_CODES, MCP_CONFIG_KEY, MCP_CONFIG_SCHEMA_VERSION

logger = logging.getLogger(__name__)


class McpSettingsStateError(ValueError):
    """配置载荷非法（未知能力码/缺字段/类型错误），HTTP 侧映射 400。"""


class McpSettingsRevisionConflict(RuntimeError):
    """expectedRevision 与库中 revision 不一致（CAS 冲突），HTTP 侧映射 409。"""

    def __init__(self, current_revision: int):
        super().__init__(f"配置已被其他会话修改（当前 revision={current_revision}）")
        self.current_revision = current_revision


@dataclass(frozen=True)
class McpRuntimeSettings:
    """原子配置快照值对象（W2 runtime 的 tools/list 与 tools/call 消费同一形态）。

    ``enabled`` 是存储值；kill switch 生效时 ``force_disabled=True`` 且
    ``effective_enabled`` 恒 False——执行层只允许消费后者。
    """

    enabled: bool
    capabilities: Dict[str, bool] = field(default_factory=dict)
    revision: int = 0
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    force_disabled: bool = False

    @property
    def effective_enabled(self) -> bool:
        return self.enabled and not self.force_disabled

    def capability_enabled(self, code: str) -> bool:
        return self.effective_enabled and self.capabilities.get(code, False)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "schemaVersion": MCP_CONFIG_SCHEMA_VERSION,
            "enabled": self.enabled,
            "capabilities": dict(self.capabilities),
            "revision": self.revision,
            "updatedAt": self.updated_at,
            "updatedBy": self.updated_by,
            "forceDisabled": self.force_disabled,
            "effectiveEnabled": self.effective_enabled,
        }


class McpSettingsService:
    """mcp.runtime.v1 的读写与 fail-closed 解析（协议无关，同步 Session）。"""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ 读

    def get_settings(self) -> McpRuntimeSettings:
        """读取生效配置：库值 + kill switch 覆盖；任何解析失败回落默认态。"""
        stored = self._load_stored_payload()
        return self._to_settings(stored)

    # ------------------------------------------------------------------ 写

    def update_settings(
        self,
        enabled: bool,
        capabilities: Dict[str, bool],
        expected_revision: int,
        updated_by: str,
    ) -> McpRuntimeSettings:
        """CAS 更新并返回新快照。

        校验顺序：载荷结构（能力码全集 + bool 类型）→ revision CAS → 提交。
        库中无记录时当前 revision 视为 0（expectedRevision=0 建行）。
        """
        normalized = self._validate_request(enabled, capabilities)
        row = self.db.query(Config).filter(Config.key == MCP_CONFIG_KEY).first()
        current_revision = self._stored_revision(row)
        if expected_revision != current_revision:
            raise McpSettingsRevisionConflict(current_revision)

        new_revision = current_revision + 1
        payload = default_mcp_settings()
        payload.update(
            {
                "enabled": normalized["enabled"],
                "capabilities": normalized["capabilities"],
                "revision": new_revision,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "updatedBy": updated_by,
            }
        )
        if row is None:
            self.db.add(
                Config(
                    key=MCP_CONFIG_KEY,
                    value=json.dumps(payload, ensure_ascii=False),
                    description=MCP_SETTINGS_DESCRIPTION,
                )
            )
        else:
            row.value = json.dumps(payload, ensure_ascii=False)
            if not row.description:
                row.description = MCP_SETTINGS_DESCRIPTION
        self.db.commit()
        return self._to_settings(payload)

    # ------------------------------------------------------------------ 内部

    def _load_stored_payload(self) -> Optional[Dict[str, Any]]:
        """读取并解析库中 JSON；缺失/损坏返回 None（不抛错，fail-closed 回落）。"""
        row = self.db.query(Config).filter(Config.key == MCP_CONFIG_KEY).first()
        if row is None or not row.value:
            return None
        try:
            payload = json.loads(row.value)
        except (TypeError, json.JSONDecodeError) as exc:
            logger.warning("MCP 配置 JSON 损坏，fail-closed 回落默认关闭: %s", exc)
            return None
        if not isinstance(payload, dict):
            logger.warning("MCP 配置 JSON 非对象，fail-closed 回落默认关闭")
            return None
        return payload

    def _to_settings(self, payload: Optional[Dict[str, Any]]) -> McpRuntimeSettings:
        """把库中载荷折叠为生效快照；结构非法（含未知 schemaVersion）整体回落默认。

        字段级校验：schemaVersion 必须等于当前支持的版本；enabled 必须是 bool；
        capabilities 必须覆盖全部已知能力码且值全为 bool——任一不满足即整份
        回落默认（G1"字段缺失均 fail-closed"），不部分采信。
        """
        parsed = self._parse_structured(payload)
        force_disabled = bool(app_settings.BTDECK_MCP_FORCE_DISABLED)
        if parsed is None:
            defaults = default_mcp_settings()
            return McpRuntimeSettings(
                enabled=False,
                capabilities=dict(defaults["capabilities"]),
                revision=0,
                updated_at=None,
                updated_by=None,
                force_disabled=force_disabled,
            )
        enabled, capabilities, revision, updated_at, updated_by = parsed
        return McpRuntimeSettings(
            enabled=enabled,
            capabilities=capabilities,
            revision=revision,
            updated_at=updated_at,
            updated_by=updated_by,
            force_disabled=force_disabled,
        )

    def _parse_structured(
        self, payload: Optional[Dict[str, Any]]
    ) -> Optional[Tuple[bool, Dict[str, bool], int, Optional[str], Optional[str]]]:
        """结构校验；非法返回 None（不信任部分字段，见 _to_settings 注释）。"""
        if payload is None:
            return None
        if payload.get("schemaVersion") != MCP_CONFIG_SCHEMA_VERSION:
            logger.warning(
                "MCP 配置 schemaVersion 未知（%r），fail-closed 回落默认关闭",
                payload.get("schemaVersion"),
            )
            return None
        enabled = payload.get("enabled")
        capabilities = payload.get("capabilities")
        revision = payload.get("revision")
        if not isinstance(enabled, bool) or not isinstance(capabilities, dict):
            return None
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            return None
        normalized: Dict[str, bool] = {}
        for code in CAPABILITY_CODES:
            value = capabilities.get(code)
            if not isinstance(value, bool):
                return None
            normalized[code] = value
        updated_at = payload.get("updatedAt")
        updated_by = payload.get("updatedBy")
        return (
            enabled,
            normalized,
            revision,
            updated_at if isinstance(updated_at, str) else None,
            updated_by if isinstance(updated_by, str) else None,
        )

    def _validate_request(self, enabled: bool, capabilities: Dict[str, bool]) -> Dict[str, Any]:
        """PUT 载荷校验：必须携带全部已知能力码，禁止未知码（防别名绕过 G2）。"""
        if not isinstance(enabled, bool):
            raise McpSettingsStateError("enabled 必须为布尔值")
        if not isinstance(capabilities, dict):
            raise McpSettingsStateError("capabilities 必须为对象")
        unknown = set(capabilities) - set(CAPABILITY_CODES)
        if unknown:
            raise McpSettingsStateError(f"未知能力码: {sorted(unknown)}")
        missing = set(CAPABILITY_CODES) - set(capabilities)
        if missing:
            raise McpSettingsStateError(f"缺少能力码: {sorted(missing)}")
        for code, value in capabilities.items():
            if not isinstance(value, bool):
                raise McpSettingsStateError(f"能力 {code} 的值必须为布尔值")
        return {"enabled": enabled, "capabilities": {code: bool(capabilities[code]) for code in CAPABILITY_CODES}}

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
