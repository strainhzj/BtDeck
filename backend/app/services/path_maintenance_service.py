# -*- coding: utf-8 -*-
"""
下载器路径维护服务

管理每个下载器的路径信息，包括默认路径和活跃路径列表。
支持种子转移时的路径选择。

@author: btpManager Team
@file: path_maintenance_service.py
@time: 2026-02-15
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.downloader_path_maintenance import DownloaderPathMaintenance
from app.models.downloader_path_maintenance import (
    DownloaderPathMaintenance,
    DownloaderPathMaintenance as DownloaderPathMaintenanceModel
)

logger = logging.getLogger(__name__)


class PathMaintenanceService:
    """
    下载器路径维护服务

    提供下载器路径信息的CRUD操作，包括：
    - 默认路径管理（default）
    - 活跃路径管理（active）
    - 路径去重逻辑
    - 种子数量统计
    """

    def __init__(self, db: Session):
        """
        初始化路径维护服务

        Args:
            db: 数据库会话
        """
        self.db = db

    # ========== 查询操作 ==========

    def get_paths_by_downloader(
        self,
        downloader_id: str,
        path_type: Optional[str] = None,
        is_enabled: Optional[bool] = None
    ) -> List[DownloaderPathMaintenanceModel]:
        """
        获取下载器的路径列表

        Args:
            downloader_id: 下载器ID
            path_type: 路径类型过滤（default/active），None表示全部
            is_enabled: 是否启用过滤，None表示全部

        Returns:
            路径列表
        """
        try:
            query = self.db.query(DownloaderPathMaintenanceModel).filter(
                DownloaderPathMaintenanceModel.downloader_id == downloader_id
            )

            if path_type:
                query = query.filter(DownloaderPathMaintenanceModel.path_type == path_type)

            if is_enabled is not None:
                query = query.filter(DownloaderPathMaintenanceModel.is_enabled == is_enabled)

            paths = query.order_by(
                DownloaderPathMaintenanceModel.path_type,
                DownloaderPathMaintenanceModel.created_at.desc()
            ).all()

            logger.info(f"获取下载器 {downloader_id} 的路径列表成功，共 {len(paths)} 条")
            return paths

        except Exception as e:
            logger.error(f"获取下载器 {downloader_id} 路径列表失败: {str(e)}")
            raise

    def get_path_by_id(self, path_id: int) -> Optional[DownloaderPathMaintenanceModel]:
        """
        根据ID获取路径信息

        Args:
            path_id: 路径ID

        Returns:
            路径对象，不存在返回None
        """
        try:
            path = self.db.query(DownloaderPathMaintenanceModel).filter(
                DownloaderPathMaintenanceModel.id == path_id
            ).first()

            if not path:
                logger.warning(f"路径ID {path_id} 不存在")
                return None

            return path

        except Exception as e:
            logger.error(f"获取路径ID {path_id} 失败: {str(e)}")
            raise

    def get_default_path(self, downloader_id: int) -> Optional[str]:
        """
        获取下载器的默认路径

        Args:
            downloader_id: 下载器ID

        Returns:
            默认路径值，不存在返回None
        """
        try:
            path = self.db.query(DownloaderPathMaintenanceModel).filter(
                DownloaderPathMaintenanceModel.downloader_id == downloader_id,
                DownloaderPathMaintenanceModel.path_type == 'default',
                DownloaderPathMaintenanceModel.is_enabled == True
            ).first()

            return path.path_value if path else None

        except Exception as e:
            logger.error(f"获取下载器 {downloader_id} 默认路径失败: {str(e)}")
            return None

    def get_active_paths(self, downloader_id: int) -> List[str]:
        """
        获取下载器的所有活跃路径

        Args:
            downloader_id: 下载器ID

        Returns:
            活跃路径值列表
        """
        try:
            paths = self.db.query(DownloaderPathMaintenanceModel).filter(
                DownloaderPathMaintenanceModel.downloader_id == downloader_id,
                DownloaderPathMaintenanceModel.path_type == 'active',
                DownloaderPathMaintenanceModel.is_enabled == True
            ).all()

            return [p.path_value for p in paths]

        except Exception as e:
            logger.error(f"获取下载器 {downloader_id} 活跃路径失败: {str(e)}")
            return []

    # ========== 创建操作 ==========

    def create_path(
        self,
        downloader_id: int,
        path_type: str,
        path_value: str,
        is_enabled: bool = True,
        torrent_count: int = 0
    ) -> DownloaderPathMaintenanceModel:
        """
        创建新路径

        Args:
            downloader_id: 下载器ID
            path_type: 路径类型（default/active）
            path_value: 路径值
            is_enabled: 是否启用
            torrent_count: 使用该路径的种子数量

        Returns:
            创建的路径对象

        Raises:
            ValueError: 路径类型无效或路径已存在
        """
        # 验证路径类型
        if path_type not in ['default', 'active']:
            raise ValueError(f"无效的路径类型: {path_type}，必须是 'default' 或 'active'")

        # 验证路径去重
        existing = self.db.query(DownloaderPathMaintenanceModel).filter(
            DownloaderPathMaintenanceModel.downloader_id == downloader_id,
            DownloaderPathMaintenanceModel.path_type == path_type,
            DownloaderPathMaintenanceModel.path_value == path_value
        ).first()

        if existing:
            raise ValueError(f"路径已存在: downloader_id={downloader_id}, path_type={path_type}, path_value={path_value}")

        try:
            path = DownloaderPathMaintenanceModel(
                downloader_id=downloader_id,
                path_type=path_type,
                path_value=path_value,
                is_enabled=is_enabled,
                torrent_count=torrent_count,
                last_updated_time=datetime.utcnow()
            )

            self.db.add(path)
            self.db.commit()

            logger.info(f"创建路径成功: {path_type} - {path_value}")
            return path

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建路径失败: {str(e)}")
            raise

    # ========== 更新操作 ==========

    def update_path(
        self,
        path_id: int,
        path_value: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        torrent_count: Optional[int] = None
    ) -> bool:
        """
        更新路径信息

        Args:
            path_id: 路径ID
            path_value: 新的路径值（可选）
            is_enabled: 是否启用（可选）
            torrent_count: 种子数量（可选）

        Returns:
            是否更新成功
        """
        try:
            path = self.get_path_by_id(path_id)
            if not path:
                return False

            if path_value is not None:
                # 检查路径值是否与其他路径重复
                existing = self.db.query(DownloaderPathMaintenanceModel).filter(
                    DownloaderPathMaintenanceModel.downloader_id == path.downloader_id,
                    DownloaderPathMaintenanceModel.path_type == path.path_type,
                    DownloaderPathMaintenanceModel.path_value == path_value,
                    DownloaderPathMaintenanceModel.id != path_id
                ).first()

                if existing:
                    raise ValueError(f"路径值已存在: {path_value}")

                path.path_value = path_value

            if is_enabled is not None:
                path.is_enabled = is_enabled

            if torrent_count is not None:
                path.torrent_count = torrent_count
                path.last_updated_time = datetime.utcnow()

            path.updated_at = datetime.utcnow()

            self.db.commit()
            logger.info(f"更新路径成功: ID={path_id}")
            return True

        except ValueError:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新路径失败: {str(e)}")
            raise

    def update_torrent_count(self, path_id: int, count: int) -> bool:
        """
        更新路径的种子数量

        Args:
            path_id: 路径ID
            count: 新的种子数量

        Returns:
            是否更新成功
        """
        try:
            path = self.get_path_by_id(path_id)
            if not path:
                return False

            path.torrent_count = count
            path.last_updated_time = datetime.utcnow()

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"更新种子数量失败: {str(e)}")
            return False

    def increment_torrent_count(self, path_id: int) -> bool:
        """
        增加路径的种子数量

        Args:
            path_id: 路径ID

        Returns:
            是否更新成功
        """
        try:
            path = self.get_path_by_id(path_id)
            if not path:
                return False

            path.torrent_count += 1
            path.last_updated_time = datetime.utcnow()

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"增加种子数量失败: {str(e)}")
            return False

    def decrement_torrent_count(self, path_id: int) -> bool:
        """
        减少路径的种子数量

        Args:
            path_id: 路径ID

        Returns:
            是否更新成功
        """
        try:
            path = self.get_path_by_id(path_id)
            if not path:
                return False

            if path.torrent_count > 0:
                path.torrent_count -= 1
                path.last_updated_time = datetime.utcnow()

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"减少种子数量失败: {str(e)}")
            return False

    # ========== 删除操作 ==========

    def delete_path(self, path_id: int) -> bool:
        """
        逻辑删除路径（标记为未启用）

        Args:
            path_id: 路径ID

        Returns:
            是否删除成功
        """
        try:
            path = self.get_path_by_id(path_id)
            if not path:
                return False

            path.is_enabled = False
            path.updated_at = datetime.utcnow()

            self.db.commit()
            logger.info(f"删除路径成功: ID={path_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"删除路径失败: {str(e)}")
            return False

    def enable_path(self, path_id: int) -> bool:
        """
        启用路径

        Args:
            path_id: 路径ID

        Returns:
            是否启用成功
        """
        try:
            path = self.get_path_by_id(path_id)
            if not path:
                return False

            path.is_enabled = True
            path.updated_at = datetime.utcnow()

            self.db.commit()
            logger.info(f"启用路径成功: ID={path_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"启用路径失败: {str(e)}")
            return False

    # ========== 统计操作 ==========

    def get_path_count(self, downloader_id: int, path_type: Optional[str] = None) -> Dict[str, int]:
        """
        获取路径统计信息

        Args:
            downloader_id: 下载器ID
            path_type: 路径类型过滤（可选）

        Returns:
            统计信息字典，包含 total/default/active/count
        """
        try:
            base_query = self.db.query(DownloaderPathMaintenanceModel).filter(
                DownloaderPathMaintenanceModel.downloader_id == downloader_id
            )

            if path_type:
                base_query = base_query.filter(DownloaderPathMaintenanceModel.path_type == path_type)

            total = base_query.count()
            enabled = base_query.filter(DownloaderPathMaintenanceModel.is_enabled == True).count()

            default_count = base_query.filter(
                DownloaderPathMaintenanceModel.path_type == 'default'
            ).count()

            active_count = base_query.filter(
                DownloaderPathMaintenanceModel.path_type == 'active'
            ).count()

            return {
                'total': total,
                'enabled': enabled,
                'default': default_count,
                'active': active_count,
                'count': total  # 兼容字段
            }

        except Exception as e:
            logger.error(f"获取路径统计失败: {str(e)}")
            return {
                'total': 0,
                'enabled': 0,
                'default': 0,
                'active': 0,
                'count': 0
            }

    def sync_paths_from_torrents(
        self,
        downloader_id: int,
        default_path: str,
        active_paths: List[str]
    ) -> Dict[str, Any]:
        """
        从种子任务同步路径信息

        Args:
            downloader_id: 下载器ID
            default_path: 默认路径
            active_paths: 活跃路径列表（所有种子的保存路径）

        Returns:
            同步结果统计
        """
        try:
            result = {
                'created': 0,
                'updated': 0,
                'skipped': 0,
                'errors': []
            }

            # 同步默认路径
            existing_default = self.db.query(DownloaderPathMaintenanceModel).filter(
                DownloaderPathMaintenanceModel.downloader_id == downloader_id,
                DownloaderPathMaintenanceModel.path_type == 'default',
                DownloaderPathMaintenanceModel.path_value == default_path
            ).first()

            if existing_default:
                # 更新最后更新时间
                existing_default.last_updated_time = datetime.utcnow()
                result['updated'] += 1
            else:
                # 创建默认路径
                self.create_path(
                    downloader_id=downloader_id,
                    path_type='default',
                    path_value=default_path,
                    is_enabled=True
                )
                result['created'] += 1

            # 同步活跃路径
            # 统计每个路径的使用次数
            path_count = {}
            for path in active_paths:
                if path not in path_count:
                    path_count[path] = 0
                path_count[path] += 1

            # 更新或创建活跃路径
            for path_value, count in path_count.items():
                existing = self.db.query(DownloaderPathMaintenanceModel).filter(
                    DownloaderPathMaintenanceModel.downloader_id == downloader_id,
                    DownloaderPathMaintenanceModel.path_type == 'active',
                    DownloaderPathMaintenanceModel.path_value == path_value
                ).first()

                if existing:
                    # 更新种子数量
                    if existing.torrent_count != count:
                        existing.torrent_count = count
                        existing.last_updated_time = datetime.utcnow()
                        result['updated'] += 1
                    else:
                        result['skipped'] += 1
                else:
                    # 创建新路径
                    self.create_path(
                        downloader_id=downloader_id,
                        path_type='active',
                        path_value=path_value,
                        is_enabled=True,
                        torrent_count=count
                    )
                    result['created'] += 1

            logger.info(f"同步下载器 {downloader_id} 路径完成: {result}")
            return result

        except Exception as e:
            logger.error(f"同步路径失败: {str(e)}")
            result['errors'].append(str(e))
            return result
