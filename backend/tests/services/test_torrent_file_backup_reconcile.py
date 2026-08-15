# -*- coding: utf-8 -*-
"""info-only 同步后的种子文件备份增量补偿回归。"""

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.torrent_file_backup import TorrentFileBackupService
from app.downloader.models import BtDownloaders
from app.models.torrent_file_backup import TorrentFileBackup
from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService
from app.torrents.models import TorrentInfo

pytestmark = pytest.mark.asyncio


def _torrent(downloader_id: str, info_hash: str, name: str, torrent_file: str = "") -> TorrentInfo:
    now = datetime.utcnow()
    return TorrentInfo(
        id_=f"info-{info_hash[:8]}",
        downloader_id=downloader_id,
        downloader_name="test-downloader",
        torrent_id=info_hash,
        hash=info_hash,
        name=name,
        save_path="/downloads",
        size=1024,
        status="seeding",
        progress=100.0,
        torrent_file=torrent_file,
        added_date=now,
        completed_date=now,
        ratio=1.0,
        ratio_limit=None,
        tags="",
        category="",
        super_seeding="0",
        enabled=True,
        create_time=now,
        create_by="test",
        update_time=now,
        update_by="test",
        dr=0,
    )


async def test_reconcile_is_bounded_idempotent_and_supports_common_filenames(async_orphan_db, tmp_path):
    downloader_id = "550e8400-e29b-41d4-a716-446655440000"
    first_hash = "a" * 40
    second_hash = "b" * 40
    source_root = tmp_path / "torrent-sources"
    backup_root = tmp_path / "project-backups"
    source_root.mkdir()
    # qB 常见纯 hash 文件名（同时验证大小写不敏感）。
    (source_root / f"{first_hash.upper()}.torrent").write_bytes(b"first")
    # Transmission 常见 name.hash.torrent 文件名。
    (source_root / f"movie.{second_hash}.torrent").write_bytes(b"second")

    async_orphan_db.add(
        BtDownloaders(
            downloader_id=downloader_id,
            nickname="test-downloader",
            downloader_type=0,
        )
    )
    async_orphan_db.add_all(
        [
            _torrent(downloader_id, first_hash, "first"),
            _torrent(downloader_id, second_hash, "second"),
        ]
    )
    await async_orphan_db.commit()

    manager = TorrentFileBackupManagerService(
        db=async_orphan_db,
        file_backup_service=TorrentFileBackupService(backup_dir=str(backup_root)),
    )
    first_run = await manager.reconcile_missing_backups(
        downloader_id,
        str(source_root),
        batch_size=1,
    )
    assert first_run["pending"] == 2
    assert first_run["created"] == 1
    assert first_run["batch_limited"] is True

    second_run = await manager.reconcile_missing_backups(
        downloader_id,
        str(source_root),
        batch_size=10,
    )
    assert second_run["pending"] == 1
    assert second_run["created"] == 1

    third_run = await manager.reconcile_missing_backups(
        downloader_id,
        str(source_root),
        batch_size=10,
    )
    assert third_run["status"] == "no_action"
    assert third_run["pending"] == 0

    backups = list((await async_orphan_db.execute(select(TorrentFileBackup))).scalars().all())
    assert {backup.info_hash for backup in backups} == {first_hash, second_hash}
    assert {backup.downloader_id for backup in backups} == {downloader_id}
    torrents = list((await async_orphan_db.execute(select(TorrentInfo))).scalars().all())
    assert all(torrent.backup_file_path for torrent in torrents)
    assert all(Path(str(torrent.backup_file_path)).is_file() for torrent in torrents)


async def test_reconcile_respects_deleted_backup_tombstone(async_orphan_db, tmp_path):
    downloader_id = "550e8400-e29b-41d4-a716-446655440001"
    info_hash = "c" * 40
    source_root = tmp_path / "torrent-sources"
    backup_root = tmp_path / "project-backups"
    source_root.mkdir()
    (source_root / f"{info_hash}.torrent").write_bytes(b"payload")
    async_orphan_db.add(BtDownloaders(downloader_id=downloader_id, nickname="test", downloader_type=0))
    async_orphan_db.add(_torrent(downloader_id, info_hash, "deleted-by-user"))
    async_orphan_db.add(
        TorrentFileBackup(
            info_hash=info_hash,
            file_path=str(backup_root / "removed.torrent"),
            downloader_id=downloader_id,
            is_deleted=True,
        )
    )
    await async_orphan_db.commit()

    manager = TorrentFileBackupManagerService(
        db=async_orphan_db,
        file_backup_service=TorrentFileBackupService(backup_dir=str(backup_root)),
    )
    result = await manager.reconcile_missing_backups(downloader_id, str(source_root))

    assert result["status"] == "no_action"
    assert result["created"] == 0
    rows = list((await async_orphan_db.execute(select(TorrentFileBackup))).scalars().all())
    assert len(rows) == 1
    assert rows[0].is_deleted is True


async def test_reconcile_reports_unavailable_runtime_source_once(async_orphan_db, tmp_path):
    downloader_id = "550e8400-e29b-41d4-a716-446655440002"
    info_hash = "d" * 40
    backup_root = tmp_path / "project-backups"
    async_orphan_db.add(BtDownloaders(downloader_id=downloader_id, nickname="test", downloader_type=1))
    async_orphan_db.add(_torrent(downloader_id, info_hash, "missing-source"))
    await async_orphan_db.commit()

    manager = TorrentFileBackupManagerService(
        db=async_orphan_db,
        file_backup_service=TorrentFileBackupService(backup_dir=str(backup_root)),
    )
    result = await manager.reconcile_missing_backups(downloader_id, None)

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "torrent_save_path_unavailable"
    assert result["attempted"] == 1
    assert result["missing_source"] == 1
