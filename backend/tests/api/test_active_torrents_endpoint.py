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
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="tester"
    )
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


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


# ============ P0-1：空响应契约（三场景） ============


class TestEmptyResponseContract:
    """守护前端 loadActiveSpeed 依赖的 code='200' data=[] 契约。

    任意一场景偏离都会让前端 speedSnapshotReady 永久 false，
    导致「仅显示活动种子」过滤失效（commit 466e18c 修复的 bug 被绕过）。
    """

    def test_no_online_downloader_returns_200_empty(self, client):
        """场景1：无在线下载器（torrent_speed.py:376-377）→ code='200' data=[]。"""
        _set_store(client.app, [])
        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"] == []
        assert body["status"] == "success"

    def test_downloader_timeout_returns_200_empty(self, client):
        """场景2：下载器调用超时（:398-400 捕获 TimeoutError 返回 []）→ code='200' data=[]。"""
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
        assert body["code"] == "200"
        assert body["data"] == []

    def test_downloader_api_error_returns_200_empty(self, client):
        """场景2b：下载器 API 异常（:401-403 捕获 QbAPIError/TransmissionError）→ code='200' data=[]。"""
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
        assert body["code"] == "200"
        assert body["data"] == []

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
        dl = _make_qb_downloader(
            torrents=[
                {"hash": "h1", "dlspeed": 100, "upspeed": 0, "progress": 0.5}
            ]
        )
        _set_store(client.app, [dl])
        # 用闭包变量记录调用：若端点绕过 runtime 直接 to_thread，该变量不会被置 True
        call_records = []

        async def spy_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
            call_records.append((downloader_id, lane))
            return func(*args, **(kwargs or {}))

        with patch(
            "app.api.endpoints.torrent_speed.call_downloader_api", side_effect=spy_call
        ):
            r = client.get(URL)
        assert r.json()["code"] == "200"
        # 核心断言：call_downloader_api 必须被调用过（证明走 runtime，非旁路）
        assert len(call_records) > 0, (
            "速度接口必须经 call_downloader_api（DownloaderApiRuntime），不能绕过限流"
        )
        # 进一步验证 lane 为 INTERACTIVE（与 _real_call_downloader_api 的断言互补）
        called_lane = call_records[0][1]
        assert called_lane == DownloadLane.INTERACTIVE

