# -*- coding: utf-8 -*-
"""
统一同步协调器（SyncCoordinator）

W2-1（PLANS/sync-database-blocking-remediation.md）：消除手动同步旁路。
手动 sync-single 与定时任务（info/tracker）共用同一业务执行入口，统一
资源准入、写治理、取消/预算语义与结构化观测。

设计：
1. SyncRequest：统一请求对象（sync_type / downloader_ids / trigger / run_id /
   deadline / record_budget / force / dry_run / is_cancelled）。
2. SyncResult：统一结果对象（outcome / phase / scanned / changed / committed /
   checkpoint / skip_reason / errors / duration_ms / run_id）。
3. run_sync 阶段编排：
   ① 资源准入（admission_controller 的 heavy_sync 令牌；cron_executor 外层已
      对同一 task_code 准入时防重入放行，避免同 code 二次 acquire 被误判跳过）；
   ② backup phase（当前仓库无同步前置的 app.db 备份逻辑，预留 hook 扩展点）；
   ③ sync phase（按 sync_type 复用现有实现，不复制业务代码）：
      - info    → qb/tr_add_torrents_info_only_async（W1-1 已治理路径）
      - tracker → qb/tr_sync_trackers_only_async + sync_tracker_status_from_keywords
      - full    → qb/tr_add_torrents_async（legacy 全量适配，写路径已收编）
   ④ 汇总 SyncResult 并输出结构化日志（run_id/trigger/sync_type/phase/outcome）。
4. 幂等运行键：f"{downloader_id}:{sync_type}" 运行注册表，重复触发返回
   already_running（不启动第二个作业）；force=True 跳过该去重。
5. 取消语义：deadline 到期或 is_cancelled() 为 True 时，在下载器调用边界/
   批次边界检查；已提交批次保留（不回滚），结果标记 partial/cancelled。

下载器读取/转换直接复用现有函数；Coordinator 只做编排与治理。
客户端只从 app.state.store 获取（downloader-connection 约束）。
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.config import settings
from app.tasks.resource_guard import SKIP_DUPLICATE, SKIP_WAIT_TIMEOUT, admission_controller
from app.tasks.task_profiles import TaskProfile, get_profile

logger = logging.getLogger(__name__)


# =============================================================================
# 统一请求/结果对象
# =============================================================================


@dataclass
class SyncRequest:
    """统一同步请求对象。

    Attributes:
        sync_type: 同步类型："info"（种子信息）/ "tracker"（Tracker 状态）/
            "full"（兼容旧全量同步）。
        downloader_ids: 目标下载器 ID 列表；None 表示全部有效下载器
            （来自 app.state.store 快照，fail_time=0）。
        trigger: 触发来源："manual"（手动接口）/ "cron"（定时任务）/ "api"。
        run_id: 运行 ID（不传时自动生成，用于日志/TaskLog 关联）。
        deadline: 时间预算（秒，可选）；到期在下载器调用边界检查，
            已提交批次保留，结果标记 partial/cancelled。
        record_budget: 记录数预算（可选，W3 单轮预算使用，本步先声明字段）。
        force: 跳过幂等运行键去重（允许排队/跳过重入检查）。
        dry_run: 只读演练：解析下载器但不执行任何写入。
        is_cancelled: 取消检测回调（阶段间轮询；True 表示请求取消）。
    """

    sync_type: str  # "info" / "tracker" / "full"
    downloader_ids: Optional[List[str]] = None  # None=全部（store 快照有效下载器）
    trigger: str = "api"  # "manual" / "cron" / "api"
    run_id: Optional[str] = None
    deadline: Optional[float] = None  # 时间预算（秒）
    record_budget: Optional[int] = None  # 记录数预算（W3 用，先声明字段）
    force: bool = False  # 跳过幂等去重
    dry_run: bool = False  # 只读演练：不执行写入
    is_cancelled: Optional[Callable[[], bool]] = None  # 取消检测回调


@dataclass
class SyncResult:
    """统一同步结果对象。

    Attributes:
        outcome: success / partial / skipped / failed / no_action /
            already_running / cancelled。
        phase: 最后到达的执行阶段（backup / sync / tracker_status / done /
            admission）。
        scanned: 扫描（参与处理）的记录数；info/full 路径底层函数暂不返回
            记录级统计，按下载器数计数（W3 补齐记录级统计）。
        changed: 实际写入（变化）行数。
        committed: 成功提交的行数。
        checkpoint: 持久化检查点（W3 使用，本步恒 None）。
        skip_reason: 跳过/拒绝原因（resource_busy / already_running 等）。
        errors: 错误消息列表（人类可读）。
        duration_ms: 整个运行耗时（毫秒）。
        run_id: 本次运行 ID。
        message: 人类可读汇总消息。
        details: 附加统计（downloader_count / successful_syncs /
            failed_syncs / admission_wait_ms / tracker_status_update 等）。
    """

    outcome: str = "success"
    phase: str = "done"
    scanned: int = 0
    changed: int = 0
    committed: int = 0
    checkpoint: Optional[Any] = None  # W3 持久化检查点，本步恒 None
    skip_reason: Optional[str] = None  # "resource_busy" / "already_running" 等
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    run_id: Optional[str] = None
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 幂等运行键注册表（进程内）
# =============================================================================

# 运行注册表：f"{downloader_id}:{sync_type}" -> run_id。
# 与 admission_controller 的 task_code 级 running 集合互补：
# - admission running 集合：同类型同步互斥（手动 vs 定时，按 task_code）。
# - 本注册表：同下载器 + 同类型去重（跨 task_code 的场景，如 full 与 info 同跑）。
_running_keys: Dict[str, str] = {}
_running_keys_lock = asyncio.Lock()

# sync_type -> 资源准入 task_code（与 cron_executor / task_profiles 对齐，
# 保证手动与定时同类型同步走同一准入通道，彻底消除旁路）。
_SYNC_TYPE_TASK_CODES: Dict[str, str] = {
    "info": "torrent_info_sync_ac608e4d",
    "tracker": "tracker_sync_598b784c",
    "full": "manual_sync_full",
}


def _sync_task_code(sync_type: str) -> str:
    """sync_type -> 资源准入 task_code。"""
    return _SYNC_TYPE_TASK_CODES.get(sync_type, f"sync_{sync_type}")


async def _register_running_keys(infos: List[Dict[str, Any]], sync_type: str, run_id: str) -> List[str]:
    """登记幂等运行键；任一 key 已存在则整体失败（返回空列表）。"""
    keys = [f"{str(info.get('downloader_id'))}:{sync_type}" for info in infos if info.get("downloader_id") is not None]
    if not keys:
        return []
    async with _running_keys_lock:
        for key in keys:
            if key in _running_keys:
                return []
        for key in keys:
            _running_keys[key] = run_id
    return keys


async def _unregister_running_keys(keys: List[str]) -> None:
    """释放幂等运行键（幂等，重复调用无害）。"""
    if not keys:
        return
    async with _running_keys_lock:
        for key in keys:
            _running_keys.pop(key, None)


# =============================================================================
# 资源准入（防重入）
# =============================================================================


@dataclass
class _AdmissionDecision:
    """Coordinator 内部准入决策。

    Attributes:
        admitted: 是否获得 heavy_sync 令牌并允许执行。
        wait_seconds: 准入等待耗时（秒）。
        skip_reason: 未准入时的原始跳过原因（SKIP_DUPLICATE / SKIP_WAIT_TIMEOUT）。
        reentrant: True 表示外层（cron_executor）已持有同一 task_code 令牌，
            本次不 acquire 也不 release（防重入）。
    """

    admitted: bool
    wait_seconds: float = 0.0
    skip_reason: Optional[str] = None
    reentrant: bool = False


async def _acquire_token(task_code: str, trigger: str) -> _AdmissionDecision:
    """请求资源准入（防重入）。

    cron_executor 已用 admission_controller.task_scope 包裹任务 execute()
    （running 集含该 task_code），此时 Coordinator 直接放行，避免同 code
    二次 acquire 被 SKIP_DUPLICATE 误判跳过整个任务。

    防重入仅对 trigger="cron" 生效：cron 路径恒由 cron_executor 外层准入
    （同 job max_instances=1 + running_tasks 防重入，job 内并发子调用共享
    同一外层令牌）；manual/api 路径没有外层令牌，若同 code 已在 running，
    说明另一实例正在运行，应返回 already_running 而不是放行。
    """
    if trigger == "cron" and task_code in admission_controller.running:
        logger.debug("sync_coordinator admission reentrant task_code=%s", task_code)
        return _AdmissionDecision(admitted=True, reentrant=True)

    profile = get_profile(task_code)
    if profile is None:
        # 未注册的 task_code（如手动全量 manual_sync_full）：构造默认重型 profile，
        # 与 task_profiles 注册项默认值一致，避免 TASK_PROFILES 注册表漂移。
        profile = TaskProfile(
            task_code=task_code,
            heavy_sync=True,
            per_downloader=False,
            queue_limit=settings.SYNC_HEAVY_QUEUE_LIMIT,
            wait_timeout=30.0,
            description=f"SyncCoordinator {task_code}",
        )
    result = await admission_controller.acquire(task_code, profile)
    return _AdmissionDecision(
        admitted=result.admitted,
        wait_seconds=result.wait_seconds,
        skip_reason=result.skip_reason,
    )


# =============================================================================
# 阶段编排
# =============================================================================

# 备份 phase 扩展 hook（当前仓库无同步前置 app.db 备份逻辑；未来接入时
# 必须在同步写入前完成并关闭文件句柄，禁止在 DML 事务中复制 app.db/WAL）。
_BACKUP_HOOK: Optional[Callable[[SyncRequest], Any]] = None


def set_backup_hook(hook: Optional[Callable[[SyncRequest], Any]]) -> None:
    """注入备份 phase hook（测试/未来接入用）。"""
    global _BACKUP_HOOK
    _BACKUP_HOOK = hook


async def run_sync(req: SyncRequest, app: Any = None) -> SyncResult:
    """统一同步入口：阶段编排 + 资源准入 + 结果汇总。

    Args:
        req: 统一同步请求对象。
        app: FastAPI 应用实例（测试注入用）；None 时从 app.main 获取。

    Returns:
        统一同步结果对象 SyncResult。

    Notes:
        - 手动后台任务也必须在后台执行体内完成准入（本函数被后台执行体调用），
          不在 HTTP 请求线程长持准入锁。
        - 取消/预算检查在下载器调用边界进行；已提交批次保留不回滚。
    """
    start_ts = time.perf_counter()
    run_id = req.run_id or f"sync-{uuid.uuid4().hex[:12]}"
    result = SyncResult(run_id=run_id, phase="admission")
    task_code = _sync_task_code(req.sync_type)
    # 解析 app 实例（测试注入；生产走 app.main，延迟导入防循环）
    runtime_app = _app_of(app)

    # ① 资源准入（重型同步全局互斥 + 同类去重）
    decision = await _acquire_token(task_code, req.trigger)
    result.details["admission_wait_ms"] = round(decision.wait_seconds * 1000.0, 1)
    if not decision.admitted:
        if decision.skip_reason == SKIP_DUPLICATE:
            result.outcome = "already_running"
            result.skip_reason = "already_running"
            result.message = "同类型同步任务正在运行中，已拒绝重复触发"
        elif decision.skip_reason == SKIP_WAIT_TIMEOUT:
            result.outcome = "skipped"
            result.skip_reason = "resource_busy"
            result.message = f"资源准入等待超时（{decision.wait_seconds:.1f}s），本轮跳过"
        else:
            result.outcome = "skipped"
            result.skip_reason = "resource_busy"
            result.message = f"资源准入未通过（{decision.skip_reason}），本轮跳过"
        return _finish(result, req, decision, start_ts)

    try:
        # ② 备份 phase（独立于同步写入，完成后关闭文件句柄）
        result.phase = "backup"
        if _check_cancelled(req, result, start_ts):
            return _finish(result, req, decision, start_ts)
        if _BACKUP_HOOK is not None:
            try:
                backup_stats = await _BACKUP_HOOK(req)
                if backup_stats is not None:
                    result.details["backup"] = backup_stats
            except Exception as e:  # noqa: BLE001 - 备份失败不阻断同步
                result.errors.append(f"备份阶段失败: {e}")

        # 解析下载器（客户端只从 app.state.store 获取）
        infos, resolve_errors = await _resolve_downloaders(req, runtime_app)
        if resolve_errors:
            result.errors.extend(resolve_errors)
        if not infos:
            # 指定了下载器但全部不可解析 → failed；未指定且无有效下载器 → no_action
            result.outcome = "failed" if req.downloader_ids else "no_action"
            result.phase = "sync"
            result.message = "; ".join(resolve_errors) or "没有有效的下载器可同步"
            return _finish(result, req, decision, start_ts)
        result.details["downloader_count"] = len(infos)

        # ③ sync phase（按 sync_type 复用现有实现）
        result.phase = "sync"
        if _check_cancelled(req, result, start_ts):
            return _finish(result, req, decision, start_ts)

        # 幂等运行键登记（同一 downloader_id + sync_type 已 running → already_running）
        acquired_keys: List[str] = []
        if not req.force:
            acquired_keys = await _register_running_keys(infos, req.sync_type, run_id)
            if not acquired_keys:
                result.outcome = "already_running"
                result.skip_reason = "already_running"
                result.message = "同一下载器 + 同步类型正在运行中，已拒绝重复触发"
                return _finish(result, req, decision, start_ts)
        try:
            if req.dry_run:
                # 只读演练：不执行任何下载器调用与写入
                result.outcome = "no_action"
                result.message = "dry_run 演练完成：未执行任何下载器调用与写入"
                return _finish(result, req, decision, start_ts)

            await _execute_sync_phase(req, result, infos, start_ts, runtime_app)
            if result.outcome == "cancelled":
                # 取消/预算到期：已提交批次保留，不再进入后续阶段
                return _finish(result, req, decision, start_ts)

            # ④ tracker_status phase（仅 tracker 类型；full/info 不内置，
            # 保持 torrent_sync_async / sync_single 现有调用语义，避免重复调用）
            if req.sync_type == "tracker":
                await _run_tracker_status_phase(req, result, start_ts)
        finally:
            await _unregister_running_keys(acquired_keys)

        result.phase = "done"
        return _finish(result, req, decision, start_ts)
    finally:
        if not decision.reentrant:
            admission_controller.release(task_code)


def _finish(
    result: SyncResult,
    req: SyncRequest,
    decision: Optional[_AdmissionDecision],
    start_ts: float,
) -> SyncResult:
    """结算结果：填充 duration_ms 并输出结构化日志。"""
    result.duration_ms = (time.perf_counter() - start_ts) * 1000.0
    _log_result(result, req, decision)
    return result


def _check_cancelled(req: SyncRequest, result: SyncResult, start_ts: float) -> bool:
    """在阶段/下载器调用边界检查取消与时间预算。

    已提交批次不回滚；取消时 outcome 标记为 partial（有部分成果）或 cancelled。
    """
    if req.is_cancelled is not None:
        try:
            cancelled = bool(req.is_cancelled())
        except Exception:  # noqa: BLE001 - 回调异常按未取消处理
            cancelled = False
        if cancelled:
            result.errors.append("任务已取消（is_cancelled）")
            result.outcome = "partial" if result.committed > 0 else "cancelled"
            result.message = "任务已取消，已提交批次保留"
            return True
    if req.deadline is not None:
        elapsed = time.perf_counter() - start_ts
        if elapsed >= req.deadline:
            result.errors.append(f"deadline 到期（预算 {req.deadline:.1f}s，实际 {elapsed:.1f}s）")
            result.outcome = "partial" if result.committed > 0 else "cancelled"
            result.message = "时间预算到期，已提交批次保留"
            return True
    return False


async def _resolve_downloaders(req: SyncRequest, app: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """从 app.state.store 快照解析下载器信息 dict 列表。

    - downloader_ids=None：全部有效下载器（fail_time=0），与
      BaseSyncTask.get_valid_downloaders 语义一致。
    - downloader_ids 指定：按 ID 过滤；store 中不存在的 ID 记入 errors。
    """
    if app is None:
        from app.main import app as downloader_app  # noqa: PLC0415 - 延迟导入防循环

        app = downloader_app

    if not hasattr(app, "state") or not hasattr(app.state, "store"):
        return [], ["下载器缓存未初始化 (app.state.store 不存在)"]

    try:
        snapshot = await app.state.store.get_snapshot()
    except Exception as e:  # noqa: BLE001 - 快照失败按无下载器处理
        return [], [f"获取下载器缓存失败: {e}"]

    snapshot = snapshot or []
    infos: List[Dict[str, Any]] = []
    errors: List[str] = []

    if req.downloader_ids is None:
        valid = [vo for vo in snapshot if getattr(vo, "fail_time", 0) == 0]
        if not valid:
            errors.append("没有有效的下载器可同步（store 快照为空或全部失效）")
        infos = [_vo_to_downloader_info(vo) for vo in valid]
        return infos, errors

    wanted = {str(did) for did in req.downloader_ids}
    present = set()
    for vo in snapshot:
        vo_id = str(getattr(vo, "downloader_id", ""))
        if vo_id in wanted:
            present.add(vo_id)
            infos.append(_vo_to_downloader_info(vo))
    for missing in sorted(wanted - present):
        errors.append(f"下载器 {missing} 不在 store 缓存中（可能离线或未启用）")
    return infos, errors


def _vo_to_downloader_info(downloader: Any) -> Dict[str, Any]:
    """下载器 VO -> downloader_info dict（字段与 BaseSyncTask.sync_single_downloader 一致）。"""
    return {
        "downloader_id": getattr(downloader, "downloader_id", None),
        "nickname": getattr(downloader, "nickname", "unknown"),
        "host": getattr(downloader, "host", None),
        "port": getattr(downloader, "port", None),
        "username": getattr(downloader, "username", None),
        "password": getattr(downloader, "password", None),
        "downloader_type": getattr(downloader, "downloader_type", None),
        "torrent_save_path": getattr(downloader, "torrent_save_path", None),
        "enabled": "1",
        "status": "1",
    }


def _normalize_downloader_type(original_type: Any) -> Optional[str]:
    """统一下载器类型转换（0=qBittorrent, 1=Transmission，兼容字符串）。"""
    if original_type in ("qbittorrent", 0, "0"):
        return "qbittorrent"
    if original_type in ("transmission", 1, "1"):
        return "transmission"
    return None


async def _get_cached_client(app: Any, downloader_id: str) -> Optional[Any]:
    """从 app.state.store 获取缓存客户端连接（遵循 downloader-connection 约束）。"""
    if app is None:
        from app.main import app as downloader_app  # noqa: PLC0415

        app = downloader_app
    try:
        cached_downloaders = await app.state.store.get_snapshot()
        vo = next(
            (d for d in cached_downloaders if str(getattr(d, "downloader_id", "")) == str(downloader_id)),
            None,
        )
        if vo is not None and getattr(vo, "client", None) is not None:
            return vo.client
    except Exception as e:  # noqa: BLE001 - 缓存获取失败由调用方 fallback
        logger.warning(f"sync_coordinator 获取缓存客户端失败: {e}")
    return None


def _build_bt_downloader(info: Dict[str, Any]) -> Any:
    """downloader_info dict -> BtDownloaders ORM 对象（与旧同步函数入口一致）。"""
    from app.downloader.models import BtDownloaders  # noqa: PLC0415 - 延迟导入

    downloader = BtDownloaders()
    for key, value in info.items():
        if hasattr(downloader, key):
            setattr(downloader, key, value)
    return downloader


async def _execute_sync_phase(
    req: SyncRequest,
    result: SyncResult,
    infos: List[Dict[str, Any]],
    start_ts: float,
    app: Any,
) -> None:
    """按 sync_type 逐个下载器执行同步（下载器调用边界检查取消/预算）。

    下载器读取/转换直接复用现有同步函数（info-only / tracker-only / legacy
    全量），本函数只做编排：会话创建、客户端获取、结果汇总。
    """
    ok = 0
    fail = 0
    for index, info in enumerate(infos):
        if _check_cancelled(req, result, start_ts):
            break
        status = await _sync_one_downloader(req, result, info, app)
        if status == "success":
            ok += 1
        else:
            fail += 1
        logger.debug(
            "sync_coordinator downloader_done run_id=%s sync_type=%s index=%d/%d " "downloader=%s status=%s",
            result.run_id,
            req.sync_type,
            index + 1,
            len(infos),
            info.get("nickname", "unknown"),
            status,
        )

    result.details["successful_syncs"] = ok
    result.details["failed_syncs"] = fail
    if result.outcome in ("cancelled", "partial"):
        # 取消/预算到期：保留取消语义（已提交批次统计已累加），不再覆盖
        return
    if ok > 0 and fail > 0:
        result.outcome = "partial"
        result.message = f"同步完成：{ok} 成功，{fail} 失败"
    elif ok > 0:
        result.outcome = "success"
        result.message = f"同步完成：{ok} 个下载器全部成功"
    else:
        result.outcome = "failed"
        result.message = f"同步失败：{fail} 个下载器全部失败"


def _app_of(app: Any) -> Any:
    """解析 app 实例：测试注入优先，否则从 app.main 延迟导入（防循环 import）。"""
    if app is not None:
        return app
    from app.main import app as downloader_app  # noqa: PLC0415

    return downloader_app


async def _sync_one_downloader(req: SyncRequest, result: SyncResult, info: Dict[str, Any], app: Any) -> str:
    """同步单个下载器，返回 "success" / "failed"。

    具体 qB/TR 读取与转换全部复用现有同步函数；异常在下载器粒度捕获，
    不阻断其他下载器（汇总为 partial）。
    """
    downloader_id = str(info.get("downloader_id") or "unknown")
    nickname = info.get("nickname", "unknown")
    downloader_type = _normalize_downloader_type(info.get("downloader_type"))
    if downloader_type is None:
        result.errors.append(f"下载器 {nickname} 不支持的下载器类型: {info.get('downloader_type')}")
        return "failed"

    from app.database import AsyncSessionLocal  # noqa: PLC0415 - 延迟导入
    from app.api.endpoints.torrents_async import (  # noqa: PLC0415
        qb_add_torrents_async,
        tr_add_torrents_async,
        qb_add_torrents_info_only_async,
        tr_add_torrents_info_only_async,
        qb_sync_trackers_only_async,
        tr_sync_trackers_only_async,
    )

    downloader = _build_bt_downloader(info)
    cached_client = await _get_cached_client(app, downloader_id)

    try:
        async with AsyncSessionLocal() as db:
            if req.sync_type == "info":
                # W1-1 已治理路径：info-only（client=None 时由同步函数 fallback 新建）
                if downloader_type == "qbittorrent":
                    await qb_add_torrents_info_only_async(db, [downloader], client=cached_client)
                else:
                    await tr_add_torrents_info_only_async(db, [downloader], client=cached_client)
            elif req.sync_type == "tracker":
                # tracker-only 需要缓存客户端（约束16：客户端只从 store 获取）
                if cached_client is None:
                    result.errors.append(f"无法获取下载器 {nickname} 的缓存客户端连接")
                    return "failed"
                if downloader_type == "qbittorrent":
                    sub_result = await qb_sync_trackers_only_async(db, downloader, cached_client)
                else:
                    sub_result = await tr_sync_trackers_only_async(db, downloader, cached_client)
                if sub_result.get("status") == "success":
                    # 记录级统计（tracker 路径底层函数返回 tracker_count/torrent_count）
                    result.scanned += int(sub_result.get("torrent_count", 0) or 0)
                    result.changed += int(sub_result.get("tracker_count", 0) or 0)
                    result.committed += int(sub_result.get("tracker_count", 0) or 0)
                    return "success"
                result.errors.append(
                    f"下载器 {nickname} tracker 同步失败: {sub_result.get('message', 'unknown error')}"
                )
                return "failed"
            else:
                # full：legacy 全量同步（qb/tr_add_torrents_async，写路径已收编
                # 至统一 bulk_upsert_with_retry；文件备份段保留原语义）
                if downloader_type == "qbittorrent":
                    await qb_add_torrents_async(db, [downloader])
                else:
                    await tr_add_torrents_async(db, [downloader])
        result.scanned += 1  # info/full 路径暂无记录级统计，按下载器计（W3 补齐）
        return "success"
    except Exception as e:  # noqa: BLE001 - 下载器粒度捕获，汇总为 partial/failed
        result.errors.append(f"同步下载器 {nickname} 失败: {e}")
        return "failed"


async def _run_tracker_status_phase(req: SyncRequest, result: SyncResult, start_ts: float) -> None:
    """tracker 同步完成后的关键词状态增量更新（W1-2 兼容包装）。

    与旧 tracker_sync_task 语义一致：仅当本批有成功同步的下载器时执行；
    结果写入 result.details["tracker_status_update"] 供任务页结构兼容。
    """
    result.phase = "tracker_status"
    if _check_cancelled(req, result, start_ts):
        return
    if result.details.get("successful_syncs", 0) <= 0:
        return
    from app.api.endpoints.torrent_sync import update_tracker_status_from_keywords  # noqa: PLC0415

    try:
        tracker_result = await update_tracker_status_from_keywords()
        result.details["tracker_status_update"] = tracker_result
    except Exception as e:  # noqa: BLE001 - 状态更新失败不改变主 outcome
        result.errors.append(f"Tracker 状态更新失败: {e}")


# =============================================================================
# 结果映射（对外兼容）
# =============================================================================


def map_sync_result_to_legacy_dict(result: SyncResult, downloader_info: Dict[str, Any]) -> Dict[str, Any]:
    """SyncResult -> torrent_sync_db_async 旧返回 dict 结构（status/message/...）。

    保持旧 API 契约：status 取值 success/failed（含 outcome 附加字段便于观测）。
    """
    if result.outcome == "success":
        status = "success"
        message = result.message or f"下载器 {downloader_info.get('nickname', 'unknown')} 同步成功"
    else:
        status = "failed"
        message = result.message or "; ".join(result.errors) or "同步失败"
    return {
        "status": status,
        "message": message,
        "downloader_type": str(downloader_info.get("downloader_type", "unknown")),
        "nickname": downloader_info.get("nickname", "unknown"),
        "outcome": result.outcome,
        "run_id": result.run_id,
        "duration_ms": round(result.duration_ms, 1),
    }


def map_sync_result_to_task_dict(result: SyncResult, downloader_info: Dict[str, Any]) -> Dict[str, Any]:
    """SyncResult -> 定时任务 sync_func 返回 dict 结构（status/message/nickname）。

    供 torrent_info_sync_task / tracker_sync_task 的 execute_sync_with_concurrency
    汇总使用（status 取值 success/failed/no_action，与旧任务语义一致）。
    """
    status = "success" if result.outcome == "success" else "failed"
    if result.outcome == "no_action":
        status = "no_action"
    return {
        "status": status,
        "message": result.message or "; ".join(result.errors) or "同步完成",
        "nickname": downloader_info.get("nickname", "unknown"),
        "outcome": result.outcome,
        "run_id": result.run_id,
        "tracker_status_update": result.details.get("tracker_status_update"),
    }


# =============================================================================
# 结构化观测日志
# =============================================================================


def _log_result(
    result: SyncResult,
    req: SyncRequest,
    decision: Optional[_AdmissionDecision] = None,
) -> None:
    """输出结构化结果日志（run_id/trigger/sync_type/phase/outcome 关联）。"""
    extra = {
        "run_id": result.run_id,
        "trigger": req.trigger,
        "sync_type": req.sync_type,
        "downloader_count": result.details.get("downloader_count", 0),
        "admission_wait_ms": result.details.get("admission_wait_ms"),
        "phase": result.phase,
        "outcome": result.outcome,
        "skip_reason": result.skip_reason,
        "duration_ms": round(result.duration_ms, 1),
    }
    if result.outcome in ("success", "partial", "no_action"):
        logger.info(
            "sync_coordinator run_id=%s trigger=%s sync_type=%s downloader_count=%d "
            "admission_wait_ms=%s phase=%s outcome=%s skip_reason=%s duration_ms=%.1f "
            "scanned=%d changed=%d committed=%d",
            result.run_id,
            req.trigger,
            req.sync_type,
            result.details.get("downloader_count", 0),
            result.details.get("admission_wait_ms"),
            result.phase,
            result.outcome,
            result.skip_reason,
            result.duration_ms,
            result.scanned,
            result.changed,
            result.committed,
            extra=extra,
        )
    else:
        logger.warning(
            "sync_coordinator run_id=%s trigger=%s sync_type=%s downloader_count=%d "
            "admission_wait_ms=%s phase=%s outcome=%s skip_reason=%s duration_ms=%.1f "
            "scanned=%d changed=%d committed=%d errors=%s",
            result.run_id,
            req.trigger,
            req.sync_type,
            result.details.get("downloader_count", 0),
            result.details.get("admission_wait_ms"),
            result.phase,
            result.outcome,
            result.skip_reason,
            result.duration_ms,
            result.scanned,
            result.changed,
            result.committed,
            result.errors[:5],
            extra=extra,
        )
