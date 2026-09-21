# -*- coding: utf-8 -*-
"""定时任务与主机能力的运行时映射。

该模块只描述“任务需要什么宿主能力”，不改写数据库中的 enabled 配置。
Android 主服务端启动时仍保留历史任务，调度/手动执行入口统一按此映射门控，
切回桌面/NAS 后无需恢复配置即可继续使用。
"""

import json
from typing import Any, Dict, Optional

from app.core.platform_capabilities import LEVEL_SUPPORTED, capability_level


TASK_REQUIRED_CAPABILITIES: Dict[str, str] = {
    "downloader_path_scan": "path_mapping",
    "orphan_scan_cleanup": "orphan_files",
    "orphan_quarantine_purge": "orphan_files",
    "orphan_notification_retry": "orphan_files",
    "orphan_hardlink_copy_scan": "orphan_files",
}

PLATFORM_CAPABILITY_SKIP_REASON = "platform_capability_unsupported"


def required_capability_for_task(task: Dict[str, Any]) -> Optional[str]:
    """返回任务所需能力；无法解析的自定义任务不在本模块拦截。"""

    task_code = str(task.get("task_code") or "")
    required = TASK_REQUIRED_CAPABILITIES.get(task_code)
    if required:
        return required

    # task_type=5 的清理任务可以同时包含等级 3/4。只在实际请求等级 3 时门控，
    # 这样 Android 仍可执行安全的等级 4 标签清理。
    if task.get("task_type") == 5:
        try:
            config = json.loads(task.get("executor") or "{}")
        except (TypeError, json.JSONDecodeError):
            return None
        if isinstance(config, dict) and config.get("cleanup_level_3") is True:
            return "level3_recycle"
    return None


def capability_block_for_task(task: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """返回不可执行原因；可执行时返回 ``None``。"""

    capability = required_capability_for_task(task)
    if not capability:
        return None
    level = capability_level(capability)
    if level == LEVEL_SUPPORTED:
        return None
    return {
        "capability": capability,
        "reason_code": PLATFORM_CAPABILITY_SKIP_REASON,
        "message": f"当前主机形态不支持任务所需能力: {capability}",
    }
