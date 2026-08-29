"""W1 健康接口 build 身份块回归（release-artifact-equivalence-gate task .2）。

硬约束：CommonResponse 外壳与 data.status/data.version 完全向后兼容（桌面/Android
伴侣依赖）；build 为新增字段。身份非法 → ready 503 + build_identity_invalid（fail-closed），
live 保持 200。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.endpoints import health
from app.core import build_info
from app.factory import create_app


def _client():
    app = create_app(configure_routes=False)
    app.include_router(health.router)
    app.include_router(health.sync_router, prefix="/api/v1/health")
    return app, TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_build_info_cache():
    build_info.reset_cache()
    yield
    build_info.reset_cache()


@pytest.fixture(autouse=True)
def _isolate_build_info(monkeypatch, tmp_path):
    monkeypatch.setenv("BTDECK_BUILD_INFO", str(tmp_path / "absent.json"))


def _patch_ready_ok(monkeypatch, app):
    monkeypatch.setattr(health, "_probe_database", AsyncMock())
    app.state.sync_lag_sampler = SimpleNamespace(sampler=None)


def _valid_payload() -> dict:
    return {
        "schema_version": 1,
        "product_version": "1.0.6",
        "git_sha": "29c6f6f68ab35e25f8cf7237ee187de359c77714",
        "git_tag": "v1.0.6",
        "source_date_epoch": 1770000000,
        "build_id": None,
        "artifact_kind": "docker-backend",
        "target_os": "linux",
        "target_arch": "amd64",
        "python_version": "3.11.9",
        "node_version": None,
        "alembic_head": "c1d2e3f4a5b6",
        "frontend_manifest_sha256": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "dependency_manifest_sha256": None,
        "dirty": False,
    }


class TestBackwardCompatibility:
    def test_live_envelope_and_legacy_fields_unchanged(self):
        _, client = _client()
        body = client.get("/health/live").json()
        assert body["status"] == "success"
        assert body["code"] == "200"
        assert body["data"]["status"] == "alive"
        assert isinstance(body["data"]["version"], str) and body["data"]["version"]

    def test_ready_legacy_fields_unchanged_in_dev_mode(self, monkeypatch):
        app, client = _client()
        _patch_ready_ok(monkeypatch, app)
        body = client.get("/health/ready").json()
        assert body["status"] == "success"
        assert body["data"]["status"] == "ready"
        assert body["data"]["version"]
        assert set(body["data"]["checks"]) == {"database", "worker", "eventLoopLag"}


class TestBuildBlockExposure:
    def test_live_dev_mode_build_block(self):
        _, client = _client()
        block = client.get("/health/live").json()["data"]["build"]
        assert block["status"] == "dev"
        assert "gitSha" not in block  # dev 模式不伪造身份

    def test_ready_exposes_embedded_identity(self, monkeypatch, tmp_path):
        target = tmp_path / "build-info.json"
        target.write_text(json.dumps(_valid_payload()), encoding="utf-8")
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))
        app, client = _client()
        _patch_ready_ok(monkeypatch, app)

        block = client.get("/health/ready").json()["data"]["build"]
        assert block["status"] == "ok"
        assert block["gitSha"] == _valid_payload()["git_sha"]
        assert block["alembicHead"] == "c1d2e3f4a5b6"
        assert block["artifactKind"] == "docker-backend"


class TestFailClosed:
    def test_invalid_identity_keeps_live_200_but_marks_invalid(self, monkeypatch, tmp_path):
        target = tmp_path / "build-info.json"
        target.write_text("{ broken", encoding="utf-8")
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))
        _, client = _client()

        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["data"]["build"] == {"status": "invalid"}

    def test_invalid_identity_fails_ready_closed(self, monkeypatch, tmp_path):
        target = tmp_path / "build-info.json"
        target.write_text(json.dumps({**_valid_payload(), "git_sha": "short"}), encoding="utf-8")
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))
        app, client = _client()
        _patch_ready_ok(monkeypatch, app)

        response = client.get("/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert "build_identity_invalid" in body["data"]["reasonCodes"]
        assert body["data"]["build"] == {"status": "invalid"}
