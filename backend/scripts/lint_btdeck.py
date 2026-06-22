#!/usr/bin/env python3
"""BtDeck 代码质量门禁检查。

本脚本只使用标准库和源码静态扫描，不 import 项目代码，适合在 CI/CD 中运行。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
APP_ROOT = BACKEND_ROOT / "app"
ENDPOINT_ROOT = APP_ROOT / "api" / "endpoints"
ALEMBIC_VERSIONS_ROOT = BACKEND_ROOT / "alembic" / "versions"

EXCLUDED_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
SQL_KEYWORDS = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\b", re.IGNORECASE)
SENSITIVE_NAME = re.compile(r"(secret|password|passwd|token|api_key|apikey|private_key|access_key)", re.IGNORECASE)
PLACEHOLDER_VALUES = {
    "",
    "none",
    "null",
    "change-me",
    "changeme",
    "example",
    "your-secret-key",
    "your-password",
}

# 中文说明：这些是当前代码中已知的历史兼容/特定设计点。新代码不得新增同类写法。
ALLOWLIST: dict[str, set[str]] = {
    "BTD201": {
        "app/api/endpoints/advanced_search.py",
        "app/api/endpoints/cron_tasks.py",
        "app/api/endpoints/cuser.py",
        "app/api/endpoints/downloader.py",
        "app/api/endpoints/downloader_capabilities.py",
        "app/api/endpoints/downloader_capabilities_management.py",
        "app/api/endpoints/downloader_path_maintenance.py",
        "app/api/endpoints/downloader_settings.py",
        "app/api/endpoints/seed_transfer.py",
        "app/api/endpoints/setting_templates.py",
        "app/api/endpoints/tag_management.py",
        "app/api/endpoints/tasks.py",
        "app/api/endpoints/torrent_backup.py",
        "app/api/endpoints/torrent_crud.py",
        "app/api/endpoints/torrent_deletion.py",
        "app/api/endpoints/torrent_location.py",
        "app/api/endpoints/torrent_sync.py",
        "app/api/endpoints/tracker.py",
        "app/api/endpoints/tracker_keywords.py",
        "app/api/endpoints/tracker_keywords_pools.py",
        "app/api/endpoints/tracker_messages.py",
        "app/api/endpoints/tracker_test.py",
    },
    "BTD301": {
        "app/tasks/cron_executor.py",
        "app/tasks/enhanced_python_executor.py",
    },
    "BTD305": {
        "app/api/endpoints/downloader.py",
        "app/api/endpoints/downloader_settings.py",
        "app/services/advanced_search.py",
        "app/tasks/cron_executor.py",
    },
    "BTD103": {
        "app/auth/utils.py",
    },
}


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    line: int
    message: str
    allowed: bool = False

    def format(self) -> str:
        prefix = "ALLOW" if self.allowed else "ERROR"
        return f"{prefix} {self.code} {self.path}:{self.line} {self.message}"


@dataclass(frozen=True)
class AuthStats:
    depends_get_current_user: int
    manual_token_parsing: int
    legacy_manual_token_parsing: int
    blocking_manual_token_parsing: int
    dependency_ratio: float


@dataclass(frozen=True)
class LintReport:
    issues: list[Issue]
    auth_stats: AuthStats

    @property
    def blocking_issues(self) -> list[Issue]:
        return [issue for issue in self.issues if not issue.allowed]


def rel(path: Path) -> str:
    return path.resolve().relative_to(BACKEND_ROOT).as_posix()


def is_allowed(code: str, path: Path) -> bool:
    return rel(path) in ALLOWLIST.get(code, set())


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig", errors="replace")


def iter_py_files(root: Path = APP_ROOT) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        yield path


def parse_ast(path: Path) -> ast.AST | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(read_text(path), filename=str(path))
    except SyntaxError as exc:
        return None


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def is_sensitive_literal(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in PLACEHOLDER_VALUES:
        return False
    if len(value.strip()) < 8:
        return False
    return bool(SENSITIVE_NAME.search(name))


def looks_like_sql_node(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return SQL_KEYWORDS.search(ast.unparse(node) if hasattr(ast, "unparse") else "") is not None
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return SQL_KEYWORDS.search(ast.unparse(node) if hasattr(ast, "unparse") else "") is not None
    return False


def call_name(call: ast.Call) -> str:
    return dotted_name(call.func)


class BtDeckVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.issues: list[Issue] = []
        self.dynamic_sql_vars: set[str] = set()

    def add(self, code: str, node: ast.AST, message: str) -> None:
        self.issues.append(
            Issue(
                code=code,
                path=rel(self.path),
                line=getattr(node, "lineno", 1),
                message=message,
                allowed=is_allowed(code, self.path),
            )
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "app.config":
            imported = {alias.name for alias in node.names}
            if "settings" in imported or "*" in imported:
                self.add("BTD101", node, "禁止直接 import app.config.settings，请改用 app.core.config")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "app.config":
                self.add("BTD101", node, "禁止直接 import app.config，请改用 app.core.config")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._check_assignment(node.targets, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._check_assignment([node.target], node.value)
        self.generic_visit(node)

    def _check_assignment(self, targets: Sequence[ast.AST], value: ast.AST) -> None:
        names = [dotted_name(target).split(".")[-1] for target in targets]
        value_text = literal_string(value)
        for name in names:
            if name == "SECRET_KEY" and value_text:
                self.add("BTD102", value, "禁止硬编码 SECRET_KEY，请使用环境变量或安全配置来源")
            elif value_text and is_sensitive_literal(name, value_text):
                self.add("BTD103", value, f"疑似硬编码密码/密钥变量 `{name}`")
        if looks_like_sql_node(value):
            for name in names:
                if name.lower() in {"sql", "query", "statement"} or name.lower().endswith("_sql"):
                    self.dynamic_sql_vars.add(name)

    def visit_Call(self, node: ast.Call) -> None:
        name = call_name(node)
        if name == "exec":
            self.add("BTD301", node, "禁止 exec() 调用；如为脚本执行器必须登记白名单")
        elif name == "eval":
            self.add("BTD302", node, "禁止 eval() 调用")
        elif name == "os.system":
            self.add("BTD303", node, "禁止 os.system() 调用，请使用 subprocess 参数列表")
        elif name == "subprocess.call" and any(
            kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in node.keywords
        ):
            self.add("BTD304", node, "禁止 subprocess.call(shell=True)")

        if name.endswith(".execute") or name in {"execute", "text"}:
            if node.args:
                first_arg = node.args[0]
                if looks_like_sql_node(first_arg):
                    self.add("BTD305", node, "疑似 SQL 字符串拼接，请使用参数化查询")
                elif isinstance(first_arg, ast.Name) and first_arg.id in self.dynamic_sql_vars:
                    self.add("BTD305", node, "疑似执行动态拼接 SQL 变量，请确认参数化或白名单")
        self.generic_visit(node)


def scan_file(path: Path) -> list[Issue]:
    tree = parse_ast(path)
    if tree is None:
        return [
            Issue(
                code="BTD000",
                path=rel(path),
                line=1,
                message="Python 语法解析失败，无法执行架构检查",
                allowed=False,
            )
        ]
    visitor = BtDeckVisitor(path)
    visitor.visit(tree)
    return visitor.issues


def scan_manual_token_parsing() -> list[Issue]:
    issues: list[Issue] = []
    if not ENDPOINT_ROOT.exists():
        return issues
    token_pattern = re.compile(r"['\"]x-access-token['\"]|['\"]X-Access-Token['\"]")
    for path in iter_py_files(ENDPOINT_ROOT):
        for line_no, line in enumerate(read_text(path).splitlines(), start=1):
            if token_pattern.search(line):
                issues.append(
                    Issue(
                        code="BTD201",
                        path=rel(path),
                        line=line_no,
                        message="endpoint 不应手动读取 X-Access-Token，请使用认证 dependency",
                        allowed=is_allowed("BTD201", path),
                    )
                )
    return issues


def scan_migration_rollback_annotation() -> list[Issue]:
    """检查 upgrade() 含破坏性操作的迁移是否标注了可回滚性。

    规则：仅检测 upgrade() 函数体内的 op.drop_column/op.alter_column/op.drop_table。
    downgrade() 里的 drop 是对应 upgrade create 的清理，属正常，不触发。
    含破坏性 upgrade 的迁移，docstring 必须含【不可回滚】或【受限回滚】，
    否则报 BTD401。纯增量迁移（create_table/add_column）不强制标注。
    """
    issues: list[Issue] = []
    if not ALEMBIC_VERSIONS_ROOT.exists():
        return issues

    destructive_pattern = re.compile(
        r"\bop\.(drop_column|alter_column|drop_table)\b"
    )
    rollback_marker_pattern = re.compile(r"【不可回滚】|【受限回滚】")

    for path in ALEMBIC_VERSIONS_ROOT.rglob("*.py"):
        tree = parse_ast(path)
        if tree is None:
            continue
        upgrade_has_destructive = False
        for node in ast.walk(tree):
            # 仅检查 upgrade() 函数体内的破坏性调用
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and isinstance(child.func.value, ast.Name)
                        and child.func.value.id == "op"
                        and child.func.attr
                        in ("drop_column", "alter_column", "drop_table")
                    ):
                        upgrade_has_destructive = True
                        break
            if upgrade_has_destructive:
                break
        if not upgrade_has_destructive:
            continue
        if rollback_marker_pattern.search(read_text(path)):
            continue
        issues.append(
            Issue(
                code="BTD401",
                path=rel(path),
                line=1,
                message=(
                    "迁移 upgrade() 含破坏性操作（drop_column/alter_column/drop_table），"
                    "docstring 必须标注【不可回滚】或【受限回滚】（见 "
                    "docs/operations/rollback-guide.md）"
                ),
                allowed=is_allowed("BTD401", path),
            )
        )
    return issues


def collect_auth_stats() -> AuthStats:
    depends_count = 0
    manual_count = 0
    legacy_manual_count = 0
    blocking_manual_count = 0
    if ENDPOINT_ROOT.exists():
        for path in iter_py_files(ENDPOINT_ROOT):
            text = read_text(path)
            depends_count += len(re.findall(r"Depends\s*\(\s*get_current_user\s*\)", text))
            found = len(re.findall(r"['\"]x-access-token['\"]|['\"]X-Access-Token['\"]", text))
            manual_count += found
            if is_allowed("BTD201", path):
                legacy_manual_count += found
            else:
                blocking_manual_count += found
    total = depends_count + blocking_manual_count
    ratio = depends_count / total if total else 1.0
    return AuthStats(depends_count, manual_count, legacy_manual_count, blocking_manual_count, ratio)


def collect_report() -> LintReport:
    issues: list[Issue] = []
    for path in iter_py_files(APP_ROOT):
        # 中文说明：数据库迁移脚本常包含动态表名，架构门禁先聚焦生产业务代码。
        if "/migrations/" in path.as_posix():
            continue
        issues.extend(scan_file(path))
    issues.extend(scan_manual_token_parsing())
    issues.extend(scan_migration_rollback_annotation())
    issues.sort(key=lambda issue: (issue.allowed, issue.path, issue.line, issue.code))
    return LintReport(issues=issues, auth_stats=collect_auth_stats())


def print_text_report(report: LintReport, show_allowed: bool) -> None:
    visible_issues = report.issues if show_allowed else report.blocking_issues
    print("BtDeck code quality checks")
    print("=" * 28)
    print(
        "认证统计: "
        f"Depends(get_current_user)={report.auth_stats.depends_get_current_user}, "
        f"手动解析={report.auth_stats.manual_token_parsing}, "
        f"白名单历史手动解析={report.auth_stats.legacy_manual_token_parsing}, "
        f"阻塞手动解析={report.auth_stats.blocking_manual_token_parsing}, "
        f"dependency 占比={report.auth_stats.dependency_ratio:.1%}"
    )
    if visible_issues:
        print("\n发现问题:")
        for issue in visible_issues:
            print(f"- {issue.format()}")
    else:
        print("\n未发现阻塞性问题。")
    if not show_allowed:
        allowed_count = len([issue for issue in report.issues if issue.allowed])
        if allowed_count:
            print(f"\n已登记白名单问题: {allowed_count} 个；使用 --show-allowed 可查看。")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BtDeck 自定义代码质量检查")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出报告")
    parser.add_argument("--show-allowed", action="store_true", help="显示白名单内问题")
    args = parser.parse_args(argv)

    report = collect_report()
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print_text_report(report, args.show_allowed)
    return 1 if report.blocking_issues else 0


if __name__ == "__main__":
    sys.exit(main())
