# -*- coding: utf-8 -*-
"""实时下载器 manifest 黑盒回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from transmission_rpc import Torrent

from app.services.orphan_manifest import (
    ManifestBuildError,
    ScanPathSelection,
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


def _config(
    downloader_id: str, downloader_type: int, mapped_root: str = ""
):
    mapping_service = None
    if mapped_root:
        mapping_service = SimpleNamespace(
            get_mappings=lambda: [
                {"internal": mapped_root, "external": mapped_root}
            ],
            get_rules=lambda: [],
            internal_to_external=lambda path: path,
        )
    return SimpleNamespace(
        downloader_id=downloader_id,
        downloader_type=downloader_type,
        path_mapping=None,
        path_mapping_service=mapping_service,
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
    builder = TorrentManifestBuilder(
        store, scan_path_selection=ScanPathSelection()
    )
    builder._load_configs = lambda: [_config("qb", 0, str(root))]

    snapshot = await builder.build()

    assert snapshot.expected_paths == {normalize_path(str(root / "movie.mkv"))}
    client.torrents_info.assert_called_once_with()
    client.torrents.files.assert_called_once_with("hash-qb")


async def test_transmission_inventory_uses_object_files(tmp_path):
    root = tmp_path / "tr"
    root.mkdir()
    torrent = Torrent(
        fields={
            "id": 1,
            "hashString": "hash-tr",
            "downloadDir": str(root),
            "name": "show",
            "files": [
                {
                    "name": "show/episode.mkv",
                    "length": 1024,
                    "bytesCompleted": 1024,
                }
            ],
        }
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
    builder = TorrentManifestBuilder(
        store, scan_path_selection=ScanPathSelection()
    )
    builder._load_configs = lambda: [_config("tr", 1, str(root))]

    snapshot = await builder.build()

    assert snapshot.expected_paths == {
        normalize_path(str(root / "show" / "episode.mkv"))
    }
    client.get_torrents.assert_called_once_with(
        arguments=["hashString", "downloadDir", "name", "files"]
    )
    client.get_torrent.assert_not_called()


async def test_transmission_detail_fallback_uses_real_torrent_raw_files(tmp_path):
    root = tmp_path / "tr-fallback"
    root.mkdir()
    inventory_torrent = Torrent(
        fields={
            "id": 2,
            "hashString": "hash-tr-fallback",
            "downloadDir": str(root),
            "name": "fallback",
        }
    )
    detail_torrent = Torrent(
        fields={
            "id": 2,
            "hashString": "hash-tr-fallback",
            "files": [
                {
                    "name": "fallback/video.mkv",
                    "length": 2048,
                    "bytesCompleted": 2048,
                }
            ],
        }
    )
    client = MagicMock()
    client.get_torrents.return_value = [inventory_torrent]
    client.get_torrent.return_value = detail_torrent
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="tr", client=client, fail_time=0)
            ]
        )
    )
    builder = TorrentManifestBuilder(
        store, scan_path_selection=ScanPathSelection()
    )
    builder._load_configs = lambda: [_config("tr", 1, str(root))]

    snapshot = await builder.build()

    assert snapshot.expected_paths == {
        normalize_path(str(root / "fallback" / "video.mkv"))
    }
    client.get_torrent.assert_called_once_with(
        "hash-tr-fallback", arguments=["files"]
    )


async def test_transmission_scalar_inventory_fails_with_context(tmp_path):
    root = tmp_path / "tr-scalar"
    root.mkdir()
    torrent = Torrent(
        fields={
            "id": 3,
            "hashString": "hash-tr-scalar",
            "downloadDir": str(root),
            "name": "scalar",
            "files": [],
        }
    )
    client = MagicMock()
    client.get_torrents.return_value = torrent
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="tr", client=client, fail_time=0)
            ]
        )
    )
    builder = TorrentManifestBuilder(
        store, scan_path_selection=ScanPathSelection()
    )
    builder._load_configs = lambda: [_config("tr", 1)]

    with pytest.raises(
        ManifestBuildError,
        match=r"下载器 tr inventory 返回不可迭代对象: Torrent",
    ):
        await builder.build()


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
    builder = TorrentManifestBuilder(
        store, scan_path_selection=ScanPathSelection()
    )
    builder._load_configs = lambda: [_config("qb", 0, str(root))]

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
    builder = TorrentManifestBuilder(
        store, scan_path_selection=ScanPathSelection()
    )
    builder._load_configs = lambda: [_config("qb", 0)]

    snapshot = await builder.build()

    assert snapshot.expected_paths == set()
    assert snapshot.downloader_ids == {"qb"}


async def test_missing_mapping_is_warned_and_skipped(tmp_path):
    """未映射的 inventory 路径不进入清单，也不会中断其他任务步骤。"""
    internal_root = "/downloads/unmapped"
    client = MagicMock()
    client.torrents_info.return_value = [
        SimpleNamespace(hash="hash-unmapped", save_path=internal_root)
    ]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(
                    downloader_id="qb", client=client, fail_time=0
                )
            ]
        )
    )
    builder = TorrentManifestBuilder(
        store, scan_path_selection=ScanPathSelection()
    )
    builder._load_configs = lambda: [_config("qb", 0)]

    snapshot = await builder.build()

    assert snapshot.expected_paths == set()
    assert snapshot.scan_roots == []
    assert len(snapshot.warnings) == 1
    assert snapshot.warnings[0].internal_path == internal_root
    client.torrents.files.assert_not_called()
