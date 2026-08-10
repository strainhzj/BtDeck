# -*- coding: utf-8 -*-
"""
sync_observability 单测（W4-1：结构化观测工具模块 + run_id 贯穿 + 阈值告警）

覆盖：
1. log_event 白名单过滤（非白名单字段不输出）+ 事件最小字段完整输出。
2. 脱敏：password/passkey/cookie/authorization/token 遮蔽；announce URL
   （含 passkey query）去 query；hash 保留前 8 位；经 log_event 输出不泄漏明文。
3. lag 采样器：注入样本 p95/p99/max 计算；窗口上限；stop 无 task 泄漏；
   测量回调抛异常后下一轮仍产生样本；SYNC_LAG_SAMPLER_ENABLED=False 空句柄。
4. snapshot_wal_stats：有/无 -wal 文件均不报错（wal_bytes 正确、busy None）。
5. _attach_done_stats 修复：cancelled future 不抛 CancelledError（不记统计）；
   正常/异常完成的 future 仍记 success/failure（语义不变）。
6. W4-1 第二部分 run_id 贯穿：set/current/clear、log_event 自动附加、
   显式值优先、asyncio 任务间隔离。
7. W4-1 第二部分阈值告警：单次 lag>500ms → WARNING；窗口 P99>100ms 且样本
   足够 → WARNING（含发射间隔抑制）；低 lag 不告警。
8. W4-1 第二部分生命周期：lag 采样器句柄 stop 幂等无 task 泄漏；
   WAL 周期快照任务周期性发射事件且 cancel 干净退出。

【测试隔离】lag 采样器用独立 EventLoopLagSampler 实例 + 短 interval，不触碰
全局单例；log_event 测试 spy 模块 logger（避免全量 pytest 时 root logger 污染）。
"""

import asyncio
import logging
import sqlite3
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services import sync_observability as obs
from app.services.downloader_api_runtime import _attach_done_stats


class TestLogEvent:
    """log_event 白名单过滤与最小字段输出。"""

    def _log_msg(self, event_name, level=None, **fields):
        with patch.object(obs.logger, "log") as mock_log:
            if level is None:
                obs.log_event(event_name, **fields)
            else:
                obs.log_event(event_name, level=level, **fields)
        return mock_log.call_args.args[1]

    def test_batch_commit_emits_all_minimal_fields(self):
        """EVENT_BATCH_COMMIT 输出含全部最小字段（关联 + 数据库类别）。"""
        msg = self._log_msg(
            obs.EVENT_BATCH_COMMIT,
            run_id="run_1",
            task_id="task_1",
            sync_type="info",
            trigger="manual",
            downloader_id="dl1",
            batch_index=3,
            batch_rows=200,
            changed_rows=180,
            commit_ms=45.2,
            lock_wait_ms=12.3,
            retry_count=0,
        )
        for token in (
            "event=sync_batch_commit",
            "run_id=run_1",
            "task_id=task_1",
            "sync_type=info",
            "trigger=manual",
            "downloader_id=dl1",
            "batch_index=3",
            "batch_rows=200",
            "changed_rows=180",
            "commit_ms=45.2",
            "lock_wait_ms=12.3",
            "retry_count=0",
        ):
            assert token in msg, f"缺少字段 {token}: {msg}"

    def test_non_whitelist_fields_dropped(self):
        """非白名单字段（rss_mb/secret_extra）不输出。"""
        msg = self._log_msg(
            obs.EVENT_LOOP_LAG,
            lag_ms=1.5,
            p95_ms=2.0,
            max_ms=3.0,
            rss_mb=123,
            secret_extra="x",
        )
        assert "event=event_loop_lag" in msg
        assert "lag_ms=1.5" in msg
        assert "p95_ms=2.0" in msg
        assert "max_ms=3.0" in msg
        assert "rss_mb" not in msg, "非白名单字段不应输出"
        assert "secret_extra" not in msg, "非白名单字段不应输出"

    def test_unknown_event_only_common_fields(self):
        """未知事件名只输出公共字段（不崩溃）。"""
        msg = self._log_msg("no_such_event", run_id="r1", downloader_id="dl1", mystery=1)
        assert "event=no_such_event" in msg
        assert "run_id=r1" in msg
        assert "mystery" not in msg

    def test_log_event_level_passthrough(self):
        """level 参数透传（告警事件用 warning 级输出）。"""
        with patch.object(obs.logger, "log") as mock_log:
            obs.log_event(obs.EVENT_CHECKPOINT, level=logging.WARNING, run_id="r1", outcome="stale")
        assert mock_log.call_args.args[0] == logging.WARNING

    def test_log_event_sensitive_fields_not_leaked(self):
        """敏感字段（password/passkey/cookie/authorization/token）不泄漏到输出。"""
        msg = self._log_msg(
            obs.EVENT_ADMISSION,
            run_id="run_1",
            downloader_id="dl1",
            outcome="rejected",
            password="hunter2",
            passkey="k123",
            cookie="c=v",
            authorization="Bearer xyz",
            token="tok_9",
        )
        # 白名单字段正常输出
        assert "outcome=rejected" in msg
        # 敏感明文一律不出现（白名单外字段被丢弃，值不落盘）
        for secret in ("hunter2", "k123", "c=v", "Bearer xyz", "tok_9"):
            assert secret not in msg, f"泄漏敏感字段: {secret}"

    def test_log_event_masks_url_value_in_whitelisted_field(self):
        """白名单字段值内含 URL（含 passkey query）→ 脱敏后输出。"""
        msg = self._log_msg(
            obs.EVENT_DOWNLOADER_CALL,
            run_id="run_1",
            lane="sync",
            downloader_id="https://evil.example.com/track?passkey=topsecret",
        )
        assert "topsecret" not in msg, "URL query 中的 passkey 不应输出"
        assert "downloader_id=https://evil.example.com/track" in msg


class TestSanitizeFields:
    """脱敏：敏感 key / URL / hash / IP。"""

    def test_sensitive_keys_masked_to_asterisks(self):
        """password/passkey/cookie/authorization/token 等 key 的值整体遮蔽。"""
        fields = {
            "password": "s3cret",
            "passkey": "abc123xyz",
            "cookie": "sid=deadbeef",
            "authorization": "Bearer token123",
            "token": "tok_abc",
        }
        out = obs.sanitize_fields(fields)
        assert set(out.values()) == {"***"}

    def test_announce_url_query_passkey_stripped(self):
        """announce URL 保留 scheme+host+path，去掉 query（passkey 被剥离）。"""
        out = obs.sanitize_value(
            "announce",
            "https://tracker.example.com/announce.php?passkey=pp_secret&event=started",
        )
        assert out == "https://tracker.example.com/announce.php"
        assert "pp_secret" not in out

    def test_url_userinfo_password_stripped(self):
        """URL userinfo 中的密码不出现。"""
        out = obs.sanitize_value("url", "https://user:pa55word@tracker.example.com/announce?passkey=x")
        assert "pa55word" not in out
        assert out == "https://tracker.example.com/announce"

    def test_schemeless_tracker_url_query_stripped(self):
        """无 scheme 的 tracker 地址（key 为 tracker）也剥离 query。"""
        out = obs.sanitize_value("tracker", "tracker.example.com:6969/announce?passkey=y")
        assert out == "tracker.example.com:6969/announce"
        assert "passkey=y" not in out

    def test_hash_key_keeps_first_8_chars(self):
        """hash 类 key 保留前 8 位，其余遮蔽。"""
        h = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        out = obs.sanitize_value("info_hash", h)
        assert out == h[:8] + "***"
        assert h not in out

    def test_ip_reuses_log_sanitizer(self):
        """纯 IP 值复用 app/utils/log_sanitizer 的 IP 脱敏实现。"""
        out = obs.sanitize_value("host", "192.168.1.5")
        assert out == "192.168.1.***"

    def test_plain_fields_untouched(self):
        """非敏感字段原样保留（数字/短字符串）。"""
        fields = {"run_id": "r1", "downloader_id": "dl1", "batch_rows": 200, "commit_ms": 1.5}
        assert obs.sanitize_fields(fields) == fields


class TestLagSampler:
    """事件循环 lag 采样器：样本/分位/窗口/生命周期/异常恢复。"""

    def test_percentiles_from_injected_samples(self):
        """注入 1..100 样本：p95/p99/max 按 nearest-rank 计算正确。"""
        sampler = obs.EventLoopLagSampler(interval_seconds=1.0, window_size=1000)
        for value in range(1, 101):
            sampler.record_sample(float(value))
        assert sampler.sample_count() == 100
        assert sampler.p95() == pytest.approx(95.0)
        assert sampler.p99() == pytest.approx(99.0)
        assert sampler.max_ms() == 100.0

    def test_empty_sampler_returns_zero(self):
        """无样本时 p95/p99/max 均为 0（不抛异常）。"""
        sampler = obs.EventLoopLagSampler()
        assert sampler.p95() == 0.0
        assert sampler.p99() == 0.0
        assert sampler.max_ms() == 0.0

    def test_window_size_caps_samples(self):
        """滑动窗口只保留最近 window_size 个样本。"""
        sampler = obs.EventLoopLagSampler(window_size=10)
        for value in range(50):
            sampler.record_sample(float(value))
        assert sampler.sample_count() == 10
        assert sampler.max_ms() == 49.0
        assert sampler.p99() == pytest.approx(49.0)

    async def test_start_collects_lag_and_stop_clean(self):
        """启动后真实采集样本；stop 后不再产生样本、无 task 泄漏。"""
        baseline_tasks = len(asyncio.all_tasks())
        sampler = obs.EventLoopLagSampler(interval_seconds=0.02, window_size=100)
        sampler.start()
        await asyncio.sleep(0.12)  # 约 6 个 tick
        assert sampler.sample_count() > 0, "采样器应采集到真实 lag 样本"
        count_before_stop = sampler.sample_count()
        sampler.stop()
        await asyncio.sleep(0.1)
        assert sampler.sample_count() == count_before_stop, "stop 后不应再产生样本"
        assert len(asyncio.all_tasks()) == baseline_tasks, "采样器不应泄漏 asyncio task"

    async def test_measure_exception_recovers_next_round(self):
        """测量回调抛异常被吞掉，下一轮仍产生样本。"""
        calls = {"n": 0}

        def flaky_measure():
            calls["n"] += 1
            if calls["n"] <= 2:
                raise RuntimeError("measure boom")
            return 5.0

        sampler = obs.EventLoopLagSampler(interval_seconds=0.02, window_size=100, measure=flaky_measure)
        sampler.start()
        await asyncio.sleep(0.15)
        sampler.stop()
        assert calls["n"] >= 3, "异常后采样循环应持续运行"
        assert sampler.sample_count() > 0, "异常后的下一轮仍应产生样本"
        assert sampler.p95() == pytest.approx(5.0)

    async def test_disabled_config_returns_noop_handle(self):
        """SYNC_LAG_SAMPLER_ENABLED=False 时 start 返回空句柄（no-op）。"""
        with patch("app.core.config.settings.SYNC_LAG_SAMPLER_ENABLED", False):
            handle = obs.start_lag_sampler()
        assert handle.enabled is False
        assert handle.sampler is None
        handle.stop()  # 空句柄 stop 不抛异常

    async def test_start_lag_sampler_returns_handle(self):
        """start_lag_sampler 启动真实采样（interval/window 参数透传）。"""
        handle = obs.start_lag_sampler(interval_seconds=0.02, window_size=50)
        assert handle.enabled is True
        await asyncio.sleep(0.1)
        assert handle.sampler.sample_count() > 0
        handle.stop()


class TestWalSnapshot:
    """WAL 只读快照：有/无 -wal 文件均不报错。"""

    def test_no_wal_file_returns_zero_and_none(self, tmp_path):
        """db 目录存在但无 -wal 文件：wal_bytes=0、busy/checkpoint 为 None。"""
        db_path = str(tmp_path / "app.db")
        stats = obs.snapshot_wal_stats(db_path)
        assert stats == {"wal_bytes": 0, "busy_count": None, "checkpoint_busy": None}

    def test_wal_file_size_read_correctly(self, tmp_path):
        """有 -wal 文件：wal_bytes 为真实文件字节数。"""
        db_path = str(tmp_path / "app.db")
        with open(db_path + "-wal", "wb") as f:
            f.write(b"x" * 2048)
        stats = obs.snapshot_wal_stats(db_path)
        assert stats["wal_bytes"] == 2048
        assert stats["busy_count"] is None
        assert stats["checkpoint_busy"] is None

    def test_missing_directory_no_error(self, tmp_path):
        """db 所在目录不存在也不抛异常（按 wal_bytes=0 处理）。"""
        stats = obs.snapshot_wal_stats(str(tmp_path / "no_such_dir" / "app.db"))
        assert stats["wal_bytes"] == 0
        assert stats["busy_count"] is None

    def test_existing_sqlite_db_reports_passive_checkpoint_state(self, tmp_path):
        """真实数据库使用 PASSIVE 探测，返回可观测的 busy 字段。"""
        db_path = str(tmp_path / "app.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY)")
            conn.commit()

        stats = obs.snapshot_wal_stats(db_path)
        assert isinstance(stats["busy_count"], int)
        assert stats["busy_count"] >= 0
        assert stats["checkpoint_busy"] is (stats["busy_count"] > 0)


class TestAttachDoneStats:
    """_attach_done_stats 修复：cancelled future 不抛 CancelledError。

    回归背景（W4-3 runbook 收口候选，本部分修复）：旧实现对 cancelled future 调
    fut.exception() 抛 CancelledError（BaseException，except Exception 捕获不到），
    done callback 异常泄漏到 loop handler；修复后 cancelled 短路返回、异常路径
    except BaseException 兜底，正常/异常完成的 future 统计语义不变。
    """

    async def test_cancelled_future_no_crash_and_no_stats(self):
        """cancelled future：不抛异常、不记 success/failure 统计。"""
        loop = asyncio.get_running_loop()
        loop_errors = []
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, ctx: loop_errors.append(ctx))
        try:
            future = loop.create_future()
            future.cancel()
            stats = MagicMock()
            _attach_done_stats(
                future,
                stats,
                "sync",
                "fetch",
                "dl1",
                time.monotonic(),
                {"queue_wait_ms": 1.0},
            )
            await asyncio.sleep(0)  # 让 done callback 执行
            assert loop_errors == [], f"回调异常泄漏到 loop handler: {loop_errors}"
            stats.record_success.assert_not_called()
            stats.record_failure.assert_not_called()
        finally:
            loop.set_exception_handler(old_handler)

    async def test_success_future_still_records_success(self):
        """正常完成的 future 仍记 success（语义不变）。"""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        future.set_result("ok")
        stats = MagicMock()
        _attach_done_stats(
            future,
            stats,
            "sync",
            "fetch",
            "dl1",
            time.monotonic(),
            {"queue_wait_ms": 0.5},
        )
        await asyncio.sleep(0)
        stats.record_success.assert_called_once()
        args = stats.record_success.call_args.args
        assert args[0] == "sync"
        assert args[1] == "fetch"
        assert args[2] == "dl1"
        stats.record_failure.assert_not_called()

    async def test_failed_future_still_records_failure(self):
        """异常完成的 future 仍记 failure（error_type 正确，语义不变）。"""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        future.set_exception(ValueError("boom"))
        stats = MagicMock()
        _attach_done_stats(
            future,
            stats,
            "tracker",
            "fetch_trackers",
            "dl2",
            time.monotonic(),
            {"queue_wait_ms": 0.5},
        )
        await asyncio.sleep(0)
        stats.record_failure.assert_called_once()
        args = stats.record_failure.call_args.args
        assert args[0] == "tracker"
        assert args[1] == "fetch_trackers"
        assert args[2] == "dl2"
        assert args[4] == "ValueError"
        stats.record_success.assert_not_called()


class TestRunIdContext:
    """W4-1 第二部分：run_id contextvars 贯穿（log_event 自动附加）。"""

    def test_current_run_id_defaults_to_none(self):
        """无活动运行：current_run_id() 返回 None。"""
        obs.clear_run_id()
        assert obs.current_run_id() is None
        obs.set_run_id("r1")
        assert obs.current_run_id() == "r1"
        obs.clear_run_id()
        assert obs.current_run_id() is None

    def test_log_event_attaches_run_id_from_context(self):
        """set_run_id 后 log_event 输出自动含 run_id。"""
        obs.set_run_id("run_abc123")
        try:
            with patch.object(obs.logger, "log") as mock_log:
                obs.log_event(obs.EVENT_ADMISSION, outcome="admitted")
        finally:
            obs.clear_run_id()
        msg = mock_log.call_args.args[1]
        assert "event=sync_admission" in msg
        assert "run_id=run_abc123" in msg

    def test_clear_run_id_drops_field(self):
        """clear_run_id 后 log_event 输出不含 run_id。"""
        obs.clear_run_id()
        with patch.object(obs.logger, "log") as mock_log:
            obs.log_event(obs.EVENT_ADMISSION, outcome="admitted")
        assert "run_id" not in mock_log.call_args.args[1]

    def test_explicit_run_id_overrides_context(self):
        """显式传入 run_id 优先于上下文值。"""
        obs.set_run_id("run_ctx")
        try:
            with patch.object(obs.logger, "log") as mock_log:
                obs.log_event(obs.EVENT_ADMISSION, run_id="run_explicit", outcome="admitted")
        finally:
            obs.clear_run_id()
        msg = mock_log.call_args.args[1]
        assert "run_id=run_explicit" in msg
        assert "run_id=run_ctx" not in msg

    async def test_context_isolated_across_tasks(self):
        """不同 asyncio 任务各自持有自己的 run_id（ContextVar 任务隔离）。"""

        async def emit(run_id):
            obs.set_run_id(run_id)
            await asyncio.sleep(0)
            with patch.object(obs.logger, "log") as mock_log:
                obs.log_event(obs.EVENT_ADMISSION, outcome="admitted")
            return mock_log.call_args.args[1]

        obs.clear_run_id()
        results = await asyncio.gather(emit("run_a"), emit("run_b"))
        assert "run_id=run_a" in results[0]
        assert "run_id=run_b" in results[1]


class TestLagThresholdAlerts:
    """W4-1 第二部分：lag 阈值告警（日志级，初始值见 sync_observability 常量）。"""

    def _warn_messages(self, mock_log):
        return [c.args[1] for c in mock_log.call_args_list if c.args[0] == logging.WARNING]

    def test_single_lag_over_500ms_emits_warning(self):
        """单次 lag > 500ms → EVENT_LOOP_LAG WARNING（携带 lag_ms/threshold_ms）。"""
        sampler = obs.EventLoopLagSampler(interval_seconds=1.0, window_size=100)
        with patch.object(obs.logger, "log") as mock_log:
            sampler.record_sample(600.0)
        warnings = self._warn_messages(mock_log)
        assert warnings, "超过 500ms 单次样本应发射 WARNING"
        msg = warnings[-1]
        assert "event=event_loop_lag" in msg
        assert "lag_ms=600.0" in msg
        assert "threshold_ms=500.0" in msg

    def test_small_samples_no_warning(self):
        """低 lag 样本（<500ms 且 P99<100ms）不发射 WARNING。"""
        sampler = obs.EventLoopLagSampler(interval_seconds=1.0, window_size=100)
        with patch.object(obs.logger, "log") as mock_log:
            for _ in range(100):
                sampler.record_sample(5.0)
        assert self._warn_messages(mock_log) == []

    def test_p99_over_100ms_with_enough_samples_warns(self):
        """窗口 P99 > 100ms 且样本数足够 → WARNING（防冷启动误报）。"""
        sampler = obs.EventLoopLagSampler(interval_seconds=1.0, window_size=300)
        with patch.object(obs.logger, "log") as mock_log:
            for _ in range(obs.LOOP_LAG_WARN_MIN_SAMPLES):
                sampler.record_sample(150.0)
        warnings = self._warn_messages(mock_log)
        assert warnings, "P99 超阈值且样本足够应发射 WARNING"
        msg = warnings[-1]
        assert "p99_ms=150.0" in msg
        assert "threshold_ms=100.0" in msg

    def test_p99_warning_suppressed_within_interval(self):
        """P99 告警受最小发射间隔抑制（窗口持续超阈值不刷屏）。"""
        sampler = obs.EventLoopLagSampler(interval_seconds=1.0, window_size=300)
        with patch.object(obs.logger, "log") as mock_log:
            for _ in range(obs.LOOP_LAG_WARN_MIN_SAMPLES):
                sampler.record_sample(150.0)
            for _ in range(20):
                sampler.record_sample(150.0)
        warnings = self._warn_messages(mock_log)
        assert len(warnings) == 1, f"间隔内只应发射一次 P99 告警: {warnings}"


class TestLifecycleMount:
    """W4-1 第二部分：观测挂载生命周期（句柄 stop 幂等 / WAL 快照任务可取消）。"""

    async def test_handle_stop_idempotent_and_no_task_leak(self):
        """lag 采样器句柄：stop 幂等；停止后不再产生样本；无 asyncio task 泄漏。"""
        baseline_tasks = len(asyncio.all_tasks())
        handle = obs.start_lag_sampler(interval_seconds=0.02, window_size=50)
        assert handle.enabled is True
        await asyncio.sleep(0.05)
        assert handle.sampler.sample_count() > 0
        handle.stop()
        handle.stop()  # 幂等：重复 stop 不抛异常
        count_after_stop = handle.sampler.sample_count()
        await asyncio.sleep(0.05)
        assert handle.sampler.sample_count() == count_after_stop, "stop 后不应再产生样本"
        assert len(asyncio.all_tasks()) == baseline_tasks

    async def test_wal_snapshot_loop_emits_and_cancels(self, monkeypatch):
        """WAL 周期快照任务：周期性发射 EVENT_WAL_SNAPSHOT；cancel 后干净退出。"""
        from app.startup.lifecycle import run_wal_snapshot_loop

        from app.core.config import settings as _settings

        monkeypatch.setattr(_settings, "SYNC_WAL_SNAPSHOT_INTERVAL_SECONDS", 0.05)
        app = MagicMock()
        with patch.object(obs.logger, "log") as mock_log:
            task = asyncio.create_task(run_wal_snapshot_loop(app))
            await asyncio.sleep(0.12)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        messages = [c.args[1] for c in mock_log.call_args_list]
        assert any(m.startswith("event=wal_snapshot") for m in messages), "WAL 快照事件应周期性发射"
