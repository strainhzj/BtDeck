"""
种子标签仓储 - 异步版本

提供异步数据库操作接口，用于异步Service层调用（如定时任务）。
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, delete
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import logging

from app.models.torrent_tags import TorrentTag, TorrentTagRelation
from app.core.database_result import DatabaseResult, DatabaseError

logger = logging.getLogger(__name__)


class AsyncTorrentTagRepository:
    """
    种子标签仓储类 - 异步版本

    封装所有标签相关的数据库异步操作，包括标签CRUD和种子-标签关联管理。
    专为定时任务和异步场景设计。
    """

    VALID_TAG_TYPES = {'category', 'tag'}

    def __init__(self, db: AsyncSession):
        """
        初始化仓储

        Args:
            db: SQLAlchemy异步会话
        """
        self.db = db

    # ==================== 基础查询方法 ====================

    async def find_by_id(self, tag_id: str) -> Optional[TorrentTag]:
        """
        根据ID查找标签

        Args:
            tag_id: 标签ID

        Returns:
            标签对象，未找到返回None
        """
        try:
            result = await self.db.execute(
                select(TorrentTag).filter(
                    and_(
                        TorrentTag.tag_id == tag_id,
                        TorrentTag.dr == 0
                    )
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"异步查找标签失败: {str(e)}")
            return None

    async def find_by_downloader(
        self,
        downloader_id: str,
        include_deleted: bool = False,
        tag_type: Optional[str] = None
    ) -> List[TorrentTag]:
        """
        根据下载器ID查找所有标签

        Args:
            downloader_id: 下载器ID
            include_deleted: 是否包含已删除的标签
            tag_type: 可选，筛选标签类型（category/tag）

        Returns:
            标签列表
        """
        try:
            query = select(TorrentTag).filter(
                TorrentTag.downloader_id == downloader_id
            )

            # 过滤已删除
            if not include_deleted:
                query = query.filter(TorrentTag.dr == 0)

            # 按类型筛选
            if tag_type:
                query = query.filter(TorrentTag.tag_type == tag_type)

            query = query.order_by(TorrentTag.created_at.desc())

            result = await self.db.execute(query)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"异步查询下载器标签失败: {str(e)}")
            return []

    async def find_relations_by_torrent_hash(
        self, torrent_hash: str
    ) -> List[TorrentTagRelation]:
        """
        查找种子的所有标签关联

        Args:
            torrent_hash: 种子哈希值

        Returns:
            标签关联列表
        """
        try:
            result = await self.db.execute(
                select(TorrentTagRelation).filter(
                    and_(
                        TorrentTagRelation.torrent_hash == torrent_hash,
                        TorrentTagRelation.dr == 0
                    )
                )
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"异步查询种子标签关联失败: {str(e)}")
            return []

    # ==================== 标签CRUD方法 ====================

    async def create(self, tag: TorrentTag) -> DatabaseResult[TorrentTag]:
        """
        创建新标签

        Args:
            tag: 标签模型对象

        Returns:
            创建结果
        """
        try:
            # 验证tag_type
            if tag.tag_type not in self.VALID_TAG_TYPES:
                return DatabaseResult.validation_error_result(
                    f"无效的标签类型: {tag.tag_type}，仅支持 {self.VALID_TAG_TYPES}"
                )

            # 生成ID（如果未提供）
            if not tag.tag_id:
                tag.tag_id = str(uuid4())

            tag.created_at = datetime.utcnow()
            tag.updated_at = datetime.utcnow()

            self.db.add(tag)
            await self.db.commit()
            await self.db.refresh(tag)

            return DatabaseResult.success_result(
                data=tag,
                message="标签创建成功",
                affected_rows=1
            )
        except Exception as e:
            await self.db.rollback()
            logger.error(f"异步创建标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"创建标签失败: {str(e)}")

    async def update(self, tag: TorrentTag) -> DatabaseResult[TorrentTag]:
        """
        更新标签

        Args:
            tag: 包含更新数据的标签对象

        Returns:
            更新结果
        """
        try:
            # 验证tag_type（如果提供）
            if tag.tag_type and tag.tag_type not in self.VALID_TAG_TYPES:
                return DatabaseResult.validation_error_result(
                    f"无效的标签类型: {tag.tag_type}，仅支持 {self.VALID_TAG_TYPES}"
                )

            # 查询现有标签
            result = await self.db.execute(
                select(TorrentTag).filter(
                    and_(
                        TorrentTag.tag_id == tag.tag_id,
                        TorrentTag.dr == 0
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                return DatabaseResult.not_found_result("标签不存在")

            # 更新字段
            update_data = {"updated_at": datetime.utcnow()}
            if tag.tag_name is not None:
                update_data["tag_name"] = tag.tag_name
            if tag.tag_type is not None:
                update_data["tag_type"] = tag.tag_type
            if tag.color is not None:
                update_data["color"] = tag.color

            await self.db.execute(
                update(TorrentTag)
                .where(and_(
                    TorrentTag.tag_id == tag.tag_id,
                    TorrentTag.dr == 0
                ))
                .values(**update_data)
            )
            await self.db.commit()

            # 重新查询获取更新后的对象
            updated_result = await self.db.execute(
                select(TorrentTag).filter(TorrentTag.tag_id == tag.tag_id)
            )
            updated_tag = updated_result.scalar_one()

            return DatabaseResult.success_result(
                data=updated_tag,
                message="标签更新成功",
                affected_rows=1
            )
        except Exception as e:
            await self.db.rollback()
            logger.error(f"异步更新标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"更新标签失败: {str(e)}")

    async def soft_delete(self, tag_id: str) -> DatabaseResult[bool]:
        """
        软删除标签

        Args:
            tag_id: 标签ID

        Returns:
            删除结果
        """
        try:
            # 查询标签
            result = await self.db.execute(
                select(TorrentTag).filter(
                    and_(
                        TorrentTag.tag_id == tag_id,
                        TorrentTag.dr == 0
                    )
                )
            )
            tag = result.scalar_one_or_none()

            if not tag:
                return DatabaseResult.not_found_result("标签不存在")

            # 软删除标签
            await self.db.execute(
                update(TorrentTag)
                .where(TorrentTag.tag_id == tag_id)
                .values(dr=1, updated_at=datetime.utcnow())
            )

            # 同时软删除相关联
            await self.db.execute(
                update(TorrentTagRelation)
                .where(TorrentTagRelation.tag_id == tag_id)
                .values(dr=1)
            )

            await self.db.commit()

            return DatabaseResult.success_result(
                data=True,
                message="标签删除成功",
                affected_rows=1
            )
        except Exception as e:
            await self.db.rollback()
            logger.error(f"异步删除标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"删除标签失败: {str(e)}")

    # ==================== 标签-种子关联方法 ====================

    async def assign_tag_to_torrent(
        self, relation: TorrentTagRelation
    ) -> DatabaseResult[bool]:
        """
        为种子分配标签

        Args:
            relation: 标签关联对象

        Returns:
            分配结果
        """
        try:
            # 生成ID（如果未提供）
            if not relation.relation_id:
                relation.relation_id = str(uuid4())

            relation.assigned_at = datetime.utcnow()

            self.db.add(relation)
            await self.db.commit()

            return DatabaseResult.success_result(
                data=True,
                message="标签分配成功",
                affected_rows=1
            )
        except Exception as e:
            await self.db.rollback()
            logger.error(f"异步分配标签失败: {str(e)}")
            # 可能是UNIQUE约束冲突
            if "UNIQUE" in str(e) or "unique" in str(e).lower():
                return DatabaseResult.validation_error_result(
                    "该标签已分配到此种子"
                )
            return DatabaseResult.database_error_result(f"分配标签失败: {str(e)}")

    async def remove_tag_from_torrent(
        self, torrent_hash: str, tag_id: str
    ) -> DatabaseResult[bool]:
        """
        移除种子的标签

        Args:
            torrent_hash: 种子哈希值
            tag_id: 标签ID

        Returns:
            移除结果
        """
        try:
            # 查询关联
            result = await self.db.execute(
                select(TorrentTagRelation).filter(
                    and_(
                        TorrentTagRelation.torrent_hash == torrent_hash,
                        TorrentTagRelation.tag_id == tag_id,
                        TorrentTagRelation.dr == 0
                    )
                )
            )
            relation = result.scalar_one_or_none()

            if not relation:
                return DatabaseResult.not_found_result("标签关联不存在")

            # 软删除关联
            await self.db.execute(
                update(TorrentTagRelation)
                .where(
                    and_(
                        TorrentTagRelation.torrent_hash == torrent_hash,
                        TorrentTagRelation.tag_id == tag_id
                    )
                )
                .values(dr=1)
            )

            await self.db.commit()

            return DatabaseResult.success_result(
                data=True,
                message="标签移除成功",
                affected_rows=1
            )
        except Exception as e:
            await self.db.rollback()
            logger.error(f"异步移除标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"移除标签失败: {str(e)}")

    async def batch_assign_tags(
        self, relations: List[TorrentTagRelation]
    ) -> DatabaseResult[Dict[str, Any]]:
        """
        批量分配标签

        Args:
            relations: 标签关联列表

        Returns:
            批量操作结果
        """
        success_count = 0
        failed_count = 0
        failed_items = []

        for idx, relation in enumerate(relations):
            try:
                # 生成ID（如果未提供）
                if not relation.relation_id:
                    relation.relation_id = str(uuid4())

                relation.assigned_at = datetime.utcnow()

                self.db.add(relation)
                await self.db.commit()

                success_count += 1
            except Exception as e:
                failed_count += 1
                failed_items.append({
                    "index": idx,
                    "torrent_hash": relation.torrent_hash,
                    "tag_id": relation.tag_id,
                    "error": str(e)
                })
                await self.db.rollback()

        result_data = {
            "total_count": len(relations),
            "success_count": success_count,
            "failed_count": failed_count,
            "failed_items": failed_items
        }

        return DatabaseResult.success_result(
            data=result_data,
            message=f"批量分配完成: 成功{success_count}，失败{failed_count}",
            affected_rows=success_count
        )
