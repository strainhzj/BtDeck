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
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestManualSyncNoLegacyFullBypass:
    """W2-1 架构断言：手动 sync-single 不再直接调用 legacy 全量实现。

    验证目标（P0-01 消除手动同步旁路）：
    - sync_single_downloader 后台执行体经 SyncCoordinator（run_sync 被调）；
    - 调用链中不再出现直接 qb_add_torrents_async / tr_add_torrents_async
      全量函数调用（patch 断言其未被调用）。
    """

    def _make_downloader_row(self):
        downloader = MagicMock()
        downloader.downloader_id = "dl_001"
        downloader.nickname = "test-dl"
        downloader.downloader_type = "qbittorrent"
        downloader.host = "192.168.1.1"
        downloader.port = 8080
        downloader.username = "admin"
        downloader.password = "password"
        downloader.torrent_save_path = "/downloads"
        downloader.enabled = True
        downloader.status = "1"
        return downloader

    async def test_manual_sync_goes_through_coordinator_not_legacy_full(self):
        """手动入口（开关开启）调 run_sync，且不直接调全量 qb/tr_add_torrents_async。"""
        from app.api.endpoints.torrent_sync import SyncSingleRequest, sync_single_downloader
        from app.core.background_task_manager import TaskStatus, task_manager
        from app.core.config import settings
        from app.services.sync_coordinator import SyncResult

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.client.port = 12345
        request.headers = {"user-agent": "test"}
        request.url.path = "/api/v1/torrents/sync-single"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = self._make_downloader_row()

        with (
            patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync,
            patch("app.api.endpoints.torrents_async.qb_add_torrents_async", new=AsyncMock()) as mock_qb_full,
            patch("app.api.endpoints.torrents_async.tr_add_torrents_async", new=AsyncMock()) as mock_tr_full,
            patch.object(settings, "SYNC_CANONICAL_COORDINATOR_ENABLED", True),
            patch(
                "app.api.endpoints.torrent_sync.asyncio.create_task",
                side_effect=lambda coro: asyncio.ensure_future(coro),
            ),
        ):
            mock_run_sync.return_value = SyncResult(outcome="success", run_id="r-arch", message="ok")
            response = await sync_single_downloader(
                request,
                SyncSingleRequest(downloader_id="dl_001"),
                _user=MagicMock(),
                db=db,
            )

            assert response.status == "success"
            task_id = response.data["task_id"]

            # 等待后台执行体完成（patch 上下文内等待，确保断言看到被 patch 的调用）
            task = task_manager.get_task(task_id)
            for _ in range(200):
                if task is not None and task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    break
                await asyncio.sleep(0.01)
                task = task_manager.get_task(task_id)

            # 架构断言 1：手动入口经统一 Coordinator（run_sync 被调、trigger=manual）
            assert mock_run_sync.await_count == 1, "手动入口必须经 SyncCoordinator::run_sync"
            req = mock_run_sync.await_args.args[0]
            assert req.trigger == "manual"
            assert req.sync_type == "full"

            # 架构断言 2：手动入口调用链不再直接出现 legacy 全量函数
            assert mock_qb_full.await_count == 0, "手动入口不得直接调用 qb_add_torrents_async（旁路写者）"
            assert mock_tr_full.await_count == 0, "手动入口不得直接调用 tr_add_torrents_async（旁路写者）"
