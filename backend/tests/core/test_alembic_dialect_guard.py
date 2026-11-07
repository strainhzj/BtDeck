"""alembic 迁移双方言禁例守卫（checklist 代码化，2026-11-07 双方言审计产物）。

锚定事件：cuser.py raw SQL `must_change_password=0` 整数字面量打 Boolean 列，
SQLite 全量回归容忍所以一路绿，生产 PG 实机才炸（DatatypeMismatch）。同类模式
在历史迁移中存在 9 处潜伏（基线 stamp 机制隔离，今日不可达——见
tests/pg_integration/test_pg_endpoints.py 模块注释与审计报告），但**未来新增
revision 照抄即炸**。本守卫把「新迁移双方言 checklist」直接编码为断言：

规则（checklist 本体，禁止在 versions/ 出现，历史违规冻结见 _EXPECTED_VIOLATIONS）：
- ``sqlite_only``：SQLite 专有语法——``UPDATE OR IGNORE`` / ``datetime('now')`` /
  ``INDEXED BY`` / ``sqlite_master`` / ``printf(`` / ``PRAGMA``
- ``sa_text_bool_default``：``server_default=sa.text("0"/"1")`` —— PG DDL 渲染
  ``DEFAULT 0``（未加引号整数）建列即炸；唯一正确形式是 Python 字符串
  ``server_default="0"``（渲染 ``DEFAULT '0'``，PG 字面量强转 boolean）
- ``bool_set_int``：raw SQL ``SET <Boolean列> = 0/1``（cuser 同类；改用 bool
  参数绑定或 TRUE/FALSE 字面量）
- ``bool_where_int``：raw SQL ``WHERE <Boolean列> = 0/1``（PG boolean=integer
  无此 operator；改 TRUE/FALSE）

Boolean 列名清单从注册模型动态收集（跨全表 Boolean 类型列），避免手工清单漂移。
历史违规按 (文件 → 规则集) 冻结在 ``_EXPECTED_VIOLATIONS``：新增文件出现任何
规则命中 → 本测试红；冻结文件若被修复 → 提示从冻结表移除（防名单腐化）。
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"


def _boolean_column_names() -> frozenset[str]:
    """从注册模型收集全部 Boolean 列名（动态，防手工清单漂移）。"""
    from sqlalchemy import Boolean

    from app.core.model_registry import register_all_models
    from app.database import Base

    register_all_models()
    names: set[str] = set()
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, Boolean):
                names.add(col.name.lower())
    return frozenset(names)


# sqlite 专有语法（双方言禁例）
_SQLITE_ONLY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in [
        ("UPDATE OR IGNORE", r"UPDATE\s+OR\s+IGNORE"),
        ("datetime('now')", r"datetime\(\s*'now'\s*\)"),
        ("INDEXED BY", r"INDEXED\s+BY"),
        ("sqlite_master", r"sqlite_master"),
        ("printf()", r"\bprintf\s*\("),
        ("PRAGMA", r"\bPRAGMA\b"),
    ]
)

# server_default=sa.text("0"/"1")：布尔列 PG 建列即炸；整型列也应用字符串形式
_SA_TEXT_DEFAULT = re.compile(r"sa\.text\(\s*(['\"])[01]\1\s*\)")

# SET/WHERE 对 Boolean 列的整型字面量（列名动态注入，长名优先避免子串误吞）
_SET_BOOL_INT: re.Pattern[str] | None = None
_WHERE_BOOL_INT: re.Pattern[str] | None = None


def _bool_column_patterns() -> tuple[re.Pattern[str], re.Pattern[str]]:
    global _SET_BOOL_INT, _WHERE_BOOL_INT
    if _SET_BOOL_INT is None or _WHERE_BOOL_INT is None:
        names = sorted(_boolean_column_names(), key=len, reverse=True)
        alt = "|".join(re.escape(n) for n in names)
        _SET_BOOL_INT = re.compile(rf"\bSET\s+({alt})\s*=\s*([01])\b", re.IGNORECASE)
        _WHERE_BOOL_INT = re.compile(rf"\bWHERE\b[^;]*?\b({alt})\s*=\s*([01])\b", re.IGNORECASE)
    return _SET_BOOL_INT, _WHERE_BOOL_INT


def scan_versions() -> dict[str, set[str]]:
    """扫描 versions/ 全部 revision 文件，返回 {文件名: 命中规则集}（无命中不出键）。"""
    set_rule, where_rule = _bool_column_patterns()
    violations: dict[str, set[str]] = defaultdict(set)
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        rules = violations[path.name]
        for label, pattern in _SQLITE_ONLY_PATTERNS:
            if pattern.search(text):
                rules.add("sqlite_only")
        if _SA_TEXT_DEFAULT.search(text):
            rules.add("sa_text_bool_default")
        for line in text.splitlines():
            if set_rule.search(line):
                rules.add("bool_set_int")
            if where_rule.search(line):
                rules.add("bool_where_int")
        if not rules:
            violations.pop(path.name, None)
    return violations


# 历史违规冻结表（只读基线；「勿回改历史迁移——引入重放风险」，修复后应从表内移除条目）。
# 生成方式：本测试首跑输出（2026-11-07，38 revision 单链全量扫描）。
_EXPECTED_VIOLATIONS: dict[str, set[str]] = {
    "6132b66d14a7_ratio_columns_to_float.py": {"sqlite_only"},
    "7b2c9d4e6f10_orphan_scan_background_and_current_detail.py": {
        "bool_set_int",
        "sa_text_bool_default",
        "sqlite_only",
    },
    "a1b2c3d4e5f6_add_orphan_ignore_and_canonical_path.py": {"bool_where_int", "sa_text_bool_default"},
    "a1f7c9e3d2b4_hash_lowercase_normalization.py": {"sqlite_only"},
    "a7b8c9d0e1f2_add_path_maintenance_disabled_by.py": {"bool_where_int", "sqlite_only"},
    "c1d2e3f4a5b6_repair_orphan_current_detail_id.py": {"sqlite_only"},
    "c3f1a8b7d902_add_orphan_file_tables.py": {"sa_text_bool_default"},
    "d1e2f3a4b5c6_add_setting_template_preset_key.py": {"bool_where_int"},
    "d4e5f6a7b8c9_orphan_hardlink_copy_count_snapshot.py": {"sqlite_only"},
}


class TestAlembicDualDialectGuard:
    """新迁移双方言禁例门禁：checklist 即断言（细节见模块 docstring）。"""

    def test_versions_dir_exists(self) -> None:
        assert VERSIONS_DIR.is_dir(), f"未找到迁移目录: {VERSIONS_DIR}"

    def test_no_new_violations(self) -> None:
        violations = scan_versions()
        unexpected: dict[str, dict[str, list[str]]] = {}
        for filename, rules in violations.items():
            allowed = _EXPECTED_VIOLATIONS.get(filename, set())
            extra = rules - allowed
            if extra:
                unexpected[filename] = {rule: sorted(rules) for rule in sorted(extra)}
        assert not unexpected, (
            "新增迁移命中双方言禁例（checklist 见 tests/core/test_alembic_dialect_guard.py 模块 docstring）：\n"
            + "\n".join(f"  {f}: {rules}" for f, rules in sorted(unexpected.items()))
            + '\n正确写法：布尔 server_default 用 Python 字符串 "0"；raw SQL 布尔用 '
            "TRUE/FALSE 字面量或 bool 参数绑定；禁 sqlite 专有语法（对方言分支进 app/core/dialect_sql.py）"
        )

    def test_freeze_list_has_no_rotten_entries(self) -> None:
        """冻结表条目应仍然违规：文件被修复后须同步移除条目（防名单腐化）。"""
        violations = scan_versions()
        rotten = [
            (filename, sorted(rules - violations.get(filename, set())))
            for filename, rules in _EXPECTED_VIOLATIONS.items()
            if rules - violations.get(filename, set())
        ]
        assert not rotten, "冻结表存在已修复条目（请从 _EXPECTED_VIOLATIONS 移除以保持名单有效）：\n" + "\n".join(
            f"  {f}: 已不命中 {rules}" for f, rules in sorted(rotten)
        )
