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
from typing import Any, Coroutine, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态枚举"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class BackgroundTask:
    """后台任务对象"""

    def __init__(self, task_id: str, task_type: str, downloader_id: str, downloader_nickname: str):
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
            "execution_time": (
                round(self.finished_at - self.started_at, 2) if self.finished_at and self.started_at else None
            ),
        }


class BackgroundTaskManager:
    """后台任务管理器（单例模式）"""

    _instance: Optional["BackgroundTaskManager"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._tasks: Dict[str, BackgroundTask] = {}
        self._downloader_tasks: Dict[str, str] = {}  # downloader_id -> task_id
        # 保留 asyncio.Task 强引用，避免 fire-and-forget 任务在执行期间被垃圾回收，
        # 同时让完成回调可以统一消费未捕获异常。
        self._runner_tasks: Dict[str, asyncio.Task[Any]] = {}
        self._max_concurrent_tasks = 3
        self._semaphore = asyncio.Semaphore(self._max_concurrent_tasks)
        self._initialized = True

        logger.info(f"后台任务管理器初始化完成，最大并发数: {self._max_concurrent_tasks}")

    def generate_task_id(self, task_type: str) -> str:
        """生成任务ID"""
        return f"{task_type}_{uuid.uuid4().hex[:12]}"

    async def create_task(self, task_type: str, downloader_id: str, downloader_nickname: str) -> BackgroundTask:
        """创建新任务"""
        task_id = self.generate_task_id(task_type)
        task = BackgroundTask(
            task_id=task_id, task_type=task_type, downloader_id=downloader_id, downloader_nickname=downloader_nickname
        )

        async with self._lock:
            self._tasks[task_id] = task
            self._downloader_tasks[downloader_id] = task_id

        logger.info(f"创建任务: {task_id} ({task_type}) - {downloader_nickname}")
        return task

    async def create_task_if_idle(
        self,
        task_type: str,
        downloader_id: str,
        downloader_nickname: str,
    ) -> tuple[BackgroundTask, bool]:
        """仅在下载器没有待执行/运行中任务时原子创建任务。

        返回 ``(task, created)``。当 ``created`` 为 False 时，task 是当前活动
        任务；调用方不得再次调度执行体。检查与写入在同一把锁内完成，避免两个
        并发请求同时通过端点层的先查后建检查。
        """
        async with self._lock:
            existing_task_id = self._downloader_tasks.get(downloader_id)
            existing_task = self._tasks.get(existing_task_id) if existing_task_id else None
            if existing_task and existing_task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return existing_task, False

            task_id = self.generate_task_id(task_type)
            task = BackgroundTask(
                task_id=task_id,
                task_type=task_type,
                downloader_id=downloader_id,
                downloader_nickname=downloader_nickname,
            )
            self._tasks[task_id] = task
            self._downloader_tasks[downloader_id] = task_id

        logger.info(f"创建任务: {task_id} ({task_type}) - {downloader_nickname}")
        return task, True

    def start_task_runner(self, task_id: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """调度并保留后台执行体句柄，完成后自动释放并消费异常。"""
        if task_id not in self._tasks:
            raise ValueError(f"任务不存在: {task_id}")

        runner = asyncio.create_task(coro, name=f"background-task:{task_id}")
        self._runner_tasks[task_id] = runner
        runner.add_done_callback(lambda finished: self._handle_runner_done(task_id, finished))
        return runner

    def _handle_runner_done(self, task_id: str, runner: asyncio.Task[Any]) -> None:
        """释放后台句柄并确保异常不会成为未检索的 Task exception。"""
        if self._runner_tasks.get(task_id) is runner:
            self._runner_tasks.pop(task_id, None)

        try:
            runner.result()
        except asyncio.CancelledError:
            task = self._tasks.get(task_id)
            if task and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                task.error = "后台任务已取消"
            logger.info("后台任务执行体已取消: %s", task_id)
        except Exception:
            # 正常执行路径应由 execute_task/端点包装器记录失败；这里作为最后兜底，
            # 防止调度层异常被静默忽略。
            logger.exception("后台任务执行体异常: %s", task_id)

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
        progress: Optional[int] = None,
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

    async def execute_task(self, task_id: str, coro) -> Dict[str, Any]:
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

                # 协程正常返回不等于业务成功。同步协调器会以结构化结果返回
                # failed/cancelled；必须映射到真实终态，供 sync-status 与前端轮询使用。
                outcome = str(result.get("outcome") or "") if isinstance(result, dict) else ""
                result_status = str(result.get("status") or "") if isinstance(result, dict) else ""
                result_message = str(result.get("message") or "") if isinstance(result, dict) else ""

                if outcome == "cancelled":
                    terminal_status = TaskStatus.CANCELLED
                elif result_status in ("failed", "error"):
                    terminal_status = TaskStatus.FAILED
                else:
                    terminal_status = TaskStatus.SUCCESS

                await self.update_task_status(
                    task_id,
                    terminal_status,
                    result=result,
                    error=result_message if terminal_status != TaskStatus.SUCCESS else None,
                    progress=100 if terminal_status == TaskStatus.SUCCESS else None,
                )

                return result

            except Exception as e:
                # 更新为失败
                await self.update_task_status(task_id, TaskStatus.FAILED, error=str(e))
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
                if task_id in self._tasks:
                    removed = self._tasks.pop(task_id)
                    self._downloader_tasks.pop(removed.downloader_id, None)

            if tasks_to_remove:
                logger.info(f"清理了 {len(tasks_to_remove)} 个旧任务")

    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务（用于调试）"""
        return {task_id: task.to_dict() for task_id, task in self._tasks.items()}


# 全局任务管理器实例
task_manager = BackgroundTaskManager()
