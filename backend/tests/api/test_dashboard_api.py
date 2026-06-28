# -*- coding: utf-8 -*-
"""
仪表盘统计 GET /api/v1/dashboard 的 API 级回归测试

覆盖范围（约 22 个测试）：
- 认证拒绝 / 响应结构（6 个顶层键）
- tasks SQL 聚合（COUNT + SUM(CASE WHEN task_status=1) + dr=0 软删除过滤 + stopped 计算）
- activities SQL（TOP-10 + operation_time DESC + 类别归一化 + None 字段降级显示 + 相对时间）
- 缓存读取（app.state.store 在线/离线计数 + app.state.torrent_stats 透传 + downloader_list 构造）
- 缓存降级（store/torrent_stats 缺失 → 零值/空列表）
- 系统信息（version 硬编码 + uptime_display 格式）
- 错误降级（service 抛异常 → code='500' HTTP 仍 200）

关键架构点（经探索确认）：
- DashboardService 是异步的，AsyncSession 经依赖注入（非自建 SessionLocal）。
  → aiosqlite 异步内存库 + 覆盖 get_async_db。
- service 用裸 SQL（text()），只查两张表：cron_task（tasks 聚合）、torrent_audit_log（activities TOP-10）。
  torrents/downloaders 统计来自内存缓存 app.state.store / app.state.torrent_stats，不打 DB。
- endpoint 把 request.app 传给 service → 测试必须在 test app 上设 app.state.store /
  app.state.torrent_stats / app.state.start_time（或故意不设测降级）。
- 所有业务错误返回 HTTP 200，code='500' 写在 CommonResponse 体里（endpoint try/except 兜底）。
- response_model=CommonResponse 不强校验 data 形状 → 测试直接断言 data 具体字段防 KeyError。
- code 是字符串"200"/"500"，断言用 ==。
"""

import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import get_current_user
from app.database import Base, get_async_db
from app.tasks.cron_models import CronTask
from app.torrents.audit_models import TorrentAuditLog

URL = "/api/v1/dashboard"


# ==================== Fixtures ====================


@pytest.fixture
async def async_db():
    """异步内存 SQLite，建 cron_task + torrent_audit_log 两张表（service 裸 SQL 只查这两张）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [CronTask.__table__, TorrentAuditLog.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=tables))


@pytest.fixture
def client(async_db):
    """独立 FastAPI app。设默认缓存状态（store=None 触发降级，便于结构测试）。

    其它测试需要真实缓存时，直接给 client.app.state 赋值（fixture 返回 client 后仍可改）。
    """
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    async def override_get_async_db():
        yield async_db

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")
    # 默认不设 store/torrent_stats → 触发降级分支（零值/空列表）
    app.state.start_time = time.time()

    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


async def _add_cron(async_db, *, task_code, task_status=0, dr=0, task_name="t"):
    """插入 cron_task 行（task_name/code/type/executor/cron_plan/create_by/update_by 均 NOT NULL）。"""
    task = CronTask(
        task_name=task_name,
        task_code=task_code,
        task_status=task_status,
        task_type=0,
        executor="echo",
        cron_plan="0 * * * *",
        dr=dr,
    )
    async_db.add(task)
    await async_db.commit()
    return task


async def _add_audit(async_db, *, operation_type="add", operation_time=None, torrent_name=None, downloader_name=None):
    """插入审计日志行。operation_time 默认 now（让相对时间落到"秒前"分支便于断言）。"""
    log = TorrentAuditLog(
        operation_type=operation_type,
        operation_time=operation_time or datetime.now(),
        torrent_name=torrent_name,
        downloader_name=downloader_name,
    )
    async_db.add(log)
    await async_db.commit()
    return log


def _set_store(app, downloaders):
    """给 test app 注入伪 store：downloaders 是 SimpleNamespace 列表，含 fail_time 等属性。"""

    class FakeStore:
        async def get_snapshot(self_inner):
            return list(downloaders)

    app.state.store = FakeStore()


# ==================== 组1：认证与响应结构 ====================


class TestAuthAndStructure:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, async_db):
        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        async def override_get_async_db():
            yield async_db

        app.dependency_overrides[get_async_db] = override_get_async_db
        app.state.start_time = time.time()
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get(URL)
        assert r.status_code == 401
        # 确认 401 来源是认证失败（非路由 404 / 端点崩溃 500）
        assert r.json()["detail"] == "Could not validate credentials"

    def test_response_has_six_top_keys(self, client):
        """成功响应 data 含 6 个顶层键。"""
        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert set(body["data"].keys()) == {
            "downloaders",
            "torrents",
            "tasks",
            "system",
            "downloader_list",
            "activities",
        }

    def test_default_degraded_values_when_no_cache(self, client):
        """store/torrent_stats 未设 → downloaders/torrents 全零，downloader_list 为空。"""
        r = client.get(URL)
        data = r.json()["data"]
        assert data["downloaders"] == {"total": 0, "online": 0, "offline": 0}
        assert data["torrents"] == {"active": 0, "downloading": 0, "seeding": 0, "paused": 0}
        assert data["downloader_list"] == []
        assert data["activities"] == []


# ==================== 组2：tasks SQL 聚合 ====================


class TestTasksStats:
    """COUNT(*) + SUM(CASE WHEN task_status=1 THEN 1 ELSE 0 END)，WHERE dr=0。
    stopped = max(total - running, 0)。"""

    @pytest.mark.asyncio
    async def test_empty_tasks(self, client):
        r = client.get(URL)
        assert r.json()["data"]["tasks"] == {"total": 0, "running": 0, "stopped": 0}

    @pytest.mark.asyncio
    async def test_running_count(self, client, async_db):
        """task_status=1 计入 running；0/2 不计。"""
        await _add_cron(async_db, task_code="c1", task_status=1)
        await _add_cron(async_db, task_code="c2", task_status=1)
        await _add_cron(async_db, task_code="c3", task_status=0)
        await _add_cron(async_db, task_code="c4", task_status=2)
        r = client.get(URL)
        tasks = r.json()["data"]["tasks"]
        assert tasks["total"] == 4
        assert tasks["running"] == 2, "只有 task_status=1 计入 running"
        assert tasks["stopped"] == 2, "stopped = total - running"

    @pytest.mark.asyncio
    async def test_dr1_excluded(self, client, async_db):
        """dr=1（软删除）不计入 total。"""
        await _add_cron(async_db, task_code="alive", task_status=1, dr=0)
        await _add_cron(async_db, task_code="deleted", task_status=1, dr=1)
        r = client.get(URL)
        tasks = r.json()["data"]["tasks"]
        assert tasks["total"] == 1, "dr=1 软删除须被 WHERE dr=0 过滤"
        assert tasks["running"] == 1


# ==================== 组3：activities SQL（TOP-10 + 归一化） ====================


class TestActivities:
    """torrent_audit_log ORDER BY operation_time DESC LIMIT 10。"""

    @pytest.mark.asyncio
    async def test_activities_limit_10(self, client, async_db):
        """超过 10 条只返回最近 10 条。"""
        for i in range(12):
            await _add_audit(
                async_db,
                operation_type="add",
                operation_time=datetime(2026, 1, i + 1, 12, 0, 0),
            )
        r = client.get(URL)
        acts = r.json()["data"]["activities"]
        assert len(acts) == 10, "LIMIT 10"

    @pytest.mark.asyncio
    async def test_activities_sorted_desc(self, client, async_db):
        """按 operation_time 倒序（最近在前）。完整序列断言防中间错位。"""
        for i in range(3):
            await _add_audit(
                async_db,
                operation_type="add",
                operation_time=datetime(2026, 1, i + 1, 12, 0, 0),
            )
        r = client.get(URL)
        acts = r.json()["data"]["activities"]
        # action 含 torrent_name（这里为 None → "未知种子"），用相对时间串断言顺序
        times = [a["time"] for a in acts]
        # 倒序：最近的（1月3日）应在前。相对时间随 now 变化，断言"第一个不比后一个更旧"
        # 用 operation_time 排序的代理：最近的行其 time_str 应是较小天数
        # 直接比较天数：3日 > 2日 > 1日（距 now 更近的 delta 更小）
        # 用 action 中 torrent_name 顺序不可靠（都 None），改用时间天数严格递增
        # 简化：断言第一条比最后一条时间更近（delta 更小 → "天前"数值更小 或 都是"天前"）
        assert "天前" in times[0] and "天前" in times[-1]
        # 解析天数比较
        d0 = int(times[0].split("天前")[0])
        d_last = int(times[-1].split("天前")[0])
        assert d0 < d_last, "倒序：最近（小天数）在前"

    @pytest.mark.asyncio
    async def test_activities_category_normalization(self, client, async_db):
        """recycle_bin/archive 等非白名单类别 → 归一化为 'system'。"""
        # add=torrent, reannounce=tracker, archive_logs=archive→system, restore=recycle_bin→system
        await _add_audit(async_db, operation_type="add")
        await _add_audit(async_db, operation_type="reannounce")
        await _add_audit(async_db, operation_type="archive_logs")
        await _add_audit(async_db, operation_type="restore")
        r = client.get(URL)
        cats = {a["type"] for a in r.json()["data"]["activities"]}
        assert cats == {"torrent", "tracker", "system"}, "archive/recycle_bin 须归一化为 system"

    @pytest.mark.asyncio
    async def test_activities_null_fields_show_placeholder(self, client, async_db):
        """torrent_name/downloader_name 为 None → action 含"未知种子"/"未知下载器"。"""
        await _add_audit(async_db, operation_type="add", torrent_name=None, downloader_name=None)
        r = client.get(URL)
        act = r.json()["data"]["activities"][0]
        assert "未知下载器" in act["action"]
        assert "未知种子" in act["action"]
        assert act["torrent_name"] is None
        assert act["downloader_name"] is None

    @pytest.mark.asyncio
    async def test_activities_populated_fields(self, client, async_db):
        """torrent_name/downloader_name 有值 → 直接展示，action 含真实名。"""
        await _add_audit(
            async_db,
            operation_type="add",
            torrent_name="my_movie.mkv",
            downloader_name="qbit-1",
        )
        r = client.get(URL)
        act = r.json()["data"]["activities"][0]
        assert "my_movie.mkv" in act["action"]
        assert "qbit-1" in act["action"]
        assert act["torrent_name"] == "my_movie.mkv"
        assert act["source"] == "系统", "source 硬编码为'系统'"

    @pytest.mark.asyncio
    async def test_activities_relative_time_recent(self, client, async_db):
        """operation_time = now → time 落到'秒前'分支。"""
        await _add_audit(async_db, operation_time=datetime.now())
        r = client.get(URL)
        act = r.json()["data"]["activities"][0]
        assert "秒前" in act["time"]

    @pytest.mark.asyncio
    async def test_activities_old_time_shows_days(self, client, async_db):
        """operation_time 远早于 now → time 落到'天前'分支。"""
        await _add_audit(async_db, operation_time=datetime.now() - timedelta(days=5))
        r = client.get(URL)
        act = r.json()["data"]["activities"][0]
        assert "天前" in act["time"]


# ==================== 组4：缓存读取（store / torrent_stats） ====================


class TestCacheRead:
    def test_downloaders_stats_from_store(self, client):
        """downloaders 统计来自 app.state.store：fail_time==0 为 online。"""
        _set_store(
            client.app,
            [
                SimpleNamespace(
                    fail_time=0,
                    downloader_id="d1",
                    nickname="A",
                    downloader_type=1,
                    downloading_count=2,
                    seeding_count=3,
                ),
                SimpleNamespace(
                    fail_time=0,
                    downloader_id="d2",
                    nickname="B",
                    downloader_type=1,
                    downloading_count=0,
                    seeding_count=1,
                ),
                SimpleNamespace(
                    fail_time=1700000000,
                    downloader_id="d3",
                    nickname="C",
                    downloader_type=2,
                    downloading_count=0,
                    seeding_count=0,
                ),
            ],
        )
        r = client.get(URL)
        dl = r.json()["data"]["downloaders"]
        assert dl == {"total": 3, "online": 2, "offline": 1}

    def test_torrent_stats_passthrough(self, client):
        """torrents 统计直接透传 app.state.torrent_stats 字典。"""
        client.app.state.torrent_stats = {"active": 10, "downloading": 4, "seeding": 6, "paused": 0}
        r = client.get(URL)
        assert r.json()["data"]["torrents"] == {"active": 10, "downloading": 4, "seeding": 6, "paused": 0}

    def test_downloader_list_construction(self, client):
        """downloader_list 每项含 6 个键，status 由 fail_time 决定。"""
        _set_store(
            client.app,
            [
                SimpleNamespace(
                    fail_time=0,
                    downloader_id="d1",
                    nickname="online-dl",
                    downloader_type=1,
                    downloading_count=2,
                    seeding_count=3,
                ),
                SimpleNamespace(
                    fail_time=999,
                    downloader_id="d2",
                    nickname="offline-dl",
                    downloader_type=2,
                    downloading_count=0,
                    seeding_count=0,
                ),
            ],
        )
        r = client.get(URL)
        lst = r.json()["data"]["downloader_list"]
        assert len(lst) == 2
        online = next(d for d in lst if d["downloader_id"] == "d1")
        assert set(online.keys()) == {
            "downloader_id",
            "nickname",
            "downloader_type",
            "status",
            "downloading",
            "seeding",
        }
        assert online["status"] == "online"
        assert online["downloading"] == 2
        assert online["seeding"] == 3
        offline = next(d for d in lst if d["downloader_id"] == "d2")
        assert offline["status"] == "offline"

    def test_downloader_list_empty_nickname_defaults_unknown(self, client):
        """nickname 为空 → 'Unknown'。"""
        _set_store(
            client.app,
            [
                SimpleNamespace(
                    fail_time=0,
                    downloader_id="d1",
                    nickname="",
                    downloader_type=1,
                    downloading_count=0,
                    seeding_count=0,
                ),
            ],
        )
        r = client.get(URL)
        assert r.json()["data"]["downloader_list"][0]["nickname"] == "Unknown"


# ==================== 组5：系统信息 ====================


class TestSystemStats:
    def test_version_hardcoded(self, client):
        """version 硬编码 '1.0.0'。"""
        r = client.get(URL)
        assert r.json()["data"]["system"]["version"] == "1.0.0"

    def test_uptime_display_minutes_when_just_started(self, client):
        """start_time = now → uptime 接近 0 → uptime_display 走'分钟'分支。"""
        client.app.state.start_time = time.time()
        r = client.get(URL)
        sys_stats = r.json()["data"]["system"]
        assert "分钟" in sys_stats["uptime_display"]
        assert sys_stats["uptime"] >= 0
        assert isinstance(sys_stats["uptime"], int)

    def test_uptime_display_days_when_old_start(self, client):
        """start_time 设为 2 天前 → uptime_display 走'天'分支。"""
        client.app.state.start_time = time.time() - 2 * 86400
        r = client.get(URL)
        sys_stats = r.json()["data"]["system"]
        assert "天" in sys_stats["uptime_display"]
        assert sys_stats["uptime"] >= 2 * 86400 - 5  # 容忍几秒抖动


# ==================== 组6：错误降级 ====================


class TestErrorDegradation:
    def test_service_exception_returns_500_body(self, async_db):
        """service 抛异常 → endpoint 兜底 code='500'，HTTP 仍 200，data=null。

        构造方式：让 store.get_snapshot 抛异常（_get_downloaders_stats 最先执行）。
        """

        class BrokenStore:
            async def get_snapshot(self):
                raise RuntimeError("cache down")

        app = FastAPI()
        app.include_router(api_router, prefix="/api/v1")

        async def override_get_async_db():
            yield async_db

        app.dependency_overrides[get_async_db] = override_get_async_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")
        app.state.start_time = time.time()
        app.state.store = BrokenStore()
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get(URL)
        body = r.json()
        assert r.status_code == 200
        assert body["code"] == "500"
        assert body["status"] == "error"
        assert body["data"] is None
        assert "获取失败" in body["msg"]
