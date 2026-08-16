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

    @pytest.mark.parametrize(
        "input_status,expected",
        [
            # 上传相关状态 -> seeding
            ("stalledUP", "seeding"),
            ("seeding", "seeding"),
            ("queuedUP", "seeding"),
            ("uploading", "seeding"),
            ("forcedUP", "seeding"),
            # 上传暂停保持不变
            ("pausedUP", "pausedUP"),
            # 下载相关状态
            ("stalledDL", "downloading"),
            ("metaDL", "downloading"),
            ("forcedMetaDL", "downloading"),
            ("allocating", "downloading"),
            ("forcedDL", "downloading"),
            # 下载暂停保持不变
            ("pausedDL", "pausedDL"),
            # 检查状态保持不变
            ("checkingDL", "checkingDL"),
            ("checkingUP", "checkingUP"),
            ("checkingResumeData", "checkingDL"),
            # 队列状态保持不变
            ("queuedDL", "queuedDL"),
            # 基本状态保持不变
            ("downloading", "downloading"),
            ("paused", "paused"),
            ("error", "error"),
            ("unknown", "unknown"),
            # 数据文件缺失归入错误
            ("missingFiles", "error"),
            # 未知状态 -> fallback 返回原值
            ("completely_new_status", "completely_new_status"),
        ],
    )
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
            "stalledUP",
            "seeding",
            "queuedUP",
            "uploading",
            "forcedUP",
            "pausedUP",
            "stalledDL",
            "metaDL",
            "forcedMetaDL",
            "allocating",
            "forcedDL",
            "pausedDL",
            "checkingDL",
            "checkingUP",
            "checkingResumeData",
            "queuedDL",
            "downloading",
            "paused",
            "error",
            "missingFiles",
            "unknown",
        }
        actual_keys = set(TorrentStatusMapper.QBITTORRENT_STATUS_MAP.keys())
        assert actual_keys == expected_keys

    def test_映射值中seeding的数量(self):
        """验证映射到 'seeding' 的状态数量"""
        seeding_sources = [k for k, v in TorrentStatusMapper.QBITTORRENT_STATUS_MAP.items() if v == "seeding"]
        assert len(seeding_sources) == 5  # stalledUP, seeding, queuedUP, uploading, forcedUP


# ============================================================
# Transmission 状态映射测试
# ============================================================


class TestTransmissionStatusMapping:
    """Transmission 状态映射测试"""

    @pytest.mark.parametrize(
        "input_status,expected",
        [
            ("stopped", "paused"),
            ("check pending", "checking"),
            ("checking", "checking"),
            ("download pending", "downloading"),
            ("downloading", "downloading"),
            ("seed pending", "seeding"),
            ("seeding", "seeding"),
            # 未知状态 fallback
            ("unknown_status", "unknown_status"),
        ],
    )
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
            "stopped",
            "check pending",
            "checking",
            "download pending",
            "downloading",
            "seed pending",
            "seeding",
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


# ============================================================
# resolve_transmission_status 联合 error 字段判定测试
# ============================================================


class TestTransmissionErrorStateMapping:
    """resolve_transmission_status：状态 + error 字段联合判定测试。

    Transmission 的 error 字段语义：0=ok, 1=tracker 警告, 2=tracker 错误, 3=本地错误。
    error>=2 应归入 "error"，与前端 status="error" 标签对齐。
    """

    @pytest.mark.parametrize("tr_status", ["downloading", "seeding", "stopped", "seed pending", "download pending"])
    def test_error严重错误映射为error(self, tr_status):
        """error=2(tracker错误)/3(本地错误) 应覆盖 status 映射为 "error" """
        assert TorrentStatusMapper.resolve_transmission_status(tr_status, 2) == "error"
        assert TorrentStatusMapper.resolve_transmission_status(tr_status, 3) == "error"

    @pytest.mark.parametrize(
        "input_status,expected",
        [
            ("stopped", "paused"),
            ("downloading", "downloading"),
            ("seeding", "seeding"),
            ("seed pending", "seeding"),
        ],
    )
    def test_error正常回退查表(self, input_status, expected):
        """error=0 正常时回退 convert_transmission_status 查表"""
        assert TorrentStatusMapper.resolve_transmission_status(input_status, 0) == expected

    def test_error1tracker警告不归入error(self):
        """error=1(tracker警告)不触发 error，回退查表"""
        assert TorrentStatusMapper.resolve_transmission_status("seeding", 1) == "seeding"
        assert TorrentStatusMapper.resolve_transmission_status("downloading", 1) == "downloading"

    @pytest.mark.parametrize("invalid_error", [None, "2", 2.0, "error"])
    def test_error非整数容错回退(self, invalid_error):
        """非 int 的 error 值按 0 处理，回退查表（规避 KeyError/MagicMock 陷阱）"""
        assert TorrentStatusMapper.resolve_transmission_status("seeding", invalid_error) == "seeding"

    def test_checking状态优先于error(self):
        """校验中(checking)状态优先，不被 tracker 错误掩盖为 error"""
        # "checking"/"check pending" 都映射到 "checking"，校验过程中 tracker 报错仍显示校验中
        assert TorrentStatusMapper.resolve_transmission_status("checking", 2) == "checking"
        assert TorrentStatusMapper.resolve_transmission_status("check pending", 3) == "checking"

    def test_error优先于空状态(self):
        """error>=2 即使 status 为空也归入 error"""
        assert TorrentStatusMapper.resolve_transmission_status("", 2) == "error"

    def test_error严重错误的真实场景组合(self):
        """覆盖常见真实场景：做种中报本地错误、下载中报 tracker 错误"""
        # 做种中 + 磁盘满(本地错误)
        assert TorrentStatusMapper.resolve_transmission_status("seeding", 3) == "error"
        # 下载中 + tracker 错误
        assert TorrentStatusMapper.resolve_transmission_status("downloading", 2) == "error"
