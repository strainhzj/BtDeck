# -*- coding: utf-8 -*-
"""报表·总览端点回归（A1-A5 + 实时速度，统计报表 W3 §6）。

覆盖：401 / 空库 / 五桶归并（错误桶优先级断言：seeding+has_tracker_error 落
错误桶）/ largest TOP10 / 回收站条件 / categories+tags+save_path 根前缀 /
孤儿下载器标注 / liveSpeed 快照 / 文件优先口径（辅种只计主种）。
"""

from datetime import datetime

import pytest

from tests.api.reports_fixtures import (  # noqa: F401 - add_tracker 共享基建导出
    URL_PREFIX,
    add_downloader,
    add_torrent,
    add_tracker,
    fake_store,
    make_env,
    vo,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def env():
    e = await make_env()
    yield e
    await e.close()


def _get(env):
    resp = env.client.get(f"{URL_PREFIX}/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "200"
    return body["data"]


async def test_no_token_returns_401():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.api import api_router

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"{URL_PREFIX}/overview")
    assert r.status_code == 401
    assert r.json()["detail"] == "Could not validate credentials"


async def test_empty_db(env):
    data = _get(env)
    assert data["totals"] == {"count": 0, "sizeBytes": 0.0, "avgSizeBytes": 0.0, "recycleBinSizeBytes": 0.0}
    assert data["largest"] == []
    assert data["statusDist"] == []
    assert data["categories"] == []
    assert data["tags"] == []
    assert data["paths"] == []
    assert data["downloaders"] == []
    # store 未注入 → liveSpeed 降级零值
    assert data["liveSpeed"] == {"totalDownloadSpeed": 0, "totalUploadSpeed": 0, "items": []}


class TestStatusDistFiveBuckets:
    async def test_error_bucket_priority(self, env):
        """seeding + has_tracker_error → 错误桶（决策 7：错误桶优先级最高）。"""
        await add_torrent(env.session, info_id="i-err", status="seeding", has_tracker_error=True, size=10)
        await add_torrent(env.session, info_id="i-plain-seed", status="seeding", size=20)
        data = _get(env)
        dist = {d["bucket"]: d for d in data["statusDist"]}
        assert dist["error"]["count"] == 1
        assert dist["error"]["sizeBytes"] == 10.0
        assert dist["seeding"]["count"] == 1

    async def test_error_status_string_bucket(self, env):
        """status='error' 字符串本身即错误桶。"""
        await add_torrent(env.session, info_id="i-e2", status="error")
        data = _get(env)
        assert [d["bucket"] for d in data["statusDist"]] == ["error"]

    async def test_tr_paused_mapped_value_bucket(self, env):
        """TR 映射后的 DB 值 'paused'（W2 常量扩充）归暂停桶。"""
        await add_torrent(env.session, info_id="i-p", status="paused", size=5)
        data = _get(env)
        dist = {d["bucket"]: d for d in data["statusDist"]}
        assert dist["paused"]["count"] == 1

    async def test_other_bucket_for_unknown_status(self, env):
        await add_torrent(env.session, info_id="i-u", status="weirdState")
        data = _get(env)
        assert [d["bucket"] for d in data["statusDist"]] == ["other"]

    async def test_downloading_statuses(self, env):
        await add_torrent(env.session, info_id="i-d1", status="downloading")
        await add_torrent(env.session, info_id="i-d2", status="stalledDL")
        await add_torrent(env.session, info_id="i-d3", status="queuedDL")
        data = _get(env)
        dist = {d["bucket"]: d for d in data["statusDist"]}
        assert dist["downloading"]["count"] == 3


class TestLargestTop10:
    async def test_top10_largest_desc(self, env):
        for i in range(12):
            await add_torrent(env.session, info_id=f"i-{i}", name=f"t{i}", size=float(i))
        data = _get(env)
        assert len(data["largest"]) == 10
        sizes = [x["sizeBytes"] for x in data["largest"]]
        assert sizes == sorted(sizes, reverse=True)
        assert sizes[0] == 11.0

    async def test_zero_size_excluded(self, env):
        await add_torrent(env.session, info_id="i-0", size=0)
        await add_torrent(env.session, info_id="i-1", size=7)
        data = _get(env)
        assert [x["sizeBytes"] for x in data["largest"]] == [7.0]


class TestCaliberFilters:
    async def test_recycle_bin_and_hard_deleted_excluded(self, env):
        """回收站（deleted_at 非空）不入库存口径但计入回收站体积；dr=1 彻底删除两者皆无。"""
        await add_torrent(env.session, info_id="i-live", size=100)
        await add_torrent(env.session, info_id="i-bin", size=50, deleted_at=datetime.now())
        await add_torrent(env.session, info_id="i-gone", size=999, dr=1)
        data = _get(env)
        assert data["totals"]["count"] == 1
        assert data["totals"]["sizeBytes"] == 100.0
        assert data["totals"]["recycleBinSizeBytes"] == 50.0


class TestCategoriesTagsPaths:
    async def test_categories_with_empty_bucket(self, env):
        await add_torrent(env.session, info_id="i-c1", category="movies", size=10)
        await add_torrent(env.session, info_id="i-c2", category="movies", size=20)
        await add_torrent(env.session, info_id="i-c3", category="")  # TR 无分类 → "" 桶（前端 i18n 未分类）
        cats = {c["name"]: c for c in _get(env)["categories"]}
        assert cats["movies"]["count"] == 2
        assert cats["movies"]["sizeBytes"] == 30.0
        assert cats[""]["count"] == 1

    async def test_tags_split_and_multi_count(self, env):
        await add_torrent(env.session, info_id="i-t1", tags="a,b", size=10)
        await add_torrent(env.session, info_id="i-t2", tags="a", size=5)
        tags = {t["name"]: t for t in _get(env)["tags"]}
        assert tags["a"]["count"] == 2
        assert tags["a"]["sizeBytes"] == 15.0
        assert tags["b"]["count"] == 1

    async def test_save_path_root_prefix(self, env):
        await add_torrent(env.session, info_id="i-p1", save_path="/downloads/movies/a", size=10)
        await add_torrent(env.session, info_id="i-p2", save_path="/downloads/movies/b", size=20)
        await add_torrent(env.session, info_id="i-p3", save_path="/downloads", size=5)
        paths = {p["path"]: p for p in _get(env)["paths"]}
        assert paths["/downloads/movies"]["count"] == 2
        assert paths["/downloads/movies"]["sizeBytes"] == 30.0
        assert paths["/downloads"]["count"] == 1

    async def test_windows_style_path(self, env):
        await add_torrent(env.session, info_id="i-w1", save_path="D:\\Downloads\\movies\\x", size=10)
        paths = {p["path"]: p for p in _get(env)["paths"]}
        assert paths["D:/Downloads"]["count"] == 1


class TestDownloaders:
    async def test_orphan_downloader_marked_removed(self, env):
        """已移除下载器（不在 bt_downloaders）标注 removed=true，昵称回退种子行 downloader_name。"""
        await add_downloader(env.session, "dl-live", nickname="活跃下载器")
        await add_torrent(env.session, info_id="i-1", downloader_id="dl-live", downloader_name="活跃下载器", size=10)
        await add_torrent(env.session, info_id="i-2", downloader_id="dl-gone", downloader_name="旧名", size=20)
        data = _get(env)
        by_id = {d["downloaderId"]: d for d in data["downloaders"]}
        assert by_id["dl-live"]["removed"] is False
        assert by_id["dl-live"]["nickname"] == "活跃下载器"
        assert by_id["dl-gone"]["removed"] is True
        assert by_id["dl-gone"]["nickname"] == "旧名"
        # 各自带五桶 statusDist
        assert by_id["dl-gone"]["statusDist"][0]["bucket"] == "seeding"

    async def test_soft_deleted_downloader_removed(self, env):
        """dr=1 下载器仍能取昵称但标注 removed。"""
        await add_downloader(env.session, "dl-soft", nickname="软删", dr=1)
        await add_torrent(env.session, info_id="i-s", downloader_id="dl-soft", downloader_name="x")
        by_id = {d["downloaderId"]: d for d in _get(env)["downloaders"]}
        assert by_id["dl-soft"]["removed"] is True
        assert by_id["dl-soft"]["nickname"] == "软删"


class TestFileFirstCaliber:
    """文件优先口径（文件>种子）：同 (name,size) 辅种组只计主种。

    数量/体积类聚合（totals/largest/分类/目录/下载器）按文件；五桶按实际种子。
    """

    async def test_cross_seed_totals_dual_caliber(self, env):
        """总种子数/平均体积按实际种子；总体积/largest 按文件口径；五桶按实际。"""
        await add_torrent(env.session, info_id="f-1", name="dup", size=100, hash_="h1", added_date=datetime(2026, 1, 1))
        await add_torrent(env.session, info_id="f-2", name="dup", size=100, hash_="h2", added_date=datetime(2026, 2, 1))
        await add_torrent(env.session, info_id="f-3", name="dup", size=100, hash_="h3", added_date=datetime(2026, 3, 1))
        await add_torrent(env.session, info_id="f-solo", name="solo", size=50)
        data = _get(env)
        assert data["totals"]["count"] == 4  # 真实种子数（3 副本 + solo）
        assert data["totals"]["sizeBytes"] == 150.0  # 文件口径体积（dup 只计一次）
        assert data["totals"]["avgSizeBytes"] == 87.5  # 真实平均 = 350/4
        assert len(data["largest"]) == 2
        # 五桶按实际种子：4 个种子各自计桶
        assert sum(d["count"] for d in data["statusDist"]) == 4

    async def test_representative_is_earliest_added(self, env):
        """主种 = added_date 最早者（其 hash 入 largest）。"""
        await add_torrent(
            env.session, info_id="r-1", name="dup", size=10, hash_="late", added_date=datetime(2026, 5, 1)
        )
        await add_torrent(
            env.session, info_id="r-2", name="dup", size=10, hash_="early", added_date=datetime(2025, 5, 1)
        )
        largest = _get(env)["largest"]
        assert [x["hash"] for x in largest] == ["early"]

    async def test_null_added_dates_tie_break_by_info_id(self, env):
        """全组 added_date NULL → tie-break info_id 升序，确定性。"""
        await add_torrent(env.session, info_id="n-9", name="dup", size=10, hash_="h9", added_date=None)
        await add_torrent(env.session, info_id="n-1", name="dup", size=10, hash_="h1", added_date=None)
        largest = _get(env)["largest"]
        assert [x["hash"] for x in largest] == ["h1"]

    async def test_invalid_key_rows_count_independently(self, env):
        """name 空白/size NULL 的行不与任何行合并（与辅种服务 else_=1 口径一致）。"""
        await add_torrent(env.session, info_id="v-1", name="", size=10)
        await add_torrent(env.session, info_id="v-2", name="", size=10)
        await add_torrent(env.session, info_id="v-3", name="x", size=None)
        data = _get(env)
        assert data["totals"]["count"] == 3

    async def test_categories_and_paths_by_file(self, env):
        await add_torrent(env.session, info_id="p-1", name="dup", size=10, category="movies")
        await add_torrent(env.session, info_id="p-2", name="dup", size=10, category="movies")
        cats = {c["name"]: c for c in _get(env)["categories"]}
        assert cats["movies"]["count"] == 1
        assert cats["movies"]["sizeBytes"] == 10.0

    async def test_recycle_bin_internal_dedup(self, env):
        """回收站站内去重：同 name+size 两行只计一次；与库存互不去重。"""
        await add_torrent(env.session, info_id="b-live", name="dup", size=100)
        await add_torrent(env.session, info_id="b-1", name="dup", size=30, deleted_at=datetime.now())
        await add_torrent(env.session, info_id="b-2", name="dup", size=30, deleted_at=datetime.now())
        data = _get(env)
        assert data["totals"]["count"] == 1
        assert data["totals"]["recycleBinSizeBytes"] == 30.0

    async def test_downloader_hosts_only_representatives(self, env):
        """仅持有辅种副本的下载器不入文件口径对比（其副本仍计入自身五桶不适用——无主种即不展示）。"""
        await add_downloader(env.session, "dl-main", nickname="主")
        await add_downloader(env.session, "dl-aux", nickname="辅")
        await add_torrent(
            env.session,
            info_id="d-1",
            name="dup",
            size=10,
            downloader_id="dl-main",
            downloader_name="主",
            added_date=datetime(2026, 1, 1),
        )
        await add_torrent(
            env.session,
            info_id="d-2",
            name="dup",
            size=10,
            downloader_id="dl-aux",
            downloader_name="辅",
            added_date=datetime(2026, 6, 1),
        )
        by_id = {d["downloaderId"]: d for d in _get(env)["downloaders"]}
        assert set(by_id) == {"dl-main"}
        assert by_id["dl-main"]["count"] == 1


class TestLiveSpeed:
    async def test_live_speed_from_store_snapshot(self, env):
        env.app.state.store = fake_store(
            [
                vo("dl-1", "a", is_online=True, download_speed=100, upload_speed=200),
                vo("dl-2", "b", is_online=False, download_speed=999, upload_speed=999),
            ]
        )
        data = _get(env)
        live = data["liveSpeed"]
        # 在线者 KB/s → bytes/s；离线者速度 0 且不入合计
        assert live["totalDownloadSpeed"] == 100 * 1024
        assert live["totalUploadSpeed"] == 200 * 1024
        items = {i["downloaderId"]: i for i in live["items"]}
        assert items["dl-1"]["downloadSpeed"] == 100 * 1024
        assert items["dl-2"]["online"] is False
        assert items["dl-2"]["downloadSpeed"] == 0
