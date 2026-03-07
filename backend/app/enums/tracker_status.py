"""
Tracker 状态枚举类

用于映射 qBittorrent 和 Transmission 的 tracker 状态为中文显示文本。

作者: AI开发助手
创建时间: 2026-02-25
版本: 1.0.0
"""

from enum import Enum


class QBittorrentTrackerStatus(Enum):
    """qBittorrent Tracker 状态枚举

    qBittorrent tracker 状态值:
        0: 已禁用 (Disabled)
        1: 未联系 (Not contacted)
        2: 工作中 (Working)
        3: 工作失败 (Not working)
        4: 超时 (Timeout)
    """

    DISABLED = 0       # 已禁用
    NOT_CONTACTED = 1  # 未联系
    WORKING = 2        # 工作中
    FAILED = 3         # 工作失败
    TIMEOUT = 4        # 超时

    @classmethod
    def get_display_text(cls, status: int) -> str:
        """获取状态的中文显示文本

        Args:
            status: qBittorrent tracker 状态值 (0-4)

        Returns:
            中文状态文本

        示例:
            >>> QBittorrentTrackerStatus.get_display_text(0)
            '已禁用'
            >>> QBittorrentTrackerStatus.get_display_text(2)
            '工作中'
        """
        status_map = {
            0: "已禁用",
            1: "未联系",
            2: "工作中",
            3: "工作失败",
            4: "超时"
        }
        return status_map.get(status, "未知")


class TransmissionTrackerStatus(Enum):
    """Transmission Tracker 状态枚举

    Transmission tracker 状态值:
        0: 未联系 (Not contacted)
        1: 发送中 (Sending)
        2: 工作中 (Working)
        3: 工作失败 (Not working)
        4: 超时 (Timeout)
        5: 已清除 (Cleared)
    """

    NOT_CONTACTED = 0  # 未联系
    SENDING = 1        # 发送中
    WORKING = 2        # 工作中
    FAILED = 3         # 工作失败
    TIMEOUT = 4        # 超时
    CLEARED = 5        # 已清除

    @classmethod
    def get_display_text(cls, status: int) -> str:
        """获取状态的中文显示文本

        Args:
            status: Transmission tracker 状态值 (0-5)

        Returns:
            中文状态文本

        示例:
            >>> TransmissionTrackerStatus.get_display_text(0)
            '未联系'
            >>> TransmissionTrackerStatus.get_display_text(2)
            '工作中'
        """
        status_map = {
            0: "未联系",
            1: "发送中",
            2: "工作中",
            3: "工作失败",
            4: "超时",
            5: "已清除"
        }
        return status_map.get(status, "未知")


def get_tracker_status_text(status_value: int, downloader_type: str = "qbittorrent") -> str:
    """根据下载器类型获取 tracker 状态的中文显示文本

    Args:
        status_value: tracker 状态值
        downloader_type: 下载器类型 ("qbittorrent" 或 "transmission")

    Returns:
        中文状态文本

    示例:
        >>> get_tracker_status_text(0, "qbittorrent")
        '已禁用'
        >>> get_tracker_status_text(2, "transmission")
        '工作中'
    """
    if downloader_type == "qbittorrent":
        return QBittorrentTrackerStatus.get_display_text(status_value)
    elif downloader_type == "transmission":
        return TransmissionTrackerStatus.get_display_text(status_value)
    else:
        # 未知类型，尝试 qBittorrent 作为默认
        return QBittorrentTrackerStatus.get_display_text(status_value)
