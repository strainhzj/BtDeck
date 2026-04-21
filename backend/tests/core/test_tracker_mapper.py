"""
Tracker状态映射模块单元测试

测试 tracker_mapper 的核心功能：
- extract_tracker_host: 从 URL 提取主机名
- map_qbittorrent_tracker_status: qBittorrent 状态值映射
- map_transmission_tracker_status: Transmission 状态值映射
- map_qbittorrent_tracker: qBittorrent 完整 tracker 映射
- map_transmission_tracker: Transmission 完整 tracker 映射
- refresh_judgment_engine_cache: 缓存刷新代理
- get_judgment_engine_stats: 缓存统计代理
"""

from unittest.mock import MagicMock, patch

import pytest


# 在导入 tracker_mapper 之前 mock 掉数据库连接（因为 tracker_mapper 导入 tracker_judgment）
with patch("app.core.tracker_judgment.SessionLocal"):
    from app.core.tracker_mapper import (
        extract_tracker_host,
        get_judgment_engine_stats,
        map_qbittorrent_tracker,
        map_qbittorrent_tracker_status,
        map_transmission_tracker,
        map_transmission_tracker_status,
        refresh_judgment_engine_cache,
    )
    from app.core.tracker_judgment import TrackerStatus


# ============================================================
# Test extract_tracker_host
# ============================================================


class TestExtractTrackerHost:
    """从 tracker URL 提取主机名测试"""

    @pytest.mark.parametrize(
        "url, expected",
        [
            ("http://tracker.example.com:8080/announce", "tracker.example.com:8080"),
            ("https://tracker.example.com/announce", "tracker.example.com"),
            ("udp://tracker.example.com:6969", "tracker.example.com:6969"),
        ],
    )
    def test_标准URL提取主机名(self, url, expected):
        """标准 URL 正确提取主机名（含端口）"""
        result = extract_tracker_host(url)
        assert result == expected

    def test_带路径的URL(self):
        """URL 带复杂路径时正确提取主机名"""
        result = extract_tracker_host("http://tracker.pterclub.com/announce.php")
        assert result == "tracker.pterclub.com"

    def test_空字符串返回Unknown(self):
        """空字符串返回 'Unknown'"""
        assert extract_tracker_host("") == "Unknown"

    def test_None返回Unknown(self):
        """None 值返回 'Unknown'"""
        assert extract_tracker_host(None) == "Unknown"

    def test_纯IP地址(self):
        """纯 IP 地址正确提取"""
        result = extract_tracker_host("http://192.168.1.1:8080/announce")
        assert result == "192.168.1.1:8080"

    def test_https协议(self):
        """HTTPS 协议正确解析"""
        result = extract_tracker_host("https://secure.tracker.io/announce")
        assert result == "secure.tracker.io"

    def test_无协议URL返回Unknown(self):
        """无协议前缀的 URL 返回 'Unknown'（urlparse 无法解析）"""
        result = extract_tracker_host("tracker.example.com/announce")
        # urlparse 对无协议的字符串，netloc 为空，hostname 也为空
        assert result == "Unknown"

    def test_异常情况返回Unknown(self):
        """解析异常时返回 'Unknown'"""
        # 传入特殊类型触发异常
        result = extract_tracker_host(12345)
        assert result == "Unknown"


# ============================================================
# Test map_qbittorrent_tracker_status
# ============================================================


class TestMapQbittorrentTrackerStatus:
    """qBittorrent 状态值映射测试"""

    @pytest.mark.parametrize(
        "status, expected",
        [
            (0, TrackerStatus.DISABLED),       # 已禁用
            (1, TrackerStatus.NOT_CONTACTED),   # 未联系
            (2, TrackerStatus.WORKING),          # 工作中
            (3, TrackerStatus.FAILED),           # 工作失败
            (4, TrackerStatus.NOT_CONTACTED),    # 超时 → 未联系
        ],
    )
    def test_所有状态值映射(self, status, expected):
        """qBittorrent 状态 0-4 正确映射"""
        assert map_qbittorrent_tracker_status(status) == expected

    def test_未知状态值回退到未联系(self):
        """未知状态值默认返回 '未联系'"""
        assert map_qbittorrent_tracker_status(99) == TrackerStatus.NOT_CONTACTED
        assert map_qbittorrent_tracker_status(-1) == TrackerStatus.NOT_CONTACTED


# ============================================================
# Test map_transmission_tracker_status
# ============================================================


class TestMapTransmissionTrackerStatus:
    """Transmission 状态值映射测试"""

    @pytest.mark.parametrize(
        "status, expected",
        [
            (0, TrackerStatus.NOT_CONTACTED),  # 未联系
            (1, TrackerStatus.NOT_CONTACTED),  # 发送中 → 未联系
            (2, TrackerStatus.WORKING),        # 工作中
            (3, TrackerStatus.FAILED),         # 工作失败
            (4, TrackerStatus.NOT_CONTACTED),  # 超时 → 未联系
            (5, TrackerStatus.DISABLED),       # 已清除 → 已禁用
        ],
    )
    def test_所有状态值映射(self, status, expected):
        """Transmission 状态 0-5 正确映射"""
        assert map_transmission_tracker_status(status) == expected

    def test_未知状态值回退到未联系(self):
        """未知状态值默认返回 '未联系'"""
        assert map_transmission_tracker_status(99) == TrackerStatus.NOT_CONTACTED
        assert map_transmission_tracker_status(-1) == TrackerStatus.NOT_CONTACTED


# ============================================================
# Test map_qbittorrent_tracker
# ============================================================


class TestMapQbittorrentTracker:
    """qBittorrent 完整 tracker 映射测试"""

    def _make_tracker(self, **overrides):
        """构造 qBittorrent tracker 字典"""
        default = {
            "url": "http://tracker.example.com:8080/announce",
            "status": 2,
            "msg": "Success",
            "tier": 1,
            "num_peers": 10,
            "num_seeds": 5,
            "num_leeches": 5,
            "downloaded": 1024,
            "uploaded": 2048,
        }
        default.update(overrides)
        return default

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_完整映射字段(self, mock_engine):
        """所有字段正确映射到返回字典"""
        mock_engine.judge_status.return_value = TrackerStatus.WORKING

        tracker = self._make_tracker()
        result = map_qbittorrent_tracker(tracker)

        assert result["tracker_host"] == "tracker.example.com:8080"
        assert result["tracker_url"] == "http://tracker.example.com:8080/announce"
        assert result["status"] == TrackerStatus.WORKING
        assert result["msg"] == "Success"
        assert result["tier"] == 1
        assert result["num_peers"] == 10
        assert result["num_seeds"] == 5
        assert result["num_leeches"] == 5
        assert result["downloaded"] == 1024
        assert result["uploaded"] == 2048

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_判断引擎被调用(self, mock_engine):
        """judge_status 被正确调用"""
        mock_engine.judge_status.return_value = TrackerStatus.WORKING

        tracker = self._make_tracker(msg="Connection timeout")
        map_qbittorrent_tracker(tracker)

        mock_engine.judge_status.assert_called_once_with(
            original_status=TrackerStatus.WORKING,
            msg="Connection timeout",
            language=None,
        )

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_缺失字段使用默认值(self, mock_engine):
        """缺失字段使用默认值"""
        mock_engine.judge_status.return_value = TrackerStatus.WORKING

        tracker = {"url": "http://tracker.example.com/announce"}
        result = map_qbittorrent_tracker(tracker)

        assert result["tier"] == 0
        assert result["num_peers"] == 0
        assert result["num_seeds"] == 0
        assert result["num_leeches"] == 0
        assert result["downloaded"] == 0
        assert result["uploaded"] == 0

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_失败状态映射(self, mock_engine):
        """失败状态正确传递给判断引擎"""
        mock_engine.judge_status.return_value = TrackerStatus.FAILED

        tracker = self._make_tracker(status=3, msg="Connection refused")
        result = map_qbittorrent_tracker(tracker)

        # 基础状态映射: 3 → FAILED
        mock_engine.judge_status.assert_called_once_with(
            original_status=TrackerStatus.FAILED,
            msg="Connection refused",
            language=None,
        )
        assert result["status"] == TrackerStatus.FAILED


# ============================================================
# Test map_transmission_tracker
# ============================================================


class TestMapTransmissionTracker:
    """Transmission 完整 tracker 映射测试"""

    def _make_tracker(self, **overrides):
        """构造 Transmission tracker 字典"""
        default = {
            "announce": "http://tracker.example.com:8080/announce",
            "last_announce_result": "Success",
            "last_announce_succeeded": True,
            "tier": 1,
            "last_announce_peer_count": 10,
            "last_announce_time": 1700000000,
            "last_scrape_time": 1700000100,
            "host": "tracker.example.com:8080",
            "site_name": "ExampleSite",
        }
        default.update(overrides)
        return default

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_完整映射字段(self, mock_engine):
        """所有字段正确映射到返回字典"""
        mock_engine.judge_status.return_value = TrackerStatus.WORKING

        tracker = self._make_tracker()
        result = map_transmission_tracker(tracker)

        assert result["tracker_host"] == "tracker.example.com:8080"
        assert result["tracker_url"] == "http://tracker.example.com:8080/announce"
        assert result["status"] == TrackerStatus.WORKING
        assert result["msg"] == "Success"
        assert result["tier"] == 1
        assert result["num_peers"] == 10
        assert result["last_announce_time"] == 1700000000
        assert result["last_scrape_time"] == 1700000100
        assert result["site_name"] == "ExampleSite"

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_announce成功时基础状态为工作中(self, mock_engine):
        """last_announce_succeeded=True 时基础状态为 WORKING"""
        mock_engine.judge_status.return_value = TrackerStatus.WORKING

        tracker = self._make_tracker(last_announce_succeeded=True)
        map_transmission_tracker(tracker)

        mock_engine.judge_status.assert_called_once_with(
            original_status=TrackerStatus.WORKING,
            msg="Success",
            language=None,
        )

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_announce失败时基础状态为未联系(self, mock_engine):
        """last_announce_succeeded=False 时基础状态为 NOT_CONTACTED"""
        mock_engine.judge_status.return_value = TrackerStatus.NOT_CONTACTED

        tracker = self._make_tracker(
            last_announce_succeeded=False,
            last_announce_result="Connection refused",
        )
        map_transmission_tracker(tracker)

        mock_engine.judge_status.assert_called_once_with(
            original_status=TrackerStatus.NOT_CONTACTED,
            msg="Connection refused",
            language=None,
        )

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_无host时从URL提取(self, mock_engine):
        """host 字段为空时从 announce URL 提取"""
        mock_engine.judge_status.return_value = TrackerStatus.WORKING

        tracker = self._make_tracker(host="")
        result = map_transmission_tracker(tracker)
        assert result["tracker_host"] == "tracker.example.com:8080"

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_缺失字段使用默认值(self, mock_engine):
        """缺失字段使用默认值"""
        mock_engine.judge_status.return_value = TrackerStatus.WORKING

        tracker = {"announce": "http://tracker.example.com/announce"}
        result = map_transmission_tracker(tracker)

        assert result["tier"] == 0
        assert result["num_peers"] == 0
        assert result["last_announce_time"] == 0
        assert result["last_scrape_time"] == 0
        assert result["site_name"] == ""


# ============================================================
# Test refresh_judgment_engine_cache & get_judgment_engine_stats
# ============================================================


class TestProxyFunctions:
    """代理函数测试"""

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_refresh_judgment_engine_cache代理调用(self, mock_engine):
        """refresh_judgment_engine_cache 委托给引擎的 refresh_cache"""
        mock_engine.refresh_cache.return_value = True
        result = refresh_judgment_engine_cache()
        assert result is True
        mock_engine.refresh_cache.assert_called_once()

    @patch("app.core.tracker_mapper.judgment_engine")
    def test_get_judgment_engine_stats代理调用(self, mock_engine):
        """get_judgment_engine_stats 委托给引擎的 get_cache_stats"""
        mock_stats = {"success_count": 10, "failed_count": 5}
        mock_engine.get_cache_stats.return_value = mock_stats
        result = get_judgment_engine_stats()
        assert result == mock_stats
        mock_engine.get_cache_stats.assert_called_once()
