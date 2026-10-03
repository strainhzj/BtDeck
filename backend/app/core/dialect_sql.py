"""双方言 SQL 分发单点（v1.0.8 P2，契约 docs/postgresql-contract.md §4）。

唯一职责：SQLite 与 PostgreSQL 的**语义差异**在此集中分发。业务代码禁止
散落方言判断（P2 验收口径：方言分支仅允许本模块与 speed_sampler 聚合 SQL
双版本两处；grep 白名单见 PLANS/v1.0.8.md 任务2.3）。

分发项与契约条目对应：
- 大小写不敏感匹配（ci_like / ci_contains / ci_startswith / ci_endswith）：§4.1
  SQLite 原生 ASCII-only 折叠保持零变化；PG 双侧同一 A–Z→a–z 折叠后 LIKE
  （构造性 locale 无关，不用 ILIKE；autoescape 转义语义与 SQLAlchemy 同构）
- upsert 基座（dialect_insert）：SQLite/PG insert 构造器（on_conflict_do_* 同名 API）
- 孤儿父目录表达式（orphan_parent_dir_expr）：§"任务2.2"
  SQLite 自定义函数 bt_orphan_parent_dir；PG 纯 SQL 等价（translate+regexp_replace），
  行为矩阵由 tests/core/test_dialect_sql.py 对拍
- JSON 数组展开（json_array_values / json_array_values_from_literal）：§4.3
  SQLite json_valid 守卫+json_each（坏数据→空集，历史行为）；PG cast 即守卫
  （非法 JSON/非数组执行时 fail-fast，允许差异登记 §6 第 1/2 条）
"""

from __future__ import annotations

import re

from typing import Any

from sqlalchemy import ColumnElement, Text, case, func
from sqlalchemy.dialects.postgresql import JSONB

from app.database import DIALECT

_UPPER_ASCII = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER_ASCII = "abcdefghijklmnopqrstuvwxyz"

_LIKE_ESCAPE = "/"  # 与 SQLAlchemy autoescape 默认转义符一致


def _fold_ascii(value: str) -> str:
    """Python 侧 A–Z → a–z 折叠（与 SQL translate 同映射表，构造性 locale 无关）。"""
    return value.translate(str.maketrans(_UPPER_ASCII, _LOWER_ASCII))


def _autoescape_like(value: str, escape: str = _LIKE_ESCAPE) -> str:
    """与 SQLAlchemy ``autoescape=True`` 同构的字面量转义（%、_、转义符自身）。"""
    return value.replace(escape, escape + escape).replace("%", escape + "%").replace("_", escape + "_")


def _folded_column(column: Any) -> Any:
    """PG 侧列折叠表达式：``translate(col, 'A-Z', 'a-z')``。"""
    return func.translate(func.cast(column, Text), _UPPER_ASCII, _LOWER_ASCII)


# ========== 大小写不敏感匹配（契约 §4.1） ==========


def ci_like(column: Any, pattern: str, *, escape: str | None = None) -> ColumnElement[bool]:
    """原始 LIKE 模式的大小写不敏感匹配。

    通配符语义保留（pattern 中的 %/_ 仍为通配符，与调用方现状一致——
    torrent_helpers 各 ``.like(f"%{x}%")`` 位点）；需要字面量转义的调用方
    自行转义后传 ``escape``。
    SQLite：``column LIKE pattern``（原生 ASCII-only 折叠，历史行为零变化）。
    PG：双侧折叠后 LIKE（折叠仅映射 A–Z，非 ASCII 原样——允许差异 §6 第 3 条）。
    """
    if DIALECT == "sqlite":
        return column.like(pattern, escape=escape) if escape else column.like(pattern)
    folded_pattern = _fold_ascii(pattern)
    return (
        _folded_column(column).like(folded_pattern, escape=escape)
        if escape
        else _folded_column(column).like(folded_pattern)
    )


def ci_contains(column: Any, value: str) -> ColumnElement[bool]:
    """等价 ``column.contains(value, autoescape=True)`` 的双方言版本（§4.1）。

    用户输入的 %/_/\\/ 按字面量处理（autoescape 语义）；SQLite 走原生
    contains（零变化），PG 走折叠列 + 转义后 LIKE，转义符与 SQLAlchemy 一致（/）。
    """
    if DIALECT == "sqlite":
        return column.contains(value, autoescape=True)
    return _folded_column(column).like(f"%{_autoescape_like(_fold_ascii(value))}%", escape=_LIKE_ESCAPE)


def ci_startswith(column: Any, value: str) -> ColumnElement[bool]:
    """等价 ``column.startswith(value, autoescape=True)``（§4.1，同 ci_contains）。"""
    if DIALECT == "sqlite":
        return column.startswith(value, autoescape=True)
    return _folded_column(column).like(f"{_autoescape_like(_fold_ascii(value))}%", escape=_LIKE_ESCAPE)


def ci_endswith(column: Any, value: str) -> ColumnElement[bool]:
    """等价 ``column.endswith(value, autoescape=True)``（§4.1，同 ci_contains）。"""
    if DIALECT == "sqlite":
        return column.endswith(value, autoescape=True)
    return _folded_column(column).like(f"%{_autoescape_like(_fold_ascii(value))}", escape=_LIKE_ESCAPE)


# ========== upsert 基座（任务2.3） ==========


def dialect_insert(table: Any) -> Any:
    """方言无关 upsert 基座：返回对应方言的 insert 构造器。

    SQLite 与 PostgreSQL 的 ``on_conflict_do_update / on_conflict_do_nothing``
    API 同名同构（冲突目标列与 ``index_where`` 谓词双库语义一致，
    partial unique index 由任务1.3 双 where 声明保证）。
    """
    if DIALECT == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _pg_insert

        return _pg_insert(table)
    from sqlalchemy.dialects.sqlite import insert as _sqlite_insert

    return _sqlite_insert(table)


# ========== 孤儿直接父目录表达式（任务2.2） ==========


def orphan_parent_dir_expr(column: Any) -> Any:
    """孤儿文件直接父目录（GROUP BY / 等值过滤共用）。

    - SQLite：``bt_orphan_parent_dir`` 自定义函数（历史行为零变化；
      反斜杠归一、无分隔符原样、NULL/空串→空串）；
    - PG：纯 SQL 等价表达式——
      ``coalesce(regexp_replace(translate(col, '\\', '/'), '/[^/]*$', ''), '')``
      行为矩阵与 Python 实现对拍（tests/core/test_dialect_sql.py；
      真实 PG 执行验证归 P4 强制 CI）。
    """
    if DIALECT == "sqlite":
        return func.bt_orphan_parent_dir(column)
    normalized = func.translate(func.cast(column, Text), "\\", "/")
    return func.coalesce(func.regexp_replace(normalized, "/[^/]*$", ""), "")


# ========== JSON 数组展开（契约 §4.3，按字段定契约） ==========


def json_array_values(column: Any, alias_name: str) -> Any:
    """持久化 JSON 列的数组展开（orphan_ids_json / canonical_paths_json）。

    - SQLite：``json_valid`` 守卫 + ``json_each``（非法文本→空集，历史宽容行为）；
    - PG：``cast(col AS jsonb)`` 即守卫——非法 JSON 在 cast 时 fail-fast、
      合法非数组在 ``jsonb_array_elements_text`` 时 fail-fast（契约 §4.3 定案：
      契约违规不静默；与 SQLite 的差异登记于允许差异表 §6 第 1/2 条）。
    """
    if DIALECT == "sqlite":
        json_source = case((func.json_valid(column) == 1, column), else_="[]")
        return func.json_each(json_source).table_valued("value").alias(alias_name)
    return func.jsonb_array_elements_text(func.cast(column, JSONB)).table_valued("value").alias(alias_name)


def json_array_values_from_literal(payload: str, alias_name: str) -> Any:
    """应用内构造 JSON 字面量的数组展开（deletion_task_manager 活动删除 ID 集合）。

    输入恒为 ``json.dumps(list)`` 产物（无损坏面，契约 §4.3）；SQLite 保持
    ``json_each(literal)`` 原样，PG 走 cast+jsonb_array_elements_text。
    """
    from sqlalchemy import literal

    if DIALECT == "sqlite":
        return func.json_each(literal(payload)).table_valued("value").alias(alias_name)
    return func.jsonb_array_elements_text(func.cast(literal(payload), JSONB)).table_valued("value").alias(alias_name)


# ========== 正则搜索（契约 §4.2，任务2.1） ==========

# PG ARE 不支持/语义分歧的构造（共同子集校验拒绝清单；SQLite 全语法不受影响）。
# 拒绝是保守取向：子集外表达式在请求校验期 4xx，而非执行期产生语义分歧。
_PG_UNSUPPORTED_CONSTRUCTS: tuple[tuple[str, Any], ...] = (
    ("lookaround（前瞻/后顾断言）", re.compile(r"\(\?<?[=!]")),
    ("named group / 命名反向引用", re.compile(r"\(\?P[<=]")),
    ("inline flags / 注释 / branch reset", re.compile(r"\(\?[#iLmsaux]|\(\?\|")),
    ("word boundary \\b（PG 用 \\y）", re.compile(r"\\b")),
    ("backreference 反向引用", re.compile(r"\\[1-9]")),
    ("possessive quantifier 独占量词", re.compile(r"[*+?}]\+")),
    ("unicode property / \\u 转义", re.compile(r"\\[pP]\{|\\u[0-9a-fA-F]{4}|\\x\{")),
)


def validate_regex_pattern_for_dialect(pattern: str, *, dialect: str | None = None) -> None:
    """PG 请求与迁移模板共用子集校验；SQLite VERSION1 保持原样。"""
    if (dialect or DIALECT) == "sqlite":
        return
    i = 0
    in_class = False
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            i += 1
            if i >= len(pattern) or pattern[i] not in r"dDsSwWAZfnrtv\\.^$*+?{}[]()|-":
                raise ValueError("regex escape is unsupported on PostgreSQL common subset")
        elif char == "[":
            if in_class:
                raise ValueError("nested character sets are unsupported on PostgreSQL")
            in_class = True
        elif char == "]":
            in_class = False
        elif not in_class and pattern.startswith("(?", i) and not pattern.startswith("(?:", i):
            raise ValueError("regex group extension is unsupported on PostgreSQL common subset")
        elif not in_class and char in "*+?}" and pattern[i : i + 2].endswith("+") and len(pattern[i : i + 2]) == 2:
            raise ValueError("possessive quantifier is unsupported on PostgreSQL")
        elif in_class and pattern[i : i + 2] in ("&&", "--", "~~", "||"):
            raise ValueError("character set operation is unsupported on PostgreSQL")
        i += 1
    for bound in re.findall(r"\{(\d+)(?:,(\d*))?\}", pattern):
        if any(int(value) > 255 for value in bound if value):
            raise ValueError("PostgreSQL regex repetition bounds must not exceed 255")


def _pg_regex_pattern(pattern: str) -> str:
    """保持 Python 默认 dot/尾锚点语义；字符集与转义原样保留。"""
    result = []
    in_class = False
    escaped = False
    for char in pattern:
        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\":
            result.append(char)
            escaped = True
        elif char == "[":
            in_class = True
            result.append(char)
        elif char == "]":
            in_class = False
            result.append(char)
        elif not in_class and char == ".":
            result.append(r"[^\n]")
        elif not in_class and char == "$":
            result.append(r"(?=\n?\Z)")
        else:
            result.append(char)
    return "".join(result)


def regex_match_expr(column: Any, pattern: str, *, case_sensitive: bool) -> ColumnElement[bool]:
    """正则匹配谓词（双方言分发）。

    SQLite：``bt_regexp(pattern, column, cs) == 1``（自定义函数 + 10ms 单次
    匹配超时，历史行为零变化）；
    PG：``column ~ pattern`` / ``column ~* pattern``（原生 ARE；模式应为
    ``validate_regex_pattern_for_dialect`` 通过的共同子集）。
    """
    if DIALECT == "sqlite":
        return func.bt_regexp(pattern, column, int(bool(case_sensitive))) == 1
    op = "~" if case_sensitive else "~*"
    return func.coalesce(column.op(op)(_pg_regex_pattern(pattern)), False)


def timestamp_parameter(value: Any) -> Any:
    """裸 SQL 时间参数：SQLite 保持秒级文本，asyncpg 需要 datetime 对象。"""
    if DIALECT == "sqlite":
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value.replace(microsecond=0)
