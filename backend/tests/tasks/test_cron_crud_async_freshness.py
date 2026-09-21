# -*- coding: utf-8 -*-
"""update_task_freshness 真实异步会话回归（2026-08-25 MissingGreenlet 修复）。

根因：CronTask.update_time 带 onupdate=func.now()，update_task_freshness 不显式
设置该列，flush 生成的 UPDATE 携带 SQL 表达式后 postfetch 机制将该列标记为
expired（独立于 expire_on_commit=False）。修复前 commit 后 to_dict() 同步访问
触发 refresh SELECT → aiosqlite await_only → MissingGreenlet，被方法内 except
捕获后返回 failure（生产日志"异步更新任务新鲜度失败"，任务页新鲜度停更）。
修复：commit 后显式 await db.refresh(task) 再序列化。

本测试用真实 aiosqlite 内存会话跑完整 commit 路径：修复前 result.success 为
False（MissingGreenlet 被吞），修复后为 True 且 payload 可同步读取 update_time。
"""

from datetime import datetime

from app.tasks.cron_crud_async import AsyncCronTaskCRUD
from app.tasks.cron_models import CronTask


async def _seed_cron_task(db) -> int:
    task = CronTask(
        task_name="新鲜度测试任务",
        task_code="freshness_test_task",
        cron_plan="*/5 * * * *",
        executor="app.tasks.scheduler.torrent_sync.tracker_sync_task.TrackerSyncTask",
        task_type=4,
    )
    db.add(task)
    await db.commit()
    return task.task_id


class TestUpdateTaskFreshnessRealSession:
    async def test_commit_then_to_dict_no_missing_greenlet(self, async_orphan_db):
        """commit 后 to_dict() 不再触发同步惰性加载（MissingGreenlet）。"""
        task_id = await _seed_cron_task(async_orphan_db)

        result = await AsyncCronTaskCRUD.update_task_freshness(
            async_orphan_db,
            task_id,
            last_attempt_at=datetime(2026, 8, 25, 20, 0, 0),
            last_outcome="success",
            last_skip_reason=None,
            last_run_id="cron-1-20260825200000-abcdef123456",
            advance_success=True,
        )

        assert result.success is True, f"不应再触发 MissingGreenlet 被吞为失败: {result.message}"
        payload = result.data
        assert payload is not None
        assert payload["last_outcome"] == "success"
        assert payload["last_run_id"] == "cron-1-20260825200000-abcdef123456"
        # onupdate postfetch 过期列经显式 refresh 后可同步读取
        assert payload["update_time"] is not None

        # 落库校验：last_success_at 已推进
        row = await async_orphan_db.get(CronTask, task_id)
        await async_orphan_db.refresh(row)
        assert row is not None
        assert row.last_success_at == datetime(2026, 8, 25, 20, 0, 0)
        assert row.last_outcome == "success"

    async def test_advance_success_false_keeps_last_success_at(self, async_orphan_db):
        """cancelled/skipped 等 outcome 不推进 last_success_at。"""
        task_id = await _seed_cron_task(async_orphan_db)

        result = await AsyncCronTaskCRUD.update_task_freshness(
            async_orphan_db,
            task_id,
            last_attempt_at=datetime(2026, 8, 25, 20, 5, 0),
            last_outcome="cancelled",
            last_skip_reason=None,
            last_run_id="cron-1-20260825200500-abcdef123456",
            advance_success=False,
        )

        assert result.success is True
        row = await async_orphan_db.get(CronTask, task_id)
        assert row is not None
        assert row.last_success_at is None
        assert row.last_outcome == "cancelled"
