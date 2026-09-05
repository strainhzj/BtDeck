import asyncio
import faulthandler
import inspect
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from app.core.config import settings
from app.tasks.cron_crud_async import AsyncCronTaskCRUD, AsyncTaskLogsCRUD
from app.tasks.cleanup_executor import CleanupTaskExecutor
from app.database import get_db, AsyncSessionLocal, SessionLocal
from app.services.speed_schedule_service import SpeedScheduleService
from app.services.sync_observability import EVENT_TASK_LIFECYCLE, log_event
from app.models import (
    OUTCOME_SUCCESS,
    OUTCOME_PARTIAL,
    OUTCOME_SKIPPED,
    OUTCOME_FAILED,
    OUTCOME_NO_ACTION,
    OUTCOME_CANCELLED,
)
import json

logger = logging.getLogger(__name__)

# =============================================================================
# 安全白名单：task_type=4 的 executor 只允许第一方任务命名空间下的类路径
# =============================================================================
# 严格类路径格式（模块段+类名，各段均为合法标识符），杜绝任意代码/表达式字符串
_INTERNAL_CLASS_PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")
# 仅允许第一方任务命名空间（系统内置定时任务全部位于 app.tasks.scheduler.*），
# 阻断标准库/第三方模块的任意导入
_INTERNAL_CLASS_MODULE_PREFIX = "app.tasks."


def is_internal_class_executor_allowed(executor: str) -> bool:
    """校验 task_type=4 的 executor 是否为允许的内置类路径。

    规则：严格类路径格式 + 模块必须位于 app.tasks. 命名空间。
    历史 exec 回落路径已删除，任何不符合本规则的 executor 一律拒绝执行。
    """
    if not executor:
        return False
    if not _INTERNAL_CLASS_PATH_PATTERN.match(executor):
        return False
    module_path = executor.rsplit(".", 1)[0]
    return module_path.startswith(_INTERNAL_CLASS_MODULE_PREFIX)


# =============================================================================
# W3-4 / P1-05：六态 outcome 与跳过原因机器码（与 app.models 统一枚举对齐）
# =============================================================================

# 合法 outcome 集合：结果 dict 显式携带 outcome 时校验，非法值回退 success 映射
_VALID_OUTCOMES = frozenset(
    {OUTCOME_SUCCESS, OUTCOME_PARTIAL, OUTCOME_SKIPPED, OUTCOME_FAILED, OUTCOME_NO_ACTION, OUTCOME_CANCELLED}
)

# 数据成功 outcome：只有这些 outcome 推进 last_success_at（新鲜度判断依据）
_SUCCESS_OUTCOMES = frozenset({OUTCOME_SUCCESS, OUTCOME_PARTIAL, OUTCOME_NO_ACTION})

# 跳过原因机器码（stable machine codes，任务页展示/过滤契约）
SKIP_REASON_RESOURCE_BUSY = "resource_busy"
SKIP_REASON_ALREADY_RUNNING = "already_running"
SKIP_REASON_OUTSIDE_BUDGET = "outside_budget"
SKIP_REASON_DOWNLOADER_OFFLINE = "downloader_offline"

# 结果 dict 未显式携带 outcome 时，按 success 布尔映射（success 保持原语义：
# “执行是否成功”；outcome 是业务结果，skipped 时 success 仍为 True 不误判故障）
_SUCCESS_TO_OUTCOME = {True: OUTCOME_SUCCESS, False: OUTCOME_FAILED}


class TaskExecutionTimeoutError(Exception):
    """task_type=4 内部类任务超过 timeout_seconds 被强制终止（2026-08-25）。

    由 _execute_internal_method_observed 的 wait_for 超时抛出，经
    _run_python_internal_class 的穿透分支（不可被通用 except Exception 兜底
    吞成普通失败 dict）传至 _execute_task，落库 outcome=failed 且
    log_detail 标注超时语义。
    """

    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds
        super().__init__(f"task execution exceeded timeout {timeout_seconds:.1f}s")


class _TaskBodyTimeoutError(Exception):
    """任务体自身抛出的 TimeoutError 包装（区别于 wait_for 强制超时）。

    wait_for 超时与任务体 TimeoutError 都是裸 TimeoutError，无法用异常类型
    区分（elapsed 判定在 Windows ~15.6ms 时钟粒度下不可靠）；在执行入口把
    任务体的 TimeoutError 包成本异常后，外层 except asyncio.TimeoutError
    必然只对应强制超时。本异常走通用异常路径（普通失败）。
    """


async def _communicate_with_output_cap(process: Any, max_bytes: int) -> "tuple[str, str]":
    """并发读取子进程 stdout/stderr 并施加单流字节上限（OOM 加固 2026-09-05）。

    旧实现 communicate() 整缓冲输出——脚本疯狂输出时内存被打爆，而 TaskLogs
    .log_detail 是 2000 字符字段，全量输出最终也被截断，毫无价值。现累计到
    max_bytes 后继续 drain 丢弃直至 EOF（防管道写满导致子进程阻塞死锁），
    再 wait() 收尸。返回 (stdout_text, stderr_text)：解码 errors=ignore
    （字节级截断可能切断多字节序列），超限时附截断标记与原始总字节数。

    max_bytes <= 0 视为不限（回落旧语义，读全量）。
    """
    effective_cap = max_bytes if max_bytes and max_bytes > 0 else None

    async def _read_capped(stream: Any) -> "tuple[bytes, int]":
        collected = bytearray()
        total = 0
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if effective_cap is None or len(collected) < effective_cap:
                if effective_cap is None:
                    collected.extend(chunk)
                else:
                    collected.extend(chunk[: effective_cap - len(collected)])
        return bytes(collected), total

    stdout_task = asyncio.create_task(_read_capped(process.stdout))
    stderr_task = asyncio.create_task(_read_capped(process.stderr))
    stdout_bytes, stdout_total = await stdout_task
    stderr_bytes, stderr_total = await stderr_task
    await process.wait()

    def _render(capped: bytes, total: int) -> str:
        text = capped.decode("utf-8", errors="ignore")
        if effective_cap is not None and total > len(capped):
            text += (
                f"\n[TRUNCATED] 输出超过 {effective_cap} 字节上限" f"（总 {total} 字节），仅保留前 {len(capped)} 字节"
            )
        return text

    return _render(stdout_bytes, stdout_total), _render(stderr_bytes, stderr_total)


def _summarize_result_for_log(result: Any, *, max_value_repr: int = 200, max_head_items: int = 3) -> str:
    """把内部类任务结果渲染为有界摘要（OOM 加固 2026-09-05）。

    旧实现 f"...{str(result)}" 全量渲染——一旦某任务把大明细列表塞进结果
    dict，这里会先构建巨型字符串再截断到 2000，瞬时放大内存。现：标量取
    repr 前 max_value_repr 字符；list/dict 只记长度 + 前 max_head_items 项
    概览。execution_log/phase 行由调用方另行拼接，不受本函数影响。
    """

    def _one(value: Any) -> str:
        text = repr(value)
        if len(text) <= max_value_repr:
            return text
        return text[:max_value_repr] + "...(截断)"

    def _container(value: Any) -> str:
        summary = f"<{type(value).__name__} len={len(value)}"
        if value:
            head: Any
            if isinstance(value, dict):
                head = {key: value[key] for key in list(value)[:max_head_items]}
            else:
                head = list(value)[:max_head_items]
            summary += " head=" + _one(head)
        return summary + ">"

    if isinstance(result, dict):
        parts = []
        for key, value in result.items():
            if isinstance(value, (list, tuple, set, dict)):
                parts.append(f"{key}={_container(value)}")
            else:
                parts.append(f"{key}={_one(value)}")
        return "{" + ", ".join(parts) + "}"
    if isinstance(result, (list, tuple, set)):
        return _container(result)
    return _one(result)


class CronTaskExecutor:
    """定时任务执行器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self.running_tasks: Dict[int, bool] = {}  # 跟踪正在运行的任务
        # 运行中执行的协程句柄（_execute_task 内自登记，覆盖 APScheduler 调度与
        # start_task_immediately 两条入口），interrupt_task 据此真正取消运行实例
        self.running_task_handles: Dict[int, "asyncio.Task[None]"] = {}
        # 用户显式中断标记：区分 interrupt 取消与调度器关闭等其它取消来源
        self.interrupt_requested: set[int] = set()
        self.app = None  # ✅ 新增：存储 FastAPI 应用实例

    def set_app(self, app):
        """设置 FastAPI 应用实例

        Args:
            app: FastAPI 应用实例
        """
        self.app = app

    async def start(self):
        """启动调度器"""
        try:
            self.scheduler.start()
            logger.info("定时任务调度器启动成功")
            self._ensure_speed_schedule_job()
            # 首次启动时立即同步一次；后续由每分钟任务持续校正。
            await asyncio.to_thread(self._sync_speed_schedule)
            self._ensure_version_check_job()
            await self.load_all_tasks()
        except Exception as e:
            logger.error(f"定时任务调度器启动失败: {str(e)}")

    async def stop(self):
        """停止调度器"""
        try:
            self.scheduler.shutdown(wait=False)
            logger.info("定时任务调度器已停止")
        except Exception as e:
            logger.error(f"定时任务调度器停止失败: {str(e)}")

    def _ensure_speed_schedule_job(self):
        """注册分时段限速同步任务（每分钟执行）"""
        job_id = "speed_schedule_sync"
        if self.scheduler.get_job(job_id):
            return

        self.scheduler.add_job(
            func=self._sync_speed_schedule,
            trigger=IntervalTrigger(minutes=1),
            id=job_id,
            name="speed_schedule_sync",
            replace_existing=True,
            misfire_grace_time=30,
            max_instances=1,
            coalesce=True,
        )

    def _sync_speed_schedule(self):
        """Sync speed schedule rules."""
        if not self.app or not hasattr(self.app.state, "store") or self.app.state.store is None:
            logger.warning("Downloader cache not initialized, skip speed schedule sync")
            return

        cached_downloaders = self.app.state.store.get_snapshot_sync()
        if not cached_downloaders:
            logger.warning("Downloader cache is empty, skip speed schedule sync")
            return

        db = SessionLocal()
        try:
            downloader_ids = [
                downloader.downloader_id
                for downloader in cached_downloaders
                if getattr(downloader, "fail_time", 0) == 0
            ]
            if not downloader_ids:
                return

            placeholders = ", ".join([f":id_{idx}" for idx in range(len(downloader_ids))])
            params = {f"id_{idx}": downloader_id for idx, downloader_id in enumerate(downloader_ids)}

            sql = f"""
                SELECT ds.id, ds.downloader_id
                FROM downloader_settings ds
                WHERE ds.downloader_id IN ({placeholders})
            """
            downloaders = db.execute(text(sql), params).fetchall()

            for row in downloaders:
                SpeedScheduleService.apply_to_downloader(db, row.downloader_id, row.id)

        except Exception as e:
            logger.error(f"同步分时段限速失败: {e}")
        finally:
            db.close()

    async def load_all_tasks(self):
        """加载所有启用的定时任务 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                result = await AsyncCronTaskCRUD.get_enabled_tasks(db)

                if result.success:
                    tasks = result.data
                    rejected: list = []
                    for task in tasks:
                        if self._is_task_allowed_by_policy(task):
                            await self.add_task_to_scheduler(task)
                        else:
                            rejected.append(task)
                    logger.info(f"成功加载 {len(tasks) - len(rejected)} 个定时任务")
                    if rejected:
                        await self._notify_policy_rejected_tasks(db, rejected)
                else:
                    logger.error(f"加载定时任务失败: {result.message}")

        except Exception as e:
            logger.error(f"加载定时任务时发生错误: {str(e)}")

    @staticmethod
    def _is_task_allowed_by_policy(task: Dict[str, Any]) -> bool:
        """加载期安全策略检查。

        0-3 脚本类型受 BTDECK_ALLOW_CUSTOM_SCRIPTS 开关管控（默认关闭）；
        4 仅允许 app.tasks. 命名空间下的内置类路径。
        执行层（_run_task_script）有同一策略的二次校验作为兜底。
        """
        task_type = task.get("task_type")
        if task_type in (0, 1, 2, 3):
            return bool(settings.BTDECK_ALLOW_CUSTOM_SCRIPTS)
        if task_type == 4:
            return is_internal_class_executor_allowed(str(task.get("executor") or ""))
        return True

    async def _notify_policy_rejected_tasks(self, db, rejected: list) -> None:
        """安全策略拒绝加载的任务：告警日志 + 系统通知（dedupe 防重复打扰）。

        不自动改写任务的 enabled 状态（避免启动期静默篡改用户数据），
        由通知引导用户到任务页自行修正或删除；执行层闸门保证该任务
        即使被手动"立即启动"也不会执行。
        """
        try:
            from app.services.notification_service import NotificationService

            service = NotificationService(db)
            for task in rejected:
                task_id = task.get("task_id")
                name = task.get("task_name") or task_id
                logger.warning(
                    f"定时任务 '{name}'(ID:{task_id}) 因安全策略被拒绝加载"
                    f"(task_type={task.get('task_type')})，请在任务页修正或删除"
                )
                await service.create_notification(
                    type="system",
                    title="定时任务被安全策略拦截",
                    content=(
                        f"任务「{name}」(ID: {task_id}) 不符合执行安全策略："
                        "task_type=4 仅允许 app.tasks. 命名空间下的内置类路径，"
                        "脚本类型(0-3)需开启 BTDECK_ALLOW_CUSTOM_SCRIPTS。"
                        "该任务已停止调度，请在任务页修正或删除。"
                    ),
                    priority="warning",
                    dedupe_key=f"cron_policy_blocked:{task_id}",
                )
        except Exception as e:
            logger.error(f"写入定时任务安全拦截通知失败: {str(e)}")

    async def add_task_to_scheduler(self, task: Dict[str, Any]) -> bool:
        """添加任务到调度器"""
        try:
            job_id = f"cron_task_{task['task_id']}"

            # 如果任务已存在，先移除
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # 解析cron表达式
            trigger = self._parse_cron_plan(task["cron_plan"])
            if not trigger:
                logger.error(f"任务 {task['task_name']} 的cron表达式解析失败: {task['cron_plan']}")
                return False

            # 添加任务到调度器
            self.scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                args=[task["task_id"]],
                id=job_id,
                name=task["task_name"],
                replace_existing=True,
                misfire_grace_time=300,  # 允许5分钟的延迟执行
                max_instances=1,  # 同一任务不重入：避免上一轮未跑完时下一轮并发触发（加剧 SQLite 写锁竞争）
                coalesce=True,  # 积压的多次触发合并为一次，避免补跑风暴
            )

            logger.info(f"成功添加定时任务到调度器: {task['task_name']}")
            return True

        except Exception as e:
            logger.error(f"添加任务到调度器失败: {str(e)}")
            return False

    def _parse_cron_plan(self, cron_plan: str):
        """解析cron表达式"""
        try:
            # 支持的cron格式: "分 时 日 月 周"
            parts = cron_plan.split()
            if len(parts) != 5:
                logger.error(f"cron表达式格式错误: {cron_plan}")
                return None

            minute, hour, day, month, day_of_week = parts

            return CronTrigger(
                minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week, timezone="Asia/Shanghai"
            )

        except Exception as e:
            logger.error(f"解析cron表达式失败: {str(e)}")
            return None

    async def _execute_task(self, task_id: int):
        """执行定时任务 - 使用异步数据库操作

        会话生命周期三段式（greenlet 交错治理）：读会话（读任务+写开始时间后即关闭）→
        任务体在无会话上下文执行 → 收尾短会话顺序三写。原实现单个 AsyncSession
        从任务开始一直开到收尾，跨越任务体执行期（重型任务可达数分钟），长期挂起的
        会话与任务体内部各路 DB 写并发交错，是 "greenlet_spawn has not been called"
        偶发错误的疑似窗口（最终定位依赖 exc_info 堆栈，见 cron_crud_async 日志）。
        """
        if self.running_tasks.get(task_id, False):
            logger.warning(f"任务 {task_id} 正在运行中，跳过本次执行")
            # W3-4：重入跳过也落库（outcome=skipped + skip_reason=already_running），
            # 让任务页能区分“调度器正常但数据没更新”；不推进 last_success_at。
            await self._record_reentrant_skip(task_id)
            return

        try:
            # 标记任务为运行中
            self.running_tasks[task_id] = True
            # 自登记协程句柄（调度触发与 start_task_immediately 两条入口都经过
            # 此处），interrupt_task 据此对运行实例真正执行 cancel()
            current_handle = asyncio.current_task()
            if current_handle is not None:
                self.running_task_handles[task_id] = current_handle

            # 更新任务状态为运行中
            await self._update_task_status(task_id, 1)

            # —— 第一段：读会话（任务配置 + 开始时间，毫秒级即关闭）——
            async with AsyncSessionLocal() as db:
                task_result = await AsyncCronTaskCRUD.get_cron_task_by_id(db, task_id)

                if not task_result.success:
                    logger.error(f"获取任务信息失败: {task_result.message}")
                    return

                task = task_result.data
                if task is None:
                    logger.error(f"任务 {task_id} 数据为空，跳过执行")
                    return
                start_time = datetime.now()
                run_id = self._new_run_id(task_id)
                # 仅在当前执行上下文传递，不写回 cron_task；用于把资源占用者
                # 与 Cron 日志/同步 run_id 关联起来。
                task["cron_run_id"] = run_id
                await AsyncCronTaskCRUD.update_task_start_time(db, task_id, start_time)

            # —— 第二段：任务体（无会话上下文执行）——
            success = False
            log_detail = ""
            result: Optional[Dict[str, Any]] = None
            try:
                logger.info(f"开始执行定时任务: {task['task_name']} (ID: {task_id})")

                # 执行任务
                result = await self._run_task_script(task)
                success = result["success"]
                log_detail = result["log_detail"]

                if isinstance(result, dict) and result.get("skipped"):
                    logger.info(f"定时任务已跳过: {task['task_name']}, 原因: {result.get('skip_reason') or '-'}")
                else:
                    logger.info(f"定时任务执行完成: {task['task_name']}, 成功: {success}")

            except asyncio.CancelledError:
                # 仅吞掉用户显式中断注入的取消并按 cancelled 走完整收尾三写；
                # 调度器关闭等其它取消来源保持取消语义向上传播。
                # 捕获后协程不再处于 pending-cancel 状态，收尾段的 await 可正常完成。
                if task_id in self.interrupt_requested:
                    success = True  # 对齐 skipped 先例：用户主动行为不误判故障/告警
                    log_detail = "[INTERRUPTED] 用户中断，运行中的执行已被取消"
                    result = {
                        "success": True,
                        "outcome": OUTCOME_CANCELLED,
                        "log_detail": log_detail,
                    }
                    logger.info(f"定时任务被中断: {task['task_name']} (ID: {task_id})")
                else:
                    raise
            except Exception as e:
                success = False
                if isinstance(e, TaskExecutionTimeoutError):
                    log_detail = f"执行超时强制终止({e.timeout_seconds:.0f}s)"
                    logger.error(
                        f"定时任务执行超时被强制终止: {task['task_name']} (ID: {task_id}), "
                        f"超时: {e.timeout_seconds:.0f}s"
                    )
                else:
                    log_detail = f"任务执行异常: {str(e)}"
                    logger.error(f"定时任务执行异常: {task['task_name']}, 错误: {str(e)}", exc_info=True)

            # —— 第三段：收尾短会话（duration → log → freshness 顺序三写）——
            end_time = datetime.now()
            duration = int((end_time - start_time).total_seconds())

            # —— W3-4：六态 outcome / skip_reason 收敛 ——
            # 1) skipped 键不再丢弃：skipped=True → outcome=skipped +
            #    skip_reason（结果带机器码则用，否则默认 resource_busy）；
            # 2) 结果显式携带合法 outcome 则采用（partial/no_action/cancelled）；
            # 3) 否则按 success 布尔映射（True→success、False→failed）。
            result_dict = result if isinstance(result, dict) else {}
            if result_dict.get("skipped"):
                outcome = OUTCOME_SKIPPED
                skip_reason = result_dict.get("skip_reason") or SKIP_REASON_RESOURCE_BUSY
            elif result_dict.get("outcome") in _VALID_OUTCOMES:
                outcome = result_dict["outcome"]
                skip_reason = result_dict.get("skip_reason") or (
                    SKIP_REASON_RESOURCE_BUSY if outcome == OUTCOME_SKIPPED else None
                )
            else:
                outcome = _SUCCESS_TO_OUTCOME.get(success, OUTCOME_FAILED)
                skip_reason = None

            # 异步创建任务日志（success 保持原语义，outcome 是业务结果）
            log_data = {
                "task_id": task_id,
                "task_name": task["task_name"],
                "task_type": task["task_type"],
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "success": success,
                "outcome": outcome,
                "skip_reason": skip_reason,
                "log_detail": log_detail,
            }

            async with AsyncSessionLocal() as db:
                # 异步更新任务的执行持续时间
                await AsyncCronTaskCRUD.update_task_execution_duration(db, task_id, duration)

                await AsyncTaskLogsCRUD.create_task_log(db, log_data)

                # W3-4：更新任务数据新鲜度——每次执行更新
                # last_attempt_at/last_outcome/last_skip_reason/last_run_id；
                # last_success_at 仅当 outcome ∈ {success, partial, no_action} 推进。
                await AsyncCronTaskCRUD.update_task_freshness(
                    db,
                    task_id,
                    last_attempt_at=end_time,
                    last_outcome=outcome,
                    last_skip_reason=skip_reason,
                    last_run_id=run_id,
                    advance_success=outcome in _SUCCESS_OUTCOMES,
                )

        except Exception as e:
            logger.error(f"执行定时任务时发生严重错误: {str(e)}", exc_info=True)
        finally:
            # 状态复位与运行标记清理：读取失败早退 / 严重异常路径同样到达此处，
            # 修复旧实现 status=1 卡死的存量缺陷（早退 return 绕过 status=2，
            # 任务页持续显示“运行中”直到下一轮跑完）。
            await self._update_task_status(task_id, 2)
            # 清除运行标记
            self.running_tasks[task_id] = False
            # 清除句柄与中断标记（pop/discard 语义：早退路径可能未注册句柄）
            self.running_task_handles.pop(task_id, None)
            self.interrupt_requested.discard(task_id)

    @staticmethod
    def _new_run_id(task_id: int) -> str:
        """生成一次执行的运行 ID（唯一，重入/准入跳过也生成，便于日志溯源）。"""
        return f"cron-{task_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:12]}"

    async def _record_reentrant_skip(self, task_id: int):
        """重入跳过落库（W3-4/P1-05）。

        与资源准入跳过保持同口径：success=True（调度器正常，不误判故障/告警）、
        outcome=skipped、skip_reason=already_running，不推进 last_success_at，
        使任务页能区分“调度器正常但数据没更新”。获取任务失败（如已删除）
        则静默跳过，不影响调度器自身。
        """
        try:
            async with AsyncSessionLocal() as db:
                task_result = await AsyncCronTaskCRUD.get_cron_task_by_id(db, task_id)
                if not task_result.success:
                    return
                task = task_result.data
                if task is None:
                    return
                now = datetime.now()
                log_data = {
                    "task_id": task_id,
                    "task_name": task["task_name"],
                    "task_type": task["task_type"],
                    "start_time": now,
                    "end_time": now,
                    "duration": 0,
                    "success": True,
                    "outcome": OUTCOME_SKIPPED,
                    "skip_reason": SKIP_REASON_ALREADY_RUNNING,
                    "log_detail": "[REENTRANT_SKIP] 任务正在运行中，跳过本次执行（上一轮尚未结束）",
                }
                await AsyncTaskLogsCRUD.create_task_log(db, log_data)
                await AsyncCronTaskCRUD.update_task_freshness(
                    db,
                    task_id,
                    last_attempt_at=now,
                    last_outcome=OUTCOME_SKIPPED,
                    last_skip_reason=SKIP_REASON_ALREADY_RUNNING,
                    last_run_id=self._new_run_id(task_id),
                    advance_success=False,
                )
        except Exception as e:
            logger.error(f"记录重入跳过日志失败 (ID: {task_id}): {str(e)}")

    async def _run_task_script(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """运行任务脚本"""
        task_type = task["task_type"]
        executor = task["executor"]

        # 执行层统一安全闸门：无论任务来自调度器还是"立即启动"（start_task_immediately
        # 不经过 load_all_tasks 的加载期检查），都在此二次校验。
        # 0-3 脚本类型受 BTDECK_ALLOW_CUSTOM_SCRIPTS 开关管控（默认关闭）；
        # 4 仅允许 app.tasks. 命名空间下的内置类路径（杜绝 exec 回落的任意代码执行）。
        if task_type in (0, 1, 2, 3) and not settings.BTDECK_ALLOW_CUSTOM_SCRIPTS:
            return {
                "success": False,
                "log_detail": "自定义脚本任务已被安全策略禁用（BTDECK_ALLOW_CUSTOM_SCRIPTS=False），本次执行被拒绝",
            }
        if task_type == 4 and not is_internal_class_executor_allowed(str(executor or "")):
            return {
                "success": False,
                "log_detail": (
                    "executor 不是允许的内置类路径（须为 app.tasks. 命名空间下的类路径），"
                    f"已拒绝执行: {str(executor)[:80]}"
                ),
            }

        try:
            if task_type == 0:  # Shell脚本
                return await self._run_shell_script(executor)
            elif task_type == 1:  # CMD脚本
                return await self._run_cmd_script(executor)
            elif task_type == 2:  # PowerShell脚本
                return await self._run_powershell_script(executor)
            elif task_type == 3:  # Python脚本
                return await self._run_python_script(executor)
            elif task_type == 4:  # Python内部类
                return await self._run_python_internal_class(task)
            elif task_type == 5:  # 清理回收站任务
                return await self._run_cleanup_task(executor)
            elif task_type == 6:  # 审计日志导出任务
                return await self._run_audit_log_export_task(executor)
            else:
                return {"success": False, "log_detail": f"不支持的任务类型: {task_type}"}

        except Exception as e:
            return {"success": False, "log_detail": f"脚本执行失败: {str(e)}"}

    async def _run_script_process(self, command: str, label: str) -> Dict[str, Any]:
        """四类脚本任务（shell/cmd/powershell/python）的共享执行实现。

        输出经 _communicate_with_output_cap 施加单流字节上限（OOM 加固
        2026-09-05，CRON_SCRIPT_OUTPUT_MAX_BYTES，默认 64KB）。
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout_text, stderr_text = await _communicate_with_output_cap(
                process, settings.CRON_SCRIPT_OUTPUT_MAX_BYTES
            )

            if process.returncode == 0:
                return {
                    "success": True,
                    "log_detail": f"{label}脚本执行成功\n输出: {stdout_text}",
                }
            else:
                return {
                    "success": False,
                    "log_detail": f"{label}脚本执行失败，返回码: {process.returncode}\n错误: {stderr_text}",
                }

        except Exception as e:
            return {"success": False, "log_detail": f"{label}脚本执行异常: {str(e)}"}

    async def _run_shell_script(self, script: str) -> Dict[str, Any]:
        """运行Shell脚本"""
        return await self._run_script_process(script, "Shell")

    async def _run_cmd_script(self, script: str) -> Dict[str, Any]:
        """运行CMD脚本"""
        return await self._run_script_process(f'cmd /c "{script}"', "CMD")

    async def _run_powershell_script(self, script: str) -> Dict[str, Any]:
        """运行PowerShell脚本"""
        return await self._run_script_process(f'powershell -Command "{script}"', "PowerShell")

    async def _run_python_script(self, script: str) -> Dict[str, Any]:
        """运行Python脚本"""
        return await self._run_script_process(f'python -c "{script}"', "Python")

    async def _execute_internal_method_observed(
        self,
        execute_method: Any,
        task: Dict[str, Any],
        task_code: Optional[str],
        execution_state: Dict[str, Any],
    ) -> Any:
        """执行内部类方法并发射生命周期/心跳观测。

        2026-08-25 起：CRON_TASK_TIMEOUT_ENFORCE 开启且任务配置了正 timeout_seconds
        时，超过该值强制终止（async 取消协程 / thread 放弃等待），抛
        TaskExecutionTimeoutError 交由 _execute_task 落库 outcome=failed。
        """
        from app.tasks.resource_guard import admission_controller

        started = time.monotonic()
        execution_mode = "async" if asyncio.iscoroutinefunction(execute_method) else "thread"
        timeout_seconds: Optional[float] = None
        raw_timeout = task.get("timeout_seconds")
        if raw_timeout is not None:
            try:
                parsed_timeout = float(raw_timeout)
                # <=0 视为未设置（不强制终止也不打超时标记）：legacy 行可为 NULL/0，
                # wait_for(timeout=0) 会立即取消，语义不合理故归一为 None
                timeout_seconds = parsed_timeout if parsed_timeout > 0 else None
            except (TypeError, ValueError):
                timeout_seconds = None
        # 强制终止开关（2026-08-25）：开启且配置了正超时时，超过 timeout_seconds
        # 由 wait_for 强制终止——此前超时仅观测打标，运行实例可无限挂起并持续
        # 占用 heavy_sync 令牌（生产案例 cron-7-20260825111000 挂 8.75h）。
        # 已知限制：thread 模式超时仅放弃等待，底层线程继续执行至自然结束
        # （期间仍持有 downloader_api_runtime 的 per-downloader 令牌，见其
        # downloader_api_runtime.py 中"超时仅放弃等待 future"的设计注释），
        # 但不再占用 heavy_sync（task_scope 的 finally 在协程层释放）。
        enforce_timeout = bool(settings.CRON_TASK_TIMEOUT_ENFORCE) and timeout_seconds is not None

        task_id = task.get("task_id")
        task_name = task.get("task_name")
        cron_run_id = task.get("cron_run_id")
        observer_task: Optional[asyncio.Task] = None
        progress_stall_dumped = False  # 全线程栈转储节流：每次运行至多一次

        def holder_context() -> Dict[str, Any]:
            snapshot = None
            if task_code:
                snapshot = admission_controller.get_holder_snapshot(task_code)
            context: Dict[str, Any] = {
                "phase": execution_state.get("phase", "execute"),
                "sync_run_id": None,
            }
            if snapshot is not None:
                context["phase"] = snapshot.get("phase") or context["phase"]
                context["sync_run_id"] = snapshot.get("sync_run_id")
            return context

        def emit_lifecycle(state: str, *, level: int = logging.INFO, error_type: Optional[str] = None) -> None:
            nonlocal progress_stall_dumped
            elapsed_ms = (time.monotonic() - started) * 1000.0
            holder = holder_context()
            last_progress_ms = max(
                0.0,
                (time.monotonic() - float(execution_state.get("last_progress_monotonic", started))) * 1000.0,
            )
            fields: Dict[str, Any] = {
                "state": state,
                "phase": holder["phase"],
                "elapsed_ms": round(elapsed_ms, 1),
                "last_progress_ms": round(last_progress_ms, 1),
                "execution_mode": execution_mode,
                "timeout_exceeded": bool(timeout_seconds is not None and elapsed_ms >= timeout_seconds * 1000.0),
            }
            # 进度停滞检测（2026-08-25）：last_progress_ms 源自 execution_logger
            # 注入通道（未实现 set_execution_context 的任务恒为启动值），停滞
            # 超阈值时心跳提级 WARNING；首次触发转储全线程栈——生产案例中
            # tracker enrich 挂 8.75h 仅剩心跳静默，该转储可自动留下挂死现场
            # （faulthandler.dump_traceback 为毫秒级同步调用，锁安全）。
            try:
                stall_threshold_s = float(settings.SYNC_TASK_PROGRESS_STALL_WARNING_SECONDS)
            except (TypeError, ValueError):
                stall_threshold_s = 300.0
            if state == "heartbeat" and stall_threshold_s > 0 and last_progress_ms >= stall_threshold_s * 1000.0:
                level = max(level, logging.WARNING)
                fields["progress_stalled"] = True
                if not progress_stall_dumped:
                    progress_stall_dumped = True
                    logger.warning(
                        "任务进度停滞 %.0fs 未推进（task=%s, ID=%s），转储全线程栈辅助定位挂死现场：",
                        last_progress_ms / 1000.0,
                        task_name or "-",
                        task_id,
                    )
                    try:
                        faulthandler.dump_traceback()
                    except Exception:  # noqa: BLE001 - 转储失败不影响观测与任务执行
                        logger.debug("faulthandler dump_traceback failed", exc_info=True)
            if task_id is not None:
                fields["task_id"] = task_id
            if task_code:
                fields["task_code"] = task_code
            if task_name:
                fields["task_name"] = task_name
            if cron_run_id:
                fields["cron_run_id"] = cron_run_id
            if holder.get("sync_run_id"):
                fields["sync_run_id"] = holder["sync_run_id"]
            if timeout_seconds is not None:
                fields["timeout_seconds"] = timeout_seconds
            if error_type:
                fields["error_type"] = error_type
            try:
                log_event(EVENT_TASK_LIFECYCLE, level=level, **fields)
            except Exception:  # noqa: BLE001 - 观测器故障不能改变任务执行
                logger.debug("task lifecycle structured observation failed", exc_info=True)

        async def heartbeat_loop() -> None:
            try:
                interval = float(settings.SYNC_TASK_OBSERVABILITY_INTERVAL_SECONDS)
            except (TypeError, ValueError):
                interval = 30.0
            if interval <= 0:
                return
            interval = max(interval, 0.05)
            timeout_warned = False
            while True:
                sleep_seconds = interval
                if timeout_seconds is not None and not timeout_warned:
                    remaining = timeout_seconds - (time.monotonic() - started)
                    if remaining > 0:
                        sleep_seconds = min(sleep_seconds, max(0.05, remaining))
                    else:
                        sleep_seconds = 0.05
                await asyncio.sleep(sleep_seconds)
                elapsed_seconds = time.monotonic() - started
                timeout_exceeded = timeout_seconds is not None and elapsed_seconds >= timeout_seconds
                if timeout_exceeded and not timeout_warned:
                    timeout_warned = True
                    emit_lifecycle("timeout_warning", level=logging.WARNING)
                else:
                    emit_lifecycle("heartbeat")

        emit_lifecycle("start")
        try:
            observer_task = asyncio.create_task(heartbeat_loop())
            if execution_mode == "async":
                if enforce_timeout and timeout_seconds is not None:

                    async def _execute_async_guard():
                        try:
                            return await execute_method(app=self.app)
                        except asyncio.TimeoutError as exc:
                            raise _TaskBodyTimeoutError(str(exc) or "task body timeout") from exc

                    result = await asyncio.wait_for(_execute_async_guard(), timeout=timeout_seconds)
                else:
                    result = await execute_method(app=self.app)
            else:
                if enforce_timeout and timeout_seconds is not None:

                    def _execute_sync_guard():
                        try:
                            return execute_method(app=self.app)
                        except asyncio.TimeoutError as exc:
                            raise _TaskBodyTimeoutError(str(exc) or "task body timeout") from exc

                    result = await asyncio.wait_for(asyncio.to_thread(_execute_sync_guard), timeout=timeout_seconds)
                else:
                    result = await asyncio.to_thread(execute_method, app=self.app)
            emit_lifecycle("end")
            return result
        except asyncio.TimeoutError:
            # 任务体自身的 TimeoutError 已被 guard 包装为 _TaskBodyTimeoutError，
            # 走通用异常路径；此处必然是 wait_for 强制超时（Windows 时钟粒度下
            # wait_for 可能略早于 timeout 触发，无需也不可用 elapsed 判定）
            emit_lifecycle("timeout_killed", level=logging.ERROR, error_type="timeout")
            raise TaskExecutionTimeoutError(timeout_seconds or 0.0)
        except BaseException as exc:
            emit_lifecycle("exception", level=logging.WARNING, error_type=type(exc).__name__)
            raise
        finally:
            if observer_task is not None:
                observer_task.cancel()
                await asyncio.gather(observer_task, return_exceptions=True)

    async def _run_python_internal_class(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """运行Python内部类或代码

        同步任务资源治理接入点（sync-resource-governance 阶段 0+1）：
        - task_type=4 的 Python 内部类任务是重型同步任务的唯一入口；
        - 按 task_code 查 TASK_PROFILES，重型任务进入 TaskAdmissionController 背压，
          同类已运行/排队满则跳过本轮，避免后台任务挤占请求侧资源；
        - 未注册的 task_code 视为轻量任务，走原路径不进入背压。
        详见 PLANS/sync-resource-governance.md。
        """
        executor_code = task["executor"]
        task_code = task.get("task_code")

        # 资源准入：仅对已登记的重型任务生效
        from app.tasks.resource_guard import admission_controller
        from app.tasks.task_profiles import get_profile

        profile = get_profile(task_code)
        execution_events = []
        execution_state: Dict[str, Any] = {
            "phase": "execute",
            "last_progress_monotonic": time.monotonic(),
        }

        def record_execution_event(message: str) -> None:
            execution_events.append(str(message))
            execution_state["last_progress_monotonic"] = time.monotonic()

        def normalize_internal_result(result: Any) -> Dict[str, Any]:
            """把内部类的业务终态透传给 Cron 日志/新鲜度字段。"""
            if not isinstance(result, dict):
                return {
                    "success": True,
                    "log_detail": f"Python内部类执行成功\n结果: {str(result)}",
                }

            normalized: Dict[str, Any] = dict(result)
            status = str(result.get("status") or "").lower()
            success = result.get("success")
            if not isinstance(success, bool):
                success = status not in {"error", "failed", "failure", "timeout"}
            normalized["success"] = success
            if status == "skipped" or result.get("skipped"):
                normalized["skipped"] = True
                normalized.setdefault("outcome", OUTCOME_SKIPPED)
                normalized.setdefault("skip_reason", SKIP_REASON_OUTSIDE_BUDGET)
            elif status in {"error", "failed", "failure", "timeout"}:
                normalized.setdefault("outcome", OUTCOME_FAILED)
            elif status == "partial":
                normalized.setdefault("outcome", OUTCOME_PARTIAL)
            elif status in {"success", "completed", "ok"}:
                normalized.setdefault("outcome", OUTCOME_SUCCESS)

            phase_lines = result.get("execution_log") or execution_events
            detail = result.get("log_detail")
            if not detail and phase_lines:
                detail = "\n".join(str(line) for line in phase_lines)
            prefix = "Python内部类执行成功" if success else "Python内部类执行失败"
            # OOM 加固（2026-09-05）：结果尾巴走有界摘要（旧实现 str(result)
            # 全量渲染，大结果 dict 会先建巨型字符串再被截断）；phase 行与
            # [:2000] 截断保持原样（TaskLogs.log_detail 是 2000 字段）。
            rendered_detail = f"{prefix}\n{detail or ''}\n结果: {_summarize_result_for_log(result)}"
            normalized["log_detail"] = rendered_detail[:2000]
            return normalized

        def attach_execution_context(task_instance: Any) -> None:
            setter = getattr(task_instance, "set_execution_context", None)
            if not callable(setter):
                return
            try:
                setter(
                    execution_logger=record_execution_event,
                    timeout_seconds=task.get("timeout_seconds"),
                )
            except TypeError:
                # 用户自定义内部类可能只接受无参上下文；上下文注入失败不能
                # 改变其原有执行契约，终态仍由 normalize_internal_result 收敛。
                logger.debug("内部类不接受标准 Cron 执行上下文", exc_info=True)

        try:
            # 安全闸门（与 _run_task_script 同一策略的双保险）：type=4 仅允许
            # 第一方任务命名空间下的严格类路径，拒绝任意代码与任意模块导入。
            if not is_internal_class_executor_allowed(executor_code):
                return {
                    "success": False,
                    "log_detail": (
                        "executor 不是允许的内置类路径（须为 app.tasks. 命名空间下的类路径），"
                        f"已拒绝执行: {executor_code[:80]}"
                    ),
                }

            # 尝试作为类路径执行
            try:
                module_path, class_name = executor_code.rsplit(".", 1)
                module = __import__(module_path, fromlist=[class_name])
                task_class = getattr(module, class_name)

                if not inspect.isclass(task_class):
                    return {"success": False, "log_detail": f"executor 解析目标不是类: {class_name}"}

                # ✅ 修复：尝试在初始化时传递 app 实例
                task_instance = None
                try:
                    # 尝试通过 __init__ 参数传递 app
                    task_instance = task_class(app=self.app)
                except TypeError:
                    # 如果 __init__ 不接受 app 参数，使用 set_app 方法
                    task_instance = task_class()
                    if hasattr(task_instance, "set_app"):
                        task_instance.set_app(self.app)

                attach_execution_context(task_instance)

                # 检查是否有execute方法
                if hasattr(task_instance, "execute"):
                    execute_method = task_instance.execute

                    # ★ 资源治理：重型任务用 task_scope 包裹 execute()，
                    # admitted=False 时直接返回 skipped，不调 execute。
                    if profile is not None:
                        from app.tasks.resource_guard import AdmissionOwner

                        owner = AdmissionOwner(
                            task_id=task.get("task_id"),
                            task_name=task.get("task_name"),
                            cron_run_id=task.get("cron_run_id"),
                        )
                        async with admission_controller.task_scope(
                            task_code or "", profile, owner=owner
                        ) as admission_result:
                            if not admission_result.admitted:
                                skip_msg = (
                                    f"[ADMISSION_SKIP] Python内部类被资源治理跳过: "
                                    f"task_code={task_code}, "
                                    f"reason={admission_result.skip_reason}, "
                                    f"wait={admission_result.wait_seconds:.3f}s, "
                                    f"running={admission_result.running_count}, "
                                    f"queued={admission_result.queued_count}, "
                                    f"blocked_by={admission_result.blocked_by_task_code or '-'}, "
                                    f"holder_phase={admission_result.blocked_by_phase or '-'}, "
                                    f"holder_age={admission_result.blocked_by_age_seconds or 0.0:.3f}s, "
                                    f"holder_cron_run_id={admission_result.blocked_by_cron_run_id or '-'}, "
                                    f"holder_sync_run_id={admission_result.blocked_by_sync_run_id or '-'}"
                                )
                                logger.info(skip_msg)
                                # skipped=True 区分资源治理跳过 vs 真执行失败：
                                # _execute_task 据此把 success 记为 True（避免误判故障/告警），
                                # log_detail 含 [ADMISSION_SKIP] 机器可解析标记便于运维 grep；
                                # outcome/skip_reason（W3-4）随结果 dict 落库为
                                # skipped + resource_busy（资源准入冲突的稳定机器码）。
                                return {
                                    "success": True,
                                    "skipped": True,
                                    "outcome": OUTCOME_SKIPPED,
                                    "skip_reason": SKIP_REASON_RESOURCE_BUSY,
                                    "log_detail": skip_msg,
                                }

                            # 同步 execute 经 to_thread 执行；观测包装负责生命周期
                            # 事件与（开关开启时）超时强制终止。
                            result = await self._execute_internal_method_observed(
                                execute_method,
                                task,
                                task_code,
                                execution_state,
                            )
                            return normalize_internal_result(result)
                    else:
                        # 轻量任务：不进入资源背压，走原路径
                        result = await self._execute_internal_method_observed(
                            execute_method,
                            task,
                            task_code,
                            execution_state,
                        )
                        return normalize_internal_result(result)
                else:
                    return {"success": False, "log_detail": f"类 {class_name} 没有execute方法"}

            except (ImportError, AttributeError) as e:
                # 类路径无法解析：按执行失败处理，绝不回落到任意代码执行
                # （历史 exec 回落路径已删除——那等价于认证后 RCE）
                return {
                    "success": False,
                    "log_detail": f"内置类路径解析失败，已拒绝执行: {executor_code[:80]} ({str(e)})",
                }

        except TaskExecutionTimeoutError:
            # 强制超时必须穿透本层兜底：否则被转成普通失败 dict，
            # _execute_task 将无法识别超时语义（log_detail/outcome 标注）
            raise
        except Exception as e:
            return {"success": False, "log_detail": f"Python内部类执行异常: {str(e)}"}

    async def _update_task_status(self, task_id: int, status: int):
        """更新任务状态 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                await AsyncCronTaskCRUD.update_task_status(db, task_id, status)
        except Exception as e:
            logger.error(f"更新任务状态失败: {str(e)}")

    # 任务控制功能
    async def start_task_immediately(self, task_id: int) -> bool:
        """立即启动任务 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                task_result = await AsyncCronTaskCRUD.get_cron_task_by_id(db, task_id)

                if task_result.success:
                    task = task_result.data or {}
                    # 检查任务是否启用
                    if not task.get("enabled"):
                        error_msg = f"任务 '{task.get('task_name', task_id)}' 处于禁用状态，无法启动。请先启用该任务。"
                        logger.warning(
                            f"启动任务失败: {error_msg} (任务ID: {task_id}, 状态: enabled={task.get('enabled')})"
                        )
                        raise ValueError(error_msg)

                    # 检查任务是否已在运行中
                    if self.running_tasks.get(task_id, False):
                        error_msg = f"任务 '{task.get('task_name', task_id)}' 正在运行中，请勿重复启动。"
                        logger.warning(f"启动任务失败: {error_msg} (任务ID: {task_id})")
                        raise ValueError(error_msg)

                    # 立即执行任务
                    logger.info(f"准备立即启动任务: {task.get('task_name', task_id)} (任务ID: {task_id})")

                    # ✅ 修复：保存task引用并添加异常处理，避免异常被忽略
                    # 注意：句柄命名与任务配置字典 task 区分，回调内读取的是配置字典
                    task_handle = asyncio.create_task(self._execute_task(task_id))

                    # 添加回调处理任务异常
                    def handle_task_exception(t: asyncio.Task):
                        try:
                            exception = t.exception()
                            if exception:
                                logger.error(
                                    f"立即执行任务异常: {task.get('task_name', task_id)} (任务ID: {task_id}), 错误: {str(exception)}"
                                )
                        except asyncio.CancelledError:
                            logger.warning(f"任务被取消: {task.get('task_name', task_id)} (任务ID: {task_id})")

                    task_handle.add_done_callback(handle_task_exception)

                    return True
                else:
                    # 任务不存在
                    error_msg = task_result.message or f"任务ID {task_id} 不存在"
                    logger.error(f"启动任务失败: {error_msg}")
                    raise ValueError(error_msg)

        except ValueError:
            # 重新抛出业务逻辑异常，让上层处理
            raise
        except Exception as e:
            logger.error(f"立即启动任务异常: {str(e)} (任务ID: {task_id})", exc_info=True)
            raise

    async def pause_task(self, task_id: int) -> bool:
        """暂停任务"""
        try:
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.pause_job(job_id)
                await self._update_task_status(task_id, 2)  # 设置为空闲状态
                return True
            return False

        except Exception as e:
            logger.error(f"暂停任务失败: {str(e)}")
            return False

    async def resume_task(self, task_id: int) -> bool:
        """恢复任务"""
        try:
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.resume_job(job_id)
                return True
            return False

        except Exception as e:
            logger.error(f"恢复任务失败: {str(e)}")
            return False

    async def interrupt_task(self, task_id: int) -> bool:
        """中断任务：移除调度 + 取消运行中的执行实例。

        2026-08-25 前仅置 running_tasks=False + remove_job，对已在运行的协程
        无效（该标志只在下一次执行前检查），生产出现运行实例挂 8.75h 且无法
        停止的案例。现在通过 _execute_task 自登记的协程句柄真正 cancel：
        执行体进入 CancelledError 分支，按 outcome=cancelled 落库并走收尾三写。
        等待收尾完成再返回，消除“运行标志已放行而旧协程收尾仍在写 task 行”
        与用户立即重启的并发窗口（收尾为毫秒级 DB 短事务）。
        """
        try:
            # 设置任务为不运行状态
            self.running_tasks[task_id] = False

            # 从调度器中移除任务
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # 更新任务状态
            await self._update_task_status(task_id, 2)

            # 取消运行中的执行实例
            handle = self.running_task_handles.get(task_id)
            if handle is not None and not handle.done():
                self.interrupt_requested.add(task_id)
                handle.cancel()
                await asyncio.gather(handle, return_exceptions=True)
            return True

        except Exception as e:
            logger.error(f"中断任务失败: {str(e)}")
            return False

    async def refresh_task(self, task_id: int) -> bool:
        """刷新任务配置 - 使用异步数据库操作"""
        try:
            async with AsyncSessionLocal() as db:
                task_result = await AsyncCronTaskCRUD.get_cron_task_by_id(db, task_id)

                if task_result.success:
                    task = task_result.data or {}
                    return await self.add_task_to_scheduler(task)

                return False

        except Exception as e:
            logger.error(f"刷新任务失败: {str(e)}")
            return False

    async def remove_task_from_scheduler(self, task_id: int) -> bool:
        """从调度器中移除任务"""
        try:
            job_id = f"cron_task_{task_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"任务 {task_id} 已从调度器中移除")
                return True
            else:
                logger.warning(f"任务 {task_id} 在调度器中不存在")
                return True  # 不存在也算成功

        except Exception as e:
            logger.error(f"从调度器移除任务失败: {str(e)}")
            return False

    async def _run_cleanup_task(self, executor: str) -> Dict[str, Any]:
        """
        执行清理回收站任务

        Args:
            executor: JSON格式的清理任务配置
                {
                    "cleanup_level_3": bool,
                    "cleanup_level_4": bool,
                    "days_threshold": int
                }

        Returns:
            执行结果字典
        """
        try:
            # 解析任务配置
            task_config = json.loads(executor)

            # 验证配置
            if not isinstance(task_config, dict):
                return {"success": False, "log_detail": "任务配置格式错误，必须是JSON对象"}

            # 定义必需字段及其类型
            required_fields = {"cleanup_level_3": bool, "cleanup_level_4": bool, "days_threshold": int}

            # 验证字段存在性和类型
            for field, expected_type in required_fields.items():
                if field not in task_config:
                    return {"success": False, "log_detail": f"缺少必需字段: {field}"}
                if not isinstance(task_config[field], expected_type):
                    return {"success": False, "log_detail": f"字段 {field} 类型错误，期望 {expected_type.__name__}"}

            # 验证 days_threshold 范围
            if not (1 <= task_config["days_threshold"] <= 365):
                return {"success": False, "log_detail": "days_threshold 必须在 1-365 之间"}

            # 获取数据库会话（使用同步Session，因为CleanupTaskExecutor是同步实现）
            with next(get_db()) as db:
                # 创建清理执行器
                cleanup_executor = CleanupTaskExecutor(db)

                # 执行清理任务
                result = await cleanup_executor.execute_cleanup_task(
                    task_config=task_config, operator="system", audit_service=None  # 可选：传入审计服务实例
                )

                # 生成日志详情
                log_detail = (
                    f"清理任务完成\n"
                    f"等级3清理: {result['level3_cleaned']} 个\n"
                    f"等级4清理: {result['level4_cleaned']} 个\n"
                    f"释放空间: {result['total_size_freed'] / (1024**3):.2f} GB"
                )

                if result["errors"]:
                    log_detail += f"\n错误: {len(result['errors'])} 个错误\n"
                    log_detail += "\n".join(result["errors"][:5])  # 最多显示5个错误
                    if len(result["errors"]) > 5:
                        log_detail += f"\n... 还有 {len(result['errors']) - 5} 个错误"

                logger.info(log_detail)

                return {"success": True, "log_detail": log_detail}

        except json.JSONDecodeError as e:
            error_msg = f"任务配置JSON解析失败: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "log_detail": error_msg}

        except Exception as e:
            error_msg = f"清理任务执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "log_detail": error_msg}

    async def _run_audit_log_export_task(self, executor: str) -> Dict[str, Any]:
        """运行审计日志导出任务"""
        try:
            from app.tasks.scheduler.audit_log_exporter import AuditLogExportTask

            # 解析执行配置
            import json

            config = json.loads(executor) if isinstance(executor, str) else {}

            # 创建任务实例
            task = AuditLogExportTask()

            # 执行导出
            async with AsyncSessionLocal() as db:
                exported_count = await task.execute_manual_export(
                    db_session=db, days=config.get("days", 7), operation_type=config.get("operation_type")
                )

            return {"success": True, "log_detail": f"成功导出{exported_count}条审计日志"}

        except Exception as e:
            logger.error(f"审计日志导出任务执行失败: {str(e)}", exc_info=True)
            return {"success": False, "log_detail": f"导出失败: {str(e)}"}

    def _ensure_version_check_job(self):
        """注册 GitHub 版本检查任务（每天凌晨2点执行）"""
        job_id = "github_version_check"
        if self.scheduler.get_job(job_id):
            logger.debug(f"版本检查任务已存在: {job_id}")
            return

        # 使用 CronTrigger 设置每天凌晨2点执行
        self.scheduler.add_job(
            func=self._check_github_version,
            trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Shanghai"),
            id=job_id,
            name="GitHub版本检查",
            replace_existing=True,
            misfire_grace_time=3600,  # 错过执行时间后的宽容时间（1小时）
        )
        logger.info("已注册 GitHub 版本检查任务，每天凌晨2点执行")

    async def _check_github_version(self):
        """检查 GitHub Release 是否有新版本"""
        try:
            from app.version import CURRENT_VERSION
            from app.services.notification_service import NotificationService

            logger.info(f"开始检查 GitHub 版本更新，当前版本: {CURRENT_VERSION}")

            async with AsyncSessionLocal() as db:
                service = NotificationService(db)
                new_version = await service.check_version_update(
                    current_version=CURRENT_VERSION, github_repo="strainhzj/BtDeck"
                )

                if new_version:
                    logger.info("发现新版本通知已创建")
                else:
                    logger.info(f"当前已是最新版本: {CURRENT_VERSION}")

        except Exception as e:
            logger.error(f"GitHub 版本检查任务执行失败: {str(e)}", exc_info=True)


# 全局定时任务执行器实例
cron_executor = CronTaskExecutor()
