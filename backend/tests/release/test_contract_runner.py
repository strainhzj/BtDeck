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


def _build_mock_app(mutations: Dict[str, Any] | None = None):
    """构造带固定状态的 mock BtDeck API handler 类。

    mutations: {"live_version": "9.9.9"} 等注入点，用于变异测试。
    状态：admin/admin（must_change_password=true）→ C04 改密到契约密码。
    """
    state: Dict[str, Any] = {
        "password": "admin",
        "must_change": True,
        "revoked": set(),
        "seq": 0,
    }
    mut = mutations or {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 静默
            return

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
            elif self.path == "/openapi.json":
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
            else:
                self._send({"status": "error", "code": "404", "msg": "nf"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
            token = self.headers.get("X-Access-Token", "")
            path = self.path

            def ok(data):
                return {"status": "success", "code": "200", "msg": "ok", "data": [data]}

            def err(code, msg):
                return {"status": "error", "code": code, "msg": msg, "data": []}

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
                else:
                    self._send(err("404", "nf"), 404)
            else:
                self._send(err("401", "未认证"))

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


class TestCompareRules:
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
