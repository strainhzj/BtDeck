# -*- coding: utf-8 -*-
"""报表·Tracker 端点回归（D14/D15/D16，统计报表 W3 §6）。

覆盖：host 去端口归一 / tracker dr=0 过滤 + 活跃种子 JOIN / errorRate 分母
排除 unknown / supplyDemand 均值排除 NULL（count=有效行数）/ 辅种跨站重复
计体积口径（文档化行为）。
"""

from datetime import datetime

import pytest

from tests.api.reports_fixtures import URL_PREFIX, add_torrent, add_tracker, make_env

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def env():
    e = await make_env()
    yield e
    await e.close()


def _trackers(env):
    resp = env.client.get(f"{URL_PREFIX}/trackers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "200"
    return body["data"]


class TestSites:
    async def test_host_port_stripped(self, env):
        """D14 站点归一：带端口 host 与裸 host 合并为同一站点。"""
        await add_torrent(env.session, info_id="i-1", size=100)
        await add_tracker(env.session, torrent_info_id="i-1", host="tracker.example.com:8080")
        await add_tracker(
            env.session, torrent_info_id="i-1", host="tracker.example.com", url="http://tracker.example.com/x"
        )
        sites = _trackers(env)["sites"]
        assert len(sites) == 1
        assert sites[0]["host"] == "tracker.example.com"
        assert sites[0]["count"] == 2

    async def test_cross_site_size_duplication_caliber(self, env):
        """口径锁定：一个种子挂两个站 → 体积在两站各计一次（辅种跨站重复计体积，前端脚注）。"""
        await add_torrent(env.session, info_id="i-2", size=50)
        await add_tracker(env.session, torrent_info_id="i-2", host="a.example.com")
        await add_tracker(env.session, torrent_info_id="i-2", host="b.example.com")
        sites = {s["host"]: s for s in _trackers(env)["sites"]}
        assert sites["a.example.com"]["sizeBytes"] == 50.0
        assert sites["b.example.com"]["sizeBytes"] == 50.0

    async def test_dr_filters(self, env):
        """tracker dr=1 行排除；回收站/彻底删除种子的 tracker 不入 JOIN。"""
        await add_torrent(env.session, info_id="i-live", size=10)
        await add_torrent(env.session, info_id="i-bin", size=20, deleted_at=datetime.now())
        await add_torrent(env.session, info_id="i-gone", size=30, dr=1)
        await add_tracker(env.session, torrent_info_id="i-live", host="ok.example.com")
        await add_tracker(env.session, torrent_info_id="i-live", host="dead.example.com", dr=1)
        await add_tracker(env.session, torrent_info_id="i-bin", host="bin.example.com")
        await add_tracker(env.session, torrent_info_id="i-gone", host="gone.example.com")
        sites = {s["host"]: s for s in _trackers(env)["sites"]}
        assert set(sites) == {"ok.example.com"}


class TestHealth:
    async def test_error_rate_excludes_unknown_denominator(self, env):
        """D15：error 率分母排除 status='unknown'（error=1, normal=1, unknown=1 → 0.5）。"""
        await add_torrent(env.session, info_id="i-h", size=10)
        await add_tracker(env.session, torrent_info_id="i-h", host="h.example.com", status="error")
        await add_tracker(
            env.session, torrent_info_id="i-h", host="h.example.com", status="normal", url="http://h.example.com/2"
        )
        await add_tracker(
            env.session, torrent_info_id="i-h", host="h.example.com", status="unknown", url="http://h.example.com/3"
        )
        health = _trackers(env)["health"]
        assert len(health) == 1
        assert health[0]["errorRate"] == pytest.approx(0.5)
        assert health[0]["affectedCount"] == 1  # error 行关联的种子数

    async def test_all_unknown_zero_rate(self, env):
        await add_torrent(env.session, info_id="i-u")
        await add_tracker(env.session, torrent_info_id="i-u", host="u.example.com", status="unknown")
        health = _trackers(env)["health"]
        assert health[0]["errorRate"] == 0.0

    async def test_health_sorted_by_error_rate_desc(self, env):
        await add_torrent(env.session, info_id="i-1")
        await add_torrent(env.session, info_id="i-2")
        # bad 站：2 error / 2 normal = 1.0；mid 站：1 error / 2 normal = 0.5
        await add_tracker(env.session, torrent_info_id="i-1", host="bad.example.com", status="error")
        await add_tracker(
            env.session, torrent_info_id="i-2", host="bad.example.com", status="error", url="http://bad.example.com/2"
        )
        await add_tracker(
            env.session, torrent_info_id="i-1", host="bad.example.com", status="normal", url="http://bad.example.com/3"
        )
        await add_tracker(
            env.session, torrent_info_id="i-2", host="bad.example.com", status="normal", url="http://bad.example.com/4"
        )
        await add_tracker(env.session, torrent_info_id="i-1", host="mid.example.com", status="error")
        await add_tracker(
            env.session, torrent_info_id="i-1", host="mid.example.com", status="normal", url="http://mid.example.com/2"
        )
        hosts = [h["host"] for h in _trackers(env)["health"]]
        assert hosts[:2] == ["bad.example.com", "mid.example.com"]


class TestSupplyDemand:
    async def test_means_exclude_null_rows(self, env):
        """D16：均值排除 NULL 行；count=有效行数（-1 已在 W2 归一 NULL 场景）。"""
        await add_torrent(env.session, info_id="i-s", size=10)
        # host 站三行：计数齐全 ×1、seeder 缺失 ×1、全 NULL ×1
        await add_tracker(
            env.session, torrent_info_id="i-s", host="s.example.com", seeder=10, leecher=4, downloaded=100
        )
        await add_tracker(
            env.session,
            torrent_info_id="i-s",
            host="s.example.com",
            seeder=None,
            leecher=6,
            downloaded=200,
            url="http://s.example.com/2",
        )
        await add_tracker(
            env.session,
            torrent_info_id="i-s",
            host="s.example.com",
            seeder=None,
            leecher=None,
            downloaded=None,
            url="http://s.example.com/3",
        )
        supply = {s["host"]: s for s in _trackers(env)["supplyDemand"]}
        s = supply["s.example.com"]
        assert s["avgSeeders"] == pytest.approx(10.0)  # 1 有效行
        assert s["avgLeechers"] == pytest.approx(5.0)  # (4+6)/2
        assert s["avgDownloads"] == pytest.approx(150.0)  # (100+200)/2
        assert s["count"] == 2  # 有效行数取三列最大者

    async def test_empty_db(self, env):
        data = _trackers(env)
        assert data["sites"] == []
        assert data["health"] == []
        assert data["supplyDemand"] == []
