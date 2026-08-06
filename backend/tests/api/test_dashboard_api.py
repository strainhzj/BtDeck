# -*- coding: utf-8 -*-
"""
仪表盘统计 GET /api/v1/dashboard 的 API 级回归测试

覆盖范围（23 个测试）：
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

import json
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


async def _add_audit(
    async_db, *, operation_type="add", operation_time=None, torrent_name=None, downloader_name=None, operation_detail=None
):
    """插入审计日志行。operation_time 默认 now（让相对时间落到"秒前"分支便于断言）。"""
    log = TorrentAuditLog(
        operation_type=operation_type,
        operation_time=operation_time or datetime.now(),
        torrent_name=torrent_name,
        downloader_name=downloader_name,
        operation_detail=operation_detail,
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
        """成功响应 data 含 6 个顶层键。

        同时断言 msg=='获取成功'：endpoint 的异常兜底会返回 code='500'+data=None+msg='获取失败:...'，
        显式断言 msg 可把"正常降级"与"service 异常被吞成 data=None"在断言层区分，
        避免 KeyError 掩盖真正的降级逻辑回归。
        """
        r = client.get(URL)
        body = r.json()
        assert body["code"] == "200"
        assert body["msg"] == "获取成功"
        assert set(body["data"].keys()) == {
            "downloaders",
            "torrents",
            "tasks",
            "system",
            "downloader_list",
            "activities",
        }

    def test_default_degraded_values_when_no_cache(self, client):
        """store/torrent_stats 未设 → downloaders/torrents 全零，downloader_list 为空。

        同时断言 msg=='获取成功'，防 service 异常被 endpoint 吞成 data=null 时
        断言因 KeyError 误报为"字段缺失"而非"降级逻辑坏了"。
        """
        r = client.get(URL)
        body = r.json()
        assert body["msg"] == "获取成功"
        data = body["data"]
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
        body = r.json()
        assert body["msg"] == "获取成功", "防 service 异常被吞成 data=null 时 KeyError 误报"
        assert body["data"]["tasks"] == {"total": 0, "running": 0, "stopped": 0}

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
        """dr=1（软删除）不计入 total。

        身份锁定：alive 行 task_status=1（running），deleted 行 task_status=0（非 running）。
        若 SQL 方向写反成 WHERE dr=1，会返回 deleted 那条 → running==0 ≠ 1 报红，
        从而区分"返回了错误的那条"（单纯 total==1 无法区分）。
        """
        await _add_cron(async_db, task_code="alive", task_status=1, dr=0)
        await _add_cron(async_db, task_code="deleted", task_status=0, dr=1)
        r = client.get(URL)
        tasks = r.json()["data"]["tasks"]
        assert tasks["total"] == 1, "dr=1 软删除须被 WHERE dr=0 过滤"
        assert tasks["running"] == 1, "返回的须是 alive(status=1) 而非 deleted(status=0)"


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
        """按 operation_time 倒序（最近在前）。

        用 torrent_name 身份标记每条记录，断言完整顺序，而非解析相对时间字符串。
        这样完全确定性，且能抓"中间元素错位"（如 [d3, d1, d2]），
        不依赖 datetime.now() 与"天前"格式解析的脆性。
        """
        # d1=1月1日(最旧), d2=1月2日, d3=1月3日(最新)；倒序应为 [d3, d2, d1]
        for i in range(3):
            await _add_audit(
                async_db,
                operation_type="add",
                torrent_name=f"d{i + 1}",
                operation_time=datetime(2026, 1, i + 1, 12, 0, 0),
            )
        r = client.get(URL)
        acts = r.json()["data"]["activities"]
        names = [a["torrent_name"] for a in acts]
        assert names == ["d3", "d2", "d1"], "倒序：最新(1月3日=d3)须在最前"

    @pytest.mark.asyncio
    async def test_activities_category_normalization(self, client, async_db):
        """recycle_bin/archive/keyword_rule 等非白名单类别 → 归一化为 'system'。

        用 dict 计数而非 set 比较：set 会丢失计数信息，无法抓"restore 误归 tracker"
        这类多归类 bug（set 仍相等）。dict 计数能精确锁每个类别的条数。
        覆盖三种非白名单 category 路径（archive/recycle_bin/keyword_rule）防白名单误改。
        """
        # add=torrent, reannounce=tracker, archive_logs=archive→system,
        # restore=recycle_bin→system, keyword_rule_add=keyword_rule→system
        await _add_audit(async_db, operation_type="add")
        await _add_audit(async_db, operation_type="reannounce")
        await _add_audit(async_db, operation_type="archive_logs")
        await _add_audit(async_db, operation_type="restore")
        await _add_audit(async_db, operation_type="keyword_rule_add")
        r = client.get(URL)
        cats = {}
        for a in r.json()["data"]["activities"]:
            cats[a["type"]] = cats.get(a["type"], 0) + 1
        assert cats == {
            "torrent": 1,
            "tracker": 1,
            "system": 3,
        }, "archive_logs/restore/keyword_rule 须归一化为 system（共 3 条 system）"

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
        """operation_time 接近 now → time 落到'秒前'分支。

        用 now()-10s 而非 now()：给 50 秒安全裕度（service 调 datetime.now() 时
        delta 仍在 < 60s 的"秒前"窗口内），避免慢 CI 下插数到查询耗时 > 60s 落到
        "分钟前"分支导致 flaky。
        """
        await _add_audit(async_db, operation_time=datetime.now() - timedelta(seconds=10))
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

    @pytest.mark.asyncio
    async def test_orphan_cleanup_shows_cleaned_files(self, client, async_db):
        """孤儿文件清理：展示被清理文件/目录名，不再出现'未知下载器 种子 未知种子'。"""
        await _add_audit(
            async_db,
            operation_type="orphan_cleanup",
            torrent_name=None,
            downloader_name=None,
            operation_detail=json.dumps(
                {"action": "manual_cleanup", "success_count": 2, "failed_count": 0, "cleaned_files": ["a.torrent", "b"]}
            ),
        )
        r = client.get(URL)
        act = r.json()["data"]["activities"][0]
        assert "孤儿文件清理文件 a.torrent、b" in act["action"]
        assert "未知下载器" not in act["action"]
        assert "未知种子" not in act["action"]

    @pytest.mark.asyncio
    async def test_orphan_cleanup_historical_without_files(self, client, async_db):
        """历史孤儿清理日志无 cleaned_files → 回退展示成功计数，不出现未知占位符。"""
        await _add_audit(
            async_db,
            operation_type="orphan_cleanup",
            torrent_name=None,
            downloader_name=None,
            operation_detail=json.dumps({"action": "manual_cleanup", "success_count": 3, "failed_count": 1}),
        )
        r = client.get(URL)
        act = r.json()["data"]["activities"][0]
        assert "孤儿文件清理（成功 3 个）" in act["action"]
        assert "未知下载器" not in act["action"]

    @pytest.mark.asyncio
    async def test_orphan_ignore_no_unknown_placeholder(self, client, async_db):
        """其它孤儿操作（忽视）走计数字段文案，同样不出现未知占位符。"""
        await _add_audit(
            async_db,
            operation_type="orphan_ignore",
            torrent_name=None,
            downloader_name=None,
            operation_detail=json.dumps({"action": "ignore", "success_count": 5, "failed_count": 0}),
        )
        r = client.get(URL)
        act = r.json()["data"]["activities"][0]
        assert "孤儿文件忽视（成功 5 个）" in act["action"]
        assert "未知下载器" not in act["action"]


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
        """downloader_list 每项含 8 个键，status 由 fail_time 决定。"""
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
                    download_speed=10,
                    upload_speed=5,
                ),
                SimpleNamespace(
                    fail_time=999,
                    downloader_id="d2",
                    nickname="offline-dl",
                    downloader_type=2,
                    downloading_count=0,
                    seeding_count=0,
                    download_speed=0,
                    upload_speed=0,
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
            "download_speed",
            "upload_speed",
        }
        assert online["status"] == "online"
        assert online["downloading"] == 2
        assert online["seeding"] == 3
        # 缓存速度单位 KB/s → bytes/s（×1024）
        assert online["download_speed"] == 10 * 1024
        assert online["upload_speed"] == 5 * 1024
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

    def test_torrent_stats_none_returns_null_known_behavior(self, client):
        """已知行为：app.state.torrent_stats=None 时 service 返回 None（非零值降级）。

        被测 _get_torrents_stats 只判 hasattr 不判 is None，与 _get_downloaders_stats
        （双重判空）不对称。若某天 service 修了对齐判空（None→零值），本测试需同步更新。
        此测试钉死当前行为，防止该不对称被无意改动而无测试告警。
        """
        client.app.state.torrent_stats = None
        r = client.get(URL)
        assert r.json()["data"]["torrents"] is None

    def test_downloader_list_prefers_torrent_stats_dict_over_counts(self, client):
        """downloader.torrent_stats 是 dict 时优先用它，忽略 downloading_count 属性。

        覆盖 _get_downloader_list 的前缀分支（之前测试只覆盖了属性回退分支）。
        让两路给不同值（torrent_stats=5 vs downloading_count=99），断言取 5 锁分支选择。

        注：当前生产代码无路径给单个 downloader 对象挂 torrent_stats dict（该属性只在
        app.state.torrent_stats 聚合级出现）。此测试钉死的是 service 对该字段的读取契约，
        供未来引入 downloader.torrent_stats 时回归；非生产 hot path。
        """
        _set_store(
            client.app,
            [
                SimpleNamespace(
                    fail_time=0,
                    downloader_id="d1",
                    nickname="A",
                    downloader_type=1,
                    torrent_stats={"downloading": 5, "seeding": 7},
                    downloading_count=99,  # 应被忽略
                    seeding_count=88,  # 应被忽略
                ),
            ],
        )
        r = client.get(URL)
        item = r.json()["data"]["downloader_list"][0]
        assert item["downloading"] == 5, "torrent_stats 是 dict 时优先取 dict 值"
        assert item["seeding"] == 7


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
        # 双向锁"刚启动"语义：uptime 应很小（< 60s），恒真的 >=0 不足以抓 start_time 算错的回归
        assert 0 <= sys_stats["uptime"] < 60
        assert isinstance(sys_stats["uptime"], int)

    def test_uptime_display_days_when_old_start(self, client):
        """start_time 设为 2 天前 → uptime_display 走'天'分支。"""
        client.app.state.start_time = time.time() - 2 * 86400
        r = client.get(URL)
        sys_stats = r.json()["data"]["system"]
        assert "天" in sys_stats["uptime_display"]
        assert sys_stats["uptime"] >= 2 * 86400 - 5  # 容忍几秒抖动

    def test_system_total_speeds_from_online_downloaders(self, client):
        """系统总速度 = 所有在线下载器速度之和（KB/s→bytes/s ×1024），离线下载器不计。"""
        _set_store(
            client.app,
            [
                SimpleNamespace(fail_time=0, download_speed=100, upload_speed=50),
                SimpleNamespace(fail_time=0, download_speed=300, upload_speed=20),
                SimpleNamespace(fail_time=1700000000, download_speed=9999, upload_speed=9999),  # 离线不计
            ],
        )
        r = client.get(URL)
        sys_stats = r.json()["data"]["system"]
        assert sys_stats["total_download_speed"] == (100 + 300) * 1024
        assert sys_stats["total_upload_speed"] == (50 + 20) * 1024

    def test_system_total_speeds_zero_without_store(self, client):
        """无 store（降级）→ 总速度为 0。"""
        r = client.get(URL)
        sys_stats = r.json()["data"]["system"]
        assert sys_stats["total_download_speed"] == 0
        assert sys_stats["total_upload_speed"] == 0


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
