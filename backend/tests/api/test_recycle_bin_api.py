# -*- coding: utf-8 -*-
"""
回收站列表查询 GET /api/v1/recycle/bin + POST /recycle/cleanup-preview 的 API 级回归测试

覆盖范围（约 9 个测试）：
- 认证拒绝 / 空数据
- 软删除双过滤（deleted_at IS NOT NULL AND dr=0）—— 写错会把已彻底删除数据显示出来
- search LIKE 搜索
- 排序（deleted_at desc）
- 分页（page/page_size / 超范围）
- 清理预览聚合（时间窗口 deleted_at < cutoff + sum(size)）

关键架构点（经探索确认）：
- RecycleBinService 是同步的，内部 `from app.database import SessionLocal` 自建同步 session
  （不复用端点传入的 async db）。因此测试必须 patch `app.database.SessionLocal` 注入内存库。
- 端点用 get_async_db + get_current_user（需覆盖）。
- 响应 list 元素是 to_dict()（snake_case 字段），有 response_model=CommonResponse。
"""

from datetime import datetime, timedelta
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
from tests.api.conftest import make_torrent

URL_BIN = "/api/v1/recycle/bin"
URL_PREVIEW = "/api/v1/recycle/cleanup-preview"


# ==================== Fixtures ====================


@pytest.fixture
def sync_engine():
    """内存 SQLite engine（StaticPool 单连接），建本接口用到的表。

    回收站只查 TorrentInfo，但 to_dict() 可能引用关联，建 3 张表保险。
    """
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
    """同步 session（注入给 RecycleBinService 自建的 SessionLocal）。"""
    Session = sessionmaker(bind=sync_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """独立 FastAPI app。

    关键：patch app.database.SessionLocal，让 RecycleBinService.__init__ 内的
    `from app.database import SessionLocal; self.db = SessionLocal()` 拿到内存库 session。
    同时覆盖 get_async_db（端点参数）和 get_current_user（认证）。
    """
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")

    with patch("app.database.SessionLocal", return_value=db_session):
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


def _info_ids(body):
    return {item["info_id"] for item in body["data"]["list"]}


# ==================== 组1：认证与空数据 ====================


class TestAuthAndEmpty:
    def test_no_token_returns_401(self, db_session):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        async def override_get_async_db():
            yield db_session

        app.dependency_overrides[get_async_db] = override_get_async_db
        with patch("app.database.SessionLocal", return_value=db_session):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.get(URL_BIN)
        assert r.status_code == 401

    def test_empty_recycle_bin_returns_zero(self, client):
        """空回收站 → total=0, list=[]。"""
        r = client.get(URL_BIN)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0
        assert body["data"]["list"] == []


# ==================== 组2：软删除双过滤（核心） ====================


class TestSoftDeleteFilter:
    """deleted_at IS NOT NULL AND dr=0（只显示可还原的）。

    易错点：dr=1（彻底删除）的记录不应显示；deleted_at=NULL（活跃）的不显示。
    """

    def test_only_recycle_bin_shown(self, client, db_session):
        """只有 deleted_at 非空 + dr=0 的记录出现。"""
        now = datetime(2026, 6, 1, 12, 0, 0)
        # 回收站种子（应显示）
        make_torrent(
            db_session,
            info_id="r1",
            downloader_id="dl-a",
            downloader_name="A",
            hash_="h1",
            name="recycled",
            deleted_at=now,
        )
        # 活跃种子（不应显示）
        make_torrent(db_session, info_id="a1", downloader_id="dl-b", downloader_name="B", hash_="h2", name="active")
        # 彻底删除 dr=1（不应显示）
        make_torrent(
            db_session,
            info_id="d1",
            downloader_id="dl-c",
            downloader_name="C",
            hash_="h3",
            name="deleted",
            dr=1,
            deleted_at=now,
        )

        r = client.get(URL_BIN)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 1
        assert _info_ids(body) == {"r1"}

    def test_dr1_excluded(self, client, db_session):
        """dr=1 即使 deleted_at 非空也被排除（只显示可还原 dr=0）。"""
        now = datetime(2026, 6, 1, 12, 0, 0)
        make_torrent(
            db_session,
            info_id="r1",
            downloader_id="dl-a",
            downloader_name="A",
            hash_="h1",
            name="restoreable",
            deleted_at=now,
            dr=0,
        )
        make_torrent(
            db_session,
            info_id="d1",
            downloader_id="dl-b",
            downloader_name="B",
            hash_="h2",
            name="purged",
            deleted_at=now,
            dr=1,
        )

        r = client.get(URL_BIN)
        body = r.json()
        assert body["data"]["total"] == 1
        assert _info_ids(body) == {"r1"}


# ==================== 组3：搜索 + 排序 + 分页 ====================


class TestSearchSortPaginate:
    def test_search_by_name(self, client, db_session):
        """search 按名称模糊匹配。"""
        now = datetime(2026, 6, 1, 12, 0, 0)
        make_torrent(
            db_session,
            info_id="r1",
            downloader_id="dl-a",
            downloader_name="A",
            hash_="h1",
            name="[movie] film",
            deleted_at=now,
        )
        make_torrent(
            db_session,
            info_id="r2",
            downloader_id="dl-b",
            downloader_name="B",
            hash_="h2",
            name="other thing",
            deleted_at=now,
        )

        r = client.get(URL_BIN, params={"search": "movie"})
        body = r.json()
        assert body["code"] == "200"
        assert _info_ids(body) == {"r1"}

    def test_sort_by_deleted_at_desc(self, client, db_session):
        """按 deleted_at 倒序（最近删除的在前）。"""
        make_torrent(
            db_session,
            info_id="old",
            downloader_id="dl-a",
            downloader_name="A",
            hash_="h1",
            name="t1",
            deleted_at=datetime(2026, 5, 1, 12, 0, 0),
        )
        make_torrent(
            db_session,
            info_id="new",
            downloader_id="dl-b",
            downloader_name="B",
            hash_="h2",
            name="t2",
            deleted_at=datetime(2026, 6, 1, 12, 0, 0),
        )

        r = client.get(URL_BIN)
        body = r.json()
        ids = [item["info_id"] for item in body["data"]["list"]]
        assert ids == ["new", "old"], "最近删除的应在前面（deleted_at desc）"

    def test_pagination_page_size(self, client, db_session):
        """3 条回收站记录，page_size=2 → 第1页 2 条, total=3。"""
        for i in range(3):
            make_torrent(
                db_session,
                info_id=f"r{i}",
                downloader_id=f"dl-{i}",
                downloader_name=f"D{i}",
                hash_=f"h{i}",
                name=f"t{i}",
                deleted_at=datetime(2026, 6, i + 1, 12, 0, 0),
            )

        r = client.get(URL_BIN, params={"page": 1, "page_size": 2})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 3
        assert len(body["data"]["list"]) == 2

    def test_pagination_out_of_range(self, client, db_session):
        """超范围 page → list=[] 但 total 正确。"""
        now = datetime(2026, 6, 1, 12, 0, 0)
        make_torrent(
            db_session, info_id="r1", downloader_id="dl-a", downloader_name="A", hash_="h1", name="t1", deleted_at=now
        )

        r = client.get(URL_BIN, params={"page": 99, "page_size": 20})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 1
        assert body["data"]["list"] == []


# ==================== 组4：清理预览聚合 ====================


class TestCleanupPreview:
    """cleanup_preview: deleted_at < cutoff（严格小于）+ dr=0，sum(size)。"""

    def test_old_records_previewed(self, client, db_session):
        """days=30 → deleted_at 在 30 天前的记录被预览，最近的不含。"""
        long_ago = datetime.now() - timedelta(days=60)  # 60天前（应命中）
        recent = datetime.now() - timedelta(days=5)  # 5天前（应排除）

        make_torrent(
            db_session,
            info_id="old",
            downloader_id="dl-a",
            downloader_name="A",
            hash_="h1",
            name="old1",
            size=500,
            deleted_at=long_ago,
        )
        make_torrent(
            db_session,
            info_id="new",
            downloader_id="dl-b",
            downloader_name="B",
            hash_="h2",
            name="new1",
            size=300,
            deleted_at=recent,
        )

        r = client.post(URL_PREVIEW, json={"days": 30})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total_count"] == 1
        assert body["data"]["total_size"] == 500
        assert body["data"]["torrent_list"][0]["info_id"] == "old"

    def test_cleanup_preview_excludes_dr1(self, client, db_session):
        """dr=1 的记录不进预览（即使 deleted_at 很旧）。"""
        long_ago = datetime.now() - timedelta(days=60)
        make_torrent(
            db_session,
            info_id="r1",
            downloader_id="dl-a",
            downloader_name="A",
            hash_="h1",
            name="restoreable",
            size=100,
            deleted_at=long_ago,
            dr=0,
        )
        make_torrent(
            db_session,
            info_id="d1",
            downloader_id="dl-b",
            downloader_name="B",
            hash_="h2",
            name="purged",
            size=200,
            deleted_at=long_ago,
            dr=1,
        )

        r = client.post(URL_PREVIEW, json={"days": 30})
        body = r.json()
        assert body["data"]["total_count"] == 1
        assert body["data"]["total_size"] == 100  # 只有 dr=0 的 r1

    def test_cleanup_preview_size_none_degraded_to_zero(self, client, db_session):
        """size 为 None 的记录累加降级为 0（sum(t.size or 0)）。"""
        long_ago = datetime.now() - timedelta(days=60)
        # 构造 size=None 的回收站记录（直接设列，绕过工厂默认 0）
        added = datetime(2026, 1, 1, 12, 0, 0)
        t = TorrentInfo(
            "s1",
            "dl-a",
            "A",
            None,
            "h1",
            "null_size",
            "/p",
            None,
            "seeding",
            0.0,
            None,
            added,
            None,
            "0",
            "0",
            "",
            "",
            "否",
            True,
            added,
            "tester",
            added,
            "tester",
            0,
        )
        t.has_tracker_error = False
        t.deleted_at = long_ago
        db_session.add(t)
        db_session.commit()

        r = client.post(URL_PREVIEW, json={"days": 30})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total_count"] == 1
        assert body["data"]["total_size"] == 0, "size=None 应降级为 0 而非报错"


class TestParamValidation:
    """cleanup-preview 的 days 参数 422 边界（Pydantic Field ge=1 le=365）。"""

    def test_days_zero_returns_422(self, client):
        """days=0 → 422（ge=1）。"""
        r = client.post(URL_PREVIEW, json={"days": 0})
        assert r.status_code == 422

    def test_days_over_limit_returns_422(self, client):
        """days=366 → 422（le=365）。"""
        r = client.post(URL_PREVIEW, json={"days": 366})
        assert r.status_code == 422
