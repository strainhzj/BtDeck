# -*- coding: utf-8 -*-
"""
孤儿文件管理端点认证与契约单元测试（v1.0.6）

验证 orphan-files 端点在以下场景下的行为：
- 无 token / 无效 token / 过期 token → 返回 401
- 有效 token → 不被 401 拒绝（正常进入业务逻辑）

测试端点（均走 require_authenticated_user 认证）：
- GET    /api/v1/orphan-files/latest
- GET    /api/v1/orphan-files/list
- POST   /api/v1/orphan-files/hardlink-copies
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

    def test_post_hardlink_copies_no_token_returns_401(self):
        """POST /hardlink-copies：无 token 应返回 401。"""
        response = self.client.post(
            "/api/v1/orphan-files/hardlink-copies",
            json={"orphan_ids": [1]},
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

    def test_cleanup_preview_resolves_select_all_filter_snapshot(self):
        """全选请求应先按筛选与排除项解析 ID，再进入既有安全预览。"""
        from app.services.orphan_file_service import OrphanFileService

        resolve_selection = AsyncMock(return_value=[11, 13])
        preview = AsyncMock(return_value={"total_count": 2, "total_size": 30, "items": []})
        with (
            patch.object(OrphanFileService, "resolve_orphan_selection", resolve_selection),
            patch.object(OrphanFileService, "cleanup_preview", preview),
        ):
            response = self.client.post(
                "/api/v1/orphan-files/cleanup-preview",
                json={
                    "scan_id": "scan-latest",
                    "select_all": True,
                    "excluded_orphan_ids": [12],
                    "filters": {
                        "status": "pending",
                        "confidence": "high",
                        "path_like": "movie",
                    },
                },
            )

        assert response.status_code == 200
        assert response.json()["data"]["total_count"] == 2
        resolve_selection.assert_awaited_once_with(
            orphan_ids=[],
            select_all=True,
            excluded_orphan_ids=[12],
            scan_id="scan-latest",
            downloader_id=None,
            min_size=None,
            path_like="movie",
            path_prefix=None,
            status="pending",
            confidence="high",
        )
        preview.assert_awaited_once_with([11, 13], scan_id="scan-latest")

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
            path_prefix=None,
            status=None,
            confidence=None,
        )

    def test_hardlink_copy_locations_passes_ids_and_preserves_result(self):
        """副本位置端点按 ID 查询，并原样返回范围内定位与未定位数量。"""
        from app.services.orphan_file_service import OrphanFileService

        payload = {
            "requested_count": 2,
            "resolved_count": 2,
            "missing_orphan_ids": [],
            "total_copy_count": 3,
            "total_found_count": 2,
            "total_unlocated_count": 1,
            "unknown_count": 0,
            "searched_root_count": 2,
            "search_error": None,
            "items": [],
        }
        mocked = AsyncMock(return_value=payload)
        with patch.object(OrphanFileService, "get_hardlink_copy_locations", mocked):
            response = self.client.post(
                "/api/v1/orphan-files/hardlink-copies",
                json={"orphan_ids": [7, 8]},
            )

        assert response.status_code == 200
        assert response.json()["code"] == "200"
        assert response.json()["data"] == payload
        mocked.assert_awaited_once_with([7, 8])

    @pytest.mark.parametrize(
        "orphan_ids",
        ([], list(range(5001))),
        ids=("empty", "over-limit"),
    )
    def test_hardlink_copy_locations_rejects_invalid_batch_size(self, orphan_ids):
        """空批次和超过 5000 项的批次在进入目录扫描前由请求模型拒绝。"""
        from app.services.orphan_file_service import OrphanFileService

        mocked = AsyncMock()
        with patch.object(OrphanFileService, "get_hardlink_copy_locations", mocked):
            response = self.client.post(
                "/api/v1/orphan-files/hardlink-copies",
                json={"orphan_ids": orphan_ids},
            )

        assert response.status_code == 422
        mocked.assert_not_awaited()

    def test_ignore_passes_scan_identity_and_preserves_failure_reasons(self):
        """忽视端点必须把服务层逐项失败原因原样返回，供前端和日志诊断。"""
        from app.services.orphan_file_service import OrphanFileService

        payload = {
            "success_count": 0,
            "failed_count": 1,
            "failed_list": [
                {
                    "id": 7,
                    "file_path": "/data/a.bin",
                    "reason": "当前候选状态不存在或已失效",
                }
            ],
        }
        mocked = AsyncMock(return_value=payload)
        with patch.object(OrphanFileService, "set_ignored", mocked):
            response = self.client.post(
                "/api/v1/orphan-files/ignore",
                json={
                    "scan_id": "scan-latest",
                    "orphan_ids": [7],
                    "ignored": True,
                },
            )

        assert response.status_code == 200
        assert response.json()["code"] == "200"
        assert response.json()["data"] == payload
        mocked.assert_awaited_once_with(
            orphan_ids=[7],
            ignored=True,
            operator="tester",
            scan_id="scan-latest",
        )

    def test_list_accepts_page_size_upper_bound_1000(self):
        """page_size 上限 1000 应被接受（与孤儿列表虚拟窗口批次上限对齐）。

        大于 1000 的请求会造成超大 SQL IN、响应序列化和浏览器内存峰值；
        列表通过滚动追加继续访问全部结果，不需要单批返回更多数据。
        """
        from app.services.orphan_file_service import OrphanFileService

        mocked = AsyncMock(return_value={"total": 0, "page": 1, "pageSize": 1000, "list": [], "scan_context": {}})
        with patch.object(OrphanFileService, "get_orphan_list", mocked):
            response = self.client.get("/api/v1/orphan-files/list?page_size=1000")

        assert response.status_code == 200, "page_size=1000 应被接受"
        mocked.assert_awaited_once_with(
            page=1,
            page_size=1000,
            downloader_id=None,
            min_size=None,
            path_like=None,
            path_prefix=None,
            status=None,
            confidence=None,
        )

    def test_list_rejects_page_size_over_upper_bound(self):
        """page_size 超过 1000 应被 Pydantic 校验拒绝（422），不进入业务逻辑。"""
        from app.services.orphan_file_service import OrphanFileService

        mocked = AsyncMock(return_value={"total": 0, "page": 1, "pageSize": 1001, "list": [], "scan_context": {}})
        with patch.object(OrphanFileService, "get_orphan_list", mocked):
            response = self.client.get("/api/v1/orphan-files/list?page_size=1001")

        assert response.status_code == 422, "page_size=1001 应被校验拒绝"
        mocked.assert_not_awaited(), "校验失败不应进入业务逻辑"

    def test_cleanup_submits_persistent_job_without_waiting_for_manifest(self):
        from app.services.orphan_purge_job_service import (
            OrphanJobSubmission,
            OrphanPurgeJobService,
        )

        job = MagicMock()
        job.task_id = "cleanup-task-1"
        job.to_dict.return_value = {
            "task_id": job.task_id,
            "operation_type": "cleanup",
            "status": "pending",
            "total_count": 1,
        }
        submit_job = AsyncMock(
            return_value=OrphanJobSubmission(
                operation_type="cleanup",
                scan_id="scan-latest",
                job=job,
                accepted_items=[1],
                skipped_items=[],
            )
        )
        dispatcher = MagicMock()
        with (
            patch.object(OrphanPurgeJobService, "submit_cleanup_job", submit_job),
            patch(
                "app.api.endpoints.orphan_files.get_orphan_purge_dispatcher",
                return_value=dispatcher,
            ),
        ):
            response = self.client.post(
                "/api/v1/orphan-files/cleanup",
                json={"scan_id": "scan-latest", "orphan_ids": [1]},
            )

        assert response.status_code == 200
        assert response.json()["code"] == "200"
        assert response.json()["data"]["status"] == "pending"
        submit_job.assert_awaited_once_with(
            scan_id="scan-latest",
            orphan_ids=[1],
            operator="tester",
        )
        dispatcher.submit.assert_called_once_with("cleanup-task-1")

    def test_cleanup_all_active_returns_success_without_dispatch(self):
        from app.services.orphan_purge_job_service import (
            OrphanJobSubmission,
            OrphanPurgeJobService,
        )

        submission = OrphanJobSubmission(
            operation_type="cleanup",
            scan_id="scan-latest",
            job=None,
            accepted_items=[],
            skipped_items=[1],
        )
        dispatcher = MagicMock()
        with (
            patch.object(
                OrphanPurgeJobService,
                "submit_cleanup_job",
                AsyncMock(return_value=submission),
            ),
            patch(
                "app.api.endpoints.orphan_files.get_orphan_purge_dispatcher",
                return_value=dispatcher,
            ),
        ):
            response = self.client.post(
                "/api/v1/orphan-files/cleanup",
                json={"scan_id": "scan-latest", "orphan_ids": [1]},
            )

        assert response.status_code == 200
        assert response.json()["code"] == "200"
        assert response.json()["data"]["task_id"] is None
        assert response.json()["data"]["status"] == "already_running"
        assert response.json()["data"]["skipped_count"] == 1
        dispatcher.submit.assert_not_called()

    def test_purge_submits_persistent_job_without_waiting_for_delete(self):
        """彻底删除端点只持久化并调度任务，不在 HTTP 请求内执行物理删除。"""
        from app.services.orphan_purge_job_service import (
            OrphanJobSubmission,
            OrphanPurgeJobService,
        )

        job = MagicMock()
        job.task_id = "purge-task-1"
        job.to_dict.return_value = {
            "task_id": job.task_id,
            "status": "pending",
            "total_count": 1,
        }
        submit_job = AsyncMock(
            return_value=OrphanJobSubmission(
                operation_type="purge",
                scan_id=None,
                job=job,
                accepted_items=["/data/orphan.bin"],
                skipped_items=[],
            )
        )
        dispatcher = MagicMock()

        with (
            patch.object(OrphanPurgeJobService, "submit_purge_job", submit_job),
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
        submit_job.assert_awaited_once_with(
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

    def test_get_cleanup_job_status_returns_persisted_state(self):
        from app.services.orphan_purge_job_service import OrphanPurgeJobService

        job = MagicMock()
        job.operation_type = "cleanup"
        job.to_dict.return_value = {
            "task_id": "cleanup-task-1",
            "operation_type": "cleanup",
            "status": "completed",
            "total_count": 1,
            "success_count": 1,
            "failed_count": 0,
        }
        get_job = AsyncMock(return_value=job)
        with patch.object(OrphanPurgeJobService, "get_job", get_job):
            response = self.client.get("/api/v1/orphan-files/cleanup-jobs/cleanup-task-1")

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "completed"
        get_job.assert_awaited_once_with("cleanup-task-1")

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


class TestOrphanFilesPrefixMatch:
    """左匹配（前缀）快捷操作端点与 select_all 透传契约。"""

    def setup_method(self):
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.dependency_overrides[get_async_db] = lambda: MagicMock()
        self.app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
        self.client = TestClient(self.app)

    def test_prefix_match_preview_no_token_returns_401(self):
        """POST /prefix-match-preview：无 token 必须 401。"""
        # 撤销 setup_method 里对认证的 override，恢复真实认证依赖
        self.app.dependency_overrides.pop(require_authenticated_user, None)
        response = self.client.post(
            "/api/v1/orphan-files/prefix-match-preview",
            json={"path_prefix": "/data/", "scan_id": "scan-latest"},
        )
        assert response.status_code == 401

    def test_prefix_match_preview_invokes_service(self):
        """POST /prefix-match-preview：应调用 prefix_match_preview 并原样返回结果。"""
        from app.services.orphan_file_service import OrphanFileService

        payload = {
            "count": 3,
            "total_size": 1234,
            "low_confidence_count": 1,
            "sample_paths": ["/data/a.bin", "/data/b.bin"],
        }
        mocked = AsyncMock(return_value=payload)
        with patch.object(OrphanFileService, "prefix_match_preview", mocked):
            response = self.client.post(
                "/api/v1/orphan-files/prefix-match-preview",
                json={"path_prefix": "/data/", "scan_id": "scan-latest"},
            )
        assert response.status_code == 200
        assert response.json()["code"] == "200"
        assert response.json()["data"] == payload
        mocked.assert_awaited_once_with("/data/", "scan-latest")

    def test_prefix_match_preview_rejects_empty_prefix(self):
        """path_prefix 为空字符串应被 Pydantic min_length=1 拒绝（422）。"""
        response = self.client.post(
            "/api/v1/orphan-files/prefix-match-preview",
            json={"path_prefix": "", "scan_id": "scan-latest"},
        )
        assert response.status_code == 422

    def test_cleanup_select_all_passes_path_prefix_filter(self):
        """select_all + filters.path_prefix 应透传到 resolve_orphan_selection。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.services.orphan_purge_job_service import (
            OrphanJobSubmission,
            OrphanPurgeJobService,
        )

        resolve_selection = AsyncMock(return_value=[1, 2])
        fake_job = SimpleNamespace(
            task_id="task-prefix",
            to_dict=lambda: {"task_id": "task-prefix", "operation_type": "cleanup"},
        )
        submission = OrphanJobSubmission(
            operation_type="cleanup",
            scan_id="scan-latest",
            job=fake_job,
            accepted_items=[1, 2],
            skipped_items=[],
        )
        with (
            patch.object(OrphanFileService, "resolve_orphan_selection", resolve_selection),
            patch.object(
                OrphanPurgeJobService,
                "submit_cleanup_job",
                AsyncMock(return_value=submission),
            ),
            patch("app.api.endpoints.orphan_files.get_orphan_purge_dispatcher"),
        ):
            self.client.post(
                "/api/v1/orphan-files/cleanup",
                json={
                    "scan_id": "scan-latest",
                    "select_all": True,
                    "filters": {"path_prefix": "/data/leak/", "status": "pending"},
                },
            )
        resolve_selection.assert_awaited_once_with(
            orphan_ids=[],
            select_all=True,
            excluded_orphan_ids=[],
            scan_id="scan-latest",
            downloader_id=None,
            min_size=None,
            path_like=None,
            path_prefix="/data/leak/",
            status="pending",
            confidence=None,
        )

    def test_ignore_select_all_passes_path_prefix_filter(self):
        """ignore 的 select_all + filters.path_prefix 应透传到 resolve_orphan_selection。"""
        from app.services.orphan_file_service import OrphanFileService

        resolve_selection = AsyncMock(return_value=[5, 6])
        with (
            patch.object(OrphanFileService, "resolve_orphan_selection", resolve_selection),
            patch.object(
                OrphanFileService,
                "set_ignored",
                AsyncMock(return_value={"success_count": 2, "failed_count": 0, "failed_list": []}),
            ),
        ):
            self.client.post(
                "/api/v1/orphan-files/ignore",
                json={
                    "scan_id": "scan-latest",
                    "select_all": True,
                    "ignored": True,
                    "filters": {"path_prefix": "/data/leak/", "status": "pending"},
                },
            )
        resolve_selection.assert_awaited_once_with(
            orphan_ids=[],
            select_all=True,
            excluded_orphan_ids=[],
            scan_id="scan-latest",
            downloader_id=None,
            min_size=None,
            path_like=None,
            path_prefix="/data/leak/",
            status="pending",
            confidence=None,
        )


# 延迟导入，避免模块加载时触发 settings 初始化
from app.auth.dependencies import require_authenticated_user  # noqa: E402
