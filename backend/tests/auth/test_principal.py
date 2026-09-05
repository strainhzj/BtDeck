"""认证内核（app/auth/principal.py）测试。

覆盖：token 缺失/无效/旧登录密钥、用户不存在/禁用/强制改密、
成功路径（payload user_id 优先 + 旧 token 回退 DB 主键）。
现有 HTTP 依赖不在本模块消费，语义零变化由全量回归保证。
"""

import pytest
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.models import Base, User
from app.auth.principal import (
    REASON_PASSWORD_CHANGE_REQUIRED,
    REASON_TOKEN_INVALID,
    REASON_TOKEN_MISSING,
    REASON_USER_INACTIVE,
    REASON_USER_NOT_FOUND,
    AuthenticatedPrincipal,
    PrincipalAuthenticationError,
    authenticate_access_token,
)
from app.auth.utils import create_access_token


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_user(db, *, username="alice", is_active=True, must_change_password=False):
    user = User(
        username=username,
        password="$2b$12$placeholderhashplaceholderhashplaceholderhashplace",
        is_active=is_active,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


TEST_LOGIN_SECRET = "test_secret_12345"


def _make_token(username="alice", user_id=None):
    """签发携带测试登录密钥的 token（create 不校验密钥，仅编码进 payload）。"""
    data = {"sub": username, "verify_secret": TEST_LOGIN_SECRET}
    if user_id is not None:
        data["user_id"] = str(user_id)
    return create_access_token(data.copy(), expires_delta=timedelta(minutes=5))


def _authenticate(token, db):
    """在登录密钥一致的补丁环境下执行认证（verify_access_token 运行时比对）。"""
    with patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET):
        return authenticate_access_token(token, db)


class TestAuthenticateAccessToken:
    def test_missing_token(self, db_session):
        with pytest.raises(PrincipalAuthenticationError) as exc_info:
            authenticate_access_token(None, db_session)
        assert exc_info.value.reason == REASON_TOKEN_MISSING

    def test_invalid_token(self, db_session):
        with pytest.raises(PrincipalAuthenticationError) as exc_info:
            authenticate_access_token("not-a-jwt", db_session)
        assert exc_info.value.reason == REASON_TOKEN_INVALID

    def test_stale_login_secret_token(self, db_session):
        """token 由旧登录密钥签发（verify_secret 不一致）→ 无效。"""
        _make_user(db_session)
        data = {"sub": "alice", "verify_secret": "old_secret"}
        with patch("app.auth.utils.get_login_secret", return_value="test_secret_12345"):
            token = create_access_token(data.copy(), expires_delta=timedelta(minutes=5))
        with pytest.raises(PrincipalAuthenticationError) as exc_info:
            _authenticate(token, db_session)
        assert exc_info.value.reason == REASON_TOKEN_INVALID

    def test_user_not_found(self, db_session):
        token = _make_token("ghost")
        with pytest.raises(PrincipalAuthenticationError) as exc_info:
            _authenticate(token, db_session)
        assert exc_info.value.reason == REASON_USER_NOT_FOUND

    def test_user_inactive(self, db_session):
        _make_user(db_session, is_active=False)
        token = _make_token("alice")
        with pytest.raises(PrincipalAuthenticationError) as exc_info:
            _authenticate(token, db_session)
        assert exc_info.value.reason == REASON_USER_INACTIVE

    def test_user_must_change_password(self, db_session):
        _make_user(db_session, must_change_password=True)
        token = _make_token("alice")
        with pytest.raises(PrincipalAuthenticationError) as exc_info:
            _authenticate(token, db_session)
        assert exc_info.value.reason == REASON_PASSWORD_CHANGE_REQUIRED

    def test_success_prefers_payload_user_id(self, db_session):
        user = _make_user(db_session)
        token = _make_token("alice", user_id=99)
        principal = _authenticate(token, db_session)
        assert isinstance(principal, AuthenticatedPrincipal)
        assert principal.user_id == 99
        assert principal.username == "alice"
        assert principal.is_active is True
        assert principal.must_change_password is False
        assert principal.token == token
        assert principal.payload["sub"] == "alice"

    def test_success_legacy_token_falls_back_to_db_id(self, db_session):
        """旧 token 不含 user_id → 回退数据库主键。"""
        user = _make_user(db_session)
        token = _make_token("alice")
        principal = _authenticate(token, db_session)
        assert principal.user_id == user.id
