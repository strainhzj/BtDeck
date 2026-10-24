"""MCP 查询条件隐私巡检（feature mcp-service-capabilities-2026-08-28 W3）。

计划 §4.5 输入契约：MCP 侧高级查询/查询模板的 tracker 条件只接受**域名**——

- 禁止 ``tracker_msg`` 条件（原始 announce/scrape 消息不开放为查询输入）；
- ``tracker_url`` 条件值必须是合规域名（``is_safe_tracker_domain``），
  操作符只允许 ``contains``/``not_contains``（域名字串语义；``eq`` 等操作符
  在完整 URL 上匹配，MCP 客户端没有完整 URL，语义必然错位故拒绝）。

巡检在 service 复用校验（pydantic 字段白名单）**之前**执行：隐私契约是 MCP
协议适配层的职责，不要求共用 service 理解 MCP 语义（G4 边界）。同时兼容
搜索形态（``condition_groups`` + 基础过滤）与模板形态（``source``/``listQuery``）。
"""

from typing import Any, Dict, List

from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.redaction import is_safe_tracker_domain

# MCP 侧允许出现在 tracker_url 条件上的操作符（域名字串语义）
_TRACKER_URL_OPERATORS = frozenset({"contains", "not_contains"})

# 搜索请求白名单：MCP conditions 对象允许的顶层键（映射到共用 service 的
# 基础过滤/条件组；白名单外键一律拒绝——协议面最小化，未列键不透传）
SEARCH_CONDITION_TOP_LEVEL = frozenset(
    {
        "downloader_id",
        "downloader_name",
        "name",
        "tags",
        "category",
        "status",
        "size_min",
        "size_max",
        "ratio_min",
        "ratio_max",
        "added_date_min",
        "added_date_max",
        "completed_date_min",
        "completed_date_max",
        "condition_groups",
        "between_group_logics",
    }
)


def _iter_condition_dicts(container: Any) -> List[Dict[str, Any]]:
    """从条件组结构中收集全部 condition dict（宽容形态：多余键交给 service 拒）。"""
    found: List[Dict[str, Any]] = []
    if isinstance(container, dict):
        # 搜索形态：{"condition_groups": [{"conditions": [...]}]}
        groups = container.get("condition_groups")
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, dict):
                    found.extend(_iter_condition_dicts(group))
        # 模板 advanced 形态：组内 conditions；模板 simple 形态：listQuery 无条件组
        conditions = container.get("conditions")
        if isinstance(conditions, list):
            for condition in conditions:
                if isinstance(condition, dict):
                    found.append(condition)
    elif isinstance(container, list):
        for item in container:
            found.extend(_iter_condition_dicts(item))
    return found


def validate_privacy_conditions(conditions: Any) -> None:
    """对 MCP 查询/模板 conditions 做隐私巡检（违规即稳定码拒绝，不透传值）。"""
    if conditions is None:
        return
    if not isinstance(conditions, dict):
        raise McpToolError(McpErrorCode.INVALID_ARGUMENT)

    # simple 模板（listQuery）不含条件组；advanced/搜索形态走条件巡检
    for condition in _iter_condition_dicts(conditions):
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")
        if field == "tracker_msg":
            raise McpToolError(McpErrorCode.INVALID_ARGUMENT)
        if field == "tracker_url":
            if operator not in _TRACKER_URL_OPERATORS:
                raise McpToolError(McpErrorCode.INVALID_ARGUMENT)
            if not is_safe_tracker_domain(value):
                raise McpToolError(McpErrorCode.INVALID_ARGUMENT)


def build_search_request(conditions: Dict[str, Any], page: int, page_size: int) -> Dict[str, Any]:
    """MCP conditions 对象 → 共用 service 的请求 dict（白名单拷贝 + 分页映射）。

    只接受 SEARCH_CONDITION_TOP_LEVEL 中的键，未知顶层键显式拒绝（不静默丢弃
    ——调用方条件拼错应当被告知）；``page_size`` 映射为 service 的 ``limit``
    （MCP 预算上限已在 catalog 校验层强制 ≤200）。service 侧
    ``EnhancedAdvancedSearchRequest.model_validate`` 再做完整结构校验。
    """
    validate_privacy_conditions(conditions)
    unknown = sorted(set(conditions) - SEARCH_CONDITION_TOP_LEVEL)
    if unknown:
        raise McpToolError(McpErrorCode.INVALID_ARGUMENT)
    request: Dict[str, Any] = {"page": page, "limit": page_size}
    for key in SEARCH_CONDITION_TOP_LEVEL:
        if key in conditions:
            request[key] = conditions[key]
    return request
