"""PG squash 基线初始化（v1.0.8 双数据库架构，契约 docs/postgresql-contract.md §3）。

演进式建库策略的唯一实现，供两处合法入口复用（契约 §3 规则 6）：
1. 应用启动 ``migrate_database()``（app/core/migration.py）
2. 迁移管线服务（database-migration-ui W1，app/services/db_migration/ + CLI 薄壳）

核心保证：
- 空库判定：无 ``alembic_version`` **且无业务表**（规则 1；有表无版本 fail-fast）
- 原子性：``create_all + stamp`` 在同一连接同一事务内完成（规则 3）——
  外部连接经 ``Config.attributes["connection"]`` 传入（Alembic Cookbook
  连接共享方式），env.py 优先复用该连接；PG 事务性 DDL 保证中途失败整体回滚
- 不 seed、不启动任务（目标库三状态规则之"全新数据库"）
- "导入未完成"状态标记（三状态规则之"本次导入未完成"）：标记表
  ``_btdeck_import_state`` 由迁移工具写入/清除，应用启动遇标记拒绝启动

database-migration-ui W1-2 增量（PLANS/database-migration-ui.md §3.2/§3.3）：
- 引擎显式参数化：``initialize_pg_baseline(engine=...)`` 接受冻结快照/显式
  目标引擎，不再隐式只读全局配置；入口方言强断言（T14：误收 SQLite 引擎
  在任何 DDL 之前拒绝）
- 基线同事务生成目标库**自己的** identity（普通新装也有身份；导入不可复制源）；
  仅当携带完整 ``ownership``（迁移基线）才同事务写 IMPORTING receipt+初始 marker
- receipt 协议操作（读/核对/finalize/状态标记）：finalize 在同一事务把既有
  IMPORTING receipt 更新为 VERIFIED 并清未完成标记；分离于会被 DROP 的 marker
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Mapping, Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

from app.core.database_protocol import (
    DIGEST_VERSION_CANONICAL_V1,
    IDENTITY_TABLE,
    IMPORT_MARKER_TABLE,
    OPERATION_KINDS,
    PROTOCOL_SCHEMA_VERSION,
    PROTOCOL_TABLE_NAMES,
    RECEIPT_STATUS_ABANDONED,
    RECEIPT_STATUS_IMPORTING,
    RECEIPT_STATUS_STALE,
    RECEIPT_STATUS_VERIFIED,
    RECEIPT_TABLE,
    is_valid_attempt_id,
)
from app.database import build_database_url

logger = logging.getLogger(__name__)

# 导入状态标记表（P4 迁移工具消费；表名下划线开头区分于业务表）。
# database-migration-ui W1-3 起常量归位 database_protocol（纯模块，引导层可消费）
IMPORT_STATE_TABLE = IMPORT_MARKER_TABLE
PG_MINIMUM_REVISION = "c9e0f1a2b3c4"


def pg_sync_engine() -> Engine:
    """构造 PG 同步引擎（psycopg2；基线/版本读取/迁移工具专用，NullPool 用后即弃）。"""
    return create_engine(build_database_url(), poolclass=NullPool)


def validate_pg_server(conn: Connection) -> None:
    """拒绝契约范围外的 PostgreSQL 版本。"""
    if conn.dialect.name == "postgresql" and (conn.dialect.server_version_info or ()) < (16,):
        raise RuntimeError("BtDeck PostgreSQL 数据源要求服务器版本 16 或更高")


def _is_alembic_versioned(conn: Connection) -> bool:
    insp = inspect(conn)
    return insp.has_table("alembic_version")


def _business_table_names(conn: Connection) -> list[str]:
    """业务表 = 非 PG 系统表、非 alembic_version、非导入状态标记表、非协议元数据表。

    schema 按方言感知：PG 用 public（排除 pg_catalog 系统表）；其他方言
    （单测 SQLite 替身）用默认 schema。协议三表（bt_database_identity/
    bt_database_migration_receipt/events，database-migration-ui W1-1）不参与
    业务导入/摘要；**未知对象仍拒绝**——不是忽略所有 ``_btdeck_*``。
    """
    insp = inspect(conn)
    schema = "public" if conn.dialect.name == "postgresql" else None
    names = insp.get_table_names(schema=schema) if schema else insp.get_table_names()
    ignored = {"alembic_version", IMPORT_STATE_TABLE} | set(PROTOCOL_TABLE_NAMES)
    return [t for t in names if t not in ignored]


def read_pg_alembic_version(conn: Connection) -> Optional[str]:
    """读取 PG 库 alembic_version；无表返回 None（连接异常由调用方处理）。"""
    if not _is_alembic_versioned(conn):
        return None
    revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    if len(revisions) > 1:
        raise RuntimeError("PG alembic_version 含多个版本，拒绝自动迁移")
    return revisions[0] if revisions else None


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


# ============================================================================
# 协议元数据操作（database-migration-ui W1-2，PLANS §3.2/§3.3）
# 均为方言中立的 Core 语句，可经 SQLite 替身单测事务语义；方言准入由
# ``assert_postgresql_target`` 在入口把关（PG 专用链路）。协议表本身由
# Alembic revision e9f0a1b2c3d4 / 基线 create_all 创建，此处不建表。
# ============================================================================


def assert_postgresql_target(target: Any) -> None:
    """PG 专用链路的方言强断言（T14）：在任何 DDL/协议写入之前拒绝非 PG 引擎。

    防止显式参数化误把 SQLite 引擎（或未来其他方言）传入 PG 专用初始化后
    静默建错对象；调用时机必须在首个副作用之前。
    """
    name = getattr(getattr(target, "dialect", None), "name", "")
    if name != "postgresql":
        raise RuntimeError(
            f"PostgreSQL 专用初始化收到非 postgresql 引擎（{name!r}）："
            "已在任何 DDL 之前拒绝（database-migration-ui T14）"
        )


def ensure_database_identity(conn: Connection) -> str:
    """同事务确保库身份单例存在；返回 database_id（幂等：已有则返回原值，绝不重生成）。

    - 身份由 revision/基线事务创建，运行期只读（禁止 FROZEN 后补 seed）；
    - 目标库生成**自己的** identity，不从源复制（§3.2）。
    """
    row = conn.execute(text(f"SELECT database_id FROM {IDENTITY_TABLE}")).first()
    if row is not None:
        return str(row[0])
    database_id = str(uuid.uuid4())
    conn.execute(
        text(
            f"INSERT INTO {IDENTITY_TABLE} (id, database_id, schema_version, created_at) " "VALUES (1, :dbid, :sv, :ca)"
        ),
        {"dbid": database_id, "sv": PROTOCOL_SCHEMA_VERSION, "ca": datetime.utcnow()},
    )
    return database_id


def read_database_identity(conn: Connection) -> Optional[str]:
    """读取库身份；无身份表/无行返回 None（不创建）。"""
    insp = inspect(conn)
    if not insp.has_table(IDENTITY_TABLE):
        return None
    row = conn.execute(text(f"SELECT database_id FROM {IDENTITY_TABLE}")).first()
    return str(row[0]) if row else None


def _validate_ownership(ownership: Mapping[str, Any]) -> dict[str, Any]:
    """校验迁移基线 ownership 请求字段（§3.3：首表导入前即有完整凭据）。"""
    required = (
        "attempt_id",
        "operation_kind",
        "target_database_id",
        "ownership_nonce",
        "revision_at_import",
        "schema_fingerprint",
        "origin_epoch",
        "eligible_epoch",
    )
    missing = [k for k in required if not ownership.get(k)]
    if missing:
        raise RuntimeError(f"ownership 请求缺少必填字段: {missing}")
    if not is_valid_attempt_id(str(ownership["attempt_id"])):
        raise RuntimeError(f"attempt_id 形态非法: {ownership['attempt_id']!r}（前缀+UUID，防路径穿越）")
    if ownership["operation_kind"] not in OPERATION_KINDS:
        raise RuntimeError(f"operation_kind 非法: {ownership['operation_kind']!r}")
    return {k: ownership.get(k) for k in (*required, "source_database_id", "deployment_id")}


def insert_importing_receipt(conn: Connection, ownership: Mapping[str, Any]) -> None:
    """同事务插入 IMPORTING receipt（首表导入前的 ownership 凭据）。

    要求 ``ensure_database_identity`` 已在同一事务执行（target_database_id
    必须是目标自身身份，由调用方保证）；attempt_id 冲突（重复导入）拒绐。
    """
    fields = _validate_ownership(ownership)
    now = datetime.utcnow()
    exists = conn.execute(
        text(f"SELECT 1 FROM {RECEIPT_TABLE} WHERE attempt_id = :a"), {"a": fields["attempt_id"]}
    ).first()
    if exists:
        raise RuntimeError(f"receipt 已存在（attempt_id={fields['attempt_id']}）：拒绝重复创建导入凭据")
    conn.execute(
        text(
            f"INSERT INTO {RECEIPT_TABLE} (attempt_id, operation_kind, source_database_id, "
            "target_database_id, deployment_id, ownership_nonce, revision_at_import, digest_version, "
            "schema_fingerprint, origin_epoch, eligible_epoch, status, created_at, updated_at) "
            "VALUES (:attempt_id, :operation_kind, :source_database_id, :target_database_id, "
            ":deployment_id, :ownership_nonce, :revision_at_import, :digest_version, "
            ":schema_fingerprint, :origin_epoch, :eligible_epoch, :status, :created_at, :updated_at)"
        ),
        {
            **fields,
            "digest_version": ownership.get("digest_version") or DIGEST_VERSION_CANONICAL_V1,
            "status": RECEIPT_STATUS_IMPORTING,
            "created_at": now,
            "updated_at": now,
        },
    )


def read_receipt(conn: Connection, attempt_id: str) -> Optional[dict[str, Any]]:
    """读取 receipt 为 dict（JSON 列解析；无行返回 None）。"""
    insp = inspect(conn)
    if not insp.has_table(RECEIPT_TABLE):
        return None
    row = conn.execute(
        text(
            f"SELECT attempt_id, operation_kind, source_database_id, target_database_id, deployment_id, "
            f"ownership_nonce, revision_at_import, digest_version, table_counts, table_digests, "
            f"schema_fingerprint, origin_epoch, eligible_epoch, status, activation_generation, "
            f"activated_at FROM {RECEIPT_TABLE} WHERE attempt_id = :a"
        ),
        {"a": attempt_id},
    ).first()
    if row is None:
        return None
    result = dict(row._mapping)
    for key in ("table_counts", "table_digests"):
        raw = result.get(key)
        if isinstance(raw, str):
            try:
                result[key] = json.loads(raw)
            except (TypeError, ValueError):
                result[key] = None
    return result


def verify_receipt_ownership(
    conn: Connection,
    attempt_id: str,
    *,
    ownership_nonce: str,
    target_database_id: str,
    operation_kind: Optional[str] = None,
) -> dict[str, Any]:
    """核对 ownership：attempt 存在、nonce/目标身份（及操作类型）匹配，返回 receipt dict。

    复制旧 marker、相同 head 或相同源摘要均不构成授权（§3.1）——
    nonce 与目标 database_id 不符即拒绝。
    """
    receipt = read_receipt(conn, attempt_id)
    if receipt is None:
        raise RuntimeError(f"receipt 不存在（attempt_id={attempt_id}）：无本次导入凭据")
    if receipt["ownership_nonce"] != ownership_nonce:
        raise RuntimeError("ownership_nonce 不匹配：拒绝（复制/伪造凭据不构成授权）")
    if receipt["target_database_id"] != target_database_id:
        raise RuntimeError(
            f"目标 database_id 不匹配（receipt={receipt['target_database_id']} 预期={target_database_id}）：拒绝"
        )
    if operation_kind is not None and receipt["operation_kind"] != operation_kind:
        raise RuntimeError(f"operation_kind 不匹配（receipt={receipt['operation_kind']} 预期={operation_kind}）：拒绝")
    return receipt


def finalize_receipt_verified(
    conn: Connection,
    attempt_id: str,
    *,
    table_counts: Mapping[str, int],
    table_digests: Mapping[str, str],
    schema_fingerprint: str,
    eligible_epoch: Optional[str] = None,
) -> None:
    """finalize：同一事务将既有 IMPORTING receipt 更新为 VERIFIED 并清除导入标记（§3.3）。

    - receipt 不存在或状态非 IMPORTING → RuntimeError（半成品/重复 finalize 拒绝）；
    - 事务性：调用方事务失败则 receipt 更新与标记清除一并回滚（仍是半成品）；
    - ``eligible_epoch`` 可选更新（重绑协议 CAS 由 W2 manager 接线，此处仅原子落盘）。
    """
    receipt = read_receipt(conn, attempt_id)
    if receipt is None:
        raise RuntimeError(f"receipt 不存在（attempt_id={attempt_id}）：无法 finalize 无凭据产物")
    if receipt["status"] != RECEIPT_STATUS_IMPORTING:
        raise RuntimeError(f"receipt 状态为 {receipt['status']}（非 IMPORTING）：拒绝重复/降级 finalize")
    epoch_expr = ":eligible_epoch" if eligible_epoch is not None else "eligible_epoch"
    params: dict[str, Any] = {
        "a": attempt_id,
        "counts": json.dumps(dict(table_counts), ensure_ascii=False),
        "digests": json.dumps(dict(table_digests), ensure_ascii=False),
        "fp": schema_fingerprint,
        "now": datetime.utcnow(),
    }
    if eligible_epoch is not None:
        params["eligible_epoch"] = eligible_epoch
    conn.execute(
        text(
            f"UPDATE {RECEIPT_TABLE} SET status = :verified, table_counts = :counts, "
            f"table_digests = :digests, schema_fingerprint = :fp, eligible_epoch = {epoch_expr}, "
            "updated_at = :now WHERE attempt_id = :a AND status = :importing"
        ),
        {**params, "verified": RECEIPT_STATUS_VERIFIED, "importing": RECEIPT_STATUS_IMPORTING},
    )
    updated = conn.execute(
        text(f"SELECT status FROM {RECEIPT_TABLE} WHERE attempt_id = :a"), {"a": attempt_id}
    ).scalar()
    if updated != RECEIPT_STATUS_VERIFIED:
        raise RuntimeError("finalize 竞态失败（IMPORTING→VERIFIED 未生效）：保持半成品状态")
    clear_import_state(conn)


def mark_receipt_status(
    conn: Connection, attempt_id: str, status: str, *, eligible_epoch: Optional[str] = None
) -> None:
    """将 receipt 标记为失效态（STALE/ABANDONED）；epoch 撤销同事务落盘。

    禁止经此函数伪造 VERIFIED/ACTIVATED/IMPORTING（各有专属原子路径）。
    """
    if status not in (RECEIPT_STATUS_STALE, RECEIPT_STATUS_ABANDONED):
        raise RuntimeError(f"mark_receipt_status 仅接受 STALE/ABANDONED，收到 {status!r}")
    epoch_expr = ":eligible_epoch" if eligible_epoch is not None else "eligible_epoch"
    params: dict[str, Any] = {"a": attempt_id, "status": status, "now": datetime.utcnow()}
    if eligible_epoch is not None:
        params["eligible_epoch"] = eligible_epoch
    result = conn.execute(
        text(
            f"UPDATE {RECEIPT_TABLE} SET status = :status, eligible_epoch = {epoch_expr}, "
            "updated_at = :now WHERE attempt_id = :a"
        ),
        params,
    )
    if result.rowcount == 0:
        raise RuntimeError(f"receipt 不存在（attempt_id={attempt_id}）：无法标记 {status}")


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
    if read_pg_alembic_version(conn) is None:
        raise RuntimeError(
            "PG 空库或缺少有效版本记录，禁止手工 alembic upgrade（会重放 SQLite 专属历史链）。"
            "请通过应用启动（migrate_database）或 SQLite→PG 迁移工具初始化"
            "（契约 docs/postgresql-contract.md §3 规则 6）。"
        )


def initialize_pg_baseline(
    cfg: Config,
    head: str,
    *,
    engine: Optional[Engine] = None,
    import_state: Optional[dict[str, Any]] = None,
    ownership: Optional[Mapping[str, Any]] = None,
) -> bool:
    """PG 空库基线初始化：单事务 create_all + stamp（契约 §3 规则 1/2/3）。

    database-migration-ui W1-2：
    - ``engine``：显式目标引擎（冻结快照/显式连接）；缺省回退 ``pg_sync_engine()``。
      任何引擎在任何 DDL 之前经 ``assert_postgresql_target`` 强断言（T14）。
    - 基线事务内初始化目标库**自己的** identity（普通新装也有身份）；
      携带 ``ownership``（迁移基线）时同事务插入 IMPORTING receipt（首表导入前
      即持久凭据，§3.3），再写初始导入标记（``import_state``）。

    Returns:
        True = 执行了基线初始化；False = 库非空（调用方走正常 upgrade 或报错）。

    Raises:
        RuntimeError: 有业务表但无版本（规则 1 fail-fast，人工介入）；
                      存在"导入未完成"标记（应用不得启动，契约三状态规则）；
                      目标引擎非 PostgreSQL（T14 方言强断言）。
    """
    from app.core.model_registry import register_all_models
    from app.database import Base

    register_all_models()

    target = engine if engine is not None else pg_sync_engine()
    # T14：方言强断言在任何 DDL 之前（含状态检查后的 create_all）
    assert_postgresql_target(target)
    try:
        with target.connect() as conn:
            validate_pg_server(conn)
            versioned = _is_alembic_versioned(conn)
            business_tables = _business_table_names(conn)
            existing_import = get_import_state(conn)

            if existing_import is not None:
                raise RuntimeError(
                    "检测到 SQLite→PG 导入未完成标记"
                    f"（migration_id={existing_import['migration_id']}）。"
                    "应用拒绝启动以防后台任务修改半成品数据；"
                    "请重跑迁移工具恢复导入，或在其校验失败时人工处理（契约 §3 三状态规则）。"
                )
            if versioned:
                if read_pg_alembic_version(conn) is None:
                    raise RuntimeError("PG alembic_version 为空，拒绝自动迁移；请人工核验数据库状态")
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
                try:
                    command.stamp(cfg, head)
                    # 目标库自己的身份（同事务；普通新装与迁移基线均生成，
                    # 幂等：已有则原值返回，绝不重生成——§3.2）
                    database_id = ensure_database_identity(conn)
                    if ownership is not None:
                        # 迁移基线：首表导入前即持久 ownership 凭据（§3.3）。
                        # target_database_id 由基线注入刚生成的目标自身身份——
                        # 调用方无法预知同事务生成的 UUID，也禁止指向其他库
                        insert_importing_receipt(conn, {**dict(ownership), "target_database_id": database_id})
                    if import_state is not None:
                        set_import_state(conn, **import_state)
                finally:
                    cfg.attributes.pop("connection", None)
            cfg.attributes.pop("btdeck_baseline_stamp", None)
            logger.info("PG 基线初始化完成（单事务提交）")
            return True
    finally:
        cfg.attributes.pop("btdeck_baseline_stamp", None)
        target.dispose()


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
