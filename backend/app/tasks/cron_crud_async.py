"""
定时任务异步CRUD操作模块

提供完全异步的数据库操作，避免阻塞事件循环，
确保定时任务执行时不会影响前端API响应性能。

作者: btpManager开发团队
创建时间: 2025-01-31
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, desc, func, select
from app.core.database_result import DatabaseResult
from app.tasks.cron_models import CronTask
from app.tasks.models import TaskLogs
import logging

logger = logging.getLogger(__name__)


class AsyncCronTaskCRUD:
    """定时任务异步CRUD操作类"""

    @staticmethod
    async def get_enabled_tasks(db: AsyncSession) -> DatabaseResult:
        """
        异步获取所有启用的定时任务

        Args:
            db: 异步数据库会话

        Returns:
            DatabaseResult: 包含任务列表的数据库结果对象
        """
        try:
            stmt = select(CronTask).where(
                and_(
                    CronTask.enabled == True,
                    CronTask.dr == 0
                )
            )
            result = await db.execute(stmt)
            tasks = result.scalars().all()

            task_list = [task.to_dict() for task in tasks]
            logger.debug(f"异步获取启用任务成功，共 {len(task_list)} 个")

            return DatabaseResult.success_result(task_list)

        except Exception as e:
            logger.error(f"异步获取启用任务失败: {str(e)}")
            return DatabaseResult.failure_result(f"获取启用任务失败: {str(e)}")

    @staticmethod
    async def get_cron_task_by_id(db: AsyncSession, task_id: int) -> DatabaseResult:
        """
        异步根据ID获取定时任务

        Args:
            db: 异步数据库会话
            task_id: 任务ID

        Returns:
            DatabaseResult: 包含任务信息的数据库结果对象
        """
        try:
            stmt = select(CronTask).where(
                and_(
                    CronTask.task_id == task_id,
                    CronTask.dr == 0
                )
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()

            if not task:
                logger.warning(f"任务ID {task_id} 不存在")
                return DatabaseResult.not_found("定时任务不存在")

            logger.debug(f"异步获取任务成功: {task.task_name} (ID: {task_id})")
            return DatabaseResult.success_result(task.to_dict())

        except Exception as e:
            logger.error(f"异步获取定时任务失败 (ID: {task_id}): {str(e)}")
            return DatabaseResult.failure_result(f"获取定时任务失败: {str(e)}")

    @staticmethod
    async def update_task_status(
        db: AsyncSession,
        task_id: int,
        status: int
    ) -> DatabaseResult:
        """
        异步更新任务状态

        Args:
            db: 异步数据库会话
            task_id: 任务ID
            status: 任务状态 (0:等待运行, 1:运行中, 2:空闲)

        Returns:
            DatabaseResult: 更新结果的数据库结果对象
        """
        try:
            stmt = select(CronTask).where(
                and_(
                    CronTask.task_id == task_id,
                    CronTask.dr == 0
                )
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()

            if not task:
                logger.warning(f"更新状态失败：任务ID {task_id} 不存在")
                return DatabaseResult.not_found("定时任务不存在")

            task.task_status = status
            task.update_time = datetime.now()

            await db.commit()

            logger.debug(f"异步更新任务状态成功: {task.task_name} (ID: {task_id}, 状态: {status})")
            return DatabaseResult.success_result(task.to_dict())

        except Exception as e:
            await db.rollback()
            logger.error(f"异步更新任务状态失败 (ID: {task_id}): {str(e)}")
            return DatabaseResult.failure_result(f"更新任务状态失败: {str(e)}")

    @staticmethod
    async def update_task_start_time(
        db: AsyncSession,
        task_id: int,
        start_time: datetime
    ) -> DatabaseResult:
        """
        异步更新任务开始执行时间

        Args:
            db: 异步数据库会话
            task_id: 任务ID
            start_time: 开始执行时间

        Returns:
            DatabaseResult: 更新结果的数据库结果对象
        """
        try:
            # ✅ 修复：添加 dr==0 检查，只更新未删除的任务
            stmt = select(CronTask).where(
                and_(
                    CronTask.task_id == task_id,
                    CronTask.dr == 0  # 只查询未删除的任务
                )
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()

            if task:
                task.last_execute_time = start_time
                await db.commit()
                logger.debug(f"异步更新任务开始时间成功: {task_id}, 时间: {start_time}")
                return DatabaseResult.success_result(True)

            logger.warning(f"更新开始时间失败：任务ID {task_id} 不存在")
            return DatabaseResult.failure_result("任务不存在")

        except Exception as e:
            await db.rollback()
            logger.error(f"异步更新任务开始时间失败 (ID: {task_id}): {str(e)}")
            return DatabaseResult.failure_result(f"更新任务开始时间失败: {str(e)}")

    @staticmethod
    async def update_task_execution_duration(
        db: AsyncSession,
        task_id: int,
        duration: int
    ) -> DatabaseResult:
        """
        异步更新任务执行持续时间

        Args:
            db: 异步数据库会话
            task_id: 任务ID
            duration: 执行持续时间（秒）

        Returns:
            DatabaseResult: 更新结果的数据库结果对象
        """
        try:
            # ✅ 修复：添加 dr==0 检查，只更新未删除的任务
            stmt = select(CronTask).where(
                and_(
                    CronTask.task_id == task_id,
                    CronTask.dr == 0  # 只查询未删除的任务
                )
            )
            result = await db.execute(stmt)
            task = result.scalar_one_or_none()

            if task:
                task.last_execute_duration = duration
                await db.commit()
                logger.debug(f"异步更新任务执行持续时间成功: {task_id}, 持续时间: {duration}秒")
                return DatabaseResult.success_result(True)

            logger.warning(f"更新执行持续时间失败：任务ID {task_id} 不存在")
            return DatabaseResult.failure_result("任务不存在")

        except Exception as e:
            await db.rollback()
            logger.error(f"异步更新任务执行持续时间失败 (ID: {task_id}): {str(e)}")
            return DatabaseResult.failure_result(f"更新任务执行持续时间失败: {str(e)}")


class AsyncTaskLogsCRUD:
    """任务日志异步CRUD操作类"""

    @staticmethod
    async def create_task_log(db: AsyncSession, log_data: Dict[str, Any]) -> DatabaseResult:
        """
        异步创建任务日志

        Args:
            db: 异步数据库会话
            log_data: 日志数据字典

        Returns:
            DatabaseResult: 创建结果的数据库结果对象
        """
        try:
            task_log = TaskLogs(
                task_id=log_data.get("task_id"),
                task_name=log_data.get("task_name"),
                task_type=log_data.get("task_type"),
                start_time=log_data.get("start_time"),
                end_time=log_data.get("end_time"),
                duration=log_data.get("duration"),
                success=log_data.get("success"),
                log_detail=log_data.get("log_detail")
            )

            db.add(task_log)
            await db.commit()
            await db.refresh(task_log)

            logger.debug(f"异步创建任务日志成功: {task_log.task_name} (ID: {task_log.task_id})")
            return DatabaseResult.success_result(task_log.to_dict())

        except Exception as e:
            await db.rollback()
            logger.error(f"异步创建任务日志失败: {str(e)}")
            return DatabaseResult.failure_result(f"创建任务日志失败: {str(e)}")
