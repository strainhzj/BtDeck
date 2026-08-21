# -*- coding: utf-8 -*-
"""info-only 同步后的种子文件备份增量补偿回归。"""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.filename_utils import FilenameUtils
from app.core.torrent_file_backup import TorrentFileBackupService
from app.downloader.models import BtDownloaders
from app.models.torrent_file_backup import TorrentFileBackup
from app.repositories.torrent_file_backup_repository import TorrentFileBackupRepository
from app.schemas.torrent_backup import TorrentFileBackupCreate
from app.services.torrent_file_backup_manager import TorrentFileBackupManagerService

import bencodepy


def _valid_torrent_bytes() -> bytes:
    """最小合法 bencode 种子（含 info 字典），满足 core 层内容校验。"""
    return bencodepy.encode({b"info": {b"name": b"t", b"length": 1}})

from app.torrents.models import TorrentInfo

pytestmark = pytest.mark.asyncio


def _torrent(
    downloader_id: str,
    info_hash: str,
    name: str,
    torrent_file: str = "",
    added_date: datetime | None = None,
    dr: int = 0,
    deleted_at: datetime | None = None,
) -> TorrentInfo:
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
        added_date=added_date or now,
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
        dr=dr,
        deleted_at=deleted_at,
    )


async def test_reconcile_is_bounded_idempotent_and_supports_common_filenames(async_orphan_db, tmp_path):
    downloader_id = "550e8400-e29b-41d4-a716-446655440000"
    first_hash = "a" * 40
    second_hash = "b" * 40
    source_root = tmp_path / "torrent-sources"
    backup_root = tmp_path / "project-backups"
    source_root.mkdir()
    # qB 常见纯 hash 文件名（同时验证大小写不敏感）。
    (source_root / f"{first_hash.upper()}.torrent").write_bytes(_valid_torrent_bytes())
    # Transmission 常见 name.hash.torrent 文件名。
    (source_root / f"movie.{second_hash}.torrent").write_bytes(_valid_torrent_bytes())

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
    (source_root / f"{info_hash}.torrent").write_bytes(_valid_torrent_bytes())
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


class TestReconcileSourceResolutionAndReuse:
    """源定位链与文件复用路径的回归保护。"""

    async def test_reuses_referenced_and_project_backup_files_without_copy(self, async_orphan_db, tmp_path):
        """backup_file_path 已存在或项目备份目录已有旧文件时直接复用，不再复制。"""
        downloader_id = "550e8400-e29b-41d4-a716-446655440010"
        backup_root = tmp_path / "project-backups"
        backup_root.mkdir()
        referenced = backup_root / "referenced.torrent"
        referenced.write_bytes(_valid_torrent_bytes())

        referenced_torrent = _torrent(downloader_id, "e" * 40, "referenced")
        referenced_torrent.backup_file_path = str(referenced)
        project_torrent = _torrent(downloader_id, "f" * 40, "project-old")
        project_filename = FilenameUtils.generate_backup_filename(project_torrent.info_id, project_torrent.name or "")
        project_file = backup_root / project_filename
        project_file.write_bytes(b"project-old")

        async_orphan_db.add(BtDownloaders(downloader_id=downloader_id, nickname="test", downloader_type=0))
        async_orphan_db.add_all([referenced_torrent, project_torrent])
        await async_orphan_db.commit()

        service = TorrentFileBackupService(backup_dir=str(backup_root))
        manager = TorrentFileBackupManagerService(db=async_orphan_db, file_backup_service=service)
        with patch.object(service, "backup_torrent_file_from_path") as copy_spy:
            result = await manager.reconcile_missing_backups(downloader_id, str(tmp_path))

        copy_spy.assert_not_called()
        assert result["created"] == 2
        assert result["reused_existing_file"] == 2
        rows = {
            row.info_hash: row for row in (await async_orphan_db.execute(select(TorrentFileBackup))).scalars().all()
        }
        assert rows["e" * 40].file_path == str(referenced)
        assert rows["f" * 40].file_path == str(project_file)

    async def test_resolves_sources_from_direct_path_and_torrents_subdir(self, async_orphan_db, tmp_path):
        """torrent_file 直连路径与下载器 .torrents 子目录索引都能作为拷贝源。"""
        downloader_id = "550e8400-e29b-41d4-a716-446655440011"
        source_root = tmp_path / "torrent-sources"
        (source_root / ".torrents").mkdir(parents=True)
        backup_root = tmp_path / "project-backups"
        backup_root.mkdir()

        direct_hash = "1" * 40
        direct_source = source_root / "direct.torrent"
        direct_source.write_bytes(_valid_torrent_bytes())
        direct_torrent = _torrent(downloader_id, direct_hash, "direct", torrent_file=str(direct_source))
        subdir_hash = "2" * 40
        (source_root / ".torrents" / f"{subdir_hash}.torrent").write_bytes(_valid_torrent_bytes())
        subdir_torrent = _torrent(downloader_id, subdir_hash, "subdir")

        async_orphan_db.add(BtDownloaders(downloader_id=downloader_id, nickname="test", downloader_type=0))
        async_orphan_db.add_all([direct_torrent, subdir_torrent])
        await async_orphan_db.commit()

        manager = TorrentFileBackupManagerService(
            db=async_orphan_db,
            file_backup_service=TorrentFileBackupService(backup_dir=str(backup_root)),
        )
        result = await manager.reconcile_missing_backups(downloader_id, str(source_root))

        assert result["created"] == 2
        assert result["missing_source"] == 0
        assert result["batch_limited"] is False
        torrents = {
            torrent.hash: torrent.backup_file_path
            for torrent in (await async_orphan_db.execute(select(TorrentInfo))).scalars().all()
        }
        assert all(path and Path(path).is_file() for path in torrents.values())

    async def test_copy_failure_records_missing_source_without_row(self, async_orphan_db, tmp_path):
        """源定位成功但复制失败：计入 missing_source，不落库、不回填路径。"""
        downloader_id = "550e8400-e29b-41d4-a716-446655440012"
        source_root = tmp_path / "torrent-sources"
        source_root.mkdir()
        backup_root = tmp_path / "project-backups"
        backup_root.mkdir()
        source = source_root / "broken.torrent"
        source.write_bytes(b"payload")
        torrent = _torrent(downloader_id, "3" * 40, "broken", torrent_file=str(source))
        async_orphan_db.add(BtDownloaders(downloader_id=downloader_id, nickname="test", downloader_type=0))
        async_orphan_db.add(torrent)
        await async_orphan_db.commit()

        service = TorrentFileBackupService(backup_dir=str(backup_root))
        manager = TorrentFileBackupManagerService(db=async_orphan_db, file_backup_service=service)
        with patch.object(
            service,
            "backup_torrent_file_from_path",
            return_value={"success": False, "error": "disk full"},
        ):
            result = await manager.reconcile_missing_backups(downloader_id, str(source_root))

        assert result["created"] == 0
        assert result["missing_source"] == 1
        assert result["status"] == "skipped"
        assert result["skip_reason"] == "torrent_source_not_found"
        rows = (await async_orphan_db.execute(select(TorrentFileBackup))).scalars().all()
        assert rows == []
        await async_orphan_db.refresh(torrent)
        assert not torrent.backup_file_path

    async def test_commit_failure_rolls_back_and_removes_newly_copied_files(self, async_orphan_db, tmp_path):
        """写库失败时回滚事务并清理本轮新复制的文件，不留孤儿备份。"""
        downloader_id = "550e8400-e29b-41d4-a716-446655440013"
        source_root = tmp_path / "torrent-sources"
        source_root.mkdir()
        backup_root = tmp_path / "project-backups"
        backup_root.mkdir()
        source = source_root / "rollback.torrent"
        source.write_bytes(_valid_torrent_bytes())
        torrent = _torrent(downloader_id, "4" * 40, "rollback", torrent_file=str(source))
        async_orphan_db.add(BtDownloaders(downloader_id=downloader_id, nickname="test", downloader_type=0))
        async_orphan_db.add(torrent)
        await async_orphan_db.commit()

        manager = TorrentFileBackupManagerService(
            db=async_orphan_db,
            file_backup_service=TorrentFileBackupService(backup_dir=str(backup_root)),
        )
        with patch.object(async_orphan_db, "commit", side_effect=RuntimeError("db offline")):
            with pytest.raises(RuntimeError, match="db offline"):
                await manager.reconcile_missing_backups(downloader_id, str(source_root))

        rows = (await async_orphan_db.execute(select(TorrentFileBackup))).scalars().all()
        assert rows == []
        # 备份目录不留本轮新复制出的文件
        assert list(backup_root.glob("*.torrent")) == []


class TestReconcileSelectionFilters:
    """补偿目标筛选与排序契约。"""

    async def test_only_target_downloader_active_torrents_selected_newest_first(self, async_orphan_db, tmp_path):
        """仅本下载器、dr=0、未删除、40 位 hash 的种子入选；批次按添加时间倒序。"""
        downloader_id = "550e8400-e29b-41d4-a716-446655440014"
        other_downloader = "550e8400-e29b-41d4-a716-446655440099"
        source_root = tmp_path / "torrent-sources"
        source_root.mkdir()
        backup_root = tmp_path / "project-backups"
        backup_root.mkdir()
        now = datetime.utcnow()

        newest = _torrent(downloader_id, "a" * 40, "newest", added_date=now)
        older = _torrent(downloader_id, "b" * 40, "older", added_date=now - timedelta(days=1))
        excluded_cases = [
            _torrent(other_downloader, "c" * 40, "other-downloader"),
            _torrent(downloader_id, "d" * 40, "removed", dr=1),
            _torrent(downloader_id, "e" * 40, "deleted", deleted_at=now),
            _torrent(downloader_id, "f" * 39, "short-hash"),
        ]
        async_orphan_db.add(BtDownloaders(downloader_id=downloader_id, nickname="a", downloader_type=0))
        async_orphan_db.add(BtDownloaders(downloader_id=other_downloader, nickname="b", downloader_type=0))
        async_orphan_db.add_all([newest, older, *excluded_cases])
        await async_orphan_db.commit()
        for torrent in [newest, older]:
            (source_root / f"{torrent.hash}.torrent").write_bytes(_valid_torrent_bytes())

        manager = TorrentFileBackupManagerService(
            db=async_orphan_db,
            file_backup_service=TorrentFileBackupService(backup_dir=str(backup_root)),
        )
        first_run = await manager.reconcile_missing_backups(downloader_id, str(source_root), batch_size=1)
        assert first_run["pending"] == 2
        assert first_run["created"] == 1

        backed_hashes = {
            row.info_hash for row in (await async_orphan_db.execute(select(TorrentFileBackup))).scalars().all()
        }
        assert backed_hashes == {newest.hash}

        second_run = await manager.reconcile_missing_backups(downloader_id, str(source_root), batch_size=10)
        assert second_run["created"] == 1
        backed_hashes = {
            row.info_hash for row in (await async_orphan_db.execute(select(TorrentFileBackup))).scalars().all()
        }
        assert backed_hashes == {newest.hash, older.hash}

    def test_runtime_path_mapping_falls_back_to_original_on_error(self):
        """路径映射抛异常时保留原始路径；无映射服务时原样返回。"""
        manager = TorrentFileBackupManagerService()
        assert manager._map_runtime_path("/downloads/a.torrent") == "/downloads/a.torrent"

        class BrokenMapping:
            def internal_to_external(self, path: str) -> str:
                raise ValueError("unmapped")

        manager_with_broken = TorrentFileBackupManagerService(path_mapping_service=BrokenMapping())
        assert manager_with_broken._map_runtime_path("/x/a.torrent") == "/x/a.torrent"

        class FixedMapping:
            def internal_to_external(self, path: str) -> str:
                return path.replace("/internal", "/external")

        manager_with_mapping = TorrentFileBackupManagerService(path_mapping_service=FixedMapping())
        assert manager_with_mapping._map_runtime_path("/internal/a.torrent") == "/external/a.torrent"


class TestBackupDownloaderIdStringContract:
    """downloader_id UUID 字符串类型契约（仓储/schema/端点辅助）。"""

    async def test_repository_filters_and_counts_by_string_downloader_id(self, async_orphan_db):
        repository = TorrentFileBackupRepository(async_orphan_db)
        uuid_a = "550e8400-e29b-41d4-a716-446655440020"
        uuid_b = "660e8400-e29b-41d4-a716-446655440021"
        await repository.create(info_hash="7" * 40, file_path="backup/a.torrent", downloader_id=uuid_a)
        await repository.create(info_hash="8" * 40, file_path="backup/b.torrent", downloader_id=uuid_b)
        await async_orphan_db.commit()

        rows_a = await repository.list_by_downloader(uuid_a)
        assert [row.info_hash for row in rows_a] == ["7" * 40]
        assert await repository.count_by_downloader(uuid_a) == 1
        assert await repository.count_by_downloader("not-exist-id") == 0

    def test_create_schema_requires_non_empty_string_downloader_id(self):
        payload = {
            "info_hash": "9" * 40,
            "torrent_name": "example.torrent",
            "downloader_id": "550e8400-e29b-41d4-a716-446655440000",
        }
        assert TorrentFileBackupCreate(**payload).downloader_id == payload["downloader_id"]
        with pytest.raises(ValidationError):
            TorrentFileBackupCreate(**{**payload, "downloader_id": ""})

    def test_get_downloader_from_store_matches_ids_by_string(self):
        """快照中的 ID 无论 UUID 字符串还是整数值，都按 str() 归一比较。"""
        from app.api.endpoints.torrent_backup import get_downloader_from_store

        uuid_downloader = SimpleNamespace(downloader_id="550e8400-e29b-41d4-a716-446655440000")
        int_like_downloader = SimpleNamespace(downloader_id=5)
        app = SimpleNamespace(
            state=SimpleNamespace(
                store=SimpleNamespace(get_snapshot_sync=lambda: [uuid_downloader, int_like_downloader])
            )
        )
        assert get_downloader_from_store("550e8400-e29b-41d4-a716-446655440000", app) is uuid_downloader
        assert get_downloader_from_store("5", app) is int_like_downloader
        assert get_downloader_from_store("missing", app) is None


def test_reconcile_batch_size_setting_default_is_positive():
    """补偿批次配置默认值必须为正，防止配置误删后单轮失控。"""
    from app.core.config import settings

    assert settings.TORRENT_BACKUP_RECONCILE_BATCH_SIZE >= 1
