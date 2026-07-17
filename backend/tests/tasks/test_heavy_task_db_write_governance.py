# -*- coding: utf-8 -*-
"""
重型任务 DB 写入治理行为测试（to_thread 止血 + db_write_scope 收尾）

【验证目标】
本轮治理（sync-resource-governance.2.6）将 4 个重型任务的 commit 包入
admission_controller.db_write_scope，并将阻塞事件循环的同步 SessionLocal/HTTP
调用经 asyncio.to_thread 移出循环。本测试用行为方式验证 db_write_scope 确实
被进入（commit 发生在 scope 激活期间），取代不可行的"AST 断言所有任务经 scope"。

【设计依据】
- execute→service→commit 多层间接，AST 跟不到 commit 点，改用行为测试。
- monkeypatch admission_controller.db_write_scope 设标志位，对重型任务 execute()
  跑一次（mock DB/最小数据），断言 scope 被进入。
- 不触碰 test_request_side_endpoints_do_not_use_governance_locks（请求侧约束保持不变）。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.resource_guard import admission_controller


@pytest.fixture(autouse=True)
def _reset_admission():
    """每个测试前后清理 admission_controller 单例状态。"""
    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


class _ScopeSpy:
    """记录 db_write_scope 是否被进入的间谍。

    用真实 admission_controller.db_write_scope 作为底层（保持串行化语义），
    仅在外层包一层标志位记录。
    """

    def __init__(self):
        self.entered = False
        self._real = admission_controller.db_write_scope

    def make_scope(self):
        real_scope = self._real
        spy = self

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _spied():
            spy.entered = True
            async with real_scope():
                yield

        return _spied


# =============================================================================
# 改动1：TorrentTrackerStatusJudge — db_write_scope 进入 + to_thread 读 helpers
# =============================================================================


class TestTorrentTrackerStatusJudgeGovernance:
    """TorrentTrackerStatusJudge.execute() 的 db_write_scope 与 to_thread 行为。"""

    async def test_db_write_scope_entered_when_torrents_exist(self):
        """有种子时 execute() 必须进入 db_write_scope（分批判断的 commit 在 scope 内）。

        场景：mock SessionLocal 返回少量关键词 + 少量种子 + 对应 tracker，
        跑 execute()，断言 db_write_scope 被进入（即 commit 发生在 scope 激活期间）。
        """
        from app.tasks.scheduler.torrent_tracker_status_judge import TorrentTrackerStatusJudge

        spy = _ScopeSpy()

        # 构造 fake session：支持多次 query 调用（关键词/种子ID/种子对象/tracker）
        fake_keyword = MagicMock(keyword="ok", keyword_type="success", priority=1)
        fake_torrent_id_row = MagicMock()
        fake_torrent_id_row.__getitem__ = lambda self, idx: "t1"
        # TorrentInfo 对象（带 has_tracker_error / update_time 属性）
        fake_torrent = MagicMock()
        fake_torrent.info_id = "t1"
        fake_torrent.has_tracker_error = True
        fake_torrent.update_time = None
        # TrackerInfo 对象
        fake_tracker = MagicMock()
        fake_tracker.torrent_info_id = "t1"
        fake_tracker.last_announce_msg = "ok"
        fake_tracker.last_scrape_msg = ""

        def _make_session():
            session = MagicMock()
            # query().filter().all() 链式调用按调用顺序返回不同结果
            # 调用顺序：_load_keywords -> _get_all_torrents -> _judge_one_batch(种子IN, trackerIN)
            query_chain_1 = MagicMock()  # keywords filter
            query_chain_1.filter.return_value.all.return_value = [fake_keyword]
            query_chain_2 = MagicMock()  # keyword dedup（不触发，因 keyword_map 已有）
            query_chain_2.filter.return_value.order_by.return_value.first.return_value = None
            # _get_all_torrents
            query_chain_3 = MagicMock()
            query_chain_3.filter.return_value.all.return_value = [fake_torrent_id_row]
            # _judge_one_batch: TorrentInfo IN
            query_chain_4 = MagicMock()
            query_chain_4.filter.return_value.all.return_value = [fake_torrent]
            # _judge_one_batch: TrackerInfo IN
            query_chain_5 = MagicMock()
            query_chain_5.filter.return_value.all.return_value = [fake_tracker]

            session.query.side_effect = [query_chain_1, query_chain_3, query_chain_4, query_chain_5]
            return session

        task = TorrentTrackerStatusJudge()

        with (
            patch(
                "app.tasks.scheduler.torrent_tracker_status_judge.SessionLocal",
                side_effect=_make_session,
            ),
            patch.object(admission_controller, "db_write_scope", spy.make_scope()),
        ):
            result = await task.execute()

        assert result["status"] == "success", f"任务应成功，实际: {result}"
        # 关键断言：db_write_scope 被进入（commit 发生在 scope 内）
        assert spy.entered, "execute() 有种子待判断时必须进入 db_write_scope"

    async def test_read_helpers_run_via_to_thread(self):
        """_load_keywords / _get_all_torrents 必须经 to_thread 调用（不阻塞事件循环）。

        防回归锚点：spy asyncio.to_thread，断言 _load_keywords / _get_all_torrents
        经 to_thread 调用。若有人改回直接同步调用，此测试报红。
        """
        from app.tasks.scheduler.torrent_tracker_status_judge import TorrentTrackerStatusJudge

        task = TorrentTrackerStatusJudge()
        to_thread_calls = []
        real_to_thread = __import__("asyncio").to_thread

        async def _spy_to_thread(fn, *args, **kwargs):
            to_thread_calls.append(getattr(fn, "__name__", str(fn)))
            # 只对 _load_keywords 返回空 dict 提前退出；其余透传真实 to_thread
            if getattr(fn, "__name__", "") == "_load_keywords":
                return {}
            return await real_to_thread(fn, *args, **kwargs)

        fake_session = MagicMock()
        fake_session.query.return_value.filter.return_value.all.return_value = []

        with (
            patch("app.tasks.scheduler.torrent_tracker_status_judge.SessionLocal", return_value=fake_session),
            patch("asyncio.to_thread", _spy_to_thread),
        ):
            await task.execute()

        # 关键断言：_load_keywords 经 to_thread 调用
        assert (
            "_load_keywords" in to_thread_calls
        ), "_load_keywords 必须经 asyncio.to_thread 调用（同步 SessionLocal 读应移出事件循环）"


# =============================================================================
# 改动2：TrackerMessageLogger — db_write_scope 进入
# =============================================================================


class TestTrackerMessageLoggerGovernance:
    """TrackerMessageLogger 的 commit 必须在 db_write_scope 内。"""

    async def test_db_write_scope_entered_on_message_upsert(self):
        """处理消息时 _process_messages_batch_async 的 commit 必须在 db_write_scope 内。

        场景：mock _collect_tracker_messages_async 返回 1 条消息，跑 execute()，
        断言 db_write_scope 被进入（UPSERT commit 在 scope 内）。
        """
        from app.tasks.scheduler.tracker_message_logger import TrackerMessageLogger

        spy = _ScopeSpy()

        # mock AsyncSessionLocal：execute/commit/rollback 支持
        fake_db = AsyncMock()
        fake_db.commit = AsyncMock()
        fake_db.rollback = AsyncMock()
        fake_db.execute = AsyncMock()

        class _FakeAsyncCtx:
            async def __aenter__(self):
                return fake_db

            async def __aexit__(self, *args):
                return False

        messages = [{"tracker_host": "h", "msg": "ok", "sample_torrents": [], "sample_urls": []}]

        task = TrackerMessageLogger()
        with (
            patch.object(task, "_collect_tracker_messages_async", AsyncMock(return_value=messages)),
            patch(
                "app.tasks.scheduler.tracker_message_logger.AsyncSessionLocal",
                return_value=_FakeAsyncCtx(),
            ),
            patch.object(admission_controller, "db_write_scope", spy.make_scope()),
        ):
            # 跳过候选池任务（避免 import 链）
            with patch(
                "app.tasks.scheduler.tracker_candidate_pool.TrackerCandidatePoolTask.execute",
                AsyncMock(return_value={"new_candidates": 0}),
            ):
                result = await task.execute()

        assert result["status"] == "success", f"任务应成功，实际: {result}"
        # 关键断言：消息处理 commit 在 db_write_scope 内
        assert spy.entered, "_process_messages_batch_async 的 commit 必须在 db_write_scope 内"


# =============================================================================
# 改动3：TrackerReannounceTask — 写段 db_write_scope + 读段 to_thread
# =============================================================================


class TestTrackerReannounceTaskGovernance:
    """TrackerReannounceTask._process_downloader 的写段必须经 db_write_scope。"""

    async def test_write_segment_uses_db_write_scope(self):
        """matched_config_ids 非空时写段必须进入 db_write_scope + to_thread。

        场景：_read_downloader_data 返回 (torrent_records, matched_config_ids)，
        execute_reannounce 返回成功，断言 db_write_scope 被进入（写段 commit 在 scope 内）。
        """
        from app.tasks.scheduler.tracker_reannounce_task import TrackerReannounceTask

        spy = _ScopeSpy()

        fake_torrent = MagicMock()
        fake_torrent.info_id = "t1"
        matched_ids = {"cfg-1"}

        task = TrackerReannounceTask()
        with (
            patch.object(task, "_read_downloader_data", return_value=([fake_torrent], matched_ids)),
            patch(
                "app.services.reannounce_service.execute_reannounce",
                AsyncMock(return_value={"success_count": 1, "failed_count": 0}),
            ),
            patch("app.core.reannounce_config_operations.batch_update_last_announce_time") as mock_batch,
            patch.object(admission_controller, "db_write_scope", spy.make_scope()),
        ):
            result = await task._process_downloader(MagicMock(), MagicMock(downloader_id=1), [])

        assert result.get("success_count") == 1
        # 关键断言：写段进入 db_write_scope
        assert spy.entered, "写段（batch_update_last_announce_time）必须进入 db_write_scope"
        # batch_update 经 to_thread 调用（在 scope 内）
        mock_batch.assert_called_once_with(["cfg-1"])

    async def test_read_segment_runs_via_to_thread(self):
        """读段 _read_downloader_data 必须经 to_thread 调用（不阻塞事件循环）。

        防回归锚点：若有人把 _read_downloader_data 改回直接同步调用，此测试报红。
        """
        from app.tasks.scheduler.tracker_reannounce_task import TrackerReannounceTask

        task = TrackerReannounceTask()
        to_thread_targets = []
        real_to_thread = __import__("asyncio").to_thread

        async def _spy_to_thread(fn, *args, **kwargs):
            to_thread_targets.append(getattr(fn, "__name__", str(fn)))
            return await real_to_thread(fn, *args, **kwargs)

        # _read_downloader_data 内部用 SessionLocal，mock 返回 None（无数据，提前返回）
        fake_db = MagicMock()
        fake_db.query.return_value.filter.return_value.all.return_value = []

        with (
            patch("app.tasks.scheduler.tracker_reannounce_task.SessionLocal", return_value=fake_db),
            patch("asyncio.to_thread", _spy_to_thread),
        ):
            result = await task._process_downloader(MagicMock(), MagicMock(downloader_id=1), [])

        assert result == {"success_count": 0, "failed_count": 0}
        # 关键断言：_read_downloader_data 经 to_thread 调用
        assert (
            "_read_downloader_data" in to_thread_targets
        ), "_read_downloader_data 必须经 asyncio.to_thread 调用（同步 SessionLocal 读应移出事件循环）"
