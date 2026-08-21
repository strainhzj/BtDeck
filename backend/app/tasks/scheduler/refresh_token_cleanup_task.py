# -*- coding: utf-8 -*-
"""定时清理 refresh_tokens 表中过期/已撤销超过保留期的记录。

表此前无任何清理路径，登录与续期各写一行导致无限增长；本任务每日一次
批量删除，行量极小属轻量任务（未在 task_profiles 登记即按轻量放行）。
"""

from typing import Any, Dict, cast

from sqlalchemy.engine import CursorResult

from app.auth.token_cleanup import CLEANUP_SQL, DEFAULT_RETENTION_DAYS, cleanup_before
from app.database import AsyncSessionLocal


class RefreshTokenCleanupTask:
    name = "refresh token 过期记录清理任务"
    description = "每日清理 refresh_tokens 表中已过期或已撤销超过保留期的记录，活跃令牌不受影响。"
    version = "1.0.0"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        del kwargs
        async with AsyncSessionLocal() as db:
            # DELETE 运行时返回 CursorResult（Result 基类类型上无 rowcount）
            result = cast(CursorResult, await db.execute(CLEANUP_SQL, cleanup_before(DEFAULT_RETENTION_DAYS)))
            removed = int(result.rowcount or 0)
            await db.commit()
        return {
            "status": "success",
            "task_name": self.name,
            "retention_days": DEFAULT_RETENTION_DAYS,
            "deleted_rows": removed,
        }
