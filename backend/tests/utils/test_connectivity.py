# -*- coding: utf-8 -*-
"""utils.connectivity 统一探测模块单测（dual-mode-client Phase 1.1）。

覆盖：TCP 成功/拒绝/超时、ICMP PermissionError 回退、loopback 短路、
主机清洗、安卓环境 ICMP 禁用、非法端口。
"""

import socket
import time

from app.utils import connectivity


# ============ 主机清洗 ============


class TestCleanHost:
    def test_strips_scheme_and_path(self):
        assert connectivity.clean_host("https://example.com/path") == "example.com"
        assert connectivity.clean_host("http://192.168.1.1:8080/") == "192.168.1.1:8080"

    def test_plain_host_unchanged(self):
        assert connectivity.clean_host("qb.example.com ") == "qb.example.com"

    def test_invalid_input(self):
        assert connectivity.clean_host(None) == ""
        assert connectivity.clean_host("") == ""
        assert connectivity.clean_host(123) == ""


class TestIsLoopback:
    def test_loopback_hosts(self):
        assert connectivity.is_loopback("127.0.0.1")
        assert connectivity.is_loopback("localhost")
        assert connectivity.is_loopback("LOCALHOST")
        assert connectivity.is_loopback("http://127.0.0.1:8080")

    def test_not_loopback(self):
        assert not connectivity.is_loopback("192.168.1.1")
        # 历史子串匹配的误判场景：含 "127.0.0.1" 的普通域名不得短路
        assert not connectivity.is_loopback("127.0.0.1.example.com")
        assert not connectivity.is_loopback("sub.localhost.example.com")


# ============ ICMP 策略 ============


class TestIcmpPolicy:
    def test_android_env_disables_icmp(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "android")
        assert connectivity.is_android_environment() is True
        assert connectivity.icmp_allowed() is False

    def test_explicit_disable_flag(self, monkeypatch):
        monkeypatch.delenv("BTDECK_PLATFORM", raising=False)
        monkeypatch.setenv("BTDECK_DISABLE_ICMP", "1")
        assert connectivity.icmp_allowed() is False

    def test_default_desktop_allows_icmp(self, monkeypatch):
        monkeypatch.delenv("BTDECK_PLATFORM", raising=False)
        monkeypatch.delenv("BTDECK_DISABLE_ICMP", raising=False)
        monkeypatch.delenv("TERMUX_VERSION", raising=False)
        # 桌面环境（无安卓标志）默认允许 ICMP
        assert connectivity.icmp_allowed() is True

    def test_icmp_permission_error_returns_none(self, monkeypatch):
        """ping3 抛 PermissionError（无 raw socket 权限）必须返回 None 而非抛出。"""
        monkeypatch.setattr(connectivity, "icmp_allowed", lambda: True)

        class FakePing3:
            @staticmethod
            def ping(*args, **kwargs):
                raise PermissionError("raw socket denied")

        import sys

        monkeypatch.setitem(sys.modules, "ping3", FakePing3)
        assert connectivity.icmp_ping_delay("192.168.1.1") is None

    def test_icmp_false_result_returns_none(self, monkeypatch):
        """ping3 返回 False（超时/失败）返回 None。"""
        monkeypatch.setattr(connectivity, "icmp_allowed", lambda: True)

        class FakePing3:
            @staticmethod
            def ping(*args, **kwargs):
                return False

        import sys

        monkeypatch.setitem(sys.modules, "ping3", FakePing3)
        assert connectivity.icmp_ping_delay("192.168.1.1") is None


# ============ TCP connect 计时 ============


def _free_port() -> int:
    """取一个临时空闲端口（绑定后立即释放，存在微小复用竞争，仅测试用）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _FakeSocket:
    """替身 socket：connect 按指令成功/拒绝/超时。"""

    behavior = "ok"

    def __init__(self, *args, **kwargs):
        pass

    def settimeout(self, value):
        pass

    def connect(self, addr):
        if _FakeSocket.behavior == "refuse":
            raise ConnectionRefusedError(f"refused {addr}")
        if _FakeSocket.behavior == "timeout":
            raise socket.timeout(f"timed out {addr}")
        return None

    def close(self):
        pass


class TestTcpConnectDelay:
    def test_success_returns_positive_ms(self):
        port = _free_port()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", port))
        server.listen(1)
        try:
            delay = connectivity.tcp_connect_delay("127.0.0.1", port, timeout_s=2.0)
            assert delay is not None and delay > 0
        finally:
            server.close()

    def test_connection_refused_returns_none(self):
        # 绑定后立刻关闭，端口几乎必然拒绝连接
        port = _free_port()
        assert connectivity.tcp_connect_delay("127.0.0.1", port, timeout_s=2.0) is None

    def test_timeout_returns_none(self, monkeypatch):
        monkeypatch.setattr(socket, "socket", _FakeSocket)
        _FakeSocket.behavior = "timeout"
        try:
            assert connectivity.tcp_connect_delay("10.255.255.1", 8080, timeout_s=0.1) is None
        finally:
            _FakeSocket.behavior = "ok"

    def test_invalid_port_returns_none(self):
        assert connectivity.tcp_connect_delay("192.168.1.1", "abc") is None
        assert connectivity.tcp_connect_delay("192.168.1.1", 0) is None
        assert connectivity.tcp_connect_delay("192.168.1.1", 70000) is None

    def test_invalid_host_returns_none(self):
        assert connectivity.tcp_connect_delay("", 8080) is None
        assert connectivity.tcp_connect_delay(None, 8080) is None


# ============ 统一入口 probe_delay_sync ============


class TestProbeDelaySync:
    def test_loopback_short_circuit(self):
        # loopback 不做任何网络 IO，直接返回固定延迟
        assert connectivity.probe_delay_sync("127.0.0.1", 8080) == connectivity.LOOPBACK_DELAY_MS
        assert connectivity.probe_delay_sync("http://localhost:9090/path", 9090) == connectivity.LOOPBACK_DELAY_MS

    def test_icmp_success_skips_tcp(self, monkeypatch):
        monkeypatch.setattr(connectivity, "icmp_allowed", lambda: True)
        monkeypatch.setattr(connectivity, "icmp_ping_delay", lambda host, t=3.0: 12.5)
        called = []

        def _tcp(host, port, timeout_s=3.0):
            called.append((host, port))
            return 99.0

        monkeypatch.setattr(connectivity, "tcp_connect_delay", _tcp)
        assert connectivity.probe_delay_sync("192.168.1.1", 8080) == 12.5
        assert called == []

    def test_icmp_failure_falls_back_to_tcp(self, monkeypatch):
        """ICMP 无权限/失败（None）必须回退 TCP connect 计时。"""
        monkeypatch.setattr(connectivity, "icmp_allowed", lambda: True)
        monkeypatch.setattr(connectivity, "icmp_ping_delay", lambda host, t=3.0: None)
        monkeypatch.setattr(connectivity, "tcp_connect_delay", lambda host, port, timeout_s=3.0: 42.0)
        assert connectivity.probe_delay_sync("192.168.1.1", 8080) == 42.0

    def test_android_disables_icmp_entirely(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "android")
        icmp_calls = []

        def _icmp(host, t=3.0):
            icmp_calls.append(host)
            return 5.0

        monkeypatch.setattr(connectivity, "icmp_ping_delay", _icmp)
        monkeypatch.setattr(connectivity, "tcp_connect_delay", lambda host, port, timeout_s=3.0: 7.0)
        assert connectivity.probe_delay_sync("192.168.1.1", 8080) == 7.0
        assert icmp_calls == []

    def test_allow_icmp_override(self, monkeypatch):
        monkeypatch.setattr(connectivity, "icmp_ping_delay", lambda host, t=3.0: None)
        monkeypatch.setattr(connectivity, "tcp_connect_delay", lambda host, port, timeout_s=3.0: 33.0)
        assert connectivity.probe_delay_sync("192.168.1.1", 8080, allow_icmp=False) == 33.0


# ============ 异步入口（pytest.ini asyncio_mode=auto） ============


class TestProbeDelayAsync:
    async def test_async_matches_sync_loopback(self):
        assert await connectivity.probe_delay("127.0.0.1", 8080) == connectivity.LOOPBACK_DELAY_MS

    async def test_async_tcp_fallback(self, monkeypatch):
        monkeypatch.setattr(connectivity, "icmp_allowed", lambda: False)
        port = _free_port()
        start = time.perf_counter()
        delay = await connectivity.probe_delay("192.0.2.1", port, timeout_s=0.05)
        elapsed = time.perf_counter() - start
        # TEST-NET 地址必然失败返回 None，且受超时约束（不悬挂）
        assert delay is None
        assert elapsed < 2.0


# 兼容直接 patch 模块内 socket.socket 的用法说明：connectivity 模块通过
# `socket.socket(...)` 动态查找，monkeypatch.setattr(socket, "socket", ...) 生效。
