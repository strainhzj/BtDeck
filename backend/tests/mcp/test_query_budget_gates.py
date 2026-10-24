# -*- coding: utf-8 -*-
"""MCP-G6 查询与响应预算门禁（feature mcp-service-capabilities-2026-08-28 W4）。

覆盖计划 §7"查询"行：0/1/200/201 pageSize 边界、1 MiB 响应边界（整体失败
不截断）、正则预算超限的稳定失败（fail-closed 固定文案，无 pattern/超时文本
泄漏）、软删除排除语义的 MCP 面锚定。依赖 mcp SDK，缺装自动 skip。
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
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import utils as auth_utils  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.mcp.server import create_mcp_server_bundle  # noqa: E402
from app.services.mcp_settings_service import McpRuntimeSettings  # noqa: E402
from app.torrents.audit_models import TorrentAuditLog  # noqa: E402
from app.torrents.models import TorrentInfo, TrackerInfo  # noqa: E402

TEST_SECRET = "test-secret-key-for-mcp-budget"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-budget"
RPC_HEADERS = {"Accept": "application/json, text/event-stream"}
LONG_NAME = "N" * 6144  # 单行 ~6KB：200 行 × 6KB ≈ 1.2MiB > 1MiB 预算


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


class _BudgetStack:
    """预算测试栈：同步域库（可配行数）+ 异步审计库 + /mcp 挂载。"""

    def __init__(self) -> None:
        self.snapshot: Optional[McpRuntimeSettings] = None
        self.bundle: Any = None
        self.app: Any = None

    @classmethod
    async def create(
        cls, on: list, rows: int = 0, soft_deleted_extra: bool = False, long_names: bool = False
    ) -> "_BudgetStack":
        stack = cls()
        stack.sync_engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(bind=stack.sync_engine, tables=[t.__table__ for t in (User, TorrentInfo, TrackerInfo)])
        stack.sync_factory = sessionmaker(bind=stack.sync_engine)

        stack.async_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        async with stack.async_engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[TorrentAuditLog.__table__]))
        stack.async_factory = async_sessionmaker(bind=stack.async_engine, class_=AsyncSession, expire_on_commit=False)

        db = stack.sync_factory()
        db.add(User(username="admin", password="x", is_active=True, must_change_password=False))
        for idx in range(rows):
            db.add(
                TorrentInfo(
                    f"i-{idx}",
                    "1",
                    "qbt",
                    str(idx),
                    f"{idx:040d}",
                    LONG_NAME if long_names else f"ubuntu-{idx}",
                    r"C:\x",
                    1000,
                    "seeding",
                    100.0,
                    None,
                    datetime(2026, 9, 8, 12, 0, 0),
                    None,
                    1.0,
                    None,
                    "",
                    "",
                    None,
                    True,
                    datetime(2026, 9, 8, 12, 0, 0),
                    "admin",
                    datetime(2026, 9, 8, 12, 0, 0),
                    "admin",
                    0,
                )
            )
        if soft_deleted_extra:
            db.add(
                TorrentInfo(
                    "i-soft",
                    "1",
                    "qbt",
                    "99",
                    "f" * 40,
                    "ubuntu-soft-deleted",
                    r"C:\x",
                    1000,
                    "seeding",
                    100.0,
                    None,
                    datetime(2026, 9, 8, 12, 0, 0),
                    None,
                    1.0,
                    None,
                    "",
                    "",
                    None,
                    True,
                    datetime(2026, 9, 8, 12, 0, 0),
                    "admin",
                    datetime(2026, 9, 8, 12, 0, 0),
                    "admin",
                    1,  # 软删除：MCP 查询面必须排除
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
        stack.bundle = create_mcp_server_bundle(None)
        stack.bundle.runtime.settings_provider = lambda: stack.snapshot
        stack.bundle.runtime.session_factory = stack.sync_factory
        stack.bundle.runtime.async_session_factory = stack.async_factory
        stack.bundle.runtime.mark_ready()

        stack.app = FastAPI()
        stack.app.mount("/mcp", stack.bundle.sub_asgi)
        return stack

    async def close(self) -> None:
        self.sync_engine.dispose()
        await self.async_engine.dispose()


@contextlib.asynccontextmanager
async def _stack_client(stack: _BudgetStack):
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
                        "clientInfo": {"name": "btdeck-budget", "version": "0"},
                    },
                },
                headers=RPC_HEADERS,
            )
            assert resp.status_code == 200
            await client.post(
                "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=RPC_HEADERS
            )
            yield client


async def _search(client: Any, page_size: Any, name_value: str = "N") -> Dict[str, Any]:
    resp = await client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 7,
            "params": {
                "name": "torrent_advanced_search",
                "arguments": {
                    "conditions": {
                        "condition_groups": [
                            {
                                "logic": "AND",
                                "conditions": [{"field": "name", "operator": "contains", "value": name_value}],
                            }
                        ]
                    },
                    "page": 1,
                    "page_size": page_size,
                },
            },
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


class TestPageSizeBoundaries:
    async def test_boundary_200_ok_and_201_rejected(self, auth_utils_patch):
        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=250)
        try:
            async with _stack_client(stack) as client:
                ok = _payload(await _search(client, 200))
                assert len(ok["items"]) == 200  # 200 边界含端
                assert ok["page_size"] == 200

                over = await _search(client, 201)
                assert _error_code(over) == "PAGE_SIZE_EXCEEDED"
        finally:
            await stack.close()

    async def test_zero_page_size_invalid_argument(self, auth_utils_patch):
        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=1)
        try:
            async with _stack_client(stack) as client:
                resp = await _search(client, 0)
                assert _error_code(resp) == "INVALID_ARGUMENT"
        finally:
            await stack.close()

    async def test_single_item_page(self, auth_utils_patch):
        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=3)
        try:
            async with _stack_client(stack) as client:
                data = _payload(await _search(client, 1, name_value="ubuntu"))
                assert len(data["items"]) == 1
                assert data["total"] == 3
        finally:
            await stack.close()


class TestResponseBudget:
    async def test_oversize_result_rejected_whole(self, auth_utils_patch):
        """200 行 × 6KB 名称 ≈ 1.2MiB > 1MiB：整体失败 RESULT_TOO_LARGE，不截断。"""
        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=200, long_names=True)
        try:
            async with _stack_client(stack) as client:
                resp = await _search(client, 200)
                assert _error_code(resp) == "RESULT_TOO_LARGE"
                result = resp["result"]
                assert result.get("isError") is True
                # 无部分数据泄漏（不截断放行）
                assert not (result.get("structuredContent") or {}).get("items")
        finally:
            await stack.close()

    async def test_under_budget_result_passes(self, auth_utils_patch):
        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=200, long_names=True)
        try:
            async with _stack_client(stack) as client:
                # 20 行 × 6KB ≈ 120KiB：预算内正常返回
                data = _payload(await _search(client, 20))
                assert len(data["items"]) == 20
        finally:
            await stack.close()


class TestRegexBudgetAndSoftDelete:
    async def test_regex_timeout_fail_closed_fixed_message(self, auth_utils_patch):
        """正则预算超限（service 抛 RegexSearchTimeout）→ 稳定失败固定文案，
        无 pattern/超时文本泄漏（§4.6 fail-closed）。"""
        from app.services.sqlite_search_runtime import RegexSearchTimeout

        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=1)
        try:
            async with _stack_client(stack) as client:
                with patch(
                    "app.services.advanced_search.AdvancedSearchService.search_torrents",
                    side_effect=RegexSearchTimeout("catastrophic pattern (a+)+$ leaked-text"),
                ):
                    resp = await client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "id": 8,
                            "params": {
                                "name": "torrent_advanced_search",
                                "arguments": {
                                    "conditions": {
                                        "condition_groups": [
                                            {
                                                "logic": "AND",
                                                "conditions": [
                                                    {
                                                        "field": "name",
                                                        "operator": "regex",
                                                        "value": {"pattern": "(a+)+$"},
                                                    }
                                                ],
                                            }
                                        ]
                                    },
                                    "page": 1,
                                    "page_size": 20,
                                },
                            },
                        },
                        headers=RPC_HEADERS,
                    )
                    assert resp.status_code == 200
                    payload = resp.json()
                    result = payload["result"]
                    assert result.get("isError") is True
                    error = (result.get("structuredContent") or {}).get("error") or {}
                    assert error.get("code") == "INTERNAL_ERROR"
                    assert "leaked-text" not in str(payload)
                    assert "(a+)+" not in str(payload)
        finally:
            await stack.close()

    async def test_soft_deleted_excluded(self, auth_utils_patch):
        """软删除行（dr=1）不出现在 MCP 查询面（与 service 同语义，§4.6）。"""
        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=2, soft_deleted_extra=True)
        try:
            async with _stack_client(stack) as client:
                data = _payload(await _search(client, 20, name_value="ubuntu"))
                names = [item["name"] for item in data["items"]]
                assert data["total"] == 2
                assert "ubuntu-soft-deleted" not in names
        finally:
            await stack.close()


class TestAsyncIoContainment:
    async def test_slow_query_does_not_block_list(self, auth_utils_patch):
        """慢查询在工作线程执行：进行中的 tools/call 不阻塞同连接 tools/list。"""
        stack = await _BudgetStack.create(on=["torrent.advanced_search"], rows=1)
        try:
            async with _stack_client(stack) as client:

                def blocking_search(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                    import time

                    time.sleep(0.4)  # 工作线程内的慢查询（to_thread 执行面）
                    return {"status": "success", "data": [], "total": 0, "page": 1, "limit": 20}

                async def slow_search():
                    with patch(
                        "app.services.advanced_search.AdvancedSearchService.search_torrents",
                        side_effect=blocking_search,
                    ):
                        return await _search(client, 20)

                task = asyncio.create_task(slow_search())
                await asyncio.sleep(0.05)
                listing = await client.post(
                    "/mcp/", json={"jsonrpc": "2.0", "method": "tools/list", "id": 9}, headers=RPC_HEADERS
                )
                assert listing.status_code == 200
                resp = await task
                assert _error_code(resp) is None
        finally:
            await stack.close()
