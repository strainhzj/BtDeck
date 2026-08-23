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

import yaml

from pydantic import Field, validator

# 兼容新旧版本pydantic（mypy 无法理解条件导入的互斥性，逐分支标注 noqa）
try:
    from pydantic_settings import BaseSettings
except ImportError:
    try:
        from pydantic import BaseSettings  # type: ignore[no-redef]  # noqa: F811
    except ImportError:
        # 如果都不存在，创建一个简单的BaseSettings类
        class BaseSettings:  # type: ignore[no-redef]  # noqa: F811
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


def _default_config_dir() -> Path:
    """不依赖 Settings 实例解析配置目录（供 _default_secret_key 引导期使用）。

    与 Settings.CONFIG_PATH 的分支语义一致：CONFIG_DIR 环境变量优先，
    其次 frozen/docker 模式的固定目录，最后仓库根 config/。
    """
    config_dir = os.getenv("CONFIG_DIR")
    if config_dir:
        return Path(config_dir)
    if is_frozen():
        return Path(sys.executable).parent / "config"
    if is_docker():
        return Path("/config")
    return Path(__file__).parents[2] / "config"


def _jwt_secret_from_yaml() -> Optional[str]:
    """从 config.yaml 读取持久化的 JWT 签名密钥（SECRET_KEY 缺省时的回退源）。

    由 init_config_file 首次启动写入（缺失才补），使默认部署重启后签名密钥
    保持稳定、存量会话不被整体杀死。文件缺失/键缺失/读取异常一律返回 None
    交回随机值兜底，不在此处创建或修改文件。
    """
    try:
        path = _default_config_dir() / "config.yaml"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        value = (config.get("security") or {}).get("jwt_secret_key")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as e:  # noqa: BLE001 - 引导期兜底路径，任何读取异常都退回随机值
        logger.warning("读取 config.yaml 的 jwt_secret_key 失败: %s", e)
    return None


def _default_secret_key() -> str:
    """开发兜底密钥：环境变量 → config.yaml 持久化密钥 → 临时随机值。"""
    secret_key = os.getenv("SECRET_KEY")
    if secret_key:
        return secret_key

    persisted = _jwt_secret_from_yaml()
    if persisted:
        return persisted

    logger.warning("SECRET_KEY 未配置且 config.yaml 无 jwt_secret_key，已生成临时开发密钥；生产环境必须显式配置。")
    return secrets.token_urlsafe(32)


class Settings(BaseSettings):
    """应用配置类"""

    # 项目基本信息
    PROJECT_NAME: str = "btdeck"

    # 网络配置
    APP_DOMAIN: str = ""
    API_V1_STR: str = "/api/v1"
    FRONTEND_PATH: str = "/public"
    HOST: str = "0.0.0.0"
    PORT: int = 5001
    NGINX_PORT: int = 5000

    # 运行模式
    # DEBUG/DB_ECHO 默认关闭（安全修复 W11）：DEBUG 开启会把完整 traceback
    # （绝对路径/源码行）写入 500 响应体；DEV 保持默认 True 以兼容
    # 桌面/frozen 发行版（DEV=False 会触发 SECRET_KEY/ALLOWED_HOSTS 强制校验，
    # 发行版无环境变量注入机制，直接拒绝启动）
    DEBUG: bool = False
    DEV: bool = True
    DB_ECHO: bool = False
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
    # refresh token 有效期（天，双令牌体系 W6-1）
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
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
    # qB tracker 明细并发上限（历史配置，保留兼容旧环境变量）：自 W3-1 起
    # 不再控制任务数上限，任务数由 QB_TRACKER_WORKER_COUNT（有界 worker 队列）
    # 取代。详见 PLANS/sync-database-blocking-remediation.md W3-1
    QB_TRACKER_CONCURRENCY: int = 3
    # qB Tracker 有界 worker 队列 worker 数（W3-1）：同时活跃的拉取协程数，
    # 禁止一次性为全部 hash 创建任务对象；10k 级种子时活跃 asyncio 任务数
    # ≈ worker_count + 控制任务（生产者 1 + 当前协程）。建议不超过下载器
    # 后台容量 DOWNLOADER_BACKGROUND_CAPACITY
    QB_TRACKER_WORKER_COUNT: int = 2
    # qB Tracker 单轮数量预算（W3-1）：每轮 enrich 最多拉取该数量的种子，
    # 达到即停止消费并返回部分结果（budget_reason=count）；小于 1 视为 1
    QB_TRACKER_MAX_TORRENTS_PER_RUN: int = 1000
    # qB Tracker 单轮时间预算（秒，W3-1）：从本轮开始计时，超过即停止消费
    # 并返回部分结果（budget_reason=time）；0 或负值表示不限时
    QB_TRACKER_RUN_BUDGET_SECONDS: float = 120.0
    # qB Tracker 单次调用超时（秒，W3-1）：单个种子 tracker 拉取的总预算
    # （含排队与远程调用），透传给 downloader_api_runtime 的 timeout 参数
    QB_TRACKER_PER_CALL_TIMEOUT: float = 30.0
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

    # 种子信息同步（info-only）资源治理配置（W3-3 第一部分，P1-02）
    # 详见 PLANS/sync-database-blocking-remediation.md W3-3
    # 下载器并发数：SQLite 默认 1（串行处理下载器，避免多下载器并发同步叠加
    # 内存/CPU 峰值挤占请求侧）。配置上限不得超过明确压测值，当前默认 1。
    INFO_SYNC_DOWNLOADER_CONCURRENCY: int = 1
    # 现有记录分页读取页大小：构建 existing_torrents_cache 时按 hash 排序分页
    # 读取，避免一次加载完整 ORM 对象图造成大下载器峰值内存（分页只解决
    # "一次加载"的峰值，缓存结构与 diff 语义不变）
    INFO_SYNC_DB_READ_PAGE_SIZE: int = 500
    # 单轮记录数上限：info-only 每轮最多处理该数量的种子，达到即停止处理
    # 剩余并返回部分结果（budget_reason=count）；小于 1 视为 1
    INFO_SYNC_MAX_TORRENTS_PER_RUN: int = 10000
    # 启动时回填 added_date 为空的行（W3-3）：后台任务执行，默认关闭
    INFO_SYNC_STARTUP_BACKFILL_ENABLED: bool = False
    # 单轮时长上限（秒）：从本轮开始计时，超过即停止处理并返回部分结果
    # （budget_reason=time）；0 或负值表示不限时
    INFO_SYNC_RUN_BUDGET_SECONDS: float = 300.0
    # to_insert+to_update 待写行缓冲上限：逐种子构造/差异计算达到该行数先
    # flush 一批到 bulk_upsert_with_retry 再继续，控制内存峰值
    INFO_SYNC_MAX_BUFFERED_ROWS: int = 2000
    # info-only 同步完成后每个下载器最多补齐的种子文件备份数。限量增量处理
    # 避免历史缺口在单轮内产生大规模文件 IO；小于 1 时按 1 处理。
    TORRENT_BACKUP_RECONCILE_BATCH_SIZE: int = 200

    # 孤儿硬链接副本预扫描定时任务（前端只读库内结果，不再实时遍历）
    # 单轮最多 stat 的孤儿明细数（keyset 游标推进，含截止时间检查）
    ORPHAN_HARDLINK_SCAN_STAT_BATCH_SIZE: int = 2000
    # 单轮最多进入目录遍历的目标 inode 数（仅 nlink>1 的文件需要遍历）
    ORPHAN_HARDLINK_SCAN_MAX_TARGETS: int = 200
    # 单轮遍历的单调时钟预算（秒）；在 os.walk 目录间检查，超时保留部分结果
    ORPHAN_HARDLINK_SCAN_BUDGET_SECONDS: float = 300.0
    # 单个 inode 最多存储的副本路径数，超出截断并标记 truncated
    ORPHAN_HARDLINK_SCAN_MAX_PATHS_PER_TARGET: int = 100
    # 结果保留天数；超期未刷新的行由任务清理，控制表体积
    ORPHAN_HARDLINK_SCAN_RESULT_RETENTION_DAYS: int = 30

    # 孤儿文件管理配置（v1.0.6）
    # 自动清理超期天数：连续成为孤儿超过该天数的候选由定时任务移入隔离区
    # 语义重做：依据「连续成为孤儿的时间」，不再依据文件 mtime
    ORPHAN_AUTO_CLEANUP_DAYS: int = 30
    # 路径维护：路径清理宽限期（天）。路径最后一次有种子距今超过该天数且当前无种子
    # 时，定时扫描才将其标记为自动禁用（disabled_by='auto'）；0=立即禁用（旧行为）。
    PATH_CLEANUP_GRACE_DAYS: int = 30
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
    # 到期删除遇硬链接副本跳过时，purge_after 延后的天数（打破每日重试循环；
    # 副本被清除后 purge_after 到期仍会正常删除，无延后次数上限）
    ORPHAN_HARDLINK_PURGE_DELAY_DAYS: int = 7
    # 隔离区目录名（在每个扫描根下创建，同文件系统保证 os.rename 原子）
    ORPHAN_QUARANTINE_DIR_NAME: str = ".btdeck_quarantine"
    # Level3 回收站归档标记：孤儿扫描与清理流水线无条件跳过含此标记的路径，
    # 防止回收站数据被误判为孤儿后清理（与 ORPHAN_QUARANTINE_DIR_NAME 同属系统保留名）。
    # 默认值与 recycle_bin_service.py / torrent_deletion_by_level.py 的硬编码一致。
    ORPHAN_RECYCLE_BIN_TAG: str = ".pending_delete"
    # 跨进程操作 lease TTL（秒）：扫描/清理互斥租约的过期时间
    ORPHAN_LEASE_TTL_SECONDS: int = 3600
    # 孤儿扫描落库分批提交批次大小（每批独立事务+写锁，防止大批量孤儿单事务
    # 独占 SQLite 写锁导致 API 卡死；实测 12 万孤儿单次 commit 约 11 分钟）
    ORPHAN_SCAN_COMMIT_BATCH_SIZE: int = 200
    # 孤儿数上限护栏阈值：扫描发现的孤儿超过此值记 warning + 通知（不阻断落库，
    # 真实大批量孤儿仍照常入库可清理，仅提醒用户核查是否为异常量级）
    ORPHAN_SCAN_MAX_ORPHANS_WARNING: int = 50000

    # 定时任务数据新鲜度兜底阈值（秒，W3-4/P1-05）：cron_plan 无法解析出最短
    # 重复间隔时，stale 判断使用该值（默认 2 小时）；可解析时按
    # “2 个调度周期”语义取 2 × 最短重复间隔（如每 5 分钟任务 → 600 秒）。
    # 详见 PLANS/sync-database-blocking-remediation.md W3-4
    CRON_STALE_THRESHOLD_SECONDS: float = 7200.0

    # 同步观测配置（W4-1 结构化观测工具模块 sync_observability）
    # 事件循环 lag 采样器开关：False 时 start_lag_sampler 返回空句柄 no-op
    SYNC_LAG_SAMPLER_ENABLED: bool = True
    # 事件循环 lag 采样间隔（秒）：每 interval 以 loop.call_at 漂移法记录一次
    # lag 样本，滑动窗口暴露 p95/p99/max（观测告警阈值见 PLANS W4-1 第 5 节）
    SYNC_LAG_SAMPLER_INTERVAL_SECONDS: float = 1.0
    # WAL 只读周期快照间隔（秒，W4-1 第二部分）：生命周期内每间隔经
    # snapshot_wal_stats 读取 -wal 文件字节数并发射 EVENT_WAL_SNAPSHOT；
    # <=0 时不启动周期快照任务（观测关闭不影响同步治理）
    SYNC_WAL_SNAPSHOT_INTERVAL_SECONDS: float = 60.0
    # Python 内部类执行观测心跳间隔（秒）；<=0 时只保留 start/end，不发心跳。
    # 心跳只写结构化日志，不写数据库，也不改变任务取消/超时语义。
    SYNC_TASK_OBSERVABILITY_INTERVAL_SECONDS: float = 30.0

    # 健康检查配置（W4-2）：readiness 只执行有界只读探针，不执行写探针。
    # SELECT 1 超时即返回 db_query_timeout，避免 SQLite busy_timeout 把健康检查
    # 拖成长期排队；lag 阈值允许运维在基线校准后临时放宽，但不跳过数据库检查。
    HEALTH_READINESS_DB_TIMEOUT_SECONDS: float = 1.0
    # 同步业务健康查询同样必须有界，避免锁争用时健康端点自身长期占用连接。
    HEALTH_SYNC_DB_TIMEOUT_SECONDS: float = 1.0
    HEALTH_READINESS_LAG_P99_THRESHOLD_MS: float = 100.0

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

    @validator("SECRET_KEY", pre=True)
    def _empty_secret_key_to_default(cls, value):
        """compose 传 ${SECRET_KEY:-} 展开为空串时，回退随机生成密钥。

        空串密钥会让 JWT 签名使用可预测空密钥（严重），必须归一化。
        生产校验（_validate_security_config）仍按环境变量层面拒绝空值。
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return _default_secret_key()
        return value

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
        # SECRET_KEY 显式传了空串（如 compose 的 ${SECRET_KEY:-}）视为未设置。
        # 放宽条件：config.yaml 已持久化 jwt_secret_key（init_config_file 写入）
        # 视为已显式配置；首启生产（YAML 尚无密钥）仍拒绝启动，护栏不拆
        if not self.DEV and not os.getenv("SECRET_KEY") and _jwt_secret_from_yaml() is None:
            raise RuntimeError(
                "生产环境必须通过 SECRET_KEY 环境变量或 config.yaml 的 security.jwt_secret_key 显式配置 JWT 密钥"
            )

        if not self.DEV and not os.getenv("ALLOWED_HOSTS"):
            raise RuntimeError("生产环境必须通过 ALLOWED_HOSTS 环境变量显式配置 CORS 来源")

        if "*" in self.ALLOWED_HOSTS:
            raise RuntimeError("allow_credentials=True 时 ALLOWED_HOSTS 不允许包含通配符 '*'")

    @property
    def CONFIG_PATH(self):
        if getattr(self, "CONFIG_DIR", None):
            return Path(self.CONFIG_DIR)
        # frozen/docker/仓库根三分支与 _default_config_dir 共用一份逻辑，
        # 避免引导期（读 YAML 密钥）与运行期路径解析漂移
        return _default_config_dir()

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
