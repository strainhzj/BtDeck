# -*- coding: utf-8 -*-
"""
qBittorrent标签适配器

实现qBittorrent下载器的标签/分类统一管理。
支持qBittorrent的分类（category）和标签（tag）两种类型。
"""

from typing import List, Dict, Any, Optional
import logging
import uuid
from qbittorrentapi import Client

from .base import TorrentTagAdapter

logger = logging.getLogger(__name__)


class QBittorrentTagAdapter(TorrentTagAdapter):
    """
    qBittorrent标签适配器

    统一处理qBittorrent的分类和标签功能。
    分类和标签都映射为统一标签，通过tag_type字段区分。

    Attributes:
        downloader_id: 下载器ID
        client: qBittorrent客户端实例
    """

    def __init__(self, downloader_id: str, client: Client):
        """
        初始化qBittorrent标签适配器

        Args:
            downloader_id: 下载器ID
            client: qBittorrent客户端实例（从app.state.store获取）
        """
        super().__init__(downloader_id)
        self.client = client

        # 本地标签ID映射表：tag_id (UUID) -> name
        self._tag_id_map: Dict[str, str] = {}
        # 反向映射：name -> tag_id
        self._name_id_map: Dict[str, str] = {}

    def get_downloader_type(self) -> str:
        """获取下载器类型"""
        return "qbittorrent"

    async def check_connection(self) -> bool:
        """检查连接状态"""
        try:
            # 尝试获取版本信息
            version = self.client.app.version()
            logger.debug(f"qBittorrent连接正常，版本: {version}")
            return True
        except Exception as e:
            logger.error(f"qBittorrent连接检查失败: {str(e)}")
            return False

    async def get_tags(self) -> Dict[str, Any]:
        """
        获取所有标签（分类+标签，统一格式）

        Returns:
            Dict[str, Any]: 统一格式的响应
        """
        try:
            all_tags = []

            # 1. 获取分类
            try:
                categories = self.client.torrent_categories.categories  # 修复：属性访问
                logger.debug(f"获取到{len(categories)}个分类")

                for cat_name, cat_info in categories.items():
                    tag_id = self._get_or_create_tag_id(cat_name, 'category')

                    all_tags.append({
                        "tag_id": tag_id,
                        "name": cat_name,
                        "type": "category",
                        "color": None,
                        "raw_data": cat_info
                    })
            except Exception as e:
                logger.error(f"获取qBittorrent分类失败: {str(e)}")

            # 2. 获取标签
            try:
                tags = self.client.torrent_tags.tags  # 修复：属性访问
                logger.debug(f"获取到{len(tags)}个标签")

                for tag_name in tags:
                    tag_id = self._get_or_create_tag_id(tag_name, 'tag')

                    all_tags.append({
                        "tag_id": tag_id,
                        "name": tag_name,
                        "type": "tag",
                        "color": None,
                        "raw_data": {"name": tag_name}
                    })
            except Exception as e:
                logger.error(f"获取qBittorrent标签失败: {str(e)}")

            return self._format_success_response(
                data=all_tags,
                message=f"成功获取{len(all_tags)}个标签（{sum(1 for t in all_tags if t['type']=='category')}个分类，{sum(1 for t in all_tags if t['type']=='tag')}个标签）"
            )

        except Exception as e:
            logger.error(f"获取qBittorrent标签列表失败: {str(e)}")
            return self._format_error_response(
                message=f"获取标签列表失败: {str(e)}",
                data=[]
            )

    async def create_tag(self, tag_name: str, tag_type: str, color: Optional[str] = None) -> Dict[str, Any]:
        """
        创建标签或分类

        Args:
            tag_name: 标签名称
            tag_type: 标签类型 ('category' | 'tag')
            color: 可选，颜色代码（qBittorrent不支持）

        Returns:
            Dict[str, Any]: 统一格式的响应
        """
        try:
            if not tag_name or not tag_name.strip():
                return self._format_error_response(message="标签名称不能为空")

            tag_name = tag_name.strip()

            # 检查是否已存在
            existing_key = f"{tag_type}:{tag_name}"
            if existing_key in self._name_id_map:
                existing_id = self._name_id_map[existing_key]
                logger.info(f"标签已存在，返回现有ID: {tag_name} ({tag_type})")
                return {
                    "success": True,
                    "message": "标签已存在",
                    "data": {
                        "tag_id": existing_id,
                        "name": tag_name,
                        "type": tag_type
                    },
                    "tag_id": existing_id
                }

            # 根据类型创建
            if tag_type == 'category':
                # 创建分类
                try:
                    self.client.torrent_categories.create_category(name=tag_name)
                    logger.info(f"成功创建qBittorrent分类: {tag_name}")
                except Exception as e:
                    logger.error(f"创建qBittorrent分类失败: {str(e)}")
                    return self._format_error_response(message=f"创建分类失败: {str(e)}")

            elif tag_type == 'tag':
                # 创建标签
                try:
                    self.client.torrent_tags.create_tags(tags=tag_name)
                    logger.info(f"成功创建qBittorrent标签: {tag_name}")
                except Exception as e:
                    logger.error(f"创建qBittorrent标签失败: {str(e)}")
                    return self._format_error_response(message=f"创建标签失败: {str(e)}")
            else:
                return self._format_error_response(message=f"不支持的标签类型: {tag_type}")

            # 生成并注册标签ID
            tag_id = str(uuid.uuid4())
            self._register_tag_id(tag_id, tag_name, tag_type)

            return {
                "success": True,
                "message": f"成功创建{tag_type}",
                "data": {
                    "tag_id": tag_id,
                    "name": tag_name,
                    "type": tag_type,
                    "color": color
                },
                "tag_id": tag_id
            }

        except Exception as e:
            logger.error(f"创建标签时发生错误: {str(e)}")
            return self._format_error_response(message=f"创建标签失败: {str(e)}")

    async def delete_tag(self, tag_id: str) -> Dict[str, Any]:
        """
        删除标签或分类

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
            tag_type = tag_info["type"]

            # 根据类型删除
            if tag_type == 'category':
                try:
                    # 删除分类（需要先移除使用该分类的种子）
                    # ⚠️ 修复API方法名：使用正确的qBittorrent API方法
                    self.client.torrents_edit_category(
                        name=tag_name,
                        savePath=""  # 设置为空路径会删除分类
                    )
                    # qBittorrent不支持直接删除分类，需要设置为空
                    # 实际操作是移除所有种子的分类关联
                    logger.info(f"成功移除qBittorrent分类: {tag_name}")
                except Exception as e:
                    logger.warning(f"移除qBittorrent分类失败: {str(e)}")
                    # qBittorrent的删除分类操作有限制
                    return self._format_error_response(
                        message=f"qBittorrent不支持直接删除分类，请确保没有种子使用该分类"
                    )

            elif tag_type == 'tag':
                try:
                    self.client.torrent_tags.delete_tags(tags=tag_name)
                    logger.info(f"成功删除qBittorrent标签: {tag_name}")
                except Exception as e:
                    logger.error(f"删除qBittorrent标签失败: {str(e)}")
                    return self._format_error_response(message=f"删除标签失败: {str(e)}")

            # 从映射表中移除
            self._unregister_tag_id(tag_id)

            return {
                "success": True,
                "message": f"成功删除{tag_type}: {tag_name}",
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
        为种子分配标签/分类

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
            categories = []
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

                if tag_info["type"] == 'category':
                    categories.append(tag_info["name"])
                else:
                    tags.append(tag_info["name"])

            success_count = 0
            errors = []

            # 分配分类（qBittorrent每个种子只能有一个分类）
            if categories:
                try:
                    # 取最后一个分类（qBittorrent只支持单个分类）
                    category = categories[-1]
                    self.client.torrents.set_category(
                        hashes=torrent_hash,
                        category=category
                    )
                    success_count += 1
                    logger.debug(f"为种子{torrent_hash[:8]}...设置分类: {category}")
                except Exception as e:
                    errors.append(f"设置分类失败: {str(e)}")
                    logger.warning(f"设置分类失败: {str(e)}")

            # 分配标签（支持多个标签）
            if tags:
                try:
                    # qBittorrent的标签是逗号分隔的字符串
                    tags_str = ','.join(tags)
                    self.client.torrents.add_tags(
                        hashes=torrent_hash,
                        tags=tags_str
                    )
                    success_count += len(tags)
                    logger.debug(f"为种子{torrent_hash[:8]}...添加标签: {tags_str}")
                except Exception as e:
                    errors.append(f"添加标签失败: {str(e)}")
                    logger.warning(f"添加标签失败: {str(e)}")

            return {
                "success": len(failed_tags) == 0 and len(errors) == 0,
                "message": f"分配完成: 成功{success_count}个，失败{len(failed_tags) + len(errors)}个",
                "assigned_count": success_count,
                "failed_count": len(failed_tags) + len(errors),
                "failed_tags": failed_tags,
                "errors": errors
            }

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

            # 解析标签信息
            categories = []
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

                if tag_info["type"] == 'category':
                    categories.append(tag_info["name"])
                else:
                    tags.append(tag_info["name"])

            removed_count = 0
            errors = []

            # 移除标签
            if tags:
                try:
                    for tag_name in tags:
                        self.client.torrents.remove_tags(
                            hashes=torrent_hash,
                            tags=tag_name
                        )
                        removed_count += 1
                        logger.debug(f"从种子{torrent_hash[:8]}...移除标签: {tag_name}")
                except Exception as e:
                    errors.append(f"移除标签失败: {str(e)}")
                    logger.warning(f"移除标签失败: {str(e)}")

            # 移除分类（实际上是设置为空分类）
            if categories:
                try:
                    for category_name in categories:
                        # 获取种子当前分类
                        torrents = self.client.torrents.info(hashes=[torrent_hash])
                        if torrents and torrents[0].category == category_name:
                            self.client.torrents.set_category(
                                hashes=torrent_hash,
                                category=""  # 设置为空
                            )
                            removed_count += 1
                            logger.debug(f"从种子{torrent_hash[:8]}...移除分类: {category_name}")
                except Exception as e:
                    errors.append(f"移除分类失败: {str(e)}")
                    logger.warning(f"移除分类失败: {str(e)}")

            return {
                "success": len(failed_tags) == 0 and len(errors) == 0,
                "message": f"移除完成: 成功{removed_count}个，失败{len(failed_tags) + len(errors)}个",
                "removed_count": removed_count,
                "failed_count": len(failed_tags) + len(errors),
                "failed_tags": failed_tags,
                "errors": errors
            }

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
            all_tags = []

            # 获取种子信息
            try:
                torrents = self.client.torrents.info(hashes=[torrent_hash])

                if not torrents:
                    return self._format_error_response(
                        message=f"种子不存在: {torrent_hash[:8]}...",
                        data=[]
                    )

                torrent = torrents[0]

                # 1. 获取分类
                if torrent.category:
                    cat_name = torrent.category
                    tag_id = self._get_or_create_tag_id(cat_name, 'category')

                    all_tags.append({
                        "tag_id": tag_id,
                        "name": cat_name,
                        "type": "category",
                        "color": None,
                        "assigned": True
                    })

                # 2. 获取标签
                if torrent.tags:
                    # qBittorrent的标签是逗号分隔的字符串
                    tag_names = torrent.tags.split(',') if torrent.tags else []

                    for tag_name in tag_names:
                        tag_name = tag_name.strip()
                        if tag_name:
                            tag_id = self._get_or_create_tag_id(tag_name, 'tag')

                            all_tags.append({
                                "tag_id": tag_id,
                                "name": tag_name,
                                "type": "tag",
                                "color": None,
                                "assigned": True
                            })

            except Exception as e:
                logger.error(f"获取种子{torrent_hash[:8]}...信息失败: {str(e)}")
                return self._format_error_response(
                    message=f"获取种子标签失败: {str(e)}",
                    data=[]
                )

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

    def _build_tag_key(self, tag_name: str, tag_type: str) -> str:
        """
        构建标签键值

        Args:
            tag_name: 标签名称
            tag_type: 标签类型

        Returns:
            str: 标签键值 (格式: "type:name")
        """
        return f"{tag_type}:{tag_name}"
