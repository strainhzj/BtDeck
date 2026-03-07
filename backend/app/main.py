import multiprocessing
import os
import sys
import threading
import asyncio
import logging

import uvicorn as uvicorn
from uvicorn import Config

from app.core.config import settings
from app.core.migration import run_alembic_migrations
from app.core.init_schema_from_production import ensure_database_initialized, init_database_from_production_schema
from app.factory import app
from app.database import init_db
from app.database import init_config_file
from app.downloader.qbittorrent import initialQb

# 配置日志
logger = logging.getLogger(__name__)

# 配置日志级别,确保 INFO 级别的日志能够输出
# 修复: 解决启动时看不到"数据库迁移完成"等 INFO 日志的问题
# 改进: 添加异常处理,防止日志配置失败导致应用启动失败
try:
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s:%(name)s:%(message)s',
        force=True  # 强制覆盖已配置的 logger
    )
except Exception as e:
    # 日志配置失败不应阻止应用启动,使用 print 输出警告
    print(f"[WARN] Failed to configure logging: {e}")
    print(f"[WARN] Using default logging configuration")


# uvicorn服务配置
# 改进: 根据环境选择不同的配置,避免生产环境多进程导致的数据库迁移竞态问题
if settings.DEV:
    # 开发环境: 热重载模式,单进程
    Server = uvicorn.Server(Config(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=True,  # 开发环境启用热重载
        workers=1,  # 强制单进程,热重载模式下多进程被忽略
        timeout_graceful_shutdown=5,
        loop="asyncio"
    ))
else:
    # 生产环境: 单进程模式,避免数据库迁移竞态条件
    # 注意: 多进程模式下只有主进程执行迁移,worker可能访问不一致的schema
    Server = uvicorn.Server(Config(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # 生产环境关闭热重载
        workers=1,  # ← 强制单进程,确保所有请求使用一致的数据库schema
        timeout_graceful_shutdown=5,
        loop="asyncio"
    ))


if __name__ == '__main__':
    # # 启动托盘
    # start_tray()

    # 初始化配置文件
    init_config_file()

    # ✨ 重新加载配置，确保 yaml 对象读取到刚生成的配置
    from app.yamlConfig import yaml
    yaml.reload()

    # === 数据库自动初始化逻辑 ===
    # 如果数据库为空（首次部署或数据库被删除），从生产schema自动初始化
    # 并自动标记为最新版本，跳过有问题的迁移链
    from pathlib import Path
    import sqlite3
    db_path = str(Path(__file__).parent.parent / 'config' / settings.DATABASE_NAME)
    logger.info(f"Database path: {db_path}")

    # 检查数据库是否需要从生产schema初始化
    if ensure_database_initialized(db_path):
        # 数据库刚从生产schema初始化，已经标记为最新版本
        # 跳过Alembic迁移，避免有问题的迁移链
        logger.info("Database initialized from production schema, skipping Alembic migration chain")
    else:
        # 数据库已存在，执行常规的Alembic迁移
        logger.info("Database already exists, running Alembic migration chain")
        run_alembic_migrations()

    # 初始化数据库
    init_db()

    initialQb()

    # # 更新数据库
    # update_db()
    # 注册启动事件

    # 启动API服务
    Server.run()
