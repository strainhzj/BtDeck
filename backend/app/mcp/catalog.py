"""MCP 能力目录 → 工具定义/双门禁解析/入参校验（feature ...W2）。

单一事实源是 ``app.mcp.contracts``；本模块把契约目录翻译成可下发的工具定义
（tools/list）、执行前门禁解析（tools/call 复核）与协议无关的入参校验。
不含 MCP SDK import——SDK 接线（types.Tool 转换）在 server.py，保证本模块
在无 SDK 环境可被静态门禁与单测加载。

门禁顺序（计划 §4.1 图 + §4.3）：

1. 全局开关（transport global gate）：``SERVICE_DISABLED``；
2. 能力开关：disabled 工具不出现在 tools/list；tools/call 对未启用工具名
   （含别名/旧名/不存在的名字，防目录枚举）统一 ``CAPABILITY_DISABLED``；
3. principal 认证与入参校验（auth.py / 本模块 validate_arguments）。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.mcp.contracts import (
    CAPABILITY_CATALOG,
    FORBIDDEN_INPUT_ARGUMENTS,
    MARK_PENDING_DELETE_MAX_ITEMS,
    PAGE_SIZE_MAX,
    TOOL_INPUT_SPECS,
    CapabilitySpec,
    ToolFieldSpec,
)
from app.mcp.errors import McpErrorCode, McpToolError
from app.services.mcp_settings_service import McpRuntimeSettings

# 契约约束映射到稳定码的字段级预算（§4.6/§4.7；集中在共享校验器避免 W3 各工具散落）
_BUDGET_RULES: Dict[str, Any] = {
    "page_size": ("max_int", PAGE_SIZE_MAX, McpErrorCode.PAGE_SIZE_EXCEEDED),
    "info_ids": ("max_len", MARK_PENDING_DELETE_MAX_ITEMS, McpErrorCode.ITEM_LIMIT_EXCEEDED),
}


@dataclass(frozen=True)
class ToolDefinition:
    """可下发的工具定义（server.py 转换为 SDK 的 types.Tool）。"""

    name: str
    description: str
    input_schema: Dict[str, Any]


def build_tool_definitions() -> Dict[str, ToolDefinition]:
    """从契约目录生成全量工具定义（能力码 → 工具名 一一对应）。"""
    definitions: Dict[str, ToolDefinition] = {}
    for spec in CAPABILITY_CATALOG:
        definitions[spec.tool_name] = ToolDefinition(
            name=spec.tool_name,
            description=f"{spec.description}（风险分级: {spec.risk}）",
            input_schema=_input_schema(spec.tool_name),
        )
    return definitions


def _input_schema(tool_name: str) -> Dict[str, Any]:
    """把 ToolFieldSpec 元组折叠为 JSON Schema object（SDK 侧禁二次校验文本外泄）。"""
    fields: tuple[ToolFieldSpec, ...] = TOOL_INPUT_SPECS[tool_name]
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for spec in fields:
        properties[spec.name] = {
            "type": spec.json_type,
            "description": spec.description,
        }
        if spec.required:
            required.append(spec.name)
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def enabled_tool_definitions(snapshot: McpRuntimeSettings) -> List[ToolDefinition]:
    """tools/list 过滤：仅返回 effective_enabled 且能力开启的工具（G2 发现门禁）。"""
    if not snapshot.effective_enabled:
        return []
    definitions = build_tool_definitions()
    return [definitions[spec.tool_name] for spec in CAPABILITY_CATALOG if snapshot.capability_enabled(spec.code)]


def resolve_callable_tool(tool_name: str, snapshot: McpRuntimeSettings) -> CapabilitySpec:
    """tools/call 复核门禁（G2 执行门禁）。

    未启用工具名（含目录外名字/别名/旧名）统一 CAPABILITY_DISABLED——
    不区分"不存在"与"存在但关闭"，避免通过错误码差异枚举目录（§4.3-3）。
    全局关闭在调用方先行判定（SERVICE_DISABLED）。
    """
    for spec in CAPABILITY_CATALOG:
        if spec.tool_name == tool_name:
            if not snapshot.capability_enabled(spec.code):
                raise McpToolError(McpErrorCode.CAPABILITY_DISABLED)
            return spec
    raise McpToolError(McpErrorCode.CAPABILITY_DISABLED)


# ==============================================================================
# 入参校验（SDK validate_input 关闭后的服务端强校验；固定文案不回显参数值）
# ==============================================================================


def validate_arguments(tool_name: str, arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """按 TOOL_INPUT_SPECS 做结构校验，返回归一后的参数字典。

    检查链：对象形态 → 主体伪造字段（FORBIDDEN_ARGUMENT）→ 未知字段/缺必填
    （INVALID_ARGUMENT）→ 类型（INVALID_ARGUMENT，bool 先于 int 判定）→
    契约级预算（PAGE_SIZE_EXCEEDED / ITEM_LIMIT_EXCEEDED）。错误文案全部固定，
    不插值参数值（§4.5）。
    """
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise McpToolError(McpErrorCode.INVALID_ARGUMENT)

    forbidden = [name for name in FORBIDDEN_INPUT_ARGUMENTS if name in arguments]
    if forbidden:
        raise McpToolError(McpErrorCode.FORBIDDEN_ARGUMENT)

    fields = TOOL_INPUT_SPECS[tool_name]
    known = {spec.name for spec in fields}
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise McpToolError(McpErrorCode.INVALID_ARGUMENT)

    normalized: Dict[str, Any] = {}
    for spec in fields:
        value = arguments.get(spec.name)
        if value is None:
            if spec.required:
                raise McpToolError(McpErrorCode.INVALID_ARGUMENT)
            continue
        _check_type(spec, value)
        _check_budget(spec.name, value)
        normalized[spec.name] = value
    return normalized


def _check_type(spec: ToolFieldSpec, value: Any) -> None:
    """JSON 类型判定（bool 是 int 的子集，必须先排除；array 兼容 list/tuple）。"""
    if spec.json_type == "string":
        ok = isinstance(value, str)
    elif spec.json_type == "boolean":
        ok = isinstance(value, bool)
    elif spec.json_type == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif spec.json_type == "array":
        ok = isinstance(value, (list, tuple))
    elif spec.json_type == "object":
        ok = isinstance(value, dict)
    else:  # 契约出现未登记类型即实现破损，按 INVALID_ARGUMENT 拒绝
        ok = False
    if not ok:
        raise McpToolError(McpErrorCode.INVALID_ARGUMENT)


def _check_budget(name: str, value: Any) -> None:
    """字段级预算（契约 constraints 中点名的两条跨工具预算；类型已由 _check_type 保证）。"""
    rule = _BUDGET_RULES.get(name)
    if rule is None:
        return
    kind, limit, error = rule
    if kind == "max_int":
        if value > limit:
            raise McpToolError(error)
    elif kind == "max_len":
        if len(value) > limit:
            raise McpToolError(error)


# ==============================================================================
# 工具处理器注册表（W2 交付注册面；六工具处理器在 W3 按风险分批注册）
# ==============================================================================


@dataclass
class ToolHandlerRegistry:
    """tool_name → 异步处理器注册表。

    处理器统一签名 ``(spec, principal, arguments, runtime) -> dict``（领域结果，
    交由 redaction.finalize_tool_output 做 allowlist/泄漏扫描/预算）。
    W2 基线为空注册表：能力开启但未注册处理器时 dispatch 返回 INTERNAL_ERROR
    （固定文案），不静默成功。
    """

    _handlers: Dict[str, Any] = field(default_factory=dict)

    def register(self, tool_name: str, handler: Any) -> None:
        self._handlers[tool_name] = handler

    def get(self, tool_name: str) -> Optional[Any]:
        return self._handlers.get(tool_name)

    def registered_names(self) -> List[str]:
        return sorted(self._handlers)


TOOL_HANDLERS = ToolHandlerRegistry()
