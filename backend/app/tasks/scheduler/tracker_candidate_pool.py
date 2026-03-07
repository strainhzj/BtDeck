"""
Tracker候选池填充任务类
用于APScheduler定时调度

功能:
- 从tracker_message_log读取未处理的消息(is_processed=False)
- 将消息作为关键词添加到tracker_keyword_config候选池(keyword_type='candidate')
- 去重处理: 仅比较keyword字段，重复则跳过
- 标记原消息为已处理(is_processed=True)
- 支持两种触发方式:
  1. 作为独立定时任务定期执行
  2. 在TrackerMessageLogger执行完毕后立即调用
"""

from datetime import datetime
from typing import Dict, Any, List
import logging
import threading
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, AsyncSessionLocal
from app.torrents.models import TrackerMessageLog, TrackerKeywordConfig

logger = logging.getLogger(__name__)


class TrackerCandidatePoolTask:
    """Tracker候选池填充任务

    从tracker_message_log读取未处理消息，添加到候选池。
    支持去重和错误处理。
    """

    # 任务元数据
    name = "Tracker候选池填充任务"
    description = "从tracker消息日志读取未处理消息，添加到候选池"
    version = "1.0.0"
    author = "btpmanager"
    category = "tracker"

    # 任务配置
    default_interval = 1800  # 默认30分钟
    batch_size = 100  # 批量处理大小

    def __init__(self):
        """初始化任务"""
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_messages_processed = 0
        self.total_new_candidates = 0
        self.total_duplicates = 0
        self.total_errors = 0

        # 线程锁保护统计信息
        self._stats_lock = threading.Lock()

    # ==================== 异步版本的核心方法 ====================

    async def _fill_candidate_pool_async(self, batch_size: int) -> tuple:
        """
        填充候选池主流程（异步版本）

        Args:
            batch_size: 批量处理大小

        Returns:
            (新增数量, 重复数量, 错误数量)
        """
        async with AsyncSessionLocal() as db:
            try:
                new_count = 0
                duplicate_count = 0
                error_count = 0

                # 查询未处理的消息(分批处理)
                offset = 0
                processed_log_ids = []

                while True:
                    # 分批查询
                    result = await db.execute(
                        select(TrackerMessageLog)
                        .filter(TrackerMessageLog.is_processed == False)
                        .limit(batch_size)
                        .offset(offset)
                    )
                    batch = result.scalars().all()

                    # 没有更多数据
                    if not batch:
                        break

                    # 查询数据库中已存在的keywords
                    existing_keywords_result = await db.execute(
                        select(TrackerKeywordConfig.keyword).filter(
                            TrackerKeywordConfig.dr == 0
                        )
                    )
                    existing_keywords = {kw[0] for kw in existing_keywords_result.all()}

                    logger.info(f"数据库中已存在 {len(existing_keywords)} 个关键词（dr=0）")

                    # 在当前批次内存中去重
                    seen_in_batch = set()
                    batch_to_process = []

                    for log in batch:
                        keyword = log.msg

                        # 批次内去重：同一批次内相同的keyword只处理一次
                        if keyword in seen_in_batch:
                            logger.debug(f"批次内跳过重复: {keyword[:50]}")
                            duplicate_count += 1
                            # 标记为已处理
                            log.is_processed = True
                            log.keyword_type = 'candidate'
                            log.update_time = datetime.now()
                            continue

                        seen_in_batch.add(keyword)

                        # 检查数据库中是否已存在
                        if keyword in existing_keywords:
                            duplicate_count += 1
                            logger.debug(f"数据库中已存在，跳过: {keyword[:50]}")
                            # 标记为已处理
                            log.is_processed = True
                            log.keyword_type = 'candidate'
                            log.update_time = datetime.now()
                        else:
                            # 待处理列表
                            batch_to_process.append(log)

                    # 处理待添加的keywords
                    for log in batch_to_process:
                        try:
                            # 创建新的候选关键词
                            new_keyword = TrackerKeywordConfig(
                                keyword_type='candidate',
                                keyword=log.msg,
                                language=None,  # NULL表示通用
                                priority=100,   # 默认优先级
                                enabled=True,
                                category=None,
                                description=f"从tracker消息自动生成 (tracker_host={log.tracker_host})",
                                create_time=datetime.now(),
                                update_time=datetime.now(),
                                create_by="system",
                                update_by="system",
                                dr=0
                            )

                            db.add(new_keyword)
                            new_count += 1
                            logger.info(f"新增候选关键词: {log.msg[:50]}")

                            # 添加到内存集合中，避免同一批次内重复
                            existing_keywords.add(log.msg)

                            # 标记原消息为已处理
                            log.is_processed = True
                            log.keyword_type = 'candidate'
                            log.update_time = datetime.now()
                            processed_log_ids.append(log.log_id)

                        except Exception as e:
                            error_count += 1
                            logger.error(f"处理消息失败: {e}, msg={log.msg[:50] if log.msg else 'empty'}")
                            continue

                    # 提交当前批次
                    await db.commit()
                    logger.info(f"批量处理完成: 处理{len(batch)}条消息, 新增{new_count}条, 跳过{duplicate_count}条")

                    # 继续下一批
                    offset += batch_size

                    # 安全检查: 避免无限循环
                    if offset > 100000:  # 最多处理10万条记录
                        logger.warning(f"[{self.name}] 处理记录数超过10万,停止处理")
                        break

                logger.info(f"候选池填充完成: 新增{new_count}条, 重复{duplicate_count}条, 错误{error_count}条")
                return (new_count, duplicate_count, error_count)

            except Exception as e:
                await db.rollback()
                logger.error(f"填充候选池失败: {e}", exc_info=True)
                raise

    # ==================== 同步版本的核心方法（保留兼容）====================

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行候选池填充流程

        Args:
            **kwargs: 任务参数(可选)
                - batch_size: 批量处理大小(可选，默认100)

        Returns:
            任务执行结果字典
        """
        try:
            batch_size = kwargs.get('batch_size', self.batch_size)

            self.last_execution_time = datetime.now()
            with self._stats_lock:
                self.execution_count += 1

            # 记录任务开始
            result = {
                "task_name": self.name,
                "execution_time": self.last_execution_time,
                "execution_count": self.execution_count,
                "status": "running",
                "message": "候选池填充任务开始",
                "batch_size": batch_size
            }

            logger.info(f"[{self.name}] 开始执行, 第{self.execution_count}次")
            logger.info(f"[{self.name}] 配置: 批量大小={batch_size}")

            # 执行填充流程
            new_count, duplicate_count, error_count = await self._fill_candidate_pool_async(batch_size)

            # 更新统计信息
            with self._stats_lock:
                self.total_new_candidates += new_count
                self.total_duplicates += duplicate_count
                self.total_errors += error_count
                self.total_messages_processed += (new_count + duplicate_count + error_count)
                self.success_count += 1

            result.update({
                "status": "success",
                "message": f"处理完成: 新增{new_count}条候选关键词, 重复{duplicate_count}条, 错误{error_count}条",
                "new_candidates": new_count,
                "duplicates": duplicate_count,
                "errors": error_count,
                "total_processed": new_count + duplicate_count + error_count,
                "total_messages_processed": self.total_messages_processed,
                "total_new_candidates": self.total_new_candidates,
                "total_duplicates": self.total_duplicates,
                "total_errors": self.total_errors,
                "success_count": self.success_count,
                "failure_count": self.failure_count
            })

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
                "failure_count": self.failure_count
            }
            logger.error(f"[{self.name}] 执行失败: {e}", exc_info=True)
            return error_result

    def _fill_candidate_pool(self, batch_size: int) -> tuple:
        """
        填充候选池主流程

        Args:
            batch_size: 批量处理大小

        Returns:
            (新增数量, 重复数量, 错误数量)
        """
        db = SessionLocal()
        try:
            new_count = 0
            duplicate_count = 0
            error_count = 0

            # 查询未处理的消息(分批处理)
            offset = 0
            processed_log_ids = []

            while True:
                # 分批查询
                query = db.query(TrackerMessageLog).filter(
                    TrackerMessageLog.is_processed == False
                ).limit(batch_size).offset(offset)

                batch = query.all()

                # 没有更多数据
                if not batch:
                    break

                # ===== 关键修复：先查询数据库中已存在的keywords =====
                existing_keywords = set()
                all_existing = db.query(TrackerKeywordConfig.keyword).filter(
                    TrackerKeywordConfig.dr == 0  # 只查询未删除的记录
                ).all()
                existing_keywords = {kw[0] for kw in all_existing}

                logger.info(f"数据库中已存在 {len(existing_keywords)} 个关键词（dr=0）")

                # 在当前批次内存中去重
                seen_in_batch = set()
                batch_to_process = []

                for log in batch:
                    keyword = log.msg

                    # 批次内去重：同一批次内相同的keyword只处理一次
                    if keyword in seen_in_batch:
                        logger.debug(f"批次内跳过重复: {keyword[:50]}")
                        duplicate_count += 1
                        # 标记为已处理
                        log.is_processed = True
                        log.keyword_type = 'candidate'
                        log.update_time = datetime.now()
                        continue

                    seen_in_batch.add(keyword)

                    # 检查数据库中是否已存在
                    if keyword in existing_keywords:
                        duplicate_count += 1
                        logger.debug(f"数据库中已存在，跳过: {keyword[:50]}")
                        # 标记为已处理
                        log.is_processed = True
                        log.keyword_type = 'candidate'
                        log.update_time = datetime.now()
                    else:
                        # 待处理列表
                        batch_to_process.append(log)

                # 处理待添加的keywords
                for log in batch_to_process:
                    try:
                        # 创建新的候选关键词
                        new_keyword = TrackerKeywordConfig(
                            keyword_type='candidate',
                            keyword=log.msg,
                            language=None,  # NULL表示通用
                            priority=100,   # 默认优先级
                            enabled=True,
                            category=None,
                            description=f"从tracker消息自动生成 (tracker_host={log.tracker_host})",
                            create_time=datetime.now(),
                            update_time=datetime.now(),
                            create_by="system",
                            update_by="system",
                            dr=0
                        )

                        db.add(new_keyword)
                        new_count += 1
                        logger.info(f"新增候选关键词: {log.msg[:50]}")

                        # 添加到内存集合中，避免同一批次内重复
                        existing_keywords.add(log.msg)

                        # 标记原消息为已处理
                        log.is_processed = True
                        log.keyword_type = 'candidate'
                        log.update_time = datetime.now()
                        processed_log_ids.append(log.log_id)

                    except Exception as e:
                        error_count += 1
                        logger.error(f"处理消息失败: {e}, msg={log.msg[:50] if log.msg else 'empty'}")
                        continue

                # 提交当前批次
                db.commit()
                logger.info(f"批量处理完成: 处理{len(batch)}条消息, 新增{new_count}条, 跳过{duplicate_count}条")

                # 继续下一批
                offset += batch_size

                # 安全检查: 避免无限循环
                if offset > 100000:  # 最多处理10万条记录
                    logger.warning(f"[{self.name}] 处理记录数超过10万,停止处理")
                    break

            logger.info(f"候选池填充完成: 新增{new_count}条, 重复{duplicate_count}条, 错误{error_count}条")
            return (new_count, duplicate_count, error_count)

        except Exception as e:
            db.rollback()
            logger.error(f"填充候选池失败: {e}", exc_info=True)
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
                "total_messages_processed": self.total_messages_processed,
                "total_new_candidates": self.total_new_candidates,
                "total_duplicates": self.total_duplicates,
                "total_errors": self.total_errors,
                "last_execution_time": self.last_execution_time,
                "success_rate": (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0
            }

    def get_schedule_config(self) -> Dict[str, Any]:
        """获取调度配置建议"""
        return {
            "cron_expression": "30 */1 * * *",  # 每小时30分执行一次（错峰）
            "timezone": "Asia/Shanghai",
            "max_instances": 1,     # 防止重叠执行
            "coalesce": True,       # 合并错过的执行
            "misfire_grace_time": 300,  # 错过执行的宽限时间（5分钟）
            "default_interval": self.default_interval,
            "batch_size": self.batch_size,
            "estimated_duration": "1-5 minutes"
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标(线程安全)"""
        with self._stats_lock:
            if self.execution_count == 0:
                return {
                    "average_new_per_execution": 0,
                    "average_duplicates_per_execution": 0,
                    "average_errors_per_execution": 0,
                    "total_processing_time": "N/A"
                }

            return {
                "average_new_per_execution": self.total_new_candidates / self.execution_count,
                "average_duplicates_per_execution": self.total_duplicates / self.execution_count,
                "average_errors_per_execution": self.total_errors / self.execution_count,
                "new_rate": (self.total_new_candidates / self.total_messages_processed * 100) if self.total_messages_processed > 0 else 0,
                "duplicate_rate": (self.total_duplicates / self.total_messages_processed * 100) if self.total_messages_processed > 0 else 0,
                "error_rate": (self.total_errors / self.total_messages_processed * 100) if self.total_messages_processed > 0 else 0,
                "task_reliability": (self.success_count / self.execution_count * 100)
            }
