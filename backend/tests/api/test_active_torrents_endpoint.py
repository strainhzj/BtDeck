# -*- coding: utf-8 -*-
"""
GET /api/v1/torrents/active-torrents 端点级回归测试。

聚焦「空响应契约」：前端 loadActiveSpeed 用 `res.code === '200'`（严格字符串相等）
判断是否把 speedSnapshotReady 置 true；后端在「无在线下载器 / 超时 / 无活动种子」
三类场景都必须返回 code="200" data=[]，否则前端会回退到“快照永不可用”，
进而使「仅显示活动种子」过滤失效（参见 commit 466e18c 修复的列表清空 bug）。

同时覆盖 P1-2 字段契约：_fetch_qb/tr_speeds_sync 返回 dict 的 keys 集合
与前端 ActiveTorrentSpeed 接口（torrents.ts:1188）一致，防字段名漂移。

模板对齐：
  - test_dashboard_api.py（FakeStore 注入 app.state.store）
  - test_torrent_list_api.py（require_authenticated_user dependency_overrides）
  - test_torrent_speed_regression.py（patch call_downloader_api 避免 lifespan 污染）
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.api import api_router
from app.api.endpoints import torrent_speed
from app.auth.dependencies import require_authenticated_user
from app.services.downloader_api_runtime import DownloadLane

URL = "/api/v1/torrents/active-torrents"

# 前端 ActiveTorrentSpeed 接口声明的 6 个字段（torrents.ts:1188-1195）
EXPECTED_SPEED_FIELDS = {
    "hash",
    "downloadSpeed",
    "uploadSpeed",
    "progress",
    "num_seeds",
    "num_leechs",
}


# ============ 辅助构造 ============


def _set_store(app, downloaders):
    """注入异步 get_snapshot 伪 store（仿 test_dashboard_api._set_store）。"""

    class FakeStore:
        async def get_snapshot(self_inner):
            return list(downloaders)

    app.state.store = FakeStore()


def _make_qb_downloader(dl_id="dl_qb", *, fail_time=0, torrents=None):
    """构造 qBittorrent 下载器：client 用 spec=qbClient 使 isinstance 通过。"""
    from qbittorrentapi import Client as qbClient

    client = MagicMock(spec=qbClient)
    client.torrents_info.return_value = torrents or []
    return SimpleNamespace(
        downloader_id=dl_id,
        downloader_type=0,
        nickname="qb_dl",
        fail_time=fail_time,
        client=client,
    )


def _make_tr_downloader(dl_id="dl_tr", *, fail_time=0, torrents=None):
    """构造 Transmission 下载器：client 用 spec=trClient 使 isinstance 通过。"""
    from transmission_rpc import Client as trClient

    client = MagicMock(spec=trClient)
    client.get_torrents.return_value = torrents or []
    return SimpleNamespace(
        downloader_id=dl_id,
        downloader_type=1,
        nickname="tr_dl",
        fail_time=fail_time,
        client=client,
    )


@pytest.fixture
def client():
    """独立 FastAPI app，覆盖 require_authenticated_user（仿 test_torrent_list_api）。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    # 同步 lambda 覆盖 async 依赖即可（FastAPI dependency_overrides 不区分 async/sync）。
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_speed_globals():
    """隔离模块级单例状态（_active_keys_cache / _ttl_queue），防用例间泄漏。

    端点每轮会写入活动集合与 TTL 队列；不重置时前序用例的 PARTIAL/过期
    快照会污染后续用例的 snapshot 断言。
    """
    torrent_speed._active_keys_cache.reset()
    torrent_speed._ttl_queue._store.clear()
    yield
    torrent_speed._active_keys_cache.reset()
    torrent_speed._ttl_queue._store.clear()


def _real_call_downloader_api():
    """patch call_downloader_api 为“真实执行同步函数”，并断言走 INTERACTIVE lane。

    全量 pytest 中其它 TestClient 退出会触发 lifespan shutdown 关闭全局
    downloader_api_runtime executor（见 test_torrent_speed_regression TestCallWithTimeout
    docstring），故必须 patch 而非依赖全局单例真实执行。
    """

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        assert lane == DownloadLane.INTERACTIVE, "速度接口必须走 INTERACTIVE lane"
        assert opts.get("timeout") == torrent_speed._DOWNLOADER_TIMEOUT
        return func(*args, **(kwargs or {}))

    return patch(
        "app.api.endpoints.torrent_speed.call_downloader_api",
        side_effect=fake_call,
    )


# ============ P0-1：活动快照响应契约（三场景） ============


class TestEmptyResponseContract:
    """守护前端 loadActiveSpeed 依赖的活动快照完整性契约。

    权威空快照返回 200；下载器失败导致的不完整快照返回 206，
    防止前端把未知状态误判为「没有活动种子」。
    """

    def test_no_online_downloader_returns_200_empty(self, client):
        """场景1：无在线下载器（torrent_speed.py:376-377）→ code='200' data=[]。"""
        _set_store(client.app, [])
        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"] == []
        assert body["status"] == "success"

    def test_downloader_timeout_returns_206_partial(self, client):
        """场景2：下载器调用超时会返回 206，标记快照不完整。"""
        import asyncio

        dl = _make_qb_downloader(torrents=[{"hash": "h1"}])

        async def timeout_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            raise asyncio.TimeoutError()

        _set_store(client.app, [dl])
        with patch(
            "app.api.endpoints.torrent_speed.call_downloader_api",
            side_effect=timeout_call,
        ):
            r = client.get(URL)
        body = r.json()
        assert body["code"] == "206"
        assert body["data"] == []
        assert body["status"] == "partial"

    def test_downloader_api_error_returns_206_partial(self, client):
        """场景2b：下载器 API 异常会返回 206，标记快照不完整。"""
        from qbittorrentapi import APIError as QbAPIError

        dl = _make_qb_downloader()

        async def error_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            raise QbAPIError("connection refused")

        _set_store(client.app, [dl])
        with patch(
            "app.api.endpoints.torrent_speed.call_downloader_api",
            side_effect=error_call,
        ):
            r = client.get(URL)
        body = r.json()
        assert body["code"] == "206"
        assert body["data"] == []
        assert body["status"] == "partial"

    def test_no_active_seeds_returns_200_empty(self, client):
        """场景3：有在线下载器但全部速度为0（:95/124 过滤后 active_torrents 空，:454）→ code='200' data=[]。"""
        # dlspeed/upspeed 均为 0，_fetch_qb_speeds_sync 过滤后返回 []
        dl = _make_qb_downloader(
            torrents=[
                {"hash": "h1", "dlspeed": 0, "upspeed": 0, "progress": 0.5},
            ]
        )
        _set_store(client.app, [dl])
        with _real_call_downloader_api():
            r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"] == []


# ============ P1-2：字段契约守护（防前后端字段名漂移） ============


class TestSpeedFieldContract:
    """守护 _fetch_qb/tr_speeds_sync 返回字段与前端 ActiveTorrentSpeed 接口一致。

    前后端无共享 schema，字段名全靠手写对齐。任一端改名（如 downloadSpeed →
    download_speed）不会被现有任何测试捕获，直到运行时前端拿不到值。
    此处断言返回 dict 的 keys 集合严格等于预期 6 字段 + progress 单位。
    """

    def test_qb_speed_dict_keys(self, client):
        """qB 活跃种子返回字段 keys 集合 == 前端 6 字段。"""
        dl = _make_qb_downloader(
            torrents=[
                {
                    "hash": "h1",
                    "dlspeed": 100,
                    "upspeed": 50,
                    "progress": 0.5,
                    "num_seeds": 2,
                    "num_leechs": 1,
                }
            ]
        )
        _set_store(client.app, [dl])
        with _real_call_downloader_api():
            r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        data = body["data"]
        assert len(data) == 1
        # 端点会额外注入 downloader_id/downloader_type，剔除后比对核心字段
        core_fields = set(data[0].keys()) - {"downloader_id", "downloader_type"}
        assert core_fields == EXPECTED_SPEED_FIELDS
        # progress 0-1 → 0-100 百分比
        assert data[0]["progress"] == 50.0
        assert data[0]["downloadSpeed"] == 100
        assert data[0]["uploadSpeed"] == 50

    def test_tr_speed_dict_keys(self, client):
        """Transmission 活跃种子返回字段 keys 集合 == 前端 6 字段。"""
        t = MagicMock()
        t.hashString = "t1"
        t.rate_download = 200
        t.rate_upload = 0
        t.percent_done = 0.25
        t.peers_sending_to_us = 3
        t.peers_getting_from_us = 0
        dl = _make_tr_downloader(torrents=[t])
        _set_store(client.app, [dl])
        with _real_call_downloader_api():
            r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        data = body["data"]
        assert len(data) == 1
        core_fields = set(data[0].keys()) - {"downloader_id", "downloader_type"}
        assert core_fields == EXPECTED_SPEED_FIELDS
        assert data[0]["progress"] == 25.0
        assert data[0]["downloadSpeed"] == 200


# ============ runtime 必经守护（sync-resource-governance） ============


class TestEndpointMustUseRuntime:
    """守护速度接口必须经 DownloaderApiRuntime（call_downloader_api）调用下载器。

    sync-resource-governance 治理的核心约束：速度接口不能绕过 per-downloader
    Semaphore 限流直接 asyncio.to_thread 调用下载器，否则前端 1 秒轮询会在同步
    期间成为旁路压力源。若有人为“提速”把 _call_with_timeout 改回直接 to_thread，
    此测试会红（mock 不被调用）。
    """

    def test_endpoint_invokes_call_downloader_api(self, client):
        """有在线下载器时，端点必须通过 call_downloader_api 调用下载器。"""
        dl = _make_qb_downloader(torrents=[{"hash": "h1", "dlspeed": 100, "upspeed": 0, "progress": 0.5}])
        _set_store(client.app, [dl])
        # 用闭包变量记录调用：若端点绕过 runtime 直接 to_thread，该变量不会被置 True
        call_records = []

        async def spy_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            call_records.append((downloader_id, lane))
            return func(*args, **(kwargs or {}))

        with patch("app.api.endpoints.torrent_speed.call_downloader_api", side_effect=spy_call):
            r = client.get(URL)
        assert r.json()["code"] == "200"
        # 核心断言：call_downloader_api 必须被调用过（证明走 runtime，非旁路）
        assert len(call_records) > 0, "速度接口必须经 call_downloader_api（DownloaderApiRuntime），不能绕过限流"
        # 进一步验证 lane 为 INTERACTIVE（与 _real_call_downloader_api 的断言互补）
        called_lane = call_records[0][1]
        assert called_lane == DownloadLane.INTERACTIVE


# ============ A-1：新鲜离线下载器跳过（僵尸下载器根治） ============


class TestFreshlyOfflineSkip:
    """状态轮询新鲜判定离线的下载器不发起远程调用，不拖垮 complete 判定。

    背景：失效下载器永久滞留 store 缓存（fail_time 剔除机制为死代码），前端
    每秒轮询对它发起调用必然失败（连接拒绝/3s 超时），把整个响应拖成 206。
    离线是已知状态（is_online=False 且 last_update 新鲜），按"完整但空"处理。
    """

    def test_freshly_offline_skipped_without_remote_call(self, client):
        """离线且 last_update 新鲜 → 不发起调用，返回 200（complete 语义）。"""
        import time

        dl = _make_qb_downloader(torrents=[{"hash": "h1", "dlspeed": 100, "upspeed": 0, "progress": 0.5}])
        dl.is_online = False
        dl.last_update = time.time()
        _set_store(client.app, [dl])
        with patch("app.api.endpoints.torrent_speed.call_downloader_api") as mock_call:
            r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"] == []
        mock_call.assert_not_called()
        # 活动快照为权威空集（READY_EMPTY），active_only 过滤不退化为 PARTIAL
        snap = torrent_speed.get_active_keys_snapshot()
        assert snap.ready
        assert snap.status == torrent_speed.ActiveSnapshotStatus.READY_EMPTY

    def test_offline_without_probe_still_called(self, client):
        """last_update 缺失（冷启动/新加入的 VO 默认 None）→ 放行，不误杀启动期。"""
        dl = _make_qb_downloader(torrents=[{"hash": "h1", "dlspeed": 100, "upspeed": 0, "progress": 0.5}])
        dl.is_online = False  # 不设 last_update（SimpleNamespace 无该属性 → getattr None）
        _set_store(client.app, [dl])
        call_records = []

        async def spy_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            call_records.append(downloader_id)
            return func(*args, **(kwargs or {}))

        with patch("app.api.endpoints.torrent_speed.call_downloader_api", side_effect=spy_call):
            r = client.get(URL)
        assert r.json()["code"] == "200"
        assert call_records == ["dl_qb"]

    def test_offline_stale_probe_still_called(self, client):
        """轮询停摆兜底：last_update 过旧（超出新鲜窗口）→ 放行由速度调用兜底。"""
        import time

        dl = _make_qb_downloader(torrents=[{"hash": "h1", "dlspeed": 100, "upspeed": 0, "progress": 0.5}])
        dl.is_online = False
        dl.last_update = time.time() - (torrent_speed._OFFLINE_FRESH_WINDOW + 10)
        _set_store(client.app, [dl])
        call_records = []

        async def spy_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            call_records.append(downloader_id)
            return func(*args, **(kwargs or {}))

        with patch("app.api.endpoints.torrent_speed.call_downloader_api", side_effect=spy_call):
            r = client.get(URL)
        assert r.json()["code"] == "200"
        assert call_records == ["dl_qb"]

    def test_online_with_fresh_probe_still_called(self, client):
        """is_online=True 时无论 last_update 如何都正常调用。"""
        import time

        dl = _make_qb_downloader(torrents=[{"hash": "h1", "dlspeed": 100, "upspeed": 0, "progress": 0.5}])
        dl.is_online = True
        dl.last_update = time.time()
        _set_store(client.app, [dl])
        call_records = []

        async def spy_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            call_records.append(downloader_id)
            return func(*args, **(kwargs or {}))

        with patch("app.api.endpoints.torrent_speed.call_downloader_api", side_effect=spy_call):
            r = client.get(URL)
        assert r.json()["code"] == "200"
        assert call_records == ["dl_qb"]

    def test_mixed_online_failure_and_offline_skip_returns_206(self, client):
        """在线下载器超时 + 离线下载器跳过 → 206 只归因在线失败者（msg 明细口径）。"""
        import asyncio
        import time

        online_dl = _make_qb_downloader(torrents=[])
        online_dl.nickname = "online_timeout_dl"
        offline_dl = _make_qb_downloader(dl_id="dl_off", torrents=[{"hash": "h2", "dlspeed": 100, "upspeed": 0}])
        offline_dl.nickname = "offline_skip_dl"
        offline_dl.is_online = False
        offline_dl.last_update = time.time()

        async def timeout_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            raise asyncio.TimeoutError()

        _set_store(client.app, [online_dl, offline_dl])
        with patch("app.api.endpoints.torrent_speed.call_downloader_api", side_effect=timeout_call):
            r = client.get(URL)
        body = r.json()
        assert body["code"] == "206"
        assert body["status"] == "partial"
        # 失败明细只含在线失败者，离线跳过不计入（complete 语义与 msg 不打架）
        assert "online_timeout_dl" in body["msg"]
        assert "offline_skip_dl" not in body["msg"]
