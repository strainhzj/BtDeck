# -*- coding: utf-8 -*-
"""
快捷删除重复种子接口 POST /api/v1/torrents/duplicates/quick-delete[-preview] 的回归测试

覆盖范围：
- 参数校验（待检测 <2 / 保留空 / 保留非子集 → 400）
- 预览分类（跨下载器重复 kept/to_delete / skipped 组 / 唯一 hash 排除 / dr 过滤 / hash 大小写归一）
- 分页（list 分页 + 全量汇总不受分页影响）
- 执行端点（提交任务返回 task_id / 无候选返回空任务）

范式照搬 tests/api/test_duplicate_torrents_api.py：独立 FastAPI app + 内存 StaticPool SQLite +
指定表建表 + 依赖覆盖（get_db + require_authenticated_user）。
"""

from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.deletion_task_manager as manager_module
from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.services.deletion_task_manager import DeletionTaskManager
from app.torrents.models import TorrentInfo
from tests.api.conftest import make_torrent

PREVIEW_URL = "/api/v1/torrents/duplicates/quick-delete-preview"
EXECUTE_URL = "/api/v1/torrents/duplicates/quick-delete"


@pytest.fixture(autouse=True)
def isolated_deletion_manager(monkeypatch):
    """隔离模块单例，并避免测试创建长期清理协程。"""
    original_manager = manager_module._manager
    original_instance = DeletionTaskManager._instance
    monkeypatch.setattr(DeletionTaskManager, "_start_cleanup_task", lambda self: None)
    manager_module._manager = None
    DeletionTaskManager._instance = None
    try:
        yield manager_module.get_deletion_task_manager()
    finally:
        manager_module._manager = original_manager
        DeletionTaskManager._instance = original_instance


@pytest.fixture
def db_session():
    """内存 SQLite（StaticPool 复用单连接），只建本接口用到的 TorrentInfo 表。"""
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


@pytest.fixture
def client(db_session):
    """独立 FastAPI app，覆盖 get_db 指向内存库 + require_authenticated_user 绕过 JWT。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestValidation:
    """参数校验（400）。"""

    def test_less_than_two_downloaders(self, client):
        r = client.post(
            PREVIEW_URL, json={"downloader_ids": ["dl-a"], "keep_downloader_ids": ["dl-a"]}
        )
        assert r.status_code == 400

    def test_empty_keep_downloaders(self, client):
        r = client.post(
            PREVIEW_URL, json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": []}
        )
        assert r.status_code == 400

    def test_keep_not_subset_of_detect(self, client):
        r = client.post(
            PREVIEW_URL,
            json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-c"]},
        )
        assert r.status_code == 400


class TestPreviewClassification:
    """跨下载器重复分类。"""

    def test_kept_to_delete_classification(self, client, db_session):
        make_torrent(db_session, info_id="a1", downloader_id="dl-a", downloader_name="A", hash_="aaa", name="n1")
        make_torrent(db_session, info_id="b1", downloader_id="dl-b", downloader_name="B", hash_="aaa", name="n2")
        r = client.post(
            PREVIEW_URL,
            json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-b"], "page": 1, "pageSize": 20},
        )
        body = r.json()
        assert body["code"] == "200"
        data = body["data"]
        assert data["total_groups"] == 1
        assert data["total_delete"] == 1
        assert data["skipped_groups"] == 0
        group = data["list"][0]
        assert group["skipped"] is False
        # 待删 = dl-a，保留 = dl-b
        assert [it["downloader_id"] for it in group["to_delete"]] == ["dl-a"]
        assert [it["downloader_id"] for it in group["kept"]] == ["dl-b"]
        assert group["name"] == "n1"
        assert group["hash"] == "aaa"

    def test_multi_keep_multi_delete(self, client, db_session):
        """4 下载器场景：保留 dl-a/dl-c，删除 dl-b/dl-d。"""
        for dl, dn in [("dl-a", "A"), ("dl-b", "B"), ("dl-c", "C"), ("dl-d", "D")]:
            make_torrent(db_session, info_id=dl, downloader_id=dl, downloader_name=dn, hash_="aaa", name="dup")
        r = client.post(
            PREVIEW_URL,
            json={
                "downloader_ids": ["dl-a", "dl-b", "dl-c", "dl-d"],
                "keep_downloader_ids": ["dl-a", "dl-c"],
                "page": 1,
                "pageSize": 20,
            },
        )
        body = r.json()
        assert body["code"] == "200"
        data = body["data"]
        assert data["total_groups"] == 1
        assert data["total_delete"] == 2
        group = data["list"][0]
        assert sorted(it["downloader_id"] for it in group["kept"]) == ["dl-a", "dl-c"]
        assert sorted(it["downloader_id"] for it in group["to_delete"]) == ["dl-b", "dl-d"]

    def test_skipped_group_when_no_keep_copy(self, client, db_session):
        """hash 仅在待删下载器间重复、保留集合无副本 → skipped，不计入删除。"""
        # "ccc" 只在 dl-a / dl-b，保留 dl-c（无 ccc 副本）
        make_torrent(db_session, info_id="a2", downloader_id="dl-a", downloader_name="A", hash_="ccc", name="x")
        make_torrent(db_session, info_id="b2", downloader_id="dl-b", downloader_name="B", hash_="ccc", name="y")
        # 同时构造一个正常组 "ddd"，保证 total_groups 区分
        make_torrent(db_session, info_id="a3", downloader_id="dl-a", downloader_name="A", hash_="ddd", name="p")
        make_torrent(db_session, info_id="c3", downloader_id="dl-c", downloader_name="C", hash_="ddd", name="q")
        r = client.post(
            PREVIEW_URL,
            json={
                "downloader_ids": ["dl-a", "dl-b", "dl-c"],
                "keep_downloader_ids": ["dl-c"],
                "page": 1,
                "pageSize": 20,
            },
        )
        body = r.json()
        assert body["code"] == "200"
        data = body["data"]
        assert data["total_groups"] == 2
        assert data["skipped_groups"] == 1
        assert data["total_delete"] == 1  # 仅 ddd 的 dl-a 副本
        by_hash = {g["hash"]: g for g in data["list"]}
        assert by_hash["ccc"]["skipped"] is True
        # skipped 组不产生删除候选（不计入 total_delete），但保留明细供前端提示展示
        assert len(by_hash["ccc"]["kept"]) == 0
        assert len(by_hash["ccc"]["to_delete"]) == 2
        assert by_hash["ddd"]["skipped"] is False

    def test_unique_hash_excluded(self, client, db_session):
        make_torrent(db_session, info_id="u1", downloader_id="dl-a", downloader_name="A", hash_="unique1", name="t")
        r = client.post(
            PREVIEW_URL,
            json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-b"], "page": 1, "pageSize": 20},
        )
        data = r.json()["data"]
        assert data["total_groups"] == 0
        assert data["total_delete"] == 0
        assert data["list"] == []

    def test_dr_deleted_excluded(self, client, db_session):
        """dr=1（已逻辑删除）的种子不参与重复。"""
        make_torrent(db_session, info_id="d1", downloader_id="dl-a", downloader_name="A", hash_="ddd", name="t", dr=1)
        make_torrent(db_session, info_id="d2", downloader_id="dl-b", downloader_name="B", hash_="ddd", name="t")
        r = client.post(
            PREVIEW_URL,
            json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-b"], "page": 1, "pageSize": 20},
        )
        data = r.json()["data"]
        # dl-a 的记录已逻辑删除，只剩 dl-b 一条 → 不构成跨下载器重复
        assert data["total_groups"] == 0

    def test_hash_case_normalized(self, client, db_session):
        """hash 大小写/空白不一致仍归为同一组。"""
        make_torrent(db_session, info_id="c1", downloader_id="dl-a", downloader_name="A", hash_="AbC", name="t")
        make_torrent(db_session, info_id="c2", downloader_id="dl-b", downloader_name="B", hash_="  abc ", name="t")
        r = client.post(
            PREVIEW_URL,
            json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-b"], "page": 1, "pageSize": 20},
        )
        data = r.json()["data"]
        assert data["total_groups"] == 1
        assert data["list"][0]["hash"] == "abc"


class TestPreviewPagination:
    """list 分页 + 全量汇总不受分页影响。"""

    def _seed_three_groups(self, db):
        for idx in range(3):
            h = f"h{idx}"
            make_torrent(db, info_id=f"a{idx}", downloader_id="dl-a", downloader_name="A", hash_=h, name=f"n{idx}")
            make_torrent(db, info_id=f"b{idx}", downloader_id="dl-b", downloader_name="B", hash_=h, name=f"n{idx}")

    def test_global_summary_independent_of_page(self, client, db_session):
        self._seed_three_groups(db_session)
        r = client.post(
            PREVIEW_URL,
            json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-b"], "page": 1, "pageSize": 1},
        )
        data = r.json()["data"]
        assert data["total"] == 3
        assert data["total_groups"] == 3
        assert data["total_delete"] == 3
        assert len(data["list"]) == 1  # 只返回当前页


class TestExecute:
    """执行端点。"""

    def test_submit_task_returns_task_id(self, client, db_session):
        make_torrent(db_session, info_id="e1", downloader_id="dl-a", downloader_name="A", hash_="aaa", name="t")
        make_torrent(db_session, info_id="e2", downloader_id="dl-b", downloader_name="B", hash_="aaa", name="t")
        with patch(
            "app.services.async_deletion_executor.AsyncDeletionExecutor.execute_deletion_task",
            new_callable=AsyncMock,
        ):
            r = client.post(
                EXECUTE_URL,
                json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-b"], "delete_level": 2},
            )
        body = r.json()
        assert body["code"] == "200"
        data = body["data"]
        assert data["task_id"]
        assert data["total_count"] == 1
        assert data["delete_level"] == 2

    def test_no_candidates_returns_empty_task(self, client, db_session):
        make_torrent(db_session, info_id="e3", downloader_id="dl-a", downloader_name="A", hash_="unique", name="t")
        r = client.post(
            EXECUTE_URL,
            json={"downloader_ids": ["dl-a", "dl-b"], "keep_downloader_ids": ["dl-b"], "delete_level": 2},
        )
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["task_id"] is None
        assert body["data"]["total_count"] == 0

    def test_repeat_preview_hides_active_item_and_execute_skips_duplicate(self, client, db_session):
        make_torrent(db_session, info_id="e4", downloader_id="dl-a", downloader_name="A", hash_="same", name="t")
        make_torrent(db_session, info_id="e5", downloader_id="dl-b", downloader_name="B", hash_="same", name="t")
        payload = {
            "downloader_ids": ["dl-a", "dl-b"],
            "keep_downloader_ids": ["dl-b"],
            "delete_level": 2,
        }
        with patch(
            "app.services.async_deletion_executor.AsyncDeletionExecutor.execute_deletion_task",
            new_callable=AsyncMock,
        ):
            first = client.post(EXECUTE_URL, json=payload).json()["data"]
            preview = client.post(
                PREVIEW_URL,
                json={
                    "downloader_ids": payload["downloader_ids"],
                    "keep_downloader_ids": payload["keep_downloader_ids"],
                },
            ).json()["data"]
            repeated = client.post(EXECUTE_URL, json=payload).json()["data"]

        assert first["task_id"]
        assert preview["total_delete"] == 0
        assert repeated["task_id"] is None
        assert repeated["accepted_count"] == 0
        assert repeated["skipped_count"] == 1

    def test_mixed_repeat_accepts_only_new_candidate(self, client, db_session):
        make_torrent(db_session, info_id="old-delete", downloader_id="dl-a", hash_="old", name="old")
        make_torrent(db_session, info_id="old-keep", downloader_id="dl-b", hash_="old", name="old")
        payload = {
            "downloader_ids": ["dl-a", "dl-b"],
            "keep_downloader_ids": ["dl-b"],
            "delete_level": 2,
        }
        with patch(
            "app.services.async_deletion_executor.AsyncDeletionExecutor.execute_deletion_task",
            new_callable=AsyncMock,
        ):
            first = client.post(EXECUTE_URL, json=payload).json()["data"]
            make_torrent(db_session, info_id="new-delete", downloader_id="dl-a", hash_="new", name="new")
            make_torrent(db_session, info_id="new-keep", downloader_id="dl-b", hash_="new", name="new")
            mixed = client.post(EXECUTE_URL, json=payload).json()["data"]

        assert first["accepted_count"] == 1
        assert mixed["task_id"]
        assert mixed["requested_count"] == 2
        assert mixed["accepted_count"] == 1
        assert mixed["skipped_count"] == 1
