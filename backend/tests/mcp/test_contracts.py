"""MCP 契约完整性测试（feature mcp-service-capabilities-2026-08-28 W0）。

锚定 ``app/mcp/contracts.py`` / ``errors.py`` 与 feature_list.json 的单一事实源：

- 能力目录 ↔ feature_list.json capabilities 完全一致（代码/工具名/风险/默认关闭）；
- 输入契约、输出 allowlist 与目录一一对应，无主体伪造字段；
- 错误码对齐表与默认文案全覆盖；principal 拒绝原因码全部可映射；
- 脱敏字典覆盖计划点名的全部敏感类型（含 §10.1-6 新泄漏面）。

W2/W3 实现层若与契约漂移，这些测试先红。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.mcp import contracts, errors

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FEATURE_LIST = REPO_ROOT / "feature_list.json"
FEATURE_ID = "mcp-service-capabilities-2026-08-28"

EXPECTED_CAPABILITY_CODES = (
    "torrent.advanced_search",
    "torrent.mark_pending_delete",
    "torrent.add",
    "search_template.create",
    "dashboard.read",
    "cron.trigger",
)


def _mcp_feature() -> dict:
    data = json.loads(FEATURE_LIST.read_text(encoding="utf-8"))
    for feature in data["features"]:
        if feature["id"] == FEATURE_ID:
            return feature
    raise AssertionError(f"feature_list.json 缺少 {FEATURE_ID}")


# ==============================================================================
# 能力目录
# ==============================================================================


def test_capability_catalog_matches_feature_list():
    """目录六能力与 feature_list.json 逐字段一致（单一事实源锚定）。"""
    feature = _mcp_feature()
    feature_caps = {c["code"]: c for c in feature["capabilities"]}
    catalog = {spec.code: spec for spec in contracts.CAPABILITY_CATALOG}
    assert set(feature_caps) == set(catalog) == set(EXPECTED_CAPABILITY_CODES)
    for code, spec in catalog.items():
        entry = feature_caps[code]
        assert spec.tool_name == entry["tool"]
        assert spec.risk == entry["risk"]
        assert entry["default_enabled"] is False, f"{code} 在 feature_list 中必须默认关闭"


def test_all_capabilities_default_disabled():
    """G1 代码侧锚点：目录派生的默认状态必须全部关闭。"""
    assert contracts.DEFAULT_CAPABILITY_STATES == {code: False for code in EXPECTED_CAPABILITY_CODES}


def test_write_capabilities_require_confirm_and_idempotency():
    """§4.7：所有写操作（write/high）必须 confirm + 幂等键 + 审计。"""
    for spec in contracts.CAPABILITY_CATALOG:
        if spec.risk in ("write", "high"):
            assert spec.requires_confirm, f"{spec.code} 缺少 confirm 要求"
            assert spec.requires_idempotency_key, f"{spec.code} 缺少幂等键要求"
            assert spec.requires_audit, f"{spec.code} 缺少审计要求"


def test_spec_lookup_rejects_unknown_and_alias():
    """G2：未知能力码/工具名必须抛错——禁止别名或旧名绕过发现门禁。"""
    with pytest.raises(KeyError):
        contracts.spec_by_code("torrent.advanced_search_v0")
    with pytest.raises(KeyError):
        contracts.spec_by_tool_name("torrent_search")  # 旧名/别名不放行


def test_contract_integrity_selfcheck():
    """目录/输入契约/输出 allowlist 三处一一对应。"""
    contracts.validate_contract_integrity()


# ==============================================================================
# 输入契约与输出 allowlist
# ==============================================================================


@pytest.mark.parametrize("tool_name", list(contracts.TOOL_NAMES))
def test_write_tool_inputs_contain_confirm_and_idempotency(tool_name):
    """目录声明 confirm/幂等的能力，其输入契约必须真的包含这两个必填字段。"""
    spec = contracts.spec_by_tool_name(tool_name)
    fields = {f.name: f for f in contracts.TOOL_INPUT_SPECS[tool_name]}
    if spec.requires_confirm:
        assert fields["confirm"].required, f"{tool_name} confirm 必须为必填"
        assert fields["idempotency_key"].required, f"{tool_name} idempotency_key 必须为必填"


def test_page_size_budget_anchored():
    """§4.6：pageSize 默认 20 / 最大 200；响应 1 MiB；等级 4 上限 100。"""
    assert contracts.PAGE_SIZE_DEFAULT == 20
    assert contracts.PAGE_SIZE_MAX == 200
    assert contracts.RESPONSE_MAX_BYTES == 1_048_576
    assert contracts.MARK_PENDING_DELETE_MAX_ITEMS == 100
    assert contracts.TORRENT_UPLOAD_DEFAULT_MAX_BYTES == 10 * 1024 * 1024
    assert contracts.TORRENT_UPLOAD_HARD_MAX_BYTES == 64 * 1024 * 1024


def test_forbidden_arguments_never_in_input_specs():
    """§4.4：user_id/operator/username 不得出现在任何工具输入契约中。"""
    for tool_name, fields in contracts.TOOL_INPUT_SPECS.items():
        for field in fields:
            assert (
                field.name not in contracts.FORBIDDEN_INPUT_ARGUMENTS
            ), f"{tool_name} 输入契约携带主体伪造字段 {field.name}"


def test_output_allowlists_exclude_hash_and_credentials():
    """输出 allowlist 不得出现种子 hash 原值与下载器连接字段（§4.5）。

    按点路径末段精确匹配：path_display（脱敏路径）与 tracker_domains（仅域名）
    是策略允许字段，不得误报。
    """
    forbidden_leaf_fields = {
        "info_hash",
        "hash",
        "password",
        "host",
        "port",
        "url",
        "msg",
        "message",
        "path",  # 原始路径禁止；脱敏形态 path_display 允许
        "token",
        "cookie",
        "username",
    }
    for tool_name, allowlist in contracts.TOOL_OUTPUT_ALLOWLISTS.items():
        for entry in allowlist:
            leaf = entry.rsplit(".", 1)[-1]
            assert leaf not in forbidden_leaf_fields, f"{tool_name} 输出含禁止字段 {entry}"


# ==============================================================================
# 错误码
# ==============================================================================


def test_error_alignment_and_messages_complete():
    """对齐表与默认文案覆盖全部错误码（契约自检不抛错）。"""
    errors.validate_alignment_completeness()


def test_principal_reason_codes_fully_mapped():
    """principal 内核的 5 个拒绝原因码必须全部可映射为 MCP 错误码。"""
    assert set(errors.PRINCIPAL_REASON_TO_ERROR.values()) <= set(errors.all_codes())
    from app.auth import principal

    assert set(errors.PRINCIPAL_REASON_TO_ERROR) == {
        principal.REASON_TOKEN_MISSING,
        principal.REASON_TOKEN_INVALID,
        principal.REASON_USER_NOT_FOUND,
        principal.REASON_USER_INACTIVE,
        principal.REASON_PASSWORD_CHANGE_REQUIRED,
    }


@pytest.mark.parametrize(
    "code",
    [
        "RUNTIME_NOT_READY",
        "CAPABILITY_DISABLED",
        "SERVICE_DISABLED",
        "RESULT_TOO_LARGE",
        "AUTH_REQUIRED",
        "AUTH_USER_INACTIVE",
        "PASSWORD_CHANGE_REQUIRED",
    ],
)
def test_plan_required_error_codes_exist(code):
    """§10.2-2 点名的错误码必须存在且值与名称一致。"""
    assert errors.McpErrorCode[code].value == code


# ==============================================================================
# 脱敏数据字典
# ==============================================================================


def test_redaction_dictionary_covers_required_data_types():
    """脱敏字典必须覆盖计划 §4.5 + §10.1-6 点名的全部敏感类型。"""
    covered = {rule.data_type for rule in contracts.REDACTION_DATA_DICTIONARY}
    required = {
        "tracker_url",
        "tracker_message",
        "absolute_path",
        "downloader_credentials",
        "torrent_hash",
        "audit_metadata",
        "free_text_error",
        "tool_payload_in_logs",
    }
    assert required <= covered, f"脱敏字典缺失: {required - covered}"


def test_redaction_sources_name_new_leak_surfaces():
    """§10.1-6：TrackerMessageLog.msg 与 sample_urls 必须显式入字典。"""
    joined = "\n".join(" ".join(rule.sources) for rule in contracts.REDACTION_DATA_DICTIONARY)
    assert "TrackerMessageLog.msg" in joined
    assert "sample_urls" in joined


def test_config_key_constants():
    """§4.2 配置键常量锚定。"""
    assert contracts.MCP_CONFIG_KEY == "mcp.runtime.v1"
    assert contracts.MCP_CONFIG_SCHEMA_VERSION == 1
    assert contracts.MCP_FORCE_DISABLED_ENV == "BTDECK_MCP_FORCE_DISABLED"
