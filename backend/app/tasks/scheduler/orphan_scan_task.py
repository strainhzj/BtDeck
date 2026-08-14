# -*- coding: utf-8 -*-
"""
孤儿文件扫描清理定时任务

每周日凌晨 2 点执行：
1. 扫描所有下载器磁盘路径，发现孤儿文件
2. 自动清理超过 ORPHAN_AUTO_CLEANUP_DAYS 天的孤儿文件

治理合规：
- 任务经 task_profiles 登记 heavy_sync，受 TaskAdmissionController 背压
- 扫描器内部：文件系统遍历经 to_thread，下载器 API 经 call_downloader_api(SYNC)
- 自动清理的 DB commit 经 db_write_scope 串行化
- 审计日志记录每次自动清理

@file: orphan_scan_task.py
@time: 2026-07-10
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.core.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class OrphanScanTask:
    """孤儿文件扫描清理定时任务（每周一次）

    cron: 0 2 * * 0（每周日凌晨 2 点）
    task_code: orphan_scan_cleanup
    """

    # 任务元数据
    name = "孤儿文件扫描清理任务"
    description = "每周扫描孤儿文件，自动清理超过 30 天的孤儿文件"
    version = "1.1.0"

    def __init__(self) -> None:
        # CronTaskExecutor 注入的回调只收集本次执行的阶段日志，最终由同一条
        # task_logs 记录落库；不会另起一套孤儿任务日志表。
        self._execution_logger: Optional[Callable[[str], None]] = None
        self._wait_timeout_seconds: Optional[float] = None

    def set_execution_context(
        self,
        *,
        execution_logger: Optional[Callable[[str], None]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        """接收 Cron 执行上下文（手动/API 调用不设置）。"""
        self._execution_logger = execution_logger
        self._wait_timeout_seconds = timeout_seconds

    def _log_phase(self, message: str) -> None:
        logger.info("[%s] %s", self.name, message)
        if self._execution_logger is not None:
            try:
                self._execution_logger(message)
            except Exception:  # pragma: no cover - 日志回调不能影响扫描安全链路
                logger.debug("记录孤儿扫描 Cron 阶段日志失败", exc_info=True)

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行扫描 + 自动清理，并等待同一 dispatcher 的终态。

        手动/API 入口仍然只提交 queued；只有 Cron 调用该类时才等待扫描和
        自动清理均结束，避免调度器先把“提交成功”误记为业务完成。
        """
        app = kwargs.get("app")
        start_time = datetime.utcnow()
        execution_log: List[str] = []

        def record_phase(message: str) -> None:
            execution_log.append(message)
            self._log_phase(message)

        result: Dict[str, Any] = {
            "task_name": self.name,
            "execution_time": start_time.isoformat(),
            "status": "running",
            "execution_log": execution_log,
        }

        try:
            # 1. 提交持久化后台扫描；完成后的自动清理由扫描调度器统一串接。
            from app.services.orphan_scan_job_service import (
                OrphanScanJobService,
                get_orphan_scan_dispatcher,
            )

            if not settings.ORPHAN_SCAN_ENABLED:
                record_phase("定时扫描已关闭（ORPHAN_SCAN_ENABLED=False），跳过")
                result.update(
                    {
                        "status": "skipped",
                        "skipped": True,
                        "outcome": "skipped",
                        "skip_reason": "outside_budget",
                        "message": "定时扫描已关闭",
                    }
                )
                return result

            record_phase("创建定时扫描批次")
            async with AsyncSessionLocal() as scan_db:
                scan_result = await OrphanScanJobService(scan_db).submit_scan(scan_type="scheduled", operator="system")
            if app is None:
                raise RuntimeError("定时孤儿扫描缺少 FastAPI app，无法提交后台任务")
            scan_id = str(scan_result["scan_id"])
            dispatcher = get_orphan_scan_dispatcher(app)
            accepted = dispatcher.submit(scan_id)
            record_phase(
                f"扫描已提交 scan_id={scan_id} status={scan_result.get('status')} "
                f"dispatcher={'started' if accepted else 'already_running'}"
            )

            # 只有定时任务等待同一个 dispatcher 的扫描+清理任务；API 手动扫描
            # 不进入此方法，继续立即返回 queued。
            completion = None
            wait_for_completion = getattr(dispatcher, "wait_for_completion", None)
            if callable(wait_for_completion):
                if self._wait_timeout_seconds is None:
                    maybe_completion = wait_for_completion(scan_id)
                else:
                    maybe_completion = wait_for_completion(
                        scan_id,
                        timeout_seconds=self._wait_timeout_seconds,
                    )
                # 兼容测试替身/旧 dispatcher：真实实现是协程；非 awaitable 不得
                # 把 MagicMock 当成终态写入 Cron 日志。
                import inspect

                if inspect.isawaitable(maybe_completion):
                    completion = await maybe_completion

            if not isinstance(completion, dict):
                # 真实 dispatcher 必须提供 wait_for_completion；这里仅保留清晰的
                # 失败结果，避免再次把 queued 误记成 success。
                raise RuntimeError("孤儿扫描 dispatcher 未提供可等待的终态接口")

            scan_terminal = completion.get("scan_result") or {}
            if isinstance(scan_terminal, dict):
                scan_terminal.setdefault("scan_id", scan_id)
                scan_terminal.setdefault("task_id", scan_id)
            scan_status = str(scan_terminal.get("status") or completion.get("status") or "unknown")
            cleanup_result = completion.get("cleanup_result")
            result["scan_submission"] = scan_result
            result["scan_result"] = scan_terminal
            result["cleanup_result"] = cleanup_result
            result["dispatcher_result"] = completion
            record_phase(f"扫描终态 scan_id={scan_id} status={scan_status}")

            if scan_status != "completed":
                result.update(
                    {
                        "status": "error",
                        "success": False,
                        "outcome": "failed",
                        "message": completion.get("error") or f"孤儿扫描未完成（status={scan_status}）",
                    }
                )
                result["log_detail"] = "\n".join(execution_log)
                return result

            if cleanup_result is None:
                result.update(
                    {
                        "status": "partial",
                        "success": True,
                        "outcome": "partial",
                        "message": "扫描已完成，但当前进程无法确认自动清理终态",
                    }
                )
                record_phase("扫描已完成，但未能确认自动清理终态")
                result["log_detail"] = "\n".join(execution_log)
                return result

            record_phase(
                "清理终态 "
                f"rejected={bool(cleanup_result.get('rejected'))} "
                f"quarantined={cleanup_result.get('quarantined_count', 0)} "
                f"failed={cleanup_result.get('failed_count', 0)}"
            )
            if cleanup_result.get("rejected"):
                result.update(
                    {
                        "status": "skipped",
                        "success": True,
                        "skipped": True,
                        "outcome": "skipped",
                        "skip_reason": "outside_budget",
                        "message": cleanup_result.get("error") or "自动清理被安全门禁拒绝，等待人工复核",
                    }
                )
            elif int(cleanup_result.get("failed_count", 0) or 0) > 0:
                result.update(
                    {
                        "status": "partial",
                        "success": True,
                        "outcome": "partial",
                        "message": "扫描完成，自动清理部分失败",
                    }
                )
            else:
                result.update(
                    {
                        "status": "success",
                        "success": True,
                        "outcome": "success",
                        "message": "扫描与自动清理已完成",
                    }
                )

            result["log_detail"] = "\n".join(execution_log)

        except Exception as e:
            logger.error(f"[{self.name}] 执行失败: {e}", exc_info=True)
            record_phase(f"执行失败：{e}")
            result.update(
                {
                    "status": "error",
                    "success": False,
                    "outcome": "failed",
                    "message": f"执行失败: {e}",
                    "log_detail": "\n".join(execution_log),
                }
            )

        return result

    async def _auto_cleanup_expired(self, scan_id: Optional[str] = None, store: Any = None) -> Dict[str, Any]:
        """自动清理超期孤儿文件（独立 session）

        Args:
            scan_id: 本次扫描 ID（必须传入，用于隔离区子目录命名）
        """
        from app.services.orphan_file_service import OrphanFileService

        async with AsyncSessionLocal() as db:
            service = OrphanFileService(db)
            return await service.auto_cleanup_expired(
                days_threshold=settings.ORPHAN_AUTO_CLEANUP_DAYS,
                operator="system",
                scan_id=scan_id,
                store=store,
            )
