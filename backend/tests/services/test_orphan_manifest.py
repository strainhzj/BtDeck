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
    """部分种子文件清单拉取失败 → 该下载器整体降级（不再 fail-closed 整批失败）。

    语义重做（v1.0.7+）：任一环节失败改为降级，避免单个种子故障拖垮整个扫描；
    该下载器不进 expected，其文件由目录粗筛白名单在扫描阶段兜底。
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
    # 文件清单拉取失败 → 整个下载器降级，expected 为空
    assert "qb" in snapshot.degraded_downloader_ids
    assert snapshot.expected_paths == set()


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
    # patch 目录粗筛白名单构建，返回含共享根的白名单（模拟 DB 种子目录）
    monkeypatch.setattr(
        manifest_mod,
        "collect_torrent_directory_whitelist",
        lambda session_factory: DirectoryWhitelist(
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
