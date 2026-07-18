"""Regression tests for live torrent metadata hydration."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.torrent_metadata import (
    fetch_live_torrent_metadata,
    fetch_qb_torrent_details,
    map_qb_torrent_metadata,
    map_transmission_torrent_metadata,
)
from app.services.downloader_api_runtime import DownloadLane


def test_map_qb_torrent_metadata_converts_display_fields():
    mapped = map_qb_torrent_metadata(
        {
            "hash": "ABC",
            "name": "movie",
            "save_path": "/downloads",
            "total_size": 1024,
            "state": "stalledUP",
            "progress": 0.5,
            "added_on": 1_700_000_000,
            "ratio": 1.25,
            "tags": "PT,4K",
            "category": "电影",
            "dlspeed": 12,
            "upspeed": 34,
            "num_leechs": 2,
            "num_seeds": 8,
        }
    )

    assert mapped["name"] == "movie"
    assert mapped["status"] == "seeding"
    assert mapped["progress"] == 50.0
    assert mapped["size"] == 1024
    assert mapped["download_speed"] == 12
    assert mapped["upload_speed"] == 34
    assert mapped["peers"] == 2
    assert mapped["seeds"] == 8


def test_map_transmission_torrent_metadata_supports_sdk_attributes():
    mapped = map_transmission_torrent_metadata(
        SimpleNamespace(
            id=7,
            hash_string="DEF",
            name="series",
            download_dir="/media",
            total_size=2048,
            status="downloading",
            percent_done=0.25,
            added_date=datetime(2026, 7, 18, 12, 0, 0),
            upload_ratio=0.5,
            seed_ratio_limit=2,
            labels=["TV", "4K"],
            rate_download=100,
            rate_upload=20,
            peers_connected=4,
            peers_sending_to_us=1,
        )
    )

    assert mapped["torrent_id"] == "7"
    assert mapped["status"] == "downloading"
    assert mapped["progress"] == 25.0
    assert mapped["tags"] == "TV,4K"
    assert mapped["save_path"] == "/media"


@pytest.mark.asyncio
async def test_fetch_qb_details_normalizes_deduplicates_and_batches_hashes():
    client = SimpleNamespace(torrents_info=lambda **_kwargs: None)
    api_mock = AsyncMock(
        side_effect=lambda *_args, **kwargs: [
            {"hash": torrent_hash, "name": torrent_hash}
            for torrent_hash in kwargs["kwargs"]["torrent_hashes"]
        ]
    )
    hashes = [f"HASH-{index}" for index in range(201)] + ["hash-0", ""]

    with patch("app.services.torrent_metadata.call_downloader_api", new=api_mock):
        details = await fetch_qb_torrent_details(
            client,
            "dl-qb",
            hashes,
            lane=DownloadLane.INTERACTIVE,
            operation="test_qb_batching",
        )

    batches = [
        call.kwargs["kwargs"]["torrent_hashes"] for call in api_mock.await_args_list
    ]
    assert [len(batch) for batch in batches] == [100, 100, 1]
    assert batches[0][0] == "hash-0"
    assert len(details) == 201


@pytest.mark.asyncio
async def test_fetch_live_transmission_metadata_uses_cached_client():
    class StaticStore:
        async def get_snapshot(self):
            return [
                SimpleNamespace(
                    downloader_id="dl-tr",
                    downloader_type=1,
                    client=SimpleNamespace(get_torrents=lambda **_kwargs: None),
                    fail_time=0,
                )
            ]

    app = SimpleNamespace(state=SimpleNamespace(store=StaticStore()))
    record = SimpleNamespace(
        downloader_id="dl-tr",
        hash="ABC",
        name="",
        save_path="",
        status="",
        size=0,
        added_date=None,
    )
    live_torrent = SimpleNamespace(
        id=7,
        hash_string="ABC",
        name="Transmission 完整名称",
        download_dir="/transmission",
        total_size=2048,
        status="downloading",
        percent_done=0.25,
        added_date=datetime(2026, 7, 18, 12, 0, 0),
        upload_ratio=0.5,
        seed_ratio_limit=2,
        labels=["TV"],
        rate_download=100,
        rate_upload=20,
        peers_connected=4,
        peers_sending_to_us=1,
    )
    api_mock = AsyncMock(return_value=[live_torrent])

    with patch("app.services.torrent_metadata.call_downloader_api", new=api_mock):
        metadata = await fetch_live_torrent_metadata(
            app, [record], {"dl-tr": "transmission"}
        )

    assert metadata[("dl-tr", "abc")]["name"] == "Transmission 完整名称"
    assert metadata[("dl-tr", "abc")]["save_path"] == "/transmission"
    call = api_mock.await_args
    assert call.args[0] == "dl-tr"
    assert call.args[1] == DownloadLane.INTERACTIVE
    assert call.kwargs["kwargs"]["ids"] == ["abc"]
    assert "name" in call.kwargs["kwargs"]["arguments"]


@pytest.mark.asyncio
async def test_live_metadata_cache_and_downloader_failures_fall_back_to_empty():
    class BrokenStore:
        async def get_snapshot(self):
            raise RuntimeError("cache unavailable")

    record = SimpleNamespace(
        downloader_id="dl-qb",
        hash="ABC",
        name="",
        save_path="",
        status="",
        size=0,
        added_date=None,
    )
    broken_app = SimpleNamespace(state=SimpleNamespace(store=BrokenStore()))
    assert await fetch_live_torrent_metadata(broken_app, [record], {}) == {}

    class StaticStore:
        async def get_snapshot(self):
            return [
                SimpleNamespace(
                    downloader_id="dl-qb",
                    downloader_type=0,
                    client=SimpleNamespace(torrents_info=lambda **_kwargs: None),
                    fail_time=0,
                )
            ]

    app = SimpleNamespace(state=SimpleNamespace(store=StaticStore()))
    with patch(
        "app.services.torrent_metadata.call_downloader_api",
        new=AsyncMock(side_effect=RuntimeError("downloader unavailable")),
    ):
        assert await fetch_live_torrent_metadata(app, [record], {}) == {}


@pytest.mark.asyncio
async def test_qb_info_incremental_sync_hydrates_partial_delta_before_write():
    """sync/maindata 的部分字段增量不得再把完整 DB 元数据覆盖为空。"""
    from app.api.endpoints import torrents_async

    downloader = SimpleNamespace(downloader_id="dl-1", nickname="qb")
    client = SimpleNamespace(sync_maindata=lambda rid: None)
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.return_value = query_result

    full_torrent = SimpleNamespace(
        hash="abc",
        name="完整名称",
        save_path="/downloads",
        total_size=4096,
        progress=0.75,
        state="stalledUP",
        added_on=1_700_000_000,
        completion_on=0,
        ratio=1.5,
        ratio_limit=2,
        tags="PT",
        category="电影",
        super_seeding=False,
    )
    details_mock = AsyncMock(return_value=[full_torrent])
    bulk_mock = AsyncMock()

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.dict(torrents_async._QB_SYNC_RID_CACHE, {"dl-1": 1}, clear=True),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(
            torrents_async,
            "call_downloader_api",
            new=AsyncMock(
                return_value={"rid": 2, "torrents": {"abc": {"progress": 0.75}}}
            ),
        ),
        patch.object(torrents_async, "fetch_qb_torrent_details", new=details_mock),
        patch.object(torrents_async, "bulk_upsert_with_retry", new=bulk_mock),
        patch.object(torrents_async, "_save_qb_rid_cache"),
    ):
        await torrents_async.qb_add_torrents_info_only_async(
            db, [downloader], client=client
        )

    details_mock.assert_awaited_once_with(
        client,
        "dl-1",
        ["abc"],
        lane=DownloadLane.SYNC,
        operation="qb_info_incremental_details",
    )
    inserted = bulk_mock.await_args.args[1]
    assert len(inserted) == 1
    assert inserted[0]["name"] == "完整名称"
    assert inserted[0]["save_path"] == "/downloads"
    assert inserted[0]["size"] == 4096
    assert inserted[0]["status"] == "seeding"


def _qb_downloader():
    return SimpleNamespace(
        downloader_id="dl-1",
        nickname="qb",
        host="localhost",
        port=8080,
        username="admin",
        password="secret",
        path_mapping=None,
        torrent_save_path="",
        downloader_type=0,
    )


def _empty_async_db():
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.return_value = query_result
    return db


@pytest.mark.asyncio
async def test_qb_full_sync_incremental_branch_hydrates_changed_rows():
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(sync_maindata=lambda rid: None)
    db = _empty_async_db()
    hydrate_mock = AsyncMock(return_value=[])
    api_mock = AsyncMock(
        return_value={"rid": 2, "torrents": {"abc": {"progress": 0.5}}}
    )

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.dict(torrents_async._QB_SYNC_RID_CACHE, {"dl-1": 1}, clear=True),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "qbClient", return_value=client),
        patch.object(torrents_async, "call_downloader_api", new=api_mock),
        patch.object(
            torrents_async, "_hydrate_qb_incremental_torrents", new=hydrate_mock
        ),
        patch.object(
            torrents_async, "_enrich_qb_torrents_with_trackers", new=AsyncMock()
        ),
        patch.object(torrents_async, "_retry_on_db_lock", new=AsyncMock()),
        patch.object(torrents_async, "_save_qb_rid_cache"),
    ):
        await torrents_async.qb_add_torrents_async(db, [downloader])

    hydrate_mock.assert_awaited_once()
    assert hydrate_mock.await_args.args[2:] == (
        "dl-1",
        "qb_sync_incremental_details",
    )
    assert api_mock.await_args.kwargs["operation"] == "sync_maindata_incremental"


@pytest.mark.asyncio
async def test_qb_full_sync_retry_branch_hydrates_changed_rows(monkeypatch):
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(sync_maindata=lambda rid: None)
    db = _empty_async_db()
    hydrate_mock = AsyncMock(return_value=[])
    api_mock = AsyncMock(
        side_effect=[
            torrents_async.APIConnectionError("temporary failure"),
            {"rid": 2, "torrents": {"abc": {"progress": 0.5}}},
        ]
    )
    monkeypatch.setattr(torrents_async.asyncio, "sleep", AsyncMock())

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.dict(torrents_async._QB_SYNC_RID_CACHE, {"dl-1": 1}, clear=True),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "qbClient", return_value=client),
        patch.object(torrents_async, "call_downloader_api", new=api_mock),
        patch.object(
            torrents_async, "_hydrate_qb_incremental_torrents", new=hydrate_mock
        ),
        patch.object(
            torrents_async, "_enrich_qb_torrents_with_trackers", new=AsyncMock()
        ),
        patch.object(torrents_async, "_retry_on_db_lock", new=AsyncMock()),
        patch.object(torrents_async, "_save_qb_rid_cache"),
    ):
        await torrents_async.qb_add_torrents_async(db, [downloader])

    hydrate_mock.assert_awaited_once()
    assert hydrate_mock.await_args.args[2:] == (
        "dl-1",
        "qb_sync_retry_incremental_details",
    )
    assert api_mock.await_args_list[1].kwargs["operation"] == "sync_maindata_retry"
