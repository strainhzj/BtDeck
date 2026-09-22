# -*- coding: utf-8 -*-
"""MCP 配置控制面 API 回归（feature mcp-service-capabilities-2026-08-28 W1）。

覆盖计划 §4.2 三组硬语义：

- **G1 fail-closed**：记录缺失/JSON 损坏/未知 schemaVersion/字段缺失或类型非法
  一律回落"全局关闭 + 全部能力关闭"；环境 kill switch 强制覆盖；
- **G2 revision CAS**：expectedRevision 不匹配 409；顺序更新 0→1→2；
  损坏行按 revision 0 可修复；载荷必须携带全部已知能力码、拒绝未知码；
- **G3 控制面认证**：走 principal 内核真实链路（真 User 行 + 真 token），
  无 token/坏 token/用户不存在 → 401；禁用/强制改密 → 403；
- **G11 审计**：成功 PUT 写入 mcp_settings_update 审计行（operator/revision）。
"""

import json
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth import utils as auth_utils
from app.auth.models import Config, User
from app.database import Base, get_async_db, get_db
from app.mcp.contracts import CAPABILITY_CODES, MCP_CONFIG_KEY
from app.torrents.audit_models import TorrentAuditLog

TEST_SECRET = "test-secret-key-for-mcp-settings"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-settings"


def _all_caps(enabled: bool = False) -> dict:
    return {code: enabled for code in CAPABILITY_CODES}


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[Config.__table__, User.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[Config.__table__, User.__table__])


@pytest.fixture
async def async_db():
    """审计日志异步会话（与 test_audit_logs_api 同模式：AUTO 模式异步 fixture）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[TorrentAuditLog.__table__]))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=[TorrentAuditLog.__table__]))
        await engine.dispose()


def _make_user(db_session: Session, username: str = "admin", **overrides) -> User:
    user = User(
        username=username,
        password="not-a-real-hash",
        is_active=overrides.get("is_active", True),
        must_change_password=overrides.get("must_change_password", False),
    )
    db_session.add(user)
    db_session.commit()
    return user


def _token(username: str, user_id: int = 1, secret: str = TEST_SECRET) -> str:
    """构造过 principal 全链校验的 token（调用时 client fixture 的补丁已生效）。"""
    return auth_utils.create_access_token(
        {"sub": username, "user_id": str(user_id), "verify_secret": TEST_LOGIN_SECRET}
    )


@pytest.fixture
def client(db_session, async_db):
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    async def override_get_async_db():
        yield async_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db

    mock_settings = MagicMock()
    mock_settings.SECRET_KEY = TEST_SECRET
    mock_settings.ALGORITHM = "HS256"
    mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    with (
        patch("app.auth.utils.settings", mock_settings),
        patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET),
    ):
        yield TestClient(app, raise_server_exceptions=False)


def _auth(username: str = "admin", user_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {_token(username, user_id)}"}


def _write_config(db_session: Session, value: str) -> None:
    db_session.add(Config(key=MCP_CONFIG_KEY, value=value, description="test"))
    db_session.commit()


def _put_body(expected_revision: int = 0, enabled: bool = True, capabilities=None):
    return {
        "enabled": enabled,
        "capabilities": capabilities if capabilities is not None else _all_caps(False),
        "expectedRevision": expected_revision,
    }


def _settings(client: TestClient) -> dict:
    resp = client.get("/api/v1/mcp/settings", headers=_auth())
    assert resp.status_code == 200
    return resp.json()["data"]["settings"]


# ==============================================================================
# G1：默认态与 fail-closed
# ==============================================================================


class TestGetFailClosed:
    def test_missing_row_returns_all_disabled_defaults(self, client, db_session):
        _make_user(db_session)
        data = _settings(client)
        assert data["enabled"] is False
        assert data["capabilities"] == _all_caps(False)
        assert data["revision"] == 0
        assert data["updatedAt"] is None and data["updatedBy"] is None
        assert data["forceDisabled"] is False
        assert data["effectiveEnabled"] is False

    def test_catalog_meta_from_single_source(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/mcp/settings", headers=_auth())
        catalog = resp.json()["data"]["catalog"]
        assert [entry["code"] for entry in catalog] == list(CAPABILITY_CODES)
        assert all(entry["defaultEnabled"] is False for entry in catalog)
        risk_by_code = {entry["code"]: entry["risk"] for entry in catalog}
        assert risk_by_code["cron.trigger"] == "high"
        assert risk_by_code["torrent.advanced_search"] == "read"

    @pytest.mark.parametrize(
        "stored_value",
        [
            "{broken-json",  # JSON 损坏
            "[1, 2, 3]",  # 非对象
            json.dumps({"schemaVersion": 2, "enabled": True}),  # 未知 schemaVersion
            json.dumps({"schemaVersion": 1}),  # 缺 enabled/capabilities
            json.dumps({"schemaVersion": 1, "enabled": "yes", "capabilities": _all_caps(True)}),  # 类型非法
            json.dumps(
                {
                    "schemaVersion": 1,
                    "enabled": True,
                    "capabilities": {k: False for k in CAPABILITY_CODES if k != "cron.trigger"},  # 缺一个能力码
                    "revision": 5,
                }
            ),
            json.dumps(
                {
                    "schemaVersion": 1,
                    "enabled": True,
                    "capabilities": _all_caps(True),
                    "revision": True,  # bool 不是合法 revision
                }
            ),
        ],
        ids=[
            "broken-json",
            "non-object",
            "unknown-schema",
            "missing-fields",
            "bad-type",
            "missing-capability",
            "bool-revision",
        ],
    )
    def test_invalid_stored_payload_fails_closed(self, client, db_session, stored_value):
        """G1：任何结构非法整体回落默认关闭，不部分采信、不暴露 revision。"""
        _make_user(db_session)
        _write_config(db_session, stored_value)
        data = _settings(client)
        assert data["enabled"] is False
        assert data["capabilities"] == _all_caps(False)
        assert data["revision"] == 0
        assert data["effectiveEnabled"] is False

    def test_valid_stored_payload_is_loaded(self, client, db_session):
        _make_user(db_session)
        _write_config(
            db_session,
            json.dumps(
                {
                    "schemaVersion": 1,
                    "enabled": True,
                    "capabilities": _all_caps(False) | {"dashboard.read": True},
                    "revision": 7,
                    "updatedAt": "2026-09-08T00:00:00+00:00",
                    "updatedBy": "someone",
                }
            ),
        )
        data = _settings(client)
        assert data["enabled"] is True
        assert data["capabilities"]["dashboard.read"] is True
        assert data["revision"] == 7
        assert data["updatedBy"] == "someone"
        assert data["effectiveEnabled"] is True

    def test_kill_switch_forces_effective_disabled(self, client, db_session):
        """环境 kill switch：存储值原样回显，但 effectiveEnabled 恒 False。"""
        from app.core import config as config_module

        _make_user(db_session)
        _write_config(
            db_session,
            json.dumps(
                {
                    "schemaVersion": 1,
                    "enabled": True,
                    "capabilities": _all_caps(True),
                    "revision": 3,
                }
            ),
        )
        with patch.object(config_module.settings, "BTDECK_MCP_FORCE_DISABLED", True):
            data = _settings(client)
        assert data["enabled"] is True  # 存储意图保留
        assert data["forceDisabled"] is True
        assert data["effectiveEnabled"] is False


# ==============================================================================
# G2：revision CAS 与载荷校验
# ==============================================================================


class TestPutRevisionCas:
    def test_put_creates_row_revision_1_and_persists(self, client, db_session):
        _make_user(db_session)
        caps = _all_caps(False) | {"torrent.advanced_search": True}
        resp = client.put("/api/v1/mcp/settings", json=_put_body(0, True, caps), headers=_auth())
        assert resp.status_code == 200
        data = resp.json()["data"]["settings"]
        assert data["revision"] == 1
        assert data["enabled"] is True
        assert data["capabilities"]["torrent.advanced_search"] is True
        assert data["updatedBy"] == "admin"
        assert data["updatedAt"]

        row = db_session.query(Config).filter(Config.key == MCP_CONFIG_KEY).first()
        assert row is not None
        assert json.loads(row.value)["revision"] == 1
        # GET 回读一致
        assert _settings(client)["revision"] == 1

    def test_put_stale_revision_returns_409(self, client, db_session):
        _make_user(db_session)
        first = client.put("/api/v1/mcp/settings", json=_put_body(0), headers=_auth())
        assert first.status_code == 200
        stale = client.put("/api/v1/mcp/settings", json=_put_body(0, enabled=False), headers=_auth())
        assert stale.status_code == 409
        detail = stale.json()["detail"]
        assert detail["code"] == "409"
        assert detail["data"]["currentRevision"] == 1
        # 库中值未被旧 revision 写穿
        assert _settings(client)["enabled"] is True

    def test_put_sequential_updates_advance_revision(self, client, db_session):
        _make_user(db_session)
        for expected, enabled in ((0, True), (1, False), (2, True)):
            resp = client.put(
                "/api/v1/mcp/settings",
                json=_put_body(expected, enabled),
                headers=_auth(),
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["data"]["settings"]["revision"] == expected + 1
        assert _settings(client)["enabled"] is True

    def test_put_repairs_corrupt_row_with_revision_zero(self, client, db_session):
        """损坏行的 CAS 基线是 revision 0：expectedRevision=0 修复，不要求先删行。"""
        _make_user(db_session)
        _write_config(db_session, "{broken")
        resp = client.put("/api/v1/mcp/settings", json=_put_body(0, False), headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["data"]["settings"]["revision"] == 1

    def test_put_under_kill_switch_persists_intent_but_effective_off(self, client, db_session):
        from app.core import config as config_module

        _make_user(db_session)
        with patch.object(config_module.settings, "BTDECK_MCP_FORCE_DISABLED", True):
            resp = client.put(
                "/api/v1/mcp/settings",
                json=_put_body(0, True, _all_caps(True)),
                headers=_auth(),
            )
        assert resp.status_code == 200
        data = resp.json()["data"]["settings"]
        assert data["forceDisabled"] is True
        assert data["effectiveEnabled"] is False
        assert data["enabled"] is True  # 落库意图保留，便于解除 kill switch 后恢复


class TestPutValidation:
    def test_unknown_capability_code_rejected(self, client, db_session):
        _make_user(db_session)
        caps = _all_caps(False) | {"torrent.magic": True}
        resp = client.put("/api/v1/mcp/settings", json=_put_body(0, True, caps), headers=_auth())
        assert resp.status_code == 400
        assert "torrent.magic" in resp.json()["detail"]["msg"]

    def test_missing_capability_code_rejected(self, client, db_session):
        _make_user(db_session)
        caps = {k: False for k in CAPABILITY_CODES if k != "cron.trigger"}
        resp = client.put("/api/v1/mcp/settings", json=_put_body(0, True, caps), headers=_auth())
        assert resp.status_code == 400
        assert "cron.trigger" in resp.json()["detail"]["msg"]

    def test_non_bool_enabled_rejected_by_schema(self, client, db_session):
        _make_user(db_session)
        body = _put_body(0)
        body["enabled"] = "maybe"
        resp = client.put("/api/v1/mcp/settings", json=body, headers=_auth())
        assert resp.status_code == 422

    def test_negative_expected_revision_rejected_by_schema(self, client, db_session):
        _make_user(db_session)
        resp = client.put("/api/v1/mcp/settings", json=_put_body(-1), headers=_auth())
        assert resp.status_code == 422


# ==============================================================================
# G3：控制面认证（principal 内核真实链路）
# ==============================================================================


class TestControlPlaneAuth:
    def test_no_token_returns_401(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/mcp/settings")
        assert resp.status_code == 401

    def test_invalid_signature_token_returns_401(self, client, db_session):
        _make_user(db_session)
        bad = pyjwt.encode(
            {"sub": "admin", "user_id": "1", "verify_secret": TEST_LOGIN_SECRET, "exp": 9999999999},
            "wrong-secret",
            algorithm="HS256",
        )
        resp = client.get("/api/v1/mcp/settings", headers={"Authorization": f"Bearer {bad}"})
        assert resp.status_code == 401

    def test_user_not_found_returns_401(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/mcp/settings", headers=_auth("ghost", 99))
        assert resp.status_code == 401

    def test_inactive_user_returns_403(self, client, db_session):
        _make_user(db_session, is_active=False)
        resp = client.get("/api/v1/mcp/settings", headers=_auth())
        assert resp.status_code == 403

    def test_must_change_password_user_returns_403(self, client, db_session):
        _make_user(db_session, must_change_password=True)
        resp = client.get("/api/v1/mcp/settings", headers=_auth())
        assert resp.status_code == 403

    def test_x_access_token_header_also_accepted(self, client, db_session):
        """与全站一致的 X-Access-Token 双兼容提取（复用 _extract_access_token）。"""
        _make_user(db_session)
        resp = client.get("/api/v1/mcp/settings", headers={"X-Access-Token": _token("admin", 1)})
        assert resp.status_code == 200


# ==============================================================================
# G11：配置变更审计
# ==============================================================================


class TestSettingsAudit:
    async def test_successful_put_writes_audit_log(self, client, db_session, async_db):
        _make_user(db_session)
        resp = client.put("/api/v1/mcp/settings", json=_put_body(0, True), headers=_auth())
        assert resp.status_code == 200
        await async_db.commit()  # log_operation 内部已提交；显式刷新会话保证可见
        logs = (
            (
                await async_db.execute(
                    select(TorrentAuditLog).where(TorrentAuditLog.operation_type == "mcp_settings_update")
                )
            )
            .scalars()
            .all()
        )
        assert len(logs) == 1
        entry = logs[0]
        assert entry.operator == "admin"
        assert entry.operation_result == "success"
        detail = json.loads(entry.operation_detail)
        assert detail["revision"] == 1
        assert detail["enabled"] is True

    async def test_conflict_put_writes_no_audit(self, client, db_session, async_db):
        """409 冲突不追加审计行：总数停留在首次成功 PUT 的那一条。"""
        _make_user(db_session)
        client.put("/api/v1/mcp/settings", json=_put_body(0), headers=_auth())
        conflict = client.put("/api/v1/mcp/settings", json=_put_body(0, False), headers=_auth())
        assert conflict.status_code == 409
        await async_db.commit()
        logs = (
            (
                await async_db.execute(
                    select(TorrentAuditLog).where(TorrentAuditLog.operation_type == "mcp_settings_update")
                )
            )
            .scalars()
            .all()
        )
        assert len(logs) == 1  # 仅首次成功 PUT 的审计；冲突未新增
        assert json.loads(logs[0].operation_detail)["revision"] == 1
