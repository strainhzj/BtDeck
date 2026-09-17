# -*- coding: utf-8 -*-
"""
按下载器触发 Tracker 批量操作 API 接口单元测试

测试2个API端点（tracker.py，2026-09-12 新增）：
- POST /tracker/addTracker-by-downloader （按下载器添加 tracker）
- POST /tracker/modifyTracker-by-downloader （按下载器替换 tracker 列表）

覆盖场景：
- 参数校验（trackers 全空白 → 400）
- 下载器行不存在 → 404
- 下载器下无种子 → 404
- 下载器缓存（app.state.store）不可用 → 500
- 正常执行（qb / tr 双类型、add / modify 双操作）
- 单条失败计数与部分成功（PARTIAL 审计结果）
- 汇总审计单条记录（by_downloader 口径，替代 per-torrent 刷库）
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints import tracker
from app.auth.dependencies import require_authenticated_user
from app.database import get_async_db
from app.torrents.audit_enums import AuditOperationResult

URL_ADD = "/tracker/addTracker-by-downloader"
URL_MODIFY = "/tracker/modifyTracker-by-downloader"


# ==================== 共享构造 ====================


def _make_downloader_row(*, is_qbittorrent=True, is_transmission=False):
    """BtDownloaders 行 mock（类型判定依据）"""
    return SimpleNamespace(
        downloader_id="dl-1",
        is_qbittorrent=is_qbittorrent,
        is_transmission=is_transmission,
    )


def _make_torrent(info_id, torrent_id):
    """torrentInfo 行 mock"""
    return SimpleNamespace(
        info_id=info_id,
        torrent_id=torrent_id,
        downloader_id="dl-1",
        name=f"种子-{info_id}",
    )


def _make_db(downloader_row, torrents):
    """AsyncSession mock：execute 第1次返回下载器行，第2次返回种子列表"""
    db = MagicMock()
    dl_result = MagicMock()
    dl_result.scalars.return_value.first.return_value = downloader_row
    ti_result = MagicMock()
    ti_result.scalars.return_value.all.return_value = torrents
    db.execute = AsyncMock(side_effect=[dl_result, ti_result])
    return db


def _set_store(app):
    """注入异步 get_snapshot 伪 store（下载器 VO 含可用 client）"""

    class FakeStore:
        async def get_snapshot(self_inner):
            return [
                SimpleNamespace(
                    downloader_id="dl-1",
                    nickname="qb_dl",
                    fail_time=0,
                    client=MagicMock(),
                )
            ]

    app.state.store = FakeStore()


def _make_client(db):
    """独立 FastAPI app：覆盖认证与异步 DB 依赖（仿 test_active_torrents_endpoint）"""
    app = FastAPI()
    app.include_router(tracker.router, prefix="/tracker")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    app.dependency_overrides[get_async_db] = lambda: db
    _set_store(app)
    return TestClient(app, raise_server_exceptions=False)


def _payload(trackers="https://tracker.example.com/announce"):
    return {"downloader_id": "dl-1", "trackers": trackers}


# ==================== 测试：参数与范围校验 ====================


class TestTrackerByDownloaderValidation:
    """参数与范围校验"""

    def test_blank_trackers_returns_400(self):
        """trackers 全空白（;;分隔后无有效项）应返回 400，不触达下载器调用"""
        db = _make_db(_make_downloader_row(), [_make_torrent("i1", "h1")])
        client = _make_client(db)
        with (
            patch.object(tracker, "qb_add_torrents_tracker", AsyncMock()) as qb_add,
            patch.object(tracker, "_write_tracker_audit_log_async", AsyncMock()),
        ):
            resp = client.post(URL_ADD, json=_payload(" ; ; "))
        data = resp.json()
        assert data["code"] == "400"
        qb_add.assert_not_awaited()

    def test_downloader_row_not_found_returns_404(self):
        """下载器行不存在（BtDownloaders 无记录）应返回 404"""
        db = _make_db(None, [_make_torrent("i1", "h1")])
        client = _make_client(db)
        with patch.object(tracker, "_write_tracker_audit_log_async", AsyncMock()):
            resp = client.post(URL_ADD, json=_payload())
        data = resp.json()
        assert data["code"] == "404"
        assert "下载器不存在" in data["msg"]

    def test_no_torrents_returns_404(self):
        """下载器下无种子应返回 404（同 reannounce-by-downloader 口径）"""
        db = _make_db(_make_downloader_row(), [])
        client = _make_client(db)
        with patch.object(tracker, "_write_tracker_audit_log_async", AsyncMock()):
            resp = client.post(URL_MODIFY, json=_payload())
        data = resp.json()
        assert data["code"] == "404"
        assert "没有种子" in data["msg"]

    def test_store_missing_returns_500(self):
        """app.state.store 未初始化：下载器缓存不可用整体失败（fail-closed）"""
        db = _make_db(_make_downloader_row(), [_make_torrent("i1", "h1")])
        app = FastAPI()
        app.include_router(tracker.router, prefix="/tracker")
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
        app.dependency_overrides[get_async_db] = lambda: db
        # 不注入 app.state.store
        client = TestClient(app, raise_server_exceptions=False)
        with patch.object(tracker, "_write_tracker_audit_log_async", AsyncMock()):
            resp = client.post(URL_ADD, json=_payload())
        data = resp.json()
        assert data["code"] == "500"
        assert "缓存未初始化" in data["msg"]


# ==================== 测试：正常执行 ====================


class TestTrackerByDownloaderExecution:
    """正常执行与类型分发"""

    def test_add_qb_success(self):
        """qb 下载器：逐种子调 qb_add_torrents_tracker，计数与汇总审计正确"""
        torrents = [_make_torrent("i1", "h1"), _make_torrent("i2", "h2")]
        db = _make_db(_make_downloader_row(is_qbittorrent=True), torrents)
        client = _make_client(db)
        qb_add = AsyncMock()
        audit = AsyncMock()
        with (
            patch.object(tracker, "qb_add_torrents_tracker", qb_add),
            patch.object(tracker, "tr_add_torrents_tracker", AsyncMock()) as tr_add,
            patch.object(tracker, "_write_tracker_audit_log_async", audit),
        ):
            resp = client.post(URL_ADD, json=_payload("https://a.example/announce;https://b.example/announce"))

        data = resp.json()
        assert data["code"] == "200"
        assert data["data"] == {"success_count": 2, "failed_count": 0}
        # 两个 tracker 均去空白；每种子一次调用
        assert qb_add.await_count == 2
        awaited_tracker_list = qb_add.await_args_list[0].args[2]
        assert awaited_tracker_list == ["https://a.example/announce", "https://b.example/announce"]
        assert qb_add.await_args_list[0].args[3] == "h1"
        assert qb_add.await_args_list[0].args[4] == "i1"
        tr_add.assert_not_awaited()
        # 汇总审计单条：by_downloader 口径 + SUCCESS
        audit.assert_awaited_once()
        kwargs = audit.await_args.kwargs
        assert kwargs["operation_detail"]["operation"] == "add_by_downloader"
        assert kwargs["operation_detail"]["torrent_count"] == 2
        assert kwargs["operation_detail"]["success_count"] == 2
        assert kwargs["downloader_id"] == "dl-1"
        assert kwargs["operation_result"] == AuditOperationResult.SUCCESS

    def test_modify_qb_calls_change_helper(self):
        """modify 端点走 qb_change_torrents_tracker（完全替换语义）"""
        torrents = [_make_torrent("i1", "h1")]
        db = _make_db(_make_downloader_row(is_qbittorrent=True), torrents)
        client = _make_client(db)
        qb_change = AsyncMock()
        audit = AsyncMock()
        with (
            patch.object(tracker, "qb_change_torrents_tracker", qb_change),
            patch.object(tracker, "qb_add_torrents_tracker", AsyncMock()) as qb_add,
            patch.object(tracker, "_write_tracker_audit_log_async", audit),
        ):
            resp = client.post(URL_MODIFY, json=_payload("https://new.example/announce"))

        data = resp.json()
        assert data["code"] == "200"
        qb_change.assert_awaited_once()
        qb_add.assert_not_awaited()
        assert audit.await_args.kwargs["operation_detail"]["operation"] == "modify_by_downloader"

    def test_tr_downloader_uses_tr_helper_with_int_id(self):
        """tr 下载器：torrent_id 转 int 传 tr_add_torrents_tracker"""
        torrents = [_make_torrent("i1", "7")]
        db = _make_db(_make_downloader_row(is_qbittorrent=False, is_transmission=True), torrents)
        client = _make_client(db)
        tr_add = AsyncMock()
        with (
            patch.object(tracker, "tr_add_torrents_tracker", tr_add),
            patch.object(tracker, "qb_add_torrents_tracker", AsyncMock()),
            patch.object(tracker, "_write_tracker_audit_log_async", AsyncMock()),
        ):
            resp = client.post(URL_ADD, json=_payload())

        assert resp.json()["code"] == "200"
        tr_add.assert_awaited_once()
        # (db, vo, tracker_list, torrent_id 转 int, info_id)
        assert tr_add.await_args_list[0].args[3] == 7
        assert tr_add.await_args_list[0].args[4] == "i1"

    def test_partial_failure_counts_and_partial_audit(self):
        """单条失败不断整体循环：计数 1/1，审计结果 PARTIAL，HTTP 仍 200"""
        torrents = [_make_torrent("i1", "h1"), _make_torrent("i2", "h2")]
        db = _make_db(_make_downloader_row(is_qbittorrent=True), torrents)
        client = _make_client(db)
        qb_add = AsyncMock(side_effect=[RuntimeError("boom"), None])
        audit = AsyncMock()
        with (
            patch.object(tracker, "qb_add_torrents_tracker", qb_add),
            patch.object(tracker, "_write_tracker_audit_log_async", audit),
        ):
            resp = client.post(URL_ADD, json=_payload())

        data = resp.json()
        assert data["code"] == "200"
        assert data["data"] == {"success_count": 1, "failed_count": 1}
        assert audit.await_args.kwargs["operation_result"] == AuditOperationResult.PARTIAL
