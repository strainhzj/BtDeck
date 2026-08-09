"""
内存任务管理器
用于管理异步批量删除任务，提供任务的创建、查询、更新和状态管理功能。
"""

import asyncio
import json
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, FrozenSet, List, Optional, Set
from enum import Enum
from dataclasses import dataclass, field

from sqlalchemy import String, cast as sql_cast, func, literal, select


class TaskStatus(str, Enum):
    """任务状态枚举"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    PARTIAL = "partial"  # 部分成功（有部分失败）


@dataclass
class DeletionTask:
    """删除任务数据类"""

    task_id: str  # 任务ID
    torrent_info_ids: List[str]  # 要删除的种子ID列表
    delete_level: int  # 删除等级
    operator: str  # 操作者
    status: TaskStatus = TaskStatus.PENDING  # 任务状态
    total_count: int = 0  # 总数量
    success_count: int = 0  # 成功数量
    failed_count: int = 0  # 失败数量
    error_message: Optional[str] = None  # 错误信息
    results: List[Dict[str, Any]] = field(default_factory=list)  # 删除结果列表
    failed_items: List[Dict[str, Any]] = field(default_factory=list)  # 失败项列表
    skipped_info_ids: List[str] = field(default_factory=list)  # 提交时已被其他活动任务占用
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    started_at: Optional[datetime] = None  # 开始时间
    completed_at: Optional[datetime] = None  # 完成时间


@dataclass(frozen=True)
class DeletionTaskSubmission:
    """原子占用后的任务提交结果。"""

    task_id: Optional[str]
    accepted_info_ids: List[str]
    skipped_info_ids: List[str]

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_info_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_info_ids)

    @property
    def requested_count(self) -> int:
        return self.accepted_count + self.skipped_count


class DeletionTaskManager:
    """
    删除任务管理器（单例模式）
    使用内存存储任务，定期清理过期任务
    """

    _instance: Optional["DeletionTaskManager"] = None
    _lock: asyncio.Lock

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._tasks: Dict[str, DeletionTask] = {}
        self._lock = asyncio.Lock()
        # 同步列表查询不能等待 asyncio.Lock，单独维护线程安全的活动 ID 快照。
        self._active_torrent_info_ids: Set[str] = set()
        self._active_ids_lock = threading.RLock()
        self._cleanup_task: Optional[asyncio.Task] = None

        # 启动后台清理任务
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """启动后台清理任务，每60秒清理一次过期任务"""

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(60)
                    await self._cleanup_expired_tasks()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"清理过期任务失败: {e}")

        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(cleanup_loop())
        except RuntimeError:
            # 如果还没有事件循环，稍后在初始化时创建
            pass

    @staticmethod
    def _normalize_info_ids(torrent_info_ids: List[str]) -> List[str]:
        return list(
            dict.fromkeys(
                str(info_id).strip()
                for info_id in torrent_info_ids
                if info_id is not None and str(info_id).strip()
            )
        )

    def get_active_torrent_info_ids_snapshot(self) -> FrozenSet[str]:
        """返回活动删除任务占用的种子 ID，不暴露内部可变集合。"""
        with self._active_ids_lock:
            return frozenset(self._active_torrent_info_ids)

    async def create_task_reserving(
        self,
        torrent_info_ids: List[str],
        delete_level: int,
        operator: str,
    ) -> DeletionTaskSubmission:
        """原子过滤已占用 ID，并只为未占用项创建任务。"""
        normalized_ids = self._normalize_info_ids(torrent_info_ids)
        if not normalized_ids:
            raise ValueError("至少需要一个有效的种子 ID")

        async with self._lock:
            with self._active_ids_lock:
                skipped_ids = [
                    info_id for info_id in normalized_ids if info_id in self._active_torrent_info_ids
                ]
                accepted_ids = [
                    info_id for info_id in normalized_ids if info_id not in self._active_torrent_info_ids
                ]
                if not accepted_ids:
                    return DeletionTaskSubmission(
                        task_id=None,
                        accepted_info_ids=[],
                        skipped_info_ids=skipped_ids,
                    )
                self._active_torrent_info_ids.update(accepted_ids)

            task_id = str(uuid.uuid4())
            task = DeletionTask(
                task_id=task_id,
                torrent_info_ids=accepted_ids,
                delete_level=delete_level,
                operator=operator,
                total_count=len(accepted_ids),
                skipped_info_ids=skipped_ids,
            )
            self._tasks[task_id] = task
            return DeletionTaskSubmission(
                task_id=task_id,
                accepted_info_ids=list(accepted_ids),
                skipped_info_ids=list(skipped_ids),
            )

    async def create_task(self, torrent_info_ids: List[str], delete_level: int, operator: str) -> str:
        """
        创建新的删除任务

        Args:
            torrent_info_ids: 种子信息ID列表
            delete_level: 删除等级（1-4）
            operator: 操作者

        Returns:
            任务ID
        """
        submission = await self.create_task_reserving(torrent_info_ids, delete_level, operator)
        if submission.task_id is None:
            raise ValueError("所选种子均已在其他删除任务中处理")
        return submission.task_id

    async def get_task(self, task_id: str) -> Optional[DeletionTask]:
        """
        获取任务信息

        Args:
            task_id: 任务ID

        Returns:
            任务对象，如果不存在返回None
        """
        async with self._lock:
            return self._tasks.get(task_id)

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        success_count: Optional[int] = None,
        failed_count: Optional[int] = None,
        error_message: Optional[str] = None,
        results: Optional[List[Dict[str, Any]]] = None,
        failed_items: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
            success_count: 成功数量
            failed_count: 失败数量
            error_message: 错误信息
            results: 结果列表
            failed_items: 失败项列表

        Returns:
            是否更新成功
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            task.status = status

            if success_count is not None:
                task.success_count = success_count
            if failed_count is not None:
                task.failed_count = failed_count
            if error_message is not None:
                task.error_message = error_message
            if results is not None:
                task.results = results
            if failed_items is not None:
                task.failed_items = failed_items

            # 更新时间戳
            if status == TaskStatus.RUNNING and task.started_at is None:
                task.started_at = datetime.now()
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.PARTIAL]:
                if task.completed_at is None:
                    task.completed_at = datetime.now()
                with self._active_ids_lock:
                    self._active_torrent_info_ids.difference_update(task.torrent_info_ids)

            return True

    async def _cleanup_expired_tasks(self):
        """清理超过1小时的任务"""
        async with self._lock:
            now = datetime.now()
            expired_tasks = []
            for task_id, task in self._tasks.items():
                # 如果任务已完成且超过1小时，或者任务创建超过24小时未完成
                if (task.completed_at and (now - task.completed_at) > timedelta(hours=1)) or (
                    now - task.created_at
                ) > timedelta(hours=24):
                    expired_tasks.append(task_id)

            for task_id in expired_tasks:
                task = self._tasks[task_id]
                with self._active_ids_lock:
                    self._active_torrent_info_ids.difference_update(task.torrent_info_ids)
                del self._tasks[task_id]

            if expired_tasks:
                print(f"清理了 {len(expired_tasks)} 个过期任务")

    async def get_all_tasks(self) -> List[DeletionTask]:
        """
        获取所有任务（用于调试）

        Returns:
            任务列表
        """
        async with self._lock:
            return list(self._tasks.values())


# 全局实例
_manager: Optional[DeletionTaskManager] = None


def get_deletion_task_manager() -> DeletionTaskManager:
    """
    获取任务管理器单例

    Returns:
        任务管理器实例
    """
    global _manager
    if _manager is None:
        _manager = DeletionTaskManager()
    return _manager


def get_active_deletion_info_ids_snapshot() -> FrozenSet[str]:
    """供同步查询读取活动删除占用；未初始化管理器时不产生副作用。"""
    if _manager is None:
        return frozenset()
    return _manager.get_active_torrent_info_ids_snapshot()


def build_active_deletion_exclusion(column: Any) -> Optional[Any]:
    """构造活动删除 ID 排除条件，单 JSON 绑定避免 SQLite 变量上限。"""
    active_ids = get_active_deletion_info_ids_snapshot()
    if not active_ids:
        return None

    payload = json.dumps(sorted(active_ids), ensure_ascii=False)
    values = func.json_each(literal(payload)).table_valued("value").alias("active_deletion_ids")
    active_ids_query = select(sql_cast(values.c.value, String))
    return column.notin_(active_ids_query)
