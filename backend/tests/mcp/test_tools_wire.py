# -*- coding: utf-8 -*-
"""MCP W3-① 只读工具线上 E2E（feature mcp-service-capabilities-2026-08-28）。

真实 stateless streamable HTTP 握手驱动三工具（G4：与 HTTP 同一 service；
G5：响应面零泄漏实证——种子哈希/passkey/绝对路径/原始 tracker URL 全程
不出现在序列化响应中）。依赖 mcp SDK，缺装自动 skip。
"""

import json
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
from app.models.search_template import SearchTemplate  # noqa: E402
from app.services.mcp_settings_service import McpRuntimeSettings  # noqa: E402
from app.tasks.cron_models import CronTask  # noqa: E402
from app.torrents.audit_models import TorrentAuditLog  # noqa: E402
from app.torrents.models import TorrentInfo, TrackerInfo  # noqa: E402

TEST_SECRET = "test-secret-key-for-mcp-tools-wire"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-tools-wire"
RPC_HEADERS = {"Accept": "application/json, text/event-stream"}

HASH_VALUE = "b" * 40
PASSKEY_VALUE = "wirepasskey999"


def _snapshot(on: list) -> McpRuntimeSettings:
    from app.mcp.contracts import CAPABILITY_CODES

    return McpRuntimeSettings(
        enabled=True,
        capabilities={code: code in on for code in CAPABILITY_CODES},
        revision=1,
    )


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


class _ToolStack:
    """线上 E2E 栈：同步域库（种子/模板）+ 异步库（审计/定时任务）+ 挂载 /mcp。

    构造必须走 ``await _ToolStack.create(on)``——asyncio 引擎绑定当前事件循环，
    在测试循环内同步另开 loop 会跨循环失败。
    """

    def __init__(self) -> None:
        self.snapshot: Optional[McpRuntimeSettings] = None
        self.bundle: Any = None
        self.app: Any = None

    @classmethod
    async def create(cls, on: list) -> "_ToolStack":
        stack = cls()
        stack.sync_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            bind=stack.sync_engine,
            tables=[t.__table__ for t in (User, TorrentInfo, TrackerInfo, SearchTemplate)],
        )
        stack.sync_factory = sessionmaker(bind=stack.sync_engine)

        stack.async_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
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
                "i-1",  # info_id（自定义 __init__ 位置参数）
                "1",  # downloader_id
                "qbt",  # downloader_name
                "42",  # torrent_id
                HASH_VALUE,
                "ubuntu-24.04",
                "C:\\Downloads\\iso",
                1.5e9,
                "seeding",
                100.0,
                None,  # torrent_file
                datetime(2026, 9, 8, 12, 0, 0),  # added_date
                None,  # completed_date
                1.0,  # ratio
                None,  # ratio_limit
                "linux",  # tags
                "iso",  # category
                None,  # super_seeding
                True,  # enabled
                datetime(2026, 9, 8, 12, 0, 0),  # create_time
                "admin",  # create_by
                datetime(2026, 9, 8, 12, 0, 0),  # update_time
                "admin",  # update_by
                0,  # dr
            )
        )
        db.add(
            TrackerInfo(
                tracker_id="t-1",
                torrent_info_id="i-1",
                tracker_name="t1",
                tracker_url=f"https://t.example.org:8080/announce?passkey={PASSKEY_VALUE}",
                last_announce_msg="announce ok",
                dr=0,
            )
        )
        db.commit()
        db.close()

        adb = stack.async_factory()
        async with adb.begin():
            adb.add(
                CronTask(
                    task_name="t",
                    task_code="cleanup",
                    task_status=2,
                    task_type=5,
                    executor="",
                    cron_plan="0 0 * * *",
                    dr=0,
                )
            )
        await adb.close()

        stack.snapshot = _snapshot(on)
        stack.bundle = create_mcp_server_bundle(state=None)
        stack.bundle.runtime.settings_provider = lambda: stack.snapshot
        stack.bundle.runtime.session_factory = stack.sync_factory
        stack.bundle.runtime.async_session_factory = stack.async_factory
        stack.bundle.runtime.mark_ready()

        stack.app = FastAPI()
        stack.app.mount("/mcp", stack.bundle.sub_asgi)
        return stack

    async def audit_rows(self) -> list:
        adb = self.async_factory()
        try:
            result = await adb.execute(select(TorrentAuditLog).order_by(TorrentAuditLog.log_id))
            return list(result.scalars())
        finally:
            await adb.close()

    async def close(self) -> None:
        self.sync_engine.dispose()
        await self.async_engine.dispose()


async def _rpc(client: Any, method: str, params: Optional[Dict[str, Any]], request_id: int) -> Dict[str, Any]:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": request_id}
    if params is not None:
        body["params"] = params
    resp = await client.post("/mcp/", json=body, headers=RPC_HEADERS)
    assert resp.status_code == 200, f"{method} HTTP {resp.status_code}: {resp.text[:300]}"
    return resp.json()


import contextlib  # noqa: E402


@contextlib.asynccontextmanager
async def _stack_client(stack: _ToolStack):
    async with stack.bundle.sub_asgi.router.lifespan_context(stack.bundle.sub_asgi):
        transport = ASGITransport(app=stack.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers={"Authorization": f"Bearer {_make_token()}"}
        ) as client:
            await _handshake(client)
            yield client


async def _handshake(client: Any) -> None:
    init = await _rpc(
        client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "btdeck-w3-test", "version": "0"},
        },
        1,
    )
    assert "error" not in init, f"initialize 失败: {init.get('error')}"
    resp = await client.post(
        "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=RPC_HEADERS
    )
    assert resp.status_code in (200, 202)


async def _call(client: Any, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return await _rpc(client, "tools/call", {"name": name, "arguments": arguments}, 99)


def _payload(resp: Dict[str, Any]) -> Dict[str, Any]:
    result = resp.get("result", {})
    assert result.get("isError") is False, f"工具调用失败: {result.get('structuredContent')}"
    return result.get("structuredContent") or {}


def _error(resp: Dict[str, Any]) -> str:
    result = resp.get("result", {})
    assert result.get("isError") is True
    return (result.get("structuredContent") or {}).get("error", {}).get("code")


class TestWireAdvancedSearch:
    async def test_search_returns_sanitized_items(self, auth_utils_patch):
        stack = await _ToolStack.create(on=["torrent.advanced_search"])
        try:
            async with _stack_client(stack) as client:
                resp = await _call(
                    client,
                    "torrent_advanced_search",
                    {"conditions": {"name": "ubuntu"}, "page": 1, "page_size": 20},
                )
                data = _payload(resp)
                assert data["total"] == 1
                item = data["items"][0]
                assert item["info_id"] == "i-1"
                assert item["name"] == "ubuntu-24.04"
                assert item["tracker_domains"] == ["t.example.org"]
                assert item["path_display"] == "iso"

                # G5 零泄漏：整包序列化文本不含哈希/passkey/绝对路径/原始 URL
                raw = json.dumps(resp, ensure_ascii=False)
                assert HASH_VALUE not in raw
                assert PASSKEY_VALUE not in raw
                assert "announce" not in raw
                assert "C:" not in raw and "\\\\" not in raw
                assert "last_announce" not in raw and "announce_msg" not in raw
        finally:
            await stack.close()

    async def test_tracker_domain_condition_matches(self, auth_utils_patch):
        stack = await _ToolStack.create(on=["torrent.advanced_search"])
        try:
            async with _stack_client(stack) as client:
                resp = await _call(
                    client,
                    "torrent_advanced_search",
                    {
                        "conditions": {
                            "condition_groups": [
                                {
                                    "logic": "AND",
                                    "conditions": [
                                        {"field": "tracker_url", "operator": "contains", "value": "t.example.org"}
                                    ],
                                }
                            ]
                        }
                    },
                )
                assert _payload(resp)["total"] == 1
        finally:
            await stack.close()

    async def test_privacy_conditions_rejected_over_wire(self, auth_utils_patch):
        stack = await _ToolStack.create(on=["torrent.advanced_search"])
        try:
            async with _stack_client(stack) as client:
                msg_condition = await _call(
                    client,
                    "torrent_advanced_search",
                    {
                        "conditions": {
                            "condition_groups": [
                                {
                                    "logic": "AND",
                                    "conditions": [{"field": "tracker_msg", "operator": "contains", "value": "x"}],
                                }
                            ]
                        }
                    },
                )
                assert _error(msg_condition) == "INVALID_ARGUMENT"

                url_condition = await _call(
                    client,
                    "torrent_advanced_search",
                    {
                        "conditions": {
                            "condition_groups": [
                                {
                                    "logic": "AND",
                                    "conditions": [
                                        {"field": "tracker_url", "operator": "contains", "value": "https://t.org/a?p=1"}
                                    ],
                                }
                            ]
                        }
                    },
                )
                assert _error(url_condition) == "INVALID_ARGUMENT"
        finally:
            await stack.close()


class TestWireTemplateCreate:
    def _args(self, key: str = "k-1") -> Dict[str, Any]:
        return {
            "name": "tpl-1",
            "conditions": {
                "source": "advanced",
                "condition_groups": [
                    {"logic": "AND", "conditions": [{"field": "name", "operator": "contains", "value": "ubuntu"}]}
                ],
            },
            "confirm": True,
            "idempotency_key": key,
        }

    async def test_create_and_replay_single_row_with_audit(self, auth_utils_patch):
        stack = await _ToolStack.create(on=["search_template.create"])
        try:
            async with _stack_client(stack) as client:
                first = _payload(await _call(client, "advanced_search_template_create", self._args()))
                assert first["created"] is True
                template_id = first["template_id"]
                assert template_id

                replay = _payload(await _call(client, "advanced_search_template_create", self._args()))
                assert replay["template_id"] == template_id

                # 幂等：DB 仅一行
                db = stack.sync_factory()
                rows = db.query(SearchTemplate).all()
                db.close()
                assert len(rows) == 1
                assert rows[0].user_id == "1"
                assert rows[0].is_public == 0

                # 审计：两次调用两条 mcp_tool_call 行（其一 replay=True；log_id 为
                # uuid4 无时间序，按内容断言不依赖行序）
                audits = await stack.audit_rows()
                assert len(audits) == 2
                assert all(a.operation_type == "mcp_tool_call" for a in audits)
                assert all(a.operator == "admin" for a in audits)
                replay_flags = ['"replay":true' in (a.operation_detail or "").replace(" ", "") for a in audits]
                assert replay_flags.count(True) == 1

                # G5：审计 detail 不含 conditions 原文与幂等键原值
                for a in audits:
                    assert "ubuntu" not in (a.operation_detail or "")
                    assert "k-1" not in (a.operation_detail or "")
        finally:
            await stack.close()

    async def test_confirm_false_rejected(self, auth_utils_patch):
        stack = await _ToolStack.create(on=["search_template.create"])
        try:
            async with _stack_client(stack) as client:
                args = self._args()
                args["confirm"] = False
                resp = await _call(client, "advanced_search_template_create", args)
                assert _error(resp) == "CONFIRM_REQUIRED"
                db = stack.sync_factory()
                assert db.query(SearchTemplate).count() == 0
                db.close()
        finally:
            await stack.close()


class TestWireDashboard:
    async def test_dashboard_aggregates_only(self, auth_utils_patch):
        stack = await _ToolStack.create(on=["dashboard.read"])
        try:
            async with _stack_client(stack) as client:
                data = _payload(await _call(client, "dashboard_get", {}))
                assert set(data) == {
                    "generated_at",
                    "totals",
                    "status_counts",
                    "active_torrent_count",
                    "global_download_speed",
                    "global_upload_speed",
                }
                assert data["totals"]["tasks"]["total"] == 1  # cron_task 种子数据
                assert data["totals"]["downloaders"] == {"total": 0, "online": 0, "offline": 0}  # store 未注入
                assert data["global_download_speed"] == 0
                # G5：不泄漏下载器连接信息与审计敏感面
                raw = json.dumps(data, ensure_ascii=False)
                assert "downloader_list" not in raw
                assert "activities" not in raw
                assert "host" not in raw and "user_agent" not in raw
        finally:
            await stack.close()
