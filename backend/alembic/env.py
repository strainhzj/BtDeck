import sys
from pathlib import Path

# frozen（PyInstaller）模式下 cwd 不可靠，显式注入 _MEIPASS 确保 app 包可被 import；
# 非 frozen 模式下 prepend_sys_path=.（alembic.ini 配置）已覆盖，这里冗余但无害。
if getattr(sys, "_MEIPASS", None):
    sys.path.insert(0, sys._MEIPASS)

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
from app.torrents.models import (
    TorrentInfo,
    TrackerInfo,
    TrackerKeywordConfig,
    TrackerMessageLog,
    TrackerReannounceConfig,
)
from app.models.torrent_tags import TorrentTag, TorrentTagRelation
from app.models.torrent_deletion_audit_log import TorrentDeletionAuditLog
from app.models.torrent_file_backup import TorrentFileBackup
from app.models.seed_transfer_audit_log import SeedTransferAuditLog

# 任务调度
from app.tasks.models import TaskLogs
from app.tasks.cron_models import CronTask
from app.torrents.audit_models import TorrentAuditLog

# 通知中心
from app.models.notification import Notification

# 搜索模板（第四轨归位，原由原生 SQL 自建）
from app.models.search_template import SearchTemplate

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# ========== 动态设置数据库URL ==========
# 统一从应用配置读取数据库路径（B3：双源一致性）。
# config.py 的 DATABASE_PATH property 已读取 DATABASE_PATH 环境变量，
# migrate_database() 会在调用 upgrade 前显式设此变量，确保应用与迁移操作同一库。
# 此处不再独立读取环境变量，避免双源漂移。
try:
    from app.core.config import settings
    db_path = settings.DATABASE_PATH
    config.set_main_option('sqlalchemy.url', f'sqlite:///{db_path}')
except Exception:
    # 应用配置加载失败时的兜底（如 alembic 独立命令行调用）
    default_db = Path(__file__).parent.parent / 'config' / 'app.db'
    config.set_main_option('sqlalchemy.url', f'sqlite:///{default_db}')

# Interpret the config file for Python logging.
# 守卫：fileConfig 会按 alembic.ini 重新配置 logging，可能覆盖应用配置。
# 这里仅在 alembic 独立运行时生效；应用内编程式调用后由应用自行管理 logging。
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        pass

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
