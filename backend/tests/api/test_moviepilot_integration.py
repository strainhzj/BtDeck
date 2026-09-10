# -*- coding: utf-8 -*-
"""MoviePilot 集成 API 回归（feature moviepilot-integration-20260908）。

覆盖第一版核心语义：

- **设置面**：默认 fail-closed（关）；CAS 更新 0→1；409 冲突；损坏行回落；
- **握手**：开关关闭 403；首次注册 created=true；重复握手幂等；实例禁用 403；
  其他有效账号冒名 403；绑定账号失效后允许改绑；
- **同步幂等**：未知实例 404；协议版本不符 400；同内容重投 skipped、字段
  变更 updated、新增 inserted，行数不重复；hash 缺失 unassociated、
  未映射 unmapped、已映射 linked；
- **映射**：更新映射后历史行重解析（unmapped→linked）；指向不存在下载器 400；
- **关联查询**：正向 (bt_downloader_id, hash) 精确命中且同 hash 双下载器
  不串联；反查路径（精确/目录前缀/mode 过滤/过短 400）并回带任务快照；
- **认证**：无/坏 token 401；禁用/强制改密 403（principal 全链）；
- **审计**：同步批次与设置变更 best-effort 写入审计行；
- **信封**：实例列表与关联查询的分页字段 total/page/pageSize/list。
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth import utils as auth_utils
from app.auth.models import Config, User
from app.database import Base, get_async_db, get_db
from app.downloader.models import BtDownloaders
from app.models.moviepilot_instance import MoviePilotInstance
from app.models.moviepilot_transfer_history import MoviePilotTransferHistory
from app.torrents.audit_models import TorrentAuditLog
from app.torrents.models import TorrentInfo
from tests.api.conftest import make_torrent

TEST_SECRET = "test-secret-key-for-moviepilot"
TEST_LOGIN_SECRET = "test-login-secret-for-moviepilot"

INSTANCE_ID = "mp-inst-0001-0002-0003-0004"
OTHER_INSTANCE_ID = "mp-inst-other-0002-0003-0004"
DL_A = "bt-dl-aaaaaaaa"
DL_B = "bt-dl-bbbbbbbb"


# ==============================================================================
# 夹具
# ==============================================================================


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Config.__table__,
            User.__table__,
            BtDownloaders.__table__,
            MoviePilotInstance.__table__,
            MoviePilotTransferHistory.__table__,
            TorrentInfo.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
async def async_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[TorrentAuditLog.__table__]))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=[TorrentAuditLog.__table__]))
        await engine.dispose()


@pytest.fixture
def client(db_session, async_db):
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    async def override_get_async_db():
        yield async_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db

    mock_settings = MagicMock()
    mock_settings.SECRET_KEY = TEST_SECRET
    mock_settings.ALGORITHM = "HS256"
    mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    with (
        patch("app.auth.utils.settings", mock_settings),
        patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET),
    ):
        yield TestClient(app, raise_server_exceptions=False)


def _make_user(db_session: Session, username: str = "admin", **overrides) -> User:
    user = User(
        username=username,
        password="not-a-real-hash",
        is_active=overrides.get("is_active", True),
        must_change_password=overrides.get("must_change_password", False),
    )
    db_session.add(user)
    db_session.commit()
    return user


def _token(username: str, user_id: int = 1) -> str:
    return auth_utils.create_access_token(
        {"sub": username, "user_id": str(user_id), "verify_secret": TEST_LOGIN_SECRET}
    )


def _auth(username: str = "admin", user_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {_token(username, user_id)}"}


def _enable_integration(client: TestClient, db_session: Session) -> None:
    _make_user(db_session, "admin")
    resp = client.put(
        "/api/v1/moviepilot/settings",
        headers=_auth(),
        json={"enabled": True, "expectedRevision": 0},
    )
    assert resp.status_code == 200, resp.text


def _make_downloader(db_session: Session, downloader_id: str, nickname: str) -> BtDownloaders:
    row = BtDownloaders(downloader_id=downloader_id, nickname=nickname, downloader_type=0)
    db_session.add(row)
    db_session.commit()
    return row


def _item(history_id: int, **overrides) -> dict:
    base = {
        "historyId": history_id,
        "srcStorage": "local",
        "srcPath": "/data/downloads/Movie/movie.mkv",
        "destStorage": "local",
        "destPath": "/data/media/电影/Movie (2026)/Movie.mkv",
        "transferMode": "link",
        "mediaType": "电影",
        "title": "Movie",
        "year": "2026",
        "seasons": None,
        "episodes": None,
        "tmdbId": 123,
        "doubanId": None,
        "mediaSource": "themoviedb",
        "mediaId": "movie:123",
        "mpDownloader": "qb-main",
        "downloadHash": "a" * 40,
        "status": True,
        "errmsg": None,
        "recordedAt": "2026-09-01 10:00:00",
        "files": [{"path": "/data/media/电影/Movie (2026)/Movie.mkv"}],
    }
    base.update(overrides)
    return base


def _sync(client: TestClient, items: list, instance_id: str = INSTANCE_ID, **overrides) -> dict:
    payload = {
        "instanceId": instance_id,
        "protocolVersion": 1,
        "syncMode": "incremental",
        "pageNumber": 1,
        "pageSize": 100,
        "isLastBatch": True,
        "items": items,
    }
    payload.update(overrides)
    resp = client.post(
        "/api/v1/moviepilot/sync/transfer-history",
        headers=_auth(),
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _handshake(client: TestClient, instance_id: str = INSTANCE_ID, name: str = "测试实例") -> dict:
    resp = client.post(
        "/api/v1/moviepilot/handshake",
        headers=_auth(),
        json={
            "instanceId": instance_id,
            "instanceName": name,
            "protocolVersion": 1,
            "pluginVersion": "1.0.0",
            "moviepilotVersion": "2.9.9",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ==============================================================================
# 设置面
# ==============================================================================


class TestSettings:
    def test_default_disabled_fail_closed(self, client, db_session):
        _make_user(db_session, "admin")
        resp = client.get("/api/v1/moviepilot/settings", headers=_auth())
        assert resp.status_code == 200
        settings = resp.json()["data"]["settings"]
        assert settings["enabled"] is False
        assert settings["revision"] == 0

    def test_cas_update_sequence(self, client, db_session):
        _make_user(db_session, "admin")
        resp = client.put("/api/v1/moviepilot/settings", headers=_auth(), json={"enabled": True, "expectedRevision": 0})
        assert resp.status_code == 200
        assert resp.json()["data"]["settings"]["revision"] == 1
        resp = client.put(
            "/api/v1/moviepilot/settings", headers=_auth(), json={"enabled": False, "expectedRevision": 0}
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["data"]["currentRevision"] == 1

    def test_corrupted_row_falls_back_closed(self, client, db_session):
        _make_user(db_session, "admin")
        db_session.add(Config(key="moviepilot.integration.v1", value="{broken json", description="t"))
        db_session.commit()
        resp = client.get("/api/v1/moviepilot/settings", headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["data"]["settings"]["enabled"] is False

    async def test_settings_audit_written(self, client, db_session, async_db):
        _make_user(db_session, "admin")
        client.put("/api/v1/moviepilot/settings", headers=_auth(), json={"enabled": True, "expectedRevision": 0})
        rows = (
            (
                await async_db.execute(
                    select(TorrentAuditLog).where(TorrentAuditLog.operation_type == "moviepilot_settings_update")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].operator == "admin"


# ==============================================================================
# 握手
# ==============================================================================


class TestHandshake:
    def test_disabled_global_switch_rejected(self, client, db_session):
        _make_user(db_session, "admin")
        resp = client.post(
            "/api/v1/moviepilot/handshake",
            headers=_auth(),
            json={"instanceId": INSTANCE_ID, "protocolVersion": 1},
        )
        assert resp.status_code == 403
        assert db_session.query(MoviePilotInstance).count() == 0

    def test_first_handshake_registers_instance(self, client, db_session):
        _enable_integration(client, db_session)
        data = _handshake(client)
        assert data["created"] is True
        assert data["protocolVersion"] == 1
        row = db_session.query(MoviePilotInstance).one()
        assert row.instance_id == INSTANCE_ID
        assert row.bound_username == "admin"
        assert row.last_handshake_at is not None

    def test_repeat_handshake_idempotent(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        data = _handshake(client)
        assert data["created"] is False
        assert db_session.query(MoviePilotInstance).count() == 1

    def test_other_user_rejected_by_binding(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        _make_user(db_session, "intruder", must_change_password=False)
        resp = client.post(
            "/api/v1/moviepilot/handshake",
            headers=_auth("intruder", user_id=2),
            json={"instanceId": INSTANCE_ID, "protocolVersion": 1},
        )
        assert resp.status_code == 403

    def test_rebind_after_bound_user_gone(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        db_session.query(User).filter(User.username == "admin").delete()
        db_session.commit()
        _make_user(db_session, "newbie")
        resp = client.post(
            "/api/v1/moviepilot/handshake",
            headers=_auth("newbie", user_id=2),
            json={"instanceId": INSTANCE_ID, "protocolVersion": 1},
        )
        assert resp.status_code == 200
        assert db_session.query(MoviePilotInstance).one().bound_username == "newbie"

    def test_disabled_instance_rejected(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        row = db_session.query(MoviePilotInstance).one()
        row.enabled = False
        db_session.commit()
        resp = client.post(
            "/api/v1/moviepilot/handshake",
            headers=_auth(),
            json={"instanceId": INSTANCE_ID, "protocolVersion": 1},
        )
        assert resp.status_code == 403


# ==============================================================================
# 同步幂等与关联状态
# ==============================================================================


class TestSyncIdempotency:
    def test_sync_unknown_instance_404(self, client, db_session):
        _enable_integration(client, db_session)
        resp = client.post(
            "/api/v1/moviepilot/sync/transfer-history",
            headers=_auth(),
            json={"instanceId": INSTANCE_ID, "protocolVersion": 1, "syncMode": "full", "items": []},
        )
        assert resp.status_code == 404

    def test_protocol_mismatch_400(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        resp = client.post(
            "/api/v1/moviepilot/sync/transfer-history",
            headers=_auth(),
            json={"instanceId": INSTANCE_ID, "protocolVersion": 2, "syncMode": "full", "items": []},
        )
        assert resp.status_code == 400

    def test_insert_skip_update_semantics(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)

        first = _sync(client, [_item(1), _item(2)])
        assert (first["inserted"], first["skipped"], first["updated"]) == (2, 0, 0)

        again = _sync(client, [_item(1), _item(2)])
        assert (again["inserted"], again["skipped"], again["updated"]) == (0, 2, 0)
        assert again["syncedHistoryCount"] == 2

        changed = _sync(client, [_item(1, title="Movie 改名", transferMode="copy")])
        assert (changed["inserted"], changed["skipped"], changed["updated"]) == (0, 0, 1)

        assert db_session.query(MoviePilotTransferHistory).count() == 2
        row = db_session.query(MoviePilotTransferHistory).filter_by(history_id=1).one()
        assert row.title == "Movie 改名"
        assert row.transfer_mode == "copy"
        assert row.first_synced_at is not None and row.last_synced_at is not None

    def test_association_status_matrix(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        _make_downloader(db_session, DL_A, "下载器A")

        # 未配置映射：有 hash → unmapped；无 hash → unassociated
        result = _sync(client, [_item(1), _item(2, downloadHash=None, mpDownloader=None)])
        assert result["inserted"] == 2
        row1 = db_session.query(MoviePilotTransferHistory).filter_by(history_id=1).one()
        row2 = db_session.query(MoviePilotTransferHistory).filter_by(history_id=2).one()
        assert row1.association_status == "unmapped"
        assert row2.association_status == "unassociated"

        # 配置映射后重解析 → linked 且冗余列指向 DL_A
        resp = client.put(
            f"/api/v1/moviepilot/instances/{INSTANCE_ID}",
            headers=_auth(),
            json={"downloaderMapping": {"qb-main": DL_A}},
        )
        assert resp.status_code == 200, resp.text
        db_session.refresh(row1)
        db_session.refresh(row2)
        assert row1.association_status == "linked"
        assert row1.bt_downloader_id == DL_A
        assert row2.association_status == "unassociated"

    def test_invalid_item_recorded_not_fatal(self, client, db_session):
        """绕过 pydantic 直调服务层：单条脏数据只记错误，不拖垮整批。"""
        from app.services.moviepilot_integration_service import MoviePilotIntegrationService

        _enable_integration(client, db_session)
        _handshake(client)
        service = MoviePilotIntegrationService(db_session)
        result = service.sync_transfer_history(
            "admin",
            {
                "instanceId": INSTANCE_ID,
                "protocolVersion": 1,
                "items": [{"srcPath": "no history id"}, _item(5)],
            },
        )
        assert result["failed"] == 1
        assert result["inserted"] == 1
        assert result["errors"][0]["historyId"] is None
        instance = db_session.query(MoviePilotInstance).one()
        assert "1 条失败" in (instance.last_error or "")

    async def test_sync_audit_written(self, client, db_session, async_db):
        _enable_integration(client, db_session)
        _handshake(client)
        _sync(client, [_item(1)])
        rows = (
            (await async_db.execute(select(TorrentAuditLog).where(TorrentAuditLog.operation_type == "moviepilot_sync")))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        detail = rows[0].operation_detail
        if isinstance(detail, str):
            import json as _json

            detail = _json.loads(detail)
        assert detail["counts"]["inserted"] == 1


# ==============================================================================
# 实例管理
# ==============================================================================


class TestInstanceManagement:
    def test_mapping_to_unknown_downloader_400(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        resp = client.put(
            f"/api/v1/moviepilot/instances/{INSTANCE_ID}",
            headers=_auth(),
            json={"downloaderMapping": {"qb-main": "not-exist-dl"}},
        )
        assert resp.status_code == 400

    def test_instances_list_envelope(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client, name="实例一")
        resp = client.get("/api/v1/moviepilot/instances", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert set(data.keys()) >= {"total", "page", "pageSize", "list"}
        assert data["total"] == 1
        assert data["list"][0]["name"] == "实例一"
        assert data["list"][0]["downloaderMapping"] == {}

    def test_delete_instance_cascades_histories(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        _sync(client, [_item(1), _item(2)])
        assert db_session.query(MoviePilotTransferHistory).count() == 2
        resp = client.delete(f"/api/v1/moviepilot/instances/{INSTANCE_ID}", headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["data"]["deletedHistories"] == 2
        assert db_session.query(MoviePilotTransferHistory).count() == 0
        assert db_session.query(MoviePilotInstance).count() == 0


# ==============================================================================
# 关联查询
# ==============================================================================


class TestAssociations:
    def _seed_linked(self, client, db_session):
        """两下载器各一个同 hash 任务 + 映射到 DL_A 的一条历史。"""
        _enable_integration(client, db_session)
        _handshake(client)
        _make_downloader(db_session, DL_A, "下载器A")
        _make_downloader(db_session, DL_B, "下载器B")
        make_torrent(
            db_session, info_id="t-a", downloader_id=DL_A, hash_="a" * 40, name="任务A", downloader_name="下载器A"
        )
        make_torrent(
            db_session, info_id="t-b", downloader_id=DL_B, hash_="a" * 40, name="任务B", downloader_name="下载器B"
        )
        resp = client.put(
            f"/api/v1/moviepilot/instances/{INSTANCE_ID}",
            headers=_auth(),
            json={"downloaderMapping": {"qb-main": DL_A}},
        )
        assert resp.status_code == 200
        _sync(client, [_item(1)])

    def test_forward_query_no_cross_downloader(self, client, db_session):
        self._seed_linked(client, db_session)
        resp = client.get(
            "/api/v1/moviepilot/associations",
            headers=_auth(),
            params={"downloaderId": DL_A, "hash": "a" * 40},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        item = data["list"][0]
        assert item["btDownloaderId"] == DL_A
        assert item["associationStatus"] == "linked"
        assert item["title"] == "Movie"
        assert item["instanceName"] == "测试实例"

        # 换成 DL_B 查询：该 hash 在 B 也有任务，但历史只映射到 A → 不串联
        resp_b = client.get(
            "/api/v1/moviepilot/associations",
            headers=_auth(),
            params={"downloaderId": DL_B, "hash": "a" * 40},
        )
        assert resp_b.json()["data"]["total"] == 0

    def test_reverse_lookup_with_task(self, client, db_session):
        self._seed_linked(client, db_session)
        resp = client.get(
            "/api/v1/moviepilot/associations/reverse",
            headers=_auth(),
            params={"path": "/data/media/电影/Movie (2026)/Movie.mkv", "mode": "dest"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        item = data["list"][0]
        assert item["task"]["downloaderId"] == DL_A
        assert item["task"]["name"] == "任务A"

    def test_reverse_lookup_directory_prefix_and_mode(self, client, db_session):
        self._seed_linked(client, db_session)
        # 目录前缀命中
        resp = client.get(
            "/api/v1/moviepilot/associations/reverse",
            headers=_auth(),
            params={"path": "/data/downloads/Movie", "mode": "src"},
        )
        assert resp.json()["data"]["total"] == 1
        # mode 过滤：dest 目录不该命中 src-only 查询
        resp2 = client.get(
            "/api/v1/moviepilot/associations/reverse",
            headers=_auth(),
            params={"path": "/data/media/电影", "mode": "src"},
        )
        assert resp2.json()["data"]["total"] == 0

    def test_reverse_lookup_short_path_400(self, client, db_session):
        _enable_integration(client, db_session)
        resp = client.get(
            "/api/v1/moviepilot/associations/reverse",
            headers=_auth(),
            params={"path": "/a"},
        )
        assert resp.status_code == 400

    def test_unlinked_history_task_is_none(self, client, db_session):
        _enable_integration(client, db_session)
        _handshake(client)
        _sync(client, [_item(1, downloadHash=None)])
        resp = client.get(
            "/api/v1/moviepilot/associations/reverse",
            headers=_auth(),
            params={"path": "/data/media/电影/Movie (2026)/Movie.mkv"},
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["list"][0]["task"] is None
        assert data["list"][0]["associationStatus"] == "unassociated"


# ==============================================================================
# 认证矩阵
# ==============================================================================


class TestAuthMatrix:
    def test_no_token_401(self, client):
        for method, url in [
            ("post", "/api/v1/moviepilot/handshake"),
            ("post", "/api/v1/moviepilot/sync/transfer-history"),
            ("get", "/api/v1/moviepilot/settings"),
            ("get", "/api/v1/moviepilot/instances"),
            ("get", "/api/v1/moviepilot/associations"),
        ]:
            kwargs = {} if method == "get" else {"json": {}}
            resp = getattr(client, method)(url, **kwargs)
            assert resp.status_code == 401, f"{method} {url} → {resp.status_code}"

    def test_invalid_token_401(self, client):
        resp = client.get("/api/v1/moviepilot/settings", headers={"Authorization": "Bearer bad-token"})
        assert resp.status_code == 401

    def test_inactive_user_403(self, client, db_session):
        _make_user(db_session, "sleeper", is_active=False)
        resp = client.get("/api/v1/moviepilot/settings", headers=_auth("sleeper", user_id=9))
        assert resp.status_code == 403

    def test_must_change_password_user_403(self, client, db_session):
        _make_user(db_session, "fresh", must_change_password=True)
        resp = client.get("/api/v1/moviepilot/settings", headers=_auth("fresh", user_id=9))
        assert resp.status_code == 403
