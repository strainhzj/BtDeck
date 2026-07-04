# -*- coding: utf-8 -*-
"""
下载器 API 调用隔离与调度层（downloader_api_runtime）

解决 qBittorrent / Transmission 远程调用通过默认线程池 + 无差别并发拖垮其它接口的问题。

核心机制：
1. 三 lane 独立 ThreadPoolExecutor，物理隔离不同功能的下载器调用：
   - tracker_lane: tracker 明细、tracker 状态、重宣告等。批量查询专用，不挤占 sync/interactive。
   - sync_lane: 种子列表、文件列表、下载器状态同步等重型周期同步。
   - interactive_lane: 用户触发的轻量操作（备份、单种子查询等），预留较高优先级。
2. per-downloader Semaphore：同一下载器的远程调用总并发受 DOWNLOADER_IO_CONCURRENCY 限制，
   避免单个 qB WebUI 被多任务同时打满。
3. call_downloader_api 统一封装：executor 选择 + semaphore 限流 + timeout + 异常归一 + lane 日志。

接入指引：替换散落的 asyncio.to_thread / 直接同步调用。
详见 PLANS/sync-resource-governance.md 阶段 2。
"""

import asyncio
import logging
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
    INTERACTIVE = "interactive"  # 用户触发的轻量操作（备份/单查询）


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


class DownloaderApiRuntime:
    """下载器 API 调用运行时（进程级单例 downloader_api_runtime）。

    管理：
    - 三个 lane 专用 ThreadPoolExecutor（物理隔离，互不挤占）。
    - per-downloader Semaphore 字典（同下载器总并发受控）。
    """

    # 各 lane 的 executor 线程数（物理隔离的核心参数）
    # tracker_lane: 满足 QB_TRACKER_CONCURRENCY(默认3) 的批量并发，留余量给重试。
    # sync_lane: 重型周期同步，单下载器串行即可，多下载器并行。
    # interactive_lane: 用户操作，预留较高并发保证响应。
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
        self._per_downloader_sems: Dict[str, asyncio.Semaphore] = {}
        self._sem_lock = asyncio.Lock()

    async def _get_semaphore(self, downloader_id: str) -> asyncio.Semaphore:
        """获取（或创建）指定下载器的并发信号量。

        DOWNLOADER_IO_CONCURRENCY(默认2) 限制同一下载器跨 lane 的总并发远程调用。
        """
        async with self._sem_lock:
            if downloader_id not in self._per_downloader_sems:
                self._per_downloader_sems[downloader_id] = asyncio.Semaphore(settings.DOWNLOADER_IO_CONCURRENCY)
            return self._per_downloader_sems[downloader_id]

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
        """
        effective_timeout = timeout if timeout is not None else settings.DOWNLOADER_API_TIMEOUT_SECONDS
        method_name = operation or getattr(func, "__name__", "unknown")
        sem = await self._get_semaphore(downloader_id)
        executor = self._executors[lane]
        loop = asyncio.get_event_loop()
        call_kwargs = kwargs or {}

        log_extra = LaneLogExtra(
            lane=lane.value,
            method=method_name,
            downloader_id=downloader_id,
            timeout=effective_timeout,
        )

        started = time.monotonic()
        # per-downloader semaphore 限制同下载器跨 lane 总并发；
        # executor 限制单 lane 总线程占用。
        async with sem:
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(executor, lambda: func(*args, **call_kwargs)),
                    timeout=effective_timeout,
                )
                log_extra.duration = time.monotonic() - started
                _log_call(log_extra, success=True)
                return result
            except asyncio.TimeoutError:
                log_extra.duration = time.monotonic() - started
                log_extra.error_type = "TimeoutError"
                _log_call(log_extra, success=False)
                raise
            except Exception as e:
                log_extra.duration = time.monotonic() - started
                log_extra.error_type = type(e).__name__
                _log_call(log_extra, success=False)
                raise

    def shutdown(self) -> None:
        """关闭所有 lane executor（应用停机时调用）。"""
        for lane, executor in self._executors.items():
            executor.shutdown(wait=False, cancel_futures=True)
            logger.info("downloader_api_runtime lane=%s executor shutdown", lane.value)


def _log_call(extra: LaneLogExtra, *, success: bool) -> None:
    """输出 lane 调用结构化日志（阶段 0 基线观测 + 阶段 2 lane 探针）。"""
    extra_dict = extra.to_dict()
    if success:
        logger.info(
            "downloader_api_call lane=%s method=%s downloader=%s duration=%.3fs",
            extra.lane,
            extra.method,
            extra.downloader_id,
            extra.duration,
            extra=extra_dict,
        )
    else:
        logger.warning(
            "downloader_api_call_failed lane=%s method=%s downloader=%s duration=%.3s error=%s",
            extra.lane,
            extra.method,
            extra.downloader_id,
            extra.duration,
            extra.error_type,
            extra=extra_dict,
        )


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
