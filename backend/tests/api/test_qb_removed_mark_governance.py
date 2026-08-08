# -*- coding: utf-8 -*-
"""
qB 移除标记统一写治理测试（W1-3，PLANS/sync-database-blocking-remediation.md）

【覆盖目标】
1. 无移除（removed_hashes 空）→ 不查询不 commit，返回零值 WriteStats。
2. 少量移除（3 个 hash，其中 1 个 dr 已为 1、1 个不存在）→ 只更新命中行
   （UPDATE 行数 = 1），其它行 dr 不变，跨下载器同名 hash 不受影响。
3. 大量移除（> batch_size）→ commit 次数为 ceil(n/batch_size)（真实内存
   SQLite + commit spy，batch_size 传小值 2 断言 commits == ceil(n/2)）。
4. 中途锁冲突（第 N 批 commit 抛 SQLITE_BUSY 错误码 5）→ 仅重试第 N 批、
   前面已提交批不重跑、最终成功、retries=1。
5. 事务外查询顺序：待更新 ID 的只读 select 发生在任何 db_write_scope 进入
   （db_writer 信号量 acquire）之前。
6. AST 源码断言：_mark_qb_removed_torrents 函数体内不再出现
   sa_update / db.execute(update(...)) / db.commit() 直接调用，
   且必须调用批准写入口 bulk_upsert_with_retry。

【测试分层】
用真实 SQLite（aiosqlite :memory: + StaticPool + create_all 建 torrent_info 表）
验证 SQL 语义；锁冲突通过 commit spy 注入带 sqlite_errorcode=5 的异常。
"""

import asyncio
import ast
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.services.sync_db_write import WriteStats
from app.torrents.models import TorrentInfo

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TORRENTS_ASYNC_PATH = BACKEND_ROOT / "app" / "api" / "endpoints" / "torrents_async.py"


@pytest.fixture
async def torrent_db():
    """异步内存 SQLite，建 torrent_info 表（含部分唯一索引 idx_torrent_hash_unique）。"""
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


def _new_torrent(info_id: str, downloader_id: str, hash_: str, *, name: str = "t", dr: int = 0) -> TorrentInfo:
    """构造真 ORM TorrentInfo 行（与 tests/api/conftest.make_torrent 同序，异步测试用）。"""
    added = datetime(2026, 1, 1, 12, 0, 0)
    t = TorrentInfo(
        info_id,  # info_id（复合主键之一）
        downloader_id,  # downloader_id（复合主键之二）
        "dl",  # downloader_name
        None,  # torrent_id
        hash_,  # hash
        name,  # name
        "/path",  # save_path
        0,  # size
        "seeding",  # status
        0.0,  # progress
        None,  # torrent_file
        added,  # added_date
        None,  # completed_date
        "0",  # ratio
        "0",  # ratio_limit
        "",  # tags
        "",  # category
        "否",  # super_seeding
        True,  # enabled
        added,  # create_time
        "tester",  # create_by
        added,  # update_time
        "tester",  # update_by
        dr,  # dr
    )
    t.has_tracker_error = False  # NOT NULL，__init__ 未赋值
    return t


def _busy_error(code: int = 5) -> sqlite3.OperationalError:
    """构造带 sqlite_errorcode 的锁冲突异常（模拟驱动抛出的 SQLITE_BUSY）。"""
    err = sqlite3.OperationalError("database is locked")
    err.sqlite_errorcode = code
    err.sqlite_errorname = "SQLITE_BUSY"
    return err


def _spy_execute(session: AsyncSession, events: list):
    """把 session.execute 换成记录事件的包装（保留真实执行）。"""
    real_execute = session.execute

    async def spied_execute(*args, **kwargs):
        events.append("execute")
        return await real_execute(*args, **kwargs)

    session.execute = spied_execute  # type: ignore[method-assign]


def _spy_commit(session: AsyncSession, events: list, *, fail_on_call: int = -1):
    """把 session.commit 换成记录事件的包装；第 fail_on_call 次抛 SQLITE_BUSY。"""
    real_commit = session.commit

    async def spied_commit():
        events.append("commit")
        if len(events) == fail_on_call:
            raise _busy_error(5)
        return await real_commit()

    session.commit = spied_commit  # type: ignore[method-assign]


def _spy_rollback(session: AsyncSession, events: list):
    """把 session.rollback 换成记录事件的包装（保留真实执行）。"""
    real_rollback = session.rollback

    async def spied_rollback():
        events.append("rollback")
        return await real_rollback()

    session.rollback = spied_rollback  # type: ignore[method-assign]


class TestQbRemovedMarkNoRemoval:
    """无移除（removed_hashes 空）：零副作用，不查询不 commit。"""

    async def test_empty_removed_hashes_zero_stats_no_db_io(self, torrent_db):
        """removed_hashes 为空 → 返回零值 WriteStats，不执行任何查询/提交。"""
        from app.api.endpoints.torrents_async import _mark_qb_removed_torrents

        events = []
        _spy_execute(torrent_db, events)
        _spy_commit(torrent_db, events)

        stats = await _mark_qb_removed_torrents(torrent_db, "dl-1", [])

        assert isinstance(stats, WriteStats)
        assert stats.scanned == 0
        assert stats.changed == 0
        assert stats.committed == 0
        assert stats.batches == 0
        assert stats.retries == 0
        assert stats.elapsed_ms == 0.0
        # 不查询、不 commit、不 rollback
        assert events == [], f"空移除不应产生任何 DB 调用，实际: {events}"


class TestQbRemovedMarkSmallRemoval:
    """少量移除：只更新命中行（dr=0 且 hash 在列表且 downloader 匹配）。"""

    async def test_only_matching_rows_updated(self, torrent_db):
        """3 个 hash（1 个 dr=0 命中、1 个 dr=1、1 个不存在）→ 只更新 1 行。"""
        from app.api.endpoints.torrents_async import _mark_qb_removed_torrents

        # 预置 4 行：
        #   dl-1/h1 dr=0（命中，应被标记）
        #   dl-1/h2 dr=1（已删，不应重复更新）
        #   dl-1/h4 dr=0（不在 removed 列表，不应更新）
        #   dl-2/h1 dr=0（跨下载器同名 hash，不应更新）
        torrent_db.add_all(
            [
                _new_torrent("t-1", "dl-1", "h1", name="hit", dr=0),
                _new_torrent("t-2", "dl-1", "h2", name="already-deleted", dr=1),
                _new_torrent("t-4", "dl-1", "h4", name="keep", dr=0),
                _new_torrent("t-5", "dl-2", "h1", name="other-downloader", dr=0),
            ]
        )
        await torrent_db.commit()

        stats = await _mark_qb_removed_torrents(torrent_db, "dl-1", ["h1", "h2", "h3-nonexistent"])

        # 写入统计：只更新 1 行（单批）
        assert stats.scanned == 1
        assert stats.changed == 1
        assert stats.committed == 1
        assert stats.batches == 1
        assert stats.retries == 0

        # DB 状态断言（expire_all 排除 identity map 缓存）
        torrent_db.expire_all()
        result = await torrent_db.execute(
            select(TorrentInfo.info_id, TorrentInfo.dr, TorrentInfo.update_by).order_by(TorrentInfo.info_id)
        )
        rows = {r.info_id: (r.dr, r.update_by) for r in result.all()}
        assert rows["t-1"] == (1, "system"), f"命中行应标记 dr=1/update_by=system，实际 {rows['t-1']}"
        assert rows["t-2"] == (1, "tester"), f"dr=1 行不应被重复更新，实际 {rows['t-2']}"
        assert rows["t-4"] == (0, "tester"), f"不在列表的活跃行不应更新，实际 {rows['t-4']}"
        assert rows["t-5"] == (0, "tester"), f"跨下载器同名 hash 不应更新，实际 {rows['t-5']}"

    async def test_query_no_match_returns_zero_stats_no_commit(self, torrent_db):
        """查询无命中（hash 均不存在）→ 零值 WriteStats，执行了只读查询但不 commit。"""
        from app.api.endpoints.torrents_async import _mark_qb_removed_torrents

        torrent_db.add(_new_torrent("t-1", "dl-1", "h1", dr=0))
        await torrent_db.commit()

        events = []
        _spy_execute(torrent_db, events)
        _spy_commit(torrent_db, events)

        stats = await _mark_qb_removed_torrents(torrent_db, "dl-1", ["h-ghost-1", "h-ghost-2"])

        assert isinstance(stats, WriteStats)
        assert stats.scanned == 0
        assert stats.changed == 0
        assert stats.batches == 0
        # 只读 select 执行了一次，但没有任何 commit
        assert events == ["execute"], f"无命中应只执行一次只读查询，实际: {events}"


class TestQbRemovedMarkLargeRemoval:
    """大量移除：按统一批大小真实分批 commit。"""

    async def test_commits_ceil_division_batches(self, torrent_db):
        """450 个 hash 全命中，batch_size=2 → commit 次数 == ceil(450/2) == 225。"""
        from app.api.endpoints.torrents_async import _mark_qb_removed_torrents

        n = 450
        torrent_db.add_all([_new_torrent(f"t-{i:04d}", "dl-1", f"h-{i:04d}", dr=0) for i in range(n)])
        await torrent_db.commit()

        events = []
        _spy_commit(torrent_db, events)

        with patch("app.core.config.settings.SYNC_DB_COMMIT_BATCH_SIZE", 2):
            stats = await _mark_qb_removed_torrents(torrent_db, "dl-1", [f"h-{i:04d}" for i in range(n)])

        expected_batches = (n + 1) // 2  # ceil(450/2) = 225
        assert len(events) == expected_batches, f"commit 次数应等于 ceil({n}/2)={expected_batches}，实际 {len(events)}"
        assert stats.batches == expected_batches
        assert stats.changed == n
        assert stats.committed == n
        assert stats.scanned == n
        assert stats.retries == 0

        # 全部行最终被标记 dr=1（分批提交不丢行）
        torrent_db.expire_all()
        result = await torrent_db.execute(select(TorrentInfo.dr))
        dr_values = [r.dr for r in result.all()]
        assert len(dr_values) == n
        assert all(dr == 1 for dr in dr_values), f"应有 {n} 行 dr=1，实际 {sum(1 for d in dr_values if d == 1)} 行"


class TestQbRemovedMarkLockConflict:
    """中途锁冲突：仅重试当前失败批，已提交批不重跑。"""

    async def test_busy_on_second_batch_retries_only_that_batch(self, torrent_db):
        """6 行 batch_size=2 → 3 批；第 2 批首次 commit 抛 SQLITE_BUSY(5)，
        仅重试第 2 批（commit 共 4 次），最终成功，retries=1。"""
        from app.api.endpoints.torrents_async import _mark_qb_removed_torrents

        n = 6
        torrent_db.add_all([_new_torrent(f"t-{i}", "dl-1", f"h-{i}", dr=0) for i in range(n)])
        await torrent_db.commit()

        events = []
        _spy_commit(torrent_db, events, fail_on_call=2)  # 第 2 次 commit（批 2 首次）抛 BUSY
        _spy_rollback(torrent_db, events)
        slept = []
        real_sleep = asyncio.sleep

        async def _fake_sleep(delay):
            slept.append(delay)
            if delay > 0:
                await real_sleep(0)  # 不真正等待，保持事件循环可调度

        with patch("app.core.config.settings.SYNC_DB_COMMIT_BATCH_SIZE", 2):
            with patch("app.services.sync_db_write.asyncio.sleep", side_effect=_fake_sleep):
                with patch("app.services.sync_db_write.random.uniform", side_effect=lambda a, b: 0.01):
                    stats = await _mark_qb_removed_torrents(torrent_db, "dl-1", [f"h-{i}" for i in range(n)])

        # 3 批：批1 commit OK、批2 首次 BUSY、批2 重试 OK、批3 OK → 共 4 次 commit + 1 次回滚
        assert events.count("commit") == 4, f"commit 应为 4 次（3 成功 + 1 失败尝试），实际: {events}"
        assert events.count("rollback") == 1, "仅失败批重试前回滚一次"
        assert stats.retries == 1
        assert stats.batches == 3
        assert stats.changed == 6
        assert stats.committed == 6

        # 最终全部成功标记（重试后数据不丢）
        torrent_db.expire_all()
        result = await torrent_db.execute(select(TorrentInfo.dr))
        assert all(r.dr == 1 for r in result.all())

    async def test_non_lock_exception_propagates_without_retry(self, torrent_db):
        """非锁异常（IntegrityError）立即上抛且不重试（保留统一写入器异常语义）。"""
        from app.api.endpoints.torrents_async import _mark_qb_removed_torrents

        torrent_db.add(_new_torrent("t-1", "dl-1", "h1", dr=0))
        await torrent_db.commit()

        events = []

        async def spied_commit():
            events.append("commit")
            raise sqlite3.IntegrityError("UNIQUE constraint failed")  # 非锁异常

        torrent_db.commit = spied_commit  # type: ignore[method-assign]

        with patch("app.services.sync_db_write.asyncio.sleep", side_effect=lambda d: None):
            with pytest.raises(sqlite3.IntegrityError):
                await _mark_qb_removed_torrents(torrent_db, "dl-1", ["h1"])

        assert len(events) == 1, "非锁异常不应触发重试（commit 只调 1 次）"


class TestQbRemovedMarkReadOnlySelectOutsideScope:
    """事务外查询顺序：只读 select 发生在任何 db_write_scope 进入之前。"""

    async def test_select_happens_before_db_write_scope_enter(self, torrent_db):
        """待更新 ID 的只读查询必须在 db_writer 信号量 acquire（db_write_scope 进入）之前。"""
        from app.api.endpoints.torrents_async import _mark_qb_removed_torrents
        from app.tasks.resource_guard import admission_controller

        torrent_db.add_all([_new_torrent(f"t-{i}", "dl-1", f"h-{i}", dr=0) for i in range(3)])
        await torrent_db.commit()

        events = []
        _spy_execute(torrent_db, events)

        with patch("app.core.config.settings.SYNC_DB_WRITE_SCOPE_ENABLED", True):
            admission_controller.reset_state()
            real_sem = admission_controller._state.db_writer
            real_acquire = real_sem.acquire

            async def spied_acquire():
                events.append("scope_enter")
                return await real_acquire()

            try:
                real_sem.acquire = spied_acquire  # type: ignore[method-assign]
                stats = await _mark_qb_removed_torrents(torrent_db, "dl-1", ["h-0", "h-1", "h-2"])
            finally:
                real_sem.acquire = real_acquire  # type: ignore[method-assign]
                admission_controller.reset_state()

        # 顺序：先 execute（事务外只读查询）→ 后 scope_enter（统一写入器 db_write_scope）
        assert events.index("execute") < events.index(
            "scope_enter"
        ), f"只读 select 必须在 db_write_scope 进入之前，实际顺序: {events}"
        assert events.count("execute") == 1
        assert events.count("scope_enter") == 1
        assert stats.changed == 3


class TestQbRemovedMarkSourceArchitecture:
    """AST 源码断言：函数体内不再有旁路 DML（sa_update / db.execute(update) / db.commit）。"""

    def _mark_removed_func_node(self):
        tree = ast.parse(TORRENTS_ASYNC_PATH.read_text(encoding="utf-8"), filename=str(TORRENTS_ASYNC_PATH))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_mark_qb_removed_torrents":
                return node
        raise AssertionError("未找到 _mark_qb_removed_torrents 函数（路径漂移？）")

    def test_no_direct_dml_in_function_body(self):
        """函数体内不得出现 db.commit() / db.execute(update|delete|insert) / 局部 import update。"""
        func = self._mark_removed_func_node()
        violations = []
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "db":
                    if f.attr == "commit":
                        violations.append(f"行 {node.lineno}: db.commit() 直接调用")
                    elif f.attr == "execute" and node.args:
                        arg0 = node.args[0]
                        dml_name = None
                        if isinstance(arg0, ast.Call):
                            if isinstance(arg0.func, ast.Name) and arg0.func.id in {
                                "update",
                                "delete",
                                "insert",
                                "sqlite_insert",
                            }:
                                dml_name = arg0.func.id
                            elif isinstance(arg0.func, ast.Attribute) and arg0.func.attr in {
                                "update",
                                "delete",
                                "insert",
                            }:
                                dml_name = arg0.func.attr
                        if dml_name:
                            violations.append(f"行 {node.lineno}: db.execute({dml_name}(...)) 直接 DML")
            elif isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy":
                for alias in node.names:
                    if alias.name in {"update", "delete"}:
                        violations.append(f"行 {node.lineno}: 函数内局部 import sqlalchemy.{alias.name}")

        assert not violations, "旁路 DML 已收敛为统一写入口，发现残留:\n" + "\n".join(violations)

    def test_must_call_approved_write_entry(self):
        """函数体必须调用批准写入口 bulk_upsert_with_retry。"""
        func = self._mark_removed_func_node()
        calls = [
            node
            for node in ast.walk(func)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "bulk_upsert_with_retry"
        ]
        assert calls, "函数体必须调用 bulk_upsert_with_retry（统一批大小 + db_write_scope + retry）"
