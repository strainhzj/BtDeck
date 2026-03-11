import time
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.tasks.models import TaskLogs


class TaskLogger:
    """任务日志记录器"""

    def __init__(self, task_name: str, task_type: Optional[int] = None):
        """
        初始化任务日志记录器

        Args:
            task_name: 任务名称
            task_type: 任务类型（0-shell脚本，1-cmd脚本，2-powershell脚本，3-python脚本，4-python内部类，5-清理回收站）
        """
        self.task_name = task_name
        self.task_type = task_type
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.log_details: list = []

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.start_time = datetime.now()
        self.log_details.append(f"Task '{self.task_name}' started at {self.start_time}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        self.end_time = datetime.now()
        duration = int((self.end_time - self.start_time).total_seconds())
        success = exc_type is None

        if exc_type:
            self.log_details.append(f"Task failed with exception: {exc_val}")
        else:
            self.log_details.append(f"Task completed successfully at {self.end_time}")

        # 记录到数据库
        await self._log_to_db(duration, success)

    def add_log(self, message: str):
        """添加日志信息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_details.append(f"[{timestamp}] {message}")

    async def _log_to_db(self, duration: int, success: bool):
        """将日志记录到数据库"""
        db = SessionLocal()
        try:
            log_detail = "\n".join(self.log_details)

            task_log = TaskLogs(
                task_name=self.task_name,
                task_type=self.task_type,
                start_time=self.start_time,
                end_time=self.end_time,
                duration=duration,
                success=success,
                log_detail=log_detail
            )

            db.add(task_log)
            db.commit()

        except Exception as e:
            print(f"Failed to log task to database: {e}")
            db.rollback()
        finally:
            db.close()


def log_task_execution(task_name: str):
    """装饰器：记录任务执行日志"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            async with TaskLogger(task_name) as logger:
                try:
                    logger.add_log(f"Starting execution of {func.__name__}")
                    result = await func(*args, **kwargs)
                    logger.add_log(f"Function {func.__name__} completed successfully")
                    return result
                except Exception as e:
                    logger.add_log(f"Function {func.__name__} failed: {str(e)}")
                    raise
        return wrapper
    return decorator


async def get_task_logs(
    task_name: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0
) -> Dict[str, Any]:
    """获取任务日志"""
    db = SessionLocal()
    try:
        query = db.query(TaskLogs)

        if task_name:
            query = query.filter(TaskLogs.task_name == task_name)

        if success is not None:
            query = query.filter(TaskLogs.success == success)

        total = query.count()
        logs = query.order_by(TaskLogs.start_time.desc()).offset(offset).limit(limit).all()

        return {
            "total": total,
            "logs": [log.to_dict() for log in logs]
        }

    finally:
        db.close()


async def get_task_statistics() -> Dict[str, Any]:
    """获取任务统计信息"""
    db = SessionLocal()
    try:
        # 总任务数
        total_tasks = db.query(TaskLogs).count()

        # 成功任务数
        successful_tasks = db.query(TaskLogs).filter(TaskLogs.success == True).count()

        # 失败任务数
        failed_tasks = db.query(TaskLogs).filter(TaskLogs.success == False).count()

        # 按任务名统计
        task_stats = db.query(
            TaskLogs.task_name,
            db.func.count(TaskLogs.log_id).label('total'),
            db.func.sum(db.func.case([(TaskLogs.success == True, 1)], else_=0)).label('success'),
            db.func.avg(TaskLogs.duration).label('avg_duration')
        ).group_by(TaskLogs.task_name).all()

        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": (successful_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            "task_breakdown": [
                {
                    "task_name": stat.task_name,
                    "total": stat.total,
                    "success": stat.success,
                    "success_rate": (stat.success / stat.total * 100) if stat.total > 0 else 0,
                    "avg_duration": round(stat.avg_duration, 2) if stat.avg_duration else 0
                }
                for stat in task_stats
            ]
        }

    finally:
        db.close()