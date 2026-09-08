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
import hashlib
import logging
from collections import OrderedDict
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from app.auth.principal import AuthenticatedPrincipal
from app.mcp.catalog import ToolCallContext
from app.mcp.contracts import CapabilitySpec
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.runtime import McpRuntime
from app.services.advanced_search import AdvancedSearchService

logger = logging.getLogger(__name__)

# 进程内幂等缓存（有界 LRU；单 Worker 前提下进程即全实例）
_IDEMPOTENCY_CACHE: "OrderedDict[Tuple[str, Any, str], Dict[str, Any]]" = OrderedDict()
_IDEMPOTENCY_CACHE_LIMIT = 512
_IDEMPOTENCY_LOCK = Lock()


def _idempotency_key_digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _cache_get(cache_key: Tuple[str, Any, str]) -> Optional[Dict[str, Any]]:
    with _IDEMPOTENCY_LOCK:
        if cache_key in _IDEMPOTENCY_CACHE:
            _IDEMPOTENCY_CACHE.move_to_end(cache_key)
            return _IDEMPOTENCY_CACHE[cache_key]
    return None


def _cache_put(cache_key: Tuple[str, Any, str], result: Dict[str, Any]) -> None:
    with _IDEMPOTENCY_LOCK:
        _IDEMPOTENCY_CACHE[cache_key] = result
        _IDEMPOTENCY_CACHE.move_to_end(cache_key)
        while len(_IDEMPOTENCY_CACHE) > _IDEMPOTENCY_CACHE_LIMIT:
            _IDEMPOTENCY_CACHE.popitem(last=False)


def _reset_idempotency_cache_for_tests() -> None:
    with _IDEMPOTENCY_LOCK:
        _IDEMPOTENCY_CACHE.clear()


def _map_template_service_error(result: Dict[str, Any]) -> McpToolError:
    code = str(result.get("code", ""))
    if code == "422":
        return McpToolError(McpErrorCode.INVALID_ARGUMENT)
    return McpToolError(McpErrorCode.INTERNAL_ERROR)


async def _log_tool_audit(
    runtime: McpRuntime,
    call_context: ToolCallContext,
    principal: AuthenticatedPrincipal,
    detail: Dict[str, Any],
    result: str,
    error_message: Optional[str] = None,
) -> None:
    """MCP 工具写操作审计（G7/G11）：best-effort，失败不改变业务结果。"""
    try:
        from app.services.audit_service import AuditLogService
        from app.torrents.audit_enums import AuditOperationType

        async def _run() -> None:
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

        await _run()
    except Exception as exc:  # noqa: BLE001 - 审计缺失不影响业务主流程
        logger.warning("MCP 工具审计写入失败（不阻断业务结果）: %s", exc)


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
        await _log_tool_audit(
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
        await _log_tool_audit(
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
    await _log_tool_audit(
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
