# -*- coding: utf-8 -*-
"""
路径维护清理与恢复回归（verified-bugfix-remediation W4）

覆盖：
- _sync_active_path：auto 禁用路径在种子回归后恢复启用；user 禁用路径不被扫描推翻
- _cleanup_obsolete_paths：宽限期（PATH_CLEANUP_GRACE_DAYS）内不禁用；
  超期才禁用并标 disabled_by='auto'；last_updated_time 为空时 coalesce 兜底
- path_maintenance_service：delete_path / update_path 的用户来源标记
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as SyncSession

from app.models.downloader_path_maintenance import DownloaderPathMaintenance


class FakeAdmissionController:
    """伪 admission_controller：db_write_scope 为幂等 async 上下文管理器。"""

    def db_write_scope(self):
        class _Scope:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *_exc):
                return False

        return _Scope()


async def _add_path(session, downloader_id, path_value, **kwargs):
    record = DownloaderPathMaintenance(
        downloader_id=downloader_id,
        path_type=kwargs.pop("path_type", "active"),
        path_value=path_value,
        is_enabled=kwargs.pop("is_enabled", True),
        torrent_count=kwargs.pop("torrent_count", 0),
        last_updated_time=kwargs.pop("last_updated_time", None),
    )
    record.disabled_by = kwargs.pop("disabled_by", None)
    session.add(record)
    await session.commit()
    return record


async def _load_paths(session, downloader_id):
    result = await session.execute(
        select(DownloaderPathMaintenance).where(
            DownloaderPathMaintenance.downloader_id == downloader_id,
            DownloaderPathMaintenance.path_type == "active",
        )
    )
    return result.scalars().all()


def _task_with_fake_admission():
    from app.tasks.scheduler.downloader_path_scan import DownloaderPathScanTask

    return DownloaderPathScanTask(), patch(
        "app.tasks.scheduler.downloader_path_scan.admission_controller",
        FakeAdmissionController(),
    )


class TestSyncActivePathReenable:
    """W4-1：_sync_active_path 仅恢复 auto 禁用路径。"""

    @pytest.mark.asyncio
    async def test_auto_disabled_path_reenabled_when_torrents_return(self, async_orphan_db):
        """auto 禁用的路径在种子回归后恢复启用并清空来源标记。"""
        task, admission_patch = _task_with_fake_admission()
        await _add_path(
            async_orphan_db,
            "dl-1",
            "/downloads/movies/",
            is_enabled=False,
            disabled_by="auto",
            last_updated_time=datetime.utcnow() - timedelta(days=40),
        )
        with admission_patch:
            await task._sync_active_path(async_orphan_db, "dl-1", "/downloads/movies/", 3)

        records = await _load_paths(async_orphan_db, "dl-1")
        assert len(records) == 1
        assert records[0].is_enabled is True
        assert records[0].disabled_by is None
        assert records[0].torrent_count == 3

    @pytest.mark.asyncio
    async def test_user_disabled_path_not_reenabled(self, async_orphan_db):
        """用户手动禁用的路径不被每小时扫描重新启用。"""
        task, admission_patch = _task_with_fake_admission()
        await _add_path(
            async_orphan_db,
            "dl-1",
            "/downloads/movies/",
            is_enabled=False,
            disabled_by="user",
            last_updated_time=datetime.utcnow() - timedelta(days=1),
        )
        with admission_patch:
            await task._sync_active_path(async_orphan_db, "dl-1", "/downloads/movies/", 5)

        records = await _load_paths(async_orphan_db, "dl-1")
        assert records[0].is_enabled is False
        assert records[0].disabled_by == "user"

    @pytest.mark.asyncio
    async def test_enabled_path_keeps_enabled(self, async_orphan_db):
        """启用中且从未禁用的路径保持启用，来源标记保持 NULL。"""
        task, admission_patch = _task_with_fake_admission()
        await _add_path(
            async_orphan_db,
            "dl-1",
            "/downloads/movies/",
            is_enabled=True,
            disabled_by=None,
            last_updated_time=datetime.utcnow(),
        )
        with admission_patch:
            await task._sync_active_path(async_orphan_db, "dl-1", "/downloads/movies/", 2)

        records = await _load_paths(async_orphan_db, "dl-1")
        assert records[0].is_enabled is True
        assert records[0].disabled_by is None


class TestCleanupObsoletePathsGracePeriod:
    """W4-2：宽限期与 auto 来源标记。"""

    @pytest.mark.asyncio
    async def test_within_grace_period_not_disabled(self, async_orphan_db):
        """宽限期（30 天）内路径无种子：不禁用，保留历史使用路径。"""
        from app.tasks.scheduler import downloader_path_scan as scan_module

        task = scan_module.DownloaderPathScanTask()
        await _add_path(
            async_orphan_db,
            "dl-1",
            "/downloads/movies/",
            last_updated_time=datetime.utcnow() - timedelta(days=10),
        )
        with (
            patch.object(scan_module.settings, "PATH_CLEANUP_GRACE_DAYS", 30),
            patch.object(scan_module, "admission_controller", FakeAdmissionController()),
        ):
            await task._cleanup_obsolete_paths(async_orphan_db, "dl-1", set())

        records = await _load_paths(async_orphan_db, "dl-1")
        assert records[0].is_enabled is True

    @pytest.mark.asyncio
    async def test_beyond_grace_period_disabled_with_auto(self, async_orphan_db):
        """超过宽限期仍无种子：禁用并标记 disabled_by='auto'（种子回归后可自愈）。"""
        from app.tasks.scheduler import downloader_path_scan as scan_module

        task = scan_module.DownloaderPathScanTask()
        await _add_path(
            async_orphan_db,
            "dl-1",
            "/downloads/movies/",
            last_updated_time=datetime.utcnow() - timedelta(days=40),
        )
        with (
            patch.object(scan_module.settings, "PATH_CLEANUP_GRACE_DAYS", 30),
            patch.object(scan_module, "admission_controller", FakeAdmissionController()),
        ):
            await task._cleanup_obsolete_paths(async_orphan_db, "dl-1", set())

        records = await _load_paths(async_orphan_db, "dl-1")
        assert records[0].is_enabled is False
        assert records[0].disabled_by == "auto"

    @pytest.mark.asyncio
    async def test_null_last_updated_coalesce_fallback(self, async_orphan_db):
        """last_updated_time 为空（可空列）：回退 created_at，超期则禁用。"""
        from app.tasks.scheduler import downloader_path_scan as scan_module

        task = scan_module.DownloaderPathScanTask()
        await _add_path(async_orphan_db, "dl-1", "/downloads/old/", last_updated_time=None)
        # created_at 由模型默认生成（当前时间）→ 宽限期内不禁用
        with (
            patch.object(scan_module.settings, "PATH_CLEANUP_GRACE_DAYS", 30),
            patch.object(scan_module, "admission_controller", FakeAdmissionController()),
        ):
            await task._cleanup_obsolete_paths(async_orphan_db, "dl-1", set())

        records = await _load_paths(async_orphan_db, "dl-1")
        assert records[0].is_enabled is True

    @pytest.mark.asyncio
    async def test_path_with_torrents_kept(self, async_orphan_db):
        """当前有种子的路径不受清理影响。"""
        from app.tasks.scheduler import downloader_path_scan as scan_module

        task = scan_module.DownloaderPathScanTask()
        await _add_path(
            async_orphan_db,
            "dl-1",
            "/downloads/movies/",
            last_updated_time=datetime.utcnow() - timedelta(days=40),
        )
        with (
            patch.object(scan_module.settings, "PATH_CLEANUP_GRACE_DAYS", 30),
            patch.object(scan_module, "admission_controller", FakeAdmissionController()),
        ):
            await task._cleanup_obsolete_paths(async_orphan_db, "dl-1", {"/downloads/movies/"})

        records = await _load_paths(async_orphan_db, "dl-1")
        assert records[0].is_enabled is True

    @pytest.mark.asyncio
    async def test_grace_zero_keeps_legacy_behavior(self, async_orphan_db):
        """PATH_CLEANUP_GRACE_DAYS=0：恢复旧行为（当前无种子立即禁用）。"""
        from app.tasks.scheduler import downloader_path_scan as scan_module

        task = scan_module.DownloaderPathScanTask()
        await _add_path(
            async_orphan_db,
            "dl-1",
            "/downloads/movies/",
            last_updated_time=datetime.utcnow() - timedelta(days=1),
        )
        with (
            patch.object(scan_module.settings, "PATH_CLEANUP_GRACE_DAYS", 0),
            patch.object(scan_module, "admission_controller", FakeAdmissionController()),
        ):
            await task._cleanup_obsolete_paths(async_orphan_db, "dl-1", set())

        records = await _load_paths(async_orphan_db, "dl-1")
        assert records[0].is_enabled is False
        assert records[0].disabled_by == "auto"


class TestPathMaintenanceServiceUserSource:
    """W4-1：用户手动禁用/启用标记 disabled_by 来源。"""

    def _make_sync_session(self):
        import sqlalchemy
        from sqlalchemy.pool import StaticPool

        from app.database import Base

        engine = sqlalchemy.create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine, tables=[DownloaderPathMaintenance.__table__])
        return SyncSession(bind=engine)

    def test_delete_path_marks_user_source(self):
        from app.services.path_maintenance_service import PathMaintenanceService

        session = self._make_sync_session()
        record = DownloaderPathMaintenance(
            downloader_id="dl-1", path_type="active", path_value="/downloads/movies/", is_enabled=True
        )
        session.add(record)
        session.commit()

        service = PathMaintenanceService(db=session)
        assert service.delete_path(record.id) is True

        session.refresh(record)
        assert record.is_enabled is False
        assert record.disabled_by == "user"

    def test_update_path_disable_marks_user_source(self):
        from app.services.path_maintenance_service import PathMaintenanceService

        session = self._make_sync_session()
        record = DownloaderPathMaintenance(
            downloader_id="dl-1", path_type="active", path_value="/downloads/movies/", is_enabled=True
        )
        session.add(record)
        session.commit()

        service = PathMaintenanceService(db=session)
        assert service.update_path(record.id, is_enabled=False) is True

        session.refresh(record)
        assert record.disabled_by == "user"

    def test_update_path_reenable_clears_source(self):
        from app.services.path_maintenance_service import PathMaintenanceService

        session = self._make_sync_session()
        record = DownloaderPathMaintenance(
            downloader_id="dl-1", path_type="active", path_value="/downloads/movies/", is_enabled=False
        )
        record.disabled_by = "auto"
        session.add(record)
        session.commit()

        service = PathMaintenanceService(db=session)
        assert service.update_path(record.id, is_enabled=True) is True

        session.refresh(record)
        assert record.is_enabled is True
        assert record.disabled_by is None
