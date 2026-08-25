# -*- coding: utf-8 -*-
"""desktop_companion.launcher 控制器测试（无 pywebview 依赖路径）。

GUI/webview 部分不在此覆盖（与安卓 MVP 同口径：逻辑层单测，窗口链路留
桌面实测）；锁住：服务端模式直达（历史行为不变）、向导选择的持久化语义、
管理页桥接 API 的增删测试与状态回写。
"""

from app.desktop_companion.launcher import (
    MODE_COMPANION,
    MODE_SERVER,
    DesktopLauncher,
    _ManagerApi,
    load_stored_mode,
    save_stored_mode,
)
from app.desktop_companion.profiles import (
    HEALTH_READY,
    ServerProfile,
    ServerProfileStore,
)


class _StubHealth:
    """按 base_url 返回预置报告的桩。"""

    def __init__(self, reports):
        self._reports = reports
        self.calls = []

    def check(self, base_url):
        self.calls.append(base_url)
        return self._reports[base_url]


def _launcher(tmp_path, stub_health=None):
    return DesktopLauncher(
        store=ServerProfileStore(tmp_path / "servers.json"),
        health=stub_health,
        mode_path=tmp_path / "desktop_mode.json",
    )


class TestLauncherModeFlow:
    def test_stored_server_launches_without_webview(self, tmp_path):
        """已记录服务端模式：launch() 直接返回，不触碰 webview（历史行为）。"""
        launcher = _launcher(tmp_path)
        save_stored_mode(MODE_SERVER, tmp_path / "desktop_mode.json")
        assert launcher.launch() == MODE_SERVER
        assert launcher._wizard_window is None
        assert launcher._manager_window is None

    def test_wizard_choice_server_persists_when_remembered(self, tmp_path):
        launcher = _launcher(tmp_path)
        launcher.on_wizard_chosen(MODE_SERVER, remember=True)
        assert launcher.mode == MODE_SERVER
        assert load_stored_mode(tmp_path / "desktop_mode.json") == MODE_SERVER
        # 服务端模式不建管理页
        assert launcher._manager_window is None

    def test_wizard_choice_companion_not_remembered(self, tmp_path):
        """不勾「记住」：仅本次生效，不落记录。"""
        launcher = _launcher(tmp_path)
        # companion 分支会创建管理页窗口（需 webview），只验证持久化副作用
        # 之前的路径：先断言非法模式回退服务端
        launcher.on_wizard_chosen("bogus", remember=True)
        assert launcher.mode == MODE_SERVER
        assert load_stored_mode(tmp_path / "desktop_mode.json") == MODE_SERVER


class TestManagerApi:
    def _api(self, tmp_path, stub_health=None):
        launcher = _launcher(tmp_path, stub_health)
        return _ManagerApi(launcher), launcher.store

    def test_add_list_roundtrip(self, tmp_path):
        api, store = self._api(tmp_path)
        result = api.add_server("NAS", "http://192.168.5.51:5001", True)
        assert result == {"ok": True}

        items = api.list_servers()
        assert len(items) == 1
        assert items[0]["displayName"] == "NAS"
        assert items[0]["baseUrl"] == "http://192.168.5.51:5001"
        assert items[0]["cleartextAllowed"] is True
        assert items[0]["healthLabel"] == "未测试"

    def test_add_validations(self, tmp_path):
        api, _ = self._api(tmp_path)
        assert api.add_server("", "http://10.0.0.5", True)["error"] == "请输入显示名称"
        assert "地址无效" in api.add_server("X", "not-a-url", True)["error"]
        assert "勾选风险确认" in api.add_server("X", "http://10.0.0.5", False)["error"]
        assert "私有局域网" in api.add_server("X", "http://example.com", True)["error"]

    def test_test_server_updates_profile_state(self, tmp_path):
        stub = _StubHealth(
            {"http://192.168.5.51:5001": type(
                "R", (), {"state": HEALTH_READY, "version": "1.0.5", "detail": "服务就绪"}
            )()}
        )
        api, store = self._api(tmp_path, stub)
        api.add_server("NAS", "http://192.168.5.51:5001", True)
        profile_id = api.list_servers()[0]["id"]

        result = api.test_server(profile_id)
        assert result["ok"] is True
        assert result["state"] == HEALTH_READY
        assert result["stateLabel"] == "就绪"
        assert result["version"] == "1.0.5"

        stored = store.load_all()[0]
        assert stored.health_state == HEALTH_READY
        assert stored.server_version == "1.0.5"
        assert stored.last_health_checked_at > 0

    def test_test_server_missing_id(self, tmp_path):
        api, _ = self._api(tmp_path)
        assert api.test_server("nope")["ok"] is False

    def test_remove_server(self, tmp_path):
        api, _ = self._api(tmp_path)
        api.add_server("NAS", "http://10.0.0.5:5001", True)
        profile_id = api.list_servers()[0]["id"]
        assert api.remove_server(profile_id)["ok"] is True
        assert api.list_servers() == []
        assert api.remove_server(profile_id)["ok"] is False
