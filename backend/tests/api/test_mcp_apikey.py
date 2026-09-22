# -*- coding: utf-8 -*-
"""MCP 服务密钥控制面 API 回归（feature mcp-service-capabilities-2026-08-28 W5）。

覆盖计划 §4.2-2/§4.4-2 与审查补齐项：

- **查看（GET /mcp/apikey）**：absent（未生成）/active（明文）/unreadable
  （密文损坏——secret_key 轮换场景）三态信封；仅 active（真实明文披露）
  写 mcp_apikey_view 审计；
- **刷新（POST /mcp/apikey/rotate）**：expectedRevision=0 建行、CAS 冲突
  409 + reasonCode MCP_APIKEY_CONFLICT + currentRevision、旧密钥立即失效、
  归属=操作者；写 mcp_apikey_rotate 审计（previousOwner/rotatedBy/revision，
  禁记密钥本体与哈希）；
- **G3 控制面认证**：与 settings 端点同门禁（无 token 401；禁用/强制改密
  403；X-Access-Token 兼容）；
- **双语目录**：catalog 每项携带成对 descriptionEn（与 description 非空）。
"""

import json
from unittest.mock import MagicMock, patch

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
from app.mcp.contracts import CAPABILITY_CODES, MCP_APIKEY_CONFIG_KEY, is_mcp_api_key_format
from app.torrents.audit_models import TorrentAuditLog

TEST_SECRET = "test-secret-key-for-mcp-apikey"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-apikey"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[Config.__table__, User.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[Config.__table__, User.__table__])
    engine.dispose()


@pytest.fixture
async def async_db():
    """审计日志异步会话（与 test_mcp_settings 同模式）。"""
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


def _token(username: str, user_id: int = 1) -> str:
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


async def _audit_rows(async_db: AsyncSession, operation_type: str) -> list:
    await async_db.commit()
    result = await async_db.execute(select(TorrentAuditLog).where(TorrentAuditLog.operation_type == operation_type))
    return list(result.scalars().all())


def _rotate(client: TestClient, expected_revision: int = 0, headers: dict | None = None):
    return client.post(
        "/api/v1/mcp/apikey/rotate",
        json={"expectedRevision": expected_revision},
        headers=headers if headers is not None else _auth(),
    )


# ==============================================================================
# GET /mcp/apikey：三态信封
# ==============================================================================


class TestGetApiKey:
    def test_absent_when_never_generated(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/mcp/apikey", headers=_auth())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success" and body["code"] == "200"
        data = body["data"]
        assert data["status"] == "absent"
        assert data["exists"] is False
        assert data["revision"] == 0
        assert "key" not in data  # 未生成不带明文
        assert data["keyPrefix"] == "btdmcp_"

    def test_active_returns_plaintext_key(self, client, db_session):
        _make_user(db_session)
        created = _rotate(client)
        assert created.status_code == 200
        key = created.json()["data"]["key"]

        resp = client.get("/api/v1/mcp/apikey", headers=_auth())
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["exists"] is True
        assert data["key"] == key  # 随时查看：明文可重复读取
        assert is_mcp_api_key_format(data["key"])
        assert data["revision"] == 1
        assert data["createdBy"] == "admin" and data["updatedBy"] == "admin"
        assert data["createdAt"] and data["updatedAt"]

    def test_unreadable_when_ciphertext_corrupted(self, client, db_session):
        """secret_key 轮换后存量密文失效：查看拒绝（unreadable），但行仍在。"""
        _make_user(db_session)
        _rotate(client)
        # 直改库中密文为「可解密但内容非密钥」的串，模拟解密结果不符合格式
        from app.utils.encryption import encrypt_password

        row = db_session.query(Config).filter(Config.key == MCP_APIKEY_CONFIG_KEY).first()
        payload = json.loads(row.value)
        payload["keyEncrypted"] = encrypt_password("not-a-key")
        row.value = json.dumps(payload, ensure_ascii=False)
        db_session.commit()

        resp = client.get("/api/v1/mcp/apikey", headers=_auth())
        data = resp.json()["data"]
        assert data["status"] == "unreadable"
        assert data["exists"] is True  # 行仍在（认证仍有效，仅查看不可用）
        assert "key" not in data
        assert data["revision"] == 1

    def test_broken_json_row_treated_as_absent(self, client, db_session):
        _make_user(db_session)
        db_session.add(Config(key=MCP_APIKEY_CONFIG_KEY, value="{broken", description="test"))
        db_session.commit()
        resp = client.get("/api/v1/mcp/apikey", headers=_auth())
        data = resp.json()["data"]
        assert data["status"] == "absent"
        assert data["revision"] == 0

    def test_envelope_shape_stable(self, client, db_session):
        """信封四字段不变（status/msg/code/data），data 内为密钥视图。"""
        _make_user(db_session)
        body = client.get("/api/v1/mcp/apikey", headers=_auth()).json()
        assert set(body.keys()) == {"status", "msg", "code", "data"}
        assert body["msg"] == "获取成功"


# ==============================================================================
# POST /mcp/apikey/rotate：CAS / 归属 / 审计
# ==============================================================================


class TestRotateApiKey:
    def test_create_with_expected_revision_zero(self, client, db_session):
        _make_user(db_session)
        resp = _rotate(client, 0)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["revision"] == 1
        assert is_mcp_api_key_format(data["key"])
        assert data["key"].startswith("btdmcp_")

    def test_rotate_replaces_previous_key(self, client, db_session):
        _make_user(db_session)
        first = _rotate(client, 0).json()["data"]["key"]
        second = _rotate(client, 1).json()["data"]
        assert second["revision"] == 2
        assert second["key"] != first

        # 旧密钥已被取代（GET 只能看到新密钥）
        current = client.get("/api/v1/mcp/apikey", headers=_auth()).json()["data"]
        assert current["key"] == second["key"]

    def test_conflict_returns_409_with_reason_code(self, client, db_session):
        _make_user(db_session)
        _rotate(client, 0)
        conflict = _rotate(client, 0)  # 过期 revision
        assert conflict.status_code == 409
        body = conflict.json()["detail"]
        assert body["data"]["reasonCode"] == "MCP_APIKEY_CONFLICT"
        assert body["data"]["currentRevision"] == 1
        assert body["code"] == "409"

    def test_conflict_keeps_existing_key(self, client, db_session):
        """409 不覆盖：并发 rotate 的败者保留胜者密钥（无 last-write-wins）。"""
        _make_user(db_session)
        first = _rotate(client, 0).json()["data"]["key"]
        second = _rotate(client, 1).json()["data"]["key"]
        _rotate(client, 0)  # 陈旧 revision → 409
        current = client.get("/api/v1/mcp/apikey", headers=_auth()).json()["data"]
        assert current["key"] == second
        assert current["key"] != first

    def test_negative_revision_rejected_by_schema(self, client, db_session):
        _make_user(db_session)
        resp = client.post("/api/v1/mcp/apikey/rotate", json={"expectedRevision": -1}, headers=_auth())
        assert resp.status_code == 422

    def test_rotate_rebinds_owner(self, client, db_session):
        """多用户：rotate 后归属=操作者（updatedBy 漂移可经审计追溯）。"""
        _make_user(db_session, "alice")
        _make_user(db_session, "bob")
        _rotate(client, 0, headers=_auth("alice", 1))
        data = _rotate(client, 1, headers=_auth("bob", 2)).json()["data"]
        assert data["updatedBy"] == "bob"
        assert data["createdBy"] == "alice"  # 创建者保留，归属以 updatedBy 为准


# ==============================================================================
# G3：控制面认证门禁（与 settings 端点同语义）
# ==============================================================================


class TestApiKeyControlPlaneAuth:
    def test_missing_token_401(self, client, db_session):
        _make_user(db_session)
        assert client.get("/api/v1/mcp/apikey").status_code == 401
        assert _rotate(client, 0, headers={}).status_code == 401

    def test_inactive_user_403(self, client, db_session):
        _make_user(db_session, "disabled", is_active=False)
        assert client.get("/api/v1/mcp/apikey", headers=_auth("disabled")).status_code == 403
        assert _rotate(client, 0, headers=_auth("disabled")).status_code == 403

    def test_must_change_password_403(self, client, db_session):
        _make_user(db_session, "resetting", must_change_password=True)
        assert client.get("/api/v1/mcp/apikey", headers=_auth("resetting")).status_code == 403
        assert _rotate(client, 0, headers=_auth("resetting")).status_code == 403

    def test_x_access_token_header_accepted(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/mcp/apikey", headers={"X-Access-Token": _token("admin", 1)})
        assert resp.status_code == 200


# ==============================================================================
# 审计：rotate 全量、查看仅 active、明细禁记密钥
# ==============================================================================


class TestApiKeyAudit:
    async def test_rotate_writes_audit_without_key_material(self, client, db_session, async_db):
        _make_user(db_session)
        resp = _rotate(client, 0)
        key = resp.json()["data"]["key"]

        rows = await _audit_rows(async_db, "mcp_apikey_rotate")
        assert len(rows) == 1
        entry = rows[0]
        assert entry.operator == "admin"
        assert entry.operation_result == "success"
        detail = json.loads(entry.operation_detail)
        assert detail["revision"] == 1
        assert detail["previousOwner"] is None  # 首次生成无前归属
        assert detail["rotatedBy"] == "admin"
        # 审计明细禁记密钥本体与哈希（防泄露面）
        assert key not in json.dumps(detail, ensure_ascii=False)

    async def test_second_rotate_records_previous_owner(self, client, db_session, async_db):
        _make_user(db_session, "alice")
        _make_user(db_session, "bob")
        _rotate(client, 0, headers=_auth("alice", 1))
        _rotate(client, 1, headers=_auth("bob", 2))

        rows = await _audit_rows(async_db, "mcp_apikey_rotate")
        assert len(rows) == 2
        latest = json.loads(rows[-1].operation_detail)
        assert latest["previousOwner"] == "alice"
        assert latest["rotatedBy"] == "bob"

    async def test_view_active_writes_audit(self, client, db_session, async_db):
        _make_user(db_session)
        _rotate(client, 0)
        client.get("/api/v1/mcp/apikey", headers=_auth())
        rows = await _audit_rows(async_db, "mcp_apikey_view")
        assert len(rows) == 1
        assert rows[0].operator == "admin"

    async def test_view_absent_writes_no_audit(self, client, db_session, async_db):
        """absent/unreadable 读取不写审计（避免面板挂载刷噪音）。"""
        _make_user(db_session)
        client.get("/api/v1/mcp/apikey", headers=_auth())
        assert await _audit_rows(async_db, "mcp_apikey_view") == []

    async def test_conflict_rotate_writes_no_audit(self, client, db_session, async_db):
        _make_user(db_session)
        _rotate(client, 0)
        _rotate(client, 0)  # 409
        rows = await _audit_rows(async_db, "mcp_apikey_rotate")
        assert len(rows) == 1


# ==============================================================================
# 双语目录：descriptionEn 与 description 成对下发
# ==============================================================================


class TestCatalogBilingualMeta:
    def test_catalog_carries_paired_english_description(self, client, db_session):
        _make_user(db_session)
        catalog = client.get("/api/v1/mcp/settings", headers=_auth()).json()["data"]["catalog"]
        assert [entry["code"] for entry in catalog] == list(CAPABILITY_CODES)
        for entry in catalog:
            assert entry["descriptionEn"], entry["code"]
            assert entry["description"], entry["code"]
            assert entry["descriptionEn"] != entry["description"]
            # 英文文案为 ASCII（中文不得混入 en 侧）
            assert entry["descriptionEn"].isascii(), entry["code"]
