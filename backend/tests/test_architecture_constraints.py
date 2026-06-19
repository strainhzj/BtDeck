"""架构约束测试。

这些测试只加载静态扫描脚本，不 import app 包，避免在 CI 中触发配置、数据库或外部服务初始化。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import warnings
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
LINT_SCRIPT = BACKEND_ROOT / "scripts" / "lint_btdeck.py"
APP_ROOT = BACKEND_ROOT / "app"


def _load_linter():
    spec = importlib.util.spec_from_file_location("lint_btdeck", LINT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _report():
    return _load_linter().collect_report()


def _blocking_codes(*codes: str):
    report = _report()
    return [issue for issue in report.blocking_issues if issue.code in codes]


def _parse(path: Path) -> ast.AST:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def test_no_direct_config_import():
    """确保生产代码不直接 import app.config"""
    issues = _blocking_codes("BTD101")
    assert not issues, "\n".join(issue.format() for issue in issues)


def test_unified_token_expiry():
    """确保 ACCESS_TOKEN_EXPIRE_MINUTES 统一"""
    definitions: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if any(part in {"__pycache__", "migrations"} for part in path.parts):
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            target_name = None
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        target_name = target.id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target_name = node.target.id
            if target_name == "ACCESS_TOKEN_EXPIRE_MINUTES":
                definitions.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno}")

    assert len(definitions) == 1 and definitions[0].startswith("app/core/config.py:"), (
        "ACCESS_TOKEN_EXPIRE_MINUTES 只能在 app/core/config.py 中定义一次，当前定义:\n"
        + "\n".join(definitions)
    )


def test_auth_dependency_usage():
    """统计并验证认证方式使用比例"""
    report = _report()
    stats = report.auth_stats
    assert stats.depends_get_current_user > 0, "未发现 Depends(get_current_user) 使用"
    assert stats.dependency_ratio >= 0.80, (
        "认证 dependency 使用占比过低: "
        f"{stats.dependency_ratio:.1%} "
        f"(Depends={stats.depends_get_current_user}, 手动解析={stats.manual_token_parsing})"
    )


def test_no_manual_token_parsing():
    """确保新代码不手动解析 token"""
    issues = _blocking_codes("BTD201")
    assert not issues, "\n".join(issue.format() for issue in issues)


def test_no_exec_calls():
    """确保没有 exec() 调用（除白名单外）"""
    issues = _blocking_codes("BTD301", "BTD302", "BTD303", "BTD304")
    assert not issues, "\n".join(issue.format() for issue in issues)


def test_no_sql_injection():
    """确保没有 SQL 字符串拼接"""
    issues = _blocking_codes("BTD305")
    assert not issues, "\n".join(issue.format() for issue in issues)
