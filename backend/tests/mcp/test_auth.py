# -*- coding: utf-8 -*-
"""MCP transport 认证接线回归（feature mcp-service-capabilities-2026-08-28 W2，G3）。

覆盖计划 §4.4 与 §7 认证矩阵：

- token → principal 全链（真 User 行 + 真 JWT，复用 principal 内核）；
- 拒绝矩阵：缺失/无效/用户不存在/禁用/强制改密 → 稳定码逐一对应；
- 未知拒绝原因码兜底 AUTH_TOKEN_INVALID（fail-closed，映射表漂移不放行）；
- 认证内核意外异常 → INTERNAL_ERROR（不外泄异常文本）；
- transport 侧 token 提取：Authorization Bearer / X-Access-Token / 缺失 /
  形态不符 / 请求对象异常。

不依赖 MCP SDK（认证接线层协议无关）。
"""

from typing import Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import utils as auth_utils
from app.auth.models import User
from app.auth.principal import PrincipalAuthenticationError
from app.database import Base
from app.mcp.auth import authenticate_token, extract_token_from_request
from app.mcp.errors import McpErrorCode, McpToolError

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
