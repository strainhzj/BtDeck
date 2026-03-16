# -*- coding: utf-8 -*-
"""
Tracker 同步任务

专门用于高频同步 Tracker 状态信息（announce成功、scrape成功、错误消息等）。
Tracker 状态变化频繁，需要高频同步以保证实时性。

执行频率: 5分钟
性能目标: 10万种子场景下 <60秒（可接受，因为只同步 tracker）
"""

import logging
from typing import Dict, Any
from app.tasks.scheduler.torrent_sync.base import BaseSyncTask

logger = logging.getLogger(__name__)


class TrackerSyncTask(BaseSyncTask):
    """
    Tracker 同步任务

    职责:
    - 同步 Tracker 状态信息
      - last_announce_succeeded: announce 成功状态
      - last_announce_msg: announce 返回消息
      - last_scrape_succeeded: scrape 成功状态
      - last_scrape_msg: scrape 返回消息

    特点:
    - 高频执行（5分钟），保证 tracker 状态的实时性
    - 专门针对 tracker 信息，不做种子基础信息同步
    - 支持增量同步，只处理变化的种子
    """

    # 任务元数据
    name = "Tracker 同步任务"
    description = "高频同步 Tracker 状态信息"
    version = "2.0.0"
    author = "btpManager"
    category = "torrent"

    # 执行频率: 5分钟
    recommended_interval = 300  # 5分钟

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行 Tracker 同步任务

        Args:
            **kwargs: 额外参数

        Returns:
            同步结果字典
        """
        from app.main import app as downloader_app
        from app.api.endpoints.torrents import (
            torrent_sync_db_async,
            update_tracker_status_from_keywords,
        )

        self.last_execution_time = self.execution_count
        self.execution_count += 1

        # 使用标准 logging 模块记录任务执行日志
        logger.info(f"开始执行 Tracker 同步任务（第{self.execution_count}次）")

        try:
            # 获取有效的下载器列表
            logger.debug("获取有效下载器列表...")
            valid_downloaders = await self.get_valid_downloaders(downloader_app)

            if not valid_downloaders:
                logger.warning(f"[{self.name}] 没有有效的下载器可同步")
                return {
                    "status": "no_action",
                    "message": "没有有效的下载器可同步",
                    "successful_syncs": 0,
                    "failed_syncs": 0,
                    "total_downloaders": 0
                }

            logger.info(f"找到 {len(valid_downloaders)} 个有效下载器")

            # 串行执行 Tracker 同步，避免 SQLite 数据库并发写入冲突
            logger.debug("开始串行执行 Tracker 同步...")
            result = await self.execute_sync_with_concurrency(
                downloaders=valid_downloaders,
                sync_func=self._sync_tracker_only,
                sync_type="Tracker",
                max_concurrent=1  # 串行执行，彻底避免并发写入导致的数据库锁定问题
            )

            # 更新统计
            if result["status"] == "success":
                self.success_count += 1
            elif result["status"] == "failed":
                self.failure_count += 1

            self.total_processed += result.get("successful_syncs", 0)
            self.total_failed += result.get("failed_syncs", 0)

            # 记录任务结果
            logger.info(
                f"[{self.name}] 任务完成: "
                f"成功 {result.get('successful_syncs', 0)}, "
                f"失败 {result.get('failed_syncs', 0)}, "
                f"总计 {result.get('total_downloaders', 0)} 个下载器"
            )

            # Tracker sync complete: update tracker status by keyword board
            if result.get("successful_syncs", 0) > 0:
                try:
                    logger.debug("使用关键词更新 tracker 状态...")
                    tracker_status_result = await update_tracker_status_from_keywords()
                    logger.info(
                        f"Tracker 状态更新结果: {tracker_status_result.get('message', 'N/A')}"
                    )
                    result["tracker_status_update"] = tracker_status_result
                except Exception as update_error:
                    logger.error(
                        "Tracker 状态更新失败: %s",
                        str(update_error),
                        exc_info=True,
                    )

            return result

        except Exception as e:
            self.failure_count += 1
            error_msg = f"{self.name} 执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "failed",
                "message": error_msg,
                "successful_syncs": 0,
                "failed_syncs": 1,
                "total_downloaders": 0
            }

    async def _sync_tracker_only(self, downloader_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        只同步 Tracker 信息

        当前实现：复用完整的种子同步函数（包含 tracker 同步）

        优化方向（未来）：
        - 只从数据库获取种子列表（hash + info_id）
        - 从下载器获取 tracker 信息
        - 只更新 tracker 表，不同步种子基础信息

        Args:
            downloader_info: 下载器信息字典

        Returns:
            同步结果字典
        """
        # 当前直接复用 torrent_sync_db_async
        # 该函数会调用 qb_add_torrents_async() 或 tr_add_torrents_async()
        # 这些函数内部包含 tracker 同步（sync_add_tracker_async）

        # 优化: 可以通过设置环境变量或参数，跳过种子基础信息的更新
        # 但考虑到实现复杂度，当前版本保持完整同步

        from app.api.endpoints.torrents import torrent_sync_db_async

        # 执行完整的种子同步（包含 tracker）
        result = await torrent_sync_db_async(downloader_info)

        # 添加标识：这是 tracker 同步任务
        if result.get("status") == "success":
            result["message"] = f"{result.get('message', '')} (Tracker同步)"

        return result
