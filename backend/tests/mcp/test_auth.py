# -*- coding: utf-8 -*-
"""MCP transport 认证接线回归（feature mcp-service-capabilities-2026-08-28 W2，G3）。

覆盖计划 §4.4 与 §7 认证矩阵：

- token → principal 全链（真 User 行 + 真 JWT，复用 principal 内核）；
- 拒绝矩阵：缺失/无效/用户不存在/禁用/强制改密 → 稳定码逐一对应；
- 未知拒绝原因码兜底 AUTH_TOKEN_INVALID（fail-closed，映射表漂移不放行）；
- 认证内核意外异常 → INTERNAL_ERROR（不外泄异常文本）；
- transport 侧 token 提取：Authorization Bearer / X-Access-Token / 缺失 /
  形态不符 / 请求对象异常；
- W5 服务密钥路径：`btdmcp_` 前缀路由 → 哈希校验 + 归属用户状态校验；
  无效/缺失/行损坏 → AUTH_API_KEY_INVALID（与 JWT 失败分开）；归属用户
  不存在/禁用/强制改密 → 既有 USER_* 原因码；rotate 后旧密钥即失效；
  密文损坏只影响「查看」不影响认证（哈希为唯一事实源）；两种认证并存。

不依赖 MCP SDK（认证接线层协议无关）。
"""

import json
from typing import Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import utils as auth_utils
from app.auth.models import Config, User
from app.auth.principal import PrincipalAuthenticationError
from app.database import Base
from app.mcp.auth import authenticate_token, extract_token_from_request
from app.mcp.contracts import MCP_APIKEY_CONFIG_KEY, MCP_APIKEY_PREFIX, generate_mcp_api_key, hash_mcp_api_key
from app.mcp.errors import McpErrorCode, McpToolError
from app.services.mcp_apikey_service import McpApiKeyService

TEST_SECRET = "test-secret-key-for-mcp-auth"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-auth"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[User.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[User.__table__])


def _make_user(db: Session, username: str = "admin", **overrides) -> User:
    user = User(
        username=username,
        password="not-a-real-hash",
        is_active=overrides.get("is_active", True),
        must_change_password=overrides.get("must_change_password", False),
    )
    db.add(user)
    db.commit()
    return user


def _token(username: str = "admin", user_id: int = 1) -> str:
    return auth_utils.create_access_token(
        {"sub": username, "user_id": str(user_id), "verify_secret": TEST_LOGIN_SECRET}
    )


@pytest.fixture(autouse=True)
def _auth_utils_patch():
    mock_settings = MagicMock()
    mock_settings.SECRET_KEY = TEST_SECRET
    mock_settings.ALGORITHM = "HS256"
    mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    with (
        patch("app.auth.utils.settings", mock_settings),
        patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET),
    ):
        yield


# ==============================================================================
# authenticate_token：token → principal 全链
# ==============================================================================


class TestAuthenticateToken:
    def test_valid_token_returns_principal(self, db_session):
        _make_user(db_session, "admin")

        principal = authenticate_token(_token("admin"), db_session)

        assert principal.username == "admin"
        assert principal.user_id == 1
        assert principal.is_active is True
        assert principal.must_change_password is False
        assert principal.token

    def test_missing_token_auth_required(self, db_session):
        _make_user(db_session, "admin")
        with pytest.raises(McpToolError) as exc:
            authenticate_token(None, db_session)
        assert exc.value.code is McpErrorCode.AUTH_REQUIRED

    def test_invalid_token_rejected(self, db_session):
        _make_user(db_session, "admin")
        with pytest.raises(McpToolError) as exc:
            authenticate_token("not-a-jwt", db_session)
        assert exc.value.code is McpErrorCode.AUTH_TOKEN_INVALID

    def test_tampered_login_secret_rejected(self, db_session):
        _make_user(db_session, "admin")
        other = auth_utils.create_access_token(
            {"sub": "admin", "user_id": "1", "verify_secret": "another-login-secret"}
        )
        with pytest.raises(McpToolError) as exc:
            authenticate_token(other, db_session)
        assert exc.value.code is McpErrorCode.AUTH_TOKEN_INVALID

    def test_user_not_found(self, db_session):
        with pytest.raises(McpToolError) as exc:
            authenticate_token(_token("ghost"), db_session)
        assert exc.value.code is McpErrorCode.AUTH_USER_NOT_FOUND

    def test_inactive_user_rejected(self, db_session):
        _make_user(db_session, "disabled-user", is_active=False)
        with pytest.raises(McpToolError) as exc:
            authenticate_token(_token("disabled-user"), db_session)
        assert exc.value.code is McpErrorCode.AUTH_USER_INACTIVE

    def test_must_change_password_rejected(self, db_session):
        _make_user(db_session, "resetting", must_change_password=True)
        with pytest.raises(McpToolError) as exc:
            authenticate_token(_token("resetting"), db_session)
        assert exc.value.code is McpErrorCode.PASSWORD_CHANGE_REQUIRED

    def test_unmapped_reason_falls_back_token_invalid(self, db_session, monkeypatch):
        """映射表未登记的新拒绝原因不得演变为放行或裸异常（fail-closed 兜底）。"""

        def _raise_unmapped(token, db):
            raise PrincipalAuthenticationError("SOME_FUTURE_REASON", "内部细节")

        monkeypatch.setattr("app.mcp.auth.authenticate_access_token", _raise_unmapped)
        with pytest.raises(McpToolError) as exc:
            authenticate_token("any", db_session)
        assert exc.value.code is McpErrorCode.AUTH_TOKEN_INVALID

    def test_kernel_crash_maps_internal_error(self, db_session, monkeypatch):
        def _crash(token, db):
            raise RuntimeError("disk on fire at C:\\db\\secret")

        monkeypatch.setattr("app.mcp.auth.authenticate_access_token", _crash)
        with pytest.raises(McpToolError) as exc:
            authenticate_token("any", db_session)
        assert exc.value.code is McpErrorCode.INTERNAL_ERROR
        assert "disk on fire" not in exc.value.message  # 固定文案，不外泄异常文本

    def test_error_message_is_fixed_default(self, db_session):
        with pytest.raises(McpToolError) as exc:
            authenticate_token(None, db_session)
        assert exc.value.message == "缺少访问令牌。"


# ==============================================================================
# extract_token_from_request：transport header 面
# ==============================================================================


class _FakeRequest:
    """starlette Request 的最小 header 面替身（_extract_access_token 只用 headers.get）。"""

    def __init__(self, headers: Optional[Dict[str, str]] = None, broken: bool = False):
        self.headers = _BrokenHeaders() if broken else (headers or {})


class _BrokenHeaders:
    def get(self, name: str) -> str:
        raise RuntimeError("header access crashed")


class TestExtractTokenFromRequest:
    def test_bearer_token(self):
        req = _FakeRequest({"authorization": "Bearer abc.def.ghi"})
        assert extract_token_from_request(req) == "abc.def.ghi"

    def test_bearer_case_insensitive_scheme(self):
        req = _FakeRequest({"authorization": "bearer abc.def.ghi"})
        assert extract_token_from_request(req) == "abc.def.ghi"

    def test_x_access_token_preferred(self):
        req = _FakeRequest({"x-access-token": "token-x", "authorization": "Bearer token-b"})
        assert extract_token_from_request(req) == "token-x"

    def test_missing_everything(self):
        assert extract_token_from_request(_FakeRequest()) is None
        assert extract_token_from_request(None) is None

    def test_malformed_authorization_ignored(self):
        req = _FakeRequest({"authorization": "Basic dXNlcjpwYXNz"})
        assert extract_token_from_request(req) is None

    def test_broken_request_object_fails_closed(self):
        # header 面异常按未携带处理，不得放行也不得外泄异常
        assert extract_token_from_request(_FakeRequest(broken=True)) is None


# ==============================================================================
# W5 服务密钥路径：btdmcp_ 前缀路由 → 哈希校验 + 归属用户状态校验
# ==============================================================================


@pytest.fixture
def apikey_db():
    """User + Config 双表内存库（服务密钥存 configs.mcp.apikey.v1）。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[User.__table__, Config.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[User.__table__, Config.__table__])
    engine.dispose()


def _rotate_key(db: Session, owner: str) -> str:
    """经服务层真实 rotate 生成密钥（SM4 加密副本 + 哈希，round-trip 用）。"""
    return McpApiKeyService(db).rotate(rotated_by=owner, expected_revision=0).key


def _seed_key_row(db: Session, *, key_hash: str, owner: str = "admin", encrypted: str = "sm4:00") -> None:
    """直写 configs 行（绕开加密组件，用于哈希面/损坏面定向用例）。"""
    db.add(
        Config(
            key=MCP_APIKEY_CONFIG_KEY,
            value=json.dumps(
                {
                    "schemaVersion": 1,
                    "keyHash": key_hash,
                    "keyEncrypted": encrypted,
                    "revision": 1,
                    "createdAt": "2026-09-22T00:00:00+00:00",
                    "createdBy": owner,
                    "updatedAt": "2026-09-22T00:00:00+00:00",
                    "updatedBy": owner,
                },
                ensure_ascii=False,
            ),
            description="test",
        )
    )
    db.commit()


class TestApiKeyAuthentication:
    """密钥路径认证矩阵（与 JWT 路径并列，互不影响）。"""

    def test_valid_api_key_returns_principal(self, apikey_db):
        _make_user(apikey_db, "admin")
        key = _rotate_key(apikey_db, "admin")

        principal = authenticate_token(key, apikey_db)

        assert principal.username == "admin"
        assert principal.user_id == 1
        assert principal.payload.get("auth_method") == "api_key"
        # 原始密钥不驻留主体对象（凭据最小化）
        assert principal.token == ""

    def test_valid_format_wrong_key_rejected(self, apikey_db):
        _make_user(apikey_db, "admin")
        _rotate_key(apikey_db, "admin")
        wrong = generate_mcp_api_key()
        assert wrong.startswith(MCP_APIKEY_PREFIX)

        with pytest.raises(McpToolError) as exc:
            authenticate_token(wrong, apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_API_KEY_INVALID

    def test_no_key_row_rejected(self, apikey_db):
        _make_user(apikey_db, "admin")
        with pytest.raises(McpToolError) as exc:
            authenticate_token(generate_mcp_api_key(), apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_API_KEY_INVALID

    def test_prefix_only_token_rejected(self, apikey_db):
        _make_user(apikey_db, "admin")
        _rotate_key(apikey_db, "admin")
        with pytest.raises(McpToolError) as exc:
            authenticate_token(MCP_APIKEY_PREFIX, apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_API_KEY_INVALID

    def test_corrupt_json_row_rejected(self, apikey_db):
        _make_user(apikey_db, "admin")
        apikey_db.add(Config(key=MCP_APIKEY_CONFIG_KEY, value="{not-json", description="test"))
        apikey_db.commit()
        with pytest.raises(McpToolError) as exc:
            authenticate_token(generate_mcp_api_key(), apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_API_KEY_INVALID

    def test_owner_missing_rejected(self, apikey_db):
        # 行在、归属用户已被删除（哈希匹配，但 principal 加载失败）
        known = generate_mcp_api_key()
        _seed_key_row(apikey_db, key_hash=hash_mcp_api_key(known), owner="ghost")
        with pytest.raises(McpToolError) as exc:
            authenticate_token(known, apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_USER_NOT_FOUND

    def test_owner_inactive_rejected(self, apikey_db):
        _make_user(apikey_db, "disabled-owner", is_active=False)
        known = generate_mcp_api_key()
        _seed_key_row(apikey_db, key_hash=hash_mcp_api_key(known), owner="disabled-owner")
        with pytest.raises(McpToolError) as exc:
            authenticate_token(known, apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_USER_INACTIVE

    def test_owner_must_change_password_rejected(self, apikey_db):
        _make_user(apikey_db, "resetting-owner", must_change_password=True)
        known = generate_mcp_api_key()
        _seed_key_row(apikey_db, key_hash=hash_mcp_api_key(known), owner="resetting-owner")
        with pytest.raises(McpToolError) as exc:
            authenticate_token(known, apikey_db)
        assert exc.value.code is McpErrorCode.PASSWORD_CHANGE_REQUIRED

    def test_rotation_invalidates_old_key(self, apikey_db):
        _make_user(apikey_db, "admin")
        old_key = _rotate_key(apikey_db, "admin")
        state = McpApiKeyService(apikey_db).get_view()
        new_key = McpApiKeyService(apikey_db).rotate(rotated_by="admin", expected_revision=state["revision"]).key

        # 旧密钥立即失效，新密钥可用
        with pytest.raises(McpToolError) as exc:
            authenticate_token(old_key, apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_API_KEY_INVALID
        assert authenticate_token(new_key, apikey_db).username == "admin"

    def test_rotation_rebinds_owner(self, apikey_db):
        """rotate 后归属=操作者：旧 owner 的密钥失效，新 owner 的密钥可用。"""
        _make_user(apikey_db, "alice")
        _make_user(apikey_db, "bob")
        alice_key = _rotate_key(apikey_db, "alice")
        state = McpApiKeyService(apikey_db).get_view()
        bob_key = McpApiKeyService(apikey_db).rotate(rotated_by="bob", expected_revision=state["revision"]).key

        with pytest.raises(McpToolError) as exc:
            authenticate_token(alice_key, apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_API_KEY_INVALID
        assert authenticate_token(bob_key, apikey_db).username == "bob"

    def test_unreadable_ciphertext_still_authenticates(self, apikey_db):
        """密文损坏（secret_key 轮换场景）只影响「查看」，不影响认证。"""
        _make_user(apikey_db, "admin")
        key = _rotate_key(apikey_db, "admin")
        # 把加密副本替换为「可解密但内容不是密钥」的密文 → 视图态 unreadable
        from app.utils.encryption import encrypt_password

        row = apikey_db.query(Config).filter(Config.key == MCP_APIKEY_CONFIG_KEY).first()
        payload = json.loads(row.value)
        payload["keyEncrypted"] = encrypt_password("garbage-not-a-key")
        row.value = json.dumps(payload, ensure_ascii=False)
        apikey_db.commit()

        view = McpApiKeyService(apikey_db).get_view()
        assert view["status"] == "unreadable"
        assert "key" not in view
        # 哈希仍为认证事实源
        assert authenticate_token(key, apikey_db).username == "admin"

    def test_jwt_and_api_key_coexist(self, apikey_db):
        """两种认证并存：密钥存在时 JWT 路径不受影响。"""
        _make_user(apikey_db, "admin")
        key = _rotate_key(apikey_db, "admin")

        jwt_principal = authenticate_token(_token("admin"), apikey_db)
        assert jwt_principal.username == "admin"
        assert jwt_principal.token  # JWT 路径保留原始 token 溯源
        assert "auth_method" not in jwt_principal.payload

        key_principal = authenticate_token(key, apikey_db)
        assert key_principal.username == "admin"
        assert key_principal.payload.get("auth_method") == "api_key"

    def test_missing_token_still_auth_required(self, apikey_db):
        _make_user(apikey_db, "admin")
        with pytest.raises(McpToolError) as exc:
            authenticate_token(None, apikey_db)
        assert exc.value.code is McpErrorCode.AUTH_REQUIRED
