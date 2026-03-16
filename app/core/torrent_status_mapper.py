"""
种子状态映射器

统一管理不同下载器（qBittorrent、Transmission）的状态转换，
确保前端接收到的状态值符合项目规范。

Author: btpmanager
Version: 1.0.0
Date: 2026-02-04
"""

from typing import Dict


class TorrentStatusMapper:
    """种子状态映射器 - 统一管理不同下载器的状态转换"""

    # qBittorrent 状态映射表
    # 源状态 -> 目标状态
    QBITTORRENT_STATUS_MAP: Dict[str, str] = {
        # 上传相关状态 -> seeding（做种中）
        "stalledUP": "seeding",        # 做种但无连接 -> 做种中
        "seeding": "seeding",          # 做种中 -> 做种中
        "queuedUP": "seeding",         # 上传队列中 -> 做种中
        "uploading": "seeding",        # 正在上传 -> 做种中
        "pausedUP": "pausedUP",        # ✅ 上传暂停 -> 保持为 pausedUP（将在统计时归入做种）

        # 下载相关状态 -> downloading
        "stalledDL": "downloading",    # 下载停滞 -> 下载中

        # 暂停状态统一 -> paused
        "pausedDL": "pausedDL",        # ✅ 下载暂停 -> 保持为 pausedDL（将在统计时归入暂停）

        # 检查状态保持不变
        "checkingDL": "checkingDL",    # 下载检查中 -> 保持不变
        "checkingUP": "checkingUP",    # 上传检查中 -> 保持不变（将在统计时归入做种）

        # 队列下载状态
        "queuedDL": "queuedDL",        # 下载队列中 -> 保持不变

        # 其他状态保持不变
        "downloading": "downloading",  # 正在下载 -> 保持不变
        "paused": "paused",            # 已暂停 -> 保持不变
        "error": "error",              # 错误 -> 保持不变
        "unknown": "unknown",          # 未知 -> 保持不变
    }

    # Transmission 状态映射表
    # 保持原有的映射逻辑
    TRANSMISSION_STATUS_MAP: Dict[str, str] = {
        "stopped": "paused",
        "check pending": "checking",
        "checking": "checking",
        "download pending": "downloading",
        "downloading": "downloading",
        "seed pending": "seeding",
        "seeding": "seeding"
    }

    @staticmethod
    def convert_qbittorrent_status(qb_status: str) -> str:
        """
        将 qBittorrent 状态转换为通用状态

        Args:
            qb_status: qBittorrent 原始状态值

        Returns:
            转换后的通用状态值

        Examples:
            >>> TorrentStatusMapper.convert_qbittorrent_status("stalledUP")
            'seeding'
            >>> TorrentStatusMapper.convert_qbittorrent_status("seeding")
            'seeding'
            >>> TorrentStatusMapper.convert_qbittorrent_status("pausedDL")
            'paused'
        """
        return TorrentStatusMapper.QBITTORRENT_STATUS_MAP.get(qb_status, qb_status)

    @staticmethod
    def convert_transmission_status(tr_status: str) -> str:
        """
        将 Transmission 状态转换为通用状态

        Args:
            tr_status: Transmission 原始状态值

        Returns:
            转换后的通用状态值

        Examples:
            >>> TorrentStatusMapper.convert_transmission_status("stopped")
            'paused'
            >>> TorrentStatusMapper.convert_transmission_status("seed pending")
            'seeding'
        """
        return TorrentStatusMapper.TRANSMISSION_STATUS_MAP.get(tr_status, tr_status)

    @classmethod
    def get_qbittorrent_mapping_rules(cls) -> Dict[str, str]:
        """
        获取 qBittorrent 状态映射规则（用于文档或调试）

        Returns:
            完整的状态映射字典
        """
        return cls.QBITTORRENT_STATUS_MAP.copy()

    @classmethod
    def get_transmission_mapping_rules(cls) -> Dict[str, str]:
        """
        获取 Transmission 状态映射规则（用于文档或调试）

        Returns:
            完整的状态映射字典
        """
        return cls.TRANSMISSION_STATUS_MAP.copy()
