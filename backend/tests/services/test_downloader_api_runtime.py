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
        """超时后 per-downloader semaphore 必须释放（不阻塞后续调用）。

        关键：wait_for 超时取消后，async with sem 的 finally 必须归还令牌。
        """
        runtime = _make_runtime()

        def slow():
            time.sleep(0.2)
            return "done"

        # 第一次调用超时
        with pytest.raises(asyncio.TimeoutError):
            await runtime.call(
                "dl1",
                DownloadLane.SYNC,
                slow,
                timeout=0.05,
                operation="slow1",
            )

        # 后续快速调用应立即可用（证明 semaphore 释放）
        result = await runtime.call(
            "dl1",
            DownloadLane.SYNC,
            lambda: "recovered",
            timeout=1.0,
            operation="recover",
        )
        assert result == "recovered"


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
