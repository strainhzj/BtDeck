"""维护启动分支真实 lifespan 测试（database-migration-ui W2-2，PLANS §4.3/§11 T06）。

真实 lifespan（非替身）带未完成受管 attempt 启动：
- 进入维护分支（不迁移/不 seed/无后台任务/无引擎初始化）；
- 业务 API 503（屏障中间件）；控制面状态可见；
- **源零写**：全程不创建/修改 app.db（缺 seed/明文密码钩子/TaskLogger 均不触达）；
- 关闭路径干净（默认控制器卸载，无普通写入）；
- 维护重入：重复进入（第二次 lifespan）fail-safe 不重复进入。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from app.api.maintenance_barrier import MaintenanceBarrierMiddleware
from app.core.config import settings
from app.services.db_migration.maintenance import get_default_controller


def _make_mini_app() -> FastAPI:
    from app.startup.lifecycle import lifespan

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(MaintenanceBarrierMiddleware)

    @app.get("/api/v1/business")
    async def business():
        return {"ok": True}

    return app


@pytest.fixture
def maintenance_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.db"))
    monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path), raising=False)
    d = tmp_path / "db-migration"
    d.mkdir(parents=True, exist_ok=True)
    (d / "control.json").write_text(
        '{"pending_attempt": "pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"}',
        encoding="utf-8",
    )
    return tmp_path


class TestRealLifespanMaintenanceBoot:
    def test_maintenance_boot_zero_source_write(self, maintenance_env, tmp_path):
        app = _make_mini_app()
        with TestClient(app) as client:
            assert app.state.maintenance_mode is True
            controller = get_default_controller()
            assert controller is not None and controller.status().boot_recovery
            # 业务 API 默认拒（含 GET）
            resp = client.get("/api/v1/business")
            assert resp.status_code == 503
            assert resp.json()["data"]["reasonCode"] == "MAINTENANCE_MODE"
        # 源零写：不创建 app.db（无迁移/seed/引擎/后台任务触达）
        assert not (tmp_path / "app.db").exists()
        # 关闭路径：默认控制器卸载
        assert get_default_controller() is None

    def test_readiness_reflects_maintenance(self, maintenance_env):
        from app.api.endpoints.health import router as health_router

        app = _make_mini_app()
        app.include_router(health_router)
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            ready = client.get("/health/ready")
            assert ready.status_code == 503
            assert ready.json()["data"]["reasonCode"] == "MAINTENANCE_MODE"

    def test_reentry_is_fail_safe(self, maintenance_env):
        app = _make_mini_app()
        with TestClient(app):
            pass
        # 第二次启动：gate 检测到控制器已初始化会跳过分流——生产不会发生
        # （进程重启即新控制器），此处验证不崩溃
        app2 = _make_mini_app()
        with TestClient(app2):
            assert app2.state.maintenance_mode is True
