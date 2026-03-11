"""
种子标签仓储 - 同步版本

提供同步数据库操作接口，用于同步Service层调用。
"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import logging

from app.models.torrent_tags import TorrentTag, TorrentTagRelation
from app.core.database_result import DatabaseResult, DatabaseError

logger = logging.getLogger(__name__)


class TorrentTagRepository:
    """
    种子标签仓储类 - 同步版本

    封装所有标签相关的数据库同步操作，包括标签CRUD和种子-标签关联管理。
    """

    VALID_TAG_TYPES = {'category', 'tag'}

    def __init__(self, db: Session):
        """
        初始化仓储

        Args:
            db: SQLAlchemy同步会话
        """
        self.db = db

    # ==================== 基础查询方法 ====================

    def find_by_id(self, tag_id: str) -> Optional[TorrentTag]:
        """
        根据ID查找标签

        Args:
            tag_id: 标签ID

        Returns:
            标签对象，未找到返回None
        """
        try:
            return self.db.query(TorrentTag).filter(
                and_(
                    TorrentTag.tag_id == tag_id,
                    TorrentTag.dr == 0
                )
            ).first()
        except Exception as e:
            logger.error(f"查找标签失败: {str(e)}")
            return None

    def find_by_downloader(
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
            # 🐛 调试日志：记录查询条件
            logger.info(f"🔍 [调试-Repository] 查询标签 - downloader_id: {downloader_id}, include_deleted: {include_deleted}, tag_type: {tag_type}")

            query = self.db.query(TorrentTag).filter(
                TorrentTag.downloader_id == downloader_id
            )

            # 过滤已删除
            if not include_deleted:
                query = query.filter(TorrentTag.dr == 0)

            # 按类型筛选
            if tag_type:
                query = query.filter(TorrentTag.tag_type == tag_type)

            result_list = query.order_by(TorrentTag.created_at.desc()).all()

            # 🐛 调试日志：记录查询结果数量
            logger.info(f"🔍 [调试-Repository] 查询到 {len(result_list)} 条标签记录")

            return result_list
        except Exception as e:
            logger.error(f"查询下载器标签失败: {str(e)}")
            return []

    def find_relations_by_torrent_hash(
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
            return self.db.query(TorrentTagRelation).filter(
                and_(
                    TorrentTagRelation.torrent_hash == torrent_hash,
                    TorrentTagRelation.dr == 0
                )
            ).all()
        except Exception as e:
            logger.error(f"查询种子标签关联失败: {str(e)}")
            return []

    # ==================== 标签CRUD方法 ====================

    def create(self, tag: TorrentTag) -> DatabaseResult[TorrentTag]:
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
                tag.tag_id = str(uuid.uuid4())

            tag.created_at = datetime.utcnow()
            tag.updated_at = datetime.utcnow()

            self.db.add(tag)
            self.db.commit()
            self.db.refresh(tag)

            return DatabaseResult.success_result(
                data=tag,
                message="标签创建成功",
                affected_rows=1
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"创建标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"创建标签失败: {str(e)}")

    def update(self, tag: TorrentTag) -> DatabaseResult[TorrentTag]:
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

            existing = self.db.query(TorrentTag).filter(
                and_(
                    TorrentTag.tag_id == tag.tag_id,
                    TorrentTag.dr == 0
                )
            ).first()

            if not existing:
                return DatabaseResult.not_found_result("标签不存在")

            # 更新字段
            if tag.tag_name is not None:
                existing.tag_name = tag.tag_name
            if tag.tag_type is not None:
                existing.tag_type = tag.tag_type
            if tag.color is not None:
                existing.color = tag.color

            existing.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(existing)

            return DatabaseResult.success_result(
                data=existing,
                message="标签更新成功",
                affected_rows=1
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"更新标签失败: {str(e)}")

    def soft_delete(self, tag_id: str) -> DatabaseResult[Dict[str, Any]]:
        """
        软删除标签

        Args:
            tag_id: 标签ID

        Returns:
            删除结果（包含被删除标签的详细信息，用于同步到下载器）
        """
        try:
            tag = self.db.query(TorrentTag).filter(
                and_(
                    TorrentTag.tag_id == tag_id,
                    TorrentTag.dr == 0
                )
            ).first()

            if not tag:
                return DatabaseResult.not_found_result("标签不存在")

            # ⚠️ 修复：保存标签信息，用于同步到下载器
            tag_info = {
                "tag_id": tag.tag_id,
                "downloader_id": tag.downloader_id,
                "tag_name": tag.tag_name,
                "tag_type": tag.tag_type,
                "color": tag.color
            }

            tag.dr = 1
            tag.updated_at = datetime.utcnow()

            # 同时软删除关联
            self.db.query(TorrentTagRelation).filter(
                TorrentTagRelation.tag_id == tag_id
            ).update({"dr": 1})

            self.db.commit()

            return DatabaseResult.success_result(
                data=tag_info,  # ⚠️ 修复：返回标签详情而不是True
                message="标签删除成功",
                affected_rows=1
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"删除标签失败: {str(e)}")

    # ==================== 标签-种子关联方法 ====================

    def assign_tag_to_torrent(
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
                relation.relation_id = str(uuid.uuid4())

            relation.assigned_at = datetime.utcnow()

            self.db.add(relation)
            self.db.commit()

            return DatabaseResult.success_result(
                data=True,
                message="标签分配成功",
                affected_rows=1
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"分配标签失败: {str(e)}")
            # 可能是UNIQUE约束冲突
            if "UNIQUE" in str(e) or "unique" in str(e).lower():
                return DatabaseResult.validation_error_result(
                    "该标签已分配到此种子"
                )
            return DatabaseResult.database_error_result(f"分配标签失败: {str(e)}")

    def remove_tag_from_torrent(
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
            relation = self.db.query(TorrentTagRelation).filter(
                and_(
                    TorrentTagRelation.torrent_hash == torrent_hash,
                    TorrentTagRelation.tag_id == tag_id,
                    TorrentTagRelation.dr == 0
                )
            ).first()

            if not relation:
                return DatabaseResult.not_found_result("标签关联不存在")

            relation.dr = 1
            self.db.commit()

            return DatabaseResult.success_result(
                data=True,
                message="标签移除成功",
                affected_rows=1
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"移除标签失败: {str(e)}")
            return DatabaseResult.database_error_result(f"移除标签失败: {str(e)}")

    def batch_assign_tags(
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
                    relation.relation_id = str(uuid.uuid4())

                relation.assigned_at = datetime.utcnow()

                self.db.add(relation)
                self.db.commit()

                success_count += 1
            except Exception as e:
                failed_count += 1
                failed_items.append({
                    "index": idx,
                    "torrent_hash": relation.torrent_hash,
                    "tag_id": relation.tag_id,
                    "error": str(e)
                })
                self.db.rollback()

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
