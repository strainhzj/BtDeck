"""架构约束测试。

这些测试只加载静态扫描脚本，不 import app 包，避免在 CI 中触发配置、数据库或外部服务初始化。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import warnings
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("from app.config import settings", "BTD101"),
        ('SECRET_KEY = "production-secret"', "BTD102"),
        ('password = "production-secret"', "BTD103"),
        ("exec('payload')", "BTD301"),
        ("eval('payload')", "BTD302"),
        ("import os\nos.system('payload')", "BTD303"),
        ("import subprocess\nsubprocess.call('payload', shell=True)", "BTD304"),
        ('query = "SELECT " + table\ndb.execute(query)', "BTD305"),
    ],
)
def test_custom_linter_rejects_forbidden_source_patterns(source: str, code: str):
    """每条 AST 规则必须拒绝独立反例，避免规则失效后仅靠扫描当前源码而假通过。"""
    linter = _load_linter()
    visitor = linter.BtDeckVisitor(BACKEND_ROOT / "app" / "_lint_fixture.py")
    visitor.visit(ast.parse(source))
    assert any(issue.code == code and not issue.allowed for issue in visitor.issues)


def test_custom_linter_allows_registered_exception():
    """白名单仅允许登记的历史位置，不能把同一规则整体关闭。"""
    linter = _load_linter()
    visitor = linter.BtDeckVisitor(BACKEND_ROOT / "app" / "auth" / "utils.py")
    visitor.visit(ast.parse('password = "production-secret"'))
    assert any(issue.code == "BTD103" and issue.allowed for issue in visitor.issues)


def test_custom_linter_rejects_manual_token_parsing(tmp_path: Path, monkeypatch):
    """端点 token 扫描规则也必须有独立反例，不能只依赖当前仓库恰好无违规。"""
    linter = _load_linter()
    endpoint = tmp_path / "endpoint.py"
    endpoint.write_text('token = request.headers["X-Access-Token"]\n', encoding="utf-8")
    monkeypatch.setattr(linter, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(linter, "ENDPOINT_ROOT", tmp_path)

    issues = linter.scan_manual_token_parsing()

    assert any(issue.code == "BTD201" and not issue.allowed for issue in issues)


def test_custom_linter_rejects_unannotated_destructive_migration(tmp_path: Path, monkeypatch):
    """迁移回滚规则缺失时必须被负向样例捕获。"""
    linter = _load_linter()
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "migration.py").write_text(
        "def upgrade():\n    op.drop_column('torrent', 'legacy_field')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(linter, "BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(linter, "ALEMBIC_VERSIONS_ROOT", versions)

    issues = linter.scan_migration_rollback_annotation()

    assert any(issue.code == "BTD401" and not issue.allowed for issue in issues)


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
                # 用 as_posix() 统一为正斜杠，跨平台一致（Windows 返回反斜杠会误判）
                definitions.append(f"{path.relative_to(BACKEND_ROOT).as_posix()}:{node.lineno}")

    assert len(definitions) == 1 and definitions[0].startswith(
        "app/core/config.py:"
    ), "ACCESS_TOKEN_EXPIRE_MINUTES 只能在 app/core/config.py 中定义一次，当前定义:\n" + "\n".join(definitions)


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
    """确保没有 SQL 注入字符串拼接"""
    issues = _blocking_codes("BTD305")
    assert not issues, "\n".join(issue.format() for issue in issues)


# ==============================================================================
# sync-resource-governance 阶段 3：请求侧路径隔离约束
# ==============================================================================
# 请求探针 endpoint（dashboard / torrent list 等）不得直接调用治理锁
# （admission_controller.task_scope / db_write_scope），否则会让请求侧被
# 后台同步任务阻塞，违背治理目标"不让后台任务挤占请求侧资源"。
# 详见 PLANS/sync-resource-governance.md 阶段 3。

# 请求侧路径白名单：这些模块是"请求探针"，禁止 import resource_guard /
# 调用 admission_controller（read-only 查询路径不需要写锁串行化）。
_REQUEST_SIDE_MODULES = [
    "app/api/endpoints/dashboard.py",
    "app/services/dashboard_service.py",
    "app/api/endpoints/torrent_crud.py",
]

# 禁止在请求侧路径出现的名字（import 或调用均算）。
_FORBIDDEN_GOVERNANCE_NAMES = {
    "admission_controller",
    "task_scope",
    "db_write_scope",
    "resource_guard",
}


def test_request_side_endpoints_do_not_use_governance_locks():
    """请求探针 endpoint 不得 import/调用 sync-resource-governance 的治理锁。

    防回归锚点：若未来有人在 dashboard 路径里加 `async with admission_controller.db_write_scope()`
    把请求侧锁住（导致同步任务持锁时 dashboard 超时），此测试立即报红。

    语义：dashboard / torrent list 是 read-only 查询，不需要写锁串行化；
    治理锁只应出现在后台同步任务路径（cron_executor / torrents_async 同步函数）。
    """
    violations = []
    for rel_path in _REQUEST_SIDE_MODULES:
        full_path = BACKEND_ROOT / rel_path
        if not full_path.exists():
            violations.append(f"{rel_path}: 文件不存在（路径漂移？）")
            continue
        tree = _parse(full_path)
        for node in ast.walk(tree):
            # 检测 import 语句中的名字
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "app.tasks.resource_guard":
                        violations.append(f"{rel_path}:{node.lineno} import resource_guard")
            elif isinstance(node, ast.ImportFrom):
                if node.module and "resource_guard" in node.module:
                    violations.append(f"{rel_path}:{node.lineno} from ... import resource_guard")
                for alias in node.names:
                    if alias.name in _FORBIDDEN_GOVERNANCE_NAMES:
                        violations.append(f"{rel_path}:{node.lineno} imports '{alias.name}'")
            # 检测名字引用（AttributeAccess / Name）
            elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_GOVERNANCE_NAMES:
                violations.append(f"{rel_path}:{node.lineno} 引用 '{node.attr}'")
            elif isinstance(node, ast.Name) and node.id == "admission_controller":
                violations.append(f"{rel_path}:{node.lineno} 引用 'admission_controller'")

    assert (
        not violations
    ), "请求侧路径不应使用治理锁（admission_controller/task_scope/db_write_scope），" "否则后台同步任务持锁时会阻塞请求侧。发现违规:\n" + "\n".join(
        violations
    )


# ==============================================================================
# sync-resource-governance code review 修复：lifespan 必须关闭 downloader_api_runtime
# ==============================================================================
# 历史背景：runtime 有 shutdown()（关闭三 lane executor + flush 残留日志统计），但应用
# 生命周期退出时只停 cron 和（已删除的）_speed_executor，导致 lane executor 线程泄漏 +
# 日志聚合器窗口内统计丢失。修复后 lifespan finally 必须调用 downloader_api_runtime.shutdown()。
# 同时 _speed_executor（速度接口旧独立线程池）已删除（速度接口接入 INTERACTIVE lane）。

_LIFECYCLE_PATH = BACKEND_ROOT / "app" / "startup" / "lifecycle.py"


def test_lifespan_shutdowns_downloader_api_runtime():
    """🔴 防回归：lifespan finally 块必须调用 downloader_api_runtime.shutdown()。

    mutation 验证点：删掉 shutdown 调用 / 改回 _speed_executor，此测试报红。
    """
    assert _LIFECYCLE_PATH.exists(), "app/startup/lifecycle.py 不存在"
    tree = _parse(_LIFECYCLE_PATH)
    found_shutdown = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "lifespan":
            for stmt in node.body:
                if isinstance(stmt, ast.Try) and stmt.finalbody:
                    for f in stmt.finalbody:
                        for sub in ast.walk(f):
                            if (
                                isinstance(sub, ast.Attribute)
                                and sub.attr == "shutdown"
                                and isinstance(sub.value, ast.Name)
                                and sub.value.id == "downloader_api_runtime"
                            ):
                                found_shutdown = True
    assert found_shutdown, (
        "lifespan finally 块必须调用 downloader_api_runtime.shutdown()，"
        "否则 lane executor 线程泄漏 + 日志聚合器窗口统计丢失。"
    )


def test_lifespan_no_longer_references_speed_executor():
    """🔴 防回归：lifespan 不应再引用已删除的 _speed_executor。

    速度接口已接入 DownloaderApiRuntime INTERACTIVE lane，独立 _speed_executor 已删除，
    lifecycle 不应再有对其 shutdown 的引用（残留引用会 AttributeError）。
    """
    tree = _parse(_LIFECYCLE_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "_speed_executor":
            pytest.fail(
                "lifecycle.py 不应再引用 _speed_executor（速度接口已接入 INTERACTIVE lane，" "独立线程池已删除）。"
            )


# ==============================================================================
# 防回归：endpoint 模块禁止顶层 import app.factory / app.main
# ==============================================================================
# 历史背景：seed_transfer.py 曾在顶层 `from app.factory import app`，触发循环 import
# （app.api.api 半成品 → app.factory → configure_routes_and_static 早退），
# 导致全局 app 不注册业务路由，tests/api/test_tag_aggregation_api.py 全量运行 16 个 404。
# 端点需要访问全局 app 时，必须在函数体内 lazy import（既有模式见 downloader.py /
# torrent_location.py）。该约束仅针对 endpoint 目录：app 入口（main.py / desktop_main.py）
# 顶层 import app.factory 是正常用法，不在本测试范围。

_ENDPOINTS_DIR = APP_ROOT / "api" / "endpoints"


def test_no_top_level_app_factory_import_in_endpoints():
    """endpoint 模块禁止顶层 import app.factory / app.main（循环 import 防回归）。

    防回归锚点：若未来有人在 endpoint 顶层加 `from app.factory import app` 或
    `from app.main import app`，会重新触发循环 import，让全局 app 丢失业务路由
    （历史 bug：tag_aggregation 测试全量运行 404）。此测试立即报红。

    语义：endpoint 需要 app 实例时应在函数体内 lazy import（参照 downloader.py /
    torrent_location.py 的既有模式）。app 入口文件（main.py / desktop_main.py）
    不在扫描范围内。
    """
    violations = []

    def _is_app_factory_or_main(module_name: str | None) -> bool:
        return module_name in {"app.factory", "app.main"}

    for path in _ENDPOINTS_DIR.glob("*.py"):
        rel_path = path.relative_to(BACKEND_ROOT).as_posix()
        tree = _parse(path)
        # 只扫模块顶层语句（tree.body 直接子节点），不进函数/类体（lazy import 在那里是合法的）
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and _is_app_factory_or_main(node.module):
                names = [alias.name for alias in node.names]
                violations.append(f"{rel_path}:{node.lineno} 顶层 `from {node.module} import {', '.join(names)}`")
            elif isinstance(node, ast.Import):
                # 形如 `import app.factory` / `import app.main`
                for alias in node.names:
                    if _is_app_factory_or_main(alias.name):
                        violations.append(f"{rel_path}:{node.lineno} 顶层 `import {alias.name}`")

    assert not violations, (
        "endpoint 模块禁止顶层 import app.factory / app.main，会触发循环 import 导致全局 app "
        "丢失业务路由（历史 bug：tag_aggregation 测试 404）。请在函数体内 lazy import。"
        "发现违规:\n" + "\n".join(violations)
    )


# ==============================================================================
# sync-database-blocking-remediation W1-3：同步模块 DML 只能通过批准写入口
# ==============================================================================
# 背景：_mark_qb_removed_torrents 曾直接执行 update(TorrentInfo) + db.commit()
# （在 db_write_scope 之外、无统一批大小、无 retry），属于旁路写者（P0-03/P0-06）。
# W1-3 已收编为 bulk_upsert_with_retry（统一批大小 + db_write_scope + 批级重试）。
# 本约束固化：info-only / tracker-only / removed 标记相关同步函数体内禁止直接 DML
# （db.commit / db.execute(update|delete|insert) / 函数内局部 import sqlalchemy.update），
# 必须调用批准写入口。只读 db.execute(select(...)) 不受限；db.rollback() 属错误清理路径不受限。

# 同步模块白名单：函数名 → 必须调用的批准写入口
_SYNC_APPROVED_ENTRY_RULES = {
    "_mark_qb_removed_torrents": ("bulk_upsert_with_retry",),
    "qb_add_torrents_info_only_async": ("bulk_upsert_with_retry",),
    "tr_add_torrents_info_only_async": ("bulk_upsert_with_retry",),
    "qb_sync_trackers_only_async": ("sync_trackers_batch_async",),
    "tr_sync_trackers_only_async": ("sync_trackers_batch_async",),
}

_DIRECT_DML_CALL_NAMES = frozenset({"update", "delete", "insert", "sqlite_insert"})


def _find_function_node(tree: ast.AST, name: str) -> ast.AST:
    """在模块 AST 中定位指定函数（路径漂移时抛 AssertionError，不让测试静默通过）。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"未找到函数 {name}（路径漂移？）")


def _sync_dml_violations(func_node: ast.AST) -> list[str]:
    """返回函数体内（含嵌套闭包）绕过批准写入口的直接 DML 描述列表。

    检测三类旁路：
    1. db.commit() 直接提交；
    2. db.execute(update(...)) / db.execute(delete(...)) / db.execute(insert(...))
       （首参是 update/delete/insert/sqlite_insert 构造调用）；
    3. 函数体内 `from sqlalchemy import update/delete` 局部导入（旁路 DML 惯用入口）。
    """
    violations = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "db":
                if func.attr == "commit":
                    violations.append(f"行 {node.lineno}: db.commit() 直接调用")
                elif func.attr == "execute" and node.args:
                    arg0 = node.args[0]
                    dml_name = None
                    if isinstance(arg0, ast.Call):
                        if isinstance(arg0.func, ast.Name) and arg0.func.id in _DIRECT_DML_CALL_NAMES:
                            dml_name = arg0.func.id
                        elif isinstance(arg0.func, ast.Attribute) and arg0.func.attr in _DIRECT_DML_CALL_NAMES:
                            dml_name = arg0.func.attr
                    if dml_name:
                        violations.append(f"行 {node.lineno}: db.execute({dml_name}(...)) 直接 DML")
        elif isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy":
            for alias in node.names:
                if alias.name in {"update", "delete"}:
                    violations.append(f"行 {node.lineno}: 函数内局部 import sqlalchemy.{alias.name}")
    return violations


def test_sync_module_dml_only_through_approved_write_entries():
    """🔴 防回归：同步模块（info-only / tracker-only / removed 标记）的 DML
    只能通过批准写入口（bulk_upsert_with_retry / sync_trackers_batch_async）。

    mutation 验证点：把 _mark_qb_removed_torrents 改回直接 update+commit，
    或在 info-only 函数里新增 db.commit() / 删掉 bulk_upsert_with_retry 调用，
    此测试立即报红。
    """
    path = APP_ROOT / "api" / "endpoints" / "torrents_async.py"
    tree = _parse(path)
    failures = []
    for func_name, approved_entries in _SYNC_APPROVED_ENTRY_RULES.items():
        func_node = _find_function_node(tree, func_name)
        for violation in _sync_dml_violations(func_node):
            failures.append(f"{func_name}: {violation}")
        called_names = {
            node.func.id
            for node in ast.walk(func_node)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for entry in approved_entries:
            if entry not in called_names:
                failures.append(f"{func_name}: 未调用批准写入口 {entry}")
    assert (
        not failures
    ), "同步模块 DML 必须通过批准写入口（bulk_upsert_with_retry / sync_trackers_batch_async）:\n" + "\n".join(failures)
