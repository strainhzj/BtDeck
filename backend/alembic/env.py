import sys
import os
sys.path.append(".")

from pathlib import Path
from app.database import Base

# 导入所有模型以确保 Alembic autogenerate 能检测到所有表
# 认证与权限
from app.auth.models import User, LoginLog, Config

# 下载器管理
from app.downloader.models import BtDownloaders
from app.models.downloader_capabilities import DownloaderCapabilities
from app.models.downloader_settings import DownloaderSetting
from app.models.downloader_path_maintenance import DownloaderPathMaintenance
from app.models.setting_templates import SettingTemplate
from app.models.speed_schedule_rules import SpeedScheduleRule

# 种子管理
from app.torrents.models import TorrentInfo, TrackerInfo
from app.models.torrent_tags import TorrentTag, TorrentTagRelation
from app.models.torrent_deletion_audit_log import TorrentDeletionAuditLog
from app.models.torrent_file_backup import TorrentFileBackup
from app.models.seed_transfer_audit_log import SeedTransferAuditLog

# 任务调度
from app.tasks.models import TaskLogs
from app.tasks.cron_models import CronTask
from app.torrents.audit_models import TorrentAuditLog

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# ========== 动态设置数据库URL ==========
# 从环境变量或应用配置中读取数据库路径
# 支持环境变量 DATABASE_PATH 覆盖默认配置
database_path = os.getenv('DATABASE_PATH')

if database_path:
    # 如果设置了环境变量，使用环境变量
    config.set_main_option('sqlalchemy.url', f'sqlite:///{database_path}')
else:
    # 否则，尝试使用应用配置
    try:
        from app.core.config import settings
        db_path = settings.DATABASE_PATH
        config.set_main_option('sqlalchemy.url', f'sqlite:///{db_path}')
    except Exception:
        # 如果应用配置加载失败，使用默认值
        # 默认使用 config/app.db
        default_db = Path(__file__).parent.parent / 'config' / 'app.db'
        config.set_main_option('sqlalchemy.url', f'sqlite:///{default_db}')

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
