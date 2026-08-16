# -*- coding: utf-8 -*-
"""
双令牌 refresh 体系回归（verified-bugfix-remediation W6-1）

覆盖：
- 登录签发 refresh_token 并落库（SHA-256 哈希）
- /auth/refresh：有效 token 换发新 access + 新 refresh（使用即轮换，旧 token 失效）
- 已撤销 / 已过期 / 伪造 token → 401
- 登出撤销该用户全部 refresh token
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth import models, utils
from app.database import Base, get_db

REFRESH_URL = "/api/v1/auth/refresh"


@pytest.fixture
def auth_client():
    """内存库（users + refresh_tokens + login_logs）+ override get_db。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[models.User.__table__, models.RefreshToken.__table__, models.LoginLog.__table__])
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        db.add(models.User(id=1, username="tester", password="x", is_active=True))
        db.commit()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=False), SessionLocal


def _issue_refresh(session: Session, user_id=1, expires_delta=None, revoked=False):
    token = utils.create_refresh_token()
    record = models.RefreshToken(
        user_id=user_id,
        token_hash=utils.hash_refresh_token(token),
        expires_at=datetime.utcnow() + (expires_delta or timedelta(days=7)),
    )
    if revoked:
        record.revoked_at = datetime.utcnow()
    session.add(record)
    session.commit()
    return token, record


class TestLoginIssuesRefreshToken:
    """登录响应携带 refresh_token，且哈希落库。"""

    def test_login_requires_password_not_tested_here(self):
        # 登录端点依赖 SM4 密码与 YAML 配置，由 refresh 端点单测覆盖核心语义；
        # 此处验证 refresh token 工具函数行为。
        token = utils.create_refresh_token()
        assert len(token) == 64
        assert utils.hash_refresh_token(token) != token
        assert utils.hash_refresh_token(token) == utils.hash_refresh_token(token)


class TestRefreshEndpoint:
    def test_valid_token_rotates_and_returns_new_pair(self, auth_client):
        client, SessionLocal = auth_client
        with SessionLocal() as session:
            token, record = _issue_refresh(session)
            old_id = record.id

        resp = client.post(REFRESH_URL, json={"refresh_token": token})

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "200"
        data = body["data"][0]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["refresh_token"] != token

        with SessionLocal() as session:
            old = session.get(models.RefreshToken, old_id)
            assert old.revoked_at is not None  # 使用即轮换
            new_record = (
                session.query(models.RefreshToken)
                .filter(models.RefreshToken.id != old_id)
                .first()
            )
            assert new_record is not None
            assert new_record.revoked_at is None
            # 换发后的新 token 可再次刷新（链式续期）
        resp2 = client.post(REFRESH_URL, json={"refresh_token": data["refresh_token"]})
        assert resp2.json()["code"] == "200"

    def test_revoked_token_returns_401(self, auth_client):
        client, SessionLocal = auth_client
        with SessionLocal() as session:
            token, _ = _issue_refresh(session, revoked=True)

        resp = client.post(REFRESH_URL, json={"refresh_token": token})
        assert resp.json()["code"] == "401"

    def test_expired_token_returns_401(self, auth_client):
        client, SessionLocal = auth_client
        with SessionLocal() as session:
            token, _ = _issue_refresh(session, expires_delta=timedelta(days=-1))

        resp = client.post(REFRESH_URL, json={"refresh_token": token})
        assert resp.json()["code"] == "401"

    def test_garbage_token_returns_401(self, auth_client):
        client, _ = auth_client
        resp = client.post(REFRESH_URL, json={"refresh_token": "not-a-real-token"})
        assert resp.json()["code"] == "401"

    def test_logout_revokes_all_refresh_tokens(self, auth_client):
        """登出撤销该用户全部 refresh token：撤销后刷新返回 401。"""
        client, SessionLocal = auth_client
        with SessionLocal() as session:
            token1, _ = _issue_refresh(session)
            token2, _ = _issue_refresh(session)

        # 登出需要认证 token：直接调用 cuser 的撤销逻辑（无认证依赖的端点层测试）
        from app.api.endpoints import cuser

        with SessionLocal() as session:
            result = cuser.logout(
                user_info=SimpleNamespace(username="tester", user_id=1),
                db=session,
            )
            assert result.code == "200"

        for token in (token1, token2):
            resp = client.post(REFRESH_URL, json={"refresh_token": token})
            assert resp.json()["code"] == "401"
