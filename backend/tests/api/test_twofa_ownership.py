# -*- coding: utf-8 -*-
"""2FA 端点本人绑定与日志脱敏测试（W10）。

安全背景：2faVerifyCode/2faVerifyQrCode/update2faFlg/verifyPasswordFor2FA
历史实现仅要求登录态，任意已认证用户可读取/重置他人 TOTP secret。
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
from app.database import Base, get_db
from app.auth.models import User


@pytest.fixture()
def client_factory(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        User(
            id=1,
            username="admin",
            password="x",
            two_factor_secret="LEGACY_SECRET_123",
            two_factor_flag="0",
        )
    )
    db.add(
        User(
            id=2,
            username="other",
            password="x",
            two_factor_secret="OTHER_SECRET_456",
            two_factor_flag="0",
        )
    )
    db.commit()

    def _make_client(current_user_id=1):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
            username="admin", user_id=str(current_user_id)
        )
        return TestClient(app, raise_server_exceptions=False), Session

    yield _make_client
    db.close()
    engine.dispose()


class TestTwofaOwnership:
    """4 个 2FA 端点的本人绑定校验。"""

    def test_2fa_verify_code_self_allowed(self, client_factory):
        c, _ = client_factory(current_user_id=1)
        r = c.get("/api/v1/users/2faVerifyCode/1")
        assert r.json() == "LEGACY_SECRET_123"

    def test_2fa_verify_code_other_denied(self, client_factory):
        c, _ = client_factory(current_user_id=1)
        r = c.get("/api/v1/users/2faVerifyCode/2")
        assert r.json() == ""

    def test_2fa_verify_qrcode_other_denied(self, client_factory):
        c, _ = client_factory(current_user_id=1)
        r = c.get("/api/v1/users/2faVerifyQrCode/2")
        assert r.json() == ""

    def test_update2fa_flag_other_denied(self, client_factory):
        c, _ = client_factory(current_user_id=1)
        r = c.post("/api/v1/users/update2faFlg/2", json={"userId": "2", "twofaFlag": "0"})
        assert r.json()["code"] == "403"

    def test_verify_password_for_2fa_other_denied(self, client_factory):
        c, _ = client_factory(current_user_id=1)
        r = c.post("/api/v1/users/verifyPasswordFor2FA", json={"userId": "2", "password": "whatever"})
        assert r.json()["code"] == "403"
