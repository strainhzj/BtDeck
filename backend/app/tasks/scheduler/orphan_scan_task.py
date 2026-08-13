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
from typing import Any, Dict, Optional

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
    version = "1.0.0"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行扫描 + 自动清理。

        Args:
            **kwargs: 包含 app=FastAPI 实例

        Returns:
            任务执行结果字典
        """
        app = kwargs.get("app")
        start_time = datetime.utcnow()

        result: Dict[str, Any] = {
            "task_name": self.name,
            "execution_time": start_time.isoformat(),
            "status": "running",
        }

        try:
            # 1. 提交持久化后台扫描；完成后的自动清理由扫描调度器统一串接。
            from app.services.orphan_scan_job_service import (
                OrphanScanJobService,
                get_orphan_scan_dispatcher,
            )

            if not settings.ORPHAN_SCAN_ENABLED:
                logger.info(f"[{self.name}] 定时扫描已关闭（ORPHAN_SCAN_ENABLED=False），跳过")
                result.update({"status": "skipped", "message": "定时扫描已关闭"})
                return result

            logger.info(f"[{self.name}] 开始扫描孤儿文件")
            async with AsyncSessionLocal() as scan_db:
                scan_result = await OrphanScanJobService(scan_db).submit_scan(scan_type="scheduled", operator="system")
            if app is None:
                raise RuntimeError("定时孤儿扫描缺少 FastAPI app，无法提交后台任务")
            get_orphan_scan_dispatcher(app).submit(str(scan_result["scan_id"]))
            result["scan_result"] = scan_result
            result["status"] = "success"
            result["message"] = (
                f"孤儿扫描后台任务已提交（scan_id={scan_result['scan_id']}，" f"status={scan_result['status']}）"
            )

            logger.info(f"[{self.name}] 执行完成: {result.get('message')}")

        except Exception as e:
            logger.error(f"[{self.name}] 执行失败: {e}", exc_info=True)
            result.update({"status": "error", "message": f"执行失败: {e}"})

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
