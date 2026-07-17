# -*- coding: utf-8 -*-
"""每日清理已超过保留期的孤儿文件隔离区。"""

from typing import Any, Dict

from app.database import AsyncSessionLocal
from app.services.orphan_file_service import OrphanFileService


class OrphanQuarantinePurgeTask:
    name = "孤儿文件隔离区到期清理任务"
    description = "每日清理超过隔离保留期且仍未被种子引用的文件"
    version = "1.0.0"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        app = kwargs.get("app")
        store = getattr(getattr(app, "state", None), "store", None)
        async with AsyncSessionLocal() as db:
            service = OrphanFileService(db)
            result = await service.purge_expired_quarantine(store=store)
        return {
            "status": "skipped" if result.get("rejected") else "success",
            "task_name": self.name,
            "purge_result": result,
        }
