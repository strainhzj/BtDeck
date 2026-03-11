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
        from app.api.endpoints.torrents import torrent_sync_db_async

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
                    "total_downloaders": 0
                }

            logger.info(f"找到 {len(valid_downloaders)} 个有效下载器")

            # 并发执行种子信息同步
            logger.debug("开始并发执行种子信息同步...")
            result = await self.execute_sync_with_concurrency(
                downloaders=valid_downloaders,
                sync_func=self._sync_torrent_info_only,
                sync_type="TorrentInfo",
                max_concurrent=3
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

    async def _sync_torrent_info_only(self, downloader_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        只同步种子信息，不同步 tracker

        Args:
            downloader_info: 下载器信息字典

        Returns:
            同步结果字典
        """
        from app.database import AsyncSessionLocal
        from app.downloader.models import BtDownloaders
        from app.api.endpoints.torrents_async import qb_add_torrents_info_only_async, tr_add_torrents_info_only_async

        async with AsyncSessionLocal() as db:
            try:
                # 创建下载器对象
                downloader = BtDownloaders()
                for key, value in downloader_info.items():
                    if hasattr(downloader, key):
                        setattr(downloader, key, value)

                # 判断下载器类型
                original_type = downloader.downloader_type
                downloader_type_str = None

                if original_type == 'qbittorrent' or original_type == 0 or original_type == '0':
                    downloader_type_str = 'qbittorrent'
                elif original_type == 'transmission' or original_type == 1 or original_type == '1':
                    downloader_type_str = 'transmission'

                if not downloader_type_str:
                    error_msg = f"不支持的下载器类型: {original_type}"
                    logger.error(error_msg)
                    return {
                        "status": "failed",
                        "message": error_msg,
                        "nickname": downloader.nickname
                    }

                # 调用种子信息同步函数（不含 tracker）
                if downloader_type_str == 'qbittorrent':
                    await qb_add_torrents_info_only_async(db, [downloader])
                    logger.info(f"[TorrentInfoSync] qBittorrent {downloader.nickname} 种子信息同步成功")
                    return {
                        "status": "success",
                        "message": f"qBittorrent下载器 {downloader.nickname} 种子信息同步成功",
                        "downloader_type": "qbittorrent",
                        "nickname": downloader.nickname
                    }
                else:  # transmission
                    await tr_add_torrents_info_only_async(db, [downloader])
                    logger.info(f"[TorrentInfoSync] Transmission {downloader.nickname} 种子信息同步成功")
                    return {
                        "status": "success",
                        "message": f"Transmission下载器 {downloader.nickname} 种子信息同步成功",
                        "downloader_type": "transmission",
                        "nickname": downloader.nickname
                    }

            except Exception as e:
                error_msg = f"同步种子信息失败: {str(e)}"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "message": error_msg,
                    "nickname": downloader_info.get('nickname', 'Unknown')
                }
