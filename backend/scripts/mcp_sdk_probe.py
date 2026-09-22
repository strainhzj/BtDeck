"""MCP SDK 兼容性探针（W0 交付物，feature mcp-service-capabilities-2026-08-28 §10.2-3）。

目的：在仓库锁定组合（fastapi 0.115.6 + starlette 0.41.3，见 backend/requirements.txt）
下实证候选 MCP SDK 的四项关键兼容性，产出可追溯证据 JSON 与选型结论：

  C1 import      —— SDK 及其依赖在目标 Python 下可导入（版本矩阵 3.11/3.12+）；
  C2 mount       —— SDK 的 ASGI 应用可挂载进 FastAPI 子路径，且挂载顺序先于 SPA catch-all；
  C3 lifespan    —— 父应用 lifespan 与 MCP 子应用会话管理共存（各自恰好启动一次，
                    工具可读取父应用 lifespan 写入的共享上下文——W2 RuntimeContext 注入前提）；
  C4 protocol    —— 经真实 HTTP（uvicorn 线程）完成 initialize → tools/list → tools/call
                    JSON-RPC 握手（兼容 JSON 与 SSE 两种响应形态）；
  C5 pyinstaller —— （可选 --pyinstaller）onefile 冻结包内完成 C2/C3/C4 的进程内等价检查。

用法：

  # 隔离 venv：按仓库锁定 + 候选 SDK 安装后自动重入 selfcheck
  python mcp_sdk_probe.py run --python <exe> --sdk fastmcp==2.14.3 \
      --workdir <dir> [--pyinstaller] [--evidence-out <json>]

  # 当前解释器就地检查（不建 venv；供 pytest 与快速复验，版本如实记录）
  python mcp_sdk_probe.py selfcheck --sdk fastmcp --json

选型结论不写在脚本内，随证据回填 PLANS/mcp-service-capabilities.md §10.4。
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 仓库锁定组合（backend/requirements.txt）；fastmcp 需 httpx>=0.28.1，取 0.28.x 最新锁定。
# packaging 是仓库已锁定依赖（~=24.0），也是 fastmcp 2.14.3 的未声明运行时依赖
# （py3.12 venv 实测缺它即 ModuleNotFoundError），探针必须如实入锁。
REPO_PINNED_DEPS: Tuple[str, ...] = (
    "fastapi==0.115.6",
    "starlette==0.41.3",
    "pydantic==2.12.4",
    "httpx==0.28.1",
    "uvicorn==0.35.0",
    "packaging==24.2",
)

SUPPORTED_SDK_FLAVORS = ("fastmcp", "mcp")

MCP_PROTOCOL_VERSION = "2025-06-18"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# selfcheck：在当前解释器内构建挂载应用并做完整协议握手（被 run 模式在 venv 内重入）
# ==============================================================================


def _collect_versions(sdk_flavor: str) -> Dict[str, str]:
    from importlib.metadata import version as pkg_version

    versions = {
        "python": sys.version.split()[0],
        "fastapi": pkg_version("fastapi"),
        "starlette": pkg_version("starlette"),
        "pydantic": pkg_version("pydantic"),
        "httpx": pkg_version("httpx"),
        "uvicorn": pkg_version("uvicorn"),
        sdk_flavor: pkg_version(sdk_flavor),
    }
    if sdk_flavor != "mcp":
        try:
            versions["mcp"] = pkg_version("mcp")
        except Exception:  # noqa: BLE001 - 探针只记录事实
            versions["mcp"] = "not-installed"
    return versions


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _ProbeError(RuntimeError):
    """检查失败（message 进入证据，禁止携带任何敏感信息——探针环境无真实数据）。"""


def _build_app_fastmcp() -> Tuple[Any, Dict[str, Any]]:
    """fastmcp 2.x：FastMCP.http_app() 挂载进 FastAPI。

    ``http_app()`` 返回 ``StarletteWithLifespan``（fastmcp/server/http.py），携带
    streamable HTTP 会话管理的 lifespan；Starlette 挂载不会自动运行子应用
    lifespan，父应用 lifespan 必须手动进入 ``sub_asgi.lifespan(sub_asgi)``
    （fastmcp 2.14.3 实测无 FastMCPManager，此为官方文档指定机制）——C3 实证点。
    共享上下文经模块级 MARKER 模拟 W2 RuntimeContext 注入。
    """
    from fastapi import FastAPI
    from fastmcp import FastMCP

    marker: Dict[str, Any] = {"lifespan_runs": 0, "value": None}

    mcp = FastMCP("btdeck-probe")

    @mcp.tool
    def echo(value: int) -> Dict[str, Any]:
        """回显工具：返回 value+1 与父应用 lifespan 写入的共享标记。"""
        return {"value": value + 1, "lifespan_marker": marker["value"]}

    sub_asgi = mcp.http_app(path="/", stateless_http=True)

    async def root_lifespan(app: Any) -> Any:
        marker["lifespan_runs"] += 1
        marker["value"] = "parent-context-ok"
        async with sub_asgi.lifespan(sub_asgi):
            yield

    root = FastAPI(lifespan=root_lifespan)
    root.mount("/mcp", sub_asgi)

    # SPA catch-all 兜底路由：挂载必须先于它（G0 挂载顺序约束）
    @root.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> Dict[str, str]:
        return {"fallback": full_path}

    return root, marker


def _build_app_mcp() -> Tuple[Any, Dict[str, Any]]:
    """官方 mcp SDK：lowlevel Server + StreamableHTTPSessionManager（stateless）。

    会话管理器需在运行中的事件循环内 start；由父应用 lifespan 进入
    session_manager.run()。官方 SDK 无高层挂载封装，全部接线显式——W2 若选官方
    SDK，这些接线即 runtime.py 的实现量基线。
    """
    from fastapi import FastAPI
    from starlette.applications import Starlette
    from starlette.routing import Mount

    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    marker: Dict[str, Any] = {"lifespan_runs": 0, "value": None}

    server = Server("btdeck-probe")

    @server.list_tools()
    async def list_tools() -> List[types.Tool]:
        return [
            types.Tool(
                name="echo",
                description="回显工具：返回 value+1 与父应用 lifespan 写入的共享标记。",
                inputSchema={
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.Content]:
        if name != "echo":
            raise _ProbeError(f"unexpected tool: {name}")
        result = {"value": int(arguments["value"]) + 1, "lifespan_marker": marker["value"]}
        return [types.TextContent(type="text", text=json.dumps(result))]

    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=True,
        stateless=True,  # mcp 1.25.0 参数名为 stateless（fastmcp 侧为 stateless_http）
    )

    async def handle_mcp(scope: Any, receive: Any, send: Any) -> None:
        await session_manager.handle_request(scope, receive, send)

    async def sub_lifespan(app: Any) -> Any:
        async with session_manager.run():
            yield

    sub_asgi = Starlette(routes=[Mount("/", app=handle_mcp)], lifespan=sub_lifespan)

    async def root_lifespan(app: Any) -> Any:
        marker["lifespan_runs"] += 1
        marker["value"] = "parent-context-ok"
        # 手动进入子应用 lifespan（FastAPI 挂载不运行子应用 lifespan）
        async with sub_asgi.router.lifespan_context(sub_asgi):
            yield

    root = FastAPI(lifespan=root_lifespan)
    root.mount("/mcp", sub_asgi)

    @root.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> Dict[str, str]:
        return {"fallback": full_path}

    return root, marker


def _parse_rpc_payload(resp: Any, request_id: int) -> Dict[str, Any]:
    """兼容 application/json 与 text/event-stream 两种 MCP 响应形态。"""
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[len("data:") :].strip())
                if isinstance(payload, dict) and payload.get("id") == request_id:
                    return payload
        raise _ProbeError(f"SSE 流中未找到 id={request_id} 的响应: {resp.text[:200]}")
    payload = resp.json()
    if not isinstance(payload, dict):
        raise _ProbeError(f"响应不是 JSON 对象: {str(payload)[:200]}")
    return payload


def _rpc_call(http: Any, url: str, method: str, params: Optional[Dict[str, Any]], request_id: int) -> Dict[str, Any]:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "id": request_id}
    if params is not None:
        body["params"] = params
    resp = http.post(url, json=body, headers={"Accept": "application/json, text/event-stream"})
    if resp.status_code != 200:
        raise _ProbeError(f"{method} HTTP {resp.status_code}: {resp.text[:200]}")
    return _parse_rpc_payload(resp, request_id)


def _protocol_sequence(http: Any, mcp_url: str) -> List[Dict[str, Any]]:
    """单个候选端点上执行 C4 握手；失败抛 _ProbeError 由候选循环接管。"""
    checks: List[Dict[str, Any]] = []
    init = _rpc_call(
        http,
        mcp_url,
        "initialize",
        {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "btdeck-probe", "version": "0"},
        },
        1,
    )
    if "error" in init:
        raise _ProbeError(f"initialize 失败: {init['error']}")
    server_name = init.get("result", {}).get("serverInfo", {}).get("name")
    http.post(
        mcp_url,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Accept": "application/json, text/event-stream"},
    )
    listing = _rpc_call(http, mcp_url, "tools/list", {}, 2)
    tools = [t.get("name") for t in listing.get("result", {}).get("tools", [])]
    checks.append(
        {
            "name": "C4_tools_list",
            "status": "PASS" if "echo" in tools else "FAIL",
            "detail": f"serverInfo={server_name}, tools={tools}",
        }
    )
    call = _rpc_call(http, mcp_url, "tools/call", {"name": "echo", "arguments": {"value": 41}}, 3)
    result = call.get("result", {})
    content = result.get("content", [])
    text = content[0].get("text", "{}") if content else "{}"
    payload = json.loads(text)
    round_trip = payload.get("value") == 42 and payload.get("lifespan_marker") == "parent-context-ok"
    checks.append(
        {
            "name": "C4_tools_call_roundtrip",
            "status": "PASS" if round_trip and not result.get("isError") else "FAIL",
            "detail": f"payload={payload}",
        }
    )
    if any(c["status"] != "PASS" for c in checks):
        raise _ProbeError(f"握手检查未全过: {checks}")
    return checks


def _run_protocol_checks(root: Any, marker: Dict[str, Any]) -> List[Dict[str, Any]]:
    """C2/C3/C4：uvicorn 线程 + 原生 httpx JSON-RPC 握手。"""
    import httpx
    import uvicorn

    checks: List[Dict[str, Any]] = []

    # C2 挂载顺序：/mcp mount 必须先于 SPA catch-all
    route_order = [getattr(r, "path", getattr(r, "path_format", "?")) for r in root.routes]
    mcp_index = next((i for i, p in enumerate(route_order) if str(p).startswith("/mcp")), None)
    fallback_index = next((i for i, p in enumerate(route_order) if str(p) == "/{full_path:path}"), None)
    ordered = mcp_index is not None and fallback_index is not None and mcp_index < fallback_index
    checks.append(
        {
            "name": "C2_mount_before_spa_fallback",
            "status": "PASS" if ordered else "FAIL",
            "detail": f"routes={route_order}",
        }
    )

    port = _free_port()
    config = uvicorn.Config(root, host="127.0.0.1", port=port, log_level="critical", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 15.0
        base_url = f"http://127.0.0.1:{port}"
        # trust_env=False：loopback 自探查绝不走系统代理（Windows 系统代理劫持
        # 127.0.0.1 的实证坑，同 Chaquopy httpx 先例）；环境代理死活不影响探针。
        with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False) as http:
            while time.monotonic() < deadline:
                try:
                    http.get("/nonexistent-health-probe")
                    break
                except httpx.TransportError:
                    time.sleep(0.1)
            else:
                raise _ProbeError("uvicorn 15s 内未就绪")

            # 候选端点：子应用路由在 "/" 时挂载点 /mcp 会 307 到 /mcp/，
            # 直接先试带斜杠形态，再试无斜杠形态，任一走通完整握手即 C4 PASS。
            failures: List[str] = []
            for candidate in (f"{base_url}/mcp/", f"{base_url}/mcp"):
                try:
                    checks += _protocol_sequence(http, candidate)
                    break
                except _ProbeError as exc:
                    failures.append(f"{candidate}: {exc}")
            else:
                checks.append({"name": "C4_handshake", "status": "FAIL", "detail": "; ".join(failures)})
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)

    # C3 父 lifespan 恰好运行一次（挂载子应用不重复触发父 lifespan）
    checks.append(
        {
            "name": "C3_parent_lifespan_runs_once",
            "status": "PASS" if marker["lifespan_runs"] == 1 else "FAIL",
            "detail": f"lifespan_runs={marker['lifespan_runs']}, marker={marker['value']!r}",
        }
    )
    return checks


def run_selfcheck(sdk_flavor: str) -> Dict[str, Any]:
    """在当前解释器执行 C1~C4；任何异常都转为 FAIL 检查项，不让探针崩溃失证。"""
    checks: List[Dict[str, Any]] = []
    try:
        versions = _collect_versions(sdk_flavor)
    except Exception as exc:  # noqa: BLE001 - 版本收集失败即 C1 失败
        return {
            "sdk": sdk_flavor,
            "generated_at": _utc_now(),
            "checks": [{"name": "C1_import", "status": "FAIL", "detail": repr(exc)}],
            "verdict": "FAIL",
        }
    checks.append({"name": "C1_import", "status": "PASS", "detail": ""})

    try:
        if sdk_flavor == "fastmcp":
            root, marker = _build_app_fastmcp()
        elif sdk_flavor == "mcp":
            root, marker = _build_app_mcp()
        else:
            raise _ProbeError(f"未知 SDK flavor: {sdk_flavor}")
        checks += _run_protocol_checks(root, marker)
    except Exception as exc:  # noqa: BLE001 - 探针必须产出结构化失败证据
        checks.append({"name": "build_or_protocol", "status": "FAIL", "detail": repr(exc)})

    verdict = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    return {"sdk": sdk_flavor, "generated_at": _utc_now(), "versions": versions, "checks": checks, "verdict": verdict}


# ==============================================================================
# run：隔离 venv 安装锁定组合后重入 selfcheck（+可选 PyInstaller onefile）
# ==============================================================================


def _venv_python(workdir: Path) -> Path:
    relative = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    candidate = workdir / "venv" / relative
    if not candidate.exists():
        raise _ProbeError(f"venv python 不存在: {candidate}")
    return candidate


def _pip_install(venv_py: Path, packages: List[str], timeout: int = 600) -> str:
    cmd = [str(venv_py), "-m", "pip", "install", "--disable-pip-version-check", *packages]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        raise _ProbeError(f"pip install 失败: {' '.join(packages)}\n{proc.stderr[-2000:]}")
    return proc.stdout[-2000:]


BUNDLE_PROBE_SOURCE = '''
"""PyInstaller onefile 冻结包内的进程内等价检查（C5）。

不依赖 uvicorn：Starlette TestClient 驱动 lifespan + JSON-RPC 请求。
stdout 只输出 BUNDLE_PROBE_OK / BUNDLE_PROBE_FAIL <detail>（父进程判据）。
"""
import json
import sys

sys.path.insert(0, r"{probe_script_dir}")
from mcp_sdk_probe import _build_app_fastmcp, _build_app_mcp  # noqa: E402


def main() -> int:
    flavor = sys.argv[1]
    try:
        from starlette.testclient import TestClient

        if flavor == "fastmcp":
            root, _marker = _build_app_fastmcp()
        else:
            root, _marker = _build_app_mcp()
        with TestClient(root) as client:
            init = client.post(
                "/mcp/",
                json={{
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {{
                        "protocolVersion": "{protocol_version}",
                        "capabilities": {{}},
                        "clientInfo": {{"name": "bundle-probe", "version": "0"}},
                    }},
                }},
                headers={{"Accept": "application/json, text/event-stream"}},
            )
            if init.status_code != 200:
                print(f"BUNDLE_PROBE_FAIL initialize HTTP {{init.status_code}}")
                return 1
            client.post(
                "/mcp/",
                json={{"jsonrpc": "2.0", "method": "notifications/initialized"}},
                headers={{"Accept": "application/json, text/event-stream"}},
            )
            listing = client.post(
                "/mcp/",
                json={{"jsonrpc": "2.0", "method": "tools/list", "id": 2, "params": {{}}}},
                headers={{"Accept": "application/json, text/event-stream"}},
            )
            body = listing.json()
            tools = [t.get("name") for t in body.get("result", {{}}).get("tools", [])]
            if "echo" not in tools:
                print(f"BUNDLE_PROBE_FAIL tools={{tools}}")
                return 1
        print("BUNDLE_PROBE_OK")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"BUNDLE_PROBE_FAIL {{exc!r}}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def _run_pyinstaller_phase(workdir: Path, venv_py: Path, sdk_flavor: str, probe_script: Path) -> Dict[str, Any]:
    result: Dict[str, Any] = {"name": "C5_pyinstaller_onefile", "status": "FAIL", "detail": ""}
    try:
        _pip_install(venv_py, ["pyinstaller"], timeout=600)
        bundle_dir = workdir / "bundle"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_script = bundle_dir / "probe_bundle.py"
        bundle_script.write_text(
            BUNDLE_PROBE_SOURCE.format(
                probe_script_dir=str(probe_script.parent),
                protocol_version=MCP_PROTOCOL_VERSION,
            ),
            encoding="utf-8",
        )
        # 把探针模块复制到 specpath 目录：PyInstaller 静态分析才能追踪
        # mcp_sdk_probe → fastapi/starlette/mcp 的完整 import 链并入包
        # （运行时 sys.path.insert 指向的目录在冻结环境不可追踪，首次实测漏打包 fastapi）。
        shutil.copyfile(probe_script, bundle_dir / "mcp_sdk_probe.py")
        build_cmd = [
            str(venv_py),
            "-m",
            "PyInstaller",
            "--onefile",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(bundle_dir / "dist"),
            "--workpath",
            str(bundle_dir / "build"),
            "--specpath",
            str(bundle_dir),
            str(bundle_script),
        ]
        started = time.monotonic()
        proc = subprocess.run(
            build_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900
        )
        build_seconds = round(time.monotonic() - started, 1)
        if proc.returncode != 0:
            result["detail"] = f"pyinstaller 构建失败({build_seconds}s): {proc.stderr[-1500:]}"
            return result
        exe = bundle_dir / "dist" / ("probe_bundle.exe" if sys.platform == "win32" else "probe_bundle")
        run_proc = subprocess.run(
            [str(exe), sdk_flavor], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        ok = run_proc.returncode == 0 and "BUNDLE_PROBE_OK" in run_proc.stdout
        result["status"] = "PASS" if ok else "FAIL"
        result["detail"] = (
            f"build={build_seconds}s, exe_size={exe.stat().st_size}, " f"stdout={run_proc.stdout.strip()[:300]}"
        )
    except Exception as exc:  # noqa: BLE001
        result["detail"] = repr(exc)
    return result


def run_probe(
    python_exe: str,
    sdk_spec: str,
    workdir: Path,
    with_pyinstaller: bool,
    evidence_out: Optional[Path],
) -> Dict[str, Any]:
    sdk_flavor = sdk_spec.split("==")[0].split(">=")[0].strip()
    if sdk_flavor not in SUPPORTED_SDK_FLAVORS:
        raise SystemExit(f"不支持的 SDK flavor: {sdk_flavor}（候选: {SUPPORTED_SDK_FLAVORS}）")

    workdir.mkdir(parents=True, exist_ok=True)
    venv_dir = workdir / "venv"
    print(f"[probe] 创建 venv: {python_exe} -> {venv_dir}", file=sys.stderr)
    proc = subprocess.run(
        [python_exe, "-m", "venv", str(venv_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise SystemExit(f"venv 创建失败: {proc.stderr[-1000:]}")
    venv_py = _venv_python(workdir)

    print(f"[probe] 安装锁定组合 + {sdk_spec}", file=sys.stderr)
    _pip_install(venv_py, [*REPO_PINNED_DEPS, sdk_spec])

    probe_script = Path(__file__).resolve()
    print(f"[probe] venv 内重入 selfcheck: {sdk_flavor}", file=sys.stderr)
    selfcheck = subprocess.run(
        [str(venv_py), str(probe_script), "selfcheck", "--sdk", sdk_flavor, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    try:
        evidence = json.loads(selfcheck.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"selfcheck 输出不可解析(rc={selfcheck.returncode}): {selfcheck.stdout[:500]}")

    if with_pyinstaller:
        print("[probe] PyInstaller onefile 检查", file=sys.stderr)
        evidence["checks"].append(_run_pyinstaller_phase(workdir, venv_py, sdk_flavor, probe_script))
        evidence["verdict"] = "PASS" if all(c["status"] == "PASS" for c in evidence["checks"]) else "FAIL"

    evidence["sdk_spec"] = sdk_spec
    evidence["python_exe"] = python_exe
    evidence["repo_pinned_deps"] = list(REPO_PINNED_DEPS)
    if evidence_out:
        evidence_out.parent.mkdir(parents=True, exist_ok=True)
        evidence_out.write_text(json.dumps(evidence, ensure_ascii=True, indent=2), encoding="utf-8")
        print(f"[probe] 证据已写入: {evidence_out}", file=sys.stderr)
    return evidence


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MCP SDK 兼容性探针")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="隔离 venv 内按仓库锁定组合检查")
    p_run.add_argument("--python", required=True, help="目标 Python 解释器路径")
    p_run.add_argument("--sdk", required=True, help="候选 SDK 安装规格，如 fastmcp==2.14.3 / mcp==1.25.0")
    p_run.add_argument("--workdir", required=True, help="工作目录（venv/构建产物）")
    p_run.add_argument("--pyinstaller", action="store_true", help="追加 C5 onefile 检查")
    p_run.add_argument("--evidence-out", default=None, help="证据 JSON 输出路径")

    p_self = sub.add_parser("selfcheck", help="当前解释器就地检查")
    p_self.add_argument("--sdk", required=True, choices=list(SUPPORTED_SDK_FLAVORS))
    p_self.add_argument("--json", action="store_true", help="仅输出 JSON（供 run 模式解析）")

    args = parser.parse_args(argv)
    if args.command == "selfcheck":
        evidence = run_selfcheck(args.sdk)
        if args.json:
            print(json.dumps(evidence, ensure_ascii=True, indent=2))
            return 0 if evidence["verdict"] == "PASS" else 1
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0 if evidence["verdict"] == "PASS" else 1

    evidence = run_probe(
        python_exe=args.python,
        sdk_spec=args.sdk,
        workdir=Path(args.workdir),
        with_pyinstaller=args.pyinstaller,
        evidence_out=Path(args.evidence_out) if args.evidence_out else None,
    )
    print(json.dumps({k: evidence[k] for k in ("sdk", "verdict")}, ensure_ascii=False))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
