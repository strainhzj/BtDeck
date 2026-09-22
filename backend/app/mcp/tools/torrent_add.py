"""MCP 工具：torrent_add_file（feature mcp-service-capabilities W3-③，高风险）。

复用协议无关 ``TorrentAddService``（G4：与 HTTP /torrent/add 同一 service，下载器
调度/超时治理沿既有路径；store 经 ``runtime.require_store()`` 注入，不自建客户端）。

输入面收敛（§4.7 首版口径）：

- 只接受 base64 编码的 ``.torrent`` 二进制内容；服务器本地路径、URL、磁力链接
  一律 ``SERVER_PATH_FORBIDDEN``（先于 base64 解码做形态判定）；
- 解码后默认 ≤10 MiB（环境变量 ``BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES`` 可调，
  永不超过契约硬上限 64 MiB）、bencode 可解析、info 字典存在且 info hash 可提取；
- 输出契约 allowlist：added/duplicate/info_id/name/downloader_id/downloader_nickname
  （仅昵称，连接信息永不输出）。

幂等：进程内共享 LRU（同键重放返回首次结果）+ MCP_TOOL_CALL 审计
（detail 只含工具名/下载器 ID/info hash/幂等键摘要，无文件内容）。
"""

import asyncio
import base64
import binascii
import hashlib
import logging
import os
import re
from typing import Any, Dict

import bencodepy

from app.auth.principal import AuthenticatedPrincipal
from app.mcp.catalog import ToolCallContext
from app.mcp.contracts import (
    TORRENT_UPLOAD_DEFAULT_MAX_BYTES,
    TORRENT_UPLOAD_HARD_MAX_BYTES,
    CapabilitySpec,
)
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.runtime import McpRuntime

logger = logging.getLogger(__name__)

# 默认上限的环境覆盖（字节；非法/非正值回落默认，始终钳制到硬上限以内）
_UPLOAD_MAX_ENV = "BTDECK_MCP_TORRENT_UPLOAD_MAX_BYTES"

# 裸输入形态判定：这些前缀不可能是合法 base64（含 ":"），按契约直接拒绝
_FORBIDDEN_RAW_PREFIXES = ("magnet:", "http://", "https://", "file://", "ftp://", "\\\\")
_WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:[\\/]")

# TorrentAddResult.code（str，对齐 HTTP body code）→ MCP 稳定错误码。
# 500/未知码 → INTERNAL_ERROR（固定文案；上游 msg 只进服务端日志，不外发）。
_ADD_RESULT_CODE_TO_ERROR = {
    "400": McpErrorCode.INVALID_ARGUMENT,
    "404": McpErrorCode.INVALID_ARGUMENT,
    "408": McpErrorCode.DOWNSTREAM_FAILURE,
    "503": McpErrorCode.DOWNSTREAM_FAILURE,
}


def _effective_upload_limit() -> int:
    """当前生效的单文件上限：环境覆盖（钳制）或契约默认值。"""
    raw = os.environ.get(_UPLOAD_MAX_ENV)
    if not raw:
        return TORRENT_UPLOAD_DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return TORRENT_UPLOAD_DEFAULT_MAX_BYTES
    if value <= 0:
        return TORRENT_UPLOAD_DEFAULT_MAX_BYTES
    return min(value, TORRENT_UPLOAD_HARD_MAX_BYTES)


def _looks_like_server_reference(raw: str) -> bool:
    """输入是否呈服务器路径/URL/磁力形态（用于 base64 解码失败的归类）。"""
    if _WINDOWS_DRIVE_RE.match(raw):
        return True
    return "/" in raw or "\\" in raw


def _decode_torrent_payload(torrent_file_b64: str) -> bytes:
    """base64 → 二进制：路径/URL/磁力 → SERVER_PATH_FORBIDDEN；坏 base64 → INVALID_ARGUMENT。

    空内容与超限在此一并拦截（超限优先于 bencode 解析，防超大恶意载荷进解析器）。
    """
    raw = torrent_file_b64.strip()
    lowered = raw.lower()
    if lowered.startswith(_FORBIDDEN_RAW_PREFIXES) or _WINDOWS_DRIVE_RE.match(raw):
        raise McpToolError(McpErrorCode.SERVER_PATH_FORBIDDEN)
    try:
        content = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        if _looks_like_server_reference(raw):
            raise McpToolError(McpErrorCode.SERVER_PATH_FORBIDDEN)
        raise McpToolError(McpErrorCode.INVALID_ARGUMENT)
    if not content:
        raise McpToolError(McpErrorCode.UPLOAD_INVALID_CONTENT)
    if len(content) > TORRENT_UPLOAD_HARD_MAX_BYTES or len(content) > _effective_upload_limit():
        raise McpToolError(McpErrorCode.UPLOAD_TOO_LARGE)
    return content


def _extract_info_digest(content: bytes) -> str:
    """bencode 校验 + info hash 提取；任何解析失败由调用方统一 UPLOAD_INVALID_CONTENT。"""
    torrent_data = bencodepy.decode(content)
    if not isinstance(torrent_data, dict):
        raise ValueError("bencode 顶层不是字典")
    info = torrent_data.get(b"info")
    if not isinstance(info, dict):
        raise ValueError("缺少 info 字典")
    digest = hashlib.sha1(bencodepy.encode(info)).hexdigest()
    if not digest:
        raise ValueError("info hash 为空")
    return digest


async def handle_torrent_add_file(
    spec: CapabilitySpec,
    principal: AuthenticatedPrincipal,
    arguments: Dict[str, Any],
    runtime: McpRuntime,
    call_context: ToolCallContext,
) -> Dict[str, Any]:
    """torrent_add_file 处理器（添加 .torrent 二进制内容到指定下载器）。"""
    from app.mcp.tools.common import log_tool_audit
    from app.mcp.tools.idempotency import cache_get, cache_put, digest_idempotency_key

    torrent_file_b64 = arguments["torrent_file_b64"]
    downloader_id = arguments["downloader_id"]
    idempotency_key = arguments["idempotency_key"]

    # ---------- 1. 内容校验（协议级拒绝，先于运行时状态） ----------
    try:
        content = _decode_torrent_payload(torrent_file_b64)
        # bencode 解析在工作线程执行（默认 10 MiB 上限内的纯 CPU 解析不占事件循环）；
        # 解析/结构失败统一 UPLOAD_INVALID_CONTENT（非 bencode、无 info、hash 为空）
        info_digest = await asyncio.to_thread(_extract_info_digest, content)
    except McpToolError as err:
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "error_code": err.code.value,
                "idempotency_key": digest_idempotency_key(idempotency_key),
            },
            result="failed",
            error_message=f"rejected={err.code.value}",
        )
        raise
    except Exception:
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "error_code": McpErrorCode.UPLOAD_INVALID_CONTENT.value,
                "idempotency_key": digest_idempotency_key(idempotency_key),
            },
            result="failed",
            error_message=f"rejected={McpErrorCode.UPLOAD_INVALID_CONTENT.value}",
        )
        raise McpToolError(McpErrorCode.UPLOAD_INVALID_CONTENT)

    # ---------- 2. store 就绪（下载器连接只能来自 app.state.store 缓存） ----------
    store = runtime.require_store()

    # ---------- 3. 幂等重放：同键返回首次结果 ----------
    cache_key = (spec.tool_name, principal.user_id, idempotency_key)
    cached = cache_get(cache_key)
    if cached is not None:
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "info_hash": info_digest,
                "idempotency_key": digest_idempotency_key(idempotency_key),
                "replay": True,
            },
            result="success",
        )
        return dict(cached)

    # ---------- 4. 共用 TorrentAddService（与 HTTP /torrent/add 同路径） ----------
    from app.services.torrent_add_service import TorrentAddParams, TorrentAddService

    db = runtime.sync_session()
    try:
        service = TorrentAddService(db, store=store)
        result = await service.add_torrent(
            TorrentAddParams(downloader_id=downloader_id, save_path=None),
            torrent_content=content,
            audit_context=call_context.audit,
            operator=principal.username,
        )
    except Exception:
        # 服务层契约是"领域结果不抛异常"；此处兜底防 SDK 把 str(e) 渲染进响应
        logger.exception(
            "MCP torrent_add_file 服务调用意外异常（message 不外发）: downloader_id=%s info_hash=%s",
            downloader_id,
            info_digest,
        )
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "downloader_id": downloader_id,
                "info_hash": info_digest,
                "idempotency_key": digest_idempotency_key(idempotency_key),
            },
            result="failed",
            error_message="service_exception",
        )
        raise McpToolError(McpErrorCode.INTERNAL_ERROR)
    finally:
        db.close()

    if not result.ok:
        error = _ADD_RESULT_CODE_TO_ERROR.get(result.code, McpErrorCode.INTERNAL_ERROR)
        # 上游 msg 可能携带异常文本/路径：只进服务端日志，不进响应与审计 detail
        logger.warning(
            "MCP torrent_add_file 失败（message 不外发）: downloader_id=%s info_hash=%s code=%s msg=%s",
            downloader_id,
            info_digest,
            result.code,
            result.msg,
        )
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "downloader_id": downloader_id,
                "info_hash": info_digest,
                "service_code": result.code,
                "idempotency_key": digest_idempotency_key(idempotency_key),
            },
            result="failed",
            error_message=f"code={result.code}",
        )
        raise McpToolError(error)

    # ---------- 5. 领域结果（allowlist 出口：finalize_tool_output 裁剪+泄漏扫描） ----------
    payload = {
        "added": bool(result.created),
        "duplicate": not bool(result.created),
        "info_id": result.info_id,
        "name": result.name,
        "downloader_id": downloader_id,
        "downloader_nickname": result.downloader_nickname,
    }
    cache_put(cache_key, payload)
    await log_tool_audit(
        runtime,
        call_context,
        principal,
        detail={
            "tool": spec.tool_name,
            "downloader_id": downloader_id,
            "info_hash": info_digest,
            "added": payload["added"],
            "idempotency_key": digest_idempotency_key(idempotency_key),
        },
        result="success",
    )
    return payload
