"""
测试 Yaml 配置类的完整行为

覆盖目标：
- __init__: 初始化时自动调用 load
- load: 成功加载 / 文件不存在 / 加载异常
- reload: 委托给 load
- get: 点分隔路径取值 / 嵌套路径 / 不存在路径返回默认值 / 懒加载
- get_all: 返回完整配置副本 / 懒加载
- __str__: 返回配置字典的字符串表示

测试策略：
- 使用 unittest.mock.patch 模拟文件系统和 yaml.safe_load
- 不依赖真实文件系统
"""

import pytest
from unittest.mock import patch, mock_open

from app.yamlConfig import Yaml


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = {
    "app": {
        "name": "BTDeck",
        "debug": False,
    },
    "database": {
        "host": "localhost",
        "port": 3306,
        "credentials": {
            "user": "admin",
            "password": "secret",
        },
    },
}

FAKE_PATH = "/fake/config.yaml"


def _make_yaml_with_config(config_data, config_path=FAKE_PATH):
    """直接构造一个 Yaml 实例，跳过 __init__ 中的 load，手动设置配置"""
    y = Yaml.__new__(Yaml)
    y._config_path = config_path
    y._config_data = config_data
    return y


# ---------------------------------------------------------------------------
# __init__ 和 load
# ---------------------------------------------------------------------------

class TestYamlInitAndLoad:
    """初始化与加载测试"""

    def test_初始化时自动加载配置(self):
        """__init__ 应自动调用 load 并填充 _config_data"""
        with patch("app.yamlConfig.os.path.exists", return_value=True), \
             patch("app.yamlConfig.pyyaml.safe_load", return_value=SAMPLE_CONFIG), \
             patch("builtins.open", mock_open(read_data="dummy")):
            y = Yaml(config_path=FAKE_PATH)
            assert y._config_data == SAMPLE_CONFIG

    def test_文件不存在时配置为空字典(self):
        """配置文件不存在时，_config_data 保持空字典"""
        with patch("app.yamlConfig.os.path.exists", return_value=False):
            y = Yaml(config_path="/nonexistent.yaml")
            assert y._config_data == {}

    def test_yaml解析异常时配置为空字典(self):
        """yaml.safe_load 抛出异常时，load 返回 False，配置保持空"""
        with patch("app.yamlConfig.os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="dummy")), \
             patch("app.yamlConfig.pyyaml.safe_load", side_effect=Exception("解析失败")):
            y = Yaml(config_path=FAKE_PATH)
            assert y._config_data == {}

    def test_load成功返回True(self):
        """文件存在且解析正常时，load 返回 True"""
        y = _make_yaml_with_config({})
        with patch("app.yamlConfig.os.path.exists", return_value=True), \
             patch("app.yamlConfig.pyyaml.safe_load", return_value=SAMPLE_CONFIG), \
             patch("builtins.open", mock_open(read_data="dummy")):
            result = y.load()
        assert result is True
        assert y._config_data == SAMPLE_CONFIG

    def test_load文件不存在返回False(self):
        """文件不存在时，load 返回 False"""
        y = _make_yaml_with_config({}, config_path="/nonexistent.yaml")
        with patch("app.yamlConfig.os.path.exists", return_value=False):
            result = y.load()
        assert result is False


# ---------------------------------------------------------------------------
# reload
# ---------------------------------------------------------------------------

class TestYamlReload:
    """重新加载测试"""

    def test_reload重新加载配置(self):
        """reload 应委托给 load，返回最新配置"""
        y = _make_yaml_with_config({"old": True})
        with patch("app.yamlConfig.os.path.exists", return_value=True), \
             patch("app.yamlConfig.pyyaml.safe_load", return_value={"reloaded": True}), \
             patch("builtins.open", mock_open(read_data="dummy")):
            result = y.reload()
        assert result is True
        assert y._config_data == {"reloaded": True}


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------

class TestYamlGet:
    """通过点分隔路径获取配置值"""

    def test_获取顶层配置(self):
        """单层路径应返回对应的字典"""
        y = _make_yaml_with_config(SAMPLE_CONFIG)
        result = y.get("app")
        assert result == {"name": "BTDeck", "debug": False}

    def test_获取嵌套配置值(self):
        """多层路径应逐层深入取值"""
        y = _make_yaml_with_config(SAMPLE_CONFIG)
        assert y.get("app.name") == "BTDeck"
        assert y.get("database.port") == 3306
        assert y.get("database.credentials.user") == "admin"

    def test_路径不存在返回默认值None(self):
        """不存在的路径应返回默认值 None"""
        y = _make_yaml_with_config(SAMPLE_CONFIG)
        result = y.get("nonexistent.key")
        assert result is None

    def test_路径不存在返回自定义默认值(self):
        """不存在的路径应返回用户指定的默认值"""
        y = _make_yaml_with_config(SAMPLE_CONFIG)
        result = y.get("nonexistent.key", default="fallback")
        assert result == "fallback"

    def test_配置为空时触发懒加载(self):
        """_config_data 为空时，get 应自动触发 load"""
        y = _make_yaml_with_config({})
        with patch("app.yamlConfig.os.path.exists", return_value=True), \
             patch("app.yamlConfig.pyyaml.safe_load", return_value=SAMPLE_CONFIG), \
             patch("builtins.open", mock_open(read_data="dummy")):
            result = y.get("app.name")
        assert result == "BTDeck"


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------

class TestYamlGetAll:
    """获取完整配置字典"""

    def test_返回完整配置浅副本(self):
        """get_all 应返回与原始配置内容相同的浅副本"""
        y = _make_yaml_with_config(SAMPLE_CONFIG)
        all_config = y.get_all()
        assert all_config == SAMPLE_CONFIG
        # get_all 使用 dict.copy() 做浅拷贝，顶层是独立对象
        assert all_config is not y._config_data

    def test_配置为空时触发懒加载(self):
        """_config_data 为空时，get_all 应自动触发 load"""
        y = _make_yaml_with_config({})
        with patch("app.yamlConfig.os.path.exists", return_value=True), \
             patch("app.yamlConfig.pyyaml.safe_load", return_value=SAMPLE_CONFIG), \
             patch("builtins.open", mock_open(read_data="dummy")):
            all_config = y.get_all()
        assert all_config == SAMPLE_CONFIG


# ---------------------------------------------------------------------------
# __str__
# ---------------------------------------------------------------------------

class TestYamlStr:
    """字符串表示测试"""

    def test_str返回配置字典字符串(self):
        """__str__ 应返回 _config_data 的字符串表示"""
        y = _make_yaml_with_config(SAMPLE_CONFIG)
        assert str(y) == str(SAMPLE_CONFIG)
