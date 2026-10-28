import sys
from pathlib import Path

# frozen（PyInstaller）模式下 cwd 不可靠，显式注入 _MEIPASS 确保 app 包可被 import；
# 非 frozen 模式下 prepend_sys_path=.（alembic.ini 配置）已覆盖，这里冗余但无害。
if getattr(sys, "_MEIPASS", None):
    sys.path.insert(0, sys._MEIPASS)

from app.database import Base

# 模型集中注册（v1.0.8 任务1.6）：单一注册点，与 PG 基线共用（契约 §3 规则 2）；
# 原散布在本文件的逐个 import 归位 app/core/model_registry.py
from app.core.model_registry import register_all_models

register_all_models()

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

    if settings.DATABASE_DIALECT == "postgresql":
        # v1.0.8 双数据库（契约 §2.1）：PG 走 URL.create 结构化构造（psycopg2 同步驱动）；
        # set_main_option 经 configparser，值中 % 需双写转义
        from app.database import build_database_url

        _url = build_database_url()
        config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))
    else:
        db_path = settings.DATABASE_PATH
        config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
except Exception:
    # 应用配置加载失败时的兑底（如 alembic 独立命令行调用；仅 SQLite 路径）
    default_db = Path(__file__).parent.parent / "config" / "app.db"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{default_db}")

# database-migration-ui W1-4：显式目标 URL 最高优先级（T14）——迁移管线重放
# 原生链到任意目标（如 PG 运行态下重放到新 SQLite staging）而不修改全局
# settings/os.environ；只作用于本次操作（PLANS §4.1）
_target_url = config.attributes.get("target_url")
if _target_url:
    config.set_main_option("sqlalchemy.url", str(_target_url).replace("%", "%%"))

# Interpret the config file for Python logging.
# 守卫：fileConfig 会按 alembic.ini 重新配置 logging，可能覆盖应用配置。
# 这里仅在 alembic 独立运行时生效；应用内编程式调用后由应用自行管理 logging。
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
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

    优先复用 ``config.attributes["connection"]``（共享连接）——
    PG 基线初始化用它在同一事务内完成 create_all + stamp（契约 §3 规则 3，
    Alembic Cookbook 连接共享方式）；无共享连接时按原路径新建引擎，
    并执行 PG 空库手工升级守卫。

    """
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        _run_migrations_with_connection(connectable)
        return

    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.begin() as connection:
        # 守卫逻辑提取至 pg_baseline（任务3.1 可单测化）；基线豁免标记透传
        from app.core.pg_baseline import guard_manual_upgrade_on_empty_db

        guard_manual_upgrade_on_empty_db(connection, baseline_flag=bool(config.attributes.get("btdeck_baseline_stamp")))
        _run_migrations_with_connection(connection)


def _run_migrations_with_connection(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    if connection.dialect.name == "postgresql":
        from app.core.pg_baseline import PG_MINIMUM_REVISION, validate_pg_server

        validate_pg_server(connection)
        migration_context = context.get_context()
        operation = migration_context.opts.get("fn")
        if getattr(operation, "__name__", "") == "downgrade":
            current = migration_context.get_current_revision()
            removed = operation(current, migration_context)
            if any(step.revision.revision == PG_MINIMUM_REVISION for step in removed):
                raise RuntimeError(f"PostgreSQL 禁止降级到基线 {PG_MINIMUM_REVISION} 之前")

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
