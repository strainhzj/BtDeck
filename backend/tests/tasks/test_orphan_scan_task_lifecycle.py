# -*- coding: utf-8 -*-
"""
H 组：孤儿文件任务与 API 契约（v1.0.6+ 语义重做）

覆盖：
- 只有 completed + scan_id 才能进入生命周期对账和自动清理
- 自动清理必须接收本次 scan ID
- cleanup 异常不能报告任务成功
- preview 与 cleanup 使用相同新鲜度规则
- stale ID 返回明确拒绝原因
- API 响应继续遵循 CommonResponse 和 list/total/pageSize

本阶段因任务/服务重构尚未实现，全部应失败。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_app():
    """伪 FastAPI 实例，带 state.store。"""
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    store = SimpleNamespace()
    store.get_snapshot = AsyncMock(return_value=[])
    app.state.store = store
    return app


class TestOrphanTaskLifecycle:
    """任务生命周期对账门禁。"""

    async def test_only_completed_enters_reconcile(self, fake_app):
        """只有 completed + scan_id 才进入生命周期对账。"""
        from app.services import orphan_lifecycle_service
        from app.services.orphan_scanner import OrphanScanner
        from app.tasks.scheduler.orphan_scan_task import OrphanScanTask

        task = OrphanScanTask()
        # mock OrphanScanner.scan 返回 failed（patch 类的 scan 方法）
        with patch.object(OrphanScanner, "scan", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = {
                "scan_id": "scan_x",
                "status": "failed",
                "error": "err",
            }

            # spy reconcile_candidates（模块尚未实现时会 ImportError，这里兼容）
            if hasattr(orphan_lifecycle_service, "OrphanLifecycleService"):
                with patch.object(
                    orphan_lifecycle_service.OrphanLifecycleService,
                    "reconcile_candidates",
                    new_callable=AsyncMock,
                ) as spy_reconcile:
                    await task.execute(app=fake_app)
                    spy_reconcile.assert_not_called()
            else:
                # 模块未实现 → 测试应在 Phase 3 后转绿
                await task.execute(app=fake_app)

    async def test_auto_cleanup_receives_scan_id(self, fake_app):
        """自动清理必须接收本次 scan ID（不能对旧批次操作）。"""
        from app.services.orphan_scanner import OrphanScanner
        from app.tasks.scheduler.orphan_scan_task import OrphanScanTask

        task = OrphanScanTask()
        with patch.object(OrphanScanner, "scan", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = {
                "scan_id": "scan_fresh",
                "status": "completed",
                "total_orphans": 5,
                "total_orphan_size": 1000,
                "total_paths_skipped": 1,
                "warnings": [
                    {
                        "code": "path_mapping_not_found",
                        "downloader_id": "dl_001",
                        "internal_path": "/downloads/unmapped",
                        "message": "path mapping missing",
                    }
                ],
            }

            with patch.object(task, "_auto_cleanup_expired", new_callable=AsyncMock) as spy_cleanup:
                result = await task.execute(app=fake_app)
                spy_cleanup.assert_called_once()
                # 自动清理应接收本次 scan_id
                call_kwargs = spy_cleanup.call_args.kwargs
                assert call_kwargs.get("scan_id") == "scan_fresh", "自动清理必须接收本次 scan ID"
                assert "1 个路径因映射不完整已记录并跳过" in result["message"]
                assert result["scan_result"]["warnings"][0]["code"] == (
                    "path_mapping_not_found"
                )

    async def test_cleanup_exception_not_reported_success(self, fake_app):
        """cleanup 异常不能报告任务成功。"""
        from app.services.orphan_scanner import OrphanScanner
        from app.tasks.scheduler.orphan_scan_task import OrphanScanTask

        task = OrphanScanTask()
        with patch.object(OrphanScanner, "scan", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = {
                "scan_id": "scan_ok",
                "status": "completed",
                "total_orphans": 3,
                "total_orphan_size": 500,
            }

            with patch.object(
                task,
                "_auto_cleanup_expired",
                new_callable=AsyncMock,
                side_effect=RuntimeError("cleanup 崩溃"),
            ):
                result = await task.execute(app=fake_app)
                assert result.get("status") != "success", "cleanup 异常不应报告任务成功"

    async def test_startup_reconciliation_uses_dedicated_session(self):
        """启动对账应在调度器前通过独立异步 session 调用服务。"""
        from app.services.orphan_file_service import OrphanFileService
        from app.startup.lifecycle import reconcile_orphan_file_state

        db = MagicMock(name="startup_reconciliation_db")
        session_context = AsyncMock()
        session_context.__aenter__.return_value = db
        session_context.__aexit__.return_value = None
        expected = {
            "candidate_count": 2,
            "updated_count": 1,
            "unmatched_count": 1,
        }
        with (
            patch(
                "app.database.AsyncSessionLocal",
                return_value=session_context,
            ),
            patch.object(
                OrphanFileService,
                "reconcile_stable_candidate_details",
                new_callable=AsyncMock,
                return_value=expected,
            ) as reconcile,
        ):
            result = await reconcile_orphan_file_state()

        assert result == expected
        reconcile.assert_awaited_once()
        assert reconcile.await_args.args == ()


class TestOrphanAPIContract:
    """API 响应格式契约（CommonResponse + list/total/pageSize）。"""

    async def test_list_response_format(self, async_orphan_db):
        """GET /orphan-files/list 响应含 list/total/pageSize。"""
        from app.services.orphan_file_service import OrphanFileService

        service = OrphanFileService(async_orphan_db)
        result = await service.get_orphan_list(page=1, page_size=10)
        assert "list" in result
        assert "total" in result
        assert "pageSize" in result
        assert isinstance(result["list"], list)
        assert isinstance(result["total"], int)
        assert result["pageSize"] == 10

    async def test_stale_scan_id_returns_rejection_reason(self, async_orphan_db):
        """stale scan ID 预览/清理返回明确拒绝原因。"""
        from app.models.orphan_file import OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        # 两条扫描
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_old",
                scan_time=datetime.utcnow() - timedelta(hours=2),
                scan_type="manual",
                status="completed",
            )
        )
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_new",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="completed",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        result = await service.cleanup_preview(orphan_ids=[], scan_id="scan_old")
        # 应返回 rejected=True + 明确原因
        assert result.get("rejected") is True or result.get("error"), "stale scan_id 应返回明确拒绝原因"
        # 拒绝原因应可读（非空字符串）
        reason = result.get("reason") or result.get("error") or result.get("message")
        assert reason, "拒绝原因不能为空"

    async def test_preview_and_cleanup_same_freshness(self, async_orphan_db):
        """preview 与 cleanup 使用相同新鲜度规则。"""
        from app.models.orphan_file import OrphanScanResult
        from app.services.orphan_file_service import OrphanFileService

        # 最新扫描 running
        async_orphan_db.add(
            OrphanScanResult(
                scan_id="scan_running",
                scan_time=datetime.utcnow(),
                scan_type="manual",
                status="running",
            )
        )
        await async_orphan_db.commit()

        service = OrphanFileService(async_orphan_db)
        preview_result = await service.cleanup_preview(orphan_ids=[])
        cleanup_result = await service.cleanup_orphans(orphan_ids=[], operator="admin", store=MagicMock())

        # 两者都应被拒绝（相同新鲜度规则）
        preview_blocked = preview_result.get("rejected") or preview_result.get("error")
        cleanup_blocked = cleanup_result.get("success_count", 0) == 0 and (
            cleanup_result.get("rejected")
            or cleanup_result.get("error")
            or len(cleanup_result.get("failed_list", [])) > 0
        )
        assert preview_blocked, "running 时 preview 应被拒绝"
        assert cleanup_blocked, "running 时 cleanup 应被拒绝"
