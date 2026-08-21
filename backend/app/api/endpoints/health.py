"""进程、应用 readiness 与同步业务健康接口（W4-2）。

设计边界：
* ``/health/live`` 只证明 FastAPI/事件循环能够处理请求，不访问数据库或下载器。
* ``/health/ready`` 只执行有超时的 ``SELECT 1``、SQLite 单 Worker 校验和 lag
  近期状态读取；绝不执行写探针，也不触发下载器远程调用。
* ``/api/v1/health/sync`` 是受认证的业务视图，读取任务 outcome/freshness、活动
  SyncCoordinator 快照、sync_checkpoints 年龄以及缓存中的下载器离线告警。
"""

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.api.responseVO import CommonResponse
from app.auth.dependencies import AuthenticatedUserInfo, require_authenticated_user
from app.core.config import settings
from app.core.startup_guard import StartupGuardError, resolve_runtime_info, validate_worker_count
from app.database import AsyncSessionLocal
from app.models import (
    OUTCOME_CANCELLED,
    OUTCOME_FAILED,
    OUTCOME_NO_ACTION,
    OUTCOME_PARTIAL,
    OUTCOME_SUCCESS,
    SyncCheckpoint,
)
from app.services.sync_coordinator import get_active_sync_runs
from app.services.sync_observability import LOOP_LAG_WARN_P99_MS
from app.tasks.cron_freshness import compute_freshness
from app.tasks.cron_models import CronTask
from app.utils.datetime_utils import serialize_utc_datetime

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])
sync_router = APIRouter(tags=["health"])

_READINESS_FAILURE_TOTAL: Counter[str] = Counter()
_SYNC_TASK_CODES: Dict[str, str] = {
    "info": "torrent_info_sync_ac608e4d",
    "tracker": "tracker_sync_598b784c",
    "full": "manual_sync_full",
}
_SYNC_TYPE_ORDER = ("info", "tracker", "full")
_SUCCESS_OUTCOMES = frozenset({OUTCOME_SUCCESS, OUTCOME_PARTIAL, OUTCOME_NO_ACTION})
_BAD_OUTCOMES = frozenset({OUTCOME_FAILED, OUTCOME_CANCELLED})


def _common_response(status_value: str, message: str, code: str, data: Any) -> Dict[str, Any]:
    """构造统一响应 envelope；health 失败响应必须显式保留 HTTP 503。"""
    return CommonResponse(status=status_value, msg=message, code=code, data=data).model_dump()


async def _probe_database() -> None:
    """执行 readiness 唯一数据库探针：只读 SELECT 1，不 commit、不写 PRAGMA。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() != 1:
            raise RuntimeError("database probe returned unexpected value")


async def _database_readiness_check() -> Tuple[Dict[str, Any], Optional[str]]:
    """以严格超时运行数据库可读性检查，返回 (check, reason_code)。"""
    timeout_seconds = max(float(settings.HEALTH_READINESS_DB_TIMEOUT_SECONDS), 0.001)
    try:
        await asyncio.wait_for(_probe_database(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return (
            {"status": "failed", "timeoutMs": round(timeout_seconds * 1000.0, 1)},
            "db_query_timeout",
        )
    except Exception:  # noqa: BLE001 - 响应只暴露稳定 reason code
        return ({"status": "failed"}, "db_unavailable")
    return ({"status": "ok"}, None)


def _worker_readiness_check() -> Tuple[Dict[str, Any], Optional[str]]:
    """复用 startup_guard 的 SQLite 单 Worker 规则，不复制判断逻辑。"""
    backend = "unknown"
    worker_count: Optional[int] = None
    scheduler_enabled: Optional[bool] = None
    try:
        backend, worker_count, scheduler_enabled = resolve_runtime_info()
        validate_worker_count(backend, worker_count, bool(scheduler_enabled))
    except (StartupGuardError, TypeError, ValueError):
        return (
            {
                "status": "failed",
                "databaseBackend": backend,
                "workerCount": worker_count,
                "schedulerEnabled": scheduler_enabled,
            },
            "worker_noncompliant",
        )
    return (
        {
            "status": "ok",
            "databaseBackend": backend,
            "workerCount": worker_count,
            "schedulerEnabled": scheduler_enabled,
        },
        None,
    )


def _lag_readiness_check(app: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """读取 lag sampler 的近期窗口；采样器未启用/尚无样本时保持 unknown。"""
    threshold = float(getattr(settings, "HEALTH_READINESS_LAG_P99_THRESHOLD_MS", LOOP_LAG_WARN_P99_MS))
    handle = getattr(getattr(app, "state", None), "sync_lag_sampler", None)
    sampler = getattr(handle, "sampler", handle)
    if sampler is None:
        return (
            {"status": "unknown", "sampleCount": 0, "p99Ms": None, "maxMs": None, "thresholdMs": threshold},
            None,
        )
    try:
        sample_count = int(sampler.sample_count())
        p99_ms = float(sampler.p99())
        max_ms = float(sampler.max_ms())
    except Exception:  # noqa: BLE001 - 观测器故障不伪造数据库故障
        return (
            {"status": "unknown", "sampleCount": 0, "p99Ms": None, "maxMs": None, "thresholdMs": threshold},
            None,
        )
    check = {
        "status": "failed" if sample_count > 0 and p99_ms > threshold else "ok",
        "sampleCount": sample_count,
        "p99Ms": round(p99_ms, 1),
        "maxMs": round(max_ms, 1),
        "thresholdMs": threshold,
    }
    return (check, "event_loop_lag" if check["status"] == "failed" else None)


def _record_readiness_failures(reason_codes: Iterable[str]) -> None:
    """记录按原因聚合的 readiness_failure_total，不写数据库。"""
    for reason_code in sorted(set(reason_codes)):
        _READINESS_FAILURE_TOTAL[reason_code] += 1
        logger.warning(
            "readiness_failure_total reason_code=%s count=%d",
            reason_code,
            _READINESS_FAILURE_TOTAL[reason_code],
        )


@router.get("/health/live", summary="进程存活检查")
async def health_live() -> CommonResponse[Dict[str, str]]:
    """只证明事件循环能处理请求；不访问数据库、下载器或其它外部依赖。"""
    return CommonResponse(status="success", msg="服务存活", code="200", data={"status": "alive"})


@router.get("/health/ready", summary="应用就绪检查")
async def health_ready(request: Request):
    """执行严格有界的只读 readiness 检查。"""
    worker_check, worker_reason = _worker_readiness_check()
    lag_check, lag_reason = _lag_readiness_check(request.app)
    database_check, database_reason = await _database_readiness_check()

    reason_codes = [reason for reason in (database_reason, worker_reason, lag_reason) if reason]
    checks = {"database": database_check, "worker": worker_check, "eventLoopLag": lag_check}
    if reason_codes:
        _record_readiness_failures(reason_codes)
        return JSONResponse(
            status_code=503,
            content=_common_response(
                "error",
                "应用未就绪",
                "503",
                {"status": "not_ready", "reasonCodes": reason_codes, "checks": checks},
            ),
        )

    return CommonResponse(
        status="success",
        msg="应用已就绪",
        code="200",
        data={"status": "ready", "checks": checks},
    )


def _as_datetime(value: Any) -> Optional[datetime]:
    return value if isinstance(value, datetime) else None


def _latest_datetime(values: Iterable[Any]) -> Optional[datetime]:
    candidates = [value for value in (_as_datetime(item) for item in values) if value is not None]
    return max(candidates, key=_datetime_order) if candidates else None


def _datetime_order(value: datetime) -> float:
    """返回可比较的 UTC 时间戳，兼容 SQLite naive 与驱动 aware datetime。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).timestamp()


def _age_seconds(value: Optional[datetime], now: datetime) -> Optional[int]:
    if value is None:
        return None
    if value.tzinfo is None and now.tzinfo is not None:
        value = value.replace(tzinfo=timezone.utc)
    elif value.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0, int((now - value).total_seconds()))


def _freshness_input(value: Optional[datetime]) -> Optional[datetime]:
    """cron_freshness 使用本地 naive datetime；统一处理带时区的测试/驱动值。"""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _checkpoint_sort_key(row: SyncCheckpoint) -> float:
    value = _latest_datetime((row.updated_at, row.last_attempt_at, row.created_at))
    return _datetime_order(value) if value is not None else float("-inf")


def _cron_sort_key(task: CronTask) -> float:
    value = _latest_datetime((task.last_attempt_at, task.last_success_at, task.update_time))
    return _datetime_order(value) if value is not None else float("-inf")


def _active_run_by_type() -> Dict[str, Dict[str, Any]]:
    active: Dict[str, Dict[str, Any]] = {}
    for run in get_active_sync_runs():
        sync_type = str(run.get("sync_type") or "unknown")
        previous = active.get(sync_type)
        current_started = _as_datetime(run.get("started_at"))
        previous_started = _as_datetime(previous.get("started_at")) if previous is not None else None
        if previous is None or (
            current_started is not None
            and (previous_started is None or _datetime_order(current_started) < _datetime_order(previous_started))
        ):
            active[sync_type] = run
    return active


def _sync_entry(
    sync_type: str,
    checkpoints: List[SyncCheckpoint],
    task: Optional[CronTask],
    active_run: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """把一个 sync_type 的 checkpoint/cron/活动快照合并成稳定 API 数据。"""
    checkpoint = max(checkpoints, key=_checkpoint_sort_key) if checkpoints else None
    checkpoint_success = _latest_datetime(row.last_success_at for row in checkpoints)
    cron_success = _as_datetime(getattr(task, "last_success_at", None)) if task is not None else None
    last_success_at = _latest_datetime((checkpoint_success, cron_success))

    checkpoint_attempt = _latest_datetime(row.last_attempt_at for row in checkpoints)
    cron_attempt = _as_datetime(getattr(task, "last_attempt_at", None)) if task is not None else None
    last_attempt_at = _latest_datetime((checkpoint_attempt, cron_attempt))

    last_outcome: Optional[str] = None
    if checkpoint is not None and checkpoint.outcome is not None:
        last_outcome = checkpoint.outcome
    if task is not None and task.last_outcome is not None:
        task_time = _cron_sort_key(task)
        checkpoint_time = _checkpoint_sort_key(checkpoint) if checkpoint is not None else float("-inf")
        if last_outcome is None or task_time >= checkpoint_time:
            last_outcome = task.last_outcome

    cron_plan = getattr(task, "cron_plan", "") if task is not None else ""
    freshness = compute_freshness(cron_plan, _freshness_input(last_success_at))
    checkpoint_updated_at = _latest_datetime((row.updated_at or row.last_attempt_at) for row in checkpoints)
    now = datetime.now(timezone.utc)

    active_payload = None
    phase = None
    if active_run is not None:
        phase = active_run.get("phase")
        active_payload = {
            "runId": active_run.get("run_id"),
            "phase": phase,
            "startedAt": serialize_utc_datetime(_as_datetime(active_run.get("started_at"))),
            "downloaderCount": active_run.get("downloader_count"),
        }

    warnings: List[str] = []
    if freshness["stale"]:
        warnings.append("data_stale")
    if last_outcome in _BAD_OUTCOMES:
        warnings.append("last_outcome_failed")

    if last_outcome in _BAD_OUTCOMES or freshness["stale"]:
        status_value = "degraded"
    elif last_outcome in _SUCCESS_OUTCOMES:
        status_value = "healthy"
    else:
        status_value = "unknown"

    return {
        "syncType": sync_type,
        "status": status_value,
        "latestOutcome": last_outcome,
        "lastSuccessfulDataAt": serialize_utc_datetime(last_success_at),
        "lastAttemptAt": serialize_utc_datetime(last_attempt_at),
        "freshnessSeconds": freshness["freshness_seconds"],
        "stale": bool(freshness["stale"]),
        "activeRun": active_payload,
        "phase": phase,
        "checkpointAgeSeconds": _age_seconds(checkpoint_updated_at, now),
        "checkpointUpdatedAt": serialize_utc_datetime(checkpoint_updated_at),
        "warnings": warnings,
    }


async def _downloader_business_health(app: Any) -> Dict[str, Any]:
    """读取缓存中的下载器状态；不主动连接下载器，离线只形成业务告警。"""
    store = getattr(getattr(app, "state", None), "store", None)
    if store is None or not hasattr(store, "get_snapshot"):
        return {"status": "unknown", "total": None, "offlineCount": None, "warnings": ["cache_unavailable"]}
    try:
        snapshot = await store.get_snapshot()
    except Exception:  # noqa: BLE001 - 健康视图不能泄露缓存异常细节
        return {"status": "unknown", "total": None, "offlineCount": None, "warnings": ["cache_unavailable"]}
    snapshot = snapshot or []
    offline_count = sum(1 for item in snapshot if getattr(item, "fail_time", 0) > 0)
    return {
        "status": "degraded" if offline_count else "healthy",
        "total": len(snapshot),
        "offlineCount": offline_count,
        "warnings": ["downloader_offline"] if offline_count else [],
    }


async def _build_sync_health(app: Any) -> Dict[str, Any]:
    """读取同步业务健康数据；整个查询只读，不执行写探针。"""
    async with AsyncSessionLocal() as db:
        checkpoint_result = await db.execute(select(SyncCheckpoint))
        checkpoints = list(checkpoint_result.scalars().all())
        task_result = await db.execute(
            select(CronTask).where(CronTask.task_code.in_(tuple(_SYNC_TASK_CODES.values())), CronTask.dr == 0)
        )
        tasks = list(task_result.scalars().all())

    checkpoints_by_type: Dict[str, List[SyncCheckpoint]] = {}
    for row in checkpoints:
        checkpoints_by_type.setdefault(str(row.sync_type), []).append(row)
    tasks_by_type = {
        sync_type: task for sync_type, code in _SYNC_TASK_CODES.items() for task in tasks if task.task_code == code
    }
    active_by_type = _active_run_by_type()

    sync_types = set(_SYNC_TASK_CODES) | set(checkpoints_by_type) | set(active_by_type)
    ordered_types = [sync_type for sync_type in _SYNC_TYPE_ORDER if sync_type in sync_types]
    ordered_types.extend(sorted(sync_types - set(ordered_types)))
    entries = [
        _sync_entry(
            sync_type,
            checkpoints_by_type.get(sync_type, []),
            tasks_by_type.get(sync_type),
            active_by_type.get(sync_type),
        )
        for sync_type in ordered_types
    ]
    return {
        "tasks": entries,
        "downloaders": await _downloader_business_health(app),
    }


@sync_router.get("/sync", summary="同步业务健康")
async def sync_health(
    request: Request,
    user_info: AuthenticatedUserInfo = Depends(require_authenticated_user),
):
    """返回同步 outcome/freshness/活动 phase/checkpoint 年龄及业务告警。"""
    # 仅记录访问者标识，不记录 Authorization/Cookie/JWT 内容。
    logger.info("sync_health_access username=%s", user_info.username)
    timeout_seconds = max(float(settings.HEALTH_SYNC_DB_TIMEOUT_SECONDS), 0.001)
    try:
        data = await asyncio.wait_for(_build_sync_health(request.app), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning("sync_health_query_timeout timeout_ms=%s", round(timeout_seconds * 1000.0, 1))
        return JSONResponse(
            status_code=503,
            content=_common_response(
                "error",
                "同步健康信息暂不可用",
                "503",
                {
                    "reasonCode": "sync_health_query_timeout",
                    "timeoutMs": round(timeout_seconds * 1000.0, 1),
                },
            ),
        )
    except Exception as exc:  # noqa: BLE001 - 对外只返回稳定 reason code
        logger.warning("sync_health_query_failed error_type=%s", type(exc).__name__)
        return CommonResponse(
            status="error",
            msg="同步健康信息暂不可用",
            code="500",
            data={"reasonCode": "sync_health_unavailable"},
        )
    return CommonResponse(status="success", msg="获取同步健康信息成功", code="200", data=data)
