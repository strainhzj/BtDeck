# -*- coding: utf-8 -*-
"""
下载器类型枚举

用于类型安全和代码可读性

注意：DownloaderTypeEnum 已迁移到 app.models.setting_templates，使用整数枚举(0/1)
本文件保留其他枚举定义（速度单位、星期等）
"""
import enum
import logging

logger = logging.getLogger(__name__)


class SpeedUnitEnum(enum.IntEnum):
    """速度单位枚举

    用于下载器设置中的速度单位
    """
    KB_PER_SEC = 0  # KB/s
    MB_PER_SEC = 1  # MB/s

    @classmethod
    def from_value(cls, value: int) -> 'SpeedUnitEnum':
        """从整数值获取枚举

        Args:
            value: 单位整数值 (0, 1)

        Returns:
            SpeedUnitEnum: 对应的枚举值

        Raises:
            ValueError: 如果值无效
        """
        try:
            return cls(value)
        except ValueError:
            valid_values = [e.value for e in cls]
            raise ValueError(
                f"无效的速度单位: '{value}'. "
                f"有效值为: {valid_values} (0=KB/s, 1=MB/s)"
            )

    def to_string(self) -> str:
        """转换为字符串表示

        Returns:
            str: "KB/s" 或 "MB/s"
        """
        return "KB/s" if self == SpeedUnitEnum.KB_PER_SEC else "MB/s"


class ScheduleDayOfWeekEnum(enum.IntEnum):
    """星期枚举

    用于分时段速度规则
    """
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6
    EVERYDAY = 7  # 每天都适用

    @classmethod
    def from_value(cls, value: int) -> 'ScheduleDayOfWeekEnum':
        """从整数值获取枚举

        Args:
            value: 星期整数值 (0-7)

        Returns:
            ScheduleDayOfWeekEnum: 对应的枚举值

        Raises:
            ValueError: 如果值无效
        """
        try:
            return cls(value)
        except ValueError:
            valid_values = [e.value for e in cls]
            raise ValueError(
                f"无效的星期值: '{value}'. "
                f"有效值为: {valid_values} (0=周一, 7=每天)"
            )

    def to_chinese(self) -> str:
        """转换为中文表示

        Returns:
            str: "周一", "周二", ..., "每天"
        """
        chinese_map = {
            ScheduleDayOfWeekEnum.MONDAY: "周一",
            ScheduleDayOfWeekEnum.TUESDAY: "周二",
            ScheduleDayOfWeekEnum.WEDNESDAY: "周三",
            ScheduleDayOfWeekEnum.THURSDAY: "周四",
            ScheduleDayOfWeekEnum.FRIDAY: "周五",
            ScheduleDayOfWeekEnum.SATURDAY: "周六",
            ScheduleDayOfWeekEnum.SUNDAY: "周日",
            ScheduleDayOfWeekEnum.EVERYDAY: "每天",
        }
        return chinese_map[self]


# 导出所有枚举
__all__ = [
    'SpeedUnitEnum',
    'ScheduleDayOfWeekEnum',
]
