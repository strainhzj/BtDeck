# -*- coding: utf-8 -*-
"""
同步观测工具模块（W4-1：结构化观测基础设施 + run_id 贯穿 + 阈值告警）

提供：
1. 稳定事件名常量 + EVENT_FIELDS（事件 → 字段白名单字典），日志不依赖自由文本解析。
2. log_event / format_event_line：白名单过滤 → key=value 格式化（event=xxx k1=v1
   k2=v2，与仓库既有 key=value 日志风格一致）→ 敏感字段脱敏后输出；当前上下文
   持有 run_id 时自动附加 run_id 字段（contextvars 贯穿）。
3. 脱敏 sanitize_fields / sanitize_value：
   - password/passkey/cookie/authorization/token 等 key 的值整体遮蔽为 ***；
   - URL 类值（含 ://，或 announce/tracker/url key 的值）保留 scheme+host(+path)、
     去掉 query/fragment（passkey 常在 query 中），并剥离 userinfo 中的密码；
   - hash 类 key 保留前 8 位；
   - 纯 IP 值复用 app/utils/log_sanitizer.py 的既有实现（不重复造轮子）。
4. run_id 贯穿（W4-1 第二部分）：set_run_id/current_run_id/clear_run_id 基于
   contextvars.ContextVar（默认 None）；run_sync 在运行开始 set、finally clear，
   log_event 在有值上下文自动附加 run_id（显式传入的 run_id 优先）。
5. 事件循环 lag 采样器 EventLoopLagSampler / start_lag_sampler：loop.call_at
   漂移法测量，滑动窗口暴露 p95()/p99()/max_ms()；记录样本处做阈值告警
   （单次 >500ms / 窗口 P99 >100ms 持续 → EVENT_LOOP_LAG WARNING）；测量/记录
   异常吞掉继续下一轮；stop() 干净取消（无 asyncio task 泄漏）；
   SYNC_LAG_SAMPLER_ENABLED=False 时 start 返回空句柄 no-op。
6. WAL 只读快照 snapshot_wal_stats：wal 文件字节数 + busy/checkpoint 预留字段，
   只读、绝不执行 TRUNCATE checkpoint。
7. 告警阈值常量（初始值来自计划 W4-1 第 5 节；两周基线后校准，调整须留变更记录）。

各业务模块（sync_coordinator / sync_db_write / downloader_api_runtime /
tracker_status_sync / lifecycle）调用 log_event 的接入点属 W4-1 第二部分接线，
在各模块内实现。
"""

import asyncio
import logging
import math
import os
import sqlite3
import sys
import threading
import time
import uuid
from collections import deque
from contextvars import ContextVar
from typing import Any, Callable, Deque, Dict, Optional
from urllib.parse import urlsplit

from app.core.config import settings
from app.utils.log_sanitizer import IP_PATTERN, sanitize_ip

logger = logging.getLogger(__name__)

# 进程级身份：用于区分真实仍在运行的任务与进程重启后遗留的状态/日志。
# 只生成一次，不写数据库；所有结构化观测事件自动携带这两个字段。
WORKER_PID = os.getpid()
WORKER_INSTANCE_ID = f"{WORKER_PID}-{uuid.uuid4().hex[:12]}"

# ==================== 稳定事件名 ====================

# 同步运行开始（SyncCoordinator 生成 run_id 后发射）
EVENT_SYNC_RUN_START = "sync_run_start"
# 后台资源准入结果（准入/拒绝）
EVENT_ADMISSION = "sync_admission"
# 分批提交完成（每批独立 commit）
EVENT_BATCH_COMMIT = "sync_batch_commit"
# 检查点读取/推进
EVENT_CHECKPOINT = "sync_checkpoint"
# 下载器 API 调用（lane 排队/远程耗时）
EVENT_DOWNLOADER_CALL = "downloader_call"
# Tracker 关键词状态同步完成（W4-1 第二部分新增：独立于 checkpoint 游标语义）
EVENT_TRACKER_STATUS = "sync_tracker_status_done"
# 事件循环 lag 样本（采样器周期性发射）
EVENT_LOOP_LAG = "event_loop_lag"
# WAL 只读快照
EVENT_WAL_SNAPSHOT = "wal_snapshot"
# Python 内部类任务生命周期（start/heartbeat/timeout_warning/end）
EVENT_TASK_LIFECYCLE = "task_lifecycle"
# heavy_sync 等资源生命周期（wait/admitted/timeout/release）
EVENT_RESOURCE_LIFECYCLE = "resource_lifecycle"
# 同步阶段切换（用于还原卡在哪个阶段）
EVENT_SYNC_PHASE = "sync_phase"
# 同步异常边界（记录异常类型、阶段以及是否被转换为结果后继续执行）
EVENT_SYNC_ERROR = "sync_error"
# 进程内存采样（OOM 治理 2026-09-05：周期采样 RSS，为内存峰值提供证据链）
EVENT_PROCESS_MEMORY = "process_memory"

# ==================== 字段白名单 ====================

# 公共字段：所有事件都允许携带（W4-1 最小字段集「关联」+「阶段」+ 通用指标/告警）
COMMON_FIELDS = frozenset(
    {
        "run_id",
        "task_id",
        "sync_type",
        "trigger",
        "downloader_id",
        "downloader_count",
        "task_code",
        "task_name",
        "cron_run_id",
        "sync_run_id",
        "resource",
        "phase",
        "phase_ms",
        "outcome",
        "skip_reason",
        "admission_wait_ms",
        "threshold_ms",  # 告警阈值类事件通用（looped 阈值对比基准）
        "state",
        "pid",
        "worker_instance_id",
        "elapsed_ms",
        "timeout_seconds",
        "timeout_exceeded",
        "execution_mode",
        "error_type",
        "last_progress_ms",
        "resource_held_ms",
    }
)

# 事件 → 事件专属字段白名单（与 COMMON_FIELDS 合并后生效）
EVENT_FIELDS: Dict[str, frozenset] = {
    EVENT_SYNC_RUN_START: frozenset(),
    EVENT_ADMISSION: frozenset({"queue_pos"}),
    EVENT_BATCH_COMMIT: frozenset(
        {"batch_index", "batch_rows", "changed_rows", "commit_ms", "lock_wait_ms", "retry_count"}
    ),
    EVENT_CHECKPOINT: frozenset({"position", "state", "cursor"}),
    EVENT_DOWNLOADER_CALL: frozenset(
        {"lane", "method", "operation", "queue_wait_ms", "remote_call_ms", "remote_timeout", "error_type"}
    ),
    EVENT_TRACKER_STATUS: frozenset({"scanned", "changed", "unchanged", "batches", "duration_ms"}),
    EVENT_LOOP_LAG: frozenset({"lag_ms", "p95_ms", "p99_ms", "max_ms", "window_size"}),
    EVENT_WAL_SNAPSHOT: frozenset({"wal_bytes", "wal_growth_bytes", "busy_count", "checkpoint_busy"}),
    # 2026-08-25：任务心跳进度停滞标记（SYNC_TASK_PROGRESS_STALL_WARNING_SECONDS
    # 阈值触发，白名单外字段会被 format_event_line 静默丢弃故必须登记）
    EVENT_TASK_LIFECYCLE: frozenset({"progress_stalled"}),
    EVENT_RESOURCE_LIFECYCLE: frozenset(
        {
            "resource_state",
            "wait_ms",
            "queue_count",
            "running_count",
            "queue_limit",
            "blocked_by_task_code",
            "blocked_by_task_id",
            "blocked_by_cron_run_id",
            "blocked_by_sync_run_id",
            "blocked_by_phase",
            "blocked_by_age_ms",
            "blocked_by_started_at",
            "blocked_by_pid",
            "blocked_by_worker_instance_id",
            "holder_task_code",
            "holder_task_id",
            "holder_cron_run_id",
            "holder_sync_run_id",
            "holder_phase",
            "holder_age_ms",
            "holder_started_at",
            "holder_pid",
            "holder_worker_instance_id",
        }
    ),
    EVENT_SYNC_PHASE: frozenset({"previous_phase", "previous_phase_ms"}),
    EVENT_SYNC_ERROR: frozenset({"stage", "operation", "suppressed", "continue_after_error"}),
    # OOM 治理（2026-09-05）：进程 RSS 采样。rss_mb 只登记在本事件专属白名单，
    # 绝不进 COMMON_FIELDS / EVENT_LOOP_LAG（test_non_whitelist_fields_dropped
    # 以 rss_mb 作"非白名单字段应被丢弃"的反例样例）。heap_trimmed 为采样后
    # 分配器归还动作的结果（SYNC_PROCESS_MEMORY_TRIM_ENABLED 门控）。
    EVENT_PROCESS_MEMORY: frozenset({"rss_mb", "sample_interval_seconds", "heap_trimmed"}),
}


def _allowed_fields(event_name: str) -> frozenset:
    """事件允许输出的字段集合（公共字段 ∪ 事件专属白名单）。"""
    return COMMON_FIELDS | EVENT_FIELDS.get(event_name, frozenset())


# ==================== 敏感字段脱敏 ====================

# 敏感 key 标记（大小写不敏感子串匹配）：命中则整值遮蔽
_SENSITIVE_KEY_MARKERS = ("password", "passkey", "cookie", "authorization", "token", "secret")
# hash 类 key 标记：命中则保留前 8 位
_HASH_KEY_MARKERS = ("hash",)
# URL 类 key 标记：值缺少 :// 时仍按 URL 处理（如省略 scheme 的 announce 地址）
_URL_KEY_MARKERS = ("announce", "tracker", "url")


def sanitize_value(key: str, value: Any) -> Any:
    """按 key 特征与值形态脱敏单个字段值。

    规则（顺序敏感）：
    1. 敏感 key（password/passkey/cookie/authorization/token/secret）→ 整体 ***；
    2. URL 形态值（含 ://，或 announce/tracker/url key 的值）→ 保留 scheme+host(+path)，
       去掉 query/fragment 并剥离 userinfo（passkey 常在 query 中）；
    3. hash 类 key → 保留前 8 位；
    4. 纯 IP 值 → 复用 log_sanitizer.sanitize_ip。
    其余原样返回。
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    value_str = str(value)
    key_lower = str(key).lower()
    if any(marker in key_lower for marker in _SENSITIVE_KEY_MARKERS):
        return "***"
    if "://" in value_str or any(marker in key_lower for marker in _URL_KEY_MARKERS):
        return _mask_url(value_str)
    if any(marker in key_lower for marker in _HASH_KEY_MARKERS):
        return _mask_hash(value_str)
    if IP_PATTERN.fullmatch(value_str.strip()):
        return sanitize_ip(value_str)
    return value_str


def _mask_url(url: str) -> str:
    """URL 脱敏：保留 scheme://host(+path)，去掉 query/fragment 与 userinfo。

    解析失败时兜底：截取首个 ? 或 # 之前的部分（passkey 在 query 中）。
    """
    try:
        parts = urlsplit(url)
        if parts.scheme and parts.netloc:
            netloc = parts.netloc
            if "@" in netloc:
                # 剥离 userinfo（user:password@host 中的密码）
                netloc = netloc.rsplit("@", 1)[1]
            masked = f"{parts.scheme}://{netloc}"
            if parts.path:
                masked += parts.path
            return masked
    except ValueError:
        pass
    for sep in ("?", "#"):
        index = url.find(sep)
        if index >= 0:
            return url[:index]
    return url


def _mask_hash(value: str) -> str:
    """hash 类值保留前 8 位，其余遮蔽（8 位熵不足以反推完整 hash）。"""
    if len(value) <= 8:
        return value
    return f"{value[:8]}***"


def sanitize_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    """对字段字典逐 key 脱敏（key 名大小写不敏感）。"""
    return {key: sanitize_value(key, value) for key, value in fields.items()}


# ==================== run_id 贯穿（contextvars，W4-1 第二部分） ====================


# 当前同步运行 run_id（ContextVar，默认 None）。
# 由 run_sync 在运行开始 set、finally clear；log_event 自动附加该字段，
# 使同一 run_id 可还原完整阶段顺序（触发 → 准入 → batch commit → checkpoint）。
# ContextVar 语义：子协程/子任务继承父任务上下文（拷贝），互不串扰。
_run_id_var: ContextVar[Optional[str]] = ContextVar("sync_observability_run_id", default=None)


def set_run_id(run_id: str) -> None:
    """设置当前上下文的 run_id（run_sync 运行开始调用）。"""
    _run_id_var.set(run_id)


def current_run_id() -> Optional[str]:
    """读取当前上下文的 run_id；无活动运行返回 None。"""
    return _run_id_var.get()


def clear_run_id() -> None:
    """清空当前上下文的 run_id（run_sync 结束 finally 调用）。"""
    _run_id_var.set(None)


# ==================== 事件输出 ====================


def format_event_line(event_name: str, **fields: Any) -> str:
    """构造结构化事件行（白名单过滤 + 脱敏）：event=xxx k1=v1 k2=v2。"""
    if event_name not in EVENT_FIELDS:
        # 未知事件名：仅输出公共字段，留 debug 线索便于发现拼写错误
        logger.debug("sync_observability unknown event=%s（仅输出公共字段）", event_name)
    filtered = {key: val for key, val in fields.items() if key in _allowed_fields(event_name)}
    sanitized = sanitize_fields(filtered)
    parts = [f"event={event_name}"]
    parts.extend(f"{key}={val}" for key, val in sorted(sanitized.items()))
    return " ".join(parts)


def log_event(event_name: str, level: int = logging.INFO, **fields: Any) -> None:
    """按事件白名单输出结构化 key=value 事件日志（先过滤、再脱敏）。

    Args:
        event_name: EVENT_* 常量（未知事件名只输出公共字段）。
        level: 日志级别（默认 INFO；告警类事件可传 logging.WARNING）。
        **fields: 事件字段（白名单外字段静默丢弃，不落盘）。

    当前上下文持有 run_id（set_run_id 后）时自动附加 run_id 字段；
    调用方显式传入 run_id 时以显式值优先。
    """
    fields = dict(fields)
    fields.setdefault("pid", WORKER_PID)
    fields.setdefault("worker_instance_id", WORKER_INSTANCE_ID)
    context_run_id = _run_id_var.get()
    if context_run_id is not None and "run_id" not in fields:
        fields = dict(fields, run_id=context_run_id)
    logger.log(level, format_event_line(event_name, **fields))


# ==================== 告警阈值（W4-1 第 5 节初始值） ====================

# 初始值来自 PLANS/sync-database-blocking-remediation.md W4-1「观测和告警初始阈值」。
# 两周基线数据后校准；任何调整必须留变更记录（阈值注释/本模块 git 历史）。
# 注意：计划中"critical event"在日志级观测中统一以 WARNING 级别发射
# （不引入分级告警通道，避免误报噪音；严重度判定留给指标层）。

# 单次事件循环 lag 超过该值（ms）→ EVENT_LOOP_LAG WARNING（计划：单次 >500ms）
LOOP_LAG_WARN_SINGLE_MS: float = 500.0
# 窗口 P99 lag 超过该值（ms）→ EVENT_LOOP_LAG WARNING（计划：P99>100ms 持续 5 分钟；
# 300 样本滑动窗口 @1s 间隔 ≈ 5 分钟窗口，全窗口维持即近似"持续"）
LOOP_LAG_WARN_P99_MS: float = 100.0
# P99 告警最小样本数：样本不足不告警（避免冷启动/少量抖动误报）
LOOP_LAG_WARN_MIN_SAMPLES: int = 30
# P99 告警最小发射间隔（秒）：窗口持续超阈值时最多每间隔告警一次（防刷屏）
LOOP_LAG_P99_WARN_MIN_INTERVAL_SECONDS: float = 300.0
# 单批 DB commit 超过该值（ms）→ EVENT_BATCH_COMMIT WARNING（W0 告警候选 + 计划第 5 节）
BATCH_COMMIT_WARN_MS: float = 500.0


# ==================== 事件循环 lag 采样器 ====================


class EventLoopLagSampler:
    """事件循环 lag 采样器（loop.call_at 漂移法）。

    每 interval 通过 loop.call_at 调度一次 tick 回调；tick 实际触发时刻与计划
    时刻的偏差即事件循环被阻塞的时长（lag，ms）。滑动窗口保留最近 window_size
    个样本，暴露 p95()/p99()/max_ms()。

    特性：
    - 异常恢复：tick 内测量/记录异常一律吞掉，下一轮照常调度（观测器不允许
      因自身故障破坏被观测系统）。
    - 干净停止：stop() 取消待触发 handle 并置停止标志；正在执行的 tick 结束后
      不再调度下一轮。采样只注册 loop callback，不创建 asyncio.Task，无任务泄漏。
    - 线程安全：样本队列受 _lock 保护（tick 在 loop 线程写，外部可任意线程读）。
    """

    def __init__(
        self,
        interval_seconds: Optional[float] = None,
        window_size: int = 300,
        measure: Optional[Callable[[], Optional[float]]] = None,
    ) -> None:
        interval = interval_seconds if interval_seconds is not None else settings.SYNC_LAG_SAMPLER_INTERVAL_SECONDS
        # 下限 10ms 防抖：0/负值配置视为最小间隔，避免 busy loop
        self._interval = max(float(interval), 0.01)
        self._window_size = max(int(window_size), 1)
        # 可注入测量回调（测试/扩展用）；None 时用默认 loop.time() 漂移测量
        self._measure = measure
        self._samples: Deque[float] = deque(maxlen=self._window_size)
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._handle: Optional[asyncio.Handle] = None
        self._next_tick = 0.0
        self._stopped = True
        # P99 告警发射抑制时间戳（W4-1 第二部分：窗口持续超阈值时防刷屏）
        self._last_p99_warn_ts = 0.0

    # ---- 生命周期 ----

    def start(self) -> None:
        """在运行中的事件循环内启动采样（须在 loop 线程中调用）。"""
        if not self._stopped:
            return
        self._loop = asyncio.get_running_loop()
        self._stopped = False
        self._next_tick = self._loop.time() + self._interval
        self._handle = self._loop.call_at(self._next_tick, self._tick)

    def stop(self) -> None:
        """停止采样：取消待触发 tick；执行中的 tick 结束后不再调度下一轮。"""
        self._stopped = True
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None

    # ---- 采样 ----

    def _tick(self) -> None:
        """单次采样回调：测量 → 记录 → 调度下一轮（无论成败）。"""
        try:
            try:
                sample = self._measure_sample()
            except Exception:  # noqa: BLE001 - 测量异常：跳过本轮，恢复继续
                sample = None
            if sample is not None:
                try:
                    self._record_sample(sample)
                except Exception:  # noqa: BLE001 - 记录异常：跳过本轮，恢复继续
                    pass
        finally:
            if not self._stopped:
                loop = self._loop
                if loop is not None:
                    self._next_tick += self._interval
                    self._handle = loop.call_at(self._next_tick, self._tick)

    def _measure_sample(self) -> Optional[float]:
        """测量一次 lag（ms）。注入 measure 时以其返回值为准（None 表示跳过本轮）。"""
        if self._measure is not None:
            return self._measure()
        loop = self._loop
        assert loop is not None  # start() 后才开始采样
        return max(0.0, (loop.time() - self._next_tick) * 1000.0)

    def _record_sample(self, lag_ms: float) -> None:
        """记录一个样本（内部：tick 调用）并做阈值告警判定（W4-1 第二部分）。

        告警规则（日志级，不阻断采样）：
        - 单次 lag > LOOP_LAG_WARN_SINGLE_MS → EVENT_LOOP_LAG WARNING（每次触发发射）。
        - 窗口 P99 > LOOP_LAG_WARN_P99_MS 且样本数 >= LOOP_LAG_WARN_MIN_SAMPLES →
          WARNING（抑制：每 LOOP_LAG_P99_WARN_MIN_INTERVAL_SECONDS 至多一次）。
        告警发射异常一律吞掉（观测器不允许因自身故障破坏采样）。
        """
        with self._lock:
            self._samples.append(float(lag_ms))
            count = len(self._samples)
            p95 = self._percentile_locked(0.95)
            p99 = self._percentile_locked(0.99)
            max_ms = max(self._samples)
            emit_p99_warn = (
                count >= LOOP_LAG_WARN_MIN_SAMPLES
                and p99 > LOOP_LAG_WARN_P99_MS
                and time.monotonic() - self._last_p99_warn_ts >= LOOP_LAG_P99_WARN_MIN_INTERVAL_SECONDS
            )
            if emit_p99_warn:
                self._last_p99_warn_ts = time.monotonic()
        try:
            if lag_ms > LOOP_LAG_WARN_SINGLE_MS:
                # 单次超阈值：属事件（每次发射），不带 P99 抑制语义
                log_event(
                    EVENT_LOOP_LAG,
                    level=logging.WARNING,
                    lag_ms=round(lag_ms, 1),
                    p95_ms=round(p95, 1),
                    p99_ms=round(p99, 1),
                    max_ms=round(max_ms, 1),
                    window_size=count,
                    threshold_ms=LOOP_LAG_WARN_SINGLE_MS,
                )
            elif emit_p99_warn:
                log_event(
                    EVENT_LOOP_LAG,
                    level=logging.WARNING,
                    lag_ms=round(lag_ms, 1),
                    p95_ms=round(p95, 1),
                    p99_ms=round(p99, 1),
                    max_ms=round(max_ms, 1),
                    window_size=count,
                    threshold_ms=LOOP_LAG_WARN_P99_MS,
                )
        except Exception:  # noqa: BLE001 - 告警发射失败绝不影响采样
            logger.debug("sync_observability lag warning emit failed", exc_info=True)

    def record_sample(self, lag_ms: float) -> None:
        """手动注入一个样本（测试与外部探针用）；与 tick 样本一样走阈值告警判定。"""
        self._record_sample(lag_ms)

    def sample_count(self) -> int:
        """当前窗口内样本数。"""
        with self._lock:
            return len(self._samples)

    # ---- 分位统计 ----

    def p95(self) -> float:
        """窗口内 P95 lag（ms）；无样本返回 0。"""
        return self._percentile(0.95)

    def p99(self) -> float:
        """窗口内 P99 lag（ms）；无样本返回 0。"""
        return self._percentile(0.99)

    def max_ms(self) -> float:
        """窗口内最大 lag（ms）；无样本返回 0。"""
        with self._lock:
            return max(self._samples) if self._samples else 0.0

    def _percentile(self, fraction: float) -> float:
        """nearest-rank 分位：窗口排序后取 ceil(fraction*n)-1 位（无样本返回 0）。"""
        with self._lock:
            return self._percentile_locked(fraction)

    def _percentile_locked(self, fraction: float) -> float:
        """nearest-rank 分位（调用方必须持有 _lock）。"""
        count = len(self._samples)
        if count == 0:
            return 0.0
        index = min(max(int(math.ceil(fraction * count)) - 1, 0), count - 1)
        return sorted(self._samples)[index]


class LagSamplerHandle:
    """lag 采样器句柄（start_lag_sampler 的返回值）。

    SYNC_LAG_SAMPLER_ENABLED=False 时为空句柄（enabled=False，所有操作 no-op）。
    """

    def __init__(self, sampler: Optional[EventLoopLagSampler] = None) -> None:
        self._sampler = sampler

    @property
    def sampler(self) -> Optional[EventLoopLagSampler]:
        """底层采样器（未启用时为 None）。"""
        return self._sampler

    @property
    def enabled(self) -> bool:
        """是否实际启动了采样。"""
        return self._sampler is not None

    def stop(self) -> None:
        """停止采样（空句柄 no-op）。"""
        if self._sampler is not None:
            self._sampler.stop()


def start_lag_sampler(interval_seconds: Optional[float] = None, window_size: int = 300) -> LagSamplerHandle:
    """启动事件循环 lag 采样器（须在运行中的事件循环内调用）。

    Args:
        interval_seconds: 采样间隔（秒）；None 取 SYNC_LAG_SAMPLER_INTERVAL_SECONDS。
        window_size: 滑动窗口样本数上限（默认 300）。

    Returns:
        LagSamplerHandle：SYNC_LAG_SAMPLER_ENABLED=False 时返回空句柄 no-op。
    """
    if not settings.SYNC_LAG_SAMPLER_ENABLED:
        return LagSamplerHandle()
    sampler = EventLoopLagSampler(interval_seconds=interval_seconds, window_size=window_size)
    sampler.start()
    return LagSamplerHandle(sampler=sampler)


# ==================== WAL 只读快照 ====================


def snapshot_wal_stats(db_path: str) -> Dict[str, Any]:
    """只读 WAL 快照（绝不执行 TRUNCATE checkpoint）。

    ``busy_count`` 来自 SQLite ``wal_checkpoint(PASSIVE)`` 的 ``busy`` 列；
    ``checkpoint_busy`` 表示本次非阻塞探测是否观察到写入者。探测使用
    ``timeout=0`` 且不会等待、打断写事务或截断 WAL，避免观测本身制造延迟。
    数据库不存在或探测失败时，这两个字段保持 ``None``。
    """
    wal_bytes = 0
    try:
        wal_bytes = os.path.getsize(db_path + "-wal")
    except OSError:
        wal_bytes = 0

    busy_count: Optional[int] = None
    checkpoint_busy: Optional[bool] = None
    if os.path.exists(db_path):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(db_path, timeout=0, check_same_thread=False)
            conn.isolation_level = None
            conn.execute("PRAGMA busy_timeout=0")
            row = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            if row:
                busy_count = int(row[0])
                checkpoint_busy = busy_count > 0
        except (OSError, sqlite3.Error) as exc:
            logger.debug("WAL PASSIVE checkpoint probe failed for %s: %s", db_path, exc)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

    return {
        "wal_bytes": wal_bytes,
        "busy_count": busy_count,
        "checkpoint_busy": checkpoint_busy,
    }


# ==================== 进程 RSS 采样（OOM 治理 2026-09-05） ====================

# 最近一次采样的 RSS（MB）；周期采样循环写，/sync 健康端点读。
# None 表示尚未采样或当前平台不可用。
_LAST_RSS_MB: Optional[float] = None


def get_process_rss_mb() -> Optional[float]:
    """采集当前进程 RSS（MB）；平台不支持/采集失败返回 None（观测不破坏主流程）。

    实现口径（刻意不引入 psutil 依赖）：
    - Linux：读 /proc/self/status 的 VmRSS 行（kB）——部署主目标（docker）路径；
    - Windows：ctypes GetProcessMemoryInfo 的 WorkingSetSize（字节）——桌面/
      PyInstaller 场景；cb 必须先赋 sizeof(结构体) 再调用（仓库 ctypes 先例
      见 desktop_companion/credentials.py）；
    - macOS：返回 None——resource.getrusage 的 ru_maxrss 是高水位（peak）而非
      当前值，且单位与 Linux 不同（字节 vs kB），语义陷阱直接规避。
    纯同步毫秒级调用，事件循环内直接调用安全。

    注意（口径声明）：desktop 模式下后端跑在 GUI 进程内线程中，本函数量到的
    是整个桌面进程（含 webview）的 RSS，数值系统性偏高——该场景数据只作
    趋势参考，不用于内存预算验收。
    """
    global _LAST_RSS_MB
    rss_bytes: Optional[int] = None
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/self/status", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        # "VmRSS:\t 123456 kB"
                        rss_kb = int(line.split()[1])
                        rss_bytes = rss_kb * 1024
                        break
        elif sys.platform.startswith("win32"):
            import ctypes

            class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_uint32),
                    ("PageFaultCount", ctypes.c_uint32),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            # getattr 取 windll：非 Windows 平台无此属性（静态检查与运行时都安全）
            windll = getattr(ctypes, "windll", None)
            if windll is None:
                return None
            kernel32 = windll.kernel32
            psapi = windll.psapi
            # GetCurrentProcess 返回 64 位伪句柄（-1）：默认 c_int restype 会截断，
            # 必须显式 c_void_p；GetProcessMemoryInfo 首参同为 HANDLE，需配 argtypes
            # 否则巨大的无符号句柄 int 触发 OverflowError。
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
                ctypes.c_uint32,
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            if psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            ):
                rss_bytes = int(counters.WorkingSetSize)
    except Exception:  # noqa: BLE001 - 观测失败静默降级，不破坏调用方
        logger.debug("get_process_rss_mb sampling failed", exc_info=True)
        return None

    if rss_bytes is None:
        return None
    rss_mb = round(rss_bytes / (1024 * 1024), 1)
    _LAST_RSS_MB = rss_mb
    return rss_mb


def get_last_rss_mb() -> Optional[float]:
    """读取最近一次采样值（不触发采集）；未采样/不可用返回 None。"""
    return _LAST_RSS_MB


def release_free_heap_memory() -> bool:
    """把分配器空闲内存归还 OS（移动端内存治理 2026-09-05；返回是否生效）。

    背景：同步任务的分批循环会产生大量短命大对象，原生分配器（glibc/scudo）
    释放后仍可能持有高水位不归还 OS——容器/移动端看到的 RSS 呈楼梯上升
    （生产实测：重启后 819MB，数小时爬到 2.2GB）。本函数在空闲时机主动触发
    归还，把楼梯变锯齿。

    平台分支（不支持/失败一律返回 False，绝不抛异常）：
    - glibc（Linux 服务器/桌面）：malloc_trim(0)——归还堆顶与空闲 chunk；
    - Android bionic/scudo：mallopt(M_PURGE)（API 31+；低版本 mallopt 对未知
      命令返回 0，等价 no-op）；
    - macOS/其它：无等价安全接口，直接 False。

    纯同步毫秒级调用（madvise 扫描空闲页），由 RSS 采样循环在采样后调用
    （默认 5 分钟一次的空闲时刻），不触碰同步热路径。
    """
    try:
        if not sys.platform.startswith("linux"):
            return False
        import ctypes

        libc = ctypes.CDLL(None, use_errno=False)
        # glibc：malloc_trim 优先（语义最直接）
        try:
            trim = libc.malloc_trim
        except AttributeError:
            trim = None
        if trim is not None:
            trim.restype = ctypes.c_int
            return bool(trim(ctypes.c_size_t(0)))
        # bionic：M_PURGE=101（scudo 主分配器释放；未知命令返回 0 不报错）
        try:
            mallopt = libc.mallopt
        except AttributeError:
            return False
        mallopt.restype = ctypes.c_int
        _M_PURGE = 101  # bionic malloc.h: M_DECAY_TIME=100, M_PURGE=101
        return bool(mallopt(ctypes.c_int(_M_PURGE), ctypes.c_int(0)))
    except Exception:  # noqa: BLE001 - 归还失败静默降级，不影响任何主流程
        logger.debug("release_free_heap_memory failed", exc_info=True)
        return False
