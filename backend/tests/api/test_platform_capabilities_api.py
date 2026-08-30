# -*- coding: utf-8 -*-
"""主机能力矩阵端点测试（dual-mode-client Phase 4 批次 A）。

GET /api/v1/platform/capabilities：认证端点，信封 data 下发形态+矩阵+计数；
两形态各锁定一次（矩阵本体由 tests/core/test_platform_capabilities.py 单测覆盖）。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user

URL = "/api/v1/platform/capabilities"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = lambda: None
    return TestClient(app)


def _data(resp):
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    return body["data"]


def test_desktop_payload(client, monkeypatch):
    monkeypatch.delenv("BTDECK_PLATFORM", raising=False)
    data = _data(client.get(URL))
    assert data["platform"] == "desktop"
    assert data["degradedCount"] == 0
    assert data["unsupportedCount"] == 0
    assert len(data["capabilities"]) == 14


def test_android_server_payload(client, monkeypatch):
    monkeypatch.setenv("BTDECK_PLATFORM", "android-server")
    data = _data(client.get(URL))
    assert data["platform"] == "android-server"
    assert data["unsupportedCount"] == 3
    assert data["degradedCount"] == 5
    scripts = data["capabilities"]["custom_scripts"]
    assert scripts["level"] == "unsupported"
    assert "Android" in scripts["note"]


def test_requires_authentication(client):
    """未认证 401/403（信封端点不匿名暴露——矩阵非敏感但保持全站一致）。"""
    unauthenticated = FastAPI()
    unauthenticated.include_router(api_router, prefix="/api/v1")
    resp = TestClient(unauthenticated).get(URL)
    assert resp.status_code in (401, 403)
