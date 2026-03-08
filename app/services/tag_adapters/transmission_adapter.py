# -*- coding: utf-8 -*-
"""
Transmission标签适配器

实现Transmission下载器的标签管理功能。
注意：Transmission只支持标签，不支持分类。
"""

from typing import List, Dict, Any, Optional
import logging
import uuid
import requests
from requests.auth import HTTPBasicAuth

from .base import TorrentTagAdapter

logger = logging.getLogger(__name__)


class TransmissionTagAdapter(TorrentTagAdapter):
    """
    Transmission标签适配器

    Transmission只支持标签功能，不支持分类。
    对于分类类型的操作，会返回降级提示。

    Attributes:
        downloader_id: 下载器ID
        session: Transmission RPC会话
        rpc_url: RPC接口地址
        username: 下载器用户名（可选）
        password: 下载器密码（可选）
    """

    # Transmission支持的标签字段名
    TAG_FIELD = "labels"

    def __init__(
        self,
        downloader_id: str,
        session: requests.Session,
        rpc_url: str,
        session_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        初始化Transmission标签适配器

        Args:
            downloader_id: 下载器ID
            session: Transmission会话对象（从app.state.store获取，可为None）
            rpc_url: RPC接口地址
            session_id: 可选的会话ID
            username: 下载器用户名（可选）
            password: 下载器密码（可选）
        """
        super().__init__(downloader_id)

        # ✅ 修复：自动创建session（如果未传入）
        if session is None:
            session = requests.Session()
            logger.debug(f"自动创建Transmission会话对象")

        self.session = session
        self.rpc_url = rpc_url
        self.session_id = session_id

        # ✅ 修复：设置HTTP Basic Auth认证
        if username and password:
            self.session.auth = HTTPBasicAuth(username, password)
            logger.debug(f"设置Transmission认证: {username}")

        # 本地标签ID映射表：tag_id (UUID) -> name
        self._tag_id_map: Dict[str, str] = {}
        # 反向映射：name -> tag_id
        self._name_id_map: Dict[str, str] = {}

    def get_downloader_type(self) -> str:
        """获取下载器类型"""
        return "transmission"

    async def check_connection(self) -> bool:
        """检查连接状态"""
        try:
            response = self._make_rpc_request({"method": "session-get"})
            if response and response.get("result") == "success":
                logger.debug("Transmission连接正常")
                return True
            return False
        except Exception as e:
            logger.error(f"Transmission连接检查失败: {str(e)}")
            return False

    async def get_tags(self) -> Dict[str, Any]:
        """
        获取所有标签

        Returns:
            Dict[str, Any]: 统一格式的响应
        """
        try:
            all_tags = set()

            # Transmission的标签存储在每个种子的labels字段中
            # 需要遍历所有种子来收集所有标签
            try:
                response = self._make_rpc_request({
                    "method": "torrent-get",
                    "arguments": {
                        "fields": ["labels"]
                    }
                })

                if response and "arguments" in response:
                    torrents = response["arguments"].get("torrents", [])
                    for torrent in torrents:
                        labels = torrent.get("labels", [])
                        all_tags.update(labels)

                    logger.debug(f"获取到{len(all_tags)}个标签")

            except Exception as e:
                logger.warning(f"获取Transmission标签失败: {str(e)}")

            # 转换为统一格式
            tag_list = []
            for tag_name in all_tags:
                tag_id = self._get_or_create_tag_id(tag_name, 'tag')

                tag_list.append({
                    "tag_id": tag_id,
                    "name": tag_name,
                    "type": "tag",  # Transmission只有标签类型
                    "color": None,
                    "raw_data": {"name": tag_name}
                })

            return self._format_success_response(
                data=tag_list,
                message=f"成功获取{len(tag_list)}个标签"
            )

        except Exception as e:
            logger.error(f"获取Transmission标签列表失败: {str(e)}")
            return self._format_error_response(
                message=f"获取标签列表失败: {str(e)}",
                data=[]
            )

    async def create_tag(self, tag_name: str, tag_type: str, color: Optional[str] = None) -> Dict[str, Any]:
        """
        创建标签（Transmission仅在本地注册）

        Args:
            tag_name: 标签名称
            tag_type: 标签类型（Transmission只支持'tag'）
            color: 可选，颜色代码（Transmission不支持）

        Returns:
            Dict[str, Any]: 统一格式的响应
        """
        try:
            if not tag_name or not tag_name.strip():
                return self._format_error_response(message="标签名称不能为空")

            tag_name = tag_name.strip()

            # Transmission不支持分类类型
            if tag_type == 'category':
                return {
                    "success": False,
                    "message": "Transmission不支持分类功能",
                    "require_fallback": True,
                    "fallback_type": "category_to_tag",
                    "suggestion": f"是否将分类名'{tag_name}'转换为标签？",
                    "data": None
                }

            # 检查是否已存在
            if tag_name in self._name_id_map:
                existing_id = self._name_id_map[tag_name]
                logger.info(f"标签已存在，返回现有ID: {tag_name}")
                return {
                    "success": True,
                    "message": "标签已存在",
                    "data": {
                        "tag_id": existing_id,
                        "name": tag_name,
                        "type": "tag"
                    },
                    "tag_id": existing_id
                }

            # ⚠️ 架构调整：Transmission标签仅在本地注册
            # 标签会在首次分配给种子时（assign_tags_to_torrent）才在Transmission中创建
            # 这符合Transmission的标签设计理念

            tag_id = str(uuid.uuid4())
            self._register_tag_id(tag_id, tag_name, 'tag')

            logger.info(f"✅ 在本地注册Transmission标签: {tag_name} (ID: {tag_id})")
            logger.info(f"ℹ️️  该标签将在首次分配给种子时在Transmission中自动创建")

            return {
                "success": True,
                "message": f"标签创建成功（将在分配给种子时在Transmission中创建）",
                "data": {
                    "tag_id": tag_id,
                    "name": tag_name,
                    "type": "tag",
                    "color": color
                },
                "tag_id": tag_id
            }

        except Exception as e:
            logger.error(f"创建标签时发生错误: {str(e)}")
            return self._format_error_response(message=f"创建标签失败: {str(e)}")

    async def delete_tag(self, tag_id: str) -> Dict[str, Any]:
        """
        删除标签

        Args:
            tag_id: 标签ID（本地UUID）

        Returns:
            Dict[str, Any]: 统一格式的响应
        """
        try:
            # 查找标签信息
            tag_info = self._get_tag_info_by_id(tag_id)
            if not tag_info:
                return self._format_error_response(message=f"标签不存在: {tag_id}")

            tag_name = tag_info["name"]

            # Transmission没有专门的删除标签API
            # 需要从所有种子中移除该标签
            # 这需要获取所有使用该标签的种子，然后逐个移除

            try:
                # 获取所有带有该标签的种子
                response = self._make_rpc_request({
                    "method": "torrent-get",
                    "arguments": {
                        "fields": ["id", "hashString", "labels"]
                    }
                })

                if response and "arguments" in response:
                    torrents = response["arguments"].get("torrents", [])
                    torrent_ids_to_update = []

                    for torrent in torrents:
                        labels = torrent.get("labels", [])
                        if tag_name in labels:
                            # 移除该标签
                            new_labels = [l for l in labels if l != tag_name]
                            torrent_ids_to_update.append({
                                "id": torrent["id"],
                                "labels": new_labels
                            })

                    # 批量更新种子标签
                    if torrent_ids_to_update:
                        for item in torrent_ids_to_update:
                            self._make_rpc_request({
                                "method": "torrent-set",
                                "arguments": {
                                    "ids": [item["id"]],
                                    "labels": item["labels"]
                                }
                            })

                        logger.info(f"从{len(torrent_ids_to_update)}个种子中移除标签: {tag_name}")

            except Exception as e:
                logger.warning(f"删除Transmission标签时发生错误: {str(e)}")
                return self._format_error_response(message=f"删除标签失败: {str(e)}")

            # 从映射表中移除
            self._unregister_tag_id(tag_id)

            return {
                "success": True,
                "message": f"成功删除标签: {tag_name}",
                "data": tag_info
            }

        except Exception as e:
            logger.error(f"删除标签时发生错误: {str(e)}")
            return self._format_error_response(message=f"删除标签失败: {str(e)}")

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
        """
        try:
            if not tag_ids:
                return self._format_error_response(message="标签ID列表为空")

            # 解析标签信息
            tags = []
            failed_tags = []

            for tag_id in tag_ids:
                tag_info = self._get_tag_info_by_id(tag_id)
                if not tag_info:
                    failed_tags.append({
                        "tag_id": tag_id,
                        "error": "标签不存在"
                    })
                    continue

                # 检查类型：Transmission不支持category
                if tag_info["type"] == 'category':
                    failed_tags.append({
                        "tag_id": tag_id,
                        "error": "Transmission不支持分类",
                        "require_fallback": True,
                        "tag_name": tag_info["name"]
                    })
                    continue

                tags.append(tag_info["name"])

            if not tags:
                return {
                    "success": False,
                    "message": "没有有效的标签可分配",
                    "assigned_count": 0,
                    "failed_count": len(failed_tags),
                    "failed_tags": failed_tags
                }

            # 获取种子ID
            torrent_id = await self._get_torrent_id_by_hash(torrent_hash)
            if not torrent_id:
                return self._format_error_response(
                    message=f"种子不存在: {torrent_hash[:8]}..."
                )

            # 获取种子当前标签
            try:
                response = self._make_rpc_request({
                    "method": "torrent-get",
                    "arguments": {
                        "ids": [torrent_id],
                        "fields": ["labels"]
                    }
                })

                current_labels = set()
                if response and "arguments" in response:
                    torrents = response["arguments"].get("torrents", [])
                    if torrents:
                        current_labels = set(torrents[0].get("labels", []))

                # 合并新旧标签
                new_labels = list(current_labels.union(set(tags)))

                # 设置标签
                response = self._make_rpc_request({
                    "method": "torrent-set",
                    "arguments": {
                        "ids": [torrent_id],
                        "labels": new_labels
                    }
                })

                if response and response.get("result") == "success":
                    logger.info(f"为种子{torrent_hash[:8]}...分配标签: {tags}")
                    return {
                        "success": len(failed_tags) == 0,
                        "message": f"分配完成: 成功{len(tags)}个，失败{len(failed_tags)}个",
                        "assigned_count": len(tags),
                        "failed_count": len(failed_tags),
                        "failed_tags": failed_tags
                    }
                else:
                    return self._format_error_response(
                        message="设置标签失败"
                    )

            except Exception as e:
                logger.error(f"设置标签失败: {str(e)}")
                return self._format_error_response(
                    message=f"分配标签失败: {str(e)}"
                )

        except Exception as e:
            logger.error(f"分配标签时发生错误: {str(e)}")
            return self._format_error_response(message=f"分配标签失败: {str(e)}")

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
        """
        try:
            if not tag_ids:
                return self._format_error_response(message="标签ID列表为空")

            # 获取种子ID
            torrent_id = await self._get_torrent_id_by_hash(torrent_hash)
            if not torrent_id:
                return self._format_error_response(
                    message=f"种子不存在: {torrent_hash[:8]}..."
                )

            # 获取种子当前标签
            try:
                response = self._make_rpc_request({
                    "method": "torrent-get",
                    "arguments": {
                        "ids": [torrent_id],
                        "fields": ["labels"]
                    }
                })

                if not (response and "arguments" in response):
                    return self._format_error_response(message="获取种子信息失败")

                torrents = response["arguments"].get("torrents", [])
                if not torrents:
                    return self._format_error_response(
                        message=f"种子不存在: {torrent_hash[:8]}..."
                    )

                current_labels = set(torrents[0].get("labels", []))

                # 解析要移除的标签
                tags_to_remove = []
                failed_tags = []

                for tag_id in tag_ids:
                    tag_info = self._get_tag_info_by_id(tag_id)
                    if not tag_info:
                        failed_tags.append({
                            "tag_id": tag_id,
                            "error": "标签不存在"
                        })
                        continue

                    if tag_info["type"] == 'category':
                        failed_tags.append({
                            "tag_id": tag_id,
                            "error": "Transmission不支持分类"
                        })
                        continue

                    tags_to_remove.append(tag_info["name"])

                # 移除标签
                new_labels = [l for l in current_labels if l not in tags_to_remove]

                # 设置新标签列表
                response = self._make_rpc_request({
                    "method": "torrent-set",
                    "arguments": {
                        "ids": [torrent_id],
                        "labels": new_labels
                    }
                })

                if response and response.get("result") == "success":
                    removed_count = len(tags_to_remove)
                    logger.info(f"从种子{torrent_hash[:8]}...移除标签: {tags_to_remove}")
                    return {
                        "success": len(failed_tags) == 0,
                        "message": f"移除完成: 成功{removed_count}个，失败{len(failed_tags)}个",
                        "removed_count": removed_count,
                        "failed_count": len(failed_tags),
                        "failed_tags": failed_tags
                    }
                else:
                    return self._format_error_response(message="移除标签失败")

            except Exception as e:
                logger.error(f"移除标签失败: {str(e)}")
                return self._format_error_response(
                    message=f"移除标签失败: {str(e)}"
                )

        except Exception as e:
            logger.error(f"移除标签时发生错误: {str(e)}")
            return self._format_error_response(message=f"移除标签失败: {str(e)}")

    async def get_torrent_tags(self, torrent_hash: str) -> Dict[str, Any]:
        """
        获取种子的所有标签

        Args:
            torrent_hash: 种子哈希值

        Returns:
            Dict[str, Any]: 统一格式的响应
        """
        try:
            # 获取种子ID
            torrent_id = await self._get_torrent_id_by_hash(torrent_hash)
            if not torrent_id:
                return self._format_error_response(
                    message=f"种子不存在: {torrent_hash[:8]}...",
                    data=[]
                )

            # 获取种子标签
            response = self._make_rpc_request({
                "method": "torrent-get",
                "arguments": {
                    "ids": [torrent_id],
                    "fields": ["labels"]
                }
            })

            if not (response and "arguments" in response):
                return self._format_error_response(
                    message="获取种子信息失败",
                    data=[]
                )

            torrents = response["arguments"].get("torrents", [])
            if not torrents:
                return self._format_error_response(
                    message=f"种子不存在: {torrent_hash[:8]}...",
                    data=[]
                )

            labels = torrents[0].get("labels", [])
            all_tags = []

            for label_name in labels:
                tag_id = self._get_or_create_tag_id(label_name, 'tag')

                all_tags.append({
                    "tag_id": tag_id,
                    "name": label_name,
                    "type": "tag",
                    "color": None,
                    "assigned": True
                })

            return self._format_success_response(
                data=all_tags,
                message=f"成功获取{len(all_tags)}个标签"
            )

        except Exception as e:
            logger.error(f"获取种子标签时发生错误: {str(e)}")
            return self._format_error_response(
                message=f"获取种子标签失败: {str(e)}",
                data=[]
            )

    # ==================== 私有辅助方法 ====================

    def _make_rpc_request(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        发送Transmission RPC请求

        Args:
            request_data: 请求数据

        Returns:
            Optional[Dict]: 响应数据
        """
        try:
            headers = {}
            if self.session_id:
                headers["X-Transmission-Session-Id"] = self.session_id

            response = self.session.post(
                self.rpc_url,
                json=request_data,
                headers=headers,
                timeout=30.0
            )

            # 检查是否需要更新session ID
            if response.status_code == 409:
                self.session_id = response.headers.get("X-Transmission-Session-Id")
                if self.session_id:
                    # 重新发送请求
                    headers["X-Transmission-Session-Id"] = self.session_id
                    response = self.session.post(
                        self.rpc_url,
                        json=request_data,
                        headers=headers,
                        timeout=30.0
                    )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Transmission RPC请求失败: {str(e)}")
            return None

    async def _get_torrent_id_by_hash(self, torrent_hash: str) -> Optional[int]:
        """
        通过种子哈希获取种子ID

        Args:
            torrent_hash: 种子哈希值

        Returns:
            Optional[int]: 种子ID，不存在则返回None
        """
        try:
            response = self._make_rpc_request({
                "method": "torrent-get",
                "arguments": {
                    "fields": ["id", "hashString"]
                }
            })

            if response and "arguments" in response:
                torrents = response["arguments"].get("torrents", [])
                for torrent in torrents:
                    if torrent.get("hashString", "").lower() == torrent_hash.lower():
                        return torrent.get("id")

            return None

        except Exception as e:
            logger.error(f"获取种子ID失败: {str(e)}")
            return None

    def _get_or_create_tag_id(self, tag_name: str, tag_type: str) -> str:
        """
        获取或创建标签ID

        Args:
            tag_name: 标签名称
            tag_type: 标签类型

        Returns:
            str: 标签UUID
        """
        key = f"{tag_type}:{tag_name}"

        # 如果已存在，返回现有ID
        if key in self._name_id_map:
            return self._name_id_map[key]

        # 创建新ID
        tag_id = str(uuid.uuid4())
        self._register_tag_id(tag_id, tag_name, tag_type)
        return tag_id

    def _register_tag_id(self, tag_id: str, tag_name: str, tag_type: str):
        """
        注册标签ID映射

        Args:
            tag_id: 标签UUID
            tag_name: 标签名称
            tag_type: 标签类型
        """
        key = f"{tag_type}:{tag_name}"
        self._tag_id_map[tag_id] = key
        self._name_id_map[key] = tag_id
        logger.debug(f"注册标签ID映射: {tag_id} -> {key}")

    def _unregister_tag_id(self, tag_id: str):
        """
        注销标签ID映射

        Args:
            tag_id: 标签UUID
        """
        if tag_id in self._tag_id_map:
            key = self._tag_id_map[tag_id]
            del self._tag_id_map[tag_id]
            if key in self._name_id_map:
                del self._name_id_map[key]
            logger.debug(f"注销标签ID映射: {tag_id}")

    def _get_tag_info_by_id(self, tag_id: str) -> Optional[Dict[str, Any]]:
        """
        通过标签ID获取标签信息

        Args:
            tag_id: 标签UUID

        Returns:
            Optional[Dict]: 标签信息，不存在则返回None
        """
        if tag_id not in self._tag_id_map:
            return None

        key = self._tag_id_map[tag_id]
        # key格式: "type:name"
        parts = key.split(':', 1)
        if len(parts) != 2:
            return None

        return {
            "tag_id": tag_id,
            "type": parts[0],
            "name": parts[1]
        }
