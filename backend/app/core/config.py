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

import logging
import os
import secrets
import sys

from pathlib import Path
from typing import List, Optional

from pydantic import Field, validator

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


logger = logging.getLogger(__name__)


def is_frozen() -> bool:
    """检测是否运行在 PyInstaller 打包（frozen）模式下。

    onefile 打包后，__file__ 指向临时解压目录 _MEIPASS（退出即销毁），
    因此数据/配置必须改写到可执行文件同级目录，否则不持久化。
    """
    return getattr(sys, "frozen", False)


def is_docker() -> bool:
    """检测是否运行在 Docker 容器中。"""
    return Path("/.dockerenv").exists()


def _default_secret_key() -> str:
    """开发兜底密钥：优先使用环境变量，未配置时生成临时密钥并记录警告。"""
    secret_key = os.getenv("SECRET_KEY")
    if secret_key:
        return secret_key

    logger.warning("SECRET_KEY 未配置，已生成临时开发密钥；生产环境必须通过环境变量显式设置。")
    return secrets.token_urlsafe(32)


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
    ALLOWED_HOSTS: List[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]
    DATABASE_NAME: str = "app.db"
    TORRENTS_DIR: Optional[str] = None

    # 安全配置
    SECRET_KEY: str = Field(default_factory=_default_secret_key)
    SM4_KEY: Optional[str] = None  # 将在应用启动时生成
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"
    BTDECK_ALLOW_CUSTOM_SCRIPTS: bool = False

    # 同步任务资源治理配置（sync-resource-governance）
    # 详见 PLANS/sync-resource-governance.md
    # heavy_sync 全局令牌：限制同时运行的重型同步任务数量，避免后台任务挤占请求侧资源
    SYNC_HEAVY_CONCURRENCY: int = 1
    # 每类重型任务最多允许排队等待的名额（按 task_code 计）；超过即跳过本轮
    SYNC_HEAVY_QUEUE_LIMIT: int = 1
    # 下载器 API 总令牌：阶段 2 downloader_api_runtime 使用，限制并发远程调用
    DOWNLOADER_IO_CONCURRENCY: int = 2
    # qB tracker 明细并发上限：阶段 2 tracker lane 使用
    QB_TRACKER_CONCURRENCY: int = 3
    # 下载器 API 单次调用超时（秒）：阶段 2 downloader_api_runtime 使用
    DOWNLOADER_API_TIMEOUT_SECONDS: int = 30
    # 同步任务 DB 批量提交大小：变更检测/批量 upsert 的批次阈值
    SYNC_DB_COMMIT_BATCH_SIZE: int = 200
    # 同步任务磁盘写入节流窗口（秒）：日志/进度类数据合并落盘的最小间隔
    SYNC_DISK_FLUSH_INTERVAL_SECONDS: float = 5.0
    # DB 写入临界区开关：True 时同步函数 commit 包裹 db_write_scope 串行化写者；
    # 上线后若多下载器并发同步 P95 退化 >30% 可临时关闭快速回滚。
    SYNC_DB_WRITE_SCOPE_ENABLED: bool = True

    model_config = {"case_sensitive": True, "env_file_encoding": "utf-8", "env_file": ".env"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._validate_security_config()
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
                print("[WARN] 请确保运行用户对该目录有写权限")

    @validator("ALLOWED_HOSTS", pre=True)
    def _parse_allowed_hosts(cls, value):
        """允许环境变量使用 JSON 数组或逗号分隔字符串配置 CORS 来源。"""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    def _validate_security_config(self):
        """启动期安全校验：生产环境拒绝隐式密钥和通配 CORS。"""
        if not self.DEV and not os.getenv("SECRET_KEY"):
            raise RuntimeError("生产环境必须通过 SECRET_KEY 环境变量显式配置 JWT 密钥")

        if not self.DEV and not os.getenv("ALLOWED_HOSTS"):
            raise RuntimeError("生产环境必须通过 ALLOWED_HOSTS 环境变量显式配置 CORS 来源")

        if "*" in self.ALLOWED_HOSTS:
            raise RuntimeError("allow_credentials=True 时 ALLOWED_HOSTS 不允许包含通配符 '*'")

    @property
    def CONFIG_PATH(self):
        if getattr(self, "CONFIG_DIR", None):
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
        # 环境变量优先（与 alembic/env.py 对齐）：migrate_database() 会显式设此变量，
        # 确保应用 engine 与 alembic 迁移操作同一个库（B3：双源一致性）。
        env_path = os.getenv("DATABASE_PATH")
        if env_path:
            return Path(env_path)
        return self.CONFIG_PATH / "app.db"

    @property
    def YAML_PATH(self):
        return self.CONFIG_PATH / "config.yaml"

    @property
    def TORRENTS_PATH(self):
        if getattr(self, "TORRENTS_DIR", None):
            return Path(self.TORRENTS_DIR)
        # frozen 模式：torrents 目录与可执行文件同级
        elif is_frozen():
            return Path(sys.executable).parent / "torrents"
        elif is_docker():
            return Path("/torrents")
        return self.ROOT_PATH / "torrents"


# 实例化配置
settings = Settings()
