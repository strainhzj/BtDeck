# -*- coding: utf-8 -*-
"""MCP-G5 数据最小化与脱敏门禁——六工具线上 canary（W4）。

W2 已有 redaction 单元 43 项（嵌套/URL 编码/camel-snake/变异负例）；本文件把
canary 提升到**六工具真实 dispatch 出口**：种子数据埋入 passkey/token/绝对路径/
URL 编码变体 canary，逐工具断言 canary 不出现在响应（成功与拒绝路径）与
captured 日志；自由文本字段（种子名）命中泄漏扫描时整体 fail-closed（不截断放行）。
依赖 mcp SDK，缺装自动 skip。
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
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
from app.models.search_template import SearchTemplate  # noqa: E402
from app.services.mcp_settings_service import McpRuntimeSettings  # noqa: E402
from app.tasks.cron_models import CronTask  # noqa: E402
from app.torrents.audit_models import TorrentAuditLog  # noqa: E402
from app.torrents.models import TorrentInfo, TrackerInfo  # noqa: E402

TEST_SECRET = "test-secret-key-for-mcp-canary"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-canary"
RPC_HEADERS = {"Accept": "application/json, text/event-stream"}

# canary 家族：明文 passkey / token / 绝对路径 / URL 编码变体（§4.5 政策面）
PASSKEY_CANARY = "WIREPASSKEYCANARY9"
TOKEN_CANARY = "WIRETOKENCANARY7"
PATH_CANARY = "WIRECANARYSECRETPATH"
ENCODED_CANARY = "%57%49%52%45"  # "WIRE" 的 URL 编码变体

TRACKER_URL_CANARY = f"https://t.canary.example.org:8080/announce?passkey={PASSKEY_CANARY}"
TRACKER_URL_ENCODED = f"https://e.canary.example.org/a?k={ENCODED_CANARY}%42"
CANARY_SAVE_PATH = f"C:\\\\Users\\\\{PATH_CANARY}\\\\iso"
CANARY_NAME_TEXT = f"leak http://10.0.0.1:8080/a?token={TOKEN_CANARY} {PASSKEY_CANARY}"

ALL_CAPS = None  # 由 _snapshot 动态填充


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


def _torrent_row(info_id: str, torrent_hash: str, name: str, save_path: str, dr: int = 0) -> TorrentInfo:
    return TorrentInfo(
        info_id,
        "1",
        "qbt-canary",
        "42",
        torrent_hash,
        name,
        save_path,
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
        dr,
    )


class _CanaryStore:
    """stub store：快照含 1 个 qB VO（昵称带路径 canary，验证昵称面脱敏）。"""

    def __init__(self, client: Any):
        self._vos = [
            SimpleNamespace(
                downloader_id="1",
                fail_time=0,
                client=client,
                nickname=f"qbt-{PATH_CANARY}",  # 连接信息永不输出；昵称即使含路径 canary 也不进搜索结果
                downloader_type=0,
            )
        ]

    async def get_snapshot(self) -> List[Any]:
        return list(self._vos)


class _CanaryQbClient:
    """qB 桩：返回的种子名嵌入 canary（自由文本泄漏扫描 fail-closed 样本）。"""

    def __init__(self, info_hash: str, name: str):
        self.info_hash = info_hash
        self.name = name

    def torrents_add(self, **kwargs: Any) -> str:
        return "Ok."

    def torrents_info(self, torrent_hashes: Optional[str] = None) -> List[Any]:
        return [
            SimpleNamespace(
                hash=self.info_hash,
                name=self.name,
                save_path=f"/data/{PATH_CANARY}",
                total_size=1024,
                state="stalledUP",
                added_on=1757000000,
                completion_on=0,
                ratio=1.0,
                ratio_limit=None,
                tags=[],
                category="",
                super_seeding=False,
            )
        ]


def _canary_torrent(name: bytes) -> bytes:
    import bencodepy

    return bencodepy.encode(
        {
            b"announce": b"http://tracker.canary.example.com/announce",
            b"info": {b"name": name, b"piece length": 16384, b"length": 1, b"pieces": b"\x00" * 20},
        }
    )


class _CanaryStack:
    def __init__(self) -> None:
        self.snapshot: Optional[McpRuntimeSettings] = None
        self.bundle: Any = None
        self.app: Any = None

    @classmethod
    async def create(cls) -> "_CanaryStack":
        from app.mcp.contracts import CAPABILITY_CODES

        stack = cls()
        stack.sync_engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(
            bind=stack.sync_engine,
            tables=[t.__table__ for t in (User, TorrentInfo, TrackerInfo, SearchTemplate, CronTask)],
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
        db.add(_torrent_row("i-canary", "c" * 40, "ubuntu-canary", CANARY_SAVE_PATH))
        db.add(_torrent_row("i-soft", "d" * 40, "soft-" + CANARY_NAME_TEXT, CANARY_SAVE_PATH, dr=1))
        db.add(
            TrackerInfo(
                tracker_id="t-canary",
                torrent_info_id="i-canary",
                tracker_name="t1",
                tracker_url=TRACKER_URL_CANARY,
                last_announce_msg="announce ok",
                dr=0,
            )
        )
        db.add(
            TrackerInfo(
                tracker_id="t-enc",
                torrent_info_id="i-canary",
                tracker_name="t2",
                tracker_url=TRACKER_URL_ENCODED,
                last_announce_msg="ok",
                dr=0,
            )
        )
        db.commit()
        db.close()

        content = _canary_torrent(f"canary-name-{TOKEN_CANARY}".encode())
        info_hash = hashlib.sha1(
            __import__("bencodepy").encode(__import__("bencodepy").decode(content)[b"info"])
        ).hexdigest()
        stack.store = _CanaryStore(_CanaryQbClient(info_hash, f"name-embeds passkey={PASSKEY_CANARY}"))

        state = SimpleNamespace(store=stack.store)
        stack.snapshot = McpRuntimeSettings(
            enabled=True,
            capabilities={
                code: code
                in (
                    "torrent.advanced_search",
                    "torrent.mark_pending_delete",
                    "dashboard.read",
                    "cron.trigger",
                    "search_template.create",
                    "torrent.add",
                )
                for code in CAPABILITY_CODES
            },
            revision=1,
        )
        stack.bundle = create_mcp_server_bundle(state)
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
async def _stack_client(stack: _CanaryStack):
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
                        "clientInfo": {"name": "btdeck-canary", "version": "0"},
                    },
                },
                headers=RPC_HEADERS,
            )
            assert resp.status_code == 200
            await client.post(
                "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=RPC_HEADERS
            )
            yield client


async def _call(client: Any, name: str, arguments: Dict[str, Any], request_id: int = 9) -> Dict[str, Any]:
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


CANARIES = (PASSKEY_CANARY, TOKEN_CANARY, PATH_CANARY, ENCODED_CANARY)


def _assert_no_canary(payload_text: str) -> None:
    for canary in CANARIES:
        assert canary not in payload_text, f"canary 泄漏: {canary}"


class TestSixToolCanarySweep:
    async def test_all_tools_zero_canary_in_response_and_logs(self, auth_utils_patch, caplog):
        """六工具真实 dispatch：响应面与日志面 canary 零泄漏。"""
        from app.mcp.tools.idempotency import reset_for_tests

        reset_for_tests()
        stack = await _CanaryStack.create()
        try:
            with caplog.at_level(logging.DEBUG, logger="app.mcp"):
                async with _stack_client(stack) as client:
                    # 1) 高级搜索：tracker 域名收敛 + 路径仅末段
                    search = await _call(
                        client,
                        "torrent_advanced_search",
                        {
                            "conditions": {
                                "condition_groups": [
                                    {
                                        "logic": "AND",
                                        "conditions": [{"field": "name", "operator": "contains", "value": "ubuntu"}],
                                    }
                                ]
                            },
                            "page": 1,
                            "page_size": 20,
                        },
                    )
                    assert search["result"].get("isError") is False
                    items = search["result"]["structuredContent"]["items"]
                    # tracker 只输出规范化域名（设计行为）；路径仅末段
                    assert items[0]["tracker_domains"] == ["e.canary.example.org", "t.canary.example.org"]
                    assert items[0]["path_display"] == "iso"
                    _assert_no_canary(str(search))

                    # 2) 仪表盘：聚合计数，无下载器名/昵称
                    dash = await _call(client, "dashboard_get", {})
                    assert dash["result"].get("isError") is False
                    _assert_no_canary(str(dash))

                    # 3) 等级4标记（service 替身成功；输出仅标识与布尔）
                    class _OkService:
                        LEVEL4_TAG = "pending_delete"

                        def __init__(self, db, store=None, audit_context=None):
                            pass

                        async def delete_by_level(self, info_id, level, operator="admin", audit_service=None):
                            return {"success": True, "db_update_success": True}

                    with patch("app.services.torrent_deletion_by_level.TorrentDeletionByLevelService", _OkService):
                        mark = await _call(
                            client,
                            "torrent_mark_pending_delete",
                            {"info_ids": ["i-canary"], "confirm": True, "idempotency_key": "canary-k"},
                        )
                    assert mark["result"].get("isError") is False
                    _assert_no_canary(str(mark))

                    # 4) Cron 触发：白名单任务缺行 → 固定文案拒绝
                    cron = await _call(
                        client,
                        "cron_task_trigger",
                        {"task_code": "torrent_info_sync_ac608e4d", "confirm": True, "idempotency_key": "ck"},
                    )
                    error = (cron["result"].get("structuredContent") or {}).get("error") or {}
                    assert error.get("code") == "CRON_TASK_NOT_TRIGGERABLE"
                    _assert_no_canary(str(cron))

                    # 5) 模板创建：conditions 内嵌 canary 不回显（输出仅 id/name/is_public/created）
                    tpl = await _call(
                        client,
                        "advanced_search_template_create",
                        {
                            "name": "tpl-canary-safe",
                            "conditions": {
                                "source": "advanced",
                                "condition_groups": [
                                    {
                                        "logic": "AND",
                                        "conditions": [
                                            {"field": "name", "operator": "contains", "value": f"x{PASSKEY_CANARY}"}
                                        ],
                                    }
                                ],
                            },
                            "confirm": True,
                            "idempotency_key": "tk",
                        },
                    )
                    assert tpl["result"].get("isError") is False
                    _assert_no_canary(str(tpl))

                    # 6) 添加种子：种子名嵌 canary → 泄漏扫描 fail-closed（不截断放行）
                    content = _canary_torrent(f"name-{PASSKEY_CANARY}-end".encode())
                    add = await _call(
                        client,
                        "torrent_add_file",
                        {
                            "torrent_file_b64": base64.b64encode(content).decode("ascii"),
                            "downloader_id": "1",
                            "confirm": True,
                            "idempotency_key": "ak",
                        },
                    )
                    add_error = (add["result"].get("structuredContent") or {}).get("error") or {}
                    assert add_error.get("code") == "INTERNAL_ERROR"  # canary 命中 = 实现缺陷语义，fail-closed
                    _assert_no_canary(str(add))

            # 日志面：工具参数/领域 payload 不入日志
            _assert_no_canary(caplog.text)
        finally:
            reset_for_tests()
            await stack.close()

    async def test_rejection_messages_never_echo_canary_input(self, auth_utils_patch, caplog):
        """拒绝路径固定文案：携带 canary 的非法输入不被回显。"""
        stack = await _CanaryStack.create()
        try:
            with caplog.at_level(logging.DEBUG, logger="app.mcp"):
                async with _stack_client(stack) as client:
                    magnet = await _call(
                        client,
                        "torrent_add_file",
                        {
                            "torrent_file_b64": f"magnet:?xt=urn:btih:{PASSKEY_CANARY}",
                            "downloader_id": "1",
                            "confirm": True,
                            "idempotency_key": "mk",
                        },
                    )
                    error = (magnet["result"].get("structuredContent") or {}).get("error") or {}
                    assert error.get("code") == "SERVER_PATH_FORBIDDEN"
                    _assert_no_canary(str(magnet))

                    privacy = await _call(
                        client,
                        "torrent_advanced_search",
                        {
                            "conditions": {
                                "condition_groups": [
                                    {
                                        "logic": "AND",
                                        "conditions": [
                                            {
                                                "field": "tracker",
                                                "operator": "contains",
                                                "value": f"passkey={PASSKEY_CANARY}",
                                            }
                                        ],
                                    }
                                ]
                            },
                            "page": 1,
                            "page_size": 20,
                        },
                    )
                    p_error = (privacy["result"].get("structuredContent") or {}).get("error") or {}
                    assert p_error.get("code") in {"INVALID_ARGUMENT"}
                    _assert_no_canary(str(privacy))

            _assert_no_canary(caplog.text)
        finally:
            await stack.close()
