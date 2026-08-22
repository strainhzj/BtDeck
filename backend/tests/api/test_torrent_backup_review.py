# -*- coding: utf-8 -*-
"""
代码审查回归测试 — torrent_backup.py 边界场景

测试范围:
- C2: downloader.save_path / path_mapping 属性不存在于 DownloaderCheckVO
- H4: fail_time 无 hasattr 防护
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def _make_downloader_vo(**overrides):
    """创建模拟的 DownloaderCheckVO 对象（只包含实际存在的属性）"""
    vo = MagicMock(
        spec=[
            "downloader_id",
            "host",
            "port",
            "username",
            "password",
            "fail_time",
            "downloader_type",
            "torrent_save_path",
            "path_mapping_rules",
            "client",
        ]
    )
    vo.downloader_id = "dl-001"
    vo.host = "192.168.1.1"
    vo.port = 8080
    vo.username = "admin"
    vo.password = "password"
    vo.fail_time = 0
    vo.downloader_type = 0
    vo.torrent_save_path = "/downloads"
    vo.path_mapping_rules = None
    vo.client = MagicMock()
    for k, v in overrides.items():
        setattr(vo, k, v)
    return vo


class TestDownloaderAttributeNames:
    """C2: 验证 backup 模块使用正确的属性名"""

    def test_get_downloader_returns_vo_with_correct_attrs(self):
        """get_downloader_from_store 返回的对象应有 torrent_save_path"""
        from app.api.endpoints.torrent_backup import get_downloader_from_store

        app = MagicMock()
        vo = _make_downloader_vo()
        app.state.store.get_snapshot_sync.return_value = [vo]

        result = get_downloader_from_store("dl-001", app)
        assert result is not None
        assert result.torrent_save_path == "/downloads"

    def test_vo_has_no_save_path_attr(self):
        """DownloaderCheckVO 不应该有 save_path 属性"""
        vo = _make_downloader_vo()
        assert not hasattr(vo, "save_path"), "DownloaderCheckVO 不应有 save_path 属性"

    def test_vo_has_no_path_mapping_attr(self):
        """DownloaderCheckVO 不应该有 path_mapping 属性"""
        vo = _make_downloader_vo()
        assert not hasattr(vo, "path_mapping"), "DownloaderCheckVO 不应有 path_mapping 属性"

    def test_backup_source_code_uses_correct_attr_names(self):
        """
        静态检查: torrent_backup.py 不应直接访问 save_path 或 path_mapping
        （应使用 torrent_save_path 和 path_mapping_rules）
        """
        import inspect
        import app.api.endpoints.torrent_backup as backup_mod

        source = inspect.getsource(backup_mod)
        lines = source.split("\n")

        errors = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳过注释和字符串中的引用
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue
            # 检测 downloader.save_path (不应出现)
            if "downloader.save_path" in line and "torrent_save_path" not in line:
                errors.append(f"Line {i}: 发现 'downloader.save_path'，应改为 'downloader.torrent_save_path'")
            # 检测 downloader.path_mapping (不应出现，排除 path_mapping_rules 和 path_mapping_service)
            if (
                "downloader.path_mapping" in line
                and "path_mapping_rules" not in line
                and "path_mapping_service" not in line
            ):
                if "path_mapping_rules" not in line:
                    errors.append(f"Line {i}: 发现 'downloader.path_mapping'，应改为 'downloader.path_mapping_rules'")

        assert not errors, "\n".join(errors)


class TestFailTimeSafety:
    """H4: fail_time 访问应有 hasattr 防护"""

    def test_get_downloader_with_missing_fail_time(self):
        """downloader 没有 fail_time 属性时 get_downloader_from_store 不应崩溃"""
        from app.api.endpoints.torrent_backup import get_downloader_from_store

        app = MagicMock()
        vo = MagicMock(spec=["downloader_id", "host", "port", "client"])
        vo.downloader_id = "dl-001"
        app.state.store.get_snapshot_sync.return_value = [vo]

        # 不应抛出 AttributeError
        result = get_downloader_from_store("dl-001", app)
        assert result is not None

    def test_backup_code_uses_hasattr_for_fail_time(self):
        """
        静态检查: torrent_backup.py 中 fail_time 应使用 hasattr 防护
        """
        import inspect
        import app.api.endpoints.torrent_backup as backup_mod

        source = inspect.getsource(backup_mod)
        lines = source.split("\n")

        errors = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # 检测直接使用 downloader.fail_time 而没有 hasattr
            if ".fail_time" in line and "hasattr" not in line and "def " not in line:
                # 允许在 hasattr 检查后面的同一逻辑块中使用
                # 但独立行直接访问 .fail_time 且没有 hasattr 保护是有风险的
                if "fail_time >" in line or "fail_time ==" in line:
                    # 查看同行或前一行是否有 hasattr
                    prev_line = lines[i - 2] if i >= 2 else ""
                    if "hasattr" not in line and "hasattr" not in prev_line:
                        errors.append(f"Line {i}: 直接访问 .fail_time 未使用 hasattr 防护: {line.strip()}")

        assert not errors, "\n".join(errors)


class TestBackupDownloaderNicknameBatching:
    """备份列表应一次查询当前昵称，并随昵称变更后的下一次请求更新。"""

    @pytest.mark.asyncio
    async def test_collects_current_nicknames_with_one_query(self):
        from app.api.endpoints.torrent_backup import get_backup_downloader_nicknames

        db = AsyncMock()
        result = MagicMock()
        result.all.return_value = [
            SimpleNamespace(downloader_id="1", nickname="家庭下载器"),
            SimpleNamespace(downloader_id="2", nickname="远程下载器"),
        ]
        db.execute.return_value = result
        backups = [
            SimpleNamespace(downloader_id=1),
            SimpleNamespace(downloader_id=2),
            SimpleNamespace(downloader_id=1),
        ]

        nickname_map = await get_backup_downloader_nicknames(db, backups)

        assert nickname_map == {"1": "家庭下载器", "2": "远程下载器"}
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_backup_page_skips_nickname_query(self):
        from app.api.endpoints.torrent_backup import get_backup_downloader_nicknames

        db = AsyncMock()
        assert await get_backup_downloader_nicknames(db, []) == {}
        db.execute.assert_not_awaited()

    def test_serialized_backup_contains_batch_nickname(self):
        from app.api.endpoints.torrent_backup import backup_to_dict

        backup = MagicMock()
        backup.to_dict.return_value = {"downloader_id": 1, "info_hash": "a" * 40}

        data = backup_to_dict(backup, "重命名后的下载器")

        assert data["downloader_nickname"] == "重命名后的下载器"
