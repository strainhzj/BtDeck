#!/usr/bin/env python3
"""SQLite → PostgreSQL 数据迁移工具（v1.0.8 任务4.1）。

契约依据：docs/postgresql-contract.md §3（目标库三状态/停写/回退窗口）与 §8（静态风险）；
计划 PLANS/v1.0.8.md 任务4.1 全环节规则表。

阶段（顺序固定）：
  1. precheck  —— 源版本（仅接受工具所属 head）/ JSON 按字段契约 / 布尔列取值 /
                  日期文本格式 / 外键悬挂 / 软删同键报告（保留不清理，仅报告）
  2. baseline  —— 目标库三状态判定：全新 → 共享基线函数（schema + stamp，
                  不 seed 不起任务）；导入未完成 → 校验迁移 ID/源摘要/工具版本/
                  检查点后恢复；已有应用数据/来源不明 → 拒绝
  3. import    —— 依赖序（metadata.sorted_tables）分表分批导入；行变换按列类型
                  （Boolean int→bool；DateTime 文本→datetime）；每表完成即更新检查点
  4. calibrate —— 整数自增 PK 表 sequence 校准：setval(seq, max(id))；
                  空表分支 setval(seq, 1, false)（禁止空表 max+1）
  5. verify    —— 行数 + 主键集合 + 内容摘要（类型归一化行的 SHA-256）双库对账
  6. finalize  —— 清除导入标记 + 切换指引（离线核对窗口/回滚边界）

用法：
  python scripts/migrate_sqlite_to_pg.py --source /path/app.db --precheck   # 仅预检（不连 PG）
  python scripts/migrate_sqlite_to_pg.py --source /path/app.db             # 完整迁移
  环境变量：DB_TYPE=postgresql + DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME（与应用同源）

退出码：0 成功；1 预检未通过（默认拒绝）；2 目标库状态非法；3 导入中断（可 --resume 恢复）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# 允许脚本从 backend/ 或仓库根运行（backend/scripts/ 下的既有惯例）
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import Integer, bindparam, create_engine, select, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.types import Boolean, DateTime, JSON, String, BigInteger, Float  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.model_registry import register_all_models  # noqa: E402
from app.database import Base, build_database_url  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_sqlite_to_pg")

TOOL_VERSION = "1.1.0"
BATCH_ROWS = 500

# 软删同键检测面：partial unique index（WHERE dr=0）所在表与列
_SOFTDELETE_KEY_TABLES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("torrent_info", ("hash", "downloader_id")),
    ("tracker_info", ("torrent_info_id", "tracker_url")),
)

# JSON 按字段契约（契约 §4.3）：表.列 → (元素类型, 适用任务谓词列, 允许 NULL 语义)
_JSON_CONTRACT: Dict[str, Tuple[str, Optional[str]]] = {
    "orphan_purge_job.orphan_ids_json": ("integer", "operation_type = 'cleanup'"),
    "orphan_purge_job.canonical_paths_json": ("string", "operation_type = 'purge'"),
}

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d{1,6})?$")


# ==================== 1. precheck ====================


def read_sqlite_version(source: sqlite3.Connection) -> Optional[str]:
    row = source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
    if not row:
        return None
    v = source.execute("SELECT version_num FROM alembic_version").fetchone()
    return v[0] if v else None


def check_json_contract(source: sqlite3.Connection, *, auto_wrap: bool = False) -> Tuple[List[str], List[str]]:
    """JSON 按字段契约校验（契约 §4.3）。

    Returns:
        (errors, warnings)：errors 非空即默认拒绝（退出码 1）；warnings 仅报告。
        auto_wrap：与字段元素类型匹配的裸标量允许包裹（记 warning，历史数据
        json_each 本就展开标量）；对象/错误类型/非整数元素恒拒绝。
    """
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
                        # 排除布尔（bool 是 int 子类）+ 范围校验交由列类型
                        if isinstance(elem, bool) or not isinstance(elem, int) or not 1 <= elem <= 2147483647:
                            errors.append(f"{key} id={row_id}: 非整数元素 {elem!r}")
                    elif not isinstance(elem, str):
                        errors.append(f"{key} id={row_id}: 非字符串元素 {elem!r}")
            elif isinstance(parsed, (int, str)) and not isinstance(parsed, bool):
                # 裸标量：与元素类型匹配才可包裹
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
    for table in Base.metadata.sorted_tables:
        bool_cols = [c.name for c in table.columns if isinstance(c.type, Boolean)]
        for col in bool_cols:
            bad = source.execute(
                f"SELECT COUNT(*) FROM {table.name} WHERE {col} IS NOT NULL AND {col} NOT IN (0, 1)"
            ).fetchone()[0]
            if bad:
                errors.append(f"{table.name}.{col}: {bad} 行取值非 0/1（PG boolean 拒绝）")
    return errors


def check_datetime_text(source: sqlite3.Connection) -> List[str]:
    """DATETIME 列文本格式校验（'YYYY-MM-DD HH:MM:SS[.ffffff]'，微秒/非微秒双格式）。"""
    register_all_models()
    errors: List[str] = []
    for table in Base.metadata.sorted_tables:
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
    """PG 严格类型/完整性预检；在创建目标 schema 之前拒绝不可导入源。"""
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
    for table in Base.metadata.sorted_tables:
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

    def patterns(value: Any) -> Iterable[str]:
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


def check_external_assets(source: sqlite3.Connection, paths: Dict[str, str]) -> List[str]:
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
    backup_root = Path(paths.get("backup_root", str(BACKEND_ROOT)))
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
    """预检（不连 PG）；版本、结构和所有持久化字段先验证再导入。"""
    conn = sqlite3.connect(Path(source_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        version = read_sqlite_version(conn)
        versions = conn.execute("SELECT COUNT(*) FROM alembic_version").fetchone()[0] if version else 0
        if version != _tool_head() or versions != 1:
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


# ==================== 2-3. baseline + import ====================


def row_transform(table: Any, row: sqlite3.Row) -> Dict[str, Any]:
    """按列类型变换 SQLite 原生值为 PG 安全绑定值。

    Boolean：int 0/1 → bool（psycopg2 直发 int 会被 PG boolean 拒绝）；
    DateTime：文本 → datetime（规避隐式文本转换，格式已在预检校验）。
    """
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
    state: Dict[str, Any],
    migration_id: str,
    source_digest: str,
) -> int:
    """单表导入（单表单事务；完成后更新检查点）。返回导入行数。"""
    from app.core.pg_baseline import set_import_state

    cursor = sqlite_conn.execute(f"SELECT * FROM {table.name}")
    imported = 0
    checkpoint = {**state, "completed": dict(state["completed"])}
    with pg_engine.begin() as pg_conn:
        while rows := cursor.fetchmany(BATCH_ROWS):
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
        checkpoint["completed"][table.name] = imported
        # 数据与检查点同事务：任一失败均回滚，重跑不会撞已提交主键。
        set_import_state(pg_conn, migration_id, source_digest, TOOL_VERSION, checkpoint)
    state.update(checkpoint)
    return imported


# ==================== 4. calibrate ====================


def calibrate_sequences(pg_engine: Engine) -> List[str]:
    """整数自增 PK 表 sequence 校准（契约 §3：空表分支 setval(seq,1,false)）。"""
    register_all_models()
    calibrated: List[str] = []
    with pg_engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
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


# ==================== 5. verify ====================


def _pk_cols(table: Any) -> List[str]:
    return [c.name for c in table.primary_key.columns]


def _row_digest(rows: Iterable[Any]) -> str:
    """行集合摘要：tuple(row) 归一（消除 sqlite3.Row / SQLAlchemy Row 的 repr 差异）。"""
    h = hashlib.sha256()
    for row in rows:
        h.update((repr(tuple(row)) + "\n").encode("utf-8"))
    return h.hexdigest()


def _content_bytes(row: Dict[str, Any]) -> bytes:
    """稳定编码，保留 JSON/Text 区别并规范化驱动返回的时间。"""

    def normalize(value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value.isoformat(timespec="microseconds")
        raise TypeError(f"Unsupported digest type: {type(value).__name__}")

    return (json.dumps(row, sort_keys=True, ensure_ascii=False, default=normalize) + "\n").encode("utf-8")


def verify_counts_and_digests(sqlite_conn: sqlite3.Connection, pg_engine: Engine, tables: Sequence[Any]) -> List[str]:
    """行数 + 主键集合 + 内容摘要双库对账。Returns: 不一致清单（空 = 通过）。"""
    problems: List[str] = []
    with pg_engine.connect() as pg:
        for table in tables:
            s_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table.name}").fetchone()[0]
            p_count = pg.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            if s_count != p_count:
                problems.append(f"{table.name}: 行数不一致 sqlite={s_count} pg={p_count}")
                continue
            pks = _pk_cols(table)
            ordering = [
                column.collate("C") if isinstance(column.type, String) and pg.dialect.name == "postgresql" else column
                for column in table.primary_key.columns
            ]
            if pks:
                pk_list = ", ".join(f'"{c}"' for c in pks)
                s_pks = _row_digest(sqlite_conn.execute(f"SELECT {pk_list} FROM {table.name} ORDER BY {pk_list}"))
                p_pks = _row_digest(
                    pg.execution_options(stream_results=True).execute(
                        select(*table.primary_key.columns).order_by(*ordering)
                    )
                )
                if s_pks != p_pks:
                    problems.append(f"{table.name}: 主键集合不一致")
                    continue
            # 读取类型化目标行；源行经与导入相同的类型归一，比较全部列。
            source_cursor = sqlite_conn.execute(f"SELECT * FROM {table.name}")
            source_cursor.row_factory = sqlite3.Row
            order = ", ".join(f'"{c}"' for c in pks)
            if order:
                source_cursor = sqlite_conn.execute(f"SELECT * FROM {table.name} ORDER BY {order}")
                source_cursor.row_factory = sqlite3.Row
            target_rows = pg.execution_options(stream_results=True).execute(
                select(
                    table,
                    *[
                        column.is_(None).label("__sql_null__" + column.name)
                        for column in table.columns
                        if isinstance(column.type, JSON)
                    ],
                ).order_by(*ordering)
            )
            source_hash = hashlib.sha256()
            target_hash = hashlib.sha256()
            for row in source_cursor:
                normalized = row_transform(table, row)
                for column in table.columns:
                    if isinstance(column.type, JSON):
                        normalized["__sql_null__" + column.name] = row[column.name] is None
                        if normalized[column.name] is JSON.NULL:
                            normalized[column.name] = None
                source_hash.update(_content_bytes(normalized))
            for row in target_rows.mappings():
                target_hash.update(_content_bytes(dict(row)))
            if source_hash.digest() != target_hash.digest():
                problems.append(f"{table.name}: 内容摘要不一致")
    return problems


# ==================== 主流程 ====================


def run_migration(
    source_path: str, *, resume: bool = False, auto_wrap: bool = False, asset_paths: Optional[Dict[str, str]] = None
) -> int:
    """只读源库的一致性快照；包含 WAL 已提交数据，修复只在临时副本执行。"""
    try:
        with tempfile.TemporaryDirectory(prefix="btdeck-pg-import-") as directory:
            snapshot = Path(directory) / "source.db"
            source = sqlite3.connect(Path(source_path).resolve().as_uri() + "?mode=ro", uri=True)
            try:
                with sqlite3.connect(snapshot) as target:
                    source.backup(target)
            finally:
                source.close()
            return _run_snapshot_migration(str(snapshot), resume=resume, auto_wrap=auto_wrap, asset_paths=asset_paths)
    except Exception as exc:
        logger.error("导入失败，已提交表与检查点保持一致；修复原因后 --resume：%s", exc)
        return 3


def _run_snapshot_migration(
    source_path: str, *, resume: bool = False, auto_wrap: bool = False, asset_paths: Optional[Dict[str, str]] = None
) -> int:
    from app.core import pg_baseline

    if settings.DATABASE_DIALECT != "postgresql":
        logger.error("必须以 DB_TYPE=postgresql 运行本工具（目标库配置与应用同源，契约 §2.1）")
        return 2

    # 阶段 1：precheck
    errors, warnings, version = precheck(source_path, auto_wrap=auto_wrap, asset_paths=asset_paths)
    for w in warnings:
        logger.warning("[预检] %s", w)
    if errors:
        for e in errors:
            logger.error("[预检] %s", e)
        return 1
    chain_head = _tool_head()
    if version != chain_head:
        logger.error(
            "源库版本 %s ≠ 工具所属 head %s（旧库请先在副本升级到 head；未来/未知版本拒绝）", version, chain_head
        )
        return 1
    logger.info("[预检] 通过（源版本=%s）", version)

    if auto_wrap:
        wrapped = auto_wrap_json_values(source_path)
        if wrapped:
            logger.info("[auto-wrap] 包裹 %d 个裸标量", wrapped)

    with open(source_path, "rb") as snapshot_file:
        source_digest = hashlib.file_digest(snapshot_file, "sha256").hexdigest()
    migration_id = f"sqlite-{source_digest[:32]}"

    pg_engine = create_engine(build_database_url())
    try:
        # 阶段 2：baseline / 三状态
        from alembic.config import Config

        cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        cfg.attributes["configure_logger"] = False

        with pg_engine.connect() as conn:
            state = pg_baseline.get_import_state(conn)
        if state is not None:
            if not resume:
                logger.error(
                    "目标库存在导入未完成标记（migration_id=%s）：校验后以 --resume 恢复", state["migration_id"]
                )
                if state["migration_id"] != migration_id:
                    logger.error("迁移 ID 不匹配（标记=%s 本次=%s）——拒绝恢复", state["migration_id"], migration_id)
                    return 2
                return 3
            if state["migration_id"] != migration_id or state["source_digest"] != source_digest:
                logger.error("标记校验失败（migration_id/source_digest 不匹配）——拒绝恢复")
                return 2
            if state["tool_version"] != TOOL_VERSION:
                logger.error("工具版本不匹配——拒绝恢复")
                return 2
            checkpoint = state["checkpoint"]
            if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("completed"), dict):
                logger.error("检查点格式非法——拒绝恢复")
                return 2
            register_all_models()
            table_names = [table.name for table in Base.metadata.sorted_tables]
            completed = checkpoint["completed"]
            if set(completed) != set(table_names[: len(completed)]):
                logger.error("检查点不是依赖序的完整前缀——拒绝恢复")
                return 2
            with pg_engine.connect() as conn:
                if pg_baseline.read_pg_alembic_version(conn) != chain_head:
                    logger.error("目标版本与工具 head 不匹配——拒绝恢复")
                    return 2
                for table_name in table_names:
                    actual = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                    expected = completed.get(table_name, 0)
                    if type(expected) is not int or expected < 0 or actual != expected:
                        logger.error("检查点行数不匹配：%s——拒绝恢复", table_name)
                        return 2
            checkpoint = {"completed": dict(completed)}
            logger.info("[恢复] 已完成 %d 表，继续导入", len(checkpoint.get("completed", {})))
        else:
            checkpoint = {"completed": {}}
            try:
                initialized = pg_baseline.initialize_pg_baseline(
                    cfg,
                    chain_head,
                    import_state={
                        "migration_id": migration_id,
                        "source_digest": source_digest,
                        "tool_version": TOOL_VERSION,
                        "checkpoint": checkpoint,
                    },
                )
            except RuntimeError as exc:
                logger.error("目标库状态非法：%s", exc)
                return 2
            if not initialized:
                logger.error("目标库非空库（已有版本/业务数据）——拒绝导入（三状态规则）")
                return 2
            checkpoint = {"completed": {}}

        # 阶段 3：import（依赖序；跳过已完成表）
        sqlite_conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        sqlite_conn.row_factory = sqlite3.Row
        try:
            register_all_models()
            total = 0
            for table in Base.metadata.sorted_tables:
                if table.name in checkpoint["completed"]:
                    continue
                n = import_table(
                    sqlite_conn,
                    pg_engine,
                    table,
                    state=checkpoint,
                    migration_id=migration_id,
                    source_digest=source_digest,
                )
                total += n
                logger.info("[导入] %s: %d 行", table.name, n)
            logger.info("[导入] 完成，共 %d 行", total)

            # 阶段 4：sequence 校准
            for line in calibrate_sequences(pg_engine):
                logger.info("[sequence] %s", line)

            # 阶段 5：verify
            problems = verify_counts_and_digests(sqlite_conn, pg_engine, Base.metadata.sorted_tables)
            if problems:
                for p in problems:
                    logger.error("[核对] %s", p)
                return 3
            logger.info("[核对] 全部 %d 表行数/主键集合/内容摘要一致", len(Base.metadata.sorted_tables))
        finally:
            sqlite_conn.close()

        # 阶段 6：finalize
        with pg_engine.begin() as conn:
            pg_baseline.clear_import_state(conn)
        logger.info("[完成] 导入标记已清除")
        _print_switch_guide(source_path)
        return 0
    finally:
        pg_engine.dispose()


def _tool_head() -> str:
    """工具所属代码的唯一 head（迁移链单一真相源）。"""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"迁移链多 head：{heads}")
    return heads[0]


def _print_switch_guide(source_path: str) -> None:
    logger.info("=" * 60)
    logger.info("切换指引（契约 §3：无损回退窗口 = 首次正常启动前的离线核对）")
    logger.info("1. 保持源库停写；目标 PG 已就绪（应用尚未启动过）")
    logger.info("2. 离线核对：psql 抽查关键表/行数（或重跑本工具 --precheck 对照源库）")
    logger.info("3. 首次启动应用（DB_TYPE=postgresql）——首次启动即结束无损回退窗口")
    logger.info("4. 回退边界：首次启动后回切旧库将丢失切换后写入；源库 %s 请归档保留", source_path)
    logger.info("=" * 60)


def main(argv: Optional[Sequence[str]] = None) -> int:
    # force：应用链路导入可能已给 root 装默认 WARNING 级 handler（basicConfig 幂等不覆盖）
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    parser = argparse.ArgumentParser(description="BtDeck SQLite → PostgreSQL 迁移工具（v1.0.8）")
    parser.add_argument("--source", default=None, help="源 SQLite 路径（默认 settings.DATABASE_PATH）")
    parser.add_argument("--precheck", action="store_true", help="仅预检（不连 PG，退出码 0/1）")
    parser.add_argument(
        "--auto-wrap-scalar", action="store_true", help="JSON 裸标量包裹为数组（仅匹配字段元素类型；出报告）"
    )
    parser.add_argument("--resume", action="store_true", help="从检查点恢复未完成导入")
    parser.add_argument("--source-config", help="原部署 config.yaml（含加密下载器时必需）")
    parser.add_argument("--target-config", help="目标部署 config.yaml（须与源 SM4 密钥同源）")
    parser.add_argument("--backup-root", default=str(BACKEND_ROOT), help="目标部署后端根目录，用于相对备份路径核验")
    args = parser.parse_args(argv)

    source = args.source or str(settings.DATABASE_PATH)
    if not Path(source).exists():
        logger.error("源库不存在: %s", source)
        return 1

    asset_paths = {
        "source_config": args.source_config or str(Path(source).parent / "config.yaml"),
        "target_config": args.target_config or str(settings.YAML_PATH),
        "backup_root": args.backup_root,
    }
    if args.precheck:
        errors, warnings, version = precheck(source, auto_wrap=args.auto_wrap_scalar, asset_paths=asset_paths)
        for w in warnings:
            logger.warning("[预检] %s", w)
        for e in errors:
            logger.error("[预检] %s", e)
        logger.info("[预检] 源版本=%s；错误=%d 警告=%d", version, len(errors), len(warnings))
        return 1 if errors else 0

    return run_migration(source, resume=args.resume, auto_wrap=args.auto_wrap_scalar, asset_paths=asset_paths)


if __name__ == "__main__":
    sys.exit(main())
