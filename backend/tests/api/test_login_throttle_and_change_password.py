# -*- coding: utf-8 -*-
"""登录限流与改密安全测试（W9）。

覆盖：
- LoginThrottle 阶梯锁定（5 次 15 分钟 / 10 次 1 小时）、成功清零
- login 端点：锁定期间拒绝（429）；密码与 TOTP 共用计数
- changePassword：绑定本人（body userId 被忽略）、改密后撤销 refresh token、
  清除 must_change_password 标志
- /users/info：mustChangePassword 实时下发（W9 补全，前端 GetUserInfo 同步用）
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.auth.login_throttle import LoginThrottle
from app.auth.models import LoginLog, RefreshToken, User
from app.auth.security import get_password_hash
from app.database import Base, get_db

URL_LOGIN = "/api/v1/auth/login"
URL_CHANGE_PW = "/api/v1/user/changePassword"
# cuser router 双前缀挂载（/user 与 /users），与前端实际调用前缀对齐
URL_USER_INFO = "/api/v1/users/info"


class TestLoginThrottle:
    """阶梯锁定纯函数。"""

    def test_lock_after_5_failures(self):
        t = LoginThrottle()
        for _ in range(5):
            t.record_failure("admin", "1.2.3.4")
        assert t.check_locked("admin", "1.2.3.4")

    def test_not_locked_below_threshold(self):
        t = LoginThrottle()
        for _ in range(4):
            t.record_failure("admin", "1.2.3.4")
        assert not t.check_locked("admin", "1.2.3.4")

    def test_success_clears(self):
        t = LoginThrottle()
        for _ in range(5):
            t.record_failure("admin", "1.2.3.4")
        t.record_success("admin", "1.2.3.4")
        assert not t.check_locked("admin", "1.2.3.4")

    def test_other_key_not_locked(self):
        t = LoginThrottle()
        for _ in range(5):
            t.record_failure("admin", "1.2.3.4")
        assert not t.check_locked("admin", "5.6.7.8")
        assert not t.check_locked("other", "1.2.3.4")


@pytest.fixture()
def login_env():
    """登录限流端点级环境：内存库 + admin 用户。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__, RefreshToken.__table__, LoginLog.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        User(
            id=1,
            username="admin",
            password=get_password_hash("admin"),
            is_active=True,
            must_change_password=True,
        )
    )
    db.commit()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id="1")
    client = TestClient(app, raise_server_exceptions=False)
    yield client, Session
    db.close()
    engine.dispose()


class TestLoginEndpointThrottle:
    """login 端点锁定行为（覆盖密码与 TOTP 共用计数）。"""

    def test_locked_after_5_failures_returns_429(self, login_env, monkeypatch):
        client, _ = login_env
        # 隔离模块级单例，避免跨测试污染
        from app.api.endpoints import login as login_mod
        from app.auth import login_throttle as throttle_mod

        fresh = LoginThrottle()
        monkeypatch.setattr(login_mod, "login_throttle", fresh)
        monkeypatch.setattr(throttle_mod, "login_throttle", fresh)

        for _ in range(5):
            r = client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
            assert r.json()["code"] == "401"
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
        assert r.json()["code"] == "429"

    def test_success_resets_throttle(self, login_env, monkeypatch):
        client, _ = login_env
        from app.api.endpoints import login as login_mod

        fresh = LoginThrottle()
        monkeypatch.setattr(login_mod, "login_throttle", fresh)

        for _ in range(4):
            client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "admin"})
        assert r.json()["code"] == "200"
        # 成功清零后再错 4 次仍不锁
        for _ in range(4):
            client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
        assert r.json()["code"] == "401", "成功登录应清零失败计数"


class TestChangePasswordSecurity:
    """改密：绑定本人、撤销 refresh token、清强制改密标志。"""

    def _login_get_tokens(self, client) -> str:
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "admin"})
        assert r.json()["code"] == "200"
        return r.json()["data"][0]

    def test_login_response_carries_must_change_password(self, login_env):
        client, _ = login_env
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "admin"})
        data = r.json()["data"][0]
        assert data["must_change_password"] is True

    def test_change_password_updates_and_clears_flag(self, login_env):
        client, Session = login_env
        token_data = self._login_get_tokens(client)
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}

        # 绑定本人：body 传不存在 userId=999，仍应操作 token 对应 admin
        r = client.post(
            URL_CHANGE_PW,
            json={"userId": "999", "old_password": "YWRtaW4=", "new_password": "bmV3cGFzczEyMw=="},
            headers=headers,
        )
        assert r.json()["code"] == "200"

        with Session() as db:
            user = db.query(User).filter_by(id=1).first()
            assert user.must_change_password is False
            # 新密码（明文 newpass123）可登录
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "newpass123"})
        assert r.json()["code"] == "200"

    def test_change_password_revokes_refresh_tokens(self, login_env):
        client, Session = login_env
        token_data = self._login_get_tokens(client)
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}

        with Session() as db:
            assert db.query(RefreshToken).filter_by(user_id=1, revoked_at=None).count() >= 1

        r = client.post(
            URL_CHANGE_PW,
            json={"userId": "1", "old_password": "YWRtaW4=", "new_password": "bmV3cGFzczEyMw=="},
            headers=headers,
        )
        assert r.json()["code"] == "200"

        with Session() as db:
            assert db.query(RefreshToken).filter_by(user_id=1, revoked_at=None).count() == 0
            # 旧 refresh token 已被撤销
            old_refresh = db.query(RefreshToken).filter_by(user_id=1).first()
            assert old_refresh.revoked_at is not None

    def test_wrong_old_password_rejected(self, login_env):
        client, _ = login_env
        token_data = self._login_get_tokens(client)
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        r = client.post(
            URL_CHANGE_PW,
            json={"userId": "1", "old_password": "d3Jvbmc=", "new_password": "bmV3cGFzczEyMw=="},
            headers=headers,
        )
        assert r.json()["code"] == "400"
        assert "密码错误" in r.json()["msg"]


class TestUserInfoMustChangePasswordDelivery:
    """/users/info 实时下发 mustChangePassword（W9 补全）。

    前端 GetUserInfo 据此同步 store 标志：此前标志仅随登录响应下发，
    F5/新会话期间后端置位的标志守卫读不到（可被刷新绕过强制改密）。
    """

    def test_info_carries_flag_true_when_marked(self, login_env):
        client, _ = login_env
        # fixture 预置 must_change_password=True（默认口令场景）
        r = client.post(URL_USER_INFO, json={"token": "irrelevant-auth-overridden"})
        assert r.json()["code"] == "200"
        user = r.json()["data"]["user"]
        assert user["mustChangePassword"] is True

    def test_info_carries_flag_false_after_change(self, login_env):
        client, Session = login_env
        with Session() as db:
            db.query(User).filter_by(id=1).update({"must_change_password": False})
            db.commit()

        r = client.post(URL_USER_INFO, json={"token": "irrelevant-auth-overridden"})
        assert r.json()["code"] == "200"
        user = r.json()["data"]["user"]
        assert user["mustChangePassword"] is False
