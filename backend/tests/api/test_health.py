"""W4-2 liveness/readiness/同步健康接口回归测试。

测试只替换健康接口的数据库探针或只读 session，不触碰生产 app.db，也不调用下载器。
"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.endpoints import health
from app.auth.dependencies import require_authenticated_user
from app import version
from app.factory import create_app
from app.models import OUTCOME_PARTIAL, OUTCOME_SUCCESS, SyncCheckpoint
from app.services import sync_coordinator
from app.tasks.cron_models import CronTask


def _client(*, authenticated: bool = False):
    app = create_app(configure_routes=False)
    app.include_router(health.router)
    app.include_router(health.sync_router, prefix="/api/v1/health")
    if authenticated:
        app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    return app, TestClient(app, raise_server_exceptions=False)


class _Sampler:
    def __init__(self, *, count: int = 1, p99: float = 10.0, maximum: float = 10.0):
        self._count = count
        self._p99 = p99
        self._maximum = maximum

    def sample_count(self) -> int:
        return self._count

    def p99(self) -> float:
        return self._p99

    def max_ms(self) -> float:
        return self._maximum


def _patch_ready_defaults(monkeypatch, app, *, sampler=None):
    monkeypatch.setattr(health, "_probe_database", AsyncMock())
    app.state.sync_lag_sampler = SimpleNamespace(sampler=sampler or _Sampler())


def test_liveness_does_not_touch_database(monkeypatch):
    app, client = _client()
    probe = AsyncMock(side_effect=AssertionError("liveness must not probe database"))
    monkeypatch.setattr(health, "_probe_database", probe)

    response = client.get("/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["msg"] == "服务存活"
    # version 供伴侣模式（dual-mode-client Phase 2）版本提示，进程内常量无 I/O；
    # build 为 W1 发布身份块（G1，见 tests/release/test_health_build_identity.py
    # 的专项回归），此处仅锁定原有两键不被破坏
    assert body["data"]["status"] == "alive"
    assert body["data"]["version"] == health.CURRENT_VERSION
    assert "build" in body["data"]
    probe.assert_not_awaited()


def test_readiness_normal_and_offline_downloader_does_not_fail(monkeypatch):
    app, client = _client()
    _patch_ready_defaults(monkeypatch, app)

    class ForbiddenStore:
        async def get_snapshot(self):
            raise AssertionError("readiness must not call downloader cache/remote health")

    app.state.store = ForbiddenStore()
    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 200
    assert body["code"] == "200"
    assert body["data"]["status"] == "ready"
    assert body["data"]["version"] == version.CURRENT_VERSION
    assert body["data"]["checks"]["database"]["status"] == "ok"


def test_readiness_database_unavailable_returns_503_without_exception_details(monkeypatch):
    app, client = _client()
    app.state.sync_lag_sampler = SimpleNamespace(sampler=_Sampler())
    monkeypatch.setattr(health, "_probe_database", AsyncMock(side_effect=OSError("database is locked: secret path")))

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 503
    assert body["status"] == "error"
    assert body["code"] == "503"
    assert "db_unavailable" in body["data"]["reasonCodes"]
    assert "database is locked" not in response.text
    assert "secret path" not in response.text


def test_readiness_query_timeout_returns_503(monkeypatch):
    app, client = _client()
    app.state.sync_lag_sampler = SimpleNamespace(sampler=_Sampler())
    monkeypatch.setattr(health.settings, "HEALTH_READINESS_DB_TIMEOUT_SECONDS", 0.001)

    async def slow_probe():
        await asyncio.sleep(0.05)

    monkeypatch.setattr(health, "_probe_database", slow_probe)
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["data"]["reasonCodes"] == ["db_query_timeout"]


def test_readiness_lag_over_threshold_returns_503(monkeypatch):
    app, client = _client()
    monkeypatch.setattr(health, "_probe_database", AsyncMock())
    app.state.sync_lag_sampler = SimpleNamespace(sampler=_Sampler(p99=250.0, maximum=300.0))
    monkeypatch.setattr(health.settings, "HEALTH_READINESS_LAG_P99_THRESHOLD_MS", 100.0)

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 503
    assert "event_loop_lag" in body["data"]["reasonCodes"]
    assert body["data"]["checks"]["eventLoopLag"]["p99Ms"] == 250.0


def test_readiness_noncompliant_sqlite_worker_returns_503(monkeypatch):
    app, client = _client()
    _patch_ready_defaults(monkeypatch, app)
    monkeypatch.setattr(health, "resolve_runtime_info", lambda: ("sqlite", 2, True))

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 503
    assert body["data"]["reasonCodes"] == ["worker_noncompliant"]
    assert body["data"]["checks"]["worker"]["workerCount"] == 2


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _FakeHealthSession:
    def __init__(self, checkpoints, tasks):
        self.checkpoints = checkpoints
        self.tasks = tasks

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is SyncCheckpoint:
            return _FakeResult(self.checkpoints)
        return _FakeResult(self.tasks)


class _FakeStore:
    async def get_snapshot(self):
        return [SimpleNamespace(fail_time=0), SimpleNamespace(fail_time=2)]


def test_sync_health_requires_authentication():
    _app, client = _client()

    response = client.get("/api/v1/health/sync")

    assert response.status_code == 401
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "401"
    assert body["data"] is None


def test_sync_health_returns_outcome_freshness_active_phase_checkpoint_age_and_offline_alert(monkeypatch):
    app, client = _client(authenticated=True)
    now = datetime.now()
    task = CronTask(
        task_name="种子信息同步任务",
        task_code="torrent_info_sync_ac608e4d",
        task_status=1,
        task_type=4,
        executor="app.tasks.scheduler.torrent_sync.TorrentInfoSyncTask",
        enabled=True,
        cron_plan="*/5 * * * *",
        last_success_at=now - timedelta(seconds=120),
        last_attempt_at=now - timedelta(seconds=30),
        last_outcome=OUTCOME_SUCCESS,
        last_run_id="cron-old",
        dr=0,
    )
    checkpoint = SyncCheckpoint(
        downloader_id="d1",
        sync_type="info",
        cycle_started_at=now - timedelta(seconds=300),
        last_success_at=now - timedelta(seconds=90),
        last_attempt_at=now - timedelta(seconds=2),
        outcome=OUTCOME_PARTIAL,
        updated_at=now - timedelta(seconds=2),
        created_at=now - timedelta(seconds=300),
    )
    fake_session = _FakeHealthSession([checkpoint], [task])
    monkeypatch.setattr(health, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        health,
        "get_active_sync_runs",
        lambda: [
            {
                "run_id": "sync-active-123",
                "sync_type": "info",
                "phase": "sync",
                "started_at": now - timedelta(seconds=10),
                "downloader_count": 2,
            }
        ],
    )
    app.state.store = _FakeStore()

    response = client.get("/api/v1/health/sync")
    body = response.json()

    assert response.status_code == 200
    assert body["code"] == "200"
    info = next(item for item in body["data"]["tasks"] if item["syncType"] == "info")
    assert info["latestOutcome"] == OUTCOME_PARTIAL
    assert info["activeRun"]["runId"] == "sync-active-123"
    assert info["phase"] == "sync"
    assert 0 <= info["checkpointAgeSeconds"] <= 2
    assert info["freshnessSeconds"] in (89, 90, 91)
    assert info["stale"] is False
    assert body["data"]["downloaders"] == {
        "status": "degraded",
        "total": 2,
        "offlineCount": 1,
        "warnings": ["downloader_offline"],
    }


@pytest.mark.asyncio
async def test_sync_health_query_timeout_returns_503(monkeypatch):
    """同步业务健康查询在数据库锁等待时必须有界返回。"""
    app, _client_instance = _client(authenticated=True)
    monkeypatch.setattr(health.settings, "HEALTH_SYNC_DB_TIMEOUT_SECONDS", 0.001)

    async def slow_health(_app):
        await asyncio.sleep(0.05)
        return {}

    monkeypatch.setattr(health, "_build_sync_health", slow_health)
    response = await health.sync_health(
        SimpleNamespace(app=app),
        SimpleNamespace(username="tester"),
    )

    assert response.status_code == 503
    body = response.body.decode("utf-8")
    assert "sync_health_query_timeout" in body


@pytest.mark.asyncio
async def test_sync_coordinator_active_snapshot_is_removed_after_run(monkeypatch):
    observed = {}
    run_id = "sync-health-lifecycle"

    async def fake_core(req, app, active_run_id, start_ts):
        observed["during"] = sync_coordinator.get_active_sync_runs()
        sync_coordinator._update_active_run(active_run_id, phase="sync", downloader_count=2)
        observed["updated"] = sync_coordinator.get_active_sync_runs()
        return sync_coordinator.SyncResult(run_id=active_run_id, phase="sync", outcome=OUTCOME_SUCCESS)

    monkeypatch.setattr(sync_coordinator, "_run_sync_core", fake_core)
    result = await sync_coordinator.run_sync(
        sync_coordinator.SyncRequest(sync_type="info", run_id=run_id, downloader_ids=["d1", "d2"]),
        app=SimpleNamespace(),
    )

    assert result.run_id == run_id
    assert observed["during"][0]["phase"] == "admission"
    assert observed["updated"][0]["phase"] == "sync"
    assert observed["updated"][0]["downloader_count"] == 2
    assert not any(item["run_id"] == run_id for item in sync_coordinator.get_active_sync_runs())
