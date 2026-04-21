# -*- coding: utf-8 -*-
"""
DownloaderTypeEnum 的单元测试

测试 setting_templates.py 中 DownloaderTypeEnum 的 normalize / to_name / from_value /
is_qbittorrent / is_transmission 方法。
"""
import pytest
from unittest.mock import patch
from app.models.setting_templates import DownloaderTypeEnum


class TestDownloaderTypeEnumNormalize:
    """DownloaderTypeEnum.normalize 标准化测试"""

    def test_normalize_int_0(self):
        """整数 0 应原样返回（qBittorrent）"""
        assert DownloaderTypeEnum.normalize(0) == 0

    def test_normalize_int_1(self):
        """整数 1 应原样返回（Transmission）"""
        assert DownloaderTypeEnum.normalize(1) == 1

    def test_normalize_str_zero(self):
        """字符串 '0' 应转换为 0"""
        assert DownloaderTypeEnum.normalize("0") == 0

    def test_normalize_str_one(self):
        """字符串 '1' 应转换为 1"""
        assert DownloaderTypeEnum.normalize("1") == 1

    def test_normalize_str_qbittorrent(self):
        """字符串 'qbittorrent' 应转换为 0（不区分大小写）"""
        assert DownloaderTypeEnum.normalize("qbittorrent") == 0

    def test_normalize_str_qbittorrent_uppercase(self):
        """字符串 'QBITTORRENT' 大写也应转换为 0"""
        assert DownloaderTypeEnum.normalize("QBITTORRENT") == 0

    def test_normalize_str_transmission(self):
        """字符串 'transmission' 应转换为 1（不区分大小写）"""
        assert DownloaderTypeEnum.normalize("transmission") == 1

    def test_normalize_str_transmission_uppercase(self):
        """字符串 'TRANSMISSION' 大写也应转换为 1"""
        assert DownloaderTypeEnum.normalize("TRANSMISSION") == 1

    def test_normalize_invalid_int_defaults_to_0(self):
        """无效整数（如 99）应默认返回 0"""
        assert DownloaderTypeEnum.normalize(99) == 0

    def test_normalize_invalid_str_defaults_to_0(self):
        """无效字符串应默认返回 0"""
        assert DownloaderTypeEnum.normalize("invalid") == 0

    def test_normalize_none_defaults_to_0(self):
        """None 值应默认返回 0"""
        assert DownloaderTypeEnum.normalize(None) == 0


class TestDownloaderTypeEnumFromValue:
    """DownloaderTypeEnum.from_value 测试"""

    def test_from_value_0(self):
        assert DownloaderTypeEnum.from_value(0) == DownloaderTypeEnum.QBITTORRENT

    def test_from_value_1(self):
        assert DownloaderTypeEnum.from_value(1) == DownloaderTypeEnum.TRANSMISSION

    def test_from_value_invalid_raises(self):
        with pytest.raises(ValueError, match="无效的下载器类型"):
            DownloaderTypeEnum.from_value(99)


class TestDownloaderTypeEnumToName:
    """DownloaderTypeEnum.to_name 测试"""

    def test_to_name_qbittorrent(self):
        """QBITTORRENT 的名称应为 'qbittorrent'"""
        assert DownloaderTypeEnum.QBITTORRENT.to_name() == "qbittorrent"

    def test_to_name_transmission(self):
        """TRANSMISSION 的名称应为 'transmission'"""
        assert DownloaderTypeEnum.TRANSMISSION.to_name() == "transmission"


class TestDownloaderTypeEnumTypeCheck:
    """DownloaderTypeEnum.is_qbittorrent / is_transmission 测试"""

    def test_is_qbittorrent_true(self):
        assert DownloaderTypeEnum.QBITTORRENT.is_qbittorrent() is True

    def test_is_qbittorrent_false(self):
        assert DownloaderTypeEnum.TRANSMISSION.is_qbittorrent() is False

    def test_is_transmission_true(self):
        assert DownloaderTypeEnum.TRANSMISSION.is_transmission() is True

    def test_is_transmission_false(self):
        assert DownloaderTypeEnum.QBITTORRENT.is_transmission() is False
