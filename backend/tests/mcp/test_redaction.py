# -*- coding: utf-8 -*-
"""MCP 脱敏层与泄漏扫描器回归（feature mcp-service-capabilities-2026-08-28 W2）。

按计划 §4.5 数据字典与 §7 测试矩阵（脱敏行）覆盖：

- tracker URL → hostname 归一（scheme/端口/路径/query/passkey/userinfo 全剥离）；
- 输入侧域名白名单（禁 ``/``、``?``、``#``、``@``、端口、passkey 载体）；
- 绝对路径 → pathDisplay（Windows 盘符/UNC/Linux 挂载根与父目录剥离）；
- 自由文本清洗（URL 凭据、完整 URL、敏感参数、三类绝对路径）；
- 输出 allowlist 点路径裁剪（裸键整树放行 / items.* 逐元素 / 白名单外丢弃）；
- 泄漏扫描器 canary 矩阵（嵌套集合、URL 编码 passkey、camel/snake 键、
  40/64 位 hex 哈希、bytes、无泄漏放行）；
- finalize 流水线（allowlist 后命中 = 实现缺陷级失败；1 MiB 预算整体失败）。

本文件不依赖 MCP SDK（脱敏层必须可在无 SDK 环境下被门禁加载）。
"""

import pytest

from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.redaction import (
    LeakScanError,
    apply_output_allowlist,
    finalize_tool_output,
    is_safe_tracker_domain,
    redact_free_text,
    redact_path_to_display,
    redact_tracker_url,
    scan_for_leaks,
)


class TestRedactTrackerUrl:
    def test_full_url_reduced_to_hostname(self):
        url = "https://tracker.example.org:8080/announce/xxx?passkey=deadbeef1234&other=1#frag"
        assert redact_tracker_url(url) == "tracker.example.org"

    def test_userinfo_and_port_stripped(self):
        assert redact_tracker_url("http://user:secret@tracker.io:6969/announce") == "tracker.io"

    def test_udp_scheme_stripped(self):
        assert redact_tracker_url("udp://tracker.net:1337/announce") == "tracker.net"

    def test_bare_domain_passthrough(self):
        assert redact_tracker_url("Tracker.Example.COM") == "tracker.example.com"

    def test_bare_domain_with_port_rejected(self):
        # 无 scheme 且带端口 → urlparse("//host:port") 的 hostname 仍可解析，
        # 端口剥离后 hostname 合法则归一（端口本身不外泄）
        assert redact_tracker_url("tracker.example.com:8080") == "tracker.example.com"

    def test_garbage_returns_none(self):
        assert redact_tracker_url("not a url at all") is None
        assert redact_tracker_url("://") is None
        assert redact_tracker_url("http://") is None

    def test_invalid_hostname_charset_returns_none(self):
        assert redact_tracker_url("http://bad_host.example/announce") is None

    def test_non_string_returns_none(self):
        assert redact_tracker_url(None) is None
        assert redact_tracker_url(12345) is None
        assert redact_tracker_url(b"https://tracker.example.org") is None

    def test_empty_returns_none(self):
        assert redact_tracker_url("") is None
        assert redact_tracker_url("   ") is None


class TestSafeTrackerDomain:
    @pytest.mark.parametrize(
        "value",
        ["tracker.example.org", "tracker.example.org.", "localhost", "xn--80ak6aa92e.com", "a.b.c.example.io"],
    )
    def test_valid_domains(self, value):
        assert is_safe_tracker_domain(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "https://tracker.example.org/announce",
            "tracker.example.org/announce?passkey=x",
            "tracker.example.org/announce#frag",
            "user@tracker.example.org",
            "user:pass@tracker.example.org",
            "tracker.example.org:8080",
            "tracker.example.org\\announce",
            "",
            "   ",
            "not a domain",
            "bad_host.example",
            None,
            123,
        ],
    )
    def test_rejected_inputs(self, value):
        assert is_safe_tracker_domain(value) is False


class TestRedactPathToDisplay:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("C:\\Downloads\\movies\\Some Movie", "Some Movie"),
            ("C:\\Downloads", "Downloads"),
            ("D:/data/torrents/iso", "iso"),
            ("\\\\NAS\\share\\torrents\\pack", "pack"),
            ("/home/btuser/downloads/ubuntu.iso", "ubuntu.iso"),
            ("/mnt/media/disk/series", "series"),
            ("/home/btuser/downloads/", "downloads"),
            ("bare-folder-name", "bare-folder-name"),
            ("C:\\", ""),
            ("\\\\NAS\\share", "share"),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_paths(self, path, expected):
        assert redact_path_to_display(path) == expected

    def test_non_string_returns_empty(self):
        assert redact_path_to_display(None) == ""
        assert redact_path_to_display(42) == ""


class TestRedactFreeText:
    def test_url_credentials_removed(self):
        text = "connect failed for http://admin:hunter2@qb.local:8080/api/v2"
        out = redact_free_text(text)
        assert "hunter2" not in out
        assert "admin:" not in out
        assert "[REDACTED]" in out

    def test_full_url_removed(self):
        out = redact_free_text("tracker error: https://t.example.org/announce returned 500")
        assert "t.example.org" not in out
        assert "[REDACTED-URL]" in out

    def test_sensitive_params_removed(self):
        out = redact_free_text("announce rejected: passkey=abcdef0123456789&uid=42")
        assert "abcdef0123456789" not in out
        assert "[REDACTED]" in out

    def test_windows_and_unix_paths_removed(self):
        out = redact_free_text("save path C:\\Downloads\\secret failed; retry /home/btuser/x")
        assert "C:\\Downloads" not in out
        assert "/home/btuser" not in out
        assert "[REDACTED-PATH]" in out

    def test_unc_path_removed(self):
        out = redact_free_text("cannot write \\\\NAS\\share\\torrents\\file.iso")
        assert "NAS" not in out
        assert "[REDACTED-PATH]" in out

    def test_clean_text_unchanged(self):
        text = "下载器返回超时（30s），任务保持原状态"
        assert redact_free_text(text) == text

    def test_non_string_returns_empty(self):
        assert redact_free_text(None) == ""
        assert redact_free_text(ValueError("boom")) == ""


class TestApplyOutputAllowlist:
    def test_extra_top_level_keys_dropped(self):
        payload = {
            "total": 1,
            "page": 1,
            "page_size": 20,
            "save_path": "C:\\Downloads\\x",  # 白名单外：整体丢弃（不允许靠过滤救回）
            "items": [],
        }
        out = apply_output_allowlist("torrent_advanced_search", payload)
        assert out == {"total": 1, "page": 1, "page_size": 20, "items": []}

    def test_items_element_fields_filtered(self):
        payload = {
            "total": 1,
            "items": [
                {
                    "info_id": 11,
                    "name": "ubuntu",
                    "hash": "a" * 40,  # 子路径白名单外
                    "save_path": "C:\\x",  # 子路径白名单外
                    "tracker_url": "https://t.org/a?passkey=z",  # 子路径白名单外
                }
            ],
        }
        out = apply_output_allowlist("torrent_advanced_search", payload)
        assert out["items"] == [{"info_id": 11, "name": "ubuntu"}]

    def test_bare_key_whole_subtree_allowed(self):
        payload = {
            "generated_at": "2026-09-08T00:00:00Z",
            "totals": {"downloading": 2, "seeding": 10},
            "status_counts": {"active": 3},
            "downloader_host": "10.0.0.5",  # 顶层白名单外
        }
        out = apply_output_allowlist("dashboard_get", payload)
        assert out["totals"] == {"downloading": 2, "seeding": 10}
        assert out["status_counts"] == {"active": 3}
        assert "downloader_host" not in out

    def test_unknown_tool_rejected(self):
        with pytest.raises(McpToolError) as exc:
            apply_output_allowlist("no_such_tool", {"a": 1})
        assert exc.value.code is McpErrorCode.INTERNAL_ERROR

    def test_non_dict_payload_rejected(self):
        with pytest.raises(McpToolError):
            apply_output_allowlist("dashboard_get", ["not", "a", "dict"])


class TestScanForLeaks:
    def test_clean_payload_no_findings(self):
        payload = {
            "total": 3,
            "items": [
                {"info_id": 1, "name": "ubuntu", "tracker_domains": ["tracker.example.org"], "path_display": "ubuntu"}
            ],
        }
        assert scan_for_leaks(payload) == []

    def test_nested_url_leak_found_with_path(self):
        payload = {"items": [{"tracker_domains": ["https://tracker.example.org/announce?passkey=z"]}]}
        findings = scan_for_leaks(payload)
        assert any(f.endswith(": url") for f in findings)
        assert "$.items[0]" in findings[0]

    def test_url_encoded_passkey_detected(self):
        assert scan_for_leaks({"note": "passkey%3Dabcdef0123456789"}) != []
        assert scan_for_leaks({"note": "announce?passkey%3Dabcdef0123456789"}) != []

    def test_plain_passkey_param_detected(self):
        findings = scan_for_leaks({"x": "http://t.org/announce?passkey=abc123"})
        assert any(": sensitive_param" in f or ": url" in f for f in findings)

    def test_camel_case_keys_do_not_hide_values(self):
        findings = scan_for_leaks({"trackerUrl": "https://t.example.org/announce"})
        assert findings

    def test_windows_drive_path_detected(self):
        assert scan_for_leaks({"pathDisplay": "C:\\Downloads\\ubuntu"}) != []

    def test_unc_path_detected(self):
        assert scan_for_leaks({"note": "\\\\NAS\\share\\torrents"}) != []

    def test_unix_abs_path_detected(self):
        assert scan_for_leaks({"note": "saved to /home/btuser/downloads/x"}) != []

    def test_torrent_hash_detected(self):
        assert scan_for_leaks({"hash": "a" * 40}) != []
        assert scan_for_leaks({"hash": "b" * 64}) != []
        # 短 hex（info_id 序列化形态）不误报
        assert scan_for_leaks({"hash": "abcd1234"}) == []

    def test_bytes_flagged(self):
        assert scan_for_leaks({"blob": b"\x00\x01"}) != []

    def test_numbers_and_bools_not_flagged(self):
        assert scan_for_leaks({"a": 1, "b": 1.5, "c": True, "d": None, "e": [1, 2, 3]}) == []


class TestFinalizeToolOutput:
    def _search_payload(self, items):
        return {"total": len(items), "page": 1, "page_size": 20, "items": items}

    def test_success_returns_sanitized(self):
        payload = self._search_payload([{"info_id": 1, "name": "ubuntu", "hash": "c" * 40, "save_path": "C:\\x"}])
        out = finalize_tool_output("torrent_advanced_search", payload)
        assert out["items"] == [{"info_id": 1, "name": "ubuntu"}]

    def test_leak_inside_allowlisted_field_fails_whole_call(self):
        # allowlist 内字段携带泄漏（实现把 URL 放进了 tracker_domains）→ 整体失败
        payload = self._search_payload([{"info_id": 1, "tracker_domains": ["https://t.org/announce?passkey=z"]}])
        with pytest.raises(LeakScanError) as exc:
            finalize_tool_output("torrent_advanced_search", payload)
        assert exc.value.code is McpErrorCode.INTERNAL_ERROR
        assert exc.value.findings

    def test_result_too_large_rejected(self):
        big_name = "x" * 64
        items = [{"info_id": i, "name": big_name} for i in range(40_000)]
        with pytest.raises(McpToolError) as exc:
            finalize_tool_output("torrent_advanced_search", self._search_payload(items))
        assert exc.value.code is McpErrorCode.RESULT_TOO_LARGE

    def test_result_under_budget_passes(self):
        items = [{"info_id": i, "name": f"torrent-{i}"} for i in range(100)]
        out = finalize_tool_output("torrent_advanced_search", self._search_payload(items))
        assert out["total"] == 100
