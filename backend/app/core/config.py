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
    # 日志级别：DEBUG/INFO/WARNING/ERROR（docker-compose 已声明 LOG_LEVEL 环境变量，
    # 由 BaseSettings 自动消费并传给 uvicorn；默认 INFO）
    LOG_LEVEL: str = "INFO"

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
    # 下载器 API 总令牌：per-downloader 跨 lane 共享（限制同一下载器的并发远程调用）。
    # 大下载器若 manifest 拉取仍慢，可通过环境变量 DOWNLOADER_IO_CONCURRENCY=4 提升；
    # 注意 requests.Session 非线程安全，提并发可能偶发连接错误（被 per-seed 降级吞掉
    # 不误删，但会部分抵消加速收益）。
    DOWNLOADER_IO_CONCURRENCY: int = 2
    # 每下载器后台容量（W2-2 交互容量保留）：background 调用（TRACKER/SYNC lane）
    # 最多占用该数量的 per-downloader 并发槽，其余槽始终保留给交互请求
    # （INTERACTIVE lane）。默认 1：后台最多占 1 槽，交互恒保留 1 槽。
    # 若配置与总容量矛盾（total<=1 且本值>=1），运行时自动降级为 0 并记录警告，
    # 不会破坏交互保留槽。详见 PLANS/sync-database-blocking-remediation.md W2-2
    DOWNLOADER_BACKGROUND_CAPACITY: int = 1
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
    # 真分批提交开关（W1-1）：True 时 bulk_upsert_with_retry 按
    # SYNC_DB_COMMIT_BATCH_SIZE 真实分批提交（每批独立 commit），消除单大事务
    # 对 SQLite 写锁的长时间持有；False 时回退旧行为（单事务一次提交）。
    # 详见 PLANS/sync-database-blocking-remediation.md W1-1
    SYNC_CHUNKED_COMMIT_ENABLED: bool = True
    # 单批最大尝试次数（含首次）：锁冲突时只重试当前失败批
    SYNC_DB_LOCK_RETRY_COUNT: int = 3
    # 单批重试总退避上限（秒）：任何一批的重试总睡眠不超过该值，
    # 防止排队雪崩（对应计划第 12 节 "DB retry total backoff 不超过 2 秒"）
    SYNC_DB_RETRY_MAX_BACKOFF_SECONDS: float = 2.0
    # Tracker 关键词状态增量写回开关（W1-2）：True 时服务层对判定结果与库中
    # 现有 (status, msg) 做 strip 归一化变化检测，只写变化行（零变化零 DML，
    # 不进 db_write_scope、不 UPDATE、不 commit）；False 时回退旧逻辑（跳过
    # 变化检测，所有匹配 tracker 全部写回）。回退不改变判定规则，只改变写回策略。
    # 详见 PLANS/sync-database-blocking-remediation.md W1-2
    SYNC_TRACKER_STATUS_INCREMENTAL_ENABLED: bool = True
    # 统一 SyncCoordinator 开关（W2-1）：True 时手动同步（sync-single）与
    # 定时任务（info/tracker）统一经 app/services/sync_coordinator.py::run_sync
    # 执行（统一资源准入/写治理/观测），torrent_sync_db_async 作为 legacy adapter
    # 内部转发；False 时手动入口回退旧直接调用 torrent_sync_db_async 全量同步的
    # 路径（应急回滚）。⚠️ legacy 只能作为应急回退，禁止与新路径同时执行，
    # 两个稳定版本后删除。详见 PLANS/sync-database-blocking-remediation.md W2-1
    SYNC_CANONICAL_COORDINATOR_ENABLED: bool = True

    # 孤儿文件管理配置（v1.0.6）
    # 自动清理超期天数：连续成为孤儿超过该天数的候选由定时任务移入隔离区
    # 语义重做：依据「连续成为孤儿的时间」，不再依据文件 mtime
    ORPHAN_AUTO_CLEANUP_DAYS: int = 30
    # 定时扫描开关：False 时定时任务跳过扫描（手动扫描不受影响）
    ORPHAN_SCAN_ENABLED: bool = True
    # 文件清单批量获取批次大小（按种子数分批调下载器 API）
    ORPHAN_SCAN_BATCH_SIZE: int = 200
    # 排除的文件模式（分号分隔，fnmatch 语法）：匹配的文件不判定为孤儿
    ORPHAN_EXCLUDE_PATTERNS: str = "*.torrent;*.pending_delete"
    # 孤儿候选清理天数阈值（连续成为孤儿的持续时间超过此值才可清理，取代 mtime 阈值）
    ORPHAN_CANDIDATE_PURGE_DAYS: int = 30
    # 隔离区保留期（天）：移入隔离区后保留该天数再允许物理删除
    ORPHAN_QUARANTINE_RETENTION_DAYS: int = 7
    # 隔离区目录名（在每个扫描根下创建，同文件系统保证 os.rename 原子）
    ORPHAN_QUARANTINE_DIR_NAME: str = ".btdeck_quarantine"
    # Level3 回收站归档标记：孤儿扫描与清理流水线无条件跳过含此标记的路径，
    # 防止回收站数据被误判为孤儿后清理（与 ORPHAN_QUARANTINE_DIR_NAME 同属系统保留名）。
    # 默认值与 recycle_bin_service.py / torrent_deletion_by_level.py 的硬编码一致。
    ORPHAN_RECYCLE_BIN_TAG: str = ".pending_delete"
    # 跨进程操作 lease TTL（秒）：扫描/清理互斥租约的过期时间
    ORPHAN_LEASE_TTL_SECONDS: int = 3600

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
