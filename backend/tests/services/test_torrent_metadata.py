"""Regression tests for live torrent metadata hydration."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qbittorrentapi.exceptions import APIError

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
            {"hash": torrent_hash, "name": torrent_hash} for torrent_hash in kwargs["kwargs"]["torrent_hashes"]
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

    batches = [call.kwargs["kwargs"]["torrent_hashes"] for call in api_mock.await_args_list]
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
        metadata = await fetch_live_torrent_metadata(app, [record], {"dl-tr": "transmission"})

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


def _live_metadata_record(torrent_hash):
    return SimpleNamespace(
        downloader_id="dl-live",
        hash=torrent_hash,
        torrent_id=torrent_hash,
        name=f"DB {torrent_hash}",
        save_path="/downloads",
        status="seeding",
        size=4096,
        added_date=datetime(2026, 7, 18, 12, 0, 0),
        progress=100.0,
        ratio=None,
        ratio_limit="0",
        tags="",
        category="",
        super_seeding="0",
        enabled=True,
        state=None,
        download_speed=None,
        upload_speed=None,
        peers=None,
        seeds=None,
    )


def _live_metadata_app(downloader_type, client):
    class StaticStore:
        async def get_snapshot(self):
            return [
                SimpleNamespace(
                    downloader_id="dl-live",
                    downloader_type=downloader_type,
                    client=client,
                    fail_time=0,
                )
            ]

    return SimpleNamespace(state=SimpleNamespace(store=StaticStore()))


def _qb_live_payload(torrent_hash):
    return {
        "hash": torrent_hash,
        "name": f"Live {torrent_hash}",
        "save_path": "/downloads",
        "total_size": 4096,
        "state": "stalledUP",
        "progress": 1,
        "added_on": 1_700_000_000,
        "ratio": 1,
    }


def _transmission_live_payload(torrent_hash):
    return SimpleNamespace(
        id=torrent_hash,
        hash_string=torrent_hash,
        name=f"Live {torrent_hash}",
        download_dir="/downloads",
        total_size=4096,
        status="seeding",
        percent_done=1,
        added_date=datetime(2026, 7, 18, 12, 0, 0),
        upload_ratio=1,
    )


@pytest.mark.asyncio
async def test_live_qb_second_batch_failure_keeps_and_caches_first_batch(
    monkeypatch,
):
    from app.services import torrent_metadata as metadata_service

    client = SimpleNamespace(torrents_info=lambda **_kwargs: None)
    app = _live_metadata_app(0, client)
    records = [_live_metadata_record("a"), _live_metadata_record("b")]
    api_mock = AsyncMock(
        side_effect=[
            [_qb_live_payload("a")],
            TimeoutError("second qB batch failed"),
            [_qb_live_payload("b")],
        ]
    )
    monkeypatch.setattr(metadata_service, "_QB_DETAIL_BATCH_SIZE", 1)
    monkeypatch.setattr(metadata_service, "call_downloader_api", api_mock)

    first = await metadata_service.fetch_live_torrent_metadata(app, records, {"dl-live": "qbittorrent"})
    second = await metadata_service.fetch_live_torrent_metadata(app, records, {"dl-live": "qbittorrent"})

    assert set(first) == {("dl-live", "a")}
    assert set(second) == {("dl-live", "a"), ("dl-live", "b")}
    batches = [call.kwargs["kwargs"]["torrent_hashes"] for call in api_mock.await_args_list]
    assert batches == [["a"], ["b"], ["b"]]


@pytest.mark.asyncio
async def test_live_transmission_second_batch_failure_keeps_and_caches_first_batch(
    monkeypatch,
):
    from app.services import torrent_metadata as metadata_service

    client = SimpleNamespace(get_torrents=lambda **_kwargs: None)
    app = _live_metadata_app(1, client)
    records = [_live_metadata_record("a"), _live_metadata_record("b")]
    api_mock = AsyncMock(
        side_effect=[
            [_transmission_live_payload("a")],
            TimeoutError("second Transmission batch failed"),
            [_transmission_live_payload("b")],
        ]
    )
    monkeypatch.setattr(metadata_service, "_TR_DETAIL_BATCH_SIZE", 1)
    monkeypatch.setattr(metadata_service, "call_downloader_api", api_mock)

    first = await metadata_service.fetch_live_torrent_metadata(app, records, {"dl-live": "transmission"})
    second = await metadata_service.fetch_live_torrent_metadata(app, records, {"dl-live": "transmission"})

    assert set(first) == {("dl-live", "a")}
    assert set(second) == {("dl-live", "a"), ("dl-live", "b")}
    batches = [call.kwargs["kwargs"]["ids"] for call in api_mock.await_args_list]
    assert batches == [["a"], ["b"], ["b"]]


@pytest.mark.asyncio
async def test_capped_hydration_rotates_past_lru_evictions(monkeypatch):
    from app.services import torrent_metadata as metadata_service

    client = SimpleNamespace(torrents_info=lambda **_kwargs: None)
    app = _live_metadata_app(0, client)
    records = [_live_metadata_record(f"hash-{index}") for index in range(8)]

    async def fetch_batch(*_args, **kwargs):
        return [_qb_live_payload(torrent_hash) for torrent_hash in kwargs["kwargs"]["torrent_hashes"]]

    api_mock = AsyncMock(side_effect=fetch_batch)
    monkeypatch.setattr(metadata_service, "_LIVE_METADATA_MAX_RECORDS", 2)
    monkeypatch.setattr(metadata_service, "_LIVE_METADATA_CACHE_MAX_ENTRIES", 4)
    monkeypatch.setattr(metadata_service, "_LIVE_METADATA_CACHE_TTL_SECONDS", 3600)
    monkeypatch.setattr(metadata_service, "call_downloader_api", api_mock)

    for _ in range(4):
        await metadata_service.fetch_live_torrent_metadata(app, records, {"dl-live": "qbittorrent"})

    batches = [call.kwargs["kwargs"]["torrent_hashes"] for call in api_mock.await_args_list]
    assert batches == [
        ["hash-0", "hash-1"],
        ["hash-2", "hash-3"],
        ["hash-4", "hash-5"],
        ["hash-6", "hash-7"],
    ]


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
    events = []
    bulk_mock = AsyncMock(side_effect=lambda *_args, **_kwargs: events.append("bulk"))
    save_mock = MagicMock(side_effect=lambda *_args: events.append("rid"))
    rid_cache = {"dl-1": 1}

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(
            torrents_async,
            "call_downloader_api",
            new=AsyncMock(return_value={"rid": 2, "torrents": {"abc": {"progress": 0.75}}}),
        ),
        patch.object(torrents_async, "fetch_qb_torrent_details", new=details_mock),
        patch.object(torrents_async, "bulk_upsert_with_retry", new=bulk_mock),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        await torrents_async.qb_add_torrents_info_only_async(db, [downloader], client=client)

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
    assert events == ["bulk", "rid"]
    assert rid_cache["dl-1"] == 2


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


def _complete_qb_torrent(torrent_hash="abc", name="完整名称"):
    return SimpleNamespace(
        hash=torrent_hash,
        name=name,
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


@pytest.mark.asyncio
async def test_qb_incremental_hydration_preserves_order_and_normalizes_hashes():
    from app.api.endpoints import torrents_async

    requested = [SimpleNamespace(hash="ABC"), SimpleNamespace(hash="def")]
    returned = [_complete_qb_torrent("DEF"), _complete_qb_torrent("abc")]

    with patch.object(
        torrents_async,
        "fetch_qb_torrent_details",
        new=AsyncMock(return_value=returned),
    ):
        hydrated = await torrents_async._hydrate_qb_incremental_torrents(
            SimpleNamespace(), requested, "dl-1", "hydrate-test"
        )

    assert [torrent.hash for torrent in hydrated] == ["abc", "DEF"]


@pytest.mark.asyncio
@pytest.mark.parametrize("returned_hashes", [[], ["abc"]])
async def test_qb_incremental_hydration_rejects_empty_or_partial_details(
    returned_hashes,
):
    from app.api.endpoints import torrents_async

    requested = [SimpleNamespace(hash="abc"), SimpleNamespace(hash="def")]
    returned = [_complete_qb_torrent(torrent_hash) for torrent_hash in returned_hashes]

    with patch.object(
        torrents_async,
        "fetch_qb_torrent_details",
        new=AsyncMock(return_value=returned),
    ):
        with pytest.raises(RuntimeError, match="hydration was incomplete"):
            await torrents_async._hydrate_qb_incremental_torrents(SimpleNamespace(), requested, "dl-1", "hydrate-test")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail_failure",
    [
        pytest.param("empty", id="empty"),
        pytest.param("partial", id="partial"),
        pytest.param(TimeoutError("details timed out"), id="timeout"),
        pytest.param(APIError("details failed"), id="api-error"),
    ],
)
async def test_qb_info_incomplete_hydration_falls_back_without_advancing_rid(
    detail_failure,
):
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(sync_maindata=lambda rid: None, torrents_info=lambda **kwargs: None)
    db = _empty_async_db()
    full_torrents = [_complete_qb_torrent("abc"), _complete_qb_torrent("def")]
    api_mock = AsyncMock(
        side_effect=[
            {
                "rid": 2,
                "torrents": {
                    "abc": {"progress": 0.5},
                    "def": {"progress": 0.25},
                },
            },
            full_torrents,
        ]
    )
    if detail_failure == "empty":
        details_mock = AsyncMock(return_value=[])
    elif detail_failure == "partial":
        details_mock = AsyncMock(return_value=[full_torrents[0]])
    else:
        details_mock = AsyncMock(side_effect=detail_failure)
    bulk_mock = AsyncMock()
    save_mock = MagicMock()
    rid_cache = {"dl-1": 1}

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "call_downloader_api", new=api_mock),
        patch.object(torrents_async, "fetch_qb_torrent_details", new=details_mock),
        patch.object(torrents_async, "bulk_upsert_with_retry", new=bulk_mock),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        await torrents_async.qb_add_torrents_info_only_async(db, [downloader], client=client)

    operations = [call.kwargs["operation"] for call in api_mock.await_args_list]
    assert operations == ["sync_maindata_incremental", "qb_torrents_info_only"]
    inserted = bulk_mock.await_args.args[1]
    assert {torrent["hash"] for torrent in inserted} == {"abc", "def"}
    assert all(torrent["name"] == "完整名称" for torrent in inserted)
    assert rid_cache["dl-1"] == 1
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_qb_info_removed_write_failure_falls_back_without_advancing_rid():
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(
        sync_maindata=lambda rid: None,
        torrents_info=lambda **kwargs: None,
    )
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.side_effect = [RuntimeError("removed write failed"), query_result]
    api_mock = AsyncMock(
        side_effect=[
            {"rid": 2, "torrents": {}, "torrents_removed": ["dead"]},
            [],
        ]
    )
    save_mock = MagicMock()
    rid_cache = {"dl-1": 1}

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "call_downloader_api", new=api_mock),
        patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        await torrents_async.qb_add_torrents_info_only_async(db, [downloader], client=client)

    operations = [call.kwargs["operation"] for call in api_mock.await_args_list]
    assert operations == ["sync_maindata_incremental", "qb_torrents_info_only"]
    assert rid_cache["dl-1"] == 1
    save_mock.assert_not_called()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_qb_info_removal_only_delta_commits_before_advancing_rid():
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(sync_maindata=lambda rid: None)
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.side_effect = [MagicMock(), query_result]
    events = []
    db.commit.side_effect = lambda: events.append("remove-commit")
    save_mock = MagicMock(side_effect=lambda *_args: events.append("rid"))
    rid_cache = {"dl-1": 1}

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(
            torrents_async,
            "call_downloader_api",
            new=AsyncMock(
                return_value={
                    "rid": 2,
                    "torrents": {},
                    "torrents_removed": ["dead"],
                }
            ),
        ),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        await torrents_async.qb_add_torrents_info_only_async(db, [downloader], client=client)

    assert events == ["remove-commit", "rid"]
    assert rid_cache["dl-1"] == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_qb_info_removal_commit_failure_falls_back_without_advancing_rid():
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(
        sync_maindata=lambda rid: None,
        torrents_info=lambda **kwargs: None,
    )
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.side_effect = [MagicMock(), query_result]
    db.commit.side_effect = RuntimeError("removed commit failed")
    api_mock = AsyncMock(
        side_effect=[
            {"rid": 2, "torrents": {}, "torrents_removed": ["dead"]},
            [],
        ]
    )
    save_mock = MagicMock()
    rid_cache = {"dl-1": 1}

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "call_downloader_api", new=api_mock),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        await torrents_async.qb_add_torrents_info_only_async(db, [downloader], client=client)

    operations = [call.kwargs["operation"] for call in api_mock.await_args_list]
    assert operations == ["sync_maindata_incremental", "qb_torrents_info_only"]
    assert rid_cache["dl-1"] == 1
    save_mock.assert_not_called()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("last_rid", "operation"),
    [(None, "sync_maindata_init"), (1, "sync_maindata_incremental")],
)
async def test_qb_info_db_write_failure_does_not_advance_initial_or_incremental_rid(last_rid, operation):
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(sync_maindata=lambda rid: None)
    db = _empty_async_db()
    full_torrent = _complete_qb_torrent()
    details_mock = AsyncMock(return_value=[full_torrent])
    save_mock = MagicMock()
    initial_cache = {} if last_rid is None else {"dl-1": last_rid}
    rid_cache = dict(initial_cache)

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(
            torrents_async,
            "call_downloader_api",
            new=AsyncMock(return_value={"rid": 2, "torrents": {"abc": {"progress": 0.5}}}),
        ) as api_mock,
        patch.object(torrents_async, "fetch_qb_torrent_details", new=details_mock),
        patch.object(
            torrents_async,
            "bulk_upsert_with_retry",
            new=AsyncMock(side_effect=RuntimeError("database write failed")),
        ),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        with pytest.raises(RuntimeError, match="database write failed"):
            await torrents_async.qb_add_torrents_info_only_async(db, [downloader], client=client)

    assert api_mock.await_args.kwargs["operation"] == operation
    assert rid_cache == initial_cache
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_qb_info_update_does_not_erase_good_ratio_when_payload_is_unavailable():
    """A transient client parse failure must omit ratio columns from UPDATE."""
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    torrent = _complete_qb_torrent()
    torrent.ratio = ValueError("temporary client parse failure")
    torrent.ratio_limit = None
    existing = SimpleNamespace(
        hash="abc",
        info_id="info-1",
        create_time=datetime(2026, 1, 1),
        progress=75.0,
        name="完整名称",
        size=4096,
        status="seeding",
        ratio=2.5,
        ratio_limit=3.0,
        tags="PT",
        category="电影",
        save_path="/downloads",
        super_seeding=False,
    )
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = [existing]
    db.execute.return_value = query_result
    bulk_mock = AsyncMock()

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
        patch.object(
            torrents_async,
            "call_downloader_api",
            new=AsyncMock(return_value=[torrent]),
        ),
        patch.object(torrents_async, "bulk_upsert_with_retry", new=bulk_mock),
    ):
        await torrents_async.qb_add_torrents_info_only_async(
            db,
            [downloader],
            client=SimpleNamespace(torrents_info=lambda **_kwargs: None),
        )

    updates = bulk_mock.await_args.args[2]
    assert len(updates) == 1
    assert "ratio" not in updates[0]
    assert "ratio_limit" not in updates[0]


@pytest.mark.asyncio
async def test_qb_info_update_clears_explicit_ratio_limit_sentinel():
    """qB -2 means no explicit per-torrent numeric limit and must become NULL."""
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    torrent = _complete_qb_torrent()
    torrent.ratio_limit = -2
    existing = SimpleNamespace(
        hash="abc",
        info_id="info-1",
        create_time=datetime(2026, 1, 1),
        progress=75.0,
        name="完整名称",
        size=4096,
        status="seeding",
        ratio=1.5,
        ratio_limit=3.0,
        tags="PT",
        category="电影",
        save_path="/downloads",
        super_seeding=False,
    )
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = [existing]
    db.execute.return_value = query_result
    bulk_mock = AsyncMock()

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
        patch.object(
            torrents_async,
            "call_downloader_api",
            new=AsyncMock(return_value=[torrent]),
        ),
        patch.object(torrents_async, "bulk_upsert_with_retry", new=bulk_mock),
    ):
        await torrents_async.qb_add_torrents_info_only_async(
            db,
            [downloader],
            client=SimpleNamespace(torrents_info=lambda **_kwargs: None),
        )

    updates = bulk_mock.await_args.args[2]
    assert len(updates) == 1
    assert updates[0]["ratio_limit"] is None


@pytest.mark.asyncio
async def test_qb_full_sync_incremental_branch_hydrates_changed_rows():
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(sync_maindata=lambda rid: None)
    db = _empty_async_db()
    hydrate_mock = AsyncMock(return_value=[])
    api_mock = AsyncMock(return_value={"rid": 2, "torrents": {"abc": {"progress": 0.5}}})

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
        patch.object(torrents_async, "_hydrate_qb_incremental_torrents", new=hydrate_mock),
        patch.object(torrents_async, "_enrich_qb_torrents_with_trackers", new=AsyncMock()),
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
async def test_qb_full_sync_main_commit_failure_does_not_advance_rid():
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(sync_maindata=lambda rid: None)
    db = _empty_async_db()
    db.commit.side_effect = RuntimeError("main commit failed")
    rid_cache = {"dl-1": 1}
    save_mock = MagicMock()

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "qbClient", return_value=client),
        patch.object(
            torrents_async,
            "call_downloader_api",
            new=AsyncMock(return_value={"rid": 2, "torrents": {}}),
        ),
        patch.object(torrents_async, "_retry_on_db_lock", new=AsyncMock()),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        with pytest.raises(RuntimeError, match="main commit failed"):
            await torrents_async.qb_add_torrents_async(db, [downloader])

    assert rid_cache["dl-1"] == 1
    save_mock.assert_not_called()


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
    save_mock = MagicMock()
    rid_cache = {"dl-1": 1}

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "qbClient", return_value=client),
        patch.object(torrents_async, "call_downloader_api", new=api_mock),
        patch.object(torrents_async, "_hydrate_qb_incremental_torrents", new=hydrate_mock),
        patch.object(torrents_async, "_enrich_qb_torrents_with_trackers", new=AsyncMock()),
        patch.object(torrents_async, "_retry_on_db_lock", new=AsyncMock()),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        await torrents_async.qb_add_torrents_async(db, [downloader])

    hydrate_mock.assert_awaited_once()
    assert hydrate_mock.await_args.args[2:] == (
        "dl-1",
        "qb_sync_retry_incremental_details",
    )
    assert api_mock.await_args_list[1].kwargs["operation"] == "sync_maindata_retry"
    assert rid_cache["dl-1"] == 2
    save_mock.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail_error",
    [
        pytest.param(TimeoutError("details timed out"), id="timeout"),
        pytest.param(APIError("details api failed"), id="api-error"),
    ],
)
async def test_qb_full_sync_retry_detail_failure_falls_back_without_advancing_rid(monkeypatch, detail_error):
    from app.api.endpoints import torrents_async

    downloader = _qb_downloader()
    client = SimpleNamespace(
        sync_maindata=lambda rid: None,
        torrents_info=lambda **kwargs: None,
    )
    db = _empty_async_db()
    hydrate_mock = AsyncMock(side_effect=detail_error)
    api_mock = AsyncMock(
        side_effect=[
            torrents_async.APIConnectionError("temporary failure"),
            {"rid": 2, "torrents": {"abc": {"progress": 0.5}}},
            [],
        ]
    )
    save_mock = MagicMock()
    rid_cache = {"dl-1": 1}
    monkeypatch.setattr(torrents_async.asyncio, "sleep", AsyncMock())

    with (
        patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", True),
        patch.object(torrents_async, "_QB_SYNC_RID_CACHE", rid_cache),
        patch.dict(
            torrents_async._QB_LAST_FULL_SYNC,
            {"dl-1": datetime.now().timestamp()},
            clear=True,
        ),
        patch.object(torrents_async, "qbClient", return_value=client),
        patch.object(torrents_async, "call_downloader_api", new=api_mock),
        patch.object(torrents_async, "_hydrate_qb_incremental_torrents", new=hydrate_mock),
        patch.object(torrents_async, "_enrich_qb_torrents_with_trackers", new=AsyncMock()),
        patch.object(torrents_async, "_retry_on_db_lock", new=AsyncMock()),
        patch.object(torrents_async, "_save_qb_rid_cache", new=save_mock),
    ):
        await torrents_async.qb_add_torrents_async(db, [downloader])

    operations = [call.kwargs["operation"] for call in api_mock.await_args_list]
    assert operations == [
        "sync_maindata_incremental",
        "sync_maindata_retry",
        "qb_torrents_info_full_sync",
    ]
    assert rid_cache["dl-1"] == 1
    save_mock.assert_not_called()
