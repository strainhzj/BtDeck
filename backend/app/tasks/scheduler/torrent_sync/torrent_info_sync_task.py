# -*- coding: utf-8 -*-
"""
种子信息同步任务

专门用于高频同步种子基础信息（名称、大小、进度、状态等）。
不包含 tracker 同步，不包含种子文件备份。

执行频率: 10分钟
性能目标: 10万种子场景下 <5秒
"""

import logging
from typing import Dict, Any
from app.core.config import settings
from app.tasks.scheduler.torrent_sync.base import BaseSyncTask

logger = logging.getLogger(__name__)


class TorrentInfoSyncTask(BaseSyncTask):
    """
    种子信息同步任务

    职责:
    - 同步种子基础信息（名称、大小、进度、状态等）
    - 使用增量同步机制（只同步变化的种子）
    - 不同步 tracker 信息
    - 不进行种子文件备份

    优势:
    - 高频执行（10分钟），保证种子信息的实时性
    - 轻量级操作，不包含耗时的 tracker 同步
    - 利用增量机制，只处理变化的种子
    """

    # 任务元数据
    name = "种子信息同步任务"
    description = "高频同步种子基础信息（不含tracker）"
    version = "2.0.0"
    author = "btpManager"
    category = "torrent"

    # 执行频率: 10分钟
    recommended_interval = 600  # 10分钟

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行种子信息同步任务

        Args:
            **kwargs: 额外参数

        Returns:
            同步结果字典
        """
        from app.main import app as downloader_app

        self.last_execution_time = self.execution_count
        self.execution_count += 1

        # 使用标准 logging 模块记录任务执行日志
        logger.info(f"开始执行种子信息同步任务（第{self.execution_count}次）")

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
                    "total_downloaders": 0,
                }

            logger.info(f"找到 {len(valid_downloaders)} 个有效下载器")

            # 并发执行种子信息同步（W3-3：并发数配置化，SQLite 默认 1 串行处理
            # 下载器；上限不超过明确压测值）
            logger.debug("开始并发执行种子信息同步...")
            result = await self.execute_sync_with_concurrency(
                downloaders=valid_downloaders,
                sync_func=self._sync_torrent_info_only,
                sync_type="TorrentInfo",
                max_concurrent=settings.INFO_SYNC_DOWNLOADER_CONCURRENCY,
            )

            # 辅种数量由同步任务统一全量校正，避免列表查询时实时分组计算。
            # 即使本轮只有部分下载器同步成功，也校正当前数据库快照；下轮任务
            # 会再次覆盖可能尚未同步到的变化。
            if result.get("status") in {"success", "partial"}:
                try:
                    result["auxiliary_seed_count"] = await self._refresh_auxiliary_seed_counts()
                except Exception as count_error:
                    # 数量校正失败不掩盖本轮下载器同步结果，下一轮任务会重试。
                    logger.error(f"[{self.name}] 辅种数量校正失败: {count_error}", exc_info=True)
                    result["auxiliary_seed_count"] = {"status": "failed", "error": str(count_error)}

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
                "total_downloaders": 0,
            }

    async def _refresh_auxiliary_seed_counts(self) -> Dict[str, int]:
        """使用独立短事务全量校正辅种数量。"""

        from app.database import AsyncSessionLocal
        from app.services.auxiliary_seed_count_service import refresh_auxiliary_seed_counts

        async with AsyncSessionLocal() as count_db:
            return await refresh_auxiliary_seed_counts(count_db)

    async def _sync_torrent_info_only(self, downloader_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        只同步种子信息，不同步 tracker（W2-1：执行核心委托 SyncCoordinator）

        自 W2-1 起，下载器读取/转换/写入统一由
        app/services/sync_coordinator.py::run_sync 编排（sync_type="info",
        trigger="cron"，同一资源准入/写治理/观测通道），本方法仅保留
        任务文件负责的下载器列表与并发语义（并发数取
        settings.INFO_SYNC_DOWNLOADER_CONCURRENCY，SQLite 默认 1）。

        Args:
            downloader_info: 下载器信息字典

        Returns:
            同步结果字典（status/message/nickname，与旧实现结构一致）
        """
        from app.services.sync_coordinator import (
            SyncRequest,
            map_sync_result_to_task_dict,
            run_sync,
        )

        downloader_id = downloader_info.get("downloader_id")
        result = await run_sync(
            SyncRequest(
                sync_type="info",
                downloader_ids=[str(downloader_id)] if downloader_id else None,
                trigger="cron",
            )
        )
        return map_sync_result_to_task_dict(result, downloader_info)
