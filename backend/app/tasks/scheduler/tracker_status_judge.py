"""
Tracker状态判断任务类
用于APScheduler定时调度

功能:
- 定期扫描TrackerMessageLog中未处理的消息
- 根据TrackerKeywordConfig关键词池进行精确匹配
- 判断tracker状态(正常/错误)并更新消息记录
- 支持4种池类型: candidate/ignored/success/failed

判断规则:
- success池: 正常信息
- ignored池: 正常信息
- failed池: 错误信息
- candidate池: 不判断(保持候选状态)
"""

from datetime import datetime
from typing import Dict, Any, List
import logging
import threading
import uuid

from app.database import SessionLocal
from app.torrents.models import TrackerMessageLog, TrackerKeywordConfig

logger = logging.getLogger(__name__)


class TrackerStatusJudge:
    """Tracker状态判断任务

    定期扫描未处理的tracker消息,根据关键词池自动判断tracker状态。

    判断规则:
    - success池/ignored池 → 正常信息 (tracker_status='normal')
    - failed池 → 错误信息 (tracker_status='error')
    - candidate池 → 不判断 (is_processed=False)

    性能优化:
    - 批量处理消息,避免N+1查询
    - 线程安全的统计信息更新
    """

    # 任务元数据
    name = "Tracker状态判断任务"
    description = "自动判断tracker消息状态(正常/错误)"
    version = "1.0.0"
    author = "btpmanager"
    category = "tracker"

    # 任务配置
    default_interval = 1800  # 默认30分钟

    # 性能优化常量
    BATCH_SIZE = 500  # 批量处理大小

    def __init__(self):
        """初始化任务"""
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_messages_processed = 0
        self.total_matched = 0
        self.total_unmatched = 0
        self.total_normal = 0
        self.total_error = 0
        self.total_candidate = 0

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
                "message": "Tracker status judgment started"
            }

            logger.info(f"[{self.name}] 开始执行, 第{self.execution_count}次")

            # Step 1: 加载所有启用的关键词到内存
            keyword_map = self._load_keywords()
            result["total_keywords_loaded"] = len(keyword_map)

            if not keyword_map:
                logger.warning(f"[{self.name}] 未加载到任何关键词,跳过执行")
                with self._stats_lock:
                    self.success_count += 1
                result.update({
                    "status": "success",
                    "message": "未加载到任何关键词",
                    "total_messages_processed": 0,
                    "total_matched": 0,
                    "total_unmatched": 0,
                    "total_normal": 0,
                    "total_error": 0,
                    "total_candidate": 0,
                    "success_count": self.success_count,
                    "failure_count": self.failure_count
                })
                return result

            # Step 2: 获取未处理的消息
            unprocessed_messages = self._get_unprocessed_messages()
            result["total_unprocessed_found"] = len(unprocessed_messages)

            if not unprocessed_messages:
                logger.warning(f"[{self.name}] 未发现未处理的消息")
                with self._stats_lock:
                    self.success_count += 1
                result.update({
                    "status": "success",
                    "message": "未发现未处理的消息",
                    "total_messages_processed": 0,
                    "total_matched": 0,
                    "total_unmatched": 0,
                    "total_normal": 0,
                    "total_error": 0,
                    "total_candidate": 0,
                    "success_count": self.success_count,
                    "failure_count": self.failure_count
                })
                return result

            # Step 3: 批量判断消息状态
            self._judge_messages_batch(unprocessed_messages, keyword_map)

            # 更新统计信息
            with self._stats_lock:
                self.success_count += 1

            result.update({
                "status": "success",
                "message": f"判断完成: 匹配{self.total_matched}条, 未匹配{self.total_unmatched}条 (正常{self.total_normal}, 错误{self.total_error})",
                "total_messages_processed": self.total_messages_processed,
                "total_matched": self.total_matched,
                "total_unmatched": self.total_unmatched,
                "total_normal": self.total_normal,
                "total_error": self.total_error,
                "total_candidate": self.total_candidate,
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

    def _load_keywords(self) -> Dict[str, Dict[str, Any]]:
        """
        加载所有启用的关键词到内存

        返回格式:
        {
            "keyword1": {"type": "success", "priority": 100},
            "keyword2": {"type": "failed", "priority": 200},
            ...
        }

        Returns:
            关键词字典
        """
        db = SessionLocal()
        try:
            # 查询所有启用的关键词
            keywords = db.query(TrackerKeywordConfig).filter(
                TrackerKeywordConfig.enabled == True,
                TrackerKeywordConfig.dr == 0
            ).all()

            # 构建快速查找字典 (keyword -> info)
            # 如果存在重复keyword(历史数据),保留priority最高的
            keyword_map = {}
            for kw in keywords:
                if kw.keyword not in keyword_map:
                    keyword_map[kw.keyword] = {
                        "type": kw.keyword_type,
                        "priority": kw.priority,
                        "keyword_id": kw.keyword_id
                    }
                else:
                    # 如果重复,保留priority更高的
                    if kw.priority > keyword_map[kw.keyword]["priority"]:
                        keyword_map[kw.keyword] = {
                            "type": kw.keyword_type,
                            "priority": kw.priority,
                            "keyword_id": kw.keyword_id
                        }
                        logger.warning(f"发现重复关键词: {kw.keyword}, 保留高优先级记录")

            logger.info(f"加载关键词: {len(keyword_map)}条")
            return keyword_map

        except Exception as e:
            logger.error(f"加载关键词失败: {e}", exc_info=True)
            return {}
        finally:
            db.close()

    def _get_unprocessed_messages(self) -> List[TrackerMessageLog]:
        """
        获取所有未处理的消息

        Returns:
            未处理的消息列表
        """
        db = SessionLocal()
        try:
            # 查询未处理的消息(过滤掉空消息)
            messages = db.query(TrackerMessageLog).filter(
                TrackerMessageLog.is_processed == False,
                TrackerMessageLog.msg.isnot(None),
                TrackerMessageLog.msg != ''
            ).limit(self.BATCH_SIZE).all()

            logger.info(f"发现未处理消息: {len(messages)}条")
            return messages

        except Exception as e:
            logger.error(f"获取未处理消息失败: {e}", exc_info=True)
            return []
        finally:
            db.close()

    def _judge_messages_batch(self, messages: List[TrackerMessageLog], keyword_map: Dict[str, Dict[str, Any]]) -> None:
        """
        批量判断消息状态

        判断规则:
        - 精确匹配 (msg == keyword)
        - success池/ignored池 → 正常信息
        - failed池 → 错误信息
        - candidate池 → 不判断

        Args:
            messages: 消息列表
            keyword_map: 关键词字典
        """
        if not messages:
            return

        db = SessionLocal()
        try:
            for message in messages:
                try:
                    # 精确匹配: 检查msg是否在keyword_map中
                    if message.msg in keyword_map:
                        # 匹配成功
                        keyword_info = keyword_map[message.msg]
                        keyword_type = keyword_info["type"]

                        # 判断tracker状态
                        if keyword_type in ["success", "ignored"]:
                            # 正常信息
                            message.is_processed = True
                            message.keyword_type = keyword_type
                            # 注意: TrackerMessageLog模型中没有tracker_status字段
                            # 如果需要,可以添加该字段或使用keyword_type来表示状态

                            with self._stats_lock:
                                self.total_matched += 1
                                self.total_normal += 1

                            logger.info(f"匹配成功(正常): {message.tracker_host} | {message.msg[:50]} | 池:{keyword_type}")

                        elif keyword_type == "failed":
                            # 错误信息
                            message.is_processed = True
                            message.keyword_type = keyword_type

                            with self._stats_lock:
                                self.total_matched += 1
                                self.total_error += 1

                            logger.info(f"匹配成功(错误): {message.tracker_host} | {message.msg[:50]} | 池:failed")

                        elif keyword_type == "candidate":
                            # 候选池: 不判断
                            with self._stats_lock:
                                self.total_candidate += 1

                            logger.info(f"候选池跳过: {message.tracker_host} | {message.msg[:50]} | 池:candidate")
                            continue  # 不更新is_processed

                    else:
                        # 未匹配
                        with self._stats_lock:
                            self.total_unmatched += 1

                        logger.debug(f"未匹配: {message.tracker_host} | {message.msg[:50]}")

                    message.update_time = datetime.now()
                    with self._stats_lock:
                        self.total_messages_processed += 1

                except Exception as e:
                    logger.error(f"判断消息失败: {e}, msg={message.msg[:50] if message.msg else ''}")
                    continue

            # 一次性提交所有更改
            db.commit()
            logger.info(f"批量判断完成: 处理{len(messages)}条消息")

        except Exception as e:
            db.rollback()
            logger.error(f"批量判断消息失败: {e}", exc_info=True)
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
                "total_matched": self.total_matched,
                "total_unmatched": self.total_unmatched,
                "total_normal": self.total_normal,
                "total_error": self.total_error,
                "total_candidate": self.total_candidate,
                "last_execution_time": self.last_execution_time,
                "success_rate": (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0,
                "match_rate": (self.total_matched / self.total_messages_processed * 100) if self.total_messages_processed > 0 else 0
            }

    def get_schedule_config(self) -> Dict[str, Any]:
        """获取调度配置建议"""
        return {
            "cron_expression": "0 */30 * * *",  # 每30分钟执行一次
            "timezone": "Asia/Shanghai",
            "max_instances": 1,     # 防止重叠执行
            "coalesce": True,       # 合并错过的执行
            "misfire_grace_time": 900,  # 错过执行的宽限时间（15分钟）
            "default_interval": self.default_interval,
            "batch_size": self.BATCH_SIZE,
            "estimated_duration": "2-5 minutes"
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标(线程安全)"""
        with self._stats_lock:
            if self.execution_count == 0:
                return {
                    "average_messages_per_execution": 0,
                    "average_matched_per_execution": 0,
                    "average_unmatched_per_execution": 0,
                    "total_processing_time": "N/A"
                }

            return {
                "average_messages_per_execution": self.total_messages_processed / self.execution_count,
                "average_matched_per_execution": self.total_matched / self.execution_count,
                "average_unmatched_per_execution": self.total_unmatched / self.execution_count,
                "match_rate": (self.total_matched / self.total_messages_processed * 100) if self.total_messages_processed > 0 else 0,
                "normal_rate": (self.total_normal / self.total_matched * 100) if self.total_matched > 0 else 0,
                "error_rate": (self.total_error / self.total_matched * 100) if self.total_matched > 0 else 0,
                "task_reliability": (self.success_count / self.execution_count * 100)
            }
