# -*- coding: utf-8 -*-
"""DashboardStatsJob W1 DB 聚合测试（仪表盘风格改造一期，PLANS/dashboard-redesign-2026-11.md W1）。

覆盖三段新聚合与节流：
- statusBuckets：五桶口径与 report_service._status_bucket 一致（error 优先 → 四主桶
  常量 → other），并通过 /reports/overview statusDist 逐桶对拍钉一致；
- siteBuckets：tracker_host 去端口归一、按种子（info_id）去重计数（一种子多 tracker /
  辅种副本只计一次）、TopN + 其他、软删除行排除；
- tasks.enabled：dr=0 AND enabled=true 的"已启用"口径（决策 #1）；
- 双节流：statusBuckets/enabled 随 60s 主循环每轮聚合，siteBuckets 独立 5min 节流。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.tasks.cron_models import CronTask
from app.tasks.scheduler.dashboard_stats import (
    SITE_BUCKET_INTERVAL_SECONDS,
    SITE_BUCKET_TOP_N,
    DashboardStatsJob,
)
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.reports_fixtures import add_torrent, add_tracker, make_env


# ==================== 共享基建 ====================


async def _make_session(tables):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    return session, engine


async def _add_cron_task(session, *, task_code, enabled=True, dr=0, task_status=0):
    task = CronTask(
        task_name=f"n-{task_code}",
        task_code=task_code,
        task_status=task_status,
        task_type=0,
        executor="echo",
        cron_plan="0 * * * *",
        enabled=enabled,
        dr=dr,
    )
    session.add(task)
    await session.commit()
    return task


class FakeStore:
    """execute 级伪 store（列表构造以复用 job 现有测试形状）。"""

    def __init__(self, downloaders=None):
        self._downloaders = downloaders or [
            SimpleNamespace(nickname="a", fail_time=0, downloading_count=1, seeding_count=2, paused_count=3)
        ]

    async def get_snapshot(self):
        return self._downloaders


class _FakeSessionFactory:
    """替换 AsyncSessionLocal：yield 同一内存库 session（聚合测试可控 DB）。"""

    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


# ==================== 组1：statusBuckets 五桶 ====================


class TestStatusBuckets:
    async def test_mixed_states_and_priority(self):
        """混合状态分桶；has_tracker_error 优先判 error（即使 status=seeding）。"""
        session, engine = await _make_session([TorrentInfo.__table__])
        try:
            job = DashboardStatsJob()
            await add_torrent(session, status="downloading")
            await add_torrent(session, status="stalledUP")  # 集合全小写，须命中 seeding
            await add_torrent(session, status="queuedDL")
            await add_torrent(session, status="seeding", has_tracker_error=True)  # → error 优先
            await add_torrent(session, status="ERROR")  # 大写不敏感
            await add_torrent(session, status="pausedDL")
            await add_torrent(session, status="stopped")  # TR 映射值
            await add_torrent(session, status="weird-future-state")  # → other
            await add_torrent(session, status=None)  # NULL → other
            buckets = await job.aggregate_status_buckets(session)
            assert buckets == {
                "error": 2,
                "downloading": 2,
                "seeding": 1,
                "paused": 2,
                "other": 2,
            }
        finally:
            await session.close()
            await engine.dispose()

    async def test_soft_deleted_and_recycle_excluded(self):
        """dr=1 与回收站（deleted_at 非空）不入桶。"""
        session, engine = await _make_session([TorrentInfo.__table__])
        try:
            job = DashboardStatsJob()
            await add_torrent(session, status="seeding")
            await add_torrent(session, status="seeding", dr=1)
            await add_torrent(session, status="seeding", deleted_at=datetime.now())
            buckets = await job.aggregate_status_buckets(session)
            assert buckets == {"error": 0, "downloading": 0, "seeding": 1, "paused": 0, "other": 0}
        finally:
            await session.close()
            await engine.dispose()

    async def test_matches_reports_overview_status_dist(self):
        """对拍：job 五桶与 /reports/overview statusDist 逐桶一致（同库同数据）。"""
        env = await make_env()
        try:
            await add_torrent(env.session, status="downloading")
            await add_torrent(env.session, status="seeding", has_tracker_error=True)
            await add_torrent(env.session, status="pausedDL")
            await add_torrent(env.session, status="stalledUP")
            await add_torrent(env.session, status=None)
            await add_torrent(env.session, status="seeding", dr=1)  # 双口径都应排除
            r = env.client.get("/api/v1/reports/overview")
            assert r.status_code == 200
            status_dist = {d["bucket"]: d["count"] for d in r.json()["data"]["statusDist"]}
            job = DashboardStatsJob()
            buckets = await job.aggregate_status_buckets(env.session)
            for key, cnt in buckets.items():
                assert status_dist.get(key, 0) == cnt, f"桶 {key} 与报表总览不一致"
        finally:
            await env.close()


# ==================== 组2：siteBuckets 站点分布 ====================


class TestSiteBuckets:
    async def test_multi_tracker_same_host_counts_once(self):
        """一种子多 tracker 同 host：去重后只计 1。"""
        session, engine = await _make_session([TorrentInfo.__table__, TrackerInfo.__table__])
        try:
            job = DashboardStatsJob()
            await add_torrent(session, info_id="i-1", status="seeding")
            # 同 host 多条 announce（UNIQUE(torrent_info_id, tracker_url) 要求 URL 不同）
            await add_tracker(
                session, torrent_info_id="i-1", host="t1.example.com", url="http://t1.example.com/announce"
            )
            await add_tracker(
                session, torrent_info_id="i-1", host="t1.example.com", url="http://t1.example.com/announce2"
            )
            await add_tracker(
                session, torrent_info_id="i-1", host="t1.example.com", url="https://t1.example.com/announce"
            )
            buckets = await job.aggregate_site_buckets(session)
            assert buckets == [{"host": "t1.example.com", "count": 1}]
        finally:
            await session.close()
            await engine.dispose()

    async def test_multi_host_counts_each_and_port_normalized(self):
        """一种子多站各计 1；host:8080 与 host 去端口归一同站合并。"""
        session, engine = await _make_session([TorrentInfo.__table__, TrackerInfo.__table__])
        try:
            job = DashboardStatsJob()
            await add_torrent(session, info_id="i-1", status="seeding")
            await add_tracker(session, torrent_info_id="i-1", host="a.example.com")
            await add_tracker(
                session,
                torrent_info_id="i-1",
                host="a.example.com:8080",
                url="http://a.example.com:8080/announce",
            )
            await add_tracker(session, torrent_info_id="i-1", host="b.example.com")
            buckets = await job.aggregate_site_buckets(session)
            assert buckets == [
                {"host": "a.example.com", "count": 1},
                {"host": "b.example.com", "count": 1},
            ]
        finally:
            await session.close()
            await engine.dispose()

    async def test_auxiliary_seed_copies_count_once(self):
        """辅种副本：同 info_id 跨下载器多行，只按种子计 1。"""
        session, engine = await _make_session([TorrentInfo.__table__, TrackerInfo.__table__])
        try:
            job = DashboardStatsJob()
            await add_torrent(session, info_id="i-dup", downloader_id="dl-1", status="seeding")
            await add_torrent(session, info_id="i-dup", downloader_id="dl-2", status="seeding")
            await add_tracker(session, torrent_info_id="i-dup", host="c.example.com")
            await add_tracker(
                session,
                torrent_info_id="i-dup",
                host="c.example.com",
                url="http://c.example.com/announce2",
            )
            buckets = await job.aggregate_site_buckets(session)
            assert buckets == [{"host": "c.example.com", "count": 1}]
        finally:
            await session.close()
            await engine.dispose()

    async def test_top_n_plus_other_and_sorted_desc(self):
        """TopN 截断 + 其他桶；降序排列。"""
        session, engine = await _make_session([TorrentInfo.__table__, TrackerInfo.__table__])
        try:
            job = DashboardStatsJob()
            hosts = [f"s{i}.example.com" for i in range(SITE_BUCKET_TOP_N + 2)]
            for idx, host in enumerate(hosts):
                # 前 TopN+1 个 host 各 1 个种子，最后 1 个 host 2 个种子 → 排第一
                info_ids = ["x-last-1", "x-last-2"] if idx == len(hosts) - 1 else [f"x-{idx}"]
                for info_id in info_ids:
                    await add_torrent(session, info_id=info_id, status="seeding")
                    await add_tracker(session, torrent_info_id=info_id, host=host)
            buckets = await job.aggregate_site_buckets(session)
            assert len(buckets) == SITE_BUCKET_TOP_N + 1
            assert buckets[0]["host"] == hosts[-1] and buckets[0]["count"] == 2
            # TopN=8 取 s9(2种)+s0..s6(各1种)，其余 s7/s8 两站入 other
            assert buckets[-1]["host"] == "other" and buckets[-1]["count"] == 2
            # 降序（除 other 桶收尾外）
            counts = [b["count"] for b in buckets[:-1]]
            assert counts == sorted(counts, reverse=True)
        finally:
            await session.close()
            await engine.dispose()

    async def test_deleted_rows_excluded(self):
        """tracker dr=1 或种子回收站/软删除的行排除。"""
        session, engine = await _make_session([TorrentInfo.__table__, TrackerInfo.__table__])
        try:
            job = DashboardStatsJob()
            await add_torrent(session, info_id="i-ok", status="seeding")
            await add_tracker(session, torrent_info_id="i-ok", host="ok.example.com")
            await add_tracker(
                session,
                torrent_info_id="i-ok",
                host="dead-tracker.example.com",
                url="http://dead-tracker.example.com/announce",
                dr=1,
            )
            await add_torrent(session, info_id="i-dead", status="seeding", dr=1)
            await add_tracker(session, torrent_info_id="i-dead", host="dead-torrent.example.com")
            await add_torrent(session, info_id="i-recycled", status="seeding", deleted_at=datetime.now())
            await add_tracker(session, torrent_info_id="i-recycled", host="recycled.example.com")
            buckets = await job.aggregate_site_buckets(session)
            assert buckets == [{"host": "ok.example.com", "count": 1}]
        finally:
            await session.close()
            await engine.dispose()


# ==================== 组3：tasks.enabled 启用计数 ====================


class TestEnabledTasks:
    async def test_enabled_only_counts_enabled_alive_rows(self):
        """dr=0 AND enabled=true；disabled 与软删除不计（决策 #1 已启用口径）。"""
        session, engine = await _make_session([CronTask.__table__])
        try:
            job = DashboardStatsJob()
            await _add_cron_task(session, task_code="c-on-1", enabled=True)
            await _add_cron_task(session, task_code="c-on-2", enabled=True)
            await _add_cron_task(session, task_code="c-on-3", enabled=True)
            await _add_cron_task(session, task_code="c-off-1", enabled=False)
            await _add_cron_task(session, task_code="c-off-2", enabled=False)
            await _add_cron_task(session, task_code="c-del", enabled=True, dr=1)
            assert await job.count_enabled_tasks(session) == 3
        finally:
            await session.close()
            await engine.dispose()

    async def test_empty_table_returns_zero(self):
        session, engine = await _make_session([CronTask.__table__])
        try:
            job = DashboardStatsJob()
            assert await job.count_enabled_tasks(session) == 0
        finally:
            await session.close()
            await engine.dispose()


# ==================== 组4：execute 集成与 5min 独立节流 ====================


class TestExecuteThrottling:
    async def test_site_buckets_throttled_other_sections_every_run(self, monkeypatch):
        """60s 主循环内：statusBuckets/enabled 每轮聚合，siteBuckets 5min 节流复用缓存。"""
        session, engine = await _make_session([TorrentInfo.__table__, TrackerInfo.__table__, CronTask.__table__])
        try:
            app = SimpleNamespace(state=SimpleNamespace(store=FakeStore()))
            job = DashboardStatsJob(app)
            monkeypatch.setattr("app.tasks.scheduler.dashboard_stats.AsyncSessionLocal", _FakeSessionFactory(session))
            await add_torrent(session, info_id="i-1", status="seeding")
            await add_tracker(session, torrent_info_id="i-1", host="t.example.com")
            await _add_cron_task(session, task_code="c-1", enabled=True)

            site_calls = []
            original_site = DashboardStatsJob.aggregate_site_buckets

            async def spy_site(self_inner, db):
                site_calls.append(db)
                return await original_site(self_inner, db)

            with patch.object(DashboardStatsJob, "aggregate_site_buckets", spy_site):
                await job.execute(app=app)  # 第 1 轮：全部聚合
                assert len(site_calls) == 1
                stats_1 = dict(app.state.torrent_stats)
                enabled_1 = app.state.dashboard_task_stats["enabled"]

                await job.execute(app=app)  # 第 2 轮：siteBuckets 复用缓存不再查
                assert len(site_calls) == 1, "5min 窗口内 siteBuckets 不应重复聚合"

            stats_2 = app.state.torrent_stats
            assert stats_2["siteBuckets"] == stats_1["siteBuckets"] == [{"host": "t.example.com", "count": 1}]
            assert stats_2["statusBuckets"]["seeding"] == stats_1["statusBuckets"]["seeding"] == 1
            assert app.state.dashboard_task_stats["enabled"] == enabled_1 == 1

            # 回拨节流时间戳超过窗口 → 下一轮重新聚合
            job._last_site_bucket_at -= timedelta(seconds=SITE_BUCKET_INTERVAL_SECONDS + 1)
            await job.execute(app=app)
            assert app.state.torrent_stats["siteBuckets"] == [{"host": "t.example.com", "count": 1}]
        finally:
            await session.close()
            await engine.dispose()

    async def test_db_failure_degrades_without_breaking_main_stats(self, monkeypatch):
        """DB 聚合段异常独立降级：主缓存统计照常，新段取零值/空。"""

        class _BrokenFactory:
            def __call__(self):
                return self

            async def __aenter__(self):
                raise RuntimeError("db down")

            async def __aexit__(self, *args):
                return False

        app = SimpleNamespace(
            state=SimpleNamespace(
                store=FakeStore(
                    [SimpleNamespace(nickname="a", fail_time=0, downloading_count=1, seeding_count=2, paused_count=0)]
                )
            )
        )
        job = DashboardStatsJob(app)
        monkeypatch.setattr("app.tasks.scheduler.dashboard_stats.AsyncSessionLocal", _BrokenFactory())
        result = await job.execute(app=app)
        assert result["status"] == "success"
        stats = app.state.torrent_stats
        assert stats["active"] == 3
        assert stats["statusBuckets"] == {"error": 0, "downloading": 0, "seeding": 0, "paused": 0, "other": 0}
        assert stats["siteBuckets"] == []
        assert app.state.dashboard_task_stats == {"enabled": 0}
