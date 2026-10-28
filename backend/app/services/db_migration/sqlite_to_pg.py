# -*- coding: utf-8 -*-
"""SQLite → PostgreSQL 迁移管线（database-migration-ui W1-5）。

自 backend/scripts/migrate_sqlite_to_pg.py（工具 1.1.0）抽取服务层；CLI 变薄壳
（参数/退出码 0|1|2|3 语义保持）。契约依据 docs/postgresql-contract.md §3/§4
与 PLANS/database-migration-ui.md §3.3/§6.1。

六阶段（顺序固定）：
  1. precheck  —— 源版本（仅接受工具唯一 head）/ JSON 按字段契约 / 布尔列取值 /
                  日期文本格式 / Float 非有限值（T12）/ 外键悬挂 / 软删同键报告
  2. baseline  —— 显式目标引擎 + ownership：单事务 create_all+stamp+目标自身
                  identity+IMPORTING receipt+初始 checkpoint marker（首表导入
                  前即持久凭据，§3.3）
  3. import    —— 依赖序分表分批；每表数据+checkpoint 同事务；协作取消边界
  4. calibrate —— 整数自增 PK sequence 校准（空表 setval(seq,1,false)）
  5. verify    —— 行数+主键集合+全列 canonical 摘要（btdeck-canonical-v1，
                  JSON SQL NULL/JSON null 区分）；收集全表 counts/digests
  6. finalize  —— 同事务 receipt VERIFIED + 清 marker（pg_baseline 协议操作）

异常→CLI 退出码：PrecheckFailed→1；TargetInvalid→2；MigrationInterrupted→3。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import JSON, Integer, bindparam, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.types import BigInteger, Boolean, DateTime, Float, String

from app.core.database_protocol import RECEIPT_STATUS_IMPORTING
from app.core.model_registry import register_all_models
from app.core.pg_baseline import (
    get_import_state,
    initialize_pg_baseline,
    read_pg_alembic_version,
    set_import_state,
    verify_receipt_ownership,
)
from app.database import Base
from app.models.database_migration import business_tables
from app.services.db_migration import canonical, pipeline
from app.services.db_migration.pipeline import (
    CheckpointIncompatible,
    MigrationCancelled,
    PipelineContext,
)

logger = logging.getLogger(__name__)

BATCH_ROWS = 500

# 软删同键检测面：partial unique index（WHERE dr=0）所在表与列
_SOFTDELETE_KEY_TABLES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("torrent_info", ("hash", "downloader_id")),
    ("tracker_info", ("torrent_info_id", "tracker_url")),
)

# JSON 按字段契约（契约 §4.3）：表.列 → (元素类型, 适用任务谓词列)
_JSON_CONTRACT: Dict[str, Tuple[str, Optional[str]]] = {
    "orphan_purge_job.orphan_ids_json": ("integer", "operation_type = 'cleanup'"),
    "orphan_purge_job.canonical_paths_json": ("string", "operation_type = 'purge'"),
}

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d{1,6})?$")


class PrecheckFailed(RuntimeError):
    """预检未通过（CLI 退出码 1）。errors 为可读问题清单。"""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors[:3]))
        self.errors = errors


class TargetInvalid(RuntimeError):
    """目标库状态非法（CLI 退出码 2）。"""


class MigrationInterrupted(RuntimeError):
    """导入中断/校验失败，可凭 checkpoint 恢复（CLI 退出码 3）。"""


# ==================== 1. precheck ====================


def read_sqlite_version(source: sqlite3.Connection) -> Optional[str]:
    row = source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
    if not row:
        return None
    v = source.execute("SELECT version_num FROM alembic_version").fetchone()
    return v[0] if v else None


def check_json_contract(source: sqlite3.Connection, *, auto_wrap: bool = False) -> Tuple[List[str], List[str]]:
    """JSON 按字段契约校验（契约 §4.3）。errors 非空即拒绝；warnings 仅报告。"""
    errors: List[str] = []
    warnings: List[str] = []
    for key, (elem_type, applicable) in _JSON_CONTRACT.items():
        table, column = key.split(".")
        missing = source.execute(f"SELECT COUNT(*) FROM {table} WHERE {applicable} AND {column} IS NULL").fetchone()[0]
        if missing:
            errors.append(f"{key}: {missing} 行适用任务缺少数组")
        rows = source.execute(f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
        for row_id, raw in rows:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                errors.append(f"{key} id={row_id}: 非法 JSON 文本")
                continue
            if isinstance(parsed, list):
                for elem in parsed:
                    if elem_type == "integer":
                        if isinstance(elem, bool) or not isinstance(elem, int) or not 1 <= elem <= 2147483647:
                            errors.append(f"{key} id={row_id}: 非整数元素 {elem!r}")
                    elif not isinstance(elem, str):
                        errors.append(f"{key} id={row_id}: 非字符串元素 {elem!r}")
            elif isinstance(parsed, (int, str)) and not isinstance(parsed, bool):
                matches = (elem_type == "integer" and isinstance(parsed, int) and 1 <= parsed <= 2147483647) or (
                    elem_type == "string" and isinstance(parsed, str)
                )
                if matches and auto_wrap:
                    warnings.append(f"{key} id={row_id}: 裸标量 {parsed!r}（--auto-wrap-scalar 将包裹为数组）")
                elif matches:
                    errors.append(f"{key} id={row_id}: 裸标量 {parsed!r}（如需包裹请加 --auto-wrap-scalar）")
                else:
                    errors.append(f"{key} id={row_id}: 顶层数组契约违规（{type(parsed).__name__}）")
            else:
                errors.append(f"{key} id={row_id}: 顶层数组契约违规（{type(parsed).__name__}）")
    return errors, warnings


def check_boolean_columns(source: sqlite3.Connection) -> List[str]:
    """Boolean 列取值域校验（SQLite 存 int 0/1/NULL 之外的值会导致 PG 拒绝）。"""
    register_all_models()
    errors: List[str] = []
    for table in business_tables():
        bool_cols = [c.name for c in table.columns if isinstance(c.type, Boolean)]
        for col in bool_cols:
            bad = source.execute(
                f"SELECT COUNT(*) FROM {table.name} WHERE {col} IS NOT NULL AND {col} NOT IN (0, 1)"
            ).fetchone()[0]
            if bad:
                errors.append(f"{table.name}.{col}: {bad} 行取值非 0/1（PG boolean 拒绝）")
    return errors


def check_datetime_text(source: sqlite3.Connection) -> List[str]:
    """DATETIME 列文本格式校验（'YYYY-MM-DD HH:MM:SS[.ffffff]' 双格式）。"""
    register_all_models()
    errors: List[str] = []
    for table in business_tables():
        dt_cols = [c.name for c in table.columns if isinstance(c.type, DateTime)]
        for col in dt_cols:
            bad = 0
            for (value,) in source.execute(f"SELECT {col} FROM {table.name} WHERE {col} IS NOT NULL"):
                try:
                    if not isinstance(value, str) or not _DATETIME_RE.fullmatch(value):
                        raise ValueError("invalid datetime syntax")
                    datetime.fromisoformat(value)
                except ValueError:
                    bad += 1
            if bad:
                errors.append(f"{table.name}.{col}: {bad} 行日期文本格式异常")
    return errors


def report_softdelete_duplicates(source: sqlite3.Connection) -> List[str]:
    """软删同键报告（保留不清理——双方均正确使用 WHERE dr=0 部分索引时为合法状态）。"""
    warnings: List[str] = []
    for table, cols in _SOFTDELETE_KEY_TABLES:
        col_list = ", ".join(cols)
        rows = source.execute(
            f"SELECT {col_list}, COUNT(*) AS n FROM {table} WHERE dr = 0 GROUP BY {col_list} HAVING n > 1"
        ).fetchall()
        if rows:
            warnings.append(f"{table}: {len(rows)} 组活动记录同键（导入后唯一索引将拒绝，需人工处理）")
    return warnings


def check_source_schema_and_values(source: sqlite3.Connection) -> List[str]:
    """PG 严格类型/完整性预检；在创建目标 schema 之前拒绝不可导入源。

    Float 非有限值（NaN/Infinity）在此拒绝（T12）——不等到导入后变 NULL。
    """
    register_all_models()
    errors: List[str] = []
    if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        errors.append("SQLite 完整性检查失败")
    if source.execute("PRAGMA foreign_key_check").fetchone():
        errors.append("SQLite 存在悬挂外键")
    known = set(Base.metadata.tables) | {"alembic_version"}
    actual = {
        row[0]
        for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if not row[0].startswith("sqlite_")
    }
    if actual != known:
        errors.append(f"源表集合不匹配：缺少={sorted(known - actual)} 额外={sorted(actual - known)}")
        return errors
    for table in business_tables():
        columns = {row[1] for row in source.execute(f'PRAGMA table_info("{table.name}")')}
        if columns != set(table.columns.keys()):
            errors.append(f"{table.name}: 源列集合与模型不匹配")
            continue
        for column in table.columns:
            bad = False
            for (value,) in source.execute(f'SELECT "{column.name}" FROM "{table.name}"'):
                if value is None:
                    bad = bad or not column.nullable
                elif isinstance(column.type, String):
                    bad = bad or not isinstance(value, str) or "\x00" in value
                    if isinstance(value, str) and column.type.length:
                        bad = bad or len(value) > column.type.length
                elif isinstance(column.type, Integer):
                    bits = 64 if isinstance(column.type, BigInteger) else 32
                    bad = bad or type(value) is not int or not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1)
                elif isinstance(column.type, Float):
                    bad = bad or not isinstance(value, (int, float)) or not math.isfinite(value)
                elif isinstance(column.type, JSON):
                    try:
                        json.loads(value)
                    except (ValueError, TypeError):
                        bad = True
            if bad:
                errors.append(f"{table.name}.{column.name}: NULL/类型/长度/范围或非法文本不满足目标列契约")
    return errors


def check_search_templates(source: sqlite3.Connection) -> List[str]:
    """迁移前列出无法在 PG 执行的存量正则模板，拒绝静默语义变化。"""
    from app.core.dialect_sql import validate_regex_pattern_for_dialect

    def patterns(value: Any) -> Iterable[Any]:
        if isinstance(value, dict):
            if value.get("operator") == "regex":
                raw = value.get("value")
                yield raw.get("pattern", "") if isinstance(raw, dict) else raw
            for child in value.values():
                yield from patterns(child)
        elif isinstance(value, list):
            for child in value:
                yield from patterns(child)

    errors: List[str] = []
    for template_id, payload in source.execute("SELECT id, conditions FROM search_templates"):
        try:
            for pattern in patterns(json.loads(payload)):
                if not isinstance(pattern, str):
                    raise ValueError("regex pattern must be text")
                validate_regex_pattern_for_dialect(pattern, dialect="postgresql")
        except (ValueError, TypeError) as exc:
            errors.append(f"search_templates id={template_id}: {exc}")
    return errors


def check_external_assets(source: sqlite3.Connection, paths: Mapping[str, str]) -> List[str]:
    """核对解密配置同源和有效种子备份可达性；不输出密钥或解密数据。"""
    import yaml

    errors: List[str] = []
    encrypted = source.execute("SELECT COUNT(*) FROM bt_downloaders WHERE password LIKE 'sm4:%'").fetchone()[0]
    if encrypted:
        keys = []
        for name in ("source_config", "target_config"):
            try:
                config = yaml.safe_load(Path(paths[name]).read_text(encoding="utf-8"))
                key = config["security"]["secret_key"]
                if not isinstance(key, str) or len(key.encode("utf-8")) != 16:
                    raise ValueError("invalid key")
                keys.append(key)
            except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
                errors.append(f"{name}: 缺少可用 SM4 配置；请显式指定源/目标 config.yaml")
        if len(keys) == 2 and keys[0] != keys[1]:
            errors.append("源/目标 SM4 密钥不一致；必须迁移同源 config.yaml")
    backup_root = Path(paths.get("backup_root", str(Path.cwd())))
    for backup_id, raw_path in source.execute("SELECT id, file_path FROM torrent_file_backup WHERE is_deleted = 0"):
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = backup_root / candidate
        try:
            with candidate.open("rb"):
                pass
        except OSError:
            errors.append(f"torrent_file_backup id={backup_id}: 备份文件在目标根目录不可读取")
    return errors


def precheck(
    source_path: str, *, auto_wrap: bool = False, asset_paths: Optional[Dict[str, str]] = None
) -> Tuple[List[str], List[str], Optional[str]]:
    """预检（不连目标）；版本、结构和所有持久化字段先验证再导入。"""
    conn = sqlite3.connect(Path(source_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        version = read_sqlite_version(conn)
        versions = conn.execute("SELECT COUNT(*) FROM alembic_version").fetchone()[0] if version else 0
        if version != tool_head() or versions != 1:
            return ["源库版本必须为工具唯一 head；旧库请先在副本升级"], [], version
        errors = check_source_schema_and_values(conn)
        if errors:
            return errors, [], version
        errors, warnings = check_json_contract(conn, auto_wrap=auto_wrap)
        errors += check_boolean_columns(conn)
        errors += check_datetime_text(conn)
        errors += check_search_templates(conn)
        errors += check_external_assets(conn, asset_paths or {})
        warnings += report_softdelete_duplicates(conn)
        return errors, warnings, version
    finally:
        conn.close()


def tool_head() -> str:
    """工具所属代码的唯一 head（迁移链单一真相源）。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"迁移链多 head：{heads}")
    return heads[0]


# ==================== 2-3. baseline + import ====================


def row_transform(table: Any, row: sqlite3.Row) -> Dict[str, Any]:
    """按列类型变换 SQLite 原生值为 PG 安全绑定值（Boolean int→bool；DateTime 文本→datetime）。"""
    out: Dict[str, Any] = {}
    for col in table.columns:
        val = row[col.name] if col.name in row.keys() else None
        if val is None:
            out[col.name] = None
        elif isinstance(col.type, JSON) and isinstance(val, str):
            parsed_json = json.loads(val)
            out[col.name] = JSON.NULL if parsed_json is None else parsed_json
        elif isinstance(col.type, Boolean):
            out[col.name] = bool(val)
        elif isinstance(col.type, DateTime) and isinstance(val, str):
            norm = val.replace("T", " ")
            parsed = datetime.fromisoformat(norm)
            if col.type.timezone and parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            out[col.name] = parsed
        else:
            out[col.name] = val
    return out


def auto_wrap_json_values(source_path: str) -> int:
    """--auto-wrap-scalar：把与字段元素类型匹配的裸标量包裹为数组（只修改调用方创建的临时快照）。"""
    conn = sqlite3.connect(source_path)
    wrapped = 0
    try:
        for key, _ in _JSON_CONTRACT.items():
            table, column = key.split(".")
            rows = conn.execute(f"SELECT rowid, {column} FROM {table} WHERE {column} IS NOT NULL").fetchall()
            for row_id, raw in rows:
                try:
                    parsed = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(parsed, (int, str)) and not isinstance(parsed, bool):
                    conn.execute(
                        f"UPDATE {table} SET {column} = :v WHERE rowid = :rid",
                        {"v": json.dumps([parsed], ensure_ascii=False), "rid": row_id},
                    )
                    wrapped += 1
        conn.commit()
    finally:
        conn.close()
    return wrapped


def import_table(
    sqlite_conn: sqlite3.Connection,
    pg_engine: Engine,
    table: Any,
    *,
    ctx: PipelineContext,
    migration_id: str,
    source_digest: str,
) -> int:
    """单表导入（单表单事务；完成后更新检查点；批间协作取消边界）。

    checkpoint 与 receipt 同步携带 ownership 绑定（§3.3）；取消仅在批边界
    生效——当前批事务要么整体提交要么整体回滚。
    """
    cursor = sqlite_conn.execute(f"SELECT * FROM {table.name}")
    imported = 0
    with pg_engine.begin() as pg_conn:
        while rows := cursor.fetchmany(BATCH_ROWS):
            ctx.check_cancel()  # 批间边界（cancel 抛出→本表事务回滚，进度不丢）
            batch = [row_transform(table, row) for row in rows]
            statement = table.insert().values(
                {
                    column.name: bindparam(column.name, type_=JSON(none_as_null=True))
                    for column in table.columns
                    if isinstance(column.type, JSON)
                }
            )
            pg_conn.execute(statement, batch)
            imported += len(batch)
        checkpoint = ctx.checkpoint_payload({**_completed_so_far(ctx, migration_id, pg_conn), table.name: imported})
        # 数据与检查点同事务：任一失败均回滚，重跑不会撞已提交主键
        set_import_state(pg_conn, migration_id, source_digest, pipeline.TOOL_VERSION, checkpoint)
    return imported


def _completed_so_far(ctx: PipelineContext, migration_id: str, pg_conn: Connection) -> Dict[str, int]:
    """从既有 marker 读取已完成表（恢复场景；首表时空）。"""
    state = get_import_state(pg_conn)
    if state is None or state.get("migration_id") != migration_id:
        return {}
    completed = state.get("checkpoint", {}).get("completed", {})
    return dict(completed) if isinstance(completed, Mapping) else {}


# ==================== 4. calibrate ====================


def calibrate_sequences(pg_engine: Engine) -> List[str]:
    """整数自增 PK 业务表 sequence 校准（契约 §3：空表分支 setval(seq,1,false)）。"""
    register_all_models()
    calibrated: List[str] = []
    with pg_engine.begin() as conn:
        for table in business_tables():
            pk_cols = list(table.primary_key.columns)
            if not (len(pk_cols) == 1 and isinstance(pk_cols[0].type, Integer) and pk_cols[0].autoincrement):
                continue
            pk = pk_cols[0].name
            seq_row = conn.execute(text("SELECT pg_get_serial_sequence(:t, :c)"), {"t": table.name, "c": pk}).scalar()
            if not seq_row:
                continue
            max_id = conn.execute(text(f'SELECT MAX("{pk}") FROM "{table.name}"')).scalar()
            if max_id is None:
                conn.execute(text("SELECT setval(:s, 1, false)"), {"s": seq_row})
            else:
                conn.execute(text("SELECT setval(:s, :m)"), {"s": seq_row, "m": int(max_id)})
            calibrated.append(f"{table.name}.{pk}→{max_id if max_id is not None else 'empty(1,false)'}")
    return calibrated


# ==================== 5. verify（canonical-v1） ====================


def verify_counts_and_digests(
    sqlite_conn: sqlite3.Connection, pg_engine: Engine, tables: Sequence[Any]
) -> Tuple[List[str], Dict[str, int], Dict[str, str]]:
    """行数+主键集合+内容摘要双库对账（canonical-v1）。

    Returns:
        (问题清单, 全表行数, 全表摘要)——后两者供 receipt finalize 落盘。
    """
    problems: List[str] = []
    counts: Dict[str, int] = {}
    digests: Dict[str, str] = {}
    with pg_engine.connect() as pg:
        for table in tables:
            s_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table.name}").fetchone()[0]
            p_count = pg.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            counts[table.name] = int(s_count)
            if s_count != p_count:
                problems.append(f"{table.name}: 行数不一致 sqlite={s_count} pg={p_count}")
                continue
            ordering = canonical.pk_order_expr(table, pg.dialect.name)
            pk_list = ", ".join(f'"{c.name}"' for c in table.primary_key.columns)
            if pk_list:
                s_pks = sqlite_conn.execute(f"SELECT {pk_list} FROM {table.name} ORDER BY {pk_list}").fetchall()
                p_pks = (
                    pg.execution_options(stream_results=True)
                    .execute(select(*table.primary_key.columns).order_by(*ordering))
                    .all()
                )
                if canonical.digest_pk_tuples(s_pks) != canonical.digest_pk_tuples(p_pks):
                    problems.append(f"{table.name}: 主键集合不一致")
                    continue
            order_clause = f" ORDER BY {pk_list}" if pk_list else ""
            source_cursor = sqlite_conn.execute(f"SELECT * FROM {table.name}{order_clause}")
            source_cursor.row_factory = sqlite3.Row  # type: ignore[assignment]  # 存量写法（ratio_data_diagnostics）
            json_columns = [c.name for c in table.columns if isinstance(c.type, JSON)]
            target_rows = pg.execution_options(stream_results=True).execute(
                select(
                    table,
                    *[
                        column.is_(None).label(canonical.SQL_NULL_FLAG_PREFIX + column.name)
                        for column in table.columns
                        if isinstance(column.type, JSON)
                    ],
                ).order_by(*ordering)
            )
            source_rows = []
            for row in source_cursor:
                normalized = row_transform(table, row)
                for name in json_columns:
                    normalized[canonical.SQL_NULL_FLAG_PREFIX + name] = row[name] is None
                    if normalized[name] is JSON.NULL:
                        normalized[name] = None
                source_rows.append(normalized)
            target_normalized = []
            for row in target_rows.mappings():
                row_dict = dict(row)
                for name in json_columns:
                    if row_dict.get(name) is None and row_dict.get(canonical.SQL_NULL_FLAG_PREFIX + name) is False:
                        # SQL NULL 为假 + 值 None → JSON null（边注区分，值域归一 None）
                        pass
                target_normalized.append(row_dict)
            s_digest = canonical.digest_rows(source_rows)
            p_digest = canonical.digest_rows(target_normalized)
            digests[table.name] = s_digest
            if s_digest != p_digest:
                problems.append(f"{table.name}: 内容摘要不一致")
    return problems, counts, digests


# ==================== 主流程（六阶段编排） ====================


def run_sqlite_to_pg(
    source_path: str,
    *,
    pg_engine: Engine,
    ctx: PipelineContext,
    alembic_cfg_factory: Any = None,
    resume: bool = False,
    auto_wrap: bool = False,
    asset_paths: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """完整迁移（只读源库一致性快照；修复只在临时副本执行）。

    Raises:
        PrecheckFailed / TargetInvalid / MigrationInterrupted
    """
    register_all_models()
    try:
        with tempfile.TemporaryDirectory(prefix="btdeck-pg-import-") as directory:
            snapshot = Path(directory) / "source.db"
            source = sqlite3.connect(Path(source_path).resolve().as_uri() + "?mode=ro", uri=True)
            try:
                with sqlite3.connect(snapshot) as target:
                    source.backup(target)
            finally:
                source.close()
            return _run_snapshot(
                str(snapshot),
                pg_engine=pg_engine,
                ctx=ctx,
                alembic_cfg_factory=alembic_cfg_factory,
                resume=resume,
                auto_wrap=auto_wrap,
                asset_paths=asset_paths,
            )
    except MigrationCancelled as exc:
        raise MigrationInterrupted(f"协作取消：{exc}") from exc
    except (PrecheckFailed, TargetInvalid):
        raise
    except Exception as exc:
        logger.error("导入失败，已提交表与检查点保持一致；修复原因后 --resume：%s", exc)
        raise MigrationInterrupted(str(exc)) from exc


def _run_snapshot(
    source_path: str,
    *,
    pg_engine: Engine,
    ctx: PipelineContext,
    alembic_cfg_factory: Any,
    resume: bool,
    auto_wrap: bool,
    asset_paths: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    from alembic.config import Config

    tables = business_tables()
    ctx.report("precheck", 0, 1)

    # 阶段 1：precheck
    errors, warnings, version = precheck(source_path, auto_wrap=auto_wrap, asset_paths=asset_paths)
    for w in warnings:
        logger.warning("[预检] %s", w)
    if errors:
        for e in errors:
            logger.error("[预检] %s", e)
        raise PrecheckFailed(errors)
    chain_head = tool_head()
    if version != chain_head:
        raise PrecheckFailed([f"源库版本 {version} ≠ 工具所属 head {chain_head}"])
    logger.info("[预检] 通过（源版本=%s）", version)

    if auto_wrap:
        wrapped = auto_wrap_json_values(source_path)
        if wrapped:
            logger.info("[auto-wrap] 包裹 %d 个裸标量", wrapped)

    with open(source_path, "rb") as snapshot_file:
        source_digest = hashlib.file_digest(snapshot_file, "sha256").hexdigest()

    # 源库身份（协议表存在则读取；老库无身份则 None）
    source_identity = _read_sqlite_identity(source_path)
    ctx.source_database_id = source_identity
    fingerprint = canonical.schema_fingerprint(tables)

    # 阶段 2：baseline / 恢复
    if alembic_cfg_factory is not None:
        cfg = alembic_cfg_factory()
    else:
        backend_root = Path(__file__).resolve().parents[3]
        cfg = Config(str(backend_root / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.attributes["configure_logger"] = False

    marker = get_import_state_over(pg_engine)
    if marker is not None:
        if marker.get("migration_id") != ctx.attempt_id:
            # 与旧工具语义一致：目标绑定其他迁移 → 目标状态非法（exit 2）
            raise TargetInvalid(f"迁移 ID 不匹配（标记={marker.get('migration_id')!r} 本次={ctx.attempt_id}）——拒绝")
        if not resume:
            raise MigrationInterrupted(
                f"目标库存在导入未完成标记（migration_id={marker.get('migration_id')}）：校验后以 --resume 恢复"
            )
        completed = _validate_resume(pg_engine, marker, tables, ctx, chain_head, source_digest)
    else:
        completed = {}
        ownership = {
            "attempt_id": ctx.attempt_id,
            "operation_kind": ctx.operation_kind,
            "source_database_id": source_identity,
            "deployment_id": ctx.deployment_id,
            "ownership_nonce": ctx.ownership_nonce,
            "revision_at_import": chain_head,
            "schema_fingerprint": fingerprint,
            "origin_epoch": ctx.origin_epoch,
            "eligible_epoch": ctx.eligible_epoch,
        }
        try:
            initialized = initialize_pg_baseline(
                cfg,
                chain_head,
                engine=pg_engine,
                import_state={
                    "migration_id": ctx.attempt_id,
                    "source_digest": source_digest,
                    "tool_version": pipeline.TOOL_VERSION,
                    "checkpoint": ctx.checkpoint_payload({}),
                },
                ownership=ownership,
            )
        except RuntimeError as exc:
            raise TargetInvalid(f"目标库状态非法：{exc}") from exc
        if not initialized:
            raise TargetInvalid("目标库非空库（已有版本/业务数据）——拒绝导入（三状态规则）")

    # 阶段 3：import（依赖序；跳过已完成表；表间取消边界）
    sqlite_conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    total_rows = 0
    try:
        ordered = [t for t in tables if t.name not in completed]
        for index, table in enumerate(ordered):
            ctx.check_cancel()
            ctx.report("import", len(completed) + index, len(tables))
            n = import_table(
                sqlite_conn,
                pg_engine,
                table,
                ctx=ctx,
                migration_id=ctx.attempt_id,
                source_digest=source_digest,
            )
            total_rows += n
            logger.info("[导入] %s: %d 行", table.name, n)
        ctx.report("import", len(tables), len(tables))
        logger.info("[导入] 完成，共 %d 行", total_rows)
    finally:
        sqlite_conn.close()

    # 阶段 4：sequence 校准
    for line in calibrate_sequences(pg_engine):
        logger.info("[sequence] %s", line)
    ctx.report("calibrate", 1, 1)

    # 阶段 5：verify
    ctx.report("verify", 0, len(tables))
    problems, counts, digests = verify_counts_and_digests(sqlite_ro(source_path), pg_engine, tables)
    if problems:
        for p in problems:
            logger.error("[核对] %s", p)
        raise MigrationInterrupted(f"对账未通过：{problems[0]}（共 {len(problems)} 项）")
    logger.info("[核对] 全部 %d 表行数/主键集合/内容摘要一致", len(tables))

    # 阶段 6：finalize（同事务 receipt VERIFIED + 清 marker）
    from app.core.pg_baseline import finalize_receipt_verified

    with pg_engine.begin() as conn:
        verify_receipt_ownership(
            conn,
            ctx.attempt_id,
            ownership_nonce=ctx.ownership_nonce,
            target_database_id=_target_identity(pg_engine),
        )
        finalize_receipt_verified(
            conn, ctx.attempt_id, table_counts=counts, table_digests=digests, schema_fingerprint=fingerprint
        )
    logger.info("[完成] receipt=VERIFIED，导入标记已清除")
    return {"attempt_id": ctx.attempt_id, "tables": len(tables), "rows": total_rows, "counts": counts}


def sqlite_ro(source_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_import_state_over(pg_engine: Engine) -> Optional[Dict[str, Any]]:
    with pg_engine.connect() as conn:
        return get_import_state(conn)


def _target_identity(pg_engine: Engine) -> str:
    from app.core.pg_baseline import read_database_identity

    with pg_engine.connect() as conn:
        identity = read_database_identity(conn)
    if identity is None:
        raise TargetInvalid("目标库缺少身份（基线未生成 identity）——状态非法")
    return identity


def _read_sqlite_identity(source_path: str) -> Optional[str]:
    conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bt_database_identity'").fetchone()
        if not has:
            return None
        row = conn.execute("SELECT database_id FROM bt_database_identity").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _validate_resume(
    pg_engine: Engine,
    marker: Mapping[str, Any],
    tables: Sequence[Any],
    ctx: PipelineContext,
    chain_head: str,
    source_digest: str,
) -> Dict[str, int]:
    """恢复校验：marker/receipt 绑定 + 依赖序前缀 + 行数对账（§6.3）。"""
    try:
        if marker.get("migration_id") != ctx.attempt_id:
            raise TargetInvalid(
                f"迁移 ID 不匹配（标记={marker.get('migration_id')!r} 本次={ctx.attempt_id}）——拒绝恢复"
            )
        if marker.get("source_digest") != source_digest:
            raise TargetInvalid("源摘要不匹配——目标已绑定其他源（拒绝换源续跑）")
        checkpoint = marker.get("checkpoint") or {}
        completed = pipeline.validate_checkpoint_prefix(
            checkpoint, [t.name for t in tables], ctx_attempt_id=ctx.attempt_id, ctx_nonce=ctx.ownership_nonce
        )
    except CheckpointIncompatible as exc:
        # 旧 1.1.0 checkpoint 无 ownership 绑定 → 明确不兼容（不伪装兼容，§6.3）
        raise TargetInvalid(str(exc)) from exc
    with pg_engine.connect() as conn:
        if read_pg_alembic_version(conn) != chain_head:
            raise TargetInvalid("目标版本与工具 head 不匹配——拒绝恢复")
        receipt = verify_receipt_ownership(
            conn,
            ctx.attempt_id,
            ownership_nonce=ctx.ownership_nonce,
            target_database_id=_target_identity(pg_engine),
        )
        if receipt["status"] != RECEIPT_STATUS_IMPORTING:
            raise TargetInvalid(f"receipt 状态 {receipt['status']} 非 IMPORTING——拒绝恢复导入")
        mismatch = pipeline.resume_row_counts_match(conn, completed, {t.name: t for t in tables})
        if mismatch is not None:
            raise TargetInvalid(f"检查点行数不匹配：{mismatch}——拒绝恢复")
    logger.info("[恢复] 已完成 %d 表，继续导入", len(completed))
    return completed
