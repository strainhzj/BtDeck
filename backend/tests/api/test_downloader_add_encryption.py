# -*- coding: utf-8 -*-
"""downloader add 端点加密落库回归测试（W6）。

保护点（防回归）：
1. POST /downloader/add 的密码必须以 sm4: 前缀加密落库——历史缺陷是
   add 明文直写、update 才加密，decrypt 对明文静默透传掩盖了明文存储
   （对抗验证实测 DB 4/4 明文）；
2. 加密发生在 ORM 构造点：缓存同步（_check_and_add_new_downloader）拿到的
   也必须是密文（仅 SQL 层加密会静默失效）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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

URL_ADD = "/api/v1/downloader/add"


@pytest.fixture()
def downloader_env():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[BtDownloaders.__table__])
    Session = sessionmaker(bind=engine)
    db = Session()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="admin", user_id="1")
    client = TestClient(app, raise_server_exceptions=False)
    yield client, Session
    db.close()
    engine.dispose()


def _add_body(password: str = "S3cretP@ssw0rd!") -> dict:
    return {
        "host": "127.0.0.1",
        "nickname": "test-qb",
        "username": "qbadmin",
        "password": password,
        "is_search": False,
        "downloader_type": 0,
        "enabled": True,
        "is_ssl": False,
        "port": 8080,
    }


class TestAddEndpointEncryptsPassword:
    """add 端点密码加密落库（ORM 构造点）。"""

    def test_password_stored_with_sm4_prefix(self, downloader_env):
        client, Session = downloader_env
        with patch(
            "app.downloader.initialization._check_and_add_new_downloader",
            new=AsyncMock(return_value=None),
        ):
            r = client.post(URL_ADD, json=_add_body("RealP@ssw0rd"))
        assert r.json()["code"] == "200", r.text

        with Session() as db:
            row = db.query(BtDownloaders).first()
            assert row is not None
            assert row.password.startswith("sm4:"), "add 端点密码必须加密落库"
            assert row.password != "RealP@ssw0rd"
            # 密文可解密回原文（内部建连路径依赖）
            from app.utils.encryption import decrypt_password

            assert decrypt_password(row.password) == "RealP@ssw0rd"

    def test_cache_sync_receives_encrypted_password(self, downloader_env):
        """缓存同步必须拿到密文——若加密只发生在 SQL 层，这里会收到明文。"""
        client, Session = downloader_env
        captured = {}

        async def _fake_check(app, downloader_data, immediate=False):
            captured["password"] = downloader_data.get("password")

        with patch(
            "app.downloader.initialization._check_and_add_new_downloader",
            new=_fake_check,
        ):
            r = client.post(URL_ADD, json=_add_body("CacheP@ss"))
        assert r.json()["code"] == "200"
        assert captured.get("password", "").startswith("sm4:"), "缓存同步必须携带密文"

    def test_empty_password_kept_empty(self, downloader_env):
        """空密码保持空串（不产生 sm4: 前缀的空加密）。"""
        client, Session = downloader_env
        with patch(
            "app.downloader.initialization._check_and_add_new_downloader",
            new=AsyncMock(return_value=None),
        ):
            r = client.post(URL_ADD, json=_add_body(""))
        assert r.json()["code"] == "200"
        with Session() as db:
            row = db.query(BtDownloaders).first()
            assert row.password == ""
