import yaml as pyyaml  # ✨ 使用别名避免命名冲突
import os
from typing import Any, Dict, Optional
from app.core.config import settings


class Yaml:
    """配置类，支持使用点表示法访问嵌套配置"""

    def __init__(self, config_path=settings.YAML_PATH):
        self._config_path = config_path
        self._config_data = {}
        self.load()

    def load(self) -> bool:
        """加载配置文件"""
        try:
            if not os.path.exists(self._config_path):
                print(f"警告：配置文件 '{self._config_path}' 不存在")
                return False

            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config_data = pyyaml.safe_load(f)
            return True
        except Exception as e:
            print(f"加载配置文件时出错: {e}")
            return False

    def reload(self) -> bool:
        """
        重新加载配置文件

        Returns:
            加载成功返回 True，否则返回 False
        """
        return self.load()

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        通过点分隔的路径获取配置值

        支持懒加载：如果配置为空，自动重新加载配置文件

        Args:
            key_path: 点分隔的配置路径, 例如 "app.name"
            default: 如果路径不存在返回的默认值

        Returns:
            配置值或默认值
        """
        # ✨ 懒加载：如果配置为空，自动重新加载
        if not self._config_data:
            self.load()

        keys = key_path.split('.')
        value = self._config_data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def get_all(self) -> Dict:
        """获取完整配置字典"""
        # ✨ 懒加载：如果配置为空，自动重新加载
        if not self._config_data:
            self.load()
        return self._config_data.copy()

    def __str__(self) -> str:
        """字符串表示"""
        return str(self._config_data)


# 使用示例
yaml = Yaml()

# # 使用点表示法获取配置
# app_name = config.get("app.name", "DefaultApp")
# db_port = config.get("database.port", 3306)
# debug_mode = config.get("app.debug", False)
#
# print(f"应用名称: {app_name}")
# print(f"数据库端口: {db_port}")
# print(f"调试模式: {'开启' if debug_mode else '关闭'}")
#
# # 获取整个部分
# database_config = config.get("database", {})
# print(f"数据库配置: {database_config}")
