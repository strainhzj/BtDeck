"""辅种数量全量计算与单分组增量更新测试。"""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.services.auxiliary_seed_count_service import (
    decrement_auxiliary_seed_count_async,
    get_auxiliary_seed_key,
    make_auxiliary_seed_key,
    refresh_auxiliary_seed_counts,
    set_active_auxiliary_seed_count_async,
)
from app.torrents.models import TorrentInfo


def _torrent(
    info_id: str,
    downloader_id: str,
    *,
    name: str,
    size: float,
    torrent_file: str,
    dr: int = 0,
    deleted_at=None,
):
    now = datetime(2026, 1, 1, 12, 0, 0)
    return TorrentInfo(
        id_=info_id,
        downloader_id=downloader_id,
        downloader_name=downloader_id,
        torrent_id=info_id,
        hash=f"{info_id}-hash",
        name=name,
        save_path="/downloads",
        size=size,
        status="seeding",
        progress=100.0,
        torrent_file=torrent_file,
        added_date=now,
        completed_date=now,
        ratio=1.0,
        ratio_limit=None,
        tags="",
        category="",
        super_seeding="",
        enabled=True,
        create_time=now,
        create_by="test",
        update_time=now,
        update_by="test",
        dr=dr,
        deleted_at=deleted_at,
    )


@pytest.mark.parametrize(
    ("name", "size"),
    [
        (None, 100),
        ("   ", 100),
        ("valid", None),
        ("valid", True),
    ],
)
def test_invalid_name_or_size_has_no_auxiliary_key(name, size):
    """空名称、空大小和布尔值大小不能误生成辅种分组键。"""

    assert make_auxiliary_seed_key(name, size) is None


async def test_refresh_counts_same_key_across_downloaders(async_orphan_db):
    group = [
        _torrent(
            f"same-{index}",
            f"downloader-{index % 2}",
            name="same",
            size=100.0,
            torrent_file=f"same-{index}.torrent",
        )
        for index in range(4)
    ]
    standalone = _torrent("standalone", "downloader-3", name="other", size=100.0, torrent_file="other.torrent")
    invalid = _torrent("invalid", "downloader-4", name="", size=100.0, torrent_file="invalid.torrent")
    deleted = _torrent(
        "deleted",
        "downloader-5",
        name="same",
        size=100.0,
        torrent_file="deleted.torrent",
        deleted_at=datetime(2026, 1, 2, 12, 0, 0),
    )
    async_orphan_db.add_all([*group, standalone, invalid, deleted])
    await async_orphan_db.commit()

    stats = await refresh_auxiliary_seed_counts(async_orphan_db)
    assert stats["updated_count"] == 6

    rows = (
        (
            await async_orphan_db.execute(
                select(TorrentInfo).where(TorrentInfo.info_id.in_([row.info_id for row in group]))
            )
        )
        .scalars()
        .all()
    )
    assert {row.auxiliary_seed_count for row in rows} == {4}

    assert (
        await async_orphan_db.execute(
            select(TorrentInfo.auxiliary_seed_count).where(TorrentInfo.info_id == standalone.info_id)
        )
    ).scalar_one() == 1
    assert (
        await async_orphan_db.execute(
            select(TorrentInfo.auxiliary_seed_count).where(TorrentInfo.info_id == invalid.info_id)
        )
    ).scalar_one() == 1


async def test_incremental_remove_and_restore_keep_group_count(async_orphan_db):
    group = [
        _torrent(
            f"incremental-{index}",
            f"downloader-{index}",
            name="same",
            size=100.0,
            torrent_file=f"incremental-{index}.torrent",
        )
        for index in range(4)
    ]
    async_orphan_db.add_all(group)
    await async_orphan_db.commit()
    await refresh_auxiliary_seed_counts(async_orphan_db)

    key = get_auxiliary_seed_key(group[0])
    group[0].dr = 1
    await decrement_auxiliary_seed_count_async(async_orphan_db, key)
    await async_orphan_db.commit()

    remaining = (
        (
            await async_orphan_db.execute(
                select(TorrentInfo.auxiliary_seed_count).where(
                    TorrentInfo.dr == 0,
                    TorrentInfo.deleted_at.is_(None),
                    TorrentInfo.name == "same",
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining == [3, 3, 3]

    group[0].dr = 0
    await set_active_auxiliary_seed_count_async(async_orphan_db, key, 4)
    await async_orphan_db.commit()
    restored = (
        (await async_orphan_db.execute(select(TorrentInfo.auxiliary_seed_count).where(TorrentInfo.name == "same")))
        .scalars()
        .all()
    )
    assert restored == [4, 4, 4, 4]


async def test_refresh_matches_name_and_size_only(async_orphan_db):
    name = "冰与火之歌S01-S08"
    active_group = [
        _torrent(
            f"active-{index}",
            "transmission",
            name=name,
            size=183145798849.0,
            torrent_file=f"/config/torrents/{index}.torrent",
        )
        for index in range(31)
    ]
    deleted_group = [
        _torrent(
            f"deleted-{index}",
            "transmission",
            name=name,
            size=183145798849.0,
            torrent_file=f"/config/torrents/deleted-{index}.torrent",
            dr=1,
        )
        for index in range(14)
    ]
    async_orphan_db.add_all([*active_group, *deleted_group])
    await async_orphan_db.commit()

    await refresh_auxiliary_seed_counts(async_orphan_db)

    counts = (
        (
            await async_orphan_db.execute(
                select(TorrentInfo.auxiliary_seed_count).where(
                    TorrentInfo.name == name,
                    TorrentInfo.dr == 0,
                    TorrentInfo.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert counts == [31] * 31
