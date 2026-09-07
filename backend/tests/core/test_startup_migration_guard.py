"""应用生命周期的数据库迁移 fail-fast 回归。"""

import pytest
from fastapi import FastAPI

from app.startup.lifecycle import lifespan


@pytest.mark.asyncio
async def test_lifespan_stops_before_initialization_when_migration_fails(monkeypatch):
    events: list[str] = []

    monkeypatch.setattr(
        "app.database.init_config_file",
        lambda: events.append("config"),
    )
    monkeypatch.setattr(
        "app.yamlConfig.yaml.reload",
        lambda: events.append("yaml"),
    )
    monkeypatch.setattr(
        "app.core.migration.migrate_database",
        lambda: False,
    )
    monkeypatch.setattr(
        "app.database.init_db",
        lambda: events.append("seed"),
    )

    with pytest.raises(RuntimeError, match="数据库迁移未完成"):
        async with lifespan(FastAPI()):
            pytest.fail("迁移失败时不得进入已启动状态")

    assert events == ["config", "yaml"]


@pytest.mark.asyncio
async def test_android_lifespan_skips_filesystem_recovery_and_dispatchers(monkeypatch):
    from unittest.mock import AsyncMock, Mock
    from app.startup import lifecycle

    monkeypatch.setenv("BTDECK_PLATFORM", "android-server")
    for target in (
        "app.database.init_config_file",
        "app.yamlConfig.yaml.reload",
        "app.database.init_db",
        "app.downloader.initialization.encrypt_plaintext_downloader_passwords",
        "app.services.downloader_api_runtime.downloader_api_runtime.shutdown",
    ):
        monkeypatch.setattr(target, Mock(return_value=None))
    monkeypatch.setattr("app.core.migration.migrate_database", lambda: True)
    for name in (
        "init_database_connection",
        "update_cron_task_status",
        "startup_event",
        "run_dashboard_stats_loop",
        "check_version_update_task",
        "add_version_update_notification_task",
    ):
        monkeypatch.setattr(lifecycle, name, AsyncMock())
    finalize = AsyncMock(return_value={"scan_count": 2, "purge_count": 1})
    monkeypatch.setattr(lifecycle, "finalize_android_orphan_jobs", finalize)
    forbidden = []
    for target in (
        "app.startup.lifecycle.reconcile_orphan_file_state",
        "app.startup.lifecycle.recover_interrupted_orphan_scans",
        "app.services.orphan_purge_job_service.get_orphan_purge_dispatcher",
        "app.services.orphan_scan_job_service.get_orphan_scan_dispatcher",
    ):
        guard = Mock(side_effect=AssertionError("Android must not scan or create dispatchers"))
        monkeypatch.setattr(target, guard)
        forbidden.append(guard)
    monkeypatch.setattr(lifecycle.cron_executor, "set_app", Mock())
    monkeypatch.setattr(lifecycle.cron_executor, "start", AsyncMock())
    monkeypatch.setattr(lifecycle.cron_executor, "stop", AsyncMock())
    monkeypatch.setattr("app.services.sync_observability.start_lag_sampler", Mock())
    monkeypatch.setattr(lifecycle.settings, "SYNC_PROCESS_MEMORY_SAMPLE_SECONDS", 0)
    monkeypatch.setattr(lifecycle.settings, "INFO_SYNC_STARTUP_BACKFILL_ENABLED", False)
    monkeypatch.setattr(lifecycle.settings, "SYNC_WAL_SNAPSHOT_INTERVAL_SECONDS", 60)
    app = FastAPI()
    async with lifespan(app):
        finalize.assert_awaited_once()
        assert not hasattr(app.state, "orphan_scan_recovery_task")
        assert not hasattr(app.state, "orphan_purge_recovery_task")
        assert not hasattr(app.state, "wal_snapshot_task")
    for guard in forbidden:
        guard.assert_not_called()


@pytest.mark.asyncio
async def test_android_finalization_only_fails_unfinished_jobs(tmp_path):
    from datetime import datetime
    import json
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.orphan_file import OrphanScanResult
    from app.models.orphan_purge_job import OrphanPurgeJob
    from app.startup.lifecycle import finalize_android_orphan_jobs

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sentinel = tmp_path / "untouched.data"
    sentinel.write_bytes(b"must remain intact")
    try:
        async with engine.begin() as conn:
            for table in (OrphanScanResult.__table__, OrphanPurgeJob.__table__):
                await conn.run_sync(table.create)
        async with factory() as db:
            for state in ("queued", "running", "completed", "failed"):
                db.add(OrphanScanResult(scan_id=state, status=state, scan_type="manual", scan_time=datetime.utcnow()))
            for state in ("pending", "running", "completed", "partial", "failed"):
                db.add(
                    OrphanPurgeJob(
                        task_id=state, status=state, operator="test", canonical_paths_json=json.dumps([str(sentinel)])
                    )
                )
            await db.commit()
        assert await finalize_android_orphan_jobs(factory) == {"scan_count": 2, "purge_count": 2}
        async with factory() as db:
            scans = (await db.execute(select(OrphanScanResult))).scalars().all()
            jobs = (await db.execute(select(OrphanPurgeJob))).scalars().all()
            assert {row.scan_id: row.status for row in scans} == {
                "queued": "failed",
                "running": "failed",
                "completed": "completed",
                "failed": "failed",
            }
            assert {row.task_id: row.status for row in jobs} == {
                "pending": "failed",
                "running": "failed",
                "completed": "completed",
                "partial": "partial",
                "failed": "failed",
            }
            assert all(row.error_message for row in scans if row.scan_id in ("queued", "running"))
        assert await finalize_android_orphan_jobs(factory) == {"scan_count": 0, "purge_count": 0}
        assert sentinel.read_bytes() == b"must remain intact"
    finally:
        await engine.dispose()
