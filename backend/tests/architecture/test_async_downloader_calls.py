# -*- coding: utf-8 -*-
"""
异步请求端下载器调用架构约束测试（sync-database-blocking-remediation W2-3，P0-04）

背景：torrent_crud.py / tracker.py / torrent_status.py 等 async 处理器曾直接执行同步
qB/TR 客户端调用（慢网络阻塞事件循环），并在 async def 内漏 await 异步 helper（coroutine
被丢弃、功能静默失效）。W2-3 按垂直切片迁移：tracker.py 已迁移，其余端点由后续切片补齐。

本框架职责（AST 静态扫描，不 import app 包）：
1. 端点文件禁止构造同步下载器客户端（qbClient/trClient/Client）——客户端只能来自
   app.state.store；允许构造的位置以文件级白名单登记（downloader_adapters / 缓存管理层）。
2. async 函数体内禁止对客户端对象（client/torrent/tr_torrent_info 等）裸调用同步方法，
   所有下载器调用必须经 call_downloader_api（DownloadLane.INTERACTIVE）封装。
3. 已知异步 helper 的调用点必须带 await（防漏 await 回归）。

扩展结构：_ENDPOINT_RULES 是「文件 → 禁止模式」字典；后续切片（torrent_crud /
torrent_status / torrent_deletion / tag_management / downloader）按同结构追加条目即可，
未列入的文件本框架不扫描（由对应切片补齐）。白名单只增不改。

测试风格参照 backend/tests/test_architecture_constraints.py：纯 ast 解析，
不 import app 包，避免在 CI 中触发配置、数据库或外部服务初始化。
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# 允许直接构造/使用同步下载器客户端的文件级白名单（客户端连接生命周期归缓存层管理）。
# 后续切片扩展规则时只增不改；路径漂移时 test_allowlist_paths_exist 报红。
_CLIENT_CONSTRUCTION_ALLOWLIST = (
    "app/services/downloader_adapters/",  # 下载器适配层（连接管理/能力探测）
    "app/downloader/initialization.py",  # 缓存管理层（app.state.store 唯一合法构造点）
)

# 同步客户端构造名（模块级 import Client 与构造调用均禁止出现在端点文件）。
_CLIENT_CONSTRUCTOR_NAMES = ("qbClient", "trClient", "Client")

# 端点文件规则：文件相对路径（相对 BACKEND_ROOT）→ 禁止模式。
# 后续切片扩展示例：
#   "app/api/endpoints/torrent_crud.py": {
#       "client_constructor_names": ("qbClient", "trClient", "Client"),
#       "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
#       "async_helpers_require_await": ("qb_add_torrent", "tr_add_torrent"),
#   },
_ENDPOINT_RULES = {
    "app/api/endpoints/tracker.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        # async 函数体内禁止对这些接收者对象直接调用方法（裸同步 RPC）。
        # 迁移后 client.* / torrent.* / tr_torrent_info.* 只能作为 call_downloader_api
        # 的 func 实参传入（Attribute 引用，不是 Call），故不会被误报。
        "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
        # 已知 async helper：调用点必须带 await（漏 await = coroutine 静默丢弃）。
        "async_helpers_require_await": (
            "qb_add_torrents_tracker",
            "tr_add_torrents_tracker",
            "qb_change_torrents_tracker",
            "tr_change_torrents_tracker",
            "qb_replace_tracker",
            "tr_replace_tracker",
        ),
    },
    # W2-3 种子 CRUD + 状态控制垂直切片（P0-04）：create_torrent 的 add / 轮询查询
    # 与 pause/resume/recheck 全部经 call_downloader_api(INTERACTIVE) 执行。
    "app/api/endpoints/torrent_crud.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
        # 已知 async helper：calculate_info_hash（torrent_helpers）与
        # get_transmission_torrent_info（torrent_helpers，轮询 30 次内的封装调用）。
        "async_helpers_require_await": ("calculate_info_hash", "get_transmission_torrent_info"),
    },
    # /add 主体 2026-09-05 抽取至服务层：规则随之迁移，确保 add/轮询继续经
    # call_downloader_api(INTERACTIVE) 执行、helper 调用点带 await。
    "app/services/torrent_add_service.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
        "async_helpers_require_await": ("calculate_info_hash", "get_transmission_torrent_info"),
    },
    "app/api/endpoints/torrent_status.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
        # 已知 async helper：execute_reannounce（reannounce 服务入口）调用点必须 await。
        "async_helpers_require_await": ("execute_reannounce",),
    },
    # W2-3 标签管理垂直切片（P0-04）：删除/批量删除/分配标签的同步 helper 全部经
    # call_downloader_api(INTERACTIVE) 执行；客户端来自 app.state.store。
    "app/api/endpoints/tag_management.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client",),
        # 已知 async helper：调用点必须带 await（_sync_tag_to_downloader 由
        # create_tag/update_tag 调用，登记强制调用点带 await）。
        "async_helpers_require_await": (
            "_sync_tag_to_downloader",
            "_sync_tags_to_torrent_downloader",
            "_sync_tag_delete_to_downloader",
        ),
    },
    # W2-3 下载器状态垂直切片（P0-04）：get_status 降级路径的 detail helper 改为
    # async + store 客户端 + call_downloader_api；不再自建 qbClient/trClient。
    "app/api/endpoints/downloader.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client", "qb_client", "tr_client"),
        "async_helpers_require_await": ("get_qbittorrent_detail", "get_transmission_detail"),
    },
    # W2-3 下载器设置垂直切片（P0-04）：test_downloader_settings 的网络探测经
    # call_downloader_api 执行。该文件模块级不 import 客户端；构造名显式含函数内
    # import 的 QBClient/TrClient 别名，保证豁免机制真实生效（不豁免时立即报红）。
    "app/api/endpoints/downloader_settings.py": {
        "client_constructor_names": ("qbClient", "trClient", "Client", "QBClient", "TrClient"),
        "client_object_names": ("qb_client", "tr_client"),
        "async_helpers_require_await": (),
        # 合法例外：test_downloader_settings 使用用户在页面提交的新配置（尚未保存，
        # store 中无对应客户端）测试连接，属于"新增/测试连接"场景，允许在函数内
        # 自建客户端做一次探测（不 login/logout、不入 store）；网络调用仍必须经
        # call_downloader_api。其余函数与模块级 import 一律禁止。
        "client_constructor_allowed_funcs": ("test_downloader_settings",),
    },
    # W2-3 服务层剩余切片（P0-04 收尾）：reannounce / recycle_bin / seed_transfer 服务的
    # async 方法内不再直接执行同步 qB/TR 调用，全部经 call_downloader_api(INTERACTIVE lane)；
    # 客户端一律来自 app.state.store 缓存（recycle_bin 经 downloader_vo.client，
    # transfer 经 store.get_snapshot 的 target/source VO，reannounce 经 _get_downloader_from_cache）。
    # recycle_bin_service 已移除模块级 qbClient/trClient 类型 import（标注改用 Any），
    # 故构造名规则可完整生效。
    "app/services/reannounce_service.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client",),
        "async_helpers_require_await": (),
    },
    "app/services/recycle_bin_service.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client", "qb_client", "tr_client"),
        "async_helpers_require_await": (),
    },
    "app/services/seed_transfer_service.py": {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("target_client", "source_client", "client"),
        "async_helpers_require_await": (),
    },
}

# 已迁移的下载器适配器切片（W2-3e，P0-04 删除/位置路径收尾）：
# async 函数体内禁止对 self.client / client 属性链裸调用同步下载器 API（慢网络
# 会阻塞事件循环）。允许 asyncio.to_thread / run_in_executor / call_downloader_api
# 包裹（含 lambda 形式，lambda 保证客户端懒建也发生在工作线程内）。
# 构造豁免：client property 的懒建（Client(...) + auth.log_in()）属于构造/兼容路径，
# 位于同步 property 内且属性链根为 self._client，不在 async 函数体扫描范围，天然不报红。
_ADAPTER_RULES = {
    "app/services/downloader_adapters/qbittorrent.py": {},
    "app/services/downloader_adapters/transmission.py": {},
    "app/services/downloader_adapters/qbittorrent_location.py": {},
    "app/services/downloader_adapters/transmission_location.py": {},
}


# =============================================================================
# AST 分析器
# =============================================================================


def _parse(path: Path) -> ast.AST:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _parent_map(tree: ast.AST) -> dict:
    """建立节点 → 父节点 映射（用于检查 Call 是否被 Await 包裹）。"""
    parents: dict = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _enclosing_func_name(parents: dict, node: ast.AST):
    """返回包含该节点的最近 AsyncFunctionDef/FunctionDef 函数名（无则 None）。

    用于函数级构造豁免（client_constructor_allowed_funcs）：模块级 import 的
    enclosing func 为 None，永不豁免。
    """
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, (ast.AsyncFunctionDef, ast.FunctionDef)):
            return cur.name
        cur = parents.get(cur)
    return None


def _client_constructor_violations(tree: ast.AST, names: tuple, allowed_funcs: tuple = ()) -> list:
    """文件内禁止 import Client / 构造 qbClient/trClient/Client。

    allowed_funcs: 函数级豁免——允许在指定函数内自建客户端（合法测试连接场景，
    如 downloader_settings.test_downloader_settings 用用户新提交配置探测）；
    模块级 import 与未登记函数内的构造仍报红。
    """
    parents = _parent_map(tree)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"qbittorrentapi", "transmission_rpc"}:
            for alias in node.names:
                if alias.name in names:
                    if _enclosing_func_name(parents, node) in allowed_funcs:
                        continue
                    violations.append(
                        f"行 {node.lineno}: 从 {node.module} import {alias.name}（客户端只能来自 app.state.store）"
                    )
        elif isinstance(node, ast.Call):
            func = node.func
            name_hit = None
            if isinstance(func, ast.Name) and func.id in names:
                name_hit = func.id
            elif isinstance(func, ast.Attribute) and func.attr in names:
                name_hit = func.attr
            if name_hit is not None:
                if _enclosing_func_name(parents, node) in allowed_funcs:
                    continue
                violations.append(f"行 {node.lineno}: 直接构造 {name_hit}(...)（禁止自建下载器客户端）")
    return violations


def _is_client_object_expr(value: ast.AST, object_names: tuple) -> bool:
    """判断表达式是否为以客户端对象名开头的属性链（client 或 client.torrents 等）。

    用于捕获嵌套属性链裸调用（如 client.torrents.set_category(...)，
    func.value 是 Attribute 而非 Name，旧实现会漏检）。
    """
    if isinstance(value, ast.Name):
        return value.id in object_names
    if isinstance(value, ast.Attribute):
        return _is_client_object_expr(value.value, object_names)
    return False


def _bare_client_call_violations(tree: ast.AST, object_names: tuple) -> list:
    """async def 函数体内禁止对客户端对象（含属性链）裸调用同步方法（必须经 call_downloader_api）。"""
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if _is_client_object_expr(sub.func.value, object_names):
                    violations.append(
                        f"{node.name} 行 {sub.lineno}: 裸调用 {ast.unparse(sub.func)}(...)（必须经 call_downloader_api）"
                    )
    return violations


# =============================================================================
# 下载器适配器文件规则（W2-3e）：async 方法内禁裸同步客户端调用
# =============================================================================

# 允许的封装调用名：被这些调用包裹（含 lambda 形式）的客户端调用视为已迁移。
# to_thread/run_in_executor 把同步调用移入工作线程；call_downloader_api 走统一
# DownloaderApiRuntime（INTERACTIVE lane 容量治理）。
_ADAPTER_WRAPPER_ALLOWLIST = ("to_thread", "run_in_executor", "call_downloader_api")


def _attribute_chain(value: ast.AST):
    """返回属性链元组（根 Name 在前），非 Name 根返回 None。

    例：self.client.torrents → ("self", "client", "torrents")；
        client.app.version → ("client", "app", "version")。
    """
    parts = []
    cur = value
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    return tuple(reversed(parts))


def _is_adapter_client_chain(chain) -> bool:
    """是否为下载器客户端属性链：self.client.* 或局部变量 client.*。

    注意 self._client（缓存字段）不在禁止范围——懒建 property 内部对 _client 的
    登录/登出调用属构造路径，天然豁免。
    """
    if not chain:
        return False
    if chain[0] == "client":
        return True
    return len(chain) >= 2 and chain[:2] == ("self", "client")


def _wrapper_call_name(node: ast.Call):
    """Call 的 func 名（Name 或 Attribute 末段，如 asyncio.to_thread → to_thread）。"""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_inside_wrapper(parents: dict, node: ast.AST) -> bool:
    """节点是否位于允许的封装调用（to_thread/run_in_executor/call_downloader_api）实参内。"""
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.Call) and _wrapper_call_name(cur) in _ADAPTER_WRAPPER_ALLOWLIST:
            return True
        cur = parents.get(cur)
    return False


def _adapter_bare_client_call_violations(tree: ast.AST, parents: dict) -> list:
    """adapter 文件：async def 内禁止对 self.client / client 属性链裸调用同步方法。"""
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call) or not isinstance(sub.func, ast.Attribute):
                continue
            if not _is_adapter_client_chain(_attribute_chain(sub.func.value)):
                continue
            if _is_inside_wrapper(parents, sub):
                continue
            violations.append(
                f"{node.name} 行 {sub.lineno}: 裸调用 {ast.unparse(sub.func)}(...)（必须经 asyncio.to_thread / call_downloader_api 包裹）"
            )
    return violations


def _missing_await_violations(tree: ast.AST, helper_names: tuple) -> list:
    """已知 async helper 的调用点必须带 await（防漏 await 静默失效回归）。"""
    parents = _parent_map(tree)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in helper_names:
            if not isinstance(parents.get(node), ast.Await):
                violations.append(f"行 {node.lineno}: 调用 async helper {node.func.id}(...) 缺少 await")
    return violations


def _analyze_file(tree: ast.AST, rules: dict) -> list:
    """对单个文件的 AST 应用全部禁止模式，返回违规描述列表。"""
    violations = []
    violations.extend(
        _client_constructor_violations(
            tree,
            rules["client_constructor_names"],
            allowed_funcs=rules.get("client_constructor_allowed_funcs", ()),
        )
    )
    violations.extend(_bare_client_call_violations(tree, rules["client_object_names"]))
    violations.extend(_missing_await_violations(tree, rules["async_helpers_require_await"]))
    return violations


# =============================================================================
# 框架自检（负向样例）：规则必须能抓到反例，避免"当前仓库恰好无违规"假通过
# =============================================================================


def test_analyzer_flags_client_constructor():
    """负向样例：async def 内构造 qbClient 必须被识别。"""
    tree = ast.parse("async def f():\n    qb_client = qbClient(host, port=1, username='u', password='p')\n")
    violations = _analyze_file(
        tree,
        {
            "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
            "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
            "async_helpers_require_await": ("qb_add_torrents_tracker",),
        },
    )
    assert any("构造 qbClient" in v for v in violations)


def test_analyzer_flags_bare_client_call_in_async_func():
    """负向样例：async def 内裸调用 client.torrents_info(...) 必须被识别。"""
    tree = ast.parse(
        "async def qb_add_torrents_tracker(db, client, torrent_id):\n"
        "    torrent = client.torrents_info(torrent_hashes=torrent_id)[0]\n"
        "    torrent.add_trackers(['http://t/announce'])\n"
    )
    violations = _analyze_file(
        tree,
        {
            "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
            "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
            "async_helpers_require_await": (),
        },
    )
    assert any("裸调用 client.torrents_info" in v for v in violations)
    assert any("裸调用 torrent.add_trackers" in v for v in violations)


def test_analyzer_flags_missing_await_on_helper():
    """负向样例：async helper 调用缺 await 必须被识别；带 await 则通过。"""
    rules = {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
        "async_helpers_require_await": ("tr_add_torrents_tracker",),
    }
    bad = ast.parse("async def add_tracker(db):\n    tr_add_torrents_tracker(db, vo, ['t'], 1, 'info')\n")
    assert any("缺少 await" in v for v in _analyze_file(bad, rules))

    good = ast.parse("async def add_tracker(db):\n    await tr_add_torrents_tracker(db, vo, ['t'], 1, 'info')\n")
    assert not _analyze_file(good, rules)


def test_analyzer_allows_awaited_db_and_lane_wrapped_calls():
    """正向样例：await db.execute / call_downloader_api(client.method) 封装不得误报。"""
    tree = ast.parse(
        "async def qb_add(db, client, torrent_id):\n"
        "    torrents = await call_downloader_api('dl', lane, client.torrents_info,"
        " kwargs={'torrent_hashes': torrent_id}, operation='qb_info')\n"
        "    torrent = torrents[0]\n"
        "    await call_downloader_api('dl', lane, torrent.add_trackers, args=(['t'],), operation='qb_add')\n"
        "    await db.commit()\n"
    )
    rules = {
        "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
        "client_object_names": ("client", "qb_client", "tr_client", "torrent", "tr_torrent_info", "torrents"),
        "async_helpers_require_await": (),
    }
    assert not _analyze_file(tree, rules)


def test_analyzer_flags_nested_attribute_client_call():
    """负向样例（W2-3 标签切片）：嵌套属性链裸调用 client.torrents.set_category(...) 必须被识别。"""
    tree = ast.parse(
        "async def sync_tag_delete(client):\n"
        "    client.torrents.set_category(category='cat', torrent_hashes=['h'])\n"
    )
    violations = _analyze_file(
        tree,
        {
            "client_constructor_names": _CLIENT_CONSTRUCTOR_NAMES,
            "client_object_names": ("client",),
            "async_helpers_require_await": (),
        },
    )
    assert any("裸调用 client.torrents.set_category" in v for v in violations)


def test_analyzer_constructor_exemption_by_func():
    """正向/负向样例（W2-3 下载器设置切片）：登记在 client_constructor_allowed_funcs 的
    函数内自建客户端不报红；模块级 import 与未登记函数仍报红。"""
    rules = {
        "client_constructor_names": ("qbClient", "trClient", "Client", "QBClient", "TrClient"),
        "client_object_names": ("qb_client", "tr_client"),
        "async_helpers_require_await": (),
        "client_constructor_allowed_funcs": ("test_downloader_settings",),
    }
    good = ast.parse(
        "async def test_downloader_settings(req):\n"
        "    from qbittorrentapi import Client as QBClient\n"
        "    qb_client = QBClient(host='http://h', username='u', password='p')\n"
        "    version = await call_downloader_api('dl', lane, qb_client.app_version, operation='qb_test')\n"
    )
    assert not _analyze_file(good, rules)

    bad_func = ast.parse(
        "async def other_func(req):\n"
        "    from qbittorrentapi import Client as QBClient\n"
        "    qb_client = QBClient(host='http://h', username='u', password='p')\n"
    )
    assert any("构造 QBClient" in v for v in _analyze_file(bad_func, rules))

    bad_module = ast.parse("from qbittorrentapi import Client as QBClient\n" "async def f(req):\n" "    return req\n")
    assert any("import Client" in v for v in _analyze_file(bad_module, rules))


# =============================================================================
# 白名单与规则表完整性
# =============================================================================


def test_allowlist_paths_exist():
    """文件级白名单路径必须真实存在（漂移即报红，防止白名单悄悄失效）。"""
    for rel in _CLIENT_CONSTRUCTION_ALLOWLIST:
        target = BACKEND_ROOT / rel
        assert target.exists(), f"白名单路径缺失: {rel}（下载器客户端构造点迁移了吗？）"


def test_rules_files_exist():
    """规则表内的端点文件必须真实存在（路径漂移时测试应报红而非静默通过）。"""
    for rel in _ENDPOINT_RULES:
        assert (BACKEND_ROOT / rel).exists(), f"规则文件缺失: {rel}"


def test_tracker_migration_slice_registered():
    """本切片（tracker.py）必须登记在规则表中。"""
    assert "app/api/endpoints/tracker.py" in _ENDPOINT_RULES, "tracker.py 切片未登记规则"


def test_w2_3c_migration_slices_registered():
    """本切片（标签 + 下载器设置/状态）必须登记在规则表中。"""
    for rel in (
        "app/api/endpoints/tag_management.py",
        "app/api/endpoints/downloader.py",
        "app/api/endpoints/downloader_settings.py",
    ):
        assert rel in _ENDPOINT_RULES, f"{rel} 切片未登记规则"


def test_w2_3d_service_slices_registered():
    """本切片（W2-3d 服务层剩余：reannounce/recycle_bin/seed_transfer）必须登记在规则表中。"""
    for rel in (
        "app/services/reannounce_service.py",
        "app/services/recycle_bin_service.py",
        "app/services/seed_transfer_service.py",
    ):
        assert rel in _ENDPOINT_RULES, f"{rel} 切片未登记规则"


# =============================================================================
# 已迁移切片的架构断言
# =============================================================================


@pytest.mark.parametrize("rel_path", sorted(_ENDPOINT_RULES.keys()))
def test_endpoint_slice_no_direct_sync_downloader_calls(rel_path: str):
    """已迁移端点切片：无客户端自建、async 函数体内无裸同步客户端调用、async helper 必 await。

    mutation 验证点：把 tracker.py 改回 qbClient(...) 自建 / client.torrents_info(...)
    裸调用 / 漏掉 await qb_add_torrents_tracker(...)，此测试立即报红。
    """
    tree = _parse(BACKEND_ROOT / rel_path)
    violations = _analyze_file(tree, _ENDPOINT_RULES[rel_path])
    assert not violations, f"{rel_path} 存在禁止的同步下载器调用模式（P0-04，W2-3）：\n" + "\n".join(violations)


# =============================================================================
# 下载器适配器切片（W2-3e）自检与断言
# =============================================================================


def test_adapter_analyzer_flags_bare_client_call_in_async_func():
    """负向样例：async def 内裸调用 self.client.torrents.delete(...) 必须被识别。"""
    tree = ast.parse("async def _delete(self, hashes):\n    self.client.torrents.delete(hashes=hashes)\n")
    violations = _adapter_bare_client_call_violations(tree, _parent_map(tree))
    assert any("裸调用 self.client.torrents.delete" in v for v in violations)


def test_adapter_analyzer_flags_local_client_var_bare_call():
    """负向样例：async def 内裸调用局部变量 client.torrents.info(...) 必须被识别。"""
    tree = ast.parse("async def probe(client):\n    return client.torrents.info()\n")
    violations = _adapter_bare_client_call_violations(tree, _parent_map(tree))
    assert any("裸调用 client.torrents.info" in v for v in violations)


def test_adapter_analyzer_allows_to_thread_and_lane_wrapped_calls():
    """正向样例：to_thread（直接引用 + lambda 形式）与 call_downloader_api 包裹不得误报。"""
    tree = ast.parse(
        "async def delete(self, hashes):\n"
        "    await asyncio.to_thread(self.client.remove_torrent, ids=hashes, delete_data=True)\n"
        "    await asyncio.to_thread(lambda: self.client.torrents.delete(hashes=hashes))\n"
        "    version = await call_downloader_api('dl', lane, self.client.app.version, operation='v')\n"
    )
    assert not _adapter_bare_client_call_violations(tree, _parent_map(tree))


def test_adapter_analyzer_allows_lazy_construction_property():
    """正向样例：client property 的懒建构造（Client(...) + auth.log_in()）属于同步 property
    （不在 async 函数体），且属性链根为 self._client，不报红。"""
    tree = ast.parse(
        "def client(self):\n"
        "    self._client = Client(host='http://h', username='u', password='p')\n"
        "    self._client.auth.log_in()\n"
        "    return self._client\n"
    )
    assert not _adapter_bare_client_call_violations(tree, _parent_map(tree))


def test_adapter_rules_files_exist():
    """适配器规则表内的文件必须真实存在（路径漂移即报红）。"""
    for rel in _ADAPTER_RULES:
        assert (BACKEND_ROOT / rel).exists(), f"适配器规则文件缺失: {rel}"


def test_w2_3e_adapter_slices_registered():
    """本切片（删除/位置 4 个下载器适配器文件）必须登记在规则表中。"""
    expected = {
        "app/services/downloader_adapters/qbittorrent.py",
        "app/services/downloader_adapters/transmission.py",
        "app/services/downloader_adapters/qbittorrent_location.py",
        "app/services/downloader_adapters/transmission_location.py",
    }
    assert expected <= set(_ADAPTER_RULES), f"缺失适配器切片登记: {expected - set(_ADAPTER_RULES)}"


@pytest.mark.parametrize("rel_path", sorted(_ADAPTER_RULES.keys()))
def test_adapter_files_no_direct_sync_downloader_calls(rel_path: str):
    """已迁移的下载器适配器切片：async 函数体内无裸同步客户端调用（P0-04，W2-3e）。

    mutation 验证点：把 qbittorrent.py 的 asyncio.to_thread(lambda: self.client.xxx(...))
    改回 self.client.xxx(...) 裸调用，此测试立即报红。
    """
    tree = _parse(BACKEND_ROOT / rel_path)
    violations = _adapter_bare_client_call_violations(tree, _parent_map(tree))
    assert not violations, f"{rel_path} 存在禁止的同步下载器调用模式（P0-04，W2-3e）：\n" + "\n".join(violations)
