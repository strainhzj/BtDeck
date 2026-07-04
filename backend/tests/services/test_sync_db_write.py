# -*- coding: utf-8 -*-
"""
sync_db_write 工具单测

【覆盖目标】
1. has_torrent_info_changes：业务字段变化检测，忽略 update_time/PK。
2. has_tracker_changes：6 字段检测，None==""/strip 归一化，死字段不对比。
3. bulk_upsert_with_retry：db_write_scope 进入 + bulk_insert/update_mappings + commit + retry + 异常透传。

【测试分层】
- 纯函数（has_*_changes）：直接断言，无 mock。
- bulk_upsert_with_retry：mock db + mock admission_controller.db_write_scope，验证调用契约。
- 真实 SQLite 部分索引测试在 Step 5 的 test_torrents_async_db_governance.py 补充。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sync_db_write import (
    _TORRENT_INFO_IGNORE_KEYS,
    _TRACKER_CHANGE_FIELDS,
    bulk_upsert_with_retry,
    has_torrent_info_changes,
    has_tracker_changes,
)


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


class TestBulkUpsertWithRetry:
    """bulk_upsert_with_retry 调用契约。"""

    async def test_noop_when_both_lists_empty(self):
        """to_insert 和 to_update 都为空时直接返回，不调 db。"""
        db = MagicMock()
        await bulk_upsert_with_retry(db, [], [], model=MagicMock(), label="test")
        db.run_sync.assert_not_called()
        db.commit.assert_not_called()

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
                with patch("app.api.endpoints.torrents_async._retry_on_db_lock") as mock_retry:

                    async def _run(func, **kw):
                        await func()

                    mock_retry.side_effect = _run

                    await bulk_upsert_with_retry(db, to_insert, [], model=MagicMock(), label="insert_only")

            # ★ 关键断言：db_writer.acquire 被调用（证明进入了 db_write_scope）
            acquire_spy.assert_awaited()
            db.commit.assert_awaited()
            admission_controller.reset_state()

    async def test_insert_and_update_both_called(self):
        """to_insert 和 to_update 都有数据时，bulk_insert + bulk_update 都被调。"""
        db = AsyncMock()
        to_insert = [{"name": "a"}]
        to_update = [{"info_id": 1, "name": "b"}]

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_scope():
            yield

        with patch("app.services.sync_db_write.admission_controller") as mock_ac:
            mock_ac.db_write_scope = fake_scope
            with patch("app.api.endpoints.torrents_async._retry_on_db_lock") as mock_retry:

                async def _run(func, **kw):
                    await func()

                mock_retry.side_effect = _run

                await bulk_upsert_with_retry(db, to_insert, to_update, model=MagicMock(), label="both")

        # 至少 2 次 run_sync（1 insert + 1 update）
        assert db.run_sync.call_count >= 2
        db.commit.assert_awaited()

    async def test_retry_on_db_lock_invoked_with_base_delay_1(self):
        """retry 必须用 base_delay=1.0（db_write_scope 串行化后短退避，非默认 10s）。"""
        db = AsyncMock()
        with patch("app.services.sync_db_write.admission_controller") as mock_ac:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_scope():
                yield

            mock_ac.db_write_scope = fake_scope
            with patch("app.api.endpoints.torrents_async._retry_on_db_lock") as mock_retry:

                async def _run(func, **kw):
                    await func()

                mock_retry.side_effect = _run

                await bulk_upsert_with_retry(db, [{"a": 1}], [], model=MagicMock(), label="delay_test")

                # 验证 retry 调用参数含 base_delay=1.0
                _, kwargs = mock_retry.call_args
                assert (
                    kwargs.get("base_delay") == 1.0
                ), f"base_delay 应为 1.0（串行化后短退避），实际 {kwargs.get('base_delay')}"

    async def test_rollback_provided_to_retry(self):
        """retry 必须收到 rollback 回调（锁冲突时回滚事务）。"""
        db = AsyncMock()
        with patch("app.services.sync_db_write.admission_controller") as mock_ac:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_scope():
                yield

            mock_ac.db_write_scope = fake_scope
            with patch("app.api.endpoints.torrents_async._retry_on_db_lock") as mock_retry:

                async def _run(func, **kw):
                    await func()

                mock_retry.side_effect = _run

                await bulk_upsert_with_retry(db, [{"a": 1}], [], model=MagicMock(), label="rollback_test")

                _, kwargs = mock_retry.call_args
                assert "rollback" in kwargs, "retry 必须收到 rollback 回调"
                assert kwargs["rollback"] == db.rollback

    async def test_exception_propagates(self):
        """_do_bulk 抛异常时原样向上抛（不吞）。"""
        db = AsyncMock()
        db.commit.side_effect = RuntimeError("commit failed")

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_scope():
            yield

        with patch("app.services.sync_db_write.admission_controller") as mock_ac:
            mock_ac.db_write_scope = fake_scope
            with patch("app.api.endpoints.torrents_async._retry_on_db_lock") as mock_retry:

                async def _run(func, **kw):
                    await func()

                mock_retry.side_effect = _run

                with pytest.raises(RuntimeError, match="commit failed"):
                    await bulk_upsert_with_retry(db, [{"a": 1}], [], model=MagicMock(), label="exc_test")
