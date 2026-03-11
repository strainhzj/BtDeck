# -*- coding: utf-8 -*-
"""
审计日志归档定时任务

定期将数据库中的审计日志导出到统一格式的日志文件，
用于长期保存和合规审计。

作者: btpManager Team
版本: v1.0
创建时间: 2026-02-14
最后更新: 2026-02-14
"""
import logging
from datetime import datetime, timedelta
from app.database import AsyncSessionLocal
from app.utils.audit_logger import export_audit_logs_from_db_to_file
from app.tasks.cron_models import CronTask

logger = logging.getLogger(__name__)


class AuditLogExportTask:
    """审计日志导出任务"""

    async def execute_daily_export(self, db_session):
        """
        执行每日审计日志导出

        导出前一天的审计日志到日志文件。

        Args:
            db_session: 数据库会话
        """
        try:
            # 计算导出时间范围（前一天的完整一天）
            now = datetime.now()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            end_time = start_time + timedelta(days=1)

            logger.info(f"开始导出审计日志: {start_time.date()} ~ {end_time.date()}")

            # 执行导出
            exported_count = await export_audit_logs_from_db_to_file(
                db_session=db_session,
                start_time=start_time,
                end_time=end_time,
                limit=10000  # 最多导出1万条
            )

            logger.info(f"审计日志导出完成: 共导出{exported_count}条记录")

        except Exception as e:
            logger.error(f"审计日志导出任务失败: {str(e)}", exc_info=True)

    async def execute_manual_export(
        self,
        db_session,
        days: int = 7,
        operation_type: str = None
    ):
        """
        手动执行审计日志导出

        Args:
            db_session: 数据库会话
            days: 导出最近N天的日志（默认7天）
            operation_type: 操作类型筛选（可选）
        """
        try:
            # 计算导出时间范围
            end_time = datetime.now()
            start_time = end_time - timedelta(days=days)

            logger.info(f"开始手动导出审计日志: 最近{days}天")

            # 执行导出
            exported_count = await export_audit_logs_from_db_to_file(
                db_session=db_session,
                operation_type=operation_type,
                start_time=start_time,
                end_time=end_time,
                limit=50000  # 手动导出允许更多条数
            )

            logger.info(f"手动审计日志导出完成: 共导出{exported_count}条记录")
            return exported_count

        except Exception as e:
            logger.error(f"手动审计日志导出失败: {str(e)}", exc_info=True)
            return 0


# 定时任务执行函数
async def audit_log_export_task():
    """定时任务入口函数"""
    try:
        async with AsyncSessionLocal() as db:
            task = AuditLogExportTask()
            await task.execute_daily_export(db)
    except Exception as e:
        logger.error(f"审计日志导出定时任务执行失败: {str(e)}", exc_info=True)


if __name__ == "__main__":
    # 手动测试导出功能
    import asyncio

    async def test_export():
        async with AsyncSessionLocal() as db:
            task = AuditLogExportTask()
            await task.execute_manual_export(db, days=1)

    asyncio.run(test_export())
