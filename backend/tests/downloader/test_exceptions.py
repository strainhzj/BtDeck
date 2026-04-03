# -*- coding: utf-8 -*-
"""
下载器异常类单元测试

目标模块: app/downloader/exceptions.py
覆盖所有异常类:
  DownloaderSettingsError / DownloaderConnectionError / AuthenticationError
  ConfigurationError / CapabilityNotSupportedError / APIError
  DownloaderTimeoutError / ValidationError
"""

import pytest

from app.downloader.exceptions import (
    DownloaderSettingsError,
    DownloaderConnectionError,
    AuthenticationError,
    ConfigurationError,
    CapabilityNotSupportedError,
    APIError,
    DownloaderTimeoutError,
    ValidationError,
)


# ══════════════════════════════════════════════════════════════
# DownloaderSettingsError（基类）
# ══════════════════════════════════════════════════════════════
class TestDownloaderSettingsError:
    """DownloaderSettingsError 基类测试组"""

    def test_仅message时异常信息正确(self):
        err = DownloaderSettingsError("出错了")
        assert str(err) == "出错了"
        assert err.message == "出错了"
        assert err.downloader_id is None
        assert err.details == {}

    def test_带downloader_id时消息包含前缀(self):
        err = DownloaderSettingsError("连接失败", downloader_id="dl-001")
        assert "[下载器 dl-001]" in str(err)
        assert "连接失败" in str(err)

    def test_带details时不暴露给用户消息(self):
        """details 不应出现在 str(err) 中"""
        err = DownloaderSettingsError("错误", details={"host": "1.2.3.4"})
        assert "host" not in str(err)
        assert err.details == {"host": "1.2.3.4"}

    def test_details默认为空字典(self):
        err = DownloaderSettingsError("测试")
        assert err.details == {}

    def test_继承自Exception(self):
        err = DownloaderSettingsError("测试")
        assert isinstance(err, Exception)

    def test_可以被try_except捕获(self):
        with pytest.raises(DownloaderSettingsError) as exc_info:
            raise DownloaderSettingsError("捕获测试")
        assert "捕获测试" in str(exc_info.value)


# ══════════════════════════════════════════════════════════════
# DownloaderConnectionError
# ══════════════════════════════════════════════════════════════
class TestDownloaderConnectionError:
    """DownloaderConnectionError 测试组"""

    def test_默认消息(self):
        err = DownloaderConnectionError()
        assert "无法连接到下载器" in str(err)

    def test_继承自基类(self):
        err = DownloaderConnectionError()
        assert isinstance(err, DownloaderSettingsError)

    def test_带host和port时details正确(self):
        err = DownloaderConnectionError(host="192.168.1.1", port=8080)
        assert err.details["host"] == "192.168.1.1"
        assert err.details["port"] == 8080

    def test_带original_error时details包含错误信息(self):
        original = ValueError("connection refused")
        err = DownloaderConnectionError(original_error=original)
        assert "connection refused" in err.details["original_error"]

    def test_带downloader_id时消息包含前缀(self):
        err = DownloaderConnectionError(downloader_id="dl-002")
        assert "[下载器 dl-002]" in str(err)

    def test_可选参数为None时不加入details(self):
        err = DownloaderConnectionError()
        assert "host" not in err.details
        assert "port" not in err.details
        assert "original_error" not in err.details


# ══════════════════════════════════════════════════════════════
# AuthenticationError
# ══════════════════════════════════════════════════════════════
class TestAuthenticationError:
    """AuthenticationError 测试组"""

    def test_默认消息(self):
        err = AuthenticationError()
        assert "认证失败" in str(err)

    def test_继承自基类(self):
        assert issubclass(AuthenticationError, DownloaderSettingsError)

    def test_带username时details正确(self):
        err = AuthenticationError(username="admin")
        assert err.details["username"] == "admin"

    def test_带original_error时details包含错误信息(self):
        original = RuntimeError("timeout")
        err = AuthenticationError(original_error=original)
        assert "timeout" in err.details["original_error"]

    def test_可选参数为None时不加入details(self):
        err = AuthenticationError()
        assert "username" not in err.details
        assert "original_error" not in err.details

    def test_自定义消息(self):
        err = AuthenticationError("密码过期")
        assert "密码过期" in str(err)


# ══════════════════════════════════════════════════════════════
# ConfigurationError
# ══════════════════════════════════════════════════════════════
class TestConfigurationError:
    """ConfigurationError 测试组"""

    def test_必填message(self):
        err = ConfigurationError("端口范围无效")
        assert "端口范围无效" in str(err)

    def test_继承自基类(self):
        assert issubclass(ConfigurationError, DownloaderSettingsError)

    def test_带parameter_name时details正确(self):
        err = ConfigurationError("参数错误", parameter_name="port")
        assert err.details["parameter_name"] == "port"

    def test_带parameter_value时details正确(self):
        err = ConfigurationError("参数错误", parameter_value=-1)
        assert err.details["parameter_value"] == "-1"

    def test_parameter_value为None时不加入details(self):
        """parameter_value 为 None 时不应加入 details（使用 is not None 判断）"""
        err = ConfigurationError("测试", parameter_value=None)
        assert "parameter_value" not in err.details

    def test_parameter_value为0时加入details(self):
        """parameter_value 为 0 是合法值，应加入 details"""
        err = ConfigurationError("测试", parameter_value=0)
        assert err.details["parameter_value"] == "0"


# ══════════════════════════════════════════════════════════════
# CapabilityNotSupportedError
# ══════════════════════════════════════════════════════════════
class TestCapabilityNotSupportedError:
    """CapabilityNotSupportedError 测试组"""

    def test_基本消息(self):
        err = CapabilityNotSupportedError("不支持此功能")
        assert "不支持此功能" in str(err)

    def test_继承自基类(self):
        assert issubclass(CapabilityNotSupportedError, DownloaderSettingsError)

    def test_带capability时details正确(self):
        err = CapabilityNotSupportedError("不支持", capability="super_seeding")
        assert err.details["capability"] == "super_seeding"

    def test_带downloader_type时details正确(self):
        err = CapabilityNotSupportedError("不支持", downloader_type="transmission")
        assert err.details["downloader_type"] == "transmission"

    def test_全部可选参数为None时details为空(self):
        err = CapabilityNotSupportedError("测试")
        assert err.details == {}


# ══════════════════════════════════════════════════════════════
# APIError
# ══════════════════════════════════════════════════════════════
class TestAPIError:
    """APIError 测试组"""

    def test_默认消息(self):
        err = APIError()
        assert "API调用失败" in str(err)

    def test_继承自基类(self):
        assert issubclass(APIError, DownloaderSettingsError)

    def test_带api_method时details正确(self):
        err = APIError(api_method="torrents_info")
        assert err.details["api_method"] == "torrents_info"

    def test_带status_code时details正确(self):
        err = APIError(status_code=403)
        assert err.details["status_code"] == 403

    def test_带original_error时details包含错误信息(self):
        original = ConnectionResetError("reset")
        err = APIError(original_error=original)
        assert "reset" in err.details["original_error"]

    def test_自定义消息覆盖默认(self):
        err = APIError("请求被拒绝")
        assert "请求被拒绝" in str(err)


# ══════════════════════════════════════════════════════════════
# DownloaderTimeoutError
# ══════════════════════════════════════════════════════════════
class TestDownloaderTimeoutError:
    """DownloaderTimeoutError 测试组"""

    def test_默认消息(self):
        err = DownloaderTimeoutError()
        assert "API调用超时" in str(err)

    def test_继承自基类(self):
        assert issubclass(DownloaderTimeoutError, DownloaderSettingsError)

    def test_带timeout时details包含秒数(self):
        err = DownloaderTimeoutError(timeout=30)
        assert err.details["timeout"] == "30秒"

    def test_timeout为0时不加入details(self):
        """timeout 为 0（falsy）时不应加入 details"""
        err = DownloaderTimeoutError(timeout=0)
        assert "timeout" not in err.details

    def test_带original_error时details包含错误信息(self):
        original = TimeoutError("read timeout")
        err = DownloaderTimeoutError(original_error=original)
        assert "read timeout" in err.details["original_error"]


# ══════════════════════════════════════════════════════════════
# ValidationError
# ══════════════════════════════════════════════════════════════
class TestValidationError:
    """ValidationError 测试组"""

    def test_基本消息(self):
        err = ValidationError("验证失败")
        assert "验证失败" in str(err)

    def test_继承自基类(self):
        assert issubclass(ValidationError, DownloaderSettingsError)

    def test_带validation_errors时details正确(self):
        errors = {"port": "必须为数字", "host": "不能为空"}
        err = ValidationError("验证失败", validation_errors=errors)
        assert err.details["validation_errors"] == errors

    def test_validation_errors为None时details为空(self):
        err = ValidationError("测试")
        assert err.details == {}

    def test_validation_errors为空字典时details为空(self):
        """空字典是 falsy，不会加入 details"""
        err = ValidationError("测试", validation_errors={})
        assert err.details == {}


# ══════════════════════════════════════════════════════════════
# __all__ 导出完整性
# ══════════════════════════════════════════════════════════════
class TestExceptionsAllExport:
    """__all__ 导出完整性测试"""

    def test_all导出8个异常类(self):
        from app.downloader import exceptions as exc_mod
        assert len(exc_mod.__all__) == 8

    @pytest.mark.parametrize(
        "name",
        [
            "DownloaderSettingsError",
            "DownloaderConnectionError",
            "AuthenticationError",
            "ConfigurationError",
            "CapabilityNotSupportedError",
            "APIError",
            "DownloaderTimeoutError",
            "ValidationError",
        ],
    )
    def test_all中每个名称均可导入(self, name):
        from app.downloader import exceptions as exc_mod
        cls = getattr(exc_mod, name)
        assert issubclass(cls, Exception)
