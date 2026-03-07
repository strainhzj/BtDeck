from typing import Any, Optional, Dict

from sqlalchemy import Boolean, Column, Integer, String, DateTime, BigInteger, Text
from app.database import Base
from app.models.setting_templates import DownloaderTypeEnum
import logging

logger = logging.getLogger(__name__)

class BtDownloaders(Base):
    __tablename__ = "bt_downloaders"

    downloader_id = Column(String, primary_key=True, index=True)
    nickname = Column(String, index=True)  #   自定义名称
    host = Column(String, index=True)  #  下载器主机
    username = Column(String, index=True)  #  登录用户名
    password = Column(String)  # SM4加密后的密码
    is_search = Column(Boolean, default=True)  # 是否启用种子搜索
    status = Column(String, default=True)  #  下载器状态
    enabled = Column(Boolean, default=True)  #  下载器启用状态
    downloader_type = Column(String, default=True)  # 下载器类型
    port = Column(String, index=True)  # 端口
    is_ssl = Column(Boolean, default=True)  # 是否https
    dr = Column(Integer, default=0)   #   删除状态，0是未删除，1是逻辑删除
    path_mapping = Column(Text, nullable=True, comment='路径映射配置（JSON格式）')  # 路径映射配置
    path_mapping_rules = Column(Text, nullable=True, comment='路径映射规则配置（多行文本，格式：源路径{#**#}目标路径）')  # 路径映射规则
    torrent_save_path = Column(String(500), nullable=True, comment='种子保存目录路径（应用运行环境可直接访问的绝对路径）')  # 种子保存目录

    def __init__(self, downloader_id=None, nickname=None, host=None, username=None, password=None,
                 is_search=True, status=None, enabled=True, downloader_type=None,
                 port=None, is_ssl=True, dr=0, path_mapping=None, path_mapping_rules=None, torrent_save_path=None, **kw: Any):
        super().__init__(**kw)
        if downloader_id is not None:
            self.downloader_id = downloader_id
        if nickname is not None:
            self.nickname = nickname
        if host is not None:
            self.host = host
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password
        if is_search is not None:
            self.is_search = is_search
        if status is not None:
            self.status = status
        if enabled is not None:
            self.enabled = enabled
        if downloader_type is not None:
            self.downloader_type = downloader_type
        if port is not None:
            self.port = port
        if is_ssl is not None:
            self.is_ssl = is_ssl
        if dr is not None:
            self.dr = dr
        if path_mapping is not None:
            self.path_mapping = path_mapping
        if path_mapping_rules is not None:
            self.path_mapping_rules = path_mapping_rules
        if torrent_save_path is not None:
            self.torrent_save_path = torrent_save_path

    def to_dict(self):
        return {
            "downloader_id": self.downloader_id,
            "nickname": self.nickname,
            "host": self.host,
            "username": self.username,
            "password": self.password,
            "is_search": self.is_search,
            "status": self.status,
            "enabled": self.enabled,
            "downloader_type": self.downloader_type,
            "port": self.port,
            "is_ssl": self.is_ssl,
            "dr": self.dr,
            "path_mapping": self.path_mapping,
            "path_mapping_rules": self.path_mapping_rules,
            "torrent_save_path": self.torrent_save_path,
        }

    @property
    def path_mapping_service(self):
        """获取统一路径映射服务实例

        使用 UnifiedPathMappingService 整合 path_mapping 和 path_mapping_rules，
        提供统一的路径映射接口。

        Returns:
            UnifiedPathMappingService: 统一路径映射服务实例
        """
        try:
            from app.core.path_mapping import UnifiedPathMappingService
            return UnifiedPathMappingService(
                path_mapping=self.path_mapping,
                path_mapping_rules=self.path_mapping_rules
            )
        except Exception as e:
            logger.error(f"加载统一路径映射服务失败: {str(e)}")
            return None

    @property
    def file_operations_service(self):
        """获取文件操作服务实例"""
        try:
            from app.core.file_operations import FileOperationService
            path_mapping = self.path_mapping_service
            return FileOperationService(path_mapping)
        except Exception as e:
            logger.error(f"初始化文件操作服务失败: {str(e)}")
            return None

    @property
    def type_enum(self) -> DownloaderTypeEnum:
        """获取下载器类型枚举

        Returns:
            DownloaderTypeEnum: 下载器类型枚举值

        Raises:
            ValueError: 如果downloader_type值无效
        """
        return DownloaderTypeEnum.from_value(self.downloader_type)

    @property
    def is_qbittorrent(self) -> bool:
        """是否为qBittorrent类型

        Returns:
            bool: 是qBittorrent返回True
        """
        try:
            return self.type_enum.is_qbittorrent()
        except ValueError:
            logger.warning(f"无效的下载器类型: {self.downloader_type}")
            return False

    @property
    def is_transmission(self) -> bool:
        """是否为Transmission类型

        Returns:
            bool: 是Transmission返回True
        """
        try:
            return self.type_enum.is_transmission()
        except ValueError:
            logger.warning(f"无效的下载器类型: {self.downloader_type}")
            return False

    def validate_downloader_type(self) -> tuple[bool, str]:
        """验证下载器类型有效性

        Returns:
            tuple[bool, str]: (是否有效, 错误消息)
        """
        try:
            DownloaderTypeEnum.from_value(self.downloader_type)
            return True, ""
        except ValueError as e:
            return False, str(e)


class DownloaderStatus:
    def __init__(self, server_id, nickname, connect_status, upload_speed, download_speed, delay):
        self.server_id = server_id
        self.nickname = nickname
        self.connect_status = connect_status
        self.upload_speed = upload_speed
        self.download_speed = download_speed
        self.delay = delay

    def to_dict(self):
        return {
            "server_id": self.server_id,
            "nickname": self.nickname,
            "connect_status": self.connect_status,
            "upload_speed": self.upload_speed,
            "download_speed": self.download_speed,
            "delay": self.delay,
        }
