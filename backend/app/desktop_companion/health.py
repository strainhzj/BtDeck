# -*- coding: utf-8 -*-
"""服务端健康检查（dual-mode-client task .6 桌面对齐）。

与安卓端 com.btdeck.companion.data.HealthClient 语义一致：
``/health/live`` → ``/health/ready`` 链式探测（live 探连通与进程存活，ready 探
业务就绪并读取 data.version）；TLS 错误单独归类 TLS_ERROR，与网络不可达区分。
响应信封为项目统一 CommonResponse（status/msg/code/data），健康数据在 data 内。

差异：urllib 单一 timeout 同时覆盖连接与读（安卓为 5s/10s 分离），此处取 10s
对齐读超时上限；仅用标准库，不引入新依赖。

回退兜底（与安卓端一致）：根路径 ``/health`` 系列端点可能被反向代理吞掉
（静态健康块返回纯文本、SPA 兜底返回 HTML），主路径探测到"HTTP 错误或响应
不是 JSON 信封"时回退探测 ``/api/v1`` 前缀下的免认证别名（同 handler），
旧部署无需更新网关配置也能读到真实存活与版本。
"""

import json
import logging
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from app.desktop_companion.profiles import (
    HEALTH_LABELS,
    HEALTH_NOT_READY,
    HEALTH_READY,
    HEALTH_TLS_ERROR,
    HEALTH_UNREACHABLE,
    HEALTH_UNKNOWN,
)

logger = logging.getLogger(__name__)

_TIMEOUT_S = 10

_API_ALIAS_PREFIX = "/api/v1"


@dataclass(frozen=True)
class HealthReport:
    state: str
    version: Optional[str]
    detail: str


def _empty_report(state: str, detail: str) -> HealthReport:
    return HealthReport(state=state, version=None, detail=detail)


class _HttpProbeOutcome:
    """单端点探测结果：HTTP 响应可达（body 为信封 data 对象或 None）。"""

    def __init__(self, ok: bool, status_code: int, reason: str, body: Optional[dict[str, Any]]):
        self.ok = ok
        self.status_code = status_code
        self.reason = reason
        self.body = body or {}
        self.version = self.body.get("version")
        if not isinstance(self.version, str) or not self.version:
            self.version = None


def _probe(url: str) -> _HttpProbeOutcome:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            body = _read_json_body(response.read())
            return _HttpProbeOutcome(True, response.status, "", body)
    except urllib.error.HTTPError as exc:
        body = _read_json_body(exc.read() if hasattr(exc, "read") else b"")
        return _HttpProbeOutcome(False, exc.code, exc.reason, body)
    except urllib.error.URLError as exc:
        raise _to_network_error(exc) from exc
    except (socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        raise _to_network_error(exc) from exc


def _read_json_body(payload: bytes) -> Optional[dict[str, Any]]:
    if not payload:
        return None
    try:
        parsed = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        data = parsed.get("data")
        return data if isinstance(data, dict) else None
    return None


class _NetworkError(Exception):
    """网络层失败；tls_error=True 表示证书校验失败（自签/过期等）。"""

    def __init__(self, tls_error: bool):
        super().__init__("tls" if tls_error else "unreachable")
        self.tls_error = tls_error


def _to_network_error(exc: BaseException) -> _NetworkError:
    reason = getattr(exc, "reason", exc)
    if isinstance(exc, ssl.SSLError) or isinstance(reason, ssl.SSLError):
        return _NetworkError(tls_error=True)
    return _NetworkError(tls_error=False)


class HealthClient:
    def check(self, base_url: str) -> HealthReport:
        live = self._probe_endpoint_with_fallback(base_url, "/health/live")
        if isinstance(live, _NetworkError):
            return self._network_report(live)
        if not live.ok:
            return _empty_report(HEALTH_UNREACHABLE, f"服务存活检查失败：HTTP {live.status_code}")
        if live.body.get("status") != "alive":
            return _empty_report(HEALTH_UNREACHABLE, "服务存活检查失败")

        ready = self._probe_endpoint_with_fallback(base_url, "/health/ready")
        if isinstance(ready, _NetworkError):
            return self._network_report(ready)
        if not ready.ok:
            return HealthReport(
                state=HEALTH_NOT_READY,
                version=ready.version,
                detail=f"服务未就绪：{ready.reason or ready.status_code}",
            )
        if ready.body.get("status") == "ready":
            return HealthReport(HEALTH_READY, ready.version, "服务就绪")
        reason_codes = ready.body.get("reasonCodes")
        detail = "服务未就绪"
        if isinstance(reason_codes, list) and reason_codes:
            detail = f"服务未就绪：{'、'.join(str(code) for code in reason_codes)}"
        return HealthReport(HEALTH_NOT_READY, ready.version, detail)

    def _probe_endpoint(self, url: str) -> _HttpProbeOutcome | _NetworkError:
        try:
            return _probe(url)
        except _NetworkError as exc:
            return exc

    def _probe_endpoint_with_fallback(self, base_url: str, path: str) -> _HttpProbeOutcome | _NetworkError:
        """主路径探测 + 反代兜底（与安卓端 HealthClient.probeWithFallback 语义一致）。

        根路径 ``/health`` 系列端点被网关静态健康块（纯文本 200）或 SPA 兜底
        （HTML 200）吞掉时，改探后端 ``/api/v1`` 前缀下的免认证别名（同 handler）。
        仅在主路径 HTTP 错误、或 2xx 但响应不是 JSON 信封（data 为空）时回退；
        网络/TLS 错误不换路径重试（同主机同结果，徒增等待）。回退仍未得到可解析
        信封则保留主路径结果，错误归因不失真。
        """
        primary = self._probe_endpoint(f"{base_url}{path}")
        if isinstance(primary, _NetworkError):
            return primary
        if primary.ok and primary.body:
            return primary
        alias = self._probe_endpoint(f"{base_url}{_API_ALIAS_PREFIX}{path}")
        if isinstance(alias, _NetworkError):
            return primary
        if alias.ok and alias.body:
            return alias
        return primary

    def _network_report(self, exc: _NetworkError) -> HealthReport:
        if exc.tls_error:
            return _empty_report(HEALTH_TLS_ERROR, "证书错误（自签证书请检查服务端配置或改用 HTTP 局域网地址）")
        return _empty_report(HEALTH_UNREACHABLE, "无法连接服务器")


def health_label(state: str) -> str:
    """健康状态中文标签（未知值回退未测试）。"""
    return HEALTH_LABELS.get(state, HEALTH_LABELS[HEALTH_UNKNOWN])
