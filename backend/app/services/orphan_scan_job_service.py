# -*- coding: utf-8 -*-
"""孤儿扫描后台任务提交、执行与启动恢复。"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models.orphan_file import OrphanScanResult
from app.services.orphan_lease import OrphanLeaseBusyError, orphan_maintenance_scope
from app.tasks.resource_guard import admission_controller
from app.torrents.audit_enums import AuditOperationResult, AuditOperationType

logger = logging.getLogger(__name__)


class OrphanScanJobService:
    """用扫描结果表持久化后台任务状态；scan_id 同时作为 task_id。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_scan(self, *, scan_type: str, operator: str) -> Dict[str, Any]:
        """创建 queued 扫描；已有 queued/running 时幂等返回现有任务。"""
        try:
            async with admission_controller.db_write_scope():
                active_result = await self.db.execute(
                    select(OrphanScanResult)
                    .where(OrphanScanResult.status.in_(["queued", "running"]))
                    .order_by(
                        OrphanScanResult.scan_time.asc(),
                        OrphanScanResult.created_at.asc(),
                    )
                    .limit(1)
                )
                active = active_result.scalar_one_or_none()
                if active is not None:
                    # rollback 会 expire ORM 属性；先复制轻量字段，避免随后访问触发
                    # 异步懒加载（MissingGreenlet）。已有任务只返回稳定标量快照。
                    active_scan_id = str(active.scan_id)
                    active_status = str(active.status)
                    await self.db.rollback()
                    return {
                        "scan_id": active_scan_id,
                        "task_id": active_scan_id,
                        "status": active_status,
                        "accepted": False,
                    }

                scan_id = str(uuid.uuid4())
                record = OrphanScanResult(
                    scan_id=scan_id,
                    scan_time=datetime.utcnow(),
                    scan_type=scan_type,
                    operator=operator,
                    status="queued",
                    details_mode="current",
                )
                self.db.add(record)
                await self.db.commit()
                return {
                    "scan_id": scan_id,
                    "task_id": scan_id,
                    "status": "queued",
                    "accepted": True,
                }
        except Exception:
            await self.db.rollback()
            raise

    async def get_scan(self, scan_id: str) -> Optional[Dict[str, Any]]:
        # 轮询只读单行批次状态，读完立即 rollback 释放 WAL 快照。
        try:
            result = await self.db.execute(select(OrphanScanResult).where(OrphanScanResult.scan_id == scan_id))
            record = result.scalar_one_or_none()
            if record is None:
                await self.db.rollback()
                return None
            payload = record.to_dict()
            payload["task_id"] = str(record.scan_id)
            await self.db.rollback()
            return payload
        except Exception:
            await self.db.rollback()
            raise

    async def queued_scan_ids(self) -> list[str]:
        result = await self.db.execute(
            select(OrphanScanResult.scan_id)
            .where(OrphanScanResult.status == "queued")
            .order_by(OrphanScanResult.scan_time.asc(), OrphanScanResult.scan_id.asc())
        )
        return [str(scan_id) for scan_id in result.scalars().all()]

    async def review_guardrail(
        self,
        *,
        scan_id: str,
        operator: str,
        note: str,
    ) -> Dict[str, Any]:
        """在路径映射和孤儿样本均由调用方确认后解锁超护栏扫描。"""
        reviewed_at = datetime.utcnow()
        try:
            async with admission_controller.db_write_scope():
                # 最新性判定和复核写入处于同一治理短事务，避免新扫描在两步之间
                # 插入后仍错误解锁旧批次。
                latest_result = await self.db.execute(
                    select(OrphanScanResult)
                    .order_by(
                        OrphanScanResult.scan_time.desc(),
                        OrphanScanResult.created_at.desc(),
                        OrphanScanResult.scan_id.desc(),
                    )
                    .limit(1)
                )
                latest = latest_result.scalar_one_or_none()
                if latest is None or str(latest.scan_id) != scan_id:
                    raise ValueError("只能复核最新扫描批次")
                if latest.status != "completed":
                    raise ValueError("扫描尚未成功完成，不能复核清理护栏")
                if not bool(latest.cleanup_review_required):
                    raise ValueError("该扫描未触发超量护栏，无需复核")
                await self.db.execute(
                    update(OrphanScanResult)
                    .where(OrphanScanResult.scan_id == scan_id)
                    .values(
                        cleanup_reviewed_at=reviewed_at,
                        cleanup_reviewed_by=operator,
                        cleanup_review_note=note[:2000],
                    )
                )
                await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        payload = latest.to_dict()
        payload.update(
            {
                "task_id": scan_id,
                "cleanup_reviewed_at": reviewed_at.isoformat(),
                "cleanup_reviewed_by": operator,
                "cleanup_review_note": note[:2000],
            }
        )
        return payload


class OrphanScanDispatcher:
    """进程内调度持久化扫描任务；跨进程互斥由孤儿维护租约保证。"""

    def __init__(self, app: Any, session_factory: Any = AsyncSessionLocal):
        self.app = app
        self.session_factory = session_factory
        self._tasks: Dict[str, asyncio.Task[Any]] = {}
        self._serial_lock = asyncio.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def submit(self, scan_id: str) -> bool:
        if self._closed:
            raise RuntimeError("孤儿扫描调度器已关闭")
        existing = self._tasks.get(scan_id)
        if existing is not None and not existing.done():
            return False
        task = asyncio.create_task(self.execute_scan(scan_id), name=f"orphan-scan-{scan_id}")
        self._tasks[scan_id] = task
        task.add_done_callback(lambda done: self._task_done(scan_id, done))
        return True

    def _task_done(self, scan_id: str, task: asyncio.Task[Any]) -> None:
        self._tasks.pop(scan_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "[孤儿扫描任务] 未捕获异常 scan_id=%s: %s",
                scan_id,
                error,
                exc_info=(type(error), error, error.__traceback__),
            )

    async def recover_pending_scans(self) -> int:
        async with self.session_factory() as db:
            scan_ids = await OrphanScanJobService(db).queued_scan_ids()
        for scan_id in scan_ids:
            self.submit(scan_id)
        return len(scan_ids)

    async def execute_scan(self, scan_id: str) -> None:
        from app.services.orphan_scanner import OrphanScanner

        async with self._serial_lock:
            try:
                await self._wait_for_store(scan_id)
            except RuntimeError:
                # _wait_for_store 已把持久化任务标记为 failed；让后台任务正常
                # 收口，避免 done callback 再记录一条“未捕获异常”噪音。
                return
            async with self.session_factory() as db:
                record_result = await db.execute(select(OrphanScanResult).where(OrphanScanResult.scan_id == scan_id))
                record = record_result.scalar_one_or_none()
                if record is None or record.status != "queued":
                    return
                scan_type = str(record.scan_type)
                operator = str(record.operator or "system")

            # 清理/隔离任务短时占用维护租约时保持 queued，并在后台重试；请求已返回。
            lease_handle = None
            for _attempt in range(60):
                try:
                    async with orphan_maintenance_scope("scan") as acquired_lease:
                        lease_handle = acquired_lease
                        result = await OrphanScanner(
                            app=self.app,
                            lease_handle=lease_handle,
                            async_session_factory=self.session_factory,
                        ).scan(
                            scan_type=scan_type,
                            operator=operator,
                            scan_id=scan_id,
                            create_record=False,
                        )
                        break
                except OrphanLeaseBusyError:
                    await asyncio.sleep(5)
            else:
                await self._mark_failed(scan_id, "等待孤儿维护租约超时")
                result = {"scan_id": scan_id, "status": "failed", "error": "等待孤儿维护租约超时"}

            await self._audit_result(result, scan_type=scan_type, operator=operator)

            # 定时扫描成功后才进入自动清理；超护栏批次被共用门禁明确拒绝。
            if scan_type == "scheduled" and result.get("status") == "completed":
                try:
                    from app.services.orphan_file_service import OrphanFileService

                    async with self.session_factory() as db:
                        await OrphanFileService(db).auto_cleanup_expired(
                            days_threshold=settings.ORPHAN_AUTO_CLEANUP_DAYS,
                            operator="system",
                            scan_id=scan_id,
                            store=getattr(getattr(self.app, "state", None), "store", None),
                        )
                except Exception as exc:
                    logger.error(
                        "[孤儿扫描任务] 定时扫描后自动清理失败 scan_id=%s: %s",
                        scan_id,
                        exc,
                        exc_info=True,
                    )

    async def _wait_for_store(self, scan_id: str, timeout_seconds: float = 60.0) -> None:
        """下载器缓存可能仍在 lifespan 后台初始化；保持 queued 等待而非误报失败。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            if getattr(getattr(self.app, "state", None), "store", None) is not None:
                return
            await asyncio.sleep(0.1)
        await self._mark_failed(scan_id, "下载器共享连接缓存初始化超时")
        raise RuntimeError("下载器共享连接缓存尚未初始化，孤儿扫描无法安全执行")

    async def _mark_failed(self, scan_id: str, reason: str) -> None:
        async with self.session_factory() as db:
            try:
                async with admission_controller.db_write_scope():
                    await db.execute(
                        update(OrphanScanResult)
                        .where(OrphanScanResult.scan_id == scan_id)
                        .values(status="failed", error_message=reason[:1000])
                    )
                    await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def _audit_result(self, result: Dict[str, Any], *, scan_type: str, operator: str) -> None:
        try:
            from app.services.audit_service import AuditLogService

            async with self.session_factory() as db:
                await AuditLogService(db).log_operation(
                    operation_type=AuditOperationType.ORPHAN_SCAN.value,
                    operator=operator,
                    operation_detail={
                        "scan_id": result.get("scan_id"),
                        "scan_type": scan_type,
                        "total_orphans": result.get("total_orphans", 0),
                        "total_paths_scanned": result.get("total_paths_scanned", 0),
                        "total_paths_skipped": result.get("total_paths_skipped", 0),
                        "warnings": result.get("warnings", []),
                        "status": result.get("status"),
                    },
                    operation_result=(
                        AuditOperationResult.SUCCESS
                        if result.get("status") == "completed"
                        else AuditOperationResult.FAILED
                    ),
                )
        except Exception as exc:
            logger.warning("[孤儿扫描任务] 审计日志记录失败: %s", exc)

    async def shutdown(self) -> None:
        self._closed = True
        tasks: Set[asyncio.Task[Any]] = {task for task in self._tasks.values() if not task.done()}
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


def get_orphan_scan_dispatcher(app: Any) -> OrphanScanDispatcher:
    dispatcher = getattr(getattr(app, "state", None), "orphan_scan_dispatcher", None)
    if dispatcher is None or dispatcher.closed:
        dispatcher = OrphanScanDispatcher(app)
        app.state.orphan_scan_dispatcher = dispatcher
    return dispatcher
