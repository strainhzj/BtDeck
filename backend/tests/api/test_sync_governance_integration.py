# -*- coding: utf-8 -*-
"""
sync-resource-governance 阶段 3 集成验证：行为契约测试

【验证目标】
admission_controller 持有 heavy_sync + db_write_scope 期间，请求侧
（DashboardService 查询）仍能正常完成，不被治理锁阻塞。

【设计依据】
- dashboard / torrent list 路径不 import resource_guard（架构约束测试已钉死）
- 治理目标是"不让后台任务挤占请求侧资源"，而非显式锁请求侧
- 纯 asyncio 并发（避开 TestClient 线程安全问题）：
  协程 A 占住 heavy_sync + db_write_scope，协程 B 同事件循环跑 DashboardService.get_dashboard_data()
- TestClient 非线程安全（test_tag_aggregation_api.py:402-411 已记录），不能并发发 HTTP
"""

import asyncio
import time
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.dashboard_service import DashboardService
from app.tasks.cron_models import CronTask
from app.tasks.resource_guard import admission_controller
from app.tasks.task_profiles import get_profile
from app.torrents.audit_models import TorrentAuditLog


@pytest.fixture
async def dashboard_db():
    """异步内存 SQLite，建 cron_task + torrent_audit_log（DashboardService 裸 SQL 查这两张）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [CronTask.__table__, TorrentAuditLog.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=tables))


@pytest.fixture(autouse=True)
def _reset_admission():
    """每个测试前后清理 admission_controller 单例状态。"""
    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


def _make_fake_app():
    """构造带降级 store/torrent_stats 的伪 app（DashboardService 降级路径）。"""
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.start_time = time.time()
    # store=None 触发降级（零值/空列表），不依赖真实下载器缓存
    app.state.store = None
    app.state.torrent_stats = None
    return app


class TestRequestSideNotBlockedByGovernance:
    """请求侧在治理锁持有时仍能查询。"""

    async def test_dashboard_query_during_heavy_sync_hold(self, dashboard_db):
        """heavy_sync 被重型任务持有时，DashboardService 查询正常完成。

        场景：协程 A acquire heavy_sync（模拟 torrent_info_sync 运行中），
        同事件循环协程 B 调 DashboardService.get_dashboard_data()，
        断言 B 不阻塞、返回完整 6 个顶层键。
        """
        app = _make_fake_app()
        # 协程 A：占住 heavy_sync
        task_code = "torrent_info_sync_ac608e4d"
        profile = get_profile(task_code)
        assert profile is not None
        holder = await admission_controller.acquire(task_code, profile)
        assert holder.admitted is True

        try:
            # 协程 B：同事件循环跑 DashboardService（不 release heavy_sync）
            service = DashboardService(dashboard_db, app)
            started = time.monotonic()
            data = await asyncio.wait_for(service.get_dashboard_data(), timeout=5.0)
            elapsed = time.monotonic() - started

            # 关键断言 1：DashboardService 正常返回，不抛超时
            assert isinstance(data, dict)
            # 关键断言 2：6 个顶层键齐全（service 完整执行）
            expected_keys = {
                "downloaders",
                "torrents",
                "tasks",
                "system",
                "downloader_list",
                "activities",
            }
            assert (
                set(data.keys()) == expected_keys
            ), f"DashboardService 返回键不完整：缺 {expected_keys - set(data.keys())}"
            # 关键断言 3：查询耗时远低于 heavy_sync 等待（证明没被锁阻塞）
            # heavy_sync 默认 wait_timeout=30s，dashboard 应在秒级完成
            assert elapsed < 3.0, f"DashboardService 耗时 {elapsed:.2f}s 异常（heavy_sync 持有中应不受影响）"
        finally:
            admission_controller.release(task_code)

    async def test_dashboard_query_during_db_write_scope_hold(self, dashboard_db):
        """db_write_scope 被持有时，DashboardService 查询正常完成。

        场景：协程 A 进入 db_write_scope（占住 db_writer 信号量），
        同事件循环协程 B 调 DashboardService.get_dashboard_data()，
        断言 B 不被 db_writer 阻塞（db_writer 只串行化写者，不阻塞读查询）。
        """
        app = _make_fake_app()

        # 协程 A：占住 db_write_scope（用真实 admission_controller）
        async with admission_controller.db_write_scope():
            # 协程 B：同事件循环跑 DashboardService
            service = DashboardService(dashboard_db, app)
            started = time.monotonic()
            data = await asyncio.wait_for(service.get_dashboard_data(), timeout=5.0)
            elapsed = time.monotonic() - started

            assert isinstance(data, dict)
            assert "downloaders" in data
            # db_writer 只串行化写者，读查询不应被阻塞
            assert elapsed < 3.0, f"DashboardService 耗时 {elapsed:.2f}s 异常（db_write_scope 不应阻塞读）"

    async def test_request_side_does_not_acquire_heavy_sync(self, dashboard_db):
        """DashboardService 路径完全不 acquire heavy_sync 信号量。

        防回归锚点：spy heavy_sync.acquire，跑 DashboardService，
        断言 acquire 未被调用（证明请求侧不碰治理锁）。
        """
        app = _make_fake_app()
        real_sem = admission_controller._state.heavy_sync
        acquire_spy = asyncio.Event()

        original_acquire = real_sem.acquire

        async def spy_acquire():
            acquire_spy.set()  # 标记被调用
            return await original_acquire()

        # 用 monkey patch 替换 acquire（测试结束还原）
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(real_sem, "acquire", spy_acquire)

            service = DashboardService(dashboard_db, app)
            await service.get_dashboard_data()

        # 关键断言：heavy_sync.acquire 在整个 DashboardService 调用期间未被触发
        assert not acquire_spy.is_set(), "DashboardService 路径不应 acquire heavy_sync（请求侧不碰治理锁）"
