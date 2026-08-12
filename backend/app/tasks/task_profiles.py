# -*- coding: utf-8 -*-
"""
重型同步任务资源 profile 注册表

为 TaskAdmissionController 提供按 task_code 查询的资源准入策略。
未在 TASK_PROFILES 中注册的 task_code 视为轻量任务，直接放行、不进入资源背压。

详见 PLANS/sync-resource-governance.md 阶段 1。

⚠️ 运维约束（违反会导致资源治理失效）：
- TASK_PROFILES 的 key 必须与 app/data/default_scheduled_tasks.py 的 task_code 严格一致；
  改名某重型任务的 task_code（无论在代码还是 DB）等于关闭该任务的资源治理。
- 运维不得在 DB 直接修改重型任务的 task_code；如需重命名，必须代码 + DB + task_profiles 同步改。
- 测试 tests/tasks/test_task_profiles.py::TestTaskProfilesAlignWithDefaultTasks 会自动
  校验 task_profiles 与 default_scheduled_tasks.py 的一致性，但不能拦截 DB 直改。

⚠️ 配置固化语义：
- TASK_PROFILES 在模块导入时构建，queue_limit 从 settings.SYNC_HEAVY_QUEUE_LIMIT 求值后固化。
- 运行时修改 settings.SYNC_HEAVY_QUEUE_LIMIT 不会更新已注册 profile，需重启进程。
- 这是 Pydantic settings 启动时固化的惯例，非 bug。
"""

from dataclasses import dataclass
from typing import Dict, Optional

from app.core.config import settings


@dataclass(frozen=True)
class TaskProfile:
    """单个任务的资源准入 profile。

    Attributes:
        task_code: 与 CronTask.task_code 对应的唯一编码。
        heavy_sync: 是否进入全局 heavy_sync 令牌（重型同步互斥）。
        per_downloader: 是否需要 per_downloader 互斥（阶段 2 接入预留位，本步只声明）。
        queue_limit: 同类任务最多允许排队等待的名额；超过即跳过本轮。
        wait_timeout: 进入 heavy_sync 的最大等待秒数；超时跳过本轮。
        description: 人类可读说明，便于日志溯源。
    """

    task_code: str
    heavy_sync: bool
    per_downloader: bool
    queue_limit: int
    wait_timeout: float
    description: str = ""


def _heavy(task_code: str, description: str, wait_timeout: float = 30.0) -> TaskProfile:
    """构造默认参数的重型任务 profile（heavy_sync=True）。

    queue_limit 取自全局配置 settings.SYNC_HEAVY_QUEUE_LIMIT，保持运行时可调。
    """
    return TaskProfile(
        task_code=task_code,
        heavy_sync=True,
        per_downloader=False,
        queue_limit=settings.SYNC_HEAVY_QUEUE_LIMIT,
        wait_timeout=wait_timeout,
        description=description,
    )


# 重型同步任务注册表：与 app/data/default_scheduled_tasks.py 的 task_code 严格对齐。
# 新增重型任务时，必须在此登记；遗忘登记的后果是该任务绕过资源背压。
TASK_PROFILES: Dict[str, TaskProfile] = {
    "torrent_info_sync_ac608e4d": _heavy(
        "torrent_info_sync_ac608e4d",
        "种子信息同步任务（TorrentInfoSyncTask，15min）",
    ),
    "tracker_sync_598b784c": _heavy(
        "tracker_sync_598b784c",
        "Tracker 状态同步任务（TrackerSyncTask，30min）",
    ),
    "TORRENT_TRACKER_STATUS_JUDGE": _heavy(
        "TORRENT_TRACKER_STATUS_JUDGE",
        "种子 Tracker 状态判断任务（30min，Tracker 同步后错峰，批量 20k+ 种子）",
    ),
    "TRACKER_MESSAGE_LOGGER": _heavy(
        "TRACKER_MESSAGE_LOGGER",
        "Tracker 消息记录任务（1h）",
    ),
    "downloader_path_scan": _heavy(
        "downloader_path_scan",
        "下载器路径扫描任务（1h）",
    ),
    "tracker_reannounce": _heavy(
        "tracker_reannounce",
        "Tracker 汇报轮询任务（5min）",
        wait_timeout=10.0,  # 高频任务，等待过久会加剧补跑，缩短超时
    ),
    "orphan_scan_cleanup": _heavy(
        "orphan_scan_cleanup",
        "孤儿文件扫描清理任务（每周，含文件系统遍历 + 下载器 API 文件清单获取）",
        wait_timeout=60.0,  # 低频周任务，允许较长等待避免跳过
    ),
    "orphan_quarantine_purge": _heavy(
        "orphan_quarantine_purge",
        "孤儿文件隔离区到期清理任务（每日，含实时 manifest 与文件系统删除）",
        wait_timeout=60.0,
    ),
}


def get_profile(task_code: Optional[str]) -> Optional[TaskProfile]:
    """按 task_code 查询 profile。

    Args:
        task_code: CronTask.task_code；None 或空串直接返回 None。

    Returns:
        TaskProfile 实例；未注册返回 None（视为轻量任务，不进入资源背压）。
    """
    if not task_code:
        return None
    return TASK_PROFILES.get(task_code)


def is_heavy_task(task_code: Optional[str]) -> bool:
    """判断 task_code 是否为已登记的重型任务。"""
    return get_profile(task_code) is not None
