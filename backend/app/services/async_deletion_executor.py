"""
异步批量删除执行器
在后台执行批量删除任务，支持超时处理、跳过失败种子、统计成功/失败数量。

增强点（快捷删除重复种子需求）：
- ``notify_on_complete``：任务完成后发送系统通知。
- 接入 ``audit_service``：使每个被删种子写入审计日志（此前未传 audit_service 导致审计缺失）。
"""

import asyncio
import logging
from typing import List, Dict, Any, Callable, Optional
from sqlalchemy.orm import Session
from fastapi import Request

from app.services.deletion_task_manager import get_deletion_task_manager, TaskStatus
from app.services.torrent_deletion_by_level import TorrentDeletionByLevelService

logger = logging.getLogger(__name__)


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
        request,
        notify_on_complete: bool = False,
    ):
        """
        执行批量删除任务

        Args:
            task_id: 任务ID
            torrent_info_ids: 种子信息ID列表
            delete_level: 删除等级（1-4）
            operator: 操作者
            request: FastAPI Request对象
            notify_on_complete: 完成后是否发送系统通知（默认 False，不影响既有流程）
        """
        task_manager = get_deletion_task_manager()

        # 更新任务状态为运行中
        await task_manager.update_task_status(task_id=task_id, status=TaskStatus.RUNNING)

        success_items: List[Dict[str, Any]] = []
        failed_items: List[Dict[str, Any]] = []

        # 创建异步审计服务；async session 需在整个任务期间存活（log_operation 依赖其提交）
        from app.database import AsyncSessionLocal
        from app.services.audit_service import get_audit_service

        audit_service = None
        async with AsyncSessionLocal() as async_db:
            try:
                audit_service = await get_audit_service(async_db)
            except Exception as e:
                logger.warning(f"获取审计日志服务失败: {e}")

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
                                request=self.request,
                                audit_service=audit_service,
                            ),
                            timeout=self.SINGLE_TORRENT_TIMEOUT,
                        )

                        if result.get("success"):
                            success_items.append({"info_id": info_id, "result": result.get("data")})

                            # 更新进度
                            await task_manager.update_task_status(
                                task_id=task_id,
                                status=TaskStatus.RUNNING,
                                success_count=len(success_items),
                                failed_count=len(failed_items),
                            )
                        else:
                            failed_items.append({"info_id": info_id, "error": result.get("msg", "未知错误")})

                    except asyncio.TimeoutError:
                        failed_items.append(
                            {"info_id": info_id, "error": f"删除超时（超过{self.SINGLE_TORRENT_TIMEOUT}秒）"}
                        )
                        print(f"种子 {info_id} 删除超时")

                    except Exception as e:
                        failed_items.append({"info_id": info_id, "error": str(e)})
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
                    failed_items=failed_items,
                )

            except Exception as e:
                # 任务执行过程中发生严重异常
                final_status = TaskStatus.FAILED
                total = len(torrent_info_ids)
                await task_manager.update_task_status(
                    task_id=task_id, status=final_status, error_message=f"任务执行异常: {str(e)}"
                )
                print(f"任务 {task_id} 执行异常: {e}")

        # 任务完成通知（async session 之外独立创建，失败仅告警不阻断任务）
        if notify_on_complete:
            await self._notify_complete(
                task_id=task_id,
                total=len(torrent_info_ids),
                success_count=len(success_items),
                failed_count=len(failed_items),
                final_status=final_status,
            )

    async def _notify_complete(
        self,
        task_id: str,
        total: int,
        success_count: int,
        failed_count: int,
        final_status: TaskStatus,
    ) -> None:
        """任务完成后发送系统通知（失败仅告警，不阻断任务状态返回）。"""
        try:
            from app.database import AsyncSessionLocal
            from app.services.notification_service import NotificationService

            status_text = {
                TaskStatus.COMPLETED: "完成",
                TaskStatus.PARTIAL: "部分完成",
                TaskStatus.FAILED: "失败",
            }.get(final_status, final_status.value)

            async with AsyncSessionLocal() as session:
                service = NotificationService(session)
                await service.create_notification(
                    type="system",
                    title="快捷删除重复种子完成",
                    content=f"删除任务已{status_text}：总数 {total}，成功 {success_count}，失败 {failed_count}。",
                    priority="info",
                    extra_data={"task_id": task_id},
                )
        except Exception as e:
            logger.warning(f"发送删除完成通知失败: {e}")

    async def _delete_single_torrent(
        self,
        info_id: str,
        delete_level: int,
        operator: str,
        request: Request,
        audit_service: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        删除单个种子

        Args:
            info_id: 种子信息ID
            delete_level: 删除等级
            operator: 操作者
            request: FastAPI Request对象
            audit_service: 审计日志服务（传入后按种子记录审计日志）

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
                operator=operator,
                audit_service=audit_service,
            )

            if result.get("success"):
                return {"success": True, "data": result}
            else:
                return {"success": False, "msg": result.get("error", "删除失败")}

        except Exception as e:
            return {"success": False, "msg": f"删除异常: {str(e)}"}
        finally:
            db.close()
