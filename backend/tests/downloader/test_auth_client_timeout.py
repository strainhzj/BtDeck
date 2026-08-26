# -*- coding: utf-8 -*-
"""认证检查一次性下载器客户端超时构造回归（2026-08-25）。

背景：缓存客户端构造带 REQUESTS_ARGS timeout（initialization.py 正式路径），
而认证检查用的一次性客户端无任何超时——外层 wait_for 只放弃等待，底层
to_thread 线程挂在无超时 socket 上永久泄漏。修复为与缓存客户端对齐：
qb REQUESTS_ARGS={"timeout": 30} / tr timeout=30.0。

若有人改回无超时构造，本测试立即报红。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.downloader.initialization import (
    _check_and_add_new_downloader,
    _check_qbittorrent_auth_with_retry,
    _check_transmission_auth_with_retry,
)

_DOWNLOADER_INFO = {
    "nickname": "认证超时测试",
    "host": "192.0.2.10",
    "port": 8080,
    "username": "admin",
    "password": "secret",
}


class TestAuthCheckClientTimeout:
    async def test_qb_auth_client_built_with_requests_timeout(self):
        """qb 认证检查客户端必须带 REQUESTS_ARGS timeout（否则 to_thread 线程
        挂死在无超时 socket 上无法回收）。"""
        fake_client = MagicMock()
        fake_client.app_version.return_value = "v5.0.0"

        with patch("qbittorrentapi.Client", return_value=fake_client) as client_cls:
            ok = await _check_qbittorrent_auth_with_retry(_DOWNLOADER_INFO, attempt=1, max_retries=3)

        assert ok is True
        kwargs = client_cls.call_args.kwargs
        assert kwargs.get("REQUESTS_ARGS") == {"timeout": 30}, (
            "认证检查一次性 qbClient 必须与缓存客户端构造对齐（REQUESTS_ARGS timeout=30），"
            "否则外层 wait_for 超时后线程永久泄漏"
        )

    async def test_tr_auth_client_built_with_timeout(self):
        """tr 认证检查客户端必须带 timeout=30.0。"""
        fake_client = MagicMock()
        fake_client.session_stats.return_value = {"downloadSpeed": 0}

        with patch("transmission_rpc.Client", return_value=fake_client) as client_cls:
            ok = await _check_transmission_auth_with_retry(_DOWNLOADER_INFO, attempt=1, max_retries=3)

        assert ok is True
        kwargs = client_cls.call_args.kwargs
        assert kwargs.get("timeout") == 30.0, "认证检查一次性 trClient 必须带 timeout=30.0"


class TestQbClientSchemeAndRetryHardening:
    """【2026-08-25 第二批】消除 detect_scheme 探测放大 + 关闭 urllib3 双层重试。

    验证结论（生产 2025.2.0 实测）：无 scheme host 触发 qbittorrentapi 的
    HTTP→HTTPS 双方案探测，异常 WebUI 下每段 30s×重试把单次调用放大到 ~6 分钟
    （生产挂死案件的库层放大器）。FORCE_SCHEME_FROM_HOST=True + 显式 scheme
    跳过探测；HTTPADAPTER_ARGS max_retries=0 关闭 urllib3 层重试（外层已有
    超时治理）。改回无参构造即报红。
    """

    async def test_qb_auth_client_skips_scheme_detection_and_retry(self):
        """认证检查客户端：FORCE_SCHEME_FROM_HOST=True + max_retries=0。"""
        fake_client = MagicMock()
        fake_client.app_version.return_value = "v5.0.0"

        with patch("qbittorrentapi.Client", return_value=fake_client) as client_cls:
            await _check_qbittorrent_auth_with_retry(_DOWNLOADER_INFO, attempt=1, max_retries=3)

        kwargs = client_cls.call_args.kwargs
        assert kwargs.get("FORCE_SCHEME_FROM_HOST") is True, "必须跳过 detect_scheme 探测（6 分钟放大器根因）"
        assert kwargs.get("HTTPADAPTER_ARGS") == {"max_retries": 0}, "必须关闭 urllib3 层重试"

    def test_qb_host_with_scheme_normalization(self):
        """host scheme 补全：无前缀按 is_ssl 补 http(s)，有前缀保持。"""
        from app.downloader.initialization import _qb_host_with_scheme

        # 无 scheme + 各 is_ssl 形态（bool 与 DB 字符串 "1"/"0" 兼容，与 tr 口径一致）
        assert _qb_host_with_scheme("192.168.5.51", False) == "http://192.168.5.51"
        assert _qb_host_with_scheme("192.168.5.51", True) == "https://192.168.5.51"
        assert _qb_host_with_scheme("192.168.5.51", "1") == "https://192.168.5.51"
        assert _qb_host_with_scheme("192.168.5.51", "0") == "http://192.168.5.51"
        assert _qb_host_with_scheme("192.168.5.51", None) == "http://192.168.5.51"
        # 已带 scheme 保持不变
        assert _qb_host_with_scheme("https://qb.example.com", False) == "https://qb.example.com"
        assert _qb_host_with_scheme("http://qb.example.com", True) == "http://qb.example.com"

    async def test_cached_qb_client_uses_normalized_scheme_and_retry_policy(self):
        """缓存客户端真实构造路径也必须跳过探测并关闭 urllib3 重试。"""
        app = SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace(add=AsyncMock())))
        downloader_data = {
            "downloader_id": "dl-qb",
            "nickname": "缓存构造测试",
            "host": "https://qb.example.com/base-path",
            "port": "8080",
            "username": "admin",
            "password": "encrypted",
            "downloader_type": "0",
            "is_ssl": "1",
            "torrent_save_path": "/downloads",
        }

        with (
            patch(
                "app.downloader.initialization._is_downloader_duplicate",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "app.downloader.initialization.check_port_connectivity",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.downloader.initialization._check_qbittorrent_auth_with_retry",
                new=AsyncMock(return_value=True),
            ),
            patch("app.utils.encryption.decrypt_password", return_value="decrypted"),
            patch("app.downloader.initialization.qbClient") as client_cls,
        ):
            client_instance = MagicMock()
            client_cls.return_value = client_instance
            ok = await _check_and_add_new_downloader(app, downloader_data, immediate=True)

        assert ok is True
        client_cls.assert_called_once()
        kwargs = client_cls.call_args.kwargs
        assert kwargs["host"] == "https://qb.example.com"
        assert kwargs["port"] == 8080
        assert kwargs["FORCE_SCHEME_FROM_HOST"] is True
        assert kwargs["HTTPADAPTER_ARGS"] == {"max_retries": 0}
        assert kwargs["REQUESTS_ARGS"] == {"timeout": 30}

        app.state.store.add.assert_awaited_once()
        cached_vo = app.state.store.add.await_args.args[0]
        assert cached_vo.host == "qb.example.com"
        assert cached_vo.client is client_instance
