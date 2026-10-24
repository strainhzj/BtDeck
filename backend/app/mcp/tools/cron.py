"""MCP 工具：cron_task_trigger（feature mcp-service-capabilities W3-②，高风险）。

复用协议无关触发入口 ``trigger_task_by_code``（G4；enabled/运行中前检与
执行器策略由其内部承担）。MCP 侧在其上再收敛一层**显式 allowlist**：
仅开放内置注册表中的只读/同步维护类任务（计划 §4.7"仅显式 task_code 白名单"，
宁缺勿滥——孤儿清理/路径扫描/重宣告等副作用面大的任务首版一律不开放；
task_type 永不作为放行依据）。

run_id 口径：触发是异步接受的，``run_id`` 由执行器在执行期写入
``CronTask.last_run_id``，触发时点不可同步取得——返回 ``run_id: null``
并不伪报完成（§4.7"不伪报完成"语义的首版实现，W4 演练复核）。
"""

import logging
from typing import Any, Dict

from app.auth.principal import AuthenticatedPrincipal
from app.mcp.catalog import ToolCallContext
from app.mcp.contracts import CapabilitySpec
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.runtime import McpRuntime

logger = logging.getLogger(__name__)

# MCP 显式 allowlist（内置注册表的保守子集；数据源 default_scheduled_tasks.py，
# §10.3-W3）。增删视同契约变更，需同步计划与威胁模型。
MCP_CRON_TASK_ALLOWLIST = (
    "cached_downloader_sync",  # 下载器缓存同步
    "Tag_Data_Sync",  # 标签数据同步
    "TORRENT_TRACKER_STATUS_JUDGE",  # Tracker 状态判定
    "torrent_info_sync_ac608e4d",  # 种子信息同步
    "tracker_sync_598b784c",  # Tracker 同步
    "refresh_token_cleanup",  # 刷新令牌清理
)

# trigger_task_by_code 稳定拒绝码 → MCP 错误码（§4.7/错误码对齐表）
_REASON_TO_ERROR = {
    "TASK_NOT_BUILTIN": McpErrorCode.CRON_TASK_NOT_ALLOWED,
    "TASK_TYPE_NOT_ALLOWED": McpErrorCode.CRON_TASK_NOT_ALLOWED,
    "TASK_NOT_FOUND": McpErrorCode.CRON_TASK_NOT_TRIGGERABLE,
    "TRIGGER_REJECTED": McpErrorCode.CRON_TASK_NOT_TRIGGERABLE,
    "TRIGGER_ERROR": McpErrorCode.INTERNAL_ERROR,
}


async def handle_cron_trigger(
    spec: CapabilitySpec,
    principal: AuthenticatedPrincipal,
    arguments: Dict[str, Any],
    runtime: McpRuntime,
    call_context: ToolCallContext,
) -> Dict[str, Any]:
    """cron_task_trigger 处理器（异步触发，accepted 语义）。"""
    from app.mcp.tools.common import log_tool_audit
    from app.mcp.tools.idempotency import cache_get, cache_put, digest_idempotency_key
    from app.tasks.cron_trigger import trigger_task_by_code

    task_code = arguments["task_code"]
    idempotency_key = arguments["idempotency_key"]

    if task_code not in MCP_CRON_TASK_ALLOWLIST:
        # 内置但未对 MCP 开放、或目录外名字：统一 NOT_ALLOWED（不区分，防枚举）
        raise McpToolError(McpErrorCode.CRON_TASK_NOT_ALLOWED)
    runtime.require_ready()

    cache_key = (spec.tool_name, principal.user_id, idempotency_key)
    cached = cache_get(cache_key)
    if cached is not None:
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "task_code": task_code,
                "idempotency_key": digest_idempotency_key(idempotency_key),
                "replay": True,
            },
            result="success",
        )
        return dict(cached)

    result = await trigger_task_by_code(task_code, session_factory=runtime.session_factory)
    if not result.get("accepted"):
        reason = str(result.get("reason", ""))
        error = _REASON_TO_ERROR.get(reason, McpErrorCode.INTERNAL_ERROR)
        await log_tool_audit(
            runtime,
            call_context,
            principal,
            detail={
                "tool": spec.tool_name,
                "task_code": task_code,
                "rejected_reason": reason,
                "idempotency_key": digest_idempotency_key(idempotency_key),
            },
            result="failed",
            error_message=f"reason={reason}",
        )
        logger.warning("MCP cron 触发被拒绝（message 不外发）: task_code=%s reason=%s", task_code, reason)
        raise McpToolError(error)

    payload = {
        "accepted": True,
        "task_code": task_code,
        "run_id": None,  # 执行期写入 CronTask.last_run_id，触发时点不可同步取得
        "reason": "",
    }
    cache_put(cache_key, payload)
    await log_tool_audit(
        runtime,
        call_context,
        principal,
        detail={
            "tool": spec.tool_name,
            "task_code": task_code,
            "idempotency_key": digest_idempotency_key(idempotency_key),
        },
        result="success",
    )
    return payload
