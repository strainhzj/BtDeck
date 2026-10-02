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
  5. verify    —— 行数 + 主键集合 + 内容摘要（规范化行 repr 的 md5）双库对账
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
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# 允许脚本从 backend/ 或仓库根运行（backend/scripts/ 下的既有惯例）
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import Integer, create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.types import Boolean, DateTime  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.model_registry import register_all_models  # noqa: E402
from app.database import Base, build_database_url  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_sqlite_to_pg")

TOOL_VERSION = "1.0.0"
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
                        if isinstance(elem, bool) or not isinstance(elem, int):
                            errors.append(f"{key} id={row_id}: 非整数元素 {elem!r}")
                    elif not isinstance(elem, str):
                        errors.append(f"{key} id={row_id}: 非字符串元素 {elem!r}")
            elif isinstance(parsed, (int, str)) and not isinstance(parsed, bool):
                # 裸标量：与元素类型匹配才可包裹
                matches = (elem_type == "integer" and isinstance(parsed, int)) or (
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
            bad = source.execute(
                f"SELECT COUNT(*) FROM {table.name} "
                f"WHERE {col} IS NOT NULL AND {col} NOT LIKE '____-__-__ __:__:__.______' "
                f"AND {col} NOT LIKE '____-__-__ __:__:__' "
                f"AND {col} NOT LIKE '____-__-__T__:__:__.______' AND {col} NOT LIKE '____-__-__T__:__:__'"
            ).fetchone()[0]
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


def precheck(source_path: str, *, auto_wrap: bool = False) -> Tuple[List[str], List[str], Optional[str]]:
    """预检（不连 PG）。Returns: (errors, warnings, source_version)。"""
    conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        version = read_sqlite_version(conn)
        errors, warnings = check_json_contract(conn, auto_wrap=auto_wrap)
        errors += check_boolean_columns(conn)
        errors += check_datetime_text(conn)
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
        elif isinstance(col.type, Boolean):
            out[col.name] = bool(val)
        elif isinstance(col.type, DateTime) and isinstance(val, str):
            norm = val.replace("T", " ")
            out[col.name] = datetime.fromisoformat(norm)
        else:
            out[col.name] = val
    return out


def auto_wrap_json_values(source_path: str) -> int:
    """--auto-wrap-scalar：把与字段元素类型匹配的裸标量包裹为数组（就地修改源库副本语义：写回源库）。"""
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
    rows = sqlite_conn.execute(f"SELECT * FROM {table.name}").fetchall()
    imported = 0
    with pg_engine.begin() as pg_conn:
        for start in range(0, len(rows), BATCH_ROWS):
            batch = [row_transform(table, r) for r in rows[start : start + BATCH_ROWS]]
            if batch:
                pg_conn.execute(table.insert(), batch)
                imported += len(batch)
    _update_checkpoint(pg_engine, state, table.name, imported, migration_id, source_digest)
    return imported


def _update_checkpoint(
    pg_engine: Engine, state: Dict[str, Any], done_table: str, rows: int, migration_id: str, source_digest: str
) -> None:
    state["completed"][done_table] = rows
    with pg_engine.begin() as conn:
        from app.core.pg_baseline import set_import_state

        set_import_state(conn, migration_id, source_digest, TOOL_VERSION, state)


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
    h = hashlib.md5()
    for key in sorted(tuple(r) for r in rows):
        h.update(repr(key).encode("utf-8", errors="replace"))
    return h.hexdigest()


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
            if pks:
                pk_list = ", ".join(f'"{c}"' for c in pks)
                s_pks = _row_digest(sqlite_conn.execute(f"SELECT {pk_list} FROM {table.name}").fetchall())
                p_pks = _row_digest(pg.execute(text(f"SELECT {pk_list} FROM {table.name}")).fetchall())
                if s_pks != p_pks:
                    problems.append(f"{table.name}: 主键集合不一致")
    return problems


# ==================== 主流程 ====================


def run_migration(source_path: str, *, resume: bool = False, auto_wrap: bool = False) -> int:
    from app.core import pg_baseline

    if settings.DATABASE_DIALECT != "postgresql":
        logger.error("必须以 DB_TYPE=postgresql 运行本工具（目标库配置与应用同源，契约 §2.1）")
        return 2

    # 阶段 1：precheck
    errors, warnings, version = precheck(source_path, auto_wrap=auto_wrap)
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

    source_digest = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    migration_id = f"{Path(source_path).name}-{source_digest[:12]}"

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
            checkpoint = dict(state["checkpoint"])
            logger.info("[恢复] 已完成 %d 表，继续导入", len(checkpoint.get("completed", {})))
        else:
            initialized = pg_baseline.initialize_pg_baseline(cfg, chain_head)
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
            logger.info("[核对] 全部 %d 表行数/主键集合一致", len(Base.metadata.sorted_tables))
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
    args = parser.parse_args(argv)

    source = args.source or str(settings.DATABASE_PATH)
    if not Path(source).exists():
        logger.error("源库不存在: %s", source)
        return 1

    if args.precheck:
        errors, warnings, version = precheck(source, auto_wrap=args.auto_wrap_scalar)
        for w in warnings:
            logger.warning("[预检] %s", w)
        for e in errors:
            logger.error("[预检] %s", e)
        logger.info("[预检] 源版本=%s；错误=%d 警告=%d", version, len(errors), len(warnings))
        return 1 if errors else 0

    return run_migration(source, resume=args.resume, auto_wrap=args.auto_wrap_scalar)


if __name__ == "__main__":
    sys.exit(main())
