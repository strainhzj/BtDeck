# -*- coding: utf-8 -*-
"""
下载器 API 调用隔离与调度层（downloader_api_runtime）

解决 qBittorrent / Transmission 远程调用通过默认线程池 + 无差别并发拖垮其它接口的问题。

核心机制：
1. 三 lane 独立 ThreadPoolExecutor，物理隔离不同功能的下载器调用：
   - tracker_lane: tracker 明细、tracker 状态、重宣告等。批量查询专用，不挤占 sync/interactive。
   - sync_lane: 种子列表、文件列表、下载器状态同步等重型周期同步。
   - interactive_lane: 用户触发的轻量操作（速度查询、备份、单种子查询等），预留较高优先级。
2. 两级 per-downloader threading.Semaphore（W2-2 交互容量保留，P0-05）：
   - total semaphore：同一下载器跨 lane 远程调用总并发受 DOWNLOADER_IO_CONCURRENCY 限制。
   - background semaphore：background 调用（TRACKER/SYNC lane）必须同时取得 background 槽
     和 total 槽；interactive 调用（INTERACTIVE lane）只取得 total 槽。这样后台最多占用
     DOWNLOADER_BACKGROUND_CAPACITY(默认1) 个槽，其余 total 槽始终保留给交互请求，
     后台任务无法占满每下载器全部并发槽。
   关键设计：两级 semaphore 均由 executor 内 wrapper 线程自身 acquire/release，确保
   "同步线程实际结束前"不释放 per-downloader 容量 —— 即使 asyncio.wait_for 在调用方
   超时，底层线程仍在持有令牌继续执行，新请求只能阻塞在 sem.acquire() 上，从而避免
   timeout 后真实远程并发突破上限。acquire 顺序 background→total，release 顺序
   total→background（interactive 永不 acquire background，不存在循环等待）。
3. call_downloader_api 统一封装：executor 选择 + 两级 semaphore 限流 + timeout + 异常归一 + lane 日志。
4. 日志聚合：成功/失败路径按 (lane, method, downloader_id) 窗口聚合，按 SYNC_DISK_FLUSH_INTERVAL_SECONDS
   合并输出，避免逐条 API 调用落盘（高频成功路径 + 失败双重放大治理）；
   排队耗时 queue_wait_ms 与远程耗时 remote_call_ms 进入结构化日志与窗口统计。

接入指引：替换散落的 asyncio.to_thread / 直接同步调用。
详见 PLANS/sync-resource-governance.md 阶段 2、PLANS/sync-database-blocking-remediation.md W2-2
与 code review 修复轮。
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
    """下载器调用 lane 分流。

    容量语义（W2-2 交互容量保留）：
    - TRACKER / SYNC 为 background 调用（定时同步/批量任务）：除 total 槽外还必须
      取得 background 槽，保证后台最多占用 DOWNLOADER_BACKGROUND_CAPACITY 个槽，
      其余 total 槽始终保留给交互请求。
    - INTERACTIVE 为交互调用（用户触发的速度查询、单种子查询等）：只取得 total 槽，
      永不 acquire background 槽（交互与后台之间不存在循环等待）。
    """

    TRACKER = "tracker"  # tracker 明细/状态/重宣告（批量查询）→ background 容量
    SYNC = "sync"  # 种子列表/详情/状态同步（重型周期任务）→ background 容量
    INTERACTIVE = "interactive"  # 用户触发的轻量操作（速度查询/备份/单查询）→ 交互容量


# background（后台）lane 集合：定时同步类调用，受 background_capacity 限制
_BACKGROUND_LANES = frozenset({DownloadLane.TRACKER, DownloadLane.SYNC})


def is_background_lane(lane: DownloadLane) -> bool:
    """lane 是否为 background（后台同步）调用。

    background 调用必须同时取得 background 槽和 total 槽；interactive 只取 total 槽。
    """
    return lane in _BACKGROUND_LANES


@dataclass
class LaneLogExtra:
    """call_downloader_api 的结构化日志 extra（便于运维还原 lane 占用）。"""

    lane: str
    method: str
    downloader_id: str
    timeout: float
    duration: float = 0.0
    error_type: Optional[str] = None
    # W2-2：排队耗时（wrapper 开始 → 两级 semaphore 全部取得）与远程调用耗时（func 执行）。
    # 超时/异常路径为尽力而为（线程未结束时取当前值，可能为 0）。
    queue_wait_ms: float = 0.0
    remote_call_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lane": self.lane,
            "method": self.method,
            "downloader_id": self.downloader_id,
            "timeout": self.timeout,
            "duration": round(self.duration, 3),
            "error_type": self.error_type,
            "queue_wait_ms": round(self.queue_wait_ms, 3),
            "remote_call_ms": round(self.remote_call_ms, 3),
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
            queue_waits = stats["queue_waits"]
            avg_queue_wait_ms = round(sum(queue_waits) / len(queue_waits), 3) if queue_waits else 0.0
            max_queue_wait_ms = round(max(queue_waits), 3) if queue_waits else 0.0
            extra = {
                "lane": lane,
                "method": method,
                "downloader_id": downloader_id,
                "success_count": success,
                "failure_count": failure,
                "total_count": total,
                "avg_duration": avg_dur,
                "max_duration": max_dur,
                "avg_queue_wait_ms": avg_queue_wait_ms,
                "max_queue_wait_ms": max_queue_wait_ms,
                "last_error_type": stats.get("last_error_type"),
            }
            if failure > 0:
                logger.warning(
                    "downloader_api_call_window lane=%s method=%s downloader=%s "
                    "success=%d failure=%d avg=%.3fs max=%.3fs avg_queue_wait=%.1fms max_queue_wait=%.1fms "
                    "last_error=%s",
                    lane,
                    method,
                    downloader_id,
                    success,
                    failure,
                    avg_dur,
                    max_dur,
                    avg_queue_wait_ms,
                    max_queue_wait_ms,
                    stats.get("last_error_type"),
                    extra=extra,
                )
            else:
                logger.info(
                    "downloader_api_call_window lane=%s method=%s downloader=%s "
                    "success=%d avg=%.3fs max=%.3fs avg_queue_wait=%.1fms max_queue_wait=%.1fms",
                    lane,
                    method,
                    downloader_id,
                    success,
                    avg_dur,
                    max_dur,
                    avg_queue_wait_ms,
                    max_queue_wait_ms,
                    extra=extra,
                )

    def record_success(
        self,
        lane: str,
        method: str,
        downloader_id: str,
        duration: float,
        queue_wait_ms: float = 0.0,
    ) -> None:
        key = (lane, method, downloader_id)
        with self._lock:
            stats = self._buckets.setdefault(
                key,
                {
                    "success": 0,
                    "failure": 0,
                    "durations": [],
                    "queue_waits": [],
                    "last_error_type": None,
                },
            )
            stats["success"] += 1
            stats["durations"].append(duration)
            stats["queue_waits"].append(queue_wait_ms)
            self._maybe_flush_locked(force=False)

    def record_failure(
        self,
        lane: str,
        method: str,
        downloader_id: str,
        duration: float,
        error_type: str,
        queue_wait_ms: float = 0.0,
    ) -> None:
        key = (lane, method, downloader_id)
        with self._lock:
            stats = self._buckets.setdefault(
                key,
                {
                    "success": 0,
                    "failure": 0,
                    "durations": [],
                    "queue_waits": [],
                    "last_error_type": None,
                },
            )
            stats["failure"] += 1
            stats["durations"].append(duration)
            stats["queue_waits"].append(queue_wait_ms)
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
    - per-downloader 两级 threading.Semaphore 字典（W2-2 交互容量保留）：
      total 信号量（DOWNLOADER_IO_CONCURRENCY）限制同下载器跨 lane 总并发；
      background 信号量（DOWNLOADER_BACKGROUND_CAPACITY）限制后台调用占用槽数。
      background 调用（TRACKER/SYNC）必须同时取得两个槽，interactive 只取 total 槽，
      后台最多占 background_capacity 个槽，其余槽始终可服务交互请求。

    关键不变量（code review 修复 + W2-2）：
    - per-downloader semaphore 必须由 executor 内 wrapper 线程自身 acquire/release，
      确保"同步线程实际结束前"不释放容量。asyncio.wait_for 超时仅放弃等待 future，
      底层线程仍在持有令牌，新请求会被 semaphore 阻塞直到旧线程 release。
    - acquire 顺序 background→total，release 顺序 total→background；
      interactive 永不 acquire background 槽，两级之间不存在循环等待。
    - 矛盾组合防护：总容量=1 且后台容量>=1 时（配置破坏交互保留槽），background
      容量自动降级为 0（background 调用仅竞争 total 槽，与交互串行）并记录警告，
      不抛异常阻断启动。
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
        # per-downloader 后台容量信号量（W2-2）：background 调用额外获取，interactive 不获取
        # 值为 None 表示该下载器 background 有效容量为 0（矛盾组合降级后缓存，避免重复解析告警）
        self._per_downloader_bg_sems: Dict[str, Optional[threading.Semaphore]] = {}
        self._sem_lock = threading.Lock()
        # 日志聚合器（实例级，便于测试注入；默认共享进程级单例）
        self._stats = _call_stats

    def _resolve_background_capacity(self) -> int:
        """解析 background 容量（含矛盾组合降级）。

        有效值 = min(配置值, total_capacity - 1)，下限 0。当配置值超过有效值时
        （典型：total=1 且 background=1 会占满全部槽、破坏交互保留槽），自动降级
        并记录 warning（自动串行，不抛异常阻断启动）。
        """
        total_capacity = settings.DOWNLOADER_IO_CONCURRENCY
        configured = settings.DOWNLOADER_BACKGROUND_CAPACITY
        effective = min(configured, max(total_capacity - 1, 0))
        if effective < configured:
            logger.warning(
                "DOWNLOADER_BACKGROUND_CAPACITY=%d 与 DOWNLOADER_IO_CONCURRENCY=%d 组合会破坏"
                "交互保留槽，已自动降级 background_capacity=%d（后台调用与交互串行共享剩余槽）",
                configured,
                total_capacity,
                effective,
            )
        return effective

    def _get_semaphores(self, downloader_id: str) -> Tuple[threading.Semaphore, Optional[threading.Semaphore]]:
        """获取（或创建）指定下载器的两级并发信号量。

        DOWNLOADER_IO_CONCURRENCY(默认2) 限制同下载器跨 lane 的总并发远程调用；
        DOWNLOADER_BACKGROUND_CAPACITY(默认1) 限制 background 调用占用槽数。
        返回 (total_sem, background_sem)；background 有效容量为 0 时返回 None
        （背景调用只竞争 total 槽，不会死锁）。由 executor 内 wrapper 线程 acquire/release。
        """
        with self._sem_lock:
            sem = self._per_downloader_sems.get(downloader_id)
            if sem is None:
                sem = threading.Semaphore(settings.DOWNLOADER_IO_CONCURRENCY)
                self._per_downloader_sems[downloader_id] = sem
            if downloader_id not in self._per_downloader_bg_sems:
                # 容量为 0 时也缓存 None（按 downloader_id 懒创建一次），
                # 避免每次调用重复解析配置并重复输出降级警告
                bg_capacity = self._resolve_background_capacity()
                new_bg_sem: Optional[threading.Semaphore] = None
                if bg_capacity > 0:
                    new_bg_sem = threading.Semaphore(bg_capacity)
                self._per_downloader_bg_sems[downloader_id] = new_bg_sem
            bg_sem = self._per_downloader_bg_sems[downloader_id]
            return sem, bg_sem

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
    ) -> Any:
        """在指定 lane 的专用 executor 上调用同步下载器 API。

        Args:
            downloader_id: 下载器标识（用于 per-downloader 限流与日志）。
            lane: 调用所属 lane（决定 executor 与 后台/交互容量语义）。
            func: 同步可调用对象（如 client.torrents_trackers）。
            args: 透传给 func 的位置参数元组。
            kwargs: 透传给 func 的关键字参数字典。
            timeout: 单次调用总预算秒数（含排队等待与远程调用）；None 取
                settings.DOWNLOADER_API_TIMEOUT_SECONDS。
            operation: 人类可读操作名（日志溯源，如 "fetch_trackers"）。

        Returns:
            func 的返回值。

        Raises:
            asyncio.TimeoutError: 超时。
            Exception: func 抛出的原始异常（透传，不吞）。

        Notes:
            容量语义（W2-2）：TRACKER/SYNC 为 background 调用，必须同时取得 background 槽
            与 total 槽；INTERACTIVE 为交互调用，只取得 total 槽。后台最多占用
            DOWNLOADER_BACKGROUND_CAPACITY 个槽，其余槽保留给交互请求。
            超时语义：asyncio.wait_for 的 timeout 是总预算（含排队等待与远程调用）——
            排队时间也计入超时。超时仅放弃等待 future，底层同步线程仍会继续运行直到
            func 返回，期间持续持有两级 semaphore。新调用会阻塞在 sem.acquire() 上直到
            旧线程 release，从而保证真实远程并发恒不超过 DOWNLOADER_IO_CONCURRENCY，
            且超时不绕过容量租约。
        """
        effective_timeout = timeout if timeout is not None else settings.DOWNLOADER_API_TIMEOUT_SECONDS
        method_name = operation or getattr(func, "__name__", "unknown")
        total_sem, bg_sem = self._get_semaphores(downloader_id)
        background = is_background_lane(lane)
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
        # 线程内实测的排队/远程耗时：成功路径精确；超时/异常路径尽力而为（可能为 0）。
        timings: Dict[str, float] = {"queue_wait_ms": 0.0, "remote_call_ms": 0.0}

        def _wrapper() -> Any:
            # 两级容量租约：
            # - background 调用：先取 background 槽，再取 total 槽（后台最多占 background_capacity 槽）。
            # - interactive 调用：只取 total 槽（保留槽永远不被后台占用）。
            # acquire 顺序 background→total，release 顺序 total→background；
            # interactive 永不 acquire background 槽，两级之间无循环等待。
            # 关键：semaphore 在工作线程内 acquire/release，确保线程实际结束前不释放容量。
            # 即使调用方 wait_for 超时，本线程仍持有令牌直到 func 返回/抛出。
            acquire_start = time.monotonic()
            if background and bg_sem is not None:
                bg_sem.acquire()
            total_sem.acquire()
            timings["queue_wait_ms"] = (time.monotonic() - acquire_start) * 1000.0
            try:
                remote_start = time.monotonic()
                result = func(*args, **call_kwargs)
                return result
            finally:
                timings["remote_call_ms"] = (time.monotonic() - remote_start) * 1000.0
                total_sem.release()
                if background and bg_sem is not None:
                    bg_sem.release()

        started = time.monotonic()
        future = loop.run_in_executor(executor, _wrapper)
        try:
            result = await asyncio.wait_for(future, timeout=effective_timeout)
            duration = time.monotonic() - started
            log_extra.duration = duration
            log_extra.queue_wait_ms = timings["queue_wait_ms"]
            log_extra.remote_call_ms = timings["remote_call_ms"]
            stats.record_success(lane.value, method_name, downloader_id, duration, timings["queue_wait_ms"])
            return result
        except asyncio.TimeoutError:
            duration = time.monotonic() - started
            log_extra.duration = duration
            log_extra.queue_wait_ms = timings["queue_wait_ms"]
            log_extra.remote_call_ms = timings["remote_call_ms"]
            log_extra.error_type = "TimeoutError"
            # 超时后底层线程仍在运行，最终会通过 future done 自行走 success/failure 统计。
            # 超时是孤儿清理 manifest 拉取慢的核心成因，提到 INFO 级便于 docker 下定位。
            logger.info(
                "downloader_api_call_timeout lane=%s method=%s downloader=%s timeout=%.1fs "
                "duration=%.1fs queue_wait_ms=%.1f remote_call_ms=%.1f",
                lane.value,
                method_name,
                downloader_id,
                effective_timeout,
                duration,
                timings["queue_wait_ms"],
                timings["remote_call_ms"],
                extra=log_extra.to_dict(),
            )
            # future 仍可能完成；附加 done callback 在线程结束后归档统计（不计入调用方等待）。
            _attach_done_stats(future, stats, lane.value, method_name, downloader_id, started, timings)
            raise
        except Exception as e:
            duration = time.monotonic() - started
            log_extra.duration = duration
            log_extra.queue_wait_ms = timings["queue_wait_ms"]
            log_extra.remote_call_ms = timings["remote_call_ms"]
            log_extra.error_type = type(e).__name__
            # 失败路径在 runtime 层记录（业务侧 _fetch_single_trackers 等已有逐条 error），
            # 同时聚合到窗口统计（shutdown/maybe_flush 时统一输出 failure_count + last_error_type）。
            stats.record_failure(
                lane.value,
                method_name,
                downloader_id,
                duration,
                type(e).__name__,
                timings["queue_wait_ms"],
            )
            logger.info(
                "downloader_api_call_error lane=%s method=%s downloader=%s error=%s duration=%.1fs "
                "queue_wait_ms=%.1f remote_call_ms=%.1f",
                lane.value,
                method_name,
                downloader_id,
                type(e).__name__,
                duration,
                timings["queue_wait_ms"],
                timings["remote_call_ms"],
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
    timings: Dict[str, float],
) -> None:
    """超时后给底层 future 附加 done callback，使线程最终完成时统计仍被归档。

    调用方已 raise TimeoutError，但底层线程可能稍后完成；此 callback 确保成功/失败计数
    不丢失（窗口聚合完整）。任何异常都被吞掉（callback 不能抛）。
    """

    def _on_done(fut: "asyncio.Future") -> None:
        try:
            duration = time.monotonic() - started
            queue_wait_ms = timings["queue_wait_ms"]
            exc = fut.exception()
            if exc is None:
                stats.record_success(lane, method, downloader_id, duration, queue_wait_ms)
            else:
                stats.record_failure(lane, method, downloader_id, duration, type(exc).__name__, queue_wait_ms)
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
