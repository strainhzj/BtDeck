"""
种子状态映射器

统一管理不同下载器（qBittorrent、Transmission）的状态转换，
确保前端接收到的状态值符合项目规范。

Author: btpmanager
Version: 1.0.0
Date: 2026-02-04
"""

from typing import Dict, Optional


class TorrentStatusMapper:
    """种子状态映射器 - 统一管理不同下载器的状态转换"""

    # qBittorrent 状态映射表
    # 源状态 -> 目标状态
    QBITTORRENT_STATUS_MAP: Dict[str, str] = {
        # 上传相关状态 -> seeding（做种中）
        "stalledUP": "seeding",  # 做种但无连接 -> 做种中
        "seeding": "seeding",  # 做种中 -> 做种中
        "queuedUP": "seeding",  # 上传队列中 -> 做种中
        "uploading": "seeding",  # 正在上传 -> 做种中
        "pausedUP": "pausedUP",  # ✅ 上传暂停 -> 保持为 pausedUP（将在统计时归入做种）
        # 下载相关状态 -> downloading
        "stalledDL": "downloading",  # 下载停滞 -> 下载中
        # 暂停状态统一 -> paused
        "pausedDL": "pausedDL",  # ✅ 下载暂停 -> 保持为 pausedDL（将在统计时归入暂停）
        # 检查状态保持不变
        "checkingDL": "checkingDL",  # 下载检查中 -> 保持不变
        "checkingUP": "checkingUP",  # 上传检查中 -> 保持不变（将在统计时归入做种）
        # 队列下载状态
        "queuedDL": "queuedDL",  # 下载队列中 -> 保持不变
        # 其他状态保持不变
        "downloading": "downloading",  # 正在下载 -> 保持不变
        # 新添加种子的初始态统一归入下载中，避免前端显示 unknown
        "metaDL": "downloading",  # 获取元数据中（磁力链初始态）-> 下载中
        "forcedMetaDL": "downloading",  # 强制获取元数据 -> 下载中
        "allocating": "downloading",  # 分配磁盘空间（新种子初始态）-> 下载中
        "forcedDL": "downloading",  # 强制下载 -> 下载中
        "forcedUP": "seeding",  # 强制做种 -> 做种中
        "missingFiles": "error",  # 数据文件缺失 -> 错误
        "checkingResumeData": "checkingDL",  # 恢复数据检查 -> 下载检查中
        # 注：moving（迁移保存路径的瞬时态）有意不映射，语义取决于迁移前的下载/做种状态
        "paused": "paused",  # 已暂停 -> 保持不变
        "error": "error",  # 错误 -> 保持不变
        "unknown": "unknown",  # 未知 -> 保持不变
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
        "seeding": "seeding",
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

    # Transmission error 字段语义（RPC spec，由 transmission_rpc Torrent.error 返回 int）：
    #   0 = ok（正常）
    #   1 = tracker warning（tracker 警告，轻微，不归入错误）
    #   2 = tracker error（tracker 错误）
    #   3 = local error（本地错误，如磁盘满/数据损坏）
    TR_ERROR_THRESHOLD = 2

    @staticmethod
    def resolve_transmission_status(tr_status: object, tr_error: object) -> str:
        """Transmission 状态 + error 字段联合判定通用状态。

        Transmission 的种子级错误独立于 ``status`` 字段（一个 error=3 的种子
        ``status`` 仍是 ``downloading``/``seeding`` 等正常值）。本方法把
        ``error >= 2``（tracker 错误 / 本地错误）的种子归入 ``"error"``，
        与前端已支持的 ``status="error"`` 标签对齐。

        Args:
            tr_status: Transmission 的 ``status`` 字段（经 transmission_rpc
                归一化为字符串，如 ``"downloading"``）。
            tr_error: Transmission 的 ``error`` 字段（int）。非 int 值（None、
                MagicMock、缺失等）按 0 处理，回退查表。

        Returns:
            转换后的通用状态值。

        Note:
            - ``isinstance`` 守卫规避两类陷阱：(1) ``transmission_rpc`` 的
              ``Torrent.error`` 在字段缺失时抛 ``KeyError``（``getattr`` 默认值无效）；
              (2) 测试 ``MagicMock`` 未设 ``error`` 属性时返回 ``MagicMock`` 而非 0。
            - ``checking`` 状态优先于 error：校验过程中 tracker 报错不应掩盖
              "校验中"语义。
        """
        base = TorrentStatusMapper.convert_transmission_status(tr_status)  # type: ignore[arg-type]
        if not isinstance(tr_error, int):
            return base
        # 校验中状态优先，避免校验过程被 tracker 错误误判为 error
        if base == "checking":
            return base
        if tr_error >= TorrentStatusMapper.TR_ERROR_THRESHOLD:
            return "error"
        return base

    @staticmethod
    def extract_transmission_error_reason(tr_torrent: object) -> Optional[str]:
        """提取 Transmission 严重错误的可展示原因。

        ``transmission_rpc`` 仅在请求包含 ``errorString`` 时才暴露
        ``Torrent.error_string``，字段缺失时属性访问可能抛出 ``KeyError``。
        因此这里集中做防御性读取，并在错误恢复、警告或空文案时返回
        ``None``，让同步写入能够清除数据库中的历史错误原因。
        """
        try:
            tr_error = getattr(tr_torrent, "error")
        except (AttributeError, KeyError):
            return None

        if not isinstance(tr_error, int) or tr_error < TorrentStatusMapper.TR_ERROR_THRESHOLD:
            return None

        try:
            raw_reason = getattr(tr_torrent, "error_string")
        except (AttributeError, KeyError):
            raw_reason = None

        if not isinstance(raw_reason, str):
            return None

        reason = raw_reason.strip()
        return reason or None

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
