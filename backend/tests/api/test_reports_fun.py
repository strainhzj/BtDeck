# -*- coding: utf-8 -*-
"""报表·趣味端点回归（24/25/26/27，统计报表 W3 §6）。

覆盖：勋章半开区间边界（1/10/50/200 断点两侧）/ 蓝光换算 / 火种 min 非
NULL + 全 NULL 排除 + -1 不误判（W2 已归一 NULL）/ 上传估算 NULL 剔除与
做种桶限定 / 年度 NULL 排除 / 白嫖慈善榜排序 / year 参数校验。
"""

from datetime import datetime

import pytest

from app.services.report_service import BYTES_PER_BLURAY, BYTES_PER_HD_MOVIE, _badge_tier
from tests.api.reports_fixtures import URL_PREFIX, add_torrent, add_tracker, make_env

pytestmark = pytest.mark.asyncio

TB = 1024**4


@pytest.fixture
async def env():
    e = await make_env()
    yield e
    await e.close()


def _summary(env):
    resp = env.client.get(f"{URL_PREFIX}/fun/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "200"
    return body["data"]


def _yearly(env, year):
    resp = env.client.get(f"{URL_PREFIX}/fun/yearly", params={"year": year})
    assert resp.status_code == 200
    return resp.json()


class TestBadgeTiers:
    """决策 9 半开区间 [lo, hi) TB：[0,1) 铜 / [1,10) 银 / [10,50) 金 / [50,200) 白金 / [200,∞) 钻。"""

    def test_boundaries_unit(self):
        assert _badge_tier(0)[0] == "bronze"
        assert _badge_tier(TB - 1)[0] == "bronze"  # 1TB 断点下侧 → 铜
        assert _badge_tier(TB)[0] == "silver"  # 1TB 断点上侧 → 银
        assert _badge_tier(10 * TB - 1)[0] == "silver"
        assert _badge_tier(10 * TB)[0] == "gold"
        assert _badge_tier(50 * TB - 1)[0] == "gold"
        assert _badge_tier(50 * TB)[0] == "platinum"
        assert _badge_tier(200 * TB - 1)[0] == "platinum"  # v2 的 200-500 空档已消除
        assert _badge_tier(200 * TB)[0] == "diamond"
        assert _badge_tier(500 * TB)[0] == "diamond"

    async def test_endpoint_badge_and_equivalents(self, env):
        """端到端：做种桶 size×ratio 估算 → 勋章 + 换算（8GB 电影 / 40GB 蓝光 / 30GB 剧集）。"""
        # 1 个做种种子：size=2TB ratio=1 → 估算 2TB → 银
        await add_torrent(env.session, info_id="b-1", status="seeding", ratio=1.0, size=2 * TB)
        badges = _summary(env)["badges"]
        assert badges["uploadedBytes"] == pytest.approx(2 * TB)
        assert badges["currentTier"] == "silver"
        assert badges["nextTier"] == "gold"
        assert badges["nextTierAtTB"] == 10
        assert badges["equivalents"]["movies"] == int(2 * TB // BYTES_PER_HD_MOVIE)  # 256 部高清电影
        assert badges["equivalents"]["blurays"] == int(2 * TB // BYTES_PER_BLURAY)  # 51 部蓝光

    async def test_upload_estimate_scope(self, env):
        """估算限定做种桶且 ratio 非 NULL：暂停/错误桶种子与 NULL ratio 种子不参与。"""
        await add_torrent(env.session, info_id="u-1", status="seeding", ratio=2.0, size=TB)  # 计 2TB
        await add_torrent(env.session, info_id="u-2", status="seeding", ratio=None, size=10 * TB)  # NULL 剔除
        await add_torrent(env.session, info_id="u-3", status="paused", ratio=9.0, size=10 * TB)  # 非做种桶剔除
        await add_torrent(
            env.session, info_id="u-4", status="seeding", has_tracker_error=True, ratio=9.0, size=10 * TB
        )  # 错误桶优先剔除
        badges = _summary(env)["badges"]
        assert badges["uploadedBytes"] == pytest.approx(2 * TB)


class TestGuardian:
    async def test_min_seeder_fire_detection(self, env):
        """每种子取 trackers 最小非 NULL seeder_count；≤2 即火种；全 NULL 种子排除。"""
        await add_torrent(env.session, info_id="g-1", name="火种种", size=10)
        await add_tracker(env.session, torrent_info_id="g-1", host="a.example.com", seeder=5)
        await add_tracker(env.session, torrent_info_id="g-1", host="b.example.com", seeder=1)  # min=1 → 火
        await add_torrent(env.session, info_id="g-2", name="健康种", size=20)
        await add_tracker(env.session, torrent_info_id="g-2", host="a.example.com", seeder=3)  # min=3 → 非火
        await add_torrent(env.session, info_id="g-3", name="无计数种", size=30)
        await add_tracker(env.session, torrent_info_id="g-3", host="a.example.com", seeder=None)  # 全 NULL → 排除
        guardian = _summary(env)["guardian"]
        assert guardian["totalConsidered"] == 2
        assert guardian["excludedCount"] == 1
        assert guardian["fireCount"] == 1
        assert guardian["top10"][0]["minSeeders"] == 1

    async def test_null_minus_one_not_fire(self, env):
        """-1 哨兵在 W2 同步路径已归一 NULL——不参与 min、不误判火种（锁住决策 6 归一口径）。"""
        await add_torrent(env.session, info_id="g-4", name="哨兵种", size=10)
        await add_tracker(env.session, torrent_info_id="g-4", host="a.example.com", seeder=None)  # 库内即 NULL
        await add_tracker(env.session, torrent_info_id="g-4", host="b.example.com", seeder=1)
        guardian = _summary(env)["guardian"]
        # min(非NULL) = 1 → 火种（NULL 不压低判定）
        assert guardian["fireCount"] == 1


class TestShamePride:
    async def test_ordering_and_null_excluded(self, env):
        await add_torrent(env.session, info_id="r-1", ratio=0.1, size=10)
        await add_torrent(env.session, info_id="r-2", ratio=9.9, size=20)
        await add_torrent(env.session, info_id="r-3", ratio=None, size=30)  # NULL 排除
        data = _summary(env)
        # NULL 排除：仅两行入榜（最低升序 / 最高降序）
        assert [x["ratio"] for x in data["shame"]] == [0.1, 9.9]
        assert [x["ratio"] for x in data["pride"]] == [9.9, 0.1]
        assert data["shame"][0]["sizeBytes"] == 10.0


class TestYearly:
    async def test_year_null_excluded_and_fields(self, env):
        now = datetime.now()
        year = now.year
        # 本年：3 月 5 日 2 个、3 月 6 日 1 个
        await add_torrent(env.session, info_id="y-1", added_date=datetime(year, 3, 5), size=10)
        await add_torrent(env.session, info_id="y-2", added_date=datetime(year, 3, 5), size=20)
        await add_torrent(env.session, info_id="y-3", added_date=datetime(year, 3, 6), size=30)
        # NULL added_date 行全部排除
        await add_torrent(env.session, info_id="y-null", added_date=None, size=999)
        # 元老：去年添加仍在做种
        elder_added = datetime(year - 1, 6, 1)
        await add_torrent(env.session, info_id="y-elder", added_date=elder_added, status="seeding", name="元老")
        # 元老站点体积
        await add_tracker(env.session, torrent_info_id="y-1", host="site.example.com")

        body = _yearly(env, year)
        assert body["code"] == "200"
        data = body["data"]
        assert data["yearAdded"]["count"] == 3
        assert data["yearAdded"]["sizeBytes"] == 60.0
        assert data["busiestMonth"] == {"key": f"{year}-03", "count": 3}
        assert data["busiestDay"] == {"key": f"{year}-03-05", "count": 2}
        assert data["topSite"]["host"] == "site.example.com"
        assert data["topSite"]["sizeBytes"] == 10.0
        assert data["elder"]["name"] == "元老"
        assert data["elder"]["addedDate"].startswith(f"{year - 1}-06-01")
        assert data["elder"]["seedingDays"] >= 300

    async def test_year_empty(self, env):
        body = _yearly(env, 2024)
        data = body["data"]
        assert data["yearAdded"]["count"] == 0
        assert data["busiestMonth"] is None
        assert data["busiestDay"] is None
        assert data["topSite"] is None
        assert data["elder"] is None

    async def test_year_param_validation(self, env):
        assert _yearly(env, 1999)["code"] == "400"
        assert _yearly(env, datetime.now().year + 5)["code"] == "400"
