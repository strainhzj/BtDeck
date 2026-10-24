# -*- coding: utf-8 -*-
"""报表·做种端点回归（C10/C11/C12，统计报表 W3 §6）。

覆盖：ratio 半开区间分桶边界 / NULL ratio 计数与排除 / slackers（ratio<0.5
AND completed_date 非空，体积降序 TOP20，实际种子口径）/ 辅种率与 TOP10 /
文件合计口径 ratioBucketsByFile（组内 Σratio）。
"""

from datetime import datetime

import pytest

from tests.api.reports_fixtures import URL_PREFIX, add_torrent, make_env

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def env():
    e = await make_env()
    yield e
    await e.close()


def _seeding(env):
    resp = env.client.get(f"{URL_PREFIX}/seeding")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "200"
    return body["data"]


class TestRatioBuckets:
    async def test_bucket_boundaries_half_open(self, env):
        """半开区间 [lo, hi)：0.49→<0.5；0.5→0.5-1；1.0→1-2；2.5→2-5；5.0→5-10；10.0→10+。"""
        for i, ratio in enumerate([0.49, 0.5, 1.0, 2.5, 5.0, 10.0]):
            await add_torrent(env.session, info_id=f"i-{i}", ratio=ratio, size=1.0)
        buckets = {b["bucket"]: b for b in _seeding(env)["ratioBuckets"]}
        assert buckets["<0.5"]["count"] == 1
        assert buckets["0.5-1"]["count"] == 1
        assert buckets["1-2"]["count"] == 1
        assert buckets["2-5"]["count"] == 1
        assert buckets["5-10"]["count"] == 1
        assert buckets["10+"]["count"] == 1

    async def test_null_ratio_counted_and_excluded(self, env):
        """NULL ratio（TR 做种态添加恒空）不进桶，进 ratioNullCount。"""
        await add_torrent(env.session, info_id="i-null", ratio=None, size=100)
        await add_torrent(env.session, info_id="i-has", ratio=1.5, size=10)
        data = _seeding(env)
        assert data["ratioNullCount"] == 1
        assert sum(b["count"] for b in data["ratioBuckets"]) == 1

    async def test_size_bytes_per_bucket(self, env):
        await add_torrent(env.session, info_id="i-a", ratio=0.3, size=10)
        await add_torrent(env.session, info_id="i-b", ratio=0.4, size=15)
        buckets = {b["bucket"]: b for b in _seeding(env)["ratioBuckets"]}
        assert buckets["<0.5"]["count"] == 2
        assert buckets["<0.5"]["sizeBytes"] == 25.0


class TestSlackers:
    async def test_filter_and_top20(self, env):
        """ratio<0.5 AND completed_date 非空；体积降序 TOP20 封顶。"""
        completed = datetime(2026, 1, 1)
        for i in range(22):  # 超量：验证 TOP20 封顶
            await add_torrent(
                env.session, info_id=f"s-{i}", name=f"s{i}", ratio=0.1, size=float(i), completed_date=completed
            )
        # 不合格样本：ratio 达标但未完成 / 完成但 ratio 达标线上
        await add_torrent(env.session, info_id="s-noc", ratio=0.1, size=999, completed_date=None)
        await add_torrent(env.session, info_id="s-hi", ratio=0.6, size=999, completed_date=completed)
        slackers = _seeding(env)["slackers"]
        assert len(slackers) == 20
        sizes = [x["sizeBytes"] for x in slackers]
        assert sizes == sorted(sizes, reverse=True)
        assert sizes[0] == 21.0  # 22 行里最大的 20 个（0..21），999 与不合格样本不入榜


class TestRatioBucketsByFile:
    """C10 文件合计口径：同 (name,size) 组内可用 ratio 求和后分桶（双口径决策）。"""

    async def test_group_ratio_sum_bucketed(self, env):
        """两副本 ratio 0.3+0.4 → 文件合计 0.7 落 0.5-1；实际口径仍各计 <0.5。"""
        await add_torrent(env.session, info_id="i-a", name="dup", ratio=0.3, size=10)
        await add_torrent(env.session, info_id="i-b", name="dup", ratio=0.4, size=10)
        data = _seeding(env)
        actual = {b["bucket"]: b for b in data["ratioBuckets"]}
        by_file = {b["bucket"]: b for b in data["ratioBucketsByFile"]}
        assert actual["<0.5"]["count"] == 2  # 实际口径：副本各自计桶
        assert by_file["0.5-1"]["count"] == 1  # 合计口径：Σratio=0.7
        assert by_file["0.5-1"]["sizeBytes"] == 10.0
        assert data["ratioNullCountByFile"] == 0

    async def test_group_sum_crosses_bucket_boundary(self, env):
        """两副本各 3.0 → 合计 6.0 落 5-10。"""
        await add_torrent(env.session, info_id="j-1", name="dup", ratio=3.0, size=5)
        await add_torrent(env.session, info_id="j-2", name="dup", ratio=3.0, size=5)
        by_file = {b["bucket"]: b for b in _seeding(env)["ratioBucketsByFile"]}
        assert by_file["5-10"]["count"] == 1

    async def test_all_null_group_counts_file_null(self, env):
        """全组无可用 ratio（NULL）→ 文件口径 NULL 计 1；另有可用单种正常计桶。"""
        await add_torrent(env.session, info_id="k-1", name="dup", ratio=None, size=10)
        await add_torrent(env.session, info_id="k-2", name="dup", ratio=None, size=10)
        await add_torrent(env.session, info_id="k-3", name="solo", ratio=1.0, size=7)
        data = _seeding(env)
        assert data["ratioNullCount"] == 2
        assert data["ratioNullCountByFile"] == 1
        assert sum(b["count"] for b in data["ratioBucketsByFile"]) == 1

    async def test_single_torrent_calibers_agree(self, env):
        """无辅种时两口径一致。"""
        await add_torrent(env.session, info_id="m-1", name="solo", ratio=1.5, size=10)
        data = _seeding(env)
        assert data["ratioBuckets"] == data["ratioBucketsByFile"]
        assert data["ratioNullCount"] == data["ratioNullCountByFile"] == 0


class TestAuxiliary:
    async def test_cross_seed_rate_and_top10(self, env):
        await add_torrent(env.session, info_id="a-1", auxiliary_seed_count=1)  # 普通种
        await add_torrent(env.session, info_id="a-2", auxiliary_seed_count=5, size=10, name="辅5")
        await add_torrent(env.session, info_id="a-3", auxiliary_seed_count=9, size=20, name="辅9")
        aux = _seeding(env)["auxiliary"]
        assert aux["totalTorrents"] == 3
        assert aux["crossSeedCount"] == 2
        assert aux["crossSeedRate"] == pytest.approx(2 / 3)
        assert [x["auxiliarySeedCount"] for x in aux["top10"]] == [9, 5]

    async def test_empty_db(self, env):
        data = _seeding(env)
        assert data["ratioNullCount"] == 0
        assert data["ratioNullCountByFile"] == 0
        assert sum(b["count"] for b in data["ratioBucketsByFile"]) == 0
        assert data["slackers"] == []
        assert data["auxiliary"] == {"totalTorrents": 0, "crossSeedCount": 0, "crossSeedRate": 0.0, "top10": []}
