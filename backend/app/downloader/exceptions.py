# -*- coding: utf-8 -*-
"""
下载器设置管理自定义异常类

用于统一处理下载器设置相关的错误
"""

from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DownloaderSettingsError(Exception):
    """下载器设置管理基础异常类

    所有下载器设置相关异常的基类
    """

    def __init__(self, message: str, downloader_id: Optional[str] = None, details: Optional[dict] = None):
        """
        初始化异常

        Args:
            message: 错误消息（面向用户）
            downloader_id: 下载器ID（可选）
            details: 详细信息（可选，仅记录日志，不暴露给用户）
        """
        self.message = message
        self.downloader_id = downloader_id
        self.details = details or {}

        # ✅ 修复：构建用户友好的错误消息（不包含内部详情）
        user_message = message
        if downloader_id:
            user_message = f"[下载器 {downloader_id}] {message}"

        # ✅ 详情仅记录在日志中，不暴露给用户
        if details:
            logger.debug(f"详细错误信息: {details}")

        super().__init__(user_message)

        # 记录日志（包含完整信息）
        full_log_message = user_message
        if details:
            full_log_message += f" - 详情: {details}"
        logger.error(full_log_message)


class DownloaderConnectionError(DownloaderSettingsError):
    """下载器连接错误

    无法连接到下载器时抛出
    """

    def __init__(
        self,
        message: str = "无法连接到下载器",
        downloader_id: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        details: Dict[str, Any] = {}
        if host:
            details["host"] = host
        if port:
            details["port"] = port
        if original_error:
            details["original_error"] = str(original_error)

        super().__init__(message, downloader_id, details)


class AuthenticationError(DownloaderSettingsError):
    """认证错误

    用户名或密码错误时抛出
    """

    def __init__(
        self,
        message: str = "认证失败，用户名或密码错误",
        downloader_id: Optional[str] = None,
        username: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details: Dict[str, Any] = {}
        if username:
            details["username"] = username
        if original_error:
            details["original_error"] = str(original_error)

        super().__init__(message, downloader_id, details)


class ConfigurationError(DownloaderSettingsError):
    """配置错误

    配置参数无效或冲突时抛出
    """

    def __init__(
        self,
        message: str,
        downloader_id: Optional[str] = None,
        parameter_name: Optional[str] = None,
        parameter_value: Any = None,
    ):
        details: Dict[str, Any] = {}
        if parameter_name:
            details["parameter_name"] = parameter_name
        if parameter_value is not None:
            details["parameter_value"] = str(parameter_value)

        super().__init__(message, downloader_id, details)


class CapabilityNotSupportedError(DownloaderSettingsError):
    """功能不支持错误

    尝试设置下载器不支持的功能时抛出
    """

    def __init__(
        self,
        message: str,
        downloader_id: Optional[str] = None,
        capability: Optional[str] = None,
        downloader_type: Optional[str] = None,
    ):
        details: Dict[str, Any] = {}
        if capability:
            details["capability"] = capability
        if downloader_type:
            details["downloader_type"] = downloader_type

        super().__init__(message, downloader_id, details)


class APIError(DownloaderSettingsError):
    """API调用错误

    调用下载器API失败时抛出
    """

    def __init__(
        self,
        message: str = "API调用失败",
        downloader_id: Optional[str] = None,
        api_method: Optional[str] = None,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        details: Dict[str, Any] = {}
        if api_method:
            details["api_method"] = api_method
        if status_code:
            details["status_code"] = status_code
        if original_error:
            details["original_error"] = str(original_error)

        super().__init__(message, downloader_id, details)


class DownloaderTimeoutError(DownloaderSettingsError):
    """下载器超时错误

    API调用超时时抛出
    """

    def __init__(
        self,
        message: str = "API调用超时",
        downloader_id: Optional[str] = None,
        timeout: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        details: Dict[str, Any] = {}
        if timeout:
            details["timeout"] = f"{timeout}秒"
        if original_error:
            details["original_error"] = str(original_error)

        super().__init__(message, downloader_id, details)


class ValidationError(DownloaderSettingsError):
    """验证错误

    设置参数验证失败时抛出
    """

    def __init__(self, message: str, downloader_id: Optional[str] = None, validation_errors: Optional[dict] = None):
        details: Dict[str, Any] = {}
        if validation_errors:
            details["validation_errors"] = validation_errors

        super().__init__(message, downloader_id, details)


# 导出所有异常类
__all__ = [
    "DownloaderSettingsError",
    "DownloaderConnectionError",
    "AuthenticationError",
    "ConfigurationError",
    "CapabilityNotSupportedError",
    "APIError",
    "DownloaderTimeoutError",
    "ValidationError",
]
