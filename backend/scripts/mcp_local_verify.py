"""MCP 本地端到端验证脚本（feature mcp-service-capabilities-2026-08-28 实测沉淀）。

背景：2026-09-17 对 dev1.0.7 合并后的 MCP 线做过两轮本地全能力实测
（六工具正路径 + 守卫链负例 + 幂等重放 + kill switch），本脚本把该
验证矩阵固化为可复用工具，供后续回归与联调使用。

覆盖用例（对运行中的后端执行，不建库、不起服务）：

  A. initialize 握手 + tools/list 能力裁剪（与 --expect-tools 比对）
  B. 认证负例：无效 token / 无 token → 稳定拒绝文案
  C. 守卫链负例：confirm=false / 缺幂等键 / 伪造主体字段 / 未知字段 /
     Cron allowlist 外任务码
  D. 正路径：dashboard_get、torrent_advanced_search、模板创建 + HTTP
     交叉验证 + 同幂等键重放、等级4标记与添加种子的 fail-closed 稳定码
  E. 清理：删除本脚本创建的测试模板（--keep 跳过）

前置条件：后端已运行且 MCP 配置已开启（GET /api/v1/mcp/settings 的
effectiveEnabled=true）；登录账号具备控制面权限。测试模板以
mcp-local-verify- 前缀命名便于辨认。

用法：

  python mcp_local_verify.py --username admin --password <pwd> \
      [--base http://127.0.0.1:5001] [--enable-all-caps]

  # --enable-all-caps：先经控制面 PUT 开启全部六能力（CAS 重试），
  # 验证结束后还原为全关；不传则假定调用方已自行配置。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ALL_CAPABILITIES = (
    "torrent.advanced_search",
    "torrent.mark_pending_delete",
    "torrent.add",
    "search_template.create",
    "dashboard.read",
    "cron.trigger",
)
ALL_TOOLS = (
    "advanced_search_template_create",
    "cron_task_trigger",
    "dashboard_get",
    "torrent_add_file",
    "torrent_advanced_search",
    "torrent_mark_pending_delete",
)
TEMPLATE_PREFIX = "mcp-local-verify-"

VALID_TEMPLATE_CONDITIONS = {
    "source": "advanced",
    "condition_groups": [
        {"logic": "AND", "conditions": [{"field": "name", "operator": "contains", "value": TEMPLATE_PREFIX}]}
    ],
}

RESULTS: List[Tuple[str, bool, str]] = []


def record(case: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((case, ok, detail))
    print(f"{'[PASS]' if ok else '[FAIL]'} {case}: {detail[:240]}")


def http_api(base: str, token: str, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
    req = urllib.request.Request(
        f"{base}/api/v1{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def login(base: str, username: str, password: str) -> str:
    req = urllib.request.Request(
        f"{base}/api/v1/auth/login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": username, "password": password}).encode(),
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    data = body.get("data") or []
    if body.get("code") != "200" or not data:
        raise SystemExit(f"登录失败: {body.get('msg')}")
    return data[0]["access_token"]


def enable_all_caps(base: str, token: str) -> bool:
    """经控制面开启全部六能力（读到最新 revision 后 CAS 提交）。返回是否执行。"""
    status, body = http_api(base, token, "GET", "/mcp/settings")
    if status != 200:
        raise SystemExit(f"读取 MCP 设置失败: http={status}")
    settings = (body.get("data") or {}).get("settings") or {}
    if settings.get("effectiveEnabled") and all(settings.get("capabilities", {}).get(c) for c in ALL_CAPABILITIES):
        return False
    rev = settings.get("revision", 0)
    put = {
        "enabled": True,
        "capabilities": {c: True for c in ALL_CAPABILITIES},
        "expectedRevision": rev,
    }
    status, body = http_api(base, token, "PUT", "/mcp/settings", put)
    if status != 200:
        raise SystemExit(f"开启 MCP 能力失败: http={status} body={str(body)[:200]}")
    return True


def revert_caps(base: str, token: str) -> None:
    status, body = http_api(base, token, "GET", "/mcp/settings")
    settings = (body.get("data") or {}).get("settings") or {}
    http_api(
        base,
        token,
        "PUT",
        "/mcp/settings",
        {
            "enabled": False,
            "capabilities": {c: False for c in ALL_CAPABILITIES},
            "expectedRevision": settings.get("revision", 0),
        },
    )


async def mcp_call(mcp_url: str, token: str, tool: str, args: Dict[str, Any]) -> Tuple[bool, Any]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(tool, args)
            payload: Any = res.structuredContent
            if payload is None and res.content:
                try:
                    payload = json.loads(res.content[0].text)
                except Exception:
                    payload = res.content[0].text
            return res.isError, payload


async def mcp_list_tools(mcp_url: str, token: str) -> List[str]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {token}"}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return sorted(t.name for t in tools.tools)


async def expect_auth_reject(mcp_url: str, case: str, token: str) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.list_tools()
        record(case, False, "意外放行")
    except BaseException as exc:  # noqa: BLE001 - 负例需兜住 ExceptionGroup
        def _leaf(e: Any, depth: int = 0) -> List[str]:
            if depth > 5:
                return []
            if hasattr(e, "exceptions"):
                out: List[str] = []
                for sub in e.exceptions:
                    out.extend(_leaf(sub, depth + 1))
                return out
            return [f"{type(e).__name__}: {e}"]

        record(case, True, "; ".join(_leaf(exc))[:200])


def err_code(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        return (payload.get("error") or {}).get("code")
    return None


def minimal_torrent_b64() -> str:
    import bencodepy

    torrent = {
        b"announce": b"http://127.0.0.1:1/announce",
        b"info": {b"name": b"mcp-local-verify-probe", b"piece length": 16384, b"pieces": b"\x00" * 20, b"length": 1},
    }
    return base64.b64encode(bencodepy.encode(torrent)).decode()


async def main() -> int:
    parser = argparse.ArgumentParser(description="BtDeck MCP 本地端到端验证")
    parser.add_argument("--base", default="http://127.0.0.1:5001", help="后端根地址")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--enable-all-caps", action="store_true", help="先开启全部六能力，结束后还原全关")
    parser.add_argument("--keep", action="store_true", help="保留创建的测试模板")
    args = parser.parse_args()

    mcp_url = f"{args.base}/mcp/"
    token = login(args.base, args.username, args.password)
    opened = enable_all_caps(args.base, token) if args.enable_all_caps else False
    created_template_ids: List[str] = []
    try:
        # A. tools/list 全量
        names = await mcp_list_tools(mcp_url, token)
        record("A1 tools/list 能力裁剪（六工具全量）", names == sorted(ALL_TOOLS), f"{len(names)} 个: {names}")

        # B. 认证负例
        await expect_auth_reject(mcp_url, "B1 无效 token 被拒", "definitely-invalid-token")
        await expect_auth_reject(mcp_url, "B2 无 token 被拒", "")

        # C. 守卫链负例
        guard_cases = (
            ("C1 confirm=false → CONFIRM_REQUIRED", "advanced_search_template_create",
             {"name": "x", "conditions": VALID_TEMPLATE_CONDITIONS, "confirm": False, "idempotency_key": "lv-g1"},
             "CONFIRM_REQUIRED"),
            ("C2 缺幂等键 → 参数层稳定拒绝", "advanced_search_template_create",
             {"name": "x", "conditions": VALID_TEMPLATE_CONDITIONS, "confirm": True},
             "INVALID_ARGUMENT"),
            ("C3 伪造 user_id → FORBIDDEN_ARGUMENT", "torrent_mark_pending_delete",
             {"info_ids": ["x"], "confirm": True, "idempotency_key": "lv-g2", "user_id": "1"},
             "FORBIDDEN_ARGUMENT"),
            ("C4 未知字段 → INVALID_ARGUMENT", "torrent_mark_pending_delete",
             {"info_ids": ["x"], "confirm": True, "idempotency_key": "lv-g3", "unknown_field": 1},
             "INVALID_ARGUMENT"),
            ("C5 allowlist 外任务码 → CRON_TASK_NOT_ALLOWED", "cron_task_trigger",
             {"task_code": "no_such_task_code", "confirm": True, "idempotency_key": "lv-g4"},
             "CRON_TASK_NOT_ALLOWED"),
        )
        for case, tool, tool_args, want in guard_cases:
            err, payload = await mcp_call(mcp_url, token, tool, tool_args)
            record(case, err and err_code(payload) == want, f"code={err_code(payload)}")

        # D1 只读工具
        err, payload = await mcp_call(mcp_url, token, "dashboard_get", {})
        record("D1 dashboard_get", not err and isinstance(payload, dict) and "totals" in payload, str(payload)[:120])

        err, payload = await mcp_call(
            mcp_url, token, "torrent_advanced_search",
            {"conditions": {"condition_groups": []}, "page": 1, "page_size": 3},
        )
        record("D2 torrent_advanced_search", not err and isinstance(payload, dict) and "total" in payload, str(payload)[:120])

        # D3 模板创建 + HTTP 交叉验证 + 幂等重放
        tpl_args = {
            "name": f"{TEMPLATE_PREFIX}{int(__import__('time').time())}",
            "conditions": VALID_TEMPLATE_CONDITIONS,
            "is_public": False,
            "confirm": True,
            "idempotency_key": "lv-tpl-001",
        }
        err, payload = await mcp_call(mcp_url, token, "advanced_search_template_create", tpl_args)
        tpl_id = payload.get("template_id") if isinstance(payload, dict) else None
        if tpl_id:
            created_template_ids.append(tpl_id)
        record("D3a 模板创建（合法模板形态）", not err and tpl_id is not None, str(payload)[:160])

        status, body = http_api(args.base, token, "GET", "/advanced-search/search-templates")
        items = body.get("data") or [] if isinstance(body, dict) else []
        if isinstance(items, dict):
            items = items.get("list") or items.get("items") or []
        found = any(t.get("id") == tpl_id or t.get("template_id") == tpl_id for t in items)
        record("D3b HTTP 交叉验证模板入库", found, f"http={status}")

        err, replay = await mcp_call(mcp_url, token, "advanced_search_template_create", tpl_args)
        status, body = http_api(args.base, token, "GET", "/advanced-search/search-templates")
        items2 = body.get("data") or [] if isinstance(body, dict) else []
        if isinstance(items2, dict):
            items2 = items2.get("list") or items2.get("items") or []
        cnt = sum(1 for t in items2 if t.get("name") == tpl_args["name"])
        record("D3c 同幂等键重放=首次结果且不重复建",
               isinstance(replay, dict) and replay.get("template_id") == tpl_id and cnt == 1,
               f"重放同ID={replay.get('template_id') == tpl_id if isinstance(replay, dict) else '?'} 同名数量={cnt}")

        # D4 fail-closed 稳定码（真实原因仅入日志）
        err, payload = await mcp_call(
            mcp_url, token, "torrent_mark_pending_delete",
            {"info_ids": ["00000000-0000-0000-0000-000000000000"], "confirm": True, "idempotency_key": "lv-mpd-001"},
        )
        record("D4 mark_pending_delete 不存在种子 → 逐项载荷",
               not err and isinstance(payload, dict) and "items" in payload, str(payload)[:160])

        err, payload = await mcp_call(
            mcp_url, token, "torrent_add_file",
            {"torrent_file_b64": minimal_torrent_b64(),
             "downloader_id": "00000000-0000-0000-0000-000000000000",
             "confirm": True, "idempotency_key": "lv-add-001"},
        )
        record("D5 torrent_add_file 不存在下载器 → 稳定码不外发细节",
               err and err_code(payload) == "INVALID_ARGUMENT", f"code={err_code(payload)}")

    finally:
        if not args.keep:
            for tid in created_template_ids:
                http_api(args.base, token, "DELETE", f"/advanced-search/search-templates/{tid}")
        if opened:
            revert_caps(args.base, token)

    ok = sum(1 for _, o, _ in RESULTS if o)
    print(f"\n===== 汇总: {ok}/{len(RESULTS)} PASS =====")
    for case, o, _ in RESULTS:
        if not o:
            print(f"  FAIL -> {case}")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
