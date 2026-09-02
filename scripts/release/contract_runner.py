#!/usr/bin/env python3
"""BtDeck 黑盒契约执行器（release-artifact-equivalence-gate W4 / G8）。

对运行中的制品实例（DEB/RPM/Docker/Windows 服务的任意一个）执行固定场景，
输出规范化 JSON 快照，供 compare_snapshots.py 跨制品比对。

铁律（计划 §G8）：
  - 本文件禁止 import app.*：测试器必须走真实 HTTP，绕过制品内部即失效。
  - 场景内不携带实例特定值（token/user_id）进快照——快照只保留结构（字段
    路径集合）与身份字段（G1 等价的对象：version/gitSha/alembicHead/
    frontendManifestSha256 等，这些必须精确一致）。
  - 时间性字段（uptime/时间戳/checks 详情）只保留名称集合，不比数值。

批次 A 场景（C01~C04）：
  C01 健康与构建身份   live/ready 的身份字段精确值 + checks 名称集合
  C02 OpenAPI 契约     openapi.json 规范化摘要（paths×methods + schema 指纹）
  C03 初始化与认证     错误码/登录/刷新/登出/token 失效全链路
  C04 用户与设置       用户信息读 + 改密写 + 新旧密码重登验证（写持久化证明）

批次 B1 场景（C07/C08/C09/C11）：
  C07 查询模板         新建/列表/更新/删除全生命周期
  C08 定时任务         13 个种子任务名集合
  C09 通知与审计       分页信封形状 + 操作类型枚举
  C11 SPA              index/资源清单/fallback（docker 用 --spa-base-url）

批次 B2 场景（C05/C06/C12 同次调用；C10 在制品重启后单独调用再 --merge-into）：
  C05 下载器管理       受控 qB stub 下新增/测连(含不可达负向)/编辑/删除
  C06 种子核心查询     固定 stub 数据同步后的列表/分页/状态筛选/Tracker/单种子
  C10 迁移与重启       重启后契约密码可登录 + C06 数据仍可见 + 身份不变
  C12 文件路径边界     路径映射 CRUD/冲突拒绝/规范化文本/test 语义

场景顺序依赖：C04 先改密（后续场景用契约密码）；C06 须先于 C10/C12
（C10 验证其数据在重启后可见，C12 复用其下载器）。C06 的夹具下载器在
场景结束时保留（C10/C12 依赖），重跑幂等靠昵称预清理 + downloader_id 过滤。

用法：
  python contract_runner.py --base-url http://127.0.0.1:5001 \
      --output snapshot.json [--scenario-set A] [--timeout 10] \
      [--downloader-stub-host w4-stub] [--qb-port 18080] [--tr-port 18081]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1

# 初始凭据：制品首启 seed 的 admin/admin（强制改密前）
INITIAL_USERNAME = "admin"
INITIAL_PASSWORD = "admin"
# C04 改密目标：跨制品统一，使各实例快照可比较
CONTRACT_PASSWORD = "W4-Contract-Pass-2026"

# B2 受控下载器 stub（scripts/release/fixtures/qb_tr_stub.py）的固定凭据与
# 夹具昵称。runner 以单文件方式 docker cp 进容器，不能 import fixtures 包，
# 凭据在此镜像一份；两侧修改必须同步（test_contract_runner 有断言护栏）。
STUB_USERNAME = "w4stub-user"
STUB_PASSWORD = "w4stub-pass"
C05_NICKNAME = "w4-c05-qb"
C05_NICKNAME_DEAD = "w4-c05-dead"
C06_QB_NICKNAME = "w4-c06-qb"
C06_TR_NICKNAME = "w4-c06-tr"
# C05 专用 qB 端口（stub 第二个 qb 监听）：下载器缓存按 host:port 去重且
# delete 不清缓存——C05 与 C06 共用 18080 会让 C06 的下载器进不了缓存
# （"已存在，跳过添加"，本地双实例实证）。分端口是真实多 qB 实例拓扑。
C05_QB_PORT_DEFAULT = 18082
# 负向夹具主机名：测连是 ICMP/TCP 可达性探测（非登录），可达主机的关闭
# 端口仍会 success=True（ICMP 先通）——必须用不可解析主机名才能确定性失败
C05_DEAD_HOST = "w4-stub-dead.invalid"


class HttpResult:
    def __init__(self, status: int, body: Any, raw: bytes) -> None:
        self.status = status
        self.body = body
        self.raw = raw


def http_request(
    base_url: str,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    timeout: int = 10,
) -> HttpResult:
    """执行请求并返回 (http_status, parsed_body)。4xx/5xx 不抛异常。"""
    url = base_url.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Access-Token", token)
    status = 0
    raw = b""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except urllib.error.URLError:
        return HttpResult(-1, {"__unreachable__": True}, b"")
    try:
        body: Any = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {"__non_json_bytes__": len(raw)}
    return HttpResult(status, body, raw)


def http_request_raw(
    base_url: str,
    method: str,
    path: str,
    token: Optional[str] = None,
    timeout: int = 10,
) -> HttpResult:
    """同 http_request，但 body 保留解码文本（SPA index 等非 JSON 响应）。"""
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("X-Access-Token", token)
    status = 0
    raw = b""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except urllib.error.URLError:
        return HttpResult(-1, "", b"")
    return HttpResult(status, raw.decode("utf-8", errors="replace"), raw)


# ---------------- 规范化（快照只保留可比内容） ----------------

# G1 等价对象（计划 §G8 C01：version/SHA/head/frontend manifest 跨制品必须一致）。
# 不含 artifactKind：包型身份（linux-deb/linux-rpm/docker-backend）按制品类型
# 天然不同，不属于跨制品等价对象（build-info 层面的包型差异由 W2 bundle 校验）。
IDENTITY_FIELDS = (
    "status",
    "version",
    "productVersion",
    "gitSha",
    "gitTag",
    "alembicHead",
    "frontendManifestSha256",
    "sourceManifestSha256",
)


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def shape(value: Any, prefix: str = "") -> List[str]:
    """提取字段路径集合（不含值）——跨制品形状等价。

    列表取全部元素形状的并集（元素可能异构：[1, {...}]）。
    """
    paths: List[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            paths.extend(shape(value[key], f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        if value:
            for item in value:
                paths.extend(shape(item, f"{prefix}[]"))
        else:
            paths.append(f"{prefix}[]")
    else:
        paths.append(prefix)
    return sorted(set(paths))


def envelope(result: HttpResult) -> Dict[str, Any]:
    """CommonResponse 外壳的结构化视图（保留 code/status/msg，剔除 data 值）。"""
    body = result.body if isinstance(result.body, dict) else {}
    return {
        "http": result.status,
        "code": body.get("code"),
        "status": body.get("status"),
        "msg": body.get("msg"),
    }


def data_of(result: HttpResult) -> Any:
    body = result.body if isinstance(result.body, dict) else {}
    data = body.get("data")
    # 部分端点 data 是 [obj] 列表信封（login 等），取首元素形状代表
    if isinstance(data, list) and data:
        return data[0]
    return data


# ---------------- 场景 ----------------


def scenario_c01_health_identity(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C01：健康与构建身份。身份字段精确值（G1 等价对象），checks 只留名称。"""
    live = http_request(ctx["base_url"], "GET", "/health/live")
    ready = http_request(ctx["base_url"], "GET", "/health/ready")

    def identity_view(data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {"__missing__": True}
        build = data.get("build") if isinstance(data.get("build"), dict) else {}
        out = {name: data.get(name) for name in ("status", "version") if name in data}
        for field in IDENTITY_FIELDS:
            if field in build:
                out[f"build.{field}"] = build[field]
        checks = data.get("checks")
        if isinstance(checks, dict):
            out["checks.names"] = sorted(checks.keys())
        return out

    return {
        "live": {**envelope(live), "identity": identity_view(data_of(live))},
        "ready": {**envelope(ready), "identity": identity_view(data_of(ready))},
    }


def scenario_c02_openapi_contract(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C02：OpenAPI 契约。paths×methods 清单 + 全文规范化指纹（同源码必同指纹）。

    生产形态（DEV=false）按安全设计关闭 openapi_url（factory.py W11）——
    此时记录 unavailable（同形态制品间仍等价可比）；DEV 形态产出完整指纹。
    """
    result = http_request(ctx["base_url"], "GET", "/api/v1/openapi.json")
    if result.status == 404:
        result = http_request(ctx["base_url"], "GET", "/openapi.json")
    # 非 JSON 响应（生产形态下 openapi 路径落到前端静态 fallback 返回 200
    # 的 index.html）与 404 同义：openapi 不可用，按 unavailable 记录保持
    # 跨形态可比（w4 CI 第十一轮实测 4 条伪差异）
    non_json = isinstance(result.body, dict) and "__non_json_bytes__" in result.body
    if result.status == 404 or non_json:
        # 不记录 http 状态码：deb（静态 fallback 200）与 docker（404）的
        # 送达路径不同但语义同为"openapi 不可用"，状态码非契约对象
        return {"unavailable": "openapi disabled in production build"}
    spec = result.body if isinstance(result.body, dict) else {}
    route_map: Dict[str, List[str]] = {}
    for path, methods in sorted(spec.get("paths", {}).items()):
        route_map[path] = sorted(
            m.upper()
            for m in methods
            if m.lower() in {"get", "post", "put", "delete", "patch"}
        )
    fingerprint_payload = {
        "openapi": spec.get("openapi", ""),
        "info.title": spec.get("info", {}).get("title", ""),
        "paths": route_map,
        "schemas": sorted(spec.get("components", {}).get("schemas", {}).keys()),
    }
    return {
        "http": result.status,
        "route_count": len(route_map),
        "routes": route_map,
        "fingerprint": canonical_sha256(fingerprint_payload),
    }


def _login(ctx: Dict[str, Any], username: str, password: str) -> HttpResult:
    return http_request(
        ctx["base_url"],
        "POST",
        "/api/v1/auth/login",
        {"username": username, "password": password},
    )


def scenario_c03_auth_lifecycle(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C03：认证全链路。错误码、登录、info、refresh、logout、token 失效。

    注意登录限流（阶梯锁定）：错误登录仅 1 次，避免污染同实例的后续场景。
    """
    steps: Dict[str, Any] = {}

    bad = _login(ctx, INITIAL_USERNAME, "definitely-wrong-password")
    steps["login_wrong_password"] = {**envelope(bad), "data_shape": shape(data_of(bad))}

    ok = _login(ctx, INITIAL_USERNAME, INITIAL_PASSWORD)
    token_payload = data_of(ok) if isinstance(data_of(ok), dict) else {}
    steps["login_initial_admin"] = {
        **envelope(ok),
        "must_change_password": token_payload.get("must_change_password"),
        "data_shape": shape(token_payload),
    }
    token = token_payload.get("access_token")

    info = http_request(ctx["base_url"], "POST", "/api/v1/user/info", token=token)
    steps["user_info_authenticated"] = {
        **envelope(info),
        "data_shape": shape(data_of(info)),
    }

    refresh = http_request(
        ctx["base_url"],
        "POST",
        "/api/v1/auth/refresh",
        token=token,
    )
    steps["refresh_with_access_token"] = envelope(refresh)

    logout = http_request(ctx["base_url"], "POST", "/api/v1/user/logout", token=token)
    steps["logout"] = envelope(logout)

    after = http_request(ctx["base_url"], "POST", "/api/v1/user/info", token=token)
    steps["user_info_after_logout"] = envelope(after)

    return steps


def scenario_c04_user_settings(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C04：用户读写与改密持久化（写→重登验证=持久化证明）。

    顺序设计：admin/admin 登录（若 C03 已把密码改走则用契约密码——幂等），
    改密到统一契约密码，旧密码登录必 401，新密码登录必 200。
    """
    import base64

    steps: Dict[str, Any] = {}

    first = _login(ctx, INITIAL_USERNAME, INITIAL_PASSWORD)
    if str((first.body or {}).get("code")) == "200":
        token = (data_of(first) or {}).get("access_token")
        old_b64 = base64.b64encode(INITIAL_PASSWORD.encode()).decode()
        new_b64 = base64.b64encode(CONTRACT_PASSWORD.encode()).decode()
        change = http_request(
            ctx["base_url"],
            "POST",
            "/api/v1/user/changePassword",
            # userId 为 schema 必填（后端绑定 token 用户、忽略该值——安全
            # 修复 W8/W9 的服务端绑定语义），传 1 占位满足校验
            {"oldPassword": old_b64, "newPassword": new_b64, "userId": "1"},
            token=token,
        )
        steps["change_password"] = envelope(change)
    else:
        # 已在本轮更早被改密（重复执行幂等）：直接用契约密码登录
        steps["change_password"] = {"skipped": "already_changed"}

    old_login = _login(ctx, INITIAL_USERNAME, INITIAL_PASSWORD)
    steps["login_old_password_after_change"] = envelope(old_login)

    new_login = _login(ctx, INITIAL_USERNAME, CONTRACT_PASSWORD)
    steps["login_new_password"] = {
        **envelope(new_login),
        "data_shape": shape(data_of(new_login)),
    }
    return steps


def _auth_token(ctx: Dict[str, Any]) -> Optional[str]:
    """获取认证 token：优先契约密码（C04 改密后），回退初始口令（场景独立执行）。

    实例不可达与认证失败必须可区分（诊断语义）：不可达时抛 URLError 由
    场景层记录 __scenario_error__，而非静默 __no_token__。
    """
    reachable = False
    for password in (CONTRACT_PASSWORD, INITIAL_PASSWORD):
        result = _login(ctx, INITIAL_USERNAME, password)
        body = result.body if isinstance(result.body, dict) else {}
        if body.get("__unreachable__"):
            raise urllib.error.URLError(f"instance unreachable: {ctx['base_url']}")
        reachable = True
        if str(body.get("code")) == "200":
            data = data_of(result)
            if isinstance(data, dict):
                return data.get("access_token")
    if not reachable:
        raise urllib.error.URLError(f"instance unreachable: {ctx['base_url']}")
    return None


def scenario_c07_query_templates(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C07：查询模板全生命周期（新建/列表/更新/删除——高级条件语义走 simple 源）。"""
    token = _auth_token(ctx)
    steps: Dict[str, Any] = {}
    if not token:
        return {"__no_token__": True}

    def _items(payload: Any) -> List[Dict[str, Any]]:
        """模板列表适配：data 直接是数组（实测契约）或 dict 带 list/items 键。"""
        if isinstance(payload, list):
            return [i for i in payload if isinstance(i, dict)]
        if isinstance(payload, dict):
            for key in ("list", "items", "templates"):
                if isinstance(payload.get(key), list):
                    return [i for i in payload[key] if isinstance(i, dict)]
        return []

    fixture = {
        "name": "w4-contract-fixture",
        "description": "W4 blackbox contract fixture",
        "conditions": {
            "source": "simple",
            "listQuery": {"status": "all", "page": 1, "pageSize": 20},
        },
        "is_public": False,
    }
    created = http_request(
        ctx["base_url"],
        "POST",
        "/api/v1/advanced-search/search-templates",
        fixture,
        token=token,
    )
    created_data = data_of(created)
    template_id = created_data.get("id") if isinstance(created_data, dict) else None
    steps["create_template"] = {
        **envelope(created),
        "data_shape": shape(created_data),
    }

    listed = http_request(
        ctx["base_url"], "GET", "/api/v1/advanced-search/search-templates", token=token
    )
    # 列表端点的 data 直接是数组：不能用 data_of（[obj] 信封取首元素语义会吞列表）
    listed_payload = (
        (listed.body or {}).get("data") if isinstance(listed.body, dict) else None
    )
    names = sorted(str(i.get("name")) for i in _items(listed_payload))
    steps["list_templates"] = {**envelope(listed), "names": names}

    if template_id is not None:
        updated = http_request(
            ctx["base_url"],
            "PUT",
            f"/api/v1/advanced-search/search-templates/{template_id}",
            dict(fixture, name="w4-contract-fixture-renamed"),
            token=token,
        )
        steps["update_template"] = envelope(updated)

        deleted = http_request(
            ctx["base_url"],
            "DELETE",
            f"/api/v1/advanced-search/search-templates/{template_id}",
            token=token,
        )
        steps["delete_template"] = envelope(deleted)

        after = http_request(
            ctx["base_url"],
            "GET",
            "/api/v1/advanced-search/search-templates",
            token=token,
        )
        after_payload = (
            (after.body or {}).get("data") if isinstance(after.body, dict) else None
        )
        after_names = sorted(str(i.get("name")) for i in _items(after_payload))
        steps["list_after_delete"] = {**envelope(after), "names": after_names}
    return steps


def scenario_c08_cron_tasks(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C08：定时任务列表契约（13 个种子任务名集合跨制品必须一致）。"""
    token = _auth_token(ctx)
    if not token:
        return {"__no_token__": True}
    listed = http_request(ctx["base_url"], "GET", "/api/v1/cronTasks/list", token=token)
    # data 可能直接是数组（实测契约）或 dict 带 list/items 键；不能用 data_of
    # （[obj] 信封取首元素语义会吞列表）
    data = listed.body.get("data") if isinstance(listed.body, dict) else None
    task_names: List[str] = []
    task_shape: List[str] = []
    items: List[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("list") or data.get("items") or data.get("tasks") or []
    if items:
        task_shape = shape(items[0])
        task_names = sorted(
            str(t.get("name") or t.get("taskName") or t.get("cronName") or "")
            for t in items
            if isinstance(t, dict)
        )
    return {
        **envelope(listed),
        "task_count": len(task_names),
        "task_names": task_names,
        "task_shape": task_shape,
    }


def scenario_c09_notifications_audit(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C09：通知与审计的分页信封形状 + 稳定枚举（操作类型集合）。"""
    token = _auth_token(ctx)
    if not token:
        return {"__no_token__": True}
    notifications = http_request(
        ctx["base_url"], "GET", "/api/v1/notifications?page=1&pageSize=5", token=token
    )
    unread = http_request(
        ctx["base_url"], "GET", "/api/v1/notifications/unread-count", token=token
    )
    op_types = http_request(
        ctx["base_url"], "GET", "/api/v1/audit-logs/operation-types", token=token
    )
    op_payload = op_types.body.get("data") if isinstance(op_types.body, dict) else None
    return {
        "notifications": {
            **envelope(notifications),
            "data_shape": shape(data_of(notifications)),
        },
        "unread_count": {**envelope(unread), "data_shape": shape(data_of(unread))},
        # 操作类型是字符串数组：data_of 取首元素会退化，用原始 data 形状
        "audit_operation_types": {
            **envelope(op_types),
            "data_shape": shape(op_payload),
        },
    }


# ---------------- B2：受控 stub 场景（C05/C06/C10/C12） ----------------


def _require_code(result: HttpResult, step: str, expected: str = "200") -> None:
    """关键步骤语义断言：失败即抛错进 scenario_failures（runner 退出非零）。

    快照比对只能拦截"跨制品不一致"；三制品同样失败（如 stub 不可达）时
    快照仍相等——语义断言把"一致地坏"转化为显式失败（fail-closed）。
    """
    body = result.body if isinstance(result.body, dict) else {}
    if result.status != int(expected) or str(body.get("code")) != expected:
        raise AssertionError(
            f"{step}: 期望 http/code={expected}，实际 http={result.status} "
            f"code={body.get('code')} msg={body.get('msg')}"
        )


def _downloader_add_payload(
    ctx: Dict[str, Any],
    nickname: str,
    downloader_type: int,
    port: int,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "host": host or ctx.get("stub_host") or "w4-stub",
        "nickname": nickname,
        "username": STUB_USERNAME,
        "password": STUB_PASSWORD,
        "is_search": False,
        "downloader_type": downloader_type,
        "enabled": True,
        "port": port,
        "is_ssl": False,
    }


def _enabled_downloader_count(ctx: Dict[str, Any], token: str) -> int:
    """当前启用下载器数（getList 默认只返回 enabled=true 行）。"""
    listed = http_request(
        ctx["base_url"], "GET", "/api/v1/downloader/getList", token=token
    )
    data = listed.body.get("data") if isinstance(listed.body, dict) else None
    return len(data) if isinstance(data, list) else 0


def _downloader_id_by_nickname(
    ctx: Dict[str, Any], token: str, nickname: str
) -> Optional[str]:
    """经简单列表（data 直接是 [{downloader_id, nickname}]）按昵称反查 id。"""
    listed = http_request(
        ctx["base_url"], "GET", "/api/v1/downloader/getList", token=token
    )
    data = listed.body.get("data") if isinstance(listed.body, dict) else None
    items = data if isinstance(data, list) else []
    for item in items:
        if isinstance(item, dict) and item.get("nickname") == nickname:
            for key in ("downloader_id", "id", "downloaderId"):
                if item.get(key):
                    return str(item[key])
    return None


def _delete_downloader_by_nickname(
    ctx: Dict[str, Any], token: str, nickname: str
) -> Optional[Dict[str, Any]]:
    downloader_id = _downloader_id_by_nickname(ctx, token, nickname)
    if not downloader_id:
        return None
    result = http_request(
        ctx["base_url"],
        "DELETE",
        f"/api/v1/downloader/delete/{downloader_id}",
        token=token,
    )
    return envelope(result)


def _ensure_downloader(
    ctx: Dict[str, Any],
    token: str,
    nickname: str,
    downloader_type: int,
    port: int,
    reuse_existing: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """幂等夹具：确保存在指向 stub 的下载器，返回 (id, add 信封)。

    reuse_existing=True（C06/C10 夹具）：存在即复用，不删不加——下载器缓存
    按 host:port 去重且 delete 不清缓存，删旧加新会换 uuid 并被去重挡在
    缓存外（同步 0 行）；复用保持 (downloader_id, 缓存客户端) 与种子行集
    三者稳定（本地双实例实证）。
    reuse_existing=False（C05 自清理 CRUD）：按昵称预清理后新增。
    """
    existing = _downloader_id_by_nickname(ctx, token, nickname)
    if reuse_existing and existing:
        return existing, {"reused": True}
    if not reuse_existing:
        _delete_downloader_by_nickname(ctx, token, nickname)
    add = http_request(
        ctx["base_url"],
        "POST",
        "/api/v1/downloader/add",
        _downloader_add_payload(ctx, nickname, downloader_type, port),
        token=token,
    )
    _require_code(add, f"add_downloader({nickname})")
    downloader_id = _downloader_id_by_nickname(ctx, token, nickname)
    if not downloader_id:
        raise AssertionError(f"add_downloader({nickname}): getList 反查不到新下载器")
    return downloader_id, envelope(add)


def _torrent_rows(payload: Any) -> List[Dict[str, Any]]:
    """getList 的 data.list 行集合（统一 list/total/pageSize 信封）。"""
    if isinstance(payload, dict) and isinstance(payload.get("list"), list):
        return [r for r in payload["list"] if isinstance(r, dict)]
    return []


def _torrent_row_view(row: Dict[str, Any]) -> Dict[str, Any]:
    """单行可比视图：确定性字段精确值（getList 行为 camelCase 契约，实测键名）。

    排除项及理由：uuid 列（infoId/downloaderId）实例内生成；速度/peers 等
    实时列为时变值；addedDate/completedDate 虽源自 stub 固定 epoch，但渲染
    经实例时区（docker 组合 TZ=Asia/Shanghai、deb/rpm CI 容器 UTC）——时区
    是部署配置差异而非制品契约（计划 §13 环境差异走规范化，不进快照）。
    """
    view: Dict[str, Any] = {}
    for key in (
        "name",
        "status",
        "size",
        "savePath",
        "tags",
        "category",
        "ratio",
        "errorReason",
    ):
        if key in row:
            view[key] = row.get(key)
    return view


def _get_list_query(ctx: Dict[str, Any], token: str, query: str) -> Dict[str, Any]:
    result = http_request(
        ctx["base_url"], "GET", f"/api/v1/torrents/getList?{query}", token=token
    )
    data = result.body.get("data") if isinstance(result.body, dict) else None
    rows = _torrent_rows(data)
    return {
        **envelope(result),
        "total": data.get("total") if isinstance(data, dict) else None,
        "pageSize": data.get("pageSize") if isinstance(data, dict) else None,
        "rows": sorted(
            (_torrent_row_view(r) for r in rows), key=lambda v: str(v.get("name"))
        ),
    }


def scenario_c05_downloader_crud(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C05：下载器管理全生命周期（新增/测连/编辑/删除）——add 触发真实 stub 认证。"""
    token = _auth_token(ctx)
    if not token:
        return {"__no_token__": True}
    steps: Dict[str, Any] = {}

    downloader_id, add_envelope = _ensure_downloader(
        ctx, token, C05_NICKNAME, 0, int(ctx.get("c05_qb_port") or C05_QB_PORT_DEFAULT)
    )
    steps["add_downloader"] = add_envelope

    test_ok = http_request(
        ctx["base_url"], "POST", f"/api/v1/downloader/test/{downloader_id}", token=token
    )
    test_ok_data = data_of(test_ok)
    _require_code(test_ok, "test_connection")
    if not (isinstance(test_ok_data, dict) and test_ok_data.get("success") is True):
        raise AssertionError(
            f"test_connection: stub 在线但 success!=True: {test_ok_data}"
        )
    # delay 为实测毫秒（时变），只保留 success 布尔语义
    steps["test_connection"] = {
        "success": test_ok_data.get("success"),
        "message": test_ok_data.get("message"),
    }

    # 负向：不可达主机名（测连=ICMP/TCP 可达性探测；可达主机的关闭端口
    # ICMP 仍通 → success=True，本地实证）——add 落库成功但测连必失败
    dead_add = http_request(
        ctx["base_url"],
        "POST",
        "/api/v1/downloader/add",
        _downloader_add_payload(ctx, C05_NICKNAME_DEAD, 0, 18080, host=C05_DEAD_HOST),
        token=token,
    )
    steps["add_downloader_unreachable"] = envelope(dead_add)
    dead_id = _downloader_id_by_nickname(ctx, token, C05_NICKNAME_DEAD)
    if dead_id:
        test_dead = http_request(
            ctx["base_url"], "POST", f"/api/v1/downloader/test/{dead_id}", token=token
        )
        dead_data = data_of(test_dead)
        if not (isinstance(dead_data, dict) and dead_data.get("success") is False):
            raise AssertionError(
                f"test_connection_unreachable: 期望 success=False: {dead_data}"
            )
        steps["test_connection_unreachable"] = {"success": dead_data.get("success")}
        delete_dead = http_request(
            ctx["base_url"],
            "DELETE",
            f"/api/v1/downloader/delete/{dead_id}",
            token=token,
        )
        _require_code(delete_dead, "delete_downloader_unreachable")
        steps["delete_downloader_unreachable"] = envelope(delete_dead)

    renamed = f"{C05_NICKNAME}-renamed"
    # UpdateDownloader 语义：带非空 password/username 变更会强制校验原密码——
    # 纯改名更新必须省略这两个字段（传 None），否则 400"必须提供原密码"
    update_payload = _downloader_add_payload(
        ctx, renamed, 0, int(ctx.get("c05_qb_port") or C05_QB_PORT_DEFAULT)
    )
    update_payload.pop("username", None)
    update_payload.pop("password", None)
    update = http_request(
        ctx["base_url"],
        "POST",
        f"/api/v1/downloader/update/{downloader_id}",
        update_payload,
        token=token,
    )
    _require_code(update, "update_downloader")
    steps["update_downloader"] = envelope(update)
    if not _downloader_id_by_nickname(ctx, token, renamed):
        raise AssertionError("update_downloader: 更名后 getList 反查不到新昵称")

    detail = http_request(
        ctx["base_url"],
        "GET",
        f"/api/v1/downloader/detail/{downloader_id}",
        token=token,
    )
    detail_data = data_of(detail)
    detail_view: Dict[str, Any] = {"data_shape": shape(detail_data)}
    if isinstance(detail_data, dict):
        for key in ("nickname", "host", "downloader_type", "port", "enabled", "is_ssl"):
            if key in detail_data:
                detail_view[key] = detail_data.get(key)
    steps["detail_downloader"] = {**envelope(detail), **detail_view}

    delete = http_request(
        ctx["base_url"],
        "DELETE",
        f"/api/v1/downloader/delete/{downloader_id}",
        token=token,
    )
    _require_code(delete, "delete_downloader")
    steps["delete_downloader"] = envelope(delete)
    if _downloader_id_by_nickname(ctx, token, renamed):
        raise AssertionError("delete_downloader: 删除后 getList 仍能反查到")

    listed = http_request(
        ctx["base_url"], "GET", "/api/v1/downloader/getList", token=token
    )
    listed_names = sorted(
        str(i.get("nickname"))
        for i in (listed.body.get("data") if isinstance(listed.body, dict) else None)
        or []
        if isinstance(i, dict)
    )
    steps["list_after_delete"] = {
        **envelope(listed),
        "c05_names_remaining": [n for n in listed_names if n.startswith("w4-c05")],
    }
    return steps


def scenario_c06_torrent_queries(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C06：固定 stub 数据下的种子核心查询（同步/列表/分页/筛选/Tracker/单种子）。

    夹具下载器（w4-c06-qb/w4-c06-tr）场景结束保留：C10 验证重启后仍可见，
    C12 复用其行与缓存客户端。重跑幂等 = 昵称预清理 + downloader_id 过滤。
    """
    token = _auth_token(ctx)
    if not token:
        return {"__no_token__": True}
    steps: Dict[str, Any] = {}

    # 顺序容错：清掉 C05 中途失败可能遗留的下载器行（sync 按全部启用下载器
    # 计数，残留会改变 synced_count 语义）
    listed_pre = http_request(
        ctx["base_url"], "GET", "/api/v1/downloader/getList", token=token
    )
    for item in (
        listed_pre.body.get("data") if isinstance(listed_pre.body, dict) else None
    ) or []:
        if isinstance(item, dict) and str(item.get("nickname", "")).startswith(
            "w4-c05"
        ):
            _delete_downloader_by_nickname(ctx, token, str(item.get("nickname")))

    # POST /torrents/list 同步全部启用下载器（synced_count=下载器数）：
    # 先只加 qb → sync(1) 走 qB 查询链，再加 tr → sync(2) 覆盖 TR 链
    qb_id, _ = _ensure_downloader(
        ctx,
        token,
        C06_QB_NICKNAME,
        0,
        int(ctx.get("qb_port") or 18080),
        reuse_existing=True,
    )

    sync_qb = http_request(
        ctx["base_url"], "POST", "/api/v1/torrents/list", token=token
    )
    sync_qb_data = data_of(sync_qb)
    _require_code(sync_qb, "sync_qb")
    # sync 同步全部启用下载器：synced_count 必须等于 sync 前的启用数且零错误
    # （重跑时夹具下载器已存在=复用，首次=1、重跑=2，动态口径）
    enabled_before = _enabled_downloader_count(ctx, token)
    if not (
        isinstance(sync_qb_data, dict)
        and sync_qb_data.get("synced_count") == enabled_before
        and sync_qb_data.get("errors") == []
    ):
        raise AssertionError(
            f"sync_qb: synced_count({sync_qb_data}) != 启用下载器数({enabled_before})"
        )
    steps["sync_qb"] = {
        **envelope(sync_qb),
        "synced_count": (
            sync_qb_data.get("synced_count") if isinstance(sync_qb_data, dict) else None
        ),
        "total_count": (
            sync_qb_data.get("total_count") if isinstance(sync_qb_data, dict) else None
        ),
    }

    qb_list = _get_list_query(ctx, token, f"downloader_id={qb_id}&limit=100")
    if qb_list.get("total") != 3:
        raise AssertionError(
            f"sync_qb: 期望 3 个 qB 夹具种子，实际 total={qb_list.get('total')}"
        )
    steps["qb_torrents"] = qb_list

    steps["qb_pagination_p1"] = _get_list_query(
        ctx, token, f"downloader_id={qb_id}&skip=0&limit=1"
    )
    steps["qb_pagination_p2"] = _get_list_query(
        ctx, token, f"downloader_id={qb_id}&skip=1&limit=2"
    )

    seeding_status = next(
        (
            r.get("status")
            for r in qb_list["rows"]
            if r.get("name") == "w4-fixture-alpha"
        ),
        None,
    )
    if not seeding_status:
        raise AssertionError(
            "qb_torrents: 反查不到 w4-fixture-alpha 的状态（数据集漂移）"
        )
    steps["qb_filter_status"] = {
        "status": seeding_status,
        "result": _get_list_query(
            ctx, token, f"downloader_id={qb_id}&status={seeding_status}"
        ),
    }
    steps["qb_filter_name"] = _get_list_query(
        ctx, token, f"downloader_id={qb_id}&name_like=w4-fixture-alpha"
    )

    domains = http_request(
        ctx["base_url"], "GET", "/api/v1/torrents/tracker-domains", token=token
    )
    domains_data = domains.body.get("data") if isinstance(domains.body, dict) else None
    steps["tracker_domains"] = {
        **envelope(domains),
        "domains": (
            sorted(str(d) for d in domains_data)
            if isinstance(domains_data, list)
            else shape(domains_data)
        ),
    }

    qb_rows_raw = http_request(
        ctx["base_url"],
        "GET",
        f"/api/v1/torrents/getList?downloader_id={qb_id}&limit=100",
        token=token,
    )
    raw_payload = (
        qb_rows_raw.body.get("data") if isinstance(qb_rows_raw.body, dict) else None
    )
    raw_rows = _torrent_rows(raw_payload)
    first_row = next((r for r in raw_rows if r.get("name") == "w4-fixture-alpha"), None)
    if not first_row or not first_row.get("infoId"):
        raise AssertionError("qb_torrents: 反查不到 w4-fixture-alpha 的 infoId")
    single = http_request(
        ctx["base_url"],
        "GET",
        f"/api/v1/torrents/torrents/{first_row['infoId']}/{qb_id}/{C06_QB_NICKNAME}",
        token=token,
    )
    single_data = data_of(single)
    steps["qb_single_torrent"] = {
        **envelope(single),
        "row": (
            _torrent_row_view(single_data)
            if isinstance(single_data, dict)
            else shape(single_data)
        ),
    }

    tr_id, _ = _ensure_downloader(
        ctx,
        token,
        C06_TR_NICKNAME,
        1,
        int(ctx.get("tr_port") or 18081),
        reuse_existing=True,
    )
    sync_tr = http_request(
        ctx["base_url"], "POST", "/api/v1/torrents/list", token=token
    )
    sync_tr_data = data_of(sync_tr)
    _require_code(sync_tr, "sync_tr")
    enabled_after_tr = _enabled_downloader_count(ctx, token)
    if not (
        isinstance(sync_tr_data, dict)
        and sync_tr_data.get("synced_count") == enabled_after_tr
        and sync_tr_data.get("errors") == []
    ):
        raise AssertionError(
            f"sync_tr: synced_count({sync_tr_data}) != 启用下载器数({enabled_after_tr})"
        )
    steps["sync_tr"] = {
        **envelope(sync_tr),
        "synced_count": (
            sync_tr_data.get("synced_count") if isinstance(sync_tr_data, dict) else None
        ),
        "total_count": (
            sync_tr_data.get("total_count") if isinstance(sync_tr_data, dict) else None
        ),
    }
    tr_list = _get_list_query(ctx, token, f"downloader_id={tr_id}&limit=100")
    if tr_list.get("total") != 2:
        raise AssertionError(
            f"sync_tr: 期望 2 个 TR 夹具种子，实际 total={tr_list.get('total')}"
        )
    steps["tr_torrents"] = tr_list

    return steps


def scenario_c10_restart_persistence(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C10：迁移与重启（API 视角）。重启由编排层完成（deb/rpm systemctl /
    docker compose restart），本场景只做重启后断言：契约密码可登录（C04 写
    持久化）、C06 下载器与种子行可见（DB 持久化）、构建身份不变。

    本场景语义断言全部 fail-closed：三制品"一致地丢数据"必须显式失败，
    不能靠快照相等蒙混过关（计划 §12.2 不可豁免项：数据丢失/secret 重置）。
    """
    steps: Dict[str, Any] = {}

    login = _login(ctx, INITIAL_USERNAME, CONTRACT_PASSWORD)
    body = login.body if isinstance(login.body, dict) else {}
    if str(body.get("code")) != "200":
        raise AssertionError(
            f"restart_persistence: 契约密码登录失败（密码未持久化或重启重置）: "
            f"http={login.status} code={body.get('code')} msg={body.get('msg')}"
        )
    token = (data_of(login) or {}).get("access_token")
    if not token:
        raise AssertionError("restart_persistence: 登录成功但无 access_token")
    steps["login_contract_password"] = envelope(login)

    live = http_request(ctx["base_url"], "GET", "/health/live")

    def identity_view(data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {"__missing__": True}
        build = data.get("build") if isinstance(data.get("build"), dict) else {}
        out = {name: data.get(name) for name in ("status", "version") if name in data}
        for field in IDENTITY_FIELDS:
            if field in build:
                out[f"build.{field}"] = build[field]
        return out

    steps["identity_after_restart"] = {
        **envelope(live),
        "identity": identity_view(data_of(live)),
    }

    listed = http_request(
        ctx["base_url"], "GET", "/api/v1/downloader/getList", token=token
    )
    names = sorted(
        str(i.get("nickname"))
        for i in (listed.body.get("data") if isinstance(listed.body, dict) else None)
        or []
        if isinstance(i, dict)
    )
    c06_names = [n for n in names if n.startswith("w4-c06")]
    if len(c06_names) != 2:
        raise AssertionError(
            f"restart_persistence: C06 下载器未全部持久化: {c06_names}"
        )
    steps["downloaders_after_restart"] = {**envelope(listed), "c06_names": c06_names}

    for nickname, expected_total in ((C06_QB_NICKNAME, 3), (C06_TR_NICKNAME, 2)):
        view = _get_list_query(ctx, token, f"downloader_name_like={nickname}&limit=100")
        if view.get("total") != expected_total:
            raise AssertionError(
                f"restart_persistence: {nickname} 种子行数漂移 "
                f"（期望 {expected_total}，实际 {view.get('total')}）"
            )
        steps[f"torrents_after_restart_{nickname.split('-')[-1]}"] = view
    return steps


def scenario_c12_path_mapping(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C12：文件路径边界。路径映射 CRUD、冲突/结构拒绝语义、规范化路径文本
    与 test 端点的验证视图（fail-closed 语义；目录探测结果跨制品同为
    false/true 时可比——CI 三制品均为 Linux 容器，外部探测目录同为不存在）。
    """
    token = _auth_token(ctx)
    if not token:
        return {"__no_token__": True}
    downloader_id = _downloader_id_by_nickname(ctx, token, C06_QB_NICKNAME)
    if not downloader_id:
        raise AssertionError("path_mapping: C06 夹具下载器不存在（场景顺序被破坏）")
    steps: Dict[str, Any] = {}

    def _mapping_view(data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("mappings"), list):
            return {
                "mappings": sorted(
                    (
                        json.dumps(m, sort_keys=True)
                        for m in data["mappings"]
                        if isinstance(m, dict)
                    )
                ),
                "default_mapping": data.get("default_mapping"),
            }
        return shape(data)

    def _get_mapping() -> Any:
        result = http_request(
            ctx["base_url"],
            "GET",
            f"/api/v1/downloader/{downloader_id}/path-mapping",
            token=token,
        )
        return {**envelope(result), "config": _mapping_view(data_of(result))}

    steps["get_initial"] = _get_mapping()

    add = http_request(
        ctx["base_url"],
        "POST",
        "/api/v1/downloader/path-mapping/add",
        {
            "downloader_id": downloader_id,
            "name": "w4map",
            "internal": "/downloads/w4-complete",
            "external": "/mnt/w4-complete",
            "description": "w4 fixture mapping",
            "mapping_type": "local",
        },
        token=token,
    )
    _require_code(add, "path_mapping_add")
    steps["add_valid"] = envelope(add)
    steps["get_after_add"] = _get_mapping()

    conflict = http_request(
        ctx["base_url"],
        "POST",
        "/api/v1/downloader/path-mapping/add",
        {
            "downloader_id": downloader_id,
            "name": "w4map2",
            "internal": "/downloads/w4-complete",
            "external": "/mnt/w4-other",
            "mapping_type": "local",
        },
        token=token,
    )
    steps["add_conflict_internal"] = envelope(conflict)

    test = http_request(
        ctx["base_url"],
        "POST",
        f"/api/v1/downloader/{downloader_id}/path-mapping/test",
        {
            "path_mapping": {
                "mappings": [
                    {
                        "name": "w4map",
                        "internal": "/downloads/w4-complete",
                        "external": "/mnt/w4-complete",
                        "description": "w4 fixture mapping",
                        "mapping_type": "local",
                    }
                ]
            }
        },
        token=token,
    )
    test_data = data_of(test)
    validation = (
        test_data.get("backend_validation") if isinstance(test_data, dict) else None
    )
    steps["test_mapping"] = {
        **envelope(test),
        "valid": test_data.get("valid") if isinstance(test_data, dict) else None,
        "backend_validation": (
            validation if isinstance(validation, dict) else shape(test_data)
        ),
    }

    # 清理全部夹具映射（重复 internal 的 add 实测也 200 落库，须一并清）
    steps["remove"] = {}
    for mapping_name in ("w4map", "w4map2"):
        remove = http_request(
            ctx["base_url"],
            "POST",
            "/api/v1/downloader/path-mapping/remove",
            {"downloader_id": downloader_id, "name": mapping_name},
            token=token,
        )
        _require_code(remove, f"path_mapping_remove({mapping_name})")
        steps["remove"][mapping_name] = envelope(remove)
    steps["get_after_remove"] = _get_mapping()
    remaining = steps["get_after_remove"]["config"]
    if isinstance(remaining, dict) and remaining.get("mappings"):
        raise AssertionError("path_mapping: 清理后仍残留夹具映射")
    return steps


def scenario_c11_spa(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C11：SPA 静态服务契约（index 可达 + 资源引用清单 + 路由 fallback 行为）。

    SPA 交付位置按部署形态不同：deb/rpm 二进制内嵌前端（backend 直出）；
    docker 部署由独立 frontend nginx 容器提供（backend 404 属预期）——CI 对
    docker 组合传 --spa-base-url 指向前端容器，比对同一唯一前端构建的
    index/资源 manifest（计划 C11 语义）。
    """
    import re as _re

    spa_base = ctx.get("spa_base_url") or ctx["base_url"]
    index = http_request_raw(spa_base, "GET", "/")
    assets: List[str] = []
    if isinstance(index.body, str):
        for pattern in (r'src="([^"]+\.js[^"]*)"', r'href="([^"]+\.css[^"]*)"'):
            assets.extend(sorted(set(_re.findall(pattern, index.body))))
        assets = sorted(set(assets))
    fallback = http_request_raw(spa_base, "GET", "/w4-fake-route-should-fallback")

    def _view(resp) -> Dict[str, Any]:
        body = resp.body if isinstance(resp.body, str) else ""
        return {
            "http": resp.status,
            "is_html": "<html" in body.lower() or "<!doctype html" in body.lower(),
            "bytes": len(resp.raw),
        }

    return {"index": {**_view(index), "assets": assets}, "fallback": _view(fallback)}


SCENARIOS = {
    "C01": ("health_identity", scenario_c01_health_identity),
    "C02": ("openapi_contract", scenario_c02_openapi_contract),
    "C03": ("auth_lifecycle", scenario_c03_auth_lifecycle),
    "C04": ("user_settings", scenario_c04_user_settings),
    "C05": ("downloader_crud", scenario_c05_downloader_crud),
    "C06": ("torrent_queries", scenario_c06_torrent_queries),
    "C07": ("query_templates", scenario_c07_query_templates),
    "C08": ("cron_tasks", scenario_c08_cron_tasks),
    "C09": ("notifications_audit", scenario_c09_notifications_audit),
    "C10": ("restart_persistence", scenario_c10_restart_persistence),
    "C11": ("spa", scenario_c11_spa),
    "C12": ("path_mapping", scenario_c12_path_mapping),
}

SCENARIO_SETS = {
    "A": ("C01", "C02", "C03", "C04"),
    "B1": ("C07", "C08", "C09", "C11"),
    "B2": ("C05", "C06", "C12"),
    # FULL = 重启前全部场景（C10 须在编排层重启后单独执行再 --merge-into）
    "FULL": (
        "C01",
        "C02",
        "C03",
        "C04",
        "C05",
        "C06",
        "C07",
        "C08",
        "C09",
        "C11",
        "C12",
    ),
}


def run_snapshot(
    base_url: str,
    scenario_ids: Tuple[str, ...],
    timeout: int = 10,
    spa_base_url: Optional[str] = None,
    stub_host: Optional[str] = None,
    qb_port: Optional[int] = None,
    tr_port: Optional[int] = None,
    c05_qb_port: Optional[int] = None,
) -> Dict[str, Any]:
    ctx = {
        "base_url": base_url,
        "timeout": timeout,
        "spa_base_url": spa_base_url,
        "stub_host": stub_host,
        "qb_port": qb_port,
        "tr_port": tr_port,
        "c05_qb_port": c05_qb_port,
    }
    scenarios: Dict[str, Any] = {}
    failures: List[str] = []
    for sid in scenario_ids:
        name, func = SCENARIOS[sid]
        try:
            scenarios[f"{sid}_{name}"] = func(ctx)
        except Exception as exc:  # noqa: BLE001 - 场景异常记录进快照而非中断整体
            failures.append(f"{sid}: {type(exc).__name__}: {exc}")
            scenarios[f"{sid}_{name}"] = {"__scenario_error__": str(exc)}
    return {
        "schema_version": SCHEMA_VERSION,
        "runner": "contract_runner.py",
        "base_url_shape": re.sub(r":\d+", ":{port}", base_url),
        "scenarios": scenarios,
        "scenario_failures": failures,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scenario-set", default="A", choices=sorted(SCENARIO_SETS))
    parser.add_argument(
        "--scenarios", default=None, help="逗号分隔场景 ID（覆盖 scenario-set）"
    )
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument(
        "--spa-base-url",
        default=None,
        help="C11 SPA 交付地址（docker 部署指向前端容器；默认 base_url）",
    )
    parser.add_argument(
        "--downloader-stub-host",
        default="w4-stub",
        help="C05/C06 受控下载器 stub 主机（容器网络名；本机演练用 127.0.0.1）",
    )
    parser.add_argument("--qb-port", type=int, default=18080, help="qB stub 端口")
    parser.add_argument(
        "--tr-port", type=int, default=18081, help="Transmission stub 端口"
    )
    parser.add_argument(
        "--c05-qb-port",
        type=int,
        default=C05_QB_PORT_DEFAULT,
        help="C05 专用 qB stub 端口（避开缓存 host:port 去重）",
    )
    parser.add_argument(
        "--merge-into",
        default=None,
        help="把本次结果并入既有快照文件（C10 重启后二次调用用），文件须已存在",
    )
    args = parser.parse_args(argv)

    ids = (
        tuple(args.scenarios.split(","))
        if args.scenarios
        else SCENARIO_SETS[args.scenario_set]
    )
    unknown = [i for i in ids if i not in SCENARIOS]
    if unknown:
        parser.error(f"未知场景: {unknown}（可用: {sorted(SCENARIOS)}）")

    snapshot = run_snapshot(
        args.base_url,
        ids,
        timeout=args.timeout,
        spa_base_url=args.spa_base_url,
        stub_host=args.downloader_stub_host,
        qb_port=args.qb_port,
        tr_port=args.tr_port,
        c05_qb_port=args.c05_qb_port,
    )

    output_path = args.output
    if args.merge_into:
        with open(args.merge_into, "r", encoding="utf-8") as f:
            merged = json.load(f)
        merged["scenarios"].update(snapshot["scenarios"])
        # 合并去重（同一场景重复执行只保留最新记录）
        merged["scenario_failures"] = sorted(
            set(merged.get("scenario_failures", []))
            | set(snapshot["scenario_failures"])
        )
        snapshot = merged
        output_path = args.merge_into

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    verdict = "FAIL" if snapshot["scenario_failures"] else "OK"
    target = args.merge_into or args.output
    print(f"snapshot: {target} scenarios={list(ids)} verdict={verdict}")
    return 1 if snapshot["scenario_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
