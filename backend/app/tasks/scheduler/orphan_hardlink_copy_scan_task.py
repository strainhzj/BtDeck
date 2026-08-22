# -*- coding: utf-8 -*-
"""定时预扫描孤儿文件的硬链接副本位置，结果落库供前端只读查询。

大文件系统上的整体目录遍历耗时不可控，因此不在交互请求里执行；本任务按轮
推进（stat 限量、遍历限量、单调时钟预算、路径上限），性能护栏详见
``app/services/orphan_hardlink_scan_service.py`` 模块注释与 Settings 配置。
"""

from typing import Any, Dict

from app.database import AsyncSessionLocal
from app.services.orphan_hardlink_scan_service import OrphanHardlinkScanService


class OrphanHardlinkCopyScanTask:
    name = "孤儿硬链接副本预扫描任务"
    description = "按轮预扫描孤儿文件的硬链接副本位置并落库；前端点击副本数量只读结果，不再实时遍历目录。"
    version = "1.0.0"

    async def execute(self, **kwargs) -> Dict[str, Any]:
        del kwargs
        async with AsyncSessionLocal() as db:
            service = OrphanHardlinkScanService(db)
            result = await service.run_round()
        return {
            "status": result.get("status", "failed"),
            "task_name": self.name,
            "scan_result": result,
        }
