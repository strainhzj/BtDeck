#!/usr/bin/env python3
"""BtDeck W4 批次 B2 受控下载器 stub（release-artifact-equivalence-gate G8）。

为 C05（下载器管理）/C06（种子核心查询）提供固定协议响应的 qBittorrent 与
Transmission 假服务；为 G8 变异演练（M2）提供响应字段改写反代。计划 §13.2：
固定协议响应、零随机、零延迟抖动、不访问真实生产下载器。

铁律：
  - 纯 stdlib（与 contract_runner 同源约束），可无依赖跑在任意 python3 容器。
  - 数据集全部为模块级常量：三制品（deb/rpm/docker）对同一 stub 的响应字节
    级一致，跨制品快照差异只能来自制品本身。

协议面（由后端实测调用链推导，见 backend：
  app/downloader/initialization.py 客户端认证/缓存
  app/api/endpoints/torrent_sync.py 种子与 tracker 同步
  app/downloader/initialization.py:_update_downloader_status 热轮询）：
  qB  POST /api/v2/auth/login            表单校验 → "Ok." / 403 "Fails."
      GET  /api/v2/app/version           → "v4.6.7"（认证探针）
      GET  /api/v2/app/webapiVersion     → "2.11.2"
      GET  /api/v2/torrents/info         → 固定种子列表
      GET  /api/v2/torrents/trackers     → 按 hash 固定 tracker 列表
      GET  /api/v2/transfer/info         → 全零速度（10 秒热轮询）
  TR  POST /transmission/rpc             409 握手（X-Transmission-Session-Id）
      method=session-get / session-stats / torrent-get

用法：
  python qb_tr_stub.py --role qb  --port 18080
  python qb_tr_stub.py --role tr  --port 18081
  python qb_tr_stub.py --role mutate-proxy --port 5002 \
      --upstream http://127.0.0.1:5001 \
      --mutate-route /health/live --mutate-field data.build.version \
      --mutate-value 1.0.6-mutated
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

# ---------------- 固定身份与凭据 ----------------

STUB_USERNAME = "w4stub-user"
STUB_PASSWORD = "w4stub-pass"
QB_VERSION = "v4.6.7"
QB_WEBAPI_VERSION = "2.11.2"
QB_SID_COOKIE = "SID=w4-fixed-qb-sid-0123456789abcdef"
TR_SESSION_ID = "w4-fixed-tr-session-id-0123456789abcdef"
TR_VERSION = "4.0.5"
TR_RPC_VERSION = 16

# ---------------- 固定数据集（qB 与 TR 表达同一逻辑内容） ----------------
# 时间戳为固定 epoch；制品内 datetime.fromtimestamp 按 TZ 渲染——CI 三制品
# 容器均为 UTC，本地双实例同机同 TZ，快照确定。

_T1_HASH = "1111111111111111111111111111111111111111"
_T2_HASH = "2222222222222222222222222222222222222222"
_T3_HASH = "3333333333333333333333333333333333333333"

_TRACKER_PRIMARY = "http://tracker.w4.example:8080/announce"
_TRACKER_SECONDARY = "http://tracker2.w4.example:8080/announce"

# qB tracker status：0 Disabled / 1 Not yet / 2 Working / 3 Updating / 4 Not working
Q_TRACKERS: Dict[str, List[Dict[str, Any]]] = {
    _T1_HASH: [
        {"url": _TRACKER_PRIMARY, "status": 2, "tier": 0, "msg": ""},
        {
            "url": _TRACKER_SECONDARY,
            "status": 4,
            "tier": 1,
            "msg": "w4 fixture tracker failure",
        },
    ],
    _T2_HASH: [
        {"url": _TRACKER_PRIMARY, "status": 2, "tier": 0, "msg": ""},
    ],
    _T3_HASH: [
        {
            "url": _TRACKER_SECONDARY,
            "status": 4,
            "tier": 0,
            "msg": "w4 fixture tracker failure",
        },
    ],
}

Q_TORRENTS: List[Dict[str, Any]] = [
    {
        "hash": _T1_HASH,
        "name": "w4-fixture-alpha",
        "state": "uploading",
        "save_path": "/downloads/w4-complete/",
        "total_size": 123456789,
        "added_on": 1700000100,
        "completion_on": 1700000200,
        "ratio": 2.5,
        "ratio_limit": -1,
        "tags": "w4,alpha",
        "category": "w4cat",
        "super_seeding": False,
        "progress": 1.0,
        "dlspeed": 0,
        "upspeed": 0,
        "eta": 8640000,
        "num_seeds": 3,
        "num_leechs": 0,
    },
    {
        "hash": _T2_HASH,
        "name": "w4-fixture-beta",
        "state": "downloading",
        "save_path": "/downloads/w4-incomplete/",
        "total_size": 987654321,
        "added_on": 1700000300,
        "completion_on": 0,
        "ratio": 0.0,
        "ratio_limit": -1,
        "tags": "",
        "category": "",
        "super_seeding": False,
        "progress": 0.42,
        "dlspeed": 0,
        "upspeed": 0,
        "eta": 3600,
        "num_seeds": 1,
        "num_leechs": 2,
    },
    {
        "hash": _T3_HASH,
        "name": "w4-fixture-gamma",
        "state": "pausedUP",
        "save_path": "/downloads/w4-complete/",
        "total_size": 555555555,
        "added_on": 1700000400,
        "completion_on": 1700000500,
        "ratio": 1.0,
        "ratio_limit": -2,
        "tags": "w4",
        "category": "",
        "super_seeding": False,
        "progress": 1.0,
        "dlspeed": 0,
        "upspeed": 0,
        "eta": 8640000,
        "num_seeds": 0,
        "num_leechs": 0,
    },
]

Q_TRANSFER_INFO: Dict[str, Any] = {
    "dl_info_speed": 0,
    "dl_info_data": 0,
    "up_info_speed": 0,
    "up_info_data": 0,
    "dl_rate_limit": 0,
    "up_rate_limit": 0,
    "connection_status": "seeding",
}

# C12 路径映射内部探测的调用面（path_mapping_validation）：
# app/preferences 的 save_path + sync/maindata 的 torrents.*.save_path
Q_PREFERENCES: Dict[str, Any] = {
    "save_path": "/downloads/w4-incomplete",
    "temp_path_enabled": False,
    "temp_path": "",
    "autorun_enabled": False,
}
Q_MAINDATA: Dict[str, Any] = {
    "rid": 1,
    "full_update": True,
    "torrents": {
        t["hash"]: {"save_path": t["save_path"]} for t in [Q_TORRENTS[0], Q_TORRENTS[2]]
    },
    "categories": {},
    "tags": [],
    "server_state": {"connection_status": "seeding"},
}

# TR status：0 STOPPED / 4 DOWNLOAD / 6 SEED；error 0 + 空 errorString。
# trackerStats 字段集覆盖 torrent_sync TR 分支直取的属性（lastAnnounceResult
# 等无守卫访问，缺失即 KeyError 回滚整行——本地双实例实证）与
# tracker_mapper.resolve_transmission_tracker_status_code 读取的布尔统计。
_TR_TRACKER_OK: Dict[str, Any] = {
    "id": 1,
    "lastAnnounceResult": "w4 ok",
    "lastAnnounceSucceeded": True,
    "lastAnnounceTimedOut": False,
    "hasAnnounced": True,
    "announceState": 3,
    "lastScrapeResult": "w4 ok",
    "lastScrapeSucceeded": True,
    "hasScraped": True,
    "seederCount": 3,
    "leecherCount": 0,
    "downloadCount": 1,
}
_TR_TRACKER_BAD: Dict[str, Any] = {
    "id": 2,
    "lastAnnounceResult": "w4 fixture tracker failure",
    "lastAnnounceSucceeded": False,
    "lastAnnounceTimedOut": False,
    "hasAnnounced": True,
    "announceState": 3,
    "lastScrapeResult": "w4 scrape failure",
    "lastScrapeSucceeded": False,
    "hasScraped": True,
    "seederCount": 0,
    "leecherCount": 0,
    "downloadCount": 0,
}
TR_TORRENTS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "hashString": _T1_HASH,
        "name": "w4-fixture-alpha",
        "status": 6,
        "error": 0,
        "errorString": "",
        "downloadDir": "/downloads/w4-complete/",
        "totalSize": 123456789,
        "torrentFile": "/var/lib/transmission-daemon/resume/w4-alpha.torrent",
        "addedDate": 1700000100,
        "doneDate": 1700000200,
        "uploadRatio": 2.5,
        "ratio": 2.5,
        "seedRatioLimit": -1,
        "labels": ["w4", "alpha"],
        "percentDone": 1.0,
        "rateDownload": 0,
        "rateUpload": 0,
        "trackerStats": [
            dict(
                _TR_TRACKER_OK,
                announce=_TRACKER_PRIMARY,
                sitename="tracker.w4.example",
                tier=0,
            ),
            dict(
                _TR_TRACKER_BAD,
                announce=_TRACKER_SECONDARY,
                sitename="tracker2.w4.example",
                tier=1,
            ),
        ],
    },
    {
        "id": 2,
        "hashString": _T2_HASH,
        "name": "w4-fixture-beta",
        "status": 4,
        "error": 0,
        "errorString": "",
        "downloadDir": "/downloads/w4-incomplete/",
        "totalSize": 987654321,
        "torrentFile": "/var/lib/transmission-daemon/resume/w4-beta.torrent",
        "addedDate": 1700000300,
        "doneDate": 0,
        "uploadRatio": 0.0,
        "ratio": 0.0,
        "seedRatioLimit": -1,
        "labels": [],
        "percentDone": 0.42,
        "rateDownload": 0,
        "rateUpload": 0,
        "trackerStats": [
            dict(
                _TR_TRACKER_OK,
                announce=_TRACKER_PRIMARY,
                sitename="tracker.w4.example",
                tier=0,
            ),
        ],
    },
]

TR_SESSION: Dict[str, Any] = {
    "version": TR_VERSION,
    "rpc-version": TR_RPC_VERSION,
    "rpc-version-minimum": 1,
    "session-id": TR_SESSION_ID,
    "download-dir": "/downloads/w4-incomplete",
    "config-dir": "/etc/transmission-daemon",
    "blocklist-enabled": False,
    "download-queue-enabled": True,
    "download-queue-size": 5,
    "seed-queue-enabled": False,
    "seed-queue-size": 10,
    "units": {"speed-units": 0, "speed-bytes": 1000},
}

TR_SESSION_STATS: Dict[str, Any] = {
    "activeTorrentCount": 2,
    "downloadSpeed": 0,
    "uploadSpeed": 0,
    "downloadedBytes": 0,
    "uploadedBytes": 0,
    "filesAdded": 0,
    "secondsActive": 1,
    "sessionCount": 1,
}


def _log(role: str, method: str, path: str, status: int) -> None:
    """逐请求单行日志：CI 排障时反查制品实际打到 stub 的调用面。"""
    sys.stdout.write(f"W4STUB {role} {method} {path} -> {status}\n")
    sys.stdout.flush()


class _BaseHandler(BaseHTTPRequestHandler):
    role = "base"

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003 - 覆写为单行
        pass

    def _reply(
        self,
        status: int,
        body: bytes,
        content_type: str = "application/json",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)
        _log(self.role, self.command, self.path, status)

    def _reply_text(
        self,
        status: int,
        text: str,
        content_type: str = "text/html; charset=UTF-8",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._reply(status, text.encode("utf-8"), content_type, extra_headers)

    def _reply_json(
        self, status: int, payload: Any, extra_headers: Optional[Dict[str, str]] = None
    ) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        self._reply(status, body, "application/json", extra_headers)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""


class QbHandler(_BaseHandler):
    """qBittorrent WebUI API v2 stub（SID Cookie 强制校验，fail-closed）。

    数据端点 GET/POST 双收：qbittorrentapi 对 torrents/info 等走 POST
    （_post_cast，2025.2.0 实测），真实 qB WebUI 同样双收。
    """

    role = "qb"

    def _sid_ok(self) -> bool:
        cookie = self.headers.get("Cookie") or ""
        return QB_SID_COOKIE in cookie

    def _authorized_api(self) -> bool:
        if self._sid_ok():
            return True
        self._reply_text(403, "Fails.")
        return False

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        body = self._read_body()
        path = self.path.split("?")[0]
        if path == "/api/v2/auth/login":
            form = urllib.parse.parse_qs(body.decode("utf-8", errors="replace"))
            if form.get("username") == [STUB_USERNAME] and form.get("password") == [
                STUB_PASSWORD
            ]:
                self._reply_text(
                    200,
                    "Ok.",
                    "text/html; charset=UTF-8",
                    {"Set-Cookie": QB_SID_COOKIE + "; path=/"},
                )
            else:
                self._reply_text(403, "Fails.")
            return
        self._dispatch_api(body)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch_api(b"")

    def _dispatch_api(self, body: bytes) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        # 参数可来自 query 或表单体（POST 时 qbittorrentapi 用表单）
        params: Dict[str, List[str]] = dict(urllib.parse.parse_qs(parsed.query))
        if body:
            for key, values in urllib.parse.parse_qs(
                body.decode("utf-8", errors="replace")
            ).items():
                params.setdefault(key, values)
        if path == "/api/v2/app/version":
            if self._authorized_api():
                self._reply_text(200, QB_VERSION)
            return
        if path == "/api/v2/app/webapiVersion":
            if self._authorized_api():
                self._reply_text(200, QB_WEBAPI_VERSION)
            return
        if path == "/api/v2/app/defaultSavePath":
            # C12 路径探测调用面（qbittorrentapi app_default_save_path）：
            # 纯文本响应，与 Q_PREFERENCES.save_path 同值
            if self._authorized_api():
                self._reply_text(200, Q_PREFERENCES["save_path"])
            return
        if path == "/api/v2/torrents/info":
            if self._authorized_api():
                self._reply_json(200, Q_TORRENTS)
            return
        if path == "/api/v2/torrents/trackers":
            if self._authorized_api():
                torrent_hash = (params.get("hash") or [""])[0]
                self._reply_json(200, Q_TRACKERS.get(torrent_hash, []))
            return
        if path == "/api/v2/transfer/info":
            if self._authorized_api():
                self._reply_json(200, Q_TRANSFER_INFO)
            return
        if path == "/api/v2/app/preferences":
            if self._authorized_api():
                self._reply_json(200, Q_PREFERENCES)
            return
        if path == "/api/v2/sync/maindata":
            if self._authorized_api():
                self._reply_json(200, Q_MAINDATA)
            return
        if path == "/api/v2/app/buildInfo":
            if self._authorized_api():
                self._reply_json(
                    200, {"qt": "stub", "libtorrent": "stub", "qbittorrent": QB_VERSION}
                )
            return
        if path.startswith("/api/v2/"):
            if self._authorized_api():
                self._reply_text(404, "Not Found")
            return
        self._reply_text(404, "Not Found")


class TrHandler(_BaseHandler):
    """Transmission RPC stub（409 握手 + 固定 session-id + Basic Auth）。"""

    role = "tr"

    def _basic_auth_ok(self) -> bool:
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        return decoded == f"{STUB_USERNAME}:{STUB_PASSWORD}"

    def do_POST(self) -> None:  # noqa: N802
        # 先读完请求体再应答（含 401/409 早退路径）：客户端还在写时断开在
        # Windows 上偶发 connection reset，污染鉴权异常语义
        body = self._read_body()
        if not self._basic_auth_ok():
            self._reply_text(401, "401: Unauthorized", "text/plain")
            return
        session_header = self.headers.get("X-Transmission-Session-Id")
        if session_header != TR_SESSION_ID:
            # 真实 TR 对缺头/错头返回 409 + 当次 session-id（客户端自动重试）
            self._reply_text(
                409,
                "409: Conflict",
                "text/plain",
                {"X-Transmission-Session-Id": TR_SESSION_ID},
            )
            return
        try:
            request = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reply_json(400, {"result": "error", "arguments": {}})
            return
        method = request.get("method", "")
        arguments: Dict[str, Any] = {}
        if method == "session-get":
            arguments = dict(TR_SESSION)
        elif method == "session-stats":
            arguments = dict(TR_SESSION_STATS)
        elif method == "torrent-get":
            arguments = {"torrents": [dict(t) for t in TR_TORRENTS], "removed": ""}
        elif method == "free-space":
            arguments = {"path": "/downloads", "size-bytes": 123456789}
        else:
            self._reply_json(
                200, {"result": f"unknown method: {method}", "arguments": {}}
            )
            return
        self._reply_json(200, {"result": "success", "arguments": arguments})

    def do_GET(self) -> None:  # noqa: N802
        self._reply_text(404, "Not Found", "text/plain")


def _set_dotted(payload: Any, dotted: str, value: str) -> bool:
    """按 a.b.c 路径写入 JSON 树；路径不存在返回 False（fail-closed 不静默）。"""
    keys = dotted.split(".")
    node = payload
    for key in keys[:-1]:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    if not isinstance(node, dict) or keys[-1] not in node:
        return False
    node[keys[-1]] = value
    return True


class MutateProxyHandler(_BaseHandler):
    """G8 变异演练（M2）：反代上游制品实例并改写命中路由的单个响应字段。

    响应字段差异必须让 compare_snapshots 报红——本角色制造的就是那种差异。
    """

    role = "mutate-proxy"
    upstream = ""
    mutate_route = ""
    mutate_field = ""
    mutate_value = ""

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length > 0 else None
        url = self.upstream.rstrip("/") + self.path
        req = urllib.request.Request(url, data=body, method=self.command)
        for header in ("Content-Type", "X-Access-Token"):
            if self.headers.get(header):
                req.add_header(header, self.headers[header])
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                raw = resp.read()
                resp_headers = dict(resp.headers.items())
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read()
            resp_headers = dict(exc.headers.items())
        except urllib.error.URLError:
            self._reply_text(502, "mutate-proxy upstream unreachable", "text/plain")
            return
        if self.mutate_route and self.mutate_route in self.path:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and _set_dotted(
                payload, self.mutate_field, self.mutate_value
            ):
                raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
                resp_headers["Content-Length"] = str(len(raw))
        content_type = resp_headers.get("Content-Type", "application/json")
        self._reply(status, raw, content_type)

    def do_GET(self) -> None:  # noqa: N802
        self._proxy()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()


HANDLERS = {
    "qb": QbHandler,
    "tr": TrHandler,
    "mutate-proxy": MutateProxyHandler,
}


def serve(
    role: str,
    bind: str,
    port: int,
    upstream: str = "",
    mutate_route: str = "",
    mutate_field: str = "",
    mutate_value: str = "",
) -> None:
    handler = HANDLERS[role]
    if role == "mutate-proxy":
        handler.upstream = upstream
        handler.mutate_route = mutate_route
        handler.mutate_field = mutate_field
        handler.mutate_value = mutate_value
    server = ThreadingHTTPServer((bind, port), handler)
    sys.stdout.write(f"W4STUB {role} listening on {bind}:{port}\n")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=sorted(HANDLERS))
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--upstream", default="", help="mutate-proxy：上游制品地址")
    parser.add_argument(
        "--mutate-route", default="", help="mutate-proxy：命中改写的 URL 子串"
    )
    parser.add_argument(
        "--mutate-field", default="", help="mutate-proxy：点分 JSON 字段路径"
    )
    parser.add_argument("--mutate-value", default="", help="mutate-proxy：改写后的值")
    args = parser.parse_args(argv)
    if args.role == "mutate-proxy" and not (
        args.upstream and args.mutate_route and args.mutate_field
    ):
        parser.error("mutate-proxy 需要 --upstream/--mutate-route/--mutate-field")
    serve(
        args.role,
        args.bind,
        args.port,
        args.upstream,
        args.mutate_route,
        args.mutate_field,
        args.mutate_value,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
