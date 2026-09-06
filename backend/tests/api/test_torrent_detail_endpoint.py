# -*- coding: utf-8 -*-
"""
GET /api/v1/torrents/detail/{hash}/files|peers 端点级回归测试。

覆盖：
- qB/TR 两侧原始字段 → 统一 VO 的归一化契约（keys 集合锁死，防前后端字段漂移）
- 下载器解析三错误路径（不在缓存 404 / fail_time>0 503 / 无客户端 500）
- 种子不存在异常分类（qB NotFound404Error / TR KeyError → 独立信封 404，
  与「下载器不在缓存」区分）；其余异常 → 500
- files 可选分页与列表强制信封格式（total/page/pageSize/list）
- TR 防御路径：length==0 进度防除零、缺省字段兜底

模板对齐：
  - test_active_torrents_endpoint.py（FakeStore + MagicMock(spec=Client)
    + patch call_downloader_api 为「真实执行同步函数」）
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qbittorrentapi import Client as qbClient
from qbittorrentapi import NotFound404Error
from transmission_rpc import Client as trClient

from app.api.api import api_router
from app.api.endpoints import torrent_detail
from app.auth.dependencies import require_authenticated_user
from app.services.downloader_api_runtime import DownloadLane

FILES_URL = "/api/v1/torrents/detail/{hash}/files"
PEERS_URL = "/api/v1/torrents/detail/{hash}/peers"
HASH = "abc123def456"

# 前端 TorrentFileInfo / TorrentPeerInfo 接口契约（views/torrents 卡片页签）
EXPECTED_FILE_FIELDS = {"name", "size", "progress"}
EXPECTED_PEER_FIELDS = {"ip", "port", "client", "progress", "down_speed", "up_speed", "flags", "country"}


# ============ 辅助构造 ============


def _set_store(app, downloaders):
    """注入异步 get_snapshot 伪 store（仿 test_active_torrents_endpoint._set_store）。"""

    class FakeStore:
        async def get_snapshot(self_inner):
            return list(downloaders)

    app.state.store = FakeStore()


class _TrTorrentStub:
    """transmission-rpc Torrent 替身：本端点只经 .get() 读 RPC 原始字段。"""

    def __init__(self, fields):
        self.fields = fields

    def get(self, key, default=None):
        return self.fields.get(key, default)


def _make_qb_downloader_with(client):
    return SimpleNamespace(
        downloader_id="dl_qb",
        downloader_type=0,
        nickname="qb_dl",
        fail_time=0,
        client=client,
    )


def _make_tr_downloader_with(client):
    return SimpleNamespace(
        downloader_id="dl_tr",
        downloader_type=1,
        nickname="tr_dl",
        fail_time=0,
        client=client,
    )


def _make_qb_downloader(dl_id="dl_qb", *, fail_time=0):
    return SimpleNamespace(
        downloader_id=dl_id,
        downloader_type=0,
        nickname="qb_dl",
        fail_time=fail_time,
        client=MagicMock(spec=qbClient),
    )


def _make_tr_downloader(dl_id="dl_tr", *, fail_time=0):
    return SimpleNamespace(
        downloader_id=dl_id,
        downloader_type=1,
        nickname="tr_dl",
        fail_time=fail_time,
        client=MagicMock(spec=trClient),
    )


@pytest.fixture
def client():
    """独立 FastAPI app，覆盖 require_authenticated_user（仿 test_torrent_list_api）。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _real_call_downloader_api():
    """patch call_downloader_api 为「真实执行同步函数」，并断言走 INTERACTIVE lane。

    全量 pytest 中其它 TestClient 退出会触发 lifespan shutdown 关闭全局
    downloader_api_runtime executor，故必须 patch 而非依赖全局单例真实执行。
    """

    async def fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        assert lane == DownloadLane.INTERACTIVE, "详情明细接口必须走 INTERACTIVE lane"
        assert opts.get("timeout") in (
            torrent_detail._QB_DETAIL_CALL_TIMEOUT,
            torrent_detail._TR_DETAIL_CALL_TIMEOUT,
        )
        return func(*args, **(kwargs or {}))

    return patch(
        "app.api.endpoints.torrent_detail.call_downloader_api",
        side_effect=fake_call,
    )


# ============ 文件列表：qB / TR 归一化契约 ============


class TestFilesNormalization:
    def test_qb_files_normalized_vo_and_envelope(self, client):
        qb_client = MagicMock(spec=qbClient)
        qb_client.torrents_files.return_value = [
            {"name": "dir/a.iso", "size": 1024, "progress": 0.5},
            {"name": "dir/b.mkv", "size": 2048, "progress": 1.0},
        ]
        _set_store(client.app, [_make_qb_downloader_with(qb_client)])

        with _real_call_downloader_api():
            r = client.get(FILES_URL.format(hash=HASH), params={"downloader_id": "dl_qb"})

        assert r.status_code == 200
        body = r.json()
        assert body["code"] == "200"
        data = body["data"]
        assert set(data.keys()) == {"total", "page", "pageSize", "list"}
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["pageSize"] == 100000
        assert len(data["list"]) == 2
        for item in data["list"]:
            assert set(item.keys()) == EXPECTED_FILE_FIELDS
        assert data["list"][0] == {"name": "dir/a.iso", "size": 1024, "progress": 0.5}
        # qB 侧调用参数：按 hash 查询
        qb_client.torrents_files.assert_called_once_with(torrent_hash=HASH)

    def test_tr_files_raw_fields_and_progress_ratio(self, client):
        tr_client = MagicMock(spec=trClient)
        tr_client.get_torrent.return_value = _TrTorrentStub(
            {
                "files": [
                    {"name": "a.iso", "length": 2000, "bytesCompleted": 1000},
                    {"name": "empty.txt", "length": 0, "bytesCompleted": 0},
                ]
            }
        )
        _set_store(client.app, [_make_tr_downloader_with(tr_client)])

        with _real_call_downloader_api():
            r = client.get(FILES_URL.format(hash=HASH), params={"downloader_id": "dl_tr"})

        assert r.json()["code"] == "200"
        data = r.json()["data"]["list"]
        assert data[0] == {"name": "a.iso", "size": 2000, "progress": 0.5}
        # length==0 防除零：进度兜底 0.0
        assert data[1] == {"name": "empty.txt", "size": 0, "progress": 0.0}
        # TR 侧调用参数：原始字段 arguments=['files']（禁用依赖 priorities/wanted 的 get_files()）
        tr_client.get_torrent.assert_called_once_with(HASH, arguments=["files"])

    def test_files_defensive_defaults_on_malformed_entries(self, client):
        qb_client = MagicMock(spec=qbClient)
        qb_client.torrents_files.return_value = [
            {"name": None, "size": None, "progress": None},
            {"name": "bad-num", "size": "not-a-number", "progress": "x"},
        ]
        _set_store(client.app, [_make_qb_downloader_with(qb_client)])

        with _real_call_downloader_api():
            r = client.get(FILES_URL.format(hash=HASH), params={"downloader_id": "dl_qb"})

        data = r.json()["data"]["list"]
        assert data[0] == {"name": "", "size": 0, "progress": 0.0}
        assert data[1] == {"name": "bad-num", "size": 0, "progress": 0.0}

    def test_files_optional_pagination_slices_server_side(self, client):
        qb_client = MagicMock(spec=qbClient)
        qb_client.torrents_files.return_value = [{"name": f"f{i}.bin", "size": 1, "progress": 0.1} for i in range(5)]
        _set_store(client.app, [_make_qb_downloader_with(qb_client)])

        with _real_call_downloader_api():
            r = client.get(
                FILES_URL.format(hash=HASH),
                params={"downloader_id": "dl_qb", "page": 2, "page_size": 2},
            )

        data = r.json()["data"]
        assert data["total"] == 5
        assert data["page"] == 2
        assert data["pageSize"] == 2
        assert [item["name"] for item in data["list"]] == ["f2.bin", "f3.bin"]


# ============ Peer 列表：qB / TR 归一化契约 ============


class TestPeersNormalization:
    def test_qb_peers_normalized_vo(self, client):
        qb_client = MagicMock(spec=qbClient)
        qb_client.sync_torrent_peers.return_value = {
            "rid": 0,
            "full_update": True,
            "peers": {
                "1.2.3.4:6881": {
                    "ip": "1.2.3.4",
                    "port": 6881,
                    "client": "qBittorrent 4.6.0",
                    "progress": 0.75,
                    "dl_speed": 10240,
                    "up_speed": 2048,
                    "flags": "D",
                    "country": "China",
                },
                "5.6.7.8:51413": {
                    # 缺省字段（新版 libtorrent 无 GeoIP 等）全部兜底
                    "ip": "5.6.7.8",
                    "port": 51413,
                },
            },
        }
        _set_store(client.app, [_make_qb_downloader_with(qb_client)])

        with _real_call_downloader_api():
            r = client.get(PEERS_URL.format(hash=HASH), params={"downloader_id": "dl_qb"})

        assert r.json()["code"] == "200"
        data = r.json()["data"]
        assert data["total"] == 2
        for item in data["list"]:
            assert set(item.keys()) == EXPECTED_PEER_FIELDS
        first = next(p for p in data["list"] if p["ip"] == "1.2.3.4")
        assert first == {
            "ip": "1.2.3.4",
            "port": 6881,
            "client": "qBittorrent 4.6.0",
            "progress": 0.75,
            "down_speed": 10240,
            "up_speed": 2048,
            "flags": "D",
            "country": "China",
        }
        second = next(p for p in data["list"] if p["ip"] == "5.6.7.8")
        assert second["client"] == ""
        assert second["down_speed"] == 0
        # rid=0 全量快照语义
        qb_client.sync_torrent_peers.assert_called_once_with(torrent_hash=HASH, rid=0)

    def test_tr_peers_key_mapping(self, client):
        tr_client = MagicMock(spec=trClient)
        tr_client.get_torrent.return_value = _TrTorrentStub(
            {
                "peers": [
                    {
                        "address": "10.0.0.8",
                        "clientName": "Transmission 3.00",
                        "flagStr": "UX",
                        "port": 51413,
                        "progress": 0.42,
                        "rateToClient": 5120,
                        "rateToPeer": 1024,
                    }
                ]
            }
        )
        _set_store(client.app, [_make_tr_downloader_with(tr_client)])

        with _real_call_downloader_api():
            r = client.get(PEERS_URL.format(hash=HASH), params={"downloader_id": "dl_tr"})

        data = r.json()["data"]
        assert data["total"] == 1
        peer = data["list"][0]
        assert set(peer.keys()) == EXPECTED_PEER_FIELDS
        assert peer == {
            "ip": "10.0.0.8",
            "port": 51413,
            "client": "Transmission 3.00",
            "progress": 0.42,
            "down_speed": 5120,
            "up_speed": 1024,
            "flags": "UX",
            "country": "",
        }
        tr_client.get_torrent.assert_called_once_with(HASH, arguments=["peers"])


# ============ 错误路径 ============


class TestErrorPaths:
    def test_downloader_not_in_cache_returns_404_envelope(self, client):
        _set_store(client.app, [])
        r = client.get(FILES_URL.format(hash=HASH), params={"downloader_id": "missing"})
        assert r.json()["code"] == "404"
        assert "下载器不在缓存中" in r.json()["msg"]

    def test_failed_downloader_returns_503_envelope(self, client):
        _set_store(client.app, [_make_qb_downloader(fail_time=123)])
        r = client.get(PEERS_URL.format(hash=HASH), params={"downloader_id": "dl_qb"})
        assert r.json()["code"] == "503"

    def test_missing_client_returns_500_envelope(self, client):
        vo = _make_qb_downloader()
        vo.client = None
        _set_store(client.app, [vo])
        r = client.get(FILES_URL.format(hash=HASH), params={"downloader_id": "dl_qb"})
        assert r.json()["code"] == "500"
        assert "客户端连接不存在" in r.json()["msg"]

    def test_unsupported_downloader_type_returns_500(self, client):
        _set_store(
            client.app,
            [SimpleNamespace(downloader_id="dl_x", downloader_type=99, nickname="x", fail_time=0, client=object())],
        )
        r = client.get(FILES_URL.format(hash=HASH), params={"downloader_id": "dl_x"})
        assert r.json()["code"] == "500"
        assert "不支持的下载器类型" in r.json()["msg"]

    def test_qb_torrent_not_found_returns_dedicated_404(self, client):
        qb_client = MagicMock(spec=qbClient)
        qb_client.torrents_files.side_effect = NotFound404Error()
        _set_store(client.app, [_make_qb_downloader_with(qb_client)])

        with _real_call_downloader_api():
            r = client.get(FILES_URL.format(hash=HASH), params={"downloader_id": "dl_qb"})

        body = r.json()
        assert body["code"] == "404"
        assert "种子不存在或已被删除" in body["msg"]

    def test_tr_torrent_not_found_keyerror_returns_dedicated_404(self, client):
        tr_client = MagicMock(spec=trClient)
        tr_client.get_torrent.side_effect = KeyError(HASH)
        _set_store(client.app, [_make_tr_downloader_with(tr_client)])

        with _real_call_downloader_api():
            r = client.get(PEERS_URL.format(hash=HASH), params={"downloader_id": "dl_tr"})

        body = r.json()
        assert body["code"] == "404"
        assert "种子不存在或已被删除" in body["msg"]

    def test_generic_downloader_api_error_returns_500(self, client):
        qb_client = MagicMock(spec=qbClient)
        qb_client.sync_torrent_peers.side_effect = RuntimeError("connection reset")
        _set_store(client.app, [_make_qb_downloader_with(qb_client)])

        with _real_call_downloader_api():
            r = client.get(PEERS_URL.format(hash=HASH), params={"downloader_id": "dl_qb"})

        body = r.json()
        assert body["code"] == "500"
        assert "获取Peer列表失败" in body["msg"]
