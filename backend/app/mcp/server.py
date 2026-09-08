"""MCP 同进程服务接线（feature mcp-service-capabilities-2026-08-28 W2）。

官方 ``mcp`` SDK（锁定 1.30.0，选型结论见计划 §10.4）：lowlevel ``Server`` +
``StreamableHTTPSessionManager(stateless=True, json_response=True)``，挂载为
Starlette 子应用供父应用 ``app.mount("/mcp", ...)``（必须早于 SPA fallback）。

关键接线事实（W0 探针 C1~C4 实证，§10.4"W2 接线实证"）：

- FastAPI 挂载子应用**不会**自动运行其 lifespan——父应用 lifespan 必须手动进入
  ``sub_asgi.router.lifespan_context(sub_asgi)``（内部即 ``session_manager.run()``）；
- 挂载点 ``/mcp`` + 子路由 ``/`` 时 ``POST /mcp`` 会 307 到 ``/mcp/``——
  客户端端点按 ``/mcp/`` 对齐；
- 工具处理器内 ``server.request_context.request`` 是 streamable HTTP transport
  注入的 Starlette Request（header 面供 auth.py 提取 Bearer）。

错误纪律：SDK 的 call_tool 装饰器会把未捕获异常渲染为 ``str(exc)`` 文本、
list_tools 侧 ``_handle_request`` 同样以异常文本构造 ErrorData——两处都会外泄
上游细节（§4.5 free_text_error）。因此本模块的处理器必须自捕获一切异常并
渲染固定文案的稳定错误码结果。

本模块在 import 期即依赖 ``mcp`` 包（生产 requirements 至 W4 才锁定），
唯一调用方 factory.py 以 try-import 守卫——SDK 缺失时 MCP 面整体不挂载。
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import mcp.types as mcp_types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.exceptions import McpError
from starlette.applications import Starlette
from starlette.routing import Mount

from app.auth.principal import AuthenticatedPrincipal
from app.mcp import catalog
from app.mcp.auth import authenticate_token, extract_token_from_request
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.redaction import finalize_tool_output
from app.mcp.runtime import McpRuntime

logger = logging.getLogger(__name__)

MCP_SERVER_NAME = "BtDeck"
MCP_SERVER_PATH = "/mcp"  # 客户端实际请求 /mcp/（无斜杠 307，§10.4）
# JSON-RPC 应用级错误码（server error 区段）；稳定字符串码放 data.error_code
_JSONRPC_APP_ERROR = -32000


@dataclass
class McpServerBundle:
    """父应用挂载所需的全部句柄。"""

    runtime: McpRuntime
    server: Server
    session_manager: StreamableHTTPSessionManager
    sub_asgi: Starlette


def _error_call_result(error: McpToolError) -> mcp_types.CallToolResult:
    """稳定错误渲染：isError + 固定文案；结构面只含 code/message。"""
    payload = {"error": {"code": error.code.value, "message": error.message}}
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structuredContent=payload,
        isError=True,
    )


def _success_call_result(payload: Dict[str, Any]) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
        structuredContent=payload,
        isError=False,
    )


def _jsonrpc_mcp_error(error: McpToolError) -> mcp_types.ErrorData:
    return mcp_types.ErrorData(
        code=_JSONRPC_APP_ERROR,
        message=error.message,
        data={"error_code": error.code.value},
    )


async def _authenticate_caller(server: Server, runtime: McpRuntime) -> AuthenticatedPrincipal:
    """从当前请求上下文取 token，并在工作线程完成 DB 认证（不占事件循环）。"""
    token: Optional[str] = extract_token_from_request(_resolve_transport_request(server))

    def _run() -> AuthenticatedPrincipal:
        db = runtime.sync_session()
        try:
            return authenticate_token(token, db)
        finally:
            db.close()

    return await asyncio.to_thread(_run)


def _audit_context_from_transport_request(request: Any) -> Any:
    """从 streamable HTTP 请求提取审计四元组（§4.5：进审计日志，不进业务响应）。"""
    from app.services.audit_context import AuditContext

    if request is None:
        return AuditContext()
    try:
        client = getattr(request, "client", None)
        ip_address = str(getattr(client, "host", "") or "")
        headers = getattr(request, "headers", None)
        user_agent = str(headers.get("user-agent", "") or "") if headers is not None else ""
        return AuditContext(ip_address=ip_address, user_agent=user_agent)
    except Exception:  # header 面异常 → 空上下文，不影响业务
        return AuditContext()


def _resolve_transport_request(server: Server) -> Any:
    """当前请求上下文中的 transport 请求（无上下文返回 None）。"""
    try:
        return server.request_context.request
    except LookupError:
        return None


def create_mcp_server_bundle(state: Any) -> McpServerBundle:
    """构造 MCP 服务束：runtime + lowlevel Server + stateless 会话管理器。

    ``state`` 是父应用 ``app.state``（runtime 惰性只读探测 store 等依赖；
    G0：本函数不接收也不反查 FastAPI app 实例）。
    """
    from app.mcp import tools as mcp_tools

    mcp_tools.register_all()
    runtime = McpRuntime.from_state(state)
    server: Server = Server(MCP_SERVER_NAME)

    async def _list_tools_handler(req: Any) -> "mcp_types.ServerResult":
        """tools/list 处理器（手动注册，见下方赋值处说明）。

        真实请求（req 非 None）：发现门禁链 全局开关 → principal 认证 →
        运行时就绪 → 能力过滤；门禁失败抛 ``McpError``（JSON-RPC 错误面携带
        稳定字符串码）。

        缓存刷新（req 为 None）：SDK 的 ``_get_cached_tool_definition`` 会在
        tools/call 处理中以此形式调用本处理器刷新工具定义缓存——该缓存仅是
        输入/输出 schema 验证元数据，不构成授权面；此处不做认证/就绪门禁，
        执行门禁由 tools/call 路径独立强制，两者互不旁路。
        """
        try:
            snapshot = await runtime.settings_snapshot_async()
            if req is not None:
                if not snapshot.effective_enabled:
                    raise McpToolError(McpErrorCode.SERVICE_DISABLED)
                await _authenticate_caller(server, runtime)
                runtime.require_ready()
                logger.info(
                    "MCP tools/list revision=%s enabled=%s",
                    snapshot.revision,
                    snapshot.effective_enabled,  # §4.5 允许面：revision/开关态
                )
            definitions = catalog.enabled_tool_definitions(snapshot)
            return mcp_types.ServerResult(
                mcp_types.ListToolsResult(
                    tools=[
                        mcp_types.Tool(name=d.name, description=d.description, inputSchema=d.input_schema)
                        for d in definitions
                    ]
                )
            )
        except McpToolError as err:
            raise McpError(_jsonrpc_mcp_error(err)) from err
        except Exception:
            logger.exception("MCP tools/list 意外异常")
            raise McpError(_jsonrpc_mcp_error(McpToolError(McpErrorCode.INTERNAL_ERROR))) from None

    # 不用 @server.list_tools() 装饰器注册：缓存刷新以 handler(None) 形式进入，
    # 装饰器包装层无法与真实请求区分；且包装层异常路径会把 str(e) 渲染进
    # 响应文本（free_text 泄漏面），手动注册可完全控制两条路径。
    server.request_handlers[mcp_types.ListToolsRequest] = _list_tools_handler

    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: Dict[str, Any]) -> mcp_types.CallToolResult:
        """执行门禁：全局 → 能力 → 认证 → 就绪 → 入参校验 → dispatch → 脱敏出口。

        自捕获一切异常（SDK 装饰器会把未捕获异常以 str(e) 外泄——见模块注释）。
        """
        try:
            snapshot = await runtime.settings_snapshot_async()
            if not snapshot.effective_enabled:
                raise McpToolError(McpErrorCode.SERVICE_DISABLED)
            spec = catalog.resolve_callable_tool(name, snapshot)
            principal = await _authenticate_caller(server, runtime)
            runtime.require_ready()
            normalized = catalog.validate_arguments(spec.tool_name, arguments)
            handler = catalog.TOOL_HANDLERS.get(spec.tool_name)
            if handler is None:
                # 注册表未覆盖（W3 分批接入中的空档）：能力开启但无实现
                # 属部署/配置超前，按 INTERNAL_ERROR 固定文案拒绝
                raise McpToolError(McpErrorCode.INTERNAL_ERROR)
            call_context = catalog.ToolCallContext(
                audit=_audit_context_from_transport_request(_resolve_transport_request(server))
            )
            payload = await handler(spec, principal, normalized, runtime, call_context)
            final = finalize_tool_output(spec.tool_name, payload)
            logger.info(
                "MCP tools/call ok tool=%s principal=%s revision=%s",
                spec.tool_name,
                principal.user_id,
                snapshot.revision,  # §4.5 允许面：capability/principal/revision/结果码
            )
            return _success_call_result(final)
        except McpToolError as err:
            return _error_call_result(err)
        except Exception:
            logger.exception("MCP tools/call 意外异常 tool=%s", name)
            return _error_call_result(McpToolError(McpErrorCode.INTERNAL_ERROR))

    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,  # stateless 模式无事件重放
        json_response=True,  # application/json 响应（探针 C4 验证形态）
        stateless=True,  # 官方 SDK 参数名（fastmcp 侧为 stateless_http，§10.4）
    )

    async def _handle_mcp(scope: Any, receive: Any, send: Any) -> None:
        await session_manager.handle_request(scope, receive, send)

    async def _sub_lifespan(app: Any) -> Any:
        async with session_manager.run():
            yield

    sub_asgi = Starlette(
        routes=[
            Mount("/", app=_handle_mcp),
        ],
        lifespan=_sub_lifespan,
    )

    return McpServerBundle(
        runtime=runtime,
        server=server,
        session_manager=session_manager,
        sub_asgi=sub_asgi,
    )
