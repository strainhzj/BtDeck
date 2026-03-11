"""
Repositories Package - 数据访问层

提供统一的数据访问接口，封装所有数据库操作。
"""

from app.repositories.torrent_tag_repository import TorrentTagRepository
from app.repositories.async_torrent_tag_repository import AsyncTorrentTagRepository

__all__ = [
    "TorrentTagRepository",
    "AsyncTorrentTagRepository",
]
