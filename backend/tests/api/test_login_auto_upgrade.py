# -*- coding: utf-8 -*-
"""登录自动升级 bcrypt 回归测试（W8）。

保护点（防回归）：
1. 旧格式（AES-ECB 可逆密文）用户登录成功后，密码必须自动升级为 bcrypt
   （$2b$ 前缀）——若未来有人删掉升级分支，存量用户将永远停留在可逆存储；
2. 升级用条件更新（WHERE password=:old_val）——并发改密交错时不得把
   新密码回滚成旧密码的 bcrypt；
3. 新格式用户登录不触发无谓 UPDATE（bcrypt 已是最新格式）。
"""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth import security
from app.auth.models import LoginLog, RefreshToken, User
from app.database import Base, get_db

URL_LOGIN = "/api/v1/auth/login"


def _make_legacy_password(password: str) -> str:
    """构造旧格式密码密文（AES-ECB(base64(密码))），依赖测试 config.yaml 密钥。"""
    payload = base64.b64encode(password.encode("utf-8")).decode("utf-8")
    return security.sm4_encrypt(payload)


@pytest.fixture()
def login_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__, LoginLog.__table__, RefreshToken.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        User(
            id=1,
            username="legacy_user",
            password=_make_legacy_password("oldpass"),
            is_active=True,
        )
    )
    db.add(
        User(
            id=2,
            username="bcrypt_user",
            password=security.get_password_hash("newpass"),
            is_active=True,
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
    client = TestClient(app, raise_server_exceptions=False)
    yield client, Session
    db.close()
    engine.dispose()


class TestLoginAutoUpgrade:
    """旧格式登录后自动升级为 bcrypt。"""

    def test_legacy_login_upgrades_to_bcrypt(self, login_env):
        client, Session = login_env
        r = client.post(URL_LOGIN, json={"username": "legacy_user", "password": "oldpass"})
        assert r.json()["code"] == "200"

        with Session() as db:
            user = db.query(User).filter_by(username="legacy_user").first()
            assert user.password.startswith("$2b$"), "旧格式密码必须升级为 bcrypt"
            assert security.verify_password("oldpass", user.password)
            assert not security.verify_password("wrong", user.password)

    def test_legacy_login_wrong_password_no_upgrade(self, login_env):
        client, Session = login_env
        r = client.post(URL_LOGIN, json={"username": "legacy_user", "password": "wrong"})
        assert r.json()["code"] == "401"
        with Session() as db:
            user = db.query(User).filter_by(username="legacy_user").first()
            assert not user.password.startswith("$2b$"), "失败登录不得触发升级"

    def test_bcrypt_login_no_rehash_churn(self, login_env):
        """已是 bcrypt 的用户登录不得触发重哈希（无谓 UPDATE 会导致每次登录改写密码列）。"""
        client, Session = login_env
        with Session() as db:
            before = db.query(User).filter_by(username="bcrypt_user").first().password

        r = client.post(URL_LOGIN, json={"username": "bcrypt_user", "password": "newpass"})
        assert r.json()["code"] == "200"

        with Session() as db:
            after = db.query(User).filter_by(username="bcrypt_user").first().password
        assert before == after, "bcrypt 用户登录不应触发重哈希"

    def test_conditional_update_uses_old_value_guard(self, login_env):
        """自动升级 SQL 必须带 WHERE password=:old_val（防并发改密回滚）。"""
        from app.api.endpoints.login import login as login_fn
        import inspect

        source = inspect.getsource(login_fn)
        assert "UPDATE users SET password = :new_hash" in source
        assert "WHERE id = :uid AND password = :old_val" in source
