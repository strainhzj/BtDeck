# -*- coding: utf-8 -*-
"""orphan_stats_cache 纯单测：get/set/失效/超限淘汰/epoch 防回写。"""

from app.services.orphan_stats_cache import OrphanStatsCache


class TestOrphanStatsCache:
    def test_set_and_get_roundtrip(self):
        cache = OrphanStatsCache()
        epoch, value = cache.get("scan-a")
        assert value is None
        cache.set("scan-a", epoch, (1, 100, 2))
        epoch2, value = cache.get("scan-a")
        assert value == (1, 100, 2)
        assert epoch2 == epoch

    def test_invalidate_specific_key(self):
        cache = OrphanStatsCache()
        e, _ = cache.get("scan-a")
        cache.set("scan-a", e, (1, 100, 2))
        cache.invalidate("scan-a")
        assert cache.get("scan-a")[1] is None

    def test_invalidate_all_clears_and_advances_epoch(self):
        cache = OrphanStatsCache()
        e, _ = cache.get("scan-a")
        cache.set("scan-a", e, (1, 100, 2))
        cache.invalidate()
        assert cache.get("scan-a")[1] is None
        # 旧 epoch 的 set 不再生效（防回写）
        cache.set("scan-a", e, (9, 9, 9))
        assert cache.get("scan-a")[1] is None

    def test_stale_epoch_write_discarded(self):
        cache = OrphanStatsCache()
        e1, _ = cache.get("scan-a")
        # 模拟：get 之后、set 之前发生 invalidate（后台任务夹在中间）
        cache.invalidate()
        cache.set("scan-a", e1, (7, 7, 7))
        assert cache.get("scan-a")[1] is None
        # 新 epoch 的 set 正常生效
        e2, _ = cache.get("scan-a")
        cache.set("scan-a", e2, (8, 8, 8))
        assert cache.get("scan-a")[1] == (8, 8, 8)

    def test_evicts_oldest_over_capacity(self):
        cache = OrphanStatsCache()
        for index in range(6):
            epoch, _ = cache.get(f"scan-{index}")
            cache.set(f"scan-{index}", epoch, (index, index, index))
        # 上限 4 条，保留最后 4 个 key（FIFO：scan-0、scan-1 被淘汰）
        assert len(cache._entries) == 4  # noqa: SLF001 - 单测直查内部状态
        assert cache.get("scan-0")[1] is None
        assert cache.get("scan-1")[1] is None
        assert cache.get("scan-2")[1] == (2, 2, 2)
        assert cache.get("scan-5")[1] == (5, 5, 5)
