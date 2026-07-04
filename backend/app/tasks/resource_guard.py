# -*- coding: utf-8 -*-
"""
同步任务资源准入控制器（TaskAdmissionController）

解决后台重型任务并发抢占 DB 写入、下载器 API 与线程池资源导致请求侧超时的问题。

核心机制：
1. heavy_sync 全局信号量限制同时运行的重型任务数量（默认 1）。
2. 按 task_code 维护运行/排队登记表，同类重型任务已运行或排队满即跳过本轮
   （skip_reason=duplicate_heavy_task_pending），避免 cron 堆积。
3. 不同 task_code 的重型任务通过 heavy_sync 互斥，等待超时则跳过（skip_reason=wait_timeout）。
4. 结构化日志输出准入结果，便于阶段 0 基线观测。

接入点：app/tasks/cron_executor.py::_run_python_internal_class
详见 PLANS/sync-resource-governance.md 阶段 0+1。
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator, DefaultDict, Optional, Set

from app.core.config import settings
from app.tasks.task_profiles import TaskProfile

logger = logging.getLogger(__name__)


# 跳过原因常量（日志/断言稳定锚点）
SKIP_DUPLICATE = "duplicate_heavy_task_pending"
SKIP_WAIT_TIMEOUT = "wait_timeout"


@dataclass
class AdmissionResult:
    """准入决策结果。

    Attributes:
        admitted: 是否获得 heavy_sync 令牌并允许执行。
        skip_reason: admitted=False 时的跳过原因（SKIP_* 常量）；admitted=True 时为 None。
        wait_seconds: 从 acquire 调用到获得/放弃令牌的实际耗时（秒）。
        running_count: 决策时刻同类 task_code 已在运行的实例数。
        queued_count: 决策时刻同类 task_code 已在排队等待的实例数。
        task_code: 触发本次准入的 task_code（日志溯源用）。
    """

    admitted: bool
    skip_reason: Optional[str] = None
    wait_seconds: float = 0.0
    running_count: int = 0
    queued_count: int = 0
    task_code: str = ""


@dataclass
class _ResourceState:
    """TaskAdmissionController 的可重置内部状态。

    抽出来便于测试通过 reset_state() 重建干净状态，避免进程级单例在测试间泄漏。
    """

    heavy_sync: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(0))
    db_writer: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(0))
    running: Set[str] = field(default_factory=set)
    queued: DefaultDict[str, int] = field(default_factory=lambda: DefaultDict(int))
    registry_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TaskAdmissionController:
    """进程级任务资源准入控制器（模块级单例 admission_controller）。"""

    def __init__(self) -> None:
        self._state: _ResourceState = _build_initial_state()
        # db_writer 并发固定 1（本步只建骨架，暴露接口供阶段 2 改造同步函数 commit 点用）
        # 不读配置：写锁竞争治理目标是单写者串行化，参数化会破坏语义。
        self._db_writer_concurrency: int = 1

    def reset_state(self) -> None:
        """重建内部状态（信号量、登记表）。

        用途：
        - 单测间隔离（避免进程级单例状态泄漏）。
        - 不在生产路径调用：正在运行的任务会丢失登记。
        """
        self._state = _build_initial_state()

    @property
    def running(self) -> Set[str]:
        """当前持有 heavy_sync 令牌的 task_code 集合（只读视图，测试断言用）。"""
        return set(self._state.running)

    def queued_count(self, task_code: str) -> int:
        """指定 task_code 当前排队等待的实例数（测试断言用）。"""
        return self._state.queued.get(task_code, 0)

    async def acquire(self, task_code: str, profile: TaskProfile) -> AdmissionResult:
        """请求准入一个重型任务。

        决策顺序：
        1. 同类去重：task_code 已运行或排队满 → 立即跳过（不阻塞）。
        2. 排队登记 + 等待 heavy_sync 令牌；超时 → 跳过。
        3. 获得令牌后转入 running 登记。

        Args:
            task_code: 触发准入的任务编码（仅用于日志/登记，profile 内已含策略）。
            profile: 任务资源 profile（来自 task_profiles.get_profile）。

        Returns:
            AdmissionResult：调用方据 admitted 决定是否执行任务体。
        """
        started = time.monotonic()
        state = self._state

        # === 同类去重检查（不阻塞，立即决策） ===
        async with state.registry_lock:
            if task_code in state.running:
                result = AdmissionResult(
                    admitted=False,
                    skip_reason=SKIP_DUPLICATE,
                    wait_seconds=time.monotonic() - started,
                    running_count=1,
                    queued_count=state.queued[task_code],
                    task_code=task_code,
                )
                _log_admission(result, profile)
                return result
            if state.queued[task_code] >= profile.queue_limit:
                result = AdmissionResult(
                    admitted=False,
                    skip_reason=SKIP_DUPLICATE,
                    wait_seconds=time.monotonic() - started,
                    running_count=0,
                    queued_count=state.queued[task_code],
                    task_code=task_code,
                )
                _log_admission(result, profile)
                return result
            # 占据一个排队名额
            state.queued[task_code] += 1

        # === 等待全局 heavy_sync 令牌 ===
        try:
            await asyncio.wait_for(
                state.heavy_sync.acquire(),
                timeout=profile.wait_timeout,
            )
        except asyncio.TimeoutError:
            # 超时：归还排队名额，跳过本轮
            async with state.registry_lock:
                state.queued[task_code] = max(0, state.queued[task_code] - 1)
            result = AdmissionResult(
                admitted=False,
                skip_reason=SKIP_WAIT_TIMEOUT,
                wait_seconds=time.monotonic() - started,
                running_count=len(state.running),
                queued_count=state.queued[task_code],
                task_code=task_code,
            )
            _log_admission(result, profile)
            return result
        except Exception:
            # 未知异常：归还排队名额并向上抛（避免泄漏 semaphore 名额由调用方负责）
            async with state.registry_lock:
                state.queued[task_code] = max(0, state.queued[task_code] - 1)
            raise

        # === 获得令牌：转入 running，归还排队名额 ===
        async with state.registry_lock:
            state.queued[task_code] = max(0, state.queued[task_code] - 1)
            state.running.add(task_code)
            running_count = len(state.running)

        result = AdmissionResult(
            admitted=True,
            skip_reason=None,
            wait_seconds=time.monotonic() - started,
            running_count=running_count,
            queued_count=state.queued[task_code],
            task_code=task_code,
        )
        _log_admission(result, profile)
        return result

    def release(self, task_code: str) -> None:
        """归还 heavy_sync 令牌并从 running 移除。

        幂等：重复 release 同一 task_code 不会多归还令牌（防误调导致 semaphore 计数溢出）。

        ⚠️ 本方法必须保持同步、体内禁止 await。release 与 acquire 的 registry_lock 临界区
        靠"release 整体不可被打断"维持互斥；若引入 await（如日志 flush/metrics 上报），
        会切断"check running → discard → semaphore.release()"三步序列的原子性。
        """
        state = self._state
        # 同步操作：登记表读写已在 acquire 的 registry_lock 外，release 只做集合移除与信号量释放，
        # 不引入新的并发竞争（running 是 set，discard 幂等；Semaphore.release 是原子操作）。
        # 关键约束：本方法体内不得出现 await（见 docstring）。
        if task_code in state.running:
            state.running.discard(task_code)
            state.heavy_sync.release()
            logger.debug(
                "task_admission_release task_code=%s running_after=%d",
                task_code,
                len(state.running),
            )
        else:
            # 未在 running：可能是 acquire 失败后误调，忽略但不归还令牌（防溢出）
            logger.debug(
                "task_admission_release no-op (task_code=%s not in running)",
                task_code,
            )

    @asynccontextmanager
    async def task_scope(self, task_code: str, profile: TaskProfile) -> AsyncIterator[AdmissionResult]:
        """任务作用域：acquire → yield AdmissionResult → release。

        用法：
            result = await admission_controller.acquire(code, profile)
            if not result.admitted:
                return skipped
            try:
                ...任务体...
            finally:
                admission_controller.release(code)

        等价的 contextmanager 形式：
            async with admission_controller.task_scope(code, profile) as result:
                if not result.admitted:
                    return skipped
                ...任务体...
        """
        result = await self.acquire(task_code, profile)
        try:
            yield result
        finally:
            if result.admitted:
                self.release(task_code)

    @asynccontextmanager
    async def db_write_scope(self) -> AsyncIterator[None]:
        """DB 写入临界区（阶段 2 改造同步函数 commit 点时使用）。

        本步只建骨架：暴露并发 1 的 db_writer 信号量，供后续批量 upsert/commit 包裹。
        当前生产路径不强制接入，避免阶段 1 范围爆炸。
        """
        async with self._state.db_writer:
            yield


def _build_initial_state() -> _ResourceState:
    """根据当前 settings 重建信号量与登记表。"""
    return _ResourceState(
        heavy_sync=asyncio.Semaphore(settings.SYNC_HEAVY_CONCURRENCY),
        db_writer=asyncio.Semaphore(1),
    )


def _build_log_extra(result: AdmissionResult, profile: TaskProfile) -> dict:
    """从 AdmissionResult + TaskProfile 组装结构化日志的 extra dict。

    抽成纯函数便于单测：直接断言 dict 的 key/value，不依赖 logging 路由/级别，
    能抓到 extra 组装 bug（如字段误删、拼错、类型错误），是阶段 0 基线观测的契约锚点。
    """
    return {
        "task_code": result.task_code,
        "admitted": result.admitted,
        "skip_reason": result.skip_reason,
        "wait_seconds": round(result.wait_seconds, 3),
        "running_count": result.running_count,
        "queued_count": result.queued_count,
        "queue_limit": profile.queue_limit,
    }


def _log_admission(result: AdmissionResult, profile: TaskProfile) -> None:
    """输出结构化准入日志（阶段 0 基线观测的核心探针）。

    日志字段固定，便于 ELK/grep 还原"哪个任务持有了什么资源、其它任务等待了多久"。
    extra 由 _build_log_extra 组装（单测直接覆盖该纯函数）。
    """
    extra = _build_log_extra(result, profile)
    if result.admitted:
        logger.info(
            "task_admission admitted task_code=%s wait=%.3fs running=%d queued=%d",
            result.task_code,
            result.wait_seconds,
            result.running_count,
            result.queued_count,
            extra=extra,
        )
    else:
        logger.warning(
            "task_admission skipped task_code=%s reason=%s wait=%.3fs running=%d queued=%d",
            result.task_code,
            result.skip_reason,
            result.wait_seconds,
            result.running_count,
            result.queued_count,
            extra=extra,
        )


# 进程级单例：cron_executor / 测试均从此处取，避免多实例导致信号量分裂
admission_controller = TaskAdmissionController()
