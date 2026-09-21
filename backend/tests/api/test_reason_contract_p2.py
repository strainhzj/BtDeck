# -*- coding: utf-8 -*-
"""双语 P2 错误契约测试（M1 子集）。

锁定的不变量（PLANS/bilingual/error-contract.md §1 原则）：
- CommonResponse 信封四字段不变；仅 data 新增 reasonCode 字段；
- 前端依赖 reasonCode 本地化展示（禁止按中文 msg 匹配），因此 reasonCode
  取值属于对外契约，本文件逐路径钉死；
- 动态拼接 msg（str(e)）已收敛为固定 msg + 日志，防止信息泄露与不可翻译。
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
from app.downloader.models import BtDownloaders

URL_LOGIN = "/api/v1/auth/login"
URL_CHANGE_PW = "/api/v1/user/changePassword"
URL_VERIFY_2FA_PW = "/api/v1/user/verifyPasswordFor2FA"


def _reason_code(body: dict) -> str:
    data = body["data"]
    assert isinstance(data, dict), f"data 应为携带 reasonCode 的 dict，实际: {data!r}"
    return data["reasonCode"]


@pytest.fixture()
def contract_env():
    """内存库 + admin 用户（可选启用 2FA）。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, RefreshToken.__table__, LoginLog.__table__, BtDownloaders.__table__],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        User(
            id=1,
            username="admin",
            password=get_password_hash("admin"),
            is_active=True,
            must_change_password=False,
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


class TestLoginReasonCodes:
    """登录端点错误契约。"""

    def test_wrong_password_carries_invalid_credentials(self, contract_env, monkeypatch):
        client, _ = contract_env
        from app.api.endpoints import login as login_mod

        monkeypatch.setattr(login_mod, "login_throttle", LoginThrottle())
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
        body = r.json()
        assert body["code"] == "401"
        assert body["status"] == "error"
        assert _reason_code(body) == "AUTH_INVALID_CREDENTIALS"

    def test_locked_carries_rate_limited(self, contract_env, monkeypatch):
        client, _ = contract_env
        from app.api.endpoints import login as login_mod

        monkeypatch.setattr(login_mod, "login_throttle", LoginThrottle())
        for _ in range(5):
            client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
        r = client.post(URL_LOGIN, json={"username": "admin", "password": "wrong"})
        body = r.json()
        assert body["code"] == "429"
        assert _reason_code(body) == "AUTH_RATE_LIMITED"

    def _enable_2fa(self, Session, secret="JBSWY3DPEHPK3PXP"):
        s = Session()
        user = s.query(User).filter(User.id == 1).first()
        user.two_factor_flag = "1"
        user.two_factor_secret = secret
        s.commit()
        s.close()

    def test_2fa_missing_code_and_wrong_code(self, contract_env, monkeypatch):
        client, Session = contract_env
        from app.api.endpoints import login as login_mod

        monkeypatch.setattr(login_mod, "login_throttle", LoginThrottle())
        self._enable_2fa(Session)

        r = client.post(URL_LOGIN, json={"username": "admin", "password": "admin"})
        body = r.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "AUTH_TOTP_REQUIRED"

        r = client.post(URL_LOGIN, json={"username": "admin", "password": "admin", "twofa_code": "000000"})
        body = r.json()
        assert body["code"] == "401"
        assert _reason_code(body) == "AUTH_TOTP_INVALID"


class TestChangePasswordReasonCodes:
    """改密端点错误契约。"""

    def test_wrong_old_password(self, contract_env):
        client, _ = contract_env
        import base64

        r = client.post(
            URL_CHANGE_PW,
            json={
                "userId": "1",
                "oldPassword": base64.b64encode("wrong".encode()).decode(),
                "newPassword": base64.b64encode("newpass".encode()).decode(),
            },
        )
        body = r.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "USER_ORIG_PASSWORD_INVALID"


class TestTwofaReasonCodes:
    """2FA 绑定/停用端点错误契约。"""

    def test_verify_password_wrong(self, contract_env):
        client, _ = contract_env
        r = client.post(URL_VERIFY_2FA_PW, json={"userId": "1", "password": "wrong"})
        body = r.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "2FA_PASSWORD_INVALID"

    def test_verify_password_already_enabled(self, contract_env):
        client, Session = contract_env
        s = Session()
        user = s.query(User).filter(User.id == 1).first()
        user.two_factor_flag = "1"
        s.commit()
        s.close()
        r = client.post(URL_VERIFY_2FA_PW, json={"userId": "1", "password": "admin"})
        body = r.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "2FA_ALREADY_ENABLED"

    def test_disable_missing_password(self, contract_env):
        client, Session = contract_env
        s = Session()
        user = s.query(User).filter(User.id == 1).first()
        user.two_factor_flag = "1"
        user.two_factor_secret = "JBSWY3DPEHPK3PXP"
        s.commit()
        s.close()
        r = client.post(
            "/api/v1/user/update2faFlg/1",
            json={"userId": "1", "twofaFlag": "0", "twoFactorCode": "123456"},
        )
        body = r.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "2FA_PASSWORD_REQUIRED"

    def test_disable_wrong_password(self, contract_env):
        client, Session = contract_env
        s = Session()
        user = s.query(User).filter(User.id == 1).first()
        user.two_factor_flag = "1"
        user.two_factor_secret = "JBSWY3DPEHPK3PXP"
        s.commit()
        s.close()
        r = client.post(
            "/api/v1/user/update2faFlg/1",
            json={"userId": "1", "twofaFlag": "0", "password": "wrong", "twoFactorCode": "123456"},
        )
        body = r.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "2FA_PASSWORD_INVALID"

    def test_invalid_operation(self, contract_env):
        client, _ = contract_env
        r = client.post("/api/v1/user/update2faFlg/1", json={"userId": "1", "twofaFlag": "x"})
        body = r.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "2FA_INVALID_OPERATION"


class TestDownloaderReasonCodes:
    """下载器端点错误契约（404 族）。路由前缀为 /downloader（单数）。"""

    def test_test_connection_not_found(self, contract_env):
        client, _ = contract_env
        r = client.post("/api/v1/downloader/test/dl-not-exist")
        body = r.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "DOWNLOADER_NOT_FOUND"

    def test_update_not_found(self, contract_env):
        client, _ = contract_env
        r = client.post(
            "/api/v1/downloader/update/dl-not-exist",
            json={"nickname": "n"},
        )
        body = r.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "DOWNLOADER_NOT_FOUND"
