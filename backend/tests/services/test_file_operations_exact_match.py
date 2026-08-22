# -*- coding: utf-8 -*-
"""file_operations 删除目标精确匹配回归测试（W15）。

保护点（防回归）：_check_file_exists_with_fallback 在 Windows UNC 诊断分支
不得再"取目录中第一个含 waiting-delete 的文件"作为删除目标——目录里其他
种子的删除标记会被误删（对抗验证附带的完整性缺陷）。修复后只接受
与目标文件名完全匹配的文件。
"""

from pathlib import Path

import pytest

from app.core.file_operations import FileOperationService


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="UNC 诊断分支仅 Windows 生效")
class TestExactMatchOnly:
    """目录含多个 waiting-delete 文件时，只接受精确匹配。"""

    def test_no_fallback_to_first_matching_file(self, tmp_path: Path):
        """目标文件不存在但目录有其他 waiting-delete 文件 → 必须返回不存在。"""
        (tmp_path / "a.waiting-delete").write_text("other torrent marker")
        (tmp_path / "b.waiting-delete").write_text("another torrent marker")
        target = tmp_path / "c.waiting-delete"

        exists, actual_path = FileOperationService._check_file_exists_with_fallback(str(target))
        assert exists is False, "不得把别的种子的删除标记当成本文件"
        assert actual_path == str(target)

    def test_exact_match_still_found(self, tmp_path: Path):
        """目标文件真实存在（含 waiting-delete 后缀）时正常返回。"""
        target = tmp_path / "c.waiting-delete"
        target.write_text("marker")
        (tmp_path / "a.waiting-delete").write_text("other")

        exists, actual_path = FileOperationService._check_file_exists_with_fallback(str(target))
        assert exists is True
        assert actual_path == str(target)

    def test_no_matching_files_returns_not_found(self, tmp_path: Path):
        """目录中没有任何 waiting-delete 文件 → 返回不存在（不猜测）。"""
        (tmp_path / "plain.txt").write_text("x")
        target = tmp_path / "c.waiting-delete"

        exists, actual_path = FileOperationService._check_file_exists_with_fallback(str(target))
        assert exists is False
