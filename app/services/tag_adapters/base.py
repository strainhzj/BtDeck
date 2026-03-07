# -*- coding: utf-8 -*-
"""
标签适配器抽象基类

定义统一的标签操作接口，支持qBittorrent和Transmission两种下载器。
所有具体适配器实现必须继承此基类并实现所有抽象方法。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class TorrentTagAdapter(ABC):
    """
    标签适配器抽象基类

    定义了标签管理的统一接口，用于屏蔽不同下载器之间的API差异。
    支持的操作包括：标签CRUD、种子标签分配、批量操作等。

    实现说明:
        - 所有方法都是异步的，以支持高并发场景
        - 返回格式统一，便于上层调用
        - 必须实现完整的错误处理和日志记录
    """

    def __init__(self, downloader_id: str):
        """
        初始化适配器

        Args:
            downloader_id: 下载器ID，用于标识和管理
        """
        self.downloader_id = downloader_id

    # ==================== 抽象方法（子类必须实现）====================

    @abstractmethod
    async def get_tags(self) -> Dict[str, Any]:
        """
        获取所有标签（统一格式）

        Returns:
            Dict[str, Any]: 统一格式的响应
                {
                    "success": bool,
                    "data": List[Dict],  # 标签列表
                    "message": str,
                    "total_count": int
                }
                每个标签包含:
                {
                    "tag_id": str,      # 本地UUID
                    "name": str,         # 标签名称
                    "type": str,         # 'category' | 'tag'
                    "color": str,        # HEX颜色码（可选）
                    "raw_data": dict     # 原始下载器数据（可选）
                }
        """
        pass

    @abstractmethod
    async def create_tag(self, tag_name: str, tag_type: str, color: Optional[str] = None) -> Dict[str, Any]:
        """
        创建标签

        Args:
            tag_name: 标签名称
            tag_type: 标签类型 ('category' | 'tag')
            color: 可选，HEX颜色码

        Returns:
            Dict[str, Any]: 统一格式的响应
                {
                    "success": bool,
                    "data": dict,  # 创建的标签信息
                    "message": str,
                    "tag_id": str  # 本地UUID
                }
        """
        pass

    @abstractmethod
    async def delete_tag(self, tag_id: str) -> Dict[str, Any]:
        """
        删除标签

        Args:
            tag_id: 标签ID（本地UUID）

        Returns:
            Dict[str, Any]: 统一格式的响应
                {
                    "success": bool,
                    "message": str,
                    "data": dict  # 可选，删除的标签信息
                }
        """
        pass

    @abstractmethod
    async def assign_tags_to_torrent(
        self,
        torrent_hash: str,
        tag_ids: List[str]
    ) -> Dict[str, Any]:
        """
        为种子分配标签

        Args:
            torrent_hash: 种子哈希值
            tag_ids: 标签ID列表（本地UUID）

        Returns:
            Dict[str, Any]: 统一格式的响应
                {
                    "success": bool,
                    "message": str,
                    "assigned_count": int,
                    "failed_count": int,
                    "failed_tags": List[dict]  # 失败的标签详情
                }
        """
        pass

    @abstractmethod
    async def remove_tags_from_torrent(
        self,
        torrent_hash: str,
        tag_ids: List[str]
    ) -> Dict[str, Any]:
        """
        移除种子的标签

        Args:
            torrent_hash: 种子哈希值
            tag_ids: 标签ID列表（本地UUID）

        Returns:
            Dict[str, Any]: 统一格式的响应
                {
                    "success": bool,
                    "message": str,
                    "removed_count": int,
                    "failed_count": int
                }
        """
        pass

    @abstractmethod
    async def get_torrent_tags(self, torrent_hash: str) -> Dict[str, Any]:
        """
        获取种子的所有标签

        Args:
            torrent_hash: 种子哈希值

        Returns:
            Dict[str, Any]: 统一格式的响应
                {
                    "success": bool,
                    "data": List[dict],  # 标签列表
                    "message": str,
                    "total_count": int
                }
        """
        pass

    # ==================== 可选方法（子类可选择性实现）====================

    async def batch_assign_tags(
        self,
        assignments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量分配标签（可选优化）

        Args:
            assignments: 分配任务列表
                [
                    {"torrent_hash": "...", "tag_ids": ["...", "..."]},
                    ...
                ]

        Returns:
            Dict[str, Any]: 统一格式的响应
        """
        # 默认实现：逐个调用 assign_tags_to_torrent
        results = []
        total_success = 0
        total_failed = 0

        for assignment in assignments:
            torrent_hash = assignment.get("torrent_hash")
            tag_ids = assignment.get("tag_ids", [])

            if not torrent_hash or not tag_ids:
                continue

            result = await self.assign_tags_to_torrent(torrent_hash, tag_ids)
            results.append({
                "torrent_hash": torrent_hash,
                "result": result
            })

            if result.get("success"):
                total_success += 1
            else:
                total_failed += 1

        return {
            "success": total_failed == 0,
            "message": f"批量分配完成: 成功{total_success}，失败{total_failed}",
            "total_assignments": len(assignments),
            "success_count": total_success,
            "failed_count": total_failed,
            "details": results
        }

    async def check_connection(self) -> bool:
        """
        检查连接状态（可选）

        Returns:
            bool: 连接是否正常
        """
        return True

    def get_downloader_type(self) -> str:
        """
        获取下载器类型

        Returns:
            str: 下载器类型标识 ('qbittorrent' | 'transmission')
        """
        return "unknown"

    # ==================== 辅助方法 ====================

    def _format_success_response(
        self,
        data: Any,
        message: str = "操作成功"
    ) -> Dict[str, Any]:
        """
        格式化成功响应

        Args:
            data: 响应数据
            message: 响应消息

        Returns:
            统一格式的成功响应
        """
        response = {
            "success": True,
            "message": message
        }

        if isinstance(data, list):
            response["data"] = data
            response["total_count"] = len(data)
        elif isinstance(data, dict):
            response.update(data)
        else:
            response["data"] = data

        return response

    def _format_error_response(
        self,
        message: str,
        data: Any = None
    ) -> Dict[str, Any]:
        """
        格式化错误响应

        Args:
            message: 错误消息
            data: 可选的错误详情

        Returns:
            统一格式的错误响应
        """
        response = {
            "success": False,
            "message": message
        }

        if data is not None:
            response["data"] = data

        return response
