# -*- coding: utf-8 -*-
"""孤儿列表 scan_context 统计的进程内缓存（单进程部署专用）。

``get_orphan_list`` / ``get_orphan_list_grouped`` 每次请求都计算三条全量聚合
（remaining_count/remaining_size/ignored_count），在大库上是每次请求数百毫秒
的主要成本。这些统计与任何过滤条件无关，只依赖三类数据：

- ``OrphanFile.is_deleted``（咽喉：``_finalize_quarantine`` / ``_finalize_restore``）
- ``OrphanCurrentCandidate.is_ignored``（咽喉：``set_ignored``，扫描对账重置经
  ``execute_scan`` 失效覆盖）
- 清理任务 active 集（咽喉：``submit_cleanup_job`` 提交即扣减、``finish_job``
  终态失败回升）

因此按 ``display_scan.scan_id`` 缓存，并由上述咽喉点失效驱动（全清）。部署恒
单进程（SQLite 约束 WORKERS=1，scheduler 与 API 同进程），无跨进程一致性问题；
模块级单例供服务层与调度层共享，纯标准库不 import 任何 app 模块（防循环依赖）。

失效契约：凡写入 is_ignored / is_deleted / 清理任务 active 状态（提交成功后）
必须调用 ``invalidate()``。新增写入路径时同样必须挂失效，否则统计会 stale。

并发说明：``get`` 与 ``set`` 之间调用方有多次 await（SQL 计算），后台任务的
``invalidate()`` 可能夹在中间——用 epoch 代际防回写：``invalidate()`` 自增
epoch 并清空；``set`` 携带读取时的 epoch，仅在 epoch 未变时写入，失效后旧计算
直接丢弃。
"""

from typing import Dict, Optional, Tuple

# 缓存条目上限：display_scan 实际只在 1-2 个值间切换（当前批次+回退批次），
# 4 条足以容纳多批次并存展示，超限淘汰最旧（对齐 dispatcher _results 有界先例）。
_MAX_CACHE_ENTRIES = 4

# (remaining_count, remaining_size, ignored_count)
OrphanStats = Tuple[int, int, int]


class OrphanStatsCache:
    """display_scan.scan_id → (remaining_count, remaining_size, ignored_count)。

    单进程事件循环内使用，dict 读写为同步原子操作；``invalidate`` 通过 epoch
    使进行中的旧计算失效（见模块 docstring）。
    """

    def __init__(self) -> None:
        self._entries: Dict[str, OrphanStats] = {}
        self._epoch = 0

    def get(self, scan_id: str) -> Tuple[int, Optional[OrphanStats]]:
        """返回 ``(epoch, value)``；未命中时 value 为 None。调用方把 epoch 原样传给 set。"""
        return (self._epoch, self._entries.get(scan_id))

    def set(self, scan_id: str, epoch: int, value: OrphanStats) -> None:
        """仅在 ``epoch == 当前代际`` 时写入（失效后旧计算直接丢弃）。"""
        if epoch != self._epoch:
            return
        self._entries[scan_id] = value
        if len(self._entries) > _MAX_CACHE_ENTRIES:
            oldest_key = next(iter(self._entries))
            del self._entries[oldest_key]

    def invalidate(self, scan_id: Optional[str] = None) -> None:
        """失效缓存；``scan_id=None`` 全清并推进代际（默认，失效低频且成本 O(1)）。

        定点失效保留在 API 中供未来精确失效与单测使用；本次生产路径一律全清，
        与"统计影响面为全局候选/明细"的语义解耦，永不出错。
        """
        if scan_id is not None:
            self._entries.pop(scan_id, None)
            return
        self._epoch += 1
        self._entries.clear()


orphan_stats_cache = OrphanStatsCache()
