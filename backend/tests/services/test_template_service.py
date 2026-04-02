# -*- coding: utf-8 -*-
"""
TemplateService 的单元测试

测试 validate_template / _validate_days_of_week / normalize_schedule_time 方法。
所有 DB 相关依赖通过 mock 隔离。
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import time


class TestNormalizeScheduleTime:
    """normalize_schedule_time 函数测试"""

    def test_valid_hhmm_format(self):
        """标准 HH:MM 格式应原样返回"""
        from app.services.template_service import normalize_schedule_time
        assert normalize_schedule_time("08:30") == "08:30"

    def test_valid_hhmmss_format(self):
        """HH:MM:SS 格式应截断为 HH:MM"""
        from app.services.template_service import normalize_schedule_time
        assert normalize_schedule_time("08:30:45") == "08:30"

    def test_time_object(self):
        """datetime.time 对象应格式化为 HH:MM"""
        from app.services.template_service import normalize_schedule_time
        assert normalize_schedule_time(time(14, 5)) == "14:05"

    def test_invalid_string_raises(self):
        """无效字符串应抛出 ValueError"""
        from app.services.template_service import normalize_schedule_time
        with pytest.raises(ValueError, match="invalid schedule time"):
            normalize_schedule_time("25:00")

    def test_non_time_non_string_raises(self):
        """非字符串非时间类型应抛出 ValueError"""
        from app.services.template_service import normalize_schedule_time
        with pytest.raises(ValueError, match="invalid schedule time"):
            normalize_schedule_time(12345)

    def test_empty_string_raises(self):
        """空字符串应抛出 ValueError"""
        from app.services.template_service import normalize_schedule_time
        with pytest.raises(ValueError, match="invalid schedule time"):
            normalize_schedule_time("")


class TestValidateTemplate:
    """TemplateService.validate_template 测试"""

    @pytest.fixture
    def service(self):
        """创建 TemplateService 实例，db 为 mock"""
        from app.services.template_service import TemplateService
        return TemplateService(db=MagicMock())

    def _valid_config(self, **overrides):
        """生成一个有效的模板配置"""
        config = {
            "dl_speed_limit": 1024,
            "ul_speed_limit": 512,
            "speed_unit": 0,
        }
        config.update(overrides)
        return config

    def test_valid_minimal_config(self, service):
        """最简有效配置应通过验证"""
        ok, msg = service.validate_template(self._valid_config(), downloader_type=0)
        assert ok is True
        assert msg == ""

    def test_missing_dl_speed_limit(self, service):
        """缺少 dl_speed_limit 应失败"""
        config = self._valid_config()
        del config["dl_speed_limit"]
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "dl_speed_limit" in msg

    def test_missing_ul_speed_limit(self, service):
        """缺少 ul_speed_limit 应失败"""
        config = self._valid_config()
        del config["ul_speed_limit"]
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "ul_speed_limit" in msg

    def test_missing_speed_unit(self, service):
        """缺少 speed_unit 应失败"""
        config = self._valid_config()
        del config["speed_unit"]
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "speed_unit" in msg

    def test_negative_dl_speed(self, service):
        """负的下载速度应失败"""
        ok, msg = service.validate_template(self._valid_config(dl_speed_limit=-1), downloader_type=0)
        assert ok is False
        assert "下载速度" in msg

    def test_negative_ul_speed(self, service):
        """负的上传速度应失败"""
        ok, msg = service.validate_template(self._valid_config(ul_speed_limit=-1), downloader_type=0)
        assert ok is False
        assert "上传速度" in msg

    def test_invalid_speed_unit(self, service):
        """无效速度单位（非 0/1）应失败"""
        ok, msg = service.validate_template(self._valid_config(speed_unit=5), downloader_type=0)
        assert ok is False
        assert "速度单位" in msg

    def test_valid_schedule_rules(self, service):
        """有效的分时段规则应通过"""
        config = self._valid_config(schedule_rules=[
            {"start_time": "08:00", "end_time": "18:00", "days_of_week": "01234"}
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is True

    def test_schedule_rules_missing_time(self, service):
        """分时段规则缺少时间字段应失败"""
        config = self._valid_config(schedule_rules=[
            {"days_of_week": "01234"}  # 缺少 start_time / end_time
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "时间字段" in msg

    def test_schedule_rules_missing_days_of_week(self, service):
        """分时段规则缺少 days_of_week 应失败"""
        config = self._valid_config(schedule_rules=[
            {"start_time": "08:00", "end_time": "18:00"}
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "days_of_week" in msg

    def test_schedule_rules_invalid_days_format(self, service):
        """days_of_week 格式无效应失败"""
        config = self._valid_config(schedule_rules=[
            {"start_time": "08:00", "end_time": "18:00", "days_of_week": "abc"}
        ])
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "days_of_week" in msg

    def test_advanced_settings_qbittorrent_valid(self, service):
        """qBittorrent 高级配置有效值应通过"""
        config = self._valid_config(advanced_settings={
            "max_connec": 100, "max_numconn": 50, "max_uploads": 20
        })
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is True

    def test_advanced_settings_qbittorrent_negative_value(self, service):
        """qBittorrent 高级配置负值应失败"""
        config = self._valid_config(advanced_settings={"max_connec": -1})
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "max_connec" in msg

    def test_advanced_settings_transmission_valid(self, service):
        """Transmission 高级配置有效值应通过"""
        config = self._valid_config(advanced_settings={
            "peer-limit-global": 200, "peer-limit-per-torrent": 50
        })
        ok, msg = service.validate_template(config, downloader_type=1)
        assert ok is True

    def test_advanced_settings_transmission_negative(self, service):
        """Transmission 高级配置负值应失败"""
        config = self._valid_config(advanced_settings={"peer-limit-global": -5})
        ok, msg = service.validate_template(config, downloader_type=1)
        assert ok is False
        assert "peer-limit-global" in msg

    def test_advanced_settings_not_dict(self, service):
        """advanced_settings 不是字典应失败"""
        config = self._valid_config(advanced_settings="not-a-dict")
        ok, msg = service.validate_template(config, downloader_type=0)
        assert ok is False
        assert "对象" in msg


class TestValidateDaysOfWeek:
    """TemplateService._validate_days_of_week 测试"""

    @pytest.fixture
    def service(self):
        from app.services.template_service import TemplateService
        return TemplateService(db=MagicMock())

    def test_valid_single_day(self, service):
        """单个有效日期数字应通过"""
        assert service._validate_days_of_week("0") is True

    def test_valid_multiple_days(self, service):
        """多个有效日期数字应通过"""
        assert service._validate_days_of_week("01234") is True

    def test_valid_all_days(self, service):
        """0-6 全部日期应通过"""
        assert service._validate_days_of_week("0123456") is True

    def test_empty_string(self, service):
        """空字符串应失败"""
        assert service._validate_days_of_week("") is False

    def test_too_long_string(self, service):
        """超过 7 位应失败"""
        assert service._validate_days_of_week("01234567") is False

    def test_out_of_range_digit(self, service):
        """包含 7/8/9 等超范围数字应失败"""
        assert service._validate_days_of_week("789") is False

    def test_duplicate_digits(self, service):
        """重复数字应失败"""
        assert service._validate_days_of_week("001") is False

    def test_non_digit_chars(self, service):
        """非数字字符应失败"""
        assert service._validate_days_of_week("abc") is False

    def test_none_value(self, service):
        """None 值应失败"""
        assert service._validate_days_of_week(None) is False
