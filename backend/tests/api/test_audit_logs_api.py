# -*- coding: utf-8 -*-
"""
审计日志 API 回归测试

覆盖端点：
- POST /api/v1/audit-logs/query        查询（11 维过滤 + 子查询 count + 排序 + 分页）
- GET  /api/v1/audit-logs/statistics    内存聚合统计
- GET  /api/v1/audit-logs/operation-types  操作类型枚举展开（39 成员）
- POST /api/v1/audit-logs/export        导出（空数据/坏时间降级）
- GET  /api/v1/audit-logs/download-export/{file_name}  下载（唯一抛 HTTPException 的端点）

覆盖范围（41 个测试）：
- 认证拒绝（含 401 来源 body 断言）/ 空数据（含 msg 排除防 service 降级假通过）
- 11 维过滤（torrent_name 是唯一 LIKE 模糊维度）+ LIKE 通配符注入已知行为 + 无匹配边界
- 时间范围（start_time / end_time 闭区间）
- 排序（operation_time DESC，完整序列断言）+ 分页（含 offset 生效/count 解耦双重验证）
- statistics 内存聚合（含 unknown 桶 + 时间过滤后 stats 字典断言）
- operation-types 枚举展开（数量 + value 集合精确相等 + 结构 + 已知成员）
- 错误降级（坏 ISO 时间 → code='400' HTTP 200；download-export 404 是真 HTTPException）

关键架构点（经探索确认）：
- AuditLogService 是异步的，用传入的 AsyncSession（依赖注入式，非自建 SessionLocal）。
  → 用 aiosqlite 异步内存库 + AsyncSession，覆盖 get_async_db。
- 所有 JSON 业务错误返回 HTTP 200，code='400'/'500' 写在 CommonResponse 体里；
  唯一例外是 download-export，它抛 HTTPException(404/500)。
- 响应 data 分页字段混用大小写：total/page（小写）vs pageSize（驼峰）—— load-bearing 断言点。
- service 不抛异常：query_logs/get_statistics 出错静默返回空结构 → 端点仍 code='200'。
  因此空表/无匹配场景额外断言 msg 不含"查询失败"，防止 service 异常被吞成假通过。
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
        # 确认 401 来源是认证失败（非路由 404 或端点崩溃 500）
        assert r.json()["detail"] == "Could not validate credentials"

    def test_empty_logs_returns_zero(self, client):
        """空表 → total=0, list=[]。

        同时断言 msg 非降级文案：query_logs 出错时静默返回空结构（不抛），
        端点仍返回 code='200'。为避免"service 坏了却因 total==0 假通过"，
        显式排除降级 msg（端点异常分支的 msg 带有"查询失败"/"参数错误"前缀）。
        """
        r = client.post(URL_QUERY, json={})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0
        assert body["data"]["list"] == []
        assert "查询失败" not in body["msg"], "msg 含降级文案说明 service 走了异常分支"

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
    async def test_filter_by_torrent_name_wildcard_injection(self, client, async_db):
        """已知行为：torrent_name 直接拼入 LIKE，% 会被当通配符。

        service 用 torrent_name.like(f"%{torrent_name}%")，未对 % / _ 转义。
        传 "%" 会匹配所有行（非空 torrent_name）。此测试记录该已知行为，
        若未来 service 加 escape，本测试需同步更新。
        """
        await _add(async_db, torrent_name="movie A", operator="a")
        await _add(async_db, torrent_name="series B", operator="a")
        await _add(async_db, operator="a")  # torrent_name=None，不应被 % 命中
        r = client.post(URL_QUERY, json={"torrent_name": "%"})
        body = r.json()
        # % 匹配任意非空 torrent_name（2 条）；NULL 不参与 LIKE 匹配
        assert body["data"]["total"] == 2

    @pytest.mark.asyncio
    async def test_filter_no_match_returns_empty(self, client, async_db):
        """传不存在的过滤值 → total=0, list=[]（边界：过滤生效但无匹配）。"""
        await _add(async_db, operation_type="add", operator="alice")
        r = client.post(URL_QUERY, json={"operator": "nobody"})
        body = r.json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0
        assert body["data"]["list"] == []
        # 排除 service 降级（吞异常也返回空）的假通过
        assert "查询失败" not in body["msg"]

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
        """按 operation_time 倒序（最近的在前）。

        用完整序列断言（非仅首尾比较），可抓中间元素错位 bug
        （例如 [06, 01, 03] 的首尾比较仍为真，会漏检）。
        """
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 6, 1, 12, 0, 0))
        await _add(async_db, operation_type="add", operation_time=datetime(2026, 3, 1, 12, 0, 0))
        r = client.post(URL_QUERY, json={})
        body = r.json()
        times = [item["operation_time"] for item in body["data"]["list"]]
        assert times == sorted(times, reverse=True), "完整序列须严格倒序"

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

    @pytest.mark.asyncio
    async def test_pagination_offset_takes_effect(self, client, async_db):
        """翻页 offset 生效：第1页与第2页无重叠，且 total 不受 limit/offset 影响。

        关键正确性点：count 用 select(func.count()).select_from(query.subquery())，
        必须与 limit/offset 解耦。本测试同时验证：
        - limit 生效（每页恰 page_size 条，非全量）
        - offset 生效（相邻页无重叠 id）
        - count 解耦（total=5 不随 page_size=2 变成 2）
        """
        ids = []
        for i in range(5):
            log = await _add(async_db, operation_type="add", operation_time=datetime(2026, 1, i + 1, 12, 0, 0))
            ids.append(log.log_id)
        page1 = client.post(URL_QUERY, json={"page": 1, "page_size": 2}).json()["data"]
        page2 = client.post(URL_QUERY, json={"page": 2, "page_size": 2}).json()["data"]
        assert page1["total"] == 5, "count 须解耦于 page_size"
        assert len(page1["list"]) == 2 and len(page2["list"]) == 2
        ids1 = {item["log_id"] for item in page1["list"]}
        ids2 = {item["log_id"] for item in page2["list"]}
        assert ids1.isdisjoint(ids2), "相邻页须无重叠（offset 生效）"

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
        """statistics 也支持 start_time/end_time 过滤（仅时间维度）。

        除 total_count 外，同时断言 stats 字典在时间过滤后仍正确聚合，
        避免"过滤失效导致全部数据混入聚合"的假通过。
        """
        await _add(
            async_db,
            operation_type="add",
            operator="alice",
            operation_result="success",
            operation_time=datetime(2026, 1, 1, 12, 0, 0),
        )
        await _add(
            async_db,
            operation_type="pause",
            operator="bob",
            operation_result="failed",
            operation_time=datetime(2026, 6, 1, 12, 0, 0),
        )
        r = client.get(URL_STATS, params={"start_time": "2026-03-01T00:00:00"})
        body = r.json()
        assert body["data"]["total_count"] == 1
        # 时间过滤后只剩 6 月那条，聚合应精确反映子集（非全量）
        assert body["data"]["operation_type_stats"] == {"pause": 1}
        assert body["data"]["operator_stats"] == {"bob": 1}
        assert body["data"]["result_stats"] == {"failed": 1}


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

    def test_operation_types_value_set_matches_enum(self, client):
        """返回的 value 集合必须精确等于枚举全部成员的 value 集合。

        比仅断言 len 更强：可抓"端点循环过滤掉某些成员但 total 与 list 同步减少"
        的逻辑偏差（此时 len 仍相等但集合不同）。
        """
        r = client.get(URL_OP_TYPES)
        returned = {it["value"] for it in r.json()["data"]["operation_types"]}
        expected = {op.value for op in AuditOperationType}
        assert returned == expected

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


# ==================== 组9：download-export / export 约定差异 ====================


class TestDownloadAndExport:
    """download-export 是唯一抛 HTTPException 的端点（404/500），
    与其他端点"HTTP 200 + code 体"约定不同；export 空数据走 code='400' 降级。"""

    def test_download_nonexistent_returns_404(self, client):
        """下载不存在的文件 → 真 HTTP 404（非 200+code 体）。"""
        r = client.get("/api/v1/audit-logs/download-export/no_such_file.csv")
        assert r.status_code == 404
        assert r.json()["detail"] == "文件不存在"

    def test_export_empty_returns_400_body(self, client):
        """export 无匹配数据 → HTTP 200 + code='400'（业务降级，非 HTTPException）。"""
        r = client.post("/api/v1/audit-logs/export", json={})
        body = r.json()
        assert r.status_code == 200
        assert body["code"] == "400"
        assert body["msg"] == "没有符合条件的数据可导出"

    def test_export_bad_time_returns_400_body(self, client):
        """export 坏 ISO 时间 → datetime.fromisoformat 抛 ValueError → code='400'。"""
        r = client.post("/api/v1/audit-logs/export", json={"start_time": "not-a-date"})
        body = r.json()
        assert r.status_code == 200
        assert body["code"] == "400"
