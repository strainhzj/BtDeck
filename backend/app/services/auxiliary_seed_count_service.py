"""辅种数量计算与增量维护。

辅种数量以 ``name + size`` 为全局匹配键，跨下载器、跨同步
任务统计。全量刷新只由种子信息同步任务调用；删除、转移和还原接口只调用
本模块的单分组增量函数，避免列表查询时实时分组计算。
"""

from numbers import Number
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.tasks.resource_guard import admission_controller
from app.torrents.models import TorrentInfo

AuxiliarySeedKey = Tuple[str, Number]


def make_auxiliary_seed_key(name: Any, size: Any) -> Optional[AuxiliarySeedKey]:
    """从字段值构造有效的辅种匹配键。

    ``torrent_file`` 和 ``save_path`` 都不参与匹配：前者通常带有各自的
    info-hash 文件名，后者可能因下载器路径映射不同而变化。
    """

    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(size, Number) or isinstance(size, bool):
        return None
    return name, size


def get_auxiliary_seed_key(torrent: Any) -> Optional[AuxiliarySeedKey]:
    """从 TorrentInfo 或测试替身中提取辅种匹配键。"""

    return make_auxiliary_seed_key(
        getattr(torrent, "name", None),
        getattr(torrent, "size", None),
    )


def _active_clause(model: Any):
    return and_(model.dr == 0, model.deleted_at.is_(None))


def _valid_key_clause(model: Any):
    return and_(
        model.name.is_not(None),
        func.trim(model.name) != "",
        model.size.is_not(None),
    )


def _key_clause(model: Any, key: AuxiliarySeedKey):
    name, size = key
    return and_(model.name == name, model.size == size)


def _safe_count(value: Any) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def get_active_auxiliary_seed_count(db: Session, key: Optional[AuxiliarySeedKey]) -> Optional[int]:
    """读取分组中任一当前有效行的缓存数量，用于还原时做增量加一。"""

    if key is None:
        return None
    row = (
        db.query(TorrentInfo.auxiliary_seed_count)
        .filter(_active_clause(TorrentInfo), _key_clause(TorrentInfo, key))
        .first()
    )
    if row is None:
        return None
    return _safe_count(row[0])


def _build_refresh_statement():
    """构造一次 SQL 全表校正语句，避免逐行查询和提交。"""

    peer = TorrentInfo.__table__.alias("auxiliary_seed_peer")
    peer_count = (
        select(func.count())
        .select_from(peer)
        .where(
            peer.c.dr == 0,
            peer.c.deleted_at.is_(None),
            peer.c.name.is_not(None),
            func.trim(peer.c.name) != "",
            peer.c.size.is_not(None),
            peer.c.name == TorrentInfo.name,
            peer.c.size == TorrentInfo.size,
        )
        .correlate(TorrentInfo.__table__)
        .scalar_subquery()
    )

    return (
        update(TorrentInfo)
        .where(_active_clause(TorrentInfo))
        .values(
            auxiliary_seed_count=case(
                (_valid_key_clause(TorrentInfo), peer_count),
                else_=1,
            )
        )
    )


async def refresh_auxiliary_seed_counts(db: AsyncSession) -> Dict[str, int]:
    """全量刷新当前有效种子的辅种数量。"""

    try:
        async with admission_controller.db_write_scope():
            result = await db.execute(_build_refresh_statement())
            await db.commit()
    except Exception:
        await db.rollback()
        raise

    return {"updated_count": int(getattr(result, "rowcount", 0) or 0)}


def _decrement_statement(key: AuxiliarySeedKey):
    current_count = func.coalesce(TorrentInfo.auxiliary_seed_count, 1)
    return (
        update(TorrentInfo)
        .where(_active_clause(TorrentInfo), _key_clause(TorrentInfo, key))
        .values(
            auxiliary_seed_count=case(
                (current_count > 1, current_count - 1),
                else_=1,
            )
        )
    )


def decrement_auxiliary_seed_count(db: Session, key: Optional[AuxiliarySeedKey]) -> int:
    """同步会话中将一个已移除副本的分组数量减一。"""

    if key is None:
        return 0
    result = db.execute(_decrement_statement(key))
    return int(getattr(result, "rowcount", 0) or 0)


async def decrement_auxiliary_seed_count_async(db: Any, key: Optional[AuxiliarySeedKey]) -> int:
    """异步会话中将一个已移除副本的分组数量减一。"""

    if key is None:
        return 0
    result = await db.execute(_decrement_statement(key))
    return int(getattr(result, "rowcount", 0) or 0)


def set_active_auxiliary_seed_count(db: Session, key: Optional[AuxiliarySeedKey], count: Any) -> int:
    """同步会话中把有效分组统一设置为指定数量。"""

    if key is None:
        return 0
    result = db.execute(
        update(TorrentInfo)
        .where(_active_clause(TorrentInfo), _key_clause(TorrentInfo, key))
        .values(auxiliary_seed_count=_safe_count(count))
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def set_active_auxiliary_seed_count_async(db: Any, key: Optional[AuxiliarySeedKey], count: Any) -> int:
    """异步会话中把有效分组统一设置为指定数量。"""

    if key is None:
        return 0
    result = await db.execute(
        update(TorrentInfo)
        .where(_active_clause(TorrentInfo), _key_clause(TorrentInfo, key))
        .values(auxiliary_seed_count=_safe_count(count))
    )
    return int(getattr(result, "rowcount", 0) or 0)


__all__ = [
    "AuxiliarySeedKey",
    "decrement_auxiliary_seed_count",
    "decrement_auxiliary_seed_count_async",
    "get_auxiliary_seed_key",
    "get_active_auxiliary_seed_count",
    "make_auxiliary_seed_key",
    "refresh_auxiliary_seed_counts",
    "set_active_auxiliary_seed_count",
    "set_active_auxiliary_seed_count_async",
]
