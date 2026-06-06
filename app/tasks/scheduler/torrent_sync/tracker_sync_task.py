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
    - 高频执行（每30分钟），保证 tracker 状态的实时性
    - 专门针对 tracker 信息，不做种子基础信息同步
    - 使用专用 tracker-only 同步函数，避免与 TorrentInfoSyncTask 重复
    """

    # 任务元数据
    name = "Tracker 同步任务"
    description = "高频同步 Tracker 状态信息（专用 tracker-only 实现）"
    version = "3.0.0"
    author = "btpManager"
    category = "torrent"

    # 执行频率: 30分钟
    recommended_interval = 1800

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行 Tracker 同步任务

        Args:
            **kwargs: 额外参数

        Returns:
            同步结果字典
        """
        from app.main import app as downloader_app
        from app.api.endpoints.torrent_sync import update_tracker_status_from_keywords

        self.last_execution_time = self.execution_count
        self.execution_count += 1

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
        只同步 Tracker 信息（专用实现）

        核心流程:
        1. 从 app.state.store 获取缓存的客户端连接（遵循约束16）
        2. 从数据库查询 hash -> info_id 映射（只查2个字段）
        3. 从下载器 API 获取 tracker 数据
        4. 调用 sync_add_tracker_async 写入 tracker_info 表

        不做的事情:
        - 不同步种子基础信息（torrent_info 表不写入）
        - 不做种子文件备份
        - 不标记删除的种子

        Args:
            downloader_info: 下载器信息字典（由 base.py sync_single_downloader 构建）

        Returns:
            同步结果字典
        """
        from app.database import AsyncSessionLocal
        from app.downloader.models import BtDownloaders
        from app.main import app as downloader_app
        from app.api.endpoints.torrents_async import (
            qb_sync_trackers_only_async,
            tr_sync_trackers_only_async,
        )

        # === 构建下载器对象 ===
        downloader = BtDownloaders()
        for key, value in downloader_info.items():
            if hasattr(downloader, key):
                setattr(downloader, key, value)

        nickname = downloader_info.get('nickname', 'unknown')

        # === 确定下载器类型 ===
        original_type = downloader.downloader_type
        if original_type == 'qbittorrent' or original_type == 0 or original_type == '0':
            downloader_type_str = 'qbittorrent'
        elif original_type == 'transmission' or original_type == 1 or original_type == '1':
            downloader_type_str = 'transmission'
        else:
            error_msg = f"不支持的下载器类型: {original_type}"
            logger.error(error_msg)
            return {"status": "failed", "message": error_msg, "nickname": nickname}

        # === 从缓存获取客户端连接（遵循约束16） ===
        try:
            cached_downloaders = await downloader_app.state.store.get_snapshot()
            downloader_vo = next(
                (d for d in cached_downloaders
                 if str(d.downloader_id) == str(downloader_info.get('downloader_id'))),
                None
            )
        except Exception as e:
            logger.error(f"获取缓存下载器失败: {e}")
            downloader_vo = None

        if not downloader_vo or not hasattr(downloader_vo, 'client') or downloader_vo.client is None:
            error_msg = f"无法获取下载器 {nickname} 的缓存客户端连接"
            logger.error(error_msg)
            return {"status": "failed", "message": error_msg, "nickname": nickname}

        client = downloader_vo.client

        # === 执行 tracker-only 同步 ===
        async with AsyncSessionLocal() as db:
            try:
                if downloader_type_str == 'qbittorrent':
                    result = await qb_sync_trackers_only_async(db, downloader, client)
                else:
                    result = await tr_sync_trackers_only_async(db, downloader, client)

                return result

            except Exception as e:
                error_msg = f"Tracker 同步失败 ({downloader_type_str}/{nickname}): {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {"status": "failed", "message": error_msg, "nickname": nickname}
