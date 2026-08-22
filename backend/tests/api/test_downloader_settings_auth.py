# -*- coding: utf-8 -*-
"""Downloader settings endpoint auth regression tests."""

import inspect
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


_TEST_SECRET = "test-secret-key-for-unit-testing"
_TEST_ALGORITHM = "HS256"
_TEST_LOGIN_SECRET = "test-login-secret"


def _mock_settings():
    mock_s = MagicMock()
    mock_s.SECRET_KEY = _TEST_SECRET
    mock_s.ALGORITHM = _TEST_ALGORITHM
    mock_s.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    return mock_s


def _create_valid_token() -> str:
    from app.auth.utils import create_access_token

    with patch("app.auth.utils.settings", _mock_settings()):
        return create_access_token({"sub": "test_user", "user_id": "1", "verify_secret": _TEST_LOGIN_SECRET})


def _create_wrong_secret_token() -> str:
    return jwt.encode(
        {"sub": "test_user", "user_id": "1", "verify_secret": _TEST_LOGIN_SECRET},
        "wrong-secret-key",
        algorithm=_TEST_ALGORITHM,
    )


def _create_test_app() -> FastAPI:
    from app.api.api import api_router

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return app


@pytest.fixture
def client():
    app = _create_test_app()
    mock_db = MagicMock()

    def override_get_db():
        yield mock_db

    from app.database import get_db

    app.dependency_overrides[get_db] = override_get_db
    with patch("app.auth.utils.settings", _mock_settings()), patch(
        "app.auth.utils.get_login_secret", return_value=_TEST_LOGIN_SECRET
    ):
        yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


ENDPOINTS = [
    ("get", "/api/v1/downloaders/dl-1/settings", None),
    ("put", "/api/v1/downloaders/dl-1/settings", {}),
    ("put", "/api/v1/downloaders/dl-1/settings/rules/reorder", {"rule_ids": []}),
    ("post", "/api/v1/downloaders/dl-1/settings/apply", None),
    (
        "post",
        "/api/v1/downloaders/dl-1/settings/test",
        {"host": "", "port": 8080, "username": "admin", "downloader_type": 0},
    ),
]


def _request(client: TestClient, method: str, url: str, token: str | None = None, body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if body is None:
        return getattr(client, method)(url, headers=headers)
    return getattr(client, method)(url, json=body, headers=headers)


@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_downloader_settings_endpoints_return_401_without_token(client, method, url, body):
    response = _request(client, method, url, body=body)
    assert response.status_code == 401


@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_downloader_settings_endpoints_return_401_with_invalid_token(client, method, url, body):
    response = _request(client, method, url, token=_create_wrong_secret_token(), body=body)
    assert response.status_code == 401


@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_downloader_settings_endpoints_accept_valid_bearer_token(client, method, url, body):
    response = _request(client, method, url, token=_create_valid_token(), body=body)

    assert response.status_code == 200
    assert response.json()["code"] != "401"


def test_downloader_settings_endpoint_signatures_use_require_authenticated_user():
    from app.api.endpoints import downloader_settings
    from app.auth.dependencies import require_authenticated_user

    endpoint_names = [
        "get_downloader_settings",
        "update_downloader_settings",
        "reorder_speed_schedule_rules",
        "apply_downloader_settings",
        "test_downloader_settings",
    ]

    for name in endpoint_names:
        source = inspect.getsource(getattr(downloader_settings, name))
        assert "Depends(require_authenticated_user)" in source
        assert 'headers.get("x-access-token")' not in source
        assert "verify_access_token" not in source
