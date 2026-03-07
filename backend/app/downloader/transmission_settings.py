# -*- coding: utf-8 -*-
"""
Transmission设置封装类

封装Transmission RPC调用，提供统一的设置接口
"""
from typing import Dict, Optional, Tuple, Union, Any
from transmission_rpc import Client
from transmission_rpc import (
    TransmissionAuthError as TrAuthError,
    TransmissionConnectError as TrConnectError,
    TransmissionTimeoutError as TrTimeoutError,
    TransmissionError,
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


class TransmissionSettings:
    """Transmission设置封装类

    提供Transmission下载器的设置管理功能
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
        初始化Transmission设置封装类

        双模式初始化(兼容旧代码,但强烈建议使用新方式):

        新方式(推荐):
            TransmissionSettings(client=cached_client)
            - 直接使用缓存中的客户端连接
            - 不创建新连接,避免资源浪费
            - 符合项目规范(CL-16)

        旧方式(已废弃,会触发警告):
            TransmissionSettings(host=..., port=..., username=..., password=...)
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
            logger.debug("TransmissionSettings 使用缓存客户端初始化(推荐方式)")
            return

        # 旧方式: 从连接参数创建客户端(已废弃)
        if client is None and host is not None:
            # 记录废弃警告
            logger.warning(
                "DeprecationWarning: TransmissionSettings 使用旧方式初始化 "
                f"(host={host}, port={port}),这违反了项目规范(CL-16)。"
                "请改为传入缓存中的客户端: TransmissionSettings(client=cached_client)"
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
        """获取Transmission客户端实例

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
                    timeout=self.timeout
                )
                if should_sanitize():
                    logger.info(f"Transmission客户端初始化成功(旧方式): {sanitize_ip(self.host)}:{self.port}")
                else:
                    logger.info(f"Transmission客户端初始化成功(旧方式): {self.host}:{self.port}")
            except Exception as e:
                self._init_failed = True  # 标记初始化失败
                logger.error(f"Transmission客户端初始化失败: {e}")
                raise DownloaderConnectionError(
                    message=f"初始化Transmission客户端失败: {e}",
                    host=self.host,
                    port=self.port,
                    original_error=e
                )
        return self._client

    def set_transfer_speed(
        self,
        dl_limit: int,
        ul_limit: int,
        unit: str = "KB/s"
    ) -> bool:
        """
        设置传输速度限制

        Args:
            dl_limit: 下载速度限制（0表示不限速）
            ul_limit: 上传速度限制（0表示不限速）
            unit: 速度单位（"KB/s"或"MB/s"）

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
            if unit not in ["KB/s", "MB/s"]:
                raise ConfigurationError(
                    message=f"不支持的速度单位: {unit}",
                    parameter_name="unit",
                    parameter_value=unit
                )

            # 转换单位为KB/s (Transmission使用KB/s)
            dl_limit_kb = self._convert_speed_to_kilobytes(dl_limit, unit)
            ul_limit_kb = self._convert_speed_to_kilobytes(ul_limit, unit)

            # 调用Transmission RPC
            # 注意：Transmission需要设置 *_enabled=True 才能启用限速
            self.client.set_session(
                speed_limit_down=dl_limit_kb,
                speed_limit_up=ul_limit_kb,
                speed_limit_down_enabled=(dl_limit > 0),
                speed_limit_up_enabled=(ul_limit > 0)
            )

            logger.info(
                f"Transmission速度设置成功: "
                f"dl={dl_limit} {unit}, ul={ul_limit} {unit}"
            )
            return True

        except ConfigurationError:
            raise
        except TrTimeoutError as e:
            raise DownloaderTimeoutError(
                message="Transmission连接超时",
                timeout=self.timeout,
                original_error=e
            )
        except TrAuthError as e:
            raise AuthenticationError(
                message="Transmission认证失败",
                username=self.username,
                original_error=e
            )
        except TrConnectError as e:
            raise DownloaderConnectionError(
                message="Transmission连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"Transmission速度设置失败: {e}",
                api_method="set_session",
                original_error=e
            )

    def set_authentication(self, username: str, password: str) -> bool:
        """
        设置认证信息

        ⚠️ 注意: Transmission RPC不支持通过RPC修改认证信息
        此方法仅用于验证，实际修改需要在配置文件中操作

        Args:
            username: 用户名
            password: 密码

        Returns:
            bool: 暂不支持，返回False
        """
        logger.warning(
            "Transmission RPC不支持通过RPC修改认证信息。"
            "请在配置文件中手动修改。"
        )
        return False

    def set_download_paths(
        self,
        download_path: str,
        incomplete_path: Optional[str] = None
    ) -> bool:
        """
        设置下载目录

        Args:
            download_path: 下载目录路径
            incomplete_path: 未完成文件目录路径（可选）

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            ConfigurationError: 参数验证失败
            APIError: RPC调用失败
        """
        try:
            # 验证参数
            if not download_path:
                raise ConfigurationError(
                    message="下载目录不能为空",
                    parameter_name="download_path"
                )

            # 调用Transmission RPC
            kwargs = {
                "download_dir": download_path
            }

            if incomplete_path:
                kwargs["incomplete_dir_enabled"] = True
                kwargs["incomplete_dir"] = incomplete_path
            else:
                kwargs["incomplete_dir_enabled"] = False

            self.client.set_session(**kwargs)

            logger.info(
                f"Transmission下载目录设置成功: "
                f"download={download_path}, incomplete={incomplete_path}"
            )
            return True

        except ConfigurationError:
            raise
        except TrTimeoutError as e:
            raise DownloaderTimeoutError(
                message=f"{self.__class__.__name__}连接超时",
                timeout=self.timeout,
                original_error=e
            )
        except TrAuthError as e:
            raise AuthenticationError(
                message="Transmission认证失败",
                username=self.username,
                original_error=e
            )
        except TrConnectError as e:
            raise DownloaderConnectionError(
                message="Transmission连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"Transmission下载目录设置失败: {e}",
                api_method="set_session",
                original_error=e
            )

    def set_port_settings(
        self,
        peer_port: int,
        port_forwarding: bool = True
    ) -> bool:
        """
        设置端口设置

        Args:
            peer_port: 监听端口
            port_forwarding: 是否启用端口转发

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            ConfigurationError: 参数验证失败
            APIError: RPC调用失败
        """
        try:
            # 验证参数
            if peer_port < 0 or peer_port > 65535:
                raise ConfigurationError(
                    message=f"端口号必须在0-65535之间: {peer_port}",
                    parameter_name="peer_port",
                    parameter_value=peer_port
                )

            # 调用Transmission RPC
            self.client.set_session(
                peer_port=peer_port,
                peer_port_random_on_start=False,
                port_forwarding_enabled=port_forwarding
            )

            logger.info(
                f"Transmission端口设置成功: "
                f"port={peer_port}, forwarding={port_forwarding}"
            )
            return True

        except ConfigurationError:
            raise
        except TrTimeoutError as e:
            raise DownloaderTimeoutError(
                message=f"{self.__class__.__name__}连接超时",
                timeout=self.timeout,
                original_error=e
            )
        except TrAuthError as e:
            raise AuthenticationError(
                message="Transmission认证失败",
                username=self.username,
                original_error=e
            )
        except TrConnectError as e:
            raise DownloaderConnectionError(
                message="Transmission连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"Transmission端口设置失败: {e}",
                api_method="set_session",
                original_error=e
            )

    def set_connection_limits(
        self,
        global_limit: int,
        peer_limit: int
    ) -> bool:
        """
        设置连接数和Peer限制

        Args:
            global_limit: 全局最大连接数
            peer_limit: 每个torrent最大Peer数

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            ConfigurationError: 参数验证失败
            APIError: RPC调用失败
        """
        try:
            # 验证参数
            if global_limit < 0:
                raise ConfigurationError(
                    message="全局连接数不能为负数",
                    parameter_name="global_limit",
                    parameter_value=global_limit
                )
            if peer_limit < 0:
                raise ConfigurationError(
                    message="每任务Peer数不能为负数",
                    parameter_name="peer_limit",
                    parameter_value=peer_limit
                )

            # 调用Transmission RPC
            self.client.set_session(
                peer_limit_global=global_limit,
                peer_limit_per_torrent=peer_limit
            )

            logger.info(
                f"Transmission连接数设置成功: "
                f"global={global_limit}, peer={peer_limit}"
            )
            return True

        except ConfigurationError:
            raise
        except TrTimeoutError as e:
            raise DownloaderTimeoutError(
                message=f"{self.__class__.__name__}连接超时",
                timeout=self.timeout,
                original_error=e
            )
        except TrAuthError as e:
            raise AuthenticationError(
                message="Transmission认证失败",
                username=self.username,
                original_error=e
            )
        except TrConnectError as e:
            raise DownloaderConnectionError(
                message="Transmission连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"Transmission连接数设置失败: {e}",
                api_method="set_session",
                original_error=e
            )

    def set_speed_schedule(self, schedule_dict: Dict) -> bool:
        """
        设置速度时间表

        ⚠️ 注意: 此方法为接口预留，实际分时段功能通过alt_speed实现
        具体应用在T4（模板系统）中实现

        Args:
            schedule_dict: 时间表配置

        Returns:
            bool: 暂不实现，返回False
        """
        logger.info(
            "Transmission分时段速度设置功能将在T4（模板系统）中实现。"
            "当前支持通过alt_speed实现日间/夜间模式切换。"
        )
        return False

    def set_all_settings(self, settings: Dict) -> bool:
        """
        批量应用所有设置

        Args:
            settings: 设置字典，包含所有配置项

        Returns:
            bool: 设置成功返回True，失败返回False

        Raises:
            APIError: RPC调用失败
        """
        try:
            # 转换参数
            kwargs = {}

            # 速度限制 (Transmission使用KB/s，支持分别的下载和上传单位)
            if "dl_speed_limit" in settings:
                dl_limit = settings["dl_speed_limit"]
                # 优先使用新的 dl_speed_unit，回退到旧的 speed_unit
                dl_unit = settings.get("dl_speed_unit") or settings.get("speed_unit", "KB/s")
                dl_limit_kb = self._convert_speed_to_kilobytes(dl_limit, dl_unit)
                kwargs["speed_limit_down"] = dl_limit_kb
                kwargs["speed_limit_down_enabled"] = (dl_limit > 0)

            if "ul_speed_limit" in settings:
                ul_limit = settings["ul_speed_limit"]
                # 优先使用新的 ul_speed_unit，回退到旧的 speed_unit
                ul_unit = settings.get("ul_speed_unit") or settings.get("speed_unit", "KB/s")
                ul_limit_kb = self._convert_speed_to_kilobytes(ul_limit, ul_unit)
                kwargs["speed_limit_up"] = ul_limit_kb
                kwargs["speed_limit_up_enabled"] = (ul_limit > 0)

            # 连接限制
            if "peer_limit_global" in settings:
                kwargs["peer_limit_global"] = settings["peer_limit_global"]
            if "peer_limit_per_torrent" in settings:
                kwargs["peer_limit_per_torrent"] = settings["peer_limit_per_torrent"]

            # 下载路径
            if "download_dir" in settings:
                kwargs["download_dir"] = settings["download_dir"]
            if "incomplete_dir" in settings:
                kwargs["incomplete_dir_enabled"] = True
                kwargs["incomplete_dir"] = settings["incomplete_dir"]

            # 端口设置
            if "peer_port" in settings:
                kwargs["peer_port"] = settings["peer_port"]
                kwargs["peer_port_random_on_start"] = False
            if "port_forwarding_enabled" in settings:
                kwargs["port_forwarding_enabled"] = settings["port_forwarding_enabled"]

            # 队列设置
            if "download_queue_enabled" in settings:
                kwargs["download_queue_enabled"] = settings["download_queue_enabled"]
            if "download_queue_size" in settings:
                kwargs["download_queue_size"] = settings["download_queue_size"]
            if "seed_queue_enabled" in settings:
                kwargs["seed_queue_enabled"] = settings["seed_queue_enabled"]
            if "seed_queue_size" in settings:
                kwargs["seed_queue_size"] = settings["seed_queue_size"]

            # 调用RPC
            if kwargs:
                self.client.set_session(**kwargs)
                logger.info(f"Transmission批量设置成功: {len(kwargs)}项配置")

            return True

        except TrAuthError as e:
            raise AuthenticationError(
                message="Transmission认证失败",
                username=self.username,
                original_error=e
            )
        except TrConnectError as e:
            raise DownloaderConnectionError(
                message="Transmission连接失败",
                host=self.host,
                port=self.port,
                original_error=e
            )
        except TrTimeoutError as e:
            raise DownloaderTimeoutError(
                message="Transmission连接超时",
                timeout=self.timeout,
                original_error=e
            )
        except Exception as e:
            raise APIError(
                message=f"Transmission批量设置失败: {e}",
                api_method="set_session",
                original_error=e
            )

    def get_capabilities(self) -> Dict[str, bool]:
        """
        获取下载器支持的功能列表

        Returns:
            Dict[str, bool]: 功能支持字典
        """
        try:
            # 尝试获取会话信息以验证连接
            session = self.client.get_session()

            return {
                "transfer_speed": True,
                "authentication": True,
                "download_paths": True,  # ✅ Transmission支持
                "port_settings": True,  # ✅ Transmission支持
                "connection_limits": hasattr(session, "peer_limit_global"),
                "peer_limits": hasattr(session, "peer_limit_per_torrent"),
                "schedule_speed": True,  # ✅ Transmission支持(应用层定时任务实现)
                "queue_settings": hasattr(session, "download_queue_enabled"),
                "advanced_settings": True,
                "version": getattr(session, 'version', 'unknown')
            }
        except Exception as e:
            # 下载器离线时降级为WARNING，避免干扰用户
            logger.warning(f"获取Transmission能力失败（下载器可能离线）: {e}")
            return {}

    def test_connection(self) -> bool:
        """
        测试连接和配置有效性

        Returns:
            bool: 连接成功返回True，失败返回False
        """
        try:
            # 1. 测试连接
            session = self.client.get_session()
            if not session:
                logger.error(f"Transmission会话获取失败: {self.host}:{self.port}")
                return False
            logger.info(f"Transmission版本: {getattr(session, 'version', 'unknown')}")

            # 2. 测试基本功能
            torrents = self.client.get_torrents()
            logger.info(f"Transmission基本功能正常")

            return True

        except TrAuthError:
            logger.error(f"Transmission认证失败: {self.username}")
            return False
        except TrConnectError:
            logger.error(f"Transmission连接失败: {self.host}:{self.port}")
            return False
        except TrTimeoutError:
            logger.error(f"Transmission连接超时: {self.host}:{self.port}")
            return False
        except Exception as e:
            logger.error(f"Transmission连接测试失败: {e}")
            return False

    def _convert_speed_to_kilobytes(self, value: int, unit: str) -> int:
        """
        将速度转换为KB/s

        Args:
            value: 速度值
            unit: 单位 ("KB/s", "MB/s")

        Returns:
            int: KB/s

        Raises:
            ConfigurationError: 单位无效
        """
        if unit == "MB/s":
            return value * 1024
        elif unit == "KB/s":
            return value
        else:
            raise ConfigurationError(
                message=f"不支持的速度单位: {unit}",
                parameter_name="unit",
                parameter_value=unit
            )


__all__ = ['TransmissionSettings']
