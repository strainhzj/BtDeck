# -*- coding: utf-8 -*-
"""
qBittorrent设置封装类

封装qBittorrent Web API调用，提供统一的设置接口
"""
from typing import Dict, Optional, Tuple, Union, Any
from qbittorrentapi import Client
from qbittorrentapi import (
    APIConnectionError as QBAPIConnectionError,
    LoginFailed as QBLoginFailed,
    HTTP401Error,
    HTTP403Error,
    HTTP500Error,
)
import logging

from app.downloader.exceptions import (
    DownloaderConnectionError,
    AuthenticationError,
    APIError,
    DownloaderTimeoutError,
    ConfigurationError,
)
from app.utils.log_sanitizer import sanitize_ip, should_sanitize

logger = logging.getLogger(__name__)


class QBitTorrentSettings:
    """qBittorrent设置封装类

    提供qBittorrent下载器的设置管理功能
    """

    def __init__(
        self,
        client: Optional[Client] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 10
    ):
        """
        初始化qBittorrent设置封装类

        双模式初始化(兼容旧代码,但强烈建议使用新方式):

        新方式(推荐):
            QBitTorrentSettings(client=cached_client)
            - 直接使用缓存中的客户端连接
            - 不创建新连接,避免资源浪费
            - 符合项目规范(CL-16)

        旧方式(已废弃,会触发警告):
            QBitTorrentSettings(host=..., port=..., username=..., password=...)
            - 内部会创建新的客户端连接(违反规范)
            - 仅用于向后兼容,计划在下一个版本移除
            - 会记录 DeprecationWarning 日志

        Args:
            client: 已创建的客户端实例(推荐)
            host: 下载器主机地址(已废弃)
            port: 下载器端口(已废弃)
            username: 用户名(已废弃)
            password: 密码(已废弃)
            timeout: 连接超时时间(已废弃)

        Raises:
            ConfigurationError: 参数冲突或无效时抛出
            DownloaderConnectionError: 客户端初始化失败时抛出(仅旧方式)
        """
        # 新方式: 直接使用缓存的客户端
        if client is not None:
            self._client = client
            self._from_cache = True
            self.host = None
            self.port = None
            self.username = None
            self.password = None
            self.timeout = None
            logger.debug("QBitTorrentSettings 使用缓存客户端初始化(推荐方式)")
            return

        # 旧方式: 从连接参数创建客户端(已废弃)
        if client is None and host is not None:
            # 记录废弃警告
            logger.warning(
                "DeprecationWarning: QBitTorrentSettings 使用旧方式初始化 "
                f"(host={host}, port={port}),这违反了项目规范(CL-16)。"
                "请改为传入缓存中的客户端: QBitTorrentSettings(client=cached_client)"
            )

            # 验证必需参数
            if port is None:
                raise ConfigurationError(
                    message="旧方式初始化必须提供 port 参数",
                    parameter_name="port",
                    parameter_value=None
                )

            self._client = None
            self._from_cache = False
            self.host = host
            self.port = port
            self.username = username
            self.password = password
            self.timeout = timeout
            self._init_failed = False  # 标记初始化是否失败,避免重复尝试
            return

        # 参数不完整
        raise ConfigurationError(
            message="初始化参数不完整: 必须提供 client 或 host+port",
            parameter_name="client",
            parameter_value=None
        )

    @property
    def client(self) -> Client:
        """获取qBittorrent客户端实例

        - 新方式: 直接返回缓存的客户端
        - 旧方式: 延迟创建新客户端(已废弃)
        """
        # 新方式: 直接返回缓存的客户端
        if self._from_cache:
            return self._client

        # 旧方式: 延迟创建客户端(已废弃)
        if self._init_failed:
            raise DownloaderConnectionError(
                message="客户端初始化失败,无法重试。请检查配置后重新创建对象。",
                host=self.host,
                port=self.port
            )
        if self._client is None:
            try:
                self._client = Client(
                    host=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    VERIFY_WEBUI_CERTIFICATE=False,  # 跳过WebUI证书验证
                    REQUESTS_ARGS={'timeout': self.timeout}
                )
                if should_sanitize():
                    logger.info(f"qBittorrent客户端初始化成功(旧方式): {sanitize_ip(self.host)}:{self.port}")
                else:
                    logger.info(f"qBittorrent客户端初始化成功(旧方式): {self.host}:{self.port}")




            except Exception as e:
                self._init_failed = True  # 标记初始化失败
                logger.error(f"qBittorrent客户端初始化失败: {e}")
                raise DownloaderConnectionError(
                    message=f"初始化qBittorrent客户端失败: {e}",
                    host=self.host,
                    port=self.port,
                    original_error=e
                )
        return self._client

    def set_transfer_speed(
        self,
        dl_limit: int,
        ul_limit: int,
        dl_unit: str = "KB/s",
        ul_unit: str = "KB/s"
    ) -> bool:
        """
        设置传输速度限制（支持分别的下载和上传单位）

        Args:
            dl_limit: 下载速度限制（0表示不限速）
            ul_limit: 上传速度限制（0表示不限速）
            dl_unit: 下载速度单位（"KB/s"或"MB/s"）
            ul_unit: 上传速度单位（"KB/s"或"MB/s"）

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            ConfigurationError: 参数验证失败
            APIError: API调用失败
        """
        try:
            # 验证参数
            if dl_limit < 0:
                raise ConfigurationError(
                    message="下载速度限制不能为负数",
                    parameter_name="dl_limit",
                    parameter_value=dl_limit
                )
            if ul_limit < 0:
                raise ConfigurationError(
                    message="上传速度限制不能为负数",
                    parameter_name="ul_limit",
                    parameter_value=ul_limit
                )
            if dl_unit not in ["KB/s", "MB/s"]:
                raise ConfigurationError(
                    message=f"不支持的下载速度单位: {dl_unit}",
                    parameter_name="dl_unit",
                    parameter_value=dl_unit
                )
            if ul_unit not in ["KB/s", "MB/s"]:
                raise ConfigurationError(
                    message=f"不支持的上传速度单位: {ul_unit}",
                    parameter_name="ul_unit",
                    parameter_value=ul_unit
                )

            # 转换单位为Bytes/s (qBittorrent使用Bytes/s)
            dl_limit_bytes = self._convert_speed_to_bytes(dl_limit, dl_unit)
            ul_limit_bytes = self._convert_speed_to_bytes(ul_limit, ul_unit)

            # 调用qBittorrent API
            prefs = {
                "dl_limit": dl_limit_bytes,
                "up_limit": ul_limit_bytes,
            }
            self.client.app_set_preferences(prefs=prefs)

            logger.info(
                f"qBittorrent速度设置成功: "
                f"dl={dl_limit} {dl_unit}, ul={ul_limit} {ul_unit}"
            )
            return True

        except ConfigurationError:
            raise
        except (QBLoginFailed, HTTP401Error) as e:
            raise AuthenticationError(
                message="qBittorrent认证失败",
                username=self.username,
                original_error=e
            )
        except QBAPIConnectionError as e:
            raise DownloaderConnectionError(
                message="qBittorrent连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"qBittorrent速度设置失败: {e}",
                api_method="app_set_preferences",
                original_error=e
            )

    def set_authentication(self, username: str, password: str) -> bool:
        """
        设置认证信息

        ⚠️ 注意: qBittorrent Web API不支持通过API修改认证信息
        此方法仅用于验证，实际修改需要在WebUI或配置文件中操作

        Args:
            username: 用户名
            password: 密码

        Returns:
            bool: 暂不支持，返回False
        """
        logger.warning(
            "qBittorrent Web API不支持通过API修改认证信息。"
            "请在WebUI或配置文件中手动修改。"
        )
        return False

    def set_connection_limits(
        self,
        global_limit: int,
        per_torrent_limit: int
    ) -> bool:
        """
        设置连接数限制

        ⚠️ 【已废弃】此方法已废弃，不再推荐使用
        原因: 作为高级设置功能的一部分，前端UI已隐藏
        保留仅为向后兼容，未来版本将移除

        Args:
            global_limit: 全局最大连接数
            per_torrent_limit: 每个torrent最大连接数

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            ConfigurationError: 参数验证失败
            APIError: API调用失败
        """
        try:
            # 验证参数
            if global_limit < 0:
                raise ConfigurationError(
                    message="全局连接数不能为负数",
                    parameter_name="global_limit",
                    parameter_value=global_limit
                )
            if per_torrent_limit < 0:
                raise ConfigurationError(
                    message="每任务连接数不能为负数",
                    parameter_name="per_torrent_limit",
                    parameter_value=per_torrent_limit
                )

            # 调用qBittorrent API
            prefs = {
                "connection_limit": global_limit,
                "max_connec_per_torrent": per_torrent_limit,
            }
            self.client.app_set_preferences(prefs=prefs)

            logger.info(
                f"qBittorrent连接数设置成功: "
                f"global={global_limit}, per_torrent={per_torrent_limit}"
            )
            return True

        except ConfigurationError:
            raise
        except (QBLoginFailed, HTTP401Error) as e:
            raise AuthenticationError(
                message="qBittorrent认证失败",
                username=self.username,
                original_error=e
            )
        except QBAPIConnectionError as e:
            raise DownloaderConnectionError(
                message="qBittorrent连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"qBittorrent连接数设置失败: {e}",
                api_method="app_set_preferences",
                original_error=e
            )

    def set_queue_settings(
        self,
        max_active_downloads: int,
        max_active_uploads: int,
        dl_queue_size: int,
        ul_queue_size: int
    ) -> bool:
        """
        设置队列管理

        ⚠️ 【已废弃】此方法已废弃，不再推荐使用
        原因: 作为高级设置功能的一部分，前端UI已隐藏
        保留仅为向后兼容，未来版本将移除

        Args:
            max_active_downloads: 同时下载任务数
            max_active_uploads: 同时上传任务数
            dl_queue_size: 下载队列大小
            ul_queue_size: 上传队列大小

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            ConfigurationError: 参数验证失败
            APIError: API调用失败
        """
        try:
            # 验证参数
            if max_active_downloads < 0:
                raise ConfigurationError(
                    message="同时下载数不能为负数",
                    parameter_name="max_active_downloads",
                    parameter_value=max_active_downloads
                )
            if max_active_uploads < 0:
                raise ConfigurationError(
                    message="同时上传数不能为负数",
                    parameter_name="max_active_uploads",
                    parameter_value=max_active_uploads
                )

            # 调用qBittorrent API
            prefs = {
                "queueing_enabled": True,
                "dl_queue_track": True,
                "ul_queue_track": True,
                "max_active_downloads": max_active_downloads,
                "max_active_uploads": max_active_uploads,
                "dl_queue_size": dl_queue_size,
                "ul_queue_size": ul_queue_size,
            }
            self.client.app_set_preferences(prefs=prefs)

            logger.info(
                f"qBittorrent队列设置成功: "
                f"downloads={max_active_downloads}, uploads={max_active_uploads}"
            )
            return True

        except ConfigurationError:
            raise
        except (QBLoginFailed, HTTP401Error) as e:
            raise AuthenticationError(
                message="qBittorrent认证失败",
                username=self.username,
                original_error=e
            )
        except QBAPIConnectionError as e:
            raise DownloaderConnectionError(
                message="qBittorrent连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"qBittorrent队列设置失败: {e}",
                api_method="app_set_preferences",
                original_error=e
            )

    def set_all_settings(self, settings: Dict) -> bool:
        """
        批量应用所有设置

        Args:
            settings: 设置字典，包含所有配置项

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            APIError: API调用失败
        """
        try:
            # 转换速度单位
            prefs = {}

            # 速度限制（支持分别的下载和上传单位）
            if "dl_speed_limit" in settings:
                dl_limit = settings["dl_speed_limit"]
                # 优先使用新的 dl_speed_unit，回退到旧的 speed_unit
                dl_unit = settings.get("dl_speed_unit") or settings.get("speed_unit", "KB/s")
                prefs["dl_limit"] = self._convert_speed_to_bytes(dl_limit, dl_unit)

            if "ul_speed_limit" in settings:
                ul_limit = settings["ul_speed_limit"]
                # 优先使用新的 ul_speed_unit，回退到旧的 speed_unit
                ul_unit = settings.get("ul_speed_unit") or settings.get("speed_unit", "KB/s")
                prefs["up_limit"] = self._convert_speed_to_bytes(ul_limit, ul_unit)

            # 连接限制
            if "connection_limit" in settings:
                prefs["connection_limit"] = settings["connection_limit"]
            if "max_connec_per_torrent" in settings:
                prefs["max_connec_per_torrent"] = settings["max_connec_per_torrent"]

            # 队列设置
            if "max_active_downloads" in settings:
                prefs["max_active_downloads"] = settings["max_active_downloads"]
            if "max_active_uploads" in settings:
                prefs["max_active_uploads"] = settings["max_active_uploads"]
            if "dl_queue_size" in settings:
                prefs["dl_queue_size"] = settings["dl_queue_size"]
            if "ul_queue_size" in settings:
                prefs["ul_queue_size"] = settings["ul_queue_size"]

            # 启用队列
            prefs["queueing_enabled"] = True
            prefs["dl_queue_track"] = True
            prefs["ul_queue_track"] = True

            # 调用API
            if prefs:
                self.client.app_set_preferences(prefs=prefs)
                logger.info(f"qBittorrent批量设置成功: {len(prefs)}项配置")

            return True

        except (QBLoginFailed, HTTP401Error) as e:
            raise AuthenticationError(
                message="qBittorrent认证失败",
                username=self.username,
                original_error=e
            )
        except QBAPIConnectionError as e:
            raise DownloaderConnectionError(
                message="qBittorrent连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"qBittorrent批量设置失败: {e}",
                api_method="app_set_preferences",
                original_error=e
            )

    def get_capabilities(self) -> Dict[str, bool]:
        """
        获取下载器支持的功能列表

        Returns:
            Dict[str, bool]: 功能支持字典
        """
        try:
            # 尝试获取当前偏好设置以验证连接
            prefs = self.client.app_preferences()
            version = self.client.app_version()

            return {
                "transfer_speed": True,
                "authentication": True,
                "connection_limits": "connection_limit" in prefs,
                "queue_settings": "queueing_enabled" in prefs,
                "schedule_speed": True,  # ✅ 应用层实现分时段限速（定时调用全局速度限制接口）
                "download_paths": False,  # qBittorrent不支持路径设置
                "port_settings": True,
                "advanced_settings": True,
                "version": version
            }
        except Exception as e:
            # 下载器离线时降级为WARNING，避免干扰用户
            logger.warning(f"获取qBittorrent能力失败（下载器可能离线）: {e}")
            return {}

    def test_connection(self) -> bool:
        """
        测试连接和配置有效性

        Returns:
            bool: 连接成功返回True，失败返回False
        """
        try:
            # 1. 测试连接
            version = self.client.app_version()
            if not version:
                logger.error(f"qBittorrent版本获取失败: {self.host}:{self.port}")
                return False
            logger.info(f"qBittorrent版本: {version}")

            # 2. 测试认证
            self.client.auth_log_in()
            logger.info(f"qBittorrent认证成功: {self.username}")

            # 3. 测试基本功能
            torrents = self.client.torrents_info(limit=1)
            logger.info(f"qBittorrent基本功能正常")

            return True

        except QBLoginFailed:
            logger.error(f"qBittorrent认证失败: {self.username}")
            return False
        except QBAPIConnectionError:
            logger.error(f"qBittorrent连接失败: {self.host}:{self.port}")
            return False
        except Exception as e:
            logger.error(f"qBittorrent连接测试失败: {e}")
            return False

    def _convert_speed_to_bytes(self, value: int, unit: str) -> int:
        """
        将速度转换为Bytes/s

        Args:
            value: 速度值
            unit: 单位 ("KB/s", "MB/s")

        Returns:
            int: Bytes/s

        Raises:
            ConfigurationError: 单位无效
        """
        if unit == "MB/s":
            return value * 1024 * 1024
        elif unit == "KB/s":
            return value * 1024
        else:
            raise ConfigurationError(
                message=f"不支持的速度单位: {unit}",
                parameter_name="unit",
                parameter_value=unit
            )


__all__ = ['QBitTorrentSettings']
