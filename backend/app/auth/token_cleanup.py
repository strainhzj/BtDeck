# -*- coding: utf-8 -*-
"""refresh_tokens 表的过期记录清理（双令牌体系 W6-1 伴随运维项）。

refresh_tokens 每次登录/续期各 +1 行且此前无任何清理路径，长期运行无限
增长，拖慢 logout/changePassword 的"撤销全部"与 /auth/refresh 的条件
UPDATE 扫描面。本模块供定时任务调用，删除已过期或已撤销超过保留期的
记录（保留期内记录留存供安全追溯），不触碰活跃令牌。
"""

import logging
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 与孤儿扫描结果保留 30 天的既有惯例对齐；可按追溯需求调整
DEFAULT_RETENTION_DAYS = 30

CLEANUP_SQL = text(
    """
    DELETE FROM refresh_tokens
    WHERE expires_at < :expired_before
       OR (revoked_at IS NOT NULL AND revoked_at < :revoked_before)
    """
)


def cleanup_before(retention_days: int = DEFAULT_RETENTION_DAYS) -> dict:
    """构造清理阈值参数（过期与撤销共用同一保留期）。"""
    before = datetime.utcnow() - timedelta(days=retention_days)
    return {"expired_before": before, "revoked_before": before}


def cleanup_expired_refresh_tokens(db: Session, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """同步删除过期/已撤销超过保留期的 refresh token 记录，返回删除行数。

    活跃令牌（未撤销且未过期，或撤销/过期未满保留期）不受影响。
    定时任务走异步会话直接执行 CLEANUP_SQL，本函数供测试与同步调用方使用。
    """
    # DELETE 语句运行时返回 CursorResult；Result 基类类型上无 rowcount
    deleted = cast(CursorResult, db.execute(CLEANUP_SQL, cleanup_before(retention_days))).rowcount
    db.commit()
    if deleted:
        logger.info("已清理 %d 条过期/已撤销超期 %d 天的 refresh token 记录", deleted, retention_days)
    return int(deleted or 0)
