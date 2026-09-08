# -*- coding: utf-8 -*-
"""MCP-G1 默认关闭与升级矩阵门禁（feature mcp-service-capabilities-2026-08-28 W4）。

在 W1 服务级 fail-closed 覆盖（缺行/坏载荷/kill switch/CAS，tests/api/test_mcp_settings）
之上补齐计划 §5-G1 的升级与运行时矩阵：

- **遗留共存升级**：老版本库（仅标量配置行、无 mcp 键）升级后默认全局关+能力全关，
  遗留行原值不动；未知未来 schemaVersion（降级场景）fail-closed；
- **重启保持**：PUT 落库后新引擎/新服务实例（等价重启）读取到同一意图与 revision；
- **生产供给器链路**：真实 ``_default_settings_provider``（短会话读 configs 表）
  驱动线上 /mcp——首装默认 SERVICE_DISABLED、落库开启后 list/call 生效、
  环境 kill switch 优先级高于库内 enabled。

静态部分无 SDK 依赖；wire 部分缺装自动 skip。
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.auth.models import Config, User
from app.database import Base
from app.mcp.contracts import CAPABILITY_CODES, MCP_CONFIG_KEY, MCP_CONFIG_SCHEMA_VERSION
from app.services.mcp_settings_service import McpSettingsService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ==============================================================================
# 服务级升级矩阵（无 SDK 依赖）
# ==============================================================================


def _temp_file_engine():
    db_dir = Path(tempfile.gettempdir()) / f"btdeck-mcp-upgrade-{uuid.uuid4().hex}"
    db_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_dir / 'upgrade.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(bind=engine, tables=[Config.__table__])
    return engine, db_dir


class TestLegacyCoexistenceUpgrade:
    def test_legacy_scalar_rows_untouched_and_mcp_default_off(self):
        """老库升级：无 mcp 键 → 默认全关；既有标量配置行原值保留。"""
        engine, db_dir = _temp_file_engine()
        try:
            db = sessionmaker(bind=engine)()
            db.add(Config(key="cookie_expire_minutes", value="60", description="legacy"))
            db.commit()
            db.close()

            snapshot = McpSettingsService(sessionmaker(bind=engine)()).get_settings()
            assert snapshot.enabled is False
            assert not any(snapshot.capabilities.values())
            assert snapshot.revision == 0

            check = sessionmaker(bind=engine)()
            legacy = check.query(Config).filter(Config.key == "cookie_expire_minutes").first()
            check.close()
            assert legacy is not None and legacy.value == "60"  # 升级不触碰遗留行
        finally:
            engine.dispose()
            import shutil

            shutil.rmtree(db_dir, ignore_errors=True)

    def test_unknown_future_schema_version_fails_closed(self):
        """降级场景：库内 schemaVersion 高于当前支持版本 → 整份回落默认全关。"""
        engine, db_dir = _temp_file_engine()
        try:
            payload = {
                "schemaVersion": MCP_CONFIG_SCHEMA_VERSION + 99,
                "enabled": True,
                "capabilities": {code: True for code in CAPABILITY_CODES},
                "revision": 7,
            }
            db = sessionmaker(bind=engine)()
            db.add(Config(key=MCP_CONFIG_KEY, value=json.dumps(payload), description="future"))
            db.commit()
            db.close()

            snapshot = McpSettingsService(sessionmaker(bind=engine)()).get_settings()
            assert snapshot.enabled is False
            assert not any(snapshot.capabilities.values())
            assert snapshot.revision == 0  # 坏载荷不采信其 revision
        finally:
            engine.dispose()
            import shutil

            shutil.rmtree(db_dir, ignore_errors=True)


class TestRestartPersistence:
    def test_put_then_restart_retains_intent_and_revision(self):
        """重启矩阵：落库意图在新引擎/新服务实例（等价进程重启）中原样恢复。"""
        engine, db_dir = _temp_file_engine()
        try:
            factory = sessionmaker(bind=engine)
            db = factory()
            updated = McpSettingsService(db).update_settings(
                enabled=True,
                capabilities={code: code == "dashboard.read" for code in CAPABILITY_CODES},
                expected_revision=0,
                updated_by="admin",
            )
            db.commit()
            db.close()
            assert updated.enabled and updated.revision == 1

            engine.dispose()  # 等价重启：新引擎读同一文件
            engine2 = create_engine(
                f"sqlite:///{db_dir / 'upgrade.sqlite3'}",
                connect_args={"check_same_thread": False, "timeout": 15},
            )
            snapshot = McpSettingsService(sessionmaker(bind=engine2)()).get_settings()
            engine2.dispose()
            assert snapshot.enabled is True
            assert snapshot.revision == 1
            assert snapshot.capabilities["dashboard.read"] is True
            assert not snapshot.capabilities["torrent.add"]
        finally:
            import shutil

            shutil.rmtree(db_dir, ignore_errors=True)


# ==============================================================================
# 生产供给器链路（wire；需 mcp SDK）
# ==============================================================================

httpx = pytest.importorskip("httpx")
pytest.importorskip("mcp.server.streamable_http_manager", reason="mcp SDK 未安装")

import contextlib  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import utils as auth_utils  # noqa: E402
from app.mcp.server import create_mcp_server_bundle  # noqa: E402
from app.tasks.cron_models import CronTask  # noqa: E402
from app.torrents.audit_models import TorrentAuditLog  # noqa: E402

TEST_SECRET = "test-secret-key-for-mcp-upgrade"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-upgrade"
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


class _ProductionProviderStack:
    """真实生产配置供给器（默认 _default_settings_provider 读 configs 表）+ /mcp。"""

    def __init__(self) -> None:
        self.bundle: Any = None
        self.app: Any = None

    @classmethod
    async def create(cls) -> "_ProductionProviderStack":
        stack = cls()
        stack.db_dir = Path(tempfile.gettempdir()) / f"btdeck-mcp-prod-{uuid.uuid4().hex}"
        stack.db_dir.mkdir(parents=True, exist_ok=True)
        stack.engine = create_engine(
            f"sqlite:///{stack.db_dir / 'prod.sqlite3'}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        Base.metadata.create_all(bind=stack.engine, tables=[Config.__table__, User.__table__, CronTask.__table__])
        stack.factory = sessionmaker(bind=stack.engine)
        db = stack.factory()
        db.add(User(username="admin", password="x", is_active=True, must_change_password=False))
        db.commit()
        db.close()

        stack.async_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        async with stack.async_engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=[TorrentAuditLog.__table__, CronTask.__table__])
            )
        stack.async_factory = async_sessionmaker(bind=stack.async_engine, class_=AsyncSession, expire_on_commit=False)

        # 生产供给器内部 `from app.database import SessionLocal` 现取——替换为临时库工厂
        stack._session_patch = patch("app.database.SessionLocal", stack.factory)
        stack._session_patch.start()

        stack.bundle = create_mcp_server_bundle(None)
        stack.bundle.runtime.session_factory = stack.factory
        stack.bundle.runtime.async_session_factory = stack.async_factory
        stack.bundle.runtime.mark_ready()

        stack.app = FastAPI()
        stack.app.mount("/mcp", stack.bundle.sub_asgi)
        return stack

    def enable_via_service(self) -> None:
        db = self.factory()
        try:
            McpSettingsService(db).update_settings(
                enabled=True,
                capabilities={code: code == "dashboard.read" for code in CAPABILITY_CODES},
                expected_revision=0,
                updated_by="admin",
            )
            db.commit()
        finally:
            db.close()

    async def close(self) -> None:
        self._session_patch.stop()
        self.engine.dispose()
        await self.async_engine.dispose()
        import shutil

        shutil.rmtree(self.db_dir, ignore_errors=True)


@contextlib.asynccontextmanager
async def _stack_client(stack: _ProductionProviderStack):
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
                        "clientInfo": {"name": "btdeck-upgrade", "version": "0"},
                    },
                },
                headers=RPC_HEADERS,
            )
            assert resp.status_code == 200
            await client.post(
                "/mcp/", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=RPC_HEADERS
            )
            yield client


async def _list_tools(client: Any) -> Dict[str, Any]:
    resp = await client.post("/mcp/", json={"jsonrpc": "2.0", "method": "tools/list", "id": 2}, headers=RPC_HEADERS)
    assert resp.status_code == 200
    return resp.json()


def _jsonrpc_error_code(payload: Dict[str, Any]) -> Optional[str]:
    error = payload.get("error") or {}
    return ((error.get("data") or {}).get("error_code")) or error.get("data")


class TestProductionProviderWire:
    async def test_first_install_default_off_then_enable_takes_effect(self, auth_utils_patch):
        """首装（configs 无 mcp 行）经生产供给器 → 全局默认关；
        落库开启后无需重启立即生效（revision 热更新链路）。"""
        stack = await _ProductionProviderStack.create()
        try:
            async with _stack_client(stack) as client:
                first = await _list_tools(client)
                assert _jsonrpc_error_code(first) == "SERVICE_DISABLED"

                stack.enable_via_service()  # 等价控制面 PUT 落库

                second = await _list_tools(client)
                assert "error" not in second
                tool_names = {t["name"] for t in second["result"]["tools"]}
                assert tool_names == {"dashboard_get"}  # 仅开启的能力可发现

                call = await client.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "id": 3,
                        "params": {"name": "dashboard_get", "arguments": {}},
                    },
                    headers=RPC_HEADERS,
                )
                assert call.status_code == 200
                assert call.json()["result"].get("isError") is False
        finally:
            await stack.close()

    async def test_kill_switch_env_overrides_enabled_db_over_wire(self, auth_utils_patch):
        """环境 kill switch 优先级最高：库内 enabled=True 仍稳定 SERVICE_DISABLED。"""
        from app.core.config import settings as app_settings

        stack = await _ProductionProviderStack.create()
        try:
            stack.enable_via_service()
            with patch.object(app_settings, "BTDECK_MCP_FORCE_DISABLED", True):
                async with _stack_client(stack) as client:
                    listing = await _list_tools(client)
                    assert _jsonrpc_error_code(listing) == "SERVICE_DISABLED"
                    call = await client.post(
                        "/mcp/",
                        json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "id": 3,
                            "params": {"name": "dashboard_get", "arguments": {}},
                        },
                        headers=RPC_HEADERS,
                    )
                    result = call.json()["result"]
                    assert result.get("isError") is True
                    error = (result.get("structuredContent") or {}).get("error") or {}
                    assert error.get("code") == "SERVICE_DISABLED"
        finally:
            await stack.close()
