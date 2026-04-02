"""
Tracker状态枚举单元测试

测试 tracker_status 枚举模块的核心功能：
- QBittorrentTrackerStatus.get_display_text: qBittorrent 各状态值中文显示
- TransmissionTrackerStatus.get_display_text: Transmission 各状态值中文显示
- get_tracker_status_text: 按下载器类型获取状态文本
- 未知值 fallback
"""

import pytest

from app.enums.tracker_status import (
    QBittorrentTrackerStatus,
    TransmissionTrackerStatus,
    get_tracker_status_text,
)


# ============================================================
# Test QBittorrentTrackerStatus.get_display_text
# ============================================================


class TestQBittorrentDisplayText:
    """qBittorrent tracker 状态中文显示测试"""

    @pytest.mark.parametrize(
        "status, expected",
        [
            (0, "已禁用"),
            (1, "未联系"),
            (2, "工作中"),
            (3, "工作失败"),
            (4, "超时"),
        ],
    )
    def test_所有状态值的中文显示(self, status, expected):
        """qBittorrent 状态 0-4 正确映射为中文"""
        assert QBittorrentTrackerStatus.get_display_text(status) == expected

    def test_未知值返回未知(self):
        """未知状态值返回 '未知'"""
        assert QBittorrentTrackerStatus.get_display_text(99) == "未知"
        assert QBittorrentTrackerStatus.get_display_text(-1) == "未知"


# ============================================================
# Test TransmissionTrackerStatus.get_display_text
# ============================================================


class TestTransmissionDisplayText:
    """Transmission tracker 状态中文显示测试"""

    @pytest.mark.parametrize(
        "status, expected",
        [
            (0, "未联系"),
            (1, "发送中"),
            (2, "工作中"),
            (3, "工作失败"),
            (4, "超时"),
            (5, "已清除"),
        ],
    )
    def test_所有状态值的中文显示(self, status, expected):
        """Transmission 状态 0-5 正确映射为中文"""
        assert TransmissionTrackerStatus.get_display_text(status) == expected

    def test_未知值返回未知(self):
        """未知状态值返回 '未知'"""
        assert TransmissionTrackerStatus.get_display_text(99) == "未知"
        assert TransmissionTrackerStatus.get_display_text(-1) == "未知"


# ============================================================
# Test get_tracker_status_text
# ============================================================


class TestGetTrackerStatusText:
    """按下载器类型获取状态文本测试"""

    def test_qbittorrent类型(self):
        """指定 qbittorrent 类型时使用 qBittorrent 映射"""
        assert get_tracker_status_text(0, "qbittorrent") == "已禁用"
        assert get_tracker_status_text(2, "qbittorrent") == "工作中"
        assert get_tracker_status_text(3, "qbittorrent") == "工作失败"

    def test_transmission类型(self):
        """指定 transmission 类型时使用 Transmission 映射"""
        assert get_tracker_status_text(0, "transmission") == "未联系"
        assert get_tracker_status_text(2, "transmission") == "工作中"
        assert get_tracker_status_text(5, "transmission") == "已清除"

    def test_整数类型参数(self):
        """下载器类型支持整数参数（0=qBittorrent）"""
        assert get_tracker_status_text(2, 0) == "工作中"

    def test_默认类型为qbittorrent(self):
        """不传 downloader_type 默认使用 qBittorrent"""
        assert get_tracker_status_text(0) == "已禁用"

    def test_未知类型回退到qbittorrent(self):
        """未知下载器类型回退到 qBittorrent 映射"""
        assert get_tracker_status_text(2, "unknown_type") == "工作中"
