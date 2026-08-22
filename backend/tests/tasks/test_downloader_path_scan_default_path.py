# -*- coding: utf-8 -*-
"""
downloader_path_scan._get_default_path_from_downloader 回归测试（prod-hotfix-2026-07-19 P2）

修复目标：消除生产 `WARNI ... 'Client' object has no attribute 'get_session_variables'`。
根因：transmission-rpc v7 移除 legacy `Client.get_session_variables()`。

覆盖：
- Transmission 分支调用 `client.get_session()` 并读取 `session.fields['download-dir']`
- 缺失 download-dir 字段时返回 None 并 warn
- get_session 抛异常时返回 None 并 warn
- 旧 API get_session_variables 不应被调用（mutation 反向锚点）
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_tr_session(download_dir="/data/torrents"):
    """构造伪 transmission_rpc Session 对象。

    真实 transmission_rpc.Session.download_dir 是 @property，内部
    `return self.fields["download-dir"]`——字段缺失时抛 KeyError 而非 AttributeError。
    我们还原这个语义（修复前 buggy getattr(default=None) 兜不住 KeyError）。
    """
    fields = {"download-dir": download_dir} if download_dir is not None else {}

    class _FakeSession:
        def __init__(self):
            self.fields = fields

        @property
        def download_dir(self):
            # 复刻 transmission_rpc.Session.download_dir @property 的真实行为
            return self.fields["download-dir"]  # 缺字段时抛 KeyError

    return _FakeSession()


def _make_tr_vo(client):
    """构造伪下载器 VO（app.state.store.get_snapshot() 返回的元素）。"""
    vo = SimpleNamespace()
    vo.downloader_id = "dl-tr-001"
    vo.downloader_type = 1  # Transmission
    vo.client = client
    vo.nickname = "tr-test"
    return vo


def _make_downloader_model():
    """构造 BtDownloaders 模型实例（_get_default_path_from_downloader 入参）。"""
    return SimpleNamespace(
        downloader_id="dl-tr-001",
        nickname="tr-test",
    )


# ==================== Test Group ====================


class TestGetDefaultPathTransmission:
    """Transmission 分支：使用 transmission-rpc v7 新 API。"""

    @pytest.mark.asyncio
    async def test_transmission_uses_get_session_and_download_dir(self):
        """正常路径：get_session() 返回 Session，从 fields['download-dir'] 取路径。"""
        from app.tasks.scheduler.downloader_path_scan import DownloaderPathScanTask

        mock_client = MagicMock()
        mock_client.get_session.return_value = _make_tr_session("/data/torrents")

        vo = _make_tr_vo(mock_client)
        store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[vo]))
        app = SimpleNamespace(state=SimpleNamespace(store=store))

        task = DownloaderPathScanTask()
        with patch("app.main.app", app):
            # 注意：方法内部 import app，需要 patch 模块级 app 或方法内 import 路径
            path = await task._get_default_path_from_downloader(_make_downloader_model())

        assert path == "/data/torrents"
        mock_client.get_session.assert_called_once()
        # 关键 mutation 锚点：旧 API 不应被调
        mock_client.get_session_variables.assert_not_called()

    @pytest.mark.asyncio
    async def test_transmission_missing_download_dir_returns_none(self):
        """缺失 download-dir 字段时返回 None 并打"未找到 download-dir"warning（不进 except）。

        关键：修复前 buggy getattr(default=None) 在真实 @property 抛 KeyError 时会
        进 except 分支打"从 Transmission 获取默认路径失败: 'download-dir'"——日志误导。
        修复后用 session.fields.get('download-dir') 显式取值，缺失返回 None，
        走 if 分支打"未找到 download-dir 字段"——日志语义正确。
        """
        from app.tasks.scheduler.downloader_path_scan import DownloaderPathScanTask

        mock_client = MagicMock()
        # fields 中无 download-dir（用 _make_tr_session(None) 还原真实 @property 抛 KeyError 的语义）
        mock_client.get_session.return_value = _make_tr_session(None)

        vo = _make_tr_vo(mock_client)
        store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[vo]))
        app = SimpleNamespace(state=SimpleNamespace(store=store))

        task = DownloaderPathScanTask()
        with (
            patch("app.main.app", app),
            patch("app.tasks.scheduler.downloader_path_scan.logger.warning") as warning,
        ):
            path = await task._get_default_path_from_downloader(_make_downloader_model())

        assert path is None
        mock_client.get_session.assert_called_once()
        # 关键 mutation 锚点：日志应该说"未找到 download-dir"而非"获取默认路径失败"
        # （后者意味着进 except 分支，即 buggy getattr 路径）
        warning.assert_called_once()
        assert "未找到 download-dir" in str(warning.call_args.args[0])
        assert "获取默认路径失败" not in str(warning.call_args.args[0])

    @pytest.mark.asyncio
    async def test_transmission_get_session_raises_returns_none(self):
        """get_session 抛异常时返回 None（不向上传播）。"""
        from app.tasks.scheduler.downloader_path_scan import DownloaderPathScanTask

        mock_client = MagicMock()
        mock_client.get_session.side_effect = RuntimeError("connect failed")

        vo = _make_tr_vo(mock_client)
        store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[vo]))
        app = SimpleNamespace(state=SimpleNamespace(store=store))

        task = DownloaderPathScanTask()
        with patch("app.main.app", app):
            path = await task._get_default_path_from_downloader(_make_downloader_model())

        # 端点 except 兜底，返回 None 而非抛
        assert path is None

    @pytest.mark.asyncio
    async def test_store_unavailable_returns_none(self):
        """app.state.store 不可用时返回 None。"""
        from app.tasks.scheduler.downloader_path_scan import DownloaderPathScanTask

        app = SimpleNamespace(state=SimpleNamespace(store=None))
        task = DownloaderPathScanTask()
        with patch("app.main.app", app):
            path = await task._get_default_path_from_downloader(_make_downloader_model())
        assert path is None

    @pytest.mark.asyncio
    async def test_client_unavailable_returns_none(self):
        """VO 中 client 为 None 时返回 None。"""
        from app.tasks.scheduler.downloader_path_scan import DownloaderPathScanTask

        vo = SimpleNamespace(downloader_id="dl-tr-001", downloader_type=1, client=None, nickname="tr")
        store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[vo]))
        app = SimpleNamespace(state=SimpleNamespace(store=store))

        task = DownloaderPathScanTask()
        with patch("app.main.app", app):
            path = await task._get_default_path_from_downloader(_make_downloader_model())
        assert path is None


class TestGetDefaultPathQBittorrent:
    """qBittorrent 分支（未改但应保持工作）。"""

    @pytest.mark.asyncio
    async def test_qbittorrent_uses_app_default_save_path(self):
        from app.tasks.scheduler.downloader_path_scan import DownloaderPathScanTask

        mock_client = MagicMock()
        mock_client.app_default_save_path.return_value = "/downloads/qb"

        vo = SimpleNamespace(downloader_id="dl-qb-001", downloader_type=0, client=mock_client, nickname="qb")
        store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[vo]))
        app = SimpleNamespace(state=SimpleNamespace(store=store))

        task = DownloaderPathScanTask()
        with patch("app.main.app", app):
            path = await task._get_default_path_from_downloader(
                SimpleNamespace(downloader_id="dl-qb-001", nickname="qb")
            )

        assert path == "/downloads/qb"
        mock_client.app_default_save_path.assert_called_once()
