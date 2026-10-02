"""dialect_sql 双方言分发单点契约测试（v1.0.8 P2 任务2.2/2.4 验收）。

覆盖：
1. 孤儿父目录行为矩阵——Python 实现（SQLite 语义源）× PG 表达式语义模拟 ×
   SQLite 实连执行三方对拍（真实 PG 执行验证归 P4 强制 CI）；
2. ci_like/ci_contains 折叠与 autoescape——与 SQLAlchemy 原生 contains 渲染
   的参数/语义等价性（SQLite 路径零变化由同一断言保证）；
3. JSON 数组展开双方言渲染。
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

import pytest
from sqlalchemy import Column, Integer, String, table, true
from sqlalchemy.dialects import postgresql, sqlite

from app.core import dialect_sql
from app.core.dialect_sql import (
    _autoescape_like,
    _fold_ascii,
    ci_contains,
    ci_like,
    dialect_insert,
    json_array_values,
    orphan_parent_dir_expr,
)
from app.services.orphan_folder_grouping import orphan_parent_dir

# 审查第 4 轮给出的对拍矩阵（含反斜杠/末尾分隔符/NULL 边界）
PARENT_DIR_MATRIX = [
    ("C:\\media\\movie.mkv", "C:/media"),
    ("/media/", "/media"),
    ("/media/movie.mkv", "/media"),
    ("C:\\media\\", "C:/media"),
    ("file.txt", "file.txt"),  # 无分隔符：原样
    ("/a/b/c.txt", "/a/b"),
    ("", ""),
    (None, ""),
    ("\\\\nas\\share\\f.iso", "//nas/share"),  # UNC 反斜杠
]


class TestOrphanParentDirMatrix:
    """任务2.2 契约：三实现对拍。"""

    def test_python_impl_matrix(self) -> None:
        for raw, expected in PARENT_DIR_MATRIX:
            assert orphan_parent_dir(raw) == expected, f"python impl: {raw!r}"

    def test_pg_expression_semantics_simulation(self) -> None:
        """PG 表达式语义模拟：translate(\\→/) + regexp_replace('/[^/]*$') + coalesce。

        regexp_replace 无 g 标志替换首个匹配；模式锚定结尾，唯一匹配。
        """
        for raw, expected in PARENT_DIR_MATRIX:
            if raw is None:
                simulated: Any = ""  # coalesce(NULL→'')
            else:
                norm = raw.replace("\\", "/")
                simulated = re.sub(r"/[^/]*$", "", norm)
            assert simulated == expected, f"pg expr simulation: {raw!r}"

    def test_sqlite_actual_execution(self) -> None:
        """SQLite 实连执行 bt_orphan_parent_dir（GROUP BY 语义路径）。"""
        from app.services.orphan_folder_grouping import install_orphan_folder_functions

        conn = sqlite3.connect(":memory:")
        try:
            install_orphan_folder_functions(conn)
            for raw, expected in PARENT_DIR_MATRIX:
                got = conn.execute("SELECT bt_orphan_parent_dir(?)", (raw,)).fetchone()[0]
                assert got == expected, f"sqlite exec: {raw!r}"
        finally:
            conn.close()

    def test_pg_expression_compiles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dialect_sql, "DIALECT", "postgresql")
        t = table("t", Column("file_path", String))
        expr = orphan_parent_dir_expr(t.c.file_path)
        sql = str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        assert "regexp_replace" in sql and "translate" in sql and "coalesce" in sql


class TestCaseInsensitiveMatching:
    """任务2.4 契约：SQLite 原生（零变化）× PG 折叠（A–Z only，locale 构造性无关）。"""

    t = table("t", Column("name", String), Column("id", Integer))

    def test_sqlite_path_is_native_contains(self) -> None:
        """SQLite 方言断言：分发函数必须逐字等价原生 contains(autoescape=True) 渲染。"""
        expr = ci_contains(self.t.c.name, "a%b")
        native = self.t.c.name.contains("a%b", autoescape=True)
        assert str(expr.compile(dialect=sqlite.dialect())) == str(native.compile(dialect=sqlite.dialect()))
        assert expr.compile(dialect=sqlite.dialect()).params == native.compile(dialect=sqlite.dialect()).params

    def test_fold_ascii_only(self) -> None:
        assert _fold_ascii("AbC-ÉÜ") == "abc-ÉÜ"  # 非 ASCII 原样（允许差异 §6 第 3 条）

    def test_autoescape_parity_with_sqlalchemy(self) -> None:
        """转义结果与 SQLAlchemy autoescape 参数逐字一致（含转义符自身）。"""
        native_param = (
            self.t.c.name.contains("a%/b_c", autoescape=True).compile(dialect=sqlite.dialect()).params
        )
        native_value = list(native_param.values())[0]
        assert _autoescape_like("a%/b_c") == native_value == "a/%//b/_c"

    def test_ci_like_keeps_wildcard_semantics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """原始模式位点：% 仍是通配符（与 torrent_helpers 现状一致，不做 autoescape）。"""
        monkeypatch.setattr(dialect_sql, "DIALECT", "postgresql")
        sql = str(ci_like(self.t.c.name, "%A%").compile(dialect=postgresql.dialect()))
        assert "translate" in sql  # PG 侧折叠
        monkeypatch.setattr(dialect_sql, "DIALECT", "sqlite")
        sqlite_sql = str(ci_like(self.t.c.name, "%A%").compile(dialect=sqlite.dialect()))
        assert sqlite_sql == str(self.t.c.name.like("%A%").compile(dialect=sqlite.dialect()))


class TestUpsertAndJson:
    """任务2.3：upsert 基座与 JSON 展开渲染。"""

    t = table("t", Column("id", Integer), Column("name", String))

    def test_dialect_insert_sqlite(self) -> None:
        stmt = dialect_insert(self.t).values(id=1)
        sql = str(stmt.compile(dialect=sqlite.dialect()))
        assert "INSERT INTO t" in sql

    def test_dialect_insert_pg_on_conflict_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dialect_sql, "DIALECT", "postgresql")
        stmt = dialect_insert(self.t).values(id=1).on_conflict_do_nothing(index_elements=["id"])
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT (id) DO NOTHING" in sql

    def test_json_array_values_sqlite_keeps_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SQLite：json_valid 守卫 + 坏数据→'[]'（历史宽容行为零变化）。"""
        monkeypatch.setattr(dialect_sql, "DIALECT", "sqlite")
        from sqlalchemy import select

        values = json_array_values(self.t.c.name, "v")
        sql = str(select(values.c.value).select_from(self.t).join(values, true()).compile(dialect=sqlite.dialect()))
        assert "json_valid" in sql and "json_each" in sql

    def test_json_array_values_pg_cast_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """PG：cast 即守卫（非法 JSON/非数组执行时 fail-fast，契约 §4.3）。"""
        monkeypatch.setattr(dialect_sql, "DIALECT", "postgresql")
        from sqlalchemy import select

        values = json_array_values(self.t.c.name, "v")
        sql = str(select(values.c.value).select_from(self.t).join(values, true()).compile(dialect=postgresql.dialect()))
        assert "CAST" in sql.upper() and "jsonb_array_elements_text" in sql


class TestFoldHelpers:
    def test_fold_matrix(self) -> None:
        assert _fold_ascii("") == ""
        assert _fold_ascii("ABC xyz 123") == "abc xyz 123"
        assert _fold_ascii("İı") == "İı"  # 土耳其语特例不受影响（构造性 A–Z only）

    def test_autoescape_double_escape(self) -> None:
        assert _autoescape_like("//") == "////"
        assert _autoescape_like("100%_") == "100/%/_"
