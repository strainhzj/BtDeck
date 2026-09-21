"""UpdateDownloader 部分更新契约回归（2026-09-07 列表启停开关 422 根修）。

锁定三层语义：
1. is_search/is_ssl/enabled 三字段键缺失＝"不修改"（None），不得再触发必填 422
   （事故：桌面列表开关整行 camelCase 展开，缺 is_search/is_ssl 整包 422）；
2. 显式 null 同样＝"不修改"（None 透传），不得被验证器吞成 False
   （旧隐患：null 会静默关闭搜索/停用下载器）；
3. "0"/"1" 字符串与布尔原值照常转换，非法值仍拒绝（防松绑过度）。
"""

import pytest
from pydantic import ValidationError

from app.downloader.request import UpdateDownloader


class TestUpdateDownloaderPartialContract:
    def test_boolean_fields_may_be_absent_meaning_keep(self):
        """键缺失＝不修改：空模型合法，三字段均为 None（修复前为 422）。"""
        model = UpdateDownloader()
        assert model.is_search is None
        assert model.enabled is None
        assert model.is_ssl is None

    def test_toggle_shape_only_enabled(self):
        """列表启停开关的最小 payload 形状。"""
        model = UpdateDownloader(enabled=False)
        assert model.enabled is False
        assert model.is_search is None
        assert model.is_ssl is None

    def test_explicit_null_passes_through_as_none_not_false(self):
        """显式 null 透传为 None（不修改），不得退化为 False。"""
        model = UpdateDownloader(is_search=None, enabled=None, is_ssl=None)
        assert model.is_search is None
        assert model.enabled is None
        assert model.is_ssl is None

    def test_string_zero_one_conversion(self):
        model = UpdateDownloader(is_search="0", enabled="1", is_ssl="0")
        assert model.is_search is False
        assert model.enabled is True
        assert model.is_ssl is False

    def test_bool_passthrough(self):
        model = UpdateDownloader(is_search=True, enabled=False, is_ssl=True)
        assert model.is_search is True
        assert model.enabled is False
        assert model.is_ssl is True

    @pytest.mark.parametrize("bad_value", ["2", "yes", "", "true", 3])
    def test_invalid_values_still_rejected(self, bad_value):
        """可选化不得放松取值校验：非法值仍拒绝。"""
        with pytest.raises(ValidationError):
            UpdateDownloader(is_search=bad_value)

    def test_incident_camel_case_body_shape_accepted(self):
        """事故请求体形状：camelCase 行字段被忽略（extra=ignore），不因缺蛇形键 422。"""
        model = UpdateDownloader(
            **{
                "nickname": "qb-rush",
                "host": "192.168.5.51:28180",
                "isSearch": "1",
                "enabled": "0",
                "downloaderType": 0,
                "downloaderId": "dabb1e6f-a26e-45be-bcb5-505892747f77",
                "port": "28180",
                "connectStatus": "1",
                "pathMappingRules": None,
                "torrentSavePath": None,
            }
        )
        assert model.enabled is False
        assert model.is_search is None
        assert model.is_ssl is None
