# -*- coding: utf-8 -*-
"""
Transmission种子位置修改适配器

实现Transmission下载器的种子位置修改功能。

@author: btpManager Team
@file: transmission_location.py
@time: 2026-03-04
"""

import logging
from typing import List, Dict, Any
from transmission_rpc import Client

from app.services.downloader_adapters.location_base import TorrentLocationAdapter

logger = logging.getLogger(__name__)


class TransmissionLocationAdapter(TorrentLocationAdapter):
    """
    Transmission种子位置修改适配器

    使用transmission_rpc的move_torrent_data方法修改种子保存路径。
    """

    def __init__(self, client: Client):
        """
        初始化Transmission适配器

        Args:
            client: 已初始化的transmission_rpc客户端对象（从缓存获取）
        """
        self._client = client

    @property
    def client(self) -> Client:
        """获取Transmission客户端实例"""
        if self._client is None:
            raise ValueError("Transmission客户端连接不存在，下载器可能离线")
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
        修改Transmission种子保存路径

        Args:
            hashes: 种子哈希值列表（Transmission使用hash字符串）
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
            logger.info(
                f"修改Transmission种子路径: hashes={len(hashes)}个, "
                f"target_path={target_path}, move_files={move_files}"
            )

            # Transmission的move参数：True=移动文件，False=仅修改路径
            # 调用API（支持批量操作）
            self.client.move_torrent_data(
                ids=hashes,  # 支持列表
                location=target_path,
                move=move_files
            )

            result["success"] = True
            result["moved_count"] = len(hashes)

            logger.info(f"成功提交{len(hashes)}个种子路径修改请求")

        except Exception as e:
            result["failed_count"] = len(hashes)
            result["error_message"] = str(e)
            logger.error(f"修改Transmission种子路径失败: {e}")

        return result
