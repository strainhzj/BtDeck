# -*- coding: utf-8 -*-
"""BtDeck Android 本机服务端运行体（dual-mode-client Phase 3）。

由 stage-server.py 拷入 staged python 目录（与 app/、alembic/、frontend/ 同级）。
Kotlin ServerService 经 Chaquopy callAttr 调用 start/stop/status，返回 JSON 字符串。

生产化自 android-wheels 仓 scripts/fullgraph_bootstrap.py（闸门判据 5/6 实证
运行体，4096 与 ps16k AVD 均 9/9 全绿）：异步启动 + 状态轮询、Alembic
fail-fast、优雅停机、幂等重启。

坑位沉淀（wheels 仓 gate.md 实证，勿改）：
- 深导入（fastapi→pydantic→typing_extensions 链）必须在 16MB 大栈线程执行
  （默认线程栈在 Python 递归限触发前先耗尽 C 栈）；
- uvicorn 在 Android 上拒绑 port=0：先以普通 socket 取空闲端口再关，交给
  uvicorn 以具体端口绑定；
- 环境变量（CONFIG_DIR/DATABASE_PATH/TORRENTS_DIR）必须在首次 import
  app.core.config 前设置（pydantic-settings 单例缓存），data_root 因此一次锚定；
- Chaquopy 源集丢弃非包目录孤儿 .py：alembic 迁移脚本以 .pymig 数据形态
  打包，本模块首跑物化还原。
"""

import json
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STATE_STOPPED = "stopped"
STATE_STARTING = "starting"
STATE_RUNNING = "running"
STATE_ERROR = "error"

_HEALTH_TIMEOUT_S = 120  # 首启含迁移+导入，16K AVD 实证最长约 42s

_lock = threading.Lock()
_state: dict = {
    "state": STATE_STOPPED,
    "port": None,
    "version": None,
    "error": None,
    "errorPhase": None,
    "startedAtMs": 0,
}
_server = None         # uvicorn.Server（运行中实例）
_uvicorn_thread = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _materialize_alembic() -> None:
    """把以 .pymig 数据形态打包的迁移脚本还原为 .py（AssetFinder 目录可写）。"""
    alembic_dir = ROOT / "alembic"
    if not alembic_dir.is_dir():
        return
    for f in alembic_dir.rglob("*.pymig"):
        target = f.with_suffix("")
        if not target.exists():
            target.write_bytes(f.read_bytes())


def _prepare_env(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "torrents").mkdir(parents=True, exist_ok=True)
    os.environ["CONFIG_DIR"] = str(root / "config")
    os.environ["DATABASE_PATH"] = str(root / "config" / "app.db")
    os.environ["TORRENTS_DIR"] = str(root / "torrents")


def _pick_port(host: str, preferred_port: int) -> int:
    """优先复用上次端口（LAN 场景其它设备免追端口），被抢占则回落动态分配。

    探测 socket 设 SO_REUSEADDR 与 uvicorn 一致：刚停机的监听端口处于
    TIME_WAIT 时仍可复用（AVD 实证：重启未复用端口 → 探测 bind 被拒）。
    """
    for candidate in (preferred_port if preferred_port > 0 else None, 0):
        if candidate is None:
            continue
        probe = socket.socket()
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, candidate))
            return candidate if candidate > 0 else probe.getsockname()[1]
        except OSError:
            continue
        finally:
            probe.close()
    raise RuntimeError(f"无法获得可用端口（host={host}）")


def _bootstrap(root: Path, host: str, preferred_port: int) -> None:
    """启动链：物化迁移 → 环境锚定 → Alembic fail-fast → 深导入 → uvicorn → 健康自检。

    在 16MB 大栈线程执行（start() 起线程前已设 stack_size）。
    顺序契约：迁移必须先于 `from app import main`——app 导入链存在模块级 DB
    查询（实证：空库时 tracker_keyword_config 查询失败刷日志，依赖 lifespan
    补救）；迁移先行让深导入看到的是已建好的库。
    """
    global _server, _uvicorn_thread
    phase = "env"
    server = None
    uvicorn_thread = None
    try:
        _materialize_alembic()
        _prepare_env(root)

        phase = "migration"
        from app.core.migration import migrate_database

        if not migrate_database():
            raise RuntimeError("migrate_database() 返回 False（详见服务端日志）")

        phase = "import"
        from app import main  # noqa: F401  完整 import graph
        from app.version import CURRENT_VERSION

        phase = "bind"
        port = _pick_port(host, preferred_port)
        import uvicorn

        config = uvicorn.Config("app.main:app", host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        uvicorn_thread = threading.Thread(
            target=server.run, daemon=True, name="btdeck-uvicorn"
        )
        threading.stack_size(16 * 1024 * 1024)
        uvicorn_thread.start()
        with _lock:  # starting 态即可见端口（诊断/提前握手）
            _state["port"] = port

        phase = "health"
        import httpx

        deadline = time.time() + _HEALTH_TIMEOUT_S
        last_error: Exception | None = None
        while time.time() < deadline:
            if not uvicorn_thread.is_alive():
                raise RuntimeError(f"uvicorn 线程提前退出: {last_error}")
            try:
                # trust_env=False：loopback 自检绝不走系统/环境代理
                # （Windows 注册表代理实证会把 127.0.0.1 转发成代理 503）
                resp = httpx.get(
                    f"http://127.0.0.1:{port}/health/live", timeout=5, trust_env=False
                )
                if resp.status_code == 200:
                    with _lock:
                        _server = server
                        _uvicorn_thread = uvicorn_thread
                        _state.update(
                            state=STATE_RUNNING,
                            port=port,
                            version=CURRENT_VERSION,
                            error=None,
                            errorPhase=None,
                        )
                    return
                last_error = RuntimeError(f"/health/live HTTP {resp.status_code}")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            time.sleep(1)
        raise TimeoutError(f"健康握手超时（{_HEALTH_TIMEOUT_S}s）: {last_error}")
    except BaseException as exc:  # noqa: BLE001
        # 尽力关掉可能已起的 uvicorn（健康超时但服务仍可能监听）
        if server is not None:
            server.should_exit = True
        detail = "".join(traceback.format_exception(exc))[-4000:]
        with _lock:
            _state.update(
                state=STATE_ERROR,
                port=None,
                error=f"[{phase}] {exc}",
                errorPhase=phase,
            )
            # error 字段只带摘要；完整 traceback 打到 logcat（Chaquopy 转 stdout/stderr）
            print(f"btdeck_server start failed at phase={phase}\n{detail}", file=sys.stderr)


def start(data_root: str, host: str = "127.0.0.1", preferred_port: int = 0) -> str:
    """启动本机服务端。立即返回 starting，进度经 status() 轮询；幂等。"""
    root = Path(str(data_root))
    host = str(host)
    preferred_port = int(preferred_port)
    with _lock:
        if _state["state"] in (STATE_STARTING, STATE_RUNNING):
            return json.dumps(
                {"ok": True, "state": _state["state"], "port": _state["port"], "version": _state["version"]}
            )
        _state.update(
            state=STATE_STARTING,
            port=None,
            version=None,
            error=None,
            errorPhase=None,
            startedAtMs=_now_ms(),
        )
    threading.stack_size(16 * 1024 * 1024)
    threading.Thread(
        target=_bootstrap, args=(root, host, preferred_port),
        name="btdeck-bootstrap", daemon=True,
    ).start()
    return json.dumps({"ok": True, "state": STATE_STARTING})


def stop() -> str:
    """优雅停机：should_exit + 最多 30s 等待。stopped/error 态幂等。"""
    global _server, _uvicorn_thread
    with _lock:
        server, uvicorn_thread = _server, _uvicorn_thread
    if server is not None:
        server.should_exit = True
    if uvicorn_thread is not None:
        uvicorn_thread.join(timeout=30)
    with _lock:
        _server = None
        _uvicorn_thread = None
        _state.update(state=STATE_STOPPED, port=None, version=None)
    return json.dumps({"ok": True, "state": STATE_STOPPED})


def status() -> str:
    with _lock:
        return json.dumps({"ok": True, **_state})
