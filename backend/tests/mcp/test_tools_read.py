# -*- coding: utf-8 -*-
"""MCP W3-① 只读工具单元回归（feature mcp-service-capabilities-2026-08-28）。

不依赖 MCP SDK（DTO 映射/条件巡检/confirm 门禁/幂等缓存/错误映射均为
协议无关层；线上 E2E 在 test_tools_wire.py）。
"""

from datetime import datetime
from typing import Any, Dict

import pytest

from app.mcp import catalog
from app.mcp.contracts import PAGE_SIZE_DEFAULT
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.tools.conditions import (
    build_search_request,
    validate_privacy_conditions,
)
from app.mcp.tools.search_templates import (
    _cache_get,
    _cache_put,
    _idempotency_key_digest,
    _reset_idempotency_cache_for_tests,
)
from app.mcp.tools.torrents import _map_search_service_error, _to_search_item


@pytest.fixture(autouse=True)
def _clean_idempotency_cache():
    _reset_idempotency_cache_for_tests()
    yield
    _reset_idempotency_cache_for_tests()


# ==============================================================================
# 搜索 DTO 映射（camelCase VO → 契约 allowlist）
# ==============================================================================


class TestToSearchItem:
    def _row(self) -> Dict[str, Any]:
        return {
            "infoId": "i-1",
            "name": "ubuntu",
            "hash": "a" * 40,
            "savePath": "C:\\Downloads\\iso",
            "size": 1234567,
            "status": "seeding",
            "state": "做种中",
            "category": "iso",
            "tags": "linux",
            "addedDate": datetime(2026, 9, 8, 12, 0, 0),
            "progress": 100.0,
            "downloadSpeed": 1024,
            "uploadSpeed": 2048,
            "errorReason": "downstream text http://admin:x@qbt:8080 failed",
            "trackerInfo": [
                {"trackerUrl": "https://t.example.org:8080/announce?passkey=secret123"},
                {"trackerUrl": "http://other.example.net/announce"},
                {"trackerUrl": "not a url"},
            ],
        }

    def test_mapping_shape(self):
        item = _to_search_item(self._row())
        assert item == {
            "info_id": "i-1",
            "name": "ubuntu",
            "size_bytes": 1234567,
            "progress": 100.0,
            "state": "做种中",
            "category": "iso",
            "tags": "linux",
            "added_at": "2026-09-08T12:00:00",
            "tracker_domains": ["other.example.net", "t.example.org"],
            "path_display": "iso",
            "download_speed": 1024,
            "upload_speed": 2048,
        }

    def test_sensitive_fields_not_constructed(self):
        item = _to_search_item(self._row())
        serialized = repr(item)
        assert "hash" not in item
        assert "save_path" not in item
        assert "errorReason" not in item
        assert "secret123" not in serialized
        assert "a" * 40 not in serialized  # 种子哈希原值不进入 DTO
        assert "admin:x" not in serialized

    def test_empty_row_tolerated(self):
        item = _to_search_item({})
        assert item["info_id"] is None
        assert item["tracker_domains"] == []
        assert item["path_display"] == ""


# ==============================================================================
# 条件隐私巡检与请求构造
# ==============================================================================


class TestPrivacyConditions:
    def test_tracker_msg_condition_rejected(self):
        conditions = {
            "condition_groups": [
                {"logic": "AND", "conditions": [{"field": "tracker_msg", "operator": "contains", "value": "error"}]}
            ]
        }
        with pytest.raises(McpToolError) as exc:
            validate_privacy_conditions(conditions)
        assert exc.value.code is McpErrorCode.INVALID_ARGUMENT

    def test_tracker_url_full_url_rejected(self):
        conditions = {
            "condition_groups": [
                {
                    "logic": "AND",
                    "conditions": [
                        {"field": "tracker_url", "operator": "contains", "value": "https://t.org/announce?passkey=x"}
                    ],
                }
            ]
        }
        with pytest.raises(McpToolError):
            validate_privacy_conditions(conditions)

    def test_tracker_url_bad_operator_rejected(self):
        conditions = {
            "condition_groups": [
                {"logic": "AND", "conditions": [{"field": "tracker_url", "operator": "eq", "value": "t.example.org"}]}
            ]
        }
        with pytest.raises(McpToolError):
            validate_privacy_conditions(conditions)

    def test_tracker_url_domain_with_contains_allowed(self):
        conditions = {
            "condition_groups": [
                {
                    "logic": "AND",
                    "conditions": [{"field": "tracker_url", "operator": "contains", "value": "t.example.org"}],
                }
            ]
        }
        validate_privacy_conditions(conditions)  # 不抛

    def test_template_shaped_conditions_walked(self):
        conditions = {
            "source": "advanced",
            "condition_groups": [
                {"logic": "AND", "conditions": [{"field": "tracker_msg", "operator": "contains", "value": "x"}]}
            ],
        }
        with pytest.raises(McpToolError):
            validate_privacy_conditions(conditions)

    def test_simple_template_without_groups_passes(self):
        validate_privacy_conditions({"source": "simple", "listQuery": {"name": "x"}})


class TestBuildSearchRequest:
    def test_whitelist_copy_and_pagination_mapping(self):
        conditions = {
            "name": "ubuntu",
            "status": "seeding",
            "size_min": "1GB",
            "condition_groups": [
                {
                    "logic": "AND",
                    "conditions": [{"field": "tracker_url", "operator": "contains", "value": "t.example.org"}],
                }
            ],
        }
        request = build_search_request(conditions, page=2, page_size=50)
        assert request["page"] == 2
        assert request["limit"] == 50  # MCP page_size → service limit
        assert request["name"] == "ubuntu"
        assert "condition_groups" in request

    def test_unknown_top_level_key_rejected(self):
        with pytest.raises(McpToolError) as exc:
            build_search_request({"surprise": 1}, page=1, page_size=PAGE_SIZE_DEFAULT)
        assert exc.value.code is McpErrorCode.INVALID_ARGUMENT

    def test_forbidden_identity_inside_conditions_not_applicable(self):
        # user_id 不在白名单 → 未知键拒绝（主体伪造在参数层已被 FORBIDDEN_ARGUMENT 拦）
        with pytest.raises(McpToolError):
            build_search_request({"user_id": 7}, page=1, page_size=20)


# ==============================================================================
# confirm 门禁与幂等缓存
# ==============================================================================


class TestConfirmGate:
    def test_write_tool_requires_true_confirm(self):
        args = {"name": "t", "conditions": {}, "confirm": False, "idempotency_key": "k"}
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("advanced_search_template_create", args)
        assert exc.value.code is McpErrorCode.CONFIRM_REQUIRED

    def test_missing_confirm_same_error(self):
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("advanced_search_template_create", {"name": "t", "conditions": {}})
        # confirm 缺失先命中 required 校验（INVALID_ARGUMENT），显式 false 才是 CONFIRM_REQUIRED
        assert exc.value.code is McpErrorCode.INVALID_ARGUMENT

    def test_read_tool_not_gated(self):
        normalized = catalog.validate_arguments("torrent_advanced_search", {"conditions": {}})
        assert "confirm" not in normalized


class TestIdempotencyCache:
    def test_same_key_returns_first_result(self):
        key = ("tool", 1, "k-1")
        _cache_put(key, {"created": True})
        assert _cache_get(key) == {"created": True}

    def test_different_principal_isolated(self):
        _cache_put(("tool", 1, "k-1"), {"created": True})
        assert _cache_get(("tool", 2, "k-1")) is None

    def test_digest_is_irreversible_prefix(self):
        digest = _idempotency_key_digest("secret-idempotency-key")
        assert len(digest) == 16
        assert "secret" not in digest


class TestServiceErrorMapping:
    def test_422_maps_invalid_argument(self):
        err = _map_search_service_error({"status": "failed", "code": "422", "msg": "条件无效: name 太长"})
        assert err.code is McpErrorCode.INVALID_ARGUMENT
        assert "条件无效" not in err.message  # 上游 msg 不透传

    def test_other_codes_map_internal_error(self):
        err = _map_search_service_error({"status": "failed", "code": "500", "msg": "sqlite locked at C:\\db"})
        assert err.code is McpErrorCode.INTERNAL_ERROR
        assert "sqlite" not in err.message


class TestHandlerRegistration:
    def test_three_read_tools_registered(self):
        from app.mcp.server import create_mcp_server_bundle

        bundle = create_mcp_server_bundle(None)
        names = catalog.TOOL_HANDLERS.registered_names()
        assert "torrent_advanced_search" in names
        assert "advanced_search_template_create" in names
        assert "dashboard_get" in names
        # W3-②/③ 工具尚未注册
        assert "cron_task_trigger" not in names
        assert "torrent_mark_pending_delete" not in names
        assert bundle.server.name == "BtDeck"
