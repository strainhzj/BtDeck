# -*- coding: utf-8 -*-
"""
批量转移失败语义回归（verified-bugfix-remediation W5-3/W5-4）

覆盖：
- 部分/全部失败时批量端点返回 code=400（results 仍在 data）
- 全部成功返回 code=200
- 转移操作写入 torrent_audit_log（操作日志页面可见），operator 为真实用户
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base
from app.factory import app as global_app
from app.torrents.audit_models import TorrentAuditLog

URL = "/api/v1/torrents/batch-transfer"


def _body(*, hashes=("a" * 40, "b" * 40), source="1", target="2"):
    return {
        "source_downloader_id": source,
        "target_downloader_id": target,
        "info_hashes": list(hashes),
        "target_path": "/downloads/movies",
        "delete_source": False,
    }


def _fake_service_cls(result_statuses):
    """构造伪 SeedTransferService 类：transfer_seed 按顺序返回给定状态。"""
    service_cls = MagicMock()
    service = service_cls.return_value
    service.aclose = AsyncMock(return_value=None)

    async def _transfer_seed(**kwargs):
        status = result_statuses.pop(0)
        if status == "success":
            return {
                "success": True,
                "transfer_status": "success",
                "torrent_name": "种子",
                "source_downloader_name": "源",
                "target_downloader_name": "目标",
                "source_path": "/s",
                "target_path": "/downloads/movies",
                "delete_source": False,
                "transfer_duration": 100,
                "error_message": None,
            }
        return {
            "success": False,
            "transfer_status": "failed",
            "torrent_name": "种子",
            "source_downloader_name": "源",
            "target_downloader_name": "目标",
            "source_path": "/s",
            "target_path": "/downloads/movies",
            "delete_source": False,
            "transfer_duration": 100,
            "error_message": "种子文件备份中未找到该种子",
        }

    service.transfer_seed = AsyncMock(side_effect=_transfer_seed)
    return service_cls


@pytest.fixture
async def batch_client():
    """内存库（torrent_audit_log）+ patch AsyncSessionLocal + 伪服务。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[TorrentAuditLog.__table__]))

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester", user_id=7)

    had_store = hasattr(global_app.state, "store")
    old_store = getattr(global_app.state, "store", None)
    global_app.state.store = SimpleNamespace()

    with (
        patch("app.api.endpoints.seed_transfer.AsyncSessionLocal", session_factory),
        patch("app.services.seed_transfer_service.AsyncSessionLocal", session_factory),
        patch("app.database.AsyncSessionLocal", session_factory),
    ):
        yield app, TestClient(app, raise_server_exceptions=False), session_factory

    if had_store:
        global_app.state.store = old_store


class TestBatchTransferFailureSemantics:
    """W5-3：批量失败返回 code=400。"""

    async def test_all_failed_returns_400_with_results(self, batch_client):
        app, client, _ = batch_client
        with patch(
            "app.api.endpoints.seed_transfer.SeedTransferService",
            _fake_service_cls(["failed", "failed"]),
        ):
            resp = client.post(URL, json=_body())

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "400"
        assert body["status"] == "error"
        assert "成功0个，失败2个" in body["msg"]
        assert body["data"]["total_count"] == 2
        assert body["data"]["failed_count"] == 2
        assert len(body["data"]["results"]) == 2

    async def test_all_success_returns_200(self, batch_client):
        app, client, _ = batch_client
        with patch(
            "app.api.endpoints.seed_transfer.SeedTransferService",
            _fake_service_cls(["success", "success"]),
        ):
            resp = client.post(URL, json=_body())

        body = resp.json()
        assert body["code"] == "200"
        assert body["status"] == "success"
        assert body["data"]["success_count"] == 2

    async def test_partial_failure_returns_400(self, batch_client):
        app, client, _ = batch_client
        with patch(
            "app.api.endpoints.seed_transfer.SeedTransferService",
            _fake_service_cls(["success", "failed"]),
        ):
            resp = client.post(URL, json=_body())

        body = resp.json()
        assert body["code"] == "400"
        assert body["data"]["success_count"] == 1
        assert body["data"]["failed_count"] == 1


class TestBatchTransferAudit:
    """W5-4：转移审计写入 torrent_audit_log，operator 为真实用户。"""

    async def test_audit_rows_written_with_real_operator(self, batch_client):
        from sqlalchemy import select

        app, client, session_factory = batch_client
        with patch(
            "app.api.endpoints.seed_transfer.SeedTransferService",
            _fake_service_cls(["success", "failed"]),
        ):
            resp = client.post(URL, json=_body())

        assert resp.json()["code"] == "400"

        async with session_factory() as db:
            rows = (await db.execute(select(TorrentAuditLog))).scalars().all()
        assert len(rows) == 2
        assert all(row.operation_type == "transfer" for row in rows)
        assert all(row.operator == "tester" for row in rows)
        assert {row.operation_result for row in rows} == {"success", "failed"}

    async def test_audit_rows_record_request_ip_and_user_agent(self, batch_client):
        """审计 IP：端点从请求提取 ip_address/user_agent 并写入审计行。"""
        from sqlalchemy import select

        app, client, session_factory = batch_client
        with (
            patch(
                "app.api.endpoints.seed_transfer.SeedTransferService",
                _fake_service_cls(["success"]),
            ),
            patch(
                "app.api.endpoints.seed_transfer.extract_audit_info_from_request",
                return_value={"ip_address": "192.168.5.60", "user_agent": "pytest-agent"},
            ),
        ):
            resp = client.post(URL, json=_body(hashes=("a" * 40,)))

        assert resp.json()["code"] == "200"

        async with session_factory() as db:
            rows = (await db.execute(select(TorrentAuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].ip_address == "192.168.5.60"
        assert rows[0].user_agent == "pytest-agent"

    async def test_single_transfer_audit_records_ip_from_xff_header(self, batch_client):
        """单个转移端点的真实提取链路：不 patch extract，TestClient 携带
        X-Forwarded-For 头 → 审计行记录首值（与 nginx 反代生产行为一致）。"""
        from sqlalchemy import select

        app, client, session_factory = batch_client
        with patch(
            "app.api.endpoints.seed_transfer.SeedTransferService",
            _fake_service_cls(["success"]),
        ):
            resp = client.post(
                "/api/v1/torrents/transfer",
                json={
                    "source_downloader_id": "1",
                    "target_downloader_id": "2",
                    "info_hash": "a" * 40,
                    "target_path": "/downloads/movies",
                    "delete_source": False,
                },
                headers={
                    "X-Forwarded-For": "203.0.113.9, 172.25.0.2",
                    "User-Agent": "regression-agent",
                },
            )

        assert resp.json()["code"] == "200"

        async with session_factory() as db:
            rows = (await db.execute(select(TorrentAuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].ip_address == "203.0.113.9"
        assert rows[0].user_agent == "regression-agent"
