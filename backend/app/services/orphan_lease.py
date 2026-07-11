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
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


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
        # 查询现有 lease
        result = await session.execute(
            sa_text("SELECT owner, expires_at FROM orphan_operation_lease WHERE lease_key = :key"),
            {"key": lease_key},
        )
        row = result.fetchone()

        if row is None:
            # 不存在 → INSERT
            await session.execute(
                sa_text(
                    "INSERT INTO orphan_operation_lease (lease_key, owner, acquired_at, expires_at) "
                    "VALUES (:key, :owner, :now, :expires)"
                ),
                {"key": lease_key, "owner": owner, "now": now, "expires": expires_at},
            )
            await session.commit()
            logger.info(f"[孤儿lease] 获取成功 key={lease_key} owner={owner}")
            return True

        existing_owner, existing_expires = row
        # SQLite 原生 SQL 返回 datetime 为字符串，需解析
        existing_expires_dt = _parse_dt(existing_expires)
        # 存在但已过期 → UPDATE 覆盖
        if existing_expires_dt < now:
            await session.execute(
                sa_text(
                    "UPDATE orphan_operation_lease SET owner = :owner, acquired_at = :now, expires_at = :expires "
                    "WHERE lease_key = :key"
                ),
                {"owner": owner, "now": now, "expires": expires_at, "key": lease_key},
            )
            await session.commit()
            logger.info(f"[孤儿lease] 过期接管成功 key={lease_key} owner={owner} (原 owner={existing_owner})")
            return True

        # 存在且未过期 → 失败
        logger.debug(
            f"[孤儿lease] 获取失败 key={lease_key} owner={owner} "
            f"(被 {existing_owner} 持有，过期时间 {existing_expires})"
        )
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
                "UPDATE orphan_operation_lease SET expires_at = :expires " "WHERE lease_key = :key AND owner = :owner"
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
    """释放 lease（仅持有者可释放；owner=None 时删除任意持有者的 lease）。"""
    async with _get_db(db) as session:
        if owner:
            result = await session.execute(
                sa_text("DELETE FROM orphan_operation_lease WHERE lease_key = :key AND owner = :owner"),
                {"key": lease_key, "owner": owner},
            )
        else:
            result = await session.execute(
                sa_text("DELETE FROM orphan_operation_lease WHERE lease_key = :key"),
                {"key": lease_key},
            )
        await session.commit()
        return result.rowcount > 0


async def get_lease_holder(lease_key: str, db: Optional[AsyncSession] = None) -> Optional[str]:
    """查询 lease 当前持有者（未过期才有值）。"""
    now = datetime.utcnow()
    async with _get_db(db) as session:
        result = await session.execute(
            sa_text("SELECT owner, expires_at FROM orphan_operation_lease WHERE lease_key = :key"),
            {"key": lease_key},
        )
        row = result.fetchone()
        if row and _parse_dt(row[1]) >= now:
            return row[0]
        return None
