# -*- coding: utf-8 -*-
"""MCP 双重发现/执行门禁与三重调用链回归（feature ...W2，G1/G2/G9）。

两层覆盖：

- **单元层（无 SDK）**：catalog 过滤/复核/入参校验 + runtime 就绪语义 +
  fail-closed 配置快照——静态门禁环境（无 mcp 包）必须可全量运行；
- **线上层（需 mcp SDK，缺装自动 skip）**：真实 stateless streamable HTTP
  走 JSON-RPC 握手（initialize → notifications/initialized → tools/list /
  tools/call，复用 W0 探针 C4 序列），验证计划 §4.1 图的三重门禁顺序
  （全局 → 能力 → 认证）、缓存直调拒绝、revision 热更新无重启、
  关闭中稳定拒绝与 307 端点口径。
"""

import contextlib
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import utils as auth_utils
from app.auth.models import User
from app.database import Base
from app.mcp.contracts import CAPABILITY_CODES, CAPABILITY_CATALOG
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp import catalog, runtime as mcp_runtime_module
from app.mcp.runtime import McpRuntime
from app.services.mcp_settings_service import McpRuntimeSettings

TEST_SECRET = "test-secret-key-for-mcp-gates"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-gates"
MCP_PROTOCOL_VERSION = "2025-06-18"


def _snapshot(enabled: bool = False, on: Optional[List[str]] = None, revision: int = 0) -> McpRuntimeSettings:
    on = on or []
    return McpRuntimeSettings(
        enabled=enabled,
        capabilities={code: code in on for code in CAPABILITY_CODES},
        revision=revision,
        force_disabled=False,
    )


# ==============================================================================
# 单元层：catalog 门禁与入参校验（无 SDK 依赖）
# ==============================================================================


class TestEnabledToolDefinitions:
    def test_all_disabled_empty(self):
        assert catalog.enabled_tool_definitions(_snapshot(enabled=False)) == []
        assert catalog.enabled_tool_definitions(_snapshot(enabled=True, on=[])) == []

    def test_global_off_ignores_capabilities(self):
        # 全局关 + 能力开 = 不发现（effective_enabled 门禁，G1）
        assert catalog.enabled_tool_definitions(_snapshot(enabled=False, on=["dashboard.read"])) == []

    def test_single_capability_listed(self):
        defs = catalog.enabled_tool_definitions(_snapshot(enabled=True, on=["dashboard.read"]))
        assert [d.name for d in defs] == ["dashboard_get"]
        tool = defs[0]
        assert tool.input_schema["type"] == "object"
        assert tool.input_schema.get("additionalProperties") is False
        assert "风险分级" in tool.description

    def test_definition_matches_catalog_contract(self):
        defs = catalog.enabled_tool_definitions(_snapshot(enabled=True, on=["torrent.advanced_search"]))
        schema = defs[0].input_schema
        assert set(schema["properties"]) == {"conditions", "page", "page_size"}
        assert schema["required"] == ["conditions"]

    def test_definition_order_follows_catalog(self):
        defs = catalog.enabled_tool_definitions(_snapshot(enabled=True, on=list(CAPABILITY_CODES)))
        expected = [spec.tool_name for spec in CAPABILITY_CATALOG]
        assert [d.name for d in defs] == expected


class TestResolveCallableTool:
    def test_unknown_name_capability_disabled(self):
        with pytest.raises(McpToolError) as exc:
            catalog.resolve_callable_tool("no_such_tool", _snapshot(enabled=True))
        assert exc.value.code is McpErrorCode.CAPABILITY_DISABLED

    def test_alias_or_old_name_rejected(self):
        # 目录外别名（即使语义相近）不可绕过（§4.3-3）
        with pytest.raises(McpToolError) as exc:
            catalog.resolve_callable_tool("torrent_search", _snapshot(enabled=True, on=list(CAPABILITY_CODES)))
        assert exc.value.code is McpErrorCode.CAPABILITY_DISABLED

    def test_disabled_capability_rejected(self):
        # 模拟缓存旧定义直调：能力未启用即拒（G2 执行门禁）
        snapshot = _snapshot(enabled=True, on=["dashboard.read"])
        with pytest.raises(McpToolError) as exc:
            catalog.resolve_callable_tool("torrent_advanced_search", snapshot)
        assert exc.value.code is McpErrorCode.CAPABILITY_DISABLED

    def test_global_off_rejected(self):
        snapshot = _snapshot(enabled=False, on=["dashboard.read"])
        with pytest.raises(McpToolError) as exc:
            catalog.resolve_callable_tool("dashboard_get", snapshot)
        assert exc.value.code is McpErrorCode.CAPABILITY_DISABLED

    def test_enabled_returns_spec(self):
        spec = catalog.resolve_callable_tool("dashboard_get", _snapshot(enabled=True, on=["dashboard.read"]))
        assert spec.code == "dashboard.read"


class TestValidateArguments:
    def test_forbidden_identity_arguments(self):
        for field in ("user_id", "operator", "username"):
            with pytest.raises(McpToolError) as exc:
                catalog.validate_arguments("torrent_advanced_search", {"conditions": {}, field: 1})
            assert exc.value.code is McpErrorCode.FORBIDDEN_ARGUMENT

    def test_unknown_argument_rejected(self):
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("torrent_advanced_search", {"conditions": {}, "surprise": 1})
        assert exc.value.code is McpErrorCode.INVALID_ARGUMENT

    def test_missing_required_rejected(self):
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("torrent_mark_pending_delete", {"info_ids": [1]})
        assert exc.value.code is McpErrorCode.INVALID_ARGUMENT

    def test_wrong_type_rejected(self):
        with pytest.raises(McpToolError):
            catalog.validate_arguments("torrent_advanced_search", {"conditions": "not-an-object"})
        with pytest.raises(McpToolError):
            catalog.validate_arguments("torrent_advanced_search", {"conditions": {}, "page_size": "20"})
        with pytest.raises(McpToolError):
            # bool 不是 integer（JSON 类型语义）
            catalog.validate_arguments("torrent_advanced_search", {"conditions": {}, "page_size": True})

    def test_page_size_budget(self):
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("torrent_advanced_search", {"conditions": {}, "page_size": 201})
        assert exc.value.code is McpErrorCode.PAGE_SIZE_EXCEEDED
        normalized = catalog.validate_arguments("torrent_advanced_search", {"conditions": {}, "page_size": 200})
        assert normalized["page_size"] == 200

    def test_item_limit_budget(self):
        ids = list(range(101))
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments(
                "torrent_mark_pending_delete", {"info_ids": ids, "confirm": True, "idempotency_key": "k"}
            )
        assert exc.value.code is McpErrorCode.ITEM_LIMIT_EXCEEDED
        ok = catalog.validate_arguments(
            "torrent_mark_pending_delete", {"info_ids": ids[:100], "confirm": True, "idempotency_key": "k"}
        )
        assert len(ok["info_ids"]) == 100

    def test_none_arguments_for_fieldless_tool(self):
        assert catalog.validate_arguments("dashboard_get", None) == {}

    def test_error_messages_are_fixed(self):
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("torrent_advanced_search", {"conditions": {}, "user_id": 7})
        assert exc.value.message == "操作者身份只能来自认证主体，禁止通过参数指定。"


class TestRuntimeReadiness:
    def _runtime(self, state: Any = None) -> McpRuntime:
        return McpRuntime(state=state, settings_provider=lambda: _snapshot())

    def test_not_ready_rejected(self):
        rt = self._runtime()
        with pytest.raises(McpToolError) as exc:
            rt.require_ready()
        assert exc.value.code is McpErrorCode.RUNTIME_NOT_READY

    def test_ready_then_closed_rejected(self):
        rt = self._runtime()
        rt.mark_ready()
        rt.require_ready()  # 不抛
        rt.mark_closed()
        with pytest.raises(McpToolError):
            rt.require_ready()

    def test_require_store_without_store_rejected(self):
        rt = self._runtime(state=SimpleState())
        rt.mark_ready()
        with pytest.raises(McpToolError) as exc:
            rt.require_store()
        assert exc.value.code is McpErrorCode.RUNTIME_NOT_READY

    def test_require_store_returns_cached_store(self):
        sentinel = object()
        rt = self._runtime(state=SimpleState(store=sentinel))
        rt.mark_ready()
        assert rt.require_store() is sentinel

    def test_settings_snapshot_provider_crash_fail_closed(self):
        def _crash():
            raise RuntimeError("db exploded")

        rt = McpRuntime(settings_provider=_crash)
        snapshot = rt.settings_snapshot()
        assert snapshot.effective_enabled is False
        assert not any(snapshot.capabilities.values())

    async def test_settings_snapshot_async_passthrough(self):
        expected = _snapshot(enabled=True, on=["dashboard.read"], revision=3)
        rt = McpRuntime(settings_provider=lambda: expected)
        assert (await rt.settings_snapshot_async()) is expected

    def test_context_lazy_semantics(self):
        # torrent_stats 三态语义：ABSENT 哨兵不因 runtime 构造而漂移
        rt = self._runtime(state=SimpleState())
        ctx = rt.context
        assert ctx.store is None
        assert ctx.torrent_stats is mcp_runtime_module.TORRENT_STATS_ABSENT
        rt2 = McpRuntime(state=SimpleState(store=1, torrent_stats={"active": 2}, start_time=3.0))
        ctx2 = rt2.context
        assert ctx2.store == 1 and ctx2.torrent_stats == {"active": 2} and ctx2.start_time == 3.0


class SimpleState:
    """app.state 的最小替身（store/torrent_stats/start_time 属性面）。"""

    def __init__(self, store: Any = None, torrent_stats: Any = ..., start_time: Any = None):
        if store is not None:
            self.store = store
        if torrent_stats is not ...:
            self.torrent_stats = torrent_stats
        if start_time is not None:
            self.start_time = start_time


# ==============================================================================
# 线上层：真实 stateless streamable HTTP（需 mcp SDK；缺装自动 skip）
# ==============================================================================

httpx = pytest.importorskip("httpx")
pytest.importorskip("mcp.server.streamable_http_manager", reason="mcp SDK 未安装")

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.mcp.server import create_mcp_server_bundle  # noqa: E402

RPC_HEADERS = {"Accept": "application/json, text/event-stream"}


def _make_token(username: str = "admin", user_id: int = 1) -> str:
    return auth_utils.create_access_token(
        {"sub": username, "user_id": str(user_id), "verify_secret": TEST_LOGIN_SECRET}
    )


class _GateStack:
    """线上层测试栈：临时文件库 + 可变配置快照 + 挂载 /mcp 的 FastAPI 应用。

    用临时文件库而非 StaticPool 内存库：并发认证路径会在多个 to_thread 工作线程
    各开 session，StaticPool 的单连接被并发共享是未定义行为（时序相关的
    INTERNAL_ERROR 假阳性）；文件库每 session 独立连接，与生产行为一致。
    """

    def __init__(self, snapshot: McpRuntimeSettings, ready: bool = True):
        import tempfile
        import uuid

        from pathlib import Path

        db_dir = Path(tempfile.gettempdir()) / f"btdeck-mcp-test-{uuid.uuid4().hex}"
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_dir / "gate.sqlite3"
        engine = create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        Base.metadata.create_all(bind=engine, tables=[User.__table__])
        self.engine = engine
        self.session_factory = sessionmaker(bind=engine)
        db = self.session_factory()
        db.add(User(username="admin", password="x", is_active=True, must_change_password=False))
        db.add(User(username="inactive-user", password="x", is_active=False, must_change_password=False))
        db.add(User(username="resetting-user", password="x", is_active=True, must_change_password=True))
        db.commit()
        db.close()

        self.snapshot = snapshot
        state = SimpleState(store=object())
        self.bundle = create_mcp_server_bundle(state)
        # 注入测试配置供给器与会话工厂（绕开生产 SessionLocal/DB 读取）
        self.bundle.runtime.settings_provider = lambda: self.snapshot
        self.bundle.runtime.session_factory = self.session_factory
        if ready:
            self.bundle.runtime.mark_ready()

        self.app = FastAPI()
        self.app.mount("/mcp", self.bundle.sub_asgi)

    def set_snapshot(self, snapshot: McpRuntimeSettings) -> None:
        """模拟 PUT 落库后的原子替换：下一次 tools/list 立即生效。"""
        self.snapshot = snapshot

    def close(self) -> None:
        self.engine.dispose()
        import shutil

        shutil.rmtree(self._db_path.parent, ignore_errors=True)


@pytest.fixture
def auth_utils_patch():
    mock_settings = MagicMock()
    mock_settings.SECRET_KEY = TEST_SECRET
    mock_settings.ALGORITHM = "HS256"
    mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    with (
        patch("app.auth.utils.settings", mock_settings),
        patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET),
    ):
        yield


@contextlib.asynccontextmanager
async def _mcp_lifespan(stack: _GateStack) -> Any:
    """手动进入 MCP 子应用 lifespan（镜像 lifecycle.py 的父 lifespan 接线）。"""
    async with stack.bundle.sub_asgi.router.lifespan_context(stack.bundle.sub_asgi):
        yield


@contextlib.asynccontextmanager
async def _mcp_client(stack: _GateStack, headers: Optional[Dict[str, str]] = None) -> Any:
    async with _mcp_lifespan(stack):
        transport = ASGITransport(app=stack.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers=headers or {}
        ) as client:
            yield client


async def _rpc(client: Any, method: str, params: Optional[Dict[str, Any]], request_id: int) -> Dict[str, Any]:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": request_id}
    if params is not None:
        body["params"] = params
    resp = await client.post("/mcp/", json=body, headers=RPC_HEADERS)
    assert resp.status_code == 200, f"{method} HTTP {resp.status_code}: {resp.text[:300]}"
    payload = resp.json()
    return payload


async def _handshake(client: Any) -> None:
    """initialize → notifications/initialized（复用 W0 探针 C4 序列）。"""
    init = await _rpc(
        client,
        "initialize",
        {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "btdeck-w2-test", "version": "0"},
        },
        1,
    )
    assert "error" not in init, f"initialize 失败: {init['error']}"
    resp = await client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=RPC_HEADERS,
    )
    assert resp.status_code in (200, 202)


async def _tools_list(client: Any) -> Dict[str, Any]:
    return await _rpc(client, "tools/list", {}, 2)


async def _tools_call(client: Any, name: str, arguments: Dict[str, Any], request_id: int = 3) -> Dict[str, Any]:
    return await _rpc(client, "tools/call", {"name": name, "arguments": arguments}, request_id)


def _jsonrpc_error_code(payload: Dict[str, Any]) -> Optional[str]:
    """JSON-RPC 错误载荷中的稳定字符串码（tools/list 错误面）。"""
    error = payload.get("error")
    if not error:
        return None
    data = error.get("data") or {}
    return data.get("error_code")


def _call_error_code(payload: Dict[str, Any]) -> Optional[str]:
    """tools/call 的 isError 结果中的稳定字符串码。"""
    result = payload.get("result", {})
    if not result.get("isError"):
        return None
    structured = result.get("structuredContent") or {}
    return (structured.get("error") or {}).get("code")


class TestWireGlobalGate:
    async def test_service_disabled_rejects_list_and_call(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=False))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                listing = await _tools_list(client)
                assert _jsonrpc_error_code(listing) == "SERVICE_DISABLED"
                call = await _tools_call(client, "dashboard_get", {})
                assert _call_error_code(call) == "SERVICE_DISABLED"
        finally:
            stack.close()

    async def test_enabled_without_capabilities_lists_empty(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=True, on=[]))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                listing = await _tools_list(client)
                assert listing["result"]["tools"] == []
        finally:
            stack.close()

    async def test_mount_before_spa_fallback_not_swallowed(self, auth_utils_patch):
        """挂载点存活证明：/mcp/ 是 MCP 端点而非 SPA fallback（G0 运行时面）。"""
        stack = _GateStack(_snapshot(enabled=False))
        try:
            async with _mcp_client(stack) as client:
                resp = await client.post(
                    "/mcp/",
                    json={"jsonrpc": "2.0", "method": "ping", "id": 9},
                    headers=RPC_HEADERS,
                )
                assert resp.status_code == 200
                assert "text/html" not in resp.headers.get("content-type", "")
        finally:
            stack.close()


class TestWireCapabilityGate:
    async def test_list_shows_only_enabled_capabilities(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read", "cron.trigger"]))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                listing = await _tools_list(client)
                names = [t["name"] for t in listing["result"]["tools"]]
                assert names == ["dashboard_get", "cron_task_trigger"]
        finally:
            stack.close()

    async def test_cached_direct_call_of_disabled_capability_rejected(self, auth_utils_patch):
        """G2：客户端缓存旧工具定义直调未启用能力 → CAPABILITY_DISABLED。"""
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"]))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                call = await _tools_call(client, "torrent_advanced_search", {"conditions": {}})
                assert _call_error_code(call) == "CAPABILITY_DISABLED"
                # 别名/旧名/不存在名字同码拒绝（防目录枚举）
                alias = await _tools_call(client, "torrent_search", {})
                assert _call_error_code(alias) == "CAPABILITY_DISABLED"
        finally:
            stack.close()

    async def test_revision_hot_update_without_restart(self, auth_utils_patch):
        """G2 热更新：配置原子替换后，下一次 tools/list 立即反映新 revision。"""
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"], revision=1))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                first = await _tools_list(client)
                assert [t["name"] for t in first["result"]["tools"]] == ["dashboard_get"]

                stack.set_snapshot(
                    _snapshot(enabled=True, on=["dashboard.read", "torrent.advanced_search"], revision=2)
                )
                second = await _tools_list(client)
                assert sorted(t["name"] for t in second["result"]["tools"]) == [
                    "dashboard_get",
                    "torrent_advanced_search",
                ]

                # 全局关：立即不可发现
                stack.set_snapshot(_snapshot(enabled=False, revision=3))
                third = await _tools_list(client)
                assert _jsonrpc_error_code(third) == "SERVICE_DISABLED"
        finally:
            stack.close()

    async def test_concurrent_snapshot_switch_never_tears(self, auth_utils_patch):
        """G2 并发切换：快照原子替换下，并发 tools/list 只见到完整旧态或完整新态。

        断言不撕裂（不同能力子集混排）且不 5xx/协议错误；关闭竞态下要么
        完整列表要么 SERVICE_DISABLED。
        """
        import asyncio

        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"], revision=1))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                valid_states = (
                    ["dashboard_get"],  # rev1
                    ["dashboard_get", "torrent_advanced_search"],  # rev2（顺序按目录）
                    ["torrent_advanced_search"],  # rev3
                )

                async def _flipper():
                    for rev, on in (
                        (2, ["dashboard.read", "torrent.advanced_search"]),
                        (3, ["torrent.advanced_search"]),
                    ):
                        await asyncio.sleep(0.01)
                        stack.set_snapshot(_snapshot(enabled=True, on=on, revision=rev))

                async def _lister(results: list):
                    for _ in range(24):
                        payload = await _tools_list(client)
                        error_code = _jsonrpc_error_code(payload)
                        names = (
                            sorted(t["name"] for t in payload.get("result", {}).get("tools", []))
                            if error_code is None
                            else error_code
                        )
                        results.append(names)

                results_a: list = []
                results_b: list = []
                await asyncio.gather(_flipper(), _lister(results_a), _lister(results_b))
                merged = results_a + results_b
                assert merged, "并发请求全部失败"
                for observed in merged:
                    assert observed in valid_states, f"撕裂/非法观测态: {observed!r}"
        finally:
            stack.close()


class TestWireAuthGate:
    async def test_missing_token_rejected(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"]))
        try:
            async with _mcp_client(stack) as client:
                await _handshake(client)
                listing = await _tools_list(client)
                assert _jsonrpc_error_code(listing) == "AUTH_REQUIRED"
                call = await _tools_call(client, "dashboard_get", {})
                assert _call_error_code(call) == "AUTH_REQUIRED"
        finally:
            stack.close()

    async def test_invalid_token_rejected(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"]))
        try:
            async with _mcp_client(stack, headers={"Authorization": "Bearer not-a-jwt"}) as client:
                await _handshake(client)
                call = await _tools_call(client, "dashboard_get", {})
                assert _call_error_code(call) == "AUTH_TOKEN_INVALID"
        finally:
            stack.close()

    async def test_user_status_rejected_over_wire(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"]))
        try:
            async with _mcp_client(stack) as client:
                await _handshake(client)
                inactive = await _tools_call_authed(client, _make_token("inactive-user", 2), "dashboard_get", {})
                assert inactive == "AUTH_USER_INACTIVE"
                resetting = await _tools_call_authed(client, _make_token("resetting-user", 3), "dashboard_get", {})
                assert resetting == "PASSWORD_CHANGE_REQUIRED"
                ghost = await _tools_call_authed(client, _make_token("ghost-user", 9), "dashboard_get", {})
                assert ghost == "AUTH_USER_NOT_FOUND"
        finally:
            stack.close()


async def _tools_call_authed(client: Any, token: str, name: str, arguments: Dict[str, Any]) -> Optional[str]:
    """带单次 token 头的 tools/call，返回稳定错误码。"""
    body = {"jsonrpc": "2.0", "method": "tools/call", "id": 77, "params": {"name": name, "arguments": arguments}}
    resp = await client.post("/mcp/", json=body, headers={**RPC_HEADERS, "Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    return _call_error_code(resp.json())


class TestWireInputAndRuntimeGates:
    async def test_forbidden_argument_rejected_before_dispatch(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=True, on=["torrent.advanced_search"]))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                call = await _tools_call(client, "torrent_advanced_search", {"conditions": {}, "user_id": 1})
                assert _call_error_code(call) == "FORBIDDEN_ARGUMENT"
                budget = await _tools_call(client, "torrent_advanced_search", {"conditions": {}, "page_size": 999})
                assert _call_error_code(budget) == "PAGE_SIZE_EXCEEDED"
        finally:
            stack.close()

    async def test_enabled_capability_without_handler_is_internal_error(self, auth_utils_patch):
        """分批接入空档：能力开启但处理器未注册（如 W3-③ 的添加种子）→ 固定文案 INTERNAL_ERROR。"""
        stack = _GateStack(_snapshot(enabled=True, on=["torrent.add"]))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                call = await _tools_call(
                    client,
                    "torrent_add_file",
                    {"torrent_file_b64": "eA==", "downloader_id": 1, "confirm": True, "idempotency_key": "k"},
                )
                assert _call_error_code(call) == "INTERNAL_ERROR"
                message = call["result"]["structuredContent"]["error"]["message"]
                assert message == "服务内部错误。"
        finally:
            stack.close()

    async def test_runtime_not_ready_stable_rejection(self, auth_utils_patch):
        """G9：未 mark_ready（store/调度器未就绪等价态）→ RUNTIME_NOT_READY。"""
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"]), ready=False)
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                call = await _tools_call(client, "dashboard_get", {})
                assert _call_error_code(call) == "RUNTIME_NOT_READY"
                listing = await _tools_list(client)
                assert _jsonrpc_error_code(listing) == "RUNTIME_NOT_READY"
        finally:
            stack.close()

    async def test_closed_runtime_stable_rejection(self, auth_utils_patch):
        stack = _GateStack(_snapshot(enabled=True, on=["dashboard.read"]))
        try:
            async with _mcp_client(stack, headers={"Authorization": f"Bearer {_make_token()}"}) as client:
                await _handshake(client)
                stack.bundle.runtime.mark_closed()  # 模拟应用关闭中
                call = await _tools_call(client, "dashboard_get", {})
                assert _call_error_code(call) == "RUNTIME_NOT_READY"
        finally:
            stack.close()


class TestWireMountOrder:
    def test_mcp_mounted_before_spa_fallback(self):
        """G0 运行时面：真实 factory 产物中 /mcp 挂载必须先于 SPA catch-all。"""
        from app.factory import app as factory_app

        mcp_index: Optional[int] = None
        spa_index: Optional[int] = None
        for idx, route in enumerate(factory_app.router.routes):
            path = getattr(route, "path", "")
            if path == "/mcp" and mcp_index is None:
                mcp_index = idx
            if path == "/{path:path}" and spa_index is None:
                spa_index = idx
        assert mcp_index is not None, "/mcp 未挂载（factory._mount_mcp_service 漂移或 SDK 缺失）"
        if spa_index is not None:
            assert mcp_index < spa_index, f"/mcp({mcp_index}) 必须早于 SPA fallback({spa_index})"
