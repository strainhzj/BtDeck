"""
SpeedScheduleRule 模型单元测试

测试 SpeedScheduleRule 的实例方法：
- to_dict: 转换为字典
- is_active_now: 判断规则当前是否生效
- get_days_of_week_list: 获取生效星期几列表
- validate_days_of_week: 验证 days_of_week 格式
- __repr__: 字符串表示

使用 MagicMock 绕过 ORM 初始化。
"""

from datetime import datetime, time
from unittest.mock import MagicMock, patch
import pytest


# ============================================================
# 辅助工具
# ============================================================

def _make_rule(**kwargs):
    """创建 SpeedScheduleRule 轻量级 mock 对象"""
    from app.models.speed_schedule_rules import SpeedScheduleRule

    defaults = {
        "id": 1,
        "downloader_setting_id": 1,
        "start_time": "08:00",
        "end_time": "18:00",
        "dl_speed_limit": 1024,
        "ul_speed_limit": 512,
        "dl_speed_unit": 0,
        "ul_speed_unit": 0,
        "sort_order": 0,
        "days_of_week": "0123456",
        "enabled": True,
    }
    defaults.update(kwargs)

    rule = MagicMock(spec=SpeedScheduleRule)
    for key, value in defaults.items():
        setattr(rule, key, value)

    # 绑定方法
    rule.to_dict = SpeedScheduleRule.to_dict.__get__(rule, SpeedScheduleRule)
    rule.is_active_now = SpeedScheduleRule.is_active_now.__get__(rule, SpeedScheduleRule)
    rule.get_days_of_week_list = SpeedScheduleRule.get_days_of_week_list.__get__(rule, SpeedScheduleRule)
    rule.validate_days_of_week = SpeedScheduleRule.validate_days_of_week.__get__(rule, SpeedScheduleRule)

    return rule


# ============================================================
# to_dict 测试
# ============================================================

class TestToDict:
    """to_dict 方法测试"""

    def test_返回包含所有字段(self):
        """to_dict 应返回包含所有字段的字典"""
        rule = _make_rule()
        result = rule.to_dict()

        assert "id" in result
        assert "sort_order" in result
        assert "start_time" in result
        assert "end_time" in result
        assert "weekdays" in result
        assert "download" in result
        assert "upload" in result
        assert "enabled" in result

    def test_下载和上传字段正确(self):
        """download 和 upload 子字典应正确"""
        rule = _make_rule(dl_speed_limit=2048, ul_speed_limit=1024)
        result = rule.to_dict()

        assert result["download"]["speed_limit"] == 2048
        assert result["upload"]["speed_limit"] == 1024
        assert result["download"]["enabled"] is True
        assert result["upload"]["enabled"] is True

    def test_速度为0时enabled为False(self):
        """速度限制为0时 enabled 应为 False"""
        rule = _make_rule(dl_speed_limit=0, ul_speed_limit=0)
        result = rule.to_dict()

        assert result["download"]["enabled"] is False
        assert result["upload"]["enabled"] is False

    def test_weekdays转换正确(self):
        """days_of_week 字符串应转为整数列表"""
        rule = _make_rule(days_of_week="12345")
        result = rule.to_dict()

        assert result["weekdays"] == [1, 2, 3, 4, 5]

    def test_days_of_week为空时weekdays为空列表(self):
        """days_of_week 为空时 weekdays 应为空列表"""
        rule = _make_rule(days_of_week="")
        result = rule.to_dict()

        assert result["weekdays"] == []

    def test_值正确映射(self):
        """所有字段值应正确映射"""
        rule = _make_rule(id=42, start_time="09:30", end_time="17:00")
        result = rule.to_dict()

        assert result["id"] == 42
        assert result["start_time"] == "09:30"
        assert result["end_time"] == "17:00"


# ============================================================
# is_active_now 测试
# ============================================================

class TestIsActiveNow:
    """is_active_now 方法测试"""

    def test_禁用规则返回False(self):
        """enabled=False 时应返回 False"""
        rule = _make_rule(enabled=False)
        assert rule.is_active_now() is False

    def test_时间为None返回False(self):
        """start_time 或 end_time 为 None 时应返回 False"""
        rule = _make_rule(start_time=None, end_time="18:00")
        assert rule.is_active_now() is False

        rule2 = _make_rule(start_time="08:00", end_time=None)
        assert rule2.is_active_now() is False

    def test_days_of_week为空返回False(self):
        """days_of_week 为空时应返回 False"""
        rule = _make_rule(days_of_week="")
        assert rule.is_active_now() is False

    def test_当前时间在范围内且星期匹配(self):
        """当前时间在范围内且星期几匹配时应返回 True"""
        rule = _make_rule(start_time="00:00", end_time="23:59", days_of_week="0123456")
        with patch("app.models.speed_schedule_rules.datetime") as mock_dt:
            mock_now = datetime(2026, 4, 3, 14, 30, 0)  # 周五
            mock_dt.now.return_value = mock_now
            mock_dt.strptime.side_effect = lambda fmt, *a: datetime.strptime(fmt, *a)
            assert rule.is_active_now() is True

    def test_旧格式7表示周日(self):
        """旧格式中使用 7 表示周日应正确处理"""
        rule = _make_rule(start_time="00:00", end_time="23:59", days_of_week="1234567")
        with patch("app.models.speed_schedule_rules.datetime") as mock_dt:
            mock_now = datetime(2026, 4, 5, 12, 0, 0)  # 周日
            mock_dt.now.return_value = mock_now
            mock_dt.strptime.side_effect = lambda fmt, *a: datetime.strptime(fmt, *a)
            assert rule.is_active_now() is True


# ============================================================
# get_days_of_week_list 测试
# ============================================================

class TestGetDaysOfWeekList:
    """get_days_of_week_list 方法测试"""

    def test_全部天数(self):
        """0123456 应返回全部天"""
        rule = _make_rule(days_of_week="0123456")
        result = rule.get_days_of_week_list()
        assert "周一" in result
        assert "周二" in result
        assert "周六" in result
        assert "周日" in result
        assert len(result) == 7

    def test_工作日(self):
        """01234 应返回周一到周五"""
        rule = _make_rule(days_of_week="01234")
        result = rule.get_days_of_week_list()
        assert result == ["周一", "周二", "周三", "周四", "周五"]

    def test_空字符串(self):
        """空字符串应返回空列表"""
        rule = _make_rule(days_of_week="")
        result = rule.get_days_of_week_list()
        assert result == []

    def test_仅周末(self):
        """56 应返回周六和周日"""
        rule = _make_rule(days_of_week="56")
        result = rule.get_days_of_week_list()
        assert "周六" in result
        assert "周日" in result


# ============================================================
# validate_days_of_week 测试
# ============================================================

class TestValidateDaysOfWeek:
    """validate_days_of_week 方法测试"""

    def test_有效字符串(self):
        """有效字符串应返回 True"""
        rule = _make_rule()
        assert rule.validate_days_of_week("0123456") is True

    def test_单个数字(self):
        """单个有效数字应返回 True"""
        rule = _make_rule()
        assert rule.validate_days_of_week("0") is True

    def test_空字符串(self):
        """空字符串应返回 False"""
        rule = _make_rule()
        assert rule.validate_days_of_week("") is False

    def test_超过7位(self):
        """超过 7 位应返回 False"""
        rule = _make_rule()
        assert rule.validate_days_of_week("01234567") is False

    def test_包含非法字符(self):
        """包含 7/8/9 应返回 False"""
        rule = _make_rule()
        assert rule.validate_days_of_week("789") is False

    def test_重复数字(self):
        """重复数字应返回 False"""
        rule = _make_rule()
        assert rule.validate_days_of_week("001") is False

    def test_None(self):
        """None 应返回 False"""
        rule = _make_rule()
        assert rule.validate_days_of_week(None) is False

    def test_字母字符(self):
        """字母字符应返回 False"""
        rule = _make_rule()
        assert rule.validate_days_of_week("abc") is False


# ============================================================
# __repr__ 测试
# ============================================================

class TestRepr:
    """__repr__ 方法测试"""

    def test_repr包含关键信息(self):
        """__repr__ 应包含 id, start_time, end_time"""
        from app.models.speed_schedule_rules import SpeedScheduleRule
        rule = _make_rule(id=1, start_time="08:00", end_time="18:00")
        # 直接调用原始 __repr__ 方法
        result = SpeedScheduleRule.__repr__(rule)

        assert "id=1" in result
        assert "08:00" in result
        assert "18:00" in result
