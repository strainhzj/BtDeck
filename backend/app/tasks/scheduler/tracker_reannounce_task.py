# -*- coding: utf-8 -*-
"""
Tracker Reannounce 定时轮询任务

按站点配置的间隔，定时对种子执行 tracker 汇报。
- 按域名匹配站点配置
- 按间隔判断是否需要汇报
- 按下载器分批限流执行
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from urllib.parse import urlparse

from app.tasks.scheduler.torrent_sync.base import BaseSyncTask
from app.core import reannounce_config_operations as ops

logger = logging.getLogger(__name__)


class TrackerReannounceTask(BaseSyncTask):
    """
    Tracker 汇报定时任务

    职责：
    - 读取启用的站点配置
    - 查询每个下载器下种子的 tracker 信息
    - 按域名匹配配置，判断间隔
    - 对满足条件的种子执行 reannounce
    """

    name = "Tracker汇报轮询任务"
    description = "按站点配置定时触发tracker汇报"
    version = "1.0.0"
    author = "btpManager"
    category = "tracker"

    recommended_interval = 300  # 5分钟检查一次

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行定时轮询"""
        from app.main import app as downloader_app
        from app.database import SessionLocal

        self.execution_count += 1
        logger.info(f"开始执行 {self.name}（第{self.execution_count}次）")

        try:
            valid_downloaders = await self.get_valid_downloaders(downloader_app)
            if not valid_downloaders:
                return {"status": "no_action", "message": "没有有效的下载器"}

            db = SessionLocal()
            try:
                # 获取启用的站点配置
                config_result = ops.get_enabled_configs(db)
                if not config_result.success or not config_result.data:
                    return {"status": "no_action", "message": "没有启用的站点配置"}

                configs = ops.filter_enabled_configs(config_result.data)
                logger.info(f"[DEBUG] 启用的站点配置数={len(configs)}, "
                             f"配置列表={[(c.domain_pattern, c.interval_minutes) for c in configs]}")
                total_success = 0
                total_failed = 0

                for dl_vo in valid_downloaders:
                    try:
                        result = await self._process_downloader(
                            downloader_app, db, dl_vo, configs
                        )
                        total_success += result.get("success_count", 0)
                        total_failed += result.get("failed_count", 0)
                    except Exception as e:
                        logger.error(f"处理下载器 {dl_vo.nickname} 失败: {e}")
                        total_failed += 1

                self.total_processed += total_success
                self.total_failed += total_failed
                self.success_count += 1

                return {
                    "status": "success",
                    "message": f"汇报完成: 成功 {total_success}, 失败 {total_failed}",
                    "successful_syncs": total_success,
                    "failed_syncs": total_failed,
                }

            finally:
                db.close()

        except Exception as e:
            self.failure_count += 1
            logger.error(f"{self.name} 执行失败: {e}", exc_info=True)
            return {"status": "failed", "message": str(e)}

    async def _process_downloader(self, app, db, dl_vo, configs) -> Dict[str, Any]:
        """处理单个下载器的汇报"""
        from app.torrents.models import TorrentInfo, TrackerInfo
        from app.services.reannounce_service import execute_reannounce

        # 查询该下载器的所有 tracker（未删除），使用 tracker_url 而非 tracker_host
        trackers = db.query(TrackerInfo).filter(
            TrackerInfo.tracker_url.isnot(None),
            TrackerInfo.dr == 0,
        ).all()
        logger.info(f"[DEBUG] 下载器={dl_vo.nickname}, tracker数量={len(trackers)}")

        if not trackers:
            return {"success_count": 0, "failed_count": 0}

        # 按 tracker_url 提取域名，匹配配置，收集需要汇报的 torrent_info_id
        torrent_ids_to_announce = set()
        matched_config_ids = set()

        sample_logged = 0
        for tracker in trackers:
            # 从 tracker_url 提取纯域名（优先用 tracker_host，为空则从 tracker_url 提取）
            domain = _extract_domain(tracker.tracker_host or tracker.tracker_url)
            if sample_logged < 3:
                logger.info(f"[DEBUG] tracker_url={tracker.tracker_url!r}, tracker_host={tracker.tracker_host!r}, 提取域名={domain!r}")
                sample_logged += 1
            if not domain:
                continue
            # 查找该 tracker 匹配的配置
            for config in configs:
                if ops.match_domain(domain, config):
                    logger.info(f"[DEBUG] 域名匹配成功: {domain} -> config={config.domain_pattern}, "
                                f"should_announce={should_announce(config)}, "
                                f"last_announce_time={config.last_announce_time}")
                    if should_announce(config):
                        torrent_ids_to_announce.add(tracker.torrent_info_id)
                        matched_config_ids.add(config.id_)
                    break

        logger.info(f"[DEBUG] 匹配到需要汇报的种子数={len(torrent_ids_to_announce)}, "
                     f"匹配到的配置数={len(matched_config_ids)}")

        if not torrent_ids_to_announce:
            return {"success_count": 0, "failed_count": 0}

        # 查询对应的种子记录（属于当前下载器且未删除）
        torrent_records = db.query(TorrentInfo).filter(
            TorrentInfo.info_id.in_(torrent_ids_to_announce),
            TorrentInfo.downloader_id == dl_vo.downloader_id,
            TorrentInfo.dr == 0,
        ).all()
        logger.info(f"[DEBUG] 属于当前下载器的种子记录数={len(torrent_records)}")

        if not torrent_records:
            return {"success_count": 0, "failed_count": 0}

        # 执行汇报
        result = await execute_reannounce(
            app=app, db=db,
            downloader_id=dl_vo.downloader_id,
            torrent_records=torrent_records,
            trigger_type="scheduled",
        )

        # 更新匹配配置的最后汇报时间
        for config_id in matched_config_ids:
            ops.update_last_announce_time(db, config_id)

        return result

    async def execute_with_app(self, app, db) -> Dict[str, Any]:
        """提供给测试使用的简化入口"""
        return await self.execute()


# ==================== 工具函数 ====================

def _extract_domain(tracker_host: str) -> str:
    """从 tracker URL 中提取纯域名"""
    if not tracker_host:
        return ""
    try:
        if "://" not in tracker_host:
            tracker_host = f"http://{tracker_host}"
        parsed = urlparse(tracker_host)
        return parsed.hostname or ""
    except Exception:
        return ""


def should_announce(config) -> bool:
    """判断是否应该执行汇报"""
    if config.last_announce_time is None:
        return True
    elapsed = datetime.now() - config.last_announce_time
    return elapsed >= timedelta(minutes=config.interval_minutes)


def group_torrents_by_domain(trackers: list, configs: list) -> Dict[str, list]:
    """按域名匹配分组 tracker"""
    groups: Dict[str, list] = {}
    for tracker in trackers:
        if not getattr(tracker, 'tracker_host', None):
            continue
        domain = _extract_domain(tracker.tracker_host)
        if not domain:
            continue
        for config in configs:
            if ops.match_domain(domain, config):
                if domain not in groups:
                    groups[domain] = []
                groups[domain].append(tracker)
                break
    return groups


def filter_torrents_by_downloader(torrents: list, downloader_id: str) -> list:
    """过滤属于指定下载器的未删除种子"""
    return [
        t for t in torrents
        if getattr(t, 'downloader_id', None) == downloader_id
        and getattr(t, 'dr', 0) == 0
    ]
