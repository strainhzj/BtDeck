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

        W2-1：执行核心统一委托 SyncCoordinator（sync_type="tracker",
        trigger="cron"）。下载器列表仍由本任务负责（get_valid_downloaders）；
        Coordinator 内串行处理各下载器（保持原 max_concurrent=1 语义），
        tracker_status 阶段（关键词状态增量写回）由 Coordinator 内置，
        本任务不再重复调用 update_tracker_status_from_keywords。

        Args:
            **kwargs: 额外参数

        Returns:
            同步结果字典（status/message/successful_syncs/failed_syncs/
            total_downloaders/tracker_status_update，结构向后兼容）
        """
        from app.main import app as downloader_app

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
                    "total_downloaders": 0,
                }

            downloader_summary = [
                {
                    "downloader_id": str(getattr(downloader, "downloader_id", "")),
                    "nickname": getattr(downloader, "nickname", "unknown"),
                    "type": getattr(downloader, "downloader_type", "unknown"),
                }
                for downloader in valid_downloaders
            ]
            logger.info(
                "tracker_sync_task valid_downloaders count=%d downloaders=%s",
                len(valid_downloaders),
                downloader_summary,
            )

            # 串行执行 Tracker 同步（Coordinator 内逐下载器处理，避免 SQLite
            # 数据库并发写入冲突；max_concurrent=1 语义保持不变）
            logger.debug("开始串行执行 Tracker 同步（经 SyncCoordinator）...")
            from app.services.sync_coordinator import SyncRequest, run_sync

            coordinator_result = await run_sync(
                SyncRequest(
                    sync_type="tracker",
                    downloader_ids=[str(getattr(d, "downloader_id", None)) for d in valid_downloaders],
                    trigger="cron",
                )
            )

            result = self._map_coordinator_result(coordinator_result, len(valid_downloaders))
            result_errors = list(getattr(coordinator_result, "errors", []) or [])
            logger.info(
                "tracker_sync_task coordinator_result run_id=%s outcome=%s phase=%s "
                "successful_syncs=%s failed_syncs=%s error_count=%d errors=%s",
                getattr(coordinator_result, "run_id", None),
                getattr(coordinator_result, "outcome", None),
                getattr(coordinator_result, "phase", None),
                result.get("successful_syncs", 0),
                result.get("failed_syncs", 0),
                len(result_errors),
                result_errors[:5],
            )

            # 更新统计
            if result["status"] == "success":
                self.success_count += 1
            elif result["status"] == "failed":
                self.failure_count += 1

            self.total_processed += result.get("successful_syncs", 0)
            self.total_failed += result.get("failed_syncs", 0)

            # 记录任务结果
            completion_logger = logger.warning if result_errors else logger.info
            completion_logger(
                "[%s] 任务完成: 成功 %s, 失败 %s, 总计 %s 个下载器, "
                "error_count=%d, errors=%s",
                self.name,
                result.get("successful_syncs", 0),
                result.get("failed_syncs", 0),
                result.get("total_downloaders", 0),
                len(result_errors),
                result_errors[:5],
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

    @staticmethod
    def _map_coordinator_result(result, total_downloaders: int) -> Dict[str, Any]:
        """SyncResult -> 任务页兼容 dict（status/successful_syncs/...）。

        outcome 映射（与旧任务语义对齐）：
        - success -> success；partial -> partial；no_action -> no_action；
        - skipped / already_running -> skipped（调度器跳过不算失败）；
        - cancelled / failed -> failed。
        """
        outcome = result.outcome
        if outcome == "success":
            status = "success"
        elif outcome == "partial":
            status = "partial"
        elif outcome == "no_action":
            status = "no_action"
        elif outcome in ("skipped", "already_running"):
            status = "skipped"
        else:  # cancelled / failed
            status = "failed"

        mapped: Dict[str, Any] = {
            "status": status,
            "message": result.message or "; ".join(result.errors) or "Tracker 同步完成",
            "successful_syncs": result.details.get("successful_syncs", 0),
            "failed_syncs": result.details.get("failed_syncs", 0),
            "total_downloaders": total_downloaders,
            "outcome": outcome,
            "run_id": result.run_id,
            "skip_reason": result.skip_reason,
        }
        tracker_status_update = result.details.get("tracker_status_update")
        if tracker_status_update is not None:
            mapped["tracker_status_update"] = tracker_status_update
        return mapped
