# -*- coding: utf-8 -*-
"""
下载器 API 调用隔离与调度层（downloader_api_runtime）

解决 qBittorrent / Transmission 远程调用通过默认线程池 + 无差别并发拖垮其它接口的问题。

核心机制：
1. 三 lane 独立 ThreadPoolExecutor，物理隔离不同功能的下载器调用：
   - tracker_lane: tracker 明细、tracker 状态、重宣告等。批量查询专用，不挤占 sync/interactive。
   - sync_lane: 种子列表、文件列表、下载器状态同步等重型周期同步。
   - interactive_lane: 用户触发的轻量操作（速度查询、备份、单种子查询等），预留较高优先级。
2. per-downloader threading.Semaphore：同一下载器的远程调用总并发受 DOWNLOADER_IO_CONCURRENCY 限制。
   关键设计：semaphore 由 executor 内 wrapper 自身 acquire/release，确保“同步线程实际结束前”
   不释放 per-downloader 容量 —— 即使 asyncio.wait_for 在调用方超时，底层线程仍在持有令牌继续执行，
   新请求只能阻塞在 sem.acquire() 上，从而避免 timeout 后真实远程并发突破上限。
3. call_downloader_api 统一封装：executor 选择 + semaphore 限流 + timeout + 异常归一 + lane 日志。
4. 日志聚合：成功/失败路径按 (lane, method, downloader_id) 窗口聚合，按 SYNC_DISK_FLUSH_INTERVAL_SECONDS
   合并输出，避免逐条 API 调用落盘（高频成功路径 + 失败双重放大治理）。

接入指引：替换散落的 asyncio.to_thread / 直接同步调用。
详见 PLANS/sync-resource-governance.md 阶段 2 与 code review 修复轮。
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class DownloadLane(str, Enum):
    """下载器调用 lane 分流。"""

    TRACKER = "tracker"  # tracker 明细/状态/重宣告（批量查询）
    SYNC = "sync"  # 种子列表/详情/状态同步（重型周期任务）
    INTERACTIVE = "interactive"  # 用户触发的轻量操作（速度查询/备份/单查询）


@dataclass
class LaneLogExtra:
    """call_downloader_api 的结构化日志 extra（便于运维还原 lane 占用）。"""

    lane: str
    method: str
    downloader_id: str
    timeout: float
    duration: float = 0.0
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lane": self.lane,
            "method": self.method,
            "downloader_id": self.downloader_id,
            "timeout": self.timeout,
            "duration": round(self.duration, 3),
            "error_type": self.error_type,
        }


class _CallStatsAggregator:
    """按 (lane, method, downloader_id) 窗口聚合 call_downloader_api 调用统计。

    目标（sync-resource-governance 日志/flush 节流）：
    - 成功路径不逐条 info 落盘，按 SYNC_DISK_FLUSH_INTERVAL_SECONDS 合并为一条结构化日志。
    - 失败路径在 runtime 层降级为 debug（业务侧 _fetch_single_trackers 等已有逐条 error/warning，
      避免 runtime + 业务侧双重放大），同样按窗口聚合统计 + last_error_type。
    - shutdown 时强制 flush 残留统计，避免进程退出前丢失窗口内数据。

    线程安全：被多个 lane executor 线程并发累加，使用 threading.Lock 保护。
    仅在 wrapper 线程内调用 record_success / record_failure（同步上下文），不涉及 asyncio。
    """

    def __init__(self, window_seconds: Optional[float] = None) -> None:
        self._window = window_seconds if window_seconds is not None else settings.SYNC_DISK_FLUSH_INTERVAL_SECONDS
        self._lock = threading.Lock()
        # key: (lane, method, downloader_id), value: stats dict
        self._buckets: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._last_flush = time.monotonic()

    def _maybe_flush_locked(self, *, force: bool) -> None:
        """检查窗口是否到期，到期则输出聚合日志并清空桶。调用方必须持有 _lock。"""
        now = time.monotonic()
        if not force and (now - self._last_flush) < self._window:
            return
        if not self._buckets:
            self._last_flush = now
            return
        buckets = self._buckets
        self._buckets = {}
        self._last_flush = now
        for (lane, method, downloader_id), stats in buckets.items():
            success = stats["success"]
            failure = stats["failure"]
            total = success + failure
            durations = stats["durations"]
            avg_dur = round(sum(durations) / len(durations), 3) if durations else 0.0
            max_dur = round(max(durations), 3) if durations else 0.0
            extra = {
                "lane": lane,
                "method": method,
                "downloader_id": downloader_id,
                "success_count": success,
                "failure_count": failure,
                "total_count": total,
                "avg_duration": avg_dur,
                "max_duration": max_dur,
                "last_error_type": stats.get("last_error_type"),
            }
            if failure > 0:
                logger.warning(
                    "downloader_api_call_window lane=%s method=%s downloader=%s "
                    "success=%d failure=%d avg=%.3fs max=%.3fs last_error=%s",
                    lane,
                    method,
                    downloader_id,
                    success,
                    failure,
                    avg_dur,
                    max_dur,
                    stats.get("last_error_type"),
                    extra=extra,
                )
            else:
                logger.info(
                    "downloader_api_call_window lane=%s method=%s downloader=%s " "success=%d avg=%.3fs max=%.3fs",
                    lane,
                    method,
                    downloader_id,
                    success,
                    avg_dur,
                    max_dur,
                    extra=extra,
                )

    def record_success(self, lane: str, method: str, downloader_id: str, duration: float) -> None:
        key = (lane, method, downloader_id)
        with self._lock:
            stats = self._buckets.setdefault(
                key,
                {
                    "success": 0,
                    "failure": 0,
                    "durations": [],
                    "last_error_type": None,
                },
            )
            stats["success"] += 1
            stats["durations"].append(duration)
            self._maybe_flush_locked(force=False)

    def record_failure(
        self,
        lane: str,
        method: str,
        downloader_id: str,
        duration: float,
        error_type: str,
    ) -> None:
        key = (lane, method, downloader_id)
        with self._lock:
            stats = self._buckets.setdefault(
                key,
                {
                    "success": 0,
                    "failure": 0,
                    "durations": [],
                    "last_error_type": None,
                },
            )
            stats["failure"] += 1
            stats["durations"].append(duration)
            stats["last_error_type"] = error_type
            self._maybe_flush_locked(force=False)

    def flush(self) -> None:
        """强制 flush 残留统计（shutdown 调用）。"""
        with self._lock:
            self._maybe_flush_locked(force=True)


# 进程级聚合器单例（被 DownloaderApiRuntime 与便捷封装共享）
_call_stats = _CallStatsAggregator()


class DownloaderApiRuntime:
    """下载器 API 调用运行时（进程级单例 downloader_api_runtime）。

    管理：
    - 三个 lane 专用 ThreadPoolExecutor（物理隔离，互不挤占）。
    - per-downloader threading.Semaphore 字典（同下载器总并发受控）。

    关键不变量（code review 修复）：
    - per-downloader semaphore 必须由 executor 内 wrapper 线程自身 acquire/release，
      确保“同步线程实际结束前”不释放容量。asyncio.wait_for 超时仅放弃等待 future，
      底层线程仍在持有令牌，新请求会被 semaphore 阻塞直到旧线程 release。
    """

    # 各 lane 的 executor 线程数（物理隔离的核心参数）
    # tracker_lane: 满足 QB_TRACKERS_CONCURRENCY(默认3) 的批量并发，留余量给重试。
    # sync_lane: 重型周期同步，单下载器串行即可，多下载器并行。
    # interactive_lane: 用户操作 + 速度轮询，预留较高并发保证响应。
    _LANE_WORKERS = {
        DownloadLane.TRACKER: 5,
        DownloadLane.SYNC: 4,
        DownloadLane.INTERACTIVE: 6,
    }

    def __init__(self) -> None:
        # 三 lane 独立 executor（线程名前缀便于诊断）
        self._executors: Dict[DownloadLane, ThreadPoolExecutor] = {
            lane: ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix=f"dl_{lane.value}",
            )
            for lane, workers in self._LANE_WORKERS.items()
        }
        # per-downloader 总并发信号量（按 downloader_id 懒创建）
        # 线程级 semaphore：在 wrapper 线程内 acquire/release，确保线程实际结束前不释放容量。
        self._per_downloader_sems: Dict[str, threading.Semaphore] = {}
        self._sem_lock = threading.Lock()
        # 日志聚合器（实例级，便于测试注入；默认共享进程级单例）
        self._stats = _call_stats

    def _get_semaphore(self, downloader_id: str) -> threading.Semaphore:
        """获取（或创建）指定下载器的并发信号量。

        DOWNLOADER_IO_CONCURRENCY(默认2) 限制同一下载器跨 lane 的总并发远程调用。
        返回 threading.Semaphore，由 executor 内 wrapper 线程 acquire/release。
        """
        with self._sem_lock:
            sem = self._per_downloader_sems.get(downloader_id)
            if sem is None:
                sem = threading.Semaphore(settings.DOWNLOADER_IO_CONCURRENCY)
                self._per_downloader_sems[downloader_id] = sem
            return sem

    async def call(
        self,
        downloader_id: str,
        lane: DownloadLane,
        func: Callable[..., Any],
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        operation: str = "",
        priority: int = 0,
    ) -> Any:
        """在指定 lane 的专用 executor 上调用同步下载器 API。

        Args:
            downloader_id: 下载器标识（用于 per-downloader 限流与日志）。
            lane: 调用所属 lane（决定 executor）。
            func: 同步可调用对象（如 client.torrents_trackers）。
            args: 透传给 func 的位置参数元组。
            kwargs: 透传给 func 的关键字参数字典。
            timeout: 单次调用超时秒数；None 取 settings.DOWNLOADER_API_TIMEOUT_SECONDS。
            operation: 人类可读操作名（日志溯源，如 "fetch_trackers"）。
            priority: 预留优先级参数（当前 lane 内不抢占，未来扩展用）。

        Returns:
            func 的返回值。

        Raises:
            asyncio.TimeoutError: 超时。
            Exception: func 抛出的原始异常（透传，不吞）。

        Notes:
            超时语义：wait_for 超时仅放弃等待 future，底层同步线程仍会继续运行直到 func 返回，
            期间持续持有 per-downloader semaphore。新调用会阻塞在 sem.acquire() 上直到旧线程
            release，从而保证真实远程并发恒不超过 DOWNLOADER_IO_CONCURRENCY。
        """
        effective_timeout = timeout if timeout is not None else settings.DOWNLOADER_API_TIMEOUT_SECONDS
        method_name = operation or getattr(func, "__name__", "unknown")
        sem = self._get_semaphore(downloader_id)
        executor = self._executors[lane]
        loop = asyncio.get_event_loop()
        call_kwargs = kwargs or {}

        log_extra = LaneLogExtra(
            lane=lane.value,
            method=method_name,
            downloader_id=downloader_id,
            timeout=effective_timeout,
        )
        stats = self._stats

        def _wrapper() -> Any:
            # 关键：semaphore 在工作线程内 acquire/release，确保线程实际结束前不释放容量。
            # 即使调用方 wait_for 超时，本线程仍持有 sem 直到 func 返回/抛出。
            sem.acquire()
            try:
                return func(*args, **call_kwargs)
            finally:
                sem.release()

        started = time.monotonic()
        future = loop.run_in_executor(executor, _wrapper)
        try:
            result = await asyncio.wait_for(future, timeout=effective_timeout)
            duration = time.monotonic() - started
            log_extra.duration = duration
            stats.record_success(lane.value, method_name, downloader_id, duration)
            return result
        except asyncio.TimeoutError:
            duration = time.monotonic() - started
            log_extra.duration = duration
            log_extra.error_type = "TimeoutError"
            # 超时后底层线程仍在运行，最终会通过 future done 自行走 success/failure 统计。
            # 此处只记录调用方视角的 timeout（debug 级，避免与业务侧 warning 双重放大）。
            logger.debug(
                "downloader_api_call_timeout lane=%s method=%s downloader=%s timeout=%.1fs",
                lane.value,
                method_name,
                downloader_id,
                effective_timeout,
                extra=log_extra.to_dict(),
            )
            # future 仍可能完成；附加 done callback 在线程结束后归档统计（不计入调用方等待）。
            _attach_done_stats(future, stats, lane.value, method_name, downloader_id, started)
            raise
        except Exception as e:
            duration = time.monotonic() - started
            log_extra.duration = duration
            log_extra.error_type = type(e).__name__
            # 失败路径在 runtime 层降级为 debug（业务侧 _fetch_single_trackers 等已有逐条 error），
            # 同时聚合到窗口统计（shutdown/maybe_flush 时统一输出 failure_count + last_error_type）。
            stats.record_failure(lane.value, method_name, downloader_id, duration, type(e).__name__)
            logger.debug(
                "downloader_api_call_error lane=%s method=%s downloader=%s error=%s",
                lane.value,
                method_name,
                downloader_id,
                type(e).__name__,
                extra=log_extra.to_dict(),
            )
            raise

    def shutdown(self) -> None:
        """关闭所有 lane executor（应用停机时调用）。

        顺序：
        1. flush 残留日志统计（避免窗口内数据丢失）。
        2. 关闭三 lane executor（cancel pending futures，不等待运行中线程）。
        """
        try:
            self._stats.flush()
        except Exception as exc:  # noqa: BLE001 - shutdown 不应因日志失败阻塞
            logger.warning("downloader_api_runtime stats flush failed during shutdown: %s", exc)
        for lane, executor in self._executors.items():
            executor.shutdown(wait=False, cancel_futures=True)
            logger.info("downloader_api_runtime lane=%s executor shutdown", lane.value)


def _attach_done_stats(
    future: "asyncio.Future",
    stats: _CallStatsAggregator,
    lane: str,
    method: str,
    downloader_id: str,
    started: float,
) -> None:
    """超时后给底层 future 附加 done callback，使线程最终完成时统计仍被归档。

    调用方已 raise TimeoutError，但底层线程可能稍后完成；此 callback 确保成功/失败计数
    不丢失（窗口聚合完整）。任何异常都被吞掉（callback 不能抛）。
    """

    def _on_done(fut: "asyncio.Future") -> None:
        try:
            duration = time.monotonic() - started
            exc = fut.exception()
            if exc is None:
                stats.record_success(lane, method, downloader_id, duration)
            else:
                stats.record_failure(lane, method, downloader_id, duration, type(exc).__name__)
        except Exception:  # noqa: BLE001
            pass

    future.add_done_callback(_on_done)


# 进程级单例
downloader_api_runtime = DownloaderApiRuntime()


async def call_downloader_api(
    downloader_id: str,
    lane: DownloadLane,
    func: Callable[..., Any],
    args: Tuple[Any, ...] = (),
    kwargs: Optional[Dict[str, Any]] = None,
    *,
    timeout: Optional[float] = None,
    operation: str = "",
) -> Any:
    """便捷封装：调用单例 downloader_api_runtime.call。

    用法（替代 await asyncio.to_thread(client.torrents_trackers, torrent_hash)）：

        trackers = await call_downloader_api(
            downloader_id, DownloadLane.TRACKER,
            client.torrents_trackers,
            args=(torrent_hash,),
            operation="fetch_trackers",
        )

    或对 kwargs：

        sync_data = await call_downloader_api(
            downloader_id, DownloadLane.SYNC,
            client.sync_maindata,
            kwargs={"rid": last_rid},
            operation="sync_maindata",
        )
    """
    return await downloader_api_runtime.call(
        downloader_id,
        lane,
        func,
        args=args,
        kwargs=kwargs,
        timeout=timeout,
        operation=operation,
    )
