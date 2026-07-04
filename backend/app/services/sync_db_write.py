# -*- coding: utf-8 -*-
"""
同步任务 DB 写入治理工具

提供变更检测与批量 upsert 公共工具，配合 admission_controller.db_write_scope
串行化 DB 写者，治理后台同步任务对 SQLite 写锁与硬盘的高频小写入放大。

设计原则（详见 backend/docs/constraints/sync-db-write-governance.md）：
1. 变更检测：状态无变化不写库（has_*_changes 纯函数）。
2. 批量 upsert：内存聚合 + 单事务提交（bulk_upsert_with_retry）。
3. db_write_scope 只包裹 commit 阶段，远程下载器调用在临界区外。

接入对象：torrents_async.py 的 info_only / tracker_only 同步函数。
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.resource_guard import admission_controller

logger = logging.getLogger(__name__)


# =============================================================================
# 变更检测纯函数
# =============================================================================


def _normalize_str(value: Any) -> str:
    """字符串归一化：None/空串 统一为 ""，其余 strip 首尾空白。

    用于 has_tracker_changes / has_torrent_info_changes 的字段对比，
    避免 "announce ok" vs "announce ok "（尾空格）/ None vs "" 误判为变化。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_scalar(value: Any) -> Any:
    """标量归一化：None 保持 None，其它原样返回（用于 int/float 对比）。"""
    return value


# TorrentInfo 同步写入的字段白名单（仅这些 key 参与变更检测）。
# 排除 has_tracker_error / deleted_at 等非同步维护字段（审查2-D10）。
# 实际检测时取 new_mapping 的 key 与 existing 的交集，动态适配。
_TORRENT_INFO_IGNORE_KEYS = {
    "update_time",
    "create_time",
    "update_by",
    "create_by",
    "info_id",  # PK，更新时不变
    "torrent_info_id",  # 同上别名
}


def has_torrent_info_changes(existing: Dict[str, Any], new_mapping: Dict[str, Any]) -> bool:
    """检测 TorrentInfo 行是否有业务字段变化。

    只对比 new_mapping 中实际出现的 key（动态适配写入 dict 的字段集），
    排除 _TORRENT_INFO_IGNORE_KEYS（时间戳/PK 等非业务字段）。

    Args:
        existing: 现有行的字段 dict（key 为列名）。
        new_mapping: 本次准备写入的字段 dict。

    Returns:
        True 表示有业务字段变化，需要写入；False 表示无变化可跳过。
    """
    for key, new_value in new_mapping.items():
        if key in _TORRENT_INFO_IGNORE_KEYS:
            continue
        old_value = existing.get(key)
        # 字符串字段归一化对比，数值字段直接对比
        if isinstance(new_value, str) or isinstance(old_value, str):
            if _normalize_str(old_value) != _normalize_str(new_value):
                return True
        elif _normalize_scalar(old_value) != _normalize_scalar(new_value):
            return True
    return False


# TrackerInfo 变更检测的 6 个业务字段（4 announce/scrape + tracker_name + tracker_host）。
# 排除 status/msg/seeder_count/leecher_count/download_count（死字段，sync 不写它们）。
_TRACKER_CHANGE_FIELDS = (
    "last_announce_succeeded",
    "last_announce_msg",
    "last_scrape_succeeded",
    "last_scrape_msg",
    "tracker_name",
    "tracker_host",
)


def has_tracker_changes(existing_row: Dict[str, Any], new_row: Dict[str, Any]) -> bool:
    """检测 TrackerInfo 行是否有业务字段变化。

    只对比 _TRACKER_CHANGE_FIELDS 的 6 个字段；字符串字段归一化对比。
    旧值缺失（existing_row 为空 dict）时返回 True（视为需要写入）。

    Args:
        existing_row: 现有 tracker 行的字段 dict（key 为列名）。空 dict 表示无旧值。
        new_row: 本次准备写入的字段 dict。

    Returns:
        True 表示有变化需要 upsert；False 表示无变化可跳过。
    """
    if not existing_row:
        return True  # 无旧值视为新行/需要写入
    for field in _TRACKER_CHANGE_FIELDS:
        old_value = existing_row.get(field)
        new_value = new_row.get(field)
        if isinstance(new_value, str) or isinstance(old_value, str):
            if _normalize_str(old_value) != _normalize_str(new_value):
                return True
        elif _normalize_scalar(old_value) != _normalize_scalar(new_value):
            return True
    return False


# =============================================================================
# 批量 upsert + retry + db_write_scope
# =============================================================================


async def bulk_upsert_with_retry(
    db: AsyncSession,
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]],
    *,
    model: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    label: str = "bulk_upsert",
) -> None:
    """批量 upsert + retry + db_write_scope 串行化写者。

    内部用 _retry_on_db_lock 包裹 _do_bulk：
    - _do_bulk 在 db_write_scope 临界区内执行 bulk_insert_mappings + bulk_update_mappings + 单次 commit。
    - retry 退避在 db_write_scope 外（每次 attempt 重新进临界区）。
    - base_delay 默认 1.0（db_write_scope 串行化后竞争窗口短，不需要 10s 退避）。

    Args:
        db: 异步数据库会话。
        to_insert: 待插入的 mapping dict 列表。
        to_update: 待更新的 mapping dict 列表。
        model: SQLAlchemy ORM 模型类（如 TorrentInfo）。
        max_retries: 最大重试次数（数据库锁冲突时）。
        base_delay: 退避基础延迟（秒，指数增长）。
        label: 日志标签（溯源用）。
    """
    if not to_insert and not to_update:
        return

    # 延迟导入避免循环依赖（torrents_async 会导入本模块）
    from app.api.endpoints.torrents_async import _retry_on_db_lock

    async def _do_bulk() -> None:
        async with admission_controller.db_write_scope():
            if to_insert:
                await db.run_sync(lambda s: s.bulk_insert_mappings(model, to_insert))
            if to_update:
                await db.run_sync(lambda s: s.bulk_update_mappings(model, to_update))
            await db.commit()

    await _retry_on_db_lock(
        _do_bulk,
        max_retries=max_retries,
        base_delay=base_delay,
        error_context=f"{label} (insert={len(to_insert)}, update={len(to_update)})",
        rollback=db.rollback,
    )
    logger.info(
        "%s done: insert=%d, update=%d",
        label,
        len(to_insert),
        len(to_update),
    )
