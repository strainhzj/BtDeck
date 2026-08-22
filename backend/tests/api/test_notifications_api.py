# -*- coding: utf-8 -*-
"""
通知中心 API 回归测试

覆盖端点：
- GET  /api/v1/notifications          列表查询（type/is_read 双过滤 + 分页）
- GET  /api/v1/notifications/unread-count  未读计数
- PUT  /api/v1/notifications/read-all 全部已读
- PUT  /api/v1/notifications/mark-read?notification_id=N   标记已读（Query 参数）
- PUT  /api/v1/notifications/mark-unread?notification_id=N 标记未读
- DELETE /api/v1/notifications/{id}   删除

关键架构点（经探索确认）：
- NotificationService 是异步的，用传入的 AsyncSession（不像回收站自建同步 session）。
  → 测试用 aiosqlite 异步内存库 + AsyncSession，覆盖 get_async_db。
- 标记/删除返回 bool（靠 rowcount>0 判断存在性），端点据此返回 code='200' 或 '404'。
- Notification 模型 id 自增，type/title/content/priority/is_read 关键字构造。
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.api.api import api_router
from app.auth.dependencies import get_current_user
from app.database import Base, get_async_db
from app.models.notification import Notification

URL_LIST = "/api/v1/notifications"
URL_UNREAD = "/api/v1/notifications/unread-count"
URL_READ_ALL = "/api/v1/notifications/read-all"


# ==================== Fixtures ====================

@pytest.fixture
async def async_db():
    """异步内存 SQLite（aiosqlite + StaticPool 单连接）+ 建表。

    StaticPool 复用单连接，使同一 test 内多个 AsyncSession 操作看到同一份数据。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[Notification.__table__]
        ))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(
                c, tables=[Notification.__table__]
            ))


@pytest.fixture
def client(async_db):
    """独立 FastAPI app，覆盖 get_async_db + get_current_user。"""
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    async def override_get_async_db():
        yield async_db

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


async def _add(async_db, **kwargs):
    """添加一条通知并提交。"""
    n = Notification(**kwargs)
    async_db.add(n)
    await async_db.commit()
    await async_db.refresh(n)
    return n


def _ids(body):
    return {item["id"] for item in body["data"]["list"]}


# ==================== 组1：认证与空数据 ====================

class TestAuthAndEmpty:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, async_db):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        async def override_get_async_db():
            yield async_db

        app.dependency_overrides[get_async_db] = override_get_async_db
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get(URL_LIST)
        assert r.status_code == 401

    def test_empty_list_returns_zero(self, client):
        r = client.get(URL_LIST)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0
        assert body["data"]["list"] == []


# ==================== 组2：列表查询与过滤 ====================

class TestListQuery:
    @pytest.mark.asyncio
    async def test_list_returns_all(self, client, async_db):
        """列表返回全部通知（按 created_at desc）。"""
        await _add(async_db, type="system", title="t1")
        await _add(async_db, type="version_update", title="t2")
        r = client.get(URL_LIST)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 2

    @pytest.mark.asyncio
    async def test_filter_by_type(self, client, async_db):
        """type 过滤：只返回指定类型。"""
        await _add(async_db, type="system", title="sys")
        await _add(async_db, type="version_update", title="ver")
        r = client.get(URL_LIST, params={"type": "version_update"})
        body = r.json()
        assert body["code"] == "200"
        titles = {item["title"] for item in body["data"]["list"]}
        assert titles == {"ver"}

    @pytest.mark.asyncio
    async def test_filter_by_is_read(self, client, async_db):
        """is_read 过滤：只返回未读。"""
        await _add(async_db, type="system", title="unread", is_read=False)
        await _add(async_db, type="system", title="read", is_read=True)
        r = client.get(URL_LIST, params={"is_read": False})
        body = r.json()
        assert body["code"] == "200"
        titles = {item["title"] for item in body["data"]["list"]}
        assert titles == {"unread"}, "is_read=False 应只返回未读通知"

    @pytest.mark.asyncio
    async def test_pagination(self, client, async_db):
        """3 条，pageSize=2 → 第1页 2 条, total=3。"""
        for i in range(3):
            await _add(async_db, type="system", title=f"t{i}")
        r = client.get(URL_LIST, params={"page": 1, "pageSize": 2})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 3
        assert len(body["data"]["list"]) == 2

    def test_datetime_serialization_marks_database_utc_values(self):
        """Naive UTC database values must not be parsed as browser-local time."""
        notification = Notification(
            type="system",
            title="time",
            created_at=datetime(2026, 8, 1, 12, 0, 0),
            read_at=datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone(timedelta(hours=8))),
        )

        result = notification.to_dict()

        assert result["created_at"] == "2026-08-01T12:00:00Z"
        assert result["read_at"] == "2026-08-01T12:00:00Z"


# ==================== 组3：未读计数 ====================

class TestUnreadCount:
    @pytest.mark.asyncio
    async def test_unread_count(self, client, async_db):
        """未读计数 = is_read=False 的数量。"""
        await _add(async_db, type="system", title="u1", is_read=False)
        await _add(async_db, type="system", title="u2", is_read=False)
        await _add(async_db, type="system", title="r1", is_read=True)
        r = client.get(URL_UNREAD)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["count"] == 2


# ==================== 组4：标记已读/未读（rowcount 存在性判断） ====================

class TestMarkReadUnread:
    """标记操作靠 rowcount>0 判断存在性：不存在返回 code='404'。"""

    @pytest.mark.asyncio
    async def test_mark_read_existing(self, client, async_db):
        """存在的通知标记已读 → code='200'。"""
        n = await _add(async_db, type="system", title="t1", is_read=False)
        r = client.put("/api/v1/notifications/mark-read", params={"notification_id": n.id})
        body = r.json()
        assert body["code"] == "200"
        # 验证 DB 状态已变
        refreshed = await async_db.get(Notification, n.id)
        assert refreshed.is_read is True
        assert refreshed.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_read_nonexistent_returns_404(self, client):
        """不存在的 notification_id → code='404'（rowcount=0）。"""
        r = client.put("/api/v1/notifications/mark-read", params={"notification_id": 9999})
        body = r.json()
        assert body["code"] == "404"

    def test_mark_read_missing_id_returns_422(self, client):
        """mark-read 不传 notification_id → 422（Query(..., 必填)）。"""
        r = client.put("/api/v1/notifications/mark-read")
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_mark_unread_existing(self, client, async_db):
        """标记未读 → is_read=False, read_at=None。"""
        n = await _add(async_db, type="system", title="t1", is_read=True)
        r = client.put("/api/v1/notifications/mark-unread", params={"notification_id": n.id})
        body = r.json()
        assert body["code"] == "200"
        refreshed = await async_db.get(Notification, n.id)
        assert refreshed.is_read is False
        assert refreshed.read_at is None

    @pytest.mark.asyncio
    async def test_mark_all_as_read(self, client, async_db):
        """全部已读：返回被更新的行数（仅原本未读的）。"""
        await _add(async_db, type="system", title="u1", is_read=False)
        await _add(async_db, type="system", title="u2", is_read=False)
        await _add(async_db, type="system", title="r1", is_read=True)  # 已读，不会被更新
        r = client.put(URL_READ_ALL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["count"] == 2, "只更新原本未读的 2 条"

    def test_mark_all_as_read_empty_table_returns_zero(self, client):
        """空表全部已读 → count=0（无未读记录可更新）。"""
        r = client.put(URL_READ_ALL)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["count"] == 0


# ==================== 组5：删除 ====================

class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_existing(self, client, async_db):
        n = await _add(async_db, type="system", title="t1")
        r = client.delete(f"/api/v1/notifications/{n.id}")
        body = r.json()
        assert body["code"] == "200"
        # 确认已删除
        refreshed = await async_db.get(Notification, n.id)
        assert refreshed is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        r = client.delete("/api/v1/notifications/9999")
        body = r.json()
        assert body["code"] == "404"
