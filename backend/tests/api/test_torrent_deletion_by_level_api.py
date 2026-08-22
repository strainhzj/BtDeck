# -*- coding: utf-8 -*-
"""
种子按等级删除接口回归测试

覆盖：
- DELETE /api/v1/torrents/delete-with-level 的参数校验（HTTP 级）
- TorrentDeletionByLevelService._add_tag_to_string 标签去重纯函数（零依赖）
- TorrentDeletionByLevelService.delete_by_level L1/L2/L3/L4 路径（service 级，含辅种数量增量与回滚）

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
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

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
from app.torrents.audit_enums import AuditOperationType, AuditOperationResult
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent

URL = "/api/v1/torrents/delete-with-level"
ASYNC_URL = "/api/v1/torrents/delete-batch-async"

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

    def test_dirty_tags_only_separators_returns_just_new_tag(self):
        """脏数据：tags 全是分隔符/空白 → strip 后全空 → 等价于空，返回仅新标签。

        防止历史脏数据（如 ", , ,"）导致新标签前缀一堆空字段。
        """
        result = TorrentDeletionByLevelService._add_tag_to_string(" , , ", LEVEL4_TAG)
        assert result == LEVEL4_TAG


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
        detail = r.json()["detail"]
        assert detail["code"] == "401"
        assert detail["status"] == "error", "确认是认证失败响应（非业务错误/路由 404）"

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


class TestAsyncDeleteReservation:
    def test_all_active_returns_semantic_success_without_executor(self, client):
        from app.services.deletion_task_manager import DeletionTaskSubmission

        manager = MagicMock()
        manager.create_task_reserving = AsyncMock(
            return_value=DeletionTaskSubmission(
                task_id=None,
                accepted_info_ids=[],
                skipped_info_ids=["a", "b"],
            )
        )
        with (
            patch(
                "app.services.deletion_task_manager.get_deletion_task_manager",
                return_value=manager,
            ),
            patch("app.services.async_deletion_executor.AsyncDeletionExecutor") as executor_class,
        ):
            response = client.post(
                ASYNC_URL,
                json={"torrent_info_ids": ["a", "b"], "delete_level": 2},
            )

        data = response.json()["data"]
        assert response.json()["code"] == "200"
        assert data["task_id"] is None
        assert data["requested_count"] == 2
        assert data["accepted_count"] == 0
        assert data["skipped_count"] == 2
        executor_class.assert_not_called()

    def test_mixed_submission_executes_only_new_ids(self, client):
        from app.services.deletion_task_manager import DeletionTaskSubmission

        manager = MagicMock()
        manager.create_task_reserving = AsyncMock(
            return_value=DeletionTaskSubmission(
                task_id="mixed-task",
                accepted_info_ids=["new"],
                skipped_info_ids=["active"],
            )
        )
        executor = MagicMock()
        executor.execute_deletion_task = AsyncMock()

        def close_background(coroutine):
            coroutine.close()
            return MagicMock()

        with (
            patch(
                "app.services.deletion_task_manager.get_deletion_task_manager",
                return_value=manager,
            ),
            patch(
                "app.services.async_deletion_executor.AsyncDeletionExecutor",
                return_value=executor,
            ),
            patch(
                "app.api.endpoints.torrent_deletion.asyncio.create_task",
                side_effect=close_background,
            ),
        ):
            response = client.post(
                ASYNC_URL,
                json={
                    "torrent_info_ids": ["active", "new"],
                    "delete_level": 2,
                },
            )

        data = response.json()["data"]
        assert data["task_id"] == "mixed-task"
        assert data["accepted_count"] == 1
        assert data["skipped_count"] == 1
        call_kwargs = executor.execute_deletion_task.call_args.kwargs
        assert call_kwargs["torrent_info_ids"] == ["new"]


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
        # audit 调用一次，断言关键字段（身份锁定 + operation_type + operation_result + tag）
        audit.log_operation.assert_awaited_once()
        kwargs = audit.log_operation.await_args.kwargs
        assert kwargs["operation_type"] == AuditOperationType.DELETE_L4
        assert kwargs["operator"] == "alice"
        assert kwargs["torrent_info_id"] == "t1", "身份锁定：审计须关联正确的种子"
        assert kwargs["operation_result"] == AuditOperationResult.SUCCESS
        assert kwargs["operation_detail"]["tag"] == LEVEL4_TAG

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
        # 精确匹配：_get_adapter 抛 ValueError("下载器不在缓存中") 被 service 包装为 "获取适配器失败: ..."
        assert result["error"].startswith("获取适配器失败:")
        assert "下载器不在缓存中" in result["error"]

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


# ==================== 组4：辅种数量与等级1/2/3删除 ====================


class TestAuxiliaryCountOnDeleteLevels:
    """等级1/2/3删除后，剩余有效同名同大小种子数量立即减一。"""

    @staticmethod
    def _make_group(db_session, *, count=3, name="same-content", size=1024):
        rows = [
            make_torrent(
                db_session,
                info_id=f"aux-{index}",
                downloader_id="dl-1",
                hash_=f"aux-hash-{index}",
                name=name,
                size=size,
            )
            for index in range(count)
        ]
        for row in rows:
            row.torrent_file = f"/config/torrents/{row.info_id}.torrent"
            row.auxiliary_seed_count = count
        db_session.commit()
        return rows

    @staticmethod
    def _service_with_delete_adapter(db_session):
        _make_downloader(db_session)
        adapter = MagicMock()
        adapter.delete_torrents = AsyncMock(return_value={"failed_hashes": {}})
        service = TorrentDeletionByLevelService(db_session, _make_mock_request([_make_fake_vo()]))
        service._get_adapter = MagicMock(return_value=adapter)
        return service, adapter

    @pytest.mark.asyncio
    @pytest.mark.parametrize("level", [1, 2])
    async def test_level1_and_level2_decrement_active_group(self, db_session, level):
        rows = self._make_group(db_session)
        service, adapter = self._service_with_delete_adapter(db_session)

        result = await service.delete_by_level(rows[0].info_id, level, operator="tester")

        assert result["success"] is True
        db_session.expire_all()
        deleted = db_session.query(TorrentInfo).filter_by(info_id=rows[0].info_id).one()
        active = (
            db_session.query(TorrentInfo)
            .filter(
                TorrentInfo.name == "same-content",
                TorrentInfo.size == 1024,
                TorrentInfo.dr == 0,
                TorrentInfo.deleted_at.is_(None),
            )
            .all()
        )
        assert deleted.dr == 1
        assert [row.auxiliary_seed_count for row in active] == [2, 2]
        adapter.delete_torrents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_level3_decrements_only_after_file_move_succeeds(self, db_session, tmp_path):
        rows = self._make_group(db_session)
        downloader = db_session.query(BtDownloaders).filter_by(downloader_id="dl-1").first()
        if downloader is None:
            downloader = _make_downloader(db_session)
        downloader.path_mapping = "{}"
        backup_path = tmp_path / "seed.torrent"
        backup_path.write_bytes(b"torrent")
        rows[0].backup_file_path = str(backup_path)
        db_session.commit()

        file_service = MagicMock()
        file_service.create_marker_file = AsyncMock(return_value={"success": True})
        file_service.delete_marker_file = AsyncMock(return_value={"success": True})
        adapter = MagicMock()
        adapter.get_torrent_files = AsyncMock(return_value=(True, [], None))
        service = TorrentDeletionByLevelService(db_session, _make_mock_request([_make_fake_vo()]))
        service._get_adapter = MagicMock(return_value=adapter)
        service._delete_from_downloader = AsyncMock(return_value=(True, None))
        service._move_torrent_files_for_recycle = AsyncMock(return_value={"success": True})

        with patch.object(
            BtDownloaders, "file_operations_service", new_callable=PropertyMock, return_value=file_service
        ):
            result = await service.delete_by_level(rows[0].info_id, 3, operator="tester")

        assert result["success"] is True
        db_session.expire_all()
        deleted = db_session.query(TorrentInfo).filter_by(info_id=rows[0].info_id).one()
        active = (
            db_session.query(TorrentInfo)
            .filter(
                TorrentInfo.name == "same-content",
                TorrentInfo.size == 1024,
                TorrentInfo.dr == 0,
                TorrentInfo.deleted_at.is_(None),
            )
            .all()
        )
        assert deleted.deleted_at is not None
        assert deleted.dr == 0
        assert [row.auxiliary_seed_count for row in active] == [2, 2]
        service._move_torrent_files_for_recycle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_level3_move_failure_keeps_group_count_unchanged(self, db_session, tmp_path):
        rows = self._make_group(db_session)
        downloader = db_session.query(BtDownloaders).filter_by(downloader_id="dl-1").first()
        if downloader is None:
            downloader = _make_downloader(db_session)
        downloader.path_mapping = "{}"
        backup_path = tmp_path / "seed.torrent"
        backup_path.write_bytes(b"torrent")
        rows[0].backup_file_path = str(backup_path)
        db_session.commit()

        file_service = MagicMock()
        file_service.create_marker_file = AsyncMock(return_value={"success": True})
        file_service.delete_marker_file = AsyncMock(return_value={"success": True})
        adapter = MagicMock()
        adapter.get_torrent_files = AsyncMock(return_value=(True, [], None))
        service = TorrentDeletionByLevelService(db_session, _make_mock_request([_make_fake_vo()]))
        service._get_adapter = MagicMock(return_value=adapter)
        service._delete_from_downloader = AsyncMock(return_value=(True, None))
        service._move_torrent_files_for_recycle = AsyncMock(return_value={"success": False, "error": "move failed"})

        with patch.object(
            BtDownloaders, "file_operations_service", new_callable=PropertyMock, return_value=file_service
        ):
            result = await service.delete_by_level(rows[0].info_id, 3, operator="tester")

        assert result["success"] is False
        db_session.expire_all()
        restored = db_session.query(TorrentInfo).filter_by(info_id=rows[0].info_id).one()
        active = (
            db_session.query(TorrentInfo)
            .filter(
                TorrentInfo.name == "same-content",
                TorrentInfo.size == 1024,
                TorrentInfo.dr == 0,
                TorrentInfo.deleted_at.is_(None),
            )
            .all()
        )
        assert restored.deleted_at is None
        assert [row.auxiliary_seed_count for row in active] == [3, 3, 3]


# ==================== 组5：delete_batch_by_level 降级编排（service 自身方法） ====================


class TestDeleteBatchByLevel:
    """批量删除编排：L3 备份失败 → 自动降级 L4（by_level.py:217-239）。

    这条降级链路是 service 核心复杂度，之前零覆盖。delete_batch_by_level 是 service
    自身方法（不经过 endpoint 的 comma-split），可在现有 service 级框架直接测。
    触发降级：mock _delete_level3 返回 downgrade_to_level4=True，真实 _delete_level4 执行。
    """

    @pytest.mark.asyncio
    async def test_l3_downgrade_to_l4_success(self, db_session, monkeypatch):
        """L3 降级到 L4 成功：level4_downgraded + level4_success 都记录该种子。"""
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="m")
        _make_downloader(db_session)
        mock_request = _make_mock_request([_make_fake_vo()])

        svc = TorrentDeletionByLevelService(db_session, mock_request)

        # mock _delete_level3 返回降级标记（模拟备份失败）
        async def fake_level3(torrent, operator, audit_service=None):
            return {
                "success": False,
                "downgrade_to_level4": True,
                "torrent_id": torrent.info_id,
                "torrent_name": torrent.name,
                "message": "种子文件备份失败: mock",
            }

        monkeypatch.setattr(svc, "_delete_level3", fake_level3)

        result = await svc.delete_batch_by_level(
            torrent_info_ids=["t1"], delete_level=3, operator="alice", audit_service=AsyncMock()
        )

        assert result["success"] is True, "L4 降级成功，无 failed"
        assert result["total"] == 1
        assert result["level4_downgraded"] == [
            {"torrent_id": "t1", "torrent_name": "m", "reason": "种子文件备份失败: mock"}
        ]
        assert result["level4_success"] == ["t1"]
        assert result["level3_success"] == []
        assert result["failed"] == []
        # L4 真实执行了：DB tags 含 pending_delete
        db_session.expire_all()
        tags = db_session.query(TorrentInfo).filter_by(info_id="t1").first().tags
        assert LEVEL4_TAG in tags

    @pytest.mark.asyncio
    async def test_l3_downgrade_to_l4_also_fails(self, db_session, monkeypatch):
        """L3 降级到 L4 也失败 → 记入 failed，整体 success=False。"""
        make_torrent(db_session, info_id="t1", downloader_id="dl-1", hash_="h1", name="m")
        _make_downloader(db_session)
        # store 返回空缓存 → _get_adapter 失败 → L4 也失败
        mock_request = _make_mock_request([])

        svc = TorrentDeletionByLevelService(db_session, mock_request)

        async def fake_level3(torrent, operator, audit_service=None):
            return {
                "success": False,
                "downgrade_to_level4": True,
                "torrent_id": torrent.info_id,
                "torrent_name": torrent.name,
                "message": "备份失败",
            }

        monkeypatch.setattr(svc, "_delete_level3", fake_level3)

        result = await svc.delete_batch_by_level(
            torrent_info_ids=["t1"], delete_level=3, operator="alice", audit_service=AsyncMock()
        )

        assert result["success"] is False, "L4 也失败 → 整体失败"
        assert len(result["failed"]) == 1
        assert result["failed"][0]["torrent_id"] == "t1"
        assert "降级到等级4也失败" in result["failed"][0]["message"]

    @pytest.mark.asyncio
    async def test_batch_l4_all_success(self, db_session):
        """批量 L4 全成功：多条种子都加标签，level4_success 收齐。"""
        for i in range(3):
            make_torrent(db_session, info_id=f"t{i}", downloader_id="dl-1", hash_=f"h{i}", name=f"m{i}")
        _make_downloader(db_session)
        mock_request = _make_mock_request([_make_fake_vo()])

        svc = TorrentDeletionByLevelService(db_session, mock_request)
        result = await svc.delete_batch_by_level(
            torrent_info_ids=["t0", "t1", "t2"], delete_level=4, audit_service=AsyncMock()
        )

        assert result["success"] is True
        assert result["total"] == 3
        assert sorted(result["level4_success"]) == ["t0", "t1", "t2"]
        assert result["failed"] == []
