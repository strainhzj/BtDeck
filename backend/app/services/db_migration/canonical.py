# -*- coding: utf-8 -*-
"""双向迁移规范化摘要算法（database-migration-ui W1-5，PLANS §6.1 阶段 5）。

``digest_version = btdeck-canonical-v1``（app.core.database_protocol 单点声明）：

- 全列类型归一：datetime 统一 UTC naive ISO（微秒精度）；bytes hex；其余原样；
- JSON 列 **SQL NULL 与 JSON null 区分**：以 ``__sql_null__<col>`` 边注键
  携带 SQL NULL 布尔值，JSON 值域中的 null 保留为 null（Text JSON 不重编码）；
- 字符串主键跨库固定排序：PG 侧 ``collate("C")``，SQLite 侧天然 BINARY；
- 行编码：``json.dumps(sort_keys=True, ensure_ascii=False)`` + 换行 → SHA-256；
  表级摘要 = 依主键序流式累积；
- schema 指纹：表/列（名/类型/可空/主键）清单排序摘要（receipt 落盘对拍）。

算法一经发布不可改动；任何变更必须新开版本号（receipt.digest_version 不
匹配即拒绝复用旧凭据，PLANS §3.1/§6.3）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

from sqlalchemy import String

from app.core.database_protocol import DIGEST_VERSION_CANONICAL_V1

DIGEST_VERSION = DIGEST_VERSION_CANONICAL_V1
SQL_NULL_FLAG_PREFIX = "__sql_null__"


def normalize_value(value: Any) -> Any:
    """归一单值为可 JSON 编码形态；不支持的类型显式抛错（防静默截断）。"""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): normalize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_value(v) for v in value]
    if isinstance(value, float):
        # 摘要阶段浮点原样编码；NaN/Infinity 由预检拒绝（T12）——json.dumps
        # 会产出对应字面量，双向一致即忠实暴露预检缺口
        return value
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    raise TypeError(f"canonical-v1 不支持的摘要类型: {type(value).__name__}")


def canonical_row_bytes(row: Mapping[str, Any]) -> bytes:
    """单行规范化编码（sort_keys 消列序差异；ensure_ascii=False 保 UTF-8 语义）。"""
    normalized = {key: normalize_value(value) for key, value in row.items()}
    return (json.dumps(normalized, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def digest_rows(rows: Iterable[Mapping[str, Any]]) -> str:
    """表级内容摘要：依传入序（调用方保证主键序）流式累积 SHA-256。"""
    h = hashlib.sha256()
    for row in rows:
        h.update(canonical_row_bytes(row))
    return h.hexdigest()


def digest_pk_tuples(pks: Iterable[Sequence[Any]]) -> str:
    """主键集合摘要：元组归一编码（消除 sqlite3.Row / SQLAlchemy Row 差异）。"""
    h = hashlib.sha256()
    for pk in pks:
        h.update((json.dumps([normalize_value(v) for v in pk]) + "\n").encode("utf-8"))
    return h.hexdigest()


def sqlite_pk_order_expr(table: Any) -> Sequence[Any]:
    """SQLite 侧主键排序（BINARY 天然跨库可比）。"""
    return list(table.primary_key.columns)


def pg_pk_order_expr(table: Any) -> Sequence[Any]:
    """PG 侧主键排序：字符串主键固定 C collation（跨库一致，PLANS §6.1）。"""
    return [column.collate("C") if isinstance(column.type, String) else column for column in table.primary_key.columns]


def pk_order_expr(table: Any, dialect_name: str) -> Sequence[Any]:
    """方言感知主键排序（SQLite 替身目标用原生序；PG 用 C collation）。"""
    return pg_pk_order_expr(table) if dialect_name == "postgresql" else sqlite_pk_order_expr(table)


def schema_fingerprint(tables: Iterable[Any]) -> str:
    """schema 指纹：表/列（名/类型/可空/主键）清单排序摘要（receipt 落盘）。"""
    lines = []
    for table in sorted(tables, key=lambda t: t.name):
        pk_names = {c.name for c in table.primary_key.columns}
        for column in sorted(table.columns, key=lambda c: c.name):
            lines.append(
                f"{table.name}|{column.name}|{column.type}|nullable={int(column.nullable)}|pk={int(column.name in pk_names)}"
            )
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def with_sql_null_flags(row: Mapping[str, Any], json_columns: Sequence[str]) -> Dict[str, Any]:
    """为 JSON 列附加 SQL NULL 边注（SQL NULL ≠ JSON null 的区分载体）。"""
    out = dict(row)
    for name in json_columns:
        out[SQL_NULL_FLAG_PREFIX + name] = row.get(name) is None
    return out
