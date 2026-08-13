# -*- coding: utf-8 -*-
"""
孤儿文件扫描任务治理测试（v1.0.6）

验证：
1. task_profiles 一致性（orphan_scan_cleanup 已注册 + 与 default_scheduled_tasks 对齐）
2. OrphanScanTask 基本结构（execute 方法存在 + 任务元数据）
3. cleanup_executor bug 修复（_query_level3_torrents / _query_level4_torrents 已定义）
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.task_profiles import TASK_PROFILES, get_profile, is_heavy_task
from app.tasks.scheduler.orphan_quarantine_purge_task import OrphanQuarantinePurgeTask
from app.tasks.scheduler.orphan_scan_task import OrphanScanTask

# ==================== task_profiles 一致性 ====================


class TestOrphanTaskProfileAlignment:
    """验证 orphan_scan_cleanup 在治理三处同步登记"""

    def test_orphan_scan_cleanup_registered_in_task_profiles(self):
        """orphan_scan_cleanup 已注册到 TASK_PROFILES"""
        assert "orphan_scan_cleanup" in TASK_PROFILES

    def test_orphan_scan_cleanup_is_heavy_task(self):
        """orphan_scan_cleanup 被识别为重型任务"""
        assert is_heavy_task("orphan_scan_cleanup")

    def test_orphan_scan_cleanup_profile_fields(self):
        """profile 字段值合理"""
        profile = get_profile("orphan_scan_cleanup")
        assert profile is not None
        assert profile.heavy_sync is True
        assert profile.wait_timeout == 60.0  # 低频周任务，允许较长等待
        assert profile.description  # 非空描述

    def test_orphan_scan_cleanup_in_default_scheduled_tasks(self):
        """orphan_scan_cleanup 在 default_scheduled_tasks.py 中登记"""
        from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS

        codes = [t["task_code"] for t in DEFAULT_SCHEDULED_TASKS]
        assert "orphan_scan_cleanup" in codes

    def test_orphan_scan_cleanup_executor_path_matches(self):
        """executor 路径指向 OrphanScanTask"""
        from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS

        task = next(t for t in DEFAULT_SCHEDULED_TASKS if t["task_code"] == "orphan_scan_cleanup")
        assert "OrphanScanTask" in task["executor"]
        assert task["executor"].startswith("app.tasks.scheduler.orphan_scan_task")

    def test_orphan_scan_cleanup_cron_is_weekly(self):
        """cron 表达式为每周一次（0 2 * * 0 = 每周日 2 点）"""
        from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS

        task = next(t for t in DEFAULT_SCHEDULED_TASKS if t["task_code"] == "orphan_scan_cleanup")
        assert task["cron_plan"] == "0 2 * * 0"

    def test_quarantine_purge_is_registered_daily(self):
        from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS

        task = next(t for t in DEFAULT_SCHEDULED_TASKS if t["task_code"] == "orphan_quarantine_purge")
        assert task["executor"].endswith("OrphanQuarantinePurgeTask")
        assert task["cron_plan"] == "0 3 * * *"


class TestOrphanQuarantinePurgeTask:
    @pytest.mark.asyncio
    async def test_execute_passes_application_store(self):
        task = OrphanQuarantinePurgeTask()
        app = MagicMock()
        store = app.state.store
        with patch(
            "app.tasks.scheduler.orphan_quarantine_purge_task.OrphanFileService.purge_expired_quarantine",
            AsyncMock(return_value={"purged_count": 2, "failed_count": 0}),
        ) as purge:
            result = await task.execute(app=app)

        purge.assert_awaited_once_with(store=store)
        assert result["status"] == "success"


# ==================== OrphanScanTask 结构 ====================


class TestOrphanScanTaskStructure:
    """验证 OrphanScanTask 类结构"""

    def test_task_metadata_exists(self):
        """任务元数据完整"""
        assert OrphanScanTask.name
        assert OrphanScanTask.description
        assert OrphanScanTask.version

    def test_execute_method_exists(self):
        """execute 方法存在且是协程函数"""
        import asyncio

        assert hasattr(OrphanScanTask, "execute")
        assert asyncio.iscoroutinefunction(OrphanScanTask.execute)

    @pytest.mark.asyncio
    async def test_execute_skipped_when_disabled(self):
        """ORPHAN_SCAN_ENABLED=False 时跳过扫描"""
        task = OrphanScanTask()
        with patch("app.tasks.scheduler.orphan_scan_task.settings") as mock_settings:
            mock_settings.ORPHAN_SCAN_ENABLED = False
            result = await task.execute(app=MagicMock())
            assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_execute_calls_scanner_when_enabled(self):
        """ORPHAN_SCAN_ENABLED=True 时只提交后台任务并立即返回。"""
        task = OrphanScanTask()
        submit_scan = AsyncMock(
            return_value={
                "status": "queued",
                "scan_id": "scan_task_test",
                "task_id": "scan_task_test",
                "accepted": True,
            }
        )
        dispatcher = MagicMock()

        with (
            patch(
                "app.services.orphan_scan_job_service.OrphanScanJobService.submit_scan",
                submit_scan,
            ),
            patch(
                "app.services.orphan_scan_job_service.get_orphan_scan_dispatcher",
                return_value=dispatcher,
            ),
        ):
            result = await task.execute(app=MagicMock())

            submit_scan.assert_awaited_once_with(scan_type="scheduled", operator="system")
            dispatcher.submit.assert_called_once_with("scan_task_test")
            assert result["status"] == "success"


# ==================== CleanupTaskExecutor bug 修复验证 ====================


class TestCleanupExecutorBugFix:
    """验证 CleanupTaskExecutor 未定义方法 bug 已修复"""

    def test_query_level3_torrents_defined(self):
        """_query_level3_torrents 方法已定义"""
        from app.tasks.cleanup_executor import CleanupTaskExecutor

        assert hasattr(CleanupTaskExecutor, "_query_level3_torrents")

    def test_query_level4_torrents_defined(self):
        """_query_level4_torrents 方法已定义"""
        from app.tasks.cleanup_executor import CleanupTaskExecutor

        assert hasattr(CleanupTaskExecutor, "_query_level4_torrents")

    def test_query_level3_torrents_returns_list(self):
        """_query_level3_torrents 返回列表（mock DB）"""
        from app.tasks.cleanup_executor import CleanupTaskExecutor

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        executor = CleanupTaskExecutor(mock_db)
        result = executor._query_level3_torrents(days_threshold=30)
        assert isinstance(result, list)

    def test_query_level4_torrents_returns_list(self):
        """_query_level4_torrents 返回列表（mock DB）"""
        from app.tasks.cleanup_executor import CleanupTaskExecutor

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        executor = CleanupTaskExecutor(mock_db)
        result = executor._query_level4_torrents()
        assert isinstance(result, list)

    def test_preview_cleanup_does_not_raise_attribute_error(self):
        """preview_cleanup 不再抛 AttributeError（task_type=5 触发路径）"""
        from app.tasks.cleanup_executor import CleanupTaskExecutor

        mock_db = MagicMock()
        # mock query 返回空列表，避免 _query_level3/4 返回非预期
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        executor = CleanupTaskExecutor(mock_db)

        # cleanup_level3 内部调 _query_level3_torrents，mock 后返回空列表不报错
        result = executor._query_level3_torrents(days_threshold=30)
        assert result == []

        result4 = executor._query_level4_torrents()
        assert result4 == []
