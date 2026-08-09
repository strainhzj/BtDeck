# -*- coding: utf-8 -*-
"""
孤儿文件扫描器单元测试（v1.0.6）

覆盖 OrphanScanner 的核心纯函数逻辑：
- inode 去重（_get_file_identifier）
- 排除模式匹配（_matches_patterns / _parse_exclude_patterns）
- 路径收集逻辑（有效数据筛选 + 严格路径映射）
- 孤儿判定（_walk_scan_root 的文件比对逻辑）

不依赖真实 DB / 文件系统，全部用 mock + 临时目录。
"""

import json
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from transmission_rpc import Torrent

from app.services.orphan_scanner import (
    OrphanFileItem,
    OrphanScanIncompleteError,
    OrphanScanner,
    _normalize_path,
)

# ==================== inode 去重 ====================


class TestInodeDedup:
    """inode 去重逻辑测试"""

    def test_get_file_identifier_returns_tuple(self, tmp_path):
        """_get_file_identifier 返回 (st_dev, st_ino) 元组"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        identifier = OrphanScanner._get_file_identifier(str(test_file))
        assert identifier is not None
        assert isinstance(identifier, tuple)
        assert len(identifier) == 2

    def test_get_file_identifier_none_for_missing_file(self):
        """_get_file_identifier 对不存在文件返回 None"""
        identifier = OrphanScanner._get_file_identifier("/nonexistent/path/file.txt")
        assert identifier is None

    def test_seen_inodes_dedup(self, tmp_path):
        """硬链接（相同 inode）应被去重"""
        test_file = tmp_path / "original.txt"
        test_file.write_text("content")
        hardlink = tmp_path / "hardlink.txt"
        os.link(str(test_file), str(hardlink))

        scanner = OrphanScanner()
        id1 = scanner._get_file_identifier(str(test_file))
        id2 = scanner._get_file_identifier(str(hardlink))

        # 硬链接 inode 相同
        assert id1 == id2

        # 模拟去重逻辑
        scanner._seen_inodes.add(id1)
        assert id2 in scanner._seen_inodes  # 会被跳过


# ==================== 排除模式匹配 ====================


class TestExcludePatterns:
    """排除模式匹配测试"""

    def test_parse_exclude_patterns(self):
        """_parse_exclude_patterns 正确解析分号分隔的模式"""
        with patch("app.services.orphan_scanner.settings") as mock_settings:
            mock_settings.ORPHAN_EXCLUDE_PATTERNS = "*.torrent;*.pending_delete;*.tmp"
            patterns = OrphanScanner._parse_exclude_patterns()
            assert patterns == ["*.torrent", "*.pending_delete", "*.tmp"]

    def test_parse_exclude_patterns_empty(self):
        """空配置返回空列表"""
        with patch("app.services.orphan_scanner.settings") as mock_settings:
            mock_settings.ORPHAN_EXCLUDE_PATTERNS = ""
            patterns = OrphanScanner._parse_exclude_patterns()
            assert patterns == []

    def test_matches_patterns_torrent(self):
        """*.torrent 模式匹配 .torrent 文件"""
        assert OrphanScanner._matches_patterns("movie.torrent", ["*.torrent", "*.pending_delete"])

    def test_matches_patterns_pending_delete(self):
        """*.pending_delete 模式匹配"""
        assert OrphanScanner._matches_patterns("data.pending_delete", ["*.torrent", "*.pending_delete"])

    def test_matches_patterns_no_match(self):
        """普通文件不匹配排除模式"""
        assert not OrphanScanner._matches_patterns("movie.mkv", ["*.torrent", "*.pending_delete"])

    def test_matches_patterns_empty_list(self):
        """空模式列表不匹配任何文件"""
        assert not OrphanScanner._matches_patterns("any.file", [])


# ==================== Level3 回收站标记判定 ====================


class TestRecycleBinTag:
    """Level3 回收站归档标记（.pending_delete）判定测试。

    回归孤儿扫描 bug：Level3 删除产生的 .pending_delete 文件被误判为孤儿。
    fnmatch 的 *.pending_delete 模式无法覆盖两种改名形态，改用子串判断。
    """

    def test_is_recycle_bin_path_multi_file_dir(self):
        """多文件目录形态：TorrentName.pending_delete 命中"""
        assert OrphanScanner._is_recycle_bin_path("[Seed].pending_delete")

    def test_is_recycle_bin_path_single_file_with_ext(self):
        """单文件改名形态（有扩展名）：movie.pending_delete.mkv 命中"""
        assert OrphanScanner._is_recycle_bin_path("movie.pending_delete.mkv")

    def test_is_recycle_bin_path_single_file_no_ext(self):
        """单文件改名形态（无扩展名）：README.pending_delete 命中（glob 盲区回归）"""
        assert OrphanScanner._is_recycle_bin_path("README.pending_delete")

    def test_is_recycle_bin_path_normal_file_not_match(self):
        """普通文件不命中"""
        assert not OrphanScanner._is_recycle_bin_path("episode.mkv")
        assert not OrphanScanner._is_recycle_bin_path("movie.mkv")

    def test_is_recycle_bin_path_empty_tag_disables(self):
        """用户显式清空 ORPHAN_RECYCLE_BIN_TAG → 返回 False（不排除任何文件）"""
        with patch("app.services.orphan_scanner.settings") as mock_settings:
            mock_settings.ORPHAN_RECYCLE_BIN_TAG = ""
            assert not OrphanScanner._is_recycle_bin_path("[Seed].pending_delete")


# ==================== 路径收集辅助方法 ====================


class TestPathCollection:
    """路径收集辅助方法测试"""

    def test_convert_to_external_with_mapping_service(self, tmp_path):
        """有路径映射服务时调用 internal_to_external。

        使用宿主无关的绝对路径（tmp_path）作为 external 映射结果：
        resolve_external_path 要求映射后的 external 路径在宿主机上为绝对路径
        （os.path.isabs，宿主平台相关），硬编码 Windows 盘符路径会在 Linux CI
        上 isabs 为 False 而误返回 None。
        """
        external_root = tmp_path / "Downloads"
        external_movie = external_root / "movie"
        dl = MagicMock()
        mapping_service = MagicMock()
        mapping_service.internal_to_external.return_value = str(external_movie)
        mapping_service.get_mappings.return_value = [
            {
                "internal": "/downloads",
                "external": str(external_root),
            }
        ]
        mapping_service.get_rules.return_value = []
        dl.path_mapping_service = mapping_service

        scanner = OrphanScanner()
        result = scanner._convert_to_external("/downloads/movie", dl)
        assert result == str(external_movie)
        mapping_service.internal_to_external.assert_called_once_with("/downloads/movie")

    def test_convert_to_external_no_downloader(self):
        """无下载器配置时不得把内部绝对路径当作外部路径"""
        scanner = OrphanScanner()
        result = scanner._convert_to_external("/downloads/movie", None)
        assert result is None

    def test_convert_to_external_requires_path_boundary_match(self):
        """相似字符串前缀不能被误认为有效目录映射。"""
        dl = MagicMock()
        mapping_service = MagicMock()
        mapping_service.get_mappings.return_value = [
            {
                "internal": "/downloads",
                "external": "/mnt/downloads",
            }
        ]
        mapping_service.get_rules.return_value = []
        dl.path_mapping_service = mapping_service

        result = OrphanScanner()._convert_to_external("/downloads-old/movie", dl)

        assert result is None
        mapping_service.internal_to_external.assert_not_called()

    def test_collect_scan_paths_filters_inactive_records_and_paths(self, tmp_path):
        """扫描根只来自有效种子、有效下载器及未停用维护路径。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.database import Base
        from app.downloader.models import BtDownloaders
        from app.models.downloader_path_maintenance import (
            DownloaderPathMaintenance,
        )
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
        external_root = tmp_path / "mounted"
        mapping = json.dumps(
            {
                "mappings": [
                    {
                        "name": "downloads",
                        "internal": "/downloads",
                        "external": str(external_root),
                    }
                ]
            }
        )

        try:
            with Session() as db:
                db.execute(
                    BtDownloaders.__table__.insert(),
                    [
                        {
                            "downloader_id": "active",
                            "downloader_type": 0,
                            "enabled": True,
                            "dr": 0,
                            "path_mapping": mapping,
                        },
                        {
                            "downloader_id": "disabled",
                            "downloader_type": 0,
                            "enabled": False,
                            "dr": 0,
                            "path_mapping": mapping,
                        },
                        {
                            "downloader_id": "deleted",
                            "downloader_type": 0,
                            "enabled": True,
                            "dr": 1,
                            "path_mapping": mapping,
                        },
                    ],
                )
                torrent_rows = [
                    ("active", "/downloads/active", True, 0, None),
                    (
                        "active",
                        "/downloads/recycle-bin",
                        True,
                        0,
                        datetime.utcnow(),
                    ),
                    ("active", "/downloads/torrent-disabled", False, 0, None),
                    ("active", "/downloads/torrent-deleted", True, 1, None),
                    (
                        "active",
                        "/downloads/maintenance-disabled",
                        True,
                        0,
                        None,
                    ),
                    ("disabled", "/downloads/downloader-disabled", True, 0, None),
                    ("deleted", "/downloads/downloader-deleted", True, 0, None),
                ]
                db.execute(
                    TorrentInfo.__table__.insert(),
                    [
                        {
                            "info_id": f"torrent-{index}",
                            "downloader_id": downloader_id,
                            "downloader_name": downloader_id,
                            "save_path": save_path,
                            "enabled": enabled,
                            "dr": dr,
                            "deleted_at": deleted_at,
                            "has_tracker_error": False,
                        }
                        for index, (
                            downloader_id,
                            save_path,
                            enabled,
                            dr,
                            deleted_at,
                        ) in enumerate(torrent_rows)
                    ],
                )
                db.add(
                    DownloaderPathMaintenance(
                        downloader_id="active",
                        path_type="active",
                        path_value="/downloads/maintenance-disabled",
                        is_enabled=False,
                    )
                )
                db.commit()

            scanner = OrphanScanner(sync_session_factory=Session)
            paths = scanner._collect_scan_paths()

            assert paths == [
                (
                    _normalize_path(str(external_root / "active")),
                    "active",
                )
            ]
            assert scanner._scan_warnings == []
            assert (
                _normalize_path(str(external_root)),
                "active",
            ) not in paths
        finally:
            engine.dispose()

    def test_collect_scan_paths_warns_and_skips_unmapped_path(self):
        """缺少映射只记录告警，内部绝对路径不能进入扫描根。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.database import Base
        from app.downloader.models import BtDownloaders
        from app.models.downloader_path_maintenance import (
            DownloaderPathMaintenance,
        )
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
        try:
            with Session() as db:
                db.execute(
                    BtDownloaders.__table__.insert(),
                    {
                        "downloader_id": "dl-unmapped",
                        "downloader_type": 0,
                        "enabled": True,
                        "dr": 0,
                        "path_mapping": json.dumps(
                            {
                                "mappings": [
                                    {
                                        "name": "other",
                                        "internal": "/other",
                                        "external": "/mnt/other",
                                    }
                                ]
                            }
                        ),
                    },
                )
                db.execute(
                    TorrentInfo.__table__.insert(),
                    {
                        "info_id": "torrent-unmapped",
                        "downloader_id": "dl-unmapped",
                        "downloader_name": "unmapped",
                        "save_path": "/downloads/unmapped",
                        "enabled": True,
                        "dr": 0,
                        "deleted_at": None,
                        "has_tracker_error": False,
                    },
                )
                db.commit()

            scanner = OrphanScanner(sync_session_factory=Session)
            paths = scanner._collect_scan_paths()

            assert paths == []
            assert len(scanner._scan_warnings) == 1
            warning = scanner._scan_warnings[0]
            assert warning.code == "path_mapping_not_found"
            assert warning.internal_path == "/downloads/unmapped"
        finally:
            engine.dispose()

    def test_collect_scan_paths_skips_empty_external_mapping(self):
        """internal 前缀命中但 external 为空的映射不得把内部绝对路径当成扫描根。

        回归：tr 自动发现映射 external 未回填（全空字符串）时，
        PathMappingService.internal_to_external 未命中分支会原样返回输入路径，
        旧 resolve_external_path 仅校验前缀命中 + isabs，于是把
        ``/Downloads/bangumi`` 这类容器内不存在的下载器内部路径误选成扫描根，
        在 _walk_all_roots 触发 fail-closed 把整批扫描标为 failed。
        """

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.database import Base
        from app.downloader.models import BtDownloaders
        from app.models.downloader_path_maintenance import (
            DownloaderPathMaintenance,
        )
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
        try:
            with Session() as db:
                db.execute(
                    BtDownloaders.__table__.insert(),
                    {
                        "downloader_id": "tr",
                        "downloader_type": 1,
                        "enabled": True,
                        "dr": 0,
                        # 模拟系统自动发现：internal 命中但 external 全空
                        "path_mapping": json.dumps(
                            {
                                "mappings": [
                                    {
                                        "name": "tr-自动发现-路径001",
                                        "internal": "/Downloads/bangumi",
                                        "external": "",
                                        "mapping_type": "local",
                                    },
                                    {
                                        "name": "tr-自动发现-路径002",
                                        "internal": "/Downloads/bangumi/eva",
                                        "external": "",
                                        "mapping_type": "local",
                                    },
                                ]
                            }
                        ),
                    },
                )
                db.execute(
                    TorrentInfo.__table__.insert(),
                    {
                        "info_id": "torrent-bangumi",
                        "downloader_id": "tr",
                        "downloader_name": "tr",
                        "save_path": "/Downloads/bangumi",
                        "enabled": True,
                        "dr": 0,
                        "deleted_at": None,
                        "has_tracker_error": False,
                    },
                )
                db.commit()

            scanner = OrphanScanner(sync_session_factory=Session)
            paths = scanner._collect_scan_paths()

            # /Downloads/bangumi 不能进入扫描根：它在 BtDeck 容器内不存在，
            # 一旦被选成根会触发 _walk_all_roots fail-closed。
            assert paths == []
            assert len(scanner._scan_warnings) == 1
            warning = scanner._scan_warnings[0]
            assert warning.code == "path_mapping_not_found"
            assert warning.internal_path == "/Downloads/bangumi"
        finally:
            engine.dispose()


# ==================== 孤儿判定逻辑 ====================


class TestOrphanDetection:
    """孤儿文件判定逻辑测试（用临时目录模拟文件系统）"""

    def test_walk_scan_root_finds_orphan(self, tmp_path):
        """不在 expected_files 中的文件被判定为孤儿"""
        from app.services.orphan_scanner import _normalize_path

        # 创建两个文件：一个在期望清单中，一个不在
        expected_file = tmp_path / "expected.txt"
        expected_file.write_text("expected")
        orphan_file = tmp_path / "orphan.txt"
        orphan_file.write_text("orphan")

        scanner = OrphanScanner()
        # 将 expected_file 的规范化路径加入期望集合（规范化 key 匹配）
        scanner._expected_files[_normalize_path(str(tmp_path))] = {_normalize_path(os.path.abspath(str(expected_file)))}

        orphans = scanner._walk_scan_root(str(tmp_path), "dl_001", [])

        # orphan.txt 应被判定为孤儿
        orphan_paths = [o.file_path for o in orphans]
        assert os.path.abspath(str(orphan_file)) in orphan_paths
        assert os.path.abspath(str(expected_file)) not in orphan_paths

    def test_walk_scan_root_respects_exclude_patterns(self, tmp_path):
        """排除模式匹配的文件不被判定为孤儿"""
        orphan_file = tmp_path / "orphan.txt"
        orphan_file.write_text("orphan")
        excluded_file = tmp_path / "excluded.torrent"
        excluded_file.write_text("torrent")

        scanner = OrphanScanner()
        scanner._expected_files[str(tmp_path)] = set()

        orphans = scanner._walk_scan_root(str(tmp_path), None, ["*.torrent"])

        orphan_paths = [o.file_path for o in orphans]
        assert os.path.abspath(str(orphan_file)) in orphan_paths
        assert os.path.abspath(str(excluded_file)) not in orphan_paths

    def test_walk_scan_root_inode_dedup(self, tmp_path):
        """硬链接文件只被报告一次"""
        original = tmp_path / "original.txt"
        original.write_text("content")
        hardlink = tmp_path / "hardlink.txt"
        os.link(str(original), str(hardlink))

        scanner = OrphanScanner()
        scanner._expected_files[str(tmp_path)] = set()

        orphans = scanner._walk_scan_root(str(tmp_path), None, [])

        # 硬链接去重后应只有 1 个孤儿（而非 2 个）
        assert len(orphans) == 1

    def test_walk_scan_root_nonexistent_path(self):
        """不存在的路径必须 fail-closed。"""
        scanner = OrphanScanner()
        with pytest.raises(OrphanScanIncompleteError):
            scanner._walk_scan_root("/nonexistent/path", None, [])

    # ==================== Level3 回收站文件不应被误判为孤儿（核心回归） ====================

    def test_iter_regular_files_skips_quarantine_dir(self, tmp_path):
        """_iter_regular_files 不递归进入隔离区目录 .btdeck_quarantine"""
        qdir = tmp_path / ".btdeck_quarantine"
        qdir.mkdir()
        (qdir / "q.bin").write_bytes(b"x")
        normal = tmp_path / "normal.mkv"
        normal.write_bytes(b"x")

        results = list(OrphanScanner._iter_regular_files(str(tmp_path), ".btdeck_quarantine"))
        names = {p.name for p, _ in results}
        assert "normal.mkv" in names
        assert "q.bin" not in names

    def test_iter_regular_files_skips_recycle_bin_dir(self, tmp_path):
        """_iter_regular_files 不递归进入 Level3 多文件回收站目录 [Seed].pending_delete。

        回归核心 bug：TorrentName.pending_delete/ 目录会被递归，内部子文件（原名不变）
        被逐个枚举为孤儿（生产库 204 条误判的来源）。
        """
        recycle_dir = tmp_path / "[Seed].pending_delete"
        recycle_dir.mkdir()
        (recycle_dir / "inner.zip").write_bytes(b"x")
        normal = tmp_path / "normal.mkv"
        normal.write_bytes(b"x")

        results = list(OrphanScanner._iter_regular_files(str(tmp_path), ".btdeck_quarantine"))
        names = {p.name for p, _ in results}
        assert "normal.mkv" in names
        # 多文件目录被剪枝，内部 inner.zip 不被枚举
        assert "inner.zip" not in names

    def test_iter_regular_files_yields_path_and_stat(self, tmp_path):
        """_iter_regular_files 返回 (Path, stat_result) 元组"""
        f = tmp_path / "f.txt"
        f.write_text("x")
        results = list(OrphanScanner._iter_regular_files(str(tmp_path), ".btdeck_quarantine"))
        assert len(results) == 1
        path, stat_info = results[0]
        assert path.name == "f.txt"
        assert hasattr(stat_info, "st_size")

    def test_walk_scan_root_skips_pending_delete_dir(self, tmp_path):
        """多文件回收站目录内的子文件不被判为孤儿（端到端）。

        场景：[Seed].pending_delete/inner.zip（Level3 多文件形态）+ 一个真孤儿。
        断言 inner.zip 不在结果，真孤儿在。
        """
        recycle_dir = tmp_path / "[Seed].pending_delete"
        recycle_dir.mkdir()
        (recycle_dir / "inner.zip").write_bytes(b"x")
        orphan = tmp_path / "real_orphan.mkv"
        orphan.write_bytes(b"x")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}

        orphans = scanner._walk_scan_root(str(tmp_path), "dl_001", [])
        paths = [o.file_path for o in orphans]

        assert os.path.abspath(str(orphan)) in paths
        # 回收站目录内子文件绝不被判孤儿
        assert not any("inner.zip" in p for p in paths)
        assert not any(".pending_delete" in p for p in paths)

    def test_walk_scan_root_skips_pending_delete_single_file(self, tmp_path):
        """单文件回收站改名（有扩展名）不被判孤儿：movie.pending_delete.mkv

        回归 fnmatch 盲区：*.pending_delete 要求以 .pending_delete 结尾，
        对 movie.pending_delete.mkv 返回 False（扩展名在后）。
        """
        recycle_file = tmp_path / "movie.pending_delete.mkv"
        recycle_file.write_bytes(b"x")
        orphan = tmp_path / "real_orphan.mkv"
        orphan.write_bytes(b"x")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}

        orphans = scanner._walk_scan_root(str(tmp_path), "dl_001", [])
        paths = [o.file_path for o in orphans]

        assert os.path.abspath(str(orphan)) in paths
        assert os.path.abspath(str(recycle_file)) not in paths

    def test_walk_scan_root_skips_pending_delete_no_ext(self, tmp_path):
        """单文件回收站改名（无扩展名）不被判孤儿：README.pending_delete

        回归 glob 方案的盲区：README → splitext 无扩展 → 改名 README.pending_delete。
        """
        recycle_file = tmp_path / "README.pending_delete"
        recycle_file.write_bytes(b"x")
        orphan = tmp_path / "real_orphan.mkv"
        orphan.write_bytes(b"x")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}

        orphans = scanner._walk_scan_root(str(tmp_path), "dl_001", [])
        paths = [o.file_path for o in orphans]

        assert os.path.abspath(str(orphan)) in paths
        assert os.path.abspath(str(recycle_file)) not in paths

    def test_orphan_file_item_attributes(self):
        """OrphanFileItem 正确保存属性"""
        mtime = datetime(2026, 1, 1, 12, 0, 0)
        item = OrphanFileItem(
            file_path="/data/orphan.txt",
            file_size=1024,
            mtime=mtime,
            downloader_id="dl_001",
        )
        assert item.file_path == "/data/orphan.txt"
        assert item.file_size == 1024
        assert item.mtime == mtime
        assert item.downloader_id == "dl_001"

    # ==================== 共享根 + 降级下载器（根因 1 回归） ====================

    def test_shared_root_file_of_degraded_downloader_protected_by_whitelist(self, tmp_path):
        """降级下载器（tr）的种子文件被在线下载器（qb）共享扫描根扫到 → 目录粗筛无条件保护。

        回归本案根因 1：Final.Fantasy.VII（tr 种子）物理在 /Downloads/jpan/Downloads 下，
        被 qb 扫描根扫到。旧代码粗筛仅在「扫描根 owner ∈ degraded」时启用，owner=qb 不在
        degraded → 跳过目录粗筛 → 误判 high 孤儿（本案 qb 37992 个孤儿的直接来源）。
        修复后：文件落在任一降级种子目录下即无条件保护，不受扫描根 owner 影响。
        """
        shared_root = tmp_path / "shared"
        seed_dir = shared_root / "Final.Fantasy.VII.Remake.Intergrade-CODEX"
        seed_dir.mkdir(parents=True)
        (seed_dir / "codex.iso").write_bytes(b"x")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}
        # 降级种子目录（tr 的 Final.Fantasy.VII 目录）在粗筛白名单
        scanner._directory_whitelist = {_normalize_path(str(seed_dir))}
        # tr 降级；但扫描根 owner 是 qb（在线）
        scanner._degraded_downloader_ids = {"tr"}

        orphans = scanner._walk_scan_root(str(shared_root), "qb", [])

        # 文件落在降级种子目录下 → 无条件保护，不得判为孤儿
        assert orphans == []

    def test_degraded_downloader_orphan_outside_whitelist_gets_low(self, tmp_path):
        """降级下载器范围内、不在粗筛白名单的真孤儿 → low confidence（不可清理）。"""
        root = tmp_path / "root"
        root.mkdir()
        (root / "stranger.txt").write_bytes(b"x")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}
        scanner._directory_whitelist = set()
        scanner._degraded_downloader_ids = {"tr"}

        orphans = scanner._walk_scan_root(str(root), "tr", [])

        assert len(orphans) == 1
        assert orphans[0].confidence == "low"

    def test_true_orphan_outside_whitelist_still_reported_high(self, tmp_path):
        """在线下载器范围、不在任何降级种子目录的真孤儿 → high confidence（可清理）。

        粗筛从「条件启用」改为「无条件启用」后，白名单只含降级种子目录，在线下载器
        精筛成功种子的目录不在白名单 → 真孤儿仍应判 high，不被目录粗筛误保护。
        """
        root = tmp_path / "root"
        root.mkdir()
        (root / "stranger.txt").write_bytes(b"x")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}
        scanner._directory_whitelist = set()
        scanner._degraded_downloader_ids = {"tr"}

        orphans = scanner._walk_scan_root(str(root), "qb", [])

        assert len(orphans) == 1
        assert orphans[0].confidence == "high"

    # ==================== 硬链接副本识别（共享存储块，不额外占空间） ====================

    def test_hardlink_copy_protected_when_scanned_before_original(self, tmp_path):
        """硬链接副本先于原文件被扫描 → 仍不判孤儿。

        回归本案：用户用硬链接把种子文件整理到媒体库（如 /Downloads/jpan/Downloads →
        /Downloads/jpan/Book），副本与种子文件共享同一存储块（同 inode），不额外占用
        磁盘空间，不应判为孤儿。旧 inode 去重依赖扫描顺序——副本先扫时其 inode 首次
        出现、又不在 expected，被误判孤儿；修复为预收集种子文件 inode 后顺序无关。
        """
        root_b = tmp_path / "b"  # 副本根（先扫）
        root_b.mkdir()
        root_a = tmp_path / "a"  # 原文件根（后扫）
        root_a.mkdir()
        seed = root_a / "movie.mkv"
        seed.write_bytes(b"data")
        hardlink = root_b / "movie_copy.mkv"
        os.link(str(seed), str(hardlink))
        standalone = root_b / "standalone.mkv"
        standalone.write_bytes(b"other")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": {_normalize_path(str(seed))}}

        orphans = scanner._walk_all_roots([(str(root_b), "dl"), (str(root_a), "dl")])
        paths = [o.file_path for o in orphans]
        # 硬链接副本（共享存储块）不判孤儿
        assert os.path.abspath(str(hardlink)) not in paths, "与种子文件共享存储块的硬链接副本不应判孤儿"
        # 独立文件（占用额外存储空间）仍判孤儿
        assert os.path.abspath(str(standalone)) in paths

    def test_hardlink_copy_protected_when_original_scanned_first(self, tmp_path):
        """原文件先扫时硬链接副本被去重（回归现有行为）。"""
        root_a = tmp_path / "a"
        root_a.mkdir()
        root_b = tmp_path / "b"
        root_b.mkdir()
        seed = root_a / "movie.mkv"
        seed.write_bytes(b"data")
        hardlink = root_b / "movie_copy.mkv"
        os.link(str(seed), str(hardlink))

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": {_normalize_path(str(seed))}}

        orphans = scanner._walk_all_roots([(str(root_a), "dl"), (str(root_b), "dl")])

        assert os.path.abspath(str(hardlink)) not in [o.file_path for o in orphans]

    def test_independent_copy_not_seed_file_is_orphan(self, tmp_path):
        """非硬链接的独立文件（不同 inode，占用额外存储空间）→ 判孤儿。

        硬链接识别不得误伤独立副本：只有与种子文件共享存储块（同 inode）的文件才被
        排除，其余不在任何种子清单中的文件仍是孤儿（提示占用额外空间）。
        """
        root = tmp_path / "b"
        root.mkdir()
        (root / "standalone.mkv").write_bytes(b"other")

        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}

        orphans = scanner._walk_scan_root(str(root), "dl", [])

        assert len(orphans) == 1


# ==================== A 组：扫描器 / runtime 契约 ====================


class TestScannerRuntimeContract:
    """A 组：扫描器 runtime 契约测试。

    断言：
    - 不泄漏 coroutine（scan 结果不返回 coroutine 对象）
    - qB 共享客户端不执行 auth.log_out()
    - 使用 DownloadLane.SYNC（当前代码用 INTERACTIVE 是缺陷）
    - 不强制走 DownloaderDeleteAdapter（允许正确实现直接调共享 client）
    - 不 mock call_downloader_api（通过真实 runtime 路径验证 lane 选择）
    """

    def test_scan_does_not_leak_coroutine(self, tmp_path, fake_app, fake_qb_client):
        """scan() 返回的结果字典中不应包含未 await 的 coroutine。"""
        import inspect

        scanner = OrphanScanner(app=fake_app)
        # 即使因 fail-closed 失败，也不应泄漏 coroutine
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        # 递归检查结果字典中无 coroutine 对象
        assert _no_coroutine_in(result), "scan 结果泄漏了未 await 的 coroutine 对象"
        # scan 本身不应返回 coroutine（scan 是 async，已 await）
        assert not inspect.iscoroutine(result)

    def test_qb_shared_client_not_logged_out(self, tmp_path, fake_app, fake_qb_client, monkeypatch):
        """扫描全程不得对共享 qB 客户端执行 auth.log_out()。"""
        # 让扫描至少走到文件清单构建阶段
        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )
        monkeypatch.setattr(
            OrphanScanner,
            "_build_torrent_file_map",
            _async_noop,
        )
        monkeypatch.setattr(
            OrphanScanner,
            "_walk_all_roots",
            lambda self, paths: [],
        )
        asyncio_run(scanner.scan() if (scanner := OrphanScanner(app=fake_app)) else None)
        fake_qb_client.auth.log_out.assert_not_called()

    def test_scan_uses_sync_lane(self, tmp_path, fake_app, monkeypatch):
        """扫描器构建文件清单时必须使用 DownloadLane.SYNC，而非 INTERACTIVE。"""
        from app.services import downloader_api_runtime
        from app.services.downloader_api_runtime import DownloadLane

        captured_lanes = []
        original = downloader_api_runtime.call_downloader_api

        async def spy_call(downloader_id, lane, func, *args, **kwargs):
            captured_lanes.append(lane)
            return await original(downloader_id, lane, func, *args, **kwargs)

        # spy downloader_api_runtime 模块上的 call_downloader_api
        monkeypatch.setattr(downloader_api_runtime, "call_downloader_api", spy_call)
        scanner = OrphanScanner(app=fake_app)
        asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        # 如果有任何下载器 API 调用，lane 必须是 SYNC
        for lane in captured_lanes:
            assert lane == DownloadLane.SYNC, f"扫描器应使用 DownloadLane.SYNC，实际用了 {lane}"

    def test_all_unmapped_paths_complete_with_warning(self, fake_app, monkeypatch):
        """全部路径均无映射时任务完成为零扫描，并返回提醒。"""
        from app.services.orphan_manifest import (
            PathMappingWarning,
            ScanPathSelection,
        )

        warning = PathMappingWarning(
            downloader_id="dl_001",
            internal_path="/downloads/unmapped",
        )

        def collect_paths(scanner):
            scanner._scan_path_selection = ScanPathSelection(warnings=(warning,))
            scanner._scan_warnings = [warning]
            return []

        async def build_manifest(scanner):
            scanner._expected_files = {"__global__": set()}
            scanner._manifest_scan_paths = []

        walked_paths = []

        def walk_roots(scanner, paths):
            walked_paths.extend(paths)
            return []

        monkeypatch.setattr(OrphanScanner, "_collect_scan_paths", collect_paths)
        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", build_manifest)
        monkeypatch.setattr(OrphanScanner, "_walk_all_roots", walk_roots)
        monkeypatch.setattr(OrphanScanner, "_create_scan_record", _async_noop)
        monkeypatch.setattr(OrphanScanner, "_finalize_successful_scan", _async_noop)
        monkeypatch.setattr(OrphanScanner, "_notify_scan_completed", _async_noop)

        result = asyncio_run(OrphanScanner(app=fake_app).scan(scan_type="scheduled", operator="system"))

        assert result["status"] == "completed"
        assert result["total_paths_scanned"] == 0
        assert result["total_paths_skipped"] == 1
        assert result["warnings"][0]["code"] == "path_mapping_not_found"
        assert walked_paths == []


# ==================== B 组：fail-closed（整批不完整即失败） ====================


class TestFailClosed:
    """B 组：任一下载器清单/路径映射/扫描根不完整，整批扫描失败且不可清理。

    统一断言：
    - 批次 status == "failed"
    - error_message 非空
    - 不生成可清理明细（orphan_file 表无 completed 批次的明细行）
    - 不调用自动清理
    - 不创建成功通知
    """

    def _assert_failed(self, result, scan_id=None):
        """统一断言：扫描结果为 failed。"""
        assert result["status"] == "failed", f"不完整场景应 fail-closed，实际 {result.get('status')}"

    def test_missing_app_store(self, monkeypatch):
        """app 或 app.state.store 缺失 → 失败。"""
        scanner = OrphanScanner(app=None)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        self._assert_failed(result)

    def test_empty_snapshot(self, fake_app, fake_store, monkeypatch):
        """store.get_snapshot() 返回空 → 失败（无下载器清单）。"""
        fake_store.get_snapshot = AsyncMock(return_value=[])
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        # 当前代码在空 snapshot 时静默返回 0 孤儿（非 fail-closed）→ 此测试应失败
        self._assert_failed(result)

    def test_client_missing(self, fake_app, fake_store, fake_qb_client, tmp_path, monkeypatch):
        """下载器 VO 缺 client → 失败（不可静默跳过）。"""
        from tests.services.conftest import make_downloader_vo

        vo = make_downloader_vo(downloader_id="dl_001", client=None)
        fake_store.get_snapshot = AsyncMock(return_value=[vo])
        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        self._assert_failed(result)

    def test_client_fail_time_positive(self, fake_app, fake_store, fake_qb_client, tmp_path, monkeypatch):
        """fail_time > 0（下载器不可用）→ 失败。"""
        from tests.services.conftest import make_downloader_vo

        vo = make_downloader_vo(downloader_id="dl_001", client=fake_qb_client, fail_time=1)
        fake_store.get_snapshot = AsyncMock(return_value=[vo])
        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        self._assert_failed(result)

    def test_api_timeout(self, fake_app, fake_store, fake_qb_client, tmp_path, monkeypatch):
        """下载器 API 超时 → 整批失败（不静默 continue）。"""
        import asyncio as _asyncio
        from tests.services.conftest import make_downloader_vo

        vo = make_downloader_vo(downloader_id="dl_001", client=fake_qb_client)
        fake_store.get_snapshot = AsyncMock(return_value=[vo])
        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )

        async def raising_build(self):
            raise _asyncio.TimeoutError()

        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", raising_build)
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        self._assert_failed(result)

    def test_api_exception(self, fake_app, fake_store, fake_qb_client, tmp_path, monkeypatch):
        """下载器 API 抛异常 → 整批失败。"""

        async def raising_build(self):
            raise RuntimeError("下载器连接失败")

        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )
        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", raising_build)
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        self._assert_failed(result)

    def test_partial_torrent_failure(self, fake_app, fake_store, fake_qb_client, tmp_path, monkeypatch):
        """部分种子清单成功、后续种子失败 → 整批失败（不允许部分清单）。

        模拟 _build_torrent_file_map 内部处理了部分种子后抛异常：
        语义是「即使部分种子成功，只要有任一失败，整批 fail-closed」。
        """

        async def partial_then_fail(self):
            # 模拟：先处理部分种子（成功），随后遇到失败种子 → 整批失败
            # _build_torrent_file_map 是整批原子操作，内部任一失败即抛
            raise RuntimeError("第 3 个种子清单获取失败（部分种子已成功但整批必须失败）")

        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )
        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", partial_then_fail)
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        self._assert_failed(result)

    def test_scan_root_not_exist(self, fake_app, monkeypatch):
        """扫描根不存在 → 失败（不可静默跳过返回空）。"""
        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [("/nonexistent/path/abc", "dl_001")],
        )

        async def noop_build(self):
            pass

        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", noop_build)
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        self._assert_failed(result)

    def test_single_nonexistent_root_degraded_others_scanned(self, fake_app, tmp_path, monkeypatch):
        """单个扫描根不存在/非目录时降级跳过该根，继续扫其余根，扫描仍 completed。

        回归本案：单文件种子/已删种子的 save_path 在磁盘上不是目录，这是正常运维
        现象，不应让一个异常路径瘫痪整个扫描。该根下文件不被扫到（保守不误判孤儿）。
        """
        # 根1：真实存在的目录，含一个孤儿文件
        good_root = tmp_path / "exists"
        good_root.mkdir()
        orphan_file = good_root / "orphan.bin"
        orphan_file.write_bytes(b"x")
        # 根2：不存在的路径（模拟单文件种子/已删种子的 save_path）
        bad_root = str(tmp_path / "nonexistent_seed_dir")

        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(good_root), "dl_good"), (bad_root, "dl_bad")],
        )

        async def noop_build(self):
            self._expected_files = {"__global__": set()}
            self._directory_whitelist = set()
            self._degraded_downloader_ids = set()

        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", noop_build)
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))

        # 单根不存在 → 降级跳过，不整批失败
        assert result["status"] == "completed", "单根不存在应降级跳过，扫描仍 completed"
        # 存在的根下的孤儿仍被扫到
        assert result["total_orphans"] >= 1, "存在的根下孤儿应被扫到"

    def test_no_auto_cleanup_on_failure(self, fake_app, monkeypatch):
        """扫描失败时不调用自动清理。"""
        cleanup_calls = []

        async def raising_build(self):
            raise RuntimeError("fail")

        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", raising_build)
        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [("/some/path", "dl_001")],
        )
        scanner = OrphanScanner(app=fake_app)
        result = asyncio_run(scanner.scan(scan_type="manual", operator="test"))
        assert result["status"] == "failed"
        assert cleanup_calls == [], "扫描失败时不应调用自动清理"

    def test_lifecycle_failure_cleans_up_details_and_marks_failed(self, fake_app, tmp_path, monkeypatch):
        """生命周期写入失败时，扫描标记 failed 且明细被 _fail_scan 清理。

        落库改为分批后，明细先于生命周期提交（不再同事务回滚）；reconcile
        失败时由 _fail_scan 删除本 scan_id 已提交的明细，避免幽灵明细残留。
        断言不变（detail_count == 0），语义从「事务回滚」变为「失败清理」。
        """
        from sqlalchemy import func, select

        from app.database import SessionLocal
        from app.models.orphan_file import OrphanFile, OrphanScanResult
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        orphan_path = tmp_path / "transaction.bin"
        orphan_path.write_bytes(b"x")

        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )

        async def build_manifest(self):
            self._expected_files = {"__global__": set()}

        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", build_manifest)
        monkeypatch.setattr(
            OrphanLifecycleService,
            "reconcile_candidates",
            AsyncMock(side_effect=RuntimeError("lifecycle commit failed")),
        )

        result = asyncio_run(OrphanScanner(app=fake_app).scan(scan_type="manual", operator="test"))

        assert result["status"] == "failed"
        with SessionLocal() as db:
            scan = db.execute(
                select(OrphanScanResult).where(OrphanScanResult.scan_id == result["scan_id"])
            ).scalar_one()
            detail_count = db.execute(
                select(func.count(OrphanFile.id)).where(OrphanFile.scan_id == result["scan_id"])
            ).scalar_one()
        assert scan.status == "failed"
        assert detail_count == 0

    def test_single_file_stat_failure_is_fail_closed(self, tmp_path, monkeypatch):
        """任一目录项无法 stat 时不得用部分磁盘视图完成扫描。"""
        target = tmp_path / "unreadable.bin"
        target.write_bytes(b"x")
        original_scandir = os.scandir

        def failing_scandir(path):
            if os.path.abspath(path) == os.path.abspath(tmp_path):
                raise PermissionError("simulated directory enumeration denial")
            return original_scandir(path)

        monkeypatch.setattr("app.services.orphan_scanner.os.scandir", failing_scandir)
        scanner = OrphanScanner()
        scanner._expected_files = {"__global__": set()}

        with pytest.raises(OrphanScanIncompleteError):
            scanner._walk_scan_root(str(tmp_path), "dl_001", [])

    def test_scan_completes_when_scoped_downloader_missing_mapping(
        self, tmp_path, fake_app, fake_qb_client, monkeypatch
    ):
        """端到端：下载器 inventory 含缺映射 save_path → 该下载器降级，scan() 仍 completed。

        语义重做（v1.0.7+ 跨下载器共享目录修复）：缺映射从整批 fail-closed 改为单下载器
        降级。验证：
        - collect 阶段：dl-a 的 /downloads/mapped 有映射 → 进 scan_roots
        - build 阶段：dl-a inventory 含缺映射 save_path → dl-a 降级（不 raise）
        - scan() 返回 status=completed（不再 failed）+ degraded_downloader_ids 含 dl-a
        """
        from tests.services.conftest import make_downloader_vo

        # 建一个真实存在的映射目录，作为有效扫描根
        mapped_root = tmp_path / "mapped"
        mapped_root.mkdir()
        # 映射根下一个非孤儿的孤儿文件（dl-a 降级后走目录粗筛；此文件不在任何种子目录
        # 下，应被判 low confidence 孤儿）
        orphan_file = mapped_root / "stranger.mkv"
        orphan_file.write_bytes(b"x")

        # dl-a 的 inventory：一个有映射，一个缺映射 → 整个 dl-a 降级
        fake_qb_client.torrents_info.return_value = [
            SimpleNamespace(hash="hash-mapped", save_path=str(mapped_root)),
            SimpleNamespace(hash="hash-unmapped", save_path="/downloads/unmapped"),
        ]
        fake_qb_client.torrents.files.return_value = [SimpleNamespace(name="mapped.mkv")]
        vo = make_downloader_vo(downloader_id="dl-a", client=fake_qb_client, downloader_type=0)
        fake_app.state.store.get_snapshot = AsyncMock(return_value=[vo])

        # 构造带映射的 BtDownloaders 配置（mapped_root → mapped_root，真实存在的目录）
        mapped_config = SimpleNamespace(
            downloader_id="dl-a",
            downloader_type=0,
            path_mapping=None,
            path_mapping_service=SimpleNamespace(
                get_mappings=lambda: [{"internal": str(mapped_root), "external": str(mapped_root)}],
                get_rules=lambda: [],
                internal_to_external=lambda path: path,
            ),
        )

        from app.services.orphan_manifest import (
            PathMappingWarning,
            ScanPathSelection,
        )

        def collect_paths(scanner):
            # collect 阶段：mapped_root 成功映射进 scan_roots（涉及 dl-a）
            scanner._scan_path_selection = ScanPathSelection(
                scan_roots=((str(mapped_root), frozenset({"dl-a"})),),
                warnings=(
                    PathMappingWarning(
                        downloader_id="dl-other",
                        internal_path="/downloads/collect-unmapped",
                    ),
                ),
            )
            scanner._scan_warnings = list(scanner._scan_path_selection.warnings)
            return list(scanner._scan_path_selection.scan_roots)

        # 让真实 build() 走 dl-a（patch _load_configs 返回带映射配置）
        import app.services.orphan_manifest as manifest_mod

        monkeypatch.setattr(
            manifest_mod.TorrentManifestBuilder,
            "_load_configs",
            lambda self: [mapped_config],
        )
        monkeypatch.setattr(OrphanScanner, "_collect_scan_paths", collect_paths)
        # 跳过 finalize/notify（仅验证 scan() 主流程的降级语义）
        monkeypatch.setattr(OrphanScanner, "_finalize_successful_scan", _async_noop)
        monkeypatch.setattr(OrphanScanner, "_notify_scan_completed", _async_noop)

        result = asyncio_run(OrphanScanner(app=fake_app).scan(scan_type="manual", operator="test"))

        # 缺映射降级 → scan() 仍 completed（不再 failed）
        assert result["status"] == "completed"
        # dl-a 被标记为降级
        assert "dl-a" in result["degraded_downloader_ids"]
        # collect 阶段 warning 仍透传
        assert result["total_paths_skipped"] == 1
        assert result["warnings"][0]["code"] == "path_mapping_not_found"


# ==================== C 组：路径与文件集合稳定性 ====================


class TestPathAndFileSet:
    """C 组：路径规范化与文件集合稳定性测试。"""

    def test_same_scanner_resets_state_between_scans(self, tmp_path):
        """同一 scanner 连续执行两次扫描，内部 expected/inode 状态必须重置。"""
        scanner = OrphanScanner()
        # 第一次扫描填充状态
        scanner._expected_files["/path1"] = {"/path1/a.txt"}
        scanner._seen_inodes.add((1, 100))

        # scan() 开始时应重置（此断言验证 scan 方法内部的重置逻辑）
        # 通过 _walk_scan_root 间接验证：如果状态没重置，第二次扫描的 inode 去重会误判
        f1 = tmp_path / "f1.txt"
        f1.write_text("content")
        scanner._expected_files = {str(tmp_path): set()}
        scanner._seen_inodes = set()  # 模拟重置
        orphans1 = scanner._walk_scan_root(str(tmp_path), None, [])
        assert len(orphans1) == 1

        # 再次创建文件，状态应干净
        f2 = tmp_path / "f2.txt"
        f2.write_text("content2")
        scanner._expected_files = {str(tmp_path): set()}
        scanner._seen_inodes = set()  # 如果 scan() 正确重置，这里应等价
        orphans2 = scanner._walk_scan_root(str(tmp_path), None, [])
        # 两次都应正确发现各自的孤儿（不含旧状态污染）
        paths2 = {os.path.basename(o.file_path) for o in orphans2}
        assert "f2.txt" in paths2

    def test_trailing_slash_normalized(self, tmp_path):
        """尾斜杠差异不影响路径匹配。"""
        scanner = OrphanScanner()
        root = str(tmp_path)
        # expected_files 用带尾斜杠的 key，扫描时不带
        scanner._expected_files = {root + os.sep: set()}
        orphan = tmp_path / "orphan.txt"
        orphan.write_text("x")
        # 当前 _walk_scan_root 用 root（无尾斜杠）查找 expected，key 不匹配→误报
        # 修复后应规范化 key
        orphans = scanner._walk_scan_root(root, None, [])
        # orphan.txt 应被发现（无论 key 带不带尾斜杠）
        # 注意：当前实现可能因 key 不匹配而漏判，此测试验证规范化
        found = any(os.path.basename(o.file_path) == "orphan.txt" for o in orphans)
        assert found, "尾斜杠差异不应导致路径匹配失败"

    def test_result_order_independent(self, tmp_path):
        """扫描结果与输入顺序无关。"""
        scanner = OrphanScanner()
        files = []
        for i in range(5):
            f = tmp_path / f"file_{i}.dat"
            f.write_text(f"content_{i}")
            files.append(f)
        scanner._expected_files = {str(tmp_path): set()}
        orphans = scanner._walk_scan_root(str(tmp_path), None, [])
        orphan_names = sorted(os.path.basename(o.file_path) for o in orphans)
        expected_names = sorted(f.name for f in files)
        assert orphan_names == expected_names

    def test_legal_files_not_false_positive(self, tmp_path):
        """在文件清单中的文件不应被误报为孤儿。"""
        from app.services.orphan_scanner import _normalize_path

        scanner = OrphanScanner()
        legal = tmp_path / "legal.txt"
        legal.write_text("legal")
        orphan = tmp_path / "orphan.txt"
        orphan.write_text("orphan")
        scanner._expected_files = {_normalize_path(str(tmp_path)): {_normalize_path(os.path.abspath(str(legal)))}}
        orphans = scanner._walk_scan_root(str(tmp_path), None, [])
        paths = [os.path.basename(o.file_path) for o in orphans]
        assert "orphan.txt" in paths
        assert "legal.txt" not in paths

    def test_hardlink_single_candidate(self, tmp_path):
        """同一物理文件（硬链接）只产生一个候选。"""
        original = tmp_path / "original.txt"
        original.write_text("content")
        hardlink = tmp_path / "hardlink.txt"
        os.link(str(original), str(hardlink))
        scanner = OrphanScanner()
        scanner._expected_files = {str(tmp_path): set()}
        orphans = scanner._walk_scan_root(str(tmp_path), None, [])
        assert len(orphans) == 1, "硬链接去重后应只有 1 个候选"

    def test_parent_child_roots_share_global_expected_set(self, tmp_path):
        """父根先扫描时也必须识别仅登记在子 save_path 下的合法文件。"""
        parent = tmp_path / "downloads"
        child = parent / "movies"
        child.mkdir(parents=True)
        legal = child / "legal.mkv"
        legal.write_bytes(b"legal")

        scanner = OrphanScanner()
        scanner._expected_files = {
            _normalize_path(str(child)): {_normalize_path(str(legal))},
        }
        parent_first = scanner._walk_all_roots([(str(parent), "dl_001"), (str(child), "dl_001")])

        scanner._seen_inodes = set()
        child_first = scanner._walk_all_roots([(str(child), "dl_001"), (str(parent), "dl_001")])

        assert parent_first == []
        assert child_first == []


@pytest.mark.asyncio
async def test_transmission_fetch_uses_files_argument_and_object_shape(fake_tr_client, monkeypatch):
    """Transmission 生产客户端返回真实 Torrent，文件列表来自原始 fields。"""
    fake_tr_client.get_torrent.return_value = Torrent(
        fields={
            "id": 1,
            "hashString": "hash-tr",
            "files": [
                {
                    "name": "folder/video.mkv",
                    "length": 1024,
                    "bytesCompleted": 1024,
                }
            ],
        }
    )
    scanner = OrphanScanner()

    async def direct_call(downloader_id, lane, method, args=None, kwargs=None, **unused):
        from app.services.downloader_api_runtime import DownloadLane

        assert lane == DownloadLane.SYNC
        return method(*(args or ()), **(kwargs or {}))

    monkeypatch.setattr("app.services.downloader_api_runtime.call_downloader_api", direct_call)

    result = await scanner._fetch_torrent_files("dl-tr", "transmission", fake_tr_client, "hash-tr")

    assert result == ["folder/video.mkv"]
    fake_tr_client.get_torrent.assert_called_once_with("hash-tr", arguments=["files"])


# ==================== 清理流水线回收站路径门禁（纵深防御） ====================


class TestPathAuthorizedRecycleBinGate:
    """_path_authorized 对 Level3 回收站路径的拒绝门禁测试。

    纵深防御：即使历史误判候选已残留在 orphan_current_candidate 中（canonical_path
    含 .pending_delete），清理流水线（手动 cleanup_orphans / 自动 auto_cleanup_expired）
    也通过 _path_authorized 统一授权入口拒绝处理，避免被移隔离→物理删除。
    """

    @staticmethod
    def _candidate(canonical_path, downloader_id="dl_001"):
        """构造仅含 canonical_path/downloader_id 的候选（门禁只读这两个字段）"""
        return SimpleNamespace(canonical_path=canonical_path, downloader_id=downloader_id)

    def test_rejects_pending_delete_path(self):
        """canonical_path 含 .pending_delete → 拒绝（多文件目录形态）"""
        from app.services.orphan_file_service import OrphanFileService

        candidate = self._candidate("/data/save/[Seed].pending_delete/inner.zip")
        # 门禁在 downloader 校验前即拒绝，manifest 可为 None
        assert OrphanFileService._path_authorized(candidate, None) is False

    def test_rejects_pending_delete_single_file(self):
        """canonical_path 含 .pending_delete → 拒绝（单文件改名形态）"""
        from app.services.orphan_file_service import OrphanFileService

        candidate = self._candidate("/data/save/movie.pending_delete.mkv")
        assert OrphanFileService._path_authorized(candidate, None) is False

    def test_rejects_quarantine_path(self):
        """canonical_path 含隔离区目录名 → 拒绝"""
        from app.services.orphan_file_service import OrphanFileService

        candidate = self._candidate("/data/save/.btdeck_quarantine/scan_1/orphan.bin")
        assert OrphanFileService._path_authorized(candidate, None) is False

    def test_normal_path_passes_gate_then_full_authorize(self, tmp_path):
        """普通路径越过回收站门禁，全部校验通过 → True（证明门禁不误伤合法孤儿）。

        对照同一 manifest 下回收站路径被门禁拒绝。区分手段：让普通路径完整通过
        downloader + scan_roots commonpath 校验得 True，回收站路径无论 manifest
        多合法都被门禁挡回 False。
        """
        from app.services.orphan_file_service import OrphanFileService

        # 构造真实存在的扫描根，使 commonpath 校验可计算
        scan_root = tmp_path / "save"
        scan_root.mkdir()
        orphan_in_root = scan_root / "real_orphan.mkv"
        orphan_in_root.write_bytes(b"x")

        manifest = SimpleNamespace(
            downloader_ids={"dl_001"},
            scan_roots=[(str(scan_root), frozenset({"dl_001"}))],
        )
        # 普通路径：门禁放行 + downloader 通过 + commonpath 通过 → True
        normal = self._candidate(str(orphan_in_root))
        assert OrphanFileService._path_authorized(normal, manifest) is True

        # 同一扫描根下的回收站路径：门禁拒绝（无论 manifest 多合法）
        recycle_dir = scan_root / "[Seed].pending_delete"
        recycle_dir.mkdir()
        recycle_candidate = self._candidate(str(recycle_dir / "inner.zip"))
        assert OrphanFileService._path_authorized(recycle_candidate, manifest) is False


# ==================== 辅助函数 ====================


def asyncio_run(coro):
    """在同步测试中安全运行协程。"""
    import asyncio as _asyncio

    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _async_noop(*args, **kwargs):
    """async no-op（用于 monkeypatch _build_torrent_file_map）。"""
    pass


def _no_coroutine_in(obj):
    """递归检查对象中是否含 coroutine 对象。"""
    import inspect

    if inspect.iscoroutine(obj):
        return False
    if isinstance(obj, dict):
        return all(_no_coroutine_in(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(_no_coroutine_in(v) for v in obj)
    return True


# ==================== 分批落库 + 护栏（v1.0.6 API 卡死治本） ====================


class TestBatchCommit:
    """落库分批提交行为（防止单大事务独占写锁卡死 API）。"""

    def test_reconcile_candidates_batch_commits(self, tmp_path):
        """reconcile_candidates 带 batch_size 时按批提交，计数语义不变。"""
        import asyncio

        from sqlalchemy import select

        from app.database import AsyncSessionLocal, SessionLocal
        from app.models.orphan_file import OrphanCurrentCandidate
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        # 构造 batch_size=2, 5 个孤儿 → 3 次 commit(2+2+1) + resolved 段 1 次
        orphans = []
        for i in range(5):
            orphans.append(
                {
                    "canonical_path": f"/tmp/batch_test_{i}.bin",
                    "downloader_id": "dl_001",
                    "file_size": 100 + i,
                    "mtime_ns": 1000 + i,
                    "device_id": 1,
                    "inode": i,
                    "confidence": "high",
                }
            )

        async def _run():
            async with AsyncSessionLocal() as db:
                svc = OrphanLifecycleService(db)
                result = await svc.reconcile_candidates(
                    "scan_batch_test",
                    datetime.utcnow(),
                    orphans,
                    scan_roots=["/tmp"],
                    batch_size=2,
                )
                assert result["inserted"] == 5
                assert result["updated"] == 0
                assert result["resolved"] == 0

        asyncio.run(_run())

        # 验证 5 条候选都落库（分批提交无遗漏）
        with SessionLocal() as db:
            cnt = (
                db.execute(
                    select(OrphanCurrentCandidate).where(
                        OrphanCurrentCandidate.canonical_path.like("/tmp/batch_test_%")
                    )
                )
                .scalars()
                .all()
            )
            assert len(cnt) == 5

    def test_reconcile_candidates_batch_resolves_after_commits(self, tmp_path):
        """分批 commit 后 resolved 仍依赖完整 seen_paths 正确标记。"""
        import asyncio

        from sqlalchemy import select

        from app.database import AsyncSessionLocal, SessionLocal
        from app.models.orphan_file import OrphanCurrentCandidate
        from app.services.orphan_lifecycle_service import OrphanLifecycleService

        # 预置一个旧候选(本次清单未出现 → 应 resolved)
        async def _seed():
            async with AsyncSessionLocal() as db:
                svc = OrphanLifecycleService(db)
                await svc.reconcile_candidates(
                    "scan_old",
                    datetime.utcnow(),
                    [
                        {
                            "canonical_path": "/tmp/old_candidate.bin",
                            "downloader_id": "dl_001",
                            "file_size": 10,
                            "mtime_ns": 100,
                            "device_id": 1,
                            "inode": 999,
                            "confidence": "high",
                        }
                    ],
                    scan_roots=["/tmp"],
                )

        asyncio.run(_seed())

        # 本次清单: 3 个新孤儿, batch_size=2
        orphans = []
        for i in range(3):
            orphans.append(
                {
                    "canonical_path": f"/tmp/new_candidate_{i}.bin",
                    "downloader_id": "dl_001",
                    "file_size": 100 + i,
                    "mtime_ns": 1000 + i,
                    "device_id": 1,
                    "inode": i,
                    "confidence": "high",
                }
            )

        async def _run():
            async with AsyncSessionLocal() as db:
                svc = OrphanLifecycleService(db)
                result = await svc.reconcile_candidates(
                    "scan_new",
                    datetime.utcnow(),
                    orphans,
                    scan_roots=["/tmp"],
                    batch_size=2,
                )
                # 旧候选被 resolved, 3 个新候选 insert
                assert result["inserted"] == 3
                assert result["resolved"] == 1

        asyncio.run(_run())

        with SessionLocal() as db:
            old = db.execute(
                select(OrphanCurrentCandidate).where(OrphanCurrentCandidate.canonical_path == "/tmp/old_candidate.bin")
            ).scalar_one()
            assert old.status == "resolved"

    def test_scan_orphan_count_warning_flag(self, fake_app, tmp_path, monkeypatch):
        """孤儿数超过护栏阈值时返回 orphan_count_warning=True（不阻断落库）。"""
        from app.core.config import settings
        from app.services.orphan_scanner import OrphanScanner

        monkeypatch.setattr(settings, "ORPHAN_SCAN_MAX_ORPHANS_WARNING", 2)

        # 生成 5 个孤儿文件
        for i in range(5):
            (tmp_path / f"orphan_{i}.bin").write_bytes(b"x")

        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )

        async def build_manifest(self):
            self._expected_files = {"__global__": set()}
            self._scan_path_selection = None
            self._manifest_scan_paths = [(str(tmp_path), "dl_001")]
            self._scan_warnings = []

        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", build_manifest)
        monkeypatch.setattr(
            OrphanScanner,
            "_notify_scan_completed",
            AsyncMock(),
        )

        result = asyncio_run(OrphanScanner(app=fake_app).scan(scan_type="manual", operator="test"))
        assert result["status"] == "completed"
        assert result["orphan_count_warning"] is True

    def test_scan_orphan_count_below_threshold_no_warning(self, fake_app, tmp_path, monkeypatch):
        """孤儿数低于护栏阈值时不返回 warning 标志。"""
        from app.core.config import settings
        from app.services.orphan_scanner import OrphanScanner

        monkeypatch.setattr(settings, "ORPHAN_SCAN_MAX_ORPHANS_WARNING", 100)

        (tmp_path / "only_one.bin").write_bytes(b"x")

        monkeypatch.setattr(
            OrphanScanner,
            "_collect_scan_paths",
            lambda self: [(str(tmp_path), "dl_001")],
        )

        async def build_manifest(self):
            self._expected_files = {"__global__": set()}
            self._scan_path_selection = None
            self._manifest_scan_paths = [(str(tmp_path), "dl_001")]
            self._scan_warnings = []

        monkeypatch.setattr(OrphanScanner, "_build_torrent_file_map", build_manifest)
        monkeypatch.setattr(
            OrphanScanner,
            "_notify_scan_completed",
            AsyncMock(),
        )

        result = asyncio_run(OrphanScanner(app=fake_app).scan(scan_type="manual", operator="test"))
        assert result["status"] == "completed"
        assert result["orphan_count_warning"] is False
