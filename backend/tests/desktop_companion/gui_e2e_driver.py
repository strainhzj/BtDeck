# -*- coding: utf-8 -*-
"""桌面伴侣 GUI E2E 驱动（由 test_launcher_gui_e2e.py 以子进程启动，BTDECK_GUI_E2E=1 时生效）。

覆盖 task .8 桌面 GUI 验收面：真实 pywebview/WebView2 窗口中的——
1. 管理页表单保存带凭据的服务器（DOM 填写 + addServer() 按钮链路）；
2. 打开远程窗口 → 自动登录脚本注入（fake 服务器收到正确凭据登录 + 成功 reload）；
3. 关闭远程窗口回管理页；
4. 改密（update_server 新密码）后重新登录成功；
5. 失败登录（错误密码）只产生一次尝试、不触发 reload；
6. 切换到无凭据 profile B（另一服务器）不携带 A 的登录。

结果以 JSON 落盘（steps + 服务器请求日志），pytest 侧断言。
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.desktop_companion.credentials import WindowsCredentialVault  # noqa: E402
from app.desktop_companion.health import HealthClient  # noqa: E402
from app.desktop_companion.launcher import DesktopLauncher  # noqa: E402
from app.desktop_companion.profiles import ServerProfileStore  # noqa: E402


class FakeServerState:
    def __init__(self, name: str, correct_username: str, correct_password: str) -> None:
        self.name = name
        self.correct_username = correct_username
        self.correct_password = correct_password
        self.requests: list[dict] = []
        self.lock = threading.Lock()

    def record(self, method: str, path: str, body: str | None) -> None:
        with self.lock:
            self.requests.append({"method": method, "path": path, "body": body})

    def count(self, method: str, path: str) -> int:
        with self.lock:
            return sum(1 for r in self.requests if r["method"] == method and r["path"] == path)

    def login_bodies(self) -> list[str]:
        with self.lock:
            return [r["body"] or "" for r in self.requests if r["path"] == "/api/v1/auth/login"]


def build_handler(state: FakeServerState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # 静默访问日志
            return

        def _respond(self, payload: str, content_type: str) -> None:
            data = payload.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            state.record("GET", self.path, None)
            if self.path == "/health/live":
                self._respond('{"code":"200","status":"success","data":{"status":"alive"}}', "application/json")
            elif self.path == "/health/ready":
                self._respond(
                    '{"code":"200","status":"success","data":{"status":"ready","version":"9.9.9-gui"}}',
                    "application/json",
                )
            else:
                self._respond(
                    "<!doctype html><html><body>DESKTOP SERVER " + state.name + "</body></html>",
                    "text/html; charset=utf-8",
                )

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8") if length else ""
            state.record("POST", self.path, body)
            if self.path == "/api/v1/auth/login":
                try:
                    payload = json.loads(body)
                except ValueError:
                    payload = {}
                if (
                    payload.get("username") == state.correct_username
                    and payload.get("password") == state.correct_password
                ):
                    self._respond(
                        '{"code":"200","status":"success","msg":"登录成功","data":[{"access_token":"tok","refresh_token":"ref"}]}',
                        "application/json",
                    )
                else:
                    self._respond('{"code":"400","status":"error","msg":"用户名或密码错误"}', "application/json")
            else:
                self._respond('{"code":"404"}', "application/json")

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    result_path = Path(args.result)

    state_a = FakeServerState("A", "admin", "secret-A")
    state_b = FakeServerState("B", "admin-b", "secret-B")
    server_a = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state_a))
    server_b = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(state_b))
    for srv in (server_a, server_b):
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    steps: list[dict] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        steps.append({"name": name, "ok": ok, "detail": detail})
        print(f"[gui-e2e] {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)

    def wait_for(condition, timeout: float, interval: float = 0.25):
        """轮询直到条件返回真值；返回该真值（条件为 bool 时即 True），超时返回 falsy。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = condition()
                if value:
                    return value
            except Exception:  # noqa: BLE001 - 轮询条件里的瞬态异常按未满足处理
                pass
            time.sleep(interval)
        try:
            return condition()
        except Exception:  # noqa: BLE001
            return None

    launcher = DesktopLauncher(
        store=ServerProfileStore(work / "companion_servers.json"),
        health=HealthClient(),
        mode_path=work / "desktop_mode.json",
        credentials=WindowsCredentialVault(work),
    )
    # 预置 companion 模式：launch() 直接进管理页（跳过向导，聚焦 .8 验收面）
    (work / "desktop_mode.json").write_text(json.dumps({"mode": "companion"}), encoding="utf-8")

    def flow() -> None:  # webview UI 就绪后的驱动线程
        import webview

        try:
            manager = wait_for(lambda: webview.windows[0] if webview.windows else None, 30)
            if not manager:
                step("manager-window", False, "管理页窗口未创建")
                return
            bridge_ready = wait_for(
                lambda: manager.evaluate_js("typeof pywebview !== 'undefined' && pywebview.api ? 'ready' : 'pending'")
                == "ready",
                30,
            )
            step("manager-bridge", bridge_ready, "pywebview.api 桥就绪")

            # ---- 1. 表单保存带凭据的服务器 A ----
            url_a = f"http://127.0.0.1:{server_a.server_port}"
            manager.evaluate_js(
                "document.getElementById('name').value='桌面服务器A';"
                f"document.getElementById('url').value='{url_a}';"
                "document.getElementById('username').value='admin';"
                "document.getElementById('password').value='secret-A';"
                "addServer();"
            )
            added = wait_for(
                lambda: manager.evaluate_js("document.getElementById('add-msg').textContent") == "已添加", 10
            )
            profiles = launcher.store.load_all()
            profile_a = next((p for p in profiles if p.display_name == "桌面服务器A"), None)
            vault_has = bool(profile_a and launcher.credentials.has(profile_a.id))
            stored_json = (work / "companion_servers.json").read_text(encoding="utf-8")
            no_plaintext = "secret-A" not in stored_json
            step(
                "add-with-credentials",
                added and profile_a is not None and vault_has and no_plaintext,
                f"表单已添加={added} vault={vault_has} 明文不入profile={no_plaintext}",
            )

            # ---- 2. 打开远程窗口 → 自动登录 ----
            manager.evaluate_js(f"pywebview.api.open_server('{profile_a.id}')")
            logged_in = wait_for(
                lambda: state_a.count("POST", "/api/v1/auth/login") >= 1
                and any('"admin"' in b and '"secret-A"' in b for b in state_a.login_bodies()),
                30,
            )
            reloaded = wait_for(lambda: state_a.count("GET", "/") >= 2, 20)
            step("remote-autologin", logged_in and reloaded, f"登录POST={logged_in} 成功reload={reloaded}")

            # ---- 3. 关闭远程窗口回管理页 ----
            remote_closed = wait_for(lambda: len(webview.windows) >= 2, 15)
            if remote_closed:
                webview.windows[-1].destroy()
            back_to_manager = wait_for(lambda: len(webview.windows) == 1, 15)
            step("remote-close-back-to-manager", bool(remote_closed and back_to_manager))

            # ---- 4. 改密后重新登录成功 ----
            api = launcher._manager_api  # noqa: SLF001 - 驱动即等价于编辑对话框提交链路
            api.update_server(profile_a.id, "桌面服务器A", url_a, False, "admin", "new-secret-A", False)
            manager.evaluate_js(f"pywebview.api.open_server('{profile_a.id}')")
            relogin = wait_for(lambda: any('"new-secret-A"' in b for b in state_a.login_bodies()), 30)
            step("password-change-relogin", relogin)
            if wait_for(lambda: len(webview.windows) >= 2, 15):
                webview.windows[-1].destroy()
                wait_for(lambda: len(webview.windows) == 1, 15)

            # ---- 5. 失败登录：全新服务器 B + 错误密码（无既有会话，确定性触发）----
            url_b = f"http://127.0.0.1:{server_b.server_port}"
            api.add_server("服务器B", url_b, False, "admin-b", "wrong-for-B")
            profile_b = next((p for p in launcher.store.load_all() if p.display_name == "服务器B"), None)
            manager.evaluate_js(f"pywebview.api.open_server('{profile_b.id}')")
            failed_attempt = wait_for(
                lambda: any('"wrong-for-B"' in b for b in state_b.login_bodies()),
                30,
            )
            time.sleep(4)  # 留足失败后的静默窗口
            b_no_reload = state_b.count("GET", "/") <= 1
            step(
                "failed-login-no-reload",
                failed_attempt and b_no_reload,
                f"错误凭据尝试={failed_attempt} 不触发reload={b_no_reload}",
            )
            if wait_for(lambda: len(webview.windows) >= 2, 15):
                webview.windows[-1].destroy()
                wait_for(lambda: len(webview.windows) == 1, 15)

            # ---- 6. 切换无凭据 profile B：不携带任何登录 ----
            api.update_server(profile_b.id, "服务器B", url_b, False, "", "")
            logins_b_before = len(state_b.login_bodies())
            manager.evaluate_js(f"pywebview.api.open_server('{profile_b.id}')")
            b_loaded = wait_for(lambda: state_b.count("GET", "/") >= 2, 30)
            time.sleep(3)
            b_no_login = len(state_b.login_bodies()) == logins_b_before
            step(
                "switch-profile-no-cross-credentials",
                b_loaded and b_no_login,
                f"B页面再次加载={b_loaded} B零新增登录={b_no_login}",
            )
        except Exception as exc:  # noqa: BLE001 - 任一步异常都要落结果文件
            step("driver-exception", False, repr(exc))
        finally:
            try:
                import webview

                # 远程窗口（B 等）不关会让 webview.start() 永不返回
                for window in list(webview.windows):
                    try:
                        window.destroy()
                    except Exception:  # noqa: BLE001
                        pass
                launcher.exit_companion()
            except Exception as exc:  # noqa: BLE001
                print(f"[gui-e2e] exit error: {exc!r}", flush=True)
            result_path.write_text(
                json.dumps(
                    {
                        "steps": steps,
                        "server_a": state_a.requests,
                        "server_b": state_b.requests,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

    threading.Thread(target=flow, daemon=True).start()
    launcher.launch()
    # launch() 返回（全部窗口关闭）后给结果文件一个落盘窗口
    deadline = time.monotonic() + 10
    while not result_path.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    server_a.shutdown()
    server_b.shutdown()
    all_ok = bool(result_path.exists()) and all(s["ok"] for s in steps) and steps
    print(f"[gui-e2e] driver exit ok={all_ok}", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
