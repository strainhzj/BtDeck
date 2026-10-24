# -*- coding: utf-8 -*-
"""SpeedSamplerJob 行为测试（统计报表 W1，PLANS/statistics-reports.md §6）。

覆盖：
- 采样插入：DB 基准清单对齐（缓存缺失/300s 剔除后仍记零 = 断网采样）、
  is_online 判定不受 fail_time 残留值影响、离线行速度恒 0；
- db_write_scope 合规（_ScopeSpy，参照 test_heavy_task_db_write_governance.py）
  与单轮单 commit；
- 聚合幂等 + online_count=0 → avg=0（在线均值口径）；
- 清理（raw 14d / hourly 730d）；
- store 缺失 skip。

治理说明（sync-db-write-governance 2.1 变更检测豁免理由）：本任务为
append-only 时序写入——每轮行携带新时间戳，数据必然"变化"，无新旧状态
可比对；2.1 条款针对状态镜像类同步（无变化不写库），不适用本场景。
2.2 批量条款由"每轮 add_all 单次 commit"满足（下载器数 ≪ SYNC_DB_COMMIT_BATCH_SIZE）。
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.speed_sample import DownloaderSpeedHourly, DownloaderSpeedSample
from app.tasks.resource_guard import admission_controller
from app.tasks.scheduler.speed_sampler import SpeedSamplerJob

pytestmark = pytest.mark.asyncio


class FakeStore:
    def __init__(self, downloaders):
        self._downloaders = downloaders

    async def get_snapshot(self):
        return self._downloaders


def _vo(downloader_id, *, is_online=True, download_speed=100, upload_speed=200, fail_time=0):
    return SimpleNamespace(
        downloader_id=downloader_id,
        nickname=downloader_id,
        is_online=is_online,
        download_speed=download_speed,
        upload_speed=upload_speed,
        fail_time=fail_time,  # 过时字段：采样判定禁止读取
    )


def _app(store):
    return SimpleNamespace(state=SimpleNamespace(store=store))


class _ScopeSpy:
    """记录 db_write_scope 进入次数的间谍（底层用真实 scope 保持串行化语义）。"""

    def __init__(self):
        self.entered_count = 0
        self._real = admission_controller.db_write_scope

    def install(self, monkeypatch):
        from contextlib import asynccontextmanager

        real_scope = self._real
        spy = self

        @asynccontextmanager
        async def _spied():
            spy.entered_count += 1
            async with real_scope():
                yield

        monkeypatch.setattr(admission_controller, "db_write_scope", _spied)


@pytest.fixture(autouse=True)
def _reset_admission():
    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


@pytest.fixture(autouse=True)
async def _clean_tables():
    """每测试前后清空采样两表与本模块造的下载器行（进程级共享测试库隔离）。"""
    from app.downloader.models import BtDownloaders

    async with AsyncSessionLocal() as db:
        await db.execute(delete(DownloaderSpeedSample))
        await db.execute(delete(DownloaderSpeedHourly))
        await db.execute(delete(BtDownloaders).where(BtDownloaders.downloader_id.like("sampler-dl-%")))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(DownloaderSpeedSample))
        await db.execute(delete(DownloaderSpeedHourly))
        await db.execute(delete(BtDownloaders).where(BtDownloaders.downloader_id.like("sampler-dl-%")))
        await db.commit()


async def _add_downloaders(*ids):
    from app.downloader.models import BtDownloaders

    async with AsyncSessionLocal() as db:
        for i in ids:
            db.add(BtDownloaders(downloader_id=i, nickname=i, host="127.0.0.1", port="8080", enabled=True, dr=0))
        await db.commit()


async def _fetch_samples():
    async with AsyncSessionLocal() as db:
        rows = (
            (await db.execute(select(DownloaderSpeedSample).order_by(DownloaderSpeedSample.downloader_id)))
            .scalars()
            .all()
        )
        return rows


async def _insert_samples(rows):
    async with AsyncSessionLocal() as db:
        db.add_all([DownloaderSpeedSample(**r) for r in rows])
        await db.commit()


# =============================================================================
# 采样插入（DB 基准 + 缓存对齐）
# =============================================================================


class TestSampling:
    async def test_skip_without_store(self):
        """store 未初始化 → skipped，不落库。"""
        job = SpeedSamplerJob()
        result = await job.execute(app=_app(None))
        assert result["status"] == "skipped"
        assert await _fetch_samples() == []

    async def test_db_baseline_alignment_offline_zero_rows(self):
        """DB 基准清单对齐：缓存缺失（含 300s 剔除者）与 is_online=False 都记 online=0 速度 0 行。

        断网采样承诺：下载器被 downloader_cache_sync 剔除缓存后仍持续记零——
        采样基准是 DB 有效清单，不是缓存清单。
        """
        await _add_downloaders("sampler-dl-1", "sampler-dl-2", "sampler-dl-3")
        store = FakeStore(
            [
                _vo("sampler-dl-1", is_online=True, download_speed=100, upload_speed=200),  # 在线记实速
                _vo("sampler-dl-2", is_online=False, download_speed=999, upload_speed=999),  # 在缓存但离线
                # sampler-dl-3：不在缓存（被剔除/冷启动）→ 记零
            ]
        )
        job = SpeedSamplerJob(_app(store))
        result = await job.execute()
        assert result["status"] == "success"

        rows = {r.downloader_id: r for r in await _fetch_samples()}
        assert set(rows) == {"sampler-dl-1", "sampler-dl-2", "sampler-dl-3"}
        # 在线：KB/s × 1024
        assert rows["sampler-dl-1"].online is True
        assert rows["sampler-dl-1"].download_speed == 100 * 1024
        assert rows["sampler-dl-1"].upload_speed == 200 * 1024
        # 在缓存但离线：online=0，速度 0（不用缓存残留速度值）
        assert rows["sampler-dl-2"].online is False
        assert rows["sampler-dl-2"].download_speed == 0
        assert rows["sampler-dl-2"].upload_speed == 0
        # 不在缓存：online=0，速度 0（DB 基准，断网采样）
        assert rows["sampler-dl-3"].online is False
        assert rows["sampler-dl-3"].download_speed == 0
        assert rows["sampler-dl-3"].upload_speed == 0

    async def test_is_online_overrides_stale_fail_time(self):
        """在线判定只认 is_online：fail_time 残留 >0 但 is_online=True 仍记 online=1。"""
        await _add_downloaders("sampler-dl-1")
        store = FakeStore([_vo("sampler-dl-1", is_online=True, fail_time=5, download_speed=10, upload_speed=20)])
        job = SpeedSamplerJob(_app(store))
        await job.execute()

        rows = await _fetch_samples()
        assert len(rows) == 1
        assert rows[0].online is True
        assert rows[0].download_speed == 10 * 1024

    async def test_disabled_or_deleted_downloaders_excluded(self):
        """enabled=0 / dr=1 的下载器不在 DB 基准清单，不采样（即使缓存有）。"""
        from app.downloader.models import BtDownloaders

        async with AsyncSessionLocal() as db:
            db.add(
                BtDownloaders(downloader_id="sampler-dl-off", nickname="off", host="h", port="1", enabled=False, dr=0)
            )
            db.add(
                BtDownloaders(downloader_id="sampler-dl-del", nickname="del", host="h", port="1", enabled=True, dr=1)
            )
            db.add(BtDownloaders(downloader_id="sampler-dl-ok", nickname="ok", host="h", port="1", enabled=True, dr=0))
            await db.commit()

        store = FakeStore(
            [
                _vo("sampler-dl-off", is_online=True),
                _vo("sampler-dl-del", is_online=True),
                _vo("sampler-dl-ok", is_online=True),
            ]
        )
        job = SpeedSamplerJob(_app(store))
        await job.execute()

        rows = await _fetch_samples()
        assert [r.downloader_id for r in rows] == ["sampler-dl-ok"]

    async def test_db_write_scope_and_single_commit(self, monkeypatch):
        """治理断言：单轮采样恰好进入 db_write_scope 一次（= 单次 commit 边界）。"""
        await _add_downloaders("sampler-dl-1", "sampler-dl-2")
        spy = _ScopeSpy()
        spy.install(monkeypatch)
        job = SpeedSamplerJob(_app(FakeStore([_vo("sampler-dl-1"), _vo("sampler-dl-2")])))
        await job.execute()

        assert spy.entered_count == 1, "单轮采样应恰好一次 db_write_scope（add_all 单次 commit）"
        assert len(await _fetch_samples()) == 2

    async def test_no_downloaders_no_commit(self, monkeypatch):
        """零下载器零行零 commit（无数据不进写临界区）。"""
        spy = _ScopeSpy()
        spy.install(monkeypatch)
        job = SpeedSamplerJob(_app(FakeStore([])))
        result = await job.execute()
        assert result["status"] == "success"
        assert spy.entered_count == 0


# =============================================================================
# hourly 聚合（幂等 + 在线均值口径）
# =============================================================================


class TestAggregation:
    async def test_aggregate_online_mean_and_idempotent(self):
        """聚合：avg 分母=online_count、MAX 全样本、幂等（二次运行零新增）。"""
        await _add_downloaders("sampler-dl-1")
        # 上一完整小时：3 行在线（10, 20, 30 KB/s→bytes）+ 2 行离线（0）
        hour = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        base = hour + timedelta(minutes=10)
        rows = [
            dict(
                downloader_id="sampler-dl-1",
                sampled_at=base + timedelta(minutes=i * 5),
                download_speed=s * 1024,
                upload_speed=(s + 1) * 1024,
                online=o,
            )
            for i, (s, o) in enumerate([(10, True), (20, True), (30, True), (0, False), (0, False)])
        ]
        await _insert_samples(rows)

        job = SpeedSamplerJob()
        result = await job._aggregate_hourly(datetime.now())
        assert result["aggregated"] == 1

        async with AsyncSessionLocal() as db:
            agg = (await db.execute(select(DownloaderSpeedHourly))).scalars().all()
        assert len(agg) == 1
        a = agg[0]
        assert a.sample_count == 5
        assert a.online_count == 3
        # avg = 在线样本均值（(10+20+30)/3 = 20 KB/s）
        assert a.avg_download_speed == 20 * 1024
        assert a.avg_upload_speed == 21 * 1024
        assert a.max_download_speed == 30 * 1024
        assert a.max_upload_speed == 31 * 1024

        # 幂等：再次聚合不新增不改动
        result2 = await job._aggregate_hourly(datetime.now())
        assert result2["aggregated"] == 0
        async with AsyncSessionLocal() as db:
            assert len((await db.execute(select(DownloaderSpeedHourly))).scalars().all()) == 1

    async def test_aggregate_all_offline_hour_avg_zero(self):
        """全离线小时：online_count=0 → avg 输出 0（行仍落，携带 sample_count 区分停机）。"""
        await _add_downloaders("sampler-dl-1")
        hour = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        rows = [
            dict(
                downloader_id="sampler-dl-1",
                sampled_at=hour + timedelta(minutes=i),
                download_speed=0,
                upload_speed=0,
                online=False,
            )
            for i in range(3)
        ]
        await _insert_samples(rows)

        job = SpeedSamplerJob()
        await job._aggregate_hourly(datetime.now())

        async with AsyncSessionLocal() as db:
            a = (await db.execute(select(DownloaderSpeedHourly))).scalars().one()
        assert a.online_count == 0
        assert a.sample_count == 3
        assert a.avg_download_speed == 0
        assert a.avg_upload_speed == 0

    async def test_aggregate_skips_incomplete_current_hour(self):
        """未结束的当前小时不聚合（hour < hour_floor 才算完整结束）。"""
        await _add_downloaders("sampler-dl-1")
        now = datetime.now()
        await _insert_samples(
            [
                dict(
                    downloader_id="sampler-dl-1",
                    sampled_at=now,
                    download_speed=5 * 1024,
                    upload_speed=5 * 1024,
                    online=True,
                )
            ]
        )

        job = SpeedSamplerJob()
        result = await job._aggregate_hourly(now)
        assert result["aggregated"] == 0

    async def test_maybe_aggregate_throttled(self):
        """5min 节流：距上次聚合不足间隔时 throttled 不查库。"""
        job = SpeedSamplerJob()
        job._last_aggregate_at = datetime.now() - timedelta(seconds=60)
        result = await job.maybe_aggregate()
        assert result["status"] == "throttled"


# =============================================================================
# 清理（raw 14d / hourly 730d）
# =============================================================================


class TestCleanup:
    async def test_cleanup_raw_retention(self):
        """raw < now-14d 删除；14d 内保留。"""
        now = datetime.now()
        await _insert_samples(
            [
                dict(
                    downloader_id="sampler-dl-1",
                    sampled_at=now - timedelta(days=15),
                    download_speed=1,
                    upload_speed=1,
                    online=True,
                ),
                dict(
                    downloader_id="sampler-dl-1",
                    sampled_at=now - timedelta(days=13),
                    download_speed=1,
                    upload_speed=1,
                    online=True,
                ),
            ]
        )
        job = SpeedSamplerJob()
        result = await job._cleanup_expired(now)
        assert result["raw_deleted"] == 1
        rows = await _fetch_samples()
        assert len(rows) == 1
        assert rows[0].sampled_at > now - timedelta(days=14)

    async def test_cleanup_hourly_retention(self):
        """hourly < now-730d 删除。"""
        now = datetime.now()
        async with AsyncSessionLocal() as db:
            db.add_all(
                [
                    DownloaderSpeedHourly(
                        downloader_id="sampler-dl-1",
                        stat_hour=now - timedelta(days=731),
                        avg_download_speed=1,
                        max_download_speed=1,
                        avg_upload_speed=1,
                        max_upload_speed=1,
                        sample_count=1,
                        online_count=1,
                    ),
                    DownloaderSpeedHourly(
                        downloader_id="sampler-dl-1",
                        stat_hour=now - timedelta(days=729),
                        avg_download_speed=1,
                        max_download_speed=1,
                        avg_upload_speed=1,
                        max_upload_speed=1,
                        sample_count=1,
                        online_count=1,
                    ),
                ]
            )
            await db.commit()

        job = SpeedSamplerJob()
        result = await job._cleanup_expired(now)
        assert result["hourly_deleted"] == 1
        async with AsyncSessionLocal() as db:
            remaining = (await db.execute(select(DownloaderSpeedHourly))).scalars().all()
        assert len(remaining) == 1

    async def test_maybe_cleanup_throttled(self):
        """每日节流。"""
        job = SpeedSamplerJob()
        job._last_cleanup_at = datetime.now() - timedelta(hours=1)
        result = await job.maybe_cleanup()
        assert result["status"] == "throttled"
