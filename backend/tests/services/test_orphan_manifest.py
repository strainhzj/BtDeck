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
    resolve_external_path,
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


async def test_missing_mapping_is_fail_closed(tmp_path):
    """白名单阶段 save_path 映射缺失必须整批失败（fail-closed），不可静默跳过。

    回归保护：旧实现记 warning 后 continue，导致该种子文件不进白名单，
    若其文件落在其它扫描根下会被误判孤儿。fail-closed 杜绝此误判。
    """
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

    with pytest.raises(ManifestBuildError, match="未找到有效路径映射"):
        await builder.build()
    # 映射缺失在外部路径解析阶段即 raise，不应继续拉取文件清单
    client.torrents.files.assert_not_called()


async def test_build_scopes_to_required_downloader_ids(tmp_path):
    """清理路径传 required_downloader_ids 时只遍历这些下载器，A 不受 B 缺映射影响。

    回归：清理下载器 A 的孤儿候选时，不应因无关下载器 B 的 save_path 缺映射
    而拒绝整个清理。
    """
    mapped_root_a = tmp_path / "a"
    mapped_root_a.mkdir()
    client_a = MagicMock()
    client_a.torrents_info.return_value = [
        SimpleNamespace(hash="hash-a", save_path=str(mapped_root_a))
    ]
    client_a.torrents.files.return_value = [SimpleNamespace(name="a.mkv")]
    # B 缺映射（path_mapping_service=None）
    client_b = MagicMock()
    client_b.torrents_info.return_value = [
        SimpleNamespace(hash="hash-b", save_path="/downloads/unmapped-b")
    ]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="dl-a", client=client_a, fail_time=0),
                SimpleNamespace(downloader_id="dl-b", client=client_b, fail_time=0),
            ]
        )
    )
    builder = TorrentManifestBuilder(store, scan_path_selection=ScanPathSelection())
    builder._load_configs = lambda: [
        _config("dl-a", 0, str(mapped_root_a)),
        _config("dl-b", 0),
    ]

    # 只限定 A → 不遍历 B，B 的缺映射不影响
    snapshot = await builder.build(required_downloader_ids={"dl-a"})

    assert snapshot.downloader_ids == {"dl-a"}
    assert normalize_path(str(mapped_root_a / "a.mkv")) in snapshot.expected_paths
    # B 的 client 不应被触碰
    client_b.torrents_info.assert_not_called()
    client_b.torrents.files.assert_not_called()


async def test_fail_closed_only_within_scope(tmp_path):
    """required=None 时遍历全部，作用域内（A、B）任一缺映射即整批 fail-closed。

    与上一测试互补：当 A、B 都在作用域内时，B 缺映射必须 raise（这正是扫描路径
    的全量语义——任何在扫描范围内的下载器缺映射都会导致其文件被误判孤儿）。
    """
    mapped_root_a = tmp_path / "a"
    mapped_root_a.mkdir()
    client_a = MagicMock()
    client_a.torrents_info.return_value = [
        SimpleNamespace(hash="hash-a", save_path=str(mapped_root_a))
    ]
    client_a.torrents.files.return_value = [SimpleNamespace(name="a.mkv")]
    client_b = MagicMock()
    client_b.torrents_info.return_value = [
        SimpleNamespace(hash="hash-b", save_path="/downloads/unmapped-b")
    ]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="dl-a", client=client_a, fail_time=0),
                SimpleNamespace(downloader_id="dl-b", client=client_b, fail_time=0),
            ]
        )
    )
    builder = TorrentManifestBuilder(store, scan_path_selection=ScanPathSelection())
    builder._load_configs = lambda: [
        _config("dl-a", 0, str(mapped_root_a)),
        _config("dl-b", 0),
    ]

    # 不传 required → 遍历全部 → B 缺映射即 raise
    with pytest.raises(ManifestBuildError, match="dl-b"):
        await builder.build()


async def test_warning_from_collect_phase_preserved_on_success(tmp_path):
    """build 成功时，collect 阶段（scan_path_selection.warnings）的 warning
    仍透传到 snapshot.warnings（成功路径 warning 链路完整）。

    回归：build 阶段映射缺失改为 raise 后，ManifestSnapshot.warnings 不再承载
    build 阶段 warning；但 collect 阶段（扫描根缺映射）的 warning 仍需透传，
    供 scan() 在成功路径返回给前端。
    """
    from app.services.orphan_manifest import PathMappingWarning

    mapped_root = tmp_path / "ok"
    mapped_root.mkdir()
    client = MagicMock()
    client.torrents_info.return_value = [
        SimpleNamespace(hash="hash-ok", save_path=str(mapped_root))
    ]
    client.torrents.files.return_value = [SimpleNamespace(name="ok.mkv")]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="dl-ok", client=client, fail_time=0)
            ]
        )
    )
    collect_warning = PathMappingWarning(
        downloader_id="dl-other",
        internal_path="/downloads/collect-unmapped",
    )
    builder = TorrentManifestBuilder(
        store,
        scan_path_selection=ScanPathSelection(warnings=(collect_warning,)),
    )
    builder._load_configs = lambda: [_config("dl-ok", 0, str(mapped_root))]

    snapshot = await builder.build(required_downloader_ids={"dl-ok"})

    assert snapshot.warnings == (collect_warning,)


def test_resolve_external_path_treats_passthrough_as_missing():
    """external 全空（service 原样返回输入）时视为映射缺失。

    复现 tr 自动发现映射 external="" 的场景：PathMappingService 未命中分支
    会原样返回输入路径，resolve_external_path 不得把它当成有效扫描根。
    """

    config = SimpleNamespace(
        downloader_id="tr",
        path_mapping_service=SimpleNamespace(
            get_mappings=lambda: [{"internal": "/Downloads/bangumi", "external": ""}],
            get_rules=lambda: [],
            # 模拟 PathMappingService 未命中分支：external 为空 → 原样返回
            internal_to_external=lambda path: path,
        ),
    )

    assert resolve_external_path("/Downloads/bangumi", config) is None


def test_resolve_external_path_treats_passthrough_trailing_slash_as_missing():
    """service 把目录规范化加尾斜杠后原样返回，仍应判定为缺失。"""

    config = SimpleNamespace(
        downloader_id="tr",
        path_mapping_service=SimpleNamespace(
            get_mappings=lambda: [{"internal": "/Downloads/bangumi/", "external": ""}],
            get_rules=lambda: [],
            internal_to_external=lambda path: path.rstrip("/") + "/",
        ),
    )

    assert resolve_external_path("/Downloads/bangumi", config) is None


def test_resolve_external_path_returns_mapped_external_when_resolved():
    """命中真实 external 的映射正常返回，新判定不得误伤正例。"""

    config = SimpleNamespace(
        downloader_id="tr",
        path_mapping_service=SimpleNamespace(
            get_mappings=lambda: [
                {"internal": "/Downloads/bangumi", "external": "/mnt/bangumi"}
            ],
            get_rules=lambda: [],
            internal_to_external=lambda path: path.replace(
                "/Downloads/bangumi", "/mnt/bangumi"
            ),
        ),
    )

    assert resolve_external_path("/Downloads/bangumi", config) == "/mnt/bangumi"
