"""MCP 工具：torrent_advanced_search（feature mcp-service-capabilities W3-①）。

复用 ``AdvancedSearchService.search_torrents``（同步 Session + dict 请求，
G4：与 HTTP 同一 service 与同一条件校验；MCP 侧仅追加隐私巡检与 DTO 映射）。

输出映射（契约 allowlist）：camelCase TorrentInfoVO → 脱敏 DTO——tracker 列表
经 ``redact_tracker_url`` 收敛为去重域名集合；保存路径经 ``redact_path_to_display``
仅留末段；hash/save_path 原值/error_reason/announce 消息等敏感字段不进入 DTO
（构造面省略 + finalize allowlist 双保险）。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

from app.auth.principal import AuthenticatedPrincipal
from app.mcp.contracts import CapabilitySpec, PAGE_SIZE_DEFAULT
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.redaction import redact_path_to_display, redact_tracker_url
from app.mcp.runtime import McpRuntime
from app.mcp.catalog import ToolCallContext
from app.services.advanced_search import AdvancedSearchService

logger = logging.getLogger(__name__)


def _to_search_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """camelCase VO dump → 契约 allowlist DTO（脱敏在映射层完成）。

    ``trackerInfo`` 元素是 TrackerInfoVO 的混合形态 dump（snake_case 键），
    双键兼容读取。
    """
    tracker_domains = set()
    for tracker in row.get("trackerInfo") or []:
        entry = tracker or {}
        url = entry.get("tracker_url") or entry.get("trackerUrl")
        domain = redact_tracker_url(url)
        if domain:
            tracker_domains.add(domain)
    added = row.get("addedDate")
    return {
        "info_id": row.get("infoId"),
        "name": row.get("name"),
        "size_bytes": row.get("size"),
        "progress": row.get("progress"),
        "state": row.get("state") or row.get("status"),
        "category": row.get("category"),
        "tags": row.get("tags"),
        "added_at": added.isoformat() if isinstance(added, datetime) else added,
        "tracker_domains": sorted(tracker_domains),
        "path_display": redact_path_to_display(row.get("savePath") or ""),
        "download_speed": row.get("downloadSpeed"),
        "upload_speed": row.get("uploadSpeed"),
    }


def _map_search_service_error(result: Dict[str, Any]) -> McpToolError:
    """service 失败字典 → 稳定错误（msg 含上游文本，不透传）。"""
    code = str(result.get("code", ""))
    if code == "422":
        return McpToolError(McpErrorCode.INVALID_ARGUMENT)
    return McpToolError(McpErrorCode.INTERNAL_ERROR)


async def handle_advanced_search(
    spec: CapabilitySpec,
    principal: AuthenticatedPrincipal,
    arguments: Dict[str, Any],
    runtime: McpRuntime,
    call_context: ToolCallContext,
) -> Dict[str, Any]:
    """torrent_advanced_search 处理器（只读；无 confirm/幂等）。"""
    from pydantic import ValidationError

    from app.mcp.tools.conditions import build_search_request
    from app.services.advanced_search import EnhancedAdvancedSearchRequest

    page = arguments.get("page", 1)
    page_size = arguments.get("page_size", PAGE_SIZE_DEFAULT)
    request_payload = build_search_request(arguments["conditions"], page, page_size)
    try:
        request = EnhancedAdvancedSearchRequest.model_validate(request_payload)
    except ValidationError as exc:
        logger.warning("MCP 高级搜索请求未过共用契约校验: %s", exc.error_count())
        raise McpToolError(McpErrorCode.INVALID_ARGUMENT) from exc
    user_id = str(principal.user_id) if principal.user_id is not None else principal.username

    def _run() -> Dict[str, Any]:
        db = runtime.sync_session()
        try:
            return AdvancedSearchService(db).search_torrents(request, user_id)
        finally:
            db.close()

    result = await asyncio.to_thread(_run)
    if result.get("status") != "success":
        logger.warning(
            "MCP torrent_advanced_search service 拒绝（结果码不外发上游 msg）: code=%s",
            result.get("code"),
        )
        raise _map_search_service_error(result)

    rows: List[Dict[str, Any]] = result.get("data") or []
    return {
        "total": result.get("total", 0),
        "page": result.get("page", page),
        "page_size": result.get("limit", page_size),
        "items": [_to_search_item(row) for row in rows],
    }


# ==============================================================================
# torrent_mark_pending_delete（W3-②，写入下载器 + DB；G7 partial 语义）
# ==============================================================================


def _tags_contain(tags: Any, tag: str) -> bool:
    """逗号分隔标签串的包含判定（与 service._add_tag_to_string 同分隔符口径）。"""
    if not isinstance(tags, str) or not tags:
        return False
    return tag in [part.strip() for part in tags.split(",")]


def _map_level4_item_error(result: Dict[str, Any]) -> str:
    """单项失败 → 稳定错误码（上游 error 文本不透传）。"""
    error = str(result.get("error", ""))
    operation = str(result.get("operation", ""))
    if "不存在" in error or "not found" in error.lower():
        return McpErrorCode.INVALID_ARGUMENT.value
    if operation in ("get_adapter", "add_tag") or "适配器" in error or "下载器" in error:
        return McpErrorCode.DOWNSTREAM_FAILURE.value
    return McpErrorCode.INTERNAL_ERROR.value


async def handle_mark_pending_delete(
    spec: CapabilitySpec,
    principal: AuthenticatedPrincipal,
    arguments: Dict[str, Any],
    runtime: McpRuntime,
    call_context: ToolCallContext,
) -> Dict[str, Any]:
    """torrent_mark_pending_delete 处理器。

    逐项调用共用 ``TorrentDeletionByLevelService.delete_by_level(..., 4)``（G4：
    与 HTTP 同一 service 与同一标签语义），逐项结果保留 partial——下载器成功
    但 DB 更新失败时 ``db_ok=False`` 不折叠为成功（§4.7）。已含 pending_delete
    标签的种子按 already_marked 计数返回，不再触发下载器调用（幂等）。
    """
    from app.mcp.tools.common import log_tool_audit
    from app.mcp.tools.idempotency import cache_get, cache_put, digest_idempotency_key
    from app.services.torrent_deletion_by_level import TorrentDeletionByLevelService
    from app.torrents.models import TorrentInfo

    LEVEL4_TAG = TorrentDeletionByLevelService.LEVEL4_TAG

    info_ids: List[str] = list(arguments["info_ids"])
    idempotency_key = arguments["idempotency_key"]
    operator = principal.username

    store = runtime.require_store()  # store 未初始化 = RUNTIME_NOT_READY（不自建连接）

    cache_key = (spec.tool_name, principal.user_id, idempotency_key)
    cached = cache_get(cache_key)
    if cached is not None:
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "idempotency_key": digest_idempotency_key(idempotency_key),
                "replay": True,
            },
            result="success",
        )
        return dict(cached)

    db = runtime.sync_session()
    items: List[Dict[str, Any]] = []
    audit_adb = None
    try:
        service = TorrentDeletionByLevelService(db, store=store, audit_context=call_context.audit)
        audit_service = None
        try:
            from app.services.audit_service import get_audit_service

            # 逐项 DELETE_L4 审计走同一异步会话（服务每次写入自行提交），
            # 会话保持到循环结束，随本 finally 统一关闭
            audit_adb = runtime.async_session()
            audit_service = await get_audit_service(audit_adb)
        except Exception as exc:
            logger.warning("MCP 等级4标记获取审计服务失败（不阻断标记）: %s", exc)
            if audit_adb is not None:
                await audit_adb.close()
                audit_adb = None

        for info_id in info_ids:
            torrent = db.query(TorrentInfo).filter(TorrentInfo.info_id == info_id, TorrentInfo.dr == 0).first()
            if torrent is None:
                items.append(
                    {
                        "info_id": info_id,
                        "downloader_ok": False,
                        "db_ok": False,
                        "already_marked": False,
                        "error_code": McpErrorCode.INVALID_ARGUMENT.value,
                    }
                )
                continue
            if _tags_contain(torrent.tags, LEVEL4_TAG):
                # 已标记：幂等直报（不再触发下载器调用），计为成功
                items.append(
                    {
                        "info_id": info_id,
                        "downloader_ok": True,
                        "db_ok": True,
                        "already_marked": True,
                        "error_code": None,
                    }
                )
                continue
            result = await service.delete_by_level(info_id, 4, operator=operator, audit_service=audit_service)
            if result.get("success"):
                items.append(
                    {
                        "info_id": info_id,
                        "downloader_ok": True,
                        "db_ok": bool(result.get("db_update_success", False)),
                        "already_marked": False,
                        "error_code": None,
                    }
                )
            else:
                items.append(
                    {
                        "info_id": info_id,
                        "downloader_ok": False,
                        "db_ok": False,
                        "already_marked": False,
                        "error_code": _map_level4_item_error(result),
                    }
                )
    finally:
        db.close()
        if audit_adb is not None:
            await audit_adb.close()

    downloader_ok_count = sum(1 for item in items if item["downloader_ok"])
    db_ok_count = sum(1 for item in items if item["db_ok"])
    already_marked_count = sum(1 for item in items if item["already_marked"])
    if downloader_ok_count == 0:
        overall = "failed"
    elif db_ok_count < downloader_ok_count:
        overall = "partial"  # 下载器成功但 DB 失败：partial 不折叠（§4.7）
    else:
        overall = "success"

    payload = {
        "result": overall,
        "downloader_success_count": downloader_ok_count,
        "db_success_count": db_ok_count,
        "already_marked_count": already_marked_count,
        "items": items,
    }
    cache_put(cache_key, payload)
    await log_tool_audit(
        runtime,
        call_context,
        principal,
        detail={
            "tool": spec.tool_name,
            "item_count": len(info_ids),
            "result": overall,
            "idempotency_key": digest_idempotency_key(idempotency_key),
        },
        result="success" if overall != "failed" else "partial" if overall == "partial" else "failed",
    )
    return payload
