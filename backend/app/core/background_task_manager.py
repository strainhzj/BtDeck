"""
后台任务管理器

管理后台运行的任务状态，支持任务查询和并发控制。
使用内存存储，适用于单服务器部署场景。
"""

import asyncio
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"       # 待执行
    RUNNING = "running"       # 执行中
    SUCCESS = "success"       # 成功
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消


class BackgroundTask:
    """后台任务对象"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        downloader_id: str,
        downloader_nickname: str
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.downloader_id = downloader_id
        self.downloader_nickname = downloader_nickname
        self.status = TaskStatus.PENDING
        self.created_at = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.progress: int = 0  # 进度 0-100

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "downloader_id": self.downloader_id,
            "downloader_nickname": self.downloader_nickname,
            "status": self.status.value,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "finished_at": datetime.fromtimestamp(self.finished_at).isoformat() if self.finished_at else None,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "execution_time": round(self.finished_at - self.started_at, 2) if self.finished_at and self.started_at else None
        }


class BackgroundTaskManager:
    """后台任务管理器（单例模式）"""

    _instance: Optional['BackgroundTaskManager'] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._tasks: Dict[str, BackgroundTask] = {}
        self._downloader_tasks: Dict[str, str] = {}  # downloader_id -> task_id
        self._max_concurrent_tasks = 3
        self._semaphore = asyncio.Semaphore(self._max_concurrent_tasks)
        self._initialized = True

        logger.info(f"后台任务管理器初始化完成，最大并发数: {self._max_concurrent_tasks}")

    def generate_task_id(self, task_type: str) -> str:
        """生成任务ID"""
        return f"{task_type}_{uuid.uuid4().hex[:12]}"

    async def create_task(
        self,
        task_type: str,
        downloader_id: str,
        downloader_nickname: str
    ) -> BackgroundTask:
        """创建新任务"""
        task_id = self.generate_task_id(task_type)
        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            downloader_id=downloader_id,
            downloader_nickname=downloader_nickname
        )

        async with self._lock:
            self._tasks[task_id] = task
            self._downloader_tasks[downloader_id] = task_id

        logger.info(f"创建任务: {task_id} ({task_type}) - {downloader_nickname}")
        return task

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """获取任务信息"""
        return self._tasks.get(task_id)

    def get_downloader_task(self, downloader_id: str) -> Optional[BackgroundTask]:
        """获取下载器的当前任务"""
        task_id = self._downloader_tasks.get(downloader_id)
        if task_id:
            return self._tasks.get(task_id)
        return None

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        progress: Optional[int] = None
    ) -> bool:
        """更新任务状态"""
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"任务不存在: {task_id}")
            return False

        task.status = status

        if status == TaskStatus.RUNNING and not task.started_at:
            task.started_at = time.time()
            logger.info(f"任务开始执行: {task_id}")

        if status in [TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.finished_at = time.time()
            logger.info(f"任务完成: {task_id} - 状态: {status.value}")

        if result is not None:
            task.result = result

        if error is not None:
            task.error = error

        if progress is not None:
            task.progress = max(0, min(100, progress))

        return True

    async def execute_task(
        self,
        task_id: str,
        coro
    ) -> Dict[str, Any]:
        """执行任务（带并发控制）"""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        async with self._semaphore:
            try:
                # 更新为运行中
                await self.update_task_status(task_id, TaskStatus.RUNNING)

                # 执行任务
                result = await coro

                # 更新为成功
                await self.update_task_status(
                    task_id,
                    TaskStatus.SUCCESS,
                    result=result
                )

                return result

            except Exception as e:
                # 更新为失败
                await self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    error=str(e)
                )
                logger.error(f"任务执行失败: {task_id} - {str(e)}", exc_info=True)
                raise

    async def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """清理旧任务（默认保留1小时）"""
        current_time = time.time()
        tasks_to_remove = []

        async with self._lock:
            for task_id, task in self._tasks.items():
                task_age = current_time - task.created_at
                if task_age > max_age_seconds:
                    tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                task = self._tasks.pop(task_id, None)
                if task:
                    self._downloader_tasks.pop(task.downloader_id, None)

            if tasks_to_remove:
                logger.info(f"清理了 {len(tasks_to_remove)} 个旧任务")

    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务（用于调试）"""
        return {
            task_id: task.to_dict()
            for task_id, task in self._tasks.items()
        }


# 全局任务管理器实例
task_manager = BackgroundTaskManager()
