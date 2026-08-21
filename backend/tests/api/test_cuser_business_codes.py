# -*- coding: utf-8 -*-
"""cuser 端点业务错误码语义回归（令牌机制对抗审计修复）。

保护点：非认证失败不得复用业务 code 401——前端把 401 一律视为认证失败
（静默续期 → 重放 → 登出），2FA 流程输错一次密码就会把在线用户误踢回
登录页并看到误导性的「登录状态已过期」提示。用户输入错误应为 400，
服务端异常兜底应为 500（前端按瞬时故障保留会话现场）。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.auth.models import User
from app.database import Base, get_db

UPDATE_2FA_URL = "/api/v1/users/update2faFlg/1"
VERIFY_PASSWORD_URL = "/api/v1/users/verifyPasswordFor2FA"


@pytest.fixture()
def client_factory():
    """flag 参数化：停用分支需 flag=1，verifyPasswordFor2FA 密码分支需 flag=0
    （端点先检查"已启用拒绝重复绑定"，再校验密码）。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    Session = sessionmaker(bind=engine)

    def _make_client(flag="1"):
        with Session() as db:
            db.add(User(id=1, username="admin", password="x", two_factor_secret="SECRET123", two_factor_flag=flag))
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
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id=1)
        return TestClient(app, raise_server_exceptions=False)

    yield _make_client
    engine.dispose()


class TestUpdate2faBusinessCodes:
    """停用/启用 2FA 的输入错误必须是 400，不是 401。"""

    def test_disable_missing_password_returns_400(self, client_factory):
        client = client_factory()
        r = client.post(UPDATE_2FA_URL, json={"userId": "1", "twofaFlag": "0"})
        assert r.json()["code"] == "400"

    def test_disable_wrong_password_returns_400(self, client_factory):
        client = client_factory()
        with patch("app.api.endpoints.cuser.security.verify_password", return_value=False):
            r = client.post(UPDATE_2FA_URL, json={"userId": "1", "twofaFlag": "0", "password": "wrong"})
        body = r.json()
        assert body["code"] == "400"
        assert body["msg"] == "密码错误"

    def test_disable_missing_code_returns_400(self, client_factory):
        client = client_factory()
        with patch("app.api.endpoints.cuser.security.verify_password", return_value=True):
            r = client.post(UPDATE_2FA_URL, json={"userId": "1", "twofaFlag": "0", "password": "right"})
        assert r.json()["code"] == "400"

    def test_disable_wrong_totp_returns_400(self, client_factory):
        client = client_factory()
        with (
            patch("app.api.endpoints.cuser.security.verify_password", return_value=True),
            patch("app.api.endpoints.cuser.utils.verify_totp", return_value=False),
        ):
            r = client.post(
                UPDATE_2FA_URL,
                json={"userId": "1", "twofaFlag": "0", "password": "right", "twoFactorCode": "000000"},
            )
        body = r.json()
        assert body["code"] == "400"
        assert body["msg"] == "双因素验证码错误"


class TestEnable2faWithDisabledUser:
    """启用 2FA（flag=0 用户）的输入错误必须是 400。"""

    @pytest.fixture()
    def enable_client(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine, tables=[User.__table__])
        Session = sessionmaker(bind=engine)
        db = Session()
        db.add(User(id=1, username="admin", password="x", two_factor_secret="SECRET123", two_factor_flag="0"))
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
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id=1)
        client = TestClient(app, raise_server_exceptions=False)
        yield client
        db.close()
        engine.dispose()

    def test_enable_missing_code_returns_400(self, enable_client):
        r = enable_client.post(UPDATE_2FA_URL, json={"userId": "1", "twofaFlag": "1"})
        assert r.json()["code"] == "400"
        assert r.json()["msg"] == "启用2fa验证需要提供验证码"

    def test_enable_wrong_totp_returns_400(self, enable_client):
        with patch("app.api.endpoints.cuser.utils.verify_totp", return_value=False):
            r = enable_client.post(UPDATE_2FA_URL, json={"userId": "1", "twofaFlag": "1", "twoFactorCode": "000000"})
        body = r.json()
        assert body["code"] == "400"
        assert body["msg"] == "验证码错误，请检查认证器应用中的6位数字"


class TestVerifyPasswordFor2fa:
    def test_wrong_password_returns_400(self, client_factory):
        client = client_factory(flag="0")
        with patch("app.api.endpoints.cuser.security.verify_password", return_value=False):
            r = client.post(VERIFY_PASSWORD_URL, json={"userId": "1", "password": "wrong"})
        body = r.json()
        assert body["code"] == "400"
        assert body["msg"] == "密码错误"


class TestInfoServerErrorReturns500:
    """/info 的异常兜底必须是 500：业务 401 会让前端把 DB 抖动当认证失败，
    续期→重放→登出，误踢在线用户。"""

    def test_db_exception_returns_500(self):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        class BoomSession:
            def query(self, *args, **kwargs):
                raise RuntimeError("db down")

        def override_get_db():
            yield BoomSession()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id=1)
        client = TestClient(app, raise_server_exceptions=False)

        r = client.post("/api/v1/user/info")
        body = r.json()
        assert body["code"] == "500"
        assert "获取用户信息失败" in body["msg"]


class TestTokenDefect401SemanticsPreserved:
    """保留的 2 处业务 401（token 缺陷）语义不得被"顺手"改成 400/500：

    前端对这两类 401 走静默续期→重放链路，refresh 端点会从 DB 重建
    sub/user_id（login.py 签发时必含），重放即自愈——改成 400/500 反而
    会把旧格式 token 用户卡死在错误提示上。"""

    def _make_client(self, user_info):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")
        app.dependency_overrides[get_db] = lambda: iter([None])
        app.dependency_overrides[require_authenticated_user] = lambda: user_info
        return TestClient(app, raise_server_exceptions=False)

    def test_info_missing_username_returns_401(self):
        client = self._make_client(SimpleNamespace(username="", user_id=1))
        r = client.post("/api/v1/user/info")
        assert r.json()["code"] == "401"

    def test_change_password_missing_user_id_returns_401(self):
        client = self._make_client(SimpleNamespace(username="admin", user_id=None))
        r = client.post(
            "/api/v1/user/changePassword",
            json={"oldPassword": "a", "newPassword": "b", "userId": "1"},
        )
        assert r.json()["code"] == "401"
