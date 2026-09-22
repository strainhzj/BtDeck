"""MCP 工具：dashboard_get（feature mcp-service-capabilities W3-①，只读）。

复用 ``DashboardService``（AsyncSession + RuntimeContext 注入版，G4）。
输出仅脱敏聚合（契约 allowlist）：下载器/种子/任务计数、全局速度——
``downloader_list``（含连接信息）与 ``activities``（审计敏感字段）不进入
MCP DTO；store 未就绪时 service 语义为零值聚合（与 HTTP 仪表盘一致），
不触发 RUNTIME_NOT_READY（纯读、无外部副作用）。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.auth.principal import AuthenticatedPrincipal
from app.mcp.catalog import ToolCallContext
from app.mcp.contracts import CapabilitySpec
from app.mcp.runtime import McpRuntime
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)


async def handle_dashboard_get(
    spec: CapabilitySpec,
    principal: AuthenticatedPrincipal,
    arguments: Dict[str, Any],
    runtime: McpRuntime,
    call_context: ToolCallContext,
) -> Dict[str, Any]:
    """dashboard_get 处理器（无入参）。"""
    adb = runtime.async_session()
    try:
        service = DashboardService(adb, runtime.context)
        data = await service.get_dashboard_data()
    finally:
        await adb.close()

    torrents_stats: Dict[str, Any] = data.get("torrents") or {}
    system_stats: Dict[str, Any] = data.get("system") or {}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "downloaders": data.get("downloaders") or {},
            "torrents": torrents_stats,
            "tasks": data.get("tasks") or {},
        },
        "status_counts": dict(torrents_stats),
        "active_torrent_count": int(torrents_stats.get("active", 0) or 0),
        "global_download_speed": int(system_stats.get("total_download_speed", 0) or 0),
        "global_upload_speed": int(system_stats.get("total_upload_speed", 0) or 0),
    }
