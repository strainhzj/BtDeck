# -*- coding: utf-8 -*-
"""
TagAdapterFactory 的单元测试

策略：
- _normalize_downloader_type / get_supported_types / is_supported 只依赖 DownloaderTypeEnum，
  通过 mock DownloaderTypeEnum 来隔离。
- create_adapter 内部使用 cls.SUPPORTED_TYPES 字典中的类来创建实例，
  该字典在模块 import 时已绑定。因此我们对 create_adapter 的测试
  验证其返回值类型和 None 情况，不做 assert_called_once_with（因为 mock patch
  无法替换模块级常量 dict 中的引用）。
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_downloader(downloader_type=0, downloader_id="test-id"):
    """创建模拟下载器对象"""
    dl = MagicMock()
    dl.downloader_type = downloader_type
    dl.downloader_id = downloader_id
    return dl


# ---- _normalize_downloader_type / get_supported_types / is_supported ----
# 这些方法通过 mock DownloaderTypeEnum.normalize 来隔离测试

class TestNormalizeDownloaderType:
    """TagAdapterFactory._normalize_downloader_type 测试"""

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_none_returns_qbittorrent(self, mock_enum):
        """None → 默认 'qbittorrent'"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 0
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "qbittorrent"
        mock_enum.return_value = mock_inst

        result = TagAdapterFactory._normalize_downloader_type(None)
        assert result == "qbittorrent"

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_int_0_returns_qbittorrent(self, mock_enum):
        """整数 0 → 'qbittorrent'"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 0
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "qbittorrent"
        mock_enum.return_value = mock_inst

        assert TagAdapterFactory._normalize_downloader_type(0) == "qbittorrent"

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_int_1_returns_transmission(self, mock_enum):
        """整数 1 → 'transmission'"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 1
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "transmission"
        mock_enum.return_value = mock_inst

        assert TagAdapterFactory._normalize_downloader_type(1) == "transmission"

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_str_qbittorrent(self, mock_enum):
        """字符串 'qbittorrent' → 'qbittorrent'"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 0
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "qbittorrent"
        mock_enum.return_value = mock_inst

        assert TagAdapterFactory._normalize_downloader_type("qbittorrent") == "qbittorrent"

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_str_transmission(self, mock_enum):
        """字符串 'transmission' → 'transmission'"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 1
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "transmission"
        mock_enum.return_value = mock_inst

        assert TagAdapterFactory._normalize_downloader_type("transmission") == "transmission"


class TestGetSupportedTypes:
    """TagAdapterFactory.get_supported_types 测试"""

    def test_returns_list_with_expected_types(self):
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        types = TagAdapterFactory.get_supported_types()
        assert isinstance(types, list)
        assert "qbittorrent" in types
        assert "transmission" in types

    def test_exactly_two_types(self):
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        assert len(TagAdapterFactory.get_supported_types()) == 2


class TestIsSupported:
    """TagAdapterFactory.is_supported 测试"""

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_qbittorrent_supported(self, mock_enum):
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 0
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "qbittorrent"
        mock_enum.return_value = mock_inst

        assert TagAdapterFactory.is_supported(0) is True

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_transmission_supported(self, mock_enum):
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 1
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "transmission"
        mock_enum.return_value = mock_inst

        assert TagAdapterFactory.is_supported(1) is True

    @patch("app.services.tag_adapters.tag_adapter_factory.DownloaderTypeEnum")
    def test_string_type_supported(self, mock_enum):
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        mock_enum.normalize.return_value = 0
        mock_inst = MagicMock()
        mock_inst.to_name.return_value = "qbittorrent"
        mock_enum.return_value = mock_inst

        assert TagAdapterFactory.is_supported("qbittorrent") is True


class TestCreateAdapter:
    """TagAdapterFactory.create_adapter 测试

    create_adapter 使用 cls.SUPPORTED_TYPES 中的真实类（在模块 import 时绑定），
    因此不能简单地 mock 类本身。我们转而验证返回值是否为预期的适配器类型。
    """

    def test_qbittorrent_with_client_returns_adapter(self):
        """qBittorrent 类型 + 有 client → 应返回 QBittorrentTagAdapter 实例"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory
        from app.services.tag_adapters.qbittorrent_adapter import QBittorrentTagAdapter

        dl = _make_downloader(downloader_type=0)
        mock_client = MagicMock()
        adapter = TagAdapterFactory.create_adapter(dl, client=mock_client)

        assert adapter is not None
        assert isinstance(adapter, QBittorrentTagAdapter)

    def test_qbittorrent_without_client_returns_none(self):
        """qBittorrent 类型 + 无 client → 返回 None"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        dl = _make_downloader(downloader_type=0)
        result = TagAdapterFactory.create_adapter(dl, client=None)
        assert result is None

    def test_transmission_with_rpc_url_returns_adapter(self):
        """Transmission 类型 + 有 rpc_url → 应返回 TransmissionTagAdapter 实例"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory
        from app.services.tag_adapters.transmission_adapter import TransmissionTagAdapter

        dl = _make_downloader(downloader_type=1)
        adapter = TagAdapterFactory.create_adapter(
            dl, rpc_url="http://localhost:9091/transmission/rpc",
        )
        assert adapter is not None
        assert isinstance(adapter, TransmissionTagAdapter)

    def test_transmission_without_rpc_url_returns_none(self):
        """Transmission 类型 + 无 rpc_url → 返回 None"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        dl = _make_downloader(downloader_type=1)
        result = TagAdapterFactory.create_adapter(dl, rpc_url=None)
        assert result is None

    def test_exception_in_normalize_returns_none(self):
        """_normalize_downloader_type 抛异常 → 返回 None"""
        from app.services.tag_adapters.tag_adapter_factory import TagAdapterFactory

        # 构造一个有 downloader_id 但没有 downloader_type 的对象，
        # 使异常处理中的 downloader.downloader_id 不再抛错
        bad_dl = MagicMock()
        del bad_dl.downloader_type  # 删除属性，访问时抛 AttributeError
        result = TagAdapterFactory.create_adapter(bad_dl, client=MagicMock())
        assert result is None
