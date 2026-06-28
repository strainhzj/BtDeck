# -*- coding: utf-8 -*-
"""
审计日志查询 POST /api/v1/audit-logs/query + GET /statistics + GET /operation-types 的 API 级回归测试

覆盖范围（约 24 个测试）：
- 认证拒绝 / 空数据
- 11 维过滤（含 torrent_name LIKE 模糊搜索——唯一非精确匹配维度）
- 时间范围（start_time / end_time）
- 子查询 count + 排序（operation_time DESC）
- 分页（page/page_size / 超范围 / page_size 边界 422）
- statistics 内存聚合（operation_type/operator/result 统计 + unknown 桶）
- operation-types 枚举展开（39 个成员）
- 错误降级（坏 ISO 时间 → code='400'，HTTP 仍 200）

关键架构点（经探索确认）：
- AuditLogService 是异步的，用传入的 AsyncSession（依赖注入式，非自建 SessionLocal）。
  → 用 aiosqlite 异步内存库 + AsyncSession，覆盖 get_async_db。
- 所有 JSON 错误返回 HTTP 200，code='400'/'500' 写在 CommonResponse 体里（只 download-export 抛 HTTPException）。
- 响应 data 分页字段混用大小写：total/page（小写）vs pageSize（驼峰）——这是 load-bearing 断言点。
- service 不抛异常：query_logs/get_statistics 出错返回空结构，不向上传播。
- operation_time/create_time 经 to_dict() 是裸 datetime（FastAPI 序列化为 ISO 字符串）。
"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace

from app.api.api import api_router
from app.auth.dependencies import get_current_user
from app.database import Base, get_async_db
from app.torrents.audit_enums import AuditOperationType
from app.torrents.audit_models import TorrentAuditLog

URL_QUERY = "/api/v1/audit-logs/query"
URL_STATS = "/api/v1/audit-logs/statistics"
URL_OP_TYPES = "/api/v1/audit-logs/operation-types"


# ==================== Fixtures ====================


@pytest.fixture
async def async_db():
    """异步内存 SQLite（aiosqlite + StaticPool 单连接），建 torrent_audit_log 表。

    StaticPool 复用单连接，使同测试内多个 AsyncSession 操作看到同一份数据。
    """
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
    """添加一条审计日志并提交。

    operation_time / create_time 默认由模型 __init__ 填 datetime.now()，
    传 operation_time= 可显式指定（排序/时间过滤测试需要）。
    """
    log = TorrentAuditLog(**kwargs)
    async_db.add(log)
    await async_db.commit()
    await async_db.refresh(log)
    return log


def _types(body):
    return {item["operation_type"] for item in body["data"]["list"]}


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
            r = c.post(URL_QUERY, json={})
        assert r.status_code == 401

    def test_empty_logs_returns_zero(self, client):
        """空表 → total=0, list=[]。"""
        r = client.post(URL_QUERY, json={})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0
        assert body["data"]["list"] == []

    def test_default_page_and_pagesize(self, client):
        """不传 page/page_size → 默认 page=1, pageSize=20。"""
        r = client.post(URL_QUERY, json={})
        body = r.json()
        assert body["data"]["page"] == 1
        assert body["data"]["pageSize"] == 20, "pageSize 是驼峰键名（非 page_size）"


# ==================== 组2：11 维过滤（核心） ====================


class TestFilters:
    """11 维过滤条件。torrent_name 用 LIKE 模糊匹配，其余 10 维都是精确 ==。"""

    @pytest.mark.asyncio
    async def test_filter_by_torrent_info_id(self, client, async_db):
        await _add(async_db, torrent_info_id="t1", operation_type="add", operator="alice")
        await _add(async_db, torrent_info_id="t2", operation_type="add", operator="alice")
        r = client.post(URL_QUERY, json={"torrent_info_id": "t1"})
        body = r.json()
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["torrent_info_id"] == "t1"

    @pytest.mark.asyncio
    async def test_filter_by_torrent_name_fuzzy(self, client, async_db):
        """torrent_name 是唯一 LIKE 维度（%...%）。"""
        await _add(async_db, torrent_name="[movie] inception 2024", operator="a")
        await _add(async_db, torrent_name="other thing", operator="a")
        # 子串匹配
        r = client.post(URL_QUERY, json={"torrent_name": "inception"})
        body = r.json()
        assert body["data"]["total"] == 1
        assert "inception" in body["data"]["list"][0]["torrent_name"]
        # 前缀子串也匹配
        r2 = client.post(URL_QUERY, json={"torrent_name": "movie"})
        assert r2.json()["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_filter_by_torrent_name_exact_does_not_match(self, client, async_db):
        """LIKE 是子串匹配，完整字符串 != 必要——传完整名也命中（子串之一）。"""
        await _add(async_db, torrent_name="hello world", operator="a")
        r = client.post(URL_QUERY, json={"torrent_name": "hello world"})
        assert r.json()["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_filter_by_operation_type(self, client, async_db):
        await _add(async_db, operation_type="add", operator="a")
        await _add(async_db, operation_type="pause", operator="a")
        r = client.post(URL_QUERY, json={"operation_type": "pause"})
        assert _types(r.json()) == {"pause"}

    @pytest.mark.asyncio
    async def test_filter_by_operator(self, client, async_db):
        await _add(async_db, operator="alice", operation_type="add")
        await _add(async_db, operator="bob", operation_type="add")
        r = client.post(URL_QUERY, json={"operator": "bob"})
        body = r.json()
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["operator"] == "bob"

    @pytest.mark.asyncio
    async def test_filter_by_downloader_id(self, client, async_db):
        await _add(async_db, downloader_id="dl-1", operation_type="add")
        await _add(async_db, downloader_id="dl-2", operation_type="add")
        r = client.post(URL_QUERY, json={"downloader_id": "dl-1"})
        assert r.json()["data"]["list"][0]["downloader_id"] == "dl-1"

    @pytest.mark.asyncio
    async def test_filter_by_operation_result(self, client, async_db):
        await _add(async_db, operation_result="success", operation_type="add")
        await _add(async_db, operation_result="failed", operation_type="add")
        r = client.post(URL_QUERY, json={"operation_result": "failed"})
        body = r.json()
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["operation_result"] == "failed"

    @pytest.mark.asyncio
    async def test_filter_by_ip_address(self, client, async_db):
        await _add(async_db, ip_address="10.0.0.1", operation_type="add")
        await _add(async_db, ip_address="10.0.0.2", operation_type="add")
        r = client.post(URL_QUERY, json={"ip_address": "10.0.0.1"})
        assert r.json()["data"]["list"][0]["ip_address"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_filter_by_request_id(self, client, async_db):
        await _add(async_db, request_id="req-aaa", operation_type="add")
        await _add(async_db, request_id="req-bbb", operation_type="add")
        r = client.post(URL_QUERY, json={"request_id": "req-bbb"})
        body = r.json()
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["request_id"] == "req-bbb"

    @pytest.mark.asyncio
    async def test_filter_by_session_id(self, client, async_db):
        await _add(async_db, session_id="sess-1", operation_type="add")
        await _add(async_db, session_id="sess-2", operation_type="add")
        r = client.post(URL_QUERY, json={"session_id": "sess-2"})
        body = r.json()
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["session_id"] == "sess-2"


# ==================== 组3：时间范围过滤 ====================


class TestTimeRange:
    @pytest.mark.asyncio
    async def test_filter_by_start_time(self, client, async_db):
        """operation_time >= start_time。"""
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 6, 1, 12, 0, 0))
        r = client.post(URL_QUERY, json={"start_time": "2026-03-01T00:00:00"})
        body = r.json()
        assert body["data"]["total"] == 1, "只有 6 月的 >= 3 月"

    @pytest.mark.asyncio
    async def test_filter_by_end_time(self, client, async_db):
        """operation_time <= end_time。"""
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 6, 1, 12, 0, 0))
        r = client.post(URL_QUERY, json={"end_time": "2026-03-01T00:00:00"})
        body = r.json()
        assert body["data"]["total"] == 1, "只有 1 月的 <= 3 月"

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self, client, async_db):
        """start_time AND end_time 闭区间。"""
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 6, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 12, 1, 12, 0, 0))
        r = client.post(
            URL_QUERY,
            json={
                "start_time": "2026-03-01T00:00:00",
                "end_time": "2026-09-01T00:00:00",
            },
        )
        body = r.json()
        assert body["data"]["total"] == 1


# ==================== 组4：排序 + 分页 ====================


class TestSortAndPaginate:
    @pytest.mark.asyncio
    async def test_sort_by_operation_time_desc(self, client, async_db):
        """按 operation_time 倒序（最近的在前）。"""
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 6, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 3, 1, 12, 0, 0))
        r = client.post(URL_QUERY, json={})
        body = r.json()
        times = [item["operation_time"] for item in body["data"]["list"]]
        assert times[0] > times[-1], "倒序：第一个应在最后之后"

    @pytest.mark.asyncio
    async def test_pagination_first_page(self, client, async_db):
        """3 条，page_size=2 → 第1页 2 条, total=3。"""
        for i in range(3):
            await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, i + 1, 12, 0, 0))
        r = client.post(URL_QUERY, json={"page": 1, "page_size": 2})
        body = r.json()
        assert body["data"]["total"] == 3
        assert len(body["data"]["list"]) == 2
        assert body["data"]["page"] == 1
        assert body["data"]["pageSize"] == 2

    @pytest.mark.asyncio
    async def test_pagination_second_page(self, client, async_db):
        """3 条，page_size=2 → 第2页只剩 1 条。"""
        for i in range(3):
            await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, i + 1, 12, 0, 0))
        r = client.post(URL_QUERY, json={"page": 2, "page_size": 2})
        body = r.json()
        assert body["data"]["total"] == 3
        assert len(body["data"]["list"]) == 1

    @pytest.mark.asyncio
    async def test_pagination_out_of_range(self, client, async_db):
        """超范围 page → list=[] 但 total 正确。"""
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, 1, 12, 0, 0))
        r = client.post(URL_QUERY, json={"page": 99, "page_size": 20})
        body = r.json()
        assert body["data"]["total"] == 1
        assert body["data"]["list"] == []

    def test_page_size_over_limit_returns_422(self, client):
        """page_size=101 → 422（le=100）。"""
        r = client.post(URL_QUERY, json={"page": 1, "page_size": 101})
        assert r.status_code == 422

    def test_page_zero_returns_422(self, client):
        """page=0 → 422（ge=1）。"""
        r = client.post(URL_QUERY, json={"page": 0, "page_size": 20})
        assert r.status_code == 422


# ==================== 组5：多维度组合 + count 子查询正确性 ====================


class TestCombinedFilter:
    @pytest.mark.asyncio
    async def test_multi_filter_combined(self, client, async_db):
        """多维度 AND 组合：operator + operation_type + operation_result。"""
        await _add(
            async_db,
            operator="alice",
            operation_type="add",
            operation_result="success",
            operation_time=datetime(2026, 6, 1),
        )
        await _add(
            async_db,
            operator="alice",
            operation_type="add",
            operation_result="failed",
            operation_time=datetime(2026, 6, 2),
        )
        await _add(
            async_db,
            operator="bob",
            operation_type="add",
            operation_result="success",
            operation_time=datetime(2026, 6, 3),
        )
        r = client.post(
            URL_QUERY,
            json={
                "operator": "alice",
                "operation_type": "add",
                "operation_result": "success",
            },
        )
        body = r.json()
        assert body["data"]["total"] == 1
        assert body["data"]["list"][0]["operator"] == "alice"

    @pytest.mark.asyncio
    async def test_count_independent_of_pagination(self, client, async_db):
        """子查询 count 反映全部匹配数，不受 page_size 影响。

        这是 query_logs 的关键正确性点：count 用 select(func.count()).select_from(query.subquery())，
        必须与 limit/offset 解耦。
        """
        for i in range(5):
            await _add(async_db, operator="alice", operation_type="add", operation_time=datetime(2026, 1, i + 1))
        r = client.post(URL_QUERY, json={"operator": "alice", "page": 1, "page_size": 2})
        body = r.json()
        assert body["data"]["total"] == 5, "count 必须是 5（全部匹配），不是 2（page_size）"
        assert len(body["data"]["list"]) == 2


# ==================== 组6：statistics 内存聚合 ====================


class TestStatistics:
    def test_empty_stats(self, client):
        """空表 → total_count=0, 三个统计字典均为空。"""
        r = client.get(URL_STATS)
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total_count"] == 0
        assert body["data"]["operation_type_stats"] == {}
        assert body["data"]["operator_stats"] == {}
        assert body["data"]["result_stats"] == {}

    @pytest.mark.asyncio
    async def test_stats_aggregation(self, client, async_db):
        """按 operation_type / operator / operation_result 内存计数。"""
        await _add(async_db, operation_type="add", operator="alice", operation_result="success")
        await _add(async_db, operation_type="add", operator="alice", operation_result="success")
        await _add(async_db, operation_type="pause", operator="bob", operation_result="failed")
        r = client.get(URL_STATS)
        body = r.json()
        assert body["data"]["total_count"] == 3
        assert body["data"]["operation_type_stats"] == {"add": 2, "pause": 1}
        assert body["data"]["operator_stats"] == {"alice": 2, "bob": 1}
        assert body["data"]["result_stats"] == {"success": 2, "failed": 1}

    @pytest.mark.asyncio
    async def test_stats_null_fields_bucketed_as_unknown(self, client, async_db):
        """operation_type/operator/operation_result 为 None → 落入 "unknown" 桶。"""
        await _add(async_db)  # 三字段全 None
        r = client.get(URL_STATS)
        body = r.json()
        assert body["data"]["total_count"] == 1
        assert body["data"]["operation_type_stats"] == {"unknown": 1}
        assert body["data"]["operator_stats"] == {"unknown": 1}
        assert body["data"]["result_stats"] == {"unknown": 1}

    @pytest.mark.asyncio
    async def test_stats_time_range_filter(self, client, async_db):
        """statistics 也支持 start_time/end_time 过滤（仅时间维度）。"""
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 6, 1, 12, 0, 0))
        r = client.get(URL_STATS, params={"start_time": "2026-03-01T00:00:00"})
        body = r.json()
        assert body["data"]["total_count"] == 1


# ==================== 组7：operation-types 枚举展开 ====================


class TestOperationTypes:
    def test_operation_types_count(self, client):
        """枚举总数 = AuditOperationType 成员数（39）。"""
        r = client.get(URL_OP_TYPES)
        body = r.json()
        assert body["code"] == "200"
        expected = len(list(AuditOperationType))
        assert body["data"]["total"] == expected
        assert len(body["data"]["operation_types"]) == expected

    def test_operation_types_structure(self, client):
        """每个元素含 value/display_name/category 三键。"""
        r = client.get(URL_OP_TYPES)
        body = r.json()
        first = body["data"]["operation_types"][0]
        assert set(first.keys()) == {"value", "display_name", "category"}

    def test_operation_types_includes_known(self, client):
        """包含已知成员 add / archive_logs，且 category 正确。"""
        r = client.get(URL_OP_TYPES)
        items = {it["value"]: it for it in r.json()["data"]["operation_types"]}
        assert "add" in items
        assert items["add"]["category"] == "torrent"
        assert "archive_logs" in items
        assert items["archive_logs"]["category"] == "archive"


# ==================== 组8：错误降级（坏 ISO 时间） ====================


class TestErrorDegradation:
    """坏 ISO 时间 → datetime.fromisoformat 抛 ValueError → 端点兜底 code='400'，
    HTTP 仍 200（业务错误约定，非 HTTPException）。"""

    def test_query_bad_start_time_returns_400_body(self, client):
        r = client.post(URL_QUERY, json={"start_time": "not-a-date"})
        body = r.json()
        assert r.status_code == 200
        assert body["code"] == "400"

    def test_query_bad_end_time_returns_400_body(self, client):
        r = client.post(URL_QUERY, json={"end_time": "2026-13-99"})
        body = r.json()
        assert r.status_code == 200
        assert body["code"] == "400"

    def test_statistics_bad_time_returns_400_body(self, client):
        r = client.get(URL_STATS, params={"start_time": "bad"})
        body = r.json()
        assert r.status_code == 200
        assert body["code"] == "400"
