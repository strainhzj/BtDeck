# -*- coding: utf-8 -*-
"""TR tracker-only 两阶段分批测试（OOM 治理 2026-09-05 批次 3c）。

`tr_sync_trackers_only_async` 改造前为零功能覆盖（仅 Coordinator 整函数 mock
与 AST 契约），本文件是其首个直接功能测试，也是两阶段改造的唯一回归网：

1. 调用形态：slim 全量（ids=None，arguments=[id, hashString]）+ N 批
   ids=detail（arguments=TR_BASE_FIELDS 含 trackerStats）；
2. 批内按 hashString 重排：TR 服务端按 id 序返回，处理序/写入序必须恢复
   hash 字典序；
3. tracker_stats 空预检跳过；
4. 批间 flush：SYNC_DB_COMMIT_BATCH_SIZE 行界累计提交；
5. hash 不在 DB（hash_to_info_id 未命中）计入 skipped_new。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.endpoints import torrents_async
from app.core.config import settings


@pytest.fixture(autouse=True)
def isolate_call_downloader_api():
    """把 torrents_async.call_downloader_api 替换为直调 fake（不经 runtime 单例）。

    与 test_torrents_async_tracker_budget.py 同款隔离：全量套件中 TestClient(app)
    的 lifespan 退出会 shutdown 进程级 runtime 单例的 executor，此后真实调用
    全部失败；本文件只测两阶段分批逻辑，与真实 runtime 解耦。
    """

    async def fake_call_downloader_api(downloader_id, lane, func, args=(), kwargs=None, timeout=None, operation=""):
        return func(*args, **(kwargs or {}))

    with patch.object(torrents_async, "call_downloader_api", new=fake_call_downloader_api):
        yield


def _tr_stat(url, *, succeeded=True):
    """单个 Transmission TrackerStats 伪对象（满足 extract_tracker_rows_from_torrent 读取面）。"""
    return SimpleNamespace(
        fields={
            "announce": url,
            "host": None,  # 触发 extract_tracker_host 回退解析
            "lastAnnounceSucceeded": succeeded,
            "lastAnnounceTimedOut": False,
            "hasAnnounced": True,
            "announceState": 1 if succeeded else 0,
            "lastAnnounceResult": "" if succeeded else "unregistered torrent",
            "lastScrapeSucceeded": succeeded,
            "lastScrapeResult": "",
        },
        site_name="tr-stat",
        last_announce_result="",
        last_scrape_result="",
    )


def _tr_detail(tid, hash_, stats):
    return SimpleNamespace(id=tid, hashString=hash_, tracker_stats=stats)


def _tr_slim(tid, hash_):
    return SimpleNamespace(id=tid, hashString=hash_)


def _make_client(details, *, detail_order="id_desc"):
    """伪 TR 客户端：slim（ids=None）返回全量轻对象；detail 按 ids 返回完整对象。

    detail_order 控制返回序（对抗形态默认按 id 降序，比请求序更恶劣）。
    """
    by_id = {d.id: d for d in details}
    client = MagicMock()

    def get_torrents(**kwargs):
        ids = kwargs.get("ids")
        if ids is None:
            return [_tr_slim(d.id, d.hashString) for d in details]
        ordered = sorted(ids, reverse=(detail_order == "id_desc"))
        return [by_id[i] for i in ordered if i in by_id]

    client.get_torrents = MagicMock(side_effect=get_torrents)
    return client


def _tr_downloader():
    return SimpleNamespace(downloader_id="dl_trk", nickname="tr-tracker")


class TestTrTrackerTwoPhaseBatches:
    async def test_slim_full_then_batched_details(self, monkeypatch):
        """调用形态：1 次 slim 全量 + ceil(N/TR_BATCH_SIZE) 次 ids detail 批。"""
        monkeypatch.setattr(torrents_async, "TR_BATCH_SIZE", 2)
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 100)

        # 5 种子：id 与 hash 反序（id 序 = hash 降序，对抗批内重排）
        details = [
            _tr_detail(100 - i, f"trh{i:06d}", [_tr_stat(f"http://t{i}.example.com/announce")]) for i in range(5)
        ]
        client = _make_client(details)
        hash_map = {d.hashString: f"info-{d.hashString}" for d in details}

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ),
        ):
            result = await torrents_async.tr_sync_trackers_only_async(MagicMock(), _tr_downloader(), client)

        calls = client.get_torrents.call_args_list
        slim_calls = [c for c in calls if c.kwargs.get("ids") is None]
        detail_calls = [c for c in calls if c.kwargs.get("ids") is not None]
        assert len(slim_calls) == 1
        assert slim_calls[0].kwargs["arguments"] == ["id", "hashString"]
        assert len(detail_calls) == 3, f"5 种子 / 批 2 应翻 3 页，实际 {len(detail_calls)}"
        for call in detail_calls:
            assert "trackerStats" in call.kwargs["arguments"]
        assert result["status"] == "success"
        assert result["tracker_count"] == 5

    async def test_write_order_is_hash_lexicographic(self, monkeypatch):
        """detail 按 id 降序返回 → 累计写入行仍是 hash 字典序（批内重排生效）。"""
        monkeypatch.setattr(torrents_async, "TR_BATCH_SIZE", 2)
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 100)

        details = [
            _tr_detail(100 - i, f"trh{i:06d}", [_tr_stat(f"http://t{i}.example.com/announce")]) for i in range(5)
        ]
        client = _make_client(details)
        hash_map = {d.hashString: f"info-{d.hashString}" for d in details}

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ) as flush_mock,
        ):
            await torrents_async.tr_sync_trackers_only_async(MagicMock(), _tr_downloader(), client)

        written = [row["torrent_info_id"] for flush in flush_mock.await_args_list for row in flush.args[1]]
        assert written == sorted(written), f"写入序必须按 hash 字典序对齐 info_id，实际: {written}"
        assert written == [f"info-trh{i:06d}" for i in range(5)]

    async def test_empty_tracker_stats_precheck_skipped(self, monkeypatch):
        """tracker_stats 为空/缺失的种子静默跳过，不计入 tracker_count。"""
        monkeypatch.setattr(torrents_async, "TR_BATCH_SIZE", 10)
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 100)

        details = [
            _tr_detail(3, "trh000003", []),  # 空 stats
            _tr_detail(1, "trh000001", [_tr_stat("http://t1.example.com/a")]),
            _tr_detail(2, "trh000002", None),  # 缺失 stats
        ]
        client = _make_client(details)
        hash_map = {d.hashString: f"info-{d.hashString}" for d in details}

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ) as flush_mock,
        ):
            result = await torrents_async.tr_sync_trackers_only_async(MagicMock(), _tr_downloader(), client)

        assert result["tracker_count"] == 1
        assert flush_mock.await_count == 1
        written_rows = flush_mock.await_args.args[1]
        assert len(written_rows) == 1
        assert written_rows[0]["tracker_url"] == "http://t1.example.com/a"

    async def test_inter_batch_row_flush(self, monkeypatch):
        """行界 flush：SYNC_DB_COMMIT_BATCH_SIZE=2 时 4 行分 2 次提交（跨批边界累计）。"""
        monkeypatch.setattr(torrents_async, "TR_BATCH_SIZE", 10)
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 2)

        details = [
            _tr_detail(
                4 - i, f"trh{i:06d}", [_tr_stat(f"http://t{i}.example.com/a"), _tr_stat(f"http://s{i}.example.com/b")]
            )
            for i in range(2)
        ]
        client = _make_client(details)
        hash_map = {d.hashString: f"info-{d.hashString}" for d in details}

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ) as flush_mock,
        ):
            await torrents_async.tr_sync_trackers_only_async(MagicMock(), _tr_downloader(), client)

        assert flush_mock.await_count == 2
        assert all(len(call.args[1]) == 2 for call in flush_mock.await_args_list)

    async def test_unknown_hash_counted_as_skipped(self, monkeypatch):
        """hash 不在 hash_to_info_id 的种子计入 skipped_new，不产生写行。"""
        monkeypatch.setattr(torrents_async, "TR_BATCH_SIZE", 10)
        monkeypatch.setattr(settings, "SYNC_DB_COMMIT_BATCH_SIZE", 100)

        details = [
            _tr_detail(2, "trh000002", [_tr_stat("http://t2.example.com/a")]),
            _tr_detail(1, "trh000001", [_tr_stat("http://t1.example.com/a")]),
        ]
        client = _make_client(details)
        hash_map = {"trh000001": "info-trh000001"}  # trh000002 未入库

        with (
            patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value=hash_map)),
            patch.object(
                torrents_async,
                "sync_trackers_batch_async",
                new=AsyncMock(return_value={"insert": 0, "update": 1, "skip": 0, "removed": 0}),
            ) as flush_mock,
        ):
            result = await torrents_async.tr_sync_trackers_only_async(MagicMock(), _tr_downloader(), client)

        assert result["tracker_count"] == 1
        assert result["torrent_count"] == 2  # tracker_count + skipped_new
        assert len(flush_mock.await_args.args[1]) == 1

    async def test_empty_library_single_slim_call(self, monkeypatch):
        """空库：仅 1 次 slim 调用即返回，不发起 detail 批。"""
        client = _make_client([])
        with patch.object(torrents_async, "_query_hash_to_info_id", new=AsyncMock(return_value={"h": "i"})):
            result = await torrents_async.tr_sync_trackers_only_async(MagicMock(), _tr_downloader(), client)

        assert client.get_torrents.call_count == 1
        assert client.get_torrents.call_args.kwargs.get("ids") is None
        assert result["status"] == "success"
        assert result["torrent_count"] == 0
