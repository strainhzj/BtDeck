"""
标签管理服务

提供标签管理的业务逻辑层，支持同步和异步两种调用方式。
"""

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional, Union
import logging

from app.repositories.torrent_tag_repository import TorrentTagRepository
from app.repositories.async_torrent_tag_repository import AsyncTorrentTagRepository
from app.models.torrent_tags import TorrentTag, TorrentTagRelation
from app.core.database_result import DatabaseResult

logger = logging.getLogger(__name__)


class TagService:
    """
    标签管理服务类

    提供标签CRUD和种子-标签关联管理的业务逻辑。
    支持同步Session和异步AsyncSession两种初始化方式。
    """

    VALID_TAG_TYPES = {'category', 'tag'}

    def __init__(self, db: Union[Session, AsyncSession]):
        """
        初始化服务

        Args:
            db: SQLAlchemy会话（同步Session或异步AsyncSession）
        """
        self.db = db
        self.is_async = isinstance(db, AsyncSession)

        # 根据会话类型创建对应的Repository
        if self.is_async:
            self.repository = AsyncTorrentTagRepository(db)
        else:
            self.repository = TorrentTagRepository(db)

    # ==================== 私有方法 ====================

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

    def _to_dict(self, tag: TorrentTag) -> Dict[str, Any]:
        """将标签模型转换为字典"""
        if tag is None:
            return None
        return {
            "tag_id": tag.tag_id,
            "downloader_id": tag.downloader_id,
            "tag_name": tag.tag_name,
            "tag_type": tag.tag_type,
            "color": tag.color,
            "created_at": tag.created_at.isoformat() if tag.created_at else None,
            "updated_at": tag.updated_at.isoformat() if tag.updated_at else None
        }

    def _to_relation_dict(self, relation: TorrentTagRelation) -> Dict[str, Any]:
        """将标签关联模型转换为字典"""
        if relation is None:
            return None
        return {
            "relation_id": relation.relation_id,
            "downloader_id": relation.downloader_id,
            "torrent_hash": relation.torrent_hash,
            "tag_id": relation.tag_id,
            "assigned_at": relation.assigned_at.isoformat() if relation.assigned_at else None
        }

    def _to_response(
        self,
        db_result: DatabaseResult,
        success_msg: str = "操作成功",
        error_prefix: str = "操作失败"
    ) -> Dict[str, Any]:
        """
        将DatabaseResult转换为统一的响应格式

        Args:
            db_result: DatabaseResult对象
            success_msg: 成功时的消息
            error_prefix: 失败时的消息前缀

        Returns:
            统一格式的响应字典
        """
        if db_result.success:
            return {
                "success": True,
                "data": self._to_dict(db_result.data) if hasattr(db_result.data, 'tag_id') or hasattr(db_result.data, '__dict__') else db_result.data,
                "message": db_result.message or success_msg,
                "affected_rows": db_result.affected_rows
            }
        else:
            return {
                "success": False,
                "data": None,
                "message": db_result.message or f"{error_prefix}: {db_result.error_code}",
                "error_code": db_result.error_code
            }

    # ==================== 标签管理方法（同步版本）====================

    def get_tag_list(
        self,
        downloader_id: str,
        tag_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取标签列表（同步）

        Args:
            downloader_id: 下载器ID
            tag_type: 可选，筛选标签类型

        Returns:
            统一格式的响应字典
        """
        try:
            # 验证tag_type
            if tag_type and tag_type not in self.VALID_TAG_TYPES:
                return {
                    "success": False,
                    "data": None,
                    "message": f"无效的标签类型: {tag_type}，仅支持 {self.VALID_TAG_TYPES}"
                }

            tags = self.repository.find_by_downloader(
                downloader_id=downloader_id,
                include_deleted=False,
                tag_type=tag_type
            )

            tag_list = [self._to_dict(tag) for tag in tags]

            return {
                "success": True,
                "data": tag_list,
                "message": "获取标签列表成功",
                "total_count": len(tag_list)
            }
        except Exception as e:
            logger.error(f"获取标签列表失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"获取标签列表失败: {str(e)}"
            }

    def create_tag(
        self,
        downloader_id: str,
        tag_name: str,
        tag_type: str,
        color: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建标签（同步）

        Args:
            downloader_id: 下载器ID
            tag_name: 标签名称
            tag_type: 标签类型（category/tag）
            color: 可选，颜色代码

        Returns:
            统一格式的响应字典
        """
        try:
            # 验证输入
            if not tag_name or not tag_name.strip():
                return {
                    "success": False,
                    "data": None,
                    "message": "标签名称不能为空"
                }

            if tag_type not in self.VALID_TAG_TYPES:
                return {
                    "success": False,
                    "data": None,
                    "message": f"无效的标签类型: {tag_type}，仅支持 {self.VALID_TAG_TYPES}"
                }

            # 验证颜色格式（如果提供）
            if color and not color.startswith('#'):
                return {
                    "success": False,
                    "data": None,
                    "message": "颜色代码必须以#开头，如#FF5733"
                }

            # 创建标签对象
            tag = TorrentTag(
                downloader_id=downloader_id,
                tag_name=tag_name.strip(),
                tag_type=tag_type,
                color=color
            )

            db_result = self.repository.create(tag)

            return self._to_response(
                db_result,
                success_msg="标签创建成功",
                error_prefix="标签创建失败"
            )
        except Exception as e:
            logger.error(f"创建标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"创建标签失败: {str(e)}"
            }

    def update_tag(
        self, tag_id: str, **kwargs
    ) -> Dict[str, Any]:
        """
        更新标签（同步）

        Args:
            tag_id: 标签ID
            **kwargs: 要更新的字段（tag_name, tag_type, color）

        Returns:
            统一格式的响应字典
        """
        try:
            # 查询现有标签
            existing = self.repository.find_by_id(tag_id)
            if not existing:
                return {
                    "success": False,
                    "data": None,
                    "message": "标签不存在"
                }

            # 验证tag_type（如果提供）
            if 'tag_type' in kwargs and kwargs['tag_type'] not in self.VALID_TAG_TYPES:
                return {
                    "success": False,
                    "data": None,
                    "message": f"无效的标签类型: {kwargs['tag_type']}，仅支持 {self.VALID_TAG_TYPES}"
                }

            # 更新字段
            tag = TorrentTag(tag_id=tag_id)
            for key, value in kwargs.items():
                if hasattr(tag, key):
                    setattr(tag, key, value)

            db_result = self.repository.update(tag)

            return self._to_response(
                db_result,
                success_msg="标签更新成功",
                error_prefix="标签更新失败"
            )
        except Exception as e:
            logger.error(f"更新标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"更新标签失败: {str(e)}"
            }

    def delete_tag(self, tag_id: str) -> Dict[str, Any]:
        """
        删除标签（同步）

        Args:
            tag_id: 标签ID

        Returns:
            统一格式的响应字典
        """
        try:
            db_result = self.repository.soft_delete(tag_id)

            return {
                "success": db_result.success,
                "data": db_result.data if db_result.success else None,
                "message": db_result.message,
                "error_code": db_result.error_code if not db_result.success else None
            }
        except Exception as e:
            logger.error(f"删除标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"删除标签失败: {str(e)}"
            }

    def get_torrent_tags(self, torrent_hash: str) -> Dict[str, Any]:
        """
        获取种子的所有标签（同步）

        Args:
            torrent_hash: 种子哈希值

        Returns:
            统一格式的响应字典
        """
        try:
            relations = self.repository.find_relations_by_torrent_hash(torrent_hash)

            # 查询标签详情
            tags = []
            for relation in relations:
                tag = self.repository.find_by_id(relation.tag_id)
                if tag:
                    tags.append(self._to_dict(tag))

            return {
                "success": True,
                "data": tags,
                "message": "获取种子标签成功",
                "total_count": len(tags)
            }
        except Exception as e:
            logger.error(f"获取种子标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"获取种子标签失败: {str(e)}"
            }

    def assign_tags_to_torrent(
        self, torrent_hash: str, tag_ids: List[str]
    ) -> Dict[str, Any]:
        """
        为种子分配标签（同步）

        Args:
            torrent_hash: 种子哈希值
            tag_ids: 标签ID列表

        Returns:
            统一格式的响应字典
        """
        try:
            # 验证标签存在性
            valid_tags = []
            not_found_tags = []

            for tag_id in tag_ids:
                tag = self.repository.find_by_id(tag_id)
                if tag:
                    valid_tags.append(tag)  # 存储完整的TorrentTag对象
                else:
                    not_found_tags.append(tag_id)

            if not_found_tags:
                return {
                    "success": False,
                    "data": None,
                    "message": f"以下标签不存在: {', '.join(not_found_tags)}"
                }

            # 创建关联
            relations = []
            for tag in valid_tags:
                relation = TorrentTagRelation(
                    torrent_hash=torrent_hash,
                    tag_id=tag.tag_id,  # 使用tag对象的tag_id属性
                    downloader_id=valid_tags[0].downloader_id if valid_tags else ""
                )
                relations.append(relation)

            result = self.repository.batch_assign_tags(relations)

            return {
                "success": result.success,
                "data": result.data if result.success else None,
                "message": result.message,
                "total_count": result.data.get("total_count", 0) if result.success else 0,
                "success_count": result.data.get("success_count", 0) if result.success else 0,
                "failed_count": result.data.get("failed_count", 0) if result.success else 0
            }
        except Exception as e:
            logger.error(f"分配标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"分配标签失败: {str(e)}"
            }

    def remove_tags_from_torrent(
        self, torrent_hash: str, tag_ids: List[str]
    ) -> Dict[str, Any]:
        """
        移除种子的标签（同步）

        Args:
            torrent_hash: 种子哈希值
            tag_ids: 标签ID列表

        Returns:
            统一格式的响应字典
        """
        try:
            removed_count = 0
            failed_count = 0
            failed_tags = []

            for tag_id in tag_ids:
                result = self.repository.remove_tag_from_torrent(torrent_hash, tag_id)
                if result.success:
                    removed_count += 1
                else:
                    failed_count += 1
                    failed_tags.append({
                        "tag_id": tag_id,
                        "error": result.message
                    })

            return {
                "success": failed_count == 0,
                "data": {
                    "removed_count": removed_count,
                    "failed_count": failed_count,
                    "failed_tags": failed_tags
                },
                "message": f"移除标签完成: 成功{removed_count}，失败{failed_count}"
            }
        except Exception as e:
            logger.error(f"移除标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"移除标签失败: {str(e)}"
            }

    def batch_assign_tags(
        self, assignments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量分配标签（同步）

        Args:
            assignments: 分配任务列表
                [
                    {"torrent_hash": "...", "tag_ids": ["...", "..."]},
                    ...
                ]

        Returns:
            统一格式的响应字典
        """
        try:
            all_relations = []

            for assignment in assignments:
                torrent_hash = assignment.get("torrent_hash")
                tag_ids = assignment.get("tag_ids", [])

                if not torrent_hash or not tag_ids:
                    continue

                # 获取第一个标签来获取downloader_id
                first_tag = self.repository.find_by_id(tag_ids[0])
                if not first_tag:
                    continue

                for tag_id in tag_ids:
                    relation = TorrentTagRelation(
                        torrent_hash=torrent_hash,
                        tag_id=tag_id,
                        downloader_id=first_tag.downloader_id
                    )
                    all_relations.append(relation)

            result = self.repository.batch_assign_tags(all_relations)

            return {
                "success": result.success,
                "data": result.data if result.success else None,
                "message": result.message,
                "total_assignments": len(assignments)
            }
        except Exception as e:
            logger.error(f"批量分配标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"批量分配失败: {str(e)}"
            }

    # ==================== 标签管理方法（异步版本）====================

    async def get_tag_list_async(
        self,
        downloader_id: str,
        tag_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取标签列表（异步）

        Args:
            downloader_id: 下载器ID
            tag_type: 可选，筛选标签类型

        Returns:
            统一格式的响应字典
        """
        try:
            # 验证tag_type
            if tag_type and tag_type not in self.VALID_TAG_TYPES:
                return {
                    "success": False,
                    "data": None,
                    "message": f"无效的标签类型: {tag_type}，仅支持 {self.VALID_TAG_TYPES}"
                }

            tags = await self.repository.find_by_downloader(
                downloader_id=downloader_id,
                include_deleted=False,
                tag_type=tag_type
            )

            tag_list = [self._to_dict(tag) for tag in tags]

            return {
                "success": True,
                "data": tag_list,
                "message": "获取标签列表成功",
                "total_count": len(tag_list)
            }
        except Exception as e:
            logger.error(f"异步获取标签列表失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"获取标签列表失败: {str(e)}"
            }

    async def create_tag_async(
        self,
        downloader_id: str,
        tag_name: str,
        tag_type: str,
        color: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建标签（异步）

        Args:
            downloader_id: 下载器ID
            tag_name: 标签名称
            tag_type: 标签类型（category/tag）
            color: 可选，颜色代码

        Returns:
            统一格式的响应字典
        """
        try:
            # 验证输入
            if not tag_name or not tag_name.strip():
                return {
                    "success": False,
                    "data": None,
                    "message": "标签名称不能为空"
                }

            if tag_type not in self.VALID_TAG_TYPES:
                return {
                    "success": False,
                    "data": None,
                    "message": f"无效的标签类型: {tag_type}，仅支持 {self.VALID_TAG_TYPES}"
                }

            # 验证颜色格式（如果提供）
            if color and not color.startswith('#'):
                return {
                    "success": False,
                    "data": None,
                    "message": "颜色代码必须以#开头，如#FF5733"
                }

            # 创建标签对象
            tag = TorrentTag(
                downloader_id=downloader_id,
                tag_name=tag_name.strip(),
                tag_type=tag_type,
                color=color
            )

            db_result = await self.repository.create(tag)

            return self._to_response(
                db_result,
                success_msg="标签创建成功",
                error_prefix="标签创建失败"
            )
        except Exception as e:
            logger.error(f"异步创建标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"创建标签失败: {str(e)}"
            }

    async def update_tag_async(
        self, tag_id: str, **kwargs
    ) -> Dict[str, Any]:
        """
        更新标签（异步）

        Args:
            tag_id: 标签ID
            **kwargs: 要更新的字段（tag_name, tag_type, color）

        Returns:
            统一格式的响应字典
        """
        try:
            # 查询现有标签
            existing = await self.repository.find_by_id(tag_id)
            if not existing:
                return {
                    "success": False,
                    "data": None,
                    "message": "标签不存在"
                }

            # 验证tag_type（如果提供）
            if 'tag_type' in kwargs and kwargs['tag_type'] not in self.VALID_TAG_TYPES:
                return {
                    "success": False,
                    "data": None,
                    "message": f"无效的标签类型: {kwargs['tag_type']}，仅支持 {self.VALID_TAG_TYPES}"
                }

            # 更新字段
            tag = TorrentTag(tag_id=tag_id)
            for key, value in kwargs.items():
                if hasattr(tag, key):
                    setattr(tag, key, value)

            db_result = await self.repository.update(tag)

            return self._to_response(
                db_result,
                success_msg="标签更新成功",
                error_prefix="标签更新失败"
            )
        except Exception as e:
            logger.error(f"异步更新标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"更新标签失败: {str(e)}"
            }

    async def delete_tag_async(self, tag_id: str) -> Dict[str, Any]:
        """
        删除标签（异步）

        Args:
            tag_id: 标签ID

        Returns:
            统一格式的响应字典
        """
        try:
            db_result = await self.repository.soft_delete(tag_id)

            return {
                "success": db_result.success,
                "data": db_result.data if db_result.success else None,
                "message": db_result.message,
                "error_code": db_result.error_code if not db_result.success else None
            }
        except Exception as e:
            logger.error(f"异步删除标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"删除标签失败: {str(e)}"
            }

    async def get_torrent_tags_async(
        self, torrent_hash: str
    ) -> Dict[str, Any]:
        """
        获取种子的所有标签（异步）

        Args:
            torrent_hash: 种子哈希值

        Returns:
            统一格式的响应字典
        """
        try:
            relations = await self.repository.find_relations_by_torrent_hash(torrent_hash)

            # 查询标签详情
            tags = []
            for relation in relations:
                tag = await self.repository.find_by_id(relation.tag_id)
                if tag:
                    tags.append(self._to_dict(tag))

            return {
                "success": True,
                "data": tags,
                "message": "获取种子标签成功",
                "total_count": len(tags)
            }
        except Exception as e:
            logger.error(f"异步获取种子标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"获取种子标签失败: {str(e)}"
            }

    async def assign_tags_to_torrent_async(
        self, torrent_hash: str, tag_ids: List[str]
    ) -> Dict[str, Any]:
        """
        为种子分配标签（异步）

        Args:
            torrent_hash: 种子哈希值
            tag_ids: 标签ID列表

        Returns:
            统一格式的响应字典
        """
        try:
            # 验证标签存在性
            valid_tags = []
            not_found_tags = []

            for tag_id in tag_ids:
                tag = await self.repository.find_by_id(tag_id)
                if tag:
                    valid_tags.append(tag)  # 存储完整的TorrentTag对象
                else:
                    not_found_tags.append(tag_id)

            if not_found_tags:
                return {
                    "success": False,
                    "data": None,
                    "message": f"以下标签不存在: {', '.join(not_found_tags)}"
                }

            # 创建关联
            relations = []
            for tag in valid_tags:
                relation = TorrentTagRelation(
                    torrent_hash=torrent_hash,
                    tag_id=tag.tag_id,  # 使用tag对象的tag_id属性
                    downloader_id=valid_tags[0].downloader_id if valid_tags else ""
                )
                relations.append(relation)

            result = await self.repository.batch_assign_tags(relations)

            return {
                "success": result.success,
                "data": result.data if result.success else None,
                "message": result.message,
                "total_count": result.data.get("total_count", 0) if result.success else 0,
                "success_count": result.data.get("success_count", 0) if result.success else 0,
                "failed_count": result.data.get("failed_count", 0) if result.success else 0
            }
        except Exception as e:
            logger.error(f"异步分配标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"分配标签失败: {str(e)}"
            }

    async def remove_tags_from_torrent_async(
        self, torrent_hash: str, tag_ids: List[str]
    ) -> Dict[str, Any]:
        """
        移除种子的标签（异步）

        Args:
            torrent_hash: 种子哈希值
            tag_ids: 标签ID列表

        Returns:
            统一格式的响应字典
        """
        try:
            removed_count = 0
            failed_count = 0
            failed_tags = []

            for tag_id in tag_ids:
                result = await self.repository.remove_tag_from_torrent(torrent_hash, tag_id)
                if result.success:
                    removed_count += 1
                else:
                    failed_count += 1
                    failed_tags.append({
                        "tag_id": tag_id,
                        "error": result.message
                    })

            return {
                "success": failed_count == 0,
                "data": {
                    "removed_count": removed_count,
                    "failed_count": failed_count,
                    "failed_tags": failed_tags
                },
                "message": f"移除标签完成: 成功{removed_count}，失败{failed_count}"
            }
        except Exception as e:
            logger.error(f"异步移除标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"移除标签失败: {str(e)}"
            }

    async def batch_assign_tags_async(
        self, assignments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量分配标签（异步）

        Args:
            assignments: 分配任务列表
                [
                    {"torrent_hash": "...", "tag_ids": ["...", "..."]},
                    ...
                ]

        Returns:
            统一格式的响应字典
        """
        try:
            all_relations = []

            for assignment in assignments:
                torrent_hash = assignment.get("torrent_hash")
                tag_ids = assignment.get("tag_ids", [])

                if not torrent_hash or not tag_ids:
                    continue

                # 获取第一个标签来获取downloader_id
                first_tag = await self.repository.find_by_id(tag_ids[0])
                if not first_tag:
                    continue

                for tag_id in tag_ids:
                    relation = TorrentTagRelation(
                        torrent_hash=torrent_hash,
                        tag_id=tag_id,
                        downloader_id=first_tag.downloader_id
                    )
                    all_relations.append(relation)

            result = await self.repository.batch_assign_tags(all_relations)

            return {
                "success": result.success,
                "data": result.data if result.success else None,
                "message": result.message,
                "total_assignments": len(assignments)
            }
        except Exception as e:
            logger.error(f"异步批量分配标签失败: {str(e)}")
            return {
                "success": False,
                "data": None,
                "message": f"批量分配失败: {str(e)}"
            }
