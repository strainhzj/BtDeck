# -*- coding: utf-8 -*-
"""种子进度精度修复回归。

背景：同步链路把下载器原始 progress（0-1 小数 ×100）原样落库，产生
99.556946664657 这类浮点尾差脏值并在列表页展示。修复：_normalize_progress_value
统一 round(2)，存量脏值依赖 0.5 阈值"保留旧值"（保留的是舍入值）+
has_torrent_info_changes 精确比较判变化，在下次同步自动覆盖（自愈）。

覆盖：
- 归一化纯函数：长尾差舍入 / 越界夹取 / 非法值归零
- 自愈链路前提：DB 脏值 vs 舍入新值必须被判为"有变化"（触发写回）
"""

from app.api.endpoints.torrents_async import _normalize_progress_value
from app.services.sync_db_write import has_torrent_info_changes


class TestNormalizeProgressRounding:
    def test_long_tail_value_rounded_to_two_decimals(self):
        assert _normalize_progress_value(99.556946664657) == 99.56

    def test_qb_fraction_scaled_then_rounded_by_caller_site(self):
        # 同步入口先 ×100 再归一化：0.99556946664657 * 100 → 99.556946664657 → 99.56
        assert _normalize_progress_value(0.99556946664657 * 100) == 99.56

    def test_two_decimal_value_unchanged(self):
        assert _normalize_progress_value(7.97) == 7.97

    def test_negative_clamped_to_zero(self):
        assert _normalize_progress_value(-0.001) == 0.0

    def test_over_100_clamped(self):
        assert _normalize_progress_value(100.0000001) == 100.0
        assert _normalize_progress_value(120.0) == 100.0

    def test_none_and_invalid_return_zero(self):
        assert _normalize_progress_value(None) == 0.0
        assert _normalize_progress_value("not-a-number") == 0.0

    def test_boundary_values_kept(self):
        assert _normalize_progress_value(0) == 0.0
        assert _normalize_progress_value(100) == 100.0


class TestDirtyProgressSelfHealPath:
    """存量脏值自愈前提：脏旧值 vs 舍入新值判为变化，写回覆盖。"""

    def _row(self, progress):
        return {"info_id": "t-1", "hash": "abc", "name": "种子", "status": "seeding", "progress": progress}

    def test_dirty_old_vs_rounded_new_detected_as_change(self):
        existing = self._row(99.556946664657)
        new_mapping = self._row(_normalize_progress_value(99.556946664657))
        assert has_torrent_info_changes(existing, new_mapping) is True

    def test_rounded_old_vs_rounded_new_skipped(self):
        """修正后的稳定态：同值不写（避免每轮同步无效写入）。"""
        existing = self._row(99.56)
        new_mapping = self._row(_normalize_progress_value(99.556946664657))
        assert has_torrent_info_changes(existing, new_mapping) is False
