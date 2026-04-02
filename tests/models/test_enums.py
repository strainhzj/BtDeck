# -*- coding: utf-8 -*-
"""
SpeedUnitEnum 和 ScheduleDayOfWeekEnum 的单元测试
"""
import pytest
from app.models.enums import SpeedUnitEnum, ScheduleDayOfWeekEnum


class TestSpeedUnitEnum:
    """SpeedUnitEnum 速度单位枚举测试"""

    def test_from_value_0_returns_kb(self):
        """整数值 0 应返回 KB_PER_SEC"""
        assert SpeedUnitEnum.from_value(0) == SpeedUnitEnum.KB_PER_SEC

    def test_from_value_1_returns_mb(self):
        """整数值 1 应返回 MB_PER_SEC"""
        assert SpeedUnitEnum.from_value(1) == SpeedUnitEnum.MB_PER_SEC

    def test_from_value_invalid_raises(self):
        """无效整数值应抛出 ValueError"""
        with pytest.raises(ValueError, match="无效的速度单位"):
            SpeedUnitEnum.from_value(99)

    def test_from_value_negative_raises(self):
        """负数应抛出 ValueError"""
        with pytest.raises(ValueError, match="无效的速度单位"):
            SpeedUnitEnum.from_value(-1)

    def test_to_string_kb(self):
        """KB_PER_SEC 的字符串表示应为 'KB/s'"""
        assert SpeedUnitEnum.KB_PER_SEC.to_string() == "KB/s"

    def test_to_string_mb(self):
        """MB_PER_SEC 的字符串表示应为 'MB/s'"""
        assert SpeedUnitEnum.MB_PER_SEC.to_string() == "MB/s"


class TestScheduleDayOfWeekEnum:
    """ScheduleDayOfWeekEnum 星期枚举测试"""

    def test_from_value_0_to_6(self):
        """整数值 0-6 应正确映射为周一到周日"""
        expected = [
            ScheduleDayOfWeekEnum.MONDAY,
            ScheduleDayOfWeekEnum.TUESDAY,
            ScheduleDayOfWeekEnum.WEDNESDAY,
            ScheduleDayOfWeekEnum.THURSDAY,
            ScheduleDayOfWeekEnum.FRIDAY,
            ScheduleDayOfWeekEnum.SATURDAY,
            ScheduleDayOfWeekEnum.SUNDAY,
        ]
        for i, exp in enumerate(expected):
            assert ScheduleDayOfWeekEnum.from_value(i) == exp

    def test_from_value_7_returns_everyday(self):
        """整数值 7 应返回 EVERYDAY（每天）"""
        assert ScheduleDayOfWeekEnum.from_value(7) == ScheduleDayOfWeekEnum.EVERYDAY

    def test_from_value_invalid_raises(self):
        """无效值应抛出 ValueError"""
        with pytest.raises(ValueError, match="无效的星期值"):
            ScheduleDayOfWeekEnum.from_value(8)

    def test_to_chinese_all_days(self):
        """每个枚举值应有正确的中文表示"""
        expected = {
            ScheduleDayOfWeekEnum.MONDAY: "周一",
            ScheduleDayOfWeekEnum.TUESDAY: "周二",
            ScheduleDayOfWeekEnum.WEDNESDAY: "周三",
            ScheduleDayOfWeekEnum.THURSDAY: "周四",
            ScheduleDayOfWeekEnum.FRIDAY: "周五",
            ScheduleDayOfWeekEnum.SATURDAY: "周六",
            ScheduleDayOfWeekEnum.SUNDAY: "周日",
            ScheduleDayOfWeekEnum.EVERYDAY: "每天",
        }
        for enum_val, chinese in expected.items():
            assert enum_val.to_chinese() == chinese
