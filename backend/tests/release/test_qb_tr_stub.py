"""W4 B2 受控下载器 stub 回归（release-artifact-equivalence-gate task .8 / G8）。

协议保真由真实客户端库背书：qbittorrentapi / transmission_rpc（后端 venv
已安装的同一组依赖）打进程内 stub，验证登录、版本探针、种子/tracker 拉取、
409 握手与鉴权失败路径——stub 应答面即制品在 C05/C06 里实际依赖的调用面。

mutate-proxy（G8 变异演练 M2）：反代上游并改写命中路由的单个 JSON 字段。
"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STUB_PATH = _REPO_ROOT / "scripts" / "release" / "fixtures" / "qb_tr_stub.py"
_RUNNER_PATH = _REPO_ROOT / "scripts" / "release" / "contract_runner.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def stub():
    return _load_module(_STUB_PATH, "btdeck_qb_tr_stub")


def _serve(stub, role: str, **kw):
    server = ThreadingHTTPServer(("127.0.0.1", 0), stub.HANDLERS[role])
    if role == "mutate-proxy":
        handler_cls = stub.HANDLERS[role]
        handler_cls.upstream = kw.get("upstream", "")
        handler_cls.mutate_route = kw.get("mutate_route", "")
        handler_cls.mutate_field = kw.get("mutate_field", "")
        handler_cls.mutate_value = kw.get("mutate_value", "")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture()
def qb_server(stub):
    server = _serve(stub, "qb")
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture()
def tr_server(stub):
    server = _serve(stub, "tr")
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


class TestQbProtocolFidelity:
    def test_login_and_version_probe(self, qb_server):
        """_check_qbittorrent_auth_with_retry 的调用面：app_version 必须成功。"""
        from qbittorrentapi import Client

        client = Client(
            host=qb_server,
            username="w4stub-user",
            password="w4stub-pass",
            REQUESTS_ARGS={"timeout": 5},
            FORCE_SCHEME_FROM_HOST=True,
            HTTPADAPTER_ARGS={"max_retries": 0},
        )
        # qbittorrentapi 2025.2.0：app_version 是方法（后端按真值探测，此处按调用断言）
        assert client.app_version() == "v4.6.7"

    def test_wrong_password_rejected(self, qb_server):
        """错密码 → 403 Fails.；调用点触发登录时 qbittorrentapi 抛
        Forbidden403Error（LoginFailed 仅部分路径），两者都算拒识成功。"""
        from qbittorrentapi import Client, Forbidden403Error, LoginFailed

        client = Client(
            host=qb_server,
            username="w4stub-user",
            password="definitely-wrong",
            REQUESTS_ARGS={"timeout": 5},
            FORCE_SCHEME_FROM_HOST=True,
            HTTPADAPTER_ARGS={"max_retries": 0},
        )
        with pytest.raises((LoginFailed, Forbidden403Error)):
            client.app_version()

    def test_torrents_info_fixed_dataset(self, qb_server):
        from qbittorrentapi import Client

        client = Client(
            host=qb_server,
            username="w4stub-user",
            password="w4stub-pass",
            REQUESTS_ARGS={"timeout": 5},
            FORCE_SCHEME_FROM_HOST=True,
            HTTPADAPTER_ARGS={"max_retries": 0},
        )
        torrents = client.torrents_info()
        assert sorted(t.name for t in torrents) == [
            "w4-fixture-alpha",
            "w4-fixture-beta",
            "w4-fixture-gamma",
        ]
        alpha = next(t for t in torrents if t.name == "w4-fixture-alpha")
        assert alpha.hash == "1" * 40
        assert alpha.state == "uploading"
        assert alpha.total_size == 123456789
        assert alpha.save_path == "/downloads/w4-complete/"
        assert alpha.tags == "w4,alpha"
        assert alpha.ratio == 2.5

    def test_trackers_lazy_load_per_hash(self, qb_server):
        """torrent_sync.sync_add_tracker 的调用面：TorrentDictionary.trackers 懒加载。"""
        from qbittorrentapi import Client

        client = Client(
            host=qb_server,
            username="w4stub-user",
            password="w4stub-pass",
            REQUESTS_ARGS={"timeout": 5},
            FORCE_SCHEME_FROM_HOST=True,
            HTTPADAPTER_ARGS={"max_retries": 0},
        )
        alpha = next(t for t in client.torrents_info() if t.name == "w4-fixture-alpha")
        trackers = alpha.trackers
        if callable(trackers):
            trackers = trackers()
        urls = [t["url"] for t in trackers]
        assert urls == [
            "http://tracker.w4.example:8080/announce",
            "http://tracker2.w4.example:8080/announce",
        ]

    def test_transfer_info_hot_polling(self, qb_server):
        """downloader_status_polling_task 的调用面：transfer_info 全零确定值。"""
        from qbittorrentapi import Client

        client = Client(
            host=qb_server,
            username="w4stub-user",
            password="w4stub-pass",
            REQUESTS_ARGS={"timeout": 5},
            FORCE_SCHEME_FROM_HOST=True,
            HTTPADAPTER_ARGS={"max_retries": 0},
        )
        info = client.transfer_info()
        assert info["up_info_speed"] == 0
        assert info["dl_info_speed"] == 0

    def test_sid_enforcement_fail_closed(self, qb_server):
        """无 SID Cookie 直打 API 面 → 403（fail-closed，真实 qB 语义）。"""
        req = urllib.request.Request(qb_server + "/api/v2/torrents/info")
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(req, timeout=5)
        assert excinfo.value.code == 403


class TestTrProtocolFidelity:
    def _client(self, tr_server):
        from transmission_rpc import Client

        return Client(
            host="127.0.0.1",
            port=int(tr_server.rsplit(":", 1)[1]),
            username="w4stub-user",
            password="w4stub-pass",
            timeout=5.0,
        )

    def test_handshake_and_session(self, tr_server, stub):
        """trClient 构造即完成 409 握手 + session-get（认证探针调用面）。"""
        client = self._client(tr_server)
        session = client.get_session()
        assert session.version == stub.TR_VERSION

    def test_session_stats_auth_probe(self, tr_server):
        """_check_transmission_auth_with_retry 的调用面：session_stats 成功。"""
        client = self._client(tr_server)
        stats = client.session_stats()
        assert stats.upload_speed == 0
        assert stats.download_speed == 0

    def test_get_torrents_fixed_dataset(self, tr_server):
        """tr_add_torrents 的调用面：种子字段与 trackerStats 可解析。"""
        client = self._client(tr_server)
        torrents = client.get_torrents()
        assert sorted(t.name for t in torrents) == [
            "w4-fixture-alpha",
            "w4-fixture-beta",
        ]
        alpha = next(t for t in torrents if t.name == "w4-fixture-alpha")
        assert alpha.hashString == "1" * 40
        assert alpha.total_size == 123456789
        assert alpha.download_dir == "/downloads/w4-complete/"
        assert alpha.added_date is not None
        stats = alpha.tracker_stats
        assert [s.site_name for s in stats] == [
            "tracker.w4.example",
            "tracker2.w4.example",
        ]
        assert stats[0].fields["announce"].startswith("http://tracker.w4.example")

    def test_wrong_password_rejected(self, tr_server):
        """错密码 → 401；trClient 构造即发 session-get，异常在构造点抛出。"""
        from transmission_rpc import Client, TransmissionAuthError

        with pytest.raises(TransmissionAuthError):
            Client(
                host="127.0.0.1",
                port=int(tr_server.rsplit(":", 1)[1]),
                username="w4stub-user",
                password="definitely-wrong",
                timeout=5.0,
            )

    def test_409_handshake_raw(self, tr_server, stub):
        """无 session-id 头 → 409 + 固定 X-Transmission-Session-Id。"""
        req = urllib.request.Request(
            tr_server + "/transmission/rpc",
            data=json.dumps({"method": "session-get", "arguments": {}}).encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        import base64

        req.add_header(
            "Authorization",
            "Basic " + base64.b64encode(b"w4stub-user:w4stub-pass").decode(),
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(req, timeout=5)
        assert excinfo.value.code == 409
        assert excinfo.value.headers["X-Transmission-Session-Id"] == stub.TR_SESSION_ID


class TestMutateProxy:
    def test_rewrites_target_field_only(self, stub):
        """M2：命中路由的指定字段被改写，未命中路由透传。"""
        from http.server import BaseHTTPRequestHandler

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def _reply(self, payload):
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/health/live":
                    self._reply(
                        {
                            "status": "success",
                            "code": "200",
                            "msg": "ok",
                            "data": {"build": {"version": "1.0.6", "gitSha": "a" * 40}},
                        }
                    )
                else:
                    self._reply({"status": "success", "code": "200", "data": {"x": 1}})

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        proxy = _serve(
            stub,
            "mutate-proxy",
            upstream=f"http://127.0.0.1:{upstream.server_port}",
            mutate_route="/health/live",
            mutate_field="data.build.version",
            mutate_value="1.0.6-mutated",
        )
        try:
            base = f"http://127.0.0.1:{proxy.server_port}"
            with urllib.request.urlopen(base + "/health/live", timeout=5) as resp:
                mutated = json.loads(resp.read())
            assert mutated["data"]["build"]["version"] == "1.0.6-mutated"
            assert mutated["data"]["build"]["gitSha"] == "a" * 40
            with urllib.request.urlopen(base + "/other", timeout=5) as resp:
                untouched = json.loads(resp.read())
            assert untouched == {"status": "success", "code": "200", "data": {"x": 1}}
        finally:
            proxy.shutdown()
            upstream.shutdown()


class TestStubRunnerContractMirror:
    def test_credentials_mirror_between_runner_and_stub(self, stub):
        """runner 以单文件 docker cp 进容器无法 import stub——凭据镜像必须同步。"""
        runner = _load_module(_RUNNER_PATH, "btdeck_contract_runner_mirror")
        assert runner.STUB_USERNAME == stub.STUB_USERNAME
        assert runner.STUB_PASSWORD == stub.STUB_PASSWORD

    def test_stub_never_imports_app(self, stub):
        src = _STUB_PATH.read_text(encoding="utf-8")
        import re

        imports = re.findall(r"^\s*(?:from|import)\s+(app[\w.]*)", src, re.M)
        assert not imports, f"stub 禁止 import app.*（实测: {imports}）"
