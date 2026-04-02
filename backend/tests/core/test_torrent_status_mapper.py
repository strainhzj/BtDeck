"""
TorrentStatusMapper 种子状态映射器单元测试

测试 qBittorrent 和 Transmission 状态转换逻辑，覆盖所有映射规则、
未知状态 fallback、以及映射规则副本返回。所有测试均为纯函数测试，无外部依赖。
"""

import pytest
from app.core.torrent_status_mapper import TorrentStatusMapper


# ============================================================
# qBittorrent 状态映射测试
# ============================================================

class TestQBittorrentStatusMapping:
    """qBittorrent 状态映射测试"""

    @pytest.mark.parametrize("input_status,expected", [
        # 上传相关状态 -> seeding
        ("stalledUP", "seeding"),
        ("seeding", "seeding"),
        ("queuedUP", "seeding"),
        ("uploading", "seeding"),
        # 上传暂停保持不变
        ("pausedUP", "pausedUP"),
        # 下载相关状态
        ("stalledDL", "downloading"),
        # 下载暂停保持不变
        ("pausedDL", "pausedDL"),
        # 检查状态保持不变
        ("checkingDL", "checkingDL"),
        ("checkingUP", "checkingUP"),
        # 队列状态保持不变
        ("queuedDL", "queuedDL"),
        # 基本状态保持不变
        ("downloading", "downloading"),
        ("paused", "paused"),
        ("error", "error"),
        ("unknown", "unknown"),
        # 未知状态 -> fallback 返回原值
        ("completely_new_status", "completely_new_status"),
    ])
    def test_qbittorrent状态映射(self, input_status, expected):
        """验证 qBittorrent 状态映射规则"""
        result = TorrentStatusMapper.convert_qbittorrent_status(input_status)
        assert result == expected

    def test_空字符串fallback(self):
        """空字符串 fallback 返回原值"""
        assert TorrentStatusMapper.convert_qbittorrent_status("") == ""

    def test_大小写敏感(self):
        """映射是大小写敏感的，Seeding 不等于 seeding"""
        # "Seeding" 不在映射表中，应返回原值
        assert TorrentStatusMapper.convert_qbittorrent_status("Seeding") == "Seeding"

    def test_映射表完整性(self):
        """验证映射表包含所有预期的键"""
        expected_keys = {
            "stalledUP", "seeding", "queuedUP", "uploading", "pausedUP",
            "stalledDL", "pausedDL",
            "checkingDL", "checkingUP",
            "queuedDL",
            "downloading", "paused", "error", "unknown"
        }
        actual_keys = set(TorrentStatusMapper.QBITTORRENT_STATUS_MAP.keys())
        assert actual_keys == expected_keys

    def test_映射值中seeding的数量(self):
        """验证映射到 'seeding' 的状态数量"""
        seeding_sources = [
            k for k, v in TorrentStatusMapper.QBITTORRENT_STATUS_MAP.items()
            if v == "seeding"
        ]
        assert len(seeding_sources) == 4  # stalledUP, seeding, queuedUP, uploading


# ============================================================
# Transmission 状态映射测试
# ============================================================

class TestTransmissionStatusMapping:
    """Transmission 状态映射测试"""

    @pytest.mark.parametrize("input_status,expected", [
        ("stopped", "paused"),
        ("check pending", "checking"),
        ("checking", "checking"),
        ("download pending", "downloading"),
        ("downloading", "downloading"),
        ("seed pending", "seeding"),
        ("seeding", "seeding"),
        # 未知状态 fallback
        ("unknown_status", "unknown_status"),
    ])
    def test_transmission状态映射(self, input_status, expected):
        """验证 Transmission 状态映射规则"""
        result = TorrentStatusMapper.convert_transmission_status(input_status)
        assert result == expected

    def test_空字符串fallback(self):
        """空字符串 fallback 返回原值"""
        assert TorrentStatusMapper.convert_transmission_status("") == ""

    def test_映射表完整性(self):
        """验证映射表包含所有预期的键"""
        expected_keys = {
            "stopped", "check pending", "checking",
            "download pending", "downloading",
            "seed pending", "seeding"
        }
        actual_keys = set(TorrentStatusMapper.TRANSMISSION_STATUS_MAP.keys())
        assert actual_keys == expected_keys

    def test_映射值去重后覆盖范围(self):
        """验证所有可能的映射目标值"""
        all_values = set(TorrentStatusMapper.TRANSMISSION_STATUS_MAP.values())
        expected_values = {"paused", "checking", "downloading", "seeding"}
        assert all_values == expected_values


# ============================================================
# get_mapping_rules 返回副本测试
# ============================================================

class TestGetMappingRules:
    """获取映射规则方法测试"""

    def test_get_qbittorrent_mapping_rules返回副本(self):
        """get_qbittorrent_mapping_rules 返回字典副本"""
        rules1 = TorrentStatusMapper.get_qbittorrent_mapping_rules()
        rules2 = TorrentStatusMapper.get_qbittorrent_mapping_rules()
        # 两次调用返回不同对象
        assert rules1 is not rules2
        # 但内容相同
        assert rules1 == rules2

    def test_get_qbittorrent_mapping_rules修改不影响原表(self):
        """修改返回的副本不影响原始映射表"""
        rules = TorrentStatusMapper.get_qbittorrent_mapping_rules()
        original_count = len(rules)
        rules["fake_status"] = "fake_value"
        # 原始表不应被修改
        assert "fake_status" not in TorrentStatusMapper.QBITTORRENT_STATUS_MAP
        assert len(TorrentStatusMapper.QBITTORRENT_STATUS_MAP) == original_count

    def test_get_transmission_mapping_rules返回副本(self):
        """get_transmission_mapping_rules 返回字典副本"""
        rules1 = TorrentStatusMapper.get_transmission_mapping_rules()
        rules2 = TorrentStatusMapper.get_transmission_mapping_rules()
        assert rules1 is not rules2
        assert rules1 == rules2

    def test_get_transmission_mapping_rules修改不影响原表(self):
        """修改返回的副本不影响原始映射表"""
        rules = TorrentStatusMapper.get_transmission_mapping_rules()
        original_count = len(rules)
        rules["fake_status"] = "fake_value"
        assert "fake_status" not in TorrentStatusMapper.TRANSMISSION_STATUS_MAP
        assert len(TorrentStatusMapper.TRANSMISSION_STATUS_MAP) == original_count

    def test_qbittorrent规则内容与映射表一致(self):
        """返回的规则内容与原始映射表完全一致"""
        rules = TorrentStatusMapper.get_qbittorrent_mapping_rules()
        assert rules == TorrentStatusMapper.QBITTORRENT_STATUS_MAP

    def test_transmission规则内容与映射表一致(self):
        """返回的规则内容与原始映射表完全一致"""
        rules = TorrentStatusMapper.get_transmission_mapping_rules()
        assert rules == TorrentStatusMapper.TRANSMISSION_STATUS_MAP
