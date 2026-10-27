# app/database.py
from sqlalchemy import create_engine, NullPool, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging
from app.core.config import settings
from app.auth.security import get_password_hash
import yaml
from typing import Any, Dict, Optional
from urllib.parse import quote_plus
from gmssl import func
from app.auth import utils
from app.services.sqlite_search_runtime import install_sqlite_search_functions
from app.services.orphan_folder_grouping import install_orphan_folder_functions

# 创建日志记录器
logger = logging.getLogger(__name__)


# ========== 数据源方言判定（v1.0.8 双数据库架构，契约 docs/postgresql-contract.md §2）==========
# sqlite（默认，行为与历史版本完全一致）或 postgresql（可选数据源）。
# 方言唯一判定入口为 settings.DATABASE_DIALECT；本模块不再独立解析 DB_TYPE。
DIALECT = settings.DATABASE_DIALECT


def _pg_ssl_args(*, async_driver: bool) -> Dict[str, Any]:
    """按契约 §2.3 将 DB_SSLMODE 映射为驱动连接参数。

    psycopg2（同步）：URL sslmode 查询参数（在 build_database_url 内拼接）。
    asyncpg（异步）：模式串或 SSLContext——disable 必须显式传 False
    （asyncpg 缺省即 prefer，不传 ssl 仍会尝试 TLS）；verify-ca/verify-full
    构造加载 DB_SSL_ROOT_CERT 的 SSLContext（verify-full 额外启用主机名校验）。
    """
    if not async_driver:
        return {}  # 同步侧走 URL 查询参数
    import ssl as _ssl

    mode = (settings.DB_SSLMODE or "prefer").strip().lower()
    if mode == "disable":
        return {"ssl": False}
    if mode in ("prefer", "require"):
        # prefer：asyncpg 模式串允许回退明文；require：无 CA 校验但强制 TLS
        return {"ssl": mode}
    # verify-ca / verify-full：加载 CA 的上下文
    if not settings.DB_SSL_ROOT_CERT:
        raise ValueError(f"DB_SSLMODE={mode} 需要 DB_SSL_ROOT_CERT 指向 CA 证书路径")
    ctx = _ssl.create_default_context(cafile=settings.DB_SSL_ROOT_CERT)
    if mode == "verify-ca":
        ctx.check_hostname = False
    # verify-full：保持 check_hostname=True（create_default_context 默认）
    return {"ssl": ctx}


def build_database_url(*, async_driver: bool = False) -> str:
    """按当前配置构造数据库 URL（双数据库架构的单一 URL 工厂，契约 §2.1）。

    - sqlite:         sqlite:///{DATABASE_PATH}（默认，与历史行为一致）
    - sqlite (async): sqlite+aiosqlite:///{DATABASE_PATH}
    - postgresql:         postgresql+psycopg2://（同步，alembic / sync session）
    - postgresql (async): postgresql+asyncpg://（异步引擎）

    PG 走 sqlalchemy.engine.URL.create 结构化构造（凭据特殊字符 % @ / : 空格
    自动转义）；同步侧 TLS 以 sslmode 查询参数携带（契约 §2.3）。
    """
    if DIALECT == "postgresql":
        from sqlalchemy.engine import URL

        query: Dict[str, Any] = {}
        if not async_driver:
            query["sslmode"] = (settings.DB_SSLMODE or "prefer").strip().lower()
            if query["sslmode"] in ("verify-ca", "verify-full") and settings.DB_SSL_ROOT_CERT:
                query["sslrootcert"] = settings.DB_SSL_ROOT_CERT
        driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
        url = URL.create(
            drivername=driver,
            username=settings.DB_USER,
            password=settings.DB_PASSWORD,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
            query=query,
        )
        # ⚠️ 禁用 str(url)：SQLAlchemy 2.0 的 str(URL) 会把密码掩码为 ***（防泄漏），
        # 引擎会拿到字面 *** 密码导致认证失败（本地 PG 实测抓出）；必须用
        # render_as_string(hide_password=False) 取真实凭据 URL
        return url.render_as_string(hide_password=False)
    suffix = "+aiosqlite" if async_driver else ""
    return f"sqlite{suffix}:///{settings.DATABASE_PATH}"


def _sync_engine_kwargs() -> Dict[str, Any]:
    """同步引擎参数：按方言分发，SQLite 路径与历史版本零差异（契约 §2.2）。"""
    if DIALECT == "postgresql":
        return {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_pre_ping": True,
            "echo": settings.DB_ECHO,
        }
    # SQLite：单文件库不支持真正的连接池，保持 NullPool + timeout=15（历史行为）
    return {
        "connect_args": {"check_same_thread": False, "timeout": 15},
        "poolclass": NullPool,
    }


SQLALCHEMY_DATABASE_URL = build_database_url()

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_sync_engine_kwargs())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _apply_sqlite_pragmas(dbapi_conn, conn_record):  # noqa: ANN001 - SQLAlchemy 事件回调签名
    """对每个新建的 SQLite 连接强制下发并发优化 PRAGMA。

    - journal_mode=WAL：写前日志，读写并发能力远超默认的 rollback journal（WAL 为数据库文件级持久属性，重复设置无害）。
    - synchronous=NORMAL：WAL 下足够安全且更快（默认 FULL 会每笔事务 fsync）。
    - busy_timeout=15000ms：遇到写锁时最多等待 15s，缓解多任务并发写时的 "database is locked"。
      （主修复后锁竞争窗口已极短：db_write_scope 串行化写者，二级兜底 15s 对齐前端 axios timeout=20s；
       若压测显示误触 SQLITE_BUSY 可回退 30s。）
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()
    install_sqlite_search_functions(dbapi_conn)
    install_orphan_folder_functions(dbapi_conn)


# 挂到同步引擎：每个新连接建立时执行 PRAGMA
# 挂到同步引擎：每个新连接建立时执行 PRAGMA（仅 SQLite 方言；PG 无 PRAGMA 机制，契约 §2）
if DIALECT == "sqlite":
    event.listens_for(engine, "connect")(_apply_sqlite_pragmas)

# ========== 异步数据库引擎配置 ==========
# 异步数据库URL（sqlite 用 aiosqlite 驱动；postgresql 用 asyncpg 驱动）
ASYNC_SQLALCHEMY_DATABASE_URL = build_database_url(async_driver=True)

# 创建异步引擎（契约 §2.2：PG 用默认 AsyncAdaptedQueuePool——普通 QueuePool 不兼容 asyncio）
# SQLite 路径与历史行为一致（NullPool + timeout=15 + PRAGMA 事件）。
if DIALECT == "postgresql":
    async_engine = create_async_engine(
        ASYNC_SQLALCHEMY_DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        echo=settings.DB_ECHO,
        connect_args=_pg_ssl_args(async_driver=True),
    )
else:
    async_engine = create_async_engine(
        ASYNC_SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=NullPool,
        echo=False,
    )

# 异步引擎需 listen 到其底层 sync_engine 的 connect 事件（直接 listen async_engine 不生效）
# 自定义搜索/分组函数仅存在于 SQLite 方言；PG 使用原生 SQL 能力（P2 清扫）
if DIALECT == "sqlite":
    event.listens_for(async_engine.sync_engine, "connect")(_apply_sqlite_pragmas)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
)

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM 声明基类（2.0 类式写法；等价于旧 declarative_base()，但对 mypy 合法）"""


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
    初始化数据库初始数据（seed）。

    四轨治理后职责收敛：
    1. 启用 WAL 模式提升并发性能
    2. 添加默认管理员账户（如果不存在）
    3. 设置默认配置（如果不存在）
    4. 初始化默认模板/定时任务/关键词/通知

    注意：表结构创建由 Alembic 迁移负责（migrate_database），本函数不再调用
    Base.metadata.create_all。调用方必须先完成迁移再调用 init_db。
    """
    db_file = settings.DATABASE_PATH

    # 导入 seed 逻辑依赖的模型（这些 import 也确保模型注册到 Base.metadata）
    from app.auth.models import User, LoginLog, Config  # noqa: F401 - 导入即注册 ORM 模型
    from app.downloader.models import BtDownloaders  # noqa: F401 - 导入即注册 ORM 模型
    from app.torrents.models import TorrentInfo  # noqa: F401 - 导入即注册 ORM 模型
    from app.torrents.models import TrackerInfo  # noqa: F401 - 导入即注册 ORM 模型
    from app.torrents.audit_models import TorrentAuditLog  # noqa: F401 - 导入即注册 ORM 模型
    from app.tasks.models import TaskLogs  # noqa: F401 - 导入即注册 ORM 模型
    from app.tasks.cron_models import CronTask  # 必须导入，TaskLogs有外键引用cron_task表
    from app.models.setting_templates import SettingTemplate  # noqa: F401 - 导入即注册 ORM 模型
    from app.models.torrent_tags import TorrentTag, TorrentTagRelation  # noqa: F401 - 导入即注册 ORM 模型
    from app.models.notification import Notification  # 通知中心

    # 表结构由 Alembic 迁移管理（migrate_database），不再用 create_all 兜底。
    # create_all 无法表达 ALTER（字段变更），且会掩盖迁移遗漏（开发能跑生产崩）。

    # 启用 WAL 模式（Write-Ahead Logging）—— 仅 SQLite 方言；PG 由服务端自管（契约 §1）
    if DIALECT == "sqlite":
        try:
            import sqlite3

            db_file = settings.DATABASE_PATH
            conn = sqlite3.connect(db_file)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")  # 平衡安全性和性能
            conn.close()
            logger.info("SQLite WAL 模式已启用，并发性能提升")
        except Exception as e:
            logger.warning(f"启用 WAL 模式失败: {str(e)}")

    # 迁移系统已升级为 Alembic
    # 旧迁移系统（app.migrations.database_migrator）已弃用，所有迁移由 Alembic 管理
    # Alembic 迁移在 migrate_database() 中自动执行（由 lifespan 调用）
    # 历史迁移记录：
    # - field_types_migration_v1 (字段类型)
    # - delete_logic_migration_v1 (删除逻辑)
    # - encryption_migration_v1 (加密字段)
    # - keyword_type_pools_migration_v1 (关键词池)
    # - add_torrent_progress_column_v1 (进度字段)
    # 以上迁移已在生产数据库完成，新数据库由 Alembic 处理

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
                # 首次登录强制改密（安全修复 W9）：默认口令不得长期留存
                must_change_password=True,
                two_factor_secret=twofactor_secret,
            )
            db.add(admin_user)
            logger.info("Default admin user created")
            print("Default admin user created (username: admin, initial password must be changed at first login)")
        elif not getattr(admin_exists, "must_change_password", False):
            # 存量部署升级路径：admin 仍在使用默认口令 → 标记强制改密
            # （幂等：一旦改密或已标记则不再触发）
            from app.auth.security import verify_password

            try:
                if verify_password("admin", admin_exists.password):
                    admin_exists.must_change_password = True
                    logger.warning("检测到 admin 仍使用默认密码，已标记强制改密")
            except Exception as e:
                logger.warning(f"默认口令检测失败（跳过强制改密标记）: {e}")

        # 添加默认配置
        cookie_expire_config = db.query(Config).filter(Config.key == "cookie_expire_minutes").first()
        if not cookie_expire_config:
            logger.info("Adding default configuration...")
            print("Adding default configuration...")
            cookie_config = Config(
                key="cookie_expire_minutes", value="30", description="Cookie expiration time in minutes"
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

    # 初始化系统预设搜索模板（v1.0.5 查询模板系统）
    try:
        from app.data.default_search_templates import init_default_search_templates

        db = SessionLocal()
        init_default_search_templates(db)
        db.close()
    except Exception as e:
        logger.error(f"Error initializing default search templates: {str(e)}")
        print(f"Error initializing default search templates: {str(e)}")

    # 初始化系统默认定时任务（增量检查：添加缺失的任务）
    try:
        from app.data.default_scheduled_tasks import get_default_scheduled_tasks

        db = SessionLocal()
        try:
            # 获取所有配置的任务代码
            default_tasks = get_default_scheduled_tasks()
            default_codes = {t["task_code"] for t in default_tasks}

            # 查询数据库中已有的任务代码
            existing_codes = {t.task_code for t in db.query(CronTask.task_code).all()}

            # 计算缺失的任务
            missing_codes = default_codes - existing_codes

            if missing_codes:
                logger.info(f"发现缺失的定时任务: {missing_codes}，执行增量初始化...")
                print(f"发现缺失的定时任务: {missing_codes}，执行增量初始化...")

                # 重新调用初始化函数，只创建缺失的任务
                from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS
                from datetime import datetime

                for task_data in DEFAULT_SCHEDULED_TASKS:
                    if task_data["task_code"] in missing_codes:
                        task = CronTask(
                            task_name=task_data["task_name"],
                            task_code=task_data["task_code"],
                            task_status=task_data["task_status"],
                            task_type=task_data["task_type"],
                            executor=task_data["executor"],
                            enabled=task_data["enabled"],
                            last_execute_time=task_data["last_execute_time"],
                            last_execute_duration=task_data["last_execute_duration"],
                            cron_plan=task_data["cron_plan"],
                            description=task_data["description"],
                            timeout_seconds=task_data["timeout_seconds"],
                            max_retry_count=task_data["max_retry_count"],
                            retry_interval=task_data["retry_interval"],
                            dr=0,
                            create_time=datetime.now(),
                            update_time=datetime.now(),
                            create_by=task_data["create_by"],
                            update_by=task_data["update_by"],
                        )
                        db.add(task)
                        logger.info(f"创建定时任务: {task_data['task_name']} ({task_data['task_code']})")
                        print(f"创建定时任务: {task_data['task_name']} ({task_data['task_code']})")

                db.commit()
                logger.info(f"增量初始化完成，共添加 {len(missing_codes)} 个任务")
                print(f"增量初始化完成，共添加 {len(missing_codes)} 个任务")
            else:
                logger.info(f"定时任务数据完整（{len(existing_codes)}条），跳过初始化")
                print(f"定时任务数据完整（{len(existing_codes)}条），跳过初始化")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error initializing default scheduled tasks: {str(e)}")
        print(f"Error initializing default scheduled tasks: {str(e)}")

    # 初始化Tracker关键词池默认数据（增量检查：添加缺失的关键词）
    try:
        from app.data.default_tracker_keywords import init_default_tracker_keywords

        db = SessionLocal()
        try:
            init_default_tracker_keywords(db)
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error initializing default tracker keywords: {str(e)}")
        print(f"Error initializing default tracker keywords: {str(e)}")

    # 初始化默认通知（欢迎通知、版本更新通知，幂等操作）
    try:
        db = SessionLocal()
        try:
            # 欢迎通知
            welcome_exists = db.query(Notification).filter(Notification.title == "欢迎使用 BtDeck").first()
            if not welcome_exists:
                db.add(
                    Notification(
                        type="system",
                        title="欢迎使用 BtDeck",
                        content="感谢您使用 BtDeck！这是您的第一条系统通知。通知中心会在这里显示版本更新和系统消息。",
                        priority="info",
                        is_read=False,
                    )
                )
                db.commit()
                logger.info("欢迎通知创建成功")
                print("[OK] 欢迎通知创建成功")

            # 版本更新通知由 lifecycle.py 中的 add_version_update_notification_task 统一处理
            # 这里不再创建，避免重复

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error initializing default notifications: {str(e)}")
        print(f"Error initializing default notifications: {str(e)}")


def init_config_file(
    config_path: str = settings.YAML_PATH, custom_config: Optional[Dict[str, Any]] = None, overwrite: bool = False
) -> bool:
    try:
        # 确保配置文件目录存在
        config_dir = os.path.dirname(config_path)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            logging.info(f"创建配置目录: {config_dir}")

        login_status_secret = str(func.random_hex(16))
        sm4Key = str(func.random_hex(16))
        jwt_secret_key = str(func.random_hex(32))

        # 检查文件是否已存在
        if os.path.exists(config_path) and not overwrite:
            logging.info(f"配置文件 {config_path} 已存在，仅更新安全密钥。")
            try:
                with open(config_path, "r", encoding="utf-8") as f:
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

                # 升级路径修复：旧版本升级上来的 config.yaml 永远不会被补
                # login_status_secret，登录端点直取该键 KeyError → 登录 500。
                # 缺失才补、不轮换已有值（轮换会使全部存量 access token 失效）
                if "login_status_secret" not in new_config["security"]:
                    new_config["security"]["login_status_secret"] = login_status_secret
                    logging.warning("配置文件中缺少login_status_secret，已添加。")

                # JWT 签名密钥持久化：SECRET_KEY 环境变量缺省时从 config.yaml
                # 回退读取，容器重启不再杀死全部会话。同样缺失才补——示例配置
                # 文件不得携带具体值，否则公开已知密钥会被"缺失才补"语义沿用
                if "jwt_secret_key" not in new_config["security"]:
                    new_config["security"]["jwt_secret_key"] = jwt_secret_key
                    logging.warning("配置文件中缺少jwt_secret_key，已添加。")

                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

                return True
            except Exception as read_error:
                logging.error(f"读取或更新现有配置文件失败: {str(read_error)}")
                # 如果读取现有文件失败，继续创建新文件
                overwrite = True

        # 默认配置
        default_config = {
            "app": {"name": "MyApplication", "version": "1.0.0", "debug": False, "log_level": "INFO"},
            "database": {
                "host": "localhost",
                "port": 3306,
                "username": "user",
                "password": "password",
                "database": "mydb",
                "charset": "utf8mb4",
                "pool_size": 5,
            },
            "server": {"host": "0.0.0.0", "port": 8000, "workers": 4, "timeout": 60},
            "security": {
                "secret_key": sm4Key,
                "token_expire_minutes": 60,
                "algorithm": "HS256",
                "login_status_secret": login_status_secret,
                "jwt_secret_key": jwt_secret_key,
            },
            "cors": {"allowed_origins": ["*"], "allowed_methods": ["*"], "allowed_headers": ["*"]},
            "logging": {"file": "app.log", "max_size_mb": 10, "backup_count": 5},
        }

        # 合并自定义配置
        if custom_config:
            merge_configs(default_config, custom_config)

        # 写入配置文件
        with open(config_path, "w", encoding="utf-8") as f:
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
