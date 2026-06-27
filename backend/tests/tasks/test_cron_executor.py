# -*- coding: utf-8 -*-
"""
CronTaskExecutor 调度器注册回归测试

【回归】问题2-d：定时任务注册时必须显式传 max_instances=1 + coalesce=True。

根因：database is locked 锁冲突被定时任务补跑风暴放大。
- 原 add_task_to_scheduler 注册 job 时未传 max_instances / coalesce。
- max_instances 默认 1 虽然挡住了同 job 重入，但未显式声明；coalesce 默认 False，
  积压的多次触发会连续补跑，加剧 SQLite 写锁竞争。
- 修复：add_job 时显式传 max_instances=1（同任务不重入）+ coalesce=True（积压合并为一次）。

收敛锚点：scheduler.add_job 的 kwargs 必须含 coalesce=True / max_instances=1。
若有人删掉或改值（如 coalesce=False），此测试立即报红。
"""

from unittest.mock import MagicMock

import pytest


class TestCronExecutorCoalesceRegression:
    """【回归】cron job 注册必须含并发保护参数。"""

    @pytest.mark.asyncio
    async def test_add_task_registers_coalesce_and_max_instances(self):
        """add_task_to_scheduler 调 scheduler.add_job 时 kwargs 必须含 coalesce=True, max_instances=1。"""
        from app.tasks.cron_executor import CronTaskExecutor

        executor = CronTaskExecutor()
        # 用 MagicMock 替换真实调度器，避免真的起调度器（只验证注册参数）
        executor.scheduler = MagicMock()
        executor.scheduler.get_job.return_value = None  # 任务不存在，走新增分支

        task = {
            "task_id": 1,
            "task_name": "测试任务",
            "cron_plan": "*/5 * * * *",  # 合法 cron，_parse_cron_plan 会返回真实 trigger
            "task_type": 0,
            "executor": "echo",
        }

        ok = await executor.add_task_to_scheduler(task)
        assert ok is True

        add_job_kwargs = executor.scheduler.add_job.call_args.kwargs

        # ★ 收敛锚点：coalesce=True 必须显式传
        assert add_job_kwargs.get("coalesce") is True, (
            "coalesce=True 必须显式传：缺则积压触发会连续补跑，加剧 SQLite 写锁竞争"
        )
        # ★ 收敛锚点：max_instances=1 必须显式传（双保险，避免任务重入）
        assert add_job_kwargs.get("max_instances") == 1, (
            "max_instances=1 必须显式传：缺则任务重入会加剧 database is locked"
        )
