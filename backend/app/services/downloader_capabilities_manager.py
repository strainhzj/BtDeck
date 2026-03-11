# -*- coding: utf-8 -*-
"""
下载器能力配置管理服务

提供下载器能力配置的CRUD操作和同步逻辑
"""
from typing import Dict, Optional, Tuple, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.downloader_capabilities import DownloaderCapabilities
from app.models.setting_templates import DownloaderTypeEnum
from app.downloader.models import BtDownloaders
from app.downloader.exceptions import (
    DownloaderSettingsError,
    ConfigurationError,
)
import logging

logger = logging.getLogger(__name__)


class DownloaderCapabilitiesManager:
    """下载器能力配置管理器

    提供以下功能：
    1. 从数据库获取下载器能力配置
    2. 创建默认能力配置
    3. 从下载器同步能力配置
    4. 更新能力配置（支持手动覆盖）
    5. 删除能力配置
    """

    def __init__(self, db: Session):
        """
        初始化能力配置管理器

        Args:
            db: 数据库会话
        """
        self.db = db

    def get_capabilities(
        self,
        downloader_id: str,
        create_if_not_exists: bool = True,
        default_for_type: Optional[int] = None
    ) -> Optional[DownloaderCapabilities]:
        """
        获取下载器能力配置

        Args:
            downloader_id: 下载器ID
            create_if_not_exists: 如果配置不存在，是否创建默认配置
            default_for_type: 下载器类型（0=qBittorrent, 1=Transmission），用于创建默认配置

        Returns:
            DownloaderCapabilities: 能力配置对象，如果不存在且create_if_not_exists=False则返回None

        Raises:
            ConfigurationError: 下载器不存在或创建失败
        """
        # 1. 从数据库查询现有配置
        capabilities = self.db.query(DownloaderCapabilities).filter(
            DownloaderCapabilities.downloader_id == downloader_id
        ).first()

        if capabilities:
            logger.debug(f"获取下载器能力配置成功: {downloader_id}")
            return capabilities

        # 2. 如果不存在且不创建，返回None
        if not create_if_not_exists:
            logger.info(f"下载器能力配置不存在: {downloader_id}")
            return None

        # 3. 创建默认配置
        if default_for_type is None:
            # 从数据库查询下载器类型
            downloader = self.db.query(BtDownloaders).filter(
                BtDownloaders.downloader_id == downloader_id,
                BtDownloaders.dr == 0
            ).first()

            if not downloader:
                raise ConfigurationError(
                    message=f"下载器不存在: {downloader_id}",
                    parameter_name="downloader_id",
                    parameter_value=downloader_id
                )

            default_for_type = downloader.downloader_type

        logger.info(f"创建默认下载器能力配置: {downloader_id}, 类型: {default_for_type}")
        return self.create_default_capabilities(downloader_id, default_for_type)

    def create_default_capabilities(
        self,
        downloader_id: str,
        downloader_type: int
    ) -> DownloaderCapabilities:
        """
        创建默认下载器能力配置

        Args:
            downloader_id: 下载器ID
            downloader_type: 下载器类型（0=qBittorrent, 1=Transmission）

        Returns:
            DownloaderCapabilities: 创建的能力配置对象

        Raises:
            ConfigurationError: 创建失败
        """
        try:
            # 根据下载器类型设置默认能力
            normalized_type = DownloaderTypeEnum.normalize(downloader_type)

            if normalized_type == DownloaderTypeEnum.QBITTORRENT:
                capabilities = DownloaderCapabilities(
                    downloader_id=downloader_id,
                    supports_speed_scheduling=True,  # 应用层实现
                    supports_transfer_speed=True,
                    supports_connection_limits=True,
                    supports_queue_settings=True,
                    supports_download_paths=False,  # qBittorrent不支持
                    supports_port_settings=True,
                    supports_advanced_settings=True,
                    supports_peer_limits=True,
                    synced_from_downloader=False,
                    manual_override=False
                )
            elif normalized_type == DownloaderTypeEnum.TRANSMISSION:
                capabilities = DownloaderCapabilities(
                    downloader_id=downloader_id,
                    supports_speed_scheduling=False,  # Transmission暂不支持（可通过alt_speed实现）
                    supports_transfer_speed=True,
                    supports_connection_limits=True,
                    supports_queue_settings=True,
                    supports_download_paths=True,  # Transmission支持
                    supports_port_settings=True,
                    supports_advanced_settings=True,
                    supports_peer_limits=True,
                    synced_from_downloader=False,
                    manual_override=False
                )
            else:
                raise ConfigurationError(
                    message=f"不支持的下载器类型: {downloader_type}",
                    parameter_name="downloader_type",
                    parameter_value=downloader_type
                )

            self.db.add(capabilities)
            self.db.commit()
            self.db.refresh(capabilities)

            logger.info(f"创建默认能力配置成功: {downloader_id}, 类型: {downloader_type}")
            return capabilities

        except Exception as e:
            self.db.rollback()
            logger.error(f"创建默认能力配置失败: {downloader_id}, 错误: {e}")
            raise ConfigurationError(
                message=f"创建默认能力配置失败: {str(e)}",
                parameter_name="downloader_id",
                parameter_value=downloader_id
            )

    def sync_from_downloader(
        self,
        downloader_id: str,
        downloader_capabilities: Dict[str, bool],
        force: bool = False
    ) -> DownloaderCapabilities:
        """
        从下载器同步能力配置

        Args:
            downloader_id: 下载器ID
            downloader_capabilities: 从下载器获取的能力字典（蛇形命名）
            force: 是否强制更新（忽略manual_override标记）

        Returns:
            DownloaderCapabilities: 更新后的能力配置对象

        Raises:
            ConfigurationError: 同步失败
        """
        try:
            # 获取现有配置
            capabilities = self.get_capabilities(
                downloader_id=downloader_id,
                create_if_not_exists=True
            )

            if not capabilities:
                raise ConfigurationError(
                    message=f"能力配置不存在且创建失败: {downloader_id}",
                    parameter_name="downloader_id",
                    parameter_value=downloader_id
                )

            # 检查是否为手动覆盖
            if capabilities.manual_override and not force:
                logger.info(f"下载器 {downloader_id} 的能力配置为手动覆盖，跳过自动同步")
                return capabilities

            # 更新能力配置
            capabilities.update_from_downloader_capabilities(
                downloader_capabilities=downloader_capabilities,
                force=force
            )

            self.db.commit()
            self.db.refresh(capabilities)

            logger.info(f"从下载器同步能力配置成功: {downloader_id}")
            return capabilities

        except Exception as e:
            self.db.rollback()
            logger.error(f"从下载器同步能力配置失败: {downloader_id}, 错误: {e}")
            raise ConfigurationError(
                message=f"同步能力配置失败: {str(e)}",
                parameter_name="downloader_id",
                parameter_value=downloader_id
            )

    def update_capabilities(
        self,
        downloader_id: str,
        capabilities_dict: Dict[str, bool],
        set_manual_override: bool = True
    ) -> DownloaderCapabilities:
        """
        更新下载器能力配置（用户手动修改）

        Args:
            downloader_id: 下载器ID
            capabilities_dict: 能力字典（驼峰命名或蛇形命名均可）
            set_manual_override: 是否设置为手动覆盖（设置为True后不再自动同步）

        Returns:
            DownloaderCapabilities: 更新后的能力配置对象

        Raises:
            ConfigurationError: 更新失败
        """
        try:
            # 获取现有配置
            capabilities = self.get_capabilities(
                downloader_id=downloader_id,
                create_if_not_exists=True
            )

            if not capabilities:
                raise ConfigurationError(
                    message=f"能力配置不存在且创建失败: {downloader_id}",
                    parameter_name="downloader_id",
                    parameter_value=downloader_id
                )

            # 字段名映射：驼峰命名 → 模型字段
            field_mapping = {
                "supports_speed_scheduling": "supports_speed_scheduling",
                "transferSpeed": "supports_transfer_speed",
                "transfer_speed": "supports_transfer_speed",
                "connectionLimits": "supports_connection_limits",
                "connection_limits": "supports_connection_limits",
                "queueSettings": "supports_queue_settings",
                "queue_settings": "supports_queue_settings",
                "downloadPaths": "supports_download_paths",
                "download_paths": "supports_download_paths",
                "portSettings": "supports_port_settings",
                "port_settings": "supports_port_settings",
                "advancedSettings": "supports_advanced_settings",
                "advanced_settings": "supports_advanced_settings",
                "peerLimits": "supports_peer_limits",
                "peer_limits": "supports_peer_limits",
            }

            # 更新核心能力开关
            for key, value in capabilities_dict.items():
                if key in field_mapping:
                    field_name = field_mapping[key]
                    setattr(capabilities, field_name, bool(value))

            # 设置手动覆盖标记
            if set_manual_override:
                capabilities.set_manual_override(True)

            # 更新时间戳
            capabilities.updated_at = datetime.now()

            self.db.commit()
            self.db.refresh(capabilities)

            logger.info(f"更新下载器能力配置成功: {downloader_id}, manual_override={set_manual_override}")
            return capabilities

        except Exception as e:
            self.db.rollback()
            logger.error(f"更新下载器能力配置失败: {downloader_id}, 错误: {e}")
            raise ConfigurationError(
                message=f"更新能力配置失败: {str(e)}",
                parameter_name="downloader_id",
                parameter_value=downloader_id
            )

    def delete_capabilities(self, downloader_id: str) -> bool:
        """
        删除下载器能力配置

        Args:
            downloader_id: 下载器ID

        Returns:
            bool: 删除成功返回True，配置不存在返回False
        """
        try:
            capabilities = self.db.query(DownloaderCapabilities).filter(
                DownloaderCapabilities.downloader_id == downloader_id
            ).first()

            if not capabilities:
                logger.info(f"下载器能力配置不存在: {downloader_id}")
                return False

            self.db.delete(capabilities)
            self.db.commit()

            logger.info(f"删除下载器能力配置成功: {downloader_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"删除下载器能力配置失败: {downloader_id}, 错误: {e}")
            return False

    def reset_to_default(
        self,
        downloader_id: str,
        downloader_type: Optional[int] = None
    ) -> DownloaderCapabilities:
        """
        重置为默认能力配置（清除手动覆盖标记）

        Args:
            downloader_id: 下载器ID
            downloader_type: 下载器类型（如果不提供，则从数据库查询）

        Returns:
            DownloaderCapabilities: 重置后的能力配置对象

        Raises:
            ConfigurationError: 重置失败
        """
        try:
            # 删除现有配置
            self.delete_capabilities(downloader_id)

            # 创建新的默认配置
            if downloader_type is None:
                downloader = self.db.query(BtDownloaders).filter(
                    BtDownloaders.downloader_id == downloader_id,
                    BtDownloaders.dr == 0
                ).first()

                if not downloader:
                    raise ConfigurationError(
                        message=f"下载器不存在: {downloader_id}",
                        parameter_name="downloader_id",
                        parameter_value=downloader_id
                    )

                downloader_type = downloader.downloader_type

            return self.create_default_capabilities(downloader_id, downloader_type)

        except Exception as e:
            logger.error(f"重置下载器能力配置失败: {downloader_id}, 错误: {e}")
            raise ConfigurationError(
                message=f"重置能力配置失败: {str(e)}",
                parameter_name="downloader_id",
                parameter_value=downloader_id
            )
