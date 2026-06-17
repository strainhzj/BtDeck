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


def is_frozen() -> bool:
    """检测是否运行在 PyInstaller 打包（frozen）模式下。

    onefile 打包后，__file__ 指向临时解压目录 _MEIPASS（退出即销毁），
    因此数据/配置必须改写到可执行文件同级目录，否则不持久化。
    """
    return getattr(sys, "frozen", False)


def is_docker() -> bool:
    """检测是否运行在 Docker 容器中。"""
    return Path("/.dockerenv").exists()


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
    TORRENTS_DIR: Optional[str] = None

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
        # 容错：frozen 模式下若可执行文件同级目录属主异常，mkdir 可能无权限，
        # 此时打印清晰日志而不让进程直接崩溃（部署脚本应预创建并 chown 该目录）
        if not self.CONFIG_PATH.exists():
            try:
                self.CONFIG_PATH.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                # frozen 模式下若可执行文件同级目录属主异常，mkdir 可能无权限
                # 不让进程直接崩溃（部署脚本应预创建并 chown 该目录；后续
                # init_config_file 有自己的 makedirs 兜底并会记录详细错误）
                print(f"[WARN] 无法创建配置目录 {self.CONFIG_PATH}: {e}")
                print(f"[WARN] 请确保运行用户对该目录有写权限")

    @property
    def CONFIG_PATH(self):
        if getattr(self, 'CONFIG_DIR', None):
            return Path(self.CONFIG_DIR)
        # frozen 模式（PyInstaller onefile）：__file__ 指向临时解压目录 _MEIPASS，
        # 数据必须写到可执行文件同级目录才能持久化
        elif is_frozen():
            return Path(sys.executable).parent / "config"
        elif is_docker():
            return Path("/config")
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
        if getattr(self, 'TORRENTS_DIR', None):
            return Path(self.TORRENTS_DIR)
        # frozen 模式：torrents 目录与可执行文件同级
        elif is_frozen():
            return Path(sys.executable).parent / "torrents"
        elif is_docker():
            return Path("/torrents")
        return self.ROOT_PATH / "torrents"

# 实例化配置
settings = Settings()

