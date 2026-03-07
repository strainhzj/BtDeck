# -*- coding: utf-8 -*-
"""
下载器设置管理器

统一管理qBittorrent和Transmission下载器的设置

通过创建对应的 Settings 包装类，提供统一的设置管理接口。
"""
from typing import Dict, Optional, Tuple, Any
import logging

from app.downloader.models import BtDownloaders
from app.downloader.exceptions import (
    DownloaderSettingsError,
    ConfigurationError,
    ValidationError,
)
from app.models.setting_templates import DownloaderTypeEnum
from app.utils.log_sanitizer import format_connection_log, should_sanitize

logger = logging.getLogger(__name__)


def _safe_parse_port(port_value: any, downloader_id: str = None) -> int:
    """安全解析端口号，防止panic

    Args:
        port_value: 端口号（可能是字符串、整数或其他类型）
        downloader_id: 下载器ID（用于错误日志）

    Returns:
        int: 解析后的端口号

    Raises:
        ConfigurationError: 端口号无效时抛出
    """
    if port_value is None:
        raise ConfigurationError(
            message="端口号不能为空",
            parameter_name="port",
            parameter_value=None
        )
    try:
        port_int = int(port_value)
        if not (1 <= port_int <= 65535):
            raise ConfigurationError(
                message=f"端口号超出有效范围(1-65535): {port_int}",
                parameter_name="port",
                parameter_value=port_int
            )
        logger.debug(f"端口号解析成功: {port_int} (downloader: {downloader_id})")
        return port_int
    except (ValueError, TypeError):
        raise ConfigurationError(
            message=f"端口号格式无效: {port_value}",
            parameter_name="port",
            parameter_value=port_value
        )


class DownloaderSettingsManager:
    """下载器设置管理器

    使用 app.state.store 缓存中的客户端连接，提供统一的设置管理接口

    强制规范：
    - 严禁直接创建新的客户端连接
    - 必须使用 get_downloader_from_cache() 获取缓存客户端
    - 必须验证缓存连接的 fail_time 状态
    """

    def __init__(self, downloader: BtDownloaders):
        """
        初始化设置管理器

        Args:
            downloader: 下载器模型实例

        Raises:
            ConfigurationError: 下载器类型无效或缓存不可用
            DownloaderSettingsError: 初始化失败
        """
        self.downloader = downloader
        self.settings_wrapper = self._create_settings_wrapper()

    def _normalize_downloader_type(self) -> int:
        """规范化下载器类型为整数

        ⚠️ 方案1修复：支持多种输入格式，解决数据库VARCHAR存储导致的类型不匹配问题

        支持的输入格式：
        - 整数：0, 1
        - 字符串数字："0", "1"
        - 英文名称："qbittorrent", "transmission"
        - 中文名称："qBittorrent", "Transmission"

        Returns:
            int: 规范化后的下载器类型 (0=qBittorrent, 1=Transmission)

        Raises:
            ConfigurationError: 无法识别的下载器类型
        """
        raw_type = self.downloader.downloader_type

        # 如果已经是整数，直接验证并返回
        if isinstance(raw_type, int):
            if raw_type in [0, 1]:
                logger.debug(f"下载器类型为整数: {raw_type}")
                return raw_type
            raise ConfigurationError(
                message=f"无效的下载器类型(整数): {raw_type}",
                parameter_name="downloader_type",
                parameter_value=raw_type
            )

        # 如果是字符串，进行转换
        if isinstance(raw_type, str):
            # 支持字符串数字
            if raw_type in ["0", "1"]:
                normalized = int(raw_type)
                logger.debug(f"下载器类型从字符串数字转换: '{raw_type}' -> {normalized}")
                return normalized

            # 支持英文名称（不区分大小写）
            lower_type = raw_type.lower()
            if lower_type in ["qbittorrent", "qbt"]:
                logger.debug(f"下载器类型从英文名称转换: '{raw_type}' -> 0")
                return 0
            if lower_type in ["transmission", "tr"]:
                logger.debug(f"下载器类型从英文名称转换: '{raw_type}' -> 1")
                return 1

            # 支持中文名称（不区分大小写，支持部分匹配）
            if "qbittorrent" in lower_type or "qbit" in lower_type:
                logger.debug(f"下载器类型从中文名称转换: '{raw_type}' -> 0")
                return 0
            if "transmission" in lower_type or "trans" in lower_type:
                logger.debug(f"下载器类型从中文名称转换: '{raw_type}' -> 1")
                return 1

        # 无法识别的类型
        raise ConfigurationError(
            message=f"不支持的下载器类型: '{raw_type}' (类型: {type(raw_type).__name__})",
            parameter_name="downloader_type",
            parameter_value=raw_type
        )

    def _create_settings_wrapper(self) -> Any:
        """
        根据下载器类型创建对应的 Settings 包装类

        ⚠️ 强制规范: 必须使用 app.state.store 缓存中的客户端连接
        ⚠️ 方案1修复：使用_normalize_downloader_type()方法规范化类型，支持多种格式

        Returns:
            QbittorrentSettings 或 TransmissionSettings 实例

        Raises:
            ConfigurationError: 缓存不可用或下载器离线
        """
        # 🔧 从全局 app 获取缓存中的下载器客户端
        from app.main import app as downloader_app

        # 检查缓存是否可用
        if not hasattr(downloader_app.state, 'store') or downloader_app.state.store is None:
            raise ConfigurationError(
                message="下载器缓存未初始化,请稍后重试",
                parameter_name="store",
                parameter_value=None
            )

        # 从缓存获取下载器列表
        cached_downloaders = downloader_app.state.store.get_snapshot_sync()

        if not cached_downloaders:
            raise ConfigurationError(
                message="下载器缓存为空,请稍后重试",
                parameter_name="store",
                parameter_value=None
            )

        # 根据 downloader_id 查找对应的缓存下载器
        downloader_vo = next(
            (d for d in cached_downloaders if d.downloader_id == self.downloader.downloader_id),
            None
        )

        if not downloader_vo:
            raise ConfigurationError(
                message=f"下载器 {self.downloader.nickname} 未在缓存中找到",
                parameter_name="downloader_id",
                parameter_value=self.downloader.downloader_id
            )

        # 验证缓存连接的 fail_time 状态
        if downloader_vo.fail_time > 0:
            raise ConfigurationError(
                message=f"下载器 {self.downloader.nickname} 不可用 (fail_time={downloader_vo.fail_time})",
                parameter_name="fail_time",
                parameter_value=downloader_vo.fail_time
            )

        # 🔧 方案1修复：使用规范化后的类型进行判断
        normalized_type = self._normalize_downloader_type()

        if normalized_type == 0:  # qBittorrent
            from app.downloader.qbittorrent_settings import QBitTorrentSettings
            # ✅ 使用缓存中的客户端(推荐方式)
            return QBitTorrentSettings(client=downloader_vo.client)

        elif normalized_type == 1:  # Transmission
            from app.downloader.transmission_settings import TransmissionSettings
            # ✅ 使用缓存中的客户端(推荐方式)
            return TransmissionSettings(client=downloader_vo.client)

        else:
            # 理论上不会执行到这里，因为_normalize_downloader_type已经做了验证
            raise ConfigurationError(
                message=f"不支持的下载器类型(规范化后): {normalized_type}",
                parameter_name="downloader_type",
                parameter_value=normalized_type
            )

    def apply_settings(self, settings: Dict) -> bool:
        """
        应用配置到下载器

        Args:
            settings: 配置字典（来自downloader_settings表）

        Returns:
            bool: 应用成功返回True，失败返回False

        Raises:
            DownloaderSettingsError: 应用失败
        """
        try:
            logger.info(
                f"应用配置到下载器: {self.downloader.nickname} "
                f"({self.downloader.downloader_id})"
            )

            # 调用设置包装类的方法
            success = self.settings_wrapper.set_all_settings(settings)

            if success:
                logger.info(f"配置应用成功: {self.downloader.nickname}")
            else:
                logger.warning(f"配置应用失败: {self.downloader.nickname}")

            return success

        except DownloaderSettingsError:
            raise
        except Exception as e:
            logger.error(f"应用配置失败: {e}")
            raise DownloaderSettingsError(
                message=f"应用配置失败: {e}",
                downloader_id=self.downloader.downloader_id
            )

    def get_supported_capabilities(self) -> Dict[str, bool]:
        """
        获取下载器支持的功能列表

        Returns:
            Dict[str, bool]: 功能支持字典
        """
        try:
            capabilities = self.settings_wrapper.get_capabilities()
            logger.info(
                f"获取下载器能力成功: {self.downloader.nickname}, "
                f"支持功能: {list(capabilities.keys())}"
            )
            return capabilities

        except Exception as e:
            logger.error(f"获取下载器能力失败: {e}")
            return {}

    def validate_settings(self, settings: Dict) -> Tuple[bool, str]:
        """
        验证配置有效性

        Args:
            settings: 配置字典

        Returns:
            Tuple[bool, str]: (是否有效, 错误消息)
        """
        validation_errors = {}

        # 基础验证
        try:
            dl_speed_limit = settings.get("dl_speed_limit", 0)
            if not isinstance(dl_speed_limit, int) or dl_speed_limit < 0:
                validation_errors["dl_speed_limit"] = "下载速度限制必须是非负整数"

            ul_speed_limit = settings.get("ul_speed_limit", 0)
            if not isinstance(ul_speed_limit, int) or ul_speed_limit < 0:
                validation_errors["ul_speed_limit"] = "上传速度限制必须是非负整数"

            # 验证下载速度单位（支持新字段 dl_speed_unit，回退到旧字段 speed_unit）
            dl_speed_unit = settings.get("dl_speed_unit") or settings.get("speed_unit", "KB/s")
            if dl_speed_unit not in ["KB/s", "MB/s"]:
                validation_errors["dl_speed_unit"] = "下载速度单位必须是KB/s或MB/s"

            # 验证上传速度单位（支持新字段 ul_speed_unit，回退到旧字段 speed_unit）
            ul_speed_unit = settings.get("ul_speed_unit") or settings.get("speed_unit", "KB/s")
            if ul_speed_unit not in ["KB/s", "MB/s"]:
                validation_errors["ul_speed_unit"] = "上传速度单位必须是KB/s或MB/s"

            # 下载器特定验证
            capabilities = self.get_supported_capabilities()

            # 如果不支持分时段速度，检查相关配置
            if not capabilities.get("schedule_speed", False):
                if settings.get("enable_schedule", False):
                    validation_errors["enable_schedule"] = (
                        f"{self.downloader.downloader_type} 不支持分时段速度限制"
                    )

            # 如果不支持下载路径，检查相关配置
            if not capabilities.get("download_paths", False):
                if settings.get("download_dir"):
                    validation_errors["download_dir"] = (
                        f"{self.downloader.downloader_type} 不支持下载路径设置"
                    )

        except Exception as e:
            return False, f"验证过程出错: {e}"

        if validation_errors:
            error_msg = "; ".join([f"{k}: {v}" for k, v in validation_errors.items()])
            logger.warning(f"配置验证失败: {error_msg}")
            return False, error_msg

        logger.info("配置验证通过")
        return True, ""

    def test_connection(self) -> bool:
        """
        测试下载器连接和配置有效性

        Returns:
            bool: 连接成功返回True，失败返回False
        """
        try:
            logger.info(
                f"测试下载器连接: "
                f"{format_connection_log(self.downloader.nickname, self.downloader.host, self.downloader.port, should_sanitize())}"
            )

            success = self.settings_wrapper.test_connection()

            if success:
                logger.info(f"下载器连接测试成功: {self.downloader.nickname}")
            else:
                logger.error(f"下载器连接测试失败: {self.downloader.nickname}")

            return success

        except Exception as e:
            logger.error(f"下载器连接测试异常: {e}")
            return False

    def create_from_template(
        self,
        template: Dict,
        downloader: BtDownloaders
    ) -> bool:
        """
        从模板创建配置

        Args:
            template: 模板配置字典
            downloader: 下载器实例

        Returns:
            bool: 创建成功返回True，失败返回False

        ⚠️ 注意: 此方法为T4（模板系统）预留接口
        """
        logger.info(
            f"从模板创建配置: {downloader.nickname}, "
            f"模板: {template.get('name', 'unknown')}"
        )

        # 验证模板与下载器兼容性
        if "downloader_type" in template:
            template_type = template["downloader_type"]
            if template_type != downloader.downloader_type:
                logger.warning(
                    f"模板类型({template_type})与下载器类型({downloader.downloader_type})不匹配"
                )
                return False

        # 验证配置
        is_valid, error_msg = self.validate_settings(template)
        if not is_valid:
            logger.error(f"模板配置验证失败: {error_msg}")
            return False

        # 应用配置
        return self.apply_settings(template)

    def get_download_speed(self) -> Optional[int]:
        """
        获取当前下载速度限制

        Returns:
            Optional[int]: 下载速度限制(KB/s)，获取失败返回None
        """
        try:
            capabilities = self.get_supported_capabilities()
            if not capabilities.get("transfer_speed"):
                logger.warning(f"{self.downloader.nickname} 不支持速度查询")
                return None

            # 这里需要调用实际的API获取速度设置
            # 暂时返回None，需要在T3中实现
            logger.info(f"获取下载速度: {self.downloader.nickname} (待实现)")
            return None

        except Exception as e:
            logger.error(f"获取下载速度失败: {e}")
            return None

    def get_upload_speed(self) -> Optional[int]:
        """
        获取当前上传速度限制

        Returns:
            Optional[int]: 上传速度限制(KB/s)，获取失败返回None
        """
        try:
            capabilities = self.get_supported_capabilities()
            if not capabilities.get("transfer_speed"):
                logger.warning(f"{self.downloader.nickname} 不支持速度查询")
                return None

            # 这里需要调用实际的API获取速度设置
            # 暂时返回None，需要在T3中实现
            logger.info(f"获取上传速度: {self.downloader.nickname} (待实现)")
            return None

        except Exception as e:
            logger.error(f"获取上传速度失败: {e}")
            return None


__all__ = ['DownloaderSettingsManager']
