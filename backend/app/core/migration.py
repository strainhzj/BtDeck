"""
数据库迁移模块

提供自动执行 Alembic 数据库迁移的功能，确保应用启动时数据库结构始终是最新状态。
"""
import logging
import os
import shutil
import subprocess
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def run_alembic_migrations() -> bool:
    """
    自动执行 Alembic 数据库迁移

    在应用启动时自动执行最新的数据库迁移，确保数据库结构始终是最新状态。

    改进: 区分开发环境和生产环境的错误处理
    - 开发环境: 迁移失败不阻止启动(便于调试)
    - 生产环境: 迁移失败必须终止启动(确保数据一致性)

    Returns:
        bool: 迁移是否成功执行

    Raises:
        RuntimeError: 生产环境迁移失败时抛出异常
    """
    try:
        logger.info("检查数据库迁移...")

        # 检查alembic命令是否可用
        if not shutil.which("alembic"):
            error_msg = "alembic命令未找到，请确保已安装alembic（pip install alembic）"
            logger.error(error_msg)
            # 改进: 生产环境缺少alembic应该终止启动
            if not settings.DEV:
                raise RuntimeError(error_msg)
            return False

        # 获取项目根目录（btpManager目录，alembic.ini所在位置）
        # 此文件在 app/core/ 目录下，需要向上两级到达项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # 优化P2-1：数据库迁移超时配置化（默认5分钟，可通过环境变量MIGRATION_TIMEOUT配置）
        migration_timeout = int(os.getenv('MIGRATION_TIMEOUT', '300'))  # 默认300秒（5分钟）
        logger.info(f"数据库迁移超时设置: {migration_timeout}秒")

        # 执行 alembic upgrade head，并指定工作目录
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            encoding='utf-8',  # 修复：指定UTF-8编码，避免Windows系统GBK编码错误
            errors='replace',  # 遇到无法解码的字符时替换而非报错
            timeout=migration_timeout,  # 使用可配置的超时时间
            cwd=project_root  # 修复：确保在正确的目录执行（包含alembic.ini的目录）
        )

        if result.returncode == 0:
            logger.info("数据库迁移完成")
            if result.stdout:
                # 过滤掉 Alembic 的日志输出，避免重复
                for line in result.stdout.split('\n'):
                    if line and 'INFO' not in line and 'Running upgrade' not in line:
                        logger.info(line)
            return True
        else:
            error_msg = f"数据库迁移失败: {result.stderr}"
            logger.error(error_msg)
            # 改进: 生产环境迁移失败必须终止启动
            if not settings.DEV:
                raise RuntimeError(f"Database migration failed in production: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        error_msg = "数据库迁移超时"
        logger.warning(f"{error_msg}，跳过自动迁移")
        # 改进: 生产环境超时必须终止启动
        if not settings.DEV:
            raise RuntimeError(f"{error_msg} in production environment")
        return False
    except FileNotFoundError:
        error_msg = "未找到 alembic 命令"
        logger.warning(f"{error_msg}，跳过自动迁移")
        # 改进: 生产环境缺少命令必须终止启动
        if not settings.DEV:
            raise RuntimeError(f"{error_msg} in production environment")
        return False
    except Exception as e:
        error_msg = f"数据库迁移异常: {str(e)}"
        logger.warning(f"{error_msg}，跳过自动迁移")
        # 改进: 生产环境异常必须终止启动
        if not settings.DEV:
            raise RuntimeError(f"Database migration error in production: {str(e)}")
        return False
