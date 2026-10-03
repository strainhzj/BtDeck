"""基线对拍 CI 门禁（v1.0.8 任务3.4，契约 docs/postgresql-contract.md §3）。

语义级比较（非 DDL 文本逐字比较）：
- 对象 A：迁移链 head schema——临时 SQLite 库跑完整 alembic 链后 introspect
  （SQLite 生产 schema 唯一事实源）
- 对象 B：PG squash 基线 schema 来源——``Base.metadata``（经 model_registry
  完整注册；PG ``create_all`` 的输入）
- 比较项：表集合/列（名/类型/可空）/主键/唯一与普通索引（名/列/唯一/partial
  where 谓词）/CHECK 约束/外键
- 差异必须 ⊆ ``ALLOWED_DIFFERENCES`` 登记表（每条注明依据）；未登记差异即失败
  ——防止 ORM↔链漂移在 PG 基线上静默漏建（notification 索引为先例）。
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import sqlite as sqlite_dialect

from app.core.model_registry import register_all_models
from app.database import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]
_HEAD = "c9e0f1a2b3c4"

_WS = re.compile(r"\s+")


def _norm(text: str | None) -> str | None:
    """空白归一（跨方言/生成器的格式差异消除）。"""
    return _WS.sub(" ", (text or "").strip()) if text else text


def _typeof_guard_normalized(sqltext: str) -> str:
    """typeof 守卫等价归一（允许差异 #1）：SQLite 链侧 typeof 守卫 ≡ ORM 中立边界。

    契约 §6 第 5 条：typeof() 守卫仅留链（防 TEXT 残留）；ORM 中立形式供 PG
    基线。两者共同保证"非负有限数值"，typeof 额外拒文本——语义登记为允许差异。
    """
    text = _norm(sqltext)
    for guard, neutral in (
        (
            "typeof(ratio) IN ('integer', 'real') AND ratio >= 0 AND ratio <= 1.7976931348623157e308",
            "ratio >= 0 AND ratio <= 1.7976931348623157e308",
        ),
        (
            "typeof(ratio_limit) IN ('integer', 'real') AND ratio_limit >= 0 AND ratio_limit <= 1.7976931348623157e308",
            "ratio_limit >= 0 AND ratio_limit <= 1.7976931348623157e308",
        ),
    ):
        text = text.replace(guard, neutral)
    return text


def _chain_schema(db_path: str) -> dict[str, dict[str, Any]]:
    """跑完整迁移链后 introspect，返回规范化 schema 清单。"""
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    os.environ["DATABASE_PATH"] = db_path
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        insp = inspect(engine)
        schema: dict[str, dict[str, Any]] = {}
        for table in sorted(insp.get_table_names()):
            if table == "alembic_version":
                continue  # 迁移链版本表，非业务 schema
            cols = sorted((c["name"], str(c["type"]).upper(), bool(c["nullable"])) for c in insp.get_columns(table))
            _pk = insp.get_pk_constraint(table).get("constrained_columns") or []
            pk = tuple(sorted(_pk)) if _pk else ()
            idx = sorted(
                (
                    i["name"],
                    tuple(i["column_names"] or []),
                    bool(i["unique"]),
                    _norm(str(i.get("dialect_options", {}).get("sqlite_where", "")) or ""),
                )
                for i in insp.get_indexes(table)
            )
            checks = sorted(_typeof_guard_normalized(cc.get("sqltext", "")) for cc in insp.get_check_constraints(table))
            fks = sorted(
                (fk["referred_table"], tuple(fk["constrained_columns"] or [])) for fk in insp.get_foreign_keys(table)
            )
            schema[table] = {"cols": cols, "pk": tuple(sorted(pk)), "idx": idx, "checks": checks, "fks": fks}
        return schema
    finally:
        engine.dispose()


def _metadata_schema() -> dict[str, dict[str, Any]]:
    """从 ORM metadata 构造同构清单（PG 基线 create_all 的输入）。"""
    register_all_models()
    dialect = sqlite_dialect.dialect()

    def _col_type(col: Any) -> str:
        return _norm(str(col.type.compile(dialect))).upper()

    schema: dict[str, dict[str, Any]] = {}
    for table in sorted(Base.metadata.sorted_tables, key=lambda t: t.name):
        cols = sorted((c.name, _col_type(c), bool(c.nullable)) for c in table.columns)
        pk = tuple(sorted(col.name for col in table.primary_key.columns))

        def _idx_where(i: Any) -> str:
            where_val = i.kwargs.get("sqlite_where", None)
            if where_val is None:
                return ""
            # ORM 侧 where 为表达式（dr == 0）——用 literal_binds 编译为 SQL 文本，
            # 与链侧 introspect 文本同构（ torrent_info.dr = 0 → 列名限定差异再归一）
            compiled = where_val.compile(dialect=sqlite_dialect.dialect(), compile_kwargs={"literal_binds": True})
            # 列限定前缀归一（torrent_info.dr = 0 → dr = 0，与链侧 introspect 同构）
            return _norm(re.sub(rf"\b{table.name}\.", "", str(compiled)))

        idx = sorted(
            (
                i.name,
                tuple(col.name for col in i.columns),
                bool(i.unique),
                _idx_where(i),
            )
            for i in table.indexes
        )
        from sqlalchemy import CheckConstraint

        checks = sorted(
            _typeof_guard_normalized(str(c.sqltext)) for c in table.constraints if isinstance(c, CheckConstraint)
        )
        fks = sorted(
            (fk.column.table.name, tuple(sorted(constraint_col.name for constraint_col in fk.constraint.columns)))
            for c in table.constraints
            if hasattr(c, "elements")
            for fk in getattr(c, "elements", [])
        )
        schema[table.name] = {"cols": cols, "pk": pk, "idx": idx, "checks": checks, "fks": fks}
    return schema


# 允许差异登记表（每条注明依据；新增条目须写明契约/审查依据）
ALLOWED_DIFFERENCES: dict[str, str] = {
    # 依据：契约 §6 第 5 条（typeof 守卫留链 / ORM 中立形式供 PG；语义等价归一处理后应抵消，
    # 若此键仍出现差异说明两侧形式超出了归一规则，需人工核验）
}


class TestBaselineSchemaParity:
    """任务3.4：PG 基线（metadata）↔ 迁移链 head（SQLite 实库）语义对拍。"""

    def test_chain_matches_baseline_semantically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chain = _chain_schema(str(Path(tmp) / "chain.db"))
        baseline = _metadata_schema()

        chain_tables = set(chain)
        baseline_tables = set(baseline)
        only_chain = chain_tables - baseline_tables
        only_baseline = baseline_tables - chain_tables
        assert not only_chain, f"链有而 ORM 缺（PG 基线会漏表）: {sorted(only_chain)}"
        assert not only_baseline, f"ORM 有而链无（autogenerate 幻影）: {sorted(only_baseline)}"

        problems: list[str] = []
        for table in sorted(chain_tables & baseline_tables):
            for aspect in ("cols", "pk", "idx", "checks", "fks"):
                if chain[table][aspect] != baseline[table][aspect]:
                    diff_chain = set(map(str, chain[table][aspect])) - set(map(str, baseline[table][aspect]))
                    diff_base = set(map(str, baseline[table][aspect])) - set(map(str, chain[table][aspect]))
                    for d in diff_chain:
                        key = f"{table}.{aspect}:{d}"
                        if key not in ALLOWED_DIFFERENCES:
                            problems.append(f"[链独有] {table}.{aspect} {d}")
                    for d in diff_base:
                        key = f"{table}.{aspect}:{d}"
                        if key not in ALLOWED_DIFFERENCES:
                            problems.append(f"[ORM 独有] {table}.{aspect} {d}")
        assert not problems, "未登记的基线↔链差异（新增迁移或模型变更后须同步两侧并登记）：\n" + "\n".join(problems)


def test_defaults_unique_constraints_and_foreign_key_actions(tmp_path, monkeypatch):
    """补齐原对拍遗漏的默认值、独立唯一约束和外键目标/删除行为。"""
    from sqlalchemy import UniqueConstraint

    source = tmp_path / "parity.db"
    monkeypatch.setenv("DATABASE_PATH", str(source))
    _chain_schema(str(source))
    engine = create_engine(f"sqlite:///{source}")
    register_all_models()

    def default(value):
        if value is None:
            return None
        return (
            str(value)
            .strip("()'\"")
            .lower()
            .replace("false", "0")
            .replace("true", "1")
            .replace("now", "current_timestamp")
        )

    problems = []
    try:
        inspector = inspect(engine)
        for table in Base.metadata.sorted_tables:
            chain_columns = {column["name"]: column for column in inspector.get_columns(table.name)}
            for column in table.columns:
                chain_default = default(chain_columns[column.name]["default"])
                orm_default = default(column.server_default.arg if column.server_default else None)
                if chain_default != orm_default:
                    problems.append(
                        f"{table.name}.{column.name}: default chain={chain_default!r} metadata={orm_default!r}"
                    )
            chain_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name)}
            orm_unique = {
                tuple(c.name for c in item.columns) for item in table.constraints if isinstance(item, UniqueConstraint)
            }
            if chain_unique != orm_unique:
                problems.append(f"{table.name}: unique {chain_unique} != {orm_unique}")
            chain_fk = {
                (
                    tuple(item["constrained_columns"]),
                    item["referred_table"],
                    tuple(item["referred_columns"]),
                    item.get("options", {}).get("ondelete"),
                )
                for item in inspector.get_foreign_keys(table.name)
            }
            orm_fk = {
                (
                    tuple(c.name for c in item.columns),
                    item.referred_table.name,
                    tuple(element.column.name for element in item.elements),
                    item.ondelete,
                )
                for item in table.foreign_key_constraints
            }
            if chain_fk != orm_fk:
                problems.append(f"{table.name}: foreign keys {chain_fk} != {orm_fk}")
        assert not problems, "\n".join(problems)
    finally:
        engine.dispose()
