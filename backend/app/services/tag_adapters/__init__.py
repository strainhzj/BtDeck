# -*- coding: utf-8 -*-
"""
标签适配器模块

提供统一的标签管理接口，支持qBittorrent和Transmission两种下载器。
使用适配器模式实现不同下载器标签/分类功能的统一访问。
"""

from .base import TorrentTagAdapter
from .qbittorrent_adapter import QBittorrentTagAdapter
from .transmission_adapter import TransmissionTagAdapter
from .fallback_handler import FallbackHandler
from .tag_adapter_factory import TagAdapterFactory

__all__ = [
    'TorrentTagAdapter',
    'QBittorrentTagAdapter',
    'TransmissionTagAdapter',
    'FallbackHandler',
    'TagAdapterFactory',
]
