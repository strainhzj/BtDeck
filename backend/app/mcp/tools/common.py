"""MCP 工具共享助手（feature mcp-service-capabilities-2026-08-28 W3-②）。"""

import logging
from typing import Any, Dict, Optional

from app.auth.principal import AuthenticatedPrincipal
from app.mcp.catalog import ToolCallContext
from app.mcp.runtime import McpRuntime

logger = logging.getLogger(__name__)


async def log_tool_audit(
    runtime: McpRuntime,
    call_context: ToolCallContext,
    principal: AuthenticatedPrincipal,
    detail: Dict[str, Any],
    result: str,
    error_message: Optional[str] = None,
) -> None:
    """MCP 工具操作审计（G7/G11）：best-effort，失败不改变业务结果。

    ``MCP_TOOL_CALL`` 汇总行：operator=principal.username，detail 只允许
    工具名/对象标识/结果码与幂等键摘要（不含工具参数与领域 payload 原文）。
    """
    try:
        from app.services.audit_service import AuditLogService
        from app.torrents.audit_enums import AuditOperationType

        adb = runtime.async_session()
        try:
            service = AuditLogService(adb)
            await service.log_operation(
                operation_type=AuditOperationType.MCP_TOOL_CALL,
                operator=principal.username,
                operation_detail=detail,
                operation_result=result,
                error_message=error_message,
                ip_address=call_context.audit.ip_address,
                user_agent=call_context.audit.user_agent,
                request_id=call_context.audit.request_id,
                session_id=call_context.audit.session_id,
            )
        finally:
            await adb.close()
    except Exception as exc:  # noqa: BLE001 - 审计缺失不影响业务主流程
        logger.warning("MCP 工具审计写入失败（不阻断业务结果）: %s", exc)
