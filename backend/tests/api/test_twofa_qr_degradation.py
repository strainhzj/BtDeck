# -*- coding: utf-8 -*-
"""2FA 二维码 Pillow 缺失降级回归（Android 服务端形态 ANDROID-DROP）。

保护点：
1. Pillow 可用（桌面/Docker）行为零变化——base64 二维码 + qr_available=True；
2. Pillow 缺失不得把绑定流程打死在步骤 1（历史缺陷：ImportError 被兜底成
   code=500，secret 已落库却不可见）——必须返回成功信封：secret 非空 +
   qr_code_base64 空串 + qr_available=False，由前端降级为手动录入；
3. 首启无 secret 用户在降级路径同样先生成并落库 secret；
4. 旧图片端点 /2faVerifyQrCode 同场景返回明确 503 信封（指引手动录入），
   替代裸 500 崩溃；已启用用户维持空响应语义不变。
"""

import sys
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

VERIFY_PASSWORD_URL = "/api/v1/users/verifyPasswordFor2FA"
QR_IMAGE_URL = "/api/v1/users/2faVerifyQrCode/1"


@pytest.fixture()
def client_factory():
    """flag=0（未启用 2FA）+ 本人 token 替身；with_secret=False 模拟首启无密钥。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
    Session = sessionmaker(bind=engine)

    def _make_client(with_secret=True, flag="0"):
        with Session() as db:
            db.add(
                User(
                    id=1,
                    username="admin",
                    password="x",
                    two_factor_secret="SECRET123" if with_secret else None,
                    two_factor_flag=flag,
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
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id=1)
        return TestClient(app, raise_server_exceptions=False)

    yield _make_client
    engine.dispose()


def _drop_qr_pil(monkeypatch):
    """模拟 Android 服务端形态：qrcode 可导入，PIL/qrcode.image.pil 不可用。"""
    monkeypatch.setitem(sys.modules, "PIL", None)
    monkeypatch.setitem(sys.modules, "PIL.Image", None)
    monkeypatch.setitem(sys.modules, "qrcode.image.pil", None)


def _verify_password(client):
    with patch("app.api.endpoints.cuser.security.verify_password", return_value=True):
        return client.post(VERIFY_PASSWORD_URL, json={"userId": "1", "password": "right"})


class TestVerifyPasswordFor2faDegradation:
    def test_pillow_available_returns_qr_base64(self, client_factory):
        client = client_factory()
        r = _verify_password(client)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["qr_available"] is True
        assert body["data"]["qr_code_base64"].startswith("data:image/png;base64,")
        assert body["data"]["secret"] == "SECRET123"

    def test_pillow_missing_degrades_to_manual_entry(self, client_factory, monkeypatch):
        _drop_qr_pil(monkeypatch)
        client = client_factory()
        r = _verify_password(client)
        assert r.status_code == 200
        body = r.json()
        # 成功信封（不得 500/401），绑定流程可继续走手动录入
        assert body["code"] == "200"
        assert body["status"] == "success"
        assert body["data"]["qr_available"] is False
        assert body["data"]["qr_code_base64"] == ""
        assert body["data"]["secret"] == "SECRET123"

    def test_pillow_missing_still_generates_secret_when_absent(self, client_factory, monkeypatch):
        _drop_qr_pil(monkeypatch)
        client = client_factory(with_secret=False)
        r = _verify_password(client)
        body = r.json()
        assert body["code"] == "200"
        # 首启无 secret：先生成并落库，再进入降级分支返回
        assert body["data"]["secret"]
        assert len(body["data"]["secret"]) >= 16


class TestQrImageEndpointDegradation:
    def test_pillow_available_streams_png(self, client_factory):
        client = client_factory()
        r = client.get(QR_IMAGE_URL)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")
        assert len(r.content) > 0

    def test_pillow_missing_returns_clear_envelope(self, client_factory, monkeypatch):
        _drop_qr_pil(monkeypatch)
        client = client_factory()
        r = client.get(QR_IMAGE_URL)
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == "503"
        assert body["status"] == "error"
        assert "手动录入" in body["msg"]

    def test_enabled_user_still_returns_empty(self, client_factory, monkeypatch):
        """已启用 2FA（flag=1）用户维持既有空响应语义，与 Pillow 可用性无关。"""
        _drop_qr_pil(monkeypatch)
        client = client_factory(flag="1")
        r = client.get(QR_IMAGE_URL)
        assert r.status_code == 200
        assert r.text == '""'
