# -*- coding: utf-8 -*-
"""
sync_db_write 工具单测

【覆盖目标】
1. has_torrent_info_changes：业务字段变化检测，忽略 update_time/PK。
2. has_tracker_changes：6 字段检测，None==""/strip 归一化，死字段不对比。
3. bulk_upsert_with_retry（W1-1 真分批提交）：
   - 空输入零副作用（不调 db、不进 db_write_scope）；
   - 批边界：行数 <、==、> batch_size，每批真实 commit；
   - 第 N 批锁冲突仅重试当前批，前面已提交批不重跑；
   - 非锁异常立即失败且不重试；
   - 有限指数退避 + 抖动 + 单批总睡眠上限；
   - SYNC_CHUNKED_COMMIT_ENABLED=False 回退单事务一次提交；
   - WriteStats 六字段完整且语义正确；
   - 锁冲突错误码分类（禁止消息字符串匹配）；
   - 部分进度：ChunkedWriteError 携带已提交批统计，原异常为 __cause__；
   - 真实文件型 SQLite：每批 commit 后另一连接立即可见已提交行。

【测试分层】
- 纯函数（has_*_changes）：直接断言，无 mock。
- bulk_upsert_with_retry：mock db + mock admission_controller.db_write_scope，
  验证分批/重试/统计契约。
- 真实 SQLite：tmp_path 文件库 + 第二连接观察批间可见性。
"""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sync_db_write import (
    _TORRENT_INFO_IGNORE_KEYS,
    _TRACKER_CHANGE_FIELDS,
    ChunkedWriteError,
    WriteStats,
    _is_sqlite_lock_conflict,
    bulk_upsert_with_retry,
    has_torrent_info_changes,
    has_tracker_changes,
)


def _fake_scope():
    """返回一个 asynccontextmanager 装饰的假 db_write_scope（直接 yield）。"""

    @asynccontextmanager
    async def _scope():
        yield

    return _scope


def _mock_ac() -> MagicMock:
    """mock admission_controller：db_write_scope 每次调用返回全新 scope。

    注意：asynccontextmanager 的 CM 实例不可重复进入（生成器已耗尽），
    因此每次调用 db_write_scope() 都必须返回新实例。
    """
    mock_ac = MagicMock()
    mock_ac.db_write_scope.side_effect = lambda: _fake_scope()()
    return mock_ac


def _busy_error(code: int = 5) -> sqlite3.OperationalError:
    """构造带 sqlite_errorcode 的锁冲突异常（模拟驱动抛出的 SQLITE_BUSY）。"""
    err = sqlite3.OperationalError("database is locked")
    err.sqlite_errorcode = code
    err.sqlite_errorname = "SQLITE_BUSY" if code == 5 else "SQLITE_LOCKED"
    return err


class TestHasTorrentInfoChanges:
    """TorrentInfo 业务字段变更检测。"""

    def test_same_values_no_change(self):
        assert has_torrent_info_changes({"name": "a", "size": 100}, {"name": "a", "size": 100}) is False

    def test_different_value_has_change(self):
        assert has_torrent_info_changes({"name": "a"}, {"name": "b"}) is True

    def test_empty_existing_treated_as_change(self):
        """旧值为空 dict（缺失）→ 视为需要写入。"""
        assert has_torrent_info_changes({}, {"name": "a"}) is True

    def test_update_time_ignored(self):
        """update_time 变化不视为业务变化（同步每轮都刷新，但不应触发写入）。"""
        existing = {"name": "a", "update_time": "2026-01-01"}
        new = {"name": "a", "update_time": "2026-07-04"}
        assert has_torrent_info_changes(existing, new) is False

    def test_create_time_and_pk_ignored(self):
        """create_time / info_id 等 PK/元数据字段不参与检测。"""
        for key in ("create_time", "info_id", "torrent_info_id", "update_by", "create_by"):
            assert key in _TORRENT_INFO_IGNORE_KEYS

    def test_string_strip_normalization(self):
        """字符串尾空格不视为变化。"""
        assert has_torrent_info_changes({"name": "torrent.mkv"}, {"name": "torrent.mkv "}) is False

    def test_progress_numeric_change_detected(self):
        """数值字段（progress）变化被检测。"""
        assert has_torrent_info_changes({"progress": 50.0}, {"progress": 60.0}) is True
        assert has_torrent_info_changes({"progress": 50.0}, {"progress": 50.0}) is False


class TestHasTrackerChanges:
    """TrackerInfo 6 字段变更检测。"""

    def test_empty_existing_treated_as_change(self):
        """无旧值（新 tracker）→ 视为需要写入。"""
        assert has_tracker_changes({}, {"last_announce_msg": "ok"}) is True

    def test_all_fields_same_no_change(self):
        existing = {f: "x" for f in _TRACKER_CHANGE_FIELDS}
        new = {f: "x" for f in _TRACKER_CHANGE_FIELDS}
        assert has_tracker_changes(existing, new) is False

    def test_announce_status_change_detected(self):
        """last_announce_succeeded 变化被检测。"""
        existing = {"last_announce_succeeded": 1}
        new = {"last_announce_succeeded": 0}
        assert has_tracker_changes(existing, new) is True

    def test_announce_msg_change_detected(self):
        existing = {"last_announce_msg": "ok"}
        new = {"last_announce_msg": "fail"}
        assert has_tracker_changes(existing, new) is True

    def test_string_strip_normalization(self):
        """尾空格不视为变化（防远程返回微小差异导致每轮都写）。"""
        existing = {"last_announce_msg": "announce ok"}
        new = {"last_announce_msg": "announce ok "}
        assert has_tracker_changes(existing, new) is False

    def test_none_equals_empty_string(self):
        """None 与 "" 等价（不视为变化）—— 关键归一化契约。"""
        existing = {"last_announce_msg": ""}
        new = {"last_announce_msg": None}
        assert has_tracker_changes(existing, new) is False

    def test_dead_fields_not_compared(self):
        """status/msg/seeder_count 等死字段不参与检测（sync 不写它们）。"""
        dead_fields = ("status", "msg", "seeder_count", "leecher_count", "download_count")
        for field in dead_fields:
            assert field not in _TRACKER_CHANGE_FIELDS, f"{field} 不应参与变更检测"

    def test_six_business_fields_covered(self):
        """确认 6 个业务字段全覆盖。"""
        assert set(_TRACKER_CHANGE_FIELDS) == {
            "last_announce_succeeded",
            "last_announce_msg",
            "last_scrape_succeeded",
            "last_scrape_msg",
            "tracker_name",
            "tracker_host",
        }


class TestSqliteLockConflictClassification:
    """锁冲突错误码分类（基于 sqlite_errorcode，禁止消息字符串匹配）。"""

    def test_busy_and_locked_codes_recognized(self):
        """SQLITE_BUSY(5)/SQLITE_LOCKED(6) 及扩展码全部识别为锁冲突。"""
        for code in (5, 6, 261, 262, 266, 517):
            err = sqlite3.OperationalError("database is locked")
            err.sqlite_errorcode = code
            assert _is_sqlite_lock_conflict(err) is True, f"code {code} 应识别为锁冲突"

    def test_sqlalchemy_wrapped_error_uses_orig_code(self):
        """SQLAlchemy 包装异常从 orig（原始驱动异常）取错误码。"""
        from sqlalchemy.exc import OperationalError

        orig = sqlite3.OperationalError("database is locked")
        orig.sqlite_errorcode = 5
        wrapped = OperationalError("SELECT 1", {}, orig)
        assert _is_sqlite_lock_conflict(wrapped) is True

    def test_constraint_code_not_retried(self):
        """SQLITE_CONSTRAINT(19，IntegrityError 场景) 不视为锁冲突、不重试。"""
        err = sqlite3.OperationalError("UNIQUE constraint failed")
        err.sqlite_errorcode = 19
        assert _is_sqlite_lock_conflict(err) is False

    def test_non_sqlite_exceptions_not_retried(self):
        """非 SQLite 异常一律不重试。"""
        assert _is_sqlite_lock_conflict(RuntimeError("boom")) is False
        assert _is_sqlite_lock_conflict(ValueError("bad value")) is False
        assert _is_sqlite_lock_conflict(sqlite3.IntegrityError("UNIQUE constraint failed")) is False

    def test_manual_operational_error_without_code_degraded(self):
        """错误码不可得时降级：裸 sqlite3.OperationalError 视为锁冲突（保守兜底）。"""
        assert _is_sqlite_lock_conflict(sqlite3.OperationalError("database is locked")) is True


class TestBulkUpsertWithRetry:
    """bulk_upsert_with_retry 真分批提交调用契约。"""

    async def test_noop_when_both_lists_empty(self):
        """空输入：返回零值 WriteStats，不调 db、不进 db_write_scope。"""
        db = AsyncMock()
        mock_ac = _mock_ac()
        with patch("app.services.sync_db_write.admission_controller", mock_ac):
            stats = await bulk_upsert_with_retry(db, [], [], model=MagicMock(), label="test")

        assert isinstance(stats, WriteStats)
        assert stats.scanned == 0
        assert stats.changed == 0
        assert stats.committed == 0
        assert stats.batches == 0
        assert stats.retries == 0
        assert stats.elapsed_ms == 0.0
        db.run_sync.assert_not_called()
        db.commit.assert_not_called()
        db.rollback.assert_not_called()
        mock_ac.db_write_scope.assert_not_called()

    async def test_db_write_scope_entered_on_write(self):
        """有数据写入时必须进入 db_write_scope（核心契约）。

        防假通过：直接用真实 admission_controller（不 mock），spy 其 _state.db_writer
        的 acquire。mutation 删掉 db_write_scope 包裹时，acquire 不会被调。
        """
        from app.tasks.resource_guard import admission_controller

        with patch("app.core.config.settings.SYNC_DB_WRITE_SCOPE_ENABLED", True):
            admission_controller.reset_state()
            db = AsyncMock()
            to_insert = [{"name": "a"}]

            # spy db_writer semaphore 的 acquire（真实信号量）
            real_sem = admission_controller._state.db_writer
            acquire_spy = AsyncMock(wraps=real_sem.acquire)
            with patch.object(real_sem, "acquire", acquire_spy):
                stats = await bulk_upsert_with_retry(db, to_insert, [], model=MagicMock(), label="insert_only")

            # ★ 关键断言：db_writer.acquire 被调用（证明进入了 db_write_scope）
            acquire_spy.assert_awaited()
            db.commit.assert_awaited()
            assert stats.batches == 1
            admission_controller.reset_state()

    async def test_insert_and_update_both_called(self):
        """to_insert 和 to_update 都有数据时，bulk_insert + bulk_update 都被调（各一真实批次）。"""
        db = AsyncMock()
        to_insert = [{"name": "a"}]
        to_update = [{"info_id": 1, "name": "b"}]

        with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
            stats = await bulk_upsert_with_retry(db, to_insert, to_update, model=MagicMock(), label="both")

        # 2 个批次（insert 1 + update 1），各一次 run_sync + 一次 commit
        assert db.run_sync.await_count == 2
        assert db.commit.await_count == 2
        assert stats.batches == 2
        assert stats.committed == 2
        assert stats.changed == 2

    async def test_batch_boundaries(self):
        """行数 <、==、> batch_size 时 commit 次数与 batches 统计正确。"""
        cases = [
            (3, 1),  # 3 < 200 → 1 批
            (200, 1),  # == batch_size → 1 批
            (450, 3),  # > batch_size → ceil(450/200) = 3 批
        ]
        for n_rows, expected_batches in cases:
            db = AsyncMock()
            to_insert = [{"id": i, "name": f"n{i}"} for i in range(n_rows)]
            with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
                stats = await bulk_upsert_with_retry(
                    db, to_insert, [], model=MagicMock(), label="boundary", batch_size=200
                )
            assert db.commit.await_count == expected_batches, f"{n_rows} 行应 commit {expected_batches} 次"
            assert stats.batches == expected_batches
            assert stats.committed == n_rows
            assert stats.changed == n_rows
            assert stats.scanned == n_rows

    async def test_lock_conflict_on_second_batch_retries_only_that_batch(self):
        """第 2 批发生一次锁冲突：仅重试第 2 批，前面已提交批不重跑，最终成功。"""
        db = AsyncMock()
        # 3 批：批 1 commit OK、批 2 首次 commit 抛 BUSY、批 2 重试 OK、批 3 OK
        db.commit.side_effect = [None, _busy_error(5), None, None]
        to_insert = [{"id": i} for i in range(6)]
        with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
            stats = await bulk_upsert_with_retry(
                db, to_insert, [], model=MagicMock(), label="retry_nth", batch_size=2, max_retries=3
            )

        # 共 4 次 commit（3 成功 + 1 失败尝试）：前面批的 commit 未被重跑
        assert db.commit.await_count == 4
        # 仅失败批（批 2）触发一次清理回滚
        assert db.rollback.await_count == 1
        assert stats.retries == 1
        assert stats.batches == 3
        assert stats.committed == 6
        assert stats.changed == 6
        assert stats.elapsed_ms >= 0.0

    async def test_non_lock_exception_fails_immediately_without_retry(self):
        """非锁异常（IntegrityError / RuntimeError）立即失败且不重试。"""
        for exc in (sqlite3.IntegrityError("UNIQUE constraint failed"), RuntimeError("boom")):
            db = AsyncMock()
            db.commit.side_effect = exc
            with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
                with pytest.raises(type(exc), match=str(exc)):
                    await bulk_upsert_with_retry(
                        db, [{"id": 1}], [], model=MagicMock(), label="non_lock", max_retries=3
                    )
            # 不重试：commit 只被调用 1 次
            assert db.commit.await_count == 1, f"{type(exc).__name__} 不应触发重试"

    async def test_total_backoff_capped_per_batch(self):
        """单批重试总睡眠不超过 SYNC_DB_RETRY_MAX_BACKOFF_SECONDS。

        用 random.uniform 上界补丁 + asyncio.sleep 探针：无上限时退避为
        1.5 + 3.0 = 4.5s；2.0s 总上限生效后实际睡眠 1.5 + 0.5 = 2.0s。
        """
        slept = []
        real_sleep = asyncio.sleep

        async def _fake_sleep(delay):
            slept.append(delay)
            if delay > 0:
                await real_sleep(0)  # 保持事件循环可调度，不真正等待

        db = AsyncMock()
        db.commit.side_effect = [_busy_error(5), _busy_error(5), None]
        with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
            with patch("app.services.sync_db_write.random.uniform", side_effect=lambda a, b: b):
                with patch("app.services.sync_db_write.asyncio.sleep", side_effect=_fake_sleep):
                    stats = await bulk_upsert_with_retry(
                        db,
                        [{"id": 1}, {"id": 2}],
                        [],
                        model=MagicMock(),
                        label="backoff_cap",
                        batch_size=2,
                        max_retries=3,
                        base_delay=1.0,
                    )

        assert stats.retries == 2
        assert stats.batches == 1
        backoff_sleeps = [d for d in slept if d > 0]
        assert backoff_sleeps == [1.5, 0.5], f"退避序列异常: {backoff_sleeps}"
        assert sum(backoff_sleeps) == 2.0
        assert sum(backoff_sleeps) <= 2.0  # 总上限生效

    async def test_chunked_commit_disabled_falls_back_to_single_transaction(self):
        """SYNC_CHUNKED_COMMIT_ENABLED=False：数据量大于 batch_size 也只 commit 1 次。"""
        db = AsyncMock()
        to_insert = [{"id": i} for i in range(500)]
        with patch("app.core.config.settings.SYNC_CHUNKED_COMMIT_ENABLED", False):
            with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
                stats = await bulk_upsert_with_retry(
                    db, to_insert, [], model=MagicMock(), label="fallback", batch_size=200
                )

        assert db.commit.await_count == 1
        assert db.run_sync.await_count == 1
        assert stats.batches == 1
        assert stats.committed == 500
        assert stats.changed == 500

    async def test_write_stats_fields_complete(self):
        """WriteStats 六字段齐全且语义正确。"""
        db = AsyncMock()
        with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
            stats = await bulk_upsert_with_retry(
                db,
                [{"id": i} for i in range(3)],
                [{"id": i} for i in range(2)],
                model=MagicMock(),
                label="stats_test",
                batch_size=2,
            )

        for field in ("scanned", "changed", "committed", "batches", "retries", "elapsed_ms"):
            assert hasattr(stats, field), f"WriteStats 缺少字段 {field}"
        assert stats.scanned == 5
        assert stats.committed == 5
        assert stats.changed == stats.committed
        assert stats.batches == 3  # insert 2 批 + update 1 批
        assert stats.retries == 0
        assert isinstance(stats.elapsed_ms, float)
        assert stats.elapsed_ms >= 0.0

    async def test_batch_commit_emits_info_event(self):
        """每批 commit 后发射 EVENT_BATCH_COMMIT（INFO，含批次/耗时字段）。"""
        from app.services import sync_observability as obs

        db = AsyncMock()
        with (
            patch("app.services.sync_db_write.admission_controller", _mock_ac()),
            patch.object(obs.logger, "log") as mock_log,
        ):
            stats = await bulk_upsert_with_retry(
                db,
                [{"id": i} for i in range(3)],
                [],
                model=MagicMock(),
                label="event_test",
            )

        assert stats.batches == 1
        infos = [c.args[1] for c in mock_log.call_args_list if c.args[0] == logging.INFO]
        assert infos, "每批 commit 后应发射 INFO 事件"
        msg = infos[-1]
        assert "event=sync_batch_commit" in msg
        assert "batch_index=0" in msg
        assert "batch_rows=3" in msg
        assert "commit_ms=" in msg
        assert "retry_count=0" in msg

    async def test_slow_commit_emits_warning_event(self):
        """单批 commit 超过 500ms → EVENT_BATCH_COMMIT WARNING（outcome=slow_commit）。"""
        from app.services import sync_observability as obs

        db = AsyncMock()
        # perf_counter 调用序列（单批一次成功）：
        # 1) bulk_upsert start_ts → 10.0；2) 批 attempt_start → 100.0；
        # 3) commit_ms 采样 → 100.6（commit=600ms）；4) elapsed_ms → 10.5
        with (
            patch("app.services.sync_db_write.admission_controller", _mock_ac()),
            patch(
                "app.services.sync_db_write.time.perf_counter",
                side_effect=[10.0, 100.0, 100.6, 10.5],
            ),
            patch.object(obs.logger, "log") as mock_log,
        ):
            stats = await bulk_upsert_with_retry(
                db,
                [{"name": "slow"}],
                [],
                model=MagicMock(),
                label="slow_commit",
            )

        assert stats.batches == 1
        warnings = [c.args[1] for c in mock_log.call_args_list if c.args[0] == logging.WARNING]
        assert warnings, "超过 500ms 的单批 commit 应发射 WARNING"
        msg = warnings[-1]
        assert "event=sync_batch_commit" in msg
        assert "outcome=slow_commit" in msg
        assert "commit_ms=600.0" in msg
        assert "threshold_ms=500.0" in msg

    async def test_partial_progress_carried_on_chunked_write_error(self):
        """某批最终失败：ChunkedWriteError 携带已提交批统计，原异常为 __cause__。"""
        db = AsyncMock()
        db.commit.side_effect = [None, _busy_error(5), _busy_error(5)]
        with patch("app.services.sync_db_write.admission_controller", _mock_ac()):
            with patch("app.services.sync_db_write.random.uniform", side_effect=lambda a, b: 0.01):
                with pytest.raises(ChunkedWriteError) as exc_info:
                    await bulk_upsert_with_retry(
                        db,
                        [{"id": i} for i in range(4)],
                        [],
                        model=MagicMock(),
                        label="partial",
                        batch_size=2,
                        max_retries=2,
                    )

        err = exc_info.value
        assert err.stats.committed == 2  # 批 1 已提交，不得标记为未执行
        assert err.stats.batches == 1
        assert err.stats.retries == 1  # 批 2 重试 1 次后仍失败
        assert err.stats.scanned == 4
        assert isinstance(err.__cause__, sqlite3.OperationalError)

    async def test_real_file_sqlite_commits_visible_between_batches(self, tmp_path):
        """真实文件型 SQLite：每批独立 commit 后，另一连接立即可见已提交行。"""
        from sqlalchemy import Column, Integer, String
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        class ChunkRow(Base):
            __tablename__ = "chunk_rows"
            id = Column(Integer, primary_key=True)
            name = Column(String(50))

        db_path = tmp_path / "chunk_commit.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        session = session_factory()

        # spy commit：每次真实 commit 后，用另一连接读取已提交行数
        reads_after_commit = []
        real_commit = session.commit

        async def spied_commit():
            await real_commit()
            conn = sqlite3.connect(str(db_path))
            try:
                reads_after_commit.append(conn.execute("SELECT COUNT(*) FROM chunk_rows").fetchone()[0])
            finally:
                conn.close()

        session.commit = spied_commit  # type: ignore[method-assign]

        try:
            stats = await bulk_upsert_with_retry(
                session,
                [{"id": i, "name": f"n{i}"} for i in range(5)],
                [],
                model=ChunkRow,
                label="real_file_test",
                batch_size=2,
            )
        finally:
            await session.close()
            await engine.dispose()

        assert stats.batches == 3
        assert stats.committed == 5
        assert stats.changed == 5
        # 每批 commit 后另一连接都能读到已提交行（真实提交边界证据）
        assert reads_after_commit == [2, 4, 5]
