# -*- coding: utf-8 -*-
"""
分时段速度规则模型

用于存储按时间段和星期几的速度限制规则
"""
from datetime import datetime, time
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base
import logging
import re

logger = logging.getLogger(__name__)


class SpeedScheduleRule(Base):
    """
    分时段速度规则表

    存储按时间段和星期几的速度限制规则
    """
    __tablename__ = "speed_schedule_rules"

    # 主键
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 外键：关联到 downloader_settings 表
    downloader_setting_id = Column(
        Integer,
        ForeignKey('downloader_settings.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment='下载器配置ID，关联downloader_settings表'
    )

    # 时间范围（使用 String 存储，SQLite 不支持 TIME 类型）
    start_time = Column(
        String(5),  # 格式: "HH:MM"
        nullable=False,
        comment='开始时间，格式"HH:MM"，如"08:00"'
    )

    end_time = Column(
        String(5),  # 格式: "HH:MM"
        nullable=False,
        comment='结束时间，格式"HH:MM"，如"18:00"'
    )

    # 表约束
    __table_args__ = (
        CheckConstraint('start_time < end_time', name='ck_start_time_before_end_time'),
        CheckConstraint(
            "days_of_week >= '0' AND days_of_week <= '6543210'",
            name='ck_days_of_week_format'
        ),
    )

    # 速度限制
    dl_speed_limit = Column(
        Integer,
        nullable=False,
        default=0,
        comment='下载速度限制（KB/s），0表示不限速'
    )

    ul_speed_limit = Column(
        Integer,
        nullable=False,
        default=0,
        comment='上传速度限制（KB/s），0表示不限速'
    )

    # 速度单位（0=KB/s, 1=MB/s）
    dl_speed_unit = Column(
        Integer,
        nullable=False,
        server_default='0',
        comment='下载速度单位：0=KB/s, 1=MB/s'
    )

    ul_speed_unit = Column(
        Integer,
        nullable=False,
        server_default='0',
        comment='上传速度单位：0=KB/s, 1=MB/s'
    )

    # 规则排序（同一下载器内）
    sort_order = Column(
        Integer,
        nullable=False,
        server_default='0',
        comment='规则排序（同一下载器内），数字越小优先级越高'
    )

    # 生效星期几（字符串，如"0123456"表示每天都生效，"12345"表示周一到周五生效）
    days_of_week = Column(
        String(7),
        nullable=False,
        default="0123456",
        comment='生效星期几，0=周日，1=周一，...，6=周六'
    )

    # 状态
    enabled = Column(
        Boolean,
        nullable=False,
        default=True,
        comment='是否启用'
    )

    # 时间戳
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment='创建时间'
    )

    # 关系定义
    # 关联到下载器配置（多对一）
    downloader_setting = relationship(
        "DownloaderSetting",
        back_populates="speed_schedule_rules"
    )

    def __init__(
        self,
        downloader_setting_id=None,
        start_time=None,
        end_time=None,
        dl_speed_limit=0,
        ul_speed_limit=0,
        dl_speed_unit=0,
        ul_speed_unit=0,
        sort_order=0,
        days_of_week="0123456",
        enabled=True,
        **kwargs
    ):
        super().__init__(**kwargs)
        if downloader_setting_id is not None:
            self.downloader_setting_id = downloader_setting_id

        # 处理时间参数：支持 datetime.time 对象或字符串
        if start_time is not None:
            if isinstance(start_time, time):
                self.start_time = start_time.strftime("%H:%M")
            else:
                self.start_time = start_time

        if end_time is not None:
            if isinstance(end_time, time):
                self.end_time = end_time.strftime("%H:%M")
            else:
                self.end_time = end_time

        if dl_speed_limit is not None:
            self.dl_speed_limit = dl_speed_limit
        if ul_speed_limit is not None:
            self.ul_speed_limit = ul_speed_limit
        if dl_speed_unit is not None:
            self.dl_speed_unit = dl_speed_unit
        if ul_speed_unit is not None:
            self.ul_speed_unit = ul_speed_unit
        if sort_order is not None:
            self.sort_order = sort_order
        if days_of_week is not None:
            self.days_of_week = days_of_week
        if enabled is not None:
            self.enabled = enabled

    def is_active_now(self):
        """
        判断规则当前是否生效

        Returns:
            bool: 如果规则当前生效返回True，否则返回False
        """
        if not self.enabled:
            return False

        if self.start_time is None or self.end_time is None:
            return False

        now = datetime.now()
        current_weekday = now.weekday()  # 0=周一，6=周日
        if not self.days_of_week:
            return False

        # 兼容旧格式：1-7（周一=1，周日=7）
        is_legacy = any(ch in "7" for ch in self.days_of_week)
        if is_legacy:
            if str(current_weekday + 1) not in self.days_of_week:
                return False
        else:
            if str(current_weekday) not in self.days_of_week:
                return False

        # 将字符串时间转换为 time 对象进行比较
        current_time = now.time()
        start_time_obj = datetime.strptime(self.start_time, "%H:%M").time()
        end_time_obj = datetime.strptime(self.end_time, "%H:%M").time()

        return start_time_obj <= current_time <= end_time_obj

    def get_days_of_week_list(self):
        """
        获取生效星期几的列表

        Returns:
            list: 星期几列表，如 ["周一", "周二", "周三"]
        """
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        result = []
        for day_char in self.days_of_week:
            if day_char.isdigit():
                idx = int(day_char)
                if 0 <= idx <= 6:
                    result.append(weekday_names[idx])
        return result

    def validate_days_of_week(self, days_str):
        """
        验证days_of_week格式是否正确

        Args:
            days_str (str): 待验证的字符串

        Returns:
            bool: 格式正确返回True，否则返回False
        """
        if not days_str or len(days_str) > 7:
            return False

        # 检查是否只包含0-6的数字
        pattern = re.compile(r'^[0-6]{1,7}$')
        if not pattern.match(days_str):
            return False

        # 检查是否有重复
        if len(set(days_str)) != len(days_str):
            return False

        return True

    def to_dict(self):
        """
        转换为字典格式

        Returns:
            dict: 模型数据的字典表示
        """
        return {
            "id": self.id,
            "sort_order": self.sort_order,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "weekdays": [int(day) for day in self.days_of_week] if self.days_of_week else [],
            "download": {
                "enabled": self.dl_speed_limit > 0,
                "speed_limit": self.dl_speed_limit,
                "speed_unit": self.dl_speed_unit
            },
            "upload": {
                "enabled": self.ul_speed_limit > 0,
                "speed_limit": self.ul_speed_limit,
                "speed_unit": self.ul_speed_unit
            },
            "enabled": self.enabled
        }

    def __repr__(self):
        return (
            f"<SpeedScheduleRule(id={self.id}, "
            f"downloader_setting_id={self.downloader_setting_id}, "
            f"start_time={self.start_time}, "
            f"end_time={self.end_time}, "
            f"enabled={self.enabled})>"
        )
