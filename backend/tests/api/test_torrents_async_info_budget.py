# -*- coding: utf-8 -*-
"""
info-only 种子信息同步资源治理测试（W3-3 第一部分，P1-02）

【覆盖目标】
1. 并发配置化：INFO_SYNC_DOWNLOADER_CONCURRENCY 透传给
   execute_sync_with_concurrency 的 max_concurrent（=1 / =3），不再硬编码 3。
2. 现有记录分页读取：existing 行数(1200) > 分页大小(500) → 分页 select 调用
   次数 = ceil(1200/500) = 3；cache 完整性（1200 行全部进 cache，diff 结果
   正确：远程种子全部命中现有行 → 插入 0、更新 1200）。
3. 单轮数量上限：INFO_SYNC_MAX_TORRENTS_PER_RUN=100 + 500 种子 → 处理 ≤ 100，
   完成日志含 budget_reason=count、partial=True。
4. 缓冲上限：INFO_SYNC_MAX_BUFFERED_ROWS=100 → 循环中多次 flush
   （bulk_upsert_with_retry 调用次数 > 1），每次 flush 后缓冲清空
   （每批恰好 100 行，无跨批累积）。
5. 时间预算：INFO_SYNC_RUN_BUDGET_SECONDS 到期（mock monotonic 可控推进）→
   完成日志含 budget_reason=time、partial=True。
6. 让行：分页循环每页后/批次 flush 后存在 asyncio.sleep(0)（行为断言：
   计数包装 sleep，3 页分页至少 3 次 sleep(0)）。
7. TR 对称性：tr info-only 同样分页读取（1200 行 3 次 select）+ cache 完整。

设计依据：
- asyncio_mode=auto（pytest.ini），异步测试直接 async def。
- call_downloader_api 全部替换为直调 fake（参照
  tests/api/test_torrents_async_tracker_budget.py 的隔离原因：全量套件中
  TestClient(app) 的 lifespan 退出会 shutdown 进程级 runtime 单例 executor）。
- info-only 返回结构不变（None）；partial/budget_reason 从完成日志读取
  （参照 W3-1 tracker 测试的日志断言方式）。
"""

import asyncio
import sys
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.endpoints import torrents_async
from app.core.config import settings
from app.database import Base
from app.tasks.scheduler.torrent_sync.torrent_info_sync_task import TorrentInfoSyncTask
from app.torrents.models import TorrentInfo


# ==================== 公共 fixture ====================


@pytest.fixture(autouse=True)
def isolate_call_downloader_api():
    """把 torrents_async.call_downloader_api 替换为直调 fake（不经 runtime 单例）。"""

    async def fake_call_downloader_api(downloader_id, lane, func, args=(), kwargs=None, timeout=None, operation=""):
        return func(*args, **(kwargs or {}))

    with patch.object(torrents_async, "call_downloader_api", new=fake_call_downloader_api):
        yield


@pytest.fixture
async def info_db():
    """异步内存 SQLite，只建 torrent_info 表（StaticPool 单连接）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[TorrentInfo.__table__]))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=[TorrentInfo.__table__]))
        await engine.dispose()


# ==================== 构造辅助 ====================

ADDED_DT = datetime(2026, 1, 1, 12, 0, 0)
ADDED_TS = int(ADDED_DT.timestamp())


def _qb_downloader():
    return SimpleNamespace(
        downloader_id="dl-1",
        nickname="qb",
        host="localhost",
        port=8080,
        username="admin",
        password="secret",
    )


def _qb_seed(hash_, name):
    """与 _qb_row 字段匹配的远程 qB 种子（SimpleNamespace，兼容 _qb_get_attr）。"""
    return SimpleNamespace(
        hash=hash_,
        name=name,
        save_path="/downloads",
        total_size=4096,
        progress=0.5,
        state="stalledUP",
        added_on=ADDED_TS,
        completion_on=0,
        ratio=1.5,
        ratio_limit=2.0,
        tags="PT",
        category="电影",
        super_seeding=False,
    )


def _qb_row(info_id, hash_, name):
    """与 _qb_seed 字段匹配的现有 DB 行（TorrentInfo ORM）。"""
    t = TorrentInfo(
        info_id,
        "dl-1",
        "qb",
        f"tid-{hash_}",
        hash_,
        name,
        "/downloads",
        4096.0,
        "seeding",
        50.0,
        None,
        ADDED_DT,
        None,
        1.5,
        2.0,
        "PT",
        "电影",
        False,
        True,
        ADDED_DT,
        "tester",
        ADDED_DT,
        "tester",
        0,
    )
    t.has_tracker_error = False
    return t


def _qb_pairs(count):
    """构造 count 对 (远程种子, 现有 DB 行)，字段一致（update 路径）。"""
    seeds, rows = [], []
    for i in range(count):
        hash_ = f"h{i:06d}"
        seeds.append(_qb_seed(hash_, f"name-{i}"))
        rows.append(_qb_row(f"info-{i}", hash_, f"name-{i}"))
    return seeds, rows


def _make_qb_client(seeds):
    """按 limit/offset 切片返回种子列表的伪 qB 客户端（torrents_info 分页）。"""
    client = MagicMock()
    client.sync_maindata = MagicMock()

    def torrents_info(**kwargs):
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 500)
        return seeds[offset : offset + limit]

    client.torrents_info = MagicMock(side_effect=torrents_info)
    return client


def _tr_seed(i, hash_, name, *, error=0, error_string=""):
    return SimpleNamespace(
        id=i,
        hashString=hash_,
        name=name,
        status=6,
        error=error,
        error_string=error_string,
        download_dir="/downloads",
        total_size=4096,
        percent_done=0.5,
        torrent_file=None,
        added_date=ADDED_DT,
        done_date=None,
        ratio=1.5,
        seed_ratio_limit=2.0,
    )


def _tr_row(info_id, hash_, i, name):
    t = TorrentInfo(
        info_id,
        "dl-tr",
        "tr",
        str(i),
        hash_,
        name,
        "/downloads",
        4096.0,
        6,
        50.0,
        None,
        ADDED_DT,
        None,
        1.5,
        2.0,
        "",
        "",
        False,
        True,
        ADDED_DT,
        "tester",
        ADDED_DT,
        "tester",
        0,
    )
    t.has_tracker_error = False
    return t


def _tr_pairs(count):
    """构造 count 对 (远程种子, 现有 DB 行)，字段一致（update 路径）。"""
    seeds, rows = [], []
    for i in range(count):
        hash_ = f"trh{i:06d}"
        name = f"name-{i}"
        seeds.append(_tr_seed(i, hash_, name))
        rows.append(_tr_row(f"info-{i}", hash_, i, name))
    return seeds, rows


def _make_tr_client(seeds):
    """按 ids 返回种子的伪 Transmission 客户端（base 全量 / detail 按 ids）。"""
    by_id = {s.id: s for s in seeds}
    client = MagicMock()

    def get_torrents(**kwargs):
        ids = kwargs.get("ids")
        if ids is None:
            return list(by_id.values())
        return [by_id[i] for i in ids]

    client.get_torrents = MagicMock(side_effect=get_torrents)
    return client


def _empty_db():
    """空库 AsyncMock：所有 select 返回空结果（与 test_torrent_metadata 同款）。"""
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.return_value = query_result
    return db


def _completion_log(mock_info, marker):
    """从 patch 的 logger.info 调用列表中提取完成日志文本。"""
    hits = [str(c) for c in mock_info.call_args_list if marker in str(c)]
    assert hits, f"未捕获完成日志（{marker}）"
    return hits[-1]


@contextmanager
def _fake_app_main():
    """临时替换 sys.modules['app.main'] 为伪模块。

    TorrentInfoSyncTask.execute 内部 `from app.main import app` 在调用时解析
    sys.modules，替换后取到伪 app（execute 只把它透传给已 patch 的
    get_valid_downloaders，实际不使用）。避免导入真实 app.main 的副作用
    （app logger 改写/启动清单校验/DB 初始化）。
    """
    fake = SimpleNamespace(app=SimpleNamespace())
    original = sys.modules.get("app.main")
    sys.modules["app.main"] = fake
    try:
        yield fake
    finally:
        if original is not None:
            sys.modules["app.main"] = original
        else:
            sys.modules.pop("app.main", None)


# ==================== 1. 并发配置化 ====================


class TestDownloaderConcurrencyConfig:
    """INFO_SYNC_DOWNLOADER_CONCURRENCY 透传给 execute_sync_with_concurrency。"""

    @pytest.mark.parametrize("expected", [1, 3])
    async def test_max_concurrent_read_from_config(self, monkeypatch, expected):
        monkeypatch.setattr(settings, "INFO_SYNC_DOWNLOADER_CONCURRENCY", expected)
        task = TorrentInfoSyncTask()
        vo = SimpleNamespace(downloader_id="dl-1", nickname="qb", fail_time=0, downloader_type=0)
        with (
            _fake_app_main(),
            patch.object(
                task, "get_valid_downloaders", new=AsyncMock(return_value=[vo])
            ) as mock_get,
            patch.object(
                task,
                "execute_sync_with_concurrency",
                new=AsyncMock(
                    return_value={
                        "status": "success",
                        "successful_syncs": 1,
                        "failed_syncs": 0,
                        "total_downloaders": 1,
                    }
                ),
            ) as mock_exec,
        ):
            result = await task.execute()

        assert result["status"] == "success"
        mock_get.assert_awaited_once()
        assert mock_exec.await_args.kwargs["max_concurrent"] == expected
        assert mock_exec.await_args.kwargs["sync_type"] == "TorrentInfo"


# ==================== 2. 现有记录分页读取（qb） ====================


class TestQbExistingRecordsPaginatedRead:
    """existing 行数 > 分页大小 → 分页 select 次数 = ceil(n/page)，cache 完整。"""

    async def test_1200_rows_read_in_3_pages_with_complete_cache(self, info_db, monkeypatch):
        monkeypatch.setattr(settings, "INFO_SYNC_DB_READ_PAGE_SIZE", 500)
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)

        seeds, rows = _qb_pairs(1200)
        info_db.add_all(rows)
        await info_db.commit()

        client = _make_qb_client(seeds)
        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async.logger, "info") as mock_info,
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
            patch.object(info_db, "execute", wraps=info_db.execute) as mock_execute,
        ):
            await torrents_async.qb_add_torrents_info_only_async(info_db, [_qb_downloader()], client=client)

        # 分页读取：1200 / 500 → 3 次 select（无 removed 查询、bulk 已 mock）
        assert len(mock_execute.call_args_list) == 3

        # cache 完整性：全部 1200 行进 cache（远程种子全部命中现有行 →
        # 插入 0、更新 1200；任一分页漏读都会退化为 insert）
        bulk_mock.assert_awaited_once()
        assert bulk_mock.await_args.args[1] == []  # to_insert
        assert len(bulk_mock.await_args.args[2]) == 1200  # to_update
        text = _completion_log(mock_info, "[QB_INFO_SYNC]")
        assert "插入 0" in text
        assert "更新 1200" in text


# ==================== 6. 让行（asyncio.sleep(0)） ====================


class TestYieldPoints:
    """分页/批次循环中存在 asyncio.sleep(0)（批间让行）。"""

    async def test_paginated_read_yields_event_loop_per_page(self, info_db, monkeypatch):
        monkeypatch.setattr(settings, "INFO_SYNC_DB_READ_PAGE_SIZE", 500)
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)

        seeds, rows = _qb_pairs(1200)
        info_db.add_all(rows)
        await info_db.commit()

        client = _make_qb_client(seeds)
        real_sleep = asyncio.sleep
        sleep_zero_calls = {"count": 0}

        async def counting_sleep(delay, *args, **kwargs):
            if delay == 0:
                sleep_zero_calls["count"] += 1
            return await real_sleep(delay, *args, **kwargs)

        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()),
            patch.object(torrents_async.asyncio, "sleep", new=counting_sleep),
        ):
            await torrents_async.qb_add_torrents_info_only_async(info_db, [_qb_downloader()], client=client)

        # 3 页分页 → 每页后 sleep(0)（无写入，无 flush 产生的额外让行）
        assert sleep_zero_calls["count"] >= 3


# ==================== 3. 单轮数量上限 ====================


class TestCountBudget:
    """INFO_SYNC_MAX_TORRENTS_PER_RUN 到期 → 停止处理剩余，budget_reason=count。"""

    async def test_count_budget_stops_at_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 100)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)

        seeds = [_qb_seed(f"h{i:06d}", f"name-{i}") for i in range(500)]
        client = _make_qb_client(seeds)
        db = _empty_db()
        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async.logger, "info") as mock_info,
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.qb_add_torrents_info_only_async(db, [_qb_downloader()], client=client)

        # 只处理前 100 个（数量预算），剩余 400 个丢弃
        bulk_mock.assert_awaited_once()
        assert len(bulk_mock.await_args.args[1]) == 100
        text = _completion_log(mock_info, "[QB_INFO_SYNC]")
        assert "插入 100" in text
        assert "partial=True" in text
        assert "budget_reason=count" in text

    async def test_info_cursor_advances_only_after_durable_write_and_resumes(self, monkeypatch):
        """部分 info 轮次持久化最后一个已写入 hash，下一轮从该 hash 后继续。"""
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 2)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)
        seeds = [_qb_seed(f"h{i:06d}", f"name-{i}") for i in range(5)]
        client = _make_qb_client(seeds)
        db = _empty_db()
        callbacks: list[str] = []

        async def capture_cursor(value: str):
            callbacks.append(value)

        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            first = await torrents_async.qb_add_torrents_info_only_async(
                db,
                [_qb_downloader()],
                client=client,
                progress_callback=capture_cursor,
            )

            assert first is not None
            assert first["partial"] is True
            assert first["cursor"] == '{"last_hash": "h000001"}'
            assert callbacks[-1] == first["cursor"]
            assert len(bulk_mock.await_args.args[1]) == 2

            bulk_mock.reset_mock()
            monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10)
            second = await torrents_async.qb_add_torrents_info_only_async(
                db,
                [_qb_downloader()],
                client=client,
                cursor=first["cursor"],
                progress_callback=capture_cursor,
            )

        assert second is not None
        assert second["cycle_complete"] is True
        assert second["cursor"] is None
        assert len(bulk_mock.await_args.args[1]) == 3
        assert callbacks[-1] == '{"last_hash": "h000004"}'


# ==================== 4. 缓冲上限（多次 flush） ====================


class TestBufferedRowsFlush:
    """INFO_SYNC_MAX_BUFFERED_ROWS 到期 → 先 flush 一批再继续，缓冲清空。"""

    async def test_buffer_flushed_in_batches(self, monkeypatch):
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_BUFFERED_ROWS", 100)
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)

        seeds = [_qb_seed(f"h{i:06d}", f"name-{i}") for i in range(500)]
        client = _make_qb_client(seeds)
        db = _empty_db()
        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async.logger, "info") as mock_info,
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.qb_add_torrents_info_only_async(db, [_qb_downloader()], client=client)

        # 4 次缓冲 flush（迭代 101/201/301/401 循环顶部）+ 1 次收尾写入 = 5 次
        assert bulk_mock.call_count == 5
        assert bulk_mock.call_count > 1
        # 每次 flush 后缓冲清空：每批恰好 100 行，无跨批累积
        for call in bulk_mock.call_args_list:
            assert len(call.args[1]) == 100
            assert call.args[2] == []
        text = _completion_log(mock_info, "[QB_INFO_SYNC]")
        assert "插入 500" in text
        assert "rows_buffered=100" in text
        assert "yield_count=5" in text  # 分页 1 页 + flush 4 次


# ==================== 5. 时间预算 ====================


class TestTimeBudget:
    """INFO_SYNC_RUN_BUDGET_SECONDS 到期（monotonic 可控推进）→ budget_reason=time。"""

    async def test_time_budget_stops_processing(self, monkeypatch):
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 0.05)

        # 每次 monotonic 调用推进 0.005s：循环中的预算检查会迅速越过时间预算
        fake_time = {"t": 0.0}

        def advancing_monotonic():
            fake_time["t"] += 0.005
            return fake_time["t"]

        seeds = [_qb_seed(f"h{i:06d}", f"name-{i}") for i in range(100)]
        client = _make_qb_client(seeds)
        db = _empty_db()
        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async.time, "monotonic", new=advancing_monotonic),
            patch.object(torrents_async.logger, "info") as mock_info,
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.qb_add_torrents_info_only_async(db, [_qb_downloader()], client=client)

        text = _completion_log(mock_info, "[QB_INFO_SYNC]")
        assert "partial=True" in text
        assert "budget_reason=time" in text
        # 未全量处理（时间预算提前到期），已处理部分（≤100）仍写入
        assert bulk_mock.call_count == 1
        assert len(bulk_mock.await_args.args[1]) < 100


# ==================== 7. TR 对称性（分页读取 + cache 完整） ====================


class TestTrSymmetricPaginatedRead:
    """TR info-only 与 qB 行为对称：同样分页读取 + cache 完整。"""

    async def test_tr_1200_rows_read_in_3_pages_with_complete_cache(self, info_db, monkeypatch):
        monkeypatch.setattr(settings, "INFO_SYNC_DB_READ_PAGE_SIZE", 500)
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)

        seeds, rows = _tr_pairs(1200)
        info_db.add_all(rows)
        await info_db.commit()

        client = _make_tr_client(seeds)
        with (
            patch.dict(torrents_async._TR_FULL_SYNC_DONE, {}, clear=True),
            patch.dict(torrents_async._TR_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async.logger, "info") as mock_info,
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
            patch.object(info_db, "execute", wraps=info_db.execute) as mock_execute,
        ):
            await torrents_async.tr_add_torrents_info_only_async(info_db, [_tr_downloader()], client=client)

        assert len(mock_execute.call_args_list) == 3
        bulk_mock.assert_awaited_once()
        assert bulk_mock.await_args.args[1] == []  # to_insert
        assert len(bulk_mock.await_args.args[2]) == 1200  # to_update
        text = _completion_log(mock_info, "[TR_INFO_SYNC]")
        assert "插入 0" in text
        assert "更新 1200" in text

    async def test_tr_error_reason_is_requested_and_written(self, monkeypatch):
        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 100)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)
        seed = _tr_seed(
            1,
            "tr-error-hash",
            "error-seed",
            error=3,
            error_string="No space left on device",
        )
        client = _make_tr_client([seed])
        db = _empty_db()

        with (
            patch.dict(torrents_async._TR_FULL_SYNC_DONE, {}, clear=True),
            patch.dict(torrents_async._TR_LAST_FULL_SYNC, {}, clear=True),
            patch.object(
                torrents_async,
                "bulk_upsert_with_retry",
                new=AsyncMock(),
            ) as bulk_mock,
        ):
            await torrents_async.tr_add_torrents_info_only_async(
                db,
                [_tr_downloader()],
                client=client,
            )

        inserted = bulk_mock.await_args.args[1]
        assert inserted[0]["status"] == "error"
        assert inserted[0]["error_reason"] == "No space left on device"
        assert all(
            "errorString" in call.kwargs["arguments"]
            for call in client.get_torrents.call_args_list
        )


def _tr_downloader():
    return SimpleNamespace(
        downloader_id="dl-tr",
        nickname="tr",
        host="localhost",
        port=9091,
        username="admin",
        password="secret",
    )
