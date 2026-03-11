from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TaskLogs(Base):
    """任务日志表"""
    __tablename__ = "task_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("cron_task.task_id"), nullable=True, comment="关联的定时任务ID")
    task_name = Column(String(100), nullable=False, comment="任务名称")
    task_type = Column(Integer, nullable=True, comment="任务类型")
    start_time = Column(DateTime, nullable=False, comment="开始时间")
    end_time = Column(DateTime, nullable=True, comment="结束时间")
    duration = Column(Integer, nullable=True, comment="持续时间(秒)")
    success = Column(Boolean, nullable=False, comment="执行结果")
    log_detail = Column(String(2000), nullable=True, comment="执行日志")
    dr = Column(Integer, nullable=False, default=0, comment="逻辑删除标识")

    def _format_datetime(self, dt):
        """
        格式化 datetime 对象为字符串

        Args:
            dt: datetime 对象或其他类型

        Returns:
            ISO 格式的 datetime 字符串，如果输入无效则返回 None
        """
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.isoformat()
        if isinstance(dt, str):
            # 尝试解析字符串格式的 datetime
            try:
                # 如果已经是 ISO 格式，直接返回
                if '-' in dt and (':' in dt or 'T' in dt):
                    return dt
            except:
                pass
        # 非法的 datetime 值，记录警告并返回 None
        logger.warning(f"Invalid datetime value in TaskLogs.log_id={self.log_id}: {dt} (type: {type(dt)})")
        return None

    def to_dict(self):
        """
        转换为字典，包含数据验证和格式化

        Returns:
            包含任务日志数据的字典，datetime 字段会被格式化为 ISO 字符串
        """
        return {
            "log_id": self.log_id,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_type": self.task_type,
            "start_time": self._format_datetime(self.start_time),
            "end_time": self._format_datetime(self.end_time),
            "duration": self.duration,
            "success": self.success,
            "log_detail": self.log_detail,
            "dr": self.dr
        }