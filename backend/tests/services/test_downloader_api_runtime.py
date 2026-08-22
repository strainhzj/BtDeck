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
8. W2-2 交互容量保留（P0-05）：background 调用（TRACKER/SYNC）最多占用
   DOWNLOADER_BACKGROUND_CAPACITY 个槽，交互调用（INTERACTIVE）恒有保留槽；
   超时后租约不绕过；queue_wait_ms / remote_call_ms 进入日志与窗口统计。

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

        DOWNLOADER_IO_CONCURRENCY 默认 2。策略：发起 5 个并发慢调用（INTERACTIVE lane，
        只取 total 槽，直接检验总容量），观察同时运行的最大数量，应 ≤ 2。
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

        tasks = [
            runtime.call("dl_cap", DownloadLane.INTERACTIVE, slow_call, args=(i,), operation=f"c{i}") for i in range(5)
        ]
        await asyncio.gather(*tasks)

        # 同下载器跨 lane（这里都 INTERACTIVE）总并发受 DOWNLOADER_IO_CONCURRENCY(默认2) 限制
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

        # 2 个不同下载器，各发 2 个并发（INTERACTIVE lane，不受 background 槽约束）
        tasks = []
        for dl in ("dl_a", "dl_b"):
            for _ in range(2):
                tasks.append(runtime.call(dl, DownloadLane.INTERACTIVE, slow_call, operation="parallel"))
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


class TestInteractiveCapacityReservation:
    """W2-2 交互容量保留（P0-05）：后台调用不能占满每下载器全部并发槽。

    两级容量模型：background（TRACKER/SYNC）必须同时取得 background 槽与 total 槽，
    interactive 只取 total 槽；后台最多占用 DOWNLOADER_BACKGROUND_CAPACITY(默认1) 个槽，
    其余槽保留给交互请求。全部用例使用真实慢 func + threading.Event（不依赖真实下载器）。
    """

    async def test_interactive_inserts_while_background_running(self):
        """🔴 物理事实：后台调用（SYNC 慢 func）运行期间，交互调用（INTERACTIVE）立即执行。

        后台 func 由 Event 控制在运行 5s 期间持有两个槽；交互调用只取 total 槽（2-1=1 空闲），
        应几乎瞬时完成（显著小于后台总时长）。修复前（后台占满全部 2 槽）交互需排队等后台结束。
        """
        runtime = _make_runtime()
        bg_entered = threading.Event()
        bg_release = threading.Event()

        def slow_bg():
            bg_entered.set()  # 后台已进入 func（持有 background + total 槽）
            bg_release.wait(timeout=5.0)  # 控制后台结束（模拟长后台任务）
            return "bg"

        bg_task = asyncio.create_task(runtime.call("dl_resv", DownloadLane.SYNC, slow_bg, operation="bg"))
        # to_thread 让出事件循环，bg_task 才能被调度并启动 executor 线程
        assert await asyncio.to_thread(bg_entered.wait, 5.0), "后台调用未进入运行态"

        interactive_start = time.monotonic()
        result = await runtime.call(
            "dl_resv",
            DownloadLane.INTERACTIVE,
            lambda: "interactive",
            operation="interactive",
        )
        interactive_elapsed = time.monotonic() - interactive_start
        assert result == "interactive"
        # 后台至少还要运行 5s；交互若排队将等待后台结束 → 显著超过 1s 即失败
        assert interactive_elapsed < 1.0, f"交互调用被后台任务阻塞: {interactive_elapsed:.3f}s"

        bg_release.set()
        await asyncio.wait_for(bg_task, timeout=5.0)

    async def test_multiple_background_calls_respect_capacity(self):
        """多个 background 调用并发：同一时间 active_background ≤ background_capacity(默认1)。

        用线程计数器统计同时进入 func 的后台调用数；4 个 TRACKER 并发后台调用最多 1 个运行。
        """
        runtime = _make_runtime()
        counter = {"current": 0, "max": 0}
        lock = threading.Lock()
        release = threading.Event()

        def bg_call(idx):
            with lock:
                counter["current"] += 1
                counter["max"] = max(counter["max"], counter["current"])
            try:
                release.wait(timeout=5.0)
            finally:
                with lock:
                    counter["current"] -= 1
            return idx

        tasks = [
            runtime.call("dl_bgcap", DownloadLane.TRACKER, bg_call, args=(i,), operation=f"bg{i}") for i in range(4)
        ]
        await asyncio.sleep(0.3)  # 让线程尽量进入 func（容量内 1 个，其余阻塞在 background 槽）
        release.set()
        await asyncio.gather(*tasks)
        assert counter["max"] <= 1, f"background 并发突破后台容量: max={counter['max']}（应 ≤1）"

    async def test_interactive_never_consumes_background_slot(self):
        """交互调用只取 total 槽：2 个并发交互调用不占用 background 槽。

        后台容量为 1 时，若交互调用误取 background 槽，两个并发交互会互相阻塞；
        此处断言两个交互调用可同时运行（total 容量 2 内），且后续后台调用仍能立即执行。
        """
        runtime = _make_runtime()
        counter = {"current": 0, "max": 0}
        lock = threading.Lock()

        def interactive_call(idx):
            with lock:
                counter["current"] += 1
                counter["max"] = max(counter["max"], counter["current"])
            time.sleep(0.15)
            with lock:
                counter["current"] -= 1
            return idx

        tasks = [
            runtime.call("dl_bgfree", DownloadLane.INTERACTIVE, interactive_call, args=(i,), operation=f"i{i}")
            for i in range(2)
        ]
        await asyncio.gather(*tasks)
        assert counter["max"] == 2, f"两个并发交互调用应同时运行（不占 background 槽），max={counter['max']}"

        # background 槽未被交互占用：后台调用仍立即可用
        result = await runtime.call("dl_bgfree", DownloadLane.SYNC, lambda: "bg_ok", operation="after")
        assert result == "bg_ok"

    async def test_downloader_isolation_with_background(self):
        """每下载器隔离：A 下载器后台拥堵（占满槽）不影响 B 下载器交互调用。"""
        runtime = _make_runtime()
        bg_entered = threading.Event()
        bg_release = threading.Event()

        def slow_bg():
            bg_entered.set()
            bg_release.wait(timeout=5.0)
            return "bg"

        bg_task = asyncio.create_task(runtime.call("dl_a", DownloadLane.SYNC, slow_bg, operation="bg_a"))
        # to_thread 让出事件循环，bg_task 才能被调度并启动 executor 线程
        assert await asyncio.to_thread(bg_entered.wait, 5.0), "A 下载器后台调用未进入运行态"

        start = time.monotonic()
        result = await runtime.call("dl_b", DownloadLane.INTERACTIVE, lambda: "b_ok", operation="b")
        elapsed = time.monotonic() - start
        assert result == "b_ok"
        assert elapsed < 1.0, f"B 下载器交互调用被 A 下载器拥堵阻塞: {elapsed:.3f}s"

        bg_release.set()
        await asyncio.wait_for(bg_task, timeout=5.0)


class TestLeaseLifecycle:
    """W2-2 租约生命周期：超时/异常/降级配置不泄露、不绕过容量。"""

    async def test_timeout_lease_not_bypassed_before_thread_finishes(self):
        """调用方超时后，底层线程完成前租约不释放：新调用不提前执行。

        修复前若 wait_for 超时立即释放信号量，新调用会提前执行、真实并发突破上限；
        修复后（线程持有租约直到 func 返回）新调用必须阻塞等待。
        """
        runtime = _make_runtime()
        thread_started = threading.Event()
        release_thread = threading.Event()
        new_call_ran = threading.Event()

        def slow_bg():
            thread_started.set()
            release_thread.wait(timeout=5.0)  # 由测试控制底层线程何时结束
            return "bg"

        def fast_call():
            new_call_ran.set()
            return "ok"

        # 第一次调用：极短超时 → TimeoutError，但底层线程仍在运行（持 background + total 槽）
        with pytest.raises(asyncio.TimeoutError):
            await runtime.call("dl_lease", DownloadLane.SYNC, slow_bg, timeout=0.05, operation="lease1")
        assert await asyncio.to_thread(thread_started.wait, 5.0), "底层线程未进入运行态"

        # 新调用（同下载器）：应阻塞在 sem.acquire()，不能提前执行
        new_task = asyncio.create_task(
            runtime.call("dl_lease", DownloadLane.SYNC, fast_call, timeout=5.0, operation="lease2")
        )
        await asyncio.sleep(0.3)  # 若租约被绕过，此时应已执行
        assert not new_call_ran.is_set(), "超时后租约被绕过：新调用提前执行"

        # 释放底层线程后，新调用恢复执行
        release_thread.set()
        result = await asyncio.wait_for(new_task, timeout=5.0)
        assert result == "ok"
        assert new_call_ran.is_set()

    async def test_exception_releases_both_leases(self):
        """func 抛异常后，background 槽与 total 槽都必须释放（后续调用可正常执行）。"""
        runtime = _make_runtime()

        def boom():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await runtime.call("dl_leak", DownloadLane.SYNC, boom, operation="boom")

        # total 槽已释放：交互调用立即可用
        result = await runtime.call("dl_leak", DownloadLane.INTERACTIVE, lambda: "i_ok", operation="after_i")
        assert result == "i_ok"
        # background 槽已释放：后台调用立即可用
        result = await runtime.call("dl_leak", DownloadLane.SYNC, lambda: "bg_ok", operation="after_bg")
        assert result == "bg_ok"

    async def test_shutdown_no_lease_leak(self):
        """shutdown 后无租约泄漏：executor 正常关闭、统计正常 flush。"""
        runtime = _make_runtime()
        await runtime.call("dl_shut", DownloadLane.SYNC, lambda: "ok", operation="warmup")
        runtime.shutdown()
        for lane, executor in runtime._executors.items():
            assert executor._shutdown, f"lane={lane} executor 未被 shutdown"

    async def test_degraded_config_background_capacity_zero(self):
        """矛盾组合防护：总容量=1 且后台容量=1 → 自动降级（background 实际容量 0）且交互可用。

        配置组合会占满全部槽、破坏交互保留槽；runtime 应自动串行（后台只竞争 total 槽）、
        记录降级警告、不抛异常阻断启动，交互调用仍可用。
        """
        from unittest.mock import patch

        with (
            patch("app.core.config.settings.DOWNLOADER_IO_CONCURRENCY", 1),
            patch("app.core.config.settings.DOWNLOADER_BACKGROUND_CAPACITY", 1),
        ):
            runtime = _make_runtime()
            with patch("app.services.downloader_api_runtime.logger") as mock_logger:
                # 交互调用可用（total 槽 1）
                result = await runtime.call("dl_degraded", DownloadLane.INTERACTIVE, lambda: "ok", operation="i")
                assert result == "ok"
                # background 实际容量降级为 0（无 background 槽）
                _, bg_sem = runtime._get_semaphores("dl_degraded")
                assert bg_sem is None, "矛盾组合应降级 background 容量为 0"
                # background 调用仍可执行（跳过 background 槽，与交互串行共享 total 槽，不死锁）
                result = await runtime.call("dl_degraded", DownloadLane.SYNC, lambda: "bg", operation="bg")
                assert result == "bg"
            warnings = [
                c for c in mock_logger.warning.call_args_list if c.args and "background_capacity" in c.args[0]
            ]
            assert warnings, "矛盾组合未记录降级警告日志"


class TestTimingObservability:
    """W2-2 排队/远程耗时分离：queue_wait_ms 与 remote_call_ms 进入日志与窗口统计。"""

    def test_lane_log_extra_contains_timings(self):
        """LaneLogExtra.to_dict() 含 queue_wait_ms / remote_call_ms 字段。"""
        extra = LaneLogExtra(
            lane="sync",
            method="m",
            downloader_id="dl",
            timeout=1.0,
            duration=0.5,
            queue_wait_ms=0.123,
            remote_call_ms=0.456,
        )
        d = extra.to_dict()
        assert d["queue_wait_ms"] == 0.123
        assert d["remote_call_ms"] == 0.456

    async def test_error_log_contains_timings(self):
        """失败路径的调用日志 extra 必须含 queue_wait_ms 与 remote_call_ms（真实测量值）。"""
        from unittest.mock import patch

        runtime = _make_runtime()

        def boom():
            raise RuntimeError("x")

        with patch("app.services.downloader_api_runtime.logger") as mock_logger:
            with pytest.raises(RuntimeError):
                await runtime.call("dl_tim", DownloadLane.SYNC, boom, operation="tim")
        error_calls = [
            c for c in mock_logger.info.call_args_list if c.args and "downloader_api_call_error" in c.args[0]
        ]
        assert len(error_calls) == 1
        extra = error_calls[0].kwargs.get("extra", {})
        assert "queue_wait_ms" in extra, "失败日志缺少 queue_wait_ms"
        assert "remote_call_ms" in extra, "失败日志缺少 remote_call_ms"

    async def test_aggregator_window_includes_queue_wait_stats(self):
        """窗口聚合日志含 avg_queue_wait_ms / max_queue_wait_ms（真实累计值）。"""
        from unittest.mock import patch

        from app.services.downloader_api_runtime import _CallStatsAggregator

        agg = _CallStatsAggregator(window_seconds=60.0)
        with patch("app.services.downloader_api_runtime.logger") as mock_logger:
            agg.record_success("sync", "fetch_maindata", "dl1", 0.01, queue_wait_ms=0.02)
            agg.record_success("sync", "fetch_maindata", "dl1", 0.03, queue_wait_ms=0.10)
            agg.flush()
        window_calls = [
            c for c in mock_logger.info.call_args_list if c.args and "downloader_api_call_window" in c.args[0]
        ]
        assert len(window_calls) == 1
        extra = window_calls[0].kwargs.get("extra", {})
        assert extra["avg_queue_wait_ms"] == 0.06
        assert extra["max_queue_wait_ms"] == 0.1


class TestPriorityParamRemoved:
    """W2-2：未生效的 priority 参数已删除（P0 不实现复杂优先级队列）。"""

    def test_call_signature_has_no_priority(self):
        """DownloaderApiRuntime.call 签名不含 priority。"""
        import inspect

        assert "priority" not in inspect.signature(DownloaderApiRuntime.call).parameters

    def test_call_downloader_api_signature_has_no_priority(self):
        """call_downloader_api 签名不含 priority。"""
        import inspect

        from app.services.downloader_api_runtime import call_downloader_api

        assert "priority" not in inspect.signature(call_downloader_api).parameters
