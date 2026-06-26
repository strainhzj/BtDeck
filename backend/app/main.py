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

import uvicorn as uvicorn
from uvicorn import Config

from app.core.config import settings
from app.core.migration import migrate_database
from app.factory import app
from app.database import init_config_file

# 配置日志
logger = logging.getLogger(__name__)

# 配置日志级别,确保 INFO 级别的日志能够输出
# 修复: 解决启动时看不到"数据库迁移完成"等 INFO 日志的问题
# 改进: 添加异常处理,防止日志配置失败导致应用启动失败
try:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s", force=True  # 强制覆盖已配置的 logger
    )
except Exception as e:
    # 日志配置失败不应阻止应用启动,使用 print 输出警告
    print(f"[WARN] Failed to configure logging: {e}")
    print("[WARN] Using default logging configuration")


# uvicorn服务配置
# 改进: 根据环境选择不同的配置,避免生产环境多进程导致的数据库迁移竞态问题
if settings.DEV:
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
