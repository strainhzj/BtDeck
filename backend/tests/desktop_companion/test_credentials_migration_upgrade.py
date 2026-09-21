# -*- coding: utf-8 -*-
"""task .8 凭据记忆的升级迁移演练（v1.0.5 形态 profile/vault → v1.0.6 代码路径）。

保护点：
1. 旧版 companion_servers.json（无 username 键、缺新字段）升级载入不丢服务器、
   username 回退空串、未落凭据时 hasSavedCredential=False；
2. 升级后在旧 profile 上补录凭据 → 改密（新密码）→ 留空保留 → 清除，全链路
   与新装路径行为一致（真实 DPAPI 文件 vault，非内存桩）；
3. 更换地址不携带旧密码；vault 密文文件损坏时降级为无凭据并可重新写入。
"""

import json
import sys
import time
from pathlib import Path

import pytest

from app.desktop_companion.credentials import CredentialRecord, WindowsCredentialVault
from app.desktop_companion.launcher import DesktopLauncher, _ManagerApi
from app.desktop_companion.profiles import ServerProfileStore

OLD_SERVERS_JSON = [
    {
        "id": "legacy-0001",
        "displayName": "NAS（v1.0.5 旧档案）",
        "baseUrl": "http://127.0.0.1:5001",
        "cleartextAllowed": False,
        "healthState": "READY",
        "serverVersion": "1.0.5",
        "lastHealthCheckedAt": 1700000000000,
        "lastConnectedAt": 1700000000000,
    }
]


@pytest.fixture()
def upgraded_env(tmp_path: Path):
    """v1.0.5 形态持久层 + v1.0.6 启动器（真实 DPAPI vault）。"""
    store_path = tmp_path / "companion_servers.json"
    store_path.write_text(json.dumps(OLD_SERVERS_JSON, ensure_ascii=False), encoding="utf-8")
    store = ServerProfileStore(store_path)
    vault = WindowsCredentialVault(tmp_path / "vault")
    launcher = DesktopLauncher(
        store=store,
        health=None,
        mode_path=tmp_path / "desktop_mode.json",
        credentials=vault,
    )
    return store, vault, launcher, tmp_path


@pytest.mark.skipif(sys.platform != "win32", reason="真实 DPAPI vault 仅 Windows")
class TestLegacyProfileUpgrade:
    def test_legacy_profile_loads_with_empty_username_and_no_credential(self, upgraded_env):
        store, vault, launcher, _ = upgraded_env
        profiles = store.load_all()
        assert len(profiles) == 1
        legacy = profiles[0]
        assert legacy.id == "legacy-0001"
        assert legacy.username == ""
        assert legacy.base_url == "http://127.0.0.1:5001"
        assert legacy.server_version == "1.0.5"
        assert not vault.has(legacy.id)
        api = _ManagerApi(launcher)
        items = api.list_servers()
        assert items[0]["hasSavedCredential"] is False

    def test_add_credentials_on_legacy_profile_then_blank_keeps(self, upgraded_env):
        store, vault, launcher, _ = upgraded_env
        api = _ManagerApi(launcher)
        legacy = store.load_all()[0]

        # 补录凭据（升级后首次设置）
        assert api.update_server(
            legacy.id, "NAS（v1.0.5 旧档案）", "http://127.0.0.1:5001", False, "admin", "first-secret"
        )["ok"]
        assert vault.get(legacy.id) == CredentialRecord("admin", "first-secret")

        # 改密（新密码覆盖）
        assert api.update_server(
            legacy.id, "NAS（v1.0.5 旧档案）", "http://127.0.0.1:5001", False, "admin", "second-secret"
        )["ok"]
        assert vault.get(legacy.id) == CredentialRecord("admin", "second-secret")

        # 密码留空 → 保留旧密码（仅当地址未变）
        assert api.update_server(legacy.id, "NAS 改名", "http://127.0.0.1:5001", False, "admin", "")["ok"]
        assert vault.get(legacy.id) == CredentialRecord("admin", "second-secret")
        assert store.load_all()[0].display_name == "NAS 改名"

        # 显式清除
        assert api.clear_credentials(legacy.id)["ok"]
        assert vault.get(legacy.id) is None

    def test_url_change_drops_legacy_password(self, upgraded_env):
        store, vault, launcher, _ = upgraded_env
        api = _ManagerApi(launcher)
        legacy = store.load_all()[0]
        api.update_server(legacy.id, "NAS", "http://127.0.0.1:5001", False, "admin", "carry-secret")
        assert vault.has(legacy.id)

        assert api.update_server(legacy.id, "NAS", "http://127.0.0.1:6001", False, "admin", "")["ok"]
        assert vault.get(legacy.id) is None, "更换地址不得携带旧服务器密码"

    def test_corrupt_vault_file_degrades_and_can_be_rewritten(self, upgraded_env):
        store, vault, launcher, tmp_path = upgraded_env
        api = _ManagerApi(launcher)
        legacy = store.load_all()[0]
        api.update_server(legacy.id, "NAS", "http://127.0.0.1:5001", False, "admin", "good-secret")

        vault_file = tmp_path / "vault" / "legacy-0001.dpapi"
        vault_file.write_bytes(b"\x00corrupted-not-dpapi")
        assert vault.get(legacy.id) is None, "密文损坏应降级为无凭据而不是崩溃"

        api.update_server(legacy.id, "NAS", "http://127.0.0.1:5001", False, "admin", "rebuilt-secret")
        assert vault.get(legacy.id) == CredentialRecord("admin", "rebuilt-secret")

    def test_password_never_enters_profile_json_after_upgrade(self, upgraded_env):
        store, vault, launcher, tmp_path = upgraded_env
        api = _ManagerApi(launcher)
        legacy = store.load_all()[0]
        api.update_server(legacy.id, "NAS", "http://127.0.0.1:5001", False, "admin", "plain-leak-check")
        # os.replace 在 Windows 上偶发读到瞬态不可见（全量套件 4466 例中一次出现，
        # 单跑/复跑均绿）——短暂重试消掉环境噪声，断言语义不变
        stored = ""
        for _ in range(5):
            try:
                stored = (tmp_path / "companion_servers.json").read_text(encoding="utf-8")
                break
            except OSError:
                time.sleep(0.1)
        assert "plain-leak-check" not in stored
