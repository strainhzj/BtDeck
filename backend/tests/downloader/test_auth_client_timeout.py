# -*- coding: utf-8 -*-
"""认证检查一次性下载器客户端超时构造回归（2026-08-25）。

背景：缓存客户端构造带 REQUESTS_ARGS timeout（initialization.py 正式路径），
而认证检查用的一次性客户端无任何超时——外层 wait_for 只放弃等待，底层
to_thread 线程挂在无超时 socket 上永久泄漏。修复为与缓存客户端对齐：
qb REQUESTS_ARGS={"timeout": 30} / tr timeout=30.0。

若有人改回无超时构造，本测试立即报红。
"""

from unittest.mock import MagicMock, patch

from app.downloader.initialization import (
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
