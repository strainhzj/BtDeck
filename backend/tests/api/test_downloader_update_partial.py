"""下载器更新端点部分更新回归（2026-09-07 生产 422 事故）。

事故复现锚点：POST /downloader/update/{id} 携带桌面列表行整行展开的 camelCase
请求体（isSearch 键名不匹配、且列表接口不返回 isSsl），修复前在请求验证层
422 missing is_search/is_ssl。本文件走完整 FastAPI 路由（含 pydantic 验证），
断言：①事故形状请求体 200；②缺省字段在数据库保持原值；③非法取值仍 422。
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.downloader.models import BtDownloaders

DOWNLOADER_ID = "dabb1e6f-a26e-45be-bcb5-505892747f77"
URL_UPDATE = f"/api/v1/downloader/update/{DOWNLOADER_ID}"

# 2026-09-07 生产事故请求体原样（camelCase 列表行 + enabled 开关值）
INCIDENT_BODY = {
    "id": DOWNLOADER_ID,
    "nickname": "qb-rush",
    "host": "192.168.5.51:28180",
    "isSearch": "1",
    "status": "1",
    "enabled": "0",
    "downloaderType": 0,
    "downloaderId": DOWNLOADER_ID,
    "port": "28180",
    "downloaderTypeName": "qbittorrent",
    "connectStatus": "1",
    "pathMappingRules": None,
    "torrentSavePath": None,
}


@pytest.fixture()
def update_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[BtDownloaders.__table__])
    Session = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id="1")
    client = TestClient(app, raise_server_exceptions=False)

    with Session() as seed:
        seed.add(
            BtDownloaders(
                downloader_id=DOWNLOADER_ID,
                nickname="qb-rush",
                host="192.168.5.51",
                username="qbadmin",
                password="encrypted-dummy",
                is_search=True,
                status="1",
                enabled=True,
                downloader_type=0,
                port="28180",
                is_ssl=True,
                dr=0,
            )
        )
        seed.commit()

    yield client, Session
    engine.dispose()


def _fetch_row(Session) -> BtDownloaders:
    with Session() as session:
        return session.query(BtDownloaders).filter_by(downloader_id=DOWNLOADER_ID).one()


class TestUpdateEndpointPartialUpdate:
    def test_incident_body(self, update_env):
        client, Session = update_env

        response = client.post(URL_UPDATE, json=INCIDENT_BODY)

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "200"
        row = _fetch_row(Session)
        # camelCase 键被忽略 → 蛇形缺省字段保持原值，只有 enabled 生效
        assert row.enabled is False
        assert row.is_search is True
        assert row.is_ssl is True
        assert row.nickname == "qb-rush"
        assert row.downloader_type == 0

    def test_minimal_toggle_payload_roundtrip(self, update_env):
        """最小开关 payload：只传 enabled 可往返启停，其余字段两次均不动。"""
        client, Session = update_env

        off = client.post(URL_UPDATE, json={"enabled": "0"})
        assert off.status_code == 200
        row = _fetch_row(Session)
        assert row.enabled is False
        assert row.is_search is True
        assert row.is_ssl is True

        on = client.post(URL_UPDATE, json={"enabled": "1"})
        assert on.status_code == 200
        row = _fetch_row(Session)
        assert row.enabled is True
        assert row.is_search is True
        assert row.is_ssl is True

    def test_invalid_boolean_value_still_422(self, update_env):
        """可选化不得放松取值校验：非法布尔值仍 422。"""
        client, _Session = update_env

        response = client.post(URL_UPDATE, json={"enabled": "maybe"})

        assert response.status_code == 422
