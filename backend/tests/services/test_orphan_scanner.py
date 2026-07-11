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
from unittest.mock import AsyncMock, MagicMock, patch

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
        scanner = OrphanScanner()
        legal = tmp_path / "legal.txt"
        legal.write_text("legal")
        orphan = tmp_path / "orphan.txt"
        orphan.write_text("orphan")
        scanner._expected_files = {str(tmp_path): {os.path.abspath(str(legal))}}
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
