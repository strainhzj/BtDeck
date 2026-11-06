"""部署环境 PG 目标回填面 + A2 环境密码开关测试（compose 三容器栈配套）。

覆盖：
- GET /database/deployment-target：sqlite → available=false；postgresql →
  非敏感回填字段下发 + hasEnvPassword 布尔，密码本体永不出现在响应；
- use_env_password 开关（A2）：test-connection / migration/start /
  migration/credentials 三面服务端自取 DB_PASSWORD（请求不含密码本体）；
- 用法错误 fail-fast：环境密码缺失 / 显式密码缺失 → 400（不落连接异常汇总）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.api import api_router
from app.api.maintenance_barrier import MaintenanceBarrierMiddleware
from app.core.config import settings

ENV_PASSWORD = "env-secret-pw"
ENV_TARGET: Dict[str, Any] = {
    "host": "postgres",
    "port": 5432,
    "user": "btdeck",
    "database": "btdeck",
    "schema": "public",
}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path), raising=False)
    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.add_middleware(MaintenanceBarrierMiddleware)
    return application


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

    conn.execute("INSERT INTO users VALUES (1, 'admin', ?, NULL, NULL, 1, 0)", (get_password_hash("pw-admin"),))
    conn.commit()
    conn.close()
    from app.services.db_migration.maintenance_auth import MaintenanceAuthService, sqlite_user_reader

    application = client.app
    application.state.maintenance_auth = MaintenanceAuthService(
        str(tmp_path), sqlite_user_reader(str(db)), secret_key="secret-key-for-tests"
    )
    resp = client.post("/api/v1/maintenance/auth", json={"username": "admin", "password": "pw-admin"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["maintenanceToken"]


def _authorized_client(app, tmp_path) -> TestClient:
    client = TestClient(app)
    _enter_maintenance(client, tmp_path)
    token = _maintenance_token(client, tmp_path)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---------------------------------------------------------------------------
# 夹具：假引擎（捕获 create_engine 入参 URL）+ 假管理器（捕获密码实参）
# ---------------------------------------------------------------------------


class _Scalar:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar(self) -> Any:
        return self._value


class _FakeConn:
    def execute(self, stmt: Any) -> _Scalar:
        if "server_version" in str(stmt):
            return _Scalar("16.4")
        return _Scalar(0)

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class _FakeEngine:
    def __init__(self, url: Any) -> None:
        self._url = url

    def connect(self) -> _FakeConn:
        return _FakeConn()

    def dispose(self) -> None:
        return None


class _StubManager:
    def __init__(self) -> None:
        self.start_calls: List[Dict[str, Any]] = []
        self.cred_calls: List[Dict[str, Any]] = []

    def start_migration(
        self,
        direction: str,
        target: Dict[str, Any],
        *,
        password: str,
        initiated_by: str = "administrator",
        source_desc: Optional[Dict[str, Any]] = None,
    ):
        self.start_calls.append({"direction": direction, "target": dict(target), "password": password})

        class _Status:
            def as_dict(self) -> Dict[str, Any]:
                return {"phase": "preparing"}

        return _Status()

    def provide_credentials(self, attempt_id: str, *, password: str, target: Dict[str, Any]) -> None:
        self.cred_calls.append({"attempt_id": attempt_id, "password": password, "target": dict(target)})


# ---------------------------------------------------------------------------
# GET /deployment-target
# ---------------------------------------------------------------------------


class TestDeploymentTarget:
    def test_unauthenticated_401(self, app):
        client = TestClient(app)
        assert client.get("/api/v1/database/deployment-target").status_code == 401

    def test_sqlite_unavailable(self, app, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "DB_TYPE", "sqlite", raising=False)
        client = _authorized_client(app, tmp_path)
        resp = client.get("/api/v1/database/deployment-target")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == {"available": False, "target": None, "hasEnvPassword": False}

    def test_pg_prefill_without_password_body(self, app, tmp_path, monkeypatch):
        """回填面只下发非敏感字段 + hasEnvPassword；密码本体不出现在响应。"""
        monkeypatch.setattr(settings, "DB_TYPE", "postgresql", raising=False)
        monkeypatch.setattr(settings, "DB_HOST", "postgres", raising=False)
        monkeypatch.setattr(settings, "DB_PORT", 5432, raising=False)
        monkeypatch.setattr(settings, "DB_USER", "btdeck", raising=False)
        monkeypatch.setattr(settings, "DB_PASSWORD", ENV_PASSWORD, raising=False)
        monkeypatch.setattr(settings, "DB_NAME", "btdeck", raising=False)
        monkeypatch.setattr(settings, "DB_SSLMODE", "prefer", raising=False)
        client = _authorized_client(app, tmp_path)
        resp = client.get("/api/v1/database/deployment-target")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["available"] is True
        assert data["hasEnvPassword"] is True
        target = data["target"]
        assert target["host"] == "postgres"
        assert target["port"] == 5432
        assert target["user"] == "btdeck"
        assert target["database"] == "btdeck"
        assert target["sslmode"] == "prefer"
        # 密码本体绝不出现（§8：迁移面不暴露凭据）
        assert ENV_PASSWORD not in resp.text
        assert "password" not in target

    def test_pg_without_env_password(self, app, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "DB_TYPE", "postgresql", raising=False)
        monkeypatch.setattr(settings, "DB_PASSWORD", "", raising=False)
        client = _authorized_client(app, tmp_path)
        data = client.get("/api/v1/database/deployment-target").json()["data"]
        assert data["available"] is True
        assert data["hasEnvPassword"] is False


# ---------------------------------------------------------------------------
# use_env_password 开关（A2）
# ---------------------------------------------------------------------------


def _patch_pg_env(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DB_TYPE", "postgresql", raising=False)
    monkeypatch.setattr(settings, "DB_PASSWORD", ENV_PASSWORD, raising=False)


class TestUseEnvPassword:
    def test_test_connection_resolves_env_password(self, app, tmp_path, monkeypatch):
        """探测面：use_env_password=true 时 URL 使用服务端环境密码。"""
        _patch_pg_env(monkeypatch)
        captured: List[str] = []

        def _fake_create_engine(url: Any, **kwargs: Any) -> _FakeEngine:
            captured.append(str(url))
            return _FakeEngine(url)

        monkeypatch.setattr("sqlalchemy.create_engine", _fake_create_engine)
        client = _authorized_client(app, tmp_path)
        resp = client.post(
            "/api/v1/database/test-connection",
            json={"dialect": "postgresql", "postgresql": dict(ENV_TARGET), "use_env_password": True},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["reachable"] is True
        assert captured and ENV_PASSWORD in captured[0]
        assert ENV_PASSWORD not in resp.text

    def test_test_connection_manual_password(self, app, tmp_path, monkeypatch):
        _patch_pg_env(monkeypatch)
        captured: List[str] = []

        def _fake_create_engine(url: Any, **kwargs: Any) -> _FakeEngine:
            captured.append(str(url))
            return _FakeEngine(url)

        monkeypatch.setattr("sqlalchemy.create_engine", _fake_create_engine)
        client = _authorized_client(app, tmp_path)
        payload = dict(ENV_TARGET)
        payload["password"] = "manual-pw"
        resp = client.post(
            "/api/v1/database/test-connection",
            json={"dialect": "postgresql", "postgresql": payload},
        )
        assert resp.status_code == 200
        assert captured and "manual-pw" in captured[0]

    def test_test_connection_env_password_missing_400(self, app, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "DB_TYPE", "postgresql", raising=False)
        monkeypatch.setattr(settings, "DB_PASSWORD", "", raising=False)
        client = _authorized_client(app, tmp_path)
        resp = client.post(
            "/api/v1/database/test-connection",
            json={"dialect": "postgresql", "postgresql": dict(ENV_TARGET), "use_env_password": True},
        )
        body = resp.json()
        assert body["status"] == "error"
        assert body["code"] == "400"

    def test_migration_start_resolves_env_password(self, app, tmp_path, monkeypatch):
        _patch_pg_env(monkeypatch)
        manager = _StubManager()
        app.state.database_migration_manager = manager
        client = _authorized_client(app, tmp_path)
        resp = client.post(
            "/api/v1/database/migration/start",
            json={
                "direction": "sqlite-to-pg",
                "target": dict(ENV_TARGET),
                "use_env_password": True,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == {"phase": "preparing"}
        assert len(manager.start_calls) == 1
        assert manager.start_calls[0]["password"] == ENV_PASSWORD

    def test_migration_start_missing_both_400(self, app, tmp_path, monkeypatch):
        """use_env_password=false 且无显式密码 → 400（不进管理器）。"""
        _patch_pg_env(monkeypatch)
        manager = _StubManager()
        app.state.database_migration_manager = manager
        client = _authorized_client(app, tmp_path)
        resp = client.post(
            "/api/v1/database/migration/start",
            json={"direction": "sqlite-to-pg", "target": dict(ENV_TARGET)},
        )
        assert resp.json()["code"] == "400"
        assert manager.start_calls == []

    def test_credentials_resolves_env_password(self, app, tmp_path, monkeypatch):
        _patch_pg_env(monkeypatch)
        manager = _StubManager()
        app.state.database_migration_manager = manager
        client = _authorized_client(app, tmp_path)
        resp = client.post(
            "/api/v1/database/migration/credentials",
            json={
                "attempt_id": "att-1",
                "target": dict(ENV_TARGET),
                "use_env_password": True,
            },
        )
        assert resp.status_code == 200
        assert len(manager.cred_calls) == 1
        assert manager.cred_calls[0]["password"] == ENV_PASSWORD
        assert manager.cred_calls[0]["attempt_id"] == "att-1"

    def test_credentials_env_password_missing_400(self, app, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "DB_TYPE", "postgresql", raising=False)
        monkeypatch.setattr(settings, "DB_PASSWORD", "", raising=False)
        manager = _StubManager()
        app.state.database_migration_manager = manager
        client = _authorized_client(app, tmp_path)
        resp = client.post(
            "/api/v1/database/migration/credentials",
            json={"attempt_id": "att-1", "target": dict(ENV_TARGET), "use_env_password": True},
        )
        assert resp.json()["code"] == "400"
        assert manager.cred_calls == []
