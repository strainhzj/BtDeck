# -*- coding: utf-8 -*-
"""
GET /torrents/torrents/{info_id}/{downloader_id}/{downloader_name} 信封序列化回归测试。

历史缺陷（M1 批次实测发现）：端点直接 return ORM 实体并声明
response_model=CommonResponse，Pydantic 无法从 ORM 属性构造信封，
实测响应为 {"status":null,"msg":null,"code":null,"data":null}。
修复：经 torrent_helpers.convert_to_vo（与 getList 同源转换）包装为
CommonResponse；未找到时按项目惯例返回信封 code="404"（HTTP 200），
不再 raise HTTPException。

路径说明：端点声明 "/torrents/{...}" 且 router 挂载于 prefix="/torrents"，
实际完整路径含双 torrents 段（历史怪癖，与 getList 单段并存）。
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
from app.torrents.models import TorrentInfo
from tests.api.conftest import make_torrent


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[TorrentInfo.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[TorrentInfo.__table__])
    engine.dispose()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id="1")
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app, raise_server_exceptions=False)


def test_get_torrent_returns_envelope_with_vo_data(client, db_session):
    """命中：信封字段完整且 data 为 VO 字段（修复前全 null）。"""
    make_torrent(
        db_session,
        info_id="i-001",
        downloader_id="d-001",
        hash_="abc123",
        name="单种子端点回归",
        downloader_name="qb-main",
        size=2048,
        status="seeding",
    )

    resp = client.get("/api/v1/torrents/torrents/i-001/d-001/qb-main")
    assert resp.status_code == 200
    body = resp.json()

    # 核心回归锚点：修复前 status/msg/code/data 均为 null
    assert body["status"] == "success"
    assert body["code"] == "200"
    data = body["data"]
    assert data is not None, "修复前 ORM 实体直塞信封 data 恒为 null"
    # TorrentInfoVO 输出 camelCase（alias_camel），与 getList 列表项同构
    assert data["infoId"] == "i-001"
    assert data["downloaderId"] == "d-001"
    assert data["downloaderName"] == "qb-main"
    assert data["name"] == "单种子端点回归"
    assert data["hash"] == "abc123"
    assert data["size"] == 2048
    assert data["status"] == "seeding"


def test_get_torrent_missing_returns_envelope_404(client, db_session):
    """未找到：信封 code=404 + HTTP 200（项目惯例），不再 raise HTTPException。"""
    make_torrent(
        db_session,
        info_id="i-exists",
        downloader_id="d-001",
        hash_="ff",
        name="存在",
    )

    resp = client.get("/api/v1/torrents/torrents/i-missing/d-001/qb-main")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["code"] == "404"
    assert body["data"] is None
    # 命中行不受影响
    hit = client.get("/api/v1/torrents/torrents/i-exists/d-001/qb-main")
    assert hit.json()["data"]["infoId"] == "i-exists"


def test_get_torrent_ignores_soft_deleted_rows(client, db_session):
    """dr=1 软删除行不返回（get_torrent_info 过滤 dr == 0）。"""
    make_torrent(
        db_session,
        info_id="i-del",
        downloader_id="d-001",
        hash_="dd",
        name="已删除",
        dr=1,
    )

    resp = client.get("/api/v1/torrents/torrents/i-del/d-001/whatever")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "404"
