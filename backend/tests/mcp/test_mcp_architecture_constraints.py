"""MCP-G0 架构边界静态门禁（feature mcp-service-capabilities-2026-08-28 W0）。

锚定计划 §3/§4.1 的三条硬边界（工具/运行时层）：

1. ``app/mcp/**`` 禁止 import 全局应用实例（``app.main`` / ``app.factory``）——
   任何位置都不允许（比 endpoint 的"仅顶层禁止"更严：MCP 工具连 lazy import
   全局 app 也不行，运行时上下文只能来自父应用显式注入的 RuntimeContext）。
2. ``app/mcp/**`` 禁止 import ``app.api`` / ``app.api.endpoints``——MCP 不得
   调用 HTTP endpoint，两种协议只能共用更下层的协议无关 service。
3. ``app/mcp/**`` 禁止导入 qbittorrent-api / transmission-rpc 或构造其 Client——
   下载器连接只能经 ``app.state.store`` 缓存（downloader-connection 约束）。

规则必须对独立反例报红（沿用 tests/test_architecture_constraints.py 的
负向变异纪律：只扫当前源码"恰好无违规"不算规则有效）。当前 ``app/mcp/``
仅含契约层，扫描基线天然为绿；W2/W3 接入实现后同规则持续生效。
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path
from typing import Iterator, List

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT / "app"
MCP_ROOT = APP_ROOT / "mcp"

# 禁止 MCP 层引用的全局应用模块（app.main / app.factory，含任意子名）
_GLOBAL_APP_MODULES = {"app.main", "app.factory"}
# 禁止 MCP 层引用的 HTTP 层模块（app.api 及其子模块；精确匹配防 app.api_schema 误报）


def _is_http_layer_module(module_name: str) -> bool:
    return module_name == "app.api" or module_name.startswith("app.api.")


# 下载器客户端构造：模块名 → 禁止 import 的名字集合
_DOWNLOADER_CLIENT_MODULES = {"qbittorrentapi", "transmission_rpc"}
_DOWNLOADER_CLIENT_NAMES = {"Client", "qbClient", "trClient"}


def _parse(path: Path) -> ast.AST:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _iter_mcp_modules() -> Iterator[Path]:
    """遍历 app/mcp/**/*.py（跳过 __pycache__）；包目录缺失时返回空迭代。"""
    if not MCP_ROOT.is_dir():
        return
    for path in sorted(MCP_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _violations_global_app_import(rel_path: str, tree: ast.AST) -> List[str]:
    """规则 1：app/mcp 内禁止 import app.main / app.factory（任何位置、任何形式）。"""
    violations: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module in _GLOBAL_APP_MODULES:
                names = [alias.name for alias in node.names]
                violations.append(f"{rel_path}:{node.lineno} `from {node.module} import {', '.join(names)}`")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _GLOBAL_APP_MODULES:
                    violations.append(f"{rel_path}:{node.lineno} `import {alias.name}`")
    return violations


def _violations_http_endpoint_import(rel_path: str, tree: ast.AST) -> List[str]:
    """规则 2：app/mcp 内禁止 import app.api（含 endpoints 子包）——MCP 不调用 HTTP 层。"""
    violations: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and _is_http_layer_module(node.module):
                names = [alias.name for alias in node.names]
                violations.append(f"{rel_path}:{node.lineno} `from {node.module} import {', '.join(names)}`")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_http_layer_module(alias.name):
                    violations.append(f"{rel_path}:{node.lineno} `import {alias.name}`")
    return violations


def _violations_downloader_client(rel_path: str, tree: ast.AST) -> List[str]:
    """规则 3：app/mcp 内禁止导入下载器客户端库或构造其 Client。"""
    violations: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            root_module = (node.module or "").split(".")[0]
            if root_module in _DOWNLOADER_CLIENT_MODULES:
                names = [alias.name for alias in node.names]
                violations.append(f"{rel_path}:{node.lineno} `from {node.module} import {', '.join(names)}`")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _DOWNLOADER_CLIENT_MODULES:
                    violations.append(f"{rel_path}:{node.lineno} `import {alias.name}`")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _DOWNLOADER_CLIENT_NAMES:
                violations.append(f"{rel_path}:{node.lineno} `{func.id}(...) 客户端构造`")
            elif isinstance(func, ast.Attribute) and func.attr in _DOWNLOADER_CLIENT_NAMES:
                violations.append(f"{rel_path}:{node.lineno} `*.{func.attr}(...) 客户端构造`")
    return violations


_ALL_RULES = (
    (_violations_global_app_import, "app.main/app.factory"),
    (_violations_http_endpoint_import, "app.api"),
    (_violations_downloader_client, "下载器客户端"),
)


def test_mcp_package_exists():
    """app/mcp 包必须存在（W0 契约层已建立；目录被误删时本门禁立即红）。"""
    assert (MCP_ROOT / "__init__.py").is_file(), f"app/mcp/__init__.py 不存在: {MCP_ROOT}"


def test_mcp_layer_respects_architecture_boundaries():
    """🔴 MCP-G0：app/mcp/** 全量静态扫描，三条边界零违规。"""
    violations: List[str] = []
    scanned = 0
    for path in _iter_mcp_modules():
        scanned += 1
        rel_path = path.relative_to(BACKEND_ROOT).as_posix()
        tree = _parse(path)
        for rule, label in _ALL_RULES:
            violations += rule(rel_path, tree)
    assert scanned > 0, "app/mcp 下未扫描到任何 .py 文件（包结构漂移？）"
    assert (
        not violations
    ), (
        "MCP 层违反架构边界（不得 import 全局 app / HTTP 层 / 构造下载器客户端），"
        "运行时上下文只能来自父应用注入:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize(
    ("rule", "source"),
    [
        (_violations_global_app_import, "from app.factory import app\n"),
        (_violations_global_app_import, "from app.main import app\n"),
        (_violations_global_app_import, "import app.main\n"),
        (_violations_global_app_import, "import app.factory\n"),
        (_violations_http_endpoint_import, "from app.api.endpoints.torrent_crud import anything\n"),
        (_violations_http_endpoint_import, "from app.api import api_router\n"),
        (_violations_http_endpoint_import, "import app.api.api\n"),
        (_violations_downloader_client, "from qbittorrentapi import Client\n"),
        (_violations_downloader_client, "from transmission_rpc import Client\n"),
        (_violations_downloader_client, "import qbittorrentapi\n"),
        (_violations_downloader_client, "client = Client(host='127.0.0.1')\n"),
        (_violations_downloader_client, "client = qbClient(host='127.0.0.1')\n"),
    ],
)
def test_rules_reject_independent_counterexamples(rule, source, tmp_path: Path):
    """负向变异纪律：每条规则必须对独立反例报红（函数内 lazy import 同样命中）。"""
    target = tmp_path / "counterexample.py"
    target.write_text(source, encoding="utf-8")
    violations = rule("counterexample.py", _parse(target))
    assert violations, f"规则未命中反例（失效即仅靠当前源码假通过）: {source!r}"


@pytest.mark.parametrize(
    ("rule", "source"),
    [
        (_violations_global_app_import, "from app.factory_something import x\n"),
        (_violations_global_app_import, "from app.services.torrent_add_service import TorrentAddService\n"),
        (_violations_http_endpoint_import, "from app.api_schema import x\n"),
        (_violations_http_endpoint_import, "from app.services.dashboard_service import DashboardService\n"),
        (_violations_downloader_client, "from sqlalchemy.orm import Session\n"),
        (_violations_downloader_client, "client = store.get_client(1)\n"),
    ],
)
def test_rules_allow_legitimate_imports(rule, source, tmp_path: Path):
    """合法引用不得误报：共用 service 层、store 取缓存连接是计划允许的核心形态。"""
    target = tmp_path / "legitimate.py"
    target.write_text(source, encoding="utf-8")
    violations = rule("legitimate.py", _parse(target))
    assert not violations, f"规则误报合法引用: {source!r} -> {violations}"
