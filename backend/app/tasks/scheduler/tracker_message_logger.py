"""
Tracker消息记录任务类
用于APScheduler定时调度

功能:
- 定期扫描所有tracker返回的消息
- 记录新消息到数据库
- 按(tracker_host, msg)组合去重
- 实现混合清理策略(时间+数量限制)

性能优化:
- 批量处理消息,避免N+1查询
- 分页查询tracker信息,控制内存占用
- 线程安全的统计信息更新
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging
import json
import uuid
import threading
from urllib.parse import urlparse

from sqlalchemy import select, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, AsyncSessionLocal
from app.torrents.models import TrackerInfo, TorrentInfo, TrackerMessageLog

logger = logging.getLogger(__name__)


class TrackerMessageLogger:
    """Tracker消息记录任务

    定期扫描所有tracker返回的消息,记录新消息到数据库。
    采用智能去重策略,按(tracker_host, msg)组合去重。
    实现混合清理策略,控制数据量。

    性能优化:
    - 批量处理消息,减少数据库查询次数
    - 分页查询,控制内存占用
    - 线程安全的统计计数器
    """

    # 任务元数据
    name = "Tracker消息记录任务"
    description = "记录所有tracker返回的新消息,用于关键词配置"
    version = "1.0.2"  # 版本升级:修复模型字段问题
    author = "btpmanager"
    category = "tracker"

    # 任务配置(可从配置文件读取)
    default_interval = 3600  # 默认1小时
    retention_days = 90      # 保留90天
    max_records = 10000      # 最多保留10000条

    # 性能优化常量
    MAX_SAMPLE_COUNT = 3           # 每条消息最多保留示例数量
    BATCH_SIZE = 50                # 批量提交大小
    QUERY_BATCH_SIZE = 500         # 分页查询大小

    def __init__(self, retention_days: Optional[int] = None, max_records: Optional[int] = None):
        """初始化任务

        Args:
            retention_days: 数据保留天数(默认90天)
            max_records: 最大记录数(默认10000条)
        """
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_messages_processed = 0
        self.total_new_messages = 0
        self.total_duplicates = 0
        self.total_cleaned = 0

        # 线程锁保护统计信息
        self._stats_lock = threading.Lock()

        # 支持配置参数覆盖
        if retention_days is not None:
            self.retention_days = retention_days
        if max_records is not None:
            self.max_records = max_records

    # ==================== 异步版本的核心方法 ====================

    async def _collect_tracker_messages_async(self) -> List[Dict]:
        """
        收集所有tracker消息(分页查询优化内存)（异步版本）

        从数据库查询所有活跃种子的tracker信息,
        提取tracker_host和msg字段,过滤空消息。

        使用分页查询避免一次性加载大量数据到内存。

        Returns:
            tracker消息列表,每个元素包含:
            {
                "tracker_host": str,
                "msg": str,
                "sample_torrents": List[Dict],
                "sample_urls": List[str]
            }
        """
        async with AsyncSessionLocal() as db:
            try:
                tracker_msg_map = {}  # (tracker_host, msg) -> 数据
                offset = 0

                while True:
                    # 分页查询tracker信息
                    query = (
                        select(
                            TrackerInfo.tracker_id,
                            TrackerInfo.tracker_name,
                            TrackerInfo.tracker_url,
                            TrackerInfo.last_announce_msg,
                            TrackerInfo.last_scrape_msg,
                            TorrentInfo.name.label('torrent_name'),
                            TorrentInfo.hash.label('torrent_hash'),
                            TorrentInfo.torrent_file.label('torrent_file')
                        )
                        .join(
                            TorrentInfo,
                            TrackerInfo.torrent_info_id == TorrentInfo.info_id
                        )
                        .filter(
                            TorrentInfo.dr == 0,
                            TrackerInfo.dr == 0
                        )
                        .limit(self.QUERY_BATCH_SIZE)
                        .offset(offset)
                    )

                    result = await db.execute(query)
                    batch = result.all()

                    # 没有更多数据
                    if not batch:
                        break

                    # 处理当前批次
                    for tracker in batch:
                        # 提取tracker_host
                        tracker_host = self._extract_tracker_host(tracker.tracker_url)
                        if not tracker_host:
                            continue

                        # 优先使用last_announce_msg,为空则使用last_scrape_msg
                        msg = tracker.last_announce_msg or tracker.last_scrape_msg or ""

                        # 过滤空消息
                        if not msg or not msg.strip():
                            continue

                        # 去重: 相同的tracker_host + msg只保留一个
                        key = (tracker_host, msg.strip())
                        if key not in tracker_msg_map:
                            tracker_msg_map[key] = {
                                "tracker_host": tracker_host,
                                "msg": msg.strip(),
                                "sample_torrents": [],
                                "sample_urls": []
                            }

                        # 添加示例数据(最多3个)
                        data = tracker_msg_map[key]
                        if len(data["sample_torrents"]) < self.MAX_SAMPLE_COUNT:
                            data["sample_torrents"].append({
                                "name": tracker.torrent_name,
                                "file": tracker.torrent_file,
                                "hash": tracker.torrent_hash
                            })

                        if len(data["sample_urls"]) < self.MAX_SAMPLE_COUNT and tracker.tracker_url:
                            if tracker.tracker_url not in data["sample_urls"]:
                                data["sample_urls"].append(tracker.tracker_url)

                    # 继续下一批
                    offset += self.QUERY_BATCH_SIZE

                    # 安全检查: 避免无限循环
                    if offset > 100000:  # 最大查询10万条记录
                        logger.warning(f"[{self.name}] 查询记录数超过10万,停止查询")
                        break

                messages = list(tracker_msg_map.values())
                logger.info(f"收集到{len(messages)}条唯一tracker消息")
                return messages

            except Exception as e:
                logger.error(f"收集tracker消息失败: {e}", exc_info=True)
                return []

    async def _process_messages_batch_async(self, messages: List[Dict]) -> None:
        """
        批量处理消息(使用原生SQL UPSERT,原子操作避免并发冲突)（异步版本）

        使用 ON CONFLICT DO UPDATE 语法实现原子性upsert操作:
        - 如果记录已存在(tracker_host, msg): 更新 last_seen 和 occurrence_count
        - 如果记录不存在: 插入新记录

        优点:
        - 原子操作,无竞态条件
        - 单次数据库往返,性能最优
        - 完全避免 UNIQUE constraint 冲突

        Args:
            messages: 消息列表
        """
        if not messages:
            return

        async with AsyncSessionLocal() as db:
            try:
                # 准备UPSERT语句
                # 使用 ON CONFLICT (tracker_host, msg) DO UPDATE 实现原子性upsert
                upsert_sql = text("""
                    INSERT INTO tracker_message_log (
                        log_id, tracker_host, msg, first_seen, last_seen,
                        occurrence_count, sample_torrents, sample_urls,
                        is_processed, keyword_type, create_time, update_time,
                        create_by, update_by
                    ) VALUES (
                        :log_id, :tracker_host, :msg, :first_seen, :last_seen,
                        :occurrence_count, :sample_torrents, :sample_urls,
                        :is_processed, :keyword_type, :create_time, :update_time,
                        :create_by, :update_by
                    )
                    ON CONFLICT (tracker_host, msg) DO UPDATE SET
                        last_seen = excluded.last_seen,
                        occurrence_count = tracker_message_log.occurrence_count + 1,
                        update_time = excluded.update_time,
                        update_by = excluded.update_by,
                        -- 只有当示例数据为空时才更新
                        sample_torrents = CASE
                            WHEN tracker_message_log.sample_torrents IS NULL
                                OR tracker_message_log.sample_torrents = ''
                            THEN excluded.sample_torrents
                            ELSE tracker_message_log.sample_torrents
                        END,
                        sample_urls = CASE
                            WHEN tracker_message_log.sample_urls IS NULL
                                OR tracker_message_log.sample_urls = ''
                            THEN excluded.sample_urls
                            ELSE tracker_message_log.sample_urls
                        END
                """)

                # 批量执行UPSERT
                current_time = datetime.now()
                processed_count = 0
                new_count = 0
                duplicate_count = 0

                batch_count = 0
                for msg_data in messages:
                    try:
                        tracker_host = msg_data["tracker_host"]
                        msg = msg_data["msg"]
                        sample_torrents = msg_data.get("sample_torrents", [])
                        sample_urls = msg_data.get("sample_urls", [])

                        # 准备参数
                        params = {
                            "log_id": str(uuid.uuid4()),
                            "tracker_host": tracker_host,
                            "msg": msg,
                            "first_seen": current_time,
                            "last_seen": current_time,
                            "occurrence_count": 1,
                            "sample_torrents": self._serialize_samples(sample_torrents, self.MAX_SAMPLE_COUNT),
                            "sample_urls": self._serialize_samples(sample_urls, self.MAX_SAMPLE_COUNT),
                            "is_processed": False,
                            "keyword_type": None,
                            "create_time": current_time,
                            "update_time": current_time,
                            "create_by": "system",
                            "update_by": "system"
                        }

                        # 执行UPSERT
                        await db.execute(upsert_sql, params)

                        processed_count += 1
                        # 注意: 由于UPSERT是原子操作,我们无法准确判断是INSERT还是UPDATE
                        # 这里假设都是新记录(保守估计),实际统计可能不够精确
                        new_count += 1
                        batch_count += 1

                        if batch_count >= self.BATCH_SIZE:
                            await db.commit()
                            batch_count = 0

                    except Exception as e:
                        logger.error(f"处理消息失败: {e}, tracker_host={msg_data.get('tracker_host')}, msg={msg_data.get('msg', '')[:50]}")
                        with self._stats_lock:
                            self.total_messages_processed += 1
                        continue

                # 提交剩余更改
                if batch_count > 0:
                    await db.commit()

                # 更新统计信息
                with self._stats_lock:
                    self.total_messages_processed += processed_count
                    self.total_new_messages += new_count

                logger.info(f"批量处理完成: 处理{processed_count}条消息 (使用UPSERT原子操作)")

            except Exception as e:
                await db.rollback()
                logger.error(f"批量处理消息失败: {e}", exc_info=True)
                raise

    async def _cleanup_old_logs_async(self, retention_days: int, max_records: int) -> int:
        """
        清理过期记录（异步版本）

        清理策略(混合策略):
        1. 删除 first_seen 超过指定天数的记录
        2. 或 总记录数超过max_records时,删除最旧的记录

        注意: 由于TrackerMessageLog模型暂无dr字段,这里使用物理删除

        Args:
            retention_days: 数据保留天数
            max_records: 最大记录数

        Returns:
            删除的记录数
        """
        async with AsyncSessionLocal() as db:
            try:
                total_deleted = 0

                # 规则1: 时间限制(物理删除)
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                result = await db.execute(
                    select(TrackerMessageLog).filter(
                        TrackerMessageLog.first_seen < cutoff_date
                    )
                )
                old_logs = result.scalars().all()

                if old_logs:
                    count = len(old_logs)
                    for log in old_logs:
                        await db.delete(log)

                    await db.commit()
                    total_deleted += count
                    logger.info(f"清理过期记录: {count}条(超过{retention_days}天)")

                # 规则2: 数量限制(物理删除最旧的记录)
                result = await db.execute(select(TrackerMessageLog))
                total_count = len(result.all())

                if total_count > max_records:
                    # 查询最旧的记录
                    excess_count = total_count - max_records
                    result = await db.execute(
                        select(TrackerMessageLog)
                        .order_by(TrackerMessageLog.first_seen.asc())
                        .limit(excess_count)
                    )
                    oldest_logs = result.scalars().all()

                    for log in oldest_logs:
                        await db.delete(log)

                    await db.commit()
                    total_deleted += len(oldest_logs)
                    logger.info(f"清理最旧记录: {len(oldest_logs)}条(总数超过{max_records})")

                return total_deleted

            except Exception as e:
                await db.rollback()
                logger.error(f"清理记录失败: {e}", exc_info=True)
                return 0

    # ==================== 同步版本的核心方法（保留兼容）====================

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行消息记录流程

        Args:
            **kwargs: 任务参数(可选)
                - retention_days: 数据保留天数
                - max_records: 最大记录数

        Returns:
            任务执行结果字典
        """
        try:
            # 支持动态参数覆盖配置
            retention_days = kwargs.get('retention_days', self.retention_days)
            max_records = kwargs.get('max_records', self.max_records)

            self.last_execution_time = datetime.now()
            with self._stats_lock:
                self.execution_count += 1

            # 记录任务开始
            result = {
                "task_name": self.name,
                "execution_time": self.last_execution_time,
                "execution_count": self.execution_count,
                "status": "running",
                "message": "Tracker message logging started",
                "retention_days": retention_days,
                "max_records": max_records
            }

            logger.info(f"[{self.name}] 开始执行, 第{self.execution_count}次")
            logger.info(f"[{self.name}] 配置: 保留{retention_days}天, 最多{max_records}条")

            # Step 1: 收集所有tracker消息
            messages = await self._collect_tracker_messages_async()
            result["total_messages_found"] = len(messages)

            if not messages:
                logger.warning(f"[{self.name}] 未收集到任何tracker消息")
                with self._stats_lock:
                    self.success_count += 1
                result.update({
                    "status": "success",
                    "message": "未收集到任何tracker消息",
                    "total_messages_processed": 0,
                    "total_new_messages": 0,
                    "total_duplicates": 0,
                    "total_cleaned": 0,
                    "success_count": self.success_count,
                    "failure_count": self.failure_count
                })
                return result

            # Step 2: 批量处理消息(优化性能)
            await self._process_messages_batch_async(messages)

            # Step 3: 清理过期记录
            cleaned_count = await self._cleanup_old_logs_async(retention_days, max_records)
            with self._stats_lock:
                self.total_cleaned += cleaned_count

            # 更新统计信息
            with self._stats_lock:
                self.success_count += 1

            result.update({
                "status": "success",
                "message": f"处理完成: 新增{self.total_new_messages}条, 重复{self.total_duplicates}条, 清理{cleaned_count}条",
                "total_messages_processed": self.total_messages_processed,
                "total_new_messages": self.total_new_messages,
                "total_duplicates": self.total_duplicates,
                "total_cleaned": self.total_cleaned,
                "success_count": self.success_count,
                "failure_count": self.failure_count
            })

            logger.info(f"[{self.name}] 执行完成: {result['message']}")

            # 任务完成后立即调用候选池填充任务（方案B）
            try:
                from app.tasks.scheduler.tracker_candidate_pool import TrackerCandidatePoolTask
                candidate_task = TrackerCandidatePoolTask()
                candidate_result = await candidate_task.execute(batch_size=self.QUERY_BATCH_SIZE)

                # 将候选池任务的结果附加到当前任务结果
                result["candidate_pool_task"] = {
                    "triggered": True,
                    "trigger_reason": "auto_after_message_logging",
                    "new_candidates": candidate_result.get("new_candidates", 0),
                    "duplicates": candidate_result.get("duplicates", 0),
                    "errors": candidate_result.get("errors", 0),
                    "message": candidate_result.get("message", "")
                }

                logger.info(f"[{self.name}] 候选池填充任务已触发: {candidate_result.get('message')}")

            except Exception as e:
                logger.error(f"[{self.name}] 触发候选池填充任务失败: {e}", exc_info=True)
                result["candidate_pool_task"] = {
                    "triggered": False,
                    "error": str(e)
                }

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
                "failure_count": self.failure_count
            }
            logger.error(f"[{self.name}] 执行失败: {e}", exc_info=True)
            return error_result

    def _collect_tracker_messages(self) -> List[Dict]:
        """
        收集所有tracker消息(分页查询优化内存)

        从数据库查询所有活跃种子的tracker信息,
        提取tracker_host和msg字段,过滤空消息。

        使用分页查询避免一次性加载大量数据到内存。

        Returns:
            tracker消息列表,每个元素包含:
            {
                "tracker_host": str,
                "msg": str,
                "sample_torrents": List[Dict],
                "sample_urls": List[str]
            }
        """
        db = SessionLocal()
        try:
            tracker_msg_map = {}  # (tracker_host, msg) -> 数据
            offset = 0

            while True:
                # 分页查询tracker信息
                query = db.query(
                    TrackerInfo.tracker_id,
                    TrackerInfo.tracker_name,
                    TrackerInfo.tracker_url,
                    TrackerInfo.last_announce_msg,
                    TrackerInfo.last_scrape_msg,
                    TorrentInfo.name.label('torrent_name'),
                    TorrentInfo.hash.label('torrent_hash'),
                    TorrentInfo.torrent_file.label('torrent_file')
                ).join(
                    TorrentInfo,
                    TrackerInfo.torrent_info_id == TorrentInfo.info_id
                ).filter(
                    TorrentInfo.dr == 0,
                    TrackerInfo.dr == 0
                ).limit(self.QUERY_BATCH_SIZE).offset(offset)

                batch = query.all()

                # 没有更多数据
                if not batch:
                    break

                # 处理当前批次
                for tracker in batch:
                    # 提取tracker_host
                    tracker_host = self._extract_tracker_host(tracker.tracker_url)
                    if not tracker_host:
                        continue

                    # 优先使用last_announce_msg,为空则使用last_scrape_msg
                    msg = tracker.last_announce_msg or tracker.last_scrape_msg or ""

                    # 过滤空消息
                    if not msg or not msg.strip():
                        continue

                    # 去重: 相同的tracker_host + msg只保留一个
                    key = (tracker_host, msg.strip())
                    if key not in tracker_msg_map:
                        tracker_msg_map[key] = {
                            "tracker_host": tracker_host,
                            "msg": msg.strip(),
                            "sample_torrents": [],
                            "sample_urls": []
                        }

                    # 添加示例数据(最多3个)
                    data = tracker_msg_map[key]
                    if len(data["sample_torrents"]) < self.MAX_SAMPLE_COUNT:
                        data["sample_torrents"].append({
                            "name": tracker.torrent_name,
                            "file": tracker.torrent_file,
                            "hash": tracker.torrent_hash
                        })

                    if len(data["sample_urls"]) < self.MAX_SAMPLE_COUNT and tracker.tracker_url:
                        if tracker.tracker_url not in data["sample_urls"]:
                            data["sample_urls"].append(tracker.tracker_url)

                # 继续下一批
                offset += self.QUERY_BATCH_SIZE

                # 安全检查: 避免无限循环
                if offset > 100000:  # 最大查询10万条记录
                    logger.warning(f"[{self.name}] 查询记录数超过10万,停止查询")
                    break

            messages = list(tracker_msg_map.values())

            logger.info(f"收集到{len(messages)}条唯一tracker消息")
            return messages

        except Exception as e:
            logger.error(f"收集tracker消息失败: {e}", exc_info=True)
            return []
        finally:
            db.close()

    def _extract_tracker_host(self, tracker_url: str) -> Optional[str]:
        """
        从tracker URL中提取主机地址

        Args:
            tracker_url: tracker URL

        Returns:
            tracker主机地址,提取失败返回None
        """
        if not tracker_url:
            return None

        try:
            parsed = urlparse(tracker_url)
            if parsed.hostname:
                return parsed.hostname
            return None
        except Exception as e:
            logger.warning(f"解析tracker URL失败: {tracker_url}, {e}")
            return None

    def _serialize_samples(self, samples: Optional[List[Any]], limit: int) -> Optional[str]:
        """
        序列化示例数据

        Args:
            samples: 示例数据列表
            limit: 最大数量限制

        Returns:
            JSON字符串或None
        """
        if not samples:
            return None
        try:
            return json.dumps(samples[:limit], ensure_ascii=False)
        except Exception as e:
            logger.warning(f"序列化示例数据失败: {e}")
            return None

    def _process_messages_batch(self, messages: List[Dict]) -> None:
        """
        批量处理消息(使用原生SQL UPSERT,原子操作避免并发冲突)

        使用 ON CONFLICT DO UPDATE 语法实现原子性upsert操作:
        - 如果记录已存在(tracker_host, msg): 更新 last_seen 和 occurrence_count
        - 如果记录不存在: 插入新记录

        优点:
        - 原子操作,无竞态条件
        - 单次数据库往返,性能最优
        - 完全避免 UNIQUE constraint 冲突

        Args:
            messages: 消息列表
        """
        if not messages:
            return

        db = SessionLocal()
        try:
            # 准备UPSERT语句
            # 使用 ON CONFLICT (tracker_host, msg) DO UPDATE 实现原子性upsert
            upsert_sql = text("""
                INSERT INTO tracker_message_log (
                    log_id, tracker_host, msg, first_seen, last_seen,
                    occurrence_count, sample_torrents, sample_urls,
                    is_processed, keyword_type, create_time, update_time,
                    create_by, update_by
                ) VALUES (
                    :log_id, :tracker_host, :msg, :first_seen, :last_seen,
                    :occurrence_count, :sample_torrents, :sample_urls,
                    :is_processed, :keyword_type, :create_time, :update_time,
                    :create_by, :update_by
                )
                ON CONFLICT (tracker_host, msg) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    occurrence_count = tracker_message_log.occurrence_count + 1,
                    update_time = excluded.update_time,
                    update_by = excluded.update_by,
                    -- 只有当示例数据为空时才更新
                    sample_torrents = CASE
                        WHEN tracker_message_log.sample_torrents IS NULL
                            OR tracker_message_log.sample_torrents = ''
                        THEN excluded.sample_torrents
                        ELSE tracker_message_log.sample_torrents
                    END,
                    sample_urls = CASE
                        WHEN tracker_message_log.sample_urls IS NULL
                            OR tracker_message_log.sample_urls = ''
                        THEN excluded.sample_urls
                        ELSE tracker_message_log.sample_urls
                    END
            """)

            # 批量执行UPSERT
            current_time = datetime.now()
            processed_count = 0
            new_count = 0

            for msg_data in messages:
                try:
                    tracker_host = msg_data["tracker_host"]
                    msg = msg_data["msg"]
                    sample_torrents = msg_data.get("sample_torrents", [])
                    sample_urls = msg_data.get("sample_urls", [])

                    # 准备参数
                    params = {
                        "log_id": str(uuid.uuid4()),
                        "tracker_host": tracker_host,
                        "msg": msg,
                        "first_seen": current_time,
                        "last_seen": current_time,
                        "occurrence_count": 1,
                        "sample_torrents": self._serialize_samples(sample_torrents, self.MAX_SAMPLE_COUNT),
                        "sample_urls": self._serialize_samples(sample_urls, self.MAX_SAMPLE_COUNT),
                        "is_processed": False,
                        "keyword_type": None,
                        "create_time": current_time,
                        "update_time": current_time,
                        "create_by": "system",
                        "update_by": "system"
                    }

                    # 执行UPSERT
                    db.execute(upsert_sql, params)

                    processed_count += 1
                    new_count += 1

                except Exception as e:
                    logger.error(f"处理消息失败: {e}, tracker_host={msg_data.get('tracker_host')}, msg={msg_data.get('msg', '')[:50]}")
                    with self._stats_lock:
                        self.total_messages_processed += 1
                    continue

            # 提交所有更改
            db.commit()

            # 更新统计信息
            with self._stats_lock:
                self.total_messages_processed += processed_count
                self.total_new_messages += new_count

            logger.info(f"批量处理完成: 处理{processed_count}条消息 (使用UPSERT原子操作)")

        except Exception as e:
            db.rollback()
            logger.error(f"批量处理消息失败: {e}", exc_info=True)
            raise
        finally:
            db.close()

    def _cleanup_old_logs(self, retention_days: int, max_records: int) -> int:
        """
        清理过期记录

        清理策略(混合策略):
        1. 删除 first_seen 超过指定天数的记录
        2. 或 总记录数超过max_records时,删除最旧的记录

        注意: 由于TrackerMessageLog模型暂无dr字段,这里使用物理删除

        Args:
            retention_days: 数据保留天数
            max_records: 最大记录数

        Returns:
            删除的记录数
        """
        db = SessionLocal()
        try:
            total_deleted = 0

            # 规则1: 时间限制(物理删除)
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            old_logs = db.query(TrackerMessageLog).filter(
                TrackerMessageLog.first_seen < cutoff_date
            ).all()

            if old_logs:
                count = len(old_logs)
                for log in old_logs:
                    db.delete(log)

                db.commit()
                total_deleted += count
                logger.info(f"清理过期记录: {count}条(超过{retention_days}天)")

            # 规则2: 数量限制(物理删除最旧的记录)
            total_count = db.query(TrackerMessageLog).count()

            if total_count > max_records:
                # 查询最旧的记录
                excess_count = total_count - max_records
                oldest_logs = db.query(TrackerMessageLog).order_by(
                    TrackerMessageLog.first_seen.asc()
                ).limit(excess_count).all()

                for log in oldest_logs:
                    db.delete(log)

                db.commit()
                total_deleted += len(oldest_logs)
                logger.info(f"清理最旧记录: {len(oldest_logs)}条(总数超过{max_records})")

            return total_deleted

        except Exception as e:
            db.rollback()
            logger.error(f"清理记录失败: {e}", exc_info=True)
            return 0

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
                "total_messages_processed": self.total_messages_processed,
                "total_new_messages": self.total_new_messages,
                "total_duplicates": self.total_duplicates,
                "total_cleaned": self.total_cleaned,
                "last_execution_time": self.last_execution_time,
                "success_rate": (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0
            }

    def get_schedule_config(self) -> Dict[str, Any]:
        """获取调度配置建议"""
        return {
            "cron_expression": "0 */1 * * *",  # 每小时执行一次
            "timezone": "Asia/Shanghai",
            "max_instances": 1,     # 防止重叠执行
            "coalesce": True,       # 合并错过的执行
            "misfire_grace_time": 900,  # 错过执行的宽限时间（15分钟）
            "default_interval": self.default_interval,
            "retention_days": self.retention_days,
            "max_records": self.max_records,
            "batch_size": self.BATCH_SIZE,
            "query_batch_size": self.QUERY_BATCH_SIZE,
            "estimated_duration": "5-15 minutes"
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标(线程安全)"""
        with self._stats_lock:
            if self.execution_count == 0:
                return {
                    "average_messages_per_execution": 0,
                    "average_new_messages_per_execution": 0,
                    "average_duplicates_per_execution": 0,
                    "average_cleaned_per_execution": 0,
                    "total_processing_time": "N/A"
                }

            return {
                "average_messages_per_execution": self.total_messages_processed / self.execution_count,
                "average_new_messages_per_execution": self.total_new_messages / self.execution_count,
                "average_duplicates_per_execution": self.total_duplicates / self.execution_count,
                "average_cleaned_per_execution": self.total_cleaned / self.execution_count,
                "new_message_rate": (self.total_new_messages / self.total_messages_processed * 100) if self.total_messages_processed > 0 else 0,
                "duplicate_rate": (self.total_duplicates / self.total_messages_processed * 100) if self.total_messages_processed > 0 else 0,
                "task_reliability": (self.success_count / self.execution_count * 100)
            }
