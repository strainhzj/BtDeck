# -*- coding: utf-8 -*-
"""孤儿扫描 12 万级稳定明细复用与状态接口响应性回归。

本测试使用真实临时文件型 SQLite，并启用与生产一致的 WAL、NullPool、
``synchronous=NORMAL`` 和 15 秒 ``busy_timeout``。它覆盖扫描完成后的数据库
阶段：120100 个已知孤儿按 200 条短事务更新生命周期时，稳定明细不得重复插入，
同时轻量扫描状态接口必须持续可响应。

这不是 Mock 或内存库基准。测试有意保留 120100 这个线上问题规模，防止未来把
生命周期查询/更新重新退化为一次性大事务，或让状态轮询被后台写入拖到请求超时。
"""

import asyncio
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, func, insert, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.endpoints import orphan_files
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_async_db
from app.models.orphan_file import (
    OrphanCurrentCandidate,
    OrphanFile,
    OrphanScanResult,
)
from app.services.orphan_lifecycle_service import OrphanLifecycleService
from app.tasks.resource_guard import admission_controller

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_ROW_COUNT = 120_100
_SEED_BATCH_SIZE = 2_000
_LIFECYCLE_BATCH_SIZE = 200
_STATUS_P95_MAX_MS = 1_000.0
_STATUS_MAX_MS = 3_000.0
_LIFECYCLE_MAX_SECONDS = 180.0


def _apply_sqlite_pragmas(dbapi_conn, conn_record):  # noqa: ANN001
    """为每个测试连接应用生产 SQLite 并发参数。"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.close()


def _percentile(samples: Sequence[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]


def _path(index: int) -> str:
    return f"C:/data/orphan-regression/{index:06d}.bin"


async def _create_engine(db_path: Path) -> AsyncEngine:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=NullPool,
    )
    event.listens_for(engine.sync_engine, "connect")(_apply_sqlite_pragmas)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[
                    OrphanScanResult.__table__,
                    OrphanFile.__table__,
                    OrphanCurrentCandidate.__table__,
                ],
            )
        )
    return engine


async def _seed_existing_orphans(engine: AsyncEngine) -> None:
    old_time = datetime.utcnow() - timedelta(hours=1)
    new_time = old_time + timedelta(minutes=30)
    scan_defaults = {
        "total_paths_scanned": 1,
        "total_files_scanned": _ROW_COUNT,
        "total_orphans": _ROW_COUNT,
        "total_orphan_size": _ROW_COUNT * 1024,
        "error_message": None,
        "operator": "regression",
        "details_mode": "current",
        "new_orphans": 0,
        "known_orphans": _ROW_COUNT,
        "resolved_orphans": 0,
        "cleanup_review_required": True,
        "cleanup_reviewed_at": None,
        "cleanup_reviewed_by": None,
        "cleanup_review_note": None,
        "created_at": old_time,
        "updated_at": old_time,
    }
    async with engine.begin() as connection:
        await connection.execute(
            insert(OrphanScanResult),
            [
                {
                    **scan_defaults,
                    "scan_id": "scan-existing-120100",
                    "scan_time": old_time,
                    "scan_type": "manual",
                    "status": "completed",
                },
                {
                    **scan_defaults,
                    "scan_id": "scan-running-120100",
                    "scan_time": new_time,
                    "scan_type": "manual",
                    "status": "running",
                    "known_orphans": 0,
                    "created_at": new_time,
                    "updated_at": new_time,
                },
            ],
        )

        for start in range(0, _ROW_COUNT, _SEED_BATCH_SIZE):
            stop = min(start + _SEED_BATCH_SIZE, _ROW_COUNT)
            details = []
            candidates = []
            for index in range(start, stop):
                detail_id = index + 1
                path = _path(index)
                details.append(
                    {
                        "id": detail_id,
                        "scan_id": "scan-existing-120100",
                        "file_path": path,
                        "file_size": 1024,
                        "mtime": None,
                        "downloader_id": "downloader-regression",
                        "confidence": "high",
                        "canonical_path": path,
                        "is_deleted": False,
                        "deleted_at": None,
                        "deleted_by": None,
                        "created_at": old_time,
                    }
                )
                candidates.append(
                    {
                        "canonical_path": path,
                        "current_detail_id": detail_id,
                        "downloader_id": "downloader-regression",
                        "first_seen_at": old_time,
                        "last_seen_at": old_time,
                        "last_seen_scan_id": "scan-existing-120100",
                        "consecutive_scan_count": 1,
                        "status": "candidate",
                        "file_size": 1024,
                        "confidence": "high",
                        "mtime_ns": index + 1,
                        "device_id": "1",
                        "inode": str(index + 10_000),
                        "quarantine_path": None,
                        "quarantine_root": None,
                        "quarantined_at": None,
                        "purge_after": None,
                        "purge_delay_count": 0,
                        "operation_state": "stable",
                        "operation_target_path": None,
                        "operation_error": None,
                        "is_ignored": False,
                        "ignored_at": None,
                        "ignored_by": None,
                        "created_at": old_time,
                        "updated_at": old_time,
                    }
                )
            await connection.execute(insert(OrphanFile), details)
            await connection.execute(insert(OrphanCurrentCandidate), candidates)


def _orphan_payload() -> list[dict]:
    return [
        {
            "canonical_path": _path(index),
            "file_path": _path(index),
            "file_size": 1024,
            "mtime": None,
            "downloader_id": "downloader-regression",
            "confidence": "high",
            "mtime_ns": index + 1,
            "device_id": "1",
            "inode": str(index + 10_000),
        }
        for index in range(_ROW_COUNT)
    ]


async def test_120100_known_orphans_reuse_details_while_status_api_stays_responsive(
    tmp_path,
):
    """12 万稳定孤儿分批推进期间，状态 API 不超时且明细数不增长。"""
    engine = await _create_engine(tmp_path / "orphan_scan_120100.db")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    admission_controller.reset_state()
    try:
        await _seed_existing_orphans(engine)

        app = FastAPI()
        app.include_router(orphan_files.router, prefix="/orphan-files")

        async def override_db():
            async with session_factory() as db:
                yield db

        app.dependency_overrides[get_async_db] = override_db
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="regression")

        scan_finished = asyncio.Event()
        status_latencies_ms: list[float] = []
        status_failures: list[str] = []

        async def advance_lifecycle():
            started = time.perf_counter()
            try:
                async with session_factory() as writer:
                    result = await OrphanLifecycleService(writer).reconcile_candidates(
                        scan_id="scan-running-120100",
                        scan_time=datetime.utcnow(),
                        orphans=_orphan_payload(),
                        scan_roots=["C:/data/orphan-regression"],
                        batch_size=_LIFECYCLE_BATCH_SIZE,
                        persist_current_details=True,
                    )
                return result, time.perf_counter() - started
            finally:
                scan_finished.set()

        async def probe_status_api():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://orphan-regression",
            ) as client:
                while not scan_finished.is_set():
                    started = time.perf_counter()
                    response = await client.get("/orphan-files/scans/scan-running-120100")
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    status_latencies_ms.append(elapsed_ms)
                    payload = response.json()
                    if (
                        response.status_code != 200
                        or payload.get("code") != "200"
                        or payload.get("data", {}).get("task_id") != "scan-running-120100"
                    ):
                        status_failures.append(str(payload))
                    await asyncio.sleep(0.025)

        lifecycle_task = asyncio.create_task(advance_lifecycle())
        probe_task = asyncio.create_task(probe_status_api())
        (result, lifecycle_seconds), _ = await asyncio.gather(
            lifecycle_task,
            probe_task,
        )

        assert result == {
            "inserted": 0,
            "updated": _ROW_COUNT,
            "resolved": 0,
            "detail_inserted": 0,
            "detail_reused": _ROW_COUNT,
        }
        assert lifecycle_seconds < _LIFECYCLE_MAX_SECONDS
        assert len(status_latencies_ms) >= 10
        assert not status_failures
        assert _percentile(status_latencies_ms, 0.95) < _STATUS_P95_MAX_MS
        assert max(status_latencies_ms) < _STATUS_MAX_MS

        async with session_factory() as verifier:
            detail_count = (await verifier.execute(select(func.count()).select_from(OrphanFile))).scalar_one()
            new_detail_count = (
                await verifier.execute(
                    select(func.count()).select_from(OrphanFile).where(OrphanFile.scan_id == "scan-running-120100")
                )
            ).scalar_one()
            candidate_count = (
                await verifier.execute(select(func.count()).select_from(OrphanCurrentCandidate))
            ).scalar_one()
            current_scan_count = (
                await verifier.execute(
                    select(func.count())
                    .select_from(OrphanCurrentCandidate)
                    .where(OrphanCurrentCandidate.last_seen_scan_id == "scan-running-120100")
                )
            ).scalar_one()

        assert detail_count == _ROW_COUNT
        assert new_detail_count == 0
        assert candidate_count == _ROW_COUNT
        assert current_scan_count == _ROW_COUNT
    finally:
        await engine.dispose()
        admission_controller.reset_state()
