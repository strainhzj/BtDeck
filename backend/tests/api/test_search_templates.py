# -*- coding: utf-8 -*-
"""
搜索模板端点认证与权限单元测试（v1.0.5.11）

验证 search-templates 端点在以下场景下的行为：
- 无 token / 无效 token / 过期 token → 返回 401
- 有效 token → 不被 401 拒绝（正常进入业务逻辑）

测试端点（均走 x-access-token 头认证）：
- GET    /api/v1/advanced-search/search-templates
- POST   /api/v1/advanced-search/search-templates
- PUT    /api/v1/advanced-search/search-templates/{id}
- DELETE /api/v1/advanced-search/search-templates/{id}
- POST   /api/v1/advanced-search/search-templates/{id}/apply

遵循项目既有测试模式（参照 tests/api/test_auth_protection.py）：
- TestClient（同步）+ MagicMock 隔离 DB
- JWT token 用真实 create_access_token 构造，patch settings + get_login_secret
- 认证失败断言：HTTP 200 + body code=="401"
"""

from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ==================== 共享常量和工具（仿 test_auth_protection.py）====================

_TEST_SECRET = "test-secret-key-for-unit-testing"
_TEST_ALGORITHM = "HS256"
_TEST_LOGIN_SECRET = "test-login-secret"


def _mock_settings():
    """创建测试用 mock settings"""
    mock_s = MagicMock()
    mock_s.SECRET_KEY = _TEST_SECRET
    mock_s.ALGORITHM = _TEST_ALGORITHM
    mock_s.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    return mock_s


def _create_valid_token() -> str:
    """创建有效 JWT token（含 verify_secret，模拟项目实际 create_access_token）"""
    from app.auth.utils import create_access_token
    mock_s = _mock_settings()
    with patch("app.auth.utils.settings", mock_s):
        return create_access_token(
            {"sub": "test_user", "user_id": "1", "verify_secret": _TEST_LOGIN_SECRET}
        )


def _create_expired_token() -> str:
    """创建过期 JWT token"""
    return jwt.encode(
        {"sub": "test_user", "user_id": "1", "verify_secret": _TEST_LOGIN_SECRET, "exp": 0},
        _TEST_SECRET,
        algorithm=_TEST_ALGORITHM,
    )


def _create_wrong_secret_token() -> str:
    """创建签名错误的 token"""
    return jwt.encode(
        {"sub": "test_user", "user_id": "1", "verify_secret": _TEST_LOGIN_SECRET},
        "wrong-secret-key",
        algorithm=_TEST_ALGORITHM,
    )


def _create_test_app() -> FastAPI:
    """创建测试用 FastAPI 应用，挂载完整 api_router"""
    from app.api.api import api_router
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return app


def _get_client_and_patches():
    """创建 TestClient 和必要的 mock 补丁（隔离 DB 与 settings）"""
    app = _create_test_app()
    client = TestClient(app, raise_server_exceptions=False)
    mock_settings = _mock_settings()
    mock_db = MagicMock()
    settings_patch = patch("app.auth.utils.settings", mock_settings)
    secret_patch = patch("app.auth.utils.get_login_secret", return_value=_TEST_LOGIN_SECRET)
    db_patch = patch("app.database.get_db", return_value=iter([mock_db]))
    store_patch = patch.object(app.state, "store", create=True)
    return client, settings_patch, secret_patch, db_patch, store_patch


# ==================== 端点认证拦截测试 ====================


class TestSearchTemplatesAuth:
    """search-templates 端点认证测试

    验证无 token / 无效 token / 过期 token 时返回 401，
    有效 token 时不被 401 拒绝。
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client, self.sp, self.sp2, self.dbp, self.stp = _get_client_and_patches()
        self.sp.start()
        self.sp2.start()
        self.dbp.start()
        self.stp.start()
        yield
        self.sp.stop()
        self.sp2.stop()
        self.dbp.stop()
        self.stp.stop()

    # --- GET 列表 ---

    def test_get_templates_no_token_returns_401(self):
        """GET 列表：无 token 应返回 401"""
        response = self.client.get(
            "/api/v1/advanced-search/search-templates",
            params={"user_id": "1"},
        )
        assert response.status_code == 401

    def test_get_templates_invalid_token_returns_401(self):
        """GET 列表：无效 token（错误签名）应返回 401"""
        response = self.client.get(
            "/api/v1/advanced-search/search-templates",
            params={"user_id": "1"},
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    def test_get_templates_expired_token_returns_401(self):
        """GET 列表：过期 token 应返回 401"""
        response = self.client.get(
            "/api/v1/advanced-search/search-templates",
            params={"user_id": "1"},
            headers={"x-access-token": _create_expired_token()},
        )
        assert response.status_code == 401

    def test_get_templates_valid_token_not_rejected_by_auth(self):
        """GET 列表：有效 token 不应被 401 拒绝（业务错误码可以是 500，但非 401）"""
        response = self.client.get(
            "/api/v1/advanced-search/search-templates",
            params={"user_id": "1"},
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        data = response.json()
        # 有效 token 通过认证后，可能因 mock db 返回业务错误，但绝不应是 401
        assert data["code"] != "401"

    # --- POST 创建 ---

    def test_create_template_no_token_returns_401(self):
        """POST 创建：无 token 应返回 401"""
        response = self.client.post(
            "/api/v1/advanced-search/search-templates",
            json={
                "name": "测试模板",
                "conditions": {"source": "simple", "version": 1, "listQuery": {}},
                "is_public": False,
            },
        )
        assert response.status_code == 401

    def test_create_template_invalid_token_returns_401(self):
        """POST 创建：无效 token 应返回 401"""
        response = self.client.post(
            "/api/v1/advanced-search/search-templates",
            json={
                "name": "测试模板",
                "conditions": {"source": "simple", "version": 1, "listQuery": {}},
                "is_public": False,
            },
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    def test_create_template_valid_token_not_rejected_by_auth(self):
        """POST 创建：有效 token 不应被 401 拒绝"""
        response = self.client.post(
            "/api/v1/advanced-search/search-templates",
            json={
                "name": "测试模板",
                "conditions": {"source": "simple", "version": 1, "listQuery": {}},
                "is_public": False,
            },
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        assert response.json()["code"] != "401"

    # --- PUT 更新 ---

    def test_update_template_no_token_returns_401(self):
        """PUT 更新：无 token 应返回 401"""
        response = self.client.put(
            "/api/v1/advanced-search/search-templates/test-template-id",
            json={"id": "test-template-id", "name": "更新后"},
        )
        assert response.status_code == 401

    def test_update_template_invalid_token_returns_401(self):
        """PUT 更新：无效 token 应返回 401"""
        response = self.client.put(
            "/api/v1/advanced-search/search-templates/test-template-id",
            json={"id": "test-template-id", "name": "更新后"},
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    def test_update_template_valid_token_not_rejected_by_auth(self):
        """PUT 更新：有效 token 不应被 401 拒绝"""
        response = self.client.put(
            "/api/v1/advanced-search/search-templates/test-template-id",
            json={"id": "test-template-id", "name": "更新后"},
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        assert response.json()["code"] != "401"

    # --- DELETE 删除 ---

    def test_delete_template_no_token_returns_401(self):
        """DELETE 删除：无 token 应返回 401"""
        response = self.client.delete(
            "/api/v1/advanced-search/search-templates/test-template-id",
        )
        assert response.status_code == 401

    def test_delete_template_invalid_token_returns_401(self):
        """DELETE 删除：无效 token 应返回 401"""
        response = self.client.delete(
            "/api/v1/advanced-search/search-templates/test-template-id",
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    def test_delete_template_valid_token_not_rejected_by_auth(self):
        """DELETE 删除：有效 token 不应被 401 拒绝"""
        response = self.client.delete(
            "/api/v1/advanced-search/search-templates/test-template-id",
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        assert response.json()["code"] != "401"

    # --- POST apply 应用 ---

    def test_apply_template_no_token_returns_401(self):
        """POST apply：无 token 应返回 401"""
        response = self.client.post(
            "/api/v1/advanced-search/search-templates/test-template-id/apply",
        )
        assert response.status_code == 401

    def test_apply_template_invalid_token_returns_401(self):
        """POST apply：无效 token 应返回 401"""
        response = self.client.post(
            "/api/v1/advanced-search/search-templates/test-template-id/apply",
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    def test_apply_template_valid_token_not_rejected_by_auth(self):
        """POST apply：有效 token 不应被 401 拒绝"""
        response = self.client.post(
            "/api/v1/advanced-search/search-templates/test-template-id/apply",
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        assert response.json()["code"] != "401"
