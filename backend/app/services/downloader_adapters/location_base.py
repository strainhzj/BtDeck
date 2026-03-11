# -*- coding: utf-8 -*-
"""
种子位置修改适配器基类

定义统一的种子位置修改接口，支持qBittorrent和Transmission。

@author: btpManager Team
@file: location_base.py
@time: 2026-03-04
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class TorrentLocationAdapter(ABC):
    """
    种子位置修改适配器基类

    定义统一的种子位置修改接口，由具体下载器适配器实现。
    """

    @abstractmethod
    async def set_location(
        self,
        hashes: List[str],
        target_path: str,
        move_files: bool
    ) -> Dict[str, Any]:
        """
        修改种子保存路径

        Args:
            hashes: 种子哈希值列表
            target_path: 目标路径（绝对路径）
            move_files: 是否移动已下载的文件

        Returns:
            操作结果字典:
            {
                "success": bool,              # 是否成功
                "moved_count": int,           # 成功修改的种子数量
                "failed_count": int,          # 失败的种子数量
                "error_message": str or None  # 错误信息
            }
        """
        pass

    @abstractmethod
    def get_client(self):
        """
        获取下载器客户端实例

        Returns:
            下载器客户端对象（qbittorrentapi.Client 或 transmission_rpc.Client）
        """
        pass
