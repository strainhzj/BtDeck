"""
下载器缓存同步任务类
用于APScheduler定时调度
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class CachedDownloaderSyncTask:
    """下载器缓存同步任务

    定期执行下载器连通性验证和缓存管理
    """

    # 任务元数据
    name = "cached_downloader_sync"
    description = "下载器连通性验证和缓存同步任务"
    version = "1.0.1"
    author = "btpmanager"
    category = "downloader"

    # 任务配置
    default_interval = 60   # 默认1分钟
    max_interval = 1800     # 最大30分钟
    min_interval = 60       # 最小1分钟

    def __init__(self, app: Optional[Any] = None):
        """初始化任务

        Args:
            app: FastAPI 应用实例（可选，建议通过 set_app 方法设置）
        """
        self.app = app
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0

    def set_app(self, app: Any):
        """设置 FastAPI 应用实例

        Args:
            app: FastAPI 应用实例
        """
        self.app = app

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行下载器缓存同步任务

        Args:
            **kwargs: 任务参数（可选）
                - app: FastAPI 应用实例（可选，如果初始化时未设置）

        Returns:
            任务执行结果字典
        """
        try:
            # ✅ 修复：从 kwargs 中获取 app 实例（如果未在初始化时设置）
            if self.app is None and 'app' in kwargs:
                self.app = kwargs['app']

            # ✅ 验证 app 实例是否可用
            if self.app is None:
                raise ValueError("FastAPI app instance not set. Pass 'app' parameter to execute() or set it via set_app()")

            self.last_execution_time = datetime.now()
            self.execution_count += 1

            # 记录任务开始
            result = {
                "task_name": self.name,
                "execution_time": self.last_execution_time,
                "execution_count": self.execution_count,
                "status": "running",
                "message": "Downloader cache sync task started"
            }

            # 这里直接调用修改后的缓存同步逻辑
            # 注意：原来的 cached_downloader_sync_task() 是无限循环的
            # 我们需要创建一个单次执行的版本
            await self._single_sync_execution()

            # 更新成功计数
            self.success_count += 1

            result.update({
                "status": "success",
                "message": "Downloader cache sync task completed successfully",
                "success_count": self.success_count,
                "failure_count": self.failure_count
            })

            return result

        except Exception as e:
            self.failure_count += 1
            error_result = {
                "task_name": self.name,
                "execution_time": datetime.now(),
                "execution_count": self.execution_count,
                "status": "failed",
                "message": f"Downloader cache sync task failed: {str(e)}",
                "success_count": self.success_count,
                "failure_count": self.failure_count
            }
            return error_result

    async def _single_sync_execution(self):
        """执行单次下载器缓存同步逻辑"""
        from app.database import SessionLocal
        from sqlalchemy import text
        from app.downloader.initialization import _check_and_add_new_downloader, _refresh_cached_downloader_fields

        # ✅ 修复：使用实例变量 self.app 而不是导入全局变量
        if self.app is None:
            raise ValueError("FastAPI app instance not set")

        # 使用标准 logging 模块记录任务执行日志
        logger.info("Starting single execution of downloader cache sync")

        # 步骤1：从数据库获取所有启用的下载器
        db = SessionLocal()
        try:
            sql = """
            SELECT downloader_id, host, nickname, username, status, enabled, is_search,
                   downloader_type, port, password, is_ssl, torrent_save_path
            FROM bt_downloaders
            WHERE enabled = true AND dr = 0
            """
            result = db.execute(text(sql))
            db_downloaders = [row._asdict() for row in result]

            logger.info(f"Found {len(db_downloaders)} downloaders in database")

            if not db_downloaders:
                logger.warning("No enabled downloaders found in database")
                return

            # 步骤2：获取当前缓存中的下载器
            cached_downloaders = await self.app.state.store.get_snapshot()
            logger.info(f"Found {len(cached_downloaders)} downloaders in cache")

            # 步骤3：刷新缓存下载器的字段值（如 torrent_save_path）
            if cached_downloaders:
                _refresh_cached_downloader_fields(cached_downloaders, db_downloaders, logger)

            # 步骤4：对比找出新下载器和孤立下载器（优先使用稳定主键 downloader_id）
            cached_id_set = {
                str(d.downloader_id) for d in cached_downloaders
                if hasattr(d, 'downloader_id') and d.downloader_id is not None
            }
            db_id_set = {
                str(d['downloader_id']) for d in db_downloaders
                if d.get('downloader_id') is not None
            }

            # 兼容：仅当 ID 不可用时才退回昵称对比
            cached_nickname_set = {d.nickname for d in cached_downloaders}
            db_nickname_set = {d['nickname'] for d in db_downloaders}

            # 找出在数据库中但不在缓存中的下载器（需要添加）
            if cached_id_set and db_id_set:
                new_downloaders = [
                    d for d in db_downloaders
                    if d.get('downloader_id') is not None and str(d['downloader_id']) not in cached_id_set
                ]
            else:
                new_downloaders = [d for d in db_downloaders if d['nickname'] not in cached_nickname_set]

            # 找出在缓存中但不在数据库中的下载器（需要移除）
            if cached_id_set and db_id_set:
                orphaned_downloaders = [
                    d for d in cached_downloaders
                    if hasattr(d, 'downloader_id')
                    and d.downloader_id is not None
                    and str(d.downloader_id) not in db_id_set
                ]
            else:
                orphaned_downloaders = [d for d in cached_downloaders if d.nickname not in db_nickname_set]

            logger.info(f"New downloaders to add: {len(new_downloaders)}")
            logger.info(f"Orphaned downloaders to remove: {len(orphaned_downloaders)}")

            # 步骤5：移除孤立的下载器
            if orphaned_downloaders:
                logger.info(f"Removing {len(orphaned_downloaders)} orphaned downloaders from cache")
                await self.app.state.store._remove_items(orphaned_downloaders)
                for orphan in orphaned_downloaders:
                    logger.info(f"Removed orphaned downloader: {orphan.nickname}")

            # 步骤6：添加新下载器
            successful_additions = 0
            failed_additions = 0
            skipped_additions = 0  # ✅ 新增：统计跳过的下载器

            for downloader_data in new_downloaders:
                try:
                    logger.info(f"Processing new downloader: {downloader_data['nickname']}")
                    result = await _check_and_add_new_downloader(self.app, downloader_data)

                    if result is True:
                        # ✅ 真正添加成功
                        successful_additions += 1
                        logger.info(f"✅ Successfully added downloader: {downloader_data['nickname']}")
                    elif result is False:
                        # ❌ 添加失败或被跳过
                        skipped_additions += 1
                        logger.info(f"⚠️ Skipped downloader: {downloader_data['nickname']}")
                    else:
                        # 异常情况（不应发生）
                        failed_additions += 1
                        logger.warning(f"❌ Unexpected result for downloader {downloader_data['nickname']}: {result}")

                except Exception as e:
                    failed_additions += 1
                    logger.error(f"❌ Failed to add downloader {downloader_data['nickname']}: {e}")

            # 步骤7：等待缓冲区处理（优化方案：最多10秒）
            if new_downloaders:
                max_wait = 10  # ✅ 增加等待时间从2秒到10秒
                wait_count = 0
                buffer_size_at_start = len(self.app.state.store._buffer)
                processing_status_at_start = self.app.state.store._processing

                logger.info(
                    f"⏳ 等待缓冲区处理: {buffer_size_at_start} 个项目, "
                    f"处理状态: {processing_status_at_start}"
                )

                while (
                    (self.app.state.store._buffer or self.app.state.store._processing)
                    and wait_count < max_wait
                ):
                    await asyncio.sleep(0.5)
                    wait_count += 1

                    # 每2秒输出一次进度日志
                    if wait_count % 4 == 0:
                        current_buffer_size = len(self.app.state.store._buffer)
                        logger.debug(
                            f"缓冲区处理进度: {wait_count * 0.5}秒, "
                            f"剩余: {current_buffer_size} 个项目, "
                            f"处理中: {self.app.state.store._processing}"
                        )

                # 输出最终状态
                final_buffer_size = len(self.app.state.store._buffer)
                final_processing = self.app.state.store._processing

                if final_buffer_size > 0 or final_processing:
                    logger.warning(
                        f"⚠️ 缓冲区等待超时: {final_buffer_size} 个项目未处理, "
                        f"处理状态: {final_processing}, "
                        f"等待时间: {wait_count * 0.5} 秒"
                    )
                else:
                    logger.info(
                        f"✅ 缓冲区处理完成: {buffer_size_at_start} 个项目, "
                        f"等待时间: {wait_count * 0.5} 秒"
                    )

            # 步骤8：输出最终缓存状态
            final_cache = await self.app.state.store.get_snapshot()
            logger.info(f"📊 最终缓存状态: {len(final_cache)} 个下载器")

            # 统计有效下载器数量
            valid_downloaders = [
                d for d in final_cache
                if hasattr(d, 'fail_time') and d.fail_time == 0
            ]

            logger.info(f"Found {len(valid_downloaders)} valid downloaders (fail_time=0)")

            # 执行连通性验证统计
            verified_count = 0
            failed_count = 0

            for downloader in final_cache:
                if hasattr(downloader, 'fail_time'):
                    if downloader.fail_time == 0:
                        verified_count += 1
                    else:
                        failed_count += 1

            logger.info(f"Downloader status: {verified_count} verified, {failed_count} failed")

            # 记录同步结果（包含跳过统计）
            logger.info(
                f"Sync summary: {successful_additions} added, "
                f"{skipped_additions} skipped, "
                f"{failed_additions} failed, "
                f"{len(orphaned_downloaders)} removed"
            )
            logger.info("Single execution of downloader cache sync completed")

        except Exception as e:
            logger.error(f"Error during downloader cache sync: {e}", exc_info=True)
            raise
        finally:
            db.close()

    def get_task_info(self) -> Dict[str, Any]:
        """获取任务信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_execution_time": self.last_execution_time,
            "success_rate": (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0
        }

    def get_schedule_config(self) -> Dict[str, Any]:
        """获取调度配置建议"""
        return {
            "cron_expression": "* * * * *",  # 每1分钟执行一次
            "timezone": "Asia/Shanghai",
            "max_instances": 1,  # 防止重叠执行
            "coalesce": True,   # 合并错过的执行
            "misfire_grace_time": 300,  # 错过执行的宽限时间（秒）
            "default_interval": self.default_interval,
            "max_interval": self.max_interval,
            "min_interval": self.min_interval
        }
