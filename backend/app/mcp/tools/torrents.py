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
