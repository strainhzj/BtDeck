# -*- coding: utf-8 -*-
"""MCP W3-② 写/高风险工具单元回归（feature mcp-service-capabilities-2026-08-28）。

覆盖 torrent_mark_pending_delete 的逐项/partial/already_marked/幂等语义与
cron_task_trigger 的 allowlist/拒绝码映射/accepted 语义。service 层以
monkeypatch 替身注入（真实 service 行为由其自身测试与 W3-① wire 模式覆盖）；
不依赖 MCP SDK。
"""

from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.principal import AuthenticatedPrincipal
from app.database import Base
from app.mcp import catalog
from app.mcp.catalog import ToolCallContext
from app.mcp.contracts import spec_by_code
from app.mcp.errors import McpErrorCode, McpToolError
from app.mcp.runtime import McpRuntime
from app.mcp.tools.cron import MCP_CRON_TASK_ALLOWLIST
from app.mcp.tools.idempotency import reset_for_tests
from app.mcp.tools.torrents import _map_level4_item_error, _tags_contain
from app.torrents.models import TorrentInfo
from datetime import datetime

MARK_SPEC = spec_by_code("torrent.mark_pending_delete")
CRON_SPEC = spec_by_code("cron.trigger")


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=1, username="admin", is_active=True, must_change_password=False, token="t", payload={}
    )


def _seed_torrent(db, info_id: str, tags: Optional[str]) -> None:
    db.add(
        TorrentInfo(
            info_id,  # info_id
            "1",
            "qbt",
            "42",
            "c" * 40 if info_id == "i-1" else f"{abs(hash(info_id)) % 10**40:040d}",
            f"name-{info_id}",
            r"C:\x",
            1000,
            "seeding",
            100.0,
            None,
            datetime(2026, 9, 8),
            None,
            1.0,
            None,
            tags or "",
            "iso",
            None,
            True,
            datetime(2026, 9, 8),
            "admin",
            datetime(2026, 9, 8),
            "admin",
            0,
        )
    )
    db.commit()


class _FakeAsyncSession:
    async def close(self) -> None:  # pragma: no cover - 占位
        pass


@pytest.fixture
def runtime():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[TorrentInfo.__table__])
    factory = sessionmaker(bind=engine)
    rt = McpRuntime(
        state=None,
        session_factory=factory,
        async_session_factory=lambda: _FakeAsyncSession(),  # type: ignore[arg-type]
        settings_provider=lambda: None,
    )
    rt.mark_ready()
    rt.state = _StateWithStore()
    yield rt, factory
    engine.dispose()


class _StateWithStore:
    store = object()


@pytest.fixture(autouse=True)
def _clean_caches():
    reset_for_tests()
    yield
    reset_for_tests()


@pytest.fixture(autouse=True)
def _no_audit():
    with patch("app.mcp.tools.common.log_tool_audit", new=_capture_audit):
        yield


AUDIT_CALLS: List[Dict[str, Any]] = []


async def _capture_audit(runtime, call_context, principal, detail, result, error_message=None):
    AUDIT_CALLS.append({"detail": detail, "result": result})
    return None


@pytest.fixture(autouse=True)
def _clear_audit_calls():
    AUDIT_CALLS.clear()
    yield


# ==============================================================================
# 标量助手
# ==============================================================================


class TestTagsContain:
    def test_matrix(self):
        assert _tags_contain("pending_delete", "pending_delete") is True
        assert _tags_contain("a, pending_delete ,b", "pending_delete") is True
        assert _tags_contain("pending_delete_x", "pending_delete") is False
        assert _tags_contain("", "pending_delete") is False
        assert _tags_contain(None, "pending_delete") is False


class TestMapItemError:
    def test_not_found(self):
        assert _map_level4_item_error({"error": "种子不存在"}) == "INVALID_ARGUMENT"

    def test_adapter_failure(self):
        assert _map_level4_item_error({"error": "获取适配器失败: x", "operation": "get_adapter"}) == (
            "DOWNSTREAM_FAILURE"
        )
        assert _map_level4_item_error({"error": "下载器不在缓存中", "operation": "add_tag"}) == "DOWNSTREAM_FAILURE"

    def test_unknown_internal(self):
        assert _map_level4_item_error({"error": "weird"}) == "INTERNAL_ERROR"


# ==============================================================================
# torrent_mark_pending_delete
# ==============================================================================


def _mark_args(ids: List[str], confirm: bool = True, key: str = "k1") -> Dict[str, Any]:
    return {"info_ids": ids, "confirm": confirm, "idempotency_key": key}


class TestMarkPendingDelete:
    async def test_already_marked_skips_service(self, runtime):
        from app.mcp.tools.torrents import handle_mark_pending_delete

        rt, factory = runtime
        _seed_torrent(factory(), "i-1", "pending_delete")

        calls: List[str] = []

        class _FakeService:
            LEVEL4_TAG = "pending_delete"

            def __init__(self, db, store=None, audit_context=None):
                pass

            async def delete_by_level(self, info_id, level, operator="admin", audit_service=None):
                calls.append(info_id)
                return {"success": True, "db_update_success": True}

        with patch("app.services.torrent_deletion_by_level.TorrentDeletionByLevelService", _FakeService):
            payload = await handle_mark_pending_delete(
                MARK_SPEC, _principal(), _mark_args(["i-1"]), rt, ToolCallContext()
            )
        assert calls == []  # 已标记不触发下载器调用
        assert payload["already_marked_count"] == 1
        assert payload["result"] == "success"
        assert payload["items"][0]["already_marked"] is True

    async def test_mixed_items_preserve_partial(self, runtime):
        from app.mcp.tools.torrents import handle_mark_pending_delete

        rt, factory = runtime
        _seed_torrent(factory(), "i-ok", None)
        _seed_torrent(factory(), "i-partial", None)
        _seed_torrent(factory(), "i-fail", None)
        _seed_torrent(factory(), "i-marked", "pending_delete")

        results = {
            "i-ok": {"success": True, "db_update_success": True},
            "i-partial": {"success": True, "db_update_success": False},
            "i-fail": {"success": False, "error": "获取适配器失败: x", "operation": "get_adapter"},
        }

        class _FakeService:
            LEVEL4_TAG = "pending_delete"

            def __init__(self, db, store=None, audit_context=None):
                pass

            async def delete_by_level(self, info_id, level, operator="admin", audit_service=None):
                return results[info_id]

        with patch("app.services.torrent_deletion_by_level.TorrentDeletionByLevelService", _FakeService):
            payload = await handle_mark_pending_delete(
                MARK_SPEC,
                _principal(),
                _mark_args(["i-ok", "i-partial", "i-fail", "i-marked", "i-missing"]),
                rt,
                ToolCallContext(),
            )

        assert payload["result"] == "partial"
        assert payload["downloader_success_count"] == 3  # ok + partial + marked
        assert payload["db_success_count"] == 2  # ok + marked（partial 项 DB 失败保留）
        assert payload["already_marked_count"] == 1
        by_id = {item["info_id"]: item for item in payload["items"]}
        assert by_id["i-partial"]["downloader_ok"] is True and by_id["i-partial"]["db_ok"] is False
        assert by_id["i-fail"]["error_code"] == "DOWNSTREAM_FAILURE"
        assert by_id["i-missing"]["error_code"] == "INVALID_ARGUMENT"

    async def test_all_failed(self, runtime):
        from app.mcp.tools.torrents import handle_mark_pending_delete

        rt, factory = runtime
        _seed_torrent(factory(), "i-1", None)

        class _FakeService:
            LEVEL4_TAG = "pending_delete"

            def __init__(self, db, store=None, audit_context=None):
                pass

            async def delete_by_level(self, info_id, level, operator="admin", audit_service=None):
                return {"success": False, "error": "适配器失败", "operation": "add_tag"}

        with patch("app.services.torrent_deletion_by_level.TorrentDeletionByLevelService", _FakeService):
            payload = await handle_mark_pending_delete(
                MARK_SPEC, _principal(), _mark_args(["i-1"]), rt, ToolCallContext()
            )
        assert payload["result"] == "failed"
        assert payload["items"][0]["error_code"] == "DOWNSTREAM_FAILURE"

    async def test_replay_returns_cached_without_service(self, runtime):
        from app.mcp.tools.torrents import handle_mark_pending_delete

        rt, factory = runtime
        _seed_torrent(factory(), "i-1", None)
        calls: List[str] = []

        class _FakeService:
            LEVEL4_TAG = "pending_delete"

            def __init__(self, db, store=None, audit_context=None):
                pass

            async def delete_by_level(self, info_id, level, operator="admin", audit_service=None):
                calls.append(info_id)
                return {"success": True, "db_update_success": True}

        with patch("app.services.torrent_deletion_by_level.TorrentDeletionByLevelService", _FakeService):
            first = await handle_mark_pending_delete(
                MARK_SPEC, _principal(), _mark_args(["i-1"], key="same"), rt, ToolCallContext()
            )
            second = await handle_mark_pending_delete(
                MARK_SPEC, _principal(), _mark_args(["i-1"], key="same"), rt, ToolCallContext()
            )
        assert calls == ["i-1"]  # 第二次命中幂等缓存
        assert second == first
        assert any(c["detail"].get("replay") for c in AUDIT_CALLS)

    async def test_store_missing_runtime_not_ready(self, runtime):
        from app.mcp.tools.torrents import handle_mark_pending_delete

        rt, _ = runtime
        rt.state = type("NoStore", (), {})()  # 无 store 属性
        with pytest.raises(McpToolError) as exc:
            await handle_mark_pending_delete(MARK_SPEC, _principal(), _mark_args(["i-1"]), rt, ToolCallContext())
        assert exc.value.code is McpErrorCode.RUNTIME_NOT_READY

    def test_confirm_and_limit_gates_via_catalog(self):
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("torrent_mark_pending_delete", _mark_args(["i-1"], confirm=False))
        assert exc.value.code is McpErrorCode.CONFIRM_REQUIRED
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("torrent_mark_pending_delete", _mark_args([f"i-{n}" for n in range(101)]))
        assert exc.value.code is McpErrorCode.ITEM_LIMIT_EXCEEDED


# ==============================================================================
# cron_task_trigger
# ==============================================================================


def _cron_args(code: str, confirm: bool = True, key: str = "kc") -> Dict[str, Any]:
    return {"task_code": code, "confirm": confirm, "idempotency_key": key}


class TestCronTrigger:
    async def test_allowlist_gate(self, runtime):
        from app.mcp.tools.cron import handle_cron_trigger

        rt, _ = runtime
        with pytest.raises(McpToolError) as exc:
            await handle_cron_trigger(CRON_SPEC, _principal(), _cron_args("tracker_reannounce"), rt, ToolCallContext())
        assert exc.value.code is McpErrorCode.CRON_TASK_NOT_ALLOWED
        with pytest.raises(McpToolError) as exc:
            await handle_cron_trigger(CRON_SPEC, _principal(), _cron_args("not_a_task"), rt, ToolCallContext())
        assert exc.value.code is McpErrorCode.CRON_TASK_NOT_ALLOWED

    async def test_accepted_returns_null_run_id(self, runtime):
        from app.mcp.tools.cron import handle_cron_trigger

        rt, _ = runtime
        with patch(
            "app.tasks.cron_trigger.trigger_task_by_code",
            new=self_async_return({"accepted": True, "task_id": 7, "reason": "", "message": ""}),
        ):
            payload = await handle_cron_trigger(
                CRON_SPEC, _principal(), _cron_args("torrent_info_sync_ac608e4d"), rt, ToolCallContext()
            )
        assert payload == {"accepted": True, "task_code": "torrent_info_sync_ac608e4d", "run_id": None, "reason": ""}

    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            ("TASK_NOT_FOUND", McpErrorCode.CRON_TASK_NOT_TRIGGERABLE),
            ("TRIGGER_REJECTED", McpErrorCode.CRON_TASK_NOT_TRIGGERABLE),
            ("TASK_TYPE_NOT_ALLOWED", McpErrorCode.CRON_TASK_NOT_ALLOWED),
            ("TASK_NOT_BUILTIN", McpErrorCode.CRON_TASK_NOT_ALLOWED),
            ("TRIGGER_ERROR", McpErrorCode.INTERNAL_ERROR),
        ],
    )
    async def test_rejected_reason_mapping(self, runtime, reason, expected):
        from app.mcp.tools.cron import handle_cron_trigger

        rt, _ = runtime
        with patch(
            "app.tasks.cron_trigger.trigger_task_by_code",
            new=self_async_return({"accepted": False, "reason": reason, "message": "内部细节不外发"}),
        ):
            with pytest.raises(McpToolError) as exc:
                await handle_cron_trigger(
                    CRON_SPEC, _principal(), _cron_args("torrent_info_sync_ac608e4d"), rt, ToolCallContext()
                )
        assert exc.value.code is expected
        assert "内部细节" not in exc.value.message

    async def test_replay_cached(self, runtime):
        from app.mcp.tools.cron import handle_cron_trigger

        rt, _ = runtime
        counter = {"n": 0}

        async def _counting(code, session_factory=None):
            counter["n"] += 1
            return {"accepted": True, "reason": ""}

        with patch("app.tasks.cron_trigger.trigger_task_by_code", new=_counting):
            first = await handle_cron_trigger(
                CRON_SPEC, _principal(), _cron_args("torrent_info_sync_ac608e4d", key="same"), rt, ToolCallContext()
            )
            second = await handle_cron_trigger(
                CRON_SPEC, _principal(), _cron_args("torrent_info_sync_ac608e4d", key="same"), rt, ToolCallContext()
            )
        assert counter["n"] == 1
        assert second == first

    def test_allowlist_subset_of_builtin(self):
        from app.data.default_scheduled_tasks import get_task_by_code

        assert MCP_CRON_TASK_ALLOWLIST, "allowlist 非空"
        for code in MCP_CRON_TASK_ALLOWLIST:
            assert get_task_by_code(code) is not None, f"MCP allowlist 含非内置任务: {code}"
        # 副作用面大的内置任务首版不开放
        for banned in ("tracker_reannounce", "orphan_quarantine_purge", "downloader_path_scan"):
            assert banned not in MCP_CRON_TASK_ALLOWLIST

    def test_confirm_gate_via_catalog(self):
        with pytest.raises(McpToolError) as exc:
            catalog.validate_arguments("cron_task_trigger", _cron_args("x", confirm=False))
        assert exc.value.code is McpErrorCode.CONFIRM_REQUIRED


def self_async_return(value: Dict[str, Any]):
    async def _fake(code: str, session_factory=None):
        return value

    return _fake
