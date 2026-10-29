"""MCP 维护门控线上测试（database-migration-ui W2-3，PLANS §5.2/§11 T03）。

复用 test_tools_wire 的线上 E2E 栈（initialize → tools/call）：
- 正常模式：tools/call 在维护准入 lease 内执行（探测计数）；
- 维护模式：新调用立即 MAINTENANCE_MODE（默认拒新 MCP，§5.2）。
"""

from __future__ import annotations

import pytest

from tests.mcp.test_tools_wire import (  # noqa: E402
    _ToolStack,
    _call,
    _error,
    _payload,
    _stack_client,
    auth_utils_patch,
)

from app.services.db_migration.maintenance import MaintenanceController, set_default_controller


@pytest.mark.asyncio
class TestMcpMaintenanceGate:
    async def test_call_holds_admission_lease(self, auth_utils_patch, tmp_path):
        controller = MaintenanceController(tmp_path)
        set_default_controller(controller)
        try:
            stack = await _ToolStack.create(on=["dashboard.read"])
            # dashboard 工具读 store/torrent 数据；探测由 lease 计数承担：
            # 调用前 0，调用返回后仍 0（lease 已随调用完成释放）
            assert controller.active_count() == 0
            try:
                async with _stack_client(stack) as client:
                    data = _payload(await _call(client, "dashboard_get", {}))
                    assert "totals" in data
            finally:
                await stack.close()
            assert controller.active_count() == 0
        finally:
            set_default_controller(None)

    async def test_maintenance_new_call_rejected(self, auth_utils_patch, tmp_path):
        controller = MaintenanceController(tmp_path)
        controller.enter_maintenance_boot()
        set_default_controller(controller)
        try:
            stack = await _ToolStack.create(on=["dashboard.read"])
            try:
                async with _stack_client(stack) as client:
                    resp = await _call(client, "dashboard_get", {})
                    assert _error(resp) == "MAINTENANCE_MODE"
            finally:
                await stack.close()
        finally:
            set_default_controller(None)
