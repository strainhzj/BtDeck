# -*- coding: utf-8 -*-
"""
孤儿文件管理端点认证与契约单元测试（v1.0.6）

验证 orphan-files 端点在以下场景下的行为：
- 无 token / 无效 token / 过期 token → 返回 401
- 有效 token → 不被 401 拒绝（正常进入业务逻辑）

测试端点（均走 require_authenticated_user 认证）：
- GET    /api/v1/orphan-files/latest
- GET    /api/v1/orphan-files/list
- POST   /api/v1/orphan-files/scan
- POST   /api/v1/orphan-files/cleanup-preview
- POST   /api/v1/orphan-files/cleanup

遵循项目既有测试模式（参照 tests/api/test_auth_protection.py + test_active_torrents_endpoint.py）：
- TestClient（同步）+ MagicMock 隔离 DB
- JWT token 用真实 create_access_token 构造，patch settings + get_login_secret
- 认证失败断言：HTTP 401
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.api import api_router
from app.database import get_async_db

# ==================== 共享常量和工具 ====================

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
    """创建有效 JWT token"""
    from app.auth.utils import create_access_token

    mock_s = _mock_settings()
    with patch("app.auth.utils.settings", mock_s):
        return create_access_token({"sub": "test_user", "user_id": "1", "verify_secret": _TEST_LOGIN_SECRET})


def _create_expired_token() -> str:
    """创建过期 JWT token"""
    return jwt.encode(
        {
            "sub": "test_user",
            "user_id": "1",
            "verify_secret": _TEST_LOGIN_SECRET,
            "exp": 0,
        },
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
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    return app


# ==================== 端点认证拦截测试 ====================


class TestOrphanFilesAuth:
    """orphan-files 端点认证测试

    验证无 token / 无效 token / 过期 token 时返回 401，
    有效 token 时不被 401 拒绝。
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        mock_settings = _mock_settings()
        self.settings_patch = patch("app.auth.utils.settings", mock_settings)
        self.secret_patch = patch("app.auth.utils.get_login_secret", return_value=_TEST_LOGIN_SECRET)
        self.settings_patch.start()
        self.secret_patch.start()
        yield
        self.settings_patch.stop()
        self.secret_patch.stop()

    # --- GET /latest ---

    def test_get_latest_no_token_returns_401(self):
        """GET /latest：无 token 应返回 401"""
        response = self.client.get("/api/v1/orphan-files/latest")
        assert response.status_code == 401

    def test_get_latest_invalid_token_returns_401(self):
        """GET /latest：无效 token 应返回 401"""
        response = self.client.get(
            "/api/v1/orphan-files/latest",
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    def test_get_latest_expired_token_returns_401(self):
        """GET /latest：过期 token 应返回 401"""
        response = self.client.get(
            "/api/v1/orphan-files/latest",
            headers={"x-access-token": _create_expired_token()},
        )
        assert response.status_code == 401

    # --- GET /list ---

    def test_get_list_no_token_returns_401(self):
        """GET /list：无 token 应返回 401"""
        response = self.client.get("/api/v1/orphan-files/list")
        assert response.status_code == 401

    def test_get_list_invalid_token_returns_401(self):
        """GET /list：无效 token 应返回 401"""
        response = self.client.get(
            "/api/v1/orphan-files/list",
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    # --- POST /scan ---

    def test_post_scan_no_token_returns_401(self):
        """POST /scan：无 token 应返回 401"""
        response = self.client.post("/api/v1/orphan-files/scan")
        assert response.status_code == 401

    def test_post_scan_invalid_token_returns_401(self):
        """POST /scan：无效 token 应返回 401"""
        response = self.client.post(
            "/api/v1/orphan-files/scan",
            headers={"x-access-token": _create_wrong_secret_token()},
        )
        assert response.status_code == 401

    # --- POST /cleanup-preview ---

    def test_post_cleanup_preview_no_token_returns_401(self):
        """POST /cleanup-preview：无 token 应返回 401"""
        response = self.client.post(
            "/api/v1/orphan-files/cleanup-preview",
            json={"orphan_ids": [1]},
        )
        assert response.status_code == 401

    # --- POST /cleanup ---

    def test_post_cleanup_no_token_returns_401(self):
        """POST /cleanup：无 token 应返回 401"""
        response = self.client.post(
            "/api/v1/orphan-files/cleanup",
            json={"orphan_ids": [1]},
        )
        assert response.status_code == 401

    def test_post_purge_no_token_returns_401(self):
        """POST /purge：无 token 应返回 401。"""
        response = self.client.post(
            "/api/v1/orphan-files/purge",
            json={"canonical_paths": ["/data/orphan.bin"]},
        )
        assert response.status_code == 401


# ==================== 有效 token 契约测试 ====================


class TestOrphanFilesWithValidToken:
    """有效 token 时的业务契约测试（隔离 DB）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _create_test_app()
        # 覆盖认证依赖（仿 test_active_torrents_endpoint.py）
        self.app.dependency_overrides[require_authenticated_user] = lambda: (SimpleNamespace(username="tester"))
        self.client = TestClient(self.app, raise_server_exceptions=False)

        # mock AsyncSession
        self.mock_db = MagicMock()
        self.db_patch = patch(
            "app.api.endpoints.orphan_files.get_async_db",
            return_value=iter([self.mock_db]),
        )
        self.db_patch.start()
        yield
        self.db_patch.stop()
        self.app.dependency_overrides.clear()

    def test_get_latest_valid_token_not_rejected_by_auth(self):
        """GET /latest：有效 token 不应被 401 拒绝"""
        response = self.client.get(
            "/api/v1/orphan-files/latest",
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] != "401"


class TestOrphanFilesCleanupWiring:
    """验证真实 HTTP 入口把快照 ID 与共享下载器 store 传入服务层。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.app = _create_test_app()
        self.app.state.store = MagicMock(name="shared_downloader_store")
        self.app.dependency_overrides[require_authenticated_user] = lambda: (SimpleNamespace(username="tester"))
        self.mock_db = MagicMock(name="async_db")

        async def override_db():
            yield self.mock_db

        self.app.dependency_overrides[get_async_db] = override_db
        self.client = TestClient(self.app, raise_server_exceptions=False)
        yield
        self.app.dependency_overrides.clear()

    def test_cleanup_preview_passes_scan_id(self):
        from app.services.orphan_file_service import OrphanFileService

        mocked = AsyncMock(return_value={"total_count": 1, "total_size": 10, "items": []})
        with patch.object(OrphanFileService, "cleanup_preview", mocked):
            response = self.client.post(
                "/api/v1/orphan-files/cleanup-preview",
                json={"scan_id": "scan-latest", "orphan_ids": [1]},
            )

        assert response.status_code == 200
        assert response.json()["code"] == "200"
        mocked.assert_awaited_once_with([1], scan_id="scan-latest")

    def test_list_returns_atomic_scan_context(self):
        """分页端点应原样返回列表、统计与扫描上下文的一致快照。"""
        from app.services.orphan_file_service import OrphanFileService

        payload = {
            "total": 1,
            "page": 1,
            "pageSize": 20,
            "list": [{"id": 1, "scan_id": "scan-ok"}],
            "scan_context": {
                "latest_attempt": {"scan_id": "scan-failed", "status": "failed"},
                "display_scan": {"scan_id": "scan-ok", "status": "completed"},
                "remaining_count": 1,
                "remaining_size": 10,
                "cleanup_allowed": False,
                "cleanup_block_reason": "最新扫描失败",
            },
        }
        mocked = AsyncMock(return_value=payload)
        with patch.object(OrphanFileService, "get_orphan_list", mocked):
            response = self.client.get("/api/v1/orphan-files/list")

        assert response.status_code == 200
        assert response.json()["data"] == payload
        mocked.assert_awaited_once_with(
            page=1,
            page_size=20,
            downloader_id=None,
            min_size=None,
            path_like=None,
            status=None,
        )

    def test_list_accepts_page_size_upper_bound_100000(self):
        """page_size 上限 100000 应被接受（与前端页大小输入上限 10 万对齐）。

        守护本次修改：orphan_files.py 的 /list page_size 从 le=100 提到 le=100000。
        若上限被误改回 100，本测试会失败（100000 被拒为 422）。
        """
        from app.services.orphan_file_service import OrphanFileService

        mocked = AsyncMock(return_value={"total": 0, "page": 1, "pageSize": 100000, "list": [], "scan_context": {}})
        with patch.object(OrphanFileService, "get_orphan_list", mocked):
            response = self.client.get("/api/v1/orphan-files/list?page_size=100000")

        assert response.status_code == 200, "page_size=100000 应被接受"
        mocked.assert_awaited_once_with(
            page=1, page_size=100000, downloader_id=None, min_size=None, path_like=None, status=None
        )

    def test_list_rejects_page_size_over_upper_bound(self):
        """page_size 超过 100000 应被 Pydantic 校验拒绝（422），不进入业务逻辑。"""
        from app.services.orphan_file_service import OrphanFileService

        mocked = AsyncMock(return_value={"total": 0, "page": 1, "pageSize": 100001, "list": [], "scan_context": {}})
        with patch.object(OrphanFileService, "get_orphan_list", mocked):
            response = self.client.get("/api/v1/orphan-files/list?page_size=100001")

        assert response.status_code == 422, "page_size=100001 应被校验拒绝"
        mocked.assert_not_awaited(), "校验失败不应进入业务逻辑"

    def test_cleanup_passes_scan_id_and_shared_store(self):
        from app.services.orphan_file_service import OrphanFileService

        mocked = AsyncMock(
            return_value={
                "success_count": 0,
                "failed_count": 0,
                "failed_list": [],
                "total_size": 0,
            }
        )
        with patch.object(OrphanFileService, "cleanup_orphans", mocked):
            response = self.client.post(
                "/api/v1/orphan-files/cleanup",
                json={"scan_id": "scan-latest", "orphan_ids": [1]},
            )

        assert response.status_code == 200
        assert response.json()["code"] == "200"
        kwargs = mocked.await_args.kwargs
        assert kwargs["scan_id"] == "scan-latest"
        assert kwargs["store"] is self.app.state.store

    def test_purge_submits_persistent_job_without_waiting_for_delete(self):
        """彻底删除端点只持久化并调度任务，不在 HTTP 请求内执行物理删除。"""
        from app.services.orphan_purge_job_service import OrphanPurgeJobService

        job = MagicMock()
        job.task_id = "purge-task-1"
        job.to_dict.return_value = {
            "task_id": job.task_id,
            "status": "pending",
            "total_count": 1,
        }
        create_job = AsyncMock(return_value=job)
        dispatcher = MagicMock()

        with (
            patch.object(OrphanPurgeJobService, "create_job", create_job),
            patch(
                "app.api.endpoints.orphan_files.get_orphan_purge_dispatcher",
                return_value=dispatcher,
            ),
        ):
            response = self.client.post(
                "/api/v1/orphan-files/purge",
                json={"canonical_paths": ["/data/orphan.bin"]},
            )

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "pending"
        create_job.assert_awaited_once_with(
            canonical_paths=["/data/orphan.bin"],
            operator="tester",
        )
        dispatcher.submit.assert_called_once_with("purge-task-1")

    def test_get_purge_job_status_returns_persisted_state(self):
        from app.services.orphan_purge_job_service import OrphanPurgeJobService

        job = MagicMock()
        job.to_dict.return_value = {
            "task_id": "purge-task-1",
            "status": "completed",
            "total_count": 1,
            "purged_count": 1,
            "failed_count": 0,
        }
        get_job = AsyncMock(return_value=job)
        with patch.object(OrphanPurgeJobService, "get_job", get_job):
            response = self.client.get("/api/v1/orphan-files/purge-jobs/purge-task-1")

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "completed"
        get_job.assert_awaited_once_with("purge-task-1")

    def test_get_list_valid_token_not_rejected_by_auth(self):
        """GET /list：有效 token 不应被 401 拒绝"""
        response = self.client.get(
            "/api/v1/orphan-files/list",
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] != "401"

    def test_cleanup_preview_validates_body(self):
        """POST /cleanup-preview：有效 token + 有效 body 不被 401 拒绝"""
        response = self.client.post(
            "/api/v1/orphan-files/cleanup-preview",
            json={"scan_id": "scan-latest", "orphan_ids": [1, 2]},
            headers={"x-access-token": _create_valid_token()},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] != "401"


# 延迟导入，避免模块加载时触发 settings 初始化
from app.auth.dependencies import require_authenticated_user  # noqa: E402
