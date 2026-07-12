# -*- coding: utf-8 -*-
"""实时下载器 manifest 黑盒回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.orphan_manifest import (
    ManifestBuildError,
    TorrentManifestBuilder,
    normalize_path,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _direct_runtime(monkeypatch):
    """隔离全局 runtime executor 生命周期，同时保留 lane/调用参数契约。"""
    from app.services.downloader_api_runtime import DownloadLane

    async def direct_call(
        downloader_id, lane, method, args=None, kwargs=None, **unused
    ):
        assert lane == DownloadLane.SYNC
        return method(*(args or ()), **(kwargs or {}))

    monkeypatch.setattr("app.services.orphan_manifest.call_downloader_api", direct_call)


def _config(downloader_id: str, downloader_type: int):
    return SimpleNamespace(
        downloader_id=downloader_id,
        downloader_type=downloader_type,
        path_mapping=None,
        path_mapping_service=None,
    )


async def test_qb_inventory_is_authoritative(tmp_path):
    root = tmp_path / "qb"
    root.mkdir()
    client = MagicMock()
    client.torrents_info.return_value = [
        SimpleNamespace(hash="hash-qb", save_path=str(root))
    ]
    client.torrents.files.return_value = [SimpleNamespace(name="movie.mkv")]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="qb", client=client, fail_time=0)
            ]
        )
    )
    builder = TorrentManifestBuilder(store)
    builder._load_configs = lambda: [_config("qb", 0)]

    snapshot = await builder.build()

    assert snapshot.expected_paths == {normalize_path(str(root / "movie.mkv"))}
    client.torrents_info.assert_called_once_with()
    client.torrents.files.assert_called_once_with("hash-qb")


async def test_transmission_inventory_uses_object_files(tmp_path):
    root = tmp_path / "tr"
    root.mkdir()
    torrent = SimpleNamespace(
        hashString="hash-tr",
        download_dir=str(root),
        files=[SimpleNamespace(name="show/episode.mkv")],
    )
    client = MagicMock()
    client.get_torrents.return_value = [torrent]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="tr", client=client, fail_time=0)
            ]
        )
    )
    builder = TorrentManifestBuilder(store)
    builder._load_configs = lambda: [_config("tr", 1)]

    snapshot = await builder.build()

    assert snapshot.expected_paths == {
        normalize_path(str(root / "show" / "episode.mkv"))
    }
    client.get_torrents.assert_called_once_with(
        arguments=["hashString", "downloadDir", "name", "files"]
    )


async def test_partial_inventory_failure_is_fail_closed(tmp_path):
    root = tmp_path / "qb"
    root.mkdir()
    client = MagicMock()
    client.torrents_info.return_value = [
        SimpleNamespace(hash="ok", save_path=str(root)),
        SimpleNamespace(hash="broken", save_path=str(root)),
    ]
    client.torrents.files.side_effect = [
        [SimpleNamespace(name="ok.mkv")],
        RuntimeError("remote failure"),
    ]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="qb", client=client, fail_time=0)
            ]
        )
    )
    builder = TorrentManifestBuilder(store)
    builder._load_configs = lambda: [_config("qb", 0)]

    with pytest.raises(ManifestBuildError):
        await builder.build()


async def test_authoritative_empty_inventory_is_valid(tmp_path):
    client = MagicMock()
    client.torrents_info.return_value = []
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="qb", client=client, fail_time=0)
            ]
        )
    )
    builder = TorrentManifestBuilder(store)
    builder._load_configs = lambda: [_config("qb", 0)]

    snapshot = await builder.build()

    assert snapshot.expected_paths == set()
    assert snapshot.downloader_ids == {"qb"}
