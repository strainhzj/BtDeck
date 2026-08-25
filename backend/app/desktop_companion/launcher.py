# -*- coding: utf-8 -*-
"""桌面双模式启动器（dual-mode-client task .6）。

对齐安卓端 Phase 2 的首启向导语义（模式二选一 + 可重跑）：
- 服务端模式为默认（PyInstaller exe 历史行为不变），无记录时首启弹向导
  一次，默认高亮服务端模式；「记住选择」后按记录直达；
- 环境变量 ``BTDECK_MODE=server|companion`` 优先于记录（快捷方式/CI 场景）；
- 伴侣模式 = 服务器管理页（显示名/URL/五态健康/版本/时间 + 增删/测试）+
  内嵌 webview 窗口直连远程服务器自带前端（同源，不内置前端资源）；
- 退出恢复：远程窗口关闭回到管理页；退出/关全部窗口即结束；重跑向导
  可再次切换模式。

已知边界（MVP，与安卓 README 同口径登记）：
- pywebview 以私有会话运行（private_mode 默认），凭据不落盘，应用重启后
  需重新登录；单会话内切换服务器共享同一私有存储；
- 自签 https 在健康检查侧归类 TLS_ERROR；内嵌 WebView 的证书错误由渲染
  引擎呈现，不做指纹信任流程（与安卓 TrustScope 的差异）。
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from app.desktop_companion import lan_policy
from app.desktop_companion.health import HealthClient, health_label
from app.desktop_companion.profiles import ServerProfile, ServerProfileStore

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查导入，测试环境无 pywebview
    import webview

logger = logging.getLogger(__name__)

MODE_SERVER = "server"
MODE_COMPANION = "companion"

_BRAND_COLOR = "#059669"


# ============ 模式持久化（desktop_mode.json） ============


def default_store_path() -> Path:
    from app.core.config import settings

    return settings.CONFIG_PATH / "companion_servers.json"


def default_mode_path() -> Path:
    from app.core.config import settings

    return settings.CONFIG_PATH / "desktop_mode.json"


def load_stored_mode(path: Optional[Path] = None) -> Optional[str]:
    mode_path = path if path is not None else default_mode_path()
    if not mode_path.exists():
        return None
    try:
        raw = json.loads(mode_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取桌面模式记录失败（%s）：%s", mode_path, exc)
        return None
    mode = raw.get("mode") if isinstance(raw, dict) else None
    return mode if mode in (MODE_SERVER, MODE_COMPANION) else None


def save_stored_mode(mode: str, path: Optional[Path] = None) -> None:
    mode_path = path if path is not None else default_mode_path()
    mode_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = mode_path.with_suffix(mode_path.suffix + ".tmp")
    temp_path.write_text(json.dumps({"mode": mode}, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_path, mode_path)


def clear_stored_mode(path: Optional[Path] = None) -> None:
    mode_path = path if path is not None else default_mode_path()
    mode_path.unlink(missing_ok=True)


def resolve_launch_mode(path: Optional[Path] = None) -> Optional[str]:
    """环境变量优先，其次持久化记录；None 表示未决（需向导）。"""
    env = os.getenv("BTDECK_MODE", "").strip().lower()
    if env in (MODE_SERVER, MODE_COMPANION):
        return env
    return load_stored_mode(path)


def _now_ms() -> int:
    return int(time.time() * 1000)


# ============ JS 桥接 API ============


class _WizardApi:
    """向导页桥接：选择模式（remember 决定是否持久化）。"""

    def __init__(self, controller: "DesktopLauncher"):
        self._controller = controller

    def choose_mode(self, mode: str, remember: bool) -> dict[str, Any]:
        self._controller.on_wizard_chosen(mode, remember)
        return {"ok": True}


class _ManagerApi:
    """服务器管理页桥接：列表/增删/测试/打开/重跑向导/退出。"""

    def __init__(self, controller: "DesktopLauncher"):
        self._controller = controller

    def list_servers(self) -> list[dict[str, Any]]:
        profiles = self._controller.store.load_all()
        items = []
        for profile in profiles:
            item = profile.to_json()
            item["healthLabel"] = health_label(profile.health_state)
            items.append(item)
        return items

    def add_server(self, name: str, url: str, consent: bool) -> dict[str, Any]:
        if not name.strip():
            return {"ok": False, "error": "请输入显示名称"}
        verdict = lan_policy.check(url, bool(consent))
        if not verdict.ok or verdict.parsed is None:
            reason = verdict.reason or lan_policy.RejectReason.MALFORMED_URL
            return {"ok": False, "error": lan_policy.REJECT_MESSAGES[reason]}
        profile = ServerProfile(
            display_name=name.strip(),
            base_url=verdict.parsed.base_url,
            cleartext_allowed=verdict.parsed.scheme == "http",
        )
        self._controller.store.upsert(profile)
        return {"ok": True}

    def test_server(self, server_id: str) -> dict[str, Any]:
        profile = self._find(server_id)
        if profile is None:
            return {"ok": False, "error": "服务器不存在"}
        report = self._controller.health.check(profile.base_url)
        profile.health_state = report.state
        profile.server_version = report.version
        profile.last_health_checked_at = _now_ms()
        self._controller.store.upsert(profile)
        return {
            "ok": True,
            "state": report.state,
            "stateLabel": health_label(report.state),
            "version": report.version,
            "detail": report.detail,
        }

    def remove_server(self, server_id: str) -> dict[str, Any]:
        return {"ok": self._controller.store.remove(server_id)}

    def open_server(self, server_id: str) -> dict[str, Any]:
        ok = self._controller.open_remote_window(server_id)
        return {"ok": ok} if ok else {"ok": False, "error": "服务器不存在"}

    def rerun_wizard(self) -> dict[str, Any]:
        self._controller.rerun_wizard()
        return {"ok": True}

    def exit_app(self) -> dict[str, Any]:
        self._controller.exit_companion()
        return {"ok": True}

    def _find(self, server_id: str) -> Optional[ServerProfile]:
        return next(
            (item for item in self._controller.store.load_all() if item.id == server_id),
            None,
        )


# ============ 启动器控制器 ============


class DesktopLauncher:
    """一次 webview.start() 内完成向导/管理页/远程窗口的事件驱动切换。"""

    def __init__(
        self,
        store: Optional[ServerProfileStore] = None,
        health: Optional[HealthClient] = None,
        mode_path: Optional[Path] = None,
    ):
        self.store = store if store is not None else ServerProfileStore(default_store_path())
        self.health = health if health is not None else HealthClient()
        self._mode_path = mode_path if mode_path is not None else default_mode_path()
        self._mode: Optional[str] = None
        self._wizard_window: Optional["webview.Window"] = None
        self._manager_window: Optional["webview.Window"] = None
        self._manager_api: Optional[_ManagerApi] = None

    @property
    def mode(self) -> Optional[str]:
        return self._mode

    def launch(self) -> str:
        """运行启动器流程，返回最终模式（server/companion）。

        已记录为 server 时直接返回（不创建任何窗口，历史默认行为不变）；
        未决时弹向导；companion 时直接进服务器管理页。
        """
        self._mode = resolve_launch_mode(self._mode_path)
        if self._mode == MODE_SERVER:
            return MODE_SERVER

        import webview

        if self._mode is None:
            self._show_wizard()
        else:
            self._show_manager()
        webview.start()
        return self._mode if self._mode else MODE_SERVER

    # ---- 由 js_api 线程触发的窗口切换 ----

    def on_wizard_chosen(self, mode: str, remember: bool) -> None:
        chosen = mode if mode in (MODE_SERVER, MODE_COMPANION) else MODE_SERVER
        if remember:
            save_stored_mode(chosen, self._mode_path)
        self._mode = chosen
        wizard = self._wizard_window
        self._wizard_window = None
        # 先建新窗、后销毁旧窗：pywebview(winforms) 销毁最后一个窗口时会直接
        # Application.Exit() 结束 GUI 循环，且运行期建窗依赖既有窗口的 Invoke
        # 通道——先 destroy 会让新窗建在正在退出的循环上（实测必崩）。
        if chosen == MODE_COMPANION:
            self._show_manager()
        if wizard is not None:
            wizard.destroy()

    def open_remote_window(self, server_id: str) -> bool:
        profile = next((item for item in self.store.load_all() if item.id == server_id), None)
        if profile is None:
            return False
        profile.last_connected_at = _now_ms()
        self.store.upsert(profile)

        import webview

        manager = self._manager_window
        remote = webview.create_window(
            f"BtDeck - {profile.display_name}",
            profile.base_url,
            width=1280,
            height=820,
            min_size=(1024, 680),
        )

        def on_remote_closed() -> None:
            if manager is not None:
                manager.show()
            self._reload_manager_page()

        remote.events.closed += on_remote_closed
        if manager is not None:
            manager.hide()
        return True

    def rerun_wizard(self) -> None:
        clear_stored_mode(self._mode_path)
        self._mode = None
        manager = self._manager_window
        self._manager_window = None
        self._manager_api = None
        # 同 on_wizard_chosen：先建向导窗、再销毁管理页，窗口计数不清零。
        self._show_wizard()
        if manager is not None:
            manager.destroy()

    def exit_companion(self) -> None:
        manager = self._manager_window
        self._manager_window = None
        self._manager_api = None
        if manager is not None:
            manager.destroy()

    # ---- 窗口创建 ----

    def _show_wizard(self) -> None:
        import webview

        self._wizard_window = webview.create_window(
            "BtDeck 启动",
            html=_WIZARD_HTML,
            js_api=_WizardApi(self),
            width=520,
            height=430,
            resizable=False,
        )

    def _show_manager(self) -> None:
        import webview

        self._manager_api = _ManagerApi(self)
        self._manager_window = webview.create_window(
            "BtDeck · 伴侣模式",
            html=_MANAGER_HTML,
            js_api=self._manager_api,
            width=620,
            height=700,
            min_size=(540, 560),
        )

    def _reload_manager_page(self) -> None:
        manager = self._manager_window
        if manager is None:
            return
        try:
            manager.evaluate_js("window.__btdeckRefreshServers && window.__btdeckRefreshServers()")
        except Exception as exc:  # noqa: BLE001 - 刷新为尽力而为，不阻塞窗口恢复
            logger.debug("管理页刷新失败：%s", exc)


# ============ 内嵌页面（本地 HTML，不依赖前端构建产物） ============

_BASE_CSS = f"""
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
         background: #f5f7fa; color: #303133; font-size: 14px; }}
  .brand {{ color: {_BRAND_COLOR}; }}
  button {{ cursor: pointer; border: none; border-radius: 6px; font-size: 13px; }}
"""

_WIZARD_HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>{_BASE_CSS}
  .wrap {{ padding: 28px 24px; }}
  h1 {{ font-size: 18px; margin-bottom: 6px; }}
  .sub {{ color: #909399; margin-bottom: 22px; }}
  .card {{ background: #fff; border: 1px solid #e4e7ed; border-radius: 10px;
          padding: 16px; margin-bottom: 14px; width: 100%; text-align: left; }}
  .card:hover {{ border-color: {_BRAND_COLOR}; }}
  .card .t {{ font-size: 15px; font-weight: 600; margin-bottom: 6px; }}
  .card .d {{ color: #909399; line-height: 1.5; }}
  .card .tag {{ display: inline-block; margin-left: 8px; font-size: 11px;
               color: {_BRAND_COLOR}; border: 1px solid {_BRAND_COLOR};
               border-radius: 4px; padding: 0 4px; vertical-align: 2px; }}
  .foot {{ display: flex; align-items: center; gap: 8px; color: #909399;
          font-size: 13px; margin-top: 6px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>BtDeck 启动</h1>
  <div class="sub">请选择运行模式（稍后可重新选择）</div>
  <button class="card" onclick="choose('companion')">
    <div class="t">伴侣模式<span class="tag">连接已有服务器</span></div>
    <div class="d">管理服务器地址并以内嵌窗口直连远程 BtDeck，本机不运行服务。</div>
  </button>
  <button class="card" onclick="choose('server')">
    <div class="t">服务端模式<span class="tag">默认</span></div>
    <div class="d">本机运行完整后端与前端（历史桌面版行为）。</div>
  </button>
  <div class="foot">
    <input type="checkbox" id="remember" checked>
    <label for="remember">记住我的选择（可在伴侣模式管理页重新选择）</label>
  </div>
</div>
<script>
  function choose(mode) {{
    var remember = document.getElementById('remember').checked;
    if (window.pywebview && pywebview.api) {{
      pywebview.api.choose_mode(mode, remember);
    }}
  }}
</script>
</body>
</html>
"""

_MANAGER_HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>{_BASE_CSS}
  .wrap {{ padding: 20px; max-width: 640px; margin: 0 auto; }}
  h1 {{ font-size: 17px; margin-bottom: 4px; }}
  .sub {{ color: #909399; margin-bottom: 16px; }}
  .panel {{ background: #fff; border: 1px solid #e4e7ed; border-radius: 10px;
           padding: 14px; margin-bottom: 14px; }}
  .panel h2 {{ font-size: 14px; margin-bottom: 10px; }}
  input[type=text] {{ width: 100%; border: 1px solid #dcdfe6; border-radius: 6px;
                     padding: 7px 10px; font-size: 13px; margin-bottom: 8px; }}
  input[type=text]:focus {{ outline: none; border-color: {_BRAND_COLOR}; }}
  .row {{ display: flex; align-items: center; gap: 8px; }}
  .consent {{ display: flex; align-items: center; gap: 6px; color: #909399;
             font-size: 12px; margin-bottom: 10px; }}
  .primary {{ background: {_BRAND_COLOR}; color: #fff; padding: 7px 16px; }}
  .plain {{ background: #fff; color: #606266; border: 1px solid #dcdfe6;
           padding: 6px 12px; }}
  .danger {{ background: #fff; color: #f56c6c; border: 1px solid #fbc4c4;
            padding: 6px 12px; }}
  .server {{ border-bottom: 1px solid #f0f2f5; padding: 12px 2px; }}
  .server:last-child {{ border-bottom: none; }}
  .s-name {{ font-weight: 600; font-size: 14px; }}
  .s-url {{ color: #909399; font-size: 12px; word-break: break-all;
           margin: 3px 0 6px; }}
  .badge {{ display: inline-block; font-size: 11px; border-radius: 4px;
           padding: 1px 6px; margin-right: 6px; }}
  .b-ready {{ color: #059669; background: #ecf5ff; }}
  .b-warn {{ color: #e6a23c; background: #fdf6ec; }}
  .b-error {{ color: #f56c6c; background: #fef0f0; }}
  .b-unknown {{ color: #909399; background: #f4f4f5; }}
  .meta {{ color: #909399; font-size: 12px; margin: 4px 0 8px; }}
  .actions {{ display: flex; gap: 8px; }}
  .msg {{ font-size: 13px; margin: 8px 0; min-height: 18px; }}
  .msg.error {{ color: #f56c6c; }}
  .msg.info {{ color: {_BRAND_COLOR}; }}
  .footer {{ display: flex; justify-content: space-between; margin-top: 4px; }}
  .empty {{ color: #c0c4cc; text-align: center; padding: 24px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>BtDeck <span class="brand">伴侣模式</span></h1>
  <div class="sub">连接已有 BtDeck 服务器（本机不运行服务）</div>

  <div class="panel">
    <h2>添加服务器</h2>
    <input type="text" id="name" placeholder="显示名称（如：NAS 服务器）">
    <input type="text" id="url" placeholder="服务器地址（http/https，如 http://192.168.1.10:5001）">
    <div class="consent">
      <input type="checkbox" id="consent">
      <label for="consent">我已了解：明文 HTTP 仅限私有局域网地址，凭据可能被同网段截获</label>
    </div>
    <div class="row"><button class="primary" onclick="addServer()">添加</button></div>
    <div class="msg" id="add-msg"></div>
  </div>

  <div class="panel">
    <h2>我的服务器</h2>
    <div id="list"><div class="empty">暂无服务器</div></div>
  </div>

  <div class="footer">
    <button class="plain" onclick="rerun()">重新选择模式</button>
    <button class="plain" onclick="exitApp()">退出</button>
  </div>
</div>
<script>
  function api() {{ return window.pywebview && pywebview.api; }}
  function esc(s) {{
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {{
      return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];
    }});
  }}
  function badgeClass(state) {{
    if (state === 'READY') return 'b-ready';
    if (state === 'NOT_READY') return 'b-warn';
    if (state === 'UNREACHABLE' || state === 'TLS_ERROR') return 'b-error';
    return 'b-unknown';
  }}
  function timeLabel(ms) {{
    if (!ms || ms <= 0) return '从未';
    var d = new Date(ms);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
  }}
  window.__btdeckRefreshServers = function () {{ loadServers(); }};
  function loadServers() {{
    if (!api()) {{ setTimeout(loadServers, 100); return; }}
    api().list_servers().then(function (items) {{
      var box = document.getElementById('list');
      if (!items || !items.length) {{
        box.innerHTML = '<div class="empty">暂无服务器</div>';
        return;
      }}
      box.innerHTML = items.map(function (it) {{
        var version = it.serverVersion ? 'v' + esc(it.serverVersion) + ' · ' : '';
        return '<div class="server">'
          + '<div class="s-name">' + esc(it.displayName) + '</div>'
          + '<div class="s-url">' + esc(it.baseUrl) + '</div>'
          + '<span class="badge ' + badgeClass(it.healthState) + '">'
          + esc(it.healthLabel) + '</span>'
          + '<div class="meta">' + version + '健康: ' + timeLabel(it.lastHealthCheckedAt)
          + ' · 连接: ' + timeLabel(it.lastConnectedAt) + '</div>'
          + '<div class="actions">'
          + '<button class="primary" onclick="openServer(\\'' + it.id + '\\')">打开</button>'
          + '<button class="plain" onclick="testServer(\\'' + it.id + '\\')">测试连接</button>'
          + '<button class="danger" onclick="removeServer(\\'' + it.id + '\\')">删除</button>'
          + '</div></div>';
      }}).join('');
    }});
  }}
  function setMsg(id, text, isError) {{
    var el = document.getElementById(id);
    el.textContent = text || '';
    el.className = 'msg' + (isError ? ' error' : ' info');
  }}
  function addServer() {{
    if (!api()) return;
    var name = document.getElementById('name').value;
    var url = document.getElementById('url').value;
    var consent = document.getElementById('consent').checked;
    setMsg('add-msg', '');
    api().add_server(name, url, consent).then(function (res) {{
      if (res && res.ok) {{
        document.getElementById('name').value = '';
        document.getElementById('url').value = '';
        document.getElementById('consent').checked = false;
        setMsg('add-msg', '已添加');
        loadServers();
      }} else {{
        setMsg('add-msg', res && res.error ? res.error : '添加失败', true);
      }}
    }});
  }}
  function testServer(id) {{
    if (!api()) return;
    api().test_server(id).then(function (res) {{
      if (res && res.ok) {{ loadServers(); }}
    }});
  }}
  function openServer(id) {{
    if (!api()) return;
    api().open_server(id);
  }}
  function removeServer(id) {{
    if (!api()) return;
    if (!window.confirm('确定删除该服务器吗？')) return;
    api().remove_server(id).then(function () {{ loadServers(); }});
  }}
  function rerun() {{
    if (!api()) return;
    api().rerun_wizard();
  }}
  function exitApp() {{
    if (!api()) return;
    api().exit_app();
  }}
  window.addEventListener('pywebviewready', loadServers);
  loadServers();
</script>
</body>
</html>
"""
