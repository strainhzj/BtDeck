"""PG squash 基线初始化（v1.0.8 双数据库架构，契约 docs/postgresql-contract.md §3）。

演进式建库策略的唯一实现，供两处合法入口复用（契约 §3 规则 6）：
1. 应用启动 ``migrate_database()``（app/core/migration.py）
2. SQLite→PG 迁移工具（P4，backend/scripts/migrate_sqlite_to_pg.py）

核心保证：
- 空库判定：无 ``alembic_version`` **且无业务表**（规则 1；有表无版本 fail-fast）
- 原子性：``create_all + stamp`` 在同一连接同一事务内完成（规则 3）——
  外部连接经 ``Config.attributes["connection"]`` 传入（Alembic Cookbook
  连接共享方式），env.py 优先复用该连接；PG 事务性 DDL 保证中途失败整体回滚
- 不 seed、不启动任务（目标库三状态规则之"全新数据库"）
- "导入未完成"状态标记（三状态规则之"本次导入未完成"）：标记表
  ``_btdeck_import_state`` 由迁移工具写入/清除，应用启动遇标记拒绝启动
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from app.database import build_database_url

logger = logging.getLogger(__name__)

# 导入状态标记表（P4 迁移工具消费；表名下划线开头区分于业务表）
IMPORT_STATE_TABLE = "_btdeck_import_state"


def pg_sync_engine() -> Engine:
    """构造 PG 同步引擎（psycopg2；基线/版本读取/迁移工具专用，NullPool 用后即弃）。"""
    return create_engine(build_database_url(), poolclass=NullPool)


def _is_alembic_versioned(conn: Connection) -> bool:
    insp = inspect(conn)
    return insp.has_table("alembic_version")


def _business_table_names(conn: Connection) -> list[str]:
    """业务表 = 非 PG 系统表、非 alembic_version、非导入状态标记表。

    schema 按方言感知：PG 用 public（排除 pg_catalog 系统表）；其他方言
    （单测 SQLite 替身）用默认 schema。
    """
    insp = inspect(conn)
    schema = "public" if conn.dialect.name == "postgresql" else None
    names = insp.get_table_names(schema=schema) if schema else insp.get_table_names()
    ignored = {"alembic_version", IMPORT_STATE_TABLE}
    return [t for t in names if not t.startswith("pg_") and t not in ignored]


def read_pg_alembic_version(conn: Connection) -> Optional[str]:
    """读取 PG 库 alembic_version；无表返回 None（连接异常由调用方处理）。"""
    if not _is_alembic_versioned(conn):
        return None
    row = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return row


def get_import_state(conn: Connection) -> Optional[dict[str, Any]]:
    """读取"导入未完成"标记；无标记表/无行返回 None。"""
    insp = inspect(conn)
    if not insp.has_table(IMPORT_STATE_TABLE):
        return None
    row = conn.execute(
        text(f"SELECT migration_id, source_digest, tool_version, checkpoint " f"FROM {IMPORT_STATE_TABLE} LIMIT 1")
    ).first()
    if row is None:
        return None
    checkpoint = row.checkpoint
    if isinstance(checkpoint, str):
        try:
            checkpoint = json.loads(checkpoint)
        except (TypeError, ValueError):
            checkpoint = {"raw": checkpoint}
    return {
        "migration_id": row.migration_id,
        "source_digest": row.source_digest,
        "tool_version": row.tool_version,
        "checkpoint": checkpoint,
    }


def set_import_state(
    conn: Connection, migration_id: str, source_digest: str, tool_version: str, checkpoint: dict
) -> None:
    """写入/更新导入状态标记（P4 迁移工具调用；单行表，先清后写）。"""
    conn.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {IMPORT_STATE_TABLE} ("
            "migration_id VARCHAR(64) NOT NULL, "
            "source_digest VARCHAR(128) NOT NULL, "
            "tool_version VARCHAR(32) NOT NULL, "
            "checkpoint TEXT NOT NULL)"
        )
    )
    conn.execute(text(f"DELETE FROM {IMPORT_STATE_TABLE}"))
    conn.execute(
        text(
            f"INSERT INTO {IMPORT_STATE_TABLE} (migration_id, source_digest, tool_version, checkpoint) "
            "VALUES (:mid, :digest, :ver, :cp)"
        ),
        {
            "mid": migration_id,
            "digest": source_digest,
            "ver": tool_version,
            "cp": json.dumps(checkpoint, ensure_ascii=False),
        },
    )


def clear_import_state(conn: Connection) -> None:
    """清除导入状态标记（迁移工具成功收尾时调用）。"""
    insp = inspect(conn)
    if insp.has_table(IMPORT_STATE_TABLE):
        conn.execute(text(f"DROP TABLE IF EXISTS {IMPORT_STATE_TABLE}"))


def guard_manual_upgrade_on_empty_db(conn: Connection, *, baseline_flag: bool = False) -> None:
    """PG 空库手工升级守卫（契约 §3 规则 6，任务3.1）。

    PG 空库手工 ``alembic upgrade head`` 会重放 SQLite 专属历史链；合法初始化
    入口仅应用启动（migrate_database）与迁移工具（共享基线函数）两处。
    基线路径以 ``baseline_flag`` 豁免（stamp 不重放迁移）。
    """
    if baseline_flag:
        return
    if conn.dialect.name != "postgresql":
        return
    if not _is_alembic_versioned(conn) and not _business_table_names(conn):
        raise RuntimeError(
            "PG 空库禁止手工 alembic upgrade（会重放 SQLite 专属历史链）。"
            "请通过应用启动（migrate_database）或 SQLite→PG 迁移工具初始化"
            "（契约 docs/postgresql-contract.md §3 规则 6）。"
        )


def initialize_pg_baseline(cfg: Config, head: str) -> bool:
    """PG 空库基线初始化：单事务 create_all + stamp（契约 §3 规则 1/2/3）。

    Returns:
        True = 执行了基线初始化；False = 库非空（调用方走正常 upgrade 或报错）。

    Raises:
        RuntimeError: 有业务表但无版本（规则 1 fail-fast，人工介入）；
                      或存在"导入未完成"标记（应用不得启动，契约三状态规则）。
    """
    from app.core.model_registry import register_all_models
    from app.database import Base

    register_all_models()

    engine = pg_sync_engine()
    try:
        with engine.connect() as conn:
            versioned = _is_alembic_versioned(conn)
            business_tables = _business_table_names(conn)
            import_state = get_import_state(conn)

            if import_state is not None:
                raise RuntimeError(
                    "检测到 SQLite→PG 导入未完成标记"
                    f"（migration_id={import_state['migration_id']}）。"
                    "应用拒绝启动以防后台任务修改半成品数据；"
                    "请重跑迁移工具恢复导入，或在其校验失败时人工处理（契约 §3 三状态规则）。"
                )
            if versioned:
                logger.info("PG 库已有 alembic_version，跳过基线初始化（走增量升级）")
                return False
            if business_tables:
                raise RuntimeError(
                    f"PG 库存在 {len(business_tables)} 张业务表但无 alembic_version"
                    f"（示例：{business_tables[:5]}）。可能为部分建库失败/手工建表/版本表丢失，"
                    "拒绝自动 stamp（契约 §3 规则 1），请人工核验后处理。"
                )

            # 空库：单事务 create_all + stamp（共享连接保证原子性，规则 3）
            logger.info(f"PG 空库：执行 squash 基线初始化（create_all + stamp {head}）")
            # 标记跳过 env.py 的空库手工升级守卫（本调用是合法基线路径）
            cfg.attributes["btdeck_baseline_stamp"] = True
            # 上述状态读取已 autobegin 事务，显式释放后再开启基线事务
            conn.rollback()
            with conn.begin():
                Base.metadata.create_all(conn)
                # command.stamp 复用同一连接（env.py 优先消费 attributes["connection"]）
                cfg.attributes["connection"] = conn
                command.stamp(cfg, head)
                cfg.attributes.pop("connection", None)
            cfg.attributes.pop("btdeck_baseline_stamp", None)
            logger.info("PG 基线初始化完成（单事务提交）")
            return True
    finally:
        engine.dispose()


def read_pg_version_standalone() -> Optional[str]:
    """独立引擎读取 PG alembic_version（供 migrate_database 版本判断；连接失败返回 None 交由后续步骤暴露真实错误）。"""
    try:
        engine = pg_sync_engine()
        try:
            with engine.connect() as conn:
                return read_pg_alembic_version(conn)
        finally:
            engine.dispose()
    except Exception as exc:  # noqa: BLE001 - 连接错误在此吞掉，upgrade 阶段会抛真实异常
        logger.warning(f"读取 PG alembic_version 失败（将在迁移阶段暴露真实错误）: {exc}")
        return None
