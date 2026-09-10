# -*- coding: utf-8 -*-
"""MoviePilot 集成默认配置 seed（feature moviepilot-integration-20260908）。

configs 表版本化 JSON 键 ``moviepilot.integration.v1`` 的默认载荷。
与 ``mcp.runtime.v1`` 同一模式（default_mcp_settings 先例）：

- 记录缺失/损坏/未知 schemaVersion 时 fail-closed 回落到本默认值
  （**默认关闭**——集成面默认不开放，须管理员显式启用）；
- 不做启动期写库：首次 GET 返回默认态（revision=0），首次 PUT 以
  expectedRevision=0 建行。
"""

import copy
from typing import Any, Dict

MOVIEPILOT_CONFIG_KEY = "moviepilot.integration.v1"
MOVIEPILOT_CONFIG_SCHEMA_VERSION = 1

# configs.description 列说明（管理界面可见）
MOVIEPILOT_SETTINGS_DESCRIPTION = "MoviePilot 集成配置（版本化 JSON，feature moviepilot-integration）"

_DEFAULT_PAYLOAD: Dict[str, Any] = {
    "schemaVersion": MOVIEPILOT_CONFIG_SCHEMA_VERSION,
    "enabled": False,
    "revision": 0,
    "updatedAt": None,
    "updatedBy": None,
}


def default_moviepilot_settings() -> Dict[str, Any]:
    """返回默认配置载荷的深拷贝（调用方可安全修改）。"""
    return copy.deepcopy(_DEFAULT_PAYLOAD)
