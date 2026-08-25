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


def _install(monkeypatch, live, ready):
    """按序返回 live/ready 两个响应（或异常工厂）。"""

    responses = [live, ready]

    def fake_urlopen(request, timeout=None):  # noqa: ARG001
        item = responses.pop(0)
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
