# Copyright (C) 2025 BTDeck Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import copy
import os
import re
import secrets
import sys
import threading

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type
from app import api

from pydantic import BaseModel, Field, validator

# 兼容新旧版本pydantic
try:
    from pydantic_settings import BaseSettings
except ImportError:
    try:
        from pydantic import BaseSettings
    except ImportError:
        # 如果都不存在，创建一个简单的BaseSettings类
        class BaseSettings:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)


class Settings(BaseSettings):
    """应用配置类"""
    # 项目基本信息
    PROJECT_NAME: str = "btdeck"

    # 网络配置
    APP_DOMAIN: str = ""
    API_V1_STR: str = "/api/v1"
    WS_V1_STR: str = "/ws"
    FRONTEND_PATH: str = "/public"
    HOST: str = "0.0.0.0"
    PORT: int = 5001
    WS_PORT: int = 5002
    NGINX_PORT: int = 5000

    # 运行模式
    DEBUG: bool = True
    DEV: bool = True
    DB_ECHO: bool = True

    # 目录配置
    CONFIG_DIR: Optional[str] = None
    ALLOWED_HOSTS: List[str] = ["*"]
    DATABASE_NAME: str = "app.db"

    # 安全配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-for-jwt")
    SM4_KEY: Optional[str] = None  # 将在应用启动时生成
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"

    model_config = {
        "case_sensitive": True,
        "env_file_encoding": "utf-8",
        "env_file": ".env"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 仅创建主配置目录（必需）
        # 子目录（temp、logs、cookies）按需创建，不在初始化时创建
        if not self.CONFIG_PATH.exists():
            self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)

    @property
    def CONFIG_PATH(self):
        if getattr(self, 'CONFIG_DIR', None):
            return Path(self.CONFIG_DIR)
        # elif SystemUtils.is_docker():
        #     return Path("/config")
        # elif SystemUtils.is_frozen():
        #     return Path(sys.executable).parent / "config"
        return self.ROOT_PATH / "config"

    @property
    def ROOT_PATH(self):
        return Path(__file__).parents[2]

    @property
    def TEMP_PATH(self):
        return self.CONFIG_PATH / "temp"

    @property
    def LOG_PATH(self):
        return self.CONFIG_PATH / "logs"

    @property
    def COOKIE_PATH(self):
        return self.CONFIG_PATH / "cookies"

    @property
    def DATABASE_PATH(self):
        return self.CONFIG_PATH / "app.db"

    @property
    def YAML_PATH(self):
        return self.CONFIG_PATH / "config.yaml"

    @property
    def TORRENTS_PATH(self):
        if self.TORRENTS_PATH:
            return Path(self.TORRENTS_PATH)
        # elif SystemUtils.is_docker():
        #     return Path("/config")
        # elif SystemUtils.is_frozen():
        #     return Path(sys.executable).parent / "config"
        return self.ROOT_PATH / "torrents"

# 实例化配置
settings = Settings()

