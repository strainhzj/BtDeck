# -*- coding: utf-8 -*-
"""
SpeedScheduleService 的单元测试

测试 calculate_effective_speed 和 get_active_rules 方法。
get_active_rules 通过 mock DB 来隔离数据库依赖。
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.speed_schedule_service import SpeedScheduleService


class TestCalculateEffectiveSpeed:
    """SpeedScheduleService.calculate_effective_speed 测试"""

    def test_empty_rules_returns_zeros(self):
        """空规则列表应返回全零速度"""
        result = SpeedScheduleService.calculate_effective_speed([])
        assert result == {"dl_speed": 0, "dl_unit": 0, "ul_speed": 0, "ul_unit": 0}

    def test_single_rule_dl_only(self):
        """单条规则仅有下载速度时，上传速度应为 0"""
        rules = [{"dl_speed_limit": 500, "dl_speed_unit": 1, "ul_speed_limit": 0, "ul_speed_unit": 0}]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_speed"] == 500
        assert result["dl_unit"] == 1
        assert result["ul_speed"] == 0
        assert result["ul_unit"] == 0

    def test_single_rule_ul_only(self):
        """单条规则仅有上传速度时，下载速度应为 0"""
        rules = [{"dl_speed_limit": 0, "dl_speed_unit": 0, "ul_speed_limit": 300, "ul_speed_unit": 0}]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_speed"] == 0
        assert result["ul_speed"] == 300
        assert result["ul_unit"] == 0

    def test_single_rule_both_speeds(self):
        """单条规则同时包含下载和上传速度"""
        rules = [{"dl_speed_limit": 1024, "dl_speed_unit": 0, "ul_speed_limit": 512, "ul_speed_unit": 0}]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_speed"] == 1024
        assert result["dl_unit"] == 0
        assert result["ul_speed"] == 512
        assert result["ul_unit"] == 0

    def test_multiple_rules_first_priority_wins(self):
        """多条规则时，第一个非零值的优先级最高（sort_order越小越优先）"""
        rules = [
            {"dl_speed_limit": 100, "dl_speed_unit": 0, "ul_speed_limit": 50, "ul_speed_unit": 0},
            {"dl_speed_limit": 200, "dl_speed_unit": 1, "ul_speed_limit": 80, "ul_speed_unit": 1},
        ]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_speed"] == 100
        assert result["dl_unit"] == 0
        assert result["ul_speed"] == 50
        assert result["ul_unit"] == 0

    def test_multiple_rules_fill_gaps(self):
        """第一条规则仅提供下载速度，第二条填补上传速度"""
        rules = [
            {"dl_speed_limit": 500, "dl_speed_unit": 1, "ul_speed_limit": 0, "ul_speed_unit": 0},
            {"dl_speed_limit": 0, "dl_speed_unit": 0, "ul_speed_limit": 200, "ul_speed_unit": 0},
        ]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_speed"] == 500
        assert result["ul_speed"] == 200

    def test_zero_speed_limit_ignored(self):
        """dl_speed_limit 为 0 的规则应被跳过"""
        rules = [
            {"dl_speed_limit": 0, "dl_speed_unit": 0, "ul_speed_limit": 0, "ul_speed_unit": 0},
            {"dl_speed_limit": 300, "dl_speed_unit": 1, "ul_speed_limit": 100, "ul_speed_unit": 0},
        ]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_speed"] == 300
        assert result["ul_speed"] == 100

    def test_missing_speed_fields_use_defaults(self):
        """规则中缺少速度字段时应使用默认值 0"""
        rules = [{"dl_speed_limit": 100}]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_speed"] == 100
        assert result["ul_speed"] == 0

    def test_unit_preserved_from_first_matching_rule(self):
        """速度单位应跟随第一条生效规则"""
        rules = [
            {"dl_speed_limit": 500, "dl_speed_unit": 1, "ul_speed_limit": 0, "ul_speed_unit": 0},
            {"dl_speed_limit": 0, "dl_speed_unit": 0, "ul_speed_limit": 200, "ul_speed_unit": 1},
        ]
        result = SpeedScheduleService.calculate_effective_speed(rules)
        assert result["dl_unit"] == 1
        assert result["ul_unit"] == 1


class TestGetActiveRules:
    """SpeedScheduleService.get_active_rules 测试"""

    def _make_mock_row(self, data: dict):
        """创建模拟数据库行对象"""
        mock_row = MagicMock()
        mock_row._mapping = data
        return mock_row

    def test_returns_matching_rules(self):
        """应返回当前时间段匹配的规则"""
        mock_db = MagicMock()
        row_data = {
            "id": 1, "sort_order": 1, "start_time": "08:00", "end_time": "18:00",
            "dl_speed_limit": 500, "dl_speed_unit": 0,
            "ul_speed_limit": 200, "ul_speed_unit": 0,
        }
        mock_row = self._make_mock_row(row_data)
        mock_db.execute.return_value.fetchall.return_value = [mock_row]

        test_time = datetime(2026, 3, 30, 10, 0)  # 周一 10:00
        results = SpeedScheduleService.get_active_rules(mock_db, downloader_setting_id=1, current_time=test_time)

        assert len(results) == 1
        assert results[0]["dl_speed_limit"] == 500

    def test_no_matching_rules_returns_empty(self):
        """没有匹配规则时应返回空列表"""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []
        test_time = datetime(2026, 3, 30, 23, 0)  # 周一 23:00

        results = SpeedScheduleService.get_active_rules(mock_db, downloader_setting_id=1, current_time=test_time)
        assert results == []

    def test_weekday_correct_for_monday(self):
        """周一的 weekday 应为 0"""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []
        # 2026-03-30 是周一
        test_time = datetime(2026, 3, 30, 10, 0)
        SpeedScheduleService.get_active_rules(mock_db, downloader_setting_id=1, current_time=test_time)

        call_args = mock_db.execute.call_args
        params = call_args[0][1]  # 第二个位置参数是 params dict
        assert params["weekday_pattern"] == "%0%"
