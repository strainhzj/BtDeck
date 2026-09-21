"""W4 黑盒契约测试器回归（release-artifact-equivalence-gate task .8 / G8）。

1. 铁律：contract_runner / compare_snapshots 禁止 import app.*（绕过真实制品即失效）。
2. 规范化纯函数：形状提取、身份字段视图、CommonResponse 外壳。
3. 端到端：内嵌 mock BtDeck API（http.server）跑 C01~C04 全场景 → 快照结构断言。
4. 变异：mock 响应里改一个身份字段 → 快照必须能检出（漏比较=退出门失败）。
5. compare_snapshots：差异检测、精确 exception 命中、宽泛/过期规则拒绝、stale 报告。
"""

from __future__ import annotations

import importlib.util
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUNNER_PATH = _REPO_ROOT / "scripts" / "release" / "contract_runner.py"
_COMPARE_PATH = _REPO_ROOT / "scripts" / "release" / "compare_snapshots.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_module(_RUNNER_PATH, "btdeck_contract_runner")


@pytest.fixture(scope="module")
def comparer():
    return _load_module(_COMPARE_PATH, "btdeck_compare_snapshots")


class TestBlackboxIronRule:
    def test_runner_never_imports_app(self):
        src = _RUNNER_PATH.read_text(encoding="utf-8")
        imports = re.findall(r"^\s*(?:from|import)\s+(app[\w.]*)", src, re.M)
        assert not imports, f"contract_runner 禁止 import app.*（实测: {imports}）"

    def test_comparer_never_imports_app(self):
        src = _COMPARE_PATH.read_text(encoding="utf-8")
        imports = re.findall(r"^\s*(?:from|import)\s+(app[\w.]*)", src, re.M)
        assert not imports, f"compare_snapshots 禁止 import app.*（实测: {imports}）"


class TestNormalizationPureFunctions:
    def test_shape_extracts_paths_without_values(self, runner):
        payload = {"a": 1, "b": {"c": [1, 2, {"d": "x"}]}}
        assert runner.shape(payload) == ["a", "b.c[]", "b.c[].d"]

    def test_envelope_keeps_code_status_msg_only(self, runner):
        result = runner.HttpResult(
            200, {"status": "success", "code": "200", "msg": "ok", "data": [1]}, b""
        )
        env = runner.envelope(result)
        assert env == {"http": 200, "code": "200", "status": "success", "msg": "ok"}

    def test_identity_view_precise_fields(self, runner):
        # identity_view 是场景内部函数；此处锚定身份字段契约（G1 等价对象）
        assert "gitSha" in runner.IDENTITY_FIELDS
        assert "frontendManifestSha256" in runner.IDENTITY_FIELDS
        assert "status" in runner.IDENTITY_FIELDS


# ---------------- 内嵌 mock BtDeck API ----------------

MOCK_LIVE = {
    "status": "success",
    "msg": "服务存活",
    "code": "200",
    "data": {
        "status": "alive",
        "version": "1.0.6",
        "build": {
            "status": "ok",
            "productVersion": "1.0.6",
            "gitSha": "a" * 40,
            "gitTag": "v1.0.6",
            "artifactKind": "linux-deb",
            "alembicHead": "b" * 12,
            "frontendManifestSha256": "c" * 64,
        },
    },
}
MOCK_READY = {
    "status": "success",
    "msg": "应用已就绪",
    "code": "200",
    "data": {
        "status": "ready",
        "version": "1.0.6",
        "checks": {"database": {"ok": True}, "scheduler": {"ok": True}},
        "build": dict(MOCK_LIVE["data"]["build"]),
    },
}


def _mock_torrent_rows(downloader_id: str, downloader_name: str, tr: bool = False):
    """与 qb_tr_stub 固定数据集同源的 getList 行（qB 3 行 / TR 2 行）。

    键名按真实契约 camelCase（实例实测：infoId/downloaderId/savePath/...）。
    """
    rows = [
        {
            "infoId": f"info-{downloader_id}-alpha",
            "downloaderId": downloader_id,
            "downloaderName": downloader_name,
            "name": "w4-fixture-alpha",
            "status": "seeding",
            "size": 123456789,
            "savePath": "/downloads/w4-complete/",
            "tags": "w4,alpha",
            "category": "" if tr else "w4cat",
            "ratio": 2.5,
            "addedDate": "2023-11-14 22:15:00",
            "completedDate": "2023-11-14 22:16:40",
            "createTime": "2026-09-02 00:00:00",
        },
        {
            "infoId": f"info-{downloader_id}-beta",
            "downloaderId": downloader_id,
            "downloaderName": downloader_name,
            "name": "w4-fixture-beta",
            "status": "downloading",
            "size": 987654321,
            "savePath": "/downloads/w4-incomplete/",
            "tags": "",
            "category": "",
            "ratio": 0.0,
            "addedDate": "2023-11-14 22:18:20",
            "completedDate": None,
            "createTime": "2026-09-02 00:00:00",
        },
    ]
    if not tr:
        rows.append(
            {
                "infoId": f"info-{downloader_id}-gamma",
                "downloaderId": downloader_id,
                "downloaderName": downloader_name,
                "name": "w4-fixture-gamma",
                "status": "pausedUP",
                "size": 555555555,
                "savePath": "/downloads/w4-complete/",
                "tags": "w4",
                "category": "",
                "ratio": 1.0,
                "addedDate": "2023-11-14 22:20:00",
                "completedDate": "2023-11-14 22:21:40",
                "createTime": "2026-09-02 00:00:00",
            }
        )
    if tr:
        rows[0]["torrentId"] = 1
        rows[1]["torrentId"] = 2
    return rows


def _build_mock_app(mutations: Dict[str, Any] | None = None):
    """构造带固定状态的 mock BtDeck API handler 类。

    mutations: {"live_version": "9.9.9"} 等注入点，用于变异测试。
    状态：admin/admin（must_change_password=true）→ C04 改密到契约密码。
    B2 路由镜像真实契约（downloader CRUD/getList 信封/分页/路径映射），
    种子数据集与 qb_tr_stub 固定数据集同源（同名同状态同尺寸）。
    """
    state: Dict[str, Any] = {
        "password": "admin",
        "must_change": True,
        "revoked": set(),
        "seq": 0,
        "templates": [],
        "downloaders": {},  # id -> {downloader_id,nickname,host,port,downloader_type,...}
        "torrents": {},  # downloader_id -> [rows]
        "path_mappings": {},  # downloader_id -> {"mappings": [...], "default_mapping": None}
    }
    mut = mutations or {}

    def _seed_c06():
        """预置 C06 夹具终态（C10 重启后视图测试用）。"""
        qb_rows = _mock_torrent_rows("dl-qb", "w4-c06-qb")
        tr_rows = _mock_torrent_rows("dl-tr", "w4-c06-tr", tr=True)
        state["downloaders"]["dl-qb"] = {
            "downloader_id": "dl-qb",
            "nickname": "w4-c06-qb",
            "host": "w4-stub",
            "port": 18080,
            "downloader_type": 0,
            "enabled": True,
        }
        state["downloaders"]["dl-tr"] = {
            "downloader_id": "dl-tr",
            "nickname": "w4-c06-tr",
            "host": "w4-stub",
            "port": 18081,
            "downloader_type": 1,
            "enabled": True,
        }
        state["torrents"]["dl-qb"] = qb_rows
        state["torrents"]["dl-tr"] = tr_rows

    if mut.get("preseed_c06"):
        _seed_c06()
    if mut.get("password"):
        state["password"] = mut["password"]
        state["must_change"] = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 静默
            return

        @staticmethod
        def _ok(data):
            return {"status": "success", "code": "200", "msg": "ok", "data": data}

        @staticmethod
        def _err(code, msg):
            return {"status": "error", "code": code, "msg": msg, "data": []}

        def _send(self, payload: Dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health/live":
                payload = json.loads(json.dumps(MOCK_LIVE))
                if "live_version" in mut:
                    payload["data"]["version"] = mut["live_version"]
                self._send(payload)
            elif self.path == "/health/ready":
                self._send(MOCK_READY)
            elif self.path == "/api/v1/openapi.json" or self.path == "/openapi.json":
                self._send(
                    {
                        "openapi": "3.1.0",
                        "info": {"title": "BtDeck"},
                        "paths": {
                            "/api/v1/auth/login": {"post": {}},
                            "/health/live": {"get": {}},
                        },
                        "components": {
                            "schemas": {"UserLogin": {}, "CommonResponse": {}}
                        },
                    }
                )
            elif self.path == "/api/v1/advanced-search/search-templates":
                self._send(self._ok(state["templates"]))
            elif self.path == "/api/v1/cronTasks/list":
                self._send(
                    self._ok(
                        [
                            {
                                "name": "种子信息同步任务",
                                "cron": "*/5 * * * *",
                                "enabled": True,
                            },
                            {
                                "name": "Tracker 状态同步任务",
                                "cron": "*/2 * * * *",
                                "enabled": True,
                            },
                        ]
                    )
                )
            elif self.path.startswith("/api/v1/notifications/unread-count"):
                self._send(
                    {
                        "status": "success",
                        "code": "200",
                        "msg": "ok",
                        "data": {"count": 0},
                    }
                )
            elif self.path.startswith("/api/v1/notifications"):
                self._send(
                    {
                        "status": "success",
                        "code": "200",
                        "msg": "ok",
                        "data": {
                            "list": [{"title": "n", "type": "system"}],
                            "total": 1,
                            "pageSize": 5,
                        },
                    }
                )
            elif self.path.startswith("/api/v1/audit-logs/operation-types"):
                self._send(
                    {
                        "status": "success",
                        "code": "200",
                        "msg": "ok",
                        "data": ["create", "delete", "update"],
                    }
                )
            elif self.path == "/api/v1/downloader/getList":
                items = [
                    {"downloader_id": d["downloader_id"], "nickname": d["nickname"]}
                    for d in state["downloaders"].values()
                ]
                self._send(self._ok(sorted(items, key=lambda x: x["nickname"])))
            elif self.path.startswith("/api/v1/downloader/detail/"):
                dl_id = self.path.rsplit("/", 1)[-1]
                record = state["downloaders"].get(dl_id)
                if record:
                    view = {k: v for k, v in record.items()}
                    view["password"] = "ENCRYPTED"
                    self._send(self._ok([view]))
                else:
                    self._send(self._err("404", "该下载器已被删除或不存在"))
            elif self.path == "/api/v1/torrents/tracker-domains":
                self._send(self._ok(["tracker.w4.example", "tracker2.w4.example"]))
            elif self.path.startswith("/api/v1/torrents/getList"):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                rows = [r for rows in state["torrents"].values() for r in rows]
                if query.get("downloader_id"):
                    rows = [
                        r
                        for r in rows
                        if r["downloaderId"] == query["downloader_id"][0]
                    ]
                if query.get("downloader_name_like"):
                    needle = query["downloader_name_like"][0]
                    rows = [r for r in rows if needle in r["downloaderName"]]
                if query.get("name_like"):
                    needle = query["name_like"][0]
                    rows = [r for r in rows if needle in r["name"]]
                if query.get("status"):
                    wanted = set(query["status"][0].split(","))
                    rows = [r for r in rows if r["status"] in wanted]
                if mut.get("torrent_status"):
                    rows = [
                        (
                            dict(r, status=mut["torrent_status"])
                            if r["name"] == "w4-fixture-alpha"
                            else r
                        )
                        for r in rows
                    ]
                rows = sorted(rows, key=lambda r: r["name"])
                skip = int(query.get("skip", ["0"])[0])
                limit = int(query.get("limit", ["100"])[0])
                page = rows[skip : skip + limit]
                self._send(
                    self._ok(
                        {
                            "list": page,
                            "total": len(rows),
                            "pageSize": limit,
                        }
                    )
                )
            elif re.fullmatch(
                r"/api/v1/torrents/torrents/[^/]+/[^/]+/[^/]+", self.path
            ):
                parts = self.path.split("/")
                info_id = parts[-3]
                found = next(
                    (
                        r
                        for rows in state["torrents"].values()
                        for r in rows
                        if r["infoId"] == info_id
                    ),
                    None,
                )
                if found:
                    self._send(self._ok(found))
                else:
                    self._send(self._err("404", "未找到该种子"))
            elif self.path.startswith("/api/v1/downloader/") and self.path.endswith(
                "/path-mapping"
            ):
                dl_id = self.path.split("/")[4]
                if dl_id in state["downloaders"]:
                    config = state["path_mappings"].get(
                        dl_id, {"mappings": [], "default_mapping": None}
                    )
                    self._send(self._ok(config))
                else:
                    self._send(self._err("404", "下载器不存在"))
            elif self.path == "/" or self.path.startswith("/w4-fake"):
                body = (
                    b'<!doctype html><html><head><script src="/assets/app.js"></script>'
                )
                body += b'<link rel="stylesheet" href="/assets/style.css"></head><body>x</body></html>'
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send({"status": "error", "code": "404", "msg": "nf"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            token = self.headers.get("X-Access-Token", "")
            path = self.path

            ok = self._ok
            err = self._err

            if path == "/api/v1/auth/login":
                if req.get("password") != state["password"]:
                    self._send(err("401", "用户名或密码错误"))
                    return
                state["seq"] += 1
                self._send(
                    ok(
                        {
                            "access_token": f"tok-{state['seq']}",
                            "refresh_token": "ref-fixed",
                            "token_type": "bearer",
                            "user_id": 1,
                            "must_change_password": state["must_change"],
                        }
                    )
                )
            elif token.startswith("tok-") and token not in state["revoked"]:
                if path == "/api/v1/user/info":
                    self._send(
                        ok(
                            {
                                "user": {
                                    "userId": "1",
                                    "roles": ["admin"],
                                    "name": "admin",
                                    "twoFactorFlag": "0",
                                    "mustChangePassword": state["must_change"],
                                }
                            }
                        )
                    )
                elif path == "/api/v1/user/changePassword":
                    state["password"] = "W4-Contract-Pass-2026"
                    state["must_change"] = False
                    self._send(ok({"changed": True}))
                elif path == "/api/v1/user/logout":
                    state["revoked"].add(token)
                    self._send(ok({"logout": True}))
                elif path == "/api/v1/auth/refresh":
                    self._send(err("401", "access token 不能刷新"))
                elif path == "/api/v1/advanced-search/search-templates":
                    new_tpl = {
                        "id": f"tpl-{state['seq']}",
                        "name": req.get("name"),
                        "conditions": req.get("conditions"),
                        "is_public": req.get("is_public", False),
                    }
                    state["templates"].append(new_tpl)
                    # 契约实测：create 的 data 是对象（非 [obj] 信封）
                    self._send(
                        {
                            "status": "success",
                            "code": "200",
                            "msg": "创建模板成功",
                            "data": new_tpl,
                        }
                    )
                elif path == "/api/v1/downloader/add":
                    state["seq"] += 1
                    dl_id = f"dl-{state['seq']}"
                    state["downloaders"][dl_id] = {
                        "downloader_id": dl_id,
                        "nickname": req.get("nickname"),
                        "host": req.get("host"),
                        "port": req.get("port"),
                        "username": req.get("username"),
                        "downloader_type": req.get("downloader_type"),
                        "enabled": bool(req.get("enabled")),
                        "is_ssl": bool(req.get("is_ssl")),
                    }
                    # 种子行按 stub 数据集即时可见（真实链路由 /torrents/list 同步）
                    if str(req.get("nickname", "")).startswith("w4-c06"):
                        state["torrents"][dl_id] = _mock_torrent_rows(
                            dl_id,
                            req.get("nickname"),
                            tr=bool(req.get("downloader_type")),
                        )
                    self._send(ok(None))
                elif path.startswith("/api/v1/downloader/test/"):
                    dl_id = path.rsplit("/", 1)[-1]
                    record = state["downloaders"].get(dl_id)
                    if not record:
                        self._send(err("404", "该下载器已被删除或不存在"))
                        return
                    # 真实语义：可达性探测（ICMP/TCP）——不可解析主机名（.invalid）
                    # 或关闭端口（59999 兼容旧负向路径）都判定失败
                    host = str(record.get("host") or "")
                    reachable = (
                        "invalid" not in host
                        and "dead" not in host
                        and int(record.get("port") or 0) != 59999
                    )
                    msg = "连接成功" if reachable else "连接失败"
                    self._send(
                        ok(
                            {
                                "success": reachable,
                                "delay": 1.23 if reachable else None,
                                "message": msg,
                            }
                        )
                    )
                elif path.startswith("/api/v1/downloader/update/"):
                    dl_id = path.rsplit("/", 1)[-1]
                    record = state["downloaders"].get(dl_id)
                    if not record:
                        self._send(err("404", "下载器不存在"))
                        return
                    old_nickname = record["nickname"]
                    for key in (
                        "nickname",
                        "host",
                        "port",
                        "username",
                        "downloader_type",
                    ):
                        if req.get(key) is not None:
                            record[key] = req.get(key)
                    if record["nickname"] != old_nickname:
                        for rows in state["torrents"].values():
                            for row in rows:
                                if row["downloaderName"] == old_nickname:
                                    row["downloaderName"] = record["nickname"]
                    self._send(ok(None))
                elif path == "/api/v1/torrents/list":
                    enabled = [d for d in state["downloaders"].values() if d["enabled"]]
                    count = len(enabled)
                    if mut.get("sync_zero"):
                        count = 0
                    self._send(
                        ok(
                            {
                                "synced_count": count,
                                "total_count": len(enabled),
                                "errors": [],
                            }
                        )
                    )
                elif path == "/api/v1/downloader/path-mapping/add":
                    dl_id = req.get("downloader_id")
                    config = state["path_mappings"].setdefault(
                        dl_id, {"mappings": [], "default_mapping": None}
                    )
                    # 实测契约：重复 internal 的 add 也 200（服务端不拒绝重复路径）
                    config["mappings"].append(
                        {
                            "name": req.get("name"),
                            "internal": req.get("internal"),
                            "external": req.get("external"),
                            "description": req.get("description"),
                            "mapping_type": req.get("mapping_type", "local"),
                        }
                    )
                    self._send(ok(None))
                elif path == "/api/v1/downloader/path-mapping/remove":
                    dl_id = req.get("downloader_id")
                    config = state["path_mappings"].get(dl_id, {"mappings": []})
                    config["mappings"] = [
                        m for m in config["mappings"] if m["name"] != req.get("name")
                    ]
                    self._send(ok(None))
                elif path.endswith("/path-mapping/test"):
                    dl_id = path.split("/")[4]
                    checks = [
                        {
                            "name": m["name"],
                            "valid": False,
                            "internal": {
                                "path": m["internal"],
                                "valid": False,
                                "message": "w4 mock: 内部目录不可用",
                            },
                            "external": {
                                "path": m["external"],
                                "valid": False,
                                "message": "w4 mock: 外部目录不可用",
                            },
                        }
                        for m in state["path_mappings"]
                        .get(dl_id, {})
                        .get("mappings", [])
                    ]
                    self._send(
                        ok(
                            {
                                "valid": False,
                                "message": "目录探测失败（mock 固定语义）",
                                "backend_validation": {
                                    "json_format_valid": True,
                                    "structure_valid": True,
                                    "fields_complete": True,
                                    "no_path_conflicts": True,
                                    "downloader_available": False,
                                    "internal_paths_valid": False,
                                    "external_paths_valid": False,
                                    "path_checks": checks,
                                    "errors": [],
                                },
                            }
                        )
                    )
                else:
                    self._send(err("404", "nf"), 404)
            else:
                self._send(err("401", "未认证"))

        def do_PUT(self):
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            if self.path.startswith(
                "/api/v1/advanced-search/search-templates/"
            ) and self.headers.get("X-Access-Token", "").startswith("tok-"):
                tpl_id = self.path.rsplit("/", 1)[-1]
                for t in state["templates"]:
                    if t["id"] == tpl_id:
                        t["name"] = req.get("name", t["name"])
                self._send(
                    {"status": "success", "code": "200", "msg": "更新成功", "data": {}}
                )
            else:
                self._send(
                    {"status": "error", "code": "401", "msg": "未认证", "data": []}
                )

        def do_DELETE(self):
            if self.path.startswith(
                "/api/v1/advanced-search/search-templates/"
            ) and self.headers.get("X-Access-Token", "").startswith("tok-"):
                tpl_id = self.path.rsplit("/", 1)[-1]
                state["templates"] = [
                    t for t in state["templates"] if t["id"] != tpl_id
                ]
                self._send(
                    {
                        "status": "success",
                        "code": "200",
                        "msg": "删除模板成功",
                        "data": {},
                    }
                )
            elif self.path.startswith(
                "/api/v1/downloader/delete/"
            ) and self.headers.get("X-Access-Token", "").startswith("tok-"):
                dl_id = self.path.rsplit("/", 1)[-1]
                state["downloaders"].pop(dl_id, None)
                state["torrents"].pop(dl_id, None)
                self._send(
                    {
                        "status": "success",
                        "code": "200",
                        "msg": "删除成功",
                        "data": None,
                    }
                )
            else:
                self._send(
                    {"status": "error", "code": "401", "msg": "未认证", "data": []}
                )

    return Handler


@pytest.fixture()
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _build_mock_app())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


class TestEndToEndSnapshot:
    def test_full_batch_a_snapshot(self, runner, mock_server):
        snapshot = runner.run_snapshot(mock_server, ("C01", "C02", "C03", "C04"))
        assert snapshot["scenario_failures"] == []
        assert set(snapshot["scenarios"]) == {
            "C01_health_identity",
            "C02_openapi_contract",
            "C03_auth_lifecycle",
            "C04_user_settings",
        }

        c01 = snapshot["scenarios"]["C01_health_identity"]
        assert c01["live"]["identity"]["version"] == "1.0.6"
        assert c01["live"]["identity"]["build.gitSha"] == "a" * 40
        assert c01["ready"]["identity"]["checks.names"] == ["database", "scheduler"]

        c03 = snapshot["scenarios"]["C03_auth_lifecycle"]
        assert c03["login_wrong_password"]["code"] == "401"
        assert c03["login_initial_admin"]["must_change_password"] is True
        assert c03["user_info_after_logout"]["code"] == "401"

        c04 = snapshot["scenarios"]["C04_user_settings"]
        assert c04["change_password"]["code"] == "200"
        assert c04["login_old_password_after_change"]["code"] == "401"
        assert c04["login_new_password"]["code"] == "200"

    def test_two_identical_mocks_compare_clean(self, runner, comparer, mock_server):
        snap1 = runner.run_snapshot(mock_server, ("C01", "C03"))
        snap2 = json.loads(json.dumps(snap1))  # 同构第二制品
        ok, report = comparer.compare(snap1, {"replica": snap2}, [])
        assert ok and report["verdict"] == "PASS"

    def test_batch_b1_scenarios(self, runner, comparer, mock_server):
        """B1 四场景（C07/C08/C09/C11）端到端：模板全生命周期/定时任务名集合/
        通知审计形状/SPA index+fallback。"""
        snapshot = runner.run_snapshot(mock_server, ("C07", "C08", "C09", "C11"))
        assert snapshot["scenario_failures"] == []

        c07 = snapshot["scenarios"]["C07_query_templates"]
        assert c07["create_template"]["code"] == "200"
        assert c07["update_template"]["code"] == "200"
        assert c07["delete_template"]["code"] == "200"
        assert c07["list_templates"]["names"] == ["w4-contract-fixture"]
        assert c07["list_after_delete"]["names"] == []

        c08 = snapshot["scenarios"]["C08_cron_tasks"]
        assert c08["task_count"] == 2
        assert c08["task_names"] == ["Tracker 状态同步任务", "种子信息同步任务"]

        c09 = snapshot["scenarios"]["C09_notifications_audit"]
        assert c09["notifications"]["code"] == "200"
        assert c09["audit_operation_types"]["data_shape"] == ["[]"]

        c11 = snapshot["scenarios"]["C11_spa"]
        assert c11["index"]["is_html"] is True
        assert "/assets/app.js" in c11["index"]["assets"]
        assert c11["fallback"]["is_html"] is True

    def test_unreachable_instance_reports_scenario_error(self, runner):
        """实例不可达必须显式报 __scenario_error__（不可达≠无 token，诊断语义）。"""
        snapshot = runner.run_snapshot("http://127.0.0.1:1", ("C07",), timeout=1)
        assert snapshot["scenario_failures"], "不可达必须记录 scenario failure"
        assert "__scenario_error__" in snapshot["scenarios"]["C07_query_templates"]

    def test_mutation_detected(self, runner, comparer, mock_server):
        """变异：第二个制品 version 不同 → 快照比较必须报红（G8 退出门）。"""
        server2 = ThreadingHTTPServer(
            ("127.0.0.1", 0), _build_mock_app({"live_version": "9.9.9"})
        )
        threading.Thread(target=server2.serve_forever, daemon=True).start()
        try:
            base = runner.run_snapshot(
                f"http://127.0.0.1:{mock_server.rsplit(':', 1)[1]}", ("C01",)
            )
            mutated = runner.run_snapshot(
                f"http://127.0.0.1:{server2.server_port}", ("C01",)
            )
            ok, report = comparer.compare(base, {"mutated": mutated}, [])
            assert not ok
            unexplained = report["candidates"]["mutated"]["unexplained"]
            assert any(d["path"].endswith("live.identity.version") for d in unexplained)
        finally:
            server2.shutdown()


class TestBatchB2Scenarios:
    """B2 四场景（C05/C06/C12 同调用；C10 重启后独立调用）端到端 + fail-closed。"""

    def test_batch_b2_scenarios(self, runner, mock_server):
        snapshot = runner.run_snapshot(mock_server, ("C05", "C06", "C12"))
        assert snapshot["scenario_failures"] == []

        c05 = snapshot["scenarios"]["C05_downloader_crud"]
        assert c05["add_downloader"]["code"] == "200"
        assert c05["test_connection"]["success"] is True
        assert c05["test_connection_unreachable"]["success"] is False
        assert c05["update_downloader"]["code"] == "200"
        assert c05["detail_downloader"]["downloader_type"] == 0
        assert c05["delete_downloader"]["code"] == "200"
        assert c05["list_after_delete"]["c05_names_remaining"] == []
        # delay 数值（实测毫秒）不得进入快照
        assert "delay" not in c05["test_connection"]

        c06 = snapshot["scenarios"]["C06_torrent_queries"]
        assert c06["sync_qb"]["synced_count"] == 1
        assert c06["sync_tr"]["synced_count"] == 2
        assert c06["qb_torrents"]["total"] == 3
        assert [r["name"] for r in c06["qb_torrents"]["rows"]] == [
            "w4-fixture-alpha",
            "w4-fixture-beta",
            "w4-fixture-gamma",
        ]
        alpha = c06["qb_torrents"]["rows"][0]
        assert alpha["status"] == "seeding"
        assert alpha["size"] == 123456789
        assert alpha["ratio"] == 2.5
        assert c06["qb_pagination_p1"]["total"] == 3
        assert len(c06["qb_pagination_p1"]["rows"]) == 1
        assert len(c06["qb_pagination_p2"]["rows"]) == 2
        assert c06["qb_filter_status"]["status"] == "seeding"
        assert [r["name"] for r in c06["qb_filter_status"]["result"]["rows"]] == [
            "w4-fixture-alpha"
        ]
        assert c06["qb_filter_name"]["total"] == 1
        assert c06["tracker_domains"]["domains"] == [
            "tracker.w4.example",
            "tracker2.w4.example",
        ]
        assert c06["qb_single_torrent"]["row"]["name"] == "w4-fixture-alpha"
        assert c06["tr_torrents"]["total"] == 2
        assert c06["tr_torrents"]["rows"][0]["tags"] == "w4,alpha"

        c12 = snapshot["scenarios"]["C12_path_mapping"]
        assert c12["add_valid"]["code"] == "200"
        # 实测契约：重复 internal 的 add 同样 200（服务端不拒绝，真实实例取证）
        assert c12["add_conflict_internal"]["code"] == "200"
        assert c12["test_mapping"]["valid"] is False
        assert c12["test_mapping"]["backend_validation"]["structure_valid"] is True
        assert c12["remove"]["w4map"]["code"] == "200"
        assert c12["remove"]["w4map2"]["code"] == "200"
        assert c12["get_after_remove"]["config"]["mappings"] == []

    def test_c10_restart_persistence(self, runner):
        """C10：重启后契约密码可登录 + C06 数据可见 + 身份不变（预置终态）。"""
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_mock_app({"password": "W4-Contract-Pass-2026", "preseed_c06": True}),
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            snapshot = runner.run_snapshot(
                f"http://127.0.0.1:{server.server_port}", ("C10",)
            )
            assert snapshot["scenario_failures"] == []
            c10 = snapshot["scenarios"]["C10_restart_persistence"]
            assert c10["login_contract_password"]["code"] == "200"
            assert c10["identity_after_restart"]["identity"]["build.gitSha"] == "a" * 40
            assert c10["downloaders_after_restart"]["c06_names"] == [
                "w4-c06-qb",
                "w4-c06-tr",
            ]
            assert c10["torrents_after_restart_qb"]["total"] == 3
            assert c10["torrents_after_restart_tr"]["total"] == 2
        finally:
            server.shutdown()

    def test_c10_fails_closed_when_password_reset(self, runner):
        """三制品"一致地丢密码"必须显式失败，不能靠快照相等蒙混（§12.2）。"""
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_mock_app({"password": "reset-somewhere", "preseed_c06": True}),
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            snapshot = runner.run_snapshot(
                f"http://127.0.0.1:{server.server_port}", ("C10",)
            )
            assert snapshot["scenario_failures"], "密码丢失必须产生 scenario failure"
            assert any("契约密码" in f for f in snapshot["scenario_failures"])
        finally:
            server.shutdown()

    def test_c06_sync_failure_fails_closed(self, runner):
        """stub 不可达/同步失败（synced_count=0）必须显式失败而非空快照。"""
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), _build_mock_app({"sync_zero": True})
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            snapshot = runner.run_snapshot(
                f"http://127.0.0.1:{server.server_port}", ("C06",)
            )
            assert snapshot["scenario_failures"], "同步失败必须产生 scenario failure"
            assert any("synced_count" in f for f in snapshot["scenario_failures"])
        finally:
            server.shutdown()

    def test_b2_mutation_detected_in_torrent_status(
        self, runner, comparer, mock_server
    ):
        """变异：第二个制品 alpha 状态字段不同 → compare 必须报红。"""
        server2 = ThreadingHTTPServer(
            ("127.0.0.1", 0), _build_mock_app({"torrent_status": "seedingX"})
        )
        threading.Thread(target=server2.serve_forever, daemon=True).start()
        try:
            base = runner.run_snapshot(mock_server, ("C05", "C06"))
            mutated = runner.run_snapshot(
                f"http://127.0.0.1:{server2.server_port}", ("C05", "C06")
            )
            ok, report = comparer.compare(base, {"mutated": mutated}, [])
            assert not ok
            unexplained = report["candidates"]["mutated"]["unexplained"]
            assert any("status" in d["path"] for d in unexplained)
        finally:
            server2.shutdown()

    def test_merge_into_combines_phases(self, runner, mock_server, tmp_path):
        """--merge-into：重启前 FULL 快照 + 重启后 C10 并入同一文件。"""
        server10 = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            _build_mock_app({"password": "W4-Contract-Pass-2026", "preseed_c06": True}),
        )
        threading.Thread(target=server10.serve_forever, daemon=True).start()
        try:
            merged = tmp_path / "snapshot-merged.json"
            rc1 = runner.main(
                [
                    "--base-url",
                    mock_server,
                    "--scenarios",
                    "C01,C03",
                    "--output",
                    str(merged),
                ]
            )
            assert rc1 == 0
            url10 = f"http://127.0.0.1:{server10.server_port}"
            rc2 = runner.main(
                [
                    "--base-url",
                    url10,
                    "--scenarios",
                    "C10",
                    "--output",
                    str(tmp_path / "c10-only.json"),
                    "--merge-into",
                    str(merged),
                ]
            )
            assert rc2 == 0
            payload = json.loads(merged.read_text(encoding="utf-8"))
            assert "C01_health_identity" in payload["scenarios"]
            assert "C10_restart_persistence" in payload["scenarios"]
            assert payload["scenario_failures"] == []
        finally:
            server10.shutdown()

    def _rule(self, path="scenarios.C01.v", **kw):
        base = {"path": path, "reason": "示例平台差异原因说明", "expires": "2099-01-01"}
        base.update(kw)
        return base

    def test_precise_exception_explains_diff(self, comparer):
        base = {"scenarios": {"C01": {"v": "1"}}}
        cand = {"scenarios": {"C01": {"v": "2"}}}
        ok, report = comparer.compare(base, {"x": cand}, [self._rule()])
        assert ok and report["candidates"]["x"]["explained"] == 1

    def test_wildcard_root_rejected(self, comparer, tmp_path):
        p = tmp_path / "exc.json"
        p.write_text(
            json.dumps({"allowed_differences": [self._rule(path="*")]}),
            encoding="utf-8",
        )
        _, problems = comparer.load_exceptions(p)
        assert any("宽泛" in x or "非法" in x for x in problems)

    def test_trailing_swallow_rejected(self, comparer, tmp_path):
        p = tmp_path / "exc.json"
        p.write_text(
            json.dumps({"allowed_differences": [self._rule(path="scenarios.*")]}),
            encoding="utf-8",
        )
        _, problems = comparer.load_exceptions(p)
        assert problems, "尾部吞段规则必须被拒绝"

    def test_expired_rule_rejected(self, comparer, tmp_path):
        p = tmp_path / "exc.json"
        p.write_text(
            json.dumps({"allowed_differences": [self._rule(expires="2020-01-01")]}),
            encoding="utf-8",
        )
        _, problems = comparer.load_exceptions(p)
        assert any("过期" in x for x in problems)

    def test_stale_rule_reported(self, comparer):
        base = {"a": 1}
        ok, report = comparer.compare(
            base, {"x": dict(base)}, [self._rule(path="never.hit.path")]
        )
        assert ok  # 无差异仍通过
        assert len(report["stale_rules"]) == 1

    def test_repo_exceptions_file_valid(self, comparer):
        rules, problems = comparer.load_exceptions(
            _REPO_ROOT / "release" / "equivalence-exceptions.json"
        )
        assert problems == []
        assert rules == []
