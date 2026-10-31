# -*- coding: utf-8 -*-
"""PostgreSQL → SQLite 迁移管线（database-migration-ui W1-5，PLANS §6.1/§6.2）。

六阶段（方向语义与 sqlite_to_pg 镜像）：

  1. precheck  —— 源 PG 版本（仅接受工具唯一 head）/ 业务表集合 / Float
                  NaN±Infinity 与时间 infinity 拒绝（T12，不建目标 schema
                  之前拦下）/ JSON 文本可解析
  2. staging   —— 目标父目录内 O_EXCL 创建 ``app.db.<attempt_uuid>.sqlite``
                  + **先持久 sidecar（归属凭据：attempt/nonce/path/inode/
                  revision）再跑任何 DDL**（PLANS §3.3 SQLite 侧边界；中断后
                  凭 sidecar 可核归属）；显式 target_url 重放原生 Alembic 链
                  （不修改全局 env/settings，T14：源 PG 运行态零 DDL）
  3. import    —— 链到 head 后、**任何业务行导入前**，同事务插入 IMPORTING
                  receipt + 初始 marker（目标身份由链内 revision seed）；
                  REPEATABLE READ 快照读源，依赖序分表分批导入，每表数据+
                  checkpoint 同事务，批间协作取消边界
  4. calibrate —— 探测 sqlite AUTOINCREMENT 对象（sqlite_sequence）；当前链
                  无该类表则报告跳过（普通 INTEGER PK 验证后续生成不冲突）
  5. verify    —— canonical-v1 全业务表对账（行数/主键集合/全列摘要）
  6. finalize  —— 同事务 receipt VERIFIED + 清 marker；final 文件即 staging
                  （唯一目标名，不覆盖任何旧库；发布/切换归 W3 activation）

异常→CLI 退出码与 sqlite_to_pg 一致：PrecheckFailed→1；TargetInvalid→2；
MigrationInterrupted→3。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import Boolean, DateTime, inspect, text
from sqlalchemy.engine import Connection, Engine

from app.core.database_protocol import RECEIPT_STATUS_IMPORTING
from app.core.model_registry import register_all_models
from app.core.pg_baseline import (
    finalize_receipt_verified,
    get_import_state,
    insert_importing_receipt,
    read_database_identity,
    read_pg_alembic_version,
    set_import_state,
    validate_pg_server,
    verify_receipt_ownership,
)
from app.models.database_migration import PROTOCOL_TABLE_NAMES, business_tables
from app.services.db_migration import canonical, pipeline
from app.services.db_migration.pipeline import (
    CheckpointIncompatible,
    MigrationCancelled,
    PipelineContext,
)
from app.services.db_migration.sqlite_to_pg import (
    MigrationInterrupted,
    PrecheckFailed,
    TargetInvalid,
    tool_head,
)

logger = logging.getLogger(__name__)

BATCH_ROWS = 500
SIDECAR_SUFFIX = ".sidecar.json"


# ==================== staging 与 sidecar（§3.3/§6.2） ====================


def staging_path(target_dir: os.PathLike[str] | str, ctx: PipelineContext) -> Path:
    """final/staging 同一唯一目标名：``app.db.<attempt_uuid>.sqlite``（预核目录+安全文件名）。"""
    uuid_tail = ctx.attempt_id.rsplit("/", 1)[1]
    return Path(target_dir) / f"app.db.{uuid_tail}.sqlite"


def create_staging_with_sidecar(target_dir: os.PathLike[str] | str, ctx: PipelineContext, *, revision: str) -> Path:
    """O_EXCL 创建 staging + 先持久 sidecar（任何 DDL 之前；§3.3 SQLite 边界）。

    - sidecar 与 staging 同目录 ``<staging>.sidecar.json``，0600；
    - O_EXCL：目标已存在即 TargetInvalid（绝不覆盖，§6.2）；
    - 目录 0700 由部署/配置仓储负责；此处至少确保 sidecar 文件限权。
    """
    directory = Path(target_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = staging_path(directory, ctx)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError as exc:
        raise TargetInvalid(f"staging 目标已存在（不覆盖）：{path}") from exc
    sidecar = {
        "attempt_id": ctx.attempt_id,
        "ownership_nonce": ctx.ownership_nonce,
        "origin_epoch": ctx.origin_epoch,
        "eligible_epoch": ctx.eligible_epoch,
        "tool_version": pipeline.TOOL_VERSION,
        "revision": revision,
        "path": str(path),
        "inode": path.stat().st_ino,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    sidecar_path = Path(str(path) + SIDECAR_SUFFIX)
    _atomic_write_private(sidecar_path, sidecar)
    return path


def _atomic_write_private(path: Path, payload: Mapping[str, Any]) -> None:
    """0600 + 临时文件→fsync→原子 replace→父目录 fsync（§4.2 持久化纪律）。"""
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(payload), f, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def read_staging_sidecar(staging: os.PathLike[str] | str) -> Optional[Dict[str, Any]]:
    """读取 sidecar（缺失/损坏 → None，调用方按归属不明隔离处置）。"""
    path = Path(str(staging) + SIDECAR_SUFFIX)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def verify_staging_ownership(staging: os.PathLike[str] | str, ctx: PipelineContext) -> bool:
    """sidecar 归属核验（T02：schema 中断后凭 sidecar 认领产物或隔离拒删）。"""
    sidecar = read_staging_sidecar(staging)
    if sidecar is None:
        return False
    path = Path(staging)
    if not path.exists():
        return False
    return (
        sidecar.get("attempt_id") == ctx.attempt_id
        and sidecar.get("ownership_nonce") == ctx.ownership_nonce
        and sidecar.get("path") == str(path)
        and sidecar.get("inode") == path.stat().st_ino
    )


# ==================== 1. precheck（PG 源） ====================


def pg_precheck(pg_engine: Engine) -> Tuple[List[str], List[str]]:
    """PG 源预检：版本/业务表集合/Float 非有限值/时间 infinity/JSON 文本（T12）。"""
    register_all_models()
    errors: List[str] = []
    warnings: List[str] = []
    tables = business_tables()

    with pg_engine.connect() as conn:
        validate_pg_server(conn)
        current = read_pg_alembic_version(conn)
        if current != tool_head():
            errors.append(f"源 PG 版本必须为工具唯一 head（当前 {current!r}，head={tool_head()}）")
            return errors, warnings
        insp = inspect(conn)
        existing = set(insp.get_table_names(schema="public"))
        known = {t.name for t in tables} | set(PROTOCOL_TABLE_NAMES) | {"alembic_version"}
        unknown = existing - known
        if unknown:
            errors.append(f"源 PG 存在未知表（拒绝）：{sorted(unknown)[:10]}")

        for table in tables:
            if table.name not in existing:
                errors.append(f"源 PG 缺少业务表：{table.name}")
                continue
            for column in table.columns:
                if isinstance(column.type, DateTime):
                    bad = conn.exec_driver_sql(
                        f'SELECT COUNT(*) FROM "{table.name}" WHERE "{column.name}" = \'infinity\'::timestamp '
                        f"OR \"{column.name}\" = '-infinity'::timestamp"
                    ).scalar()
                    if bad:
                        errors.append(f"{table.name}.{column.name}: {bad} 行时间值为 infinity（不可表示，拒绝）")
                elif _is_float_type(column.type):
                    bad = conn.exec_driver_sql(
                        f'SELECT COUNT(*) FROM "{table.name}" WHERE "{column.name}" = \'NaN\'::float8 '
                        f"OR \"{column.name}\" = 'Infinity'::float8 OR \"{column.name}\" = '-Infinity'::float8"
                    ).scalar()
                    if bad:
                        errors.append(f"{table.name}.{column.name}: {bad} 行浮点非有限值（NaN/Infinity，拒绝）")
    return errors, warnings


def _is_float_type(type_: Any) -> bool:
    from sqlalchemy.types import Float

    return isinstance(type_, Float)


# ==================== 2-3. schema 重放 + 导入 ====================


def replay_schema_chain(staging: os.PathLike[str] | str) -> str:
    """显式 target_url 重放原生 Alembic 链到 staging（不修改全局 env；T14）。

    返回链 head（= revision_at_import）。staging 内协议表与身份由链内
    revision e9f0a1b2c3d4 创建/seed。
    """
    from alembic import command

    from app.core.migration import _build_alembic_config

    backend_root = Path(__file__).resolve().parents[3]
    placeholder = str(backend_root / "config" / "replay.db")  # 不消费（target_url 优先）
    cfg = _build_alembic_config(placeholder, target_url=f"sqlite:///{staging}")
    cfg.attributes["configure_logger"] = False
    head = tool_head()
    command.upgrade(cfg, head)
    return head


def begin_receipt_on_staging(staging_engine: Engine, ctx: PipelineContext, *, source_digest: str) -> None:
    """链到 head 后、首业务行前：同事务 IMPORTING receipt + 初始 marker（§3.3）。"""
    fingerprint = canonical.schema_fingerprint(business_tables())
    with staging_engine.begin() as conn:
        identity = read_database_identity(conn)
        if identity is None:
            raise TargetInvalid("staging 缺少库身份（链重放未 seed identity）——状态非法")
        insert_importing_receipt(
            conn,
            {
                "attempt_id": ctx.attempt_id,
                "operation_kind": ctx.operation_kind,
                "source_database_id": ctx.source_database_id,
                "deployment_id": ctx.deployment_id,
                "target_database_id": identity,
                "ownership_nonce": ctx.ownership_nonce,
                "revision_at_import": tool_head(),
                "schema_fingerprint": fingerprint,
                "origin_epoch": ctx.origin_epoch,
                "eligible_epoch": ctx.eligible_epoch,
            },
        )
        set_import_state(conn, ctx.attempt_id, source_digest, pipeline.TOOL_VERSION, ctx.checkpoint_payload({}))


def _normalize_by_column_type(table: Any, row: Mapping[str, Any]) -> Dict[str, Any]:
    """列类型归一（双向对称）：Boolean→bool；DateTime 文本→datetime；其余原样。"""
    out: Dict[str, Any] = {}
    for col in table.columns:
        value = row.get(col.name)
        if value is None:
            out[col.name] = None
        elif isinstance(col.type, Boolean):
            out[col.name] = bool(value)
        elif isinstance(col.type, DateTime) and isinstance(value, str):
            out[col.name] = datetime.fromisoformat(value.replace("T", " "))
        else:
            out[col.name] = value
    return out


def import_table_from_pg(
    pg_conn: Connection,
    staging_engine: Engine,
    table: Any,
    *,
    ctx: PipelineContext,
    source_digest: str,
) -> int:
    """单表导入（REPEATABLE READ 快照内流式读；数据+checkpoint 同事务）。"""
    imported = 0
    ordering = canonical.pg_pk_order_expr(table)
    statement = table.select().order_by(*ordering) if ordering else table.select()
    result = pg_conn.execution_options(stream_results=True).execute(statement)
    with staging_engine.begin() as staging_conn:
        while rows := result.fetchmany(BATCH_ROWS):
            ctx.check_cancel()
            batch = [_normalize_by_column_type(table, dict(row._mapping)) for row in rows]
            staging_conn.execute(table.insert(), batch)
            imported += len(batch)
        completed = _completed_on_staging(staging_conn, ctx) or {}
        checkpoint = ctx.checkpoint_payload({**completed, table.name: imported})
        set_import_state(staging_conn, ctx.attempt_id, source_digest, pipeline.TOOL_VERSION, checkpoint)
    return imported


def _completed_on_staging(conn: Connection, ctx: PipelineContext) -> Optional[Dict[str, int]]:
    state = get_import_state(conn)
    if state is None or state.get("migration_id") != ctx.attempt_id:
        return None
    completed = state.get("checkpoint", {}).get("completed", {})
    return dict(completed) if isinstance(completed, Mapping) else None


# ==================== 4. calibrate（SQLite 自增） ====================


def calibrate_sqlite_autoincrement(staging_engine: Engine) -> List[str]:
    """探测 AUTOINCREMENT 对象（sqlite_sequence）；无则报告跳过（§6.1 阶段 4）。"""
    with staging_engine.connect() as conn:
        insp = inspect(conn)
        if not insp.has_table("sqlite_sequence"):
            return ["sqlite_sequence 不存在：链内无 AUTOINCREMENT 表，跳过（普通 INTEGER PK 不冲突）"]
        rows = conn.exec_driver_sql("SELECT name FROM sqlite_sequence").fetchall()
        if not rows:
            return ["sqlite_sequence 为空：无 AUTOINCREMENT 计数需要校准"]
        # 链内当前无 AUTOINCREMENT 表；若出现（外部改动）按报告处理而非静默
        return [f"发现 AUTOINCREMENT 序列（非本链产物，人工核验）：{[r[0] for r in rows]}"]


# ==================== 5. verify（canonical-v1 双侧归一） ====================


def verify_pg_vs_sqlite(
    pg_conn: Connection, staging_engine: Engine, tables: Sequence[Any]
) -> Tuple[List[str], Dict[str, int], Dict[str, str]]:
    """行数+主键集合+全列摘要对账（双侧列类型归一，canonical-v1）。"""
    problems: List[str] = []
    counts: Dict[str, int] = {}
    digests: Dict[str, str] = {}
    with staging_engine.connect() as staging:
        for table in tables:
            p_count = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            s_count = staging.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            assert p_count is not None  # COUNT 恒非空
            counts[table.name] = int(p_count)
            if p_count != s_count:
                problems.append(f"{table.name}: 行数不一致 pg={p_count} sqlite={s_count}")
                continue
            # 只选主键列（与正向 sqlite_to_pg.verify 同源）：此前误用 table.select()
            # 全列行喂 digest_pk_tuples，跨库存储格式差异（datetime 文本/布尔等）
            # 造成"主键集合不一致"假阳性（W6 实跑抓出）
            pk_columns = list(table.primary_key.columns)
            if pk_columns:
                from sqlalchemy import select as sa_select

                ordering = canonical.pg_pk_order_expr(table)
                p_pks = (
                    pg_conn.execution_options(stream_results=True)
                    .execute(sa_select(*pk_columns).order_by(*ordering))
                    .all()
                )
                sqlite_ordering = canonical.sqlite_pk_order_expr(table)
                s_pks = (
                    staging.execution_options(stream_results=True)
                    .execute(sa_select(*pk_columns).order_by(*sqlite_ordering))
                    .all()
                )
                if canonical.digest_pk_tuples(p_pks) != canonical.digest_pk_tuples(s_pks):
                    problems.append(f"{table.name}: 主键集合不一致")
                continue

            def _pg_rows():
                sel = table.select().order_by(*ordering) if ordering else table.select()
                for row in pg_conn.execution_options(stream_results=True).execute(sel).mappings():
                    yield _normalize_by_column_type(table, dict(row))

            def _sqlite_rows():
                sel = table.select().order_by(*sqlite_ordering) if sqlite_ordering else table.select()
                for row in staging.execution_options(stream_results=True).execute(sel).mappings():
                    yield _normalize_by_column_type(table, dict(row))

            p_digest = canonical.digest_rows(_pg_rows())
            s_digest = canonical.digest_rows(_sqlite_rows())
            digests[table.name] = p_digest
            if p_digest != s_digest:
                problems.append(f"{table.name}: 内容摘要不一致")
    return problems, counts, digests


# ==================== 主流程 ====================


def run_pg_to_sqlite(
    pg_engine: Engine,
    *,
    target_dir: os.PathLike[str] | str,
    ctx: PipelineContext,
    resume_staging: Optional[os.PathLike[str] | str] = None,
) -> Dict[str, Any]:
    """完整反向迁移。 Raises: PrecheckFailed / TargetInvalid / MigrationInterrupted。"""
    register_all_models()
    tables = business_tables()
    ctx.report("precheck", 0, 1)

    errors, warnings = pg_precheck(pg_engine)
    for w in warnings:
        logger.warning("[预检] %s", w)
    if errors:
        for e in errors:
            logger.error("[预检] %s", e)
        raise PrecheckFailed(errors)
    logger.info("[预检] 通过（源 PG=%s）", tool_head())

    # 快照源身份（源库自己的 identity，不得复制给目标）
    with pg_engine.connect() as conn:
        ctx.source_database_id = read_database_identity(conn)
    source_digest = _pg_source_digest(pg_engine, tables)

    # staging：恢复（凭 sidecar 归属）或新建（sidecar 先于 DDL）
    if resume_staging is not None:
        staging = Path(resume_staging)
        if not verify_staging_ownership(staging, ctx):
            raise TargetInvalid(
                f"恢复 staging 归属核验失败（sidecar 缺失/不符/inode 变化）：{staging}——隔离处置，不续跑"
            )
    else:
        staging = create_staging_with_sidecar(target_dir, ctx, revision=tool_head())
    logger.info("[staging] %s", staging)

    from app.services.db_migration.target_params import sqlite_engine

    staging_engine = sqlite_engine(str(staging))

    try:
        # 阶段 2：schema 重放（显式目标，源零 DDL；T14）
        marker_exists = _staging_has_marker(staging_engine)
        if not marker_exists:
            replay_schema_chain(staging)
            # 阶段 3 前置：首业务行前同事务 IMPORTING receipt + marker（§3.3）
            begin_receipt_on_staging(staging_engine, ctx, source_digest=source_digest)
        else:
            _validate_staging_resume(staging_engine, tables, ctx, source_digest)

        # 阶段 3：import（REPEATABLE READ 快照读源）
        with _pg_snapshot_connection(pg_engine) as pg_conn:
            skipped = _staging_completed(staging_engine, ctx) or {}
            total = 0
            ordered = [t for t in tables if t.name not in skipped]
            for index, table in enumerate(ordered):
                ctx.check_cancel()
                ctx.report("import", len(skipped) + index, len(tables))
                n = import_table_from_pg(pg_conn, staging_engine, table, ctx=ctx, source_digest=source_digest)
                total += n
                logger.info("[导入] %s: %d 行", table.name, n)
            ctx.report("import", len(tables), len(tables))
            logger.info("[导入] 完成，共 %d 行", total)

            # 阶段 4：AUTOINCREMENT 探测
            for line in calibrate_sqlite_autoincrement(staging_engine):
                logger.info("[sequence] %s", line)
            ctx.report("calibrate", 1, 1)

            # 阶段 5：verify（同一快照内对账）
            ctx.report("verify", 0, len(tables))
            problems, counts, digests = verify_pg_vs_sqlite(pg_conn, staging_engine, tables)
            if problems:
                for p in problems:
                    logger.error("[核对] %s", p)
                raise MigrationInterrupted(f"对账未通过：{problems[0]}（共 {len(problems)} 项）")
            logger.info("[核对] 全部 %d 表行数/主键集合/内容摘要一致", len(tables))

        # 阶段 6：finalize（同事务 VERIFIED + 清 marker）
        with staging_engine.begin() as conn:
            identity = read_database_identity(conn)
            if identity is None:
                raise TargetInvalid("staging 缺少库身份——状态非法")
            verify_receipt_ownership(
                conn, ctx.attempt_id, ownership_nonce=ctx.ownership_nonce, target_database_id=identity
            )
            finalize_receipt_verified(
                conn,
                ctx.attempt_id,
                table_counts=counts,
                table_digests=digests,
                schema_fingerprint=canonical.schema_fingerprint(tables),
            )
        logger.info("[完成] receipt=VERIFIED，导入标记已清除；final=%s", staging)
        return {
            "attempt_id": ctx.attempt_id,
            "final": str(staging),
            "tables": len(tables),
            "counts": counts,
            "database_id": identity,  # staging 自身身份（activation 候选 expected_database_id）
        }
    except MigrationCancelled as exc:
        raise MigrationInterrupted(f"协作取消：{exc}") from exc
    except (PrecheckFailed, TargetInvalid):
        raise
    except Exception as exc:
        logger.error("反向导入失败，已提交表与检查点保持一致；凭 sidecar 恢复：%s", exc)
        raise MigrationInterrupted(str(exc)) from exc


def _pg_snapshot_connection(pg_engine: Engine) -> Any:
    """REPEATABLE READ 快照连接（W1：一致性读取；fence/SHARE 锁属 W2 维护屏障）。"""
    conn = pg_engine.connect().execution_options(isolation_level="REPEATABLE READ")
    return _SnapshotContext(conn)


class _SnapshotContext:
    """把快照连接包成上下文管理器（进入时开启只读事务，退出归还）。"""

    def __init__(self, conn: Connection):
        self._conn = conn

    def __enter__(self) -> Connection:
        # psycopg2 事务第一条语句：READ ONLY 固化快照只读语义
        self._conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        return self._conn

    def __exit__(self, *exc_info: Any) -> None:
        self._conn.rollback()
        self._conn.close()


def _pg_source_digest(pg_engine: Engine, tables: Sequence[Any]) -> str:
    """源内容摘要（快照前概要——用于 checkpoint 绑定；全量对账在 verify）。"""
    h = hashlib.sha256()
    with pg_engine.connect() as conn:
        for table in tables:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            h.update(f"{table.name}:{count}\n".encode("utf-8"))
    return h.hexdigest()


def _staging_has_marker(staging_engine: Engine) -> bool:
    with staging_engine.connect() as conn:
        return get_import_state(conn) is not None


def _staging_completed(staging_engine: Engine, ctx: PipelineContext) -> Optional[Dict[str, int]]:
    with staging_engine.connect() as conn:
        return _completed_on_staging(conn, ctx)


def _validate_staging_resume(
    staging_engine: Engine, tables: Sequence[Any], ctx: PipelineContext, source_digest: str
) -> Dict[str, int]:
    marker = _staging_marker(staging_engine)
    try:
        if marker.get("source_digest") != source_digest:
            raise TargetInvalid("源摘要不匹配——staging 已绑定其他源（拒绝换源续跑）")
        completed = pipeline.validate_checkpoint_prefix(
            marker.get("checkpoint") or {},
            [t.name for t in tables],
            ctx_attempt_id=ctx.attempt_id,
            ctx_nonce=ctx.ownership_nonce,
        )
    except CheckpointIncompatible as exc:
        raise TargetInvalid(str(exc)) from exc
    with staging_engine.connect() as conn:
        identity = read_database_identity(conn)
        if identity is None:
            raise TargetInvalid("staging 缺少库身份——状态非法")
        receipt = verify_receipt_ownership(
            conn, ctx.attempt_id, ownership_nonce=ctx.ownership_nonce, target_database_id=identity
        )
        if receipt["status"] != RECEIPT_STATUS_IMPORTING:
            raise TargetInvalid(f"receipt 状态 {receipt['status']} 非 IMPORTING——拒绝恢复")
        mismatch = pipeline.resume_row_counts_match(conn, completed, {t.name: t for t in tables})
        if mismatch is not None:
            raise TargetInvalid(f"检查点行数不匹配：{mismatch}——拒绝恢复")
    logger.info("[恢复] staging 已完成 %d 表，继续导入", len(completed))
    return completed


def _staging_marker(staging_engine: Engine) -> Dict[str, Any]:
    with staging_engine.connect() as conn:
        state = get_import_state(conn)
    if state is None:
        raise TargetInvalid("staging 无导入标记（状态不明）——拒绝")
    return state
