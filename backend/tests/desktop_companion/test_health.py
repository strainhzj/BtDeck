# -*- coding: utf-8 -*-
"""desktop_companion.health 契约测试：live→ready 链式探测与五态分类。

对齐安卓 HealthClient 语义：READY/NOT_READY/UNREACHABLE/TLS_ERROR；
TLS 错误与网络不可达必须区分（自签 https 走 TLS_ERROR 提示）。
urlopen 全部 monkeypatch，不发真实网络请求。
"""

import io
import socket
import ssl
import urllib.error

import pytest

from app.desktop_companion import health as health_module
from app.desktop_companion.health import HealthClient
from app.desktop_companion.profiles import (
    HEALTH_NOT_READY,
    HEALTH_READY,
    HEALTH_TLS_ERROR,
    HEALTH_UNREACHABLE,
)


class _FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _envelope(data: dict, status: str = "success") -> bytes:
    import json

    return json.dumps({"status": status, "msg": "ok", "code": "200", "data": data}).encode()


def _install(monkeypatch, live=None, ready=None, live_alias=None, ready_alias=None, recorder=None):
    """按 URL 分发响应（或异常工厂）。

    live/ready 为主路径（/health/live、/health/ready），live_alias/ready_alias 为
    /api/v1 别名回退路径；未配置的路径默认抛 URLError（网络错误，不触发回退分支）。
    recorder 可选记录实际请求的 URL 序列（回退顺序断言用）。
    别名 URL 以主路径后缀结尾，必须先判别名再判主路径。
    """

    def fake_urlopen(request, timeout=None):  # noqa: ARG001
        url = request.full_url
        if recorder is not None:
            recorder.append(url)
        if url.endswith("/api/v1/health/live"):
            item = live_alias
        elif url.endswith("/api/v1/health/ready"):
            item = ready_alias
        elif url.endswith("/health/live"):
            item = live
        elif url.endswith("/health/ready"):
            item = ready
        else:
            raise AssertionError(f"unexpected probe url: {url}")
        if item is None:
            raise urllib.error.URLError(OSError("no response configured"))
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(health_module.urllib.request, "urlopen", fake_urlopen)


class TestHealthClientReadyPath:
    def test_live_alive_ready_ready_with_version(self, monkeypatch):
        _install(
            monkeypatch,
            _FakeResponse(200, _envelope({"status": "alive", "version": "1.0.5"})),
            _FakeResponse(200, _envelope({"status": "ready", "version": "1.0.5"})),
        )
        report = HealthClient().check("http://192.168.5.51:5001")
        assert report.state == HEALTH_READY
        assert report.version == "1.0.5"
        assert report.detail == "服务就绪"

    def test_live_data_not_alive(self, monkeypatch):
        _install(
            monkeypatch,
            _FakeResponse(200, _envelope({"status": "dead"})),
            _FakeResponse(200, _envelope({"status": "ready"})),
        )
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_UNREACHABLE
        assert report.detail == "服务存活检查失败"

    def test_live_http_error(self, monkeypatch):
        _install(
            monkeypatch,
            urllib.error.HTTPError("http://x/health/live", 500, "Internal Error", None, io.BytesIO(b"{}")),
            None,
        )
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_UNREACHABLE
        assert "HTTP 500" in report.detail


class TestHealthClientNotReadyPath:
    def test_ready_not_ready_with_reason_codes(self, monkeypatch):
        _install(
            monkeypatch,
            _FakeResponse(200, _envelope({"status": "alive", "version": "1.0.5"})),
            _FakeResponse(
                503,
                _envelope({"status": "not_ready", "reasonCodes": ["DB_BUSY", "WORKER"]}),
            ),
        )
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_NOT_READY
        assert "DB_BUSY、WORKER" in report.detail

    def test_ready_http_error_keeps_version(self, monkeypatch):
        _install(
            monkeypatch,
            _FakeResponse(200, _envelope({"status": "alive", "version": "1.0.5"})),
            urllib.error.HTTPError(
                "http://x/health/ready", 503, "Service Unavailable", None, io.BytesIO(b'{"data": {"version": "1.0.4"}}')
            ),
        )
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_NOT_READY
        assert report.version == "1.0.4"

    def test_non_json_body_treated_as_failure(self, monkeypatch):
        _install(
            monkeypatch,
            _FakeResponse(200, b"<html>proxy login</html>"),
            None,
        )
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_UNREACHABLE


class TestHealthClientNetworkErrors:
    def test_ssl_error_classified_as_tls(self, monkeypatch):
        _install(
            monkeypatch,
            urllib.error.URLError(ssl.SSLCertVerificationError("self signed cert")),
            None,
        )
        report = HealthClient().check("https://10.0.0.5:5001")
        assert report.state == HEALTH_TLS_ERROR
        assert "证书错误" in report.detail

    def test_generic_url_error_unreachable(self, monkeypatch):
        _install(monkeypatch, urllib.error.URLError(OSError("refused")), None)
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_UNREACHABLE
        assert report.detail == "无法连接服务器"

    def test_socket_timeout_unreachable(self, monkeypatch):
        _install(monkeypatch, socket.timeout("timed out"), None)
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_UNREACHABLE

    def test_connection_error_unreachable(self, monkeypatch):
        _install(monkeypatch, ConnectionError("reset"), None)
        report = HealthClient().check("http://10.0.0.5:5001")
        assert report.state == HEALTH_UNREACHABLE


class TestHealthClientApiAliasFallback:
    """主路径被反代吞掉时的 /api/v1 别名回退（与安卓 HealthClientFallbackTest 同口径）。"""

    def test_text_health_block_falls_back_and_reaches_ready(self, monkeypatch):
        urls: list[str] = []
        _install(
            monkeypatch,
            live=_FakeResponse(200, b"healthy\n"),
            ready=_FakeResponse(200, b"healthy\n"),
            live_alias=_FakeResponse(200, _envelope({"status": "alive", "version": "1.0.6"})),
            ready_alias=_FakeResponse(200, _envelope({"status": "ready", "version": "1.0.6"})),
            recorder=urls,
        )
        report = HealthClient().check("http://10.0.0.8:8080")
        assert report.state == HEALTH_READY
        assert report.version == "1.0.6"
        assert report.detail == "服务就绪"
        assert urls == [
            "http://10.0.0.8:8080/health/live",
            "http://10.0.0.8:8080/api/v1/health/live",
            "http://10.0.0.8:8080/health/ready",
            "http://10.0.0.8:8080/api/v1/health/ready",
        ]

    def test_http_error_falls_back_to_alias(self, monkeypatch):
        _install(
            monkeypatch,
            live=urllib.error.HTTPError("http://x/health/live", 404, "Not Found", None, io.BytesIO(b"{}")),
            ready=urllib.error.HTTPError("http://x/health/ready", 404, "Not Found", None, io.BytesIO(b"{}")),
            live_alias=_FakeResponse(200, _envelope({"status": "alive", "version": "1.0.6"})),
            ready_alias=_FakeResponse(200, _envelope({"status": "ready", "version": "1.0.6"})),
        )
        report = HealthClient().check("http://example.com")
        assert report.state == HEALTH_READY
        assert report.version == "1.0.6"

    def test_both_paths_fail_keeps_primary_attribution(self, monkeypatch):
        _install(
            monkeypatch,
            live=urllib.error.HTTPError("http://x/health/live", 502, "Bad Gateway", None, io.BytesIO(b"{}")),
            live_alias=urllib.error.HTTPError(
                "http://x/api/v1/health/live", 502, "Bad Gateway", None, io.BytesIO(b"{}")
            ),
        )
        report = HealthClient().check("http://example.com")
        assert report.state == HEALTH_UNREACHABLE
        assert "HTTP 502" in report.detail

    def test_network_error_does_not_fallback(self, monkeypatch):
        urls: list[str] = []
        _install(
            monkeypatch,
            live=urllib.error.URLError(OSError("refused")),
            recorder=urls,
        )
        report = HealthClient().check("http://example.com")
        assert report.state == HEALTH_UNREACHABLE
        assert report.detail == "无法连接服务器"
        assert urls == ["http://example.com/health/live"]

    def test_primary_healthy_never_touches_alias(self, monkeypatch):
        urls: list[str] = []
        _install(
            monkeypatch,
            live=_FakeResponse(200, _envelope({"status": "alive", "version": "1.0.6"})),
            ready=_FakeResponse(200, _envelope({"status": "ready", "version": "1.0.6"})),
            recorder=urls,
        )
        report = HealthClient().check("http://example.com")
        assert report.state == HEALTH_READY
        assert urls == ["http://example.com/health/live", "http://example.com/health/ready"]


@pytest.mark.parametrize(
    "state,label",
    [
        ("READY", "就绪"),
        ("NOT_READY", "未就绪"),
        ("UNREACHABLE", "不可达"),
        ("TLS_ERROR", "证书错误"),
        ("UNKNOWN", "未测试"),
        ("WEIRD", "未测试"),
    ],
)
def test_health_label(state, label):
    from app.desktop_companion.health import health_label

    assert health_label(state) == label
