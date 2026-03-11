# app/database.py
from sqlalchemy import create_engine, NullPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging
from app.core.config import settings
from app.auth.security import get_password_hash
import os
import yaml
import logging
import base64
from typing import Dict, Any, Optional
from gmssl import sm4, func
from app.auth import utils


# 创建日志记录器
logger = logging.getLogger(__name__)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{settings.DATABASE_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30  # 设置30秒超时，避免"database is locked"错误
    },
    poolclass=NullPool
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ========== 异步数据库引擎配置 ==========
# 异步数据库URL（使用 aiosqlite 驱动）
ASYNC_SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{settings.DATABASE_PATH}"

# 创建异步引擎
# 优化说明：
# 1. 使用 StaticPool 替代 NullPool，复用单个连接，减少锁竞争
# 2. 设置 busy_timeout=30，等待锁的最长时间为30秒（默认5秒太短）
# 3. 启用 WAL 模式（Write-Ahead Logging），提升并发性能
async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30  # 设置30秒的超时时间，避免"database is locked"错误
    },
    poolclass=NullPool,  # SQLite推荐使用NullPool，因为单个文件数据库不支持真正的连接池
    echo=False  # 设置为 True 可以查看 SQL 执行日志
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """
    异步数据库会话依赖注入函数

    用于FastAPI的Depends，提供异步数据库会话。
    与 get_db() 并存，保持向后兼容性。

    Yields:
        AsyncSession: 异步数据库会话
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def init_db():
    """
    初始化数据库：
    1. 检查数据库文件是否存在
    2. 如果不存在，创建所有表
    3. 启用WAL模式提升并发性能
    4. 添加默认管理员账户（如果不存在）
    5. 设置默认配置（如果不存在）
    """
    db_file = settings.DATABASE_PATH
    db_exists = os.path.exists(db_file)

    # 导入所有模型，确保它们被注册到Base.metadata
    from app.auth.models import User, LoginLog, Config
    from app.downloader.models import BtDownloaders
    from app.torrents.models import TorrentInfo
    from app.torrents.models import TrackerInfo
    from app.torrents.audit_models import TorrentAuditLog
    from app.tasks.models import TaskLogs
    from app.tasks.cron_models import CronTask  # 必须导入，TaskLogs有外键引用cron_task表
    from app.models.setting_templates import SettingTemplate
    from app.models.torrent_tags import TorrentTag, TorrentTagRelation

    # 创建表（如果不存在）
    Base.metadata.create_all(bind=engine)

    # 启用 WAL 模式（Write-Ahead Logging）
    # WAL模式优势：
    # 1. 读写操作不互相阻塞（提升并发性能）
    # 2. 更快的提交速度（只写日志，不覆盖原文件）
    # 3. 更好的崩溃恢复能力
    try:
        import sqlite3
        conn = sqlite3.connect(db_file)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # 平衡安全性和性能
        conn.close()
        logger.info("SQLite WAL 模式已启用，并发性能提升")
    except Exception as e:
        logger.warning(f"启用 WAL 模式失败: {str(e)}")

    # 迁移系统已升级为 Alembic
    # 旧迁移系统（app.migrations.database_migrator）已弃用，所有迁移由 Alembic 管理
    # Alembic 迁移在 main.py 的 run_alembic_migrations() 中自动执行
    # 历史迁移记录：
    # - field_types_migration_v1 (字段类型)
    # - delete_logic_migration_v1 (删除逻辑)
    # - encryption_migration_v1 (加密字段)
    # - keyword_type_pools_migration_v1 (关键词池)
    # - add_torrent_progress_column_v1 (进度字段)
    # 以上迁移已在生产数据库完成，新数据库由 Alembic 处理
    pass

    # 修复：无论数据库是否已存在，都要检查并创建初始数据
    # 原因：Alembic迁移会创建数据库文件，但不会创建初始用户数据
    db = SessionLocal()
    try:
        # 检查是否已有admin用户
        admin_exists = db.query(User).filter(User.username == "admin").first()
        if not admin_exists:
            # 创建默认admin用户
            logger.info("Creating default admin user...")
            print("Creating default admin user...")
            admin_password = "admin"  # 初始密码
            hashed_password = get_password_hash(admin_password)
            twofactor_secret = utils.generate_totp_secret()
            admin_user = User(
                username="admin",
                password=hashed_password,
                is_active=True,
                two_factor_secret=twofactor_secret,
            )
            db.add(admin_user)
            logger.info("Default admin user created")
            print("Default admin user created (username: admin, password: admin)")

        # 添加默认配置
        cookie_expire_config = db.query(Config).filter(Config.key == "cookie_expire_minutes").first()
        if not cookie_expire_config:
            logger.info("Adding default configuration...")
            print("Adding default configuration...")
            cookie_config = Config(
                key="cookie_expire_minutes",
                value="30",
                description="Cookie expiration time in minutes"
            )
            db.add(cookie_config)
            logger.info("Default configuration added")
            print("Default configuration added")

        db.commit()
        logger.info("Database initialization completed")
        print("Database initialization completed")
    except Exception as e:
        db.rollback()
        logger.error(f"Error initializing database: {str(e)}")
        print(f"Error initializing database: {str(e)}")
    finally:
        db.close()

    # 初始化系统默认模板（无论数据库是否已存在）
    try:
        from app.data.default_templates import init_default_templates
        db = SessionLocal()
        init_default_templates(db)
        db.close()
    except Exception as e:
        logger.error(f"Error initializing default templates: {str(e)}")
        print(f"Error initializing default templates: {str(e)}")


    # 初始化系统默认定时任务（基于数据存在性判断）
    # 修复：改用数据存在性判断，而非文件存在性判断
    # 原因：ensure_database_initialized()可能已创建数据库文件，导致db_exists判断失效
    try:
        from app.data.default_scheduled_tasks import init_default_scheduled_tasks
        from app.tasks.cron_models import CronTask

        db = SessionLocal()
        try:
            # 检查是否已有定时任务数据
            task_count = db.query(CronTask).count()

            if task_count == 0:
                # 没有定时任务数据，执行初始化
                logger.info("初始化系统默认定时任务...")
                print("初始化系统默认定时任务...")
                init_default_scheduled_tasks(db)
                logger.info("系统默认定时任务初始化完成")
                print("系统默认定时任务初始化完成")
            else:
                logger.info(f"定时任务数据已存在（{task_count}条），跳过初始化")
                print(f"定时任务数据已存在（{task_count}条），跳过初始化")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error initializing default scheduled tasks: {str(e)}")
        print(f"Error initializing default scheduled tasks: {str(e)}")


def init_config_file(
        config_path: str = settings.YAML_PATH,
        custom_config: Optional[Dict[str, Any]] = None,
        overwrite: bool = False
) -> bool:
    try:
        # 确保配置文件目录存在
        config_dir = os.path.dirname(config_path)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            logging.info(f"创建配置目录: {config_dir}")

        login_status_secret = str(func.random_hex(16))
        sm4Key = str(func.random_hex(16))

        # 检查文件是否已存在
        if os.path.exists(config_path) and not overwrite:
            logging.info(f"配置文件 {config_path} 已存在，仅更新安全密钥。")
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    new_config = yaml.load(f, Loader=yaml.SafeLoader)

                # 确保security部分存在
                if "security" not in new_config:
                    new_config["security"] = {}

                # 更新安全密钥但保留原有的其他配置
                # new_config["security"]["login_status_secret"] = login_status_secret

                # 确保SM4密钥存在
                if "secret_key" not in new_config["security"]:
                    new_config["security"]["secret_key"] = sm4Key
                    logging.warning("配置文件中缺少secret_key，已添加。")

                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

                return True
            except Exception as read_error:
                logging.error(f"读取或更新现有配置文件失败: {str(read_error)}")
                # 如果读取现有文件失败，继续创建新文件
                overwrite = True

        # 默认配置
        default_config = {
            "app": {
                "name": "MyApplication",
                "version": "1.0.0",
                "debug": False,
                "log_level": "INFO"
            },
            "database": {
                "host": "localhost",
                "port": 3306,
                "username": "user",
                "password": "password",
                "database": "mydb",
                "charset": "utf8mb4",
                "pool_size": 5
            },
            "server": {
                "host": "0.0.0.0",
                "port": 8000,
                "workers": 4,
                "timeout": 60
            },
            "security": {
                "secret_key": sm4Key,
                "token_expire_minutes": 60,
                "algorithm": "HS256",
                "login_status_secret": login_status_secret
            },
            "cors": {
                "allowed_origins": ["*"],
                "allowed_methods": ["*"],
                "allowed_headers": ["*"]
            },
            "logging": {
                "file": "app.log",
                "max_size_mb": 10,
                "backup_count": 5
            }
        }

        # 合并自定义配置
        if custom_config:
            merge_configs(default_config, custom_config)

        # 写入配置文件
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        # 验证文件是否成功创建
        if not os.path.exists(config_path):
            logging.error(f"配置文件似乎未成功创建: {config_path}")
            return False

        logging.info(f"配置文件已成功生成: {config_path}")
        print(f"配置文件已成功生成: {config_path}")  # 控制台输出，便于调试
        return True

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logging.error(f"生成配置文件时出错: {str(e)}\n{error_trace}")
        print(f"生成配置文件时出错: {str(e)}\n{error_trace}")  # 控制台输出更详细的错误
        return False


def merge_configs(base_config: Dict[str, Any], custom_config: Dict[str, Any]) -> None:
    """
    递归合并两个配置字典，custom_config的值会覆盖base_config中的对应值

    Args:
        base_config: 基础配置字典，将被修改
        custom_config: 自定义配置字典，其值将覆盖base_config中的对应值
    """
    for key, value in custom_config.items():
        if key in base_config and isinstance(base_config[key], dict) and isinstance(value, dict):
            merge_configs(base_config[key], value)
        else:
            base_config[key] = value
