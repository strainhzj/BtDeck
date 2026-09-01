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

批次 A 场景（C01~C04；C05~C12 需 qB/TR stub，批次 B）：
  C01 健康与构建身份   live/ready 的身份字段精确值 + checks 名称集合
  C02 OpenAPI 契约     openapi.json 规范化摘要（paths×methods + schema 指纹）
  C03 初始化与认证     错误码/登录/刷新/登出/token 失效全链路
  C04 用户与设置       用户信息读 + 改密写 + 新旧密码重登验证（写持久化证明）

用法：
  python contract_runner.py --base-url http://127.0.0.1:5001 \
      --output snapshot.json [--scenario-set A] [--timeout 10]
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


def scenario_c11_spa(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """C11：SPA 静态服务契约（index 可达 + 资源引用清单 + 路由 fallback 行为）。"""
    import re as _re

    index = http_request_raw(ctx["base_url"], "GET", "/")
    assets: List[str] = []
    content_type = ""
    if isinstance(index.body, str):
        for pattern in (r'src="([^"]+\.js[^"]*)"', r'href="([^"]+\.css[^"]*)"'):
            assets.extend(sorted(set(_re.findall(pattern, index.body))))
        assets = sorted(set(assets))
    fallback = http_request_raw(
        ctx["base_url"], "GET", "/w4-fake-route-should-fallback"
    )

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
    "C07": ("query_templates", scenario_c07_query_templates),
    "C08": ("cron_tasks", scenario_c08_cron_tasks),
    "C09": ("notifications_audit", scenario_c09_notifications_audit),
    "C11": ("spa", scenario_c11_spa),
}

SCENARIO_SETS = {
    "A": ("C01", "C02", "C03", "C04"),
    "B1": ("C07", "C08", "C09", "C11"),
    "B": (),  # C05/C06/C10/C12（qB/TR stub+重启编排），批次 B2
}


def run_snapshot(
    base_url: str, scenario_ids: Tuple[str, ...], timeout: int = 10
) -> Dict[str, Any]:
    ctx = {"base_url": base_url, "timeout": timeout}
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
    args = parser.parse_args(argv)

    ids = (
        tuple(args.scenarios.split(","))
        if args.scenarios
        else SCENARIO_SETS[args.scenario_set]
    )
    unknown = [i for i in ids if i not in SCENARIOS]
    if unknown:
        parser.error(f"未知场景: {unknown}（可用: {sorted(SCENARIOS)}）")

    snapshot = run_snapshot(args.base_url, ids, timeout=args.timeout)
    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    verdict = "FAIL" if snapshot["scenario_failures"] else "OK"
    print(f"snapshot: {args.output} scenarios={list(ids)} verdict={verdict}")
    return 1 if snapshot["scenario_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
