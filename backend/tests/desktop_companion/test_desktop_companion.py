# -*- coding: utf-8 -*-
"""desktop_companion 契约测试：hosts / lan_policy / profiles / 模式持久化。

语义对齐安卓端 com.btdeck.companion（Hosts/LanHostPolicy/ServerProfileStore），
重点锁 fail-closed 行为：公网明文拒绝、未知状态回退、损坏文件容错。
"""

import json

from app.desktop_companion import lan_policy
from app.desktop_companion.hosts import is_private_lan_host, parse_url
from app.desktop_companion.launcher import (
    MODE_COMPANION,
    MODE_SERVER,
    clear_stored_mode,
    load_stored_mode,
    resolve_launch_mode,
    save_stored_mode,
)
from app.desktop_companion.profiles import (
    HEALTH_READY,
    HEALTH_UNKNOWN,
    ServerProfile,
    ServerProfileStore,
)


# ============ hosts.parse_url ============


class TestParseUrl:
    def test_http_with_port_and_path(self):
        parsed = parse_url("http://192.168.1.10:5001/console#/x?q=1")
        assert parsed is not None
        assert parsed.scheme == "http"
        assert parsed.host == "192.168.1.10"
        assert parsed.port == 5001
        assert parsed.base_url == "http://192.168.1.10:5001"

    def test_default_ports_normalized(self):
        assert parse_url("http://example.com:80").base_url == "http://example.com"
        assert parse_url("https://example.com:443").base_url == "https://example.com"
        assert parse_url("https://example.com:8443").base_url == "https://example.com:8443"

    def test_case_normalization(self):
        parsed = parse_url("HTTPS://Example.COM/")
        assert parsed is not None
        assert parsed.scheme == "https"
        assert parsed.host == "example.com"

    def test_ipv6_literal(self):
        parsed = parse_url("http://[::1]:8080/path")
        assert parsed is not None
        assert parsed.host == "::1"
        assert parsed.port == 8080
        assert parsed.base_url == "http://[::1]:8080"

    def test_invalid(self):
        assert parse_url("") is None
        assert parse_url("   ") is None
        assert parse_url("192.168.1.10:5001") is None  # 无 scheme
        assert parse_url("ftp://example.com") is None
        assert parse_url("http://") is None
        assert parse_url("http://host:notaport") is None
        assert parse_url("http://host:99999") is None


class TestIsPrivateLanHost:
    def test_private_literals(self):
        for host in [
            "localhost",
            "nas.local",
            "127.0.0.1",
            "10.1.2.3",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.5.51",
            "169.254.10.10",
            "::1",
            "fc00::1",
            "fd12:3456::1",
            "fe80::1",
        ]:
            assert is_private_lan_host(host), host

    def test_public_literals(self):
        for host in [
            "example.com",
            "8.8.8.8",
            "172.32.0.1",  # RFC1918 边界外
            "172.15.0.1",
            "2001:db8::1",
            "my-server",
        ]:
            assert not is_private_lan_host(host), host


# ============ lan_policy ============


class TestLanPolicy:
    def test_https_always_ok(self):
        verdict = lan_policy.check("https://example.com", cleartext_consent=False)
        assert verdict.ok
        assert verdict.parsed is not None
        assert verdict.parsed.base_url == "https://example.com"

    def test_http_private_with_consent_ok(self):
        verdict = lan_policy.check("http://192.168.5.51:5001", cleartext_consent=True)
        assert verdict.ok

    def test_http_private_without_consent_rejected(self):
        verdict = lan_policy.check("http://192.168.5.51:5001", cleartext_consent=False)
        assert not verdict.ok
        assert verdict.reason is lan_policy.RejectReason.HTTP_LAN_WITHOUT_CONSENT

    def test_http_public_rejected_even_with_consent(self):
        verdict = lan_policy.check("http://example.com", cleartext_consent=True)
        assert not verdict.ok
        assert verdict.reason is lan_policy.RejectReason.HTTP_PUBLIC_HOST

    def test_malformed_url(self):
        verdict = lan_policy.check("not-a-url", cleartext_consent=True)
        assert not verdict.ok
        assert verdict.reason is lan_policy.RejectReason.MALFORMED_URL
        assert "地址无效" in lan_policy.REJECT_MESSAGES[verdict.reason]

    def test_needs_cleartext_consent(self):
        assert lan_policy.needs_cleartext_consent("http://10.0.0.5:5001")
        assert not lan_policy.needs_cleartext_consent("https://10.0.0.5:5001")
        assert not lan_policy.needs_cleartext_consent("http://example.com")
        assert not lan_policy.needs_cleartext_consent("bad")


# ============ profiles ============


class TestServerProfileStore:
    def test_roundtrip_upsert_and_remove(self, tmp_path):
        store = ServerProfileStore(tmp_path / "servers.json")
        assert store.load_all() == []

        profile = ServerProfile(
            display_name="NAS",
            base_url="http://192.168.5.51:5001",
            health_state=HEALTH_READY,
            server_version="1.0.5",
        )
        store.upsert(profile)

        loaded = store.load_all()
        assert len(loaded) == 1
        assert loaded[0].display_name == "NAS"
        assert loaded[0].health_state == HEALTH_READY
        assert loaded[0].server_version == "1.0.5"
        assert loaded[0].id == profile.id

        # upsert 同 id 覆盖不重复
        profile.health_state = "UNREACHABLE"
        store.upsert(profile)
        assert len(store.load_all()) == 1

        assert store.remove(profile.id) is True
        assert store.load_all() == []
        assert store.remove(profile.id) is False

    def test_json_keys_align_with_android(self, tmp_path):
        """持久化键名与安卓 ServerProfile.toJson 对齐（displayName/baseUrl/...）。"""
        store = ServerProfileStore(tmp_path / "servers.json")
        profile = ServerProfile(display_name="NAS", base_url="http://10.0.0.5:5001")
        store.upsert(profile)
        raw = json.loads((tmp_path / "servers.json").read_text(encoding="utf-8"))
        assert set(raw[0].keys()) == {
            "id",
            "displayName",
            "baseUrl",
            "cleartextAllowed",
            "healthState",
            "serverVersion",
            "lastHealthCheckedAt",
            "lastConnectedAt",
        }

    def test_from_json_tolerates_dirty_data(self):
        profile = ServerProfile.from_json(
            {
                "displayName": "旧数据",
                "baseUrl": "http://10.0.0.5",
                "healthState": "SOMETHING_NEW",
            }
        )
        assert profile.health_state == HEALTH_UNKNOWN
        assert len(profile.id) == 32  # 缺 id 时生成 uuid hex

    def test_corrupted_file_returns_empty(self, tmp_path):
        path = tmp_path / "servers.json"
        path.write_text("{not json", encoding="utf-8")
        assert ServerProfileStore(path).load_all() == []

        path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        assert ServerProfileStore(path).load_all() == []


# ============ 模式持久化与解析 ============


class TestModePersistence:
    def test_save_load_clear_roundtrip(self, tmp_path):
        mode_path = tmp_path / "desktop_mode.json"
        assert load_stored_mode(mode_path) is None

        save_stored_mode(MODE_COMPANION, mode_path)
        assert load_stored_mode(mode_path) == MODE_COMPANION

        clear_stored_mode(mode_path)
        assert load_stored_mode(mode_path) is None

    def test_invalid_stored_value_ignored(self, tmp_path):
        mode_path = tmp_path / "desktop_mode.json"
        mode_path.write_text(json.dumps({"mode": "whatever"}), encoding="utf-8")
        assert load_stored_mode(mode_path) is None

    def test_env_overrides_stored(self, tmp_path, monkeypatch):
        mode_path = tmp_path / "desktop_mode.json"
        save_stored_mode(MODE_SERVER, mode_path)

        monkeypatch.setenv("BTDECK_MODE", "companion")
        assert resolve_launch_mode(mode_path) == MODE_COMPANION

        monkeypatch.setenv("BTDECK_MODE", "SERVER ")
        assert resolve_launch_mode(mode_path) == MODE_SERVER

        monkeypatch.delenv("BTDECK_MODE")
        assert resolve_launch_mode(mode_path) == MODE_SERVER

        monkeypatch.setenv("BTDECK_MODE", "bogus")
        assert resolve_launch_mode(mode_path) == MODE_SERVER  # 非法环境值回落记录
