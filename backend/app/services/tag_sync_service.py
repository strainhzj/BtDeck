# -*- coding: utf-8 -*-
"""
标签同步服务（优化版）

优化点：
1. ✅ 去掉数据库查询，直接从缓存获取下载器
2. ✅ 动态构建RPC URL，修复AttributeError
3. ✅ 统一使用SDK方法获取标签和分类

负责从下载器获取标签数据并同步到数据库。
支持手动触发和定时自动同步两种模式。
"""

from typing import List, Dict, Any, Optional, Union
import logging

from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tag_service import TagService
from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory
from app.models.setting_templates import DownloaderTypeEnum

logger = logging.getLogger(__name__)


class TagSyncService:
    """
    标签同步服务类（优化版）

    优化内容：
    - ✅ 直接从缓存获取下载器，减少数据库I/O
    - ✅ 动态构建RPC URL，修复AttributeError
    - ✅ 统一使用SDK方法获取标签数据
    """

    def __init__(self, db: Union[Session, AsyncSession]):
        """
        初始化标签同步服务

        Args:
            db: SQLAlchemy会话（同步Session或异步AsyncSession）
        """
        self.db = db
        self.is_async = isinstance(db, AsyncSession)
        # 根据会话类型创建对应的TagService
        self.tag_service = TagService(db)

    # ==================== 核心同步方法（优化版）====================

    async def sync_all_downloaders(
        self,
        delete_missing: bool = True
    ) -> Dict[str, Any]:
        """
        同步所有下载器的标签数据（优化版）

        优化点：
        - ✅ 去掉数据库查询，直接从缓存获取
        - ✅ 过滤出连接良好的下载器（fail_time=0）

        Args:
            delete_missing: 是否删除下载器中不存在的标签

        Returns:
            全量同步结果字典
            {
                "success": bool,
                "message": str,
                "total_downloaders": int,
                "success_count": int,
                "failed_count": int,
                "total_tags_synced": int,
                "details": List[Dict]
            }
        """
        try:
            from app.main import app

            # ✅ 优化1：直接从缓存获取下载器（去掉数据库查询）
            if not hasattr(app.state, 'store'):
                logger.warning("下载器缓存未初始化，跳过标签同步")
                return {
                    "success": True,
                    "message": "缓存未初始化，无需同步",
                    "total_downloaders": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "total_tags_synced": 0,
                    "details": []
                }

            # 获取缓存快照
            cached_downloaders = await app.state.store.get_snapshot()

            if not cached_downloaders:
                logger.info("缓存中没有下载器，无需同步")
                return {
                    "success": True,
                    "message": "无下载器需要同步",
                    "total_downloaders": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "total_tags_synced": 0,
                    "details": []
                }

            # ✅ 优化2：过滤出连接良好的下载器
            valid_downloaders = []
            for cached in cached_downloaders:
                # 检查连接状态
                if not hasattr(cached, 'fail_time') or cached.fail_time > 0:
                    logger.debug(
                        f"跳过失效下载器: {cached.nickname} "
                        f"(fail_time: {getattr(cached, 'fail_time', 'N/A')})"
                    )
                    continue

                # 检查客户端连接是否存在
                if not hasattr(cached, 'client') or not cached.client:
                    logger.debug(f"跳过无客户端下载器: {cached.nickname}")
                    continue

                # ✅ 通过所有检查，加入有效列表
                valid_downloaders.append(cached)

            if not valid_downloaders:
                logger.info("没有连接良好的下载器需要同步")
                return {
                    "success": True,
                    "message": "无有效下载器需要同步",
                    "total_downloaders": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "total_tags_synced": 0,
                    "details": []
                }

            logger.info(f"开始同步{len(valid_downloaders)}个有效下载器的标签")

            results = []
            success_count = 0
            failed_count = 0
            total_tags = 0

            # 逐个同步
            for downloader in valid_downloaders:
                try:
                    result = await self.sync_downloader_tags(
                        downloader,  # ✅ 直接传递缓存对象
                        delete_missing=delete_missing
                    )
                    results.append(result)

                    if result.get("success"):
                        success_count += 1
                        total_tags += result.get("total_tags", 0)
                    else:
                        failed_count += 1

                except Exception as e:
                    logger.error(f"同步下载器 {downloader.nickname} 失败: {str(e)}")
                    failed_count += 1
                    results.append({
                        "success": False,
                        "downloader_id": downloader.downloader_id,
                        "downloader_name": downloader.nickname,
                        "message": f"同步异常: {str(e)}"
                    })

            return {
                "success": failed_count == 0,
                "message": f"全量同步完成: 成功{success_count}，失败{failed_count}",
                "total_downloaders": len(valid_downloaders),
                "success_count": success_count,
                "failed_count": failed_count,
                "total_tags_synced": total_tags,
                "details": results
            }

        except Exception as e:
            logger.error(f"全量同步失败: {str(e)}")
            return {
                "success": False,
                "message": f"全量同步失败: {str(e)}",
                "total_downloaders": 0,
                "success_count": 0,
                "failed_count": 1,
                "total_tags_synced": 0
            }

    async def sync_downloader_tags(
        self,
        downloader: Any,  # ✅ 类型：DownloaderVO（缓存对象）
        delete_missing: bool = True
    ) -> Dict[str, Any]:
        """
        同步指定下载器的标签数据（优化版）

        优化点：
        - ✅ 直接接收缓存对象，不需要再查询数据库
        - ✅ 动态构建RPC URL，修复AttributeError
        - ✅ 统一使用SDK方法获取标签

        Args:
            downloader: 下载器缓存对象（DownloaderVO）
            delete_missing: 是否删除下载器中不存在的标签（僵尸数据处理）

        Returns:
            同步结果字典
            {
                "success": bool,
                "downloader_id": str,
                "downloader_name": str,
                "total_tags": int,
                "created_count": int,
                "updated_count": int,
                "unchanged_count": int,
                "deleted_count": int,
                "message": str
            }
        """
        try:
            # 1. ✅ 优化：直接使用缓存对象，不需要查询数据库
            downloader_id = downloader.downloader_id
            nickname = downloader.nickname

            # 2. 获取客户端连接
            client = getattr(downloader, 'client', None)
            if not client:
                return {
                    "success": False,
                    "message": f"下载器客户端连接不存在: {nickname}",
                    "total_tags": 0
                }

            # 3. 从下载器获取标签数据
            fetch_result = await self.fetch_tags_from_downloader(downloader)
            if not fetch_result.get("success"):
                return {
                    "success": False,
                    "message": f"获取下载器标签失败: {fetch_result.get('message')}",
                    "total_tags": 0
                }

            new_tags = fetch_result.get("data", [])

            # 4. 合并到数据库
            merge_result = await self.merge_with_existing_tags(
                downloader_id,
                new_tags,
                delete_missing=delete_missing
            )

            return {
                "success": True,
                "downloader_id": downloader_id,
                "downloader_name": nickname,
                "total_tags": len(new_tags),
                **merge_result
            }

        except Exception as e:
            logger.error(f"同步下载器标签失败 ({downloader.downloader_id}): {str(e)}")
            return {
                "success": False,
                "message": f"同步失败: {str(e)}",
                "total_tags": 0
            }

    # ==================== 数据获取方法（优化版）====================

    async def fetch_tags_from_downloader(
        self,
        downloader: Any  # ✅ 类型：DownloaderVO（缓存对象）
    ) -> Dict[str, Any]:
        """
        从下载器获取标签数据（优化版）

        优化点：
        - ✅ 使用SDK方法获取标签，避免手动解析
        - ✅ 动态构建RPC URL，修复AttributeError

        Args:
            downloader: 下载器缓存对象（DownloaderVO）

        Returns:
            统一格式的标签数据
            {
                "success": bool,
                "data": List[Dict],  # 标签列表
                "message": str,
                "total_count": int
            }
        """
        try:
            # 获取客户端连接
            client = getattr(downloader, 'client', None)
            if not client:
                return {
                    "success": False,
                    "data": [],
                    "message": "下载器客户端连接不存在",
                    "total_count": 0
                }

            # 标准化下载器类型
            normalized_type = DownloaderTypeEnum.normalize(downloader.downloader_type)

            if normalized_type == DownloaderTypeEnum.UNKNOWN:
                return {
                    "success": False,
                    "data": [],
                    "message": f"不支持的下载器类型: {downloader.downloader_type}",
                    "total_count": 0
                }

            client_type = 'qbittorrent' if normalized_type == DownloaderTypeEnum.QBITTORRENT else 'transmission'

            # ✅ 优化：根据类型使用不同的获取策略
            if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                # qBittorrent：使用SDK方法（已实现）
                adapter = TagAdapterFactory.create_adapter(
                    downloader=downloader,
                    client=client,
                    session=None,
                    rpc_url=None
                )
            elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                # Transmission：动态构建RPC URL
                # ✅ 修复：兼容is_ssl和isSsl两种属性名
                has_ssl = getattr(downloader, 'is_ssl', None)
                if has_ssl is None:
                    has_ssl = getattr(downloader, 'isSsl', False)

                # 处理布尔值和字符串'1'的情况
                if isinstance(has_ssl, bool):
                    protocol = 'https' if has_ssl else 'http'
                elif isinstance(has_ssl, str):
                    protocol = 'https' if has_ssl == '1' else 'http'
                elif isinstance(has_ssl, int):
                    protocol = 'https' if has_ssl == 1 else 'http'
                else:
                    protocol = 'http'  # 默认HTTP

                rpc_url = f'{protocol}://{downloader.host}:{downloader.port}/transmission/rpc'
                logger.debug(f"构建Transmission RPC URL: {rpc_url}")

                # ✅ 修复：获取username和password用于认证
                username = getattr(downloader, 'username', None)
                password = getattr(downloader, 'password', None)

                adapter = TagAdapterFactory.create_adapter(
                    downloader=downloader,
                    client=None,
                    session=None,
                    rpc_url=rpc_url,
                    username=username,
                    password=password
                )
            else:
                return {
                    "success": False,
                    "data": [],
                    "message": f"不支持的下载器类型: {client_type}",
                    "total_count": 0
                }

            if not adapter:
                return {
                    "success": False,
                    "data": [],
                    "message": f"创建标签适配器失败: {client_type}",
                    "total_count": 0
                }

            # 调用适配器获取标签
            adapter_result = await adapter.get_tags()

            if not adapter_result.get("success"):
                return {
                    "success": False,
                    "data": [],
                    "message": f"获取标签失败: {adapter_result.get('message')}",
                    "total_count": 0
                }

            # 转换格式为数据库统一格式
            raw_tags = adapter_result.get("data", [])
            formatted_tags = self._convert_tags_to_db_format(
                downloader.downloader_id,
                raw_tags
            )

            return {
                "success": True,
                "data": formatted_tags,
                "message": f"成功获取{len(formatted_tags)}个标签",
                "total_count": len(formatted_tags)
            }

        except Exception as e:
            logger.error(f"从下载器获取标签失败: {str(e)}")
            return {
                "success": False,
                "data": [],
                "message": f"获取标签失败: {str(e)}",
                "total_count": 0
            }

    # ==================== 数据保存方法 ====================

    async def save_tags_to_database(
        self,
        downloader_id: str,
        tags: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        将标签数据保存到数据库（直接创建，不合并）

        Args:
            downloader_id: 下载器ID
            tags: 标签数据列表

        Returns:
            保存结果
        """
        try:
            created_count = 0
            failed_count = 0

            for tag_data in tags:
                result = await self.tag_service.create_tag_async(
                    downloader_id=downloader_id,
                    tag_name=tag_data["tag_name"],
                    tag_type=tag_data["tag_type"],
                    color=tag_data.get("color")
                )

                if result.get("success"):
                    created_count += 1
                else:
                    failed_count += 1

            return {
                "success": failed_count == 0,
                "created_count": created_count,
                "failed_count": failed_count,
                "message": f"保存完成: 创建{created_count}，失败{failed_count}"
            }

        except Exception as e:
            logger.error(f"保存标签到数据库失败: {str(e)}")
            return {
                "success": False,
                "created_count": 0,
                "failed_count": len(tags),
                "message": f"保存失败: {str(e)}"
            }

    # ==================== 数据合并方法 ====================

    async def merge_with_existing_tags(
        self,
        downloader_id: str,
        new_tags: List[Dict[str, Any]],
        delete_missing: bool = True
    ) -> Dict[str, Any]:
        """
        合并新标签与现有标签（去重、更新、删除僵尸数据）

        Args:
            downloader_id: 下载器ID
            new_tags: 从下载器获取的新标签列表
            delete_missing: 是否删除下载器中不存在的标签（僵尸数据处理）

        Returns:
            合并结果
            {
                "created_count": int,
                "updated_count": int,
                "unchanged_count": int,
                "deleted_count": int,
                "message": str
            }
        """
        try:
            # 1. 查询现有标签
            existing_result = await self.tag_service.get_tag_list_async(downloader_id)

            if not existing_result.get("success"):
                logger.warning(f"查询现有标签失败，将直接创建新标签: {existing_result.get('message')}")
                # 无法查询现有，直接创建
                return await self._create_all_tags(downloader_id, new_tags)

            existing_tags = existing_result.get("data", [])

            # 2. 构建现有标签映射 (tag_name + tag_type -> tag_info)
            existing_map = {
                (t["tag_name"], t["tag_type"]): t
                for t in existing_tags
            }

            # 3. 对比并分类
            to_create = []
            to_update = []
            new_tag_keys = set()

            for new_tag in new_tags:
                key = (new_tag["tag_name"], new_tag["tag_type"])
                new_tag_keys.add(key)

                if key in existing_map:
                    # 已存在，检查是否需要更新
                    existing_tag = existing_map[key]
                    if self._should_update_tag(existing_tag, new_tag):
                        to_update.append({
                            "tag_id": existing_tag["tag_id"],
                            **new_tag
                        })
                else:
                    # 不存在，需要创建
                    to_create.append(new_tag)

            # 4. 执行创建和更新
            created_count = 0
            updated_count = 0
            unchanged_count = 0

            # 批量创建新标签
            if to_create:
                for tag_data in to_create:
                    result = await self.tag_service.create_tag_async(
                        downloader_id=downloader_id,
                        tag_name=tag_data["tag_name"],
                        tag_type=tag_data["tag_type"],
                        color=tag_data.get("color")
                    )
                    if result.get("success"):
                        created_count += 1
                    else:
                        logger.warning(f"创建标签失败: {tag_data}, {result.get('message')}")

            # 批量更新已有标签
            if to_update:
                for tag_data in to_update:
                    tag_id = tag_data.pop("tag_id")
                    result = await self.tag_service.update_tag_async(tag_id, **tag_data)
                    if result.get("success"):
                        updated_count += 1
                    else:
                        logger.warning(f"更新标签失败: {tag_id}, {result.get('message')}")

            # 计算未变化的数量
            unchanged_count = len(new_tag_keys) - created_count - updated_count

            # 5. 处理僵尸数据（删除下载器中不存在的标签）
            deleted_count = 0
            if delete_missing:
                deleted_count = await self._delete_zombie_tags(
                    downloader_id,
                    new_tag_keys
                )

            return {
                "created_count": created_count,
                "updated_count": updated_count,
                "unchanged_count": unchanged_count,
                "deleted_count": deleted_count,
                "message": f"合并完成: 新增{created_count}，更新{updated_count}，未变{unchanged_count}，删除{deleted_count}"
            }

        except Exception as e:
            logger.error(f"合并标签数据失败: {str(e)}")
            return {
                "created_count": 0,
                "updated_count": 0,
                "unchanged_count": 0,
                "deleted_count": 0,
                "message": f"合并失败: {str(e)}"
            }

    # ==================== 私有辅助方法 ====================

    def _convert_tags_to_db_format(
        self,
        downloader_id: str,
        raw_tags: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        将适配器返回的标签转换为数据库格式

        Args:
            downloader_id: 下载器ID
            raw_tags: 原始标签数据

        Returns:
            数据库格式的标签列表
        """
        formatted = []
        for tag in raw_tags:
            formatted.append({
                'downloader_id': downloader_id,
                'tag_name': tag.get('name'),
                'tag_type': tag.get('type'),  # 'category' | 'tag'
                'color': tag.get('color')
            })
        return formatted

    def _should_update_tag(
        self,
        existing: Dict[str, Any],
        new: Dict[str, Any]
    ) -> bool:
        """
        判断标签是否需要更新

        Args:
            existing: 现有标签数据
            new: 新标签数据

        Returns:
            是否需要更新
        """
        # 检查颜色是否变化
        existing_color = existing.get("color") or ""
        new_color = new.get("color") or ""

        if existing_color != new_color:
            return True

        # 其他字段目前不需要更新
        return False

    async def _create_all_tags(
        self,
        downloader_id: str,
        tags: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        直接创建所有标签（无法查询现有标签时的降级方案）

        Args:
            downloader_id: 下载器ID
            tags: 标签列表

        Returns:
            创建结果
        """
        created_count = 0
        for tag_data in tags:
            result = await self.tag_service.create_tag_async(
                downloader_id=downloader_id,
                tag_name=tag_data["tag_name"],
                tag_type=tag_data["tag_type"],
                color=tag_data.get("color")
            )
            if result.get("success"):
                created_count += 1

        return {
            "created_count": created_count,
            "updated_count": 0,
            "unchanged_count": 0,
            "deleted_count": 0,
            "message": f"创建完成: {created_count}个标签"
        }

    async def _delete_zombie_tags(
        self,
        downloader_id: str,
        new_tag_keys: set
    ) -> int:
        """
        删除僵尸标签（下载器中不存在的标签）

        Args:
            downloader_id: 下载器ID
            new_tag_keys: 新标签键集合 (tag_name, tag_type)

        Returns:
            删除的标签数量
        """
        try:
            # 查询现有标签
            existing_result = await self.tag_service.get_tag_list_async(downloader_id)
            if not existing_result.get("success"):
                return 0

            existing_tags = existing_result.get("data", [])

            deleted_count = 0

            # 找出需要删除的标签（在新标签键中不存在的）
            for existing_tag in existing_tags:
                key = (existing_tag["tag_name"], existing_tag["tag_type"])
                if key not in new_tag_keys:
                    # 这是僵尸标签，需要删除
                    result = await self.tag_service.delete_tag_async(existing_tag["tag_id"])
                    if result.get("success"):
                        deleted_count += 1
                        logger.debug(
                            f"删除僵尸标签: {existing_tag['tag_name']} "
                            f"({existing_tag['tag_type']})"
                        )
                    else:
                        logger.warning(
                            f"删除僵尸标签失败: {existing_tag['tag_name']}, "
                            f"{result.get('message')}"
                        )

            if deleted_count > 0:
                logger.info(f"下载器 {downloader_id} 清理了 {deleted_count} 个僵尸标签")

            return deleted_count

        except Exception as e:
            logger.error(f"删除僵尸标签失败: {str(e)}")
            return 0

    # ==================== 同步方法版本 ====================
    # 用于非定时任务场景，通过 _execute_sync 在同步上下文中执行异步逻辑

    def _execute_sync(self, coro):
        """
        在同步上下文中执行异步方法
        用于同步Service中需要调用异步Repository方法的场景。
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    def sync_downloader_tags_sync(
        self,
        downloader: Any,  # ✅ 类型：DownloaderVO（缓存对象）
        delete_missing: bool = True
    ) -> Dict[str, Any]:
        """
        同步指定下载器的标签数据（同步版本）

        Args:
            downloader: 下载器缓存对象（DownloaderVO）
            delete_missing: 是否删除下载器中不存在的标签（僵尸数据处理）

        Returns:
            同步结果字典
        """
        return self._execute_sync(
            self.sync_downloader_tags(
                downloader=downloader,
                delete_missing=delete_missing
            )
        )

    def sync_all_downloaders_sync(
        self,
        delete_missing: bool = True
    ) -> Dict[str, Any]:
        """
        同步所有下载器的标签数据（同步版本）

        Args:
            delete_missing: 是否删除下载器中不存在的标签

        Returns:
            全量同步结果字典
        """
        return self._execute_sync(
            self.sync_all_downloaders(
                delete_missing=delete_missing
            )
        )
