"""
种子Tracker状态判断任务
用于APScheduler定时调度

功能:
- 遍历所有种子，检查每个种子的tracker状态
- 根据关键词池（失败池、成功池、忽略池）判断tracker是否失败
- 如果所有dr=0的tracker都失败，标记种子has_tracker_error=True
- 如果至少有一个tracker正常，标记种子has_tracker_error=False

判断规则:
- 匹配失败池关键词 → tracker错误
- 匹配成功池/忽略池关键词 → tracker正常
- 未匹配任何池 → 保持原有状态

Created: 2026-02-25
Author: btpmanager
Version: 1.0.0
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
import threading

from app.database import SessionLocal
from app.downloader.models import BtDownloaders
from app.models.setting_templates import DownloaderTypeEnum
from app.tasks.resource_guard import admission_controller
from app.torrents.models import TorrentInfo, TrackerInfo, TrackerKeywordConfig

logger = logging.getLogger(__name__)


def _tracker_is_not_contacted(tracker: TrackerInfo, downloader_type: Any) -> bool:
    """判断 Tracker 是否处于未联系/发送中的中性状态。"""
    if downloader_type is None:
        return False
    try:
        type_name = DownloaderTypeEnum(DownloaderTypeEnum.normalize(downloader_type)).to_name()
        announce_status = int(tracker.last_announce_succeeded)
    except (TypeError, ValueError):
        return False

    if type_name == "qbittorrent":
        return announce_status == 1
    return announce_status in {0, 1}


def evaluate_tracker_error_state(
    trackers: List[TrackerInfo], keyword_map: Dict[str, str], downloader_type: Any
) -> Optional[bool]:
    """根据 Tracker 原始状态与关键词返回种子的错误标记。

    ``True`` 表示所有 Tracker 都明确失败，``False`` 表示至少存在正常或未联系的
    Tracker，``None`` 表示仍有未知状态，应保留数据库原值。
    """
    has_normal_tracker = False
    has_failed_tracker = False
    has_neutral_tracker = False
    has_unknown_tracker = False

    for tracker in trackers:
        if _tracker_is_not_contacted(tracker, downloader_type):
            has_neutral_tracker = True
            continue

        messages = [
            message
            for message in (tracker.last_announce_msg or "", tracker.last_scrape_msg or "")
            if message
        ]
        tracker_matched = False
        for message in messages:
            keyword_type = keyword_map.get(message)
            if keyword_type == "failed":
                has_failed_tracker = True
                tracker_matched = True
                break
            if keyword_type in {"success", "ignored"}:
                has_normal_tracker = True
                tracker_matched = True
                break

        if not tracker_matched:
            has_unknown_tracker = True

    if has_normal_tracker or has_neutral_tracker:
        return False
    if has_failed_tracker and not has_unknown_tracker:
        return True
    return None


class TorrentTrackerStatusJudge:
    """种子Tracker状态判断任务

    定期检查所有种子的tracker状态，更新has_tracker_error字段。

    判断规则:
    - 检查每个种子的所有dr=0的tracker
    - tracker的last_announce_msg或last_scrape_msg匹配失败池 → tracker错误
    - tracker的last_announce_msg或last_scrape_msg匹配成功池/忽略池 → tracker正常
    - 所有tracker都错误 → has_tracker_error=True
    - 至少有一个tracker正常 → has_tracker_error=False
    - 没有任何tracker → 保持原状态不变

    性能优化:
    - 批量处理种子，避免N+1查询
    - 线程安全的统计信息更新
    """

    # 任务元数据
    name = "种子Tracker状态判断任务"
    description = "检查所有种子的tracker状态，更新has_tracker_error字段"
    version = "1.0.0"
    author = "btpmanager"
    category = "tracker"

    # 任务配置
    default_interval = 300  # 默认5分钟（300秒）

    # 性能优化常量
    BATCH_SIZE = 1000  # 批量处理种子数量

    def __init__(self):
        """初始化任务"""
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_torrents_processed = 0
        self.total_torrents_updated = 0
        self.total_no_change = 0
        self.total_all_failed = 0
        self.total_at_least_one_normal = 0
        self.total_no_tracker = 0

        # 线程锁保护统计信息
        self._stats_lock = threading.Lock()

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行状态判断流程

        Args:
            **kwargs: 任务参数(可选)

        Returns:
            任务执行结果字典
        """
        try:
            self.last_execution_time = datetime.now()
            with self._stats_lock:
                self.execution_count += 1

            # 记录任务开始
            result = {
                "task_name": self.name,
                "execution_time": self.last_execution_time,
                "execution_count": self.execution_count,
                "status": "running",
                "message": "Torrent tracker status judgment started",
            }

            logger.info(f"[{self.name}] 开始执行，第{self.execution_count}次")

            # Step 1: 加载所有启用的关键词到内存
            # to_thread：_load_keywords 是同步 SessionLocal 读，移出事件循环避免冻结
            keyword_map = await asyncio.to_thread(self._load_keywords)
            result["total_keywords_loaded"] = len(keyword_map)

            if not keyword_map:
                logger.warning(f"[{self.name}] 未加载到任何关键词，跳过执行")
                with self._stats_lock:
                    self.success_count += 1
                result.update(
                    {
                        "status": "success",
                        "message": "未加载到任何关键词",
                        "total_torrents_processed": 0,
                        "total_torrents_updated": 0,
                        "success_count": self.success_count,
                        "failure_count": self.failure_count,
                    }
                )
                return result

            # Step 2: 获取所有未删除的种子
            # to_thread：_get_all_torrents 是同步 SessionLocal 读，移出事件循环避免冻结
            torrents = await asyncio.to_thread(self._get_all_torrents)
            result["total_torrents_found"] = len(torrents)

            if not torrents:
                logger.warning(f"[{self.name}] 未发现任何种子")
                with self._stats_lock:
                    self.success_count += 1
                result.update(
                    {
                        "status": "success",
                        "message": "未发现任何种子",
                        "total_torrents_processed": 0,
                        "total_torrents_updated": 0,
                        "success_count": self.success_count,
                        "failure_count": self.failure_count,
                    }
                )
                return result

            # Step 3: 分批判断种子状态
            # 按 BATCH_SIZE 切分，每批独立 commit（毫秒级），db_write_scope 串行化写者。
            # 单批失败即终止（前面已提交批次保留——has_tracker_error 幂等可重算，下次执行覆盖）。
            for i in range(0, len(torrents), self.BATCH_SIZE):
                batch = torrents[i : i + self.BATCH_SIZE]
                async with admission_controller.db_write_scope():
                    await asyncio.to_thread(self._judge_one_batch, batch, keyword_map)

            # 更新统计信息
            with self._stats_lock:
                self.success_count += 1

            result.update(
                {
                    "status": "success",
                    "message": f"判断完成: 处理{self.total_torrents_processed}个种子，更新{self.total_torrents_updated}个 (全部失败{self.total_all_failed}，至少正常{self.total_at_least_one_normal})",
                    "total_torrents_processed": self.total_torrents_processed,
                    "total_torrents_updated": self.total_torrents_updated,
                    "total_no_change": self.total_no_change,
                    "total_all_failed": self.total_all_failed,
                    "total_at_least_one_normal": self.total_at_least_one_normal,
                    "total_no_tracker": self.total_no_tracker,
                    "success_count": self.success_count,
                    "failure_count": self.failure_count,
                }
            )

            logger.info(f"[{self.name}] 执行完成: {result['message']}")

            return result

        except Exception as e:
            with self._stats_lock:
                self.failure_count += 1
            error_result = {
                "task_name": self.name,
                "execution_time": datetime.now(),
                "execution_count": self.execution_count,
                "status": "failed",
                "message": f"任务执行失败: {str(e)}",
                "success_count": self.success_count,
                "failure_count": self.failure_count,
            }
            logger.error(f"[{self.name}] 执行失败: {e}", exc_info=True)
            return error_result

    def _load_keywords(self) -> Dict[str, str]:
        """
        加载所有启用的关键词到内存

        返回格式:
        {
            "keyword1": "failed",
            "keyword2": "success",
            "keyword3": "ignored",
            ...
        }

        Returns:
            关键词字典 (keyword -> type)
        """
        db = SessionLocal()
        try:
            # 查询所有启用的关键词（仅失败池、成功池、忽略池）
            keywords = (
                db.query(TrackerKeywordConfig)
                .filter(
                    TrackerKeywordConfig.enabled.is_(True),
                    TrackerKeywordConfig.dr == 0,
                    TrackerKeywordConfig.keyword_type.in_(["failed", "success", "ignored"]),
                )
                .all()
            )

            # 构建快速查找字典 (keyword -> type)
            # 如果存在重复keyword，保留priority最高的
            keyword_map = {}
            for kw in keywords:
                if kw.keyword not in keyword_map:
                    keyword_map[kw.keyword] = kw.keyword_type
                else:
                    # 如果重复，保留priority更高的
                    existing = (
                        db.query(TrackerKeywordConfig)
                        .filter(
                            TrackerKeywordConfig.keyword == kw.keyword,
                            TrackerKeywordConfig.enabled.is_(True),
                            TrackerKeywordConfig.dr == 0,
                        )
                        .order_by(TrackerKeywordConfig.priority.desc())
                        .first()
                    )
                    if existing:
                        keyword_map[kw.keyword] = existing.keyword_type
                        logger.warning(f"发现重复关键词: {kw.keyword}，保留高优先级记录")

            logger.info(f"加载关键词: {len(keyword_map)}条")
            return keyword_map

        except Exception as e:
            logger.error(f"加载关键词失败: {e}", exc_info=True)
            return {}
        finally:
            db.close()

    def _get_all_torrents(self) -> List[str]:
        """
        获取所有未删除的种子

        Returns:
            种子ID列表（只返回ID，避免会话问题）
        """
        db = SessionLocal()
        try:
            # 只查询ID，避免返回会话绑定的对象
            torrent_ids = db.query(TorrentInfo.info_id).filter(TorrentInfo.dr == 0).all()

            # 提取ID列表
            ids = [tid[0] for tid in torrent_ids]

            logger.info(f"发现种子: {len(ids)}个")
            return ids

        except Exception as e:
            logger.error(f"获取种子失败: {e}", exc_info=True)
            return []
        finally:
            db.close()

    def _judge_one_batch(self, torrent_ids: List[str], keyword_map: Dict[str, str]) -> None:
        """
        判断单个批次的种子状态（同步方法，由 execute 经 to_thread 调用）。

        N+1 优化：批次内改用两次 IN 查询取本批种子+tracker，内存按 torrent_info_id
        分组后遍历判断，消除逐种子 db.query。

        判断规则:
        - 检查每个种子的所有dr=0的tracker
        - tracker的last_announce_msg或last_scrape_msg匹配失败池 → tracker错误
        - tracker的last_announce_msg或last_scrape_msg匹配成功池/忽略池 → tracker正常
        - 所有tracker都错误 → has_tracker_error=True
        - 至少有一个tracker正常 → has_tracker_error=False
        - 没有任何tracker → 保持原状态不变

        Args:
            torrent_ids: 本批种子ID列表
            keyword_map: 关键词字典

        Raises:
            Exception: 单批 commit 失败时抛出（execute 侧终止，已提交批次保留）
        """
        if not torrent_ids:
            return

        db = SessionLocal()
        try:
            # 一次 IN 查询取本批种子（消除 N+1）
            torrents = db.query(TorrentInfo).filter(TorrentInfo.info_id.in_(torrent_ids)).all()
            # 按 info_id 索引，便于与 tracker 分组对齐
            torrent_map: Dict[str, TorrentInfo] = {str(t.info_id): t for t in torrents}

            # 一次 IN 查询取本批种子的 tracker（消除 N+1）
            batch_trackers = (
                db.query(TrackerInfo)
                .filter(
                    TrackerInfo.torrent_info_id.in_(torrent_ids),
                    TrackerInfo.dr == 0,
                )
                .all()
            )
            # 按 torrent_info_id 分组 tracker
            trackers_by_torrent: Dict[str, List[TrackerInfo]] = {}
            for tracker in batch_trackers:
                trackers_by_torrent.setdefault(str(tracker.torrent_info_id), []).append(tracker)

            downloader_ids = {str(t.downloader_id) for t in torrents if t.downloader_id is not None}
            downloader_type_rows = (
                db.query(BtDownloaders.downloader_id, BtDownloaders.downloader_type)
                .filter(BtDownloaders.downloader_id.in_(downloader_ids), BtDownloaders.dr == 0)
                .all()
                if downloader_ids
                else []
            )
            downloader_type_map = {str(row[0]): row[1] for row in downloader_type_rows}

            for torrent_id in torrent_ids:
                try:
                    torrent = torrent_map.get(torrent_id)
                    if not torrent:
                        continue

                    trackers = trackers_by_torrent.get(str(torrent.info_id), [])

                    # 判断是否有tracker
                    if not trackers:
                        with self._stats_lock:
                            self.total_no_tracker += 1
                        continue

                    # 更新has_tracker_error字段
                    old_value = torrent.has_tracker_error
                    decision = evaluate_tracker_error_state(
                        trackers,
                        keyword_map,
                        downloader_type_map.get(str(torrent.downloader_id)),
                    )

                    if decision is False:
                        torrent.has_tracker_error = False
                        with self._stats_lock:
                            self.total_at_least_one_normal += 1
                    elif decision is True:
                        torrent.has_tracker_error = True
                        with self._stats_lock:
                            self.total_all_failed += 1
                    else:
                        with self._stats_lock:
                            self.total_no_change += 1

                    # 统计更新数量
                    if torrent.has_tracker_error != old_value:
                        with self._stats_lock:
                            self.total_torrents_updated += 1

                    torrent.update_time = datetime.now()
                    with self._stats_lock:
                        self.total_torrents_processed += 1

                except Exception as e:
                    logger.error(f"判断种子失败: {e}")
                    continue

            # 提交本批更改（单批 commit，毫秒级）
            try:
                db.commit()
                logger.info(f"批量判断完成: 处理{len(torrent_ids)}个种子")
            except Exception as commit_error:
                logger.error(f"提交数据库失败: {commit_error}", exc_info=True)
                db.rollback()
                raise

        except Exception as e:
            db.rollback()
            logger.error(f"批量判断种子失败: {e}", exc_info=True)
            raise

        finally:
            db.close()

    def get_task_info(self) -> Dict[str, Any]:
        """获取任务信息(线程安全)"""
        with self._stats_lock:
            return {
                "name": self.name,
                "description": self.description,
                "version": self.version,
                "author": self.author,
                "category": self.category,
                "execution_count": self.execution_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "total_torrents_processed": self.total_torrents_processed,
                "total_torrents_updated": self.total_torrents_updated,
                "total_no_change": self.total_no_change,
                "total_all_failed": self.total_all_failed,
                "total_at_least_one_normal": self.total_at_least_one_normal,
                "total_no_tracker": self.total_no_tracker,
                "last_execution_time": self.last_execution_time,
                "success_rate": (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0,
                "update_rate": (
                    (self.total_torrents_updated / self.total_torrents_processed * 100)
                    if self.total_torrents_processed > 0
                    else 0
                ),
            }

    def get_schedule_config(self) -> Dict[str, Any]:
        """获取调度配置建议"""
        return {
            "cron_expression": "0 */5 * * *",  # 每5分钟执行一次
            "timezone": "Asia/Shanghai",
            "max_instances": 1,  # 防止重叠执行
            "coalesce": True,  # 合并错过的执行
            "misfire_grace_time": 300,  # 错过执行的宽限时间（5分钟）
            "default_interval": self.default_interval,
            "batch_size": self.BATCH_SIZE,
            "estimated_duration": "1-3 minutes",
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标(线程安全)"""
        with self._stats_lock:
            if self.execution_count == 0:
                return {
                    "average_torrents_per_execution": 0,
                    "average_updates_per_execution": 0,
                    "total_processing_time": "N/A",
                }

            return {
                "average_torrents_per_execution": self.total_torrents_processed / self.execution_count,
                "average_updates_per_execution": self.total_torrents_updated / self.execution_count,
                "update_rate": (
                    (self.total_torrents_updated / self.total_torrents_processed * 100)
                    if self.total_torrents_processed > 0
                    else 0
                ),
                "all_failed_rate": (
                    (self.total_all_failed / self.total_torrents_processed * 100)
                    if self.total_torrents_processed > 0
                    else 0
                ),
                "at_least_one_normal_rate": (
                    (self.total_at_least_one_normal / self.total_torrents_processed * 100)
                    if self.total_torrents_processed > 0
                    else 0
                ),
                "no_tracker_rate": (
                    (self.total_no_tracker / self.total_torrents_processed * 100)
                    if self.total_torrents_processed > 0
                    else 0
                ),
                "task_reliability": (self.success_count / self.execution_count * 100),
            }
