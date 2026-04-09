"""
API端点认证保护单元测试

验证所有修复后的端点在以下场景下的认证行为：
- 无token请求 → 返回401
- 无效token请求 → 返回401
- 有效token请求 → 正常通过认证（不返回401）

测试覆盖的修复文件：
- torrent_status.py: POST /pause, /resume, /recheck
- torrent_crud.py: GET /torrents/{...}, /getList
- tracker_keywords_pools.py: GET /pool, POST /move, POST /batch-move,
  GET /pool/statistics, GET /pool/search-all
"""

from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ==================== 共享常量和工具 ====================

_TEST_SECRET = "test-secret-key-for-unit-testing"
_TEST_ALGORITHM = "HS256"
_TEST_LOGIN_SECRET = "test-login-secret"


def _create_valid_token() -> str:
    """创建有效JWT token（模拟项目实际的create_access_token）"""
    from datetime import datetime, timedelta
    from app.auth.utils import create_access_token
    mock_s = _mock_settings()
    with patch("app.auth.utils.settings", mock_s):
        return create_access_token(
            {"sub": "test_user", "user_id": "1", "verify_secret": _TEST_LOGIN_SECRET}
        )


def _create_expired_token() -> str:
    """创建过期JWT token"""
    return jwt.encode(
        {
            "sub": "test_user",
            "verify_secret": _TEST_LOGIN_SECRET,
            "exp": 0,
        },
        _TEST_SECRET,
        algorithm=_TEST_ALGORITHM,
    )


def _create_wrong_secret_token() -> str:
    """创建签名错误的token"""
    return jwt.encode(
        {
            "sub": "test_user",
            "verify_secret": _TEST_LOGIN_SECRET,
        },
        "wrong-secret-key",
        algorithm=_TEST_ALGORITHM,
    )


def _mock_settings():
    """创建测试用mock settings"""
    mock_s = MagicMock()
    mock_s.SECRET_KEY = _TEST_SECRET
    mock_s.ALGORITHM = _TEST_ALGORITHM
    mock_s.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    return mock_s


def _create_test_app() -> FastAPI:
    """创建用于测试的FastAPI应用，包含待测路由"""
    from app.api.api import api_router

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return app


def _get_client_and_patches():
    """创建TestClient和必要的mock补丁"""
    app = _create_test_app()
    client = TestClient(app, raise_server_exceptions=False)

    mock_settings = _mock_settings()

    # mock数据库依赖，避免真实数据库连接
    mock_db = MagicMock()

    # 需要同时patch所有使用settings的路径
    settings_patch = patch("app.auth.utils.settings", mock_settings)
    secret_patch = patch(
        "app.auth.utils.get_login_secret", return_value=_TEST_LOGIN_SECRET
    )
    db_patch = patch("app.database.get_db", return_value=iter([mock_db]))
    # mock app.state.store 以避免下载器缓存相关的错误
    store_patch = patch.object(app.state, "store", create=True)

    return client, settings_patch, secret_patch, db_patch, store_patch


# ==================== 认证拦截测试 ====================


class TestTorrentStatusAuth:
    """torrent_status.py 端点认证测试

    验证 POST /api/v1/torrents/pause, /resume, /recheck
    在缺少或无效token时返回401。
    """

    ENDPOINTS = [
        ("/api/v1/torrents/pause", "post"),
        ("/api/v1/torrents/resume", "post"),
        ("/api/v1/torrents/recheck", "post"),
    ]

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

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_no_token_returns_401(self, endpoint, method):
        """无token请求应返回401"""
        request_body = {"downloader_id": "test-id", "hashes": ["abc123"]}
        response = self.client.post(endpoint, json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"
        assert "token" in data["msg"].lower()

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_invalid_token_returns_401(self, endpoint, method):
        """无效token应返回401"""
        request_body = {"downloader_id": "test-id", "hashes": ["abc123"]}
        response = self.client.post(
            endpoint,
            json=request_body,
            headers={"x-access-token": "invalid-token-string"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_expired_token_returns_401(self, endpoint, method):
        """过期token应返回401"""
        token = _create_expired_token()
        request_body = {"downloader_id": "test-id", "hashes": ["abc123"]}
        response = self.client.post(
            endpoint,
            json=request_body,
            headers={"x-access-token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_wrong_secret_token_returns_401(self, endpoint, method):
        """签名错误的token应返回401"""
        token = _create_wrong_secret_token()
        request_body = {"downloader_id": "test-id", "hashes": ["abc123"]}
        response = self.client.post(
            endpoint,
            json=request_body,
            headers={"x-access-token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_valid_token_not_rejected_by_auth(self, endpoint, method):
        """有效token应通过认证（不会因认证失败返回401）"""
        token = _create_valid_token()
        request_body = {"downloader_id": "test-id", "hashes": ["abc123"]}
        response = self.client.post(
            endpoint,
            json=request_body,
            headers={"x-access-token": token},
        )
        data = response.json()
        # 认证通过后，可能因业务逻辑报错（如下载器不存在），
        # 但code不应是401
        assert data["code"] != "401"


class TestTorrentCrudAuth:
    """torrent_crud.py 端点认证测试

    验证 GET /api/v1/torrents/getList 和
    GET /api/v1/torrents/torrents/{info_id}/{downloader_id}/{name}
    在缺少或无效token时返回401。
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

    def test_get_list_no_token_returns_401(self):
        """GET /getList 无token应返回401"""
        response = self.client.get("/api/v1/torrents/getList")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"
        assert "token" in data["msg"].lower()

    def test_get_list_invalid_token_returns_401(self):
        """GET /getList 无效token应返回401"""
        response = self.client.get(
            "/api/v1/torrents/getList",
            headers={"x-access-token": "not-a-real-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    def test_get_list_expired_token_returns_401(self):
        """GET /getList 过期token应返回401"""
        token = _create_expired_token()
        response = self.client.get(
            "/api/v1/torrents/getList",
            headers={"x-access-token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    def test_get_list_valid_token_not_rejected_by_auth(self):
        """GET /getList 有效token应通过认证"""
        token = _create_valid_token()
        response = self.client.get(
            "/api/v1/torrents/getList",
            headers={"x-access-token": token},
        )
        data = response.json()
        assert data["code"] != "401"

    def test_get_torrent_by_id_no_token_returns_401(self):
        """GET /torrents/{info_id}/{downloader_id}/{name} 无token应返回401"""
        response = self.client.get(
            "/api/v1/torrents/torrents/test-info/test-dl/test-name"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    def test_get_torrent_by_id_invalid_token_returns_401(self):
        """GET /torrents/{...} 无效token应返回401"""
        response = self.client.get(
            "/api/v1/torrents/torrents/test-info/test-dl/test-name",
            headers={"x-access-token": "bad-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    def test_get_torrent_by_id_valid_token_not_rejected_by_auth(self):
        """GET /torrents/{...} 有效token应通过认证"""
        token = _create_valid_token()
        response = self.client.get(
            "/api/v1/torrents/torrents/test-info/test-dl/test-name",
            headers={"x-access-token": token},
        )
        data = response.json()
        # 认证通过后，可能因业务逻辑返回404（HTTPException格式）或CommonResponse
        # 关键是返回码不应是401
        if "code" in data:
            assert data["code"] != "401"
        else:
            # HTTPException格式，detail字段说明非认证错误
            assert "detail" in data


class TestTrackerKeywordsPoolsAuth:
    """tracker_keywords_pools.py 端点认证测试

    验证所有5个端点在缺少或无效token时返回401，
    确保修复了"if token:"条件性认证漏洞。
    """

    ENDPOINTS = [
        ("/api/v1/tracker-keywords/pool?pool_type=candidate", "get"),
        ("/api/v1/tracker-keywords/pool/statistics", "get"),
        ("/api/v1/tracker-keywords/pool/search-all", "get"),
    ]

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

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_get_no_token_returns_401(self, endpoint, method):
        """GET端点无token应返回401"""
        response = self.client.get(endpoint)
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_get_invalid_token_returns_401(self, endpoint, method):
        """GET端点无效token应返回401"""
        response = self.client.get(
            endpoint,
            headers={"x-access-token": "invalid"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS)
    def test_get_expired_token_returns_401(self, endpoint, method):
        """GET端点过期token应返回401"""
        token = _create_expired_token()
        response = self.client.get(
            endpoint,
            headers={"x-access-token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    @pytest.mark.parametrize("endpoint,method", ENDPOINTS
    )
    def test_get_valid_token_not_rejected_by_auth(self, endpoint, method):
        """GET端点有效token应通过认证"""
        token = _create_valid_token()
        response = self.client.get(
            endpoint,
            headers={"x-access-token": token},
        )
        data = response.json()
        assert data["code"] != "401"

    def test_move_no_token_returns_401(self):
        """POST /move 无token应返回401"""
        response = self.client.post(
            "/api/v1/tracker-keywords/move",
            json={"keyword_id": "test-id", "target_pool": "success"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    def test_move_invalid_token_returns_401(self):
        """POST /move 无效token应返回401"""
        response = self.client.post(
            "/api/v1/tracker-keywords/move",
            json={"keyword_id": "test-id", "target_pool": "success"},
            headers={"x-access-token": "bad-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    def test_batch_move_no_token_returns_401(self):
        """POST /batch-move 无token应返回401"""
        response = self.client.post(
            "/api/v1/tracker-keywords/batch-move",
            json={"keyword_ids": ["id1", "id2"], "target_pool": "success"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "401"

    def test_batch_move_valid_token_not_rejected_by_auth(self):
        """POST /batch-move 有效token应通过认证"""
        token = _create_valid_token()
        response = self.client.post(
            "/api/v1/tracker-keywords/batch-move",
            json={"keyword_ids": ["id1", "id2"], "target_pool": "success"},
            headers={"x-access-token": token},
        )
        data = response.json()
        assert data["code"] != "401"


class TestLoginStillPublic:
    """确认登录接口仍然公开可访问"""

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

    def test_login_no_token_is_ok(self):
        """POST /auth/login 不需要token，不应返回401"""
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        data = response.json()
        # 登录失败应返回401（用户名/密码错误），而非token验证失败
        # 如果返回了token验证相关的401，说明登录接口被误加认证了
        assert "token" not in data.get("msg", "").lower() or data["code"] != "401"


class TestAlreadyProtectedEndpoints:
    """
    确认原有端点的认证模式。

    注意：这些端点使用 try/except 模式调用 verify_access_token，
    而 verify_access_token 在验证失败时返回 None 而非抛异常。
    因此这些端点实际上也存在认证绕过漏洞（返回None后代码继续执行）。
    这是项目已有的技术债务，不在本次修复范围内。
    本次修复的3个文件已使用 if not user_info 检查返回值来避免此问题。
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

    def test_downloader_get_list_no_token_does_not_crash(self):
        """GET /downloader/getList 无token应不崩溃（可能绕过认证）"""
        response = self.client.get("/api/v1/downloader/getList")
        assert response.status_code == 200
        data = response.json()
        # 已知问题：现有 try/except 模式无法捕获 verify_access_token 返回 None 的情况
        # 此测试仅验证接口不会崩溃

    def test_torrent_list_no_token_does_not_crash(self):
        """POST /torrents/list 无token应不崩溃"""
        response = self.client.post("/api/v1/torrents/list")
        assert response.status_code == 200

    def test_tracker_keywords_list_no_token_does_not_crash(self):
        """GET /tracker-keywords 无token应不崩溃"""
        response = self.client.get("/api/v1/tracker-keywords")
        assert response.status_code == 200
