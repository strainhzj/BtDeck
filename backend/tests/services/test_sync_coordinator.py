# -*- coding: utf-8 -*-
"""
SyncCoordinator 单元测试（W2-1，PLANS/sync-database-blocking-remediation.md）

覆盖行为契约：
1. 手动与 Cron 触发相同输入时调用相同 Coordinator 方法及同一写入服务
   （断言 run_sync 被调、参数 trigger 区分）。
2. 两个相同任务竞争时只允许一个运行（第二个返回 already_running，
   使用 admission_controller 真实 running 集）。
3. admission 超时（wait_timeout）→ skipped + skip_reason="resource_busy"。
4. 取消（is_cancelled 在阶段间返回 True）→ cancelled 且已提交批次保留
   （mock 写入函数断言其被调用过）。
5. 下载器离线（store 无该下载器/客户端为空）→ failed + errors 含可读信息。
6. 旧 API 响应兼容：legacy adapter 转发后返回旧 dict 结构（status/message/
   downloader_type/nickname），手动入口返回 task_id 的 HTTP 契约不变。
7. dry_run 不执行写入（写入函数不被调）。
8. legacy adapter：SYNC_CANONICAL_COORDINATOR_ENABLED=False 走旧路径、
   True 走 Coordinator（patch 断言调用分支）。
9. W4-1 第二部分：run_id 贯穿 + 阶段事件顺序还原（一次 info run_sync 全流程
   捕获结构化事件，按 run_id 过滤断言 START→ADMISSION→BATCH_COMMIT→CHECKPOINT；
   run_sync 结束后 run_id 上下文被清空）。
10. tracker-only 原始同步成功后才执行行级 Tracker 状态同步，且调用顺序固定。
"""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.sync_coordinator import SyncRequest, SyncResult, run_sync
from app.tasks.resource_guard import SKIP_WAIT_TIMEOUT, AdmissionResult, admission_controller

# =============================================================================
# fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_admission():
    """每个测试前后清理 admission_controller 单例状态（防进程级状态泄漏）。"""
    admission_controller.reset_state()
    yield
    admission_controller.reset_state()


def make_vo(downloader_id="dl_001", client=None, fail_time=0, downloader_type=0, nickname="test-dl"):
    """构造伪下载器 VO（app.state.store.get_snapshot() 返回的元素）。"""
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.client = client
    vo.fail_time = fail_time
    vo.downloader_type = downloader_type
    vo.nickname = nickname
    vo.host = "192.168.1.1"
    vo.port = 8080
    vo.username = "admin"
    vo.password = "password"
    vo.torrent_save_path = "/downloads"
    return vo


def make_fake_app(vos=None):
    """构造带 store 的伪 FastAPI 实例。"""
    store = SimpleNamespace()
    store.get_snapshot = AsyncMock(return_value=vos or [])
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.store = store
    return app


def make_downloader_info(downloader_id="dl_001", downloader_type=0, nickname="test-dl"):
    """构造 downloader_info dict（与手动入口/任务文件传入的结构一致）。"""
    return {
        "downloader_id": downloader_id,
        "nickname": nickname,
        "host": "192.168.1.1",
        "port": 8080,
        "username": "admin",
        "password": "password",
        "downloader_type": downloader_type,
        "torrent_save_path": "/downloads",
        "enabled": "1",
        "status": "1",
    }


# =============================================================================
# 1. 手动与 Cron 触发调用同一 Coordinator 方法（trigger 区分）
# =============================================================================


class TestManualAndCronConvergeOnCoordinator:
    """手动与定时任务统一走 run_sync，参数 trigger 区分来源。"""

    async def test_manual_entry_calls_run_sync_with_trigger_manual(self):
        """手动入口后台执行体调 run_sync（sync_type=full, trigger=manual）。"""
        from app.api.endpoints.torrent_sync import _execute_manual_sync_via_coordinator

        with patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync:
            mock_run_sync.return_value = SyncResult(outcome="success", run_id="r-manual", message="ok")
            result = await _execute_manual_sync_via_coordinator(make_downloader_info())

        assert mock_run_sync.await_count == 1
        req: SyncRequest = mock_run_sync.await_args.args[0]
        assert req.sync_type == "full"
        assert req.trigger == "manual"
        assert req.downloader_ids == ["dl_001"]
        # 旧 dict 结构契约不变
        assert result["status"] == "success"
        assert result["nickname"] == "test-dl"
        assert result["downloader_type"] == "0"

    async def test_cron_info_task_calls_run_sync_with_trigger_cron(self):
        """info 定时任务委托 run_sync（sync_type=info, trigger=cron）。"""
        from app.tasks.scheduler.torrent_sync.torrent_info_sync_task import TorrentInfoSyncTask

        with patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync:
            mock_run_sync.return_value = SyncResult(outcome="success", run_id="r-cron", message="ok")
            result = await TorrentInfoSyncTask()._sync_torrent_info_only(make_downloader_info())

        assert mock_run_sync.await_count == 1
        req: SyncRequest = mock_run_sync.await_args.args[0]
        assert req.sync_type == "info"
        assert req.trigger == "cron"
        assert req.downloader_ids == ["dl_001"]
        # 任务文件兼容 dict 结构
        assert result["status"] == "success"
        assert result["nickname"] == "test-dl"

    async def test_cron_tracker_task_calls_run_sync_with_trigger_cron(self):
        """tracker 定时任务委托 run_sync（sync_type=tracker, trigger=cron）。"""
        from app.tasks.scheduler.torrent_sync.tracker_sync_task import TrackerSyncTask

        app = make_fake_app([make_vo(client=MagicMock())])
        with (
            patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync,
            patch.object(TrackerSyncTask, "get_valid_downloaders", new=AsyncMock()) as mock_get_valid,
        ):
            mock_get_valid.return_value = [make_vo(downloader_id="dl_002", client=MagicMock())]
            mock_run_sync.return_value = SyncResult(
                outcome="success",
                run_id="r-tracker-cron",
                message="ok",
                details={"successful_syncs": 1, "failed_syncs": 0},
            )
            result = await TrackerSyncTask().execute(app=app)

        assert mock_run_sync.await_count == 1
        req: SyncRequest = mock_run_sync.await_args.args[0]
        assert req.sync_type == "tracker"
        assert req.trigger == "cron"
        assert req.downloader_ids == ["dl_002"]
        # 任务页兼容 dict 结构
        assert result["status"] == "success"
        assert result["successful_syncs"] == 1
        assert result["total_downloaders"] == 1

    async def test_run_sync_info_uses_governed_write_service(self):
        """run_sync(info) 调用 W1-1 已治理的 info-only 写入函数（手动/Cron 同源）。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with (
            patch(
                "app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()
            ) as mock_info_only,
            patch(
                "app.services.sync_coordinator._reconcile_torrent_file_backups",
                new=AsyncMock(),
            ) as reconcile_backups,
        ):
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )

        assert result.outcome == "success"
        assert mock_info_only.await_count == 1
        # 写入函数收到同一 db 会话与下载器对象（client 以关键字传入）
        assert mock_info_only.await_args.args[0] is not None
        downloaders = mock_info_only.await_args.args[1]
        assert len(downloaders) == 1
        reconcile_backups.assert_awaited_once()

    async def test_run_sync_full_also_reconciles_backups(self):
        """full 同步路径在下载器完成后同样触发备份增量补偿。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with (
            patch("app.api.endpoints.torrents_async.qb_add_torrents_async", new=AsyncMock()) as mock_full_sync,
            patch(
                "app.services.sync_coordinator._reconcile_torrent_file_backups",
                new=AsyncMock(),
            ) as reconcile_backups,
            patch(
                "app.services.sync_coordinator._get_cached_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            result = await run_sync(
                SyncRequest(sync_type="full", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )

        assert result.outcome == "success"
        assert mock_full_sync.await_count == 1
        reconcile_backups.assert_awaited_once()

    async def test_run_sync_tracker_does_not_reconcile_backups(self):
        """tracker-only 同步不改种子信息，不触发备份补偿。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with (
            patch(
                "app.api.endpoints.torrents_async.qb_sync_trackers_only_async",
                new=AsyncMock(
                    return_value={
                        "status": "success",
                        "tracker_count": 0,
                        "torrent_count": 0,
                        "cycle_complete": True,
                    }
                ),
            ) as mock_tracker,
            patch(
                "app.services.sync_coordinator._reconcile_torrent_file_backups",
                new=AsyncMock(),
            ) as reconcile_backups,
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_001"], trigger="cron"),
                app=app,
            )

        assert result.outcome == "success"
        assert mock_tracker.await_count == 1
        reconcile_backups.assert_not_awaited()

    async def test_backup_reconcile_failure_does_not_block_info_sync(self):
        """补偿抛异常时只记入 errors/details，下载器信息同步结果保持 success。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with (
            patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()),
            patch(
                "app.services.torrent_file_backup_manager.TorrentFileBackupManagerService." "reconcile_missing_backups",
                new=AsyncMock(side_effect=RuntimeError("nas unreachable")),
            ),
        ):
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="cron"),
                app=app,
            )

        assert result.outcome == "success"
        assert any("种子文件增量备份失败" in message for message in result.errors)
        failed_detail = result.details.get("torrent_file_backup", {}).get("dl_001")
        assert failed_detail == {"status": "failed", "error": "nas unreachable"}


# =============================================================================
# 2. 两个相同任务竞争：只允许一个运行
# =============================================================================


class TestSameTaskCompetition:
    """两个相同任务竞争时第二个返回 already_running（admission 真实 running 集）。"""

    async def test_second_same_task_returns_already_running(self):
        """同 downloader + sync_type 并发：第二个 run_sync 返回 already_running。"""
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocking_sync(db, downloaders, client=None):
            started.set()
            await release.wait()

        app = make_fake_app([make_vo(client=MagicMock())])
        with patch(
            "app.api.endpoints.torrents_async.qb_add_torrents_info_only_async",
            new=blocking_sync,
        ):
            first_task = asyncio.create_task(
                run_sync(
                    SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                    app=app,
                )
            )
            await asyncio.wait_for(started.wait(), timeout=5)

            # 第二个相同任务：同类去重（admission running 集）→ already_running
            second = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )
            assert second.outcome == "already_running"
            assert second.skip_reason == "already_running"

            release.set()
            first = await asyncio.wait_for(first_task, timeout=5)
            assert first.outcome == "success"

    async def test_force_allows_second_run(self):
        """force=True 跳过幂等去重：第二个任务可排队/执行（不同运行键不冲突）。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()):
            first = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )
            second = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual", force=True),
                app=app,
            )
        assert first.outcome == "success"
        assert second.outcome == "success"


# =============================================================================
# 3. admission 超时 → skipped + resource_busy
# =============================================================================


class TestAdmissionTimeout:
    """admission wait_timeout 超时 → skipped + skip_reason="resource_busy"。"""

    async def test_wait_timeout_returns_skipped_resource_busy(self):
        """acquire 返回 SKIP_WAIT_TIMEOUT 时结果标记 skipped/resource_busy。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with patch.object(
            admission_controller,
            "acquire",
            new=AsyncMock(
                return_value=AdmissionResult(
                    admitted=False,
                    skip_reason=SKIP_WAIT_TIMEOUT,
                    wait_seconds=30.0,
                    running_count=1,
                    queued_count=0,
                    task_code="torrent_info_sync_ac608e4d",
                )
            ),
        ):
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )

        assert result.outcome == "skipped"
        assert result.skip_reason == "resource_busy"
        assert result.details.get("admission_wait_ms") == pytest.approx(30000.0, abs=1.0)
        # 未执行任何写入
        assert result.scanned == 0


# =============================================================================
# 4. 取消语义：已提交批次保留
# =============================================================================


class TestCancellation:
    """is_cancelled 在阶段间返回 True → cancelled，且已提交批次保留。"""

    async def test_cancel_between_downloaders_keeps_committed_batches(self):
        """第一个下载器写入已执行（批次保留），第二个下载器前取消。"""
        app = make_fake_app(
            [
                make_vo(downloader_id="dl_001", client=MagicMock()),
                make_vo(downloader_id="dl_002", client=MagicMock()),
            ]
        )
        state = {"write_calls": 0}

        async def counting_sync(db, downloaders, client=None):
            state["write_calls"] += 1

        def is_cancelled():
            # 第一个下载器完成后取消（阶段间检查点）
            return state["write_calls"] >= 1

        with patch(
            "app.api.endpoints.torrents_async.qb_add_torrents_info_only_async",
            new=counting_sync,
        ):
            result = await run_sync(
                SyncRequest(
                    sync_type="info",
                    downloader_ids=["dl_001", "dl_002"],
                    trigger="manual",
                    is_cancelled=is_cancelled,
                ),
                app=app,
            )

        # 已提交批次保留：第一个下载器的写入被调用过
        assert state["write_calls"] == 1
        assert result.outcome == "cancelled"
        assert any("取消" in err for err in result.errors)
        assert result.details.get("successful_syncs") == 1

    async def test_cancel_before_any_commit_returns_cancelled(self):
        """阶段起始即取消：无任何写入，outcome=cancelled。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()) as mock_write:
            result = await run_sync(
                SyncRequest(
                    sync_type="info",
                    downloader_ids=["dl_001"],
                    trigger="manual",
                    is_cancelled=lambda: True,
                ),
                app=app,
            )

        assert mock_write.await_count == 0
        assert result.outcome == "cancelled"

    async def test_deadline_expiry_marks_cancelled(self):
        """deadline=0 到期：不执行写入，outcome=cancelled。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()) as mock_write:
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual", deadline=0.0),
                app=app,
            )

        assert mock_write.await_count == 0
        assert result.outcome == "cancelled"
        assert any("deadline" in err for err in result.errors)


# =============================================================================
# 5. Tracker 原始同步与行级状态同步顺序
# =============================================================================


class TestTrackerStatusPhaseOrdering:
    """Tracker 行级联合判定必须在原始 Tracker 数据同步完成后执行。"""

    async def test_tracker_status_phase_runs_after_raw_tracker_sync(self):
        app = make_fake_app([make_vo(client=MagicMock())])
        calls = []

        async def raw_tracker_sync(*args, **kwargs):
            calls.append("raw_tracker_sync")
            return {
                "status": "success",
                "message": "ok",
                "scanned": 1,
                "changed": 1,
                "batches": 1,
                "cycle_complete": True,
            }

        async def tracker_status_sync():
            calls.append("tracker_status_sync")
            return {"status": "success", "changed": 1}

        with (
            patch(
                "app.api.endpoints.torrents_async.qb_sync_trackers_only_async",
                new=raw_tracker_sync,
            ),
            patch(
                "app.api.endpoints.torrent_sync.update_tracker_status_from_keywords",
                new=tracker_status_sync,
            ),
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_001"], trigger="cron"),
                app=app,
            )

        assert calls == ["raw_tracker_sync", "tracker_status_sync"]
        assert result.details["successful_syncs"] == 1
        assert result.details["tracker_status_update"]["changed"] == 1

    async def test_tracker_status_phase_is_skipped_when_raw_sync_fails(self):
        app = make_fake_app([make_vo(client=MagicMock())])
        status_sync = AsyncMock()

        async def failed_raw_tracker_sync(*args, **kwargs):
            return {"status": "failed", "message": "raw sync failed"}

        with (
            patch(
                "app.api.endpoints.torrents_async.qb_sync_trackers_only_async",
                new=failed_raw_tracker_sync,
            ),
            patch(
                "app.api.endpoints.torrent_sync.update_tracker_status_from_keywords",
                new=status_sync,
            ),
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_001"], trigger="cron"),
                app=app,
            )

        assert status_sync.await_count == 0
        assert result.details["successful_syncs"] == 0

    async def test_tracker_status_exception_is_logged_and_keeps_error_in_result(self):
        """状态阶段异常仍保持原 outcome，但必须有 traceback 与 sync_error 事件。"""
        app = make_fake_app([make_vo(client=MagicMock())])

        async def raw_tracker_sync(*args, **kwargs):
            return {"status": "success", "message": "ok", "torrent_count": 1, "tracker_count": 1}

        async def failed_tracker_status_sync():
            raise RuntimeError("tracker status boom")

        with (
            patch("app.api.endpoints.torrents_async.qb_sync_trackers_only_async", new=raw_tracker_sync),
            patch(
                "app.api.endpoints.torrent_sync.update_tracker_status_from_keywords",
                new=failed_tracker_status_sync,
            ),
            patch("app.services.sync_coordinator.logger.error") as mock_error,
            patch("app.services.sync_coordinator.log_event") as mock_event,
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_001"], trigger="cron"),
                app=app,
            )

        assert result.outcome == "success"
        assert any("Tracker 状态更新失败" in error for error in result.errors)
        assert any("tracker_status" in str(call.args) for call in mock_error.call_args_list)
        assert any(call.args and call.args[0] == "sync_error" for call in mock_event.call_args_list)


# =============================================================================
# 5. 下载器离线 → failed + errors 可读
# =============================================================================


class TestDownloaderOffline:
    """store 无该下载器 / 客户端为空 → failed + errors 含可读信息。"""

    async def test_missing_downloader_in_store_returns_failed(self):
        """store 中不存在指定下载器 → failed + errors 含可读信息。"""
        app = make_fake_app([make_vo(downloader_id="dl_other", client=MagicMock())])
        result = await run_sync(
            SyncRequest(sync_type="info", downloader_ids=["dl_missing"], trigger="manual"),
            app=app,
        )

        assert result.outcome == "failed"
        assert any("dl_missing" in err and "store" in err for err in result.errors)

    @pytest.mark.parametrize("sync_type", ["info", "tracker", "full"])
    async def test_empty_client_for_all_sync_types_returns_failed(self, sync_type):
        """任何同步类型都不能在 store 客户端为空时 fallback 自建连接。"""
        app = make_fake_app([make_vo(client=None)])
        result = await run_sync(
            SyncRequest(sync_type=sync_type, downloader_ids=["dl_001"], trigger="manual"),
            app=app,
        )

        assert result.outcome == "failed"
        assert any("缓存客户端连接" in err for err in result.errors)

    async def test_unsupported_type_returns_failed(self):
        """不支持的下载器类型 → failed + errors。"""
        app = make_fake_app([make_vo(downloader_type=99, client=MagicMock())])
        result = await run_sync(
            SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
            app=app,
        )

        assert result.outcome == "failed"
        assert any("不支持的下载器类型" in err for err in result.errors)

    async def test_no_valid_downloaders_returns_no_action(self):
        """未指定下载器且 store 无有效下载器 → no_action。"""
        app = make_fake_app([make_vo(fail_time=5, client=MagicMock())])
        result = await run_sync(SyncRequest(sync_type="info", trigger="cron"), app=app)

        assert result.outcome == "no_action"


# =============================================================================
# 6. 旧 API 响应兼容（legacy adapter 转发）
# =============================================================================


class TestLegacyAdapterCompatibility:
    """torrent_sync_db_async 作为 legacy adapter 保持旧返回结构。"""

    async def test_adapter_returns_legacy_dict_structure(self):
        """开关开启时 adapter 转发 run_sync 并返回旧 dict 结构。"""
        from app.api.endpoints.torrent_sync import torrent_sync_db_async

        with (
            patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync,
            patch.object(settings, "SYNC_CANONICAL_COORDINATOR_ENABLED", True),
        ):
            mock_run_sync.return_value = SyncResult(
                outcome="success", run_id="r-adapter", message="qBittorrent下载器 test-dl 同步成功"
            )
            result = await torrent_sync_db_async(make_downloader_info())

        req: SyncRequest = mock_run_sync.await_args.args[0]
        assert req.sync_type == "full"
        assert req.downloader_ids == ["dl_001"]
        # 旧契约字段齐全
        assert result["status"] == "success"
        assert result["message"]
        assert result["nickname"] == "test-dl"
        assert "downloader_type" in result

    async def test_manual_entry_http_contract_keeps_task_id(self):
        """sync_single_downloader 返回 task_id 结构不变（直接调端点函数）。"""
        from app.api.endpoints.torrent_sync import SyncSingleRequest, sync_single_downloader

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.client.port = 12345
        request.headers = {"user-agent": "test"}
        request.url.path = "/api/v1/torrents/sync-single"

        db = MagicMock()
        downloader = MagicMock()
        downloader.downloader_id = "dl_001"
        downloader.nickname = "test-dl"
        downloader.downloader_type = "qbittorrent"
        downloader.host = "192.168.1.1"
        downloader.port = 8080
        downloader.username = "admin"
        downloader.password = "password"
        downloader.torrent_save_path = "/downloads"
        downloader.enabled = True
        downloader.status = "1"
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = downloader
        db.execute = AsyncMock(return_value=execute_result)

        from app.core.background_task_manager import task_manager, TaskStatus  # noqa: F401

        with (
            patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync,
            patch.object(settings, "SYNC_CANONICAL_COORDINATOR_ENABLED", True),
            # 让后台执行体真正调度到事件循环（等价 asyncio.create_task 语义）
            patch(
                "app.api.endpoints.torrent_sync.asyncio.create_task",
                side_effect=lambda coro, **_kwargs: asyncio.ensure_future(coro),
            ),
        ):
            mock_run_sync.return_value = SyncResult(outcome="success", run_id="r-http", message="ok")
            response = await sync_single_downloader(
                request,
                SyncSingleRequest(downloader_id="dl_001"),
                _user=MagicMock(),
                db=db,
            )

            # HTTP 契约：返回 task_id / downloader_id / status / query_url
            assert response.status == "success"
            data = response.data
            assert data["task_id"]
            assert data["downloader_id"] == "dl_001"
            assert data["query_url"] == f"/torrents/sync-status/{data['task_id']}"

            # 等待后台执行体完成（create_task 在端点返回后于事件循环中运行；
            # 必须在 patch 上下文内等待，否则后台执行体将使用真实 run_sync）
            task = task_manager.get_task(data["task_id"])
            for _ in range(200):
                if task is not None and task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    break
                await asyncio.sleep(0.01)
                task = task_manager.get_task(data["task_id"])

            # 后台执行体经 Coordinator（trigger=manual）
            assert (
                mock_run_sync.await_count == 1
            ), f"run_sync 未被后台执行体调用，task.status={task.status if task else None}"
            req: SyncRequest = mock_run_sync.await_args.args[0]
            assert req.trigger == "manual"
            assert req.sync_type == "full"
            # TaskLog 记录结果
            assert task is not None
            assert task.status == TaskStatus.SUCCESS
            assert task.result["status"] == "success"


# =============================================================================
# 7. dry_run 不执行写入
# =============================================================================


class TestDryRun:
    """dry_run 只读演练：不执行任何下载器调用与写入。"""

    async def test_dry_run_does_not_call_write_functions(self):
        """dry_run 时 info-only 写入函数不被调用，outcome=no_action。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with (
            patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=AsyncMock()) as mock_qb,
            patch("app.api.endpoints.torrents_async.tr_add_torrents_info_only_async", new=AsyncMock()) as mock_tr,
        ):
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual", dry_run=True),
                app=app,
            )

        assert mock_qb.await_count == 0
        assert mock_tr.await_count == 0
        assert result.outcome == "no_action"
        assert "dry_run" in result.message

    async def test_dry_run_tracker_does_not_call_write_functions(self):
        """dry_run 时 tracker-only 写入函数不被调用。"""
        app = make_fake_app([make_vo(client=MagicMock())])
        with (
            patch("app.api.endpoints.torrents_async.qb_sync_trackers_only_async", new=AsyncMock()) as mock_qb,
            patch("app.api.endpoints.torrents_async.tr_sync_trackers_only_async", new=AsyncMock()) as mock_tr,
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_001"], trigger="cron", dry_run=True),
                app=app,
            )

        assert mock_qb.await_count == 0
        assert mock_tr.await_count == 0
        assert result.outcome == "no_action"


# =============================================================================
# 8. legacy adapter 开关分支
# =============================================================================


class TestLegacyAdapterSwitch:
    """SYNC_CANONICAL_COORDINATOR_ENABLED 控制 adapter 走新/旧路径。"""

    async def test_switch_off_uses_legacy_impl(self):
        """开关关闭：torrent_sync_db_async 走旧直接调用 qb/tr_add_torrents_async 路径。"""
        from app.api.endpoints.torrent_sync import torrent_sync_db_async

        with (
            patch.object(settings, "SYNC_CANONICAL_COORDINATOR_ENABLED", False),
            patch("app.api.endpoints.torrents_async.qb_add_torrents_async", new=AsyncMock()) as mock_full,
            patch(
                "app.services.sync_coordinator._get_cached_client",
                new=AsyncMock(return_value=MagicMock()),
            ) as mock_cached_client,
            patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync,
        ):
            result = await torrent_sync_db_async(make_downloader_info())

        # 旧路径：全量函数被调，run_sync 不被调
        assert mock_full.await_count == 1
        mock_cached_client.assert_awaited_once()
        assert mock_run_sync.await_count == 0
        assert result["status"] == "success"

    async def test_switch_on_uses_coordinator(self):
        """开关开启：torrent_sync_db_async 转发 run_sync，全量函数不被直接调用。"""
        from app.api.endpoints.torrent_sync import torrent_sync_db_async

        with (
            patch.object(settings, "SYNC_CANONICAL_COORDINATOR_ENABLED", True),
            patch("app.api.endpoints.torrents_async.qb_add_torrents_async", new=AsyncMock()) as mock_full,
            patch("app.services.sync_coordinator.run_sync", new=AsyncMock()) as mock_run_sync,
        ):
            mock_run_sync.return_value = SyncResult(outcome="success", run_id="r-switch", message="ok")
            result = await torrent_sync_db_async(make_downloader_info())

        assert mock_run_sync.await_count == 1
        assert mock_full.await_count == 0
        assert result["status"] == "success"


# =============================================================================
# 9. W4-1 第二部分：run_id 贯穿 + 阶段事件顺序还原
# =============================================================================


class TestObservabilityRunIdStageOrder:
    """一次 run_sync 全流程的事件可按 run_id 还原完整阶段顺序。"""

    async def test_run_sync_events_ordered_by_run_id(self, caplog):
        """info run：START→ADMISSION→BATCH_COMMIT→CHECKPOINT；结束后上下文清空。"""
        from app.services import sync_observability as obs

        class _FakeSession:
            """伪 AsyncSession：run_sync/commit 均 no-op（事件顺序测试不落库）。"""

            def __init__(self):
                self.commits = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def run_sync(self, fn):
                return None

            async def commit(self):
                self.commits += 1

            async def rollback(self):
                pass

        @asynccontextmanager
        async def _fake_write_scope():
            yield

        mock_ac = MagicMock()
        mock_ac.db_write_scope.side_effect = lambda: _fake_write_scope()

        app = make_fake_app([make_vo(client=MagicMock())])

        async def fake_info_sync(db, downloaders, client=None):
            # 复用真实 bulk_upsert_with_retry（W1-1 分批提交路径），产生真实
            # BATCH_COMMIT 事件；250 行按默认 200 批大小应产生 ≥2 次真实批提交
            from app.services.sync_db_write import bulk_upsert_with_retry

            stats = await bulk_upsert_with_retry(
                db,
                [{"name": f"torrent-{i}"} for i in range(250)],
                [],
                model=MagicMock(),
                label="order_test",
            )
            assert stats.batches >= 2

        with (
            patch("app.database.AsyncSessionLocal", new=_FakeSession),
            patch("app.api.endpoints.torrents_async.qb_add_torrents_info_only_async", new=fake_info_sync),
            patch("app.services.sync_db_write.admission_controller", new=mock_ac),
            patch.object(obs.logger, "log", wraps=obs.logger.log) as spy_log,
            # 注：不用 caplog 断言——仓库会话级 fixture 的 alembic fileConfig 会把
            # app.* logger 级别抬高/禁用（见 test_sync_observability 注释），INFO 级
            # event 日志未必进入 caplog.records；spy 直接捕获 log() 调用更可靠。
        ):
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )

        assert result.outcome == "success"
        # run_sync 结束后 run_id 上下文必须清空（finally clear_run_id）
        assert obs.current_run_id() is None

        run_id = result.run_id
        assert run_id and run_id.startswith("sync-")
        # spy 捕获 log() 的位置参数：logger.log(level, msg)，msg 即格式化的 event 行
        event_lines = [
            c.args[1]
            for c in spy_log.call_args_list
            if isinstance(c.args[1], str) and c.args[1].startswith("event=") and f"run_id={run_id}" in c.args[1]
        ]
        assert event_lines, "应捕获到带 run_id 的结构化事件"
        names = [line.split(" ", 1)[0].split("=", 1)[1] for line in event_lines]

        # 阶段顺序：START → ADMISSION → BATCH_COMMIT → CHECKPOINT
        expected = [
            obs.EVENT_SYNC_RUN_START,
            obs.EVENT_ADMISSION,
            obs.EVENT_BATCH_COMMIT,
            obs.EVENT_CHECKPOINT,
        ]
        assert names[0] == obs.EVENT_SYNC_RUN_START, f"首个事件应为 START: {names}"
        indexes = [names.index(name) for name in expected]
        assert indexes == sorted(indexes), f"阶段顺序错误: {names}"
        # 每批一个 BATCH_COMMIT（≥2 批）；推进 + 终态两个 CHECKPOINT 都存在
        assert names.count(obs.EVENT_BATCH_COMMIT) >= 2
        assert names.count(obs.EVENT_CHECKPOINT) >= 2

    async def test_run_sync_clear_run_id_on_rejected_path(self):
        """准入拒绝路径（资源忙）也走 finally 清空 run_id 上下文。"""
        from app.services import sync_observability as obs

        app = make_fake_app([make_vo(client=MagicMock())])
        with patch.object(
            admission_controller,
            "acquire",
            new=AsyncMock(
                return_value=AdmissionResult(
                    admitted=False,
                    skip_reason=SKIP_WAIT_TIMEOUT,
                    wait_seconds=30.0,
                    running_count=1,
                    queued_count=0,
                    task_code="torrent_info_sync_ac608e4d",
                )
            ),
        ):
            result = await run_sync(
                SyncRequest(sync_type="info", downloader_ids=["dl_001"], trigger="manual"),
                app=app,
            )

        assert result.outcome == "skipped"
        assert result.run_id and result.run_id.startswith("sync-")
        assert obs.current_run_id() is None, "准入拒绝路径结束后也必须清空 run_id"


class TestTrackerDownloaderHardTimeout:
    """【2026-08-25】下载器级硬熔断：tracker 同步单下载器超时被 wait_for 强制取消。

    回归锚点：enrich 内部预算（budget_seconds/max_per_run）是协作式检查点，
    worker 挂死在某个 await 上时永不执行（生产 cron-7-20260825111000 挂 8.75h
    的形态）。熔断在下载器边界强制取消且放行其余下载器——若有人移除 wait_for
    包裹或超时未中断，本测试即超时失败。
    """

    @staticmethod
    async def _hang_forever(*args, **kwargs):
        await asyncio.sleep(30)

    async def test_qb_downloader_hard_timeout_interrupts_and_fails(self):
        """qb tracker 同步超过硬超时：被强制中断，outcome=failed 且 errors 可读。"""
        app = make_fake_app([make_vo(downloader_id="dl_stuck", client=MagicMock())])

        with (
            patch.object(settings, "TRACKER_SYNC_DOWNLOADER_TIMEOUT_SECONDS", 0.05),
            patch(
                "app.api.endpoints.torrents_async.qb_sync_trackers_only_async",
                new=AsyncMock(side_effect=self._hang_forever),
            ),
        ):
            result = await asyncio.wait_for(
                run_sync(
                    SyncRequest(sync_type="tracker", downloader_ids=["dl_stuck"], trigger="cron"),
                    app=app,
                ),
                timeout=5.0,
            )

        assert result.outcome == "failed", f"单下载器熔断应为 failed: {result.message}"
        assert any("主动中断" in err for err in result.errors), f"errors 应含熔断说明: {result.errors}"
        assert any("超过 0s" in err for err in result.errors), "熔断文案应含实际阈值秒数"

    async def test_tr_downloader_hard_timeout_symmetric(self):
        """tr tracker 同步同样受下载器级硬熔断保护（对称防御）。"""
        app = make_fake_app([make_vo(downloader_id="dl_tr_stuck", client=MagicMock(), downloader_type=1)])

        with (
            patch.object(settings, "TRACKER_SYNC_DOWNLOADER_TIMEOUT_SECONDS", 0.05),
            patch(
                "app.api.endpoints.torrents_async.tr_sync_trackers_only_async",
                new=AsyncMock(side_effect=self._hang_forever),
            ),
        ):
            result = await asyncio.wait_for(
                run_sync(
                    SyncRequest(sync_type="tracker", downloader_ids=["dl_tr_stuck"], trigger="cron"),
                    app=app,
                ),
                timeout=5.0,
            )

        assert result.outcome == "failed"
        assert any("主动中断" in err for err in result.errors)

    async def test_hard_timeout_does_not_block_other_downloaders(self):
        """一个下载器熔断后其余下载器正常完成：汇总 partial（1 成功 1 失败）。"""
        app = make_fake_app(
            [
                make_vo(downloader_id="dl_stuck", client=MagicMock()),
                make_vo(downloader_id="dl_ok", client=MagicMock()),
            ]
        )

        async def _sync_by_downloader(db, downloader, *args, **kwargs):
            downloader_id = str(getattr(downloader, "downloader_id", "") or "")
            if downloader_id == "dl_stuck":
                await asyncio.sleep(30)
            return {
                "status": "success",
                "tracker_count": 3,
                "torrent_count": 5,
                "cycle_complete": True,
            }

        with (
            patch.object(settings, "TRACKER_SYNC_DOWNLOADER_TIMEOUT_SECONDS", 0.05),
            patch(
                "app.api.endpoints.torrents_async.qb_sync_trackers_only_async",
                new=AsyncMock(side_effect=_sync_by_downloader),
            ),
        ):
            result = await asyncio.wait_for(
                run_sync(
                    SyncRequest(sync_type="tracker", downloader_ids=["dl_stuck", "dl_ok"], trigger="cron"),
                    app=app,
                ),
                timeout=5.0,
            )

        assert result.outcome == "partial", f"一熔断一成功应汇总 partial: {result.message}"
        assert "1 成功，1 失败" in result.message
        stuck_errors = [err for err in result.errors if "dl_stuck" in err or "test-dl" in err]
        assert any("主动中断" in err for err in result.errors)
        assert stuck_errors, "熔断错误应可追溯到具体下载器"

    async def test_hard_timeout_disabled_by_zero_keeps_hang_semantics(self):
        """配置 0 关闭熔断：wait_for 收到 timeout=None，不再强制中断（开关语义）。"""
        from app.services import sync_coordinator as coordinator_module

        app = make_fake_app([make_vo(downloader_id="dl_zero", client=MagicMock())])
        captured_wait_for_timeouts = []

        original_wait_for = asyncio.wait_for

        async def _spy_wait_for(aw, timeout=None):
            captured_wait_for_timeouts.append(timeout)
            # 立即完成，不真正等待（本用例只验证开关语义传参）
            return await aw

        quick_result = {
            "status": "success",
            "tracker_count": 0,
            "torrent_count": 0,
            "cycle_complete": True,
        }

        with (
            patch.object(settings, "TRACKER_SYNC_DOWNLOADER_TIMEOUT_SECONDS", 0),
            patch(
                "app.api.endpoints.torrents_async.qb_sync_trackers_only_async",
                new=AsyncMock(return_value=quick_result),
            ),
            patch.object(asyncio, "wait_for", new=_spy_wait_for),
            patch.object(coordinator_module.asyncio, "wait_for", new=_spy_wait_for),
        ):
            result = await run_sync(
                SyncRequest(sync_type="tracker", downloader_ids=["dl_zero"], trigger="cron"),
                app=app,
            )

        assert result.outcome == "success"
        assert None in captured_wait_for_timeouts, "配置 0 时 wait_for 应收到 timeout=None（关闭熔断）"
        # 恢复安全性：patch 退出自动还原，无需手动恢复
        _ = original_wait_for  # 防止 lint 报未使用
