# -*- coding: utf-8 -*-
"""
孤儿文件操作跨进程 lease（v1.0.6+ 语义重做）

保护扫描/预览/手动清理/自动清理互斥，防止跨进程竞争。
lease 表在 Phase 3 迁移创建（orphan_operation_lease）。

语义：
- acquire_lease(lease_key, owner, ttl, db) → bool：原子抢占；已存在且未过期→False；过期→覆盖
- renew_lease(lease_key, owner, ttl, db) → bool：续期（仅持有者可续）
- release_lease(lease_key, owner, db) → bool：释放（仅持有者可释放）

所有函数接受可选 db 参数（测试注入临时 DB）；不传则开生产 AsyncSessionLocal。

lease 表结构：
- lease_key: PK（如 orphan_scan / orphan_cleanup）
- owner: 持有者标识（进程ID+UUID）
- acquired_at / expires_at

@file: orphan_lease.py
@time: 2026-07-11
"""

import logging
import os
import uuid
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

ORPHAN_MAINTENANCE_LEASE = "orphan_maintenance"


class OrphanLeaseBusyError(RuntimeError):
    """另一个进程正在执行孤儿文件维护。"""


class OrphanLeaseHandle:
    """维护租约句柄；危险操作前必须确认租约仍归当前 worker。"""

    def __init__(self, owner: str):
        self.owner = owner
        self.lost = asyncio.Event()

    async def assert_owned(self) -> None:
        if (
            self.lost.is_set()
            or await get_lease_holder(ORPHAN_MAINTENANCE_LEASE) != self.owner
        ):
            self.lost.set()
            raise OrphanLeaseBusyError("孤儿维护租约已丢失，停止文件操作")


def _make_owner() -> str:
    """生成进程唯一标识（PID + UUID）。"""
    return f"pid-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _parse_dt(val: object) -> datetime:
    """将 SQLite 原生 SQL 返回的 datetime 值解析为 datetime 对象。

    SQLite 可能返回字符串（ISO 格式）或已是 datetime（ORM 路径）。
    """
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        # SQLite 存储格式：YYYY-MM-DD HH:MM:SS.ffffff
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            try:
                return datetime.strptime(val, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
    return datetime.utcnow()


@asynccontextmanager
async def _get_db(db: Optional[AsyncSession] = None):
    """获取 DB session：传入则直接用，否则开生产 AsyncSessionLocal。

    注意：不在此处加 db_write_scope（lease 操作本身需要调用方控制事务边界，
    且测试注入的 DB 不应走生产 admission_controller）。
    """
    if db is not None:
        yield db
    else:
        from app.tasks.resource_guard import admission_controller

        async with AsyncSessionLocal() as session:
            async with admission_controller.db_write_scope():
                yield session


async def acquire_lease(
    lease_key: str,
    owner: Optional[str] = None,
    ttl: Optional[int] = None,
    db: Optional[AsyncSession] = None,
) -> bool:
    """原子获取跨进程 lease。

    策略（SQLite 友好，避免 ON CONFLICT 方言差异）：
    1. 查询 lease 是否存在
    2. 不存在 → INSERT（成功=True）
    3. 存在但已过期 → UPDATE 覆盖（成功=True）
    4. 存在且未过期 → 失败（False）

    Args:
        lease_key: 租约键（如 orphan_scan / orphan_cleanup）
        owner: 持有者标识（None 自动生成）
        ttl: TTL 秒数（None 取 settings.ORPHAN_LEASE_TTL_SECONDS）
        db: 可选 DB session（测试注入；不传则开生产 session + db_write_scope）

    Returns:
        是否成功获取
    """
    owner = owner or _make_owner()
    ttl_seconds = ttl if ttl is not None else settings.ORPHAN_LEASE_TTL_SECONDS
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)

    async with _get_db(db) as session:
        inserted = await session.execute(
            sa_text(
                "INSERT OR IGNORE INTO orphan_operation_lease "
                "(lease_key, owner, acquired_at, expires_at) "
                "VALUES (:key, :owner, :now, :expires)"
            ),
            {"key": lease_key, "owner": owner, "now": now, "expires": expires_at},
        )
        if inserted.rowcount == 1:
            await session.commit()
            logger.info(f"[孤儿lease] 获取成功 key={lease_key} owner={owner}")
            return True

        taken_over = await session.execute(
            sa_text(
                "UPDATE orphan_operation_lease "
                "SET owner = :owner, acquired_at = :now, expires_at = :expires "
                "WHERE lease_key = :key AND expires_at < :now"
            ),
            {"owner": owner, "now": now, "expires": expires_at, "key": lease_key},
        )
        if taken_over.rowcount == 1:
            await session.commit()
            logger.info(f"[孤儿lease] 过期接管成功 key={lease_key} owner={owner}")
            return True
        await session.rollback()
        logger.debug(f"[孤儿lease] 获取失败 key={lease_key} owner={owner}")
        return False


async def renew_lease(
    lease_key: str,
    owner: str,
    ttl: Optional[int] = None,
    db: Optional[AsyncSession] = None,
) -> bool:
    """续期 lease（仅持有者可续）。"""
    ttl_seconds = ttl if ttl is not None else settings.ORPHAN_LEASE_TTL_SECONDS
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)

    async with _get_db(db) as session:
        result = await session.execute(
            sa_text(
                "UPDATE orphan_operation_lease SET expires_at = :expires "
                "WHERE lease_key = :key AND owner = :owner"
            ),
            {"expires": expires_at, "key": lease_key, "owner": owner},
        )
        await session.commit()
        return result.rowcount > 0


async def release_lease(
    lease_key: str,
    owner: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> bool:
    """释放 lease（仅持有者可释放）。"""
    if not owner:
        raise ValueError("release_lease 必须提供 owner")
    async with _get_db(db) as session:
        result = await session.execute(
            sa_text(
                "DELETE FROM orphan_operation_lease WHERE lease_key = :key AND owner = :owner"
            ),
            {"key": lease_key, "owner": owner},
        )
        await session.commit()
        return result.rowcount > 0


async def get_lease_holder(
    lease_key: str, db: Optional[AsyncSession] = None
) -> Optional[str]:
    """查询 lease 当前持有者（未过期才有值）。"""
    now = datetime.utcnow()
    async with _get_db(db) as session:
        result = await session.execute(
            sa_text(
                "SELECT owner, expires_at FROM orphan_operation_lease WHERE lease_key = :key"
            ),
            {"key": lease_key},
        )
        row = result.fetchone()
        if row and _parse_dt(row[1]) >= now:
            return row[0]
        return None


@asynccontextmanager
async def orphan_maintenance_scope(operation: str, ttl: Optional[int] = None):
    """统一跨进程维护 lease，始终使用独立 session。"""
    owner = f"{operation}-{_make_owner()}"
    ttl_seconds = ttl if ttl is not None else settings.ORPHAN_LEASE_TTL_SECONDS
    if not await acquire_lease(ORPHAN_MAINTENANCE_LEASE, owner=owner, ttl=ttl_seconds):
        raise OrphanLeaseBusyError("另一个孤儿文件维护操作正在运行")

    stopped = asyncio.Event()
    handle = OrphanLeaseHandle(owner)

    async def heartbeat() -> None:
        interval = max(1, ttl_seconds // 3)
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=interval)
            except asyncio.TimeoutError:
                if not await renew_lease(
                    ORPHAN_MAINTENANCE_LEASE, owner, ttl=ttl_seconds
                ):
                    logger.error(
                        "[孤儿lease] 续期失败 operation=%s owner=%s", operation, owner
                    )
                    handle.lost.set()
                    stopped.set()

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        yield handle
    finally:
        stopped.set()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await release_lease(ORPHAN_MAINTENANCE_LEASE, owner=owner)
