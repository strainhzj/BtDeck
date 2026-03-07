# -*- coding: utf-8 -*-
"""
qBittorrent种子位置修改适配器

实现qBittorrent下载器的种子位置修改功能。

@author: btpManager Team
@file: qbittorrent_location.py
@time: 2026-03-04
"""

import logging
from typing import List, Dict, Any
from qbittorrentapi import Client

from app.services.downloader_adapters.location_base import TorrentLocationAdapter

logger = logging.getLogger(__name__)


class QBittorrentLocationAdapter(TorrentLocationAdapter):
    """
    qBittorrent种子位置修改适配器

    使用qbittorrentapi的torrents_set_location方法修改种子保存路径。
    """

    def __init__(self, client: Client):
        """
        初始化qBittorrent适配器

        Args:
            client: 已初始化的qBittorrent客户端对象（从缓存获取）
        """
        self._client = client

    @property
    def client(self) -> Client:
        """获取qBittorrent客户端实例"""
        if self._client is None:
            raise ValueError("qBittorrent客户端连接不存在，下载器可能离线")
        return self._client

    def get_client(self):
        """获取下载器客户端实例"""
        return self.client

    async def set_location(
        self,
        hashes: List[str],
        target_path: str,
        move_files: bool
    ) -> Dict[str, Any]:
        """
        修改qBittorrent种子保存路径

        Args:
            hashes: 种子哈希值列表
            target_path: 目标路径（绝对路径）
            move_files: 是否移动已下载的文件

        Returns:
            操作结果字典
        """
        result = {
            "success": False,
            "moved_count": 0,
            "failed_count": 0,
            "error_message": None
        }

        try:
            # qBittorrent API使用|分隔多个hash
            hashes_str = "|".join(hashes)

            logger.info(
                f"修改qBittorrent种子路径: hashes={len(hashes)}个, "
                f"target_path={target_path}, move_files={move_files}"
            )

            if move_files:
                # torrents_set_location 会移动文件
                self.client.torrents_set_location(
                    location=target_path,
                    torrent_hashes=hashes_str
                )
            else:
                # 仅修改保存路径，不移动文件
                self.client.torrents_set_save_path(
                    save_path=target_path,
                    torrent_hashes=hashes_str
                )
                logger.info(f"已修改保存路径（未移动文件）: {hashes_str}")

            result["success"] = True
            result["moved_count"] = len(hashes)

            logger.info(f"成功提交{len(hashes)}个种子路径修改请求")

        except Exception as e:
            result["failed_count"] = len(hashes)
            result["error_message"] = str(e)
            logger.error(f"修改qBittorrent种子路径失败: {e}")

        return result
