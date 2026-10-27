# -*- coding: utf-8 -*-
"""MCP-G9 运行时与关闭语义门禁（feature mcp-service-capabilities-2026-08-28 W4）。

计划 §7"生命周期"行：MCP 先于 store 就绪的稳定拒绝、服务关闭后无新调用、
在途写操作一致性收尾（mark_closed 不中断已过执行门禁的写调用，业务与审计
均完整落库）。依赖 mcp SDK，缺装自动 skip。
"""

import asyncio
import contextlib
from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("mcp.server.streamable_http_manager", reason="mcp SDK 未安装")

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import utils as auth_utils  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.mcp.server import create_mcp_server_bundle  # noqa: E402
from app.services.mcp_settings_service import McpRuntimeSettings  # noqa: E402
from app.tasks.cron_models import CronTask  # noqa: E402
from app.torrents.audit_models import TorrentAuditLog  # noqa: E402
from app.torrents.models import TorrentInfo  # noqa: E402

TEST_SECRET = "test-secret-key-for-mcp-lifecycle"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-lifecycle"
RPC_HEADERS = {"Accept": "application/json, text/event-stream"}


def _make_token(username: str = "admin", user_id: int = 1) -> str:
    return auth_utils.create_access_token(
        {"sub": username, "user_id": str(user_id), "verify_secret": TEST_LOGIN_SECRET}
    )


@pytest.fixture
def auth_utils_patch():
    mock = MagicMock()
    mock.SECRET_KEY = TEST_SECRET
    mock.ALGORITHM = "HS256"
    mock.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    with (
        patch("app.auth.utils.settings", mock),
        patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET),
    ):
        yield


class _StateNoStore:
    """就绪但 store 尚未初始化的 app.state 等价态（属性不存在）。"""


class _StateWithStore:
    def __init__(self, store: Any):
        self.store = store


class _LifecycleStack:
    def __init__(self) -> None:
        self.snapshot: Optional[McpRuntimeSettings] = None
        self.bundle: Any = None
        self.app: Any = None

    @classmethod
    async def create(
        cls,
        on: list,
        state: Any = None,
        ready: bool = True,
    ) -> "_LifecycleStack":
        stack = cls()
        stack.sync_engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(
            bind=stack.sync_engine, tables=[User.__table__, TorrentInfo.__table__, CronTask.__table__]
        )
        stack.sync_factory = sessionmaker(bind=stack.sync_engine)

        stack.async_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        async with stack.async_engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=[TorrentAuditLog.__table__, CronTask.__table__])
            )
        stack.async_factory = async_sessionmaker(bind=stack.async_engine, class_=AsyncSession, expire_on_commit=False)

        db = stack.sync_factory()
        db.add(User(username="admin", password="x", is_active=True, must_change_password=False))
        db.add(
            TorrentInfo(
                "i-1",
                "1",
                "qbt",
                "42",
                "b" * 40,
                "lifecycle-torrent",
                r"C:\x",
                1000,
                "seeding",
                100.0,
                None,
                datetime(2026, 9, 8),
                None,
                1.0,
                None,
                "",
                "",
                None,
                True,
                datetime(2026, 9, 8),
                "admin",
                datetime(2026, 9, 8),
                "admin",
                0,
            )
        )
        db.commit()
        db.close()

        stack.snapshot = McpRuntimeSettings(
            enabled=True,
            capabilities={
                code: code in on
                for code in __import__("app.mcp.contracts", fromlist=["CAPABILITY_CODES"]).CAPABILITY_CODES
            },
            revision=1,
        )
        stack.bundle = create_mcp_server_bundle(state)
        stack.bundle.runtime.settings_provider = lambda: stack.snapshot
        stack.bundle.runtime.session_factory = stack.sync_factory
        stack.bundle.runtime.async_session_factory = stack.async_factory
        if ready:
            stack.bundle.runtime.mark_ready()

        stack.app = FastAPI()
        stack.app.mount("/mcp", stack.bundle.sub_asgi)
        return stack

    async def audit_rows(self) -> list:
        adb = self.async_factory()
        try:
            result = await adb.execute(select(TorrentAuditLog))
            return list(result.scalars())
        finally:
            await adb.close()

    async def close(self) -> None:
        self.sync_engine.dispose()
        await self.async_engine.dispose()


@contextlib.asynccontextmanager
async def _stack_client(stack: _LifecycleStack):
    async with stack.bundle.sub_asgi.router.lifespan_context(stack.bundle.sub_asgi):
        transport = ASGITransport(app=stack.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers={"Authorization": f"Bearer {_make_token()}"}
        ) as client:
            resp = await client.post(
                "/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "btdeck-lifecycle", "version": "0"},
                    },
                },
                headers=RPC_HEADERS,
            )
            assert resp.status_code == 200
            await client.post(
                "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=RPC_HEADERS
            )
            yield client


async def _call(client: Any, name: str, arguments: Dict[str, Any], request_id: int = 5) -> Dict[str, Any]:
    resp = await client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": request_id,
            "params": {"name": name, "arguments": arguments},
        },
        headers=RPC_HEADERS,
    )
    assert resp.status_code == 200
    return resp.json()


def _error_code(resp: Dict[str, Any]) -> Optional[str]:
    result = resp.get("result", {})
    if not result.get("isError"):
        return None
    return ((result.get("structuredContent") or {}).get("error") or {}).get("code")


def _payload(resp: Dict[str, Any]) -> Dict[str, Any]:
    result = resp.get("result", {})
    assert result.get("isError") is False, f"预期成功: {result.get('structuredContent')}"
    return result.get("structuredContent") or {}


_MARK_ARGS = {"info_ids": ["i-1"], "confirm": True, "idempotency_key": "life-k"}


class TestReadinessMatrix:
    @pytest.mark.parametrize(
        "tool,args",
        [
            ("dashboard_get", {}),
            ("torrent_mark_pending_delete", _MARK_ARGS),
        ],
    )
    async def test_store_absent_ready_write_tools_rejected(self, auth_utils_patch, tool, args):
        """就绪但 store 缺失（MCP 先于 store 初始化）：需 store 的写工具稳定拒绝；
        dashboard 的空 context 同样不崩溃（三态哨兵零值）；cron 触发不依赖
        store（门禁序 allowlist→ready→任务行），不在此矩阵。"""
        stack = await _LifecycleStack.create(
            on=["dashboard.read", "torrent.mark_pending_delete"], state=_StateNoStore()
        )
        try:
            async with _stack_client(stack) as client:
                resp = await _call(client, tool, args)
                code = _error_code(resp)
                if tool == "dashboard_get":
                    assert code is None  # 只读聚合降级零值，不拒绝
                else:
                    assert code == "RUNTIME_NOT_READY"
        finally:
            await stack.close()

    async def test_not_ready_rejects_read_and_write(self, auth_utils_patch):
        stack = await _LifecycleStack.create(on=["dashboard.read"], state=_StateNoStore(), ready=False)
        try:
            async with _stack_client(stack) as client:
                listing = await client.post(
                    "/mcp/", json={"jsonrpc": "2.0", "method": "tools/list", "id": 2}, headers=RPC_HEADERS
                )
                payload = listing.json()
                assert ((payload.get("error") or {}).get("data") or {}).get("error_code") == "RUNTIME_NOT_READY"
                resp = await _call(client, "dashboard_get", {})
                assert _error_code(resp) == "RUNTIME_NOT_READY"
        finally:
            await stack.close()


class TestShutdownSemantics:
    @pytest.mark.parametrize(
        "tool,args",
        [
            ("dashboard_get", {}),
            ("torrent_mark_pending_delete", _MARK_ARGS),
        ],
    )
    async def test_closed_runtime_rejects_new_calls(self, auth_utils_patch, tool, args):
        stack = await _LifecycleStack.create(
            on=["dashboard.read", "torrent.mark_pending_delete"], state=_StateWithStore(object())
        )
        stack.bundle.runtime.mark_closed()
        try:
            async with _stack_client(stack) as client:
                resp = await _call(client, tool, args)
                assert _error_code(resp) == "RUNTIME_NOT_READY"
        finally:
            await stack.close()

    async def test_inflight_write_completes_after_close(self, auth_utils_patch):
        """在途写操作一致性收尾：已过执行门禁的写调用在 mark_closed 后不被中断，
        业务结果与 MCP_TOOL_CALL 审计完整落地；其后新调用稳定拒绝。"""

        class _SlowService:
            LEVEL4_TAG = "pending_delete"

            def __init__(self, db, store=None, audit_context=None):
                pass

            async def delete_by_level(self, info_id, level, operator="admin", audit_service=None):
                await asyncio.sleep(0.3)  # 模拟下载器往返窗口
                return {"success": True, "db_update_success": True}

        stack = await _LifecycleStack.create(on=["torrent.mark_pending_delete"], state=_StateWithStore(object()))
        try:
            async with _stack_client(stack) as client:
                with patch("app.services.torrent_deletion_by_level.TorrentDeletionByLevelService", _SlowService):
                    inflight = asyncio.create_task(_call(client, "torrent_mark_pending_delete", dict(_MARK_ARGS)))
                    await asyncio.sleep(0.1)  # 请求已过门禁、进入 service 等待
                    stack.bundle.runtime.mark_closed()
                    completed = await inflight

                data = _payload(completed)
                assert data["result"] == "success"
                assert data["downloader_success_count"] == 1

                rejected = await _call(client, "torrent_mark_pending_delete", dict(_MARK_ARGS), request_id=6)
                assert _error_code(rejected) == "RUNTIME_NOT_READY"

            audits = await stack.audit_rows()
            mcp_rows = [a for a in audits if "torrent_mark_pending_delete" in (a.operation_detail or "")]
            assert len(mcp_rows) == 1  # 在途调用审计完整落地（重放被拒不再补行）
            assert mcp_rows[0].operation_result == "success"
        finally:
            await stack.close()
