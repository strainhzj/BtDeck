# -*- coding: utf-8 -*-
"""
DownloaderApiRuntime 单测

【覆盖目标】
1. 三 lane 独立 executor（物理隔离）：不同 lane 的并发调用互不挤占。
2. call_downloader_api 参数透传：args/kwargs 正确传给被调函数。
3. per-downloader Semaphore：同下载器跨 lane 总并发受 DOWNLOADER_IO_CONCURRENCY 限制。
4. timeout 生效：超时抛 asyncio.TimeoutError。
5. 异常透传：被调函数抛的异常原样向上抛，不被吞。
6. 调用结果正确返回。
7. lane 日志 extra 字段（阶段 0 基线观测）。

【测试隔离】
每个测试新建独立 DownloaderApiRuntime 实例（不用全局单例），避免 executor 状态泄漏。
"""

import asyncio
import threading
import time

import pytest

from app.services.downloader_api_runtime import (
    DownloadLane,
    DownloaderApiRuntime,
    LaneLogExtra,
)


def _make_runtime() -> DownloaderApiRuntime:
    """构造独立 runtime 实例（避免全局单例污染）。"""
    return DownloaderApiRuntime()


class TestCallBasics:
    """call_downloader_api 基础契约。"""

    async def test_args_kwargs_passthrough(self):
        """位置参数 + 关键字参数正确透传给被调函数。"""
        runtime = _make_runtime()

        def fake_api(x, y=0, z=None):
            return {"x": x, "y": y, "z": z}

        result = await runtime.call(
            "dl1",
            DownloadLane.SYNC,
            fake_api,
            args=(10,),
            kwargs={"y": 5, "z": "hello"},
            operation="fake",
        )
        assert result == {"x": 10, "y": 5, "z": "hello"}

    async def test_returns_func_result(self):
        """被调函数返回值原样返回。"""
        runtime = _make_runtime()
        result = await runtime.call(
            "dl1",
            DownloadLane.TRACKER,
            lambda: 42,
            operation="const",
        )
        assert result == 42

    async def test_default_timeout_from_settings(self):
        """timeout=None 时取 settings.DOWNLOADER_API_TIMEOUT_SECONDS。"""
        runtime = _make_runtime()
        # 间接验证：不传 timeout，调用快速完成的函数应正常返回（不超时）
        result = await runtime.call(
            "dl1",
            DownloadLane.INTERACTIVE,
            lambda: "ok",
            operation="fast",
        )
        assert result == "ok"


class TestTimeout:
    """超时行为。"""

    async def test_timeout_raises_asyncio_timeout(self):
        """被调函数超过 timeout 时抛 asyncio.TimeoutError。"""
        runtime = _make_runtime()

        def slow():
            time.sleep(0.3)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await runtime.call(
                "dl1",
                DownloadLane.SYNC,
                slow,
                timeout=0.05,
                operation="slow",
            )

    async def test_timeout_releases_semaphore(self):
        """超时后 per-downloader semaphore 最终释放（新调用能恢复）。

        语义（code review 修复后）：semaphore 由 executor 内 wrapper 线程持有，
        超时只放弃等待 future，底层线程仍持有令牌继续运行。新调用会阻塞在 sem.acquire()
        直到旧线程 release，最终能拿到结果。这证明令牌不会因超时永久泄漏。
        """
        runtime = _make_runtime()

        def slow():
            time.sleep(0.2)
            return "done"

        # 第一次调用超时（底层线程仍会跑完 0.2s）
        with pytest.raises(asyncio.TimeoutError):
            await runtime.call(
                "dl1",
                DownloadLane.SYNC,
                slow,
                timeout=0.05,
                operation="slow1",
            )

        # 后续调用最终能完成（等底层线程 release 后，新线程拿到令牌）
        result = await runtime.call(
            "dl1",
            DownloadLane.SYNC,
            lambda: "recovered",
            timeout=2.0,
            operation="recover",
        )
        assert result == "recovered"

    async def test_timeout_does_not_break_real_concurrency_cap(self):
        """🔴 关键不变量（code review 修复目标）：超时后底层线程仍运行时，
        同一 downloader 的真实远程调用并发不超过 DOWNLOADER_IO_CONCURRENCY。

        背景：修复前 asyncio.Semaphore 在 wait_for 超时后立即释放，新请求继续堆积，
        真实远程并发突破上限。修复后改用 threading.Semaphore 由 wrapper 线程持有，
        超时线程未结束前不释放容量。

        策略：发起 N 个慢调用（每个 sleep 0.3s），每个用极短 timeout（0.05s）让它们
        全部在调用方超时。然后等待底层线程全部跑完，断言观察到的同时运行线程数 ≤ 上限。
        """
        from app.core.config import settings

        runtime = _make_runtime()
        limit = settings.DOWNLOADER_IO_CONCURRENCY  # 默认 2

        concurrent = {"current": 0, "max": 0}
        lock = threading.Lock()
        done_event = threading.Event()

        def slow_call(idx):
            with lock:
                concurrent["current"] += 1
                if concurrent["current"] > concurrent["max"]:
                    concurrent["max"] = concurrent["current"]
            time.sleep(0.3)  # 模拟慢远程调用，超出 timeout
            with lock:
                concurrent["current"] -= 1
                if concurrent["current"] == 0:
                    done_event.set()
            return idx

        # 发起 limit + 3 个调用，每个调用方超时 0.05s，底层线程仍跑 0.3s
        n_calls = limit + 3
        tasks = [
            runtime.call(
                "dl_cap_timeout",
                DownloadLane.SYNC,
                slow_call,
                args=(i,),
                timeout=0.05,
                operation=f"c{i}",
            )
            for i in range(n_calls)
        ]
        # 全部在调用方超时
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(
            isinstance(r, asyncio.TimeoutError) for r in results
        ), "所有调用应在调用方超时（timeout=0.05s < sleep=0.3s）"

        # 等待所有底层线程跑完（最多 5s 裕度）
        done_event.wait(timeout=5.0)

        # 关键断言：底层线程同时运行数不超过 limit
        # 注意：修复前 max 可能达到 limit + 残留线程数；修复后恒 ≤ limit。
        assert concurrent["max"] <= limit, (
            f"超时后真实并发突破上限: max={concurrent['max']} > limit={limit}。"
            "说明 per-downloader semaphore 在超时后被过早释放。"
        )


class TestExceptionPassthrough:
    """异常透传（不吞）。"""

    async def test_exception_propagates(self):
        """被调函数抛 ValueError 时，原样向上抛（不吞、不包装）。"""
        runtime = _make_runtime()

        def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            await runtime.call(
                "dl1",
                DownloadLane.TRACKER,
                boom,
                operation="boom",
            )

    async def test_exception_releases_semaphore(self):
        """异常后 per-downloader semaphore 必须释放。"""
        runtime = _make_runtime()

        def boom():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await runtime.call("dl1", DownloadLane.SYNC, boom, operation="boom")

        # 后续调用应正常（证明 semaphore 释放）
        result = await runtime.call(
            "dl1",
            DownloadLane.SYNC,
            lambda: "ok",
            operation="after_boom",
        )
        assert result == "ok"


class TestLaneIsolation:
    """三 lane executor 物理隔离。"""

    async def test_different_lanes_use_different_threads(self):
        """不同 lane 的调用应运行在不同线程（证明物理隔离）。

        策略：在三个 lane 各发一个调用，记录线程名前缀（dl_tracker/dl_sync/dl_interactive）。
        """
        runtime = _make_runtime()
        seen_thread_names = {}

        def record_thread(lane_name):
            seen_thread_names[lane_name] = threading.current_thread().name
            time.sleep(0.05)  # 让并发窗口可观察
            return lane_name

        # 并发发三个 lane 调用
        tasks = [
            runtime.call("dl1", DownloadLane.TRACKER, record_thread, args=("tracker",), operation="t"),
            runtime.call("dl1", DownloadLane.SYNC, record_thread, args=("sync",), operation="s"),
            runtime.call("dl1", DownloadLane.INTERACTIVE, record_thread, args=("interactive",), operation="i"),
        ]
        await asyncio.gather(*tasks)

        # 关键断言：三个 lane 的线程名前缀不同（物理隔离）
        assert "tracker" in seen_thread_names
        assert "sync" in seen_thread_names
        assert "interactive" in seen_thread_names
        # 线程名前缀必须是各自的 lane 标识
        assert "dl_tracker" in seen_thread_names["tracker"]
        assert "dl_sync" in seen_thread_names["sync"]
        assert "dl_interactive" in seen_thread_names["interactive"]


class TestPerDownloaderSemaphore:
    """per-downloader 总并发限制。"""

    async def test_same_downloader_concurrency_capped(self):
        """同一下载器的并发调用数不超过 DOWNLOADER_IO_CONCURRENCY。

        DOWNLOADER_IO_CONCURRENCY 默认 2。策略：发起 5 个并发慢调用，
        观察同时运行的最大数量，应 ≤ 2。
        """
        runtime = _make_runtime()
        concurrent = {"current": 0, "max": 0}
        lock = threading.Lock()

        def slow_call(idx):
            with lock:
                concurrent["current"] += 1
                if concurrent["current"] > concurrent["max"]:
                    concurrent["max"] = concurrent["current"]
            time.sleep(0.1)  # 模拟慢 API
            with lock:
                concurrent["current"] -= 1
            return idx

        tasks = [runtime.call("dl_cap", DownloadLane.SYNC, slow_call, args=(i,), operation=f"c{i}") for i in range(5)]
        await asyncio.gather(*tasks)

        # 同下载器跨 lane（这里都 SYNC）总并发受 DOWNLOADER_IO_CONCURRENCY(默认2) 限制
        from app.core.config import settings

        assert concurrent["max"] <= settings.DOWNLOADER_IO_CONCURRENCY, (
            f"per-downloader 并发超限: max={concurrent['max']}, " f"limit={settings.DOWNLOADER_IO_CONCURRENCY}"
        )
        assert concurrent["max"] >= 2, "应至少观察到 2 个并发（默认限制）"

    async def test_different_downloaders_run_in_parallel(self):
        """不同下载器的调用不受彼此 semaphore 限制（独立计数）。"""
        runtime = _make_runtime()
        concurrent = {"current": 0, "max": 0}
        lock = threading.Lock()

        def slow_call():
            with lock:
                concurrent["current"] += 1
                if concurrent["current"] > concurrent["max"]:
                    concurrent["max"] = concurrent["current"]
            time.sleep(0.1)
            with lock:
                concurrent["current"] -= 1

        # 2 个不同下载器，各发 2 个并发
        tasks = []
        for dl in ("dl_a", "dl_b"):
            for _ in range(2):
                tasks.append(runtime.call(dl, DownloadLane.SYNC, slow_call, operation="parallel"))
        await asyncio.gather(*tasks)

        # 不同下载器不互相限制，应观察到 >2 的并发（因为 dl_a 和 dl_b 各自独立）
        assert concurrent["max"] > 2, f"不同下载器应并行运行，但 max={concurrent['max']}（应 >2）"


class TestShutdown:
    """shutdown 行为（code review 修复：接入生命周期 + flush 统计）。"""

    async def test_shutdown_closes_lane_executors(self):
        """shutdown 后 lane executor 应标记为已关闭（不能再提交新任务）。"""
        runtime = _make_runtime()
        # 先做一次调用确保 executor 已初始化
        await runtime.call("dl1", DownloadLane.SYNC, lambda: "ok", operation="warmup")
        runtime.shutdown()
        # 关闭后提交新任务应抛 RuntimeError（executor 已 shutdown）
        for lane, executor in runtime._executors.items():
            assert executor._shutdown, f"lane={lane} executor 未被 shutdown"

    async def test_shutdown_flushes_pending_stats(self):
        """shutdown 必须强制 flush 残留日志统计（窗口未到期也输出）。

        用 spy logger 而非 caplog，避免全量 pytest 时 root logger 级别污染。
        """
        from unittest.mock import patch

        runtime = _make_runtime()
        runtime._stats = type(runtime._stats)(window_seconds=60.0)  # 大窗口不自动到期
        # 累积一些成功调用
        for _ in range(5):
            await runtime.call("dl_flush", DownloadLane.SYNC, lambda: 1, operation="flush_test")

        with patch("app.services.downloader_api_runtime.logger") as mock_logger:
            runtime.shutdown()
        window_msgs = [
            c for c in mock_logger.info.call_args_list if c.args and "downloader_api_call_window" in c.args[0]
        ]
        assert len(window_msgs) == 1, "shutdown 应 flush 出 1 条聚合日志"
        extra = window_msgs[0].kwargs.get("extra", {})
        assert extra.get("success_count") == 5


class TestBuildLogExtra:
    """LaneLogExtra / _log_call 的 extra 组装（结构化日志契约）。"""

    def test_lane_log_extra_to_dict_has_all_fields(self):
        """LaneLogExtra.to_dict() 含运维溯源所需的全部字段。"""
        extra = LaneLogExtra(
            lane="tracker",
            method="fetch_trackers",
            downloader_id="dl1",
            timeout=30.0,
            duration=0.5,
            error_type=None,
        )
        d = extra.to_dict()
        assert d["lane"] == "tracker"
        assert d["method"] == "fetch_trackers"
        assert d["downloader_id"] == "dl1"
        assert d["timeout"] == 30.0
        assert d["duration"] == 0.5
        assert d["error_type"] is None

    def test_lane_log_extra_duration_rounded(self):
        """duration 在 to_dict 中被 round 到 3 位小数（与 _build_log_extra 一致风格）。"""
        extra = LaneLogExtra(
            lane="sync",
            method="m",
            downloader_id="dl",
            timeout=1.0,
            duration=0.123456,
        )
        assert extra.to_dict()["duration"] == 0.123

    def test_error_type_recorded_on_failure(self):
        """失败路径的 error_type 必须记录异常类名（运维告警依赖）。"""
        extra = LaneLogExtra(
            lane="tracker",
            method="m",
            downloader_id="dl",
            timeout=1.0,
            duration=0.01,
            error_type="ValueError",
        )
        assert extra.to_dict()["error_type"] == "ValueError"


class TestCallStatsAggregator:
    """_CallStatsAggregator 日志/flush 节流（sync-resource-governance code review 修复）。

    覆盖问题 3：高频成功路径不逐条落盘；失败路径不双重放大；窗口 flush + shutdown flush。

    测试策略：spy 模块级 logger 的 info/warning 方法（不依赖 logging 传播，避免全量 pytest
    时 root logger 级别被前序测试抬高导致 caplog 抓不到 INFO 的污染）。
    """

    def _make_agg(self):
        from app.services.downloader_api_runtime import _CallStatsAggregator

        return _CallStatsAggregator(window_seconds=60.0)  # 大窗口，确保不自动 flush

    @staticmethod
    def _extra_of(mock_call) -> dict:
        """提取 logger 调用的 extra dict（结构化字段，断言可靠）。"""
        return mock_call.kwargs.get("extra", {})

    def test_success_path_aggregated_not_per_call(self):
        """N 次成功调用 → record 累积到 buckets，不立即 flush 出 info 日志。"""
        from unittest.mock import patch

        agg = self._make_agg()
        with patch("app.services.downloader_api_runtime.logger") as mock_logger:
            for _ in range(100):
                agg.record_success("tracker", "fetch_trackers", "dl1", 0.01)
            # 窗口未到期 → 不应调用 info/warning
            assert mock_logger.info.call_count == 0
            assert mock_logger.warning.call_count == 0

            # flush 后应有 1 条 info 聚合日志
            agg.flush()
            assert mock_logger.info.call_count == 1
            extra = self._extra_of(mock_logger.info.call_args)
            assert extra["success_count"] == 100
            assert extra["failure_count"] == 0
            assert extra["total_count"] == 100

    def test_failure_path_recorded_as_warning_on_flush(self):
        """失败路径在 flush 时输出 warning（含 failure_count + last_error_type）。"""
        from unittest.mock import patch

        agg = self._make_agg()
        with patch("app.services.downloader_api_runtime.logger") as mock_logger:
            for _ in range(5):
                agg.record_failure("sync", "fetch_maindata", "dl1", 0.5, "ValueError")
            # 窗口未到期 → 不立即 flush
            assert mock_logger.warning.call_count == 0

            agg.flush()
            # failure_count > 0 → warning 级别
            assert mock_logger.warning.call_count == 1
            extra = self._extra_of(mock_logger.warning.call_args)
            assert extra["failure_count"] == 5
            assert extra["last_error_type"] == "ValueError"

    def test_shutdown_flushes_pending_stats(self):
        """shutdown 必须强制 flush 窗口内未到期的统计。"""
        from unittest.mock import patch

        agg = self._make_agg()
        agg.record_success("interactive", "speed", "dl1", 0.01)
        agg.record_failure("interactive", "speed", "dl1", 0.02, "TimeoutError")
        with patch("app.services.downloader_api_runtime.logger") as mock_logger:
            agg.flush()
            # success + failure 都有 → warning（因 failure > 0）
            assert mock_logger.warning.call_count == 1
            extra = self._extra_of(mock_logger.warning.call_args)
            assert extra["success_count"] == 1
            assert extra["failure_count"] == 1
            assert extra["last_error_type"] == "TimeoutError"

    async def test_runtime_call_uses_aggregator_no_per_call_info(self):
        """端到端：runtime.call 成功路径不逐条 info（聚合到窗口后才输出）。"""
        from unittest.mock import patch

        from app.services.downloader_api_runtime import DownloaderApiRuntime

        runtime = DownloaderApiRuntime()
        # 注入大窗口聚合器，确保测试期间不自动 flush
        runtime._stats = type(runtime._stats)(window_seconds=60.0)

        with patch("app.services.downloader_api_runtime.logger") as mock_logger:
            for i in range(20):
                await runtime.call(
                    "dl_agg",
                    DownloadLane.SYNC,
                    lambda i=i: i,
                    operation="agg_call",
                )
            # 不应有任何 per-call info（旧实现的 downloader_api_call 行已移除）
            info_msgs = [c for c in mock_logger.info.call_args_list if c.args and "downloader_api_call " in c.args[0]]
            assert info_msgs == [], "成功路径不应逐条 info 落盘"
            # 窗口未到期不应有聚合日志
            window_msgs = [
                c for c in mock_logger.info.call_args_list if c.args and "downloader_api_call_window" in c.args[0]
            ]
            assert window_msgs == [], "窗口未到期不应 flush"

            # flush 后才输出聚合
            runtime._stats.flush()
            window_msgs = [
                c for c in mock_logger.info.call_args_list if c.args and "downloader_api_call_window" in c.args[0]
            ]
            assert len(window_msgs) == 1
            extra = self._extra_of(window_msgs[0])
            assert extra["success_count"] == 20


class TestConvenienceFunction:
    """call_downloader_api 便捷封装契约。"""

    async def test_convenience_function_delegates_to_runtime(self):
        """call_downloader_api 转发到单例 downloader_api_runtime.call。"""
        from unittest.mock import patch, AsyncMock

        from app.services.downloader_api_runtime import call_downloader_api, downloader_api_runtime

        with patch.object(downloader_api_runtime, "call", new=AsyncMock(return_value="delegated")) as mock_call:
            result = await call_downloader_api(
                "dl_x",
                DownloadLane.TRACKER,
                lambda: None,
                args=(1,),
                kwargs={"k": "v"},
                operation="test",
                timeout=5.0,
            )
        assert result == "delegated"
        mock_call.assert_awaited_once()
        # 验证转发参数
        call_args = mock_call.call_args
        assert call_args.args[0] == "dl_x"  # downloader_id
        assert call_args.args[1] == DownloadLane.TRACKER  # lane
        assert call_args.kwargs["args"] == (1,)
        assert call_args.kwargs["kwargs"] == {"k": "v"}
        assert call_args.kwargs["operation"] == "test"
        assert call_args.kwargs["timeout"] == 5.0
