"""维护屏障/启动分流/钩子测试（database-migration-ui W2-2/W2-3，PLANS §5/§11 T03/T05/T06）。

- 屏障中间件：普通模式业务面持 lease（响应完成才释放）；维护模式默认拒
  （含 GET）/MCP 路径 503+MAINTENANCE_MODE；health/静态/维护端点放行；
- cron 包装：维护模式跳过且零调用；正常模式透传；
- TaskLogger 哨兵：维护模式不写源库（落本地审计哨兵）；
- 维护启动分流（组件级）：受管态/崩溃 intent → 维护分支；正常态直通。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.maintenance_barrier import MaintenanceBarrierMiddleware
from app.services.db_migration.maintenance import (
    MaintenanceController,
    set_default_controller,
)


@pytest.fixture
def controller(tmp_path):
    c = MaintenanceController(tmp_path)
    set_default_controller(c)
    yield c
    set_default_controller(None)


def _make_app(controller_probe=None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(MaintenanceBarrierMiddleware)

    @app.get("/api/v1/business")
    async def business():
        if controller_probe is not None:
            controller_probe()
        return {"ok": True}

    @app.get("/health/live")
    async def live():
        return {"alive": True}

    @app.get("/api/v1/maintenance/status")
    async def maintenance_status():
        return {"state": "HELD"}

    @app.get("/")
    async def index():
        return {"static": True}

    return app


class TestBarrierMiddleware:
    def test_normal_mode_holds_lease_during_request(self, controller):
        seen = {}

        def probe():
            seen["count"] = controller.active_count()
            seen["kinds"] = controller.active_kinds()

        app = _make_app(probe)
        with TestClient(app) as client:
            resp = client.get("/api/v1/business")
        assert resp.status_code == 200
        assert seen["count"] == 1
        assert seen["kinds"] == ["http:/api/v1/business"]
        assert controller.active_count() == 0  # 响应完成后释放

    def test_maintenance_rejects_business_including_get(self, controller):
        controller.enter_maintenance_boot()
        app = _make_app()
        with TestClient(app) as client:
            resp = client.get("/api/v1/business")
        assert resp.status_code == 503
        body = resp.json()
        assert body["data"]["reasonCode"] == "MAINTENANCE_MODE"
        assert body["code"] == "503"

    def test_maintenance_allows_health_static_maintenance_api(self, controller):
        controller.enter_maintenance_boot()
        app = _make_app()
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/").status_code == 200
            # SPA 静态路由：屏障放行（无路由命中 404 是路由层事实，非屏障 503）
            assert client.get("/some/spa/route").status_code == 404
            assert client.get("/api/v1/maintenance/status").status_code == 200
            assert client.get("/mcp/").status_code == 503

    def test_gate_close_between_queue_and_entry(self, controller):
        """闸门在请求进入前关上 → 503（非 500）。"""
        app = _make_app()
        controller.enter_maintenance_boot()
        with TestClient(app) as client:
            assert client.get("/api/v1/business").status_code == 503


class TestCronWrapper:
    def test_cron_skipped_in_maintenance_zero_calls(self, controller, monkeypatch):
        from app.tasks.cron_executor import CronTaskExecutor

        executor = CronTaskExecutor()
        called = []

        async def _body(task_id):
            called.append(task_id)

        monkeypatch.setattr(executor, "_execute_task_body", _body)
        controller.enter_maintenance_boot()
        asyncio.get_event_loop_policy()
        result = asyncio.run(executor._execute_task(42))
        assert result is None
        assert called == []

    def test_cron_passes_in_normal(self, controller, monkeypatch):
        from app.tasks.cron_executor import CronTaskExecutor

        executor = CronTaskExecutor()
        called = []

        async def _body(task_id):
            called.append(task_id)
            assert controller.active_count() == 1  # 任务体在 lease 内执行

        monkeypatch.setattr(executor, "_execute_task_body", _body)
        asyncio.run(executor._execute_task(42))
        assert called == [42]


class TestTaskLoggerSentinel:
    def test_tasklogger_suppressed_in_maintenance(self, controller, tmp_path, monkeypatch):
        # CONFIG_PATH 为 property（分支语义），经 CONFIG_DIR 环境变量注入
        monkeypatch.setattr("app.core.config.Settings.CONFIG_DIR", tmp_path, raising=False)
        from app.core.config import settings

        monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
        from app.tasks.logger import TaskLogger

        controller.enter_maintenance_boot()

        async def _run():
            async with TaskLogger("demo-task", 3):
                pass

        asyncio.run(_run())
        audit_path = tmp_path / "db-migration" / "maintenance-audit.jsonl"
        assert audit_path.exists(), "维护期 TaskLogger 应落哨兵行"
        content = audit_path.read_text(encoding="utf-8")
        assert "task-log-suppressed" in content


class TestStartupGate:
    def _gate(self, tmp_path, app=None, **kw):
        from app.startup.lifecycle import _startup_maintenance_gate

        return _startup_maintenance_gate(
            app or SimpleNamespace(state=SimpleNamespace()),
            yaml_path=str(tmp_path / "no-config.yaml"),
            config_dir=str(tmp_path),
            db_path=str(tmp_path / "app.db"),
            secret_key="unit",
            **kw,
        )

    def test_normal_returns_false(self, tmp_path):
        set_default_controller(None)
        assert self._gate(tmp_path) is False

    def test_pending_attempt_enters_maintenance(self, tmp_path):
        from app.core.database_protocol import DB_MIGRATION_DIR

        d = tmp_path / DB_MIGRATION_DIR
        d.mkdir(parents=True)
        (d / "control.json").write_text(
            '{"pending_attempt": "pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"}',
            encoding="utf-8",
        )
        fake_app = SimpleNamespace(state=SimpleNamespace())
        assert self._gate(tmp_path, app=fake_app) is True
        assert fake_app.state.maintenance_mode is True
        status = fake_app.state.maintenance.status()
        assert status.in_maintenance and status.boot_recovery
        assert fake_app.state.maintenance_auth is not None
        # 本地审计已落 maintenance-boot 事件
        audit = fake_app.state.maintenance_audit
        assert any(r["action"] == "maintenance-boot" for r in audit.replay_events())
        set_default_controller(None)

    def test_crashed_prepare_intent_enters_maintenance(self, tmp_path):
        from app.core.database_protocol import DB_MIGRATION_DIR

        d = tmp_path / DB_MIGRATION_DIR
        d.mkdir(parents=True)
        (d / "maintenance-intent.json").write_text(
            '{"version": 1, "state": "PREPARING", "attempt_id": "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"}',
            encoding="utf-8",
        )
        fake_app = SimpleNamespace(state=SimpleNamespace())
        assert self._gate(tmp_path, app=fake_app) is True
        assert fake_app.state.maintenance.attempt_id == "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
        set_default_controller(None)

    def test_corrupted_control_fail_closed(self, tmp_path):
        from app.core.database_protocol import DB_MIGRATION_DIR

        d = tmp_path / DB_MIGRATION_DIR
        d.mkdir(parents=True)
        (d / "control.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(Exception, match="fail-closed|拒绝"):
            self._gate(tmp_path)
