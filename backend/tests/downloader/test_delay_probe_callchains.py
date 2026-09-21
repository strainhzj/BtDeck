# -*- coding: utf-8 -*-
"""下载器延迟探测两条调用链的回归测试（dual-mode-client Phase 1.1）。

链路 1：app.api.endpoints.downloader 的 get_delay_async / get_delay
        （/detail/{id} 与 /test/{id} 端点使用），替换 ping3 直调后
        必须保持"float 毫秒 / False|None 失败"的历史返回语义。
链路 2：app.downloader.initialization._update_downloader_status 的延迟段
        （状态轮询），探测值直接写入 downloader.delay。

两条链路均 mock utils.connectivity，不做真实网络 IO。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.utils import connectivity


# ============ 链路 1：downloader.py get_delay_async / get_delay ============


class TestGetDelayAsync:
    def _dl(self, host="192.168.1.10", port=8080):
        return SimpleNamespace(host=host, port=port)

    async def test_probe_success_returns_float(self, monkeypatch):
        from app.api.endpoints import downloader as dl_mod

        probe = AsyncMock(return_value=12.5)
        monkeypatch.setattr(dl_mod.connectivity, "probe_delay", probe)
        assert await dl_mod.get_delay_async(self._dl()) == 12.5
        probe.assert_awaited_once_with("192.168.1.10", 8080, timeout_s=3.0)

    async def test_probe_unreachable_returns_none(self, monkeypatch):
        from app.api.endpoints import downloader as dl_mod

        monkeypatch.setattr(dl_mod.connectivity, "probe_delay", AsyncMock(return_value=None))
        assert await dl_mod.get_delay_async(self._dl()) is None

    async def test_probe_exception_returns_false(self, monkeypatch):
        """探测意外异常按历史约定返回 False（safe_delay_value 视为未连接）。"""
        from app.api.endpoints import downloader as dl_mod

        monkeypatch.setattr(dl_mod.connectivity, "probe_delay", AsyncMock(side_effect=RuntimeError("boom")))
        assert await dl_mod.get_delay_async(self._dl()) is False

    async def test_loopback_semantics_preserved(self, monkeypatch):
        """loopback 主机短路为固定延迟（历史 delay=1），不发起网络探测。"""
        from app.api.endpoints import downloader as dl_mod

        monkeypatch.setattr(dl_mod.connectivity, "probe_delay", connectivity.probe_delay)
        assert await dl_mod.get_delay_async(self._dl(host="127.0.0.1")) == connectivity.LOOPBACK_DELAY_MS


class TestGetDelaySync:
    def _dl(self, host="192.168.1.10", port=8080):
        return SimpleNamespace(host=host, port=port)

    def test_probe_success_returns_float(self, monkeypatch):
        from app.api.endpoints import downloader as dl_mod

        probe = Mock(return_value=8.25)
        monkeypatch.setattr(dl_mod.connectivity, "probe_delay_sync", probe)
        assert dl_mod.get_delay(self._dl()) == 8.25
        probe.assert_called_once_with("192.168.1.10", 8080, timeout_s=3.0)

    def test_probe_exception_returns_false(self, monkeypatch):
        from app.api.endpoints import downloader as dl_mod

        monkeypatch.setattr(dl_mod.connectivity, "probe_delay_sync", Mock(side_effect=OSError("net down")))
        assert dl_mod.get_delay(self._dl()) is False


# ============ 链路 2：initialization._update_downloader_status 延迟段 ============


class TestUpdateDownloaderStatusDelay:
    def _make_dl(self, host="192.168.1.20"):
        return SimpleNamespace(nickname="dl", host=host, port=9090, downloader_type=0)

    def _patch(self, monkeypatch, *, probe_value=None, probe_exc=None, port_online=True):
        # initialization 在函数体内 `from app.utils import connectivity`，
        # 运行时按模块属性查找 probe_delay，因此直接 patch 模块属性即可生效
        from app.downloader import initialization as init_mod
        from app.utils import connectivity as conn_mod

        if probe_exc is not None:

            async def _raise(*a, **k):
                raise probe_exc

            monkeypatch.setattr(conn_mod, "probe_delay", _raise)
        else:
            monkeypatch.setattr(conn_mod, "probe_delay", AsyncMock(return_value=probe_value))
        monkeypatch.setattr(init_mod, "check_port_connectivity", AsyncMock(return_value=port_online))
        # 在线路径会继续拉取下载器状态，mock 为稳定返回，避免真实客户端创建
        monkeypatch.setattr(
            init_mod,
            "_get_qbittorrent_status",
            AsyncMock(return_value={"upload_speed": 10, "download_speed": 20}),
        )

    async def test_delay_written_to_downloader(self, monkeypatch):
        from app.downloader import initialization as init_mod

        self._patch(monkeypatch, probe_value=15.5, port_online=False)
        dl = self._make_dl()
        ok = await init_mod._update_downloader_status(dl)
        assert ok is True
        assert dl.delay == 15.5
        assert dl.is_online is False  # 端口检查独立判定

    async def test_out_of_range_delay_clamped_to_none(self, monkeypatch):
        from app.downloader import initialization as init_mod

        self._patch(monkeypatch, probe_value=99999.0, port_online=True)
        dl = self._make_dl()
        await init_mod._update_downloader_status(dl)
        assert dl.delay is None  # 超出合理范围视为异常值

    async def test_probe_exception_does_not_break_status_update(self, monkeypatch):
        from app.downloader import initialization as init_mod

        self._patch(monkeypatch, probe_exc=OSError("probe exploded"), port_online=True)
        dl = self._make_dl()
        ok = await init_mod._update_downloader_status(dl)
        assert ok is True  # 延迟失败不阻断端口检查与状态更新
        assert dl.delay is None

    async def test_loopback_shortcut_kept(self, monkeypatch):
        """loopback 主机仍短路为固定延迟（真实 connectivity 路径）。"""
        from app.downloader import initialization as init_mod
        from app.utils import connectivity as conn_mod

        real_probe = conn_mod.probe_delay  # 先捕获真实函数（_patch 会覆盖模块属性）
        self._patch(monkeypatch, probe_value=None, port_online=True)
        monkeypatch.setattr(conn_mod, "probe_delay", real_probe)
        dl = self._make_dl(host="localhost")
        await init_mod._update_downloader_status(dl)
        assert dl.delay == connectivity.LOOPBACK_DELAY_MS
