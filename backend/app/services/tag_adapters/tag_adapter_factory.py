# -*- coding: utf-8 -*-
"""
标签适配器工厂

根据下载器类型创建对应的标签适配器实例，实现适配器的模块化管理。
"""

from typing import Optional, Any
import logging

from .base import TorrentTagAdapter
from .qbittorrent_adapter import QBittorrentTagAdapter
from .transmission_adapter import TransmissionTagAdapter
from app.models.setting_templates import DownloaderTypeEnum

logger = logging.getLogger(__name__)


class TagAdapterFactory:
    """
    标签适配器工厂类

    负责根据下载器类型创建对应的标签适配器实例。
    支持qBittorrent和Transmission两种下载器类型。
    """

    # 支持的下载器类型
    SUPPORTED_TYPES = {
        'qbittorrent': QBittorrentTagAdapter,
        'transmission': TransmissionTagAdapter,
    }

    @classmethod
    def create_adapter(
        cls,
        downloader: Any,
        client: Any = None,
        session: Any = None,
        rpc_url: Optional[str] = None,
        session_id: Optional[str] = None,
        username: Optional[str] = None,  # ✅ 新增：用于认证
        password: Optional[str] = None   # ✅ 新增：用于认证
    ) -> Optional[TorrentTagAdapter]:
        """
        创建标签适配器实例

        Args:
            downloader: 下载器对象（BtDownloaders模型实例）
            client: 可选的客户端实例（用于qBittorrent）
            session: 可选的会话对象（用于Transmission）
            rpc_url: 可选的RPC地址（用于Transmission）
            session_id: 可选的会话ID（用于Transmission）
            username: 可选的用户名（用于Transmission认证）
            password: 可选的密码（用于Transmission认证）

        Returns:
            对应的标签适配器实例，不支持时返回None

        Examples:
            >>> # qBittorrent
            >>> adapter = TagAdapterFactory.create_adapter(
            ...     downloader, client=qb_client
            ... )
            >>> isinstance(adapter, QBittorrentTagAdapter)
            True

            >>> # Transmission
            >>> adapter = TagAdapterFactory.create_adapter(
            ...     downloader, session=rpc_session,
            ...     rpc_url="http://localhost:9091/transmission/rpc"
            ... )
            >>> isinstance(adapter, TransmissionTagAdapter)
            True
        """
        try:
            # 获取下载器类型
            downloader_type = cls._normalize_downloader_type(downloader.downloader_type)

            if downloader_type not in cls.SUPPORTED_TYPES:
                logger.warning(
                    f"不支持的下载器类型: {downloader.downloader_type} "
                    f"(标准化后: {downloader_type})，下载器ID: {downloader.downloader_id}"
                )
                return None

            # 获取适配器类
            adapter_class = cls.SUPPORTED_TYPES[downloader_type]
            downloader_id = downloader.downloader_id

            # 根据类型创建适配器
            if downloader_type == 'qbittorrent':
                if not client:
                    logger.error(f"创建qBittorrent适配器失败: 缺少client参数，下载器ID: {downloader_id}")
                    return None
                return adapter_class(downloader_id=downloader_id, client=client)

            elif downloader_type == 'transmission':
                if not rpc_url:
                    logger.error(
                        f"创建Transmission适配器失败: 缺少rpc_url参数，"
                        f"下载器ID: {downloader_id}"
                    )
                    return None
                # ✅ 修复：传递username和password参数用于认证
                return adapter_class(
                    downloader_id=downloader_id,
                    session=session,  # 可能是 None，适配器自己处理
                    rpc_url=rpc_url,
                    session_id=session_id,
                    username=username,
                    password=password
                )

            return None

        except Exception as e:
            logger.error(f"创建标签适配器失败: {str(e)}，下载器ID: {downloader.downloader_id}")
            return None

    @classmethod
    def _normalize_downloader_type(cls, downloader_type: str) -> str:
        """
        标准化下载器类型标识

        使用统一的枚举类方法进行类型转换，支持多种输入格式：
        - 整数：0, 1
        - 字符串数字："0", "1"
        - 名称："qbittorrent", "transmission"（不区分大小写）

        Args:
            downloader_type: 原始下载器类型

        Returns:
            标准化后的类型标识 ('qbittorrent' | 'transmission')
        """
        if downloader_type is None:
            logger.debug(f"下载器类型为 None，返回 qbittorrent（默认值）")
            return 'qbittorrent'

        # 使用枚举类规范化并转换为名称
        normalized_int = DownloaderTypeEnum.normalize(downloader_type)
        type_name = DownloaderTypeEnum(normalized_int).to_name()
        logger.debug(f"类型标准化: {downloader_type} (type: {type(downloader_type).__name__}) -> {type_name}")
        return type_name

    @classmethod
    def get_supported_types(cls) -> list:
        """
        获取支持的下载器类型列表

        Returns:
            支持的类型标识列表
        """
        return list(cls.SUPPORTED_TYPES.keys())

    @classmethod
    def is_supported(cls, downloader_type: str) -> bool:
        """
        检查下载器类型是否支持

        Args:
            downloader_type: 下载器类型

        Returns:
            是否支持
        """
        normalized_type = cls._normalize_downloader_type(downloader_type)
        return normalized_type in cls.SUPPORTED_TYPES
