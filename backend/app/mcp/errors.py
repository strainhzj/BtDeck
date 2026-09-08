"""MCP 稳定错误码与 HTTP 业务语义对齐表（W0 固化）。

原则（PLANS/mcp-service-capabilities.md §4.5/§4.7）：

- MCP 返回领域结果，不使用 HTTP ``CommonResponse``；错误以稳定字符串码
  抛出/返回，禁止把上游异常文本、URL、路径透传给客户端（先清洗再映射）。
- 每个错误码的默认文案固定，不含动态上游细节；细节只进脱敏审计日志。
- 对齐表描述"等价 HTTP 语义"仅用于跨协议排障与等价测试对齐，HTTP 侧
  现有行为保持不变（不反向上 HTTP endpoint 语义靠拢 MCP）。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping

# app/auth/principal.py 的拒绝原因码 → MCP 错误码（统一认证内核接线用，
# W2 transport 捕获 PrincipalAuthenticationError 后按本表映射）。
PRINCIPAL_REASON_TO_ERROR: Mapping[str, str] = {
    "TOKEN_MISSING": "AUTH_REQUIRED",
    "TOKEN_INVALID": "AUTH_TOKEN_INVALID",
    "USER_NOT_FOUND": "AUTH_USER_NOT_FOUND",
    "USER_INACTIVE": "AUTH_USER_INACTIVE",
    "PASSWORD_CHANGE_REQUIRED": "PASSWORD_CHANGE_REQUIRED",
}


class McpErrorCode(str, Enum):
    """稳定错误码枚举。值为跨版本承诺的字符串码，禁止重命名既有值。"""

    # ---- 认证（G3）----
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_USER_NOT_FOUND = "AUTH_USER_NOT_FOUND"
    AUTH_USER_INACTIVE = "AUTH_USER_INACTIVE"
    PASSWORD_CHANGE_REQUIRED = "PASSWORD_CHANGE_REQUIRED"

    # ---- 服务与能力开关（G1/G2）----
    SERVICE_DISABLED = "SERVICE_DISABLED"
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED"

    # ---- 运行时与生命周期（G9）----
    RUNTIME_NOT_READY = "RUNTIME_NOT_READY"

    # ---- 输入与预算（G6/G8）----
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FORBIDDEN_ARGUMENT = "FORBIDDEN_ARGUMENT"
    PAGE_SIZE_EXCEEDED = "PAGE_SIZE_EXCEEDED"
    RESULT_TOO_LARGE = "RESULT_TOO_LARGE"
    ITEM_LIMIT_EXCEEDED = "ITEM_LIMIT_EXCEEDED"
    UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
    UPLOAD_INVALID_CONTENT = "UPLOAD_INVALID_CONTENT"
    SERVER_PATH_FORBIDDEN = "SERVER_PATH_FORBIDDEN"

    # ---- 写操作确认与幂等（G7）----
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"

    # ---- Cron 白名单（G8）----
    CRON_TASK_NOT_ALLOWED = "CRON_TASK_NOT_ALLOWED"
    CRON_TASK_NOT_TRIGGERABLE = "CRON_TASK_NOT_TRIGGERABLE"

    # ---- 上游与领域结果（G4/G7）----
    DOWNSTREAM_FAILURE = "DOWNSTREAM_FAILURE"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class HttpAlignment:
    """与 HTTP 业务语义的对齐描述（跨协议等价测试锚点，非行为耦合）。"""

    http_status: int
    note: str


HTTP_ALIGNMENT: Dict[McpErrorCode, HttpAlignment] = {
    McpErrorCode.AUTH_REQUIRED: HttpAlignment(401, "未携带 Bearer token；HTTP 侧为 401 未认证"),
    McpErrorCode.AUTH_TOKEN_INVALID: HttpAlignment(401, "token 过期/签名或登录密钥不一致"),
    McpErrorCode.AUTH_USER_NOT_FOUND: HttpAlignment(401, "token 有效但用户已不存在"),
    McpErrorCode.AUTH_USER_INACTIVE: HttpAlignment(403, "用户被禁用；现状仅在登录拦截，MCP 侧认证内核统一拦截"),
    McpErrorCode.PASSWORD_CHANGE_REQUIRED: HttpAlignment(403, "强制改密期间拒绝业务调用"),
    McpErrorCode.SERVICE_DISABLED: HttpAlignment(503, "全局开关关闭/环境 kill switch 生效"),
    McpErrorCode.CAPABILITY_DISABLED: HttpAlignment(404, "能力关闭即不可发现；对缓存旧定义直调等价 404 语义的稳定拒绝"),
    McpErrorCode.RUNTIME_NOT_READY: HttpAlignment(503, "store/scheduler 未就绪或应用关闭中，稳定拒绝不重试自愈"),
    McpErrorCode.INVALID_ARGUMENT: HttpAlignment(422, "参数结构/取值不满足 schema"),
    McpErrorCode.FORBIDDEN_ARGUMENT: HttpAlignment(403, "工具参数携带 user_id/operator 等主体伪造字段"),
    McpErrorCode.PAGE_SIZE_EXCEEDED: HttpAlignment(422, "pageSize 超过 200 上限（HTTP 高级搜索沿用自身上限，不联动）"),
    McpErrorCode.RESULT_TOO_LARGE: HttpAlignment(413, "序列化结果超过 1 MiB，整体失败不截断"),
    McpErrorCode.ITEM_LIMIT_EXCEEDED: HttpAlignment(422, "单次批量条目超过 100（等级 4 标记）"),
    McpErrorCode.UPLOAD_TOO_LARGE: HttpAlignment(413, "种子文件超过 10 MiB 默认/64 MiB 硬上限"),
    McpErrorCode.UPLOAD_INVALID_CONTENT: HttpAlignment(422, "非 bencode/扩展名不符/空文件/info hash 无法解析"),
    McpErrorCode.SERVER_PATH_FORBIDDEN: HttpAlignment(400, "首版不接受服务器本地路径/URL/磁力输入"),
    McpErrorCode.CONFIRM_REQUIRED: HttpAlignment(428, "写操作缺少 confirm=true 前置条件"),
    McpErrorCode.IDEMPOTENCY_KEY_REQUIRED: HttpAlignment(400, "写操作缺少幂等键"),
    McpErrorCode.CRON_TASK_NOT_ALLOWED: HttpAlignment(403, "task_code 不在 MCP 显式白名单或类型永拒"),
    McpErrorCode.CRON_TASK_NOT_TRIGGERABLE: HttpAlignment(
        409, "任务禁用/运行中/执行器策略检查未过，语义对齐 HTTP 触发冲突"
    ),
    McpErrorCode.DOWNSTREAM_FAILURE: HttpAlignment(502, "下载器/上游失败，已清洗无敏感细节"),
    McpErrorCode.PARTIAL_FAILURE: HttpAlignment(200, "领域结果非错误：下载器成功但 DB 失败等部分成功，保留逐项明细"),
    McpErrorCode.INTERNAL_ERROR: HttpAlignment(500, "兜底错误，文案固定不含异常细节"),
}

# 稳定默认文案：不插值上游文本；W2 错误构造器只允许追加审计 ID。
DEFAULT_MESSAGES: Dict[McpErrorCode, str] = {
    McpErrorCode.AUTH_REQUIRED: "缺少访问令牌。",
    McpErrorCode.AUTH_TOKEN_INVALID: "访问令牌无效或已过期。",
    McpErrorCode.AUTH_USER_NOT_FOUND: "访问令牌对应的用户不存在。",
    McpErrorCode.AUTH_USER_INACTIVE: "用户已被禁用。",
    McpErrorCode.PASSWORD_CHANGE_REQUIRED: "用户处于强制改密状态，需先完成改密。",
    McpErrorCode.SERVICE_DISABLED: "MCP 服务未启用。",
    McpErrorCode.CAPABILITY_DISABLED: "该能力未启用或已被关闭。",
    McpErrorCode.RUNTIME_NOT_READY: "服务运行时尚未就绪，请稍后重试。",
    McpErrorCode.INVALID_ARGUMENT: "参数不符合工具契约。",
    McpErrorCode.FORBIDDEN_ARGUMENT: "操作者身份只能来自认证主体，禁止通过参数指定。",
    McpErrorCode.PAGE_SIZE_EXCEEDED: "分页大小超过上限。",
    McpErrorCode.RESULT_TOO_LARGE: "结果超出响应预算，请缩小查询范围。",
    McpErrorCode.ITEM_LIMIT_EXCEEDED: "单次操作条目数超过上限。",
    McpErrorCode.UPLOAD_TOO_LARGE: "种子文件大小超过限制。",
    McpErrorCode.UPLOAD_INVALID_CONTENT: "种子文件内容或类型校验未通过。",
    McpErrorCode.SERVER_PATH_FORBIDDEN: "不接受服务器路径、URL 或磁力链接输入。",
    McpErrorCode.CONFIRM_REQUIRED: "写操作需要显式确认（confirm=true）。",
    McpErrorCode.IDEMPOTENCY_KEY_REQUIRED: "写操作需要幂等键。",
    McpErrorCode.CRON_TASK_NOT_ALLOWED: "该定时任务不在 MCP 允许范围内。",
    McpErrorCode.CRON_TASK_NOT_TRIGGERABLE: "定时任务当前不可触发。",
    McpErrorCode.DOWNSTREAM_FAILURE: "下游服务调用失败。",
    McpErrorCode.PARTIAL_FAILURE: "操作部分成功，详见逐项结果。",
    McpErrorCode.INTERNAL_ERROR: "服务内部错误。",
}


def all_codes() -> frozenset[str]:
    """全部稳定错误码集合（契约测试与序列化守卫用）。"""
    return frozenset(code.value for code in McpErrorCode)


def validate_alignment_completeness() -> None:
    """对齐表与默认文案必须覆盖全部错误码（缺失即契约破损，W0 测试锚定）。"""
    missing_alignment = set(McpErrorCode) - set(HTTP_ALIGNMENT)
    missing_message = set(McpErrorCode) - set(DEFAULT_MESSAGES)
    if missing_alignment or missing_message:
        raise ValueError(
            f"错误码契约不完整: 对齐表缺失 {[e.value for e in missing_alignment]}, "
            f"默认文案缺失 {[e.value for e in missing_message]}"
        )
