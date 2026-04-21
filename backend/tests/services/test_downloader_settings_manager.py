# -*- coding: utf-8 -*-
"""
DownloaderSettingsManager 的单元测试

测试下载器设置管理服务的核心方法，包括：
- _safe_parse_port: 端口号安全解析（纯函数）
- _normalize_downloader_type: 下载器类型规范化
- validate_settings: 配置有效性验证
- apply_settings / get_supported_capabilities / test_connection
- create_from_template: 从模板创建配置
- get_download_speed / get_upload_speed: 速度查询

所有外部依赖（缓存、客户端连接）通过 mock 隔离。
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.downloader_settings_manager import (
    _safe_parse_port,
    DownloaderSettingsManager,
)
from app.downloader.exceptions import (
    DownloaderSettingsError,
    ConfigurationError,
)


# ==================== 辅助工具 ====================

class _FakeDownloader:
    """轻量级下载器对象，用于替代 SQLAlchemy 模型实例"""
    def __init__(
        self,
        downloader_id="dl-001",
        nickname="测试下载器",
        host="127.0.0.1",
        port="8080",
        downloader_type=0,
    ):
        self.downloader_id = downloader_id
        self.nickname = nickname
        self.host = host
        self.port = port
        self.downloader_type = downloader_type


def make_downloader(**kwargs):
    """创建测试用下载器对象"""
    return _FakeDownloader(**kwargs)


def _create_manager_with_mock_wrapper(downloader=None, wrapper=None, capabilities=None):
    """
    创建 DownloaderSettingsManager 实例，跳过 __init__ 中的 _create_settings_wrapper，
    直接注入 mock 的 settings_wrapper。

    Args:
        downloader: 下载器对象（默认使用 _FakeDownloader）
        wrapper: mock 的 settings_wrapper
        capabilities: 能力字典（如果提供则自动配置 wrapper.get_capabilities）

    Returns:
        DownloaderSettingsManager 实例
    """
    if downloader is None:
        downloader = make_downloader()
    if wrapper is None:
        wrapper = MagicMock()

    if capabilities is not None:
        wrapper.get_capabilities.return_value = capabilities

    manager = DownloaderSettingsManager.__new__(DownloaderSettingsManager)
    manager.downloader = downloader
    manager.settings_wrapper = wrapper
    return manager


# ==================== _safe_parse_port 测试 ====================

class TestSafeParsePort:
    """_safe_parse_port 端口号安全解析测试"""

    def test_正常整数端口(self):
        """有效整数端口号应正常返回"""
        assert _safe_parse_port(8080) == 8080

    def test_字符串数字端口(self):
        """字符串格式的数字端口应被正确解析"""
        assert _safe_parse_port("9090") == 9090

    def test_最小边界端口1(self):
        """端口号最小有效值 1 应正常返回"""
        assert _safe_parse_port(1) == 1

    def test_最大边界端口65535(self):
        """端口号最大有效值 65535 应正常返回"""
        assert _safe_parse_port(65535) == 65535

    def test_端口0超出范围(self):
        """端口号 0 应抛出 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="超出有效范围"):
            _safe_parse_port(0)

    def test_端口65536超出范围(self):
        """端口号 65536 应抛出 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="超出有效范围"):
            _safe_parse_port(65536)

    def test_负数端口(self):
        """负数端口应抛出 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="超出有效范围"):
            _safe_parse_port(-1)

    def test_端口为None(self):
        """端口号为 None 应抛出 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="不能为空"):
            _safe_parse_port(None)

    def test_端口为非数字字符串(self):
        """非数字字符串端口应抛出 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="格式无效"):
            _safe_parse_port("abc")

    def test_端口为浮点数(self):
        """浮点数端口应被截断为整数并验证（8080.5 -> 8080，有效）"""
        # int(8080.5) == 8080，在有效范围内
        assert _safe_parse_port(8080.5) == 8080

    def test_端口为空字符串(self):
        """空字符串端口应抛出 ConfigurationError"""
        with pytest.raises(ConfigurationError, match="格式无效"):
            _safe_parse_port("")

    def test_异常包含downloader_id日志信息(self):
        """传入 downloader_id 时错误消息中应包含相关信息"""
        with pytest.raises(ConfigurationError):
            _safe_parse_port(None, downloader_id="dl-001")


# ==================== _normalize_downloader_type 测试 ====================

class TestNormalizeDownloaderType:
    """_normalize_downloader_type 下载器类型规范化测试"""

    def test_整数0返回qBittorrent(self):
        """整数 0 应被识别为 qBittorrent"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type=0)
        )
        assert manager._normalize_downloader_type() == 0

    def test_整数1返回Transmission(self):
        """整数 1 应被识别为 Transmission"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type=1)
        )
        assert manager._normalize_downloader_type() == 1

    def test_字符串0返回0(self):
        """字符串 "0" 应被规范化为 0"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type="0")
        )
        assert manager._normalize_downloader_type() == 0

    def test_字符串1返回1(self):
        """字符串 "1" 应被规范化为 1"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type="1")
        )
        assert manager._normalize_downloader_type() == 1

    def test_字符串qbittorrent返回0(self):
        """字符串 "qbittorrent" 应被规范化为 0"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type="qbittorrent")
        )
        assert manager._normalize_downloader_type() == 0

    def test_字符串TRANSMISSION大写返回1(self):
        """字符串 "TRANSMISSION"（大写）应被规范化为 1"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type="TRANSMISSION")
        )
        assert manager._normalize_downloader_type() == 1

    def test_无效类型默认返回0(self):
        """无效类型（如 99）应默认返回 0（qBittorrent）"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type=99)
        )
        assert manager._normalize_downloader_type() == 0

    def test_None类型默认返回0(self):
        """None 类型应默认返回 0（qBittorrent）"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type=None)
        )
        assert manager._normalize_downloader_type() == 0


# ==================== validate_settings 测试 ====================

class TestValidateSettings:
    """validate_settings 配置有效性验证测试"""

    def test_有效配置返回成功(self):
        """所有字段合法时应返回 (True, "")"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True}
        )
        settings = {
            "dl_speed_limit": 1024,
            "ul_speed_limit": 512,
            "dl_speed_unit": "KB/s",
            "ul_speed_unit": "MB/s",
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is True
        assert error_msg == ""

    def test_下载速度限制为负数(self):
        """dl_speed_limit 为负数时应验证失败"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True}
        )
        settings = {
            "dl_speed_limit": -100,
            "ul_speed_limit": 0,
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is False
        assert "dl_speed_limit" in error_msg

    def test_上传速度限制为非整数(self):
        """ul_speed_limit 为字符串时应验证失败"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True}
        )
        settings = {
            "dl_speed_limit": 0,
            "ul_speed_limit": "fast",
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is False
        assert "ul_speed_limit" in error_msg

    def test_下载速度单位无效(self):
        """dl_speed_unit 为无效值时应验证失败"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True}
        )
        settings = {
            "dl_speed_limit": 0,
            "ul_speed_limit": 0,
            "dl_speed_unit": "GB/s",
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is False
        assert "dl_speed_unit" in error_msg

    def test_上传速度单位无效(self):
        """ul_speed_unit 为无效值时应验证失败"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True}
        )
        settings = {
            "dl_speed_limit": 0,
            "ul_speed_limit": 0,
            "ul_speed_unit": "invalid",
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is False
        assert "ul_speed_unit" in error_msg

    def test_不支持分时段速度但启用schedule(self):
        """下载器不支持分时段速度但启用了 enable_schedule 应验证失败"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": False, "download_paths": True}
        )
        settings = {
            "dl_speed_limit": 0,
            "ul_speed_limit": 0,
            "enable_schedule": True,
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is False
        assert "enable_schedule" in error_msg

    def test_不支持下载路径但配置了download_dir(self):
        """下载器不支持下载路径但配置了 download_dir 应验证失败"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": False}
        )
        settings = {
            "dl_speed_limit": 0,
            "ul_speed_limit": 0,
            "download_dir": "/some/path",
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is False
        assert "download_dir" in error_msg

    def test_缺少字段使用默认值(self):
        """settings 中缺少速度字段时应使用默认值 0，验证通过"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True}
        )
        settings = {}
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is True
        assert error_msg == ""

    def test_速度单位回退到旧字段speed_unit(self):
        """缺少 dl_speed_unit/ul_speed_unit 时应回退到 speed_unit"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True}
        )
        settings = {
            "dl_speed_limit": 0,
            "ul_speed_limit": 0,
            "speed_unit": "MB/s",
        }
        is_valid, error_msg = manager.validate_settings(settings)
        assert is_valid is True

    def test_get_capabilities异常后空字典基础验证仍可通过(self):
        """get_supported_capabilities 抛异常时返回空字典，
        基础字段合法的情况下验证应通过（空字典中 schedule_speed/download_paths 为 False，
        但 settings 中未启用相关功能，所以不触发错误）"""
        wrapper = MagicMock()
        wrapper.get_capabilities.side_effect = Exception("连接异常")
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)
        settings = {"dl_speed_limit": 0, "ul_speed_limit": 0}
        is_valid, error_msg = manager.validate_settings(settings)
        # 异常被 get_supported_capabilities 内部捕获，返回空字典，
        # 基础字段合法且未启用 schedule/download_dir，验证通过
        assert is_valid is True
        assert error_msg == ""

    def test_get_capabilities异常后启用不支持的功能应验证失败(self):
        """get_supported_capabilities 抛异常返回空字典后，
        如果 settings 启用了 schedule/download_dir 等不被支持的功能应验证失败"""
        wrapper = MagicMock()
        wrapper.get_capabilities.side_effect = Exception("连接异常")
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)
        settings = {
            "dl_speed_limit": 0,
            "ul_speed_limit": 0,
            "enable_schedule": True,
        }
        is_valid, error_msg = manager.validate_settings(settings)
        # 空字典中 schedule_speed=False，启用 schedule 应报错
        assert is_valid is False
        assert "enable_schedule" in error_msg


# ==================== apply_settings 测试 ====================

class TestApplySettings:
    """apply_settings 应用配置测试"""

    def test_应用成功返回True(self):
        """设置包装类返回 True 时应返回 True"""
        wrapper = MagicMock()
        wrapper.set_all_settings.return_value = True
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        result = manager.apply_settings({"dl_speed_limit": 100})
        assert result is True
        wrapper.set_all_settings.assert_called_once_with({"dl_speed_limit": 100})

    def test_应用失败返回False(self):
        """设置包装类返回 False 时应返回 False"""
        wrapper = MagicMock()
        wrapper.set_all_settings.return_value = False
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        result = manager.apply_settings({})
        assert result is False

    def test_抛出DownloaderSettingsError应向上传播(self):
        """设置包装类抛出 DownloaderSettingsError 时应直接向上传播"""
        wrapper = MagicMock()
        wrapper.set_all_settings.side_effect = DownloaderSettingsError(
            message="设置失败", downloader_id="dl-001"
        )
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        with pytest.raises(DownloaderSettingsError, match="设置失败"):
            manager.apply_settings({})

    def test_抛出普通异常应包装为DownloaderSettingsError(self):
        """设置包装类抛出普通异常时应包装为 DownloaderSettingsError"""
        wrapper = MagicMock()
        wrapper.set_all_settings.side_effect = RuntimeError("未知错误")
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        with pytest.raises(DownloaderSettingsError, match="应用配置失败"):
            manager.apply_settings({})


# ==================== get_supported_capabilities 测试 ====================

class TestGetSupportedCapabilities:
    """get_supported_capabilities 获取能力列表测试"""

    def test_正常返回能力字典(self):
        """正常情况应返回能力字典"""
        wrapper = MagicMock()
        wrapper.get_capabilities.return_value = {
            "schedule_speed": True,
            "download_paths": False,
        }
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        result = manager.get_supported_capabilities()
        assert result == {"schedule_speed": True, "download_paths": False}

    def test_异常时返回空字典(self):
        """get_capabilities 抛异常时应返回空字典"""
        wrapper = MagicMock()
        wrapper.get_capabilities.side_effect = Exception("连接超时")
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        result = manager.get_supported_capabilities()
        assert result == {}


# ==================== test_connection 测试 ====================

class TestConnection:
    """test_connection 连接测试"""

    def test_连接成功返回True(self):
        """连接成功时返回 True"""
        wrapper = MagicMock()
        wrapper.test_connection.return_value = True
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        result = manager.test_connection()
        assert result is True

    def test_连接失败返回False(self):
        """连接失败时返回 False"""
        wrapper = MagicMock()
        wrapper.test_connection.return_value = False
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        result = manager.test_connection()
        assert result is False

    def test_连接异常返回False(self):
        """连接测试抛异常时应返回 False"""
        wrapper = MagicMock()
        wrapper.test_connection.side_effect = Exception("网络错误")
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        result = manager.test_connection()
        assert result is False


# ==================== create_from_template 测试 ====================

class TestCreateFromTemplate:
    """create_from_template 从模板创建配置测试"""

    def test_类型不匹配返回False(self):
        """模板类型与下载器类型不匹配时应返回 False"""
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type=0),
            capabilities={"schedule_speed": True, "download_paths": True},
        )
        template = {
            "name": "Transmission模板",
            "downloader_type": 1,
        }
        result = manager.create_from_template(template, make_downloader(downloader_type=0))
        assert result is False

    def test_类型匹配且验证通过应调用apply_settings(self):
        """模板类型匹配且验证通过时应调用 apply_settings"""
        wrapper = MagicMock()
        wrapper.get_capabilities.return_value = {"schedule_speed": True, "download_paths": True}
        wrapper.set_all_settings.return_value = True
        manager = _create_manager_with_mock_wrapper(
            downloader=make_downloader(downloader_type=0),
            wrapper=wrapper,
        )
        template = {
            "name": "qBit模板",
            "downloader_type": 0,
            "dl_speed_limit": 1024,
            "ul_speed_limit": 512,
        }
        result = manager.create_from_template(template, make_downloader(downloader_type=0))
        assert result is True

    def test_模板不含downloader_type跳过类型检查(self):
        """模板不含 downloader_type 时应跳过类型匹配检查"""
        wrapper = MagicMock()
        wrapper.get_capabilities.return_value = {"schedule_speed": True, "download_paths": True}
        wrapper.set_all_settings.return_value = True
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        template = {"name": "通用模板", "dl_speed_limit": 0, "ul_speed_limit": 0}
        result = manager.create_from_template(template, make_downloader())
        assert result is True

    def test_验证失败返回False(self):
        """模板配置验证失败时应返回 False"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"schedule_speed": True, "download_paths": True},
        )
        template = {
            "name": "无效模板",
            "dl_speed_limit": -999,
        }
        result = manager.create_from_template(template, make_downloader())
        assert result is False


# ==================== get_download_speed / get_upload_speed 测试 ====================

class TestGetSpeed:
    """get_download_speed / get_upload_speed 速度查询测试"""

    def test_获取下载速度不支持时返回None(self):
        """不支持速度查询时应返回 None"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"transfer_speed": False},
        )
        assert manager.get_download_speed() is None

    def test_获取上传速度不支持时返回None(self):
        """不支持速度查询时应返回 None"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"transfer_speed": False},
        )
        assert manager.get_upload_speed() is None

    def test_获取下载速度支持时当前返回None待实现(self):
        """支持速度查询但当前尚未实现，应返回 None"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"transfer_speed": True},
        )
        # 当前实现返回 None（待 T3 实现）
        assert manager.get_download_speed() is None

    def test_获取上传速度支持时当前返回None待实现(self):
        """支持速度查询但当前尚未实现，应返回 None"""
        manager = _create_manager_with_mock_wrapper(
            capabilities={"transfer_speed": True},
        )
        assert manager.get_upload_speed() is None

    def test_获取下载速度异常返回None(self):
        """get_capabilities 抛异常时应返回 None"""
        wrapper = MagicMock()
        wrapper.get_capabilities.side_effect = Exception("错误")
        manager = _create_manager_with_mock_wrapper(wrapper=wrapper)

        assert manager.get_download_speed() is None
