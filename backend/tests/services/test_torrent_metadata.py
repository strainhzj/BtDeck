"""Regression tests for live torrent metadata hydration."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.torrent_metadata import (
    map_qb_torrent_metadata,
    map_transmission_torrent_metadata,
)


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
    hydrate_mock = AsyncMock(return_value=[full_torrent])
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
        patch.object(
            torrents_async, "_hydrate_qb_incremental_torrents", new=hydrate_mock
        ),
        patch.object(torrents_async, "bulk_upsert_with_retry", new=bulk_mock),
        patch.object(torrents_async, "_save_qb_rid_cache"),
    ):
        await torrents_async.qb_add_torrents_info_only_async(
            db, [downloader], client=client
        )

    hydrate_mock.assert_awaited_once()
    inserted = bulk_mock.await_args.args[1]
    assert len(inserted) == 1
    assert inserted[0]["name"] == "完整名称"
    assert inserted[0]["save_path"] == "/downloads"
    assert inserted[0]["size"] == 4096
    assert inserted[0]["status"] == "seeding"
