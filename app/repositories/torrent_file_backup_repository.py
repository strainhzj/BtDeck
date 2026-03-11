# -*- coding: utf-8 -*-
"""
种子文件备份仓储（Repository）

负责种子文件备份数据库操作的数据访问层。
遵循Repository模式，封装所有数据库CRUD操作。

职责：
- 数据库CRUD操作（增删改查）
- 数据库事务管理
- 数据一致性验证
- 乐观锁控制（version字段）

@author: btpManager Team
@file: torrent_file_backup_repository.py
@time: 2026-02-15
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.models.torrent_file_backup import TorrentFileBackup
from app.database import AsyncSessionLocal


class TorrentFileBackupRepository:
    """
    种子文件备份仓储类

    提供种子文件备份数据库操作的统一接口。
    所有数据库操作通过此类进行，确保数据访问的一致性。
    """

    def __init__(self, db: AsyncSession):
        """
        初始化仓储

        Args:
            db: 异步数据库会话
        """
        self.db = db

    async def create(
        self,
        info_hash: str,
        file_path: str,
        file_size: Optional[int] = None,
        task_name: Optional[str] = None,
        uploader_id: Optional[int] = None,
        downloader_id: Optional[int] = None,
        upload_time: Optional[datetime] = None,
        use_count: int = 0
    ) -> Optional[TorrentFileBackup]:
        """
        创建种子文件备份记录

        Args:
            info_hash: 种子的info_hash（唯一）
            file_path: 种子文件存储路径
            file_size: 文件大小（字节）
            task_name: 关联的任务名称
            uploader_id: 上传用户ID
            downloader_id: 关联的下载器ID
            upload_time: 上传时间
            use_count: 使用次数

        Returns:
            创建的TorrentFileBackup对象，失败返回None

        Raises:
            ValueError: 参数验证失败
            SQLAlchemyError: 数据库操作失败
        """
        try:
            # 验证参数
            if not info_hash or len(info_hash) != 40:
                raise ValueError("info_hash必须是40位字符")

            if not file_path:
                raise ValueError("file_path不能为空")

            # 检查是否已存在（去重）
            existing = await self.get_by_info_hash(info_hash)
            if existing:
                raise ValueError(f"info_hash {info_hash} 已存在")

            # 创建记录
            torrent_backup = TorrentFileBackup(
                info_hash=info_hash,
                file_path=file_path,
                file_size=file_size,
                task_name=task_name,
                uploader_id=uploader_id,
                downloader_id=downloader_id,
                upload_time=upload_time,
                use_count=use_count,
                is_deleted=False
            )

            self.db.add(torrent_backup)
            await self.db.commit()
            await self.db.refresh(torrent_backup)

            return torrent_backup

        except ValueError as e:
            await self.db.rollback()
            raise e
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise e

    async def get_by_info_hash(
        self,
        info_hash: str,
        include_deleted: bool = False
    ) -> Optional[TorrentFileBackup]:
        """
        根据info_hash查询种子文件备份

        Args:
            info_hash: 种子的info_hash
            include_deleted: 是否包含已删除的记录

        Returns:
            TorrentFileBackup对象或None
        """
        try:
            query = select(TorrentFileBackup).filter(
                TorrentFileBackup.info_hash == info_hash
            )

            if not include_deleted:
                query = query.filter(TorrentFileBackup.is_deleted == False)

            result = await self.db.execute(query)
            return result.scalar_one_or_none()

        except SQLAlchemyError as e:
            return None

    async def get_by_id(
        self,
        backup_id: int
    ) -> Optional[TorrentFileBackup]:
        """
        根据ID查询种子文件备份

        Args:
            backup_id: 备份记录ID

        Returns:
            TorrentFileBackup对象或None
        """
        try:
            query = select(TorrentFileBackup).filter(
                TorrentFileBackup.id == backup_id
            ).filter(
                TorrentFileBackup.is_deleted == False
            )

            result = await self.db.execute(query)
            return result.scalar_one_or_none()

        except SQLAlchemyError as e:
            return None

    async def list_by_downloader(
        self,
        downloader_id: int,
        skip: int = 0,
        limit: int = 20
    ) -> List[TorrentFileBackup]:
        """
        按下载器查询种子文件备份列表

        Args:
            downloader_id: 下载器ID
            skip: 跳过记录数
            limit: 返回记录数

        Returns:
            TorrentFileBackup对象列表
        """
        try:
            query = select(TorrentFileBackup).filter(
                TorrentFileBackup.downloader_id == downloader_id
            ).filter(
                TorrentFileBackup.is_deleted == False
            ).order_by(
                TorrentFileBackup.created_at.desc()
            ).offset(skip).limit(limit)

            result = await self.db.execute(query)
            return list(result.scalars().all())

        except SQLAlchemyError as e:
            return []

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 20
    ) -> List[TorrentFileBackup]:
        """
        查询所有种子文件备份列表

        Args:
            skip: 跳过记录数
            limit: 返回记录数

        Returns:
            TorrentFileBackup对象列表
        """
        try:
            query = select(TorrentFileBackup).filter(
                TorrentFileBackup.is_deleted == False
            ).order_by(
                TorrentFileBackup.created_at.desc()
            ).offset(skip).limit(limit)

            result = await self.db.execute(query)
            return list(result.scalars().all())

        except SQLAlchemyError as e:
            return []

    async def count_by_downloader(
        self,
        downloader_id: int
    ) -> int:
        """
        统计下载器的备份文件数量

        Args:
            downloader_id: 下载器ID

        Returns:
            备份文件数量
        """
        try:
            from sqlalchemy import func

            query = select(func.count(TorrentFileBackup.id)).filter(
                TorrentFileBackup.downloader_id == downloader_id
            ).filter(
                TorrentFileBackup.is_deleted == False
            )

            result = await self.db.execute(query)
            return result.scalar_one() or 0

        except SQLAlchemyError as e:
            return 0

    async def count_all(self) -> int:
        """
        统计所有备份文件数量

        Returns:
            备份文件总数量
        """
        try:
            from sqlalchemy import func

            query = select(func.count(TorrentFileBackup.id)).filter(
                TorrentFileBackup.is_deleted == False
            )

            result = await self.db.execute(query)
            return result.scalar_one() or 0

        except SQLAlchemyError as e:
            return 0

    async def soft_delete(
        self,
        info_hash: str
    ) -> bool:
        """
        逻辑删除种子文件备份

        Args:
            info_hash: 种子的info_hash

        Returns:
            是否删除成功
        """
        try:
            # 获取记录
            torrent_backup = await self.get_by_info_hash(info_hash)
            if not torrent_backup:
                return False

            # 执行逻辑删除
            torrent_backup.soft_delete()
            await self.db.commit()

            return True

        except SQLAlchemyError as e:
            await self.db.rollback()
            return False

    async def physical_delete(
        self,
        info_hash: str
    ) -> bool:
        """
        物理删除种子文件备份记录

        Args:
            info_hash: 种子的info_hash

        Returns:
            是否删除成功
        """
        try:
            # 直接执行DELETE语句
            stmt = delete(TorrentFileBackup).filter(
                TorrentFileBackup.info_hash == info_hash
            )

            result = await self.db.execute(stmt)
            await self.db.commit()

            return result.rowcount > 0

        except SQLAlchemyError as e:
            await self.db.rollback()
            return False

    async def increment_use_count(
        self,
        info_hash: str
    ) -> bool:
        """
        增加种子文件使用次数并更新最后使用时间

        Args:
            info_hash: 种子的info_hash

        Returns:
            是否更新成功
        """
        try:
            # 获取记录
            torrent_backup = await self.get_by_info_hash(info_hash)
            if not torrent_backup:
                return False

            # 增加使用次数
            torrent_backup.increment_use_count()
            await self.db.commit()

            return True

        except SQLAlchemyError as e:
            await self.db.rollback()
            return False

    async def update_file_path(
        self,
        info_hash: str,
        file_path: str,
        file_size: Optional[int] = None
    ) -> bool:
        """
        更新种子文件路径

        Args:
            info_hash: 种子的info_hash
            file_path: 新的文件路径
            file_size: 文件大小（可选）

        Returns:
            是否更新成功
        """
        try:
            # 获取记录
            torrent_backup = await self.get_by_info_hash(info_hash)
            if not torrent_backup:
                return False

            # 更新字段
            torrent_backup.file_path = file_path
            if file_size is not None:
                torrent_backup.file_size = file_size

            await self.db.commit()
            return True

        except SQLAlchemyError as e:
            await self.db.rollback()
            return False

    async def check_exists(
        self,
        info_hash: str
    ) -> bool:
        """
        检查种子文件备份是否存在

        用于去重验证。

        Args:
            info_hash: 种子的info_hash

        Returns:
            是否存在
        """
        try:
            query = select(TorrentFileBackup.id).filter(
                TorrentFileBackup.info_hash == info_hash
            ).filter(
                TorrentFileBackup.is_deleted == False
            )

            result = await self.db.execute(query)
            return result.scalar_one_or_none() is not None

        except SQLAlchemyError as e:
            return False

    async def get_total_size_by_downloader(
        self,
        downloader_id: int
    ) -> int:
        """
        统计下载器备份文件总大小

        Args:
            downloader_id: 下载器ID

        Returns:
            总大小（字节）
        """
        try:
            from sqlalchemy import func

            query = select(func.sum(TorrentFileBackup.file_size)).filter(
                TorrentFileBackup.downloader_id == downloader_id
            ).filter(
                TorrentFileBackup.file_size.isnot(None)
            ).filter(
                TorrentFileBackup.is_deleted == False
            )

            result = await self.db.execute(query)
            return result.scalar_one() or 0

        except SQLAlchemyError as e:
            return 0
