# -*- coding: utf-8 -*-
"""
代码审查回归测试 — torrent_deletion.py 边界场景

测试范围:
- C3: async_db 会话在 async with 块外使用
"""

import pytest
import inspect


class TestAsyncSessionScope:
    """C3: deletion_service.delete_torrents() 必须在 async with 块内调用"""

    def _check_delete_torrents_inside_async_with(self, func):
        """通用检查：delete_torrents 调用是否在 async with AsyncSessionLocal() 块内"""
        from app.api.endpoints import torrent_deletion
        source = inspect.getsource(func)
        lines = source.split('\n')

        async_with_blocks = []  # (start_line, indent_level)
        delete_torrents_calls = []  # (line_number, indent_level)

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            if 'async with AsyncSessionLocal()' in stripped:
                async_with_blocks.append((i, indent))

            if 'deletion_service.delete_torrents' in stripped:
                delete_torrents_calls.append((i, indent))

        errors = []
        for dt_line, dt_indent in delete_torrents_calls:
            inside_any_block = False
            for aw_line, aw_indent in async_with_blocks:
                if aw_line < dt_line and dt_indent > aw_indent:
                    inside_any_block = True
                    break
            if not inside_any_block:
                errors.append(
                    f"Line {dt_line + 1}: deletion_service.delete_torrents() 在 async with 块外调用 "
                    f"(indent={dt_indent}, 需要 > async_with indent)"
                )

        return errors

    def test_delete_torrent_session_scope(self):
        """delete_torrent 中 delete_torrents 应在 async with 块内"""
        from app.api.endpoints.torrent_deletion import delete_torrent
        errors = self._check_delete_torrents_inside_async_with(delete_torrent)
        assert not errors, '\n'.join(errors)

    def test_preview_bulk_delete_session_scope(self):
        """preview_bulk_torrent_deletion 中 delete_torrents 应在 async with 块内"""
        from app.api.endpoints.torrent_deletion import preview_bulk_torrent_deletion
        errors = self._check_delete_torrents_inside_async_with(preview_bulk_torrent_deletion)
        assert not errors, '\n'.join(errors)

    def test_bulk_delete_session_scope(self):
        """bulk_delete_torrents 中 delete_torrents 应在 async with 块内"""
        from app.api.endpoints.torrent_deletion import bulk_delete_torrents
        errors = self._check_delete_torrents_inside_async_with(bulk_delete_torrents)
        assert not errors, '\n'.join(errors)
