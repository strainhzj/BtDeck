# -*- coding: utf-8 -*-
"""MCP-G4 Service 共用门禁（feature mcp-service-capabilities-2026-08-28 W4）。

两段：

1. **AST 守卫（纯静态，不 import app 包）**
   a) MCP 工具引用的业务模块闭包（app/services/**、app/tasks/**、app/core/**）
      禁止 fastapi/starlette import、禁止 endpoint 层依赖（app.api.*，唯
      ``app.api.models`` Pydantic 请求 DTO 白名单）、函数签名禁止
      Request/UploadFile/CommonResponse 注解。登记例外：
      ``audit_context.AuditContext.from_request``——HTTP 侧构造适配器
      （计划 §11.1 边界；MCP 侧走 ToolCallContext.audit 不经 Request）。
   b) 六工具 ↔ HTTP 端点共用同一 service 的映射表守卫；cron 为 MCP-only
      （无 HTTP 触发入口，反向守卫：endpoint 层不得 import cron_trigger）。
2. **等价契约测试（运行时，需 mcp SDK）**——同一 DB/同一输入下，
   HTTP 路径（=端点薄壳所调的同一 service 直调）与 MCP 线上工具输出的
   领域事实比对：MCP 只做脱敏/DTO 映射，不得增删领域事实。
"""

from __future__ import annotations

import ast
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = BACKEND_ROOT / "app"

# MCP 工具处理器/共享助手所在的源文件（闭包起点）
_MCP_SOURCE_FILES = tuple(sorted((APP_ROOT / "mcp").rglob("*.py")))
# 业务层命名空间（闭包只沿这些前缀展开）
_BUSINESS_PREFIXES = ("app.services.", "app.tasks.", "app.core.")

# 登记例外（HTTP 侧构造适配器，MCP 注入路径不经 Request——见 §11.1 适配边界）：
# - audit_context.AuditContext.from_request：HTTP 端点构造 AuditContext 的入口；
# - audit_service：协议中立 AuditLogService 核心 + HTTP 适配面
#   （extract_audit_info_from_request / get_audit_service 的 Depends 提供器；
#   MCP 侧直接 AuditLogService.log_operation + 显式四元组，不经适配器）。
_ADAPTER_EXCEPTION_MODULES = {
    "app/services/audit_context.py": {"from_request"},
    "app/services/audit_service.py": {"extract_audit_info_from_request"},
}

# 六工具 ↔ 共用 service ↔ HTTP 端点（None = MCP-only，无 HTTP 入口）
SAME_SERVICE_MAP: Dict[str, Tuple[str, str, Optional[str]]] = {
    "torrent_advanced_search": (
        "app/mcp/tools/torrents.py",
        "app/services/advanced_search.py",
        "app/api/endpoints/advanced_search.py",
    ),
    "advanced_search_template_create": (
        "app/mcp/tools/search_templates.py",
        "app/services/advanced_search.py",
        "app/api/endpoints/advanced_search.py",
    ),
    "dashboard_get": (
        "app/mcp/tools/dashboard.py",
        "app/services/dashboard_service.py",
        "app/api/endpoints/dashboard.py",
    ),
    "torrent_mark_pending_delete": (
        "app/mcp/tools/torrents.py",
        "app/services/torrent_deletion_by_level.py",
        "app/api/endpoints/torrent_deletion.py",
    ),
    "torrent_add_file": (
        "app/mcp/tools/torrent_add.py",
        "app/services/torrent_add_service.py",
        "app/api/endpoints/torrent_crud.py",
    ),
    "cron_task_trigger": (
        "app/mcp/tools/cron.py",
        "app/tasks/cron_trigger.py",
        None,
    ),
}

_FORBIDDEN_ANNOTATIONS = ("Request", "UploadFile", "CommonResponse")
# 词边界匹配：EnhancedAdvancedSearchRequest 等含 Request 子串的领域模型名不误报
_FORBIDDEN_ANNOTATION_RE = re.compile(r"\b(Request|UploadFile|CommonResponse)\b")


def _parse_source(source: str) -> ast.AST:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(source)


def _parse_file(path: Path) -> ast.AST:
    return _parse_source(path.read_text(encoding="utf-8-sig"))


def _rel(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


def _dotted(rel_path: str) -> str:
    return rel_path[: -len(".py")].replace("/", ".").replace(".__init__", "")


def _imported_modules(tree: ast.AST, prefixes: Tuple[str, ...]) -> Set[str]:
    """tree 内（含函数级）import 的、命中前缀的模块点路径集合。"""
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(prefixes):
                found.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(prefixes):
                    found.add(alias.name)
    return found


def _business_closure() -> Set[str]:
    """MCP 层引用的业务模块闭包（沿 app.services/app.tasks/app.core 前缀展开到不动点）。"""
    rel_paths: Set[str] = set()
    pending: List[str] = []
    for path in _MCP_SOURCE_FILES:
        if "__pycache__" in path.parts:
            continue
        for module in _imported_modules(_parse_file(path), _BUSINESS_PREFIXES):
            if module not in pending:
                pending.append(module)
    visited: Set[str] = set()
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        rel_path = module.replace(".", "/") + ".py"
        candidate = BACKEND_ROOT / rel_path
        if not candidate.is_file():
            candidate = BACKEND_ROOT / (module.replace(".", "/")) / "__init__.py"
            if not candidate.is_file():
                continue
        rel_paths.add(_rel(candidate))
        for sub in _imported_modules(_parse_file(candidate), _BUSINESS_PREFIXES):
            if sub not in visited:
                pending.append(sub)
    return rel_paths


def _purity_violations(rel_path: str, tree: ast.AST) -> List[str]:
    """业务模块纯度：禁 fastapi/starlette、禁 endpoint 层 import、禁三大协议类型签名。"""
    violations: List[str] = []
    exempt_funcs = _ADAPTER_EXCEPTION_MODULES.get(rel_path)
    adapter_module = exempt_funcs is not None
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in ("fastapi", "starlette") and not adapter_module:
                violations.append(f"{rel_path}:{node.lineno} import {node.module}（业务层禁 web 框架）")
            if (node.module == "app.api" or node.module.startswith("app.api.")) and not (
                node.module == "app.api" or node.module.startswith("app.api.models")
            ):
                violations.append(f"{rel_path}:{node.lineno} import {node.module}（禁 endpoint 层依赖）")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in ("fastapi", "starlette") and not adapter_module:
                    violations.append(f"{rel_path}:{node.lineno} import {alias.name}（业务层禁 web 框架）")
                if alias.name == "app.api" or (
                    alias.name.startswith("app.api.") and not alias.name.startswith("app.api.models")
                ):
                    violations.append(f"{rel_path}:{node.lineno} import {alias.name}（禁 endpoint 层依赖）")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if exempt_funcs and node.name in exempt_funcs:
                continue
            annotations: List[ast.expr] = []
            args = node.args
            for arg in list(args.args) + list(args.kwonlyargs) + list(getattr(args, "posonlyargs", [])):
                if arg.annotation is not None:
                    annotations.append(arg.annotation)
            if getattr(node, "returns", None) is not None:
                annotations.append(node.returns)
            for ann in annotations:
                text = ast.unparse(ann)
                match = _FORBIDDEN_ANNOTATION_RE.search(text)
                if match:
                    violations.append(
                        f"{rel_path}:{node.lineno} {node.name} 签名含 {match.group(1)}（业务层禁协议类型）"
                    )
    return violations


# ==============================================================================
# 静态守卫
# ==============================================================================


class TestServicePurityGuard:
    def test_closure_includes_expected_shared_services(self):
        closure = _business_closure()
        for expected in (
            "app/services/advanced_search.py",
            "app/services/advanced_search_condition_builder.py",
            "app/services/torrent_add_service.py",
            "app/services/torrent_add_helpers.py",
            "app/services/torrent_deletion_by_level.py",
            "app/services/dashboard_service.py",
            "app/services/torrent_vo_conversion.py",
            "app/tasks/cron_trigger.py",
            "app/services/audit_context.py",
        ):
            if (BACKEND_ROOT / expected).is_file():
                assert expected in closure, f"{expected} 应在 MCP 业务闭包内"

    def test_shared_services_pure(self):
        violations: List[str] = []
        for rel_path in sorted(_business_closure()):
            path = BACKEND_ROOT / rel_path
            violations.extend(_purity_violations(rel_path, _parse_file(path)))
        assert not violations, "\n".join(violations)

    def test_negative_mutations_flagged(self):
        """负向变异纪律：守卫函数必须对独立反例报红，只扫当前源码不算规则有效。"""
        samples = [
            ("from fastapi import Request\n\ndef f(r: Request):\n    return 1\n", "Request"),
            ("from fastapi import UploadFile\n\ndef f(u: UploadFile):\n    return 1\n", "UploadFile"),
            (
                "from app.api.responseVO import CommonResponse\n\ndef f() -> CommonResponse:\n    return 1\n",
                "CommonResponse",
            ),
            (
                "from app.api.endpoints.torrent_helpers import get_torrent_infos\n\ndef f():\n    return get_torrent_infos\n",
                "endpoint",
            ),
            ("import fastapi\n\ndef f():\n    return fastapi\n", "fastapi"),
        ]
        for source, keyword in samples:
            violations = _purity_violations("app/services/synthetic.py", _parse_source(source))
            assert violations and keyword in "\n".join(violations), f"反例未命中: {keyword}"

    def test_clean_sample_not_flagged(self):
        source = (
            "from app.services.torrent_add_helpers import calculate_info_hash\n"
            "from app.api.models.advanced_search import EnhancedAdvancedSearchRequest\n"
            "from typing import Any\n\n"
            "def f(request: EnhancedAdvancedSearchRequest) -> Any:\n    return request\n"
        )
        # app.api.models 白名单样例需登记到合法路径上下文（模块名不影响判定）
        violations = _purity_violations("app/services/synthetic_ok.py", _parse_source(source))
        assert violations == []


class TestSameServiceMapping:
    def test_http_and_mcp_share_service(self):
        problems: List[str] = []
        for tool_name, (mcp_file, service_rel, http_file) in SAME_SERVICE_MAP.items():
            service_dotted = _dotted(service_rel)
            mcp_imports = _imported_modules(_parse_file(BACKEND_ROOT / mcp_file), _BUSINESS_PREFIXES)
            if service_dotted not in mcp_imports:
                problems.append(f"{tool_name}: MCP 处理器未 import 共用 service {service_dotted}")
            if http_file is None:
                continue
            http_tree = _parse_file(BACKEND_ROOT / http_file)
            http_imports = _imported_modules(http_tree, ("app.services.", "app.tasks."))
            if service_dotted not in http_imports:
                problems.append(f"{tool_name}: HTTP 端点 {http_file} 未 import 共用 service {service_dotted}")
        assert not problems, "\n".join(problems)

    def test_cron_trigger_is_mcp_only(self):
        """cron 触发无 HTTP 入口（计划 §11.1）：endpoint 层不得 import cron_trigger。"""
        offenders: List[str] = []
        for path in sorted((APP_ROOT / "api" / "endpoints").glob("*.py")):
            if "app.tasks.cron_trigger" in _imported_modules(_parse_file(path), ("app.tasks.",)):
                offenders.append(_rel(path))
        assert not offenders, f"cron_trigger 出现 HTTP 入口: {offenders}"


# ==============================================================================
# 等价契约（运行时；需 mcp SDK，缺装自动 skip）
# ==============================================================================

httpx = pytest.importorskip("httpx")
pytest.importorskip("mcp.server.streamable_http_manager", reason="mcp SDK 未安装")

import base64  # noqa: E402
import contextlib  # noqa: E402
from datetime import datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import utils as auth_utils  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.database import Base  # noqa: E402
from app.mcp.server import create_mcp_server_bundle  # noqa: E402
from app.models.search_template import SearchTemplate  # noqa: E402
from app.services.mcp_settings_service import McpRuntimeSettings  # noqa: E402
from app.tasks.cron_models import CronTask  # noqa: E402
from app.torrents.audit_models import TorrentAuditLog  # noqa: E402
from app.torrents.models import TorrentInfo, TrackerInfo  # noqa: E402

TEST_SECRET = "test-secret-key-for-mcp-parity"
TEST_LOGIN_SECRET = "test-login-secret-for-mcp-parity"
RPC_HEADERS = {"Accept": "application/json, text/event-stream"}
HASH_VALUE = "a" * 40
PASSKEY_VALUE = "paritypasskey777"


def _make_token(username: str = "admin", user_id: int = 1) -> str:
    return auth_utils.create_access_token(
        {"sub": username, "user_id": str(user_id), "verify_secret": TEST_LOGIN_SECRET}
    )


@pytest.fixture
def auth_utils_patch():
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.SECRET_KEY = TEST_SECRET
    mock.ALGORITHM = "HS256"
    mock.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    with (
        patch("app.auth.utils.settings", mock),
        patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET),
    ):
        yield


def _minimal_torrent_bytes(name: bytes = b"parity-add") -> bytes:
    import bencodepy

    return bencodepy.encode(
        {
            b"announce": b"http://tracker.parity.example.com/announce",
            b"info": {b"name": name, b"piece length": 16384, b"length": 1, b"pieces": b"\x00" * 20},
        }
    )


class _StubStore:
    """最小下载器缓存：仅暴露 get_snapshot/get_snapshot_sync 返回给定 VO 列表。"""

    def __init__(self, vos: List[Any]):
        self._vos = vos

    async def get_snapshot(self) -> List[Any]:
        return list(self._vos)

    def get_snapshot_sync(self) -> List[Any]:
        return list(self._vos)


class _FakeQbClient:
    """qB 客户端桩：torrents_add 成功 + torrents_info 立即返回新种子。"""

    def __init__(self, info_hash: str, name: str):
        self.info_hash = info_hash
        self.name = name
        self.add_calls: List[Dict[str, Any]] = []

    def torrents_add(self, **kwargs: Any) -> str:
        self.add_calls.append(kwargs)
        return "Ok."

    def torrents_info(self, torrent_hashes: Optional[str] = None) -> List[Any]:
        return [
            SimpleNamespace(
                hash=self.info_hash,
                name=self.name,
                save_path="/downloads/parity",
                total_size=2048,
                state="stalledUP",
                added_on=1757000000,
                completion_on=0,
                ratio=1.0,
                ratio_limit=None,
                tags=["parity"],
                category="iso",
                super_seeding=False,
            )
        ]


def _expected_info_hash(content: bytes) -> str:
    import hashlib

    import bencodepy

    return hashlib.sha1(bencodepy.encode(bencodepy.decode(content)[b"info"])).hexdigest()


class _ParityStack:
    """等价测试栈：同步域库 + 异步审计库 + /mcp 挂载 + 可注入 stub store。"""

    def __init__(self) -> None:
        self.snapshot: Optional[McpRuntimeSettings] = None
        self.bundle: Any = None
        self.app: Any = None
        self.store: Any = None

    @classmethod
    async def create(
        cls,
        on: List[str],
        store: Any = None,
        state_extra: Optional[Dict[str, Any]] = None,
    ) -> "_ParityStack":
        stack = cls()
        stack.sync_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            bind=stack.sync_engine,
            tables=[t.__table__ for t in (User, TorrentInfo, TrackerInfo, CronTask, SearchTemplate)],
        )
        stack.sync_factory = sessionmaker(bind=stack.sync_engine)

        stack.async_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with stack.async_engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(c, tables=[TorrentAuditLog.__table__, CronTask.__table__])
            )
        stack.async_factory = async_sessionmaker(bind=stack.async_engine, class_=AsyncSession, expire_on_commit=False)

        db = stack.sync_factory()
        db.add(User(username="admin", password="x", is_active=True, must_change_password=False))
        db.add(
            TorrentInfo(
                "i-1",  # info_id
                "1",  # downloader_id
                "qbt",  # downloader_name
                "42",  # torrent_id
                HASH_VALUE,
                "ubuntu-24.04-parity",
                "C:\\Downloads\\iso",
                1.5e9,
                "seeding",
                100.0,
                None,
                datetime(2026, 9, 8, 12, 0, 0),
                None,
                1.0,
                None,
                "linux",
                "iso",
                None,
                True,
                datetime(2026, 9, 8, 12, 0, 0),
                "admin",
                datetime(2026, 9, 8, 12, 0, 0),
                "admin",
                0,
            )
        )
        db.add(
            TrackerInfo(
                tracker_id="t-1",
                torrent_info_id="i-1",
                tracker_name="t1",
                tracker_url=f"https://t.parity.example.org:8080/announce?passkey={PASSKEY_VALUE}",
                last_announce_msg="announce ok",
                dr=0,
            )
        )
        db.commit()
        db.close()

        adb = stack.async_factory()
        async with adb.begin():
            adb.add(
                CronTask(
                    task_name="t",
                    task_code="cleanup",
                    task_status=2,
                    task_type=5,
                    executor="",
                    cron_plan="0 0 * * *",
                    dr=0,
                )
            )
        await adb.close()

        stack.store = store
        state = SimpleNamespace(store=store, **(state_extra or {}))
        stack.snapshot = McpRuntimeSettings(
            enabled=True,
            capabilities={
                code: code in on
                for code in __import__("app.mcp.contracts", fromlist=["CAPABILITY_CODES"]).CAPABILITY_CODES
            },
            revision=1,
        )
        stack.bundle = create_mcp_server_bundle(state)
        stack.bundle.runtime.settings_provider = lambda: stack.snapshot
        stack.bundle.runtime.session_factory = stack.sync_factory
        stack.bundle.runtime.async_session_factory = stack.async_factory
        stack.bundle.runtime.mark_ready()

        stack.app = FastAPI()
        stack.app.mount("/mcp", stack.bundle.sub_asgi)
        return stack

    async def close(self) -> None:
        self.sync_engine.dispose()
        await self.async_engine.dispose()


@contextlib.asynccontextmanager
async def _stack_client(stack: _ParityStack):
    async with stack.bundle.sub_asgi.router.lifespan_context(stack.bundle.sub_asgi):
        transport = ASGITransport(app=stack.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers={"Authorization": f"Bearer {_make_token()}"}
        ) as client:
            resp = await client.post(
                "/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "btdeck-parity", "version": "0"},
                    },
                },
                headers=RPC_HEADERS,
            )
            assert resp.status_code == 200
            await client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=RPC_HEADERS,
            )
            yield client


async def _call(client: Any, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    resp = await client.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "method": "tools/call", "id": 99, "params": {"name": name, "arguments": arguments}},
        headers=RPC_HEADERS,
    )
    assert resp.status_code == 200, resp.text[:300]
    return resp.json()


def _payload(resp: Dict[str, Any]) -> Dict[str, Any]:
    result = resp.get("result", {})
    assert result.get("isError") is False, f"工具调用失败: {result.get('structuredContent')}"
    return result.get("structuredContent") or {}


_NAME_CONDITIONS = {
    "source": "advanced",
    "condition_groups": [
        {"logic": "AND", "conditions": [{"field": "name", "operator": "contains", "value": "ubuntu"}]}
    ],
}
# 搜索请求模型无 source 字段（source 是模板持久化包装字段）
_SEARCH_REQUEST_CONDITIONS = {"condition_groups": _NAME_CONDITIONS["condition_groups"]}


class TestAdvancedSearchEquivalence:
    async def test_service_rows_equal_mcp_items(self, auth_utils_patch):
        """HTTP 路径（service 直调=端点薄壳同参数）与 MCP 输出领域事实一致；
        MCP 仅追加脱敏（tracker 收敛域名、路径仅末段）。"""
        from app.api.models.advanced_search import EnhancedAdvancedSearchRequest
        from app.services.advanced_search import AdvancedSearchService

        stack = await _ParityStack.create(on=["torrent.advanced_search"])
        try:
            db = stack.sync_factory()
            request = EnhancedAdvancedSearchRequest.model_validate(
                {"page": 1, "limit": 20, **_SEARCH_REQUEST_CONDITIONS}
            )
            service_result = AdvancedSearchService(db).search_torrents(request, "1")
            db.close()
            assert service_result["status"] == "success"
            rows = service_result["data"]
            assert len(rows) == 1

            async with _stack_client(stack) as client:
                data = _payload(
                    await _call(
                        client,
                        "torrent_advanced_search",
                        {"conditions": dict(_SEARCH_REQUEST_CONDITIONS), "page": 1, "page_size": 20},
                    )
                )

            assert data["total"] == service_result["total"] == 1
            item = data["items"][0]
            row = rows[0]
            assert item["info_id"] == row["infoId"] == "i-1"
            assert item["name"] == row["name"] == "ubuntu-24.04-parity"
            assert item["size_bytes"] == row["size"]
            assert item["state"] == row["status"]
            assert item["category"] == row["category"] == "iso"
            assert item["tags"] == row["tags"] == "linux"
            # MCP 脱敏面：tracker 只剩域名、路径仅末段（service 行携带原文属 HTTP 侧语义）
            assert item["tracker_domains"] == ["t.parity.example.org"]
            assert item["path_display"] == "iso"
            assert PASSKEY_VALUE not in str(data)
        finally:
            await stack.close()


class TestDashboardEquivalence:
    async def test_service_stats_equal_mcp_payload(self, auth_utils_patch):
        from app.core.runtime_context import RuntimeContext
        from app.services.dashboard_service import DashboardService

        stack = await _ParityStack.create(
            on=["dashboard.read"], store=_StubStore([]), state_extra={"torrent_stats": {"active": 2, "seeding": 5}}
        )
        try:
            adb = stack.async_factory()
            service = DashboardService(
                adb, RuntimeContext(store=stack.store, torrent_stats={"active": 2, "seeding": 5})
            )
            direct = await service.get_dashboard_data()
            await adb.close()

            async with _stack_client(stack) as client:
                data = _payload(await _call(client, "dashboard_get", {}))

            torrents_stats = direct["torrents"]
            assert data["status_counts"] == torrents_stats
            assert data["active_torrent_count"] == torrents_stats.get("active", 0)
            assert data["totals"]["torrents"] == torrents_stats
            assert data["totals"]["downloaders"] == direct["downloaders"]
        finally:
            await stack.close()


class TestTemplateCreateEquivalence:
    async def test_service_create_equals_mcp_create(self, auth_utils_patch):
        from app.services.advanced_search import AdvancedSearchService

        stack = await _ParityStack.create(on=["search_template.create"])
        try:
            # 同 user 模板名唯一：两路用不同名，比对领域结构等价
            http_payload = {"name": "tpl-parity-http", "conditions": _NAME_CONDITIONS, "is_public": False}
            mcp_payload = {"name": "tpl-parity-mcp", "conditions": _NAME_CONDITIONS, "is_public": False}
            db = stack.sync_factory()
            direct = AdvancedSearchService(db).create_search_template(dict(http_payload), "1")
            db.close()
            assert direct.get("status") == "success"

            async with _stack_client(stack) as client:
                data = _payload(
                    await _call(
                        client,
                        "advanced_search_template_create",
                        {**mcp_payload, "confirm": True, "idempotency_key": "parity-k"},
                    )
                )

            db = stack.sync_factory()
            from app.models.search_template import SearchTemplate

            rows = db.query(SearchTemplate).order_by(SearchTemplate.id).all()
            db.close()
            assert len(rows) == 2  # HTTP 路径与 MCP 各一行，同 user 同构
            by_name = {r.name: r for r in rows}
            assert set(by_name) == {"tpl-parity-http", "tpl-parity-mcp"}
            assert all(r.user_id == "1" for r in rows)
            assert all(r.is_public == 0 for r in rows)
            # 等价点：两路经同一 service 归一化后的 conditions 完全一致
            # （service 可能补默认键，不与原始输入做全等比对）
            assert rows[0].conditions == rows[1].conditions
            assert "condition_groups" in rows[0].conditions
            assert data["created"] is True
            assert data["name"] == "tpl-parity-mcp"
            assert data["template_id"]
        finally:
            await stack.close()


class TestTorrentAddEquivalence:
    async def test_http_service_path_equals_mcp_path(self, auth_utils_patch):
        """同一 DB/stub 下载器：HTTP 薄壳路径（service 直调）先建行，MCP 同种子
        再添加报 duplicate 且 info_id 指向同一行——两路领域事实一致。"""
        from app.services.torrent_add_service import TorrentAddParams, TorrentAddService

        content = _minimal_torrent_bytes()
        info_hash = _expected_info_hash(content)
        client_stub = _FakeQbClient(info_hash, "parity-add")
        vo = SimpleNamespace(
            downloader_id="1", fail_time=0, client=client_stub, nickname="qbt-parity", downloader_type=0
        )
        stack = await _ParityStack.create(on=["torrent.add"], store=_StubStore([vo]))
        try:
            with patch("app.services.torrent_add_service.AsyncSessionLocal", stack.async_factory):
                # HTTP 路径：端点薄壳对 service 的同参直调（audit_context 由端点构造，
                # 此处传 None=端点无请求对象时的等价形态）
                db = stack.sync_factory()
                http_result = await TorrentAddService(db, store=stack.store).add_torrent(
                    TorrentAddParams(downloader_id="1", save_path=None),
                    torrent_content=content,
                    audit_context=None,
                    operator="admin",
                )
                db.close()
                assert http_result.ok and http_result.created is True

                async with _stack_client(stack) as client:
                    data = _payload(
                        await _call(
                            client,
                            "torrent_add_file",
                            {
                                "torrent_file_b64": base64.b64encode(content).decode("ascii"),
                                "downloader_id": "1",
                                "confirm": True,
                                "idempotency_key": "parity-add-k",
                            },
                        )
                    )

            # 领域事实等价：MCP duplicate 指向 HTTP 路径创建的同一行
            assert data["added"] is False and data["duplicate"] is True
            assert data["info_id"] == http_result.info_id
            assert data["name"] == http_result.name == "parity-add"
            assert data["downloader_id"] == "1"
            assert data["downloader_nickname"] == "qbt-parity"

            db = stack.sync_factory()
            rows = db.query(TorrentInfo).filter(TorrentInfo.hash == info_hash).all()
            db.close()
            assert len(rows) == 1  # 两路同一行，不重复入库
            assert rows[0].downloader_id == "1" and rows[0].name == "parity-add"
            # 下载器仅被 HTTP 路径真实调用（MCP 路径 DB 已存在→仍走下载器添加但记录复用）
            assert len(client_stub.add_calls) == 2
        finally:
            await stack.close()
