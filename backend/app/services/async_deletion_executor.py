"""
异步批量删除执行器
在后台执行批量删除任务，支持超时处理、跳过失败种子、统计成功/失败数量。
"""
import asyncio
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import Request

from app.services.deletion_task_manager import get_deletion_task_manager, TaskStatus
from app.services.torrent_deletion_by_level import TorrentDeletionByLevelService


class AsyncDeletionExecutor:
    """
    异步删除执行器
    在后台执行批量删除任务，每个种子有独立的超时控制
    """

    # 单个种子删除超时时间（秒）
    SINGLE_TORRENT_TIMEOUT = 30

    def __init__(self, db_session_factory: Callable[[], Session], request: Request):
        """
        初始化执行器

        Args:
            db_session_factory: 数据库会话工厂函数
            request: FastAPI Request 对象
        """
        self.db_session_factory = db_session_factory
        self.request = request

    async def execute_deletion_task(
        self,
        task_id: str,
        torrent_info_ids: List[str],
        delete_level: int,
        operator: str,
        request
    ):
        """
        执行批量删除任务

        Args:
            task_id: 任务ID
            torrent_info_ids: 种子信息ID列表
            delete_level: 删除等级（1-4）
            operator: 操作者
            request: FastAPI Request对象
        """
        task_manager = get_deletion_task_manager()

        # 更新任务状态为运行中
        await task_manager.update_task_status(
            task_id=task_id,
            status=TaskStatus.RUNNING
        )

        success_items = []
        failed_items = []

        try:
            total = len(torrent_info_ids)

            for idx, info_id in enumerate(torrent_info_ids, 1):
                try:
                    # 使用wait_for实现超时控制
                    result = await asyncio.wait_for(
                        self._delete_single_torrent(
                            info_id=info_id,
                            delete_level=delete_level,
                            operator=operator,
                            request=self.request
                        ),
                        timeout=self.SINGLE_TORRENT_TIMEOUT
                    )

                    if result.get("success"):
                        success_items.append({
                            "info_id": info_id,
                            "result": result.get("data")
                        })

                        # 更新进度
                        await task_manager.update_task_status(
                            task_id=task_id,
                            status=TaskStatus.RUNNING,
                            success_count=len(success_items),
                            failed_count=len(failed_items)
                        )
                    else:
                        failed_items.append({
                            "info_id": info_id,
                            "error": result.get("msg", "未知错误")
                        })

                except asyncio.TimeoutError:
                    failed_items.append({
                        "info_id": info_id,
                        "error": f"删除超时（超过{self.SINGLE_TORRENT_TIMEOUT}秒）"
                    })
                    print(f"种子 {info_id} 删除超时")

                except Exception as e:
                    failed_items.append({
                        "info_id": info_id,
                        "error": str(e)
                    })
                    print(f"删除种子 {info_id} 时发生异常: {e}")

            # 确定最终状态
            if len(success_items) == total:
                final_status = TaskStatus.COMPLETED
                error_message = None
            elif len(success_items) == 0:
                final_status = TaskStatus.FAILED
                error_message = "所有种子删除失败"
            else:
                final_status = TaskStatus.PARTIAL
                error_message = f"部分种子删除失败（成功{len(success_items)}/{total}）"

            # 更新任务最终状态
            await task_manager.update_task_status(
                task_id=task_id,
                status=final_status,
                success_count=len(success_items),
                failed_count=len(failed_items),
                error_message=error_message,
                results=success_items,
                failed_items=failed_items
            )

        except Exception as e:
            # 任务执行过程中发生严重异常
            await task_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error_message=f"任务执行异常: {str(e)}"
            )
            print(f"任务 {task_id} 执行异常: {e}")

    async def _delete_single_torrent(
        self,
        info_id: str,
        delete_level: int,
        operator: str,
        request: Request
    ) -> Dict[str, Any]:
        """
        删除单个种子

        Args:
            info_id: 种子信息ID
            delete_level: 删除等级
            operator: 操作者
            request: FastAPI Request对象

        Returns:
            删除结果字典
        """
        db = self.db_session_factory()
        try:
            # 创建删除服务实例
            deletion_service = TorrentDeletionByLevelService(db, request)

            # 调用删除方法
            result = await deletion_service.delete_by_level(
                torrent_info_id=info_id,
                delete_level=delete_level,
                operator=operator
            )

            if result.get("success"):
                return {
                    "success": True,
                    "data": result
                }
            else:
                return {
                    "success": False,
                    "msg": result.get("error", "删除失败")
                }

        except Exception as e:
            return {
                "success": False,
                "msg": f"删除异常: {str(e)}"
            }
        finally:
            db.close()
