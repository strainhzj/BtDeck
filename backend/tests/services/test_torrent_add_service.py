"""TorrentAddService（协议无关添加服务）决策路径测试。

覆盖 store 注入缺失/下载器不在缓存/已失效/客户端缺失/Transmission 无文件
五条前置拒绝路径的 status/code/msg 契约（与原 HTTP endpoint 逐字一致）。
成功路径与异常兜底由 tests/api/test_torrent_crud_add_fallback.py 经端点覆盖。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.torrent_add_service import TorrentAddParams, TorrentAddService


def _make_store(vos):
    store = MagicMock()
    store.get_snapshot = AsyncMock(return_value=list(vos))
    return store


def _make_vo(*, downloader_id="dl-1", fail_time=0, client="default", downloader_type=0):
    return SimpleNamespace(
        downloader_id=downloader_id,
        fail_time=fail_time,
        client=MagicMock() if client == "default" else client,
        nickname="qbt",
        downloader_type=downloader_type,
    )


def _params(**overrides):
    base = {"downloader_id": "dl-1", "save_path": "/downloads"}
    base.update(overrides)
    return TorrentAddParams(**base)


class TestTorrentAddServiceDecisions:
    @pytest.mark.asyncio
    async def test_store_missing(self):
        service = TorrentAddService(MagicMock(), store=None)
        result = await service.add_torrent(_params(), torrent_content=b"x")
        assert (result.status, result.code) == ("failed", "500")
        assert result.msg == "下载器缓存未初始化"

    @pytest.mark.asyncio
    async def test_downloader_not_in_cache(self):
        service = TorrentAddService(MagicMock(), store=_make_store([]))
        result = await service.add_torrent(_params(), torrent_content=b"x")
        assert (result.status, result.code) == ("failed", "404")
        assert "下载器不在缓存中" in result.msg

    @pytest.mark.asyncio
    async def test_downloader_failed(self):
        service = TorrentAddService(MagicMock(), store=_make_store([_make_vo(fail_time=1)]))
        result = await service.add_torrent(_params(), torrent_content=b"x")
        assert (result.status, result.code) == ("failed", "503")
        assert "下载器已失效" in result.msg

    @pytest.mark.asyncio
    async def test_client_missing(self):
        service = TorrentAddService(MagicMock(), store=_make_store([_make_vo(client=None)]))
        result = await service.add_torrent(_params(), torrent_content=b"x")
        assert (result.status, result.code) == ("failed", "500")
        assert "下载器客户端连接不存在" in result.msg

    @pytest.mark.asyncio
    async def test_transmission_requires_file(self):
        service = TorrentAddService(MagicMock(), store=_make_store([_make_vo(downloader_type=1)]))
        result = await service.add_torrent(_params(), torrent_content=None)
        assert result.code == "400"
        assert result.msg == "Transmission需要种子文件"
