# -*- coding: utf-8 -*-
"""URL 解析与主机分类（dual-mode-client task .6 桌面对齐）。

与安卓端 com.btdeck.companion.util.Hosts 语义一致：
- 只允许 http/https（必须显式带 ``://``，裸 host 不接受）；
- 私有主机判定不做 DNS 解析（避免阻塞与不可判定行为），只认字面量：
  loopback 127/8、RFC1918 三段、169.254/16、IPv6 ``::1``/``fc00::/7``/
  ``fe80::/10``、``*.local`` 与 ``localhost``；
- 真实域名指向内网主机的场景按公网处理（fail-closed：明文一律拒绝，
  HTTPS 不受影响）。
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

_HTTPS_DEFAULT_PORT = 443
_HTTP_DEFAULT_PORT = 80


@dataclass(frozen=True)
class ParsedUrl:
    scheme: str
    host: str
    port: int
    base_url: str


def parse_url(raw: str) -> Optional[ParsedUrl]:
    """解析并规范化 baseUrl（scheme://host[:port]，无路径无 query）。非法返回 None。"""
    trimmed = raw.strip()
    if not trimmed:
        return None

    try:
        split = urlsplit(trimmed)
    except ValueError:
        return None
    if split.scheme not in ("http", "https"):
        return None

    host = split.hostname
    if not host:
        return None
    try:
        port = split.port
    except ValueError:
        # 非数字/越界端口（urlsplit 惰性解析，访问 .port 时才抛）
        return None
    if port is None:
        port = _HTTPS_DEFAULT_PORT if split.scheme == "https" else _HTTP_DEFAULT_PORT
    if not 1 <= port <= 65535:
        return None

    host_part = f"[{host}]" if ":" in host else host
    default_port = (split.scheme == "https" and port == _HTTPS_DEFAULT_PORT) or (
        split.scheme == "http" and port == _HTTP_DEFAULT_PORT
    )
    base_url = f"{split.scheme}://{host_part}" + ("" if default_port else f":{port}")
    return ParsedUrl(scheme=split.scheme, host=host, port=port, base_url=base_url)


def is_loopback_host(host: str) -> bool:
    """是否回环主机（127/8、IPv6 ``::1``、``localhost``）。

    与安卓端 Hosts.isLoopbackHost 对齐：回环明文不上网络线，本机服务端
    （http://127.0.0.1:port）免明文风险确认。
    """
    h = host.lower()
    if h.endswith("."):
        h = h[:-1]
    if h == "localhost" or h == "::1":
        return True
    if ":" in h:
        return False
    parts = h.split(".")
    if len(parts) != 4:
        return False
    if not parts[0] == "127":
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def is_private_lan_host(host: str) -> bool:
    """是否私有/本地主机（按字面量判定，不做 DNS）。"""
    h = host.lower()
    if h.endswith("."):
        h = h[:-1]
    if h == "localhost":
        return True
    if h.endswith(".local"):
        return True
    if ":" in h:
        return _is_private_ipv6(h)

    parts = h.split(".")
    if len(parts) != 4:
        return False
    octets: list[int] = []
    for part in parts:
        if not part or len(part) > 3 or not (part.isascii() and part.isdigit()):
            return False
        value = int(part)
        if value > 255:
            return False
        octets.append(value)

    o0, o1 = octets[0], octets[1]
    return (
        o0 == 127  # loopback 127.0.0.0/8
        or o0 == 10  # RFC1918
        or (o0 == 172 and 16 <= o1 <= 31)
        or (o0 == 192 and o1 == 168)
        or (o0 == 169 and o1 == 254)  # link-local
    )


def _is_private_ipv6(h: str) -> bool:
    # 仅字面量判定：::1 / fc00::/7（ULA）/ fe80::/10（link-local）
    if h in ("::1", "::"):
        return True
    first_group = h.split(":", 1)[0]
    if not first_group:
        return h.startswith("f") or h.startswith("fe8")
    try:
        first = int(first_group, 16)
    except ValueError:
        return False
    return (first & 0xFE00) == 0xFC00 or (first & 0xFFC0) == 0xFE80
