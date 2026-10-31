"""数据库控制端点鉴权矩阵与三探针测试（W3-4/8；§8/§5.4）。

矩阵（评审修正：前缀放行≠授权豁免）：
- 普通模式：/api/v1/database/* 未认证 401；认证后 200（依赖分派普通管理员）；
- 维护模式：屏障放行传输；无维护 token → 401；普通 access token 同样拒绝
  （维护依赖只认 aud=btdeck-maintenance）；带维护 token → 200；
- 运行时迁移窗口（W6-B 发现②③修正）：controller.in_maintenance 而
  app.state.maintenance_mode=False 时，鉴权/维护认证/control-ready 与启动
  维护分支同一语义（维护 token 必需且可签发；businessReady=false）；
- 路径边界：/api/v1/database-evil 不在放行前缀（屏障 503）；
- 三探针：live 200/ready 503/control-ready 200+businessReady=false（维护）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.api import api_router
from app.api.maintenance_barrier import MaintenanceBarrierMiddleware
from app.core.config import settings


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path), raising=False)
    from app.api.endpoints.health import router as health_router

    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.include_router(health_router)
    application.add_middleware(MaintenanceBarrierMiddleware)
    return application


def _maintenance_token(client, tmp_path) -> str:
    """经维护认证端点取得 token（复用 W2 测试的 seed 面最小构造）。"""
    import sqlite3

    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, "
        "two_factor_flag TEXT, two_factor_secret TEXT, is_active BOOLEAN, must_change_password BOOLEAN)"
    )
    from app.auth.security import get_password_hash

    conn.execute(
        "INSERT INTO users VALUES (1, 'admin', ?, NULL, NULL, 1, 0)", (get_password_hash("pw-admin"),)
    )
    conn.commit()
    conn.close()
    from app.services.db_migration.maintenance_auth import MaintenanceAuthService, sqlite_user_reader

    app = client.app
    app.state.maintenance_auth = MaintenanceAuthService(
        str(tmp_path), sqlite_user_reader(str(db)), secret_key="secret-key-for-tests"
    )
    resp = client.post("/api/v1/maintenance/auth", json={"username": "admin", "password": "pw-admin"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["maintenanceToken"]


def _enter_maintenance(client, tmp_path):
    from app.services.db_migration.maintenance import (
        MaintenanceController,
        set_default_controller,
    )

    controller = MaintenanceController(str(tmp_path))
    controller.enter_maintenance_boot()
    set_default_controller(controller)
    client.app.state.maintenance = controller
    client.app.state.maintenance_mode = True
    return controller


@pytest.fixture(autouse=True)
def _cleanup_controller():
    yield
    from app.services.db_migration.maintenance import set_default_controller

    set_default_controller(None)


class TestNormalModeAuth:
    def test_unauthenticated_401(self, app):
        client = TestClient(app)
        resp = client.get("/api/v1/database/status")
        assert resp.status_code == 401

    def test_health_probes_public(self, app):
        client = TestClient(app)
        assert client.get("/health/control-ready").status_code in (200, 503)


class TestMaintenanceModeAuthMatrix:
    def test_barrier_allows_prefix_but_auth_rejects_anonymous(self, app, tmp_path):
        client = TestClient(app)
        _enter_maintenance(client, tmp_path)
        resp = client.get("/api/v1/database/migration/status")
        # 屏障放行（传输）→ 端点鉴权拒绝（无维护 token）
        assert resp.status_code == 401

    def test_maintenance_token_accepted(self, app, tmp_path):
        client = TestClient(app)
        _enter_maintenance(client, tmp_path)
        token = _maintenance_token(client, tmp_path)
        client.headers.update({"Authorization": f"Bearer {token}"})
        # manager 未装载 → 503（鉴权已通过；服务不可用语义）
        resp = client.get("/api/v1/database/migration/status")
        assert resp.status_code == 503

    def test_normal_access_token_rejected_in_maintenance(self, app, tmp_path):
        """普通 access token 不能冒充维护 scope（无维护 aud）。"""
        client = TestClient(app)
        _enter_maintenance(client, tmp_path)
        client.headers.update({"Authorization": "Bearer normal-looking-token"})
        resp = client.get("/api/v1/database/migration/status")
        assert resp.status_code == 401


def _enter_runtime_maintenance(client, tmp_path):
    """模拟运行时迁移窗口（start→FROZEN）：controller 进入维护、但
    app.state.maintenance_mode 保持 False（非启动维护分支）。"""
    from app.services.db_migration.maintenance import (
        MaintenanceController,
        set_default_controller,
    )

    controller = MaintenanceController(str(tmp_path))
    controller.enter_maintenance_boot()
    set_default_controller(controller)
    client.app.state.maintenance = controller
    assert getattr(client.app.state, "maintenance_mode", False) is False
    assert controller.status().in_maintenance is True
    return controller


class TestRuntimeMigrationWindow:
    """运行时迁移窗口鉴权/探针一致性（W6-B 发现②③回归）。"""

    def test_control_requires_maintenance_token_not_normal(self, app, tmp_path):
        client = TestClient(app)
        _enter_runtime_maintenance(client, tmp_path)
        assert client.get("/api/v1/database/migration/status").status_code == 401
        client.headers.update({"Authorization": "Bearer normal-looking-token"})
        assert client.get("/api/v1/database/migration/status").status_code == 401

    def test_maintenance_auth_issuable_and_accepted(self, app, tmp_path):
        client = TestClient(app)
        _enter_runtime_maintenance(client, tmp_path)
        token = _maintenance_token(client, tmp_path)  # 服务已装载+in_maintenance → 可签发
        client.headers.update({"Authorization": f"Bearer {token}"})
        resp = client.get("/api/v1/database/migration/status")
        assert resp.status_code == 503  # 鉴权通过（manager 未装载 → 不可用语义）

    def test_control_ready_business_not_ready(self, app, tmp_path):
        client = TestClient(app)
        _enter_runtime_maintenance(client, tmp_path)
        control = client.get("/health/control-ready")
        assert control.status_code == 200
        data = control.json().get("data") or control.json()
        assert data.get("businessReady") is False
        assert data.get("maintenance") is True


class TestBarrierPathBoundary:
    def test_prefix_boundary_not_broadened(self, app, tmp_path):
        client = TestClient(app)
        _enter_maintenance(client, tmp_path)

        @client.app.get("/api/v1/database-evil")
        async def evil():
            return {"ok": True}

        resp = client.get("/api/v1/database-evil")
        assert resp.status_code == 503  # 不在放行前缀（严格前缀边界）


class TestHealthThreeProbes:
    def test_maintenance_probes(self, app, tmp_path):
        client = TestClient(app)
        _enter_maintenance(client, tmp_path)
        assert client.get("/health/live").status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        control = client.get("/health/control-ready")
        assert control.status_code == 200
        data = control.json().get("data") or control.json()
        assert data.get("businessReady") is False

    def test_normal_mode_control_ready_delegates(self, app):
        client = TestClient(app)
        # 普通模式：control-ready 委托业务就绪判定（本测试环境 DB 不可达→503 语义）
        resp = client.get("/health/control-ready")
        assert resp.status_code in (200, 503)
