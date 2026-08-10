# -*- coding: utf-8 -*-
"""
定时任务 outcome / 数据新鲜度 API 契约测试（W3-4 / P1-05）

覆盖目标：
- GET /list 与 GET /{task_id} 返回 lastOutcome/lastSuccessfulDataAt/lastAttemptAt/
  lastSkipReason/lastRunId/freshnessSeconds/stale（向后兼容增量）。
- stale 计算：无 last_success_at → stale=True；freshness 超过“2 个调度周期”
  阈值 → stale=True；未超过 → stale=False。
- GET /logs 返回 outcome/skipReason；支持 outcome 过滤；历史记录无 outcome
  （NULL）→ API 返回 null 不报错。
- GET /logs/statistics 口径不变（仍按 success 布尔统计：skipped 计入 success）。

测试基建与 tests/api/test_cron_security_api.py 一致：内存 SQLite + StaticPool，
require_authenticated_user 与 get_db 均 override。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.models import OUTCOME_SKIPPED, OUTCOME_SUCCESS
from app.tasks.cron_models import CronTask
from app.tasks.models import TaskLogs

URL_LIST = "/api/v1/cronTasks/list"
URL_DETAIL = "/api/v1/cronTasks/{task_id}"
URL_LOGS = "/api/v1/cronTasks/logs"
URL_STATS = "/api/v1/cronTasks/logs/statistics"

# 每 5 分钟任务 → 阈值 = 2 × 300 = 600 秒
CRON_EVERY_5_MIN = "*/5 * * * *"


@pytest.fixture
def db_session():
    """同步内存库，建 cron_task + task_logs 表。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[CronTask.__table__, TaskLogs.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client_factory(db_session):
    """返回构造 client 的工厂（get_db / 认证 override，与 security 测试一致）。"""

    def _make_client():
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            db = sessionmaker(bind=db_session.bind)()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
        return TestClient(app, raise_server_exceptions=False)

    return _make_client


def _make_task(db, *, task_code="task_outcome_1", task_name="测试任务", cron_plan=CRON_EVERY_5_MIN, **kwargs):
    """插入一条 CronTask，kwargs 覆盖新鲜度字段。"""
    task = CronTask(
        task_name=task_name,
        task_code=task_code,
        task_type=4,
        executor="app.tasks.system_tasks.SystemTask",
        cron_plan=cron_plan,
        enabled=False,
    )
    for key, value in kwargs.items():
        setattr(task, key, value)
    db.add(task)
    db.commit()
    return task


def _make_log(db, *, task_id=1, task_name="测试任务", success=True, outcome=None, skip_reason=None):
    """插入一条 TaskLogs（outcome/skip_reason 可空，模拟历史记录兼容）。"""
    log = TaskLogs(
        task_id=task_id,
        task_name=task_name,
        task_type=4,
        start_time=datetime(2026, 8, 1, 0, 0, 0),
        end_time=datetime(2026, 8, 1, 0, 0, 10),
        duration=10,
        success=success,
        outcome=outcome,
        skip_reason=skip_reason,
        log_detail="执行日志",
    )
    db.add(log)
    db.commit()
    return log


# ==================== 任务列表/详情：outcome + freshness 字段 ====================


class TestTaskListOutcomeFreshness:
    """GET /list 与 GET /{task_id} 返回 W3-4 增补字段。"""

    def test_list_returns_outcome_and_freshness_fields(self, db_session, client_factory):
        """list 含 lastOutcome/lastSuccessfulDataAt/lastAttemptAt/lastSkipReason/lastRunId/
        freshnessSeconds/stale；无 last_success_at → lastSuccessfulDataAt=null、stale=True。"""
        _make_task(
            db_session,
            last_outcome=OUTCOME_SKIPPED,
            last_skip_reason="resource_busy",
            last_attempt_at=datetime(2026, 8, 10, 10, 0, 0),
            last_run_id="cron-1-20260810100000-abcdef123456",
            last_success_at=None,
        )

        c = client_factory()
        r = c.get(URL_LIST)
        body = r.json()
        assert body["code"] == "200"
        item = body["data"]["list"][0]

        assert item["lastOutcome"] == OUTCOME_SKIPPED
        assert item["lastSkipReason"] == "resource_busy"
        assert item["lastRunId"] == "cron-1-20260810100000-abcdef123456"
        assert item["lastAttemptAt"] == "2026-08-10 10:00:00"
        assert item["lastSuccessfulDataAt"] is None, "无数据成功记录时 lastSuccessfulDataAt 应为 null"
        assert item["freshnessSeconds"] is None, "无数据成功记录时 freshnessSeconds 应为 null"
        assert item["stale"] is True, "无 last_success_at → stale=True"
        # 兼容旧字段保持存在
        assert "cronPlan" in item
        assert item["lastExecuteTime"] is None

    def test_detail_returns_same_shape(self, db_session, client_factory):
        """GET /{task_id} 详情与 list 同一套增补字段。"""
        task = _make_task(db_session, task_code="task_detail_1")

        c = client_factory()
        r = c.get(URL_DETAIL.format(task_id=task.task_id))
        body = r.json()
        assert body["code"] == "200"
        item = body["data"]
        assert item["lastOutcome"] is None
        assert item["lastSkipReason"] is None
        assert item["lastRunId"] is None
        assert item["lastSuccessfulDataAt"] is None
        assert item["stale"] is True


class TestStaleComputation:
    """stale 阈值：2 × 最短 cron 重复间隔；freshness 超阈值 → stale=True。"""

    def test_stale_true_when_freshness_exceeds_threshold(self, db_session, client_factory):
        """last_success_at = 700 秒前（阈值 600 秒）→ stale=True，freshnessSeconds ≈ 700。"""
        task = _make_task(
            db_session,
            task_code="task_stale_over",
            cron_plan=CRON_EVERY_5_MIN,
            last_success_at=datetime.now() - timedelta(seconds=700),
        )

        c = client_factory()
        item = c.get(URL_DETAIL.format(task_id=task.task_id)).json()["data"]
        assert item["stale"] is True, "freshness 超过 2 个调度周期 → stale=True"
        assert 690 <= item["freshnessSeconds"] <= 710, f"freshnessSeconds 应≈700，实际 {item['freshnessSeconds']}"

    def test_not_stale_within_threshold(self, db_session, client_factory):
        """last_success_at = 500 秒前（阈值 600 秒）→ stale=False。"""
        task = _make_task(
            db_session,
            task_code="task_fresh_ok",
            cron_plan=CRON_EVERY_5_MIN,
            last_success_at=datetime.now() - timedelta(seconds=500),
        )

        c = client_factory()
        item = c.get(URL_DETAIL.format(task_id=task.task_id)).json()["data"]
        assert item["stale"] is False, "freshness 未超过 2 个调度周期 → stale=False"
        assert 490 <= item["freshnessSeconds"] <= 510

    def test_slow_cron_gets_longer_threshold(self, db_session, client_factory):
        """日更任务（0 3 * * *，间隔 86400s）在 2 天内的 last_success_at 不 stale。"""
        task = _make_task(
            db_session,
            task_code="task_daily",
            cron_plan="0 3 * * *",
            last_success_at=datetime.now() - timedelta(days=1),
        )

        c = client_factory()
        item = c.get(URL_DETAIL.format(task_id=task.task_id)).json()["data"]
        assert item["stale"] is False, "日更任务 1 天前数据成功不应 stale（阈值≈2 天）"

    def test_unparseable_cron_falls_back_to_config_threshold(self, db_session, client_factory):
        """非法 cron_plan → 兜底 CRON_STALE_THRESHOLD_SECONDS（默认 7200s）。"""
        task = _make_task(
            db_session,
            task_code="task_bad_cron",
            cron_plan="bad cron plan",
            last_success_at=datetime.now() - timedelta(seconds=3600),
        )

        c = client_factory()
        item = c.get(URL_DETAIL.format(task_id=task.task_id)).json()["data"]
        # 3600 < 7200 → 不 stale（兜底阈值生效）
        assert item["stale"] is False


# ==================== 任务日志：outcome/skipReason + 过滤 + 兼容 ====================


class TestTaskLogsOutcome:
    """GET /logs 返回 outcome/skipReason，支持 outcome 过滤，历史 NULL 兼容。"""

    def test_logs_include_outcome_and_skip_reason(self, db_session, client_factory):
        """日志项含 outcome/skipReason（驼峰映射）。"""
        _make_log(db_session, outcome=OUTCOME_SKIPPED, skip_reason="resource_busy")

        c = client_factory()
        body = c.get(URL_LOGS).json()
        assert body["code"] == "200"
        item = body["data"]["list"][0]
        assert item["outcome"] == OUTCOME_SKIPPED
        assert item["skipReason"] == "resource_busy"
        assert item["success"] is True  # skipped 不改变 success 布尔（原语义保留）

    def test_logs_filter_by_outcome(self, db_session, client_factory):
        """outcome 过滤参数：只返回匹配业务结果的日志。"""
        _make_log(db_session, outcome=OUTCOME_SKIPPED, skip_reason="resource_busy")
        _make_log(db_session, outcome=OUTCOME_SUCCESS, skip_reason=None)

        c = client_factory()
        body = c.get(URL_LOGS, params={"outcome": OUTCOME_SKIPPED}).json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["outcome"] == OUTCOME_SKIPPED

        # 不传 outcome 返回全部（兼容旧调用）
        body_all = c.get(URL_LOGS).json()
        assert body_all["data"]["total"] == 2

    def test_old_logs_without_outcome_are_null_compatible(self, db_session, client_factory):
        """历史 task_logs 行（outcome=NULL）→ API 返回 outcome=null，不报错。"""
        _make_log(db_session, outcome=None, skip_reason=None)

        c = client_factory()
        r = c.get(URL_LOGS)
        assert r.status_code == 200
        item = r.json()["data"]["list"][0]
        assert item["outcome"] is None
        assert item["skipReason"] is None

    def test_logs_statistics_keep_success_bool_caliber(self, db_session, client_factory):
        """统计口径不变：仍按 success 布尔（skipped 的 success=True 计入成功）。"""
        _make_log(db_session, outcome=OUTCOME_SUCCESS, skip_reason=None)
        _make_log(db_session, outcome=OUTCOME_SKIPPED, skip_reason="resource_busy")
        _make_log(db_session, outcome="failed", skip_reason=None, success=False)

        c = client_factory()
        body = c.get(URL_STATS).json()
        assert body["code"] == "200"
        stats = body["data"]
        assert stats["totalLogs"] == 3
        assert stats["successLogs"] == 2, "skipped 的 success=True 计入成功（口径兼容，不因 outcome 改变）"
        assert stats["failedLogs"] == 1
