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

    # inventory 返回不可迭代对象 → 整个下载器降级（不 raise），记入降级集合；
    # 其文件由目录粗筛白名单兜底，产出的孤儿标 low confidence。
    snapshot = await builder.build()
    assert "tr" in snapshot.degraded_downloader_ids
    assert snapshot.expected_paths == set()


async def test_partial_inventory_failure_degrades_downloader(tmp_path):
    """部分种子文件清单拉取失败 → 仅失败种子降级，成功种子仍精筛进 expected。

    语义重做（per-seed 精筛）：不再因单个种子清单失败整体降级拖垮全部种子——
    成功种子（ok）仍进 expected；失败种子（broken）目录进粗筛白名单保护；
    下载器标记有降级种子（报告用）。
    """
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

    snapshot = await builder.build()
    # 成功种子仍精筛进 expected（不再整体降级）
    assert normalize_path(str(root / "ok.mkv")) in snapshot.expected_paths
    # 清单拉取失败的种子目录进粗筛白名单（保护）
    assert normalize_path(str(root)) in snapshot.directory_whitelist
    # 下载器标记有降级种子
    assert "qb" in snapshot.degraded_downloader_ids


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


async def test_missing_mapping_degrades_downloader(tmp_path):
    """save_path 映射缺失 → 该下载器降级（不再 fail-closed 整批失败）。

    语义重做（v1.0.7+ 跨下载器共享目录修复）：映射缺失从整批 fail-closed 改为
    单下载器降级，避免共享目录场景下一个下载器配置不全拖垮整批扫描。其文件由
    目录粗筛白名单（save_path+name）在扫描阶段兜底保护，不再被误判孤儿。
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

    snapshot = await builder.build()
    # 映射缺失 → 下载器降级，不进 expected；其文件由 directory_whitelist 兜底
    assert "qb" in snapshot.degraded_downloader_ids
    assert snapshot.expected_paths == set()
    # 映射缺失在外部路径解析阶段即降级，不应继续拉取文件清单
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


async def test_unmapped_downloader_degrades_when_scanning_all(tmp_path):
    """required=None 扫描全量时，B 缺映射不再整批 fail-closed，而是 B 降级、A 正常精筛。

    语义重做（v1.0.7+ 跨下载器共享目录修复）：与清理路径的 required 收窄互补——
    扫描全量语义下，任一下载器缺映射只让它自己降级（文件走目录粗筛兜底），不影响
    其他在线下载器的精筛。这避免了「共享目录下一个下载器配置不全就拖垮整批扫描」。
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

    # 不传 required → 遍历全部 → A 正常精筛，B 缺映射降级（不 raise）
    snapshot = await builder.build()

    assert snapshot.downloader_ids == {"dl-a"}
    assert "dl-b" in snapshot.degraded_downloader_ids
    assert normalize_path(str(mapped_root_a / "a.mkv")) in snapshot.expected_paths


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


# ==================== v1.0.7+ 跨下载器共享目录修复回归 ====================


async def test_build_keeps_shared_root_owners(tmp_path):
    """两个下载器 external 映射到同一物理根 → ManifestSnapshot.scan_roots 该根
    owners 集合含两者（回归 setdefault first-writer-wins 丢 owner 的盲区）。

    本案 9 万误判的代码层根因：旧实现 roots.setdefault(root, dl) 只保留第一个
    downloader_id，导致共享根下另一个下载器的种子不进 expected 被误判孤儿。
    """
    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    client_a = MagicMock()
    client_a.torrents_info.return_value = [
        SimpleNamespace(hash="hash-a", save_path=str(shared_root))
    ]
    client_a.torrents.files.return_value = [SimpleNamespace(name="a.mkv")]
    client_b = MagicMock()
    client_b.torrents_info.return_value = [
        SimpleNamespace(hash="hash-b", save_path=str(shared_root))
    ]
    client_b.torrents.files.return_value = [SimpleNamespace(name="b.mkv")]
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="dl-a", client=client_a, fail_time=0),
                SimpleNamespace(downloader_id="dl-b", client=client_b, fail_time=0),
            ]
        )
    )
    # 预构造 scan_path_selection：两个下载器共享同一根 → owners 含两者（验证 build
    # 合并 selection.scan_roots 的多 owner 结构）
    shared_norm = normalize_path(str(shared_root))
    selection = ScanPathSelection(
        scan_roots=((shared_norm, frozenset({"dl-a", "dl-b"})),)
    )
    builder = TorrentManifestBuilder(store, scan_path_selection=selection)
    builder._load_configs = lambda: [
        _config("dl-a", 0, str(shared_root)),
        _config("dl-b", 0, str(shared_root)),
    ]

    snapshot = await builder.build()

    # 两个下载器的文件都进 expected（精筛全量合并）
    assert normalize_path(str(shared_root / "a.mkv")) in snapshot.expected_paths
    assert normalize_path(str(shared_root / "b.mkv")) in snapshot.expected_paths
    # scan_roots 中该共享根的 owners 含两个下载器
    shared_owners = {
        owners
        for _, owners in snapshot.scan_roots
        if "dl-a" in owners or "dl-b" in owners
    }
    assert shared_owners, "共享根 owner 集合不应为空"
    merged = set().union(*shared_owners)
    assert merged == {"dl-a", "dl-b"}


async def test_offline_downloader_degrades_and_directory_whitelist_backed(tmp_path, monkeypatch):
    """离线下载器（无 client）降级：其文件不进精筛 expected，但其种子目录由
    directory_whitelist 兜底（本案核心：tr_lpan/tr 映射缺失，文件被 tr_kpan/qb
    扫描根误判孤儿的回归保护）。

    验证：
    - 离线下载器进 degraded_downloader_ids，不进 downloader_ids/expected
    - 其种子目录仍在 directory_whitelist 中（粗筛兜底）
    """
    import app.services.orphan_manifest as manifest_mod
    from app.services.orphan_manifest import DirectoryWhitelist

    shared_root = tmp_path / "shared"
    shared_root.mkdir()
    client_a = MagicMock()
    client_a.torrents_info.return_value = [
        SimpleNamespace(hash="hash-a", save_path=str(shared_root))
    ]
    client_a.torrents.files.return_value = [SimpleNamespace(name="a.mkv")]
    # dl-b 离线：无 client
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="dl-a", client=client_a, fail_time=0),
                SimpleNamespace(downloader_id="dl-b", client=None, fail_time=0),
            ]
        )
    )
    # patch 目录粗筛白名单构建，返回含共享根的白名单（模拟 DB 种子目录）。
    # build 现在以 downloader_ids=inventory_failed_ids 调用，monkeypatch 需兼容。
    monkeypatch.setattr(
        manifest_mod,
        "collect_torrent_directory_whitelist",
        lambda session_factory, downloader_ids=None: DirectoryWhitelist(
            dirs={normalize_path(str(shared_root))}
        ),
    )
    builder = TorrentManifestBuilder(store, scan_path_selection=ScanPathSelection())
    builder._load_configs = lambda: [
        _config("dl-a", 0, str(shared_root)),
        _config("dl-b", 0, str(shared_root)),
    ]

    snapshot = await builder.build()

    # dl-a 在线精筛正常
    assert snapshot.downloader_ids == {"dl-a"}
    # dl-b 离线降级
    assert "dl-b" in snapshot.degraded_downloader_ids
    # directory_whitelist 非空（含 dl-a/dl-b 共享根目录，离线降级兜底）
    assert snapshot.directory_whitelist
    assert normalize_path(str(shared_root)) in snapshot.directory_whitelist


async def test_partial_mapping_missing_keeps_mapped_seeds_precise(tmp_path):
    """部分种子 save_path 缺映射 → 仅缺映射种子降级，可映射种子仍进 expected（per-seed 精筛）。

    回归本案根因 2：tr 有 2164 个种子落在未映射目录（/Downloads/bangumi*），旧代码
    _build_precise_expected 任一种子缺映射即整体降级，导致 tr 其余 7792 个可映射种子的
    文件也丢失精筛保护，被共享目录在线下载器扫描根误判孤儿（qb 37992 / tr_kpan 19767）。
    """
    mapped_root = tmp_path / "mapped"
    mapped_root.mkdir()
    client = MagicMock()
    client.torrents_info.return_value = [
        SimpleNamespace(hash="hash-mapped", save_path=str(mapped_root)),
        SimpleNamespace(hash="hash-unmapped", save_path="/downloads/unmapped"),
    ]
    client.torrents.files.return_value = [SimpleNamespace(name="mapped.mkv")]
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
    builder._load_configs = lambda: [_config("tr", 0, str(mapped_root))]

    snapshot = await builder.build()

    # 可映射种子仍精筛进 expected（不再因个别种子缺映射整体降级）
    assert normalize_path(str(mapped_root / "mapped.mkv")) in snapshot.expected_paths
    # 缺映射种子目录进入目录粗筛白名单（保护），避免被共享目录在线下载器误判孤儿
    assert normalize_path("/downloads/unmapped") in snapshot.directory_whitelist
    # 下载器仍标记有降级种子（报告用），但 expected 不再为空
    assert "tr" in snapshot.degraded_downloader_ids
    # 缺映射种子不得拉取文件清单
    assert client.torrents.files.call_count == 1  # 仅 hash-mapped


async def test_partial_file_fetch_failure_keeps_other_seeds_precise(tmp_path):
    """部分种子文件清单拉取失败 → 仅该种子降级，其他种子仍进 expected（per-seed 精筛）。

    回归：清单拉取失败的种子目录进入目录粗筛白名单，其余种子不受连累。
    """
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

    snapshot = await builder.build()

    # 成功种子仍进 expected（不再整体降级）
    assert normalize_path(str(root / "ok.mkv")) in snapshot.expected_paths
    # 清单拉取失败的种子目录进入粗筛白名单（保护）
    assert normalize_path(str(root)) in snapshot.directory_whitelist
    # 下载器标记有降级种子
    assert "qb" in snapshot.degraded_downloader_ids


async def test_directory_whitelist_covers_both_root_and_seed_dir(tmp_path):
    """collect_torrent_directory_whitelist 保守加入 external_root 和 join(root,name)
    两个候选目录，覆盖单文件/多文件种子形态歧义。"""
    from app.services.orphan_manifest import collect_torrent_directory_whitelist

    seed_root = tmp_path / "downloads"
    seed_root.mkdir()
    mapped = str(seed_root)

    # 用内存 SQLite 构造一个多文件种子（name=MyTorrent，save_path=mapped）
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.downloader.models import BtDownloaders
    from app.models.downloader_path_maintenance import DownloaderPathMaintenance
    from app.torrents.models import TorrentInfo

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            BtDownloaders.__table__,
            TorrentInfo.__table__,
            DownloaderPathMaintenance.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    db.execute(
        BtDownloaders.__table__.insert(),
        {
            "downloader_id": "dl-x",
            "nickname": "x",
            "host": "h",
            "username": "u",
            "password": "p",
            "downloader_type": 0,
            "enabled": True,
            "dr": 0,
        },
    )
    db.execute(
        TorrentInfo.__table__.insert(),
        {
            "info_id": "i1",
            "downloader_id": "dl-x",
            "downloader_name": "x",
            "hash": "h1",
            "name": "MyTorrent",
            "save_path": mapped,
            "enabled": True,
            "dr": 0,
        },
    )
    db.commit()
    db.close()

    whitelist = collect_torrent_directory_whitelist(Session)
    # 两个候选目录都应在白名单（保守保护）
    assert normalize_path(mapped) in whitelist.dirs
    assert normalize_path(str(seed_root / "MyTorrent")) in whitelist.dirs


async def test_directory_whitelist_filters_by_downloader(tmp_path):
    """collect_torrent_directory_whitelist 支持 downloader_ids 过滤。

    回归修复 2：白名单只含降级下载器/降级种子的目录。精筛成功下载器的种子目录
    不进白名单——否则无条件目录粗筛会把在线下载器的真孤儿误保护。
    """
    from app.services.orphan_manifest import collect_torrent_directory_whitelist

    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.downloader.models import BtDownloaders
    from app.models.downloader_path_maintenance import DownloaderPathMaintenance
    from app.torrents.models import TorrentInfo

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            BtDownloaders.__table__,
            TorrentInfo.__table__,
            DownloaderPathMaintenance.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    for dl in ("dl-a", "dl-b"):
        db.execute(
            BtDownloaders.__table__.insert(),
            {
                "downloader_id": dl,
                "nickname": dl,
                "host": "h",
                "username": "u",
                "password": "p",
                "downloader_type": 0,
                "enabled": True,
                "dr": 0,
            },
        )
    db.execute(
        TorrentInfo.__table__.insert(),
        {
            "info_id": "i-a",
            "downloader_id": "dl-a",
            "downloader_name": "dl-a",
            "hash": "h-a",
            "name": "TorrentA",
            "save_path": str(root_a),
            "enabled": True,
            "dr": 0,
        },
    )
    db.execute(
        TorrentInfo.__table__.insert(),
        {
            "info_id": "i-b",
            "downloader_id": "dl-b",
            "downloader_name": "dl-b",
            "hash": "h-b",
            "name": "TorrentB",
            "save_path": str(root_b),
            "enabled": True,
            "dr": 0,
        },
    )
    db.commit()
    db.close()

    # 只收集 dl-a 的种子目录：dl-b 的目录（在线精筛覆盖）不得进白名单
    whitelist = collect_torrent_directory_whitelist(Session, downloader_ids={"dl-a"})
    assert normalize_path(str(root_a)) in whitelist.dirs
    assert normalize_path(str(root_a / "TorrentA")) in whitelist.dirs
    assert normalize_path(str(root_b)) not in whitelist.dirs
    assert normalize_path(str(root_b / "TorrentB")) not in whitelist.dirs


async def test_partial_seed_degrade_downloader_excluded_from_cleanup_ids(tmp_path):
    """下载器有任一 per-seed 降级种子 → 整体退出 downloader_ids（清理授权不可靠）。

    回归修复 1 的清理授权语义：orphan_file_service._path_authorized 依赖
    downloader_ids 判断候选所属下载器的文件级判定是否可靠。per-seed 语义下，
    即使部分种子精筛进 expected，只要有一个种子缺映射/清单失败，该下载器整体
    退出 downloader_ids —— 否则缺映射种子的文件若被误判孤儿，清理授权会误删
    不可靠判定的文件。
    """
    mapped_root = tmp_path / "mapped"
    mapped_root.mkdir()
    client = MagicMock()
    client.torrents_info.return_value = [
        SimpleNamespace(hash="hash-mapped", save_path=str(mapped_root)),
        SimpleNamespace(hash="hash-unmapped", save_path="/downloads/unmapped"),
    ]
    client.torrents.files.return_value = [SimpleNamespace(name="mapped.mkv")]
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
    builder._load_configs = lambda: [_config("tr", 0, str(mapped_root))]

    snapshot = await builder.build()

    # 可映射种子仍精筛进 expected（per-seed 不整体降级）
    assert normalize_path(str(mapped_root / "mapped.mkv")) in snapshot.expected_paths
    # 但下载器有降级种子 → 退出 downloader_ids（清理授权不可靠，不得清理其候选）
    assert "tr" not in snapshot.downloader_ids
    assert "tr" in snapshot.degraded_downloader_ids


async def test_inventory_failure_downloader_db_seed_dirs_in_whitelist(tmp_path):
    """inventory 拉取失败（下载器级）→ 该下载器的 DB 种子目录进粗筛白名单。

    完整链路回归（不 monkeypatch）：inventory 失败 → inventory_failed_ids →
    build 用 collect_torrent_directory_whitelist(downloader_ids={dl-x}) 从 DB
    收集该下载器的种子目录 → 白名单包含它们，供扫描阶段粗筛兜底保护（其文件
    不被共享目录在线下载器扫描根误判孤儿）。
    """
    from app.services.orphan_manifest import (
        collect_torrent_directory_whitelist,  # noqa: F401  # 确保导入不误用 monkeypatch
    )

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.downloader.models import BtDownloaders
    from app.models.downloader_path_maintenance import DownloaderPathMaintenance
    from app.torrents.models import TorrentInfo

    external_root = tmp_path / "dlx-root"
    external_root.mkdir()

    # StaticPool 共享单连接：build 内 collect_torrent_directory_whitelist 在
    # asyncio.to_thread 的新线程执行，:memory: 默认每连接独立库会丢表。
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            BtDownloaders.__table__,
            TorrentInfo.__table__,
            DownloaderPathMaintenance.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    db = Session()
    db.execute(
        BtDownloaders.__table__.insert(),
        {
            "downloader_id": "dl-x",
            "nickname": "x",
            "host": "h",
            "username": "u",
            "password": "p",
            "downloader_type": 0,
            "enabled": True,
            "dr": 0,
        },
    )
    db.execute(
        TorrentInfo.__table__.insert(),
        {
            "info_id": "i-x",
            "downloader_id": "dl-x",
            "downloader_name": "x",
            "hash": "h-x",
            "name": "MyTorrent",
            "save_path": str(external_root),
            "enabled": True,
            "dr": 0,
        },
    )
    db.commit()
    db.close()

    # dl-x 的 inventory 拉取抛异常 → 下载器级降级（不是 per-seed）
    client_x = MagicMock()
    client_x.torrents_info.side_effect = RuntimeError("connection lost")
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[
                SimpleNamespace(downloader_id="dl-x", client=client_x, fail_time=0)
            ]
        )
    )
    builder = TorrentManifestBuilder(
        store,
        scan_path_selection=ScanPathSelection(),
        session_factory=Session,
    )
    builder._load_configs = lambda: [_config("dl-x", 0, str(external_root))]

    snapshot = await builder.build()

    # inventory 失败 → 下载器整体降级 + 退出 downloader_ids
    assert "dl-x" in snapshot.degraded_downloader_ids
    assert "dl-x" not in snapshot.downloader_ids
    # 其 DB 种子目录经真实 collect_torrent_directory_whitelist 进粗筛白名单
    assert normalize_path(str(external_root)) in snapshot.directory_whitelist
    assert normalize_path(str(external_root / "MyTorrent")) in snapshot.directory_whitelist


async def test_gather_fetch_many_seeds_no_loss_no_duplication(tmp_path):
    """gather 并发拉取多种子文件清单：成功种子的文件全部进 expected，无丢失无重复。

    守护本次 _build_precise_expected 串行→gather 改造：worker 返回纯数据、主协程串行汇合，
    大量种子下不应丢文件或重复。使用 20 个种子验证并发汇合正确性。

    注：client.torrents.files 用「按 hash 参数返回」的函数 side_effect（非列表），
    因为 gather 并发调用顺序不确定，列表 side_effect 按序消耗会错配——这恰恰是
    「worker 应自包含、不依赖调用顺序」这一并发安全设计的核心验证点。
    """
    root = tmp_path / "qb"
    root.mkdir()
    client = MagicMock()
    seeds = [SimpleNamespace(hash=f"hash-{i:02d}", save_path=str(root)) for i in range(20)]
    client.torrents_info.return_value = seeds

    # 按 hash 返回对应种子的 2 个文件（与调用顺序无关，并发安全）
    def files_by_hash(torrent_hash):
        return [
            SimpleNamespace(name=f"{torrent_hash}-a.mkv"),
            SimpleNamespace(name=f"{torrent_hash}-b.mkv"),
        ]

    client.torrents.files.side_effect = files_by_hash
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[SimpleNamespace(downloader_id="qb", client=client, fail_time=0)]
        )
    )
    builder = TorrentManifestBuilder(store, scan_path_selection=ScanPathSelection())
    builder._load_configs = lambda: [_config("qb", 0, str(root))]

    snapshot = await builder.build()

    # 20 种子 × 2 文件 = 40 个路径，全部进 expected（无丢失、无重复）
    expected_under_root = [
        p for p in snapshot.expected_paths if normalize_path(str(root)) in p
    ]
    assert len(expected_under_root) == 40, f"20 种子×2 文件应得 40，实际 {len(expected_under_root)}"
    # 每个种子的 a/b 文件都在
    for i in range(20):
        assert normalize_path(str(root / f"hash-{i:02d}-a.mkv")) in snapshot.expected_paths
        assert normalize_path(str(root / f"hash-{i:02d}-b.mkv")) in snapshot.expected_paths
    # 无降级（全部成功）
    assert "qb" not in snapshot.degraded_downloader_ids
    assert "qb" in snapshot.downloader_ids


async def test_gather_empty_files_degrades_single_seed(tmp_path):
    """单种子文件清单为空 → 该种子降级（目录进粗筛白名单），不进 expected。

    守护 gather 路径下 _merge_seed_files 对空清单的降级处理（files=[] 触发 seed_degrade）。
    """
    root = tmp_path / "qb"
    root.mkdir()
    client = MagicMock()
    client.torrents_info.return_value = [
        SimpleNamespace(hash="empty-seed", save_path=str(root)),
        SimpleNamespace(hash="ok-seed", save_path=str(root)),
    ]

    # 按 hash 返回（gather 并发顺序无关）：empty-seed 空清单，ok-seed 正常
    def files_by_hash(torrent_hash):
        if torrent_hash == "empty-seed":
            return []
        return [SimpleNamespace(name="real.mkv")]

    client.torrents.files.side_effect = files_by_hash
    store = SimpleNamespace(
        get_snapshot=AsyncMock(
            return_value=[SimpleNamespace(downloader_id="qb", client=client, fail_time=0)]
        )
    )
    builder = TorrentManifestBuilder(store, scan_path_selection=ScanPathSelection())
    builder._load_configs = lambda: [_config("qb", 0, str(root))]

    snapshot = await builder.build()

    # 成功种子进 expected
    assert normalize_path(str(root / "real.mkv")) in snapshot.expected_paths
    # 空清单种子目录进粗筛白名单（降级保护）
    assert normalize_path(str(root)) in snapshot.directory_whitelist
    assert "qb" in snapshot.degraded_downloader_ids
