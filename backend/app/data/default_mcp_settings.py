# -*- coding: utf-8 -*-
"""MCP 服务默认配置 seed（feature mcp-service-capabilities-2026-08-28 W1）。

``configs`` 表首个版本化 JSON 键 ``mcp.runtime.v1`` 的默认载荷定义。
历史先例只有标量键 ``cookie_expire_minutes``（database.py init_db seed），
本键不自建表、不走 Alembic（无 Schema 变更），seed 语义由
``McpSettingsService`` 按需派生：

- 记录缺失/损坏/未知 schemaVersion 时 fail-closed 回落到本默认值（G1），
  **不做启动期写库**——首次 GET 返回默认态（revision=0），
  首次 PUT 以 expectedRevision=0 建行（revision 递增为 1）；
- 默认值与 ``app/mcp/contracts.py`` 的能力目录单一事实源联动：
  新增能力码自动进入默认关闭集，无需修改本文件。
"""

import copy
from typing import Any, Dict

from app.mcp.contracts import (
    DEFAULT_CAPABILITY_STATES,
    MCP_CONFIG_KEY,
    MCP_CONFIG_SCHEMA_VERSION,
)

# configs.description 列说明（管理界面可见）
MCP_SETTINGS_DESCRIPTION = "MCP 服务运行时配置（版本化 JSON，feature mcp-service-capabilities）"

_DEFAULT_PAYLOAD: Dict[str, Any] = {
    "schemaVersion": MCP_CONFIG_SCHEMA_VERSION,
    "enabled": False,
    "capabilities": dict(DEFAULT_CAPABILITY_STATES),
    "revision": 0,
    "updatedAt": None,
    "updatedBy": None,
}


def default_mcp_settings() -> Dict[str, Any]:
    """返回默认配置载荷的深拷贝（调用方可安全修改）。"""
    return copy.deepcopy(_DEFAULT_PAYLOAD)


__all__ = ["MCP_CONFIG_KEY", "MCP_SETTINGS_DESCRIPTION", "default_mcp_settings"]
