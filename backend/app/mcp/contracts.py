"""MCP 能力契约（W0 固化，feature mcp-service-capabilities-2026-08-28）。

框架无关声明层：配置键与版本、能力目录、工具输入契约、输出 allowlist、
脱敏数据字典与资源预算。本模块是 W2 catalog/redaction 与 W3 工具实现的
单一事实源，实现层禁止散落重定义；任何字段增删视同契约变更，需同步
PLANS/mcp-service-capabilities.md §4.3/§4.5/§4.6 与 docs/security/mcp-threat-model.md。

本模块不 import 任何 MCP SDK（SDK 选型探针见 backend/scripts/mcp_sdk_probe.py，
结论记录于计划 §10.4），仅依赖 stdlib，保证在无 SDK 环境下可被静态门禁加载。
"""

from dataclasses import dataclass
from typing import Dict, Tuple

# ==============================================================================
# 配置持久化（§4.2）：复用 configs 表的首个版本化 JSON 键
# ==============================================================================

MCP_CONFIG_KEY = "mcp.runtime.v1"
MCP_CONFIG_SCHEMA_VERSION = 1
# 只读环境紧急开关，优先级最高，UI 不得覆盖（§4.2）
MCP_FORCE_DISABLED_ENV = "BTDECK_MCP_FORCE_DISABLED"

# ==============================================================================
# 资源预算（§4.6/§4.7）：MCP 侧独立预算，不沿用 HTTP 上限
# ==============================================================================

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 200
RESPONSE_MAX_BYTES = 1_048_576  # 序列化响应硬上限 1 MiB，超限 RESULT_TOO_LARGE
MARK_PENDING_DELETE_MAX_ITEMS = 100  # 等级 4 标记单次条目上限
TORRENT_UPLOAD_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 默认单文件 10 MiB（可配置）
TORRENT_UPLOAD_HARD_MAX_BYTES = 64 * 1024 * 1024  # 硬上限 64 MiB（不可配置突破）


@dataclass(frozen=True)
class CapabilitySpec:
    """预置能力目录条目（§4.3）。风险分级决定默认关闭与额外门禁强度。"""

    code: str
    tool_name: str
    risk: str  # "read" | "write" | "high"
    description: str
    extra_gates: Tuple[str, ...]
    requires_confirm: bool = False
    requires_idempotency_key: bool = False
    requires_audit: bool = True


CAPABILITY_CATALOG: Tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        code="torrent.advanced_search",
        tool_name="torrent_advanced_search",
        risk="read",
        description="按字段白名单条件高级查询种子（脱敏摘要，默认省略种子 hash）。",
        extra_gates=(
            "字段白名单（与 HTTP 高级搜索共用 service 的条件校验）",
            "pageSize 默认 20 / 最大 200，响应 ≤1 MiB",
            "输出为脱敏 DTO（tracker 仅域名、路径仅 pathDisplay）",
        ),
    ),
    CapabilitySpec(
        code="torrent.mark_pending_delete",
        tool_name="torrent_mark_pending_delete",
        risk="write",
        description=("为下载器与数据库中的种子添加 pending_delete 标签；" "仅添加标签，不删除任务或文件。"),
        extra_gates=(
            "单次最多 100 项（info_id 列表）",
            "逐项结果：下载器成功但 DB 失败必须保留 partial 语义",
            "幂等：重复提交已标记项返回 already_marked 而非报错",
        ),
        requires_confirm=True,
        requires_idempotency_key=True,
    ),
    CapabilitySpec(
        code="torrent.add",
        tool_name="torrent_add_file",
        risk="high",
        description="添加 .torrent 种子文件（仅二进制内容，不接受磁力/URL/服务器路径）。",
        extra_gates=(
            "默认 10 MiB / 硬上限 64 MiB，bencode、扩展名、空文件与 info hash 校验",
            "禁止服务器本地路径与任意 URL 输入",
            "与 HTTP /torrent/add 共用 TorrentAddService（含下载器调度/超时治理）",
        ),
        requires_confirm=True,
        requires_idempotency_key=True,
    ),
    CapabilitySpec(
        code="search_template.create",
        tool_name="advanced_search_template_create",
        risk="write",
        description="创建高级查询组合/查询模板（模板归属认证主体）。",
        extra_gates=(
            "user_id 只能来自 principal，参数携带即 FORBIDDEN_ARGUMENT",
            "严格条件校验复用共用 service，与 HTTP 侧一致",
            "is_public 默认 false",
        ),
        requires_confirm=True,
        requires_idempotency_key=True,
    ),
    CapabilitySpec(
        code="dashboard.read",
        tool_name="dashboard_get",
        risk="read",
        description="读取仪表盘聚合数据（脱敏聚合，无下载器地址与审计敏感字段）。",
        extra_gates=(
            "仅脱敏聚合 DTO，不含下载器连接信息与绝对路径",
            "复用 DashboardService（RuntimeContext 注入版）",
        ),
    ),
    CapabilitySpec(
        code="cron.trigger",
        tool_name="cron_task_trigger",
        risk="high",
        description="立即触发一个内置定时任务（仅白名单 task_code）。",
        extra_gates=(
            "仅 MCP 显式 allowlist 中的内置 task_code；task_type 一律不作为放行依据",
            "任务必须 enabled、未运行且通过执行器策略检查",
            "返回 accepted/task_code/run_id，不伪报完成；禁止修改任务定义/启停",
        ),
        requires_confirm=True,
        requires_idempotency_key=True,
    ),
)

CAPABILITY_CODES: Tuple[str, ...] = tuple(spec.code for spec in CAPABILITY_CATALOG)
TOOL_NAMES: Tuple[str, ...] = tuple(spec.tool_name for spec in CAPABILITY_CATALOG)

# 所有能力的默认状态：全局关闭 + 逐能力关闭（G1 fail-closed 的代码侧锚点）
DEFAULT_CAPABILITY_STATES: Dict[str, bool] = {code: False for code in CAPABILITY_CODES}

# 操作者身份只能来自认证 principal；这些参数名出现在工具参数中即拒绝（§4.4）
FORBIDDEN_INPUT_ARGUMENTS: Tuple[str, ...] = ("user_id", "operator", "username")


def spec_by_code(code: str) -> CapabilitySpec:
    """按能力码取目录条目；未知码抛 KeyError（W2 用于配置加载校验）。"""
    for spec in CAPABILITY_CATALOG:
        if spec.code == code:
            return spec
    raise KeyError(f"未知 MCP 能力码: {code}")


def spec_by_tool_name(tool_name: str) -> CapabilitySpec:
    """按工具名取目录条目；禁止别名/旧名绕过（G2）。"""
    for spec in CAPABILITY_CATALOG:
        if spec.tool_name == tool_name:
            return spec
    raise KeyError(f"未知 MCP 工具名: {tool_name}")


# ==============================================================================
# 工具输入契约（§4.5/§4.6/§4.7）：W2 据此生成 JSON Schema 并做服务端复核
# ==============================================================================


@dataclass(frozen=True)
class ToolFieldSpec:
    """工具入参字段契约。constraints 为人读约束，服务端必须逐一强制执行。"""

    name: str
    json_type: str  # "string" | "boolean" | "integer" | "array" | "object"
    required: bool
    description: str
    constraints: Tuple[str, ...] = ()


TOOL_INPUT_SPECS: Dict[str, Tuple[ToolFieldSpec, ...]] = {
    "torrent_advanced_search": (
        ToolFieldSpec(
            name="conditions",
            json_type="object",
            required=True,
            description="条件组结构，与 HTTP 高级搜索共用条件校验；user_id/operator 出现即拒绝。",
            constraints=(
                "字段白名单复用共用 service 校验",
                "tracker 条件仅接受域名（禁 /、?、#、@、userinfo、passkey）",
                "不开放原始 tracker message 条件",
            ),
        ),
        ToolFieldSpec(
            name="page",
            json_type="integer",
            required=False,
            description="页码，从 1 开始。",
            constraints=("默认 1",),
        ),
        ToolFieldSpec(
            name="page_size",
            json_type="integer",
            required=False,
            description="每页条数。",
            constraints=(f"默认 {PAGE_SIZE_DEFAULT}", f"最大 {PAGE_SIZE_MAX}，超限 PAGE_SIZE_EXCEEDED"),
        ),
    ),
    "torrent_mark_pending_delete": (
        ToolFieldSpec(
            name="info_ids",
            json_type="array",
            required=True,
            description="种子关联 ID 列表（跨工具关联用 info_id，非种子 hash）。",
            constraints=(f"最多 {MARK_PENDING_DELETE_MAX_ITEMS} 项，超限 ITEM_LIMIT_EXCEEDED",),
        ),
        ToolFieldSpec(
            name="confirm",
            json_type="boolean",
            required=True,
            description="必须显式传 true 才执行。",
            constraints=("false/缺失均 CONFIRM_REQUIRED",),
        ),
        ToolFieldSpec(
            name="idempotency_key",
            json_type="string",
            required=True,
            description="调用方生成的幂等键。",
            constraints=("同键重复提交返回首次结果",),
        ),
    ),
    "torrent_add_file": (
        ToolFieldSpec(
            name="torrent_file_b64",
            json_type="string",
            required=True,
            description=".torrent 文件二进制内容的 base64 编码。",
            constraints=(
                f"解码后默认 ≤{TORRENT_UPLOAD_DEFAULT_MAX_BYTES // (1024 * 1024)} MiB，"
                f"硬上限 {TORRENT_UPLOAD_HARD_MAX_BYTES // (1024 * 1024)} MiB",
                "bencode 可解析、info hash 可提取、非空、扩展名语义为 .torrent",
                "不接受服务器本地路径/URL/磁力链接（SERVER_PATH_FORBIDDEN）",
            ),
        ),
        ToolFieldSpec(
            name="downloader_id",
            json_type="string",
            required=True,
            description="目标下载器 ID（UUID 字符串主键，仅 ID，连接信息永不回显）。",
            constraints=("必须使用 app.state.store 缓存连接",),
        ),
        ToolFieldSpec(
            name="confirm",
            json_type="boolean",
            required=True,
            description="必须显式传 true 才执行。",
            constraints=("false/缺失均 CONFIRM_REQUIRED",),
        ),
        ToolFieldSpec(
            name="idempotency_key",
            json_type="string",
            required=True,
            description="调用方生成的幂等键。",
            constraints=("同键重复提交返回首次结果",),
        ),
    ),
    "advanced_search_template_create": (
        ToolFieldSpec(
            name="name",
            json_type="string",
            required=True,
            description="模板名称。",
            constraints=("长度与字符集复用共用 service 校验",),
        ),
        ToolFieldSpec(
            name="conditions",
            json_type="object",
            required=True,
            description="条件组结构，同 torrent_advanced_search。",
            constraints=("tracker 条件仅接受域名",),
        ),
        ToolFieldSpec(
            name="is_public",
            json_type="boolean",
            required=False,
            description="是否公开；默认 false。",
            constraints=("默认 false",),
        ),
        ToolFieldSpec(
            name="confirm",
            json_type="boolean",
            required=True,
            description="必须显式传 true 才执行。",
            constraints=("false/缺失均 CONFIRM_REQUIRED",),
        ),
        ToolFieldSpec(
            name="idempotency_key",
            json_type="string",
            required=True,
            description="调用方生成的幂等键。",
            constraints=("同键重复提交返回首次结果",),
        ),
    ),
    "dashboard_get": (),
    "cron_task_trigger": (
        ToolFieldSpec(
            name="task_code",
            json_type="string",
            required=True,
            description="内置定时任务稳定 code。",
            constraints=(
                "必须命中 MCP 显式 allowlist（数据源 default_scheduled_tasks.py + task_profiles.py）",
                "task_type 一律不作为放行依据，0-3 永拒",
            ),
        ),
        ToolFieldSpec(
            name="confirm",
            json_type="boolean",
            required=True,
            description="必须显式传 true 才执行。",
            constraints=("false/缺失均 CONFIRM_REQUIRED",),
        ),
        ToolFieldSpec(
            name="idempotency_key",
            json_type="string",
            required=True,
            description="调用方生成的幂等键。",
            constraints=("同键重复提交返回首次结果",),
        ),
    ),
}


# ==============================================================================
# 工具输出 allowlist（§4.5）：最终序列化前的白名单，嵌套字段用点路径表示
# ==============================================================================

TOOL_OUTPUT_ALLOWLISTS: Dict[str, Tuple[str, ...]] = {
    "torrent_advanced_search": (
        "total",
        "page",
        "page_size",
        "items.info_id",
        "items.name",
        "items.size_bytes",
        "items.progress",
        "items.state",
        "items.category",
        "items.tags",
        "items.added_at",
        "items.tracker_domains",
        "items.path_display",
        "items.download_speed",
        "items.upload_speed",
    ),
    "torrent_mark_pending_delete": (
        "result",
        "downloader_success_count",
        "db_success_count",
        "already_marked_count",
        "items.info_id",
        "items.downloader_ok",
        "items.db_ok",
        "items.already_marked",
        "items.error_code",
    ),
    "torrent_add_file": (
        "added",
        "duplicate",
        "info_id",
        "name",
        "downloader_id",
        "downloader_nickname",
    ),
    "advanced_search_template_create": ("template_id", "name", "is_public", "created"),
    "dashboard_get": (
        "generated_at",
        "totals",
        "status_counts",
        "active_torrent_count",
        "global_download_speed",
        "global_upload_speed",
        "storage_used_bytes",
        "storage_total_bytes",
    ),
    "cron_task_trigger": ("accepted", "task_code", "run_id", "reason"),
}


# ==============================================================================
# 脱敏数据字典（§4.5 + §10.1-6）：响应、错误与日志三面统一适用
# ==============================================================================


@dataclass(frozen=True)
class RedactionRule:
    """敏感数据类型 → 来源与输出策略。W2 sanitizer/泄漏扫描按此实现。"""

    data_type: str
    sources: Tuple[str, ...]
    policy: str


REDACTION_DATA_DICTIONARY: Tuple[RedactionRule, ...] = (
    RedactionRule(
        data_type="tracker_url",
        sources=(
            "TrackerInfoVO/同步响应中的 tracker URL",
            "torrents/models.py TrackerMessageLog.sample_urls（原始 URL 列表）",
            "上游 announce/scrape 响应",
        ),
        policy="仅返回规范化 hostname/domain；移除 scheme、路径、query、fragment、userinfo、端口与 passkey/token。",
    ),
    RedactionRule(
        data_type="tracker_message",
        sources=("torrents/models.py TrackerMessageLog.msg（2048 长原始消息）",),
        policy="不返回原始 announce/scrape 文本；仅 working/error/unknown 规范状态与安全计数。",
    ),
    RedactionRule(
        data_type="absolute_path",
        sources=("种子保存路径", "种子文件路径", "异常与日志中的绝对路径"),
        policy="不返回原值；仅输出不含盘符、UNC、挂载根与父目录的 pathDisplay，或整体省略。",
    ),
    RedactionRule(
        data_type="downloader_credentials",
        sources=("下载器配置（host/port/username/password/cookie/token）",),
        policy="永不输出；仅允许 ID、nickname、类型、在线状态与聚合速度。",
    ),
    RedactionRule(
        data_type="torrent_hash",
        sources=("info_hash/hash 字段",),
        policy="高级查询默认省略；跨工具关联使用 info_id；诊断场景只返回不可逆短指纹。",
    ),
    RedactionRule(
        data_type="audit_metadata",
        sources=("审计记录中的 IP、User-Agent、session/request token",),
        policy="不进入 MCP 业务响应；审计 ID 允许返回供关联。",
    ),
    RedactionRule(
        data_type="free_text_error",
        sources=("下游客户端异常文本", "上游错误响应"),
        policy="先移除 URL 凭据、passkey/token、绝对路径与客户端异常细节，再映射为稳定错误码。",
    ),
    RedactionRule(
        data_type="tool_payload_in_logs",
        sources=("工具调用日志面",),
        policy=(
            "禁止记录完整工具参数、返回 payload、原始 Tracker URL/消息、上传内容与绝对路径；"
            "允许 capability code、principal ID、配置 revision、耗时、行数、结果码与审计 ID。"
        ),
    ),
)


def validate_contract_integrity() -> None:
    """契约完整性自检：目录、输入契约、输出 allowlist 三处必须一一对应。"""
    catalog_tools = set(TOOL_NAMES)
    input_tools = set(TOOL_INPUT_SPECS)
    output_tools = set(TOOL_OUTPUT_ALLOWLISTS)
    if not (catalog_tools == input_tools == output_tools):
        raise ValueError(
            "MCP 工具契约不一致: "
            f"目录={sorted(catalog_tools)}, 输入={sorted(input_tools)}, 输出={sorted(output_tools)}"
        )
    duplicate_codes = len(CAPABILITY_CODES) != len(set(CAPABILITY_CODES))
    duplicate_tools = len(TOOL_NAMES) != len(set(TOOL_NAMES))
    if duplicate_codes or duplicate_tools:
        raise ValueError("MCP 能力码或工具名存在重复")
    forbidden_overlap = set(FORBIDDEN_INPUT_ARGUMENTS) & {
        field.name for fields in TOOL_INPUT_SPECS.values() for field in fields
    }
    if forbidden_overlap:
        raise ValueError(f"输入契约不得包含主体伪造字段: {sorted(forbidden_overlap)}")
