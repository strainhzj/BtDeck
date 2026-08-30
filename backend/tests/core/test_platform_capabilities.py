# -*- coding: utf-8 -*-
"""主机能力矩阵单元测试（dual-mode-client Phase 4 批次 A）。

锁定内容（docs/android/host-capability-matrix.md 冻结基线）：
- 矩阵键集：14 项能力，新增能力必须先登记文档（键集变化即红）；
- 每项两形态级别均为合法枚举，非 supported 必须带 note（UI 降级说明来源）；
- 两形态已知差异点（unsupported/degraded 项）；
- resolve_platform 的 fail-safe 语义（未设置/非法值回落 desktop）；
- capability_payload 载荷形状与降级计数。
"""

import pytest

from app.core.platform_capabilities import (
    CAPABILITY_DEFINITIONS,
    LEVEL_DEGRADED,
    LEVEL_SUPPORTED,
    LEVEL_UNSUPPORTED,
    PLATFORM_ANDROID_SERVER,
    PLATFORM_DESKTOP,
    VALID_PLATFORMS,
    capability_level,
    capability_payload,
    get_capability_matrix,
    resolve_platform,
)

EXPECTED_KEYS = {
    "downloader_management",
    "torrent_crud",
    "tracker_management",
    "advanced_search",
    "audit_export",
    "custom_scripts",
    "shell_capabilities",
    "host_filesystem",
    "saf_file_access",
    "torrent_file_transfer",
    "system_notifications",
    "scheduled_tasks",
    "local_server",
    "always_on_service",
}

# 矩阵冻结基线的两形态差异点（矩阵文档第 2 节逐行对照）
ANDROID_UNSUPPORTED = {
    "custom_scripts",
    "shell_capabilities",
    "always_on_service",
}
ANDROID_DEGRADED = {
    "host_filesystem",
    "saf_file_access",
    "torrent_file_transfer",
    "system_notifications",
    "scheduled_tasks",
}


class TestMatrixIntegrity:
    def test_keyset_frozen_14_items(self):
        """键集 = 冻结基线 14 项；新增能力未登记文档即红。"""
        assert set(CAPABILITY_DEFINITIONS.keys()) == EXPECTED_KEYS

    @pytest.mark.parametrize("platform", sorted(VALID_PLATFORMS))
    def test_every_capability_has_valid_level_and_label(self, platform):
        matrix = get_capability_matrix(platform)
        assert len(matrix) == 14
        for key, entry in matrix.items():
            assert entry["level"] in {LEVEL_SUPPORTED, LEVEL_DEGRADED, LEVEL_UNSUPPORTED}, key
            assert entry["label"], key

    @pytest.mark.parametrize("platform", sorted(VALID_PLATFORMS))
    def test_non_supported_entries_carry_note(self, platform):
        """降级/不支持项必须带说明（UI 一致降级的文案来源）。"""
        matrix = get_capability_matrix(platform)
        for key, entry in matrix.items():
            if entry["level"] != LEVEL_SUPPORTED:
                assert entry.get("note"), f"{key}@{platform} 缺降级说明"

    def test_desktop_is_full_capability_except_none(self):
        """desktop 是能力全集（矩阵产品基线）。"""
        matrix = get_capability_matrix(PLATFORM_DESKTOP)
        assert all(e["level"] == LEVEL_SUPPORTED for e in matrix.values())

    def test_android_server_known_diffs(self):
        matrix = get_capability_matrix(PLATFORM_ANDROID_SERVER)
        assert {k for k, e in matrix.items() if e["level"] == LEVEL_UNSUPPORTED} == ANDROID_UNSUPPORTED
        assert {k for k, e in matrix.items() if e["level"] == LEVEL_DEGRADED} == ANDROID_DEGRADED


class TestResolvePlatform:
    def test_default_desktop(self, monkeypatch):
        monkeypatch.delenv("BTDECK_PLATFORM", raising=False)
        assert resolve_platform() == PLATFORM_DESKTOP

    @pytest.mark.parametrize("raw", ["", "android", "ios", "123", "server"])
    def test_illegal_values_fallback_desktop(self, monkeypatch, raw):
        """fail-safe：非法值回落 desktop（能力全集方向，只会在漏注入时少降级）。"""
        monkeypatch.setenv("BTDECK_PLATFORM", raw)
        assert resolve_platform() == PLATFORM_DESKTOP

    def test_case_insensitive_passthrough(self, monkeypatch):
        """大小写宽容：ANDROID-SERVER 仍按 android-server 降级（漏大小写不能装成 desktop）。"""
        monkeypatch.setenv("BTDECK_PLATFORM", "ANDROID-SERVER")
        assert resolve_platform() == PLATFORM_ANDROID_SERVER

    def test_android_server_passthrough(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "android-server")
        assert resolve_platform() == PLATFORM_ANDROID_SERVER

    def test_unknown_platform_raises_in_matrix(self):
        with pytest.raises(ValueError):
            get_capability_matrix("watch")


class TestPayloadAndLevel:
    def test_payload_shape_and_counts(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "android-server")
        payload = capability_payload()
        assert payload["platform"] == PLATFORM_ANDROID_SERVER
        assert payload["degradedCount"] == len(ANDROID_DEGRADED)
        assert payload["unsupportedCount"] == len(ANDROID_UNSUPPORTED)
        assert set(payload["capabilities"].keys()) == EXPECTED_KEYS

    def test_capability_level_query(self, monkeypatch):
        monkeypatch.setenv("BTDECK_PLATFORM", "android-server")
        assert capability_level("custom_scripts") == LEVEL_UNSUPPORTED
        assert capability_level("scheduled_tasks") == LEVEL_DEGRADED

    def test_capability_level_unknown_key_raises(self):
        with pytest.raises(KeyError):
            capability_level("not_registered_capability")
