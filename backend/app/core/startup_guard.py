# app/core/startup_guard.py
"""SQLite 单 Worker 启动约束（W2-4 / P0-06，fail-fast）。

背景：resource_guard 与 Python 信号量均为进程内对象；若容器脚本（btdeck_startup.sh）
或外部 uvicorn 命令以多 Worker（WORKERS>1）启动，每个进程都会各自启动 scheduler，
导致进程内锁与资源准入全部失效，SQLite 写锁治理（db_write_scope / 短事务分批）
退化为空转。

约束：SQLite 后端强制 WORKERS=1，违规启动期立即失败（fail-fast），并输出可操作错误。
注意：不能通过启动多个 SQLite Worker 缓解接口卡顿。

本模块保持纯函数 + 仅标准库依赖，可在不拉起应用进程的情况下独立单元测试。
规则与 btdeck_startup.sh 中的 shell 检查保持一致（改动需同步两边）。
"""

import logging
import os
import sys
from typing import Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

# 后端类型常量（detect_backend 返回值）
BACKEND_SQLITE = "sqlite"
BACKEND_POSTGRES = "postgres"
BACKEND_MYSQL = "mysql"
BACKEND_OTHER = "other"

# DATABASE_URL scheme → 后端类型（scheme 取 "+" 前的方言名，如 sqlite+aiosqlite → sqlite）
_SQLITE_PREFIXES = ("sqlite", "sqlite3")
_POSTGRES_PREFIXES = ("postgres", "postgresql")
_MYSQL_PREFIXES = ("mysql", "mariadb")


class StartupGuardError(RuntimeError):
    """启动约束校验失败。错误信息面向运维，可直接展示。"""


def detect_backend(database_url: Optional[str]) -> str:
    """从 database_url 解析后端类型。

    - 未设置/空值：按默认文件型 SQLite 处理（settings.DATABASE_PATH 决定，
      与 app/database.py、alembic/env.py 同源）。
    - 支持带驱动方言的 scheme（sqlite+aiosqlite://、postgresql+asyncpg:// 等）。
    """
    if not database_url or not database_url.strip():
        return BACKEND_SQLITE
    scheme = database_url.split("://", 1)[0].split("+", 1)[0].strip().lower()
    if scheme in _SQLITE_PREFIXES:
        return BACKEND_SQLITE
    if scheme in _POSTGRES_PREFIXES:
        return BACKEND_POSTGRES
    if scheme in _MYSQL_PREFIXES:
        return BACKEND_MYSQL
    return BACKEND_OTHER


def parse_worker_count(raw: Optional[str]) -> int:
    """解析 WORKERS 环境变量。

    - 未设置/空值：视为 1（与 python main.py 内部写死 workers=1 的默认一致）。
    - 非整数：抛 StartupGuardError（fail-fast，避免静默按 1 放行掩盖配置错误）。
    """
    if raw is None or not raw.strip():
        return 1
    try:
        return int(raw.strip())
    except ValueError:
        raise StartupGuardError(f"WORKERS 环境变量必须是整数（当前值 {raw!r}），请修正后重启")


def _parse_bool(raw: str) -> bool:
    """解析布尔环境变量：空/0/false/no/off 视为 False，其余视为 True。"""
    return raw.strip().lower() not in ("", "0", "false", "no", "off")


def resolve_database_url(env: Optional[Mapping[str, str]] = None) -> str:
    """按仓库实际生效优先级解析 DATABASE_URL。

    1. DATABASE_URL 环境变量（未来 PostgreSQL/MySQL 等后端入口）；
    2. sqlite:///DATABASE_PATH（与 app/database.py / alembic/env.py 同源）；
    3. 均未配置：返回空串（detect_backend 按默认 SQLite 文件库处理）。
    """
    environ = env if env is not None else os.environ
    url = environ.get("DATABASE_URL", "")
    if url:
        return url
    db_path = environ.get("DATABASE_PATH", "")
    if db_path:
        return f"sqlite:///{db_path}"
    return ""


def validate_worker_count(database_backend: str, worker_count: int, scheduler_enabled: bool = True) -> None:
    """核心校验：SQLite 后端 + worker_count != 1 即失败（错误信息可操作）。

    scheduler_enabled 保留为参数：当 scheduler 关闭时多 Worker 仍违反锁治理约束，
    因此本校验不因 scheduler 开关而放宽；参数仅供启动清单日志使用。
    """
    if not isinstance(worker_count, int):
        raise StartupGuardError(f"WORKERS 必须是整数，当前值 {worker_count!r}")
    if database_backend == BACKEND_SQLITE and worker_count != 1:
        raise StartupGuardError(
            f"SQLite 后端禁止多 Worker 启动：当前 WORKERS={worker_count}，请改为 1。"
            "SQLite 文件库的写锁治理与资源准入（db_write_scope / 信号量）均为进程内对象，"
            "多 Worker 会使锁与准入失效并放大写锁争用，且各进程都会各自启动 scheduler；"
            "不能通过启动多个 SQLite Worker 缓解接口卡顿。"
            "如确需多 Worker，请先切换 PostgreSQL 后端（scheduler Leader 选举另行实现）。"
        )


def validate_scheduler_scope(database_backend: str, worker_count: int) -> str:
    """scheduler 单实例纵深防御（W2-4 第 4 条）。

    前置启动校验已挡住 SQLite 多 Worker；此处作为最后防线：
    - SQLite + worker_count != 1：拒绝 scheduler 启动（抛异常，正常情况下不可达）；
    - PostgreSQL + worker_count > 1：Leader 选举未实现，记录显式状态日志；
    - 其余：单实例安全。
    返回日志说明文本，供调用方记录。
    """
    if database_backend == BACKEND_SQLITE and worker_count != 1:
        msg = (
            f"SQLite 后端 + WORKERS={worker_count} 违反单 Worker 约束，scheduler 拒绝启动"
            "（前置启动校验应已拦截，此为纵深防御兜底）"
        )
        logger.error(
            "scheduler_scope database_backend=%s worker_count=%d status=blocked %s",
            database_backend,
            worker_count,
            msg,
        )
        raise StartupGuardError(msg)
    if database_backend == BACKEND_POSTGRES and worker_count > 1:
        msg = (
            f"PostgreSQL 多 Worker（WORKERS={worker_count}）scheduler Leader 未实现："
            "多个进程各自启动 scheduler 会造成定时任务重复执行，请保持 WORKERS=1 "
            "或外置独立 scheduler 进程"
        )
        logger.warning(
            "scheduler_scope database_backend=%s worker_count=%d status=leader_not_implemented %s",
            database_backend,
            worker_count,
            msg,
        )
        return msg
    msg = f"scheduler 单实例安全 database_backend={database_backend} worker_count={worker_count}"
    logger.info(
        "scheduler_scope database_backend=%s worker_count=%d status=ok %s",
        database_backend,
        worker_count,
        msg,
    )
    return msg


def resolve_runtime_info(env: Optional[Mapping[str, str]] = None) -> Tuple[str, int, bool]:
    """解析启动运行时信息（不校验）：(database_backend, worker_count, scheduler_enabled)。"""
    environ = env if env is not None else os.environ
    backend = detect_backend(resolve_database_url(environ))
    workers = parse_worker_count(environ.get("WORKERS"))
    scheduler_enabled = _parse_bool(environ.get("SCHEDULER_ENABLED", "1"))
    return backend, workers, scheduler_enabled


def validate_from_env(env: Optional[Mapping[str, str]] = None) -> Tuple[str, int, bool]:
    """从环境变量解析并校验启动约束（fail-fast）。

    校验通过返回 (database_backend, worker_count, scheduler_enabled) 供启动日志使用；
    校验失败抛 StartupGuardError（错误信息可操作）。
    """
    backend, workers, scheduler_enabled = resolve_runtime_info(env)
    validate_worker_count(backend, workers, scheduler_enabled)
    return backend, workers, scheduler_enabled


def log_startup_manifest(
    database_backend: str,
    worker_count: int,
    scheduler_enabled: bool,
    process_id: Optional[int] = None,
) -> None:
    """启动清单日志（key=value 风格，参照仓库日志格式）。

    字段：database_backend / worker_count / scheduler_enabled / process_id。
    启动配置与实际进程数在此日志中可核对（W2-4 DoD）。
    """
    if process_id is None:
        process_id = os.getpid()
    logger.info(
        "startup_manifest database_backend=%s worker_count=%d scheduler_enabled=%s process_id=%d",
        database_backend,
        worker_count,
        scheduler_enabled,
        process_id,
    )


def main() -> int:
    """命令行入口：python -m app.core.startup_guard。

    供运维在拉起服务前人工校验（容器脚本本身使用内联 shell 检查，规则与本模块一致）。
    校验通过打印清单并返回 0；失败打印可操作错误并返回 1。
    """
    try:
        backend, workers, scheduler_enabled = validate_from_env()
    except StartupGuardError as exc:
        print(f"startup_guard: {exc}", file=sys.stderr)
        return 1
    print(
        f"startup_guard ok database_backend={backend} worker_count={workers} " f"scheduler_enabled={scheduler_enabled}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
