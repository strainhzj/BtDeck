# -*- coding: utf-8 -*-
"""
标签降级策略处理器

处理Transmission不支持分类功能时的降级策略。
将分类操作自动转换为标签操作，提供用户友好的降级提示。
"""

from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class FallbackHandler:
    """
    降级策略处理器

    提供静态方法用于检查和执行降级策略。
    主要处理Transmission不支持分类功能的场景。

    降级场景:
        1. 用户尝试为Transmission种子分配分类
        2. 检测到下载器类型为Transmission
        3. 返回降级提示，询问用户是否转换为标签
        4. 用户确认后执行标签分配
    """

    # 下载器类型常量
    DOWNLOADER_QBITTORRENT = "qbittorrent"
    DOWNLOADER_TRANSMISSION = "transmission"

    # 标签类型常量
    TAG_TYPE_CATEGORY = "category"
    TAG_TYPE_TAG = "tag"

    # 降级类型常量
    FALLBACK_CATEGORY_TO_TAG = "category_to_tag"

    # 分类标签前缀（用于区分转换后的标签）
    CATEGORY_TAG_PREFIX = "[分类] "

    @staticmethod
    def check_category_support(downloader_type: str) -> Dict[str, Any]:
        """
        检查下载器是否支持分类功能

        Args:
            downloader_type: 下载器类型 ('qbittorrent' | 'transmission')

        Returns:
            Dict[str, Any]: 检查结果
                {
                    "supported": bool,           # 是否支持分类
                    "require_fallback": bool,     # 是否需要降级
                    "fallback_type": str,         # 降级类型
                    "message": str,              # 提示消息
                    "suggestion": str            # 转换建议
                }
        """
        if downloader_type == FallbackHandler.DOWNLOADER_TRANSMISSION:
            return {
                "supported": False,
                "require_fallback": True,
                "downloader_type": downloader_type,
                "fallback_type": FallbackHandler.FALLBACK_CATEGORY_TO_TAG,
                "message": "Transmission不支持分类功能",
                "suggestion": "您可以将分类名转换为标签，以达到类似的管理效果"
            }
        elif downloader_type == FallbackHandler.DOWNLOADER_QBITTORRENT:
            return {
                "supported": True,
                "require_fallback": False,
                "downloader_type": downloader_type,
                "message": "qBittorrent支持分类和标签功能"
            }
        else:
            # 未知下载器类型，默认不支持
            return {
                "supported": False,
                "require_fallback": True,
                "downloader_type": downloader_type,
                "fallback_type": FallbackHandler.FALLBACK_CATEGORY_TO_TAG,
                "message": f"未知的下载器类型: {downloader_type}",
                "suggestion": "请联系管理员确认该下载器的功能支持情况"
            }

    @staticmethod
    def check_batch_category_support(
        downloader_type: str,
        tag_ids: List[str],
        tag_info_getter
    ) -> Dict[str, Any]:
        """
        批量检查标签中是否包含不支持的分类

        Args:
            downloader_type: 下载器类型
            tag_ids: 标签ID列表
            tag_info_getter: 获取标签信息的函数 (tag_id -> Dict)

        Returns:
            Dict[str, Any]: 检查结果
                {
                    "can_proceed": bool,           # 是否可以直接继续
                    "require_fallback": bool,      # 是否需要降级
                    "category_tags": List[dict],   # 需要降级的分类标签
                    "tag_tags": List[str],        # 可直接使用的标签ID
                    "message": str                # 提示消息
                }
        """
        # 检查下载器支持
        support_check = FallbackHandler.check_category_support(downloader_type)

        if support_check["supported"]:
            # 下载器支持分类，可以直接使用
            return {
                "can_proceed": True,
                "require_fallback": False,
                "category_tags": [],
                "tag_tags": tag_ids,
                "message": "所有标签都可以正常使用"
            }

        # 下载器不支持分类，需要检查标签列表
        category_tags = []
        tag_tags = []

        for tag_id in tag_ids:
            tag_info = tag_info_getter(tag_id)
            if not tag_info:
                continue

            if tag_info.get("type") == FallbackHandler.TAG_TYPE_CATEGORY:
                category_tags.append({
                    "tag_id": tag_id,
                    "name": tag_info.get("name", ""),
                    "type": "category"
                })
            else:
                tag_tags.append(tag_id)

        if not category_tags:
            # 没有分类标签，可以继续
            return {
                "can_proceed": True,
                "require_fallback": False,
                "category_tags": [],
                "tag_tags": tag_tags,
                "message": "所有标签都可以正常使用"
            }

        # 有分类标签，需要降级
        category_names = [t["name"] for t in category_tags]
        return {
            "can_proceed": False,
            "require_fallback": True,
            "downloader_type": downloader_type,
            "category_tags": category_tags,
            "tag_tags": tag_tags,
            "fallback_type": FallbackHandler.FALLBACK_CATEGORY_TO_TAG,
            "message": f"检测到{len(category_tags)}个分类标签: {', '.join(category_names)}",
            "suggestion": f"Transmission不支持分类，是否将以下分类转换为标签？{', '.join(category_names)}"
        }

    @staticmethod
    def fallback_category_to_tag(category_name: str, add_prefix: bool = True) -> str:
        """
        将分类名转换为标签名

        Args:
            category_name: 原分类名称
            add_prefix: 是否添加前缀标记

        Returns:
            str: 转换后的标签名
        """
        if add_prefix:
            return f"{FallbackHandler.CATEGORY_TAG_PREFIX}{category_name}"
        return category_name

    @staticmethod
    def fallback_batch_categories_to_tags(
        category_names: List[str],
        add_prefix: bool = True
    ) -> Dict[str, Any]:
        """
        批量将分类名转换为标签名

        Args:
            category_names: 分类名称列表
            add_prefix: 是否添加前缀标记

        Returns:
            Dict[str, Any]: 转换结果
                {
                    "success": bool,
                    "mapping": dict,       # 原分类名 -> 标签名
                    "tag_names": List[str], # 转换后的标签名列表
                    "message": str
                }
        """
        mapping = {}
        tag_names = []

        for category_name in category_names:
            tag_name = FallbackHandler.fallback_category_to_tag(category_name, add_prefix)
            mapping[category_name] = tag_name
            tag_names.append(tag_name)

        return {
            "success": True,
            "mapping": mapping,
            "tag_names": tag_names,
            "message": f"成功将{len(category_names)}个分类转换为标签"
        }

    @staticmethod
    def is_category_tag(tag_name: str) -> bool:
        """
        检查标签名是否为转换后的分类标签

        Args:
            tag_name: 标签名称

        Returns:
            bool: 是否为转换后的分类标签
        """
        return tag_name.startswith(FallbackHandler.CATEGORY_TAG_PREFIX)

    @staticmethod
    def extract_original_category(tag_name: str) -> Optional[str]:
        """
        从转换后的标签名中提取原始分类名

        Args:
            tag_name: 标签名称

        Returns:
            Optional[str]: 原始分类名，如果不是转换标签则返回None
        """
        if FallbackHandler.is_category_tag(tag_name):
            return tag_name[len(FallbackHandler.CATEGORY_TAG_PREFIX):]
        return None

    @staticmethod
    def format_fallback_prompt(
        downloader_type: str,
        category_names: List[str]
    ) -> str:
        """
        格式化降级提示信息（用于显示给用户）

        Args:
            downloader_type: 下载器类型
            category_names: 分类名称列表

        Returns:
            str: 格式化的提示信息
        """
        if downloader_type == FallbackHandler.DOWNLOADER_TRANSMISSION:
            return (
                f"⚠️ Transmission不支持分类功能\n\n"
                f"检测到 {len(category_names)} 个分类标签:\n"
                f"  {', '.join(category_names)}\n\n"
                f"建议: 将这些分类转换为标签以实现类似的管理效果\n"
                f"转换后的标签将添加 '{FallbackHandler.CATEGORY_TAG_PREFIX}' 前缀以便区分"
            )

        return (
            f"⚠️ 该下载器不支持分类功能\n\n"
            f"检测到 {len(category_names)} 个分类标签:\n"
            f"  {', '.join(category_names)}"
        )

    @staticmethod
    def validate_fallback_decision(
        user_decision: bool,
        category_names: List[str]
    ) -> Dict[str, Any]:
        """
        验证用户的降级决策

        Args:
            user_decision: 用户是否同意降级
            category_names: 分类名称列表

        Returns:
            Dict[str, Any]: 验证结果
                {
                    "can_proceed": bool,
                    "action": str,        # 'proceed_with_tags' | 'cancel' | 'partial'
                    "message": str,
                    "converted_tags": List[str]  # 转换后的标签名
                }
        """
        if not user_decision:
            return {
                "can_proceed": False,
                "action": "cancel",
                "message": "用户取消操作，未进行标签分配"
            }

        # 用户同意降级，执行转换
        result = FallbackHandler.fallback_batch_categories_to_tags(category_names)

        return {
            "can_proceed": True,
            "action": "proceed_with_tags",
            "message": result["message"],
            "converted_tags": result["tag_names"],
            "mapping": result["mapping"]
        }

    @staticmethod
    def get_adapter_by_type(
        downloader_type: str,
        downloader_id: str,
        app_state_store
    ):
        """
        根据下载器类型获取对应的适配器实例

        Args:
            downloader_type: 下载器类型
            downloader_id: 下载器ID
            app_state_store: 应用状态存储 (app.state.store)

        Returns:
            对应的适配器实例，或None（如果不支持的类型）
        """
        from .qbittorrent_adapter import QBittorrentTagAdapter
        from .transmission_adapter import TransmissionTagAdapter

        # 从缓存获取下载器信息
        cached_downloaders = app_state_store.get_snapshot_sync()
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == downloader_id),
            None
        )

        if not downloader_vo or downloader_vo.fail_time > 0:
            logger.error(f"下载器不可用: {downloader_id}")
            return None

        # 根据类型创建适配器
        if downloader_vo.downloader_type == 0:  # qBittorrent
            return QBittorrentTagAdapter(
                downloader_id=downloader_id,
                client=downloader_vo.client
            )
        elif downloader_vo.downloader_type == 1:  # Transmission
            return TransmissionTagAdapter(
                downloader_id=downloader_id,
                session=downloader_vo.session,
                rpc_url=downloader_vo.rpc_url,
                session_id=getattr(downloader_vo, 'session_id', None)
            )

        logger.error(f"不支持的下载器类型: {downloader_vo.downloader_type}")
        return None

    @staticmethod
    def get_downloader_type_constant(downloader_type_int: int) -> str:
        """
        将下载器类型整数转换为字符串常量

        Args:
            downloader_type_int: 下载器类型整数 (0=qbittorrent, 1=transmission)

        Returns:
            str: 下载器类型字符串
        """
        type_mapping = {
            0: FallbackHandler.DOWNLOADER_QBITTORRENT,
            1: FallbackHandler.DOWNLOADER_TRANSMISSION
        }
        return type_mapping.get(downloader_type_int, "unknown")
