"""MCP 输出脱敏层与最终泄漏扫描器（feature mcp-service-capabilities-2026-08-28 W2）。

按 ``app.mcp.contracts.REDACTION_DATA_DICTIONARY``（§4.5 数据字典）实现三类
原语 + 一条最终流水线：

- **标量脱敏原语**：tracker URL → 规范化 hostname（tracker_url）；绝对路径 →
  pathDisplay（absolute_path）；自由文本 → 移除 URL 凭据/passkey/绝对路径
  （free_text_error）。输入侧配套 ``is_safe_tracker_domain``（条件仅接受域名）。
- **allowlist 过滤**：按 ``TOOL_OUTPUT_ALLOWLISTS`` 点路径白名单裁剪 payload，
  白名单外字段（含下游 service 误塞的敏感字段）一律丢弃。
- **泄漏扫描器**：最终序列化前的纵深防线——对已过滤结构做 canary 扫描
  （scheme URL、URL 内凭据、passkey/token 参数、URL 编码变体、Windows/UNC/
  Unix 绝对路径、40/64 位 hex 种子哈希），命中即抛 ``LeakScanError``（工具
  调用整体失败 INTERNAL_ERROR，绝不截断放行）。
- **finalize_tool_output**：allowlist → 泄漏扫描 → 1 MiB 序列化预算
  （RESULT_TOO_LARGE 整体失败，不截断为不合法 JSON，§4.6）。

本模块仅依赖 stdlib + contracts，无 SDK / ORM / FastAPI 依赖。
"""

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote_plus, urlparse

from app.mcp.contracts import RESPONSE_MAX_BYTES, TOOL_OUTPUT_ALLOWLISTS
from app.mcp.errors import McpErrorCode, McpToolError

# ==============================================================================
# 标量脱敏原语
# ==============================================================================

# 合规 hostname：小写字母/数字/连字符/点（含 punycode xn-- 域）；禁止下划线等
_HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")


def redact_tracker_url(url: Any) -> Optional[str]:
    """tracker URL → 规范化 hostname（policy: tracker_url）。

    移除 scheme、userinfo、端口、路径、query（passkey/token 所在）、fragment；
    裸域名输入同样归一；无法解析出合规 hostname 返回 None（整体省略）。
    """
    if not isinstance(url, str):
        return None
    value = url.strip()
    if not value:
        return None
    try:
        if "://" in value:
            host = urlparse(value).hostname
        else:
            host = urlparse(f"//{value}").hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    if not host or len(host) > 253 or not _HOSTNAME_RE.match(host):
        return None
    return host


def is_safe_tracker_domain(value: Any) -> bool:
    """输入侧约束：tracker 条件仅接受域名。

    禁 scheme、``/``、``?``、``#``、``@``（userinfo/passkey 载体）、端口冒号；
    每个标签符合 hostname 字符集（§4.5 输入契约）；FQDN 尾点归一后判定。
    """
    if not isinstance(value, str):
        return False
    value = value.strip().lower().rstrip(".")
    if not value or len(value) > 253:
        return False
    if any(ch in value for ch in (":", "/", "?", "#", "@", "\\")):
        return False
    labels = value.split(".")
    return all(_HOSTNAME_RE.match(label) is not None for label in labels)


def redact_path_to_display(path: Any) -> str:
    """绝对路径 → pathDisplay（policy: absolute_path）。

    仅保留最后一个路径分量：盘符（含孤立 ``C:`` 残片）、UNC 主机/共享、
    挂载根与父目录全部丢弃；空值/不可解析返回空串（调用方按"整体省略"处理）。
    """
    if not isinstance(path, str):
        return ""
    parts = [p for p in re.split(r"[\\/]+", path.strip()) if p and not _DRIVE_LABEL_RE.match(p)]
    if not parts:
        return ""
    return parts[-1]


_DRIVE_LABEL_RE = re.compile(r"^[A-Za-z]:$")


# URL 内凭据（scheme://user:pass@host）与敏感查询参数（passkey/token/…）
_URL_WITH_CREDENTIALS_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9+.\-]*://[^\s\"'>@/]+:[^\s\"'>@]+@")
_SENSITIVE_PARAM_NAMES = r"passkey|token|apikey|api_key|secret|password|passwd"


class _SensitiveParamRe:
    """敏感查询参数正则（含 URL 编码变体 ``passkey%3D`` 的双形态匹配）。"""

    PLAIN = re.compile(rf"(?i)(?:^|[?&;\s])({_SENSITIVE_PARAM_NAMES})=")
    ENCODED = re.compile(rf"(?i)({_SENSITIVE_PARAM_NAMES})%3d")

    @classmethod
    def hit(cls, text: str) -> bool:
        return bool(cls.PLAIN.search(text) or cls.ENCODED.search(text) or cls.PLAIN.search(unquote_plus(text)))


def redact_free_text(text: Any) -> str:
    """自由文本清洗（policy: free_text_error）。

    移除 URL 凭据、完整 URL、敏感参数值与 Windows/UNC/Unix 绝对路径，
    替换为固定占位符；非字符串输入返回空串。清洗后仍应映射稳定错误码使用。
    """
    if not isinstance(text, str):
        return ""
    out = text
    out = _URL_WITH_CREDENTIALS_RE.sub("[REDACTED]@", out)
    out = re.sub(r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s\"'>]+", "[REDACTED-URL]", out)
    out = re.sub(rf"(?i)(?:^|[?&;\s])(?:{_SENSITIVE_PARAM_NAMES})=[^&\s\"'>]*", "[REDACTED]", out)
    out = re.sub(r"(?i)\b[a-z]:[\\/][^\s\"'>]*", "[REDACTED-PATH]", out)
    out = re.sub(r"\\\\[^\\]+(?:\\[^\\]+)+", "[REDACTED-PATH]", out)
    out = re.sub(r"(?i)(?<![\w])/(?:home|root|mnt|media|srv|opt|var|tmp|data|Users)/[^\s\"'>]*", "[REDACTED-PATH]", out)
    return out


# ==============================================================================
# 输出 allowlist 过滤（点路径）
# ==============================================================================


class LeakScanError(McpToolError):
    """泄漏扫描命中：实现缺陷级故障，整体失败并记录命中类型（不记录值）。"""

    def __init__(self, findings: List[str]):
        self.findings = findings
        super().__init__(McpErrorCode.INTERNAL_ERROR, "输出安全检查未通过。")


def _filter_by_paths(value: Any, paths: List[str]) -> Any:
    """按点路径集合过滤 dict / list；叶子标量原样保留。

    调用方保证 paths 非空（空集合场景由 apply_output_allowlist 以"整树放行"
    语义处理，不会进入本函数）。
    """
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            key = str(key)
            if key not in paths:
                continue
            result[key] = item
        return result
    if isinstance(value, list):
        return [_filter_by_paths(item, paths) for item in value]
    return value


def apply_output_allowlist(tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """按 TOOL_OUTPUT_ALLOWLISTS 白名单裁剪 payload。

    点路径语义：裸键（如 ``totals``）= 整树放行；带子路径的键（如
    ``items.info_id``）= 对每个 list 元素/子对象仅保留列出的子字段。
    未知工具名 = 契约破损，按 INTERNAL_ERROR 拒绝（不猜测默认集）。
    """
    allow = TOOL_OUTPUT_ALLOWLISTS.get(tool_name)
    if allow is None:
        raise McpToolError(McpErrorCode.INTERNAL_ERROR)
    top_paths = {p.split(".", 1)[0] for p in allow}
    nested: Dict[str, List[str]] = {}
    for p in allow:
        if "." in p:
            head, tail = p.split(".", 1)
            nested.setdefault(head, []).append(tail)

    if not isinstance(payload, dict):
        raise McpToolError(McpErrorCode.INTERNAL_ERROR)
    result: Dict[str, Any] = {}
    for key, value in payload.items():
        key = str(key)
        if key not in top_paths:
            continue
        result[key] = _filter_by_paths(value, nested[key]) if key in nested else value
    return result


# ==============================================================================
# 最终泄漏扫描器（纵深防线：结构扫描 + 字符串 canary 模式）
# ==============================================================================

_WIN_PATH_SCAN_RE = re.compile(r"(?i)\b[a-z]:[\\/]")
_UNC_PATH_SCAN_RE = re.compile(r"\\\\[a-z0-9_.$-]+\\", re.IGNORECASE)
_UNIX_ABS_SCAN_RE = re.compile(r"(?i)(?<![\w])/(?:home|root|mnt|media|srv|opt|var|tmp|data|Users)/")
_URL_SCHEME_SCAN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://")
_HEX_HASH_SCAN_RE = re.compile(r"\b[0-9a-fA-F]{40}\b|\b[0-9a-fA-F]{64}\b")


def _scan_string(value: str, path: str, findings: List[str]) -> None:
    if _URL_SCHEME_SCAN_RE.search(value):
        findings.append(f"{path}: url")
    if _URL_WITH_CREDENTIALS_RE.search(value):
        findings.append(f"{path}: url_credentials")
    if _SensitiveParamRe.hit(value):
        findings.append(f"{path}: sensitive_param")
    if _WIN_PATH_SCAN_RE.search(value) or _UNC_PATH_SCAN_RE.search(value):
        findings.append(f"{path}: absolute_path")
    if _UNIX_ABS_SCAN_RE.search(value):
        findings.append(f"{path}: unix_path")
    if _HEX_HASH_SCAN_RE.search(value):
        findings.append(f"{path}: torrent_hash")


def scan_for_leaks(value: Any, path: str = "$") -> List[str]:
    """递归扫描任意 JSON 形结构的泄漏 canary；返回命中描述（路径:类型）。

    bool 是 int 子集无需特判（字符串面才承载泄漏）；bytes 直接按命中处理
    （二进制不该出现在 MCP 业务响应）。
    """
    findings: List[str] = []
    if isinstance(value, str):
        _scan_string(value, path, findings)
    elif isinstance(value, bytes):
        findings.append(f"{path}: bytes")
    elif isinstance(value, dict):
        for key, item in value.items():
            findings.extend(scan_for_leaks(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            findings.extend(scan_for_leaks(item, f"{path}[{idx}]"))
    return findings


# ==============================================================================
# 最终流水线：allowlist → 泄漏扫描 → 序列化预算
# ==============================================================================


def finalize_tool_output(tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """W3 工具统一出口：三段流水线，任一失败整体 fail-closed。

    1. allowlist 裁剪（契约外字段丢弃）；
    2. 泄漏扫描（命中即 INTERNAL_ERROR——allowlist 之后的命中意味着
       实现把敏感值放进了白名单字段，属缺陷，不得截断放行）；
    3. 序列化预算（> RESPONSE_MAX_BYTES → RESULT_TOO_LARGE，提示缩小查询）。
    """
    sanitized = apply_output_allowlist(tool_name, payload)
    findings = scan_for_leaks(sanitized)
    if findings:
        # 记录命中类型与路径（不含值本身）；上抛由 server 层渲染固定文案
        raise LeakScanError(findings)
    serialized = json.dumps(sanitized, ensure_ascii=False, default=str)
    if len(serialized.encode("utf-8")) > RESPONSE_MAX_BYTES:
        raise McpToolError(McpErrorCode.RESULT_TOO_LARGE)
    return sanitized


__all__ = [
    "LeakScanError",
    "apply_output_allowlist",
    "finalize_tool_output",
    "is_safe_tracker_domain",
    "redact_free_text",
    "redact_path_to_display",
    "redact_tracker_url",
    "scan_for_leaks",
]
