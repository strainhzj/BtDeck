# -*- coding: utf-8 -*-
"""明文 HTTP 准入策略（dual-mode-client task .6 桌面对齐）。

与安卓端 com.btdeck.companion.net.LanHostPolicy 语义一致：
http URL 必须同时满足「主机是私有 LAN 字面量」+「用户已显式确认明文风险」；
https 一律放行；公网主机的任何 http 形态都拒绝（fail-closed）。
"""

import enum
from dataclasses import dataclass
from typing import Optional

from app.desktop_companion.hosts import ParsedUrl, is_private_lan_host, parse_url


class RejectReason(enum.Enum):
    MALFORMED_URL = "malformed_url"
    SCHEME_NOT_ALLOWED = "scheme_not_allowed"
    HTTP_PUBLIC_HOST = "http_public_host"
    HTTP_LAN_WITHOUT_CONSENT = "http_lan_without_consent"


@dataclass(frozen=True)
class PolicyVerdict:
    ok: bool
    reason: Optional[RejectReason] = None
    host: str = ""
    parsed: Optional[ParsedUrl] = None


REJECT_MESSAGES: dict[RejectReason, str] = {
    RejectReason.MALFORMED_URL: "地址无效（仅支持 http/https）",
    RejectReason.SCHEME_NOT_ALLOWED: "仅支持 http/https",
    RejectReason.HTTP_PUBLIC_HOST: (
        "明文 HTTP 仅允许私有局域网地址（如 192.168.x.x、10.x.x.x、*.local）；公网地址请使用 HTTPS"
    ),
    RejectReason.HTTP_LAN_WITHOUT_CONSENT: "私有地址使用明文 HTTP 需先勾选风险确认",
}


def check(raw_url: str, cleartext_consent: bool) -> PolicyVerdict:
    """校验服务器地址的可保存性。"""
    parsed = parse_url(raw_url)
    if parsed is None:
        return PolicyVerdict(ok=False, reason=RejectReason.MALFORMED_URL)
    return check_parsed(parsed, cleartext_consent)


def check_parsed(parsed: ParsedUrl, cleartext_consent: bool) -> PolicyVerdict:
    if parsed.scheme == "https":
        return PolicyVerdict(ok=True, parsed=parsed)
    if not is_private_lan_host(parsed.host):
        return PolicyVerdict(ok=False, reason=RejectReason.HTTP_PUBLIC_HOST, host=parsed.host, parsed=parsed)
    if not cleartext_consent:
        return PolicyVerdict(ok=False, reason=RejectReason.HTTP_LAN_WITHOUT_CONSENT, host=parsed.host, parsed=parsed)
    return PolicyVerdict(ok=True, parsed=parsed)


def needs_cleartext_consent(raw_url: str) -> bool:
    """该 URL 是否需要展示明文风险确认（http + 私有主机）。"""
    parsed = parse_url(raw_url)
    if parsed is None:
        return False
    return parsed.scheme == "http" and is_private_lan_host(parsed.host)
