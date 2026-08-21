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
6. 持久化检查点（W3-2）：运行前按 (downloader_id, sync_type) 读取/初始化
   sync_checkpoints；运行中批次 durable commit 后推进（outcome=partial +
   last_success_at + cursor）；运行后按最终 outcome 落终态。更新走 version
   乐观锁（独立短事务），并发冲突不倒退；dry_run 零副作用。

下载器读取/转换直接复用现有函数；Coordinator 只做编排与治理。
客户端只从 app.state.store 获取（downloader-connection 约束）。
"""

import asyncio
import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from sqlalchemy import case as sa_case
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.sync_checkpoint import (
    OUTCOME_FAILED,
    OUTCOME_PARTIAL,
    OUTCOME_SUCCESS,
    TERMINAL_OUTCOMES,
    SyncCheckpoint,
    sanitize_detail_json,
)
from app.services.sync_observability import (
    EVENT_ADMISSION,
    EVENT_CHECKPOINT,
    EVENT_SYNC_RUN_START,
    clear_run_id,
    log_event,
    set_run_id,
)
from app.tasks.resource_guard import SKIP_DUPLICATE, SKIP_WAIT_TIMEOUT, admission_controller
from app.tasks.task_profiles import TaskProfile, get_profile
from app.utils.datetime_utils import serialize_utc_datetime

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
            已提交批次保留，结果标记 partial/cancelled；W3-1 起透传给 qB
            tracker 单轮时间预算（QB_TRACKER_RUN_BUDGET_SECONDS 覆盖）。
        record_budget: 记录数预算（可选）；W3-1 起透传给 qB tracker 单轮
            数量预算（QB_TRACKER_MAX_TORRENTS_PER_RUN 覆盖）。
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
        checkpoint: 持久化检查点（W3-2）：本次运行读取/初始化后的检查点记录
            dict 列表（含 downloader_id/cursor/cycle_started_at/outcome/version
            等）；dry_run 或未进入同步阶段时保持 None。
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
    checkpoint: Optional[Any] = None  # W3-2 持久化检查点 dict 列表（运行后填充；dry_run 保持 None）
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

# 活动运行只读快照（W4-2 健康接口）。
# 与 _running_keys 分开：前者只负责幂等去重，后者提供 run_id/phase 等运维视图。
# 该注册表是进程内短生命周期状态，不作为业务事实落库，也不在健康检查中写入。
_active_runs: Dict[str, Dict[str, Any]] = {}


def _register_active_run(run_id: str, req: SyncRequest) -> None:
    """登记同步运行，供受保护同步健康接口读取。"""
    _active_runs[run_id] = {
        "run_id": run_id,
        "sync_type": req.sync_type,
        "phase": "admission",
        "started_at": datetime.now(),
        "downloader_count": len(req.downloader_ids) if req.downloader_ids is not None else None,
    }


def _update_active_run(
    run_id: str,
    *,
    phase: Optional[str] = None,
    downloader_count: Optional[int] = None,
) -> None:
    """更新活动同步运行快照；运行已结束时允许调用并安全忽略。"""
    active = _active_runs.get(run_id)
    if active is None:
        return
    if phase is not None:
        active["phase"] = phase
    if downloader_count is not None:
        active["downloader_count"] = downloader_count


def _unregister_active_run(run_id: str) -> None:
    """移除活动运行快照。"""
    _active_runs.pop(run_id, None)


def get_active_sync_runs() -> List[Dict[str, Any]]:
    """返回活动同步运行的脱敏快照，供健康接口只读。"""
    return [dict(value) for value in _active_runs.values()]


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
# 持久化同步检查点（W3-2，PLANS/sync-database-blocking-remediation.md）
# =============================================================================


def _default_checkpoint_session_factory() -> AsyncSession:
    """默认检查点会话工厂：真实库 AsyncSessionLocal（延迟导入防循环）。"""
    from app.database import AsyncSessionLocal  # noqa: PLC0415 - 延迟导入

    return AsyncSessionLocal()


async def _query_checkpoint_row(db: AsyncSession, downloader_id: str, sync_type: str) -> Optional[SyncCheckpoint]:
    """按 (downloader_id, sync_type) 查询检查点行。"""
    stmt = select(SyncCheckpoint).where(
        SyncCheckpoint.downloader_id == downloader_id,
        SyncCheckpoint.sync_type == sync_type,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_checkpoint_by_id(db: AsyncSession, checkpoint_id: int) -> Optional[SyncCheckpoint]:
    """按主键查询检查点行。"""
    stmt = select(SyncCheckpoint).where(SyncCheckpoint.id == checkpoint_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _checkpoint_row_to_dict(row: SyncCheckpoint) -> Dict[str, Any]:
    """ORM 行 -> raw dict（datetime 保持原值，供内部比较/推进用）。"""
    return {
        "id": row.id,
        "downloader_id": row.downloader_id,
        "sync_type": row.sync_type,
        "cursor": row.cursor_value,
        "cycle_started_at": row.cycle_started_at,
        "last_full_sync_at": row.last_full_sync_at,
        "last_success_at": row.last_success_at,
        "last_attempt_at": row.last_attempt_at,
        "outcome": row.outcome,
        "detail": row.detail,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _checkpoint_public_dict(checkpoint: Dict[str, Any]) -> Dict[str, Any]:
    """raw dict -> 对外可读 dict（datetime 统一转 UTC ISO 字符串）。"""
    return {
        key: (serialize_utc_datetime(value) if isinstance(value, datetime) else value)
        for key, value in checkpoint.items()
    }


class SyncCheckpointStore:
    """持久化同步检查点存储（W3-2）。

    设计要点：
    1. 独立短事务：每次读写使用独立 AsyncSession 并单独 commit，不持有跨批
       写锁；checkpoint 是低频小写，不与同步数据批次争用 db_write_scope 写锁。
    2. 原子性（cursor 不超前于数据）：checkpoint 更新与数据批次 commit 不在
       同一事务（把 checkpoint 并入统一写入器会放大批次事务持有时间、侵入
       sync_db_write 公共路径，成本高收益低）。本步保证推进只发生在同步实现
       报告批次 durable commit 之后——推进严格滞后于数据落盘，重启后重做
       最后一批是幂等安全的。
    3. 并发不倒退：更新一律 ``UPDATE ... WHERE id=? AND version=?`` 乐观锁；
       受影响行数=0 视为 version 冲突，重读最新行后按单调性合并
       （last_success_at 取 max、既有 cursor 不被覆盖、终态 outcome 不被
       进行中状态降级），重试一次仍失败则放弃本次推进并计入 conflicts。
    """

    def __init__(self, session_factory: Optional[Callable[[], AsyncSession]] = None) -> None:
        self._session_factory = session_factory or _default_checkpoint_session_factory

    def _open(self) -> AsyncSession:
        return self._session_factory()

    async def get_or_create(self, downloader_id: str, sync_type: str) -> Dict[str, Any]:
        """读取或初始化检查点行（独立短事务），返回 raw dict。

        新建行：downloader_id/sync_type/cycle_started_at=now/last_attempt_at=now，
        outcome 保持 None（尚无完成记录）；既有行只读不改（周期语义保留，
        W3-1 续跑依据）。并发创建竞争由唯一约束兜底：回滚后读取已存在行。
        """
        now = datetime.utcnow()
        async with self._open() as db:
            row = await _query_checkpoint_row(db, downloader_id, sync_type)
            if row is not None:
                return _checkpoint_row_to_dict(row)
            db.add(
                SyncCheckpoint(
                    downloader_id=downloader_id,
                    sync_type=sync_type,
                    cycle_started_at=now,
                    last_attempt_at=now,
                    outcome=None,
                    version=0,
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                row = await _query_checkpoint_row(db, downloader_id, sync_type)
                if row is None:
                    raise
                return _checkpoint_row_to_dict(row)
            fresh = await _query_checkpoint_row(db, downloader_id, sync_type)
            if fresh is None:  # 防御：插入成功后重读为空不应发生
                raise RuntimeError(f"checkpoint 创建后重读失败 downloader_id={downloader_id} sync_type={sync_type}")
            return _checkpoint_row_to_dict(fresh)

    async def advance(
        self,
        checkpoint_id: int,
        expected_version: int,
        *,
        cursor: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """运行中推进：outcome=partial + last_success_at=now（独立短事务）。

        Args:
            checkpoint_id: 检查点主键。
            expected_version: 读取时的乐观锁版本。
            cursor: 新的游标值（W3-1 起由同步实现提供；None 表示不提供，
                冲突重试时既有 cursor 不被覆盖）。
            detail: 聚合统计（sanitize_detail_json 白名单清洗后落库）。

        Returns:
            {"applied": bool, "conflicts": int, "checkpoint": raw dict | None}。
        """
        now = datetime.utcnow()
        applied = False
        conflicts = 0
        version = expected_version
        for attempt in range(2):
            outcome_value: str = OUTCOME_PARTIAL
            if attempt > 0:
                fresh = await self._get_by_id(checkpoint_id)
                if fresh is None:
                    break
                version = int(fresh["version"])
                # 单调性合并（并发不倒退）：
                # - last_success_at 取 max（不把成功提交时间回拨）
                # - 既有 cursor 不被覆盖（透明游标不可比大小，保守保留）
                # - 对方已落终态时不降级为 partial
                if fresh["last_success_at"] is not None and fresh["last_success_at"] >= now:
                    now = fresh["last_success_at"]
                if fresh["cursor"] is not None and fresh["cursor"] != cursor:
                    cursor = fresh["cursor"]
                if fresh["outcome"] in TERMINAL_OUTCOMES:
                    outcome_value = cast(str, fresh["outcome"])
            if await self._apply_advance(checkpoint_id, version, now, cursor, outcome_value, detail):
                applied = True
                break
            conflicts += 1
        return {"applied": applied, "conflicts": conflicts, "checkpoint": await self._get_by_id(checkpoint_id)}

    async def finalize(
        self,
        checkpoint_id: int,
        expected_version: int,
        *,
        outcome: str,
        cursor: Optional[str] = None,
        last_success: bool = False,
        last_full: bool = False,
        detail: Optional[Dict[str, Any]] = None,
        clear_cursor: bool = False,
    ) -> Dict[str, Any]:
        """运行结束落终态（独立短事务）。

        - last_success=True（success/partial）：last_success_at=now；
        - last_full=True（success 且本轮覆盖全部）：last_full_sync_at=now；
        - 失败/跳过/取消：只更新 outcome + last_attempt_at，last_success_at 保留。
        - clear_cursor=True（W3-1 第二部分 cycle complete）：强制清空 cursor，
          覆盖"既有 cursor 不被覆盖"的冲突合并保护（仅周期完整、由 Coordinator
          在 tracker 路径使用，防止陈旧 cursor 被写回）。

        Returns:
            {"applied": bool, "conflicts": int, "checkpoint": raw dict | None}。
        """
        now = datetime.utcnow()
        applied = False
        conflicts = 0
        version = expected_version
        for attempt in range(2):
            if attempt > 0:
                fresh = await self._get_by_id(checkpoint_id)
                if fresh is None:
                    break
                version = int(fresh["version"])
                if last_success and fresh["last_success_at"] is not None and fresh["last_success_at"] >= now:
                    now = fresh["last_success_at"]
                if fresh["cursor"] is not None and fresh["cursor"] != cursor:
                    cursor = fresh["cursor"]
                if clear_cursor:
                    cursor = None
            if await self._apply_finalize(
                checkpoint_id, version, now, outcome, cursor, last_success, last_full, detail
            ):
                applied = True
                break
            conflicts += 1
        return {"applied": applied, "conflicts": conflicts, "checkpoint": await self._get_by_id(checkpoint_id)}

    async def _apply_advance(
        self,
        checkpoint_id: int,
        expected_version: int,
        now: datetime,
        cursor: Optional[str],
        outcome_value: str,
        detail: Optional[Dict[str, Any]],
    ) -> bool:
        """乐观锁推进 UPDATE；受影响行数>0 表示推进成功。"""
        stmt = (
            update(SyncCheckpoint)
            .where(SyncCheckpoint.id == checkpoint_id, SyncCheckpoint.version == expected_version)
            .values(
                cursor_value=cursor,
                last_success_at=now,
                last_attempt_at=now,
                outcome=outcome_value,
                detail_json=sanitize_detail_json(detail),
                version=SyncCheckpoint.version + 1,
                updated_at=now,
            )
        )
        async with self._open() as db:
            result = await db.execute(stmt)
            await db.commit()
            return bool(result.rowcount and result.rowcount > 0)

    async def _apply_finalize(
        self,
        checkpoint_id: int,
        expected_version: int,
        now: datetime,
        outcome: str,
        cursor: Optional[str],
        last_success: bool,
        last_full: bool,
        detail: Optional[Dict[str, Any]],
    ) -> bool:
        """乐观锁终态 UPDATE；受影响行数>0 表示更新成功。"""
        stmt = (
            update(SyncCheckpoint)
            .where(SyncCheckpoint.id == checkpoint_id, SyncCheckpoint.version == expected_version)
            .values(
                cursor_value=cursor,
                last_attempt_at=now,
                last_success_at=sa_case((last_success, now), else_=SyncCheckpoint.last_success_at),
                last_full_sync_at=sa_case((last_full, now), else_=SyncCheckpoint.last_full_sync_at),
                outcome=outcome,
                detail_json=sanitize_detail_json(detail),
                version=SyncCheckpoint.version + 1,
                updated_at=now,
            )
        )
        async with self._open() as db:
            result = await db.execute(stmt)
            await db.commit()
            return bool(result.rowcount and result.rowcount > 0)

    async def _get_by_id(self, checkpoint_id: int) -> Optional[Dict[str, Any]]:
        """按主键读取检查点（独立短事务）。"""
        async with self._open() as db:
            row = await _get_checkpoint_by_id(db, checkpoint_id)
            return _checkpoint_row_to_dict(row) if row is not None else None


# 全局检查点存储（默认真实库实现；测试用 set_checkpoint_store 换内存库）
_CHECKPOINT_STORE = SyncCheckpointStore()


def set_checkpoint_store(store: Optional[SyncCheckpointStore]) -> None:
    """替换全局检查点存储（测试注入内存库）；None 恢复默认真实库实现。"""
    global _CHECKPOINT_STORE
    _CHECKPOINT_STORE = store if store is not None else SyncCheckpointStore()


# 运行期活动检查点上下文：f"{downloader_id}:{sync_type}" -> raw checkpoint dict。
# 供同步实现（W3-1 起）通过 get_run_checkpoint / push_sync_progress 查询与推进。
# 进程内单运行上下文：同一 (downloader_id, sync_type) 的并发运行由幂等运行键
# 防重入；不同 sync_type 之间按复合 key 隔离，互不覆盖。
_ACTIVE_CHECKPOINTS: Dict[str, Dict[str, Any]] = {}


def _checkpoint_key(downloader_id: str, sync_type: str) -> str:
    return f"{str(downloader_id)}:{sync_type}"


def _resolve_active_checkpoint(downloader_id: str, sync_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """按 (downloader_id, sync_type) 解析活动检查点；sync_type 缺省时唯一匹配兜底。"""
    if sync_type is not None:
        return _ACTIVE_CHECKPOINTS.get(_checkpoint_key(downloader_id, sync_type))
    matches = [value for key, value in _ACTIVE_CHECKPOINTS.items() if key.startswith(f"{str(downloader_id)}:")]
    return matches[0] if len(matches) == 1 else None


def get_run_checkpoint(downloader_id: str, sync_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """查询当前运行的持久化检查点（续跑上下文）。

    同步实现（或测试替身）在运行中调用：返回 raw checkpoint dict
    （cursor/outcome/version/last_success_at 等）；无活动运行返回 None。
    """
    return _resolve_active_checkpoint(downloader_id, sync_type)


async def push_sync_progress(
    downloader_id: str,
    sync_type: Optional[str] = None,
    *,
    cursor: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> bool:
    """同步实现运行期推进检查点（每批 durable commit 后调用，W3-1 起使用）。

    内部走 version 乐观锁独立短事务；推进失败（冲突重试后仍失败）返回 False，
    由调用方决定是否重试。约定：cursor 必须在调用方对应批次数据 commit 之后
    才能传入，保证游标不超前于落盘数据。
    """
    row = _resolve_active_checkpoint(downloader_id, sync_type)
    if row is None:
        logger.warning("sync_coordinator push_sync_progress 无活动检查点上下文 downloader_id=%s", downloader_id)
        return False
    store_out = await _CHECKPOINT_STORE.advance(int(row["id"]), int(row["version"]), cursor=cursor, detail=detail)
    if store_out["checkpoint"] is not None:
        _ACTIVE_CHECKPOINTS[_checkpoint_key(str(row["downloader_id"]), str(row["sync_type"]))] = store_out["checkpoint"]
    if not store_out["applied"]:
        logger.warning(
            "sync_coordinator checkpoint_advance_conflict downloader_id=%s sync_type=%s conflicts=%d",
            row["downloader_id"],
            row["sync_type"],
            store_out["conflicts"],
        )
    return bool(store_out["applied"])


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
        - W4-1 第二部分：run_id 经 contextvars 贯穿整个运行（log_event 自动
          附加 run_id 字段），finally 清空，保证事件可按 run_id 还原阶段顺序。
    """
    start_ts = time.perf_counter()
    run_id = req.run_id or f"sync-{uuid.uuid4().hex[:12]}"
    _register_active_run(run_id, req)
    set_run_id(run_id)
    try:
        return await _run_sync_core(req, app, run_id, start_ts)
    finally:
        _unregister_active_run(run_id)
        clear_run_id()


async def _run_sync_core(req: SyncRequest, app: Any, run_id: str, start_ts: float) -> SyncResult:
    """run_sync 主体编排（run_id 上下文已就绪，见 run_sync）。"""
    result = SyncResult(run_id=run_id, phase="admission")
    _update_active_run(run_id, phase="admission")
    task_code = _sync_task_code(req.sync_type)
    # 解析 app 实例（测试注入；生产走 app.main，延迟导入防循环）
    runtime_app = _app_of(app)

    # W4-1 第二部分：运行开始事件（run_id 由上下文自动附加；downloader_count
    # 仅当显式指定下载器时携带请求数，未指定时以实际解析数在后续事件出现）
    _start_fields: Dict[str, Any] = {
        "sync_type": req.sync_type,
        "trigger": req.trigger,
        "phase": "admission",
    }
    if req.downloader_ids is not None:
        _start_fields["downloader_count"] = len(req.downloader_ids)
    log_event(EVENT_SYNC_RUN_START, **_start_fields)

    # ① 资源准入（重型同步全局互斥 + 同类去重）
    decision = await _acquire_token(task_code, req.trigger)
    result.details["admission_wait_ms"] = round(decision.wait_seconds * 1000.0, 1)
    log_event(
        EVENT_ADMISSION,
        outcome="admitted" if decision.admitted else "rejected",
        skip_reason=decision.skip_reason,
        admission_wait_ms=result.details["admission_wait_ms"],
    )
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

    checkpoints: Dict[str, Dict[str, Any]] = {}
    try:
        # ② 备份 phase（独立于同步写入，完成后关闭文件句柄）
        result.phase = "backup"
        _update_active_run(run_id, phase="backup")
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
            _update_active_run(run_id, phase="sync", downloader_count=0)
            result.message = "; ".join(resolve_errors) or "没有有效的下载器可同步"
            return _finish(result, req, decision, start_ts)
        result.details["downloader_count"] = len(infos)

        # ③ sync phase（按 sync_type 复用现有实现）
        result.phase = "sync"
        _update_active_run(run_id, phase="sync", downloader_count=len(infos))
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
                # 只读演练：不执行任何下载器调用、检查点读写与写入
                result.outcome = "no_action"
                result.message = "dry_run 演练完成：未执行任何下载器调用与写入"
                return _finish(result, req, decision, start_ts)

            # ③.1 持久化检查点：运行前读取/初始化（get_or_create；dry_run 已提前
            #      返回，本步零副作用；读取失败仅告警，不阻断同步）
            checkpoints = await _init_checkpoints(req, infos, result, start_ts)

            cycle_complete_map: Dict[str, bool] = {}
            try:
                cycle_complete_map = await _execute_sync_phase(req, result, infos, checkpoints, start_ts, runtime_app)
            except Exception as e:  # noqa: BLE001 - 意外异常仍要落最终检查点后上抛
                if result.outcome not in ("cancelled", "partial", "failed"):
                    result.outcome = "failed"
                result.errors.append(f"同步阶段异常: {e}")
                raise
            finally:
                # ③.2 checkpoint 最终化：成功/部分/失败/取消统一在此落终态
                #      （独立短事务；取消时 outcome=cancelled 且 last_success_at 保留；
                #       tracker 周期完整的下载器清空 cursor + 更新 last_full_sync_at）
                await _finalize_checkpoints(
                    req,
                    result,
                    checkpoints,
                    start_ts,
                    cancelled=_is_run_cancelled(req, result),
                    cycle_complete_map=cycle_complete_map,
                )

            if result.outcome == "cancelled":
                # 取消/预算到期：已提交批次保留，不再进入后续阶段
                return _finish(result, req, decision, start_ts)

            # ④ tracker_status phase（仅 tracker 类型；full/info 不内置，
            # 保持 torrent_sync_async / sync_single 现有调用语义，避免重复调用）
            if req.sync_type == "tracker":
                result.phase = "tracker_status"
                _update_active_run(run_id, phase="tracker_status")
                await _run_tracker_status_phase(req, result, start_ts)
        finally:
            await _unregister_running_keys(acquired_keys)

        result.phase = "done"
        _update_active_run(run_id, phase="done")
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
    if result.run_id:
        _update_active_run(result.run_id, phase=result.phase)
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
        "path_mapping": getattr(downloader, "path_mapping", None),
        "path_mapping_rules": getattr(downloader, "path_mapping_rules", None),
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


# =============================================================================
# 检查点编排（W3-2：读取/推进/最终化）
# =============================================================================


def _is_run_cancelled(req: SyncRequest, result: SyncResult) -> bool:
    """判断本轮是否被取消（显式 is_cancelled 回调或结果已标记 cancelled）。

    注意：取消且已有提交时 SyncResult.outcome 为 partial，因此需要单独判定，
    保证 checkpoint 按 cancelled 落终态且 last_success_at 保留。
    """
    if result.outcome == "cancelled":
        return True
    if req.is_cancelled is not None:
        try:
            return bool(req.is_cancelled())
        except Exception:  # noqa: BLE001 - 回调异常按未取消处理
            return False
    return False


def _is_full_coverage(req: SyncRequest, checkpoint: Dict[str, Any]) -> bool:
    """本轮是否覆盖全部：full 类型，或从未续跑（开始无游标）即全量覆盖。

    W3-1 引入游标后，从 cursor 续跑的轮次不再算全覆盖（每轮到达末尾时才
    记录 cycle complete + last_full_sync_at）。
    """
    if req.sync_type == "full":
        return True
    return not checkpoint.get("cursor")


async def _init_checkpoints(
    req: SyncRequest,
    infos: List[Dict[str, Any]],
    result: SyncResult,
    start_ts: float,
) -> Dict[str, Dict[str, Any]]:
    """运行前读取/初始化每个有效下载器的检查点（get_or_create，独立短事务）。

    - 新建行：downloader_id/sync_type/cycle_started_at=now/last_attempt_at=now，
      outcome 保持 None；既有行只读不改。
    - 读取的 cursor/outcome 透传到 SyncResult.checkpoint（对外可读 dict）。
    - 读取失败仅告警跳过（重启后重做是幂等安全的），不阻断同步。
    - 本函数只在非 dry_run 路径被调用。
    """
    checkpoints: Dict[str, Dict[str, Any]] = {}
    public_entries: List[Dict[str, Any]] = []
    for info in infos:
        downloader_id = str(info.get("downloader_id") or "")
        if not downloader_id:
            continue
        try:
            row = await _CHECKPOINT_STORE.get_or_create(downloader_id, req.sync_type)
        except Exception as e:  # noqa: BLE001 - 检查点读取失败不阻断同步
            logger.warning(
                "sync_coordinator checkpoint_read_failed downloader_id=%s sync_type=%s error=%s",
                downloader_id,
                req.sync_type,
                e,
            )
            continue
        checkpoints[downloader_id] = row
        _ACTIVE_CHECKPOINTS[_checkpoint_key(downloader_id, req.sync_type)] = row
        public_entries.append(_checkpoint_public_dict(row))
        logger.info(
            "sync_coordinator checkpoint_loaded downloader_id=%s sync_type=%s outcome=%s cursor=%s version=%s",
            downloader_id,
            req.sync_type,
            row["outcome"],
            row["cursor"],
            row["version"],
        )
    result.checkpoint = public_entries
    return checkpoints


async def _advance_checkpoint_after_sync(
    req: SyncRequest,
    result: SyncResult,
    checkpoints: Dict[str, Dict[str, Any]],
    downloader_id: str,
    start_ts: float,
    new_cursor: Optional[str] = None,
) -> None:
    """下载器同步成功（内部批次均已 durable commit）后推进检查点。

    - 记录进行中状态：outcome=partial + last_success_at=now（聚合统计进
      detail_json）。
    - W3-1 第二部分：tracker 路径由同步实现按批推进持久化 cursor 后，此处用
      同步结果携带的最终 cursor 做一致性收敛；new_cursor=None（info/full 路径
      或本轮无新游标）时透传既有 cursor，保证不倒退、不清空。
    - 失败仅告警（含 version 冲突累计），不阻断同步结果。
    """
    row = checkpoints.get(downloader_id)
    if row is None:
        return
    detail: Dict[str, Any] = {
        "scanned": result.scanned,
        "changed": result.changed,
        "committed": result.committed,
        "duration_ms": round((time.perf_counter() - start_ts) * 1000.0, 1),
    }
    cursor_value = row.get("cursor") if new_cursor is None else new_cursor
    try:
        store_out = await _CHECKPOINT_STORE.advance(
            int(row["id"]), int(row["version"]), cursor=cursor_value, detail=detail
        )
        conflicts = int(store_out.get("conflicts", 0) or 0)
        if conflicts:
            result.details["checkpoint_version_conflicts"] = (
                int(result.details.get("checkpoint_version_conflicts", 0) or 0) + conflicts
            )
        fresh = store_out["checkpoint"]
        if fresh is not None:
            checkpoints[downloader_id] = fresh
            _ACTIVE_CHECKPOINTS[_checkpoint_key(downloader_id, req.sync_type)] = fresh
        logger.info(
            "sync_coordinator checkpoint_advanced downloader_id=%s sync_type=%s outcome=%s cursor=%s version=%s",
            downloader_id,
            req.sync_type,
            fresh["outcome"] if fresh else row.get("outcome"),
            fresh["cursor"] if fresh else row.get("cursor"),
            fresh["version"] if fresh else row.get("version"),
        )
        # W4-1 第二部分：检查点推进事件（run_id 由上下文自动附加；与既有日志并存）
        log_event(
            EVENT_CHECKPOINT,
            downloader_id=downloader_id,
            sync_type=req.sync_type,
            outcome=fresh["outcome"] if fresh else row.get("outcome"),
            cursor=fresh["cursor"] if fresh else row.get("cursor"),
        )
    except Exception as e:  # noqa: BLE001 - 检查点推进失败不影响同步结果
        logger.warning(
            "sync_coordinator checkpoint_advance_failed downloader_id=%s sync_type=%s error=%s",
            downloader_id,
            req.sync_type,
            e,
        )


async def _finalize_checkpoints(
    req: SyncRequest,
    result: SyncResult,
    checkpoints: Dict[str, Dict[str, Any]],
    start_ts: float,
    cancelled: bool = False,
    cycle_complete_map: Optional[Dict[str, bool]] = None,
) -> None:
    """运行后按最终 outcome 更新全部涉及检查点（独立短事务，不持有跨批写锁）。

    - success/partial → outcome + last_success_at
    - failed/skipped/no_action/cancelled → outcome + last_attempt_at
      （last_success_at 保留，取消后仍能看到最近成功提交时间）
    - success 且本轮覆盖全部 → last_full_sync_at
    - W3-1 第二部分：tracker 周期完整（全部处理完且全部批 commit 成功）视为
      全覆盖 → 终态清空 cursor（clear_cursor=True，下一轮从头开始新周期）
      并更新 last_full_sync_at；非周期完整时 cursor 透传最后 durable 批位置。
    - 失败仅告警（含 version 冲突累计），不阻断结果返回。
    """
    if not checkpoints:
        _ACTIVE_CHECKPOINTS.clear()
        return
    final_outcome = "cancelled" if cancelled else (result.outcome or OUTCOME_FAILED)
    last_success = final_outcome in (OUTCOME_SUCCESS, OUTCOME_PARTIAL)
    detail: Dict[str, Any] = {
        "scanned": result.scanned,
        "changed": result.changed,
        "committed": result.committed,
        "duration_ms": round((time.perf_counter() - start_ts) * 1000.0, 1),
        "version_conflicts": int(result.details.get("checkpoint_version_conflicts", 0) or 0),
    }
    cycle_map = cycle_complete_map or {}
    for downloader_id, row in checkpoints.items():
        try:
            full_coverage = _is_full_coverage(req, row)
            # info/tracker 的有界续跑在本轮完整处理后都允许清除 cursor；
            # full 路径没有游标，保持原有语义。
            cycle_done = bool(cycle_map.get(downloader_id))
            if cycle_done:
                full_coverage = True
            clear_cursor = bool(cycle_done and final_outcome == OUTCOME_SUCCESS)
            store_out = await _CHECKPOINT_STORE.finalize(
                int(row["id"]),
                int(row["version"]),
                outcome=final_outcome,
                cursor=None if clear_cursor else row.get("cursor"),
                clear_cursor=clear_cursor,
                last_success=last_success,
                last_full=(final_outcome == OUTCOME_SUCCESS and full_coverage),
                detail=detail,
            )
            conflicts = int(store_out.get("conflicts", 0) or 0)
            if conflicts:
                result.details["checkpoint_version_conflicts"] = (
                    int(result.details.get("checkpoint_version_conflicts", 0) or 0) + conflicts
                )
            fresh = store_out["checkpoint"]
            if fresh is not None:
                _ACTIVE_CHECKPOINTS[_checkpoint_key(downloader_id, req.sync_type)] = fresh
            logger.info(
                "sync_coordinator checkpoint_finalized downloader_id=%s sync_type=%s outcome=%s cursor=%s version=%s",
                downloader_id,
                req.sync_type,
                final_outcome,
                fresh["cursor"] if fresh else row.get("cursor"),
                fresh["version"] if fresh else row.get("version"),
            )
            # W4-1 第二部分：检查点终态事件（run_id 由上下文自动附加；与既有日志并存）
            log_event(
                EVENT_CHECKPOINT,
                downloader_id=downloader_id,
                sync_type=req.sync_type,
                outcome=final_outcome,
                cursor=fresh["cursor"] if fresh else row.get("cursor"),
            )
        except Exception as e:  # noqa: BLE001 - 检查点落盘失败不阻断结果返回
            logger.warning(
                "sync_coordinator checkpoint_finalize_failed downloader_id=%s sync_type=%s error=%s",
                downloader_id,
                req.sync_type,
                e,
            )
    _ACTIVE_CHECKPOINTS.clear()


async def _execute_sync_phase(
    req: SyncRequest,
    result: SyncResult,
    infos: List[Dict[str, Any]],
    checkpoints: Dict[str, Dict[str, Any]],
    start_ts: float,
    app: Any,
) -> Dict[str, bool]:
    """按 sync_type 逐个下载器执行同步（下载器调用边界检查取消/预算）。

    下载器读取/转换直接复用现有同步函数（info-only / tracker-only / legacy
    全量），本函数只做编排：会话创建、客户端获取、结果汇总、检查点推进。

    Returns:
        cycle_complete_map：downloader_id -> 是否本轮完成完整周期（tracker
        路径由同步函数报告；info/full 路径恒为空），供终态 finalize 清空
        cursor 并更新 last_full_sync_at。
    """
    ok = 0
    partial_ok = 0
    fail = 0
    cycle_complete_map: Dict[str, bool] = {}
    for index, info in enumerate(infos):
        if _check_cancelled(req, result, start_ts):
            break
        downloader_id = str(info.get("downloader_id") or "")
        status, meta = await _sync_one_downloader(req, result, info, app, checkpoints.get(downloader_id))
        if status == "success":
            ok += 1
            if meta and meta.get("cycle_complete"):
                # W3-1 第二部分：周期完整 → 跳过中间推进，终态 finalize 负责
                # 清空 cursor + 更新 last_full_sync_at（下一轮从头开始新周期）
                cycle_complete_map[downloader_id] = True
                logger.info(
                    "sync_coordinator downloader_cycle_complete run_id=%s sync_type=%s downloader=%s",
                    result.run_id,
                    req.sync_type,
                    info.get("nickname", "unknown"),
                )
            else:
                await _advance_checkpoint_after_sync(
                    req,
                    result,
                    checkpoints,
                    downloader_id,
                    start_ts,
                    new_cursor=(meta or {}).get("cursor"),
                )
        elif status == "partial":
            # W3-1 第二部分：预算到期/批次失败——有部分成果（已提交批次保留），
            # 计入成功数（不阻塞其他下载器）但最终 outcome 标记 partial
            ok += 1
            partial_ok += 1
            await _advance_checkpoint_after_sync(
                req,
                result,
                checkpoints,
                downloader_id,
                start_ts,
                new_cursor=(meta or {}).get("cursor"),
            )
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
        return cycle_complete_map
    if ok > 0 and fail > 0:
        result.outcome = "partial"
        result.message = f"同步完成：{ok} 成功，{fail} 失败"
    elif partial_ok > 0:
        result.outcome = "partial"
        result.message = "同步完成：存在部分完成（单轮预算到期或批次边界）"
    elif ok > 0:
        result.outcome = "success"
        result.message = f"同步完成：{ok} 个下载器全部成功"
    else:
        result.outcome = "failed"
        result.message = f"同步失败：{fail} 个下载器全部失败"
    return cycle_complete_map


def _app_of(app: Any) -> Any:
    """解析 app 实例：测试注入优先，否则从 app.main 延迟导入（防循环 import）。"""
    if app is not None:
        return app
    from app.main import app as downloader_app  # noqa: PLC0415

    return downloader_app


async def _sync_one_downloader(
    req: SyncRequest,
    result: SyncResult,
    info: Dict[str, Any],
    app: Any,
    checkpoint: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """同步单个下载器，返回 (status, meta)。

    status: "success" / "partial"（预算到期/批次失败，有部分成果）/"failed"。
    meta: info/tracker 路径携带 {"cursor": ..., "cycle_complete": bool} 供检查点
    推进与终态（清空 cursor / last_full_sync_at）使用；full 路径为 None。

    具体 qB/TR 读取与转换全部复用现有同步函数；异常在下载器粒度捕获，
    不阻断其他下载器（汇总为 partial）。
    """
    downloader_id = str(info.get("downloader_id") or "unknown")
    nickname = info.get("nickname", "unknown")
    downloader_type = _normalize_downloader_type(info.get("downloader_type"))
    if downloader_type is None:
        result.errors.append(f"下载器 {nickname} 不支持的下载器类型: {info.get('downloader_type')}")
        return "failed", None

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
    if cached_client is None:
        result.errors.append(f"无法获取下载器 {nickname} 的缓存客户端连接")
        return "failed", None

    try:
        async with AsyncSessionLocal() as db:
            if req.sync_type == "info":
                info_cursor: Optional[str] = None

                async def _on_info_progress(cursor_value: str) -> None:
                    nonlocal info_cursor
                    info_cursor = cursor_value
                    applied = await push_sync_progress(
                        downloader_id,
                        "info",
                        cursor=cursor_value,
                        detail={"downloader_id": downloader_id},
                    )
                    if applied and checkpoint is not None:
                        fresh = get_run_checkpoint(downloader_id, "info")
                        if fresh is not None:
                            checkpoint.clear()
                            checkpoint.update(fresh)

                info_sync_func = (
                    qb_add_torrents_info_only_async
                    if downloader_type == "qbittorrent"
                    else tr_add_torrents_info_only_async
                )
                info_kwargs: Dict[str, Any] = {
                    "client": cached_client,
                    "cursor": checkpoint.get("cursor") if checkpoint else None,
                    "progress_callback": _on_info_progress,
                }
                try:
                    signature = inspect.signature(info_sync_func)
                    accepts_kwargs = any(
                        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
                    )
                    if not accepts_kwargs:
                        info_kwargs = {key: value for key, value in info_kwargs.items() if key in signature.parameters}
                except (TypeError, ValueError):
                    pass
                info_meta = await info_sync_func(db, [downloader], **info_kwargs)
                await _reconcile_torrent_file_backups(db, downloader, result, nickname)
                if isinstance(info_meta, dict):
                    if info_cursor is not None and not info_meta.get("cursor"):
                        info_meta["cursor"] = info_cursor
                    result.scanned += int(info_meta.get("processed", 0) or 0)
                    if info_meta.get("partial"):
                        result.errors.append(
                            f"下载器 {nickname} info 同步部分完成（预算到期），"
                            f"processed={info_meta.get('processed', 0)}/{info_meta.get('total', 0)}"
                        )
                        return "partial", info_meta
                    if info_meta.get("cycle_complete"):
                        return "success", info_meta
            elif req.sync_type == "tracker":
                # tracker-only 需要缓存客户端（约束16：客户端只从 store 获取）
                if downloader_type == "qbittorrent":
                    # W3-1 第二部分：Coordinator 预算（deadline/record_budget）透传给
                    # qB tracker 单轮预算；续跑 cursor 由同步实现从运行期检查点自行读取
                    sub_result = await qb_sync_trackers_only_async(
                        db,
                        downloader,
                        cached_client,
                        deadline=req.deadline,
                        record_budget=req.record_budget,
                    )
                else:
                    sub_result = await tr_sync_trackers_only_async(db, downloader, cached_client)
                if sub_result.get("status") == "success":
                    # 记录级统计（tracker 路径底层函数返回 tracker_count/torrent_count）
                    result.scanned += int(sub_result.get("torrent_count", 0) or 0)
                    result.changed += int(sub_result.get("tracker_count", 0) or 0)
                    result.committed += int(sub_result.get("tracker_count", 0) or 0)
                    meta: Optional[Dict[str, Any]] = {
                        "cursor": sub_result.get("cursor"),
                        "cycle_complete": bool(sub_result.get("cycle_complete", False)),
                    }
                    if sub_result.get("partial"):
                        # 单轮预算到期/批次失败：有部分成果，结果标记 partial
                        result.errors.append(
                            f"下载器 {nickname} tracker 同步部分完成（预算到期或批次边界）: "
                            f"{sub_result.get('message', 'partial')}"
                        )
                        return "partial", meta
                    return "success", meta
                result.errors.append(
                    f"下载器 {nickname} tracker 同步失败: {sub_result.get('message', 'unknown error')}"
                )
                return "failed", None
            else:
                # full：legacy 全量同步（qb/tr_add_torrents_async，写路径已收编
                # 至统一 bulk_upsert_with_retry；文件备份段保留原语义）
                if downloader_type == "qbittorrent":
                    await qb_add_torrents_async(db, [downloader], client=cached_client)
                else:
                    await tr_add_torrents_async(db, [downloader], client=cached_client)
                await _reconcile_torrent_file_backups(db, downloader, result, nickname)
        result.scanned += 1  # info/full 路径暂无记录级统计，按下载器计（W3 补齐）
        return "success", None
    except Exception as e:  # noqa: BLE001 - 下载器粒度捕获，汇总为 partial/failed
        result.errors.append(f"同步下载器 {nickname} 失败: {e}")
        return "failed", None


async def _reconcile_torrent_file_backups(
    db: AsyncSession,
    downloader: Any,
    result: SyncResult,
    nickname: str,
) -> None:
    """在种子信息落库后限量补齐备份；失败不改变信息同步结果。"""
    downloader_id = str(getattr(downloader, "downloader_id", ""))
    try:
        from app.services.torrent_file_backup_manager import (  # noqa: PLC0415
            TorrentFileBackupManagerService,
        )

        manager = TorrentFileBackupManagerService(
            db=db,
            path_mapping_service=getattr(downloader, "path_mapping_service", None),
        )
        stats = await manager.reconcile_missing_backups(
            downloader_id=downloader_id,
            torrent_save_path=getattr(downloader, "torrent_save_path", None),
            batch_size=max(1, settings.TORRENT_BACKUP_RECONCILE_BATCH_SIZE),
        )
        result.details.setdefault("torrent_file_backup", {})[downloader_id] = stats
        if stats.get("status") == "skipped":
            logger.warning(
                "torrent_backup_reconcile skipped downloader=%s nickname=%s reason=%s "
                "pending=%s attempted=%s missing_source=%s",
                downloader_id,
                nickname,
                stats.get("skip_reason"),
                stats.get("pending"),
                stats.get("attempted"),
                stats.get("missing_source"),
            )
        elif stats.get("created"):
            logger.info(
                "torrent_backup_reconcile done downloader=%s nickname=%s created=%s " "pending=%s batch_limited=%s",
                downloader_id,
                nickname,
                stats.get("created"),
                stats.get("pending"),
                stats.get("batch_limited"),
            )
    except Exception as exc:  # noqa: BLE001 - 备份补偿失败不阻断种子信息同步
        message = f"下载器 {nickname} 种子文件增量备份失败: {exc}"
        result.errors.append(message)
        result.details.setdefault("torrent_file_backup", {})[downloader_id] = {
            "status": "failed",
            "error": str(exc),
        }
        logger.warning("torrent_backup_reconcile failed downloader=%s error=%s", downloader_id, exc)


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
