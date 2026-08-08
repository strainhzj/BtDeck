# -*- coding: utf-8 -*-
"""
同步任务 DB 写入治理工具

提供变更检测与批量 upsert 公共工具，配合 admission_controller.db_write_scope
串行化 DB 写者，治理后台同步任务对 SQLite 写锁与硬盘的高频小写入放大。

设计原则（详见 backend/docs/constraints/sync-db-write-governance.md）：
1. 变更检测：状态无变化不写库（has_*_changes 纯函数）。
2. 批量 upsert：内存聚合 + 真实分批提交（bulk_upsert_with_retry，
   W1-1：每批独立 commit，形成真实提交边界，消除单大事务对 SQLite
   写锁的长时间持有；锁冲突只重试当前批，退避有上限）。
3. db_write_scope 只包裹 commit 阶段，远程下载器调用在临界区外。

接入对象：torrents_async.py 的 info_only / tracker_only 同步函数。
"""

import asyncio
import logging
import random
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.tasks.resource_guard import admission_controller

logger = logging.getLogger(__name__)


# =============================================================================
# 写入统计结构
# =============================================================================


@dataclass
class WriteStats:
    """批量写入统计（W1-1 真分批提交）。

    - scanned: 待写入总行数（to_insert + to_update）。
    - changed: 实际写入行数（成功提交的行数）。
    - committed: 成功提交的批内总行数（应等于 changed）。
    - batches: 实际执行的 commit 批次数（不含空批）。
    - retries: 锁冲突重试总次数（只重试当前失败批，已提交批不受影响）。
    - elapsed_ms: 整个写入耗时（毫秒）。
    """

    scanned: int = 0
    changed: int = 0
    committed: int = 0
    batches: int = 0
    retries: int = 0
    elapsed_ms: float = 0.0


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
# 批量 upsert + 真实分批提交 + 批级重试 + db_write_scope
# =============================================================================

# SQLite 锁冲突错误码集合（按错误码分类判定，禁止消息字符串匹配）：
# 5=SQLITE_BUSY、6=SQLITE_LOCKED；扩展码
# 261=SQLITE_BUSY_SNAPSHOT、262=SQLITE_LOCKED_SHAREDCACHE、
# 266=SQLITE_BUSY_RECOVERY、517=SQLITE_LOCKED_VTAB。
_SQLITE_LOCK_ERROR_CODES = frozenset({5, 6, 261, 262, 266, 517})


class ChunkedWriteError(Exception):
    """分批写入失败异常：携带已提交批次的部分进度统计。

    - stats: 失败时已完成（已提交批）的写入统计，未提交批不计入。
    - 原始失败异常保留在 __cause__（异常链不丢失）。
    """

    def __init__(self, message: str, stats: WriteStats):
        super().__init__(message)
        self.stats = stats


def _is_sqlite_lock_conflict(exc: BaseException) -> bool:
    """SQLite 锁冲突判定（基于错误码分类，禁止消息字符串匹配）。

    判定顺序：
    1. SQLAlchemy 包装异常的 orig（原始 DBAPI 驱动异常）上的 sqlite_errorcode；
    2. 异常自身携带的 sqlite_errorcode（裸 sqlite3 异常，驱动抛出时自动设置）；
    3. 降级：sqlite_errorname 属性（SQLITE_BUSY / SQLITE_LOCKED）；
    4. 最终降级：错误码与错误名均不可得（旧版 Python / 自定义异常）时，
       仅按异常类型保守判断——裸 sqlite3.OperationalError 才视为锁冲突。
    """
    candidate = getattr(exc, "orig", None)
    if candidate is None:
        candidate = exc

    code = getattr(candidate, "sqlite_errorcode", None)
    if isinstance(code, int) and code != 0:
        return code in _SQLITE_LOCK_ERROR_CODES

    name = getattr(candidate, "sqlite_errorname", None)
    if name:
        return name in ("SQLITE_BUSY", "SQLITE_LOCKED")

    # 最终降级：SQLite 驱动对 BUSY/LOCKED 均抛 sqlite3.OperationalError；
    # 其余异常类型（含 IntegrityError 等）一律视为非锁冲突、不重试。
    return isinstance(candidate, sqlite3.OperationalError)


def _compute_backoff_delay(
    retry_index: int,
    base_delay: float,
    total_backoff: float,
    max_total_backoff: float,
) -> float:
    """计算一次重试退避（秒）：有限指数退避 + 抖动，且累计睡眠不超过上限。

    Args:
        retry_index: 第几次重试（从 1 开始）。
        base_delay: 基础延迟（秒，指数增长）。
        total_backoff: 本批已累计睡眠（秒）。
        max_total_backoff: 本批重试总睡眠上限（秒，防止排队雪崩）。

    Returns:
        本次应睡眠的秒数（可能为 0，表示预算已耗尽）。
    """
    raw = base_delay * (2 ** (retry_index - 1))
    jittered = random.uniform(raw * 0.5, raw * 1.5)
    remaining = max(0.0, max_total_backoff - total_backoff)
    return min(jittered, remaining)


def _build_chunked_batches(
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]],
    batch_size: int,
) -> List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """把 insert/update 行列表按 batch_size 切分为有序批次序列。

    批次顺序：先 insert 块、后 update 块。调用方保证同一行不会同时出现在
    insert 与 update，因此顺序不影响正确性；每个批次对应一次真实 commit。
    """
    batches: List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]] = []
    for i in range(0, len(to_insert), batch_size):
        batches.append((to_insert[i : i + batch_size], []))
    for i in range(0, len(to_update), batch_size):
        batches.append(([], to_update[i : i + batch_size]))
    return batches


async def _safe_rollback(db: AsyncSession, label: str, batch_index: int) -> None:
    """尽力回滚失败批的事务，失败只记录警告（不掩盖原始锁冲突原因）。"""
    try:
        await db.rollback()
    except Exception as rb_err:  # pragma: no cover - 防御路径
        logger.warning(
            "sync_db_write rollback_failed label=%s batch_index=%d error=%r",
            label,
            batch_index,
            rb_err,
        )


async def _execute_batch_once(
    db: AsyncSession,
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]],
    *,
    model: Any,
) -> int:
    """在 db_write_scope 临界区内执行一个批次 DML 并真实 commit。

    Returns:
        该批成功写入的行数。

    commit 成功后主动让出事件循环（批间让行，避免长循环饿死其它协程）。
    """
    async with admission_controller.db_write_scope():
        if to_insert:
            await db.run_sync(lambda s: s.bulk_insert_mappings(model, to_insert))
        if to_update:
            await db.run_sync(lambda s: s.bulk_update_mappings(model, to_update))
        await db.commit()
    # 批间让行：主动让出事件循环，避免 async 线程饿死
    await asyncio.sleep(0)
    return len(to_insert) + len(to_update)


async def _commit_batch_with_retry(
    db: AsyncSession,
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]],
    *,
    model: Any,
    label: str,
    batch_index: int,
    max_attempts: int,
    base_delay: float,
    max_total_backoff: float,
    stats: WriteStats,
) -> int:
    """提交一个批次：锁冲突只重试当前批，非锁异常立即失败。

    - 锁冲突（SQLite BUSY/LOCKED 错误码）：有限指数退避 + 抖动，最多
      max_attempts 次尝试；单批重试总睡眠不超过 max_total_backoff。
    - 非锁异常（IntegrityError、SQL 语法错误等）：立即失败，原样上抛
      （异常链保留，不包装吞掉原因）。
    - 已提交的批不受影响；本函数只重试当前失败批，重试前回滚失败批事务。

    Returns:
        成功提交的行数。
    """
    attempt = 0
    total_backoff = 0.0
    while True:
        attempt_start = time.perf_counter()
        try:
            rows = await _execute_batch_once(db, to_insert, to_update, model=model)
            commit_ms = (time.perf_counter() - attempt_start) * 1000.0
            logger.info(
                "sync_db_write batch_done label=%s batch_index=%d batch_rows=%d "
                "changed_rows=%d commit_ms=%.1f lock_wait_ms=%.1f retry_count=%d",
                label,
                batch_index,
                rows,
                rows,
                commit_ms,
                total_backoff * 1000.0,
                attempt,
            )
            return rows
        except Exception as e:
            if not _is_sqlite_lock_conflict(e):
                # 非锁异常：立即失败且不重试，原异常上抛
                raise
            attempt += 1
            if attempt >= max_attempts:
                # 已达最大尝试次数：回滚失败批事务后抛出，携带已提交进度
                await _safe_rollback(db, label, batch_index)
                raise ChunkedWriteError(
                    f"{label} 分批写入失败：已提交 {stats.batches} 批 / {stats.committed} 行，"
                    f"第 {batch_index} 批（{len(to_insert) + len(to_update)} 行）尝试 "
                    f"{max_attempts} 次仍遇锁冲突",
                    stats=stats,
                ) from e
            # 回滚失败批的事务状态，保证重试时事务干净
            await _safe_rollback(db, label, batch_index)
            stats.retries += 1
            delay = _compute_backoff_delay(attempt, base_delay, total_backoff, max_total_backoff)
            total_backoff += delay
            logger.warning(
                "sync_db_write batch_retry label=%s batch_index=%d attempt=%d "
                "max_attempts=%d backoff_s=%.3f total_backoff_s=%.3f",
                label,
                batch_index,
                attempt,
                max_attempts,
                delay,
                total_backoff,
            )
            if delay > 0:
                await asyncio.sleep(delay)


async def bulk_upsert_with_retry(
    db: AsyncSession,
    to_insert: List[Dict[str, Any]],
    to_update: List[Dict[str, Any]],
    *,
    model: Any,
    max_retries: Optional[int] = None,
    base_delay: float = 1.0,
    label: str = "bulk_upsert",
    batch_size: Optional[int] = None,
) -> WriteStats:
    """批量 upsert + 真实分批提交 + 批级重试 + db_write_scope 串行化写者。

    核心语义（W1-1，PLANS/sync-database-blocking-remediation.md）：
    - 真实分批：to_insert / to_update 各自按 batch_size 分块，每批进入
      db_write_scope → 执行该批 DML → 独立 commit，形成真实提交边界，
      不再由一次全量同步持续持有 SQLite 写锁。
    - 批级重试：锁冲突只重试当前失败批，已提交的批不回滚、不重复提交；
      退避为有限指数退避 + 抖动，单批重试总睡眠不超过
      settings.SYNC_DB_RETRY_MAX_BACKOFF_SECONDS（防止排队雪崩）。
    - 非锁异常（IntegrityError、SQL 语法错误、编程错误）立即失败且不重试，
      原异常链保留。
    - 空输入（to_insert 与 to_update 均为空）不创建事务、不 commit、
      不进 db_write_scope，直接返回零值 WriteStats。
    - SYNC_CHUNKED_COMMIT_ENABLED=False 时回退旧行为：单事务一次提交。

    Args:
        db: 异步数据库会话。
        to_insert: 待插入的 mapping dict 列表。
        to_update: 待更新的 mapping dict 列表。
        model: SQLAlchemy ORM 模型类（如 TorrentInfo）。
        max_retries: 单批最大尝试次数（含首次）；None 时取
            settings.SYNC_DB_LOCK_RETRY_COUNT。
        base_delay: 退避基础延迟（秒，指数增长 + 抖动，默认 1.0）。
        label: 日志标签（溯源用）。
        batch_size: 真实提交批大小；None 时取 settings.SYNC_DB_COMMIT_BATCH_SIZE。

    Returns:
        WriteStats 统计对象（scanned/changed/committed/batches/retries/elapsed_ms）。
        某批最终失败时抛 ChunkedWriteError（携带已提交批的统计，
        原异常为 __cause__）。
    """
    scanned = len(to_insert) + len(to_update)
    if scanned == 0:
        return WriteStats()

    batch_size = int(batch_size or settings.SYNC_DB_COMMIT_BATCH_SIZE)
    if batch_size < 1:
        batch_size = 1
    max_attempts = max_retries if max_retries is not None else settings.SYNC_DB_LOCK_RETRY_COUNT
    if max_attempts < 1:
        max_attempts = 1
    max_total_backoff = max(0.0, settings.SYNC_DB_RETRY_MAX_BACKOFF_SECONDS)
    chunked = bool(settings.SYNC_CHUNKED_COMMIT_ENABLED)

    if chunked:
        batches = _build_chunked_batches(to_insert, to_update, batch_size)
    else:
        # 回退路径：单事务一次提交（旧行为）
        batches = [(to_insert, to_update)]

    stats = WriteStats(scanned=scanned)
    start_ts = time.perf_counter()
    try:
        for batch_index, (ins_rows, upd_rows) in enumerate(batches):
            rows = await _commit_batch_with_retry(
                db,
                ins_rows,
                upd_rows,
                model=model,
                label=label,
                batch_index=batch_index,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_total_backoff=max_total_backoff,
                stats=stats,
            )
            stats.committed += rows
            stats.batches += 1
    except ChunkedWriteError:
        logger.warning(
            "%s partial: committed=%d, batches=%d, retries=%d",
            label,
            stats.committed,
            stats.batches,
            stats.retries,
        )
        raise
    except Exception:
        logger.warning(
            "%s partial: committed=%d, batches=%d, retries=%d",
            label,
            stats.committed,
            stats.batches,
            stats.retries,
        )
        raise
    finally:
        stats.elapsed_ms = (time.perf_counter() - start_ts) * 1000.0

    stats.changed = stats.committed
    logger.info(
        "%s done: insert=%d, update=%d, batches=%d, retries=%d, elapsed_ms=%.1f",
        label,
        len(to_insert),
        len(to_update),
        stats.batches,
        stats.retries,
        stats.elapsed_ms,
    )
    return stats
