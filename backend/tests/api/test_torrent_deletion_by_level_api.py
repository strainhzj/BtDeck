# -*- coding: utf-8 -*-
"""
种子按等级删除接口回归测试

覆盖：
- DELETE /api/v1/torrents/delete-with-level 的参数校验（HTTP 级）
- TorrentDeletionByLevelService._add_tag_to_string 标签去重纯函数（零依赖）
- TorrentDeletionByLevelService.delete_by_level L4 路径（service 级，核心价值）

设计决策（经子代理独立审查 + 实证）：
- 类3 用 **service 级测试**而非 HTTP e2e。原因（3 个 🔴 缺陷）：
  1. endpoint 同时用同步 get_db(sqlite3) 和异步 AsyncSessionLocal(aiosqlite)，两驱动两引擎
     无法共享一个内存库（StaticPool 只在单引擎内复用连接）→ HTTP e2e 注入审计异步库不可行。
  2. endpoint 的 CommonResponse.data 丢弃了 db_update_success/db_update_error 等字段，
     HTTP 级无法断言 service 返回的完整结果。
  3. _get_adapter 必读 request.app.state.store，HTTP e2e 需在 test app 上挂 store。
  service 级直接传同步 db + mock request/audit，绕开三缺陷。
- 认证依赖是 require_authenticated_user（非 get_current_user），401 detail 是 dict（CommonResponse 序列化），
  非字符串 "Could not validate credentials"。
- audit_service 传 AsyncMock（记录调用断言 operation_type），不碰异步库。
- store.get_snapshot_sync 是**同步方法**，mock 用普通 MagicMock（非 AsyncMock）。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

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
from app.services.torrent_deletion_by_level import TorrentDeletionByLevelService
from app.torrents.audit_enums import AuditOperationType
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent

URL = "/api/v1/torrents/delete-with-level"

LEVEL4_TAG = TorrentDeletionByLevelService.LEVEL4_TAG  # "pending_delete"


# ==================== 组1：_add_tag_to_string 纯函数（零依赖） ====================


class TestAddTagToString:
    """标签去重纯静态方法。L4 删除的核心 DB 逻辑。"""

    def test_none_existing_returns_just_new_tag(self):
        assert TorrentDeletionByLevelService._add_tag_to_string(None, LEVEL4_TAG) == LEVEL4_TAG

    def test_empty_existing_returns_just_new_tag(self):
        assert TorrentDeletionByLevelService._add_tag_to_string("", LEVEL4_TAG) == LEVEL4_TAG

    def test_single_tag_appended(self):
        result = TorrentDeletionByLevelService._add_tag_to_string("movie", LEVEL4_TAG)
        assert result == "movie,pending_delete"

    def test_already_present_dedup_unchanged(self):
        """已含目标标签 → 不重复追加。"""
        result = TorrentDeletionByLevelService._add_tag_to_string(LEVEL4_TAG, LEVEL4_TAG)
        assert result == LEVEL4_TAG

    def test_whitespace_normalized_and_dedup(self):
        """空白归一化 + 已存在去重，顺序保留。

        "movie, pending_delete ,hd" → strip 后 ["movie","pending_delete","hd"]，
        pending_delete 已在 → 不追加 → "movie,pending_delete,hd"
        """
        result = TorrentDeletionByLevelService._add_tag_to_string("movie, pending_delete ,hd", LEVEL4_TAG)
        assert result == "movie,pending_delete,hd"

    def test_multiple_tags_appended_at_end(self):
        result = TorrentDeletionByLevelService._add_tag_to_string("a,b,c", LEVEL4_TAG)
        assert result == "a,b,c,pending_delete"


# ==================== 组2：端点 HTTP 参数校验 ====================


@pytest.fixture
def sync_engine():
    """同步内存库（建 torrent_info + bt_downloaders），给 get_db override 用。

    类2 大多测试不真查库，但 endpoint 有 Depends(get_db)，必须 override 避免连生产库。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[TorrentInfo.__table__, TrackerInfo.__table__])
    yield engine
    Base.metadata.drop_all(engine, tables=[TrackerInfo.__table__, TorrentInfo.__table__])


@pytest.fixture
def client(sync_engine):
    """最小 app，override 认证 + get_db（给空内存库，类2 不插数据）。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    Session = sessionmaker(bind=sync_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestDeleteWithLevelParamValidation:
    """DELETE /delete-with-level 参数校验。delete_level Query ge=1 le=4，torrent_info_ids Query 必填。"""

    def test_no_token_returns_401(self, sync_engine):
        """无认证 → 401，detail 是 dict（require_authenticated_user 的 CommonResponse 序列化）。"""
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        def override_get_db():
            db = sessionmaker(bind=sync_engine)()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        # 不 override require_authenticated_user → 走真实认证 → 无 token 拒绝
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.delete(URL, params={"torrent_info_ids": "x", "delete_level": 4})
        assert r.status_code == 401
        # require_authenticated_user 抛 HTTPException(401, detail=CommonResponse(code='401').model_dump())
        assert r.json()["detail"]["code"] == "401"

    def test_delete_level_zero_returns_422(self, client):
        r = client.delete(URL, params={"torrent_info_ids": "x", "delete_level": 0})
        assert r.status_code == 422

    def test_delete_level_five_returns_422(self, client):
        r = client.delete(URL, params={"torrent_info_ids": "x", "delete_level": 5})
        assert r.status_code == 422

    def test_missing_torrent_info_ids_returns_422(self, client):
        r = client.delete(URL, params={"delete_level": 4})
        assert r.status_code == 422

    def test_empty_id_list_returns_zero_total(self, client):
        """torrent_info_ids="," → comma-split 得空列表 → service 循环 0 次 → code='200', total=0。"""
        r = client.delete(URL, params={"torrent_info_ids": ",", "delete_level": 4})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0


# ==================== 组3：L4 service 级测试（核心价值） ====================


@pytest.fixture
def db_session():
    """同步内存库，建 torrent_info + bt_downloaders 表。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[TorrentInfo.__table__, TrackerInfo.__table__, BtDownloaders.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_downloader(db, *, downloader_id="dl-1", downloader_type=0, nickname="qbt"):
    """构造最小 BtDownloaders 行（kwargs 风格，非 24 位置参数）。"""
    dl = BtDownloaders(downloader_id=downloader_id, downloader_type=downloader_type, nickname=nickname)
    db.add(dl)
    db.commit()
    return dl


def _make_mock_request(store_downloaders):
    """构造 mock request，其 app.state.store.get_snapshot_sync 返回给定下载器 VO 列表。

    get_snapshot_sync 是同步方法 → 用普通 MagicMock（非 AsyncMock）。
    VO 需含 downloader_id/fail_time/client（_get_adapter 读取）。
    """
    mock_request = MagicMock()
    mock_store = MagicMock()
    mock_store.get_snapshot_sync.return_value = list(store_downloaders)
    mock_request.app.state.store = mock_store
    return mock_request


def _make_fake_vo(*, downloader_id="dl-1", fail_time=0, client=None):
    """构造伪下载器 VO（缓存快照中的对象）。"""
    return SimpleNamespace(
        downloader_id=downloader_id,
        fail_time=fail_time,
        client=client or MagicMock(),
        nickname="qbt",
    )


class TestDeleteLevel4Service:
    """L4 待删除标签路径（service 级，直接实例化 service 调 delete_by_level）。

    核心断言点：DB tags 变更（去重）+ audit 调用 operation_type + adapter 失败降级。
    """

    @pytest.mark.asyncio
    async def test_l4_success_updates_tags_and_logs_audit(self, db_session):
        """L4 成功：tags 含 pending_delete（去重）+ audit 调一次 DELETE_L4。"""
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="movie")
        _make_downloader(db_session)
        fake_client = MagicMock()
        mock_request = _make_mock_request([_make_fake_vo(client=fake_client)])
        audit = AsyncMock()

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        result = await svc.delete_by_level("t1", 4, operator="alice", audit_service=audit)

        assert result["success"] is True
        assert result["db_update_success"] is True
        # 查库：tags 含 pending_delete
        db_session.expire_all()
        torrent = db_session.query(TorrentInfo).filter_by(info_id="t1").first()
        assert LEVEL4_TAG in torrent.tags
        # audit 调用一次，operation_type=DELETE_L4
        audit.log_operation.assert_awaited_once()
        kwargs = audit.log_operation.await_args.kwargs
        assert kwargs["operation_type"] == AuditOperationType.DELETE_L4
        assert kwargs["operator"] == "alice"

    @pytest.mark.asyncio
    async def test_l4_already_has_tag_no_duplicate(self, db_session):
        """torrent.tags 已含 pending_delete → 不重复追加。"""
        # make_torrent 默认 tags=""，这里手动预设
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="m")
        db_session.query(TorrentInfo).filter_by(info_id="t1").first().tags = f"movie,{LEVEL4_TAG}"
        db_session.commit()
        _make_downloader(db_session)
        mock_request = _make_mock_request([_make_fake_vo()])

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        result = await svc.delete_by_level("t1", 4, audit_service=AsyncMock())

        assert result["success"] is True
        db_session.expire_all()
        tags = db_session.query(TorrentInfo).filter_by(info_id="t1").first().tags
        # pending_delete 只出现一次
        assert tags.count(LEVEL4_TAG) == 1

    @pytest.mark.asyncio
    async def test_l4_adapter_failure_leaves_tags_unchanged(self, db_session):
        """适配器 add_tag 失败（torrents_add_tags 抛异常）→ DB tags 不变，返回 success=False。"""
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="m")
        _make_downloader(db_session)
        fake_client = MagicMock()
        # 注意：create_tags 异常会被吞，必须让 torrents_add_tags 抛
        fake_client.torrents_add_tags.side_effect = Exception("boom")
        mock_request = _make_mock_request([_make_fake_vo(client=fake_client)])

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        result = await svc.delete_by_level("t1", 4, audit_service=AsyncMock())

        assert result["success"] is False
        db_session.expire_all()
        tags = db_session.query(TorrentInfo).filter_by(info_id="t1").first().tags
        assert LEVEL4_TAG not in tags, "适配器失败时 DB tags 不应被修改"

    @pytest.mark.asyncio
    async def test_l4_downloader_not_in_cache_fails(self, db_session):
        """下载器不在缓存快照 → _get_adapter 抛 ValueError → success=False。"""
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="m")
        _make_downloader(db_session)
        mock_request = _make_mock_request([])  # 空缓存

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        result = await svc.delete_by_level("t1", 4, audit_service=AsyncMock())

        assert result["success"] is False
        assert "适配器" in result.get("error", "") or "缓存" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_l4_downloader_invalid_fails(self, db_session):
        """下载器 fail_time>0（失效）→ _get_adapter 抛 ValueError → success=False。"""
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="m")
        _make_downloader(db_session)
        vo = _make_fake_vo(fail_time=999)
        mock_request = _make_mock_request([vo])

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        result = await svc.delete_by_level("t1", 4, audit_service=AsyncMock())

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_l4_torrent_not_found_fails(self, db_session):
        """info_id 查不到（dr=1 或不存在）→ success=False（"种子不存在"）。"""
        _make_downloader(db_session)
        mock_request = _make_mock_request([_make_fake_vo()])

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        result = await svc.delete_by_level("nonexistent", 4, audit_service=AsyncMock())

        assert result["success"] is False
        assert result.get("error") == "种子不存在"

    @pytest.mark.asyncio
    async def test_l4_db_commit_failure_still_success_but_db_flag_false(self, db_session):
        """DB commit 抛异常 → service 仍返回 success=True（下载器标签已加），
        但 db_update_success=False + db_update_error 非空（独立结果维度）。

        这是 service 级才能测到的细节：HTTP 响应丢弃了 db_update_success 字段。
        """
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="m")
        _make_downloader(db_session)
        mock_request = _make_mock_request([_make_fake_vo()])

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        # 让 commit 抛异常（rollback 也 mock，不抛）
        original_commit = db_session.commit
        original_rollback = db_session.rollback
        from sqlalchemy.exc import SQLAlchemyError

        db_session.commit = MagicMock(side_effect=SQLAlchemyError("forced commit fail"))
        db_session.rollback = MagicMock()
        try:
            result = await svc.delete_by_level("t1", 4, audit_service=AsyncMock())
        finally:
            db_session.commit = original_commit
            db_session.rollback = original_rollback

        assert result["success"] is True, "下载器标签已加，业务仍 success"
        assert result["db_update_success"] is False, "DB 更新失败标记"
        assert result["db_update_error"] is not None
