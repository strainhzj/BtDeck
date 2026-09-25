# -*- coding: utf-8 -*-
"""报表·趋势端点回归（B6/B7/B8 + B9 速度历史，统计报表 W3 §6）。

覆盖：月桶边界 / 周桶 %Y-%W Python 分桶 / NULL 过滤 / 未知桶 / 库龄边界 /
B9 拼接缝（hourly 主体 + raw 尾段、含整点后无样本断点语义）/ onlineRatio
「采样期间」语义（online_count=0 的小时 avg=0 输出，行携带 sampleCount/
onlineCount）/ 无样本空态 / downloaderId 过滤 / 已移除下载器标注。
"""

from datetime import datetime, timedelta

import pytest

from app.models.speed_sample import DownloaderSpeedHourly, DownloaderSpeedSample
from tests.api.reports_fixtures import URL_PREFIX, add_downloader, add_torrent, make_env

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def env():
    e = await make_env()
    yield e
    await e.close()


def _trends(env, params=None):
    resp = env.client.get(f"{URL_PREFIX}/trends", params=params or {})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "200"
    return body["data"]


def _speed(env, params=None):
    resp = env.client.get(f"{URL_PREFIX}/speed/history", params=params or {})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "200"
    return body["data"]


async def _add_samples(session, rows):
    session.add_all([DownloaderSpeedSample(**r) for r in rows])
    await session.commit()


async def _add_hourly(session, rows):
    session.add_all([DownloaderSpeedHourly(**r) for r in rows])
    await session.commit()


class TestAddedTrendBuckets:
    async def test_month_bucket_boundary(self, env):
        """月桶边界：1-31 23:59 与 2-1 00:00 分属两桶。"""
        await add_torrent(env.session, info_id="i-1", added_date=datetime(2026, 1, 31, 23, 59), size=10)
        await add_torrent(env.session, info_id="i-2", added_date=datetime(2026, 2, 1, 0, 0), size=20)
        added = _trends(env)["added"]
        by_key = {b["key"]: b for b in added}
        assert by_key["2026-01"] == {"key": "2026-01", "count": 1, "sizeBytes": 10.0}
        assert by_key["2026-02"]["count"] == 1

    async def test_week_bucket_python_strftime(self, env):
        """周桶 %Y-%W（Python 侧分桶；SQLite strftime 无 ISO 周）。"""
        d1 = datetime(2026, 1, 1)  # 周四 → 2026-00
        d2 = datetime(2026, 1, 5)  # 周一 → 2026-01
        await add_torrent(env.session, info_id="i-w1", added_date=d1)
        await add_torrent(env.session, info_id="i-w2", added_date=d2)
        added = _trends(env, {"period": "week"})["added"]
        by_key = {b["key"]: b for b in added}
        assert by_key[d1.strftime("%Y-%W")]["count"] == 1
        assert by_key[d2.strftime("%Y-%W")]["count"] == 1

    async def test_null_added_date_excluded_from_trend(self, env):
        """added_date IS NULL 行过滤（不进趋势桶，进未知库龄桶）。"""
        await add_torrent(env.session, info_id="i-n", added_date=None, size=5)
        data = _trends(env)
        assert data["added"] == []
        assert {b["name"] for b in data["ageBuckets"] if b["count"] > 0} == {"unknown"}

    async def test_limit_caps_buckets(self, env):
        for m in range(1, 15):  # 2025-01 ~ 2026-02 共 14 桶
            await add_torrent(
                env.session, info_id=f"i-m{m}", added_date=datetime(2025 + (m - 1) // 12, ((m - 1) % 12) + 1, 1)
            )
        added = _trends(env, {"limit": 5})["added"]
        assert len(added) == 5
        assert added[0]["key"] == "2025-10"  # 保留最近 5 桶


class TestCompletedTrend:
    async def test_completed_buckets(self, env):
        await add_torrent(env.session, info_id="i-c", completed_date=datetime(2026, 3, 15))
        await add_torrent(env.session, info_id="i-nc", completed_date=None)  # 做种态添加恒空——过滤
        completed = _trends(env)["completed"]
        assert {b["key"]: b["count"] for b in completed} == {"2026-03": 1}


class TestAgeBuckets:
    async def test_age_boundaries(self, env):
        now = datetime.now()
        await add_torrent(env.session, info_id="i-a", added_date=now - timedelta(days=1))  # under7d
        await add_torrent(env.session, info_id="i-b", added_date=now - timedelta(days=10))  # to30d
        await add_torrent(env.session, info_id="i-c", added_date=now - timedelta(days=100))  # to180d
        await add_torrent(env.session, info_id="i-d", added_date=now - timedelta(days=400))  # over1y
        await add_torrent(env.session, info_id="i-e", added_date=None, size=1)  # unknown
        buckets = {b["name"]: b for b in _trends(env)["ageBuckets"]}
        assert buckets["under7d"]["count"] == 1
        assert buckets["to30d"]["count"] == 1
        assert buckets["to90d"]["count"] == 0
        assert buckets["to180d"]["count"] == 1
        assert buckets["over1y"]["count"] == 1
        assert buckets["unknown"]["count"] == 1
        assert buckets["unknown"]["sizeBytes"] == 1.0


class TestSpeedHistory:
    async def test_empty_state(self, env):
        """无样本：series=[] + samplingActive=true + firstSampleAt=null（B9 冷启动空态）。"""
        data = _speed(env)
        assert data["series"] == []
        assert data["samplingActive"] is True
        assert data["firstSampleAt"] is None
        # trends 内嵌同款
        assert _trends(env)["speedHistory"]["series"] == []

    async def test_range_24h_pure_raw_points(self, env):
        """24h 窗口纯 raw 分钟级点位（含离线 0 速点——离线是数据点不是断点）。"""
        now = datetime.now()
        await _add_samples(
            env.session,
            [
                {
                    "downloader_id": "dl-1",
                    "sampled_at": now - timedelta(hours=1),
                    "download_speed": 1024,
                    "upload_speed": 2048,
                    "online": True,
                },
                {
                    "downloader_id": "dl-1",
                    "sampled_at": now - timedelta(minutes=30),
                    "download_speed": 0,
                    "upload_speed": 0,
                    "online": False,
                },
                {
                    "downloader_id": "dl-1",
                    "sampled_at": now - timedelta(hours=30),
                    "download_speed": 99,
                    "upload_speed": 99,
                    "online": True,
                },  # 窗口外
            ],
        )
        data = _speed(env, {"range": "24h"})
        series = data["series"]
        assert len(series) == 1
        points = series[0]["points"]
        assert len(points) == 2
        assert points[0]["downloadSpeed"] == 1024
        assert points[1]["online"] is False
        assert data["firstSampleAt"] is not None

    async def test_range_7d_hourly_body_plus_raw_tail_seam(self, env):
        """7d 窗口：hourly 主体 + raw 尾段拼接（raw >= max(stat_hour)+1h）。"""
        now = datetime.now()
        hour_floor = now.replace(minute=0, second=0, microsecond=0)
        h1 = hour_floor - timedelta(hours=3)
        h2 = hour_floor - timedelta(hours=2)
        await _add_hourly(
            env.session,
            [
                {
                    "downloader_id": "dl-1",
                    "stat_hour": h1,
                    "avg_download_speed": 100,
                    "max_download_speed": 200,
                    "avg_upload_speed": 10,
                    "max_upload_speed": 20,
                    "sample_count": 60,
                    "online_count": 60,
                },
                {
                    "downloader_id": "dl-1",
                    "stat_hour": h2,
                    "avg_download_speed": 0,
                    "max_download_speed": 0,
                    "avg_upload_speed": 0,
                    "max_upload_speed": 0,
                    "sample_count": 60,
                    "online_count": 0,
                },
            ],
        )
        # 尾段：h2 之后 1h 起的 raw（拼接缝：h2 整点后到下一整点前的分钟点）
        tail1 = h2 + timedelta(hours=1) + timedelta(minutes=5)
        await _add_samples(
            env.session,
            [
                {
                    "downloader_id": "dl-1",
                    "sampled_at": tail1,
                    "download_speed": 512,
                    "upload_speed": 64,
                    "online": True,
                },
                # 缝前样本（应被排除，属 h2 小时内、已被 hourly 覆盖）
                {
                    "downloader_id": "dl-1",
                    "sampled_at": h2 + timedelta(minutes=30),
                    "download_speed": 99,
                    "upload_speed": 99,
                    "online": True,
                },
            ],
        )
        data = _speed(env, {"range": "7d"})
        points = data["series"][0]["points"]
        assert len(points) == 3
        # hourly 点携带 sampleCount/onlineCount（供前端区分全离线小时与停机无行）
        assert points[0]["sampleCount"] == 60
        assert points[0]["onlineCount"] == 60
        # online_count=0 的小时：avg 输出 0（不是断点、不缺行）
        assert points[1]["onlineCount"] == 0
        assert points[1]["downloadSpeed"] == 0
        # raw 尾点（h2 后被排除的样本不出现）
        assert points[2]["downloadSpeed"] == 512

    async def test_seven_d_no_hourly_full_raw_window(self, env):
        """7d 无 hourly 行 → raw 全窗口。"""
        now = datetime.now()
        await _add_samples(
            env.session,
            [
                {
                    "downloader_id": "dl-1",
                    "sampled_at": now - timedelta(days=2),
                    "download_speed": 7,
                    "upload_speed": 7,
                    "online": True,
                },
            ],
        )
        data = _speed(env, {"range": "7d"})
        assert len(data["series"][0]["points"]) == 1

    async def test_downloader_filter_and_removed_marker(self, env):
        await add_downloader(env.session, "dl-live", nickname="在册")
        now = datetime.now()
        await _add_samples(
            env.session,
            [
                {
                    "downloader_id": "dl-live",
                    "sampled_at": now - timedelta(minutes=5),
                    "download_speed": 1,
                    "upload_speed": 1,
                    "online": True,
                },
                {
                    "downloader_id": "dl-gone",
                    "sampled_at": now - timedelta(minutes=5),
                    "download_speed": 2,
                    "upload_speed": 2,
                    "online": True,
                },
            ],
        )
        data = _speed(env, {"downloaderId": "dl-gone"})
        assert len(data["series"]) == 1
        assert data["series"][0]["removed"] is True  # 已删下载器历史行保留（标注）
        assert data["series"][0]["nickname"] == "dl-gone"
        # 不过滤时两条序列都在，在册下载器取昵称
        all_data = _speed(env)
        by_id = {s["downloaderId"]: s for s in all_data["series"]}
        assert by_id["dl-live"]["nickname"] == "在册"
        assert by_id["dl-live"]["removed"] is False
