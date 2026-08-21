# -*- coding: utf-8 -*-
"""
CronTaskExecutor 调度器注册回归测试

【回归】问题2-d：定时任务注册时必须显式传 max_instances=1 + coalesce=True。

根因：database is locked 锁冲突被定时任务补跑风暴放大。
- 原 add_task_to_scheduler 注册 job 时未传 max_instances / coalesce。
- max_instances 默认 1 虽然挡住了同 job 重入，但未显式声明；coalesce 默认 False，
  积压的多次触发会连续补跑，加剧 SQLite 写锁竞争。
- 修复：add_job 时显式传 coalesce=True（积压合并为一次）+ max_instances=1（同任务不重入）。

收敛锚点：scheduler.add_job 的 kwargs 必须含 coalesce=True / max_instances=1。
若有人删掉或改值（如 coalesce=False），此测试立即报红。

【W3-4/P1-05】另覆盖 _execute_task 的六态 outcome 落库映射与 freshness 推进语义：
- skipped 不再丢弃（outcome=skipped + skip_reason）；
- last_success_at 仅当 outcome ∈ {success/partial/no_action} 推进；
- 重入跳过（already_running）也落库。
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.database_result import DatabaseResult
from app.models import (
    OUTCOME_CANCELLED,
    OUTCOME_FAILED,
    OUTCOME_NO_ACTION,
    OUTCOME_PARTIAL,
    OUTCOME_SKIPPED,
    OUTCOME_SUCCESS,
)
import app.tasks.cron_executor as cron_module
from app.tasks.cron_executor import CronTaskExecutor


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
        assert (
            add_job_kwargs.get("coalesce") is True
        ), "coalesce=True 必须显式传：缺则积压触发会连续补跑，加剧 SQLite 写锁竞争"
        # ★ 收敛锚点：max_instances=1 必须显式传（双保险，避免任务重入）
        assert (
            add_job_kwargs.get("max_instances") == 1
        ), "max_instances=1 必须显式传：缺则任务重入会加剧 database is locked"


# ==================== W3-4/P1-05：六态 outcome 落库与 freshness 推进 ====================


class _FakeSessionCtx:
    """模拟 `async with AsyncSessionLocal() as db` 的异步上下文管理器。"""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


class TestExecuteTaskOutcomeMapping:
    """_execute_task 六态 outcome 落库映射与 last_success_at 推进语义（W3-4/P1-05）。"""

    # 固定时钟：断言 freshness 落库参数与 start/end 时间一致
    FIXED_NOW = datetime(2026, 8, 10, 12, 0, 0)

    TASK = {
        "task_id": 1,
        "task_name": "测试任务",
        "task_type": 4,
        "task_code": "test_task_code",
        "executor": "app.tasks.system_tasks.SystemTask",
    }

    def _patch_env(self, monkeypatch, run_script_result, run_script_exc=None):
        """patch 出 _execute_task 的最小执行环境，返回 (captured, freshness_mock)。"""
        captured = {"log_data": None}
        fake_db = MagicMock()
        monkeypatch.setattr(cron_module, "AsyncSessionLocal", lambda: _FakeSessionCtx(fake_db))
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(return_value=DatabaseResult.success_result(self.TASK)),
        )
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "update_task_start_time",
            AsyncMock(return_value=DatabaseResult.success_result(True)),
        )
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "update_task_execution_duration",
            AsyncMock(return_value=DatabaseResult.success_result(True)),
        )
        freshness_mock = AsyncMock(return_value=DatabaseResult.success_result(True))
        monkeypatch.setattr(cron_module.AsyncCronTaskCRUD, "update_task_freshness", freshness_mock)

        async def _capture_log(db, log_data):
            captured["log_data"] = log_data
            return DatabaseResult.success_result(log_data)

        monkeypatch.setattr(cron_module.AsyncTaskLogsCRUD, "create_task_log", AsyncMock(side_effect=_capture_log))

        async def _run_script(self, task):
            if run_script_exc is not None:
                raise run_script_exc
            return run_script_result

        monkeypatch.setattr(CronTaskExecutor, "_run_task_script", _run_script)

        # 固定 datetime.now()，保证 freshness 落库参数可精确断言
        class _FakeDatetime:
            @classmethod
            def now(cls):
                return TestExecuteTaskOutcomeMapping.FIXED_NOW

        monkeypatch.setattr(cron_module, "datetime", _FakeDatetime)

        return captured, freshness_mock

    async def _execute(self, monkeypatch, run_script_result, run_script_exc=None):
        captured, freshness_mock = self._patch_env(monkeypatch, run_script_result, run_script_exc)
        executor = CronTaskExecutor()
        monkeypatch.setattr(executor, "_update_task_status", AsyncMock())
        await executor._execute_task(1)
        return captured, freshness_mock

    @pytest.mark.parametrize(
        "result_dict, expected_outcome, expected_success, expected_skip_reason, advance_success",
        [
            ({"success": True, "log_detail": "成功"}, OUTCOME_SUCCESS, True, None, True),
            ({"success": False, "log_detail": "失败"}, OUTCOME_FAILED, False, None, False),
            (
                {"success": True, "outcome": OUTCOME_PARTIAL, "log_detail": "部分"},
                OUTCOME_PARTIAL,
                True,
                None,
                True,
            ),
            ({"success": True, "skipped": True, "log_detail": "跳过"}, OUTCOME_SKIPPED, True, "resource_busy", False),
            (
                {"success": True, "skipped": True, "skip_reason": "already_running", "log_detail": "重入"},
                OUTCOME_SKIPPED,
                True,
                "already_running",
                False,
            ),
            (
                {"success": True, "outcome": OUTCOME_NO_ACTION, "log_detail": "无变化"},
                OUTCOME_NO_ACTION,
                True,
                None,
                True,
            ),
            (
                {"success": True, "outcome": OUTCOME_CANCELLED, "log_detail": "取消"},
                OUTCOME_CANCELLED,
                True,
                None,
                False,
            ),
        ],
        ids=[
            "success",
            "failed",
            "partial",
            "skipped-default-reason",
            "skipped-explicit-reason",
            "no_action",
            "cancelled",
        ],
    )
    async def test_six_state_outcome_persistence(
        self,
        monkeypatch,
        result_dict,
        expected_outcome,
        expected_success,
        expected_skip_reason,
        advance_success,
    ):
        """六态结果 dict → 日志落库 outcome/skip_reason + freshness 推进语义。"""
        captured, freshness_mock = await self._execute(monkeypatch, result_dict)

        log = captured["log_data"]
        assert log["success"] is expected_success
        assert log["outcome"] == expected_outcome
        assert log["skip_reason"] == expected_skip_reason
        assert log["start_time"] == self.FIXED_NOW
        assert log["end_time"] == self.FIXED_NOW

        # freshness：每次执行更新 attempt 字段，仅数据成功 outcome 推进 last_success_at
        freshness_mock.assert_awaited_once()
        await_args = freshness_mock.await_args
        assert await_args.args[1] == 1, "task_id 为第 2 个位置参数"
        kwargs = await_args.kwargs
        assert kwargs["last_attempt_at"] == self.FIXED_NOW
        assert kwargs["last_outcome"] == expected_outcome
        assert kwargs["last_skip_reason"] == expected_skip_reason
        assert kwargs["advance_success"] is advance_success, (
            f"outcome={expected_outcome} 的 advance_success 应为 {advance_success}（"
            "last_success_at 仅 success/partial/no_action 推进）"
        )
        assert "last_success_at" not in kwargs, "last_success_at 由 CRUD 内部按 advance_success 推进，不应由调用方传入"

    async def test_invalid_outcome_falls_back_to_success_mapping(self, monkeypatch):
        """结果 dict 携带非法 outcome 字符串 → 回退 success 布尔映射（不落脏值）。"""
        captured, freshness_mock = await self._execute(
            monkeypatch, {"success": True, "outcome": "not-a-state", "log_detail": "成功"}
        )

        assert captured["log_data"]["outcome"] == OUTCOME_SUCCESS
        assert captured["log_data"]["skip_reason"] is None
        assert freshness_mock.await_args.kwargs["last_outcome"] == OUTCOME_SUCCESS
        assert freshness_mock.await_args.kwargs["advance_success"] is True

    async def test_exception_maps_to_failed(self, monkeypatch):
        """脚本抛出异常 → success=False + outcome=failed，不推进 last_success_at。"""
        captured, freshness_mock = await self._execute(monkeypatch, None, run_script_exc=RuntimeError("boom"))

        log = captured["log_data"]
        assert log["success"] is False
        assert log["outcome"] == OUTCOME_FAILED
        assert log["skip_reason"] is None
        assert "任务执行异常" in log["log_detail"]
        assert freshness_mock.await_args.kwargs["advance_success"] is False


class TestReentrantSkipRecording:
    """重入跳过（already_running）落库（W3-4/P1-05）。"""

    def _patch_env(self, monkeypatch):
        captured = {"log_data": None}
        fake_db = MagicMock()
        monkeypatch.setattr(cron_module, "AsyncSessionLocal", lambda: _FakeSessionCtx(fake_db))
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(return_value=DatabaseResult.success_result(TestExecuteTaskOutcomeMapping.TASK)),
        )

        async def _capture_log(db, log_data):
            captured["log_data"] = log_data
            return DatabaseResult.success_result(log_data)

        monkeypatch.setattr(cron_module.AsyncTaskLogsCRUD, "create_task_log", AsyncMock(side_effect=_capture_log))
        freshness_mock = AsyncMock(return_value=DatabaseResult.success_result(True))
        monkeypatch.setattr(cron_module.AsyncCronTaskCRUD, "update_task_freshness", freshness_mock)

        class _FakeDatetime:
            @classmethod
            def now(cls):
                return TestExecuteTaskOutcomeMapping.FIXED_NOW

        monkeypatch.setattr(cron_module, "datetime", _FakeDatetime)
        return captured, freshness_mock

    async def test_reentrant_skip_records_log_and_does_not_advance_success(self, monkeypatch):
        """running_tasks 已占用时：落一条 outcome=skipped/already_running 日志，
        success=True（不误判故障），last_success_at 不推进。"""
        captured, freshness_mock = self._patch_env(monkeypatch)
        executor = CronTaskExecutor()
        executor.running_tasks[1] = True  # 模拟上一轮仍在运行

        await executor._execute_task(1)

        log = captured["log_data"]
        assert log is not None, "重入跳过应落库一条日志"
        assert log["success"] is True
        assert log["outcome"] == OUTCOME_SKIPPED
        assert log["skip_reason"] == "already_running"
        assert "[REENTRANT_SKIP]" in log["log_detail"]
        assert log["duration"] == 0

        freshness_mock.assert_awaited_once()
        kwargs = freshness_mock.await_args.kwargs
        assert kwargs["last_outcome"] == OUTCOME_SKIPPED
        assert kwargs["last_skip_reason"] == "already_running"
        assert kwargs["advance_success"] is False

    async def test_reentrant_skip_when_task_missing_silently_returns(self, monkeypatch):
        """任务已被删除时重入跳过：静默返回，不抛异常。"""
        fake_db = MagicMock()
        monkeypatch.setattr(cron_module, "AsyncSessionLocal", lambda: _FakeSessionCtx(fake_db))
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(return_value=DatabaseResult.not_found_result("定时任务不存在")),
        )
        log_mock = AsyncMock()
        monkeypatch.setattr(cron_module.AsyncTaskLogsCRUD, "create_task_log", log_mock)

        executor = CronTaskExecutor()
        executor.running_tasks[1] = True

        await executor._execute_task(1)

        log_mock.assert_not_called()


# ==================== B-2：会话生命周期三段式（greenlet 交错治理） ====================


class TestExecuteTaskSessionLifecycle:
    """_execute_task 三段式会话收敛锚点。

    原实现单个 AsyncSession 跨越任务体执行期（重型任务数分钟），与任务体
    内部各路 DB 写并发交错，是 "greenlet_spawn has not been called" 偶发
    错误的疑似窗口。收敛后：读会话/收尾会话毫秒级关闭，任务体执行期间
    不存在任何打开的会话。
    """

    TASK = TestExecuteTaskOutcomeMapping.TASK

    def _patch_session_factory(self, monkeypatch):
        """AsyncSessionLocal 换成计数工厂：记录当前打开的会话上下文数。"""
        state = {"open": []}

        class _CountingCtx(_FakeSessionCtx):
            async def __aenter__(self):
                state["open"].append(self)
                return await _FakeSessionCtx.__aenter__(self)

            async def __aexit__(self, *exc):
                state["open"].remove(self)
                return await _FakeSessionCtx.__aexit__(self, *exc)

        monkeypatch.setattr(cron_module, "AsyncSessionLocal", lambda: _CountingCtx(MagicMock()))
        return state

    def _patch_cruds(self, monkeypatch, call_order):
        """patch 全部 CRUD 为成功，并记录调用顺序。"""
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(return_value=DatabaseResult.success_result(self.TASK)),
        )
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "update_task_start_time",
            AsyncMock(return_value=DatabaseResult.success_result(True)),
        )

        def _record(name):
            async def _inner(*args, **kwargs):
                call_order.append(name)
                return DatabaseResult.success_result(True)

            return _inner

        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD, "update_task_execution_duration", AsyncMock(side_effect=_record("duration"))
        )
        monkeypatch.setattr(cron_module.AsyncTaskLogsCRUD, "create_task_log", AsyncMock(side_effect=_record("log")))
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD, "update_task_freshness", AsyncMock(side_effect=_record("freshness"))
        )

    async def test_no_open_session_during_task_body(self, monkeypatch):
        """任务体执行期间活跃会话数必须为 0（读会话已在进入任务体前关闭）。"""
        state = self._patch_session_factory(monkeypatch)
        call_order = []
        self._patch_cruds(monkeypatch, call_order)
        body_open_counts = []

        async def _run_script(self_inner, task):
            body_open_counts.append(len(state["open"]))
            return {"success": True, "log_detail": "ok"}

        monkeypatch.setattr(CronTaskExecutor, "_run_task_script", _run_script)
        executor = CronTaskExecutor()
        monkeypatch.setattr(executor, "_update_task_status", AsyncMock())
        await executor._execute_task(1)

        assert body_open_counts == [0], "任务体执行期间不得存在未关闭的 AsyncSession（greenlet 交错窗口）"
        assert state["open"] == [], "执行结束后不得残留打开的会话"

    async def test_finalize_writes_order_and_isolated_session(self, monkeypatch):
        """收尾三写顺序 duration → log → freshness（均在收尾短会话内完成）。"""
        self._patch_session_factory(monkeypatch)
        call_order = []
        self._patch_cruds(monkeypatch, call_order)
        monkeypatch.setattr(
            CronTaskExecutor, "_run_task_script", AsyncMock(return_value={"success": True, "log_detail": "ok"})
        )
        executor = CronTaskExecutor()
        monkeypatch.setattr(executor, "_update_task_status", AsyncMock())
        await executor._execute_task(1)

        assert call_order == ["duration", "log", "freshness"]

    async def test_early_return_still_resets_status_and_running_flag(self, monkeypatch):
        """读取任务失败早退：status=2 复位仍执行（修复旧实现卡"运行中"的存量缺陷）。"""
        self._patch_session_factory(monkeypatch)
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(return_value=DatabaseResult.failure_result("任务不存在")),
        )
        executor = CronTaskExecutor()
        status_mock = AsyncMock()
        monkeypatch.setattr(executor, "_update_task_status", status_mock)

        await executor._execute_task(1)

        statuses = [c.args[1] for c in status_mock.await_args_list]
        assert 1 in statuses, "执行前应写 status=1"
        assert 2 in statuses, "早退路径必须经 finally 复位 status=2（否则任务页永久显示运行中）"
        assert executor.running_tasks.get(1) is False, "早退路径必须清除运行标记"

    async def test_severe_exception_still_finalizes(self, monkeypatch):
        """收尾会话自身异常（严重错误路径）：running 标记仍复位，不抛出。"""
        self._patch_session_factory(monkeypatch)
        # get_cron_task_by_id 抛异常 → 进入外层 except（严重错误日志路径）
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(side_effect=RuntimeError("session broken")),
        )
        executor = CronTaskExecutor()
        monkeypatch.setattr(executor, "_update_task_status", AsyncMock())

        await executor._execute_task(1)  # 不应抛出

        assert executor.running_tasks.get(1) is False


# ==================== B-2 补充：会话事件序列与早退副作用 ====================


class TestExecuteTaskSessionEventSequence:
    """三段式会话的完整事件序列锚点（比"任务体期间计数为 0"更强的时序锁定）。

    期望序列：读会话 open → close → 任务体 body → 收尾会话 open → close。
    若有人把任务体挪回会话内（事件序变为 open→body→close），或收尾
    复用了读会话（少一组 open/close），此用例立即报红。
    """

    def _patch_events(self, monkeypatch):
        events = []

        class _EventCtx(_FakeSessionCtx):
            _seq = 0

            async def __aenter__(self):
                type(self)._seq += 1
                self._tag = type(self)._seq
                events.append(f"open{self._tag}")
                return await _FakeSessionCtx.__aenter__(self)

            async def __aexit__(self, *exc):
                events.append(f"close{self._tag}")
                return await _FakeSessionCtx.__aexit__(self, *exc)

        monkeypatch.setattr(cron_module, "AsyncSessionLocal", lambda: _EventCtx(MagicMock()))
        return events

    async def test_session_lifecycle_event_sequence(self, monkeypatch):
        """读会话关闭后才开始任务体；收尾使用新的独立会话。"""
        events = self._patch_events(monkeypatch)
        call_order = []

        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(return_value=DatabaseResult.success_result(TestExecuteTaskOutcomeMapping.TASK)),
        )
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "update_task_start_time",
            AsyncMock(
                side_effect=lambda *a, **k: call_order.append("start_time") or DatabaseResult.success_result(True)
            ),
        )
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "update_task_execution_duration",
            AsyncMock(side_effect=lambda *a, **k: call_order.append("duration") or DatabaseResult.success_result(True)),
        )
        monkeypatch.setattr(
            cron_module.AsyncTaskLogsCRUD,
            "create_task_log",
            AsyncMock(side_effect=lambda *a, **k: call_order.append("log") or DatabaseResult.success_result(True)),
        )
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "update_task_freshness",
            AsyncMock(
                side_effect=lambda *a, **k: call_order.append("freshness") or DatabaseResult.success_result(True)
            ),
        )

        async def _run_script(self_inner, task):
            call_order.append("body")
            events.append("body")
            return {"success": True, "log_detail": "ok"}

        monkeypatch.setattr(CronTaskExecutor, "_run_task_script", _run_script)

        executor = CronTaskExecutor()
        monkeypatch.setattr(executor, "_update_task_status", AsyncMock())
        await executor._execute_task(1)

        # CRUD 时序：start_time 在读会话内（body 之前），三写在收尾会话内（body 之后）
        assert call_order == ["start_time", "body", "duration", "log", "freshness"]
        # 会话事件完整序列：第一组会话在任务体前关闭，第二组在任务体后开启
        assert events == ["open1", "close1", "body", "open2", "close2"]

    async def test_early_return_creates_no_task_log(self, monkeypatch):
        """读取任务失败早退：不产生任务日志、不执行三写（早退不是一次执行）。"""
        self._patch_events(monkeypatch)
        monkeypatch.setattr(
            cron_module.AsyncCronTaskCRUD,
            "get_cron_task_by_id",
            AsyncMock(return_value=DatabaseResult.failure_result("任务不存在")),
        )
        log_mock = AsyncMock()
        monkeypatch.setattr(cron_module.AsyncTaskLogsCRUD, "create_task_log", log_mock)
        duration_mock = AsyncMock()
        monkeypatch.setattr(cron_module.AsyncCronTaskCRUD, "update_task_execution_duration", duration_mock)

        executor = CronTaskExecutor()
        monkeypatch.setattr(executor, "_update_task_status", AsyncMock())
        await executor._execute_task(1)

        log_mock.assert_not_called()
        duration_mock.assert_not_called()
