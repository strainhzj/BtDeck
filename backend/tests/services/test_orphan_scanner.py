# -*- coding: utf-8 -*-
"""
孤儿文件扫描器单元测试（v1.0.6）

覆盖 OrphanScanner 的核心纯函数逻辑：
- inode 去重（_get_file_identifier）
- 排除模式匹配（_matches_patterns / _parse_exclude_patterns）
- 路径收集逻辑（_convert_to_external / _extract_external_paths_from_mapping）
- 孤儿判定（_walk_scan_root 的文件比对逻辑）

不依赖真实 DB / 文件系统，全部用 mock + 临时目录。
"""

import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.orphan_scanner import OrphanFileItem, OrphanScanner

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


# ==================== 路径收集辅助方法 ====================


class TestPathCollection:
    """路径收集辅助方法测试"""

    def test_extract_external_paths_from_mapping_valid_json(self):
        """从有效 path_mapping JSON 提取 external 路径"""
        dl = MagicMock()
        dl.path_mapping = json.dumps(
            {
                "mappings": [
                    {"name": "map1", "internal": "/downloads", "external": "D:/Downloads"},
                    {"name": "map2", "internal": "/data", "external": "E:/Data"},
                ]
            }
        )
        scanner = OrphanScanner()
        paths = scanner._extract_external_paths_from_mapping(dl)
        assert paths == ["D:/Downloads", "E:/Data"]

    def test_extract_external_paths_from_mapping_empty(self):
        """空 path_mapping 返回空列表"""
        dl = MagicMock()
        dl.path_mapping = None
        scanner = OrphanScanner()
        paths = scanner._extract_external_paths_from_mapping(dl)
        assert paths == []

    def test_extract_external_paths_from_mapping_invalid_json(self):
        """无效 JSON 返回空列表（不抛异常）"""
        dl = MagicMock()
        dl.path_mapping = "not a json"
        scanner = OrphanScanner()
        paths = scanner._extract_external_paths_from_mapping(dl)
        assert paths == []

    def test_convert_to_external_with_mapping_service(self):
        """有路径映射服务时调用 internal_to_external"""
        dl = MagicMock()
        mapping_service = MagicMock()
        mapping_service.internal_to_external.return_value = "D:/Downloads/movie"
        dl.path_mapping_service = mapping_service

        scanner = OrphanScanner()
        result = scanner._convert_to_external("/downloads/movie", dl)
        assert result == "D:/Downloads/movie"
        mapping_service.internal_to_external.assert_called_once_with("/downloads/movie")

    def test_convert_to_external_no_downloader(self):
        """无下载器配置时原样返回"""
        scanner = OrphanScanner()
        result = scanner._convert_to_external("/downloads/movie", None)
        assert result == "/downloads/movie"


# ==================== 孤儿判定逻辑 ====================


class TestOrphanDetection:
    """孤儿文件判定逻辑测试（用临时目录模拟文件系统）"""

    def test_walk_scan_root_finds_orphan(self, tmp_path):
        """不在 expected_files 中的文件被判定为孤儿"""
        # 创建两个文件：一个在期望清单中，一个不在
        expected_file = tmp_path / "expected.txt"
        expected_file.write_text("expected")
        orphan_file = tmp_path / "orphan.txt"
        orphan_file.write_text("orphan")

        scanner = OrphanScanner()
        # 将 expected_file 的绝对路径加入期望集合
        scanner._expected_files[str(tmp_path)] = {os.path.abspath(str(expected_file))}

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
        """不存在的路径返回空列表（不抛异常）"""
        scanner = OrphanScanner()
        orphans = scanner._walk_scan_root("/nonexistent/path", None, [])
        assert orphans == []

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
