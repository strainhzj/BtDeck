# -*- coding: utf-8 -*-
"""
标签同步定时任务

用于APScheduler定时调度，定期从下载器同步标签数据到数据库。
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TagSyncTask:
    """
    标签同步定时任务类

    定期执行标签数据同步，保持数据库标签与下载器标签一致。
    支持同步所有下载器或指定下载器。
    """

    # 任务元数据
    name = "tag_sync"
    description = "标签数据同步任务"
    version = "1.0.0"
    author = "btpmanager"
    category = "tag_management"

    # 任务配置
    default_interval = 3600  # 默认1小时（3600秒）
    max_interval = 7200     # 最大2小时
    min_interval = 1800      # 最小30分钟

    def __init__(self):
        """初始化任务"""
        self.last_execution_time: Optional[datetime] = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行标签同步任务

        Args:
            **kwargs: 任务参数
                - downloader_id: 可选，指定同步的下载器ID
                - delete_missing: 可选，是否删除僵尸数据（默认True）
                - force: 可选，强制同步所有下载器（默认False）

        Returns:
            任务执行结果字典
        """
        try:
            self.last_execution_time = datetime.now()
            self.execution_count += 1

            # ✅ 硬编码默认参数（用于定时任务）
            # 定时任务调用时没有传递参数，使用默认值
            downloader_id = kwargs.get("downloader_id", None)
            delete_missing = kwargs.get("delete_missing", True)
            force = kwargs.get("force", False)  # 预留参数，当前未实现

            # 使用标准 logging 模块记录任务执行日志
            logger.info("Starting tag sync task execution")
            # 记录参数
            params_str = (
                f"downloader_id={downloader_id}, "
                f"delete_missing={delete_missing}, force={force}"
            )
            logger.debug(f"Parameters: {params_str}")

            # 导入服务
            from app.services.tag_sync_service import TagSyncService
            from app.database import AsyncSessionLocal

            # 获取异步数据库会话
            async with AsyncSessionLocal() as db:
                sync_service = TagSyncService(db)

                # 执行同步
                if downloader_id:
                    # 同步指定下载器
                    logger.info(f"Syncing tags for downloader: {downloader_id}")
                    # 从缓存获取downloader对象
                    from app.main import app
                    if not hasattr(app.state, 'store'):
                        result = {
                            "success": False,
                            "message": "下载器缓存未初始化"
                        }
                    else:
                        cached_downloaders = await app.state.store.get_snapshot()
                        downloader_obj = next(
                            (d for d in cached_downloaders if d.downloader_id == downloader_id),
                            None
                        )
                        if not downloader_obj:
                            result = {
                                "success": False,
                                "message": f"下载器不存在: {downloader_id}"
                            }
                        else:
                            result = await sync_service.sync_downloader_tags(
                                downloader_obj,  # 传递downloader对象，而不是字符串
                                delete_missing=delete_missing
                            )
                else:
                    # 同步所有下载器
                    logger.info("Syncing tags for all downloaders")
                    result = await sync_service.sync_all_downloaders(
                        delete_missing=delete_missing
                    )

                # 记录同步结果
                logger.info(f"Sync result: {result.get('message')}")
                if result.get("success"):
                    self.success_count += 1
                    logger.info(
                        f"Sync completed successfully: "
                        f"total_tags={result.get('total_tags', 0)}, "
                        f"created={result.get('created_count', 0)}, "
                        f"updated={result.get('updated_count', 0)}, "
                        f"deleted={result.get('deleted_count', 0)}"
                    )
                else:
                    self.failure_count += 1
                    logger.warning(f"Sync failed: {result.get('message')}")

                # 构建返回结果
                result_data = {
                    "task_name": self.name,
                    "execution_time": self.last_execution_time,
                    "execution_count": self.execution_count,
                    "status": "success" if result.get("success") else "failed",
                    "message": result.get("message"),
                    "success_count": self.success_count,
                    "failure_count": self.failure_count,
                    "downloader_id": downloader_id,
                }
                result_data.update(result)
                return result_data

        except Exception as e:
            self.failure_count += 1
            # 构建错误结果
            error_msg = f"标签同步任务异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            error_result = {
                "task_name": self.name,
                "execution_time": datetime.now(),
                "execution_count": self.execution_count,
                "status": "failed",
                "message": error_msg,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "error": str(e)
            }

            return error_result

    async def execute_single_downloader(
        self,
        downloader_id: str,
        delete_missing: bool = True
    ) -> Dict[str, Any]:
        """
        同步单个下载器的标签

        Args:
            downloader_id: 下载器ID
            delete_missing: 是否删除僵尸数据

        Returns:
            同步结果
        """
        return await self.execute(
            downloader_id=downloader_id,
            delete_missing=delete_missing
        )

    async def execute_all_downloaders(
        self,
        delete_missing: bool = True
    ) -> Dict[str, Any]:
        """
        同步所有下载器的标签

        Args:
            delete_missing: 是否删除僵尸数据

        Returns:
            同步结果
        """
        return await self.execute(
            downloader_id=None,
            delete_missing=delete_missing
        )

    def get_task_info(self) -> Dict[str, Any]:
        """
        获取任务信息

        Returns:
            任务信息字典
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "default_interval": self.default_interval,
            "min_interval": self.min_interval,
            "max_interval": self.max_interval,
            "last_execution": self.last_execution_time.isoformat() if self.last_execution_time else None,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count
        }

    def reset_stats(self):
        """重置统计信息"""
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0


# ==================== 快捷函数 ====================

async def sync_tags_for_downloader(downloader_id: str, delete_missing: bool = True) -> Dict[str, Any]:
    """
    同步指定下载器的标签快捷函数

    Args:
        downloader_id: 下载器ID
        delete_missing: 是否删除僵尸数据

    Returns:
        同步结果
    """
    task = TagSyncTask()
    return await task.execute_single_downloader(downloader_id, delete_missing)


async def sync_tags_for_all(delete_missing: bool = True) -> Dict[str, Any]:
    """
    同步所有下载器的标签快捷函数

    Args:
        delete_missing: 是否删除僵尸数据

    Returns:
        同步结果
    """
    task = TagSyncTask()
    return await task.execute_all_downloaders(delete_missing)


async def force_sync_all() -> Dict[str, Any]:
    """
    强制同步所有下载器的标签快捷函数

    Returns:
        同步结果
    """
    task = TagSyncTask()
    return await task.execute_all_downloaders(delete_missing=True)
