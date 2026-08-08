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
import sys

import uvicorn as uvicorn
from uvicorn import Config

from app.core.config import is_frozen, settings
from app.core.migration import migrate_database
from app.core.startup_guard import StartupGuardError, log_startup_manifest, validate_from_env
from app.factory import app
from app.database import init_config_file

# 配置日志
logger = logging.getLogger(__name__)

# 配置日志级别：接通 LOG_LEVEL 环境变量（docker-compose 已声明）。
_log_level_name = (settings.LOG_LEVEL or os.environ.get("LOG_LEVEL") or "INFO").upper()
_app_log_level = getattr(logging, _log_level_name, logging.INFO)
try:
    # 方案：给 app.* 整棵 logger 树装独立 handler 并 propagate=False，
    # 彻底脱离对 root/basicConfig 的依赖（避免被 uvicorn dictConfig 等覆盖/清空）。
    # 业务日志（app.services.* 等）始终由此 handler 输出。
    # 显式绑定 stdout（与 lifespan 的 print 同流，docker 下已验证可见），
    # 避免 stderr 在某些查看方式下被遗漏。
    _app_formatter = logging.Formatter("%(asctime)s %(levelname)s:%(name)s:%(message)s")
    _app_handler = logging.StreamHandler(sys.stdout)
    _app_handler.setFormatter(_app_formatter)
    _app_root_logger = logging.getLogger("app")
    _app_root_logger.setLevel(_app_log_level)
    # 清理可能残留的 handler（force 语义），避免重复输出
    for _h in list(_app_root_logger.handlers):
        _app_root_logger.removeHandler(_h)
    _app_root_logger.addHandler(_app_handler)
    _app_root_logger.propagate = False  # 关键：不依赖 root，不受 basicConfig/uvicorn 影响

    # 立即输出一条验证日志，便于确认 app logger 已就绪（docker logs 可见）
    logger.info("[日志] app logger 已就绪，级别=%s，输出流=stdout", _log_level_name)

    # 同时配置 root（兼容非 app.* 的库日志）
    logging.basicConfig(
        level=_app_log_level,
        format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
        force=True,
    )
    # 压制第三方库噪声：避免 LOG_LEVEL=DEBUG 时 SQL/HTTP 明文洪水 + cookie 泄露。
    for _noisy in (
        "sqlalchemy.engine",
        "urllib3",
        "qbittorrentapi",
        "transmission_rpc",
        "httpx",
        "httpcore",
        "asyncio",
    ):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
except Exception as e:
    # 日志配置失败不应阻止应用启动,使用 print 输出警告
    print(f"[WARN] Failed to configure logging: {e}")
    print("[WARN] Using default logging configuration")


# === SQLite 单 Worker 启动约束（W2-4 / P0-06，fail-fast）===
# 容器脚本（btdeck_startup.sh）与外部 uvicorn 命令可能绕过下方 Server 配置写死的
# workers=1，因此这里解析**实际生效的 WORKERS 环境变量**（未设置视为 1，与
# python main.py 直接运行默认一致），校验不通过直接抛异常阻止启动。
try:
    _startup_backend, _startup_workers, _startup_scheduler_enabled = validate_from_env()
    # 启动清单日志：database_backend / worker_count / scheduler_enabled / process_id
    # 启动配置与实际进程数在此日志中可核对。
    log_startup_manifest(_startup_backend, _startup_workers, _startup_scheduler_enabled)
except StartupGuardError as exc:
    logger.error("启动约束校验失败，拒绝启动: %s", exc)
    raise


# uvicorn服务配置
# 改进: 根据环境选择不同的配置,避免生产环境多进程导致的数据库迁移竞态问题

# 规范化 LOG_LEVEL 为 uvicorn 接受的小写值（critical/error/warning/info/debug/trace）。
# 兼容常见缩写（warn→warning 等）；非法值兜底为 info，避免 uvicorn KeyError 启动失败。
_UVICORN_LEVEL_ALIASES = {"warn": "warning", "err": "error", "crit": "critical"}
_UVICORN_VALID_LEVELS = {"critical", "error", "warning", "info", "debug", "trace"}


def _to_uvicorn_level(raw: str) -> str:
    val = (raw or "info").lower()
    val = _UVICORN_LEVEL_ALIASES.get(val, val)
    return val if val in _UVICORN_VALID_LEVELS else "info"


_uvicorn_log_level = _to_uvicorn_level(settings.LOG_LEVEL)

if settings.DEV and not is_frozen():
    # 开发环境: 热重载模式,单进程
    Server = uvicorn.Server(
        Config(
            app,
            host=settings.HOST,
            port=settings.PORT,
            reload=True,  # 开发环境启用热重载
            workers=1,  # 强制单进程,热重载模式下多进程被忽略
            timeout_graceful_shutdown=5,
            loop="asyncio",
            log_level=_uvicorn_log_level,  # 同步 LOG_LEVEL，避免 uvicorn 默认覆盖
        )
    )
else:
    # 生产环境: 单进程模式,避免数据库迁移竞态条件
    # 注意: 多进程模式下只有主进程执行迁移,worker可能访问不一致的schema
    Server = uvicorn.Server(
        Config(
            app,
            host=settings.HOST,
            port=settings.PORT,
            reload=False,  # 生产环境关闭热重载
            workers=1,  # ← 强制单进程,确保所有请求使用一致的数据库schema
            timeout_graceful_shutdown=5,
            loop="asyncio",
            log_level=_uvicorn_log_level,  # 同步 LOG_LEVEL，避免 uvicorn 默认覆盖
        )
    )


if __name__ == "__main__":
    # # 启动托盘
    # start_tray()

    # 初始化配置文件
    init_config_file()

    # ✨ 重新加载配置，确保 yaml 对象读取到刚生成的配置
    from app.yamlConfig import yaml

    yaml.reload()

    # === 数据库迁移统一入口 ===
    # 四轨治理后，迁移由 migrate_database() 统一负责（空库建表/已有库升级/幽灵版本救援）。
    # 注意：Server.run() 启动 uvicorn 时会触发 FastAPI lifespan，
    # lifespan 内也会调用 migrate_database() + init_db()。两者均幂等，双执行安全。
    # 但 frozen/直接运行场景下，先在此迁移可更早暴露错误。
    db_path = str(settings.DATABASE_PATH)
    logger.info(f"Database path: {db_path}")
    migrate_database()

    # 启动API服务（lifespan 内完成 init_db / 后台任务初始化）
    Server.run()
