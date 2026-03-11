from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.database import Base


class CronTask(Base):
    """定时任务表"""
    __tablename__ = "cron_task"

    task_id = Column(Integer, primary_key=True, autoincrement=True, comment="主键id")
    task_name = Column(String(200), nullable=False, comment="任务名称")
    task_code = Column(String(50), nullable=False, unique=True, comment="任务编码")
    task_status = Column(Integer, nullable=False, default=0, comment="任务状态，0等待运行，1运行中，2空闲")
    task_type = Column(Integer, nullable=False, comment="脚本类型，0-shell脚本，1-cmd脚本，2-powershell脚本，3-python脚本，4-python内部类，5-清理回收站任务")
    executor = Column(Text, nullable=False, comment="执行脚本内容或路径")
    enabled = Column(Boolean, nullable=False, default=True, comment="启用状态")
    last_execute_time = Column(DateTime, nullable=True, comment="上次运行时间")
    last_execute_duration = Column(Integer, nullable=True, comment="上次运行持续时间，单位秒")
    cron_plan = Column(String(100), nullable=False, comment="运行计划周期")
    description = Column(String(500), nullable=True, comment="任务描述")
    timeout_seconds = Column(Integer, nullable=True, default=3600, comment="超时时间(秒)")
    max_retry_count = Column(Integer, nullable=True, default=0, comment="最大重试次数")
    retry_interval = Column(Integer, nullable=True, default=300, comment="重试间隔(秒)")
    dr = Column(Integer, nullable=False, default=0, comment="逻辑删除标识，1为逻辑删除，0为未删除")
    create_time = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    update_time = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")
    create_by = Column(String(50), nullable=False, default="admin", comment="创建人")
    update_by = Column(String(50), nullable=False, default="admin", comment="更新人")

    def to_dict(self):
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "task_code": self.task_code,
            "task_status": self.task_status,
            "task_type": self.task_type,
            "executor": self.executor,
            "enabled": self.enabled,
            "last_execute_time": self.last_execute_time,
            "last_execute_duration": self.last_execute_duration,
            "cron_plan": self.cron_plan,
            "description": self.description,
            "timeout_seconds": self.timeout_seconds,
            "max_retry_count": self.max_retry_count,
            "retry_interval": self.retry_interval,
            "dr": self.dr,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "create_by": self.create_by,
            "update_by": self.update_by
        }

    @property
    def task_status_name(self):
        """任务状态名称"""
        status_map = {0: "等待运行", 1: "运行中", 2: "空闲"}
        return status_map.get(self.task_status, "未知")

    @property
    def task_type_name(self):
        """任务类型名称"""
        type_map = {
            0: "Shell脚本",
            1: "CMD脚本",
            2: "PowerShell脚本",
            3: "Python脚本",
            4: "Python内部类",
            5: "清理回收站"
        }
        return type_map.get(self.task_type, "未知")