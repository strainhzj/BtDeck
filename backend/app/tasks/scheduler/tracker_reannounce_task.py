# -*- coding: utf-8 -*-
"""
Tracker Reannounce 定时轮询任务

按站点配置的间隔，定时对种子执行 tracker 汇报。
- 按域名匹配站点配置
- 按间隔判断是否需要汇报
- 按下载器分批限流执行
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse

from app.tasks.scheduler.torrent_sync.base import BaseSyncTask
from app.core import reannounce_config_operations as ops
from app.database import SessionLocal
from app.tasks.resource_guard import admission_controller

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

            # 读段（短 session）：仅查询启用的站点配置，查完立即释放连接。
            # 同步 SessionLocal 读经 to_thread 移出事件循环，避免阻塞循环。
            def _read_enabled_configs():
                db = SessionLocal()
                try:
                    return ops.get_enabled_configs(db)
                finally:
                    db.close()

            config_result = await asyncio.to_thread(_read_enabled_configs)

            if not config_result.success or not config_result.data:
                return {"status": "no_action", "message": "没有启用的站点配置"}

            configs = ops.filter_enabled_configs(config_result.data)
            total_success = 0
            total_failed = 0

            for dl_vo in valid_downloaders:
                try:
                    # _process_downloader 内部自行管理 session 生命周期：
                    # 读段(查种子/tracker) → 网络段(不持session) → 写段(短session)
                    result = await self._process_downloader(downloader_app, dl_vo, configs)
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

        except Exception as e:
            self.failure_count += 1
            logger.error(f"{self.name} 执行失败: {e}", exc_info=True)
            return {"status": "failed", "message": str(e)}

    async def _process_downloader(self, app, dl_vo, configs) -> Dict[str, Any]:
        """处理单个下载器的汇报。

        Session 生命周期拆分为三段（修复 database is locked / 事件循环饥饿）：
        1. 读段：同步 _read_downloader_data 经 to_thread 在线程池执行，短 session 查询
           tracker / 种子记录，expunge 剥离后立即 close（不阻塞事件循环）。
        2. 网络段：execute_reannounce 是 HTTP 远程调用，不持有任何 session。
        3. 写段：batch_update_last_announce_time 经 to_thread + db_write_scope 串行化写者。
        """
        from app.services.reannounce_service import execute_reannounce

        # ===== 读段（同步查询经 to_thread 移出事件循环）=====
        read_result = await asyncio.to_thread(self._read_downloader_data, dl_vo, configs)
        if read_result is None:
            return {"success_count": 0, "failed_count": 0}

        torrent_records, matched_config_ids = read_result
        if not torrent_records:
            return {"success_count": 0, "failed_count": 0}

        # ===== 网络段（不持有任何 session）=====
        result = await execute_reannounce(
            app=app,
            downloader_id=dl_vo.downloader_id,
            torrent_records=torrent_records,
            trigger_type="scheduled",
        )

        # ===== 写段（batch_update 内部自开短 session，to_thread + db_write_scope 串行化）=====
        if matched_config_ids:
            async with admission_controller.db_write_scope():
                await asyncio.to_thread(ops.batch_update_last_announce_time, list(matched_config_ids))

        return result

    def _read_downloader_data(self, dl_vo, configs) -> Optional[Tuple[List, set]]:
        """读段：短 session 查询 tracker / 种子记录，expunge 剥离后立即 close。

        同步方法，由 _process_downloader 经 asyncio.to_thread 调用，避免阻塞事件循环。
        Session 生命周期自管：查完 expunge_all + close，使返回的 ORM 对象脱离 session。

        Args:
            dl_vo: 下载器视图对象（需有 downloader_id）。
            configs: 站点配置列表。

        Returns:
            (torrent_records, matched_config_ids)：无数据时返回 None。
        """
        from app.torrents.models import TorrentInfo, TrackerInfo

        db = SessionLocal()
        try:
            # 先查出该下载器下所有未删除的种子info_id，用于过滤tracker
            downloader_torrent_ids = [
                r.info_id
                for r in db.query(TorrentInfo.info_id)
                .filter(
                    TorrentInfo.downloader_id == dl_vo.downloader_id,
                    TorrentInfo.dr == 0,
                )
                .all()
            ]
            if not downloader_torrent_ids:
                return None

            # 只查询属于当前下载器的 tracker，避免全表扫描
            trackers = (
                db.query(TrackerInfo)
                .filter(
                    TrackerInfo.torrent_info_id.in_(downloader_torrent_ids),
                    TrackerInfo.tracker_url.isnot(None),
                    TrackerInfo.dr == 0,
                )
                .all()
            )
            if not trackers:
                return None

            # 预编译配置匹配：按需汇报的config缓存判断结果
            eligible_config_ids = set()
            for config in configs:
                if should_announce(config):
                    eligible_config_ids.add(config.id_)

            # 按 tracker_url 提取域名，匹配配置，收集需要汇报的 torrent_info_id
            torrent_ids_to_announce = set()
            matched_config_ids = set()

            for tracker in trackers:
                domain = _extract_domain(tracker.tracker_host or tracker.tracker_url or "")
                if not domain:
                    continue
                for config in configs:
                    if ops.match_domain(domain, config):
                        if config.id_ in eligible_config_ids:
                            torrent_ids_to_announce.add(tracker.torrent_info_id)
                            matched_config_ids.add(config.id_)
                        break

            if not torrent_ids_to_announce:
                return None

            # 查询对应的种子记录（属于当前下载器且未删除）
            torrent_records = (
                db.query(TorrentInfo)
                .filter(
                    TorrentInfo.info_id.in_(torrent_ids_to_announce),
                    TorrentInfo.downloader_id == dl_vo.downloader_id,
                    TorrentInfo.dr == 0,
                )
                .all()
            )
            # 关键：把 ORM 对象从 session 剥离，使 close 后仍可在网络段使用其字段。
            db.expunge_all()
        finally:
            db.close()

        if not torrent_records:
            return None

        return torrent_records, matched_config_ids


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
        if not getattr(tracker, "tracker_host", None):
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
    return [t for t in torrents if getattr(t, "downloader_id", None) == downloader_id and getattr(t, "dr", 0) == 0]
