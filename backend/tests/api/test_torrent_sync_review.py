# -*- coding: utf-8 -*-
"""
代码审查回归测试 — torrent_sync.py 边界场景

测试范围:
- C4: qb_add_torrents 新建连接/调用异常保护
- C5: tr_add_torrents 新建连接/调用异常保护
- H1: completion_on 为 0 或 None 时 datetime.fromtimestamp 鴩溃
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


def _make_bt_downloader(**kwargs):
    """创建模拟的 BtDownloaders 对象"""
    dl = MagicMock()
    dl.downloader_id = "dl-001"
    dl.host = "192.168.1.1"
    dl.port = 8080
    dl.username = "admin"
    dl.password = "password"
    dl.nickname = "test-downloader"
    dl.downloader_type = 0
    for k, v in kwargs.items():
        setattr(dl, k, v)
    return dl


class TestQbAddTorrentsExceptionSafety:
    """C4: qb_add_torrents 在连接异常时应安全处理"""

    def test_empty_downloaders_list(self):
        """空下载器列表应安全返回"""
        from app.api.endpoints.torrent_sync import qb_add_torrents

        db = MagicMock()
        result = qb_add_torrents(db, [], app=None)
        assert result is None

    def test_none_downloaders_list(self):
        """None下载器列表应安全返回"""
        from app.api.endpoints.torrent_sync import qb_add_torrents

        db = MagicMock()
        result = qb_add_torrents(db, None, app=None)
        assert result is None

    def test_cached_client_exception_handled(self):
        """缓存连接 torrents_info() 异常应被捕获"""
        from app.api.endpoints.torrent_sync import qb_add_torrents

        db = MagicMock()
        downloader = _make_bt_downloader()

        mock_vo = MagicMock()
        mock_vo.downloader_id = "dl-001"
        mock_vo.client = MagicMock()
        mock_vo.client.torrents_info.side_effect = ConnectionError("Connection reset")

        app = MagicMock()
        app.state.store.get_snapshot_sync.return_value = [mock_vo]

        # 不应抛出异常
        result = qb_add_torrents(db, [downloader], app=app)
        assert result is None

    @patch('qbittorrentapi.Client')
    def test_new_connection_exception_handled(self, mock_qb_cls):
        """后备新建 qbClient 连接失败应被捕获"""
        from app.api.endpoints.torrent_sync import qb_add_torrents

        mock_qb_cls.side_effect = ConnectionError("Connection refused")

        db = MagicMock()
        downloader = _make_bt_downloader()

        result = qb_add_torrents(db, [downloader], app=None)
        assert result is None


class TestTrAddTorrentsExceptionSafety:
    """C5: tr_add_torrents 在连接异常时应安全处理"""

    @patch('transmission_rpc.Client')
    def test_new_connection_exception_handled(self, mock_tr_cls):
        """后备新建 trClient 连接失败应被捕获"""
        from app.api.endpoints.torrent_sync import tr_add_torrents

        mock_tr_cls.side_effect = ConnectionError("Connection refused")

        db = MagicMock()
        downloader = _make_bt_downloader(downloader_type=1, port=9091)

        result = tr_add_torrents(db, [downloader], app=None)
        assert result is None

    def test_cached_client_exception_handled(self):
        """缓存连接 get_torrents() 异常应被捕获"""
        from app.api.endpoints.torrent_sync import tr_add_torrents

        db = MagicMock()
        downloader = _make_bt_downloader(downloader_type=1, port=9091)

        mock_vo = MagicMock()
        mock_vo.downloader_id = "dl-001"
        mock_vo.client = MagicMock()
        mock_vo.client.get_torrents.side_effect = ConnectionError("Connection reset")

        app = MagicMock()
        app.state.store.get_snapshot_sync.return_value = [mock_vo]

        result = tr_add_torrents(db, [downloader], app=app)
        assert result is None


class TestCompletionOnTimestampSafety:
    """H1: completion_on 为 0 或 None 时不应崩溃"""

    @patch('qbittorrentapi.Client')
    def test_completion_on_zero(self, mock_qb_cls):
        """completion_on=0 时不应抛 TypeError"""
        from app.api.endpoints.torrent_sync import qb_add_torrents

        # mock qbClient 实例和它的返回值
        mock_instance = MagicMock()
        mock_torrent = MagicMock()
        mock_torrent.hash = "abc123"
        mock_torrent.name = "test"
        mock_torrent.state = "paused"
        mock_torrent.save_path = "/downloads"
        mock_torrent.total_size = 1024
        mock_torrent.added_on = 1700000000
        mock_torrent.completion_on = 0  # 未完成 → 0
        mock_torrent.ratio = 1.0
        mock_torrent.ratio_limit = -1
        mock_torrent.tags = ""
        mock_torrent.category = ""
        mock_torrent.super_seeding = False
        mock_torrent.trackers = []
        mock_instance.torrents_info.return_value = [mock_torrent]
        mock_qb_cls.return_value = mock_instance

        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

        downloader = _make_bt_downloader()
        # 不应抛出 TypeError
        qb_add_torrents(db, [downloader], app=None)

    @patch('qbittorrentapi.Client')
    def test_completion_on_none(self, mock_qb_cls):
        """completion_on=None 时不应抛 TypeError"""
        from app.api.endpoints.torrent_sync import qb_add_torrents

        mock_instance = MagicMock()
        mock_torrent = MagicMock()
        mock_torrent.hash = "abc456"
        mock_torrent.name = "test"
        mock_torrent.state = "paused"
        mock_torrent.save_path = "/downloads"
        mock_torrent.total_size = 1024
        mock_torrent.added_on = 1700000000
        mock_torrent.completion_on = None  # None值
        mock_torrent.ratio = 1.0
        mock_torrent.ratio_limit = -1
        mock_torrent.tags = ""
        mock_torrent.category = ""
        mock_torrent.super_seeding = False
        mock_torrent.trackers = []
        mock_instance.torrents_info.return_value = [mock_torrent]
        mock_qb_cls.return_value = mock_instance

        db = MagicMock()
        db.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = []

        downloader = _make_bt_downloader()
        # 不应抛出 TypeError
        qb_add_torrents(db, [downloader], app=None)
