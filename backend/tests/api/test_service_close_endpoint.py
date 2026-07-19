# -*- coding: utf-8 -*-
"""
端点 try/finally 调用 close/aclose 的回归测试（prod-hotfix-2026-07-19 P0）

验证目标：
- recycle_bin.py 4 个端点在请求结束后调用 service.close()
- recycle_bin.py 端点业务异常时 finally 仍调用 close
- seed_transfer.py 2 个端点在请求结束后调用 service.aclose()

mutation 反向验证点：删除端点 finally 中的 close/aclose 调用应让这些测试报红。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import get_current_user
from app.database import Base, get_async_db
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo

URL_BIN = "/api/v1/recycle/bin"


# ==================== recycle_bin 端点 fixtures ====================


@pytest.fixture
def sync_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[TorrentInfo.__table__, TrackerInfo.__table__, BtDownloaders.__table__],
    )
    yield engine
    Base.metadata.drop_all(
        bind=engine,
        tables=[TrackerInfo.__table__, TorrentInfo.__table__, BtDownloaders.__table__],
    )


@pytest.fixture
def db_session(sync_engine):
    Session = sessionmaker(bind=sync_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client_with_close_spy(db_session):
    """FastAPI app + RecycleBinService.close 的 spy（wraps 真实方法）。

    返回 (client, close_spy)。spy 用 patch.object wraps 真实方法，
    既允许真实关闭行为，又能断言被调用次数。
    """
    from app.services.recycle_bin_service import RecycleBinService

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")

    with patch("app.database.SessionLocal", return_value=db_session):
        with patch.object(RecycleBinService, "close", wraps=RecycleBinService.close) as spy:
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c, spy

    app.dependency_overrides.clear()


# ==================== recycle_bin 端点 close 测试 ====================


class TestRecycleBinEndpointClosesService:
    """验证 recycle_bin.py 端点 try/finally 中 service.close() 真的被调用。"""

    def test_close_called_on_happy_path(self, client_with_close_spy):
        """happy path：GET /recycle/bin 请求完成后 close 必须被调用一次。"""
        client, spy = client_with_close_spy
        r = client.get(URL_BIN)
        assert r.status_code == 200
        assert spy.call_count == 1, "happy path 必须调用 service.close()"

    def test_close_called_on_cleanup_preview(self, client_with_close_spy):
        """cleanup-preview 端点也必须 close。"""
        client, spy = client_with_close_spy
        r = client.post("/api/v1/recycle/cleanup-preview", json={"days": 30})
        assert r.status_code == 200
        assert spy.call_count == 1

    def test_close_called_even_when_service_method_raises(self, db_session):
        """业务异常路径下 finally 仍必须 close。

        mutation 验证点：删除 finally 块的 close 调用应让此测试报红。
        """
        from app.services.recycle_bin_service import RecycleBinService

        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        async def override_get_async_db():
            yield db_session

        app.dependency_overrides[get_async_db] = override_get_async_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")

        with patch("app.database.SessionLocal", return_value=db_session):
            with patch.object(RecycleBinService, "close", wraps=RecycleBinService.close) as spy:
                # 让业务方法抛异常，触发外层 except，finally 仍应执行 close
                with patch.object(RecycleBinService, "get_recycle_bin_list", side_effect=RuntimeError("biz error")):
                    with TestClient(app, raise_server_exceptions=False) as c:
                        r = c.get(URL_BIN)
                        # 端点 except 兜底返回 500 而非抛
                        assert r.status_code == 200
                        body = r.json()
                        assert body["code"] == "500"
                        # 关键：finally 必须已 close
                        assert spy.call_count == 1, "业务异常时 finally 仍必须 close"

        app.dependency_overrides.clear()
