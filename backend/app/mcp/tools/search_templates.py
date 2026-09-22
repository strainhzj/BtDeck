"""MCP 工具：advanced_search_template_create（feature ...W3-①，唯一写工具）。

G4：复用 ``AdvancedSearchService.create_search_template``（同一条件校验
``validate_template_conditions_payload``）；user_id 只取 principal（HTTP 同语义
``str(user_id)``），参数携带 user_id 已被 catalog FORBIDDEN_ARGUMENT 拦截。

G7 三要件：

- **confirm**：catalog 层统一强制（requires_confirm 工具 confirm=true）；
- **幂等**：进程内有界缓存 ``(tool, principal, idempotency_key)`` → 首次结果，
  同键重放返回缓存结果。单进程前提由 SQLite WORKERS=1 启动守卫保证；进程
  重启后同键将再次执行（首版口径，G7 完整重放矩阵在 W4 复核）；
- **审计**：成功/失败均写 ``MCP_TOOL_CALL`` 审计行（operator=principal.username，
  detail 只含工具名/模板 id/结果与幂等键摘要，不含 conditions 原文）。
"""

import asyncio
import logging
from typing import Any, Dict

from app.auth.principal import AuthenticatedPrincipal
from app.mcp.catalog import ToolCallContext
from app.mcp.contracts import CapabilitySpec
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.runtime import McpRuntime
from app.mcp.tools.common import log_tool_audit
from app.mcp.tools.idempotency import cache_get, cache_put, digest_idempotency_key, reset_for_tests
from app.services.advanced_search import AdvancedSearchService

logger = logging.getLogger(__name__)

# 兼容面：W3-① 测试与既有引用的本地别名（实现已收敛到 idempotency 模块）
_idempotency_key_digest = digest_idempotency_key
_cache_get = cache_get
_cache_put = cache_put
_reset_idempotency_cache_for_tests = reset_for_tests


def _map_template_service_error(result: Dict[str, Any]) -> McpToolError:
    code = str(result.get("code", ""))
    if code == "422":
        return McpToolError(McpErrorCode.INVALID_ARGUMENT)
    return McpToolError(McpErrorCode.INTERNAL_ERROR)


async def handle_template_create(
    spec: CapabilitySpec,
    principal: AuthenticatedPrincipal,
    arguments: Dict[str, Any],
    runtime: McpRuntime,
    call_context: ToolCallContext,
) -> Dict[str, Any]:
    """advanced_search_template_create 处理器（DB 写入）。"""
    from app.mcp.tools.conditions import validate_privacy_conditions

    name = arguments["name"]
    conditions = arguments["conditions"]
    is_public = arguments.get("is_public", False)
    idempotency_key = arguments["idempotency_key"]
    validate_privacy_conditions(conditions)

    if principal.user_id is None:
        # 与 HTTP 旧 token 拒绝语义对齐（principal 内核已做 DB 兜底，理论不可达）
        raise McpToolError(McpErrorCode.AUTH_TOKEN_INVALID)
    user_id = str(principal.user_id)

    cache_key = (spec.tool_name, principal.user_id, idempotency_key)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("MCP 幂等重放命中: tool=%s principal=%s", spec.tool_name, principal.user_id)
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "template_id": cached.get("template_id"),
                "idempotency_key": _idempotency_key_digest(idempotency_key),
                "replay": True,
            },
            result="success",
        )
        return dict(cached)

    request_payload = {"name": name, "description": None, "conditions": conditions, "is_public": is_public}

    def _run() -> Dict[str, Any]:
        db = runtime.sync_session()
        try:
            return AdvancedSearchService(db).create_search_template(request_payload, user_id)
        finally:
            db.close()

    result = await asyncio.to_thread(_run)
    if result.get("status") != "success":
        logger.warning("MCP 模板创建被 service 拒绝: code=%s", result.get("code"))
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "idempotency_key": _idempotency_key_digest(idempotency_key),
            },
            result="failed",
            error_message=f"code={result.get('code')}",
        )
        raise _map_template_service_error(result)

    data = result.get("data") or {}
    payload = {
        "template_id": data.get("id"),
        "name": name,
        "is_public": bool(is_public),
        "created": True,
    }
    _cache_put(cache_key, payload)
    await log_tool_audit(
        runtime,
        call_context,
        principal,
        detail={
            "tool": spec.tool_name,
            "template_id": data.get("id"),
            "idempotency_key": _idempotency_key_digest(idempotency_key),
        },
        result="success",
    )
    return payload
