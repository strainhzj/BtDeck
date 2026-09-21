# -*- coding: utf-8 -*-
"""双语 P5 错误契约测试（删除链路 / 回收站，E13～E16）。

锁定的不变量（PLANS/desktop-bilingual.md §3.3、error-contract.md §1 原则）：
- CommonResponse 信封四字段不变；仅 data 新增 reasonCode 字段；
- 前端依赖 reasonCode 本地化展示（禁止按中文 msg 匹配），因此 reasonCode
  取值属于对外契约，本文件逐路径钉死；
- 动态拼接 msg（str(e)/task_id/异常类名）只进日志，msg 固定（防泄露 + 可翻译）；
- E14 双形态（code=200 受理语义）：有 task_id → TORRENT_DELETE_ACCEPTED；
  全部已在处理（task_id=None）→ TORRENT_DELETE_ALREADY_PROCESSED，
  两种形态均不得改 code（B03 信封兼容冻结）；
- E16 回收站手动还原 stub → 501 + NOT_IMPLEMENTED（明示未开放而非失败）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import get_current_user, require_authenticated_user
from app.database import Base, get_async_db, get_db
from app.downloader.models import BtDownloaders
from app.services.audit_service import get_audit_service
from app.torrents.models import TorrentInfo
from tests.api.conftest import make_torrent

URL_DELETE = "/api/v1/torrents/delete"
URL_DELETE_LEVEL = "/api/v1/torrents/delete-with-level"
URL_ASYNC = "/api/v1/torrents/delete-batch-async"
URL_STATUS = "/api/v1/torrents/delete-batch-status"
URL_BIN = "/api/v1/recycle/bin"
URL_RESTORE = "/api/v1/recycle/restore"
URL_RESTORE_MANUAL = "/api/v1/recycle/restore-manual"
URL_PREVIEW = "/api/v1/recycle/cleanup-preview"
URL_CLEANUP = "/api/v1/recycle/cleanup"


def _reason_code(body: dict) -> str:
    data = body["data"]
    assert isinstance(data, dict), f"data 应为携带 reasonCode 的 dict，实际: {data!r}"
    return data["reasonCode"]


def _envelope_keys(body: dict) -> set:
    """信封四字段形状（B03 兼容冻结）。"""
    return set(body.keys())


class _FakeAsyncSessionCtx:
    """AsyncSessionLocal() 的替身：async with 直接返回 MagicMock 会话。"""

    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *args):
        return False


class _FakeStore:
    """最小化下载器缓存替身：get_snapshot 返回注入的 VO 列表。"""

    def __init__(self, items=None):
        self._items = items or []

    async def get_snapshot(self):
        return self._items


@pytest.fixture()
def sync_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[TorrentInfo.__table__, BtDownloaders.__table__])
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(sync_engine):
    Session = sessionmaker(bind=sync_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    """内存库 + 认证豁免的 TestClient（同步 SessionLocal 一并指到内存库）。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    app.dependency_overrides[get_audit_service] = lambda: None

    with patch("app.database.SessionLocal", return_value=db_session):
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


def _make_torrent_row(db, info_id="t1", downloader_id="dl-a"):
    make_torrent(
        db,
        info_id=info_id,
        downloader_id=downloader_id,
        hash_="hash-" + info_id,
        name="torrent-" + info_id,
        status="paused",
    )


# ====================================================================
# 一、E14：异步批量删除提交（/torrents/delete-batch-async）
# ====================================================================


def _submission(task_id, accepted, skipped):
    from app.services.deletion_task_manager import DeletionTaskSubmission

    return DeletionTaskSubmission(
        task_id=task_id,
        accepted_info_ids=accepted,
        skipped_info_ids=skipped,
    )


class TestBatchDeleteSubmitContract:
    def test_accepted_returns_200_with_reason_code(self, client):
        """有 task_id → code=200（受理语义不变）+ data.reasonCode=TORRENT_DELETE_ACCEPTED。"""
        manager = MagicMock()
        manager.create_task_reserving = AsyncMock(return_value=_submission("task-1", ["a"], []))

        def _close(coroutine):
            coroutine.close()
            return MagicMock()

        with (
            patch("app.services.deletion_task_manager.get_deletion_task_manager", return_value=manager),
            patch("app.services.async_deletion_executor.AsyncDeletionExecutor"),
            patch("app.api.endpoints.torrent_deletion.asyncio.create_task", side_effect=_close),
        ):
            resp = client.post(URL_ASYNC, json={"torrent_info_ids": ["a"], "delete_level": 2})

        body = resp.json()
        assert body["code"] == "200"
        assert body["status"] == "success"
        assert _reason_code(body) == "TORRENT_DELETE_ACCEPTED"
        assert _envelope_keys(body) == {"code", "msg", "data", "status"}

    def test_already_processed_returns_200_with_reason_code(self, client):
        """全部已在处理（task_id=None）→ code=200 不变 + TORRENT_DELETE_ALREADY_PROCESSED。"""
        manager = MagicMock()
        manager.create_task_reserving = AsyncMock(return_value=_submission(None, [], ["a", "b"]))

        with (
            patch("app.services.deletion_task_manager.get_deletion_task_manager", return_value=manager),
            patch("app.services.async_deletion_executor.AsyncDeletionExecutor"),
        ):
            resp = client.post(URL_ASYNC, json={"torrent_info_ids": ["a", "b"], "delete_level": 4})

        body = resp.json()
        assert body["code"] == "200"
        assert body["data"]["task_id"] is None
        assert _reason_code(body) == "TORRENT_DELETE_ALREADY_PROCESSED"

    def test_submit_failure_fixed_msg_with_reason_code(self, client):
        """提交异常 → 500 + TORRENT_DELETE_SUBMIT_FAILED + msg 固定（str(e) 不进 msg）。"""
        manager = MagicMock()
        manager.create_task_reserving = AsyncMock(side_effect=RuntimeError("boom-detail"))

        with patch("app.services.deletion_task_manager.get_deletion_task_manager", return_value=manager):
            resp = client.post(URL_ASYNC, json={"torrent_info_ids": ["a"], "delete_level": 1})

        body = resp.json()
        assert body["code"] == "500"
        assert body["status"] == "error"
        assert _reason_code(body) == "TORRENT_DELETE_SUBMIT_FAILED"
        assert body["msg"] == "提交删除任务失败"
        assert "boom-detail" not in body["msg"]


# ====================================================================
# 二、批量删除任务状态查询（/torrents/delete-batch-status/{task_id}）
# ====================================================================


class TestBatchDeleteStatusContract:
    def test_task_not_found_fixed_msg_with_reason_code(self, client):
        """任务不存在 → 404 + msg 固定（task_id 不再拼进 msg）+ TORRENT_DELETE_TASK_NOT_FOUND。"""
        manager = MagicMock()
        manager.get_task = AsyncMock(return_value=None)

        with patch("app.services.deletion_task_manager.get_deletion_task_manager", return_value=manager):
            resp = client.get(URL_STATUS + "/missing-task")

        body = resp.json()
        assert body["code"] == "404"
        assert _reason_code(body) == "TORRENT_DELETE_TASK_NOT_FOUND"
        assert body["msg"] == "任务不存在"
        assert "missing-task" not in body["msg"]

    def test_status_query_failure_fixed_msg_with_reason_code(self, client):
        """查询异常 → 500 + TORRENT_DELETE_STATUS_QUERY_FAILED + msg 固定。"""
        manager = MagicMock()
        manager.get_task = AsyncMock(side_effect=RuntimeError("boom-detail"))

        with patch("app.services.deletion_task_manager.get_deletion_task_manager", return_value=manager):
            resp = client.get(URL_STATUS + "/t1")

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "TORRENT_DELETE_STATUS_QUERY_FAILED"
        assert body["msg"] == "查询任务状态失败"
        assert "boom-detail" not in body["msg"]


# ====================================================================
# 三、按等级删除同步接口（/torrents/delete-with-level）
# ====================================================================


class TestDeleteWithLevelContract:
    def test_db_error_returns_reason_code(self, client):
        """服务层 SQLAlchemyError → 500 + DB_OPERATION_FAILED。"""
        with patch(
            "app.services.torrent_deletion_by_level.TorrentDeletionByLevelService",
            side_effect=SQLAlchemyError("db-boom"),
        ):
            resp = client.delete(URL_DELETE_LEVEL, params={"torrent_info_ids": "x", "delete_level": 4})

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "DB_OPERATION_FAILED"

    def test_value_error_fixed_msg_with_reason_code(self, client):
        """ValueError → 400 + TORRENT_DELETE_INVALID_PARAMS + msg 固定（str(e) 不进 msg）。"""
        with patch(
            "app.services.torrent_deletion_by_level.TorrentDeletionByLevelService",
            side_effect=ValueError("bad-param-detail"),
        ):
            resp = client.delete(URL_DELETE_LEVEL, params={"torrent_info_ids": "x", "delete_level": 4})

        body = resp.json()
        assert body["code"] == "400"
        assert _reason_code(body) == "TORRENT_DELETE_INVALID_PARAMS"
        assert body["msg"] == "参数错误"
        assert "bad-param-detail" not in body["msg"]


# ====================================================================
# 四、旧删除接口（/torrents/delete）下载器分支（E13）
# ====================================================================


class TestLegacyDeleteContract:
    def test_cache_missing_returns_reason_code(self, client, db_session):
        """torrent 存在 + app.state.store 缺失 → 500 + DOWNLOADER_CACHE_UNAVAILABLE。"""
        _make_torrent_row(db_session)

        with (
            patch("app.database.AsyncSessionLocal", return_value=_FakeAsyncSessionCtx()),
            patch("app.services.audit_service.get_audit_service", new=AsyncMock(return_value=MagicMock())),
        ):
            resp = client.delete(
                URL_DELETE,
                params={"info_id": "t1", "downloader_id": "dl-a", "delete_data": 0, "id_recycle": 1},
            )

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "DOWNLOADER_CACHE_UNAVAILABLE"

    def test_adapter_init_failure_fixed_msg_with_reason_code(self, client, db_session):
        """适配器创建异常 → 500 + DOWNLOADER_ADAPTER_INIT_FAILED + msg 固定（str(e) 不进 msg）。"""
        _make_torrent_row(db_session)
        vo = SimpleNamespace(
            downloader_id="dl-a",
            nickname="A",
            downloader_type=0,
            fail_time=0,
            client=MagicMock(),
        )
        client_ = client  # 避免 fixture 变量遮蔽
        # TestClient fixture 挂载的 app 可通过 last response 反查；这里直接用 with 复刻同一 app 不必要，
        # 直接发请求（fixture 内 app.state.store 由本用例注入）。
        client_.app.state.store = _FakeStore([vo])

        with (
            patch("app.database.AsyncSessionLocal", return_value=_FakeAsyncSessionCtx()),
            patch("app.services.audit_service.get_audit_service", new=AsyncMock(return_value=MagicMock())),
            patch(
                "app.services.torrent_deletion_service.DownloaderAdapterFactory.create_adapter",
                side_effect=RuntimeError("adapter-boom"),
            ),
        ):
            resp = client_.delete(
                URL_DELETE,
                params={"info_id": "t1", "downloader_id": "dl-a", "delete_data": 0, "id_recycle": 1},
            )

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "DOWNLOADER_ADAPTER_INIT_FAILED"
        assert body["msg"] == "下载器适配器初始化失败"
        assert "adapter-boom" not in body["msg"]

    def test_delete_failed_count_returns_reason_code(self, client, db_session):
        """删除结果 failed_count>0 → 500 + TORRENT_DELETE_FAILED + 计数字段保留。"""
        failed_result = SimpleNamespace(
            success_count=0, failed_count=1, skipped_count=0, failed_torrents=[{"info_id": "t1"}], total_size_freed=0
        )
        with (
            patch("app.database.AsyncSessionLocal", return_value=_FakeAsyncSessionCtx()),
            patch("app.services.audit_service.get_audit_service", new=AsyncMock(return_value=MagicMock())),
            patch.object(
                __import__(
                    "app.api.endpoints.torrent_deletion", fromlist=["TorrentDeletionService"]
                ).TorrentDeletionService,
                "delete_torrents",
                new=AsyncMock(return_value=failed_result),
            ),
        ):
            resp = client.delete(
                URL_DELETE,
                params={"info_id": "missing", "downloader_id": "dl-a", "delete_data": 0, "id_recycle": 1},
            )

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "TORRENT_DELETE_FAILED"
        assert body["data"]["failed_count"] == 1


# ====================================================================
# 五、回收站（E16 + 动态 msg 收敛）
# ====================================================================


class TestRecycleBinContract:
    def test_restore_manual_501_with_reason_code(self, client):
        """E16：手动上传还原 stub → 501 + NOT_IMPLEMENTED（明示未开放而非失败）。"""
        resp = client.post(
            URL_RESTORE_MANUAL,
            data={"torrent_id": "t1"},
            files={"torrent_file": ("a.torrent", b"...", "application/x-bittorrent")},
        )
        body = resp.json()
        assert body["code"] == "501"
        assert _reason_code(body) == "NOT_IMPLEMENTED"

    def test_bin_query_failure_fixed_msg_with_reason_code(self, client):
        with patch(
            "app.services.recycle_bin_service.RecycleBinService.get_recycle_bin_list",
            side_effect=RuntimeError("boom-detail"),
        ):
            resp = client.get(URL_BIN)

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "RECYCLE_BIN_QUERY_FAILED"
        assert body["msg"] == "回收站查询失败"
        assert "boom-detail" not in body["msg"]

    def test_restore_failure_fixed_msg_with_reason_code(self, client):
        with patch(
            "app.services.recycle_bin_service.RecycleBinService.restore_torrents",
            side_effect=RuntimeError("boom-detail"),
        ):
            resp = client.post(URL_RESTORE, json={"torrent_ids": ["t1"]})

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "RECYCLE_RESTORE_FAILED"
        assert body["msg"] == "还原种子失败"

    def test_preview_failure_fixed_msg_with_reason_code(self, client):
        with patch(
            "app.services.recycle_bin_service.RecycleBinService.cleanup_preview",
            side_effect=RuntimeError("boom-detail"),
        ):
            resp = client.post(URL_PREVIEW, json={"days": 30})

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "RECYCLE_PREVIEW_FAILED"
        assert body["msg"] == "清理预览失败"

    def test_cleanup_failure_fixed_msg_with_reason_code(self, client):
        with patch(
            "app.services.recycle_bin_service.RecycleBinService.manual_cleanup",
            side_effect=RuntimeError("boom-detail"),
        ):
            resp = client.post(URL_CLEANUP, json={"torrent_ids": ["t1"]})

        body = resp.json()
        assert body["code"] == "500"
        assert _reason_code(body) == "RECYCLE_CLEANUP_FAILED"
        assert body["msg"] == "清理回收站失败"


# ====================================================================
# 六、源码级契约：删除链路全部错误分支 reasonCode 无遗漏
# ====================================================================


def _endpoint_source() -> str:
    from pathlib import Path

    return Path("app/api/endpoints/torrent_deletion.py").read_text(encoding="utf-8")


class TestSourceContract:
    def test_no_raw_exception_in_msg(self):
        """全文件不再有 f\"...: {str(e)}\" 形态的 msg 动态拼接（诊断只进日志）。"""
        import re

        source = _endpoint_source()
        # msg= 参数值中不允许出现 str(e) 插值
        offenders = re.findall(r"msg=f\"[^\"]*\{str\(e\)\}[^\"]*\"", source)
        assert offenders == [], f"msg 仍含动态 str(e): {offenders}"

    def test_delete_chain_reason_code_inventory(self):
        """P5 新增 reasonCode 清单逐个在源码中出现（防重构丢字段）。"""
        source = _endpoint_source()
        for code in [
            "TORRENT_DELETE_ACCEPTED",
            "TORRENT_DELETE_ALREADY_PROCESSED",
            "TORRENT_DELETE_TASK_NOT_FOUND",
            "TORRENT_DELETE_SUBMIT_FAILED",
            "TORRENT_DELETE_STATUS_QUERY_FAILED",
            "TORRENT_DELETE_FAILED",
            "TORRENT_DELETE_INVALID_PARAMS",
            "DOWNLOADER_ADAPTER_INIT_FAILED",
            "DOWNLOADER_UNSUPPORTED_TYPE",
            "DOWNLOADER_CACHE_UNAVAILABLE",
            "DOWNLOADER_NOT_FOUND",
            "DOWNLOADER_OFFLINE",
            "DOWNLOADER_CONNECTION_MISSING",
        ]:
            assert f'"{code}"' in source, f"torrent_deletion.py 缺少 reasonCode: {code}"

    def test_recycle_reason_code_inventory(self):
        from pathlib import Path

        source = Path("app/api/endpoints/recycle_bin.py").read_text(encoding="utf-8")
        for code in [
            "RECYCLE_BIN_QUERY_FAILED",
            "RECYCLE_RESTORE_FAILED",
            "RECYCLE_PREVIEW_FAILED",
            "RECYCLE_CLEANUP_FAILED",
            "NOT_IMPLEMENTED",
        ]:
            assert f'"{code}"' in source, f"recycle_bin.py 缺少 reasonCode: {code}"
