# -*- coding: utf-8 -*-
"""隔离区彻底删除持久化任务与进程内调度器。"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.orphan_purge_job import OrphanPurgeJob
from app.services.notification_service import NotificationService
from app.tasks.resource_guard import admission_controller

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "partial", "failed")
NOTIFICATION_EVENT = "orphan_purge_completed"
NOTIFICATION_ROUTE = "/orphan-files/index"


class OrphanPurgeJobService:
    """隔离区彻底删除任务的持久化状态服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, canonical_paths: List[str], operator: str) -> OrphanPurgeJob:
        """创建 pending 任务；按原顺序去重路径。"""
        # 路径可合法包含首尾空格；只用 strip 判断空白值，不改写原始主键。
        normalized_paths = list(dict.fromkeys(path for path in canonical_paths if path and path.strip()))
        if not normalized_paths:
            raise ValueError("至少需要一个有效的隔离区路径")

        now = datetime.utcnow()
        job = OrphanPurgeJob(
            task_id=str(uuid.uuid4()),
            status="pending",
            canonical_paths_json=json.dumps(normalized_paths, ensure_ascii=False),
            operator=operator,
            total_count=len(normalized_paths),
            purged_count=0,
            failed_count=0,
            created_at=now,
            updated_at=now,
        )
        try:
            async with admission_controller.db_write_scope():
                self.db.add(job)
                await self.db.commit()
                await self.db.refresh(job)
        except Exception:
            await self.db.rollback()
            raise
        return job

    async def get_job(self, task_id: str) -> Optional[OrphanPurgeJob]:
        return await self.db.get(OrphanPurgeJob, task_id)

    async def claim_job(self, task_id: str) -> bool:
        """原子领取 pending 任务，防止恢复任务与请求调度重复执行。"""
        now = datetime.utcnow()
        try:
            async with admission_controller.db_write_scope():
                result = await self.db.execute(
                    update(OrphanPurgeJob)
                    .where(
                        OrphanPurgeJob.task_id == task_id,
                        OrphanPurgeJob.status == "pending",
                    )
                    .values(
                        status="running",
                        started_at=now,
                        updated_at=now,
                        error_message=None,
                    )
                )
                await self.db.commit()
                return bool(getattr(result, "rowcount", 0))
        except Exception:
            await self.db.rollback()
            raise

    async def finish_job(
        self,
        task_id: str,
        *,
        status: str,
        purged_count: int,
        failed_count: int,
        failed_list: List[Dict[str, Any]],
        error_message: Optional[str] = None,
    ) -> bool:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"非法终态: {status}")
        now = datetime.utcnow()
        try:
            async with admission_controller.db_write_scope():
                result = await self.db.execute(
                    update(OrphanPurgeJob)
                    .where(
                        OrphanPurgeJob.task_id == task_id,
                        OrphanPurgeJob.status == "running",
                    )
                    .values(
                        status=status,
                        purged_count=max(0, int(purged_count)),
                        failed_count=max(0, int(failed_count)),
                        failed_list_json=json.dumps(failed_list, ensure_ascii=False),
                        error_message=error_message,
                        completed_at=now,
                        updated_at=now,
                    )
                )
                await self.db.commit()
                return bool(getattr(result, "rowcount", 0))
        except Exception:
            await self.db.rollback()
            raise

    async def recover_interrupted_jobs(self) -> List[str]:
        """启动时将上次进程遗留的 running 任务恢复为 pending。"""
        now = datetime.utcnow()
        try:
            async with admission_controller.db_write_scope():
                await self.db.execute(
                    update(OrphanPurgeJob)
                    .where(OrphanPurgeJob.status == "running")
                    .values(
                        status="pending",
                        updated_at=now,
                        error_message="服务重启后自动恢复任务",
                    )
                )
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        result = await self.db.execute(
            select(OrphanPurgeJob.task_id)
            .where(OrphanPurgeJob.status == "pending")
            .order_by(OrphanPurgeJob.created_at.asc())
        )
        return [str(task_id) for task_id in result.scalars().all()]

    async def get_unsent_notification_task_ids(self, limit: int = 100) -> List[str]:
        result = await self.db.execute(
            select(OrphanPurgeJob.task_id)
            .where(
                OrphanPurgeJob.status.in_(TERMINAL_STATUSES),
                OrphanPurgeJob.notification_sent_at.is_(None),
            )
            .order_by(OrphanPurgeJob.completed_at.asc())
            .limit(limit)
        )
        return [str(task_id) for task_id in result.scalars().all()]

    async def notify_job_result(self, task_id: str) -> bool:
        """幂等写入任务结果通知，并记录通知成功时间。"""
        job = await self.get_job(task_id)
        if job is None or job.status not in TERMINAL_STATUSES:
            return False
        if job.notification_sent_at is not None:
            return True

        title, priority = self._notification_style(job.status)
        content = self._notification_content(job)
        notification = await NotificationService(self.db).create_notification(
            type="system",
            title=title,
            content=content,
            priority=priority,
            extra_data={
                "event": NOTIFICATION_EVENT,
                "route": NOTIFICATION_ROUTE,
                "task_id": job.task_id,
                "task_status": job.status,
                "total_count": job.total_count,
                "purged_count": job.purged_count,
                "failed_count": job.failed_count,
                "failed_list": job.failed_list[:20],
            },
            dedupe_key=f"orphan_purge:{job.task_id}",
        )
        if notification is None:
            return False

        try:
            async with admission_controller.db_write_scope():
                await self.db.execute(
                    update(OrphanPurgeJob)
                    .where(OrphanPurgeJob.task_id == task_id)
                    .values(notification_sent_at=datetime.utcnow(), updated_at=datetime.utcnow())
                )
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return True

    @staticmethod
    def _notification_style(status: str) -> tuple[str, str]:
        if status == "completed":
            return "孤儿文件彻底删除完成", "info"
        if status == "partial":
            return "孤儿文件彻底删除部分完成", "warning"
        return "孤儿文件彻底删除失败", "error"

    @staticmethod
    def _notification_content(job: OrphanPurgeJob) -> str:
        lines = [
            "### 彻底删除结果",
            f"- 任务 ID：{job.task_id}",
            f"- 总数：{job.total_count}",
            f"- 成功：{job.purged_count}",
            f"- 失败：{job.failed_count}",
        ]
        if job.error_message:
            lines.append(f"- 任务错误：{job.error_message[:500]}")
        if job.failed_list:
            lines.append("")
            lines.append("### 失败明细（最多显示 10 条）")
            for item in job.failed_list[:10]:
                canonical_path = str(item.get("canonical_path", "未知原路径"))
                quarantine_path = item.get("quarantine_path")
                reason = str(item.get("reason", "未知原因"))
                if quarantine_path and str(quarantine_path) != canonical_path:
                    lines.append(
                        f"- 原路径: {canonical_path[-160:]}；隔离路径: {str(quarantine_path)[-160:]}：{reason[:300]}"
                    )
                else:
                    lines.append(f"- {canonical_path[-200:]}：{reason[:300]}")
        return "\n".join(lines)


class OrphanPurgeJobDispatcher:
    """单进程串行执行持久化任务；数据库领取保证幂等。"""

    def __init__(self, app: Any, session_factory: Any = AsyncSessionLocal):
        self.app = app
        self.session_factory = session_factory
        self._tasks: Dict[str, asyncio.Task[Any]] = {}
        self._serial_lock = asyncio.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def submit(self, task_id: str) -> bool:
        """安排任务并立即返回；已安排的 task_id 不重复创建协程。"""
        if self._closed:
            raise RuntimeError("孤儿彻底删除调度器已关闭")
        existing = self._tasks.get(task_id)
        if existing and not existing.done():
            return False

        task = asyncio.create_task(self.execute_job(task_id), name=f"orphan-purge-{task_id}")
        self._tasks[task_id] = task

        def _on_done(done: asyncio.Task[Any]) -> None:
            self._task_done(task_id, done)

        task.add_done_callback(_on_done)
        return True

    def _task_done(self, task_id: str, task: asyncio.Task[Any]) -> None:
        self._tasks.pop(task_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "[隔离删除任务] 未捕获异常 task_id=%s: %s",
                task_id,
                error,
                exc_info=(type(error), error, error.__traceback__),
            )

    async def recover_pending_jobs(self) -> Dict[str, int]:
        """启动恢复 pending/running 任务、补发通知并清理历史空目录。"""
        async with self.session_factory() as db:
            service = OrphanPurgeJobService(db)
            pending_ids = await service.recover_interrupted_jobs()
            notification_ids = await service.get_unsent_notification_task_ids()

        for task_id in notification_ids:
            await self._notify_safely(task_id)

        try:
            async with self.session_factory() as db:
                from app.services.orphan_file_service import OrphanFileService

                await OrphanFileService(db).prune_recorded_empty_quarantine_dirs()
        except Exception as exc:
            logger.warning("[隔离删除任务] 启动清理历史空目录失败: %s", exc)

        for task_id in pending_ids:
            self.submit(task_id)
        return {"recovered_count": len(pending_ids), "notification_retry_count": len(notification_ids)}

    async def execute_job(self, task_id: str) -> None:
        """领取并执行单个任务，任务终态先落库再发送通知。"""
        async with self._serial_lock:
            async with self.session_factory() as db:
                job_service = OrphanPurgeJobService(db)
                if not await job_service.claim_job(task_id):
                    return
                job = await job_service.get_job(task_id)
                if job is None:
                    return
                canonical_paths = job.canonical_paths
                operator = str(job.operator)
                total_count = int(job.total_count or 0)

            try:
                if not canonical_paths:
                    raise ValueError("任务路径数据为空或损坏")
                store = await self._wait_for_store()
                async with self.session_factory() as db:
                    from app.services.audit_service import AuditLogService
                    from app.services.orphan_file_service import OrphanFileService

                    purge_service = OrphanFileService(db)
                    result = await purge_service.purge_quarantine_now(
                        canonical_paths=canonical_paths,
                        operator=operator,
                        store=store,
                        audit_service=AuditLogService(db),
                    )
                    await purge_service.prune_recorded_empty_quarantine_dirs()

                purged_count = int(result.get("purged_count", 0) or 0)
                failed_list_value = result.get("failed_list", [])
                failed_list = failed_list_value if isinstance(failed_list_value, list) else []
                failed_count = int(result.get("failed_count", len(failed_list)) or 0)
                if result.get("rejected") or (purged_count == 0 and failed_count > 0):
                    status = "failed"
                elif failed_count > 0:
                    status = "partial"
                else:
                    status = "completed"
                error_message = str(result.get("error")) if result.get("error") else None

                async with self.session_factory() as db:
                    await OrphanPurgeJobService(db).finish_job(
                        task_id,
                        status=status,
                        purged_count=purged_count,
                        failed_count=failed_count,
                        failed_list=failed_list,
                        error_message=error_message,
                    )
            except asyncio.CancelledError:
                # 保持 running；下次启动会恢复为 pending 并重新领取。
                raise
            except Exception as exc:
                logger.error("[隔离删除任务] 执行失败 task_id=%s: %s", task_id, exc, exc_info=True)
                failed_list = [{"canonical_path": path, "reason": str(exc)} for path in canonical_paths]
                async with self.session_factory() as db:
                    await OrphanPurgeJobService(db).finish_job(
                        task_id,
                        status="failed",
                        purged_count=0,
                        failed_count=total_count,
                        failed_list=failed_list,
                        error_message=str(exc)[:2000],
                    )

            await self._notify_safely(task_id)

    async def _wait_for_store(self, timeout_seconds: float = 60.0) -> Any:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            store = getattr(getattr(self.app, "state", None), "store", None)
            if store is not None:
                return store
            await asyncio.sleep(0.1)
        raise RuntimeError("下载器共享连接缓存尚未初始化，任务无法安全执行")

    async def _notify_safely(self, task_id: str) -> None:
        try:
            async with self.session_factory() as db:
                await OrphanPurgeJobService(db).notify_job_result(task_id)
        except Exception as exc:
            # 终态已持久化；启动恢复和通知补偿任务会再次发送。
            logger.error("[隔离删除任务] 结果通知失败 task_id=%s: %s", task_id, exc, exc_info=True)

    async def shutdown(self) -> None:
        """取消进程内协程；持久化 running 状态由下次启动恢复。"""
        self._closed = True
        tasks: Set[asyncio.Task[Any]] = {task for task in self._tasks.values() if not task.done()}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


def get_orphan_purge_dispatcher(app: Any) -> OrphanPurgeJobDispatcher:
    """获取应用级调度器；测试或无 lifespan 场景下允许惰性创建。"""
    dispatcher = getattr(getattr(app, "state", None), "orphan_purge_dispatcher", None)
    if dispatcher is None or dispatcher.closed:
        dispatcher = OrphanPurgeJobDispatcher(app)
        app.state.orphan_purge_dispatcher = dispatcher
    return dispatcher
