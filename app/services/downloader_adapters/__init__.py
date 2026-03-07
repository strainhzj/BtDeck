"""
下载器适配器包
提供各种BitTorrent下载器的删除功能适配器
"""

from .qbittorrent import QBittorrentDeleteAdapter
from .transmission import TransmissionDeleteAdapter

__all__ = [
    "QBittorrentDeleteAdapter",
    "TransmissionDeleteAdapter"
]