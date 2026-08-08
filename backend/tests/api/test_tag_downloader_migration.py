# -*- coding: utf-8 -*-
"""
标签 + 下载器设置/状态垂直切片迁移测试（sync-database-blocking-remediation W2-3，P0-04）

覆盖对象（async 请求端同步下载器调用迁移）：
1. tag_management.py：_sync_tags_to_torrent_downloader / _sync_tag_delete_to_downloader /
   _sync_tag_to_downloader（死代码）的全部下载器调用必须经 call_downloader_api（INTERACTIVE
   lane）执行，客户端来自 app.state.store。
2. downloader.py：get_status 降级路径 get_qbittorrent_detail / get_transmission_detail
   改为 async + store 客户端 + call_downloader_api。
3. downloader_settings.py：test_downloader_settings 保留"自建客户端"（用户新提交配置的
   合法测试连接场景），但网络调用必须经 call_downloader_api。

每条迁移路径覆盖：成功（断言 client 方法经 runtime 被调）、超时、离线/缺失客户端、
权限失败（APIError/LoginFailed/TransmissionError）。

测试手法：mock client + fake store（参照 tests/services/conftest.py 的
fake_qb_client / fake_store / make_downloader_vo 样板）；patch 各端点模块内
call_downloader_api 引用，side_effect 直接执行 func（等价于 runtime 线程内调用），
从而断言"client 方法经 runtime 被调"且确定性无真实网络。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.downloader.responseVO import DownloaderVO
from app.models.downloader_settings import DownloaderSetting
from app.services.downloader_api_runtime import DownloadLane
from qbittorrentapi import APIError, LoginFailed
from transmission_rpc import TransmissionAuthError
from transmission_rpc.error import TransmissionError

# ==================== 公共辅助 ====================


def make_downloader_vo(downloader_id="dl_001", client=None, fail_time=0, downloader_type=0):
    """构造伪下载器 VO（app.state.store.get_snapshot() 返回的元素）。

    nickname 必须存在：helper 的"下载器已失效"日志会读取 downloader_vo.nickname。
    """
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.nickname = "test-dl"
    vo.client = client
    vo.fail_time = fail_time
    vo.downloader_type = downloader_type
    return vo


def make_fake_app(store):
    """伪 FastAPI 实例，带 state.store（helper 通过 request.app 取缓存）。"""
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.store = store
    return app


def make_fake_store(vo_list):
    """伪 store，get_snapshot() 返回给定 VO 列表。"""
    store = SimpleNamespace()
    store.get_snapshot = AsyncMock(return_value=vo_list)
    return store


def make_fake_request(app):
    """伪 FastAPI Request（helper 只使用 request.app）。"""
    return SimpleNamespace(app=app)


def runtime_executor(downloader_id, lane, func, args=(), kwargs=None, *, timeout=None, operation=""):
    """模拟 runtime：在调用线程内直接执行 func（断言 client 方法经 runtime 被调）。"""
    return func(*args, **(kwargs or {}))


def assert_lane_and_func(mock_runtime, expected_func, downloader_id="dl_001"):
    """断言 call_downloader_api 收到指定 func 且 lane=INTERACTIVE、downloader_id 正确。"""
    for call in mock_runtime.await_args_list:
        if call.args[2] == expected_func:
            assert call.args[0] == downloader_id
            assert call.args[1] is DownloadLane.INTERACTIVE
            return True
    return False


# ==================== tag_management.py helper 迁移 ====================


class TestSyncTagsToTorrentDownloader:
    """_sync_tags_to_torrent_downloader：分配标签同步（成功/超时/离线/权限失败）。"""

    async def test_qb_success_routes_through_runtime(self):
        """成功：qB 分类+标签三步全部经 call_downloader_api，save_path 来自 torrents_info。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        client.torrents_info.return_value = [{"save_path": "/data/torrents", "hash": "h1"}]
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
        ) as mock_runtime:
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=["电影"],
                tag_names=["PT"],
            )

        assert result["success"] is True
        # client 方法经 runtime 被调（side_effect 在 runtime 包装内执行 func）
        client.torrents_info.assert_called_once_with(torrent_hashes=["h1"])
        client.torrents_set_category.assert_called_once_with(
            category="电影", save_path="/data/torrents", torrent_hashes=["h1"]
        )
        client.torrents_add_tags.assert_called_once_with(tags=["PT"], torrent_hashes=["h1"])
        # 断言全部经 call_downloader_api(INTERACTIVE) 且 downloader_id 正确
        assert assert_lane_and_func(mock_runtime, client.torrents_info)
        assert assert_lane_and_func(mock_runtime, client.torrents_set_category)
        assert assert_lane_and_func(mock_runtime, client.torrents_add_tags)

    async def test_tr_success_strips_at_prefix(self):
        """成功：Transmission 全部标签合并为 tags，@前缀被去掉。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=1)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
        ) as mock_runtime:
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=["@电影"],
                tag_names=["PT"],
            )

        assert result["success"] is True
        client.torrents_set_tags.assert_called_once_with(tags=["电影", "PT"], torrent_hashes=["h1"])
        assert assert_lane_and_func(mock_runtime, client.torrents_set_tags)

    async def test_timeout_returns_failure(self):
        """超时：call_downloader_api 抛 TimeoutError → helper 返回失败且不抛异常。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()
        ):
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=["电影"],
                tag_names=[],
            )

        assert result["success"] is False
        assert "同步失败" in result["message"]

    async def test_permission_failure_qb_api_error(self):
        """权限失败：qB APIError（403）→ helper 返回失败并带错误信息。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=APIError("Forbidden 403")
        ):
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=["电影"],
                tag_names=[],
            )

        assert result["success"] is False
        assert "Forbidden" in result["message"]

    async def test_permission_failure_tr_transmission_error(self):
        """权限失败：TransmissionError → helper 返回失败并带错误信息。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=1)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management,
            "call_downloader_api",
            new_callable=AsyncMock,
            side_effect=TransmissionError("401: unauthorized"),
        ):
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=[],
                tag_names=["PT"],
            )

        assert result["success"] is False
        assert "401" in result["message"]

    async def test_downloader_not_in_cache(self):
        """缺失客户端：store 中没有该下载器 → 返回失败且不发起任何调用。"""
        from app.api.endpoints import tag_management

        store = make_fake_store([])
        request = make_fake_request(make_fake_app(store))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock) as mock_runtime:
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=["电影"],
                tag_names=[],
            )

        assert result["success"] is False
        assert "不在缓存中" in result["message"]
        mock_runtime.assert_not_awaited()

    async def test_downloader_offline(self):
        """离线：fail_time>0 → helper 返回"下载器已失效"，不发起调用。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, fail_time=5, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock) as mock_runtime:
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=["电影"],
                tag_names=[],
            )

        assert result["success"] is False
        assert "已失效" in result["message"]
        mock_runtime.assert_not_awaited()

    async def test_client_missing_on_vo(self):
        """缺失客户端：VO 存在但 client 为空 → helper 返回失败，不发起调用。"""
        from app.api.endpoints import tag_management

        store = make_fake_store([make_downloader_vo(client=None, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock) as mock_runtime:
            result = await tag_management._sync_tags_to_torrent_downloader(
                request,
                downloader_id="dl_001",
                torrent_hash="h1",
                category_tags=["电影"],
                tag_names=[],
            )

        assert result["success"] is False
        assert "客户端连接不存在" in result["message"]
        mock_runtime.assert_not_awaited()


class TestSyncTagDeleteToDownloader:
    """_sync_tag_delete_to_downloader：删除标签/分类同步（成功/超时/离线/权限失败）。"""

    async def test_qb_category_delete_empty_success(self):
        """成功：分类下无种子 → 直接 torrents_remove_categories。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        client.torrents_info.return_value = []
        client.torrents.info.return_value = []
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
        ) as mock_runtime:
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
            )

        assert result["success"] is True
        client.torrents_remove_categories.assert_called_once_with(categories=["电影"])
        assert assert_lane_and_func(mock_runtime, client.torrents_info)
        assert assert_lane_and_func(mock_runtime, client.torrents.info)
        assert assert_lane_and_func(mock_runtime, client.torrents_remove_categories)

    async def test_qb_category_delete_with_transfer(self):
        """成功：分类下有种子且提供目标分类 → 逐种子 set_category 后删除分类。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        client.torrents_info.return_value = [{"hash": "h1", "name": "t1"}]
        client.torrents.info.return_value = []
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
        ) as mock_runtime:
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
                target_category="新分类",
            )

        assert result["success"] is True
        client.torrents.set_category.assert_called_once_with(category="新分类", torrent_hashes=["h1"])
        client.torrents_remove_categories.assert_called_once_with(categories=["电影"])
        assert assert_lane_and_func(mock_runtime, client.torrents.set_category)

    async def test_qb_category_transfer_all_failed_aborts(self):
        """失败：全部种子转移失败 → 中止删除。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        # hash 为空 → 转移失败
        client.torrents_info.return_value = [{"hash": "", "name": "bad"}]
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor):
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
                target_category="新分类",
            )

        assert result["success"] is False
        assert "种子转移全部失败" in result["message"]

    async def test_qb_category_remaining_torrents_block_delete(self):
        """失败：分类下仍有种子（未转移）→ 拒绝删除。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        client.torrents_info.return_value = [{"hash": "h1", "name": "t1"}]
        client.torrents.info.return_value = [{"hash": "h1", "name": "t1"}]
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor):
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
                target_category=None,
            )

        assert result["success"] is False
        assert "仍有 1 个种子" in result["message"]

    async def test_qb_tag_delete_success(self):
        """成功：qB 普通标签删除。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
        ) as mock_runtime:
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="PT",
                tag_type="tag",
            )

        assert result["success"] is True
        client.torrents_delete_tags.assert_called_once_with(tags="PT")
        assert assert_lane_and_func(mock_runtime, client.torrents_delete_tags)

    async def test_timeout_returns_failure(self):
        """超时：分类删除过程中 runtime 超时 → helper 返回失败（由分类块内层捕获）。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()
        ):
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
            )

        # 超时发生在分类删除块内层 try 中，被既有错误映射捕获为"删除分类失败"（契约不变）
        assert result["success"] is False
        assert "删除分类失败" in result["message"]

    async def test_permission_failure_on_remove_categories(self):
        """权限失败：删除分类时 APIError → 返回失败且不抛异常。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        client.torrents_info.return_value = []
        client.torrents.info.return_value = []
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        def _failing_runtime(downloader_id, lane, func, args=(), kwargs=None, *, timeout=None, operation=""):
            if func == client.torrents_remove_categories:
                raise APIError("Forbidden 403")
            return func(*args, **(kwargs or {}))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=_failing_runtime):
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
            )

        assert result["success"] is False
        assert "删除分类失败" in result["message"]

    async def test_permission_failure_on_delete_tags(self):
        """权限失败：删除标签时 APIError → 返回失败且不抛异常。"""
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        def _failing_runtime(downloader_id, lane, func, args=(), kwargs=None, *, timeout=None, operation=""):
            if func == client.torrents_delete_tags:
                raise APIError("Forbidden 403")
            return func(*args, **(kwargs or {}))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=_failing_runtime):
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="PT",
                tag_type="tag",
            )

        assert result["success"] is False
        assert "删除标签失败" in result["message"]

    async def test_downloader_not_in_cache(self):
        """缺失客户端：store 中无该下载器 → 返回失败且不发起调用。"""
        from app.api.endpoints import tag_management

        store = make_fake_store([])
        request = make_fake_request(make_fake_app(store))

        with patch.object(tag_management, "call_downloader_api", new_callable=AsyncMock) as mock_runtime:
            result = await tag_management._sync_tag_delete_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
            )

        assert result["success"] is False
        assert "不在缓存中" in result["message"]
        mock_runtime.assert_not_awaited()


class TestSyncTagToDownloaderDeadCode:
    """_sync_tag_to_downloader（当前无调用方死代码）：顺手迁移后仍保持正确行为。"""

    async def test_qb_create_category_via_runtime(self):
        from app.api.endpoints import tag_management

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(client=client, downloader_type=0)])
        request = make_fake_request(make_fake_app(store))

        with patch.object(
            tag_management, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
        ) as mock_runtime:
            result = await tag_management._sync_tag_to_downloader(
                request,
                downloader_id="dl_001",
                tag_id="t1",
                tag_name="电影",
                tag_type="category",
                color=None,
            )

        assert result["success"] is True
        client.torrent_categories.create_category.assert_called_once_with(name="电影")
        assert assert_lane_and_func(mock_runtime, client.torrent_categories.create_category)


# ==================== downloader.py 降级路径迁移 ====================


def make_downloader_vo_db(downloader_type=0):
    """构造 DownloaderVO（get_status 降级路径从 DB 行构建的对象）。"""
    return DownloaderVO(
        downloader_id="dl_001",
        nickname="qb-test",
        host="127.0.0.1",
        username="admin",
        password="admin",
        is_search="0",
        status="1",
        enabled="1",
        downloader_type=downloader_type,
        port=8080,
        is_ssl="0",
    )


class TestGetQbittorrentDetail:
    """get_qbittorrent_detail（[已废弃] get_status 降级路径，async + store 客户端）。"""

    async def test_success_routes_through_runtime(self):
        from app.api.endpoints import downloader as dl_endpoint

        client = MagicMock()
        client.transfer_info.return_value = {"up_info_speed": 1024, "dl_info_speed": 2048}
        store = make_fake_store([make_downloader_vo(downloader_id="dl_001", client=client, downloader_type=0)])
        fake_app = make_fake_app(store)
        downloader = make_downloader_vo_db(downloader_type=0)

        with (
            patch.object(
                dl_endpoint, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
            ) as mock_runtime,
            patch("app.factory.app", fake_app),
        ):
            status_vo = await dl_endpoint.get_qbittorrent_detail(1.0, downloader)

        assert status_vo.connectStatus == "connected"
        assert status_vo.uploadSpeed == "1.00 KB/s"
        assert status_vo.downloadSpeed == "2.00 KB/s"
        client.transfer_info.assert_called_once_with()
        assert assert_lane_and_func(mock_runtime, client.transfer_info, downloader_id="dl_001")

    async def test_timeout_returns_connection_timeout(self):
        from app.api.endpoints import downloader as dl_endpoint

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(downloader_id="dl_001", client=client, downloader_type=0)])
        fake_app = make_fake_app(store)
        downloader = make_downloader_vo_db(downloader_type=0)

        with (
            patch.object(
                dl_endpoint, "call_downloader_api", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()
            ),
            patch("app.factory.app", fake_app),
        ):
            status_vo = await dl_endpoint.get_qbittorrent_detail(1.0, downloader)

        assert status_vo.connectStatus == "连接超时，请检查网络和下载器配置"

    async def test_auth_failure_returns_login_failed(self):
        from app.api.endpoints import downloader as dl_endpoint

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(downloader_id="dl_001", client=client, downloader_type=0)])
        fake_app = make_fake_app(store)
        downloader = make_downloader_vo_db(downloader_type=0)

        with (
            patch.object(
                dl_endpoint, "call_downloader_api", new_callable=AsyncMock, side_effect=LoginFailed("401 unauthorized")
            ),
            patch("app.factory.app", fake_app),
        ):
            status_vo = await dl_endpoint.get_qbittorrent_detail(1.0, downloader)

        assert status_vo.connectStatus == "登录失败，请检查账号密码是否正确"

    async def test_no_cached_client_returns_disconnected(self):
        """缺失客户端：store 无该下载器 → 直接返回 disconnected，不发起调用。"""
        from app.api.endpoints import downloader as dl_endpoint

        store = make_fake_store([])
        fake_app = make_fake_app(store)
        downloader = make_downloader_vo_db(downloader_type=0)

        with (
            patch.object(dl_endpoint, "call_downloader_api", new_callable=AsyncMock) as mock_runtime,
            patch("app.factory.app", fake_app),
        ):
            status_vo = await dl_endpoint.get_qbittorrent_detail(1.0, downloader)

        assert status_vo.connectStatus == "disconnected"
        mock_runtime.assert_not_awaited()

    async def test_zero_delay_returns_disconnected_without_store_access(self):
        """delay=0 → 直接 disconnected（不访问 store、不发起调用）。"""
        from app.api.endpoints import downloader as dl_endpoint

        with patch.object(dl_endpoint, "call_downloader_api", new_callable=AsyncMock) as mock_runtime:
            status_vo = await dl_endpoint.get_qbittorrent_detail(0, make_downloader_vo_db(downloader_type=0))

        assert status_vo.connectStatus == "disconnected"
        mock_runtime.assert_not_awaited()


class TestGetTransmissionDetail:
    """get_transmission_detail（[已废弃] get_status 降级路径，async + store 客户端）。"""

    async def test_success_routes_through_runtime(self):
        from app.api.endpoints import downloader as dl_endpoint

        client = MagicMock()
        client.session_stats.return_value = SimpleNamespace(upload_speed=1024, download_speed=2048)
        store = make_fake_store([make_downloader_vo(downloader_id="dl_001", client=client, downloader_type=1)])
        fake_app = make_fake_app(store)
        downloader = make_downloader_vo_db(downloader_type=1)

        with (
            patch.object(
                dl_endpoint, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
            ) as mock_runtime,
            patch("app.factory.app", fake_app),
        ):
            status_vo = await dl_endpoint.get_transmission_detail(1.0, downloader)

        assert status_vo.connectStatus == "connected"
        assert status_vo.uploadSpeed == "1.00 KB/s"
        assert status_vo.downloadSpeed == "2.00 KB/s"
        client.session_stats.assert_called_once_with()
        assert assert_lane_and_func(mock_runtime, client.session_stats, downloader_id="dl_001")

    async def test_auth_failure_returns_login_failed(self):
        from app.api.endpoints import downloader as dl_endpoint

        client = MagicMock()
        store = make_fake_store([make_downloader_vo(downloader_id="dl_001", client=client, downloader_type=1)])
        fake_app = make_fake_app(store)
        downloader = make_downloader_vo_db(downloader_type=1)

        with (
            patch.object(
                dl_endpoint,
                "call_downloader_api",
                new_callable=AsyncMock,
                side_effect=TransmissionAuthError("401: auth"),
            ),
            patch("app.factory.app", fake_app),
        ):
            status_vo = await dl_endpoint.get_transmission_detail(1.0, downloader)

        assert status_vo.connectStatus == "登录失败，请检查账号密码是否正确"

    async def test_no_cached_client_returns_disconnected(self):
        from app.api.endpoints import downloader as dl_endpoint

        store = make_fake_store([])
        fake_app = make_fake_app(store)
        downloader = make_downloader_vo_db(downloader_type=1)

        with (
            patch.object(dl_endpoint, "call_downloader_api", new_callable=AsyncMock) as mock_runtime,
            patch("app.factory.app", fake_app),
        ):
            status_vo = await dl_endpoint.get_transmission_detail(1.0, downloader)

        assert status_vo.connectStatus == "disconnected"
        mock_runtime.assert_not_awaited()

    async def test_zero_delay_returns_disconnected(self):
        from app.api.endpoints import downloader as dl_endpoint

        with patch.object(dl_endpoint, "call_downloader_api", new_callable=AsyncMock) as mock_runtime:
            status_vo = await dl_endpoint.get_transmission_detail(0, make_downloader_vo_db(downloader_type=1))

        assert status_vo.connectStatus == "disconnected"
        mock_runtime.assert_not_awaited()


# ==================== downloader_settings.py test_downloader_settings ====================

TEST_SETTINGS_URL = "/api/v1/downloaders/dl-1/settings/test"


@pytest.fixture
def settings_client():
    """独立 FastAPI app（api_router），override get_db + 认证。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[DownloaderSetting.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    return TestClient(app, raise_server_exceptions=False)


class TestDownloaderSettingsTestConnection:
    """test_downloader_settings：保留自建客户端（用户新提交配置的合法测试连接场景），
    但网络调用必须经 call_downloader_api。"""

    def test_qb_still_self_builds_client_but_calls_via_runtime(self, settings_client):
        """成功：自建 QBClient（新配置）→ 但 app_version 经 call_downloader_api 执行。"""
        from app.api.endpoints import downloader_settings

        fake_qb = MagicMock()
        fake_qb.app_version.return_value = "v4.6.7"

        with (
            patch("qbittorrentapi.Client") as mock_qb_client_cls,
            patch.object(
                downloader_settings, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
            ) as mock_runtime,
        ):
            mock_qb_client_cls.return_value = fake_qb
            r = settings_client.post(
                TEST_SETTINGS_URL,
                json={
                    "host": "127.0.0.1",
                    "port": 8080,
                    "username": "admin",
                    "password": "secret",
                    "downloader_type": 0,
                    "is_ssl": "0",
                },
            )

        body = r.json()
        assert body["status"] == "success"
        assert body["data"]["success"] is True
        assert body["data"]["delay"] is not None
        # 合法例外保留：确实用用户提交的新配置自建了客户端
        mock_qb_client_cls.assert_called_once()
        constructed = mock_qb_client_cls.call_args
        assert constructed.kwargs["host"] == "http://127.0.0.1:8080"
        assert constructed.kwargs["username"] == "admin"
        # 网络调用经 runtime（func 为 qb_client.app_version，INTERACTIVE lane）
        assert assert_lane_and_func(mock_runtime, fake_qb.app_version, downloader_id="dl-1")
        assert mock_runtime.await_count >= 1

    def test_tr_still_self_builds_client_but_calls_via_runtime(self, settings_client):
        """成功：自建 TrClient（新配置）→ 但 get_session 经 call_downloader_api 执行。"""
        from app.api.endpoints import downloader_settings

        fake_tr = MagicMock()
        fake_tr.get_session.return_value = SimpleNamespace(version="4.0.0")

        with (
            patch("transmission_rpc.Client") as mock_tr_client_cls,
            patch.object(
                downloader_settings, "call_downloader_api", new_callable=AsyncMock, side_effect=runtime_executor
            ) as mock_runtime,
        ):
            mock_tr_client_cls.return_value = fake_tr
            r = settings_client.post(
                TEST_SETTINGS_URL,
                json={
                    "host": "127.0.0.1",
                    "port": 9091,
                    "username": "admin",
                    "password": "secret",
                    "downloader_type": 1,
                    "is_ssl": "0",
                },
            )

        body = r.json()
        assert body["status"] == "success"
        assert body["data"]["success"] is True
        mock_tr_client_cls.assert_called_once()
        constructed = mock_tr_client_cls.call_args
        assert constructed.kwargs["host"] == "127.0.0.1"
        assert constructed.kwargs["port"] == 9091
        assert assert_lane_and_func(mock_runtime, fake_tr.get_session, downloader_id="dl-1")

    def test_qb_timeout_returns_connection_failed(self, settings_client):
        """超时：runtime 抛 TimeoutError → 返回 success=False（HTTP 200 保持契约）。"""
        from app.api.endpoints import downloader_settings

        fake_qb = MagicMock()

        with (
            patch("qbittorrentapi.Client") as mock_qb_client_cls,
            patch.object(
                downloader_settings, "call_downloader_api", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()
            ),
        ):
            mock_qb_client_cls.return_value = fake_qb
            r = settings_client.post(
                TEST_SETTINGS_URL,
                json={
                    "host": "127.0.0.1",
                    "port": 8080,
                    "username": "admin",
                    "password": "secret",
                    "downloader_type": 0,
                    "is_ssl": "0",
                },
            )

        body = r.json()
        assert body["status"] == "success"
        assert body["data"]["success"] is False
        assert "连接失败" in body["data"]["message"]

    def test_qb_login_failed_returns_auth_message(self, settings_client):
        """权限失败：LoginFailed → 返回认证失败消息。"""
        from app.api.endpoints import downloader_settings

        fake_qb = MagicMock()

        with (
            patch("qbittorrentapi.Client") as mock_qb_client_cls,
            patch.object(
                downloader_settings, "call_downloader_api", new_callable=AsyncMock, side_effect=LoginFailed("bad creds")
            ),
        ):
            mock_qb_client_cls.return_value = fake_qb
            r = settings_client.post(
                TEST_SETTINGS_URL,
                json={
                    "host": "127.0.0.1",
                    "port": 8080,
                    "username": "admin",
                    "password": "secret",
                    "downloader_type": 0,
                    "is_ssl": "0",
                },
            )

        body = r.json()
        assert body["data"]["success"] is False
        assert "认证失败" in body["data"]["message"]
