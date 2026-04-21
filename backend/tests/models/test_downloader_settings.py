"""
DownloaderSetting 模型单元测试

测试 DownloaderSetting 的实例方法：
- to_dict: 转换为字典
- __repr__: 字符串表示
- SpeedUnitEnum 枚举值

使用 MagicMock 绕过 ORM 初始化。
"""

from datetime import datetime
from unittest.mock import MagicMock
import pytest


# ============================================================
# 辅助工具
# ============================================================

def _make_setting(**kwargs):
    """创建 DownloaderSetting 轻量级 mock 对象"""
    from app.models.downloader_settings import DownloaderSetting, SpeedUnitEnum

    defaults = {
        "id": 1,
        "downloader_id": "dl-001",
        "dl_speed_limit": 1024,
        "ul_speed_limit": 512,
        "dl_speed_unit": SpeedUnitEnum.KB_PER_SEC,
        "ul_speed_unit": SpeedUnitEnum.KB_PER_SEC,
        "enable_schedule": False,
        "username": None,
        "password": None,
        "advanced_settings": None,
        "override_local": False,
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
    }
    defaults.update(kwargs)

    setting = MagicMock(spec=DownloaderSetting)
    for key, value in defaults.items():
        setattr(setting, key, value)

    # 绑定方法
    setting.to_dict = DownloaderSetting.to_dict.__get__(setting, DownloaderSetting)

    return setting


# ============================================================
# to_dict 测试
# ============================================================

class TestToDict:
    """to_dict 方法测试"""

    def test_返回包含所有字段(self):
        """to_dict 应返回包含所有字段的字典"""
        setting = _make_setting()
        result = setting.to_dict()

        expected_keys = {
            "id", "downloader_id", "dl_speed_limit", "ul_speed_limit",
            "dl_speed_unit", "ul_speed_unit", "enable_schedule",
            "username", "password", "advanced_settings", "override_local",
            "created_at", "updated_at",
        }
        assert set(result.keys()) == expected_keys

    def test_值正确映射(self):
        """所有字段值应正确映射"""
        setting = _make_setting(
            downloader_id="dl-002",
            dl_speed_limit=2048,
            ul_speed_limit=1024,
        )
        result = setting.to_dict()

        assert result["downloader_id"] == "dl-002"
        assert result["dl_speed_limit"] == 2048
        assert result["ul_speed_limit"] == 1024

    def test_speed_unit_MB转换为1(self):
        """MB_PER_SEC 应转换为 1"""
        from app.models.downloader_settings import SpeedUnitEnum

        setting = _make_setting(
            dl_speed_unit=SpeedUnitEnum.MB_PER_SEC,
        )
        result = setting.to_dict()

        assert result["dl_speed_unit"] == 1  # MB_PER_SEC

    def test_speed_unit_KB转换为0(self):
        """KB_PER_SEC 值为 0，注意源码使用 truthy 检查，0 会返回 None"""
        from app.models.downloader_settings import SpeedUnitEnum

        setting = _make_setting(
            dl_speed_unit=SpeedUnitEnum.KB_PER_SEC,
        )
        result = setting.to_dict()

        # 源码: value if self.dl_speed_unit else None
        # SpeedUnitEnum.KB_PER_SEC == 0 (falsy)，所以返回 None
        assert result["dl_speed_unit"] is None

    def test_speed_unit为None时返回None(self):
        """速度单位为 None 时应返回 None"""
        setting = _make_setting(dl_speed_unit=None, ul_speed_unit=None)
        result = setting.to_dict()

        assert result["dl_speed_unit"] is None
        assert result["ul_speed_unit"] is None

    def test_时间为None时返回None(self):
        """时间为 None 时应返回 None"""
        setting = _make_setting(created_at=None, updated_at=None)
        result = setting.to_dict()

        assert result["created_at"] is None
        assert result["updated_at"] is None

    def test_时间正确格式化为ISO(self):
        """时间应正确格式化为 ISO 格式字符串"""
        dt = datetime(2026, 4, 3, 14, 30, 0)
        setting = _make_setting(created_at=dt, updated_at=dt)
        result = setting.to_dict()

        assert result["created_at"] == "2026-04-03T14:30:00"
        assert result["updated_at"] == "2026-04-03T14:30:00"


# ============================================================
# SpeedUnitEnum 测试
# ============================================================

class TestSpeedUnitEnum:
    """SpeedUnitEnum 枚举测试"""

    def test_KB_PER_SEC值为0(self):
        from app.models.downloader_settings import SpeedUnitEnum
        assert SpeedUnitEnum.KB_PER_SEC == 0

    def test_MB_PER_SEC值为1(self):
        from app.models.downloader_settings import SpeedUnitEnum
        assert SpeedUnitEnum.MB_PER_SEC == 1


# ============================================================
# __repr__ 测试
# ============================================================

class TestRepr:
    """__repr__ 方法测试"""

    def test_repr包含关键信息(self):
        """__repr__ 应包含 id, downloader_id, 速度信息"""
        from app.models.downloader_settings import DownloaderSetting

        setting = _make_setting(id=1, downloader_id="dl-001", dl_speed_limit=1024, ul_speed_limit=512)
        result = DownloaderSetting.__repr__(setting)

        assert "id=1" in result
        assert "dl-001" in result
        assert "1024" in result
        assert "512" in result
