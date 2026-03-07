# -*- coding: utf-8 -*-
"""
系统默认定时任务数据

提供生产环境必需的定时任务配置，包括：
1. 下载器状态同步任务
2. Tracker状态监控任务
3. Tag同步任务
4. Tracker消息记录任务
5. 下载器路径扫描任务
"""
import logging

logger = logging.getLogger(__name__)


# ========== 定时任务配置常量 ==========

# 任务类型枚举
TASK_TYPE_PYTHON = 4      # Python脚本任务
TASK_TYPE_SHELL = 0       # Shell脚本任务
TASK_TYPE_HTTP = 1        # HTTP请求任务
TASK_TYPE_SQL = 2         # SQL执行任务
TASK_TYPE_PLUGIN = 3      # 插件任务

# 任务状态枚举
TASK_STATUS_READY = 1     # 就绪
TASK_STATUS_RUNNING = 2   # 运行中
TASK_STATUS_PAUSED = 0    # 已暂停
TASK_STATUS_DISABLED = -1 # 已禁用


# ========== 系统默认定时任务定义 ==========

DEFAULT_SCHEDULED_TASKS = [
    {
        "task_name": "缓存下载器同步任务",
        "task_code": "cached_downloader_sync",
        "task_status": TASK_STATUS_READY,
        "task_type": TASK_TYPE_PYTHON,
        "executor": "app.tasks.scheduler.downloader_cache_sync.CachedDownloaderSyncTask",
        "enabled": True,
        "last_execute_time": None,
        "last_execute_duration": None,
        "cron_plan": "*/5 * * * *",  # 每5分钟执行
        "description": "定期同步所有下载器的缓存状态，包括下载器在线状态、速度信息等",
        "timeout_seconds": 3600,
        "max_retry_count": 0,
        "retry_interval": 300,
        "create_by": "migration_system",
        "update_by": "admin",
    },
    {
        "task_name": "Tracker消息记录任务",
        "task_code": "TRACKER_MESSAGE_LOGGER",
        "task_status": TASK_STATUS_READY,
        "task_type": TASK_TYPE_PYTHON,
        "executor": "app.tasks.scheduler.tracker_message_logger.TrackerMessageLogger",
        "enabled": True,
        "last_execute_time": None,
        "last_execute_duration": None,
        "cron_plan": "0 */1 * * *",  # 每小时执行
        "description": "记录所有tracker返回的新消息,用于关键词配置。支持自动去重和混合清理策略。",
        "timeout_seconds": 600,
        "max_retry_count": 2,
        "retry_interval": 300,
        "create_by": "system",
        "update_by": "admin",
    },
    {
        "task_name": "下载器路径扫描任务",
        "task_code": "downloader_path_scan",
        "task_status": TASK_STATUS_READY,
        "task_type": TASK_TYPE_PYTHON,
        "executor": "app.tasks.scheduler.downloader_path_scan.DownloaderPathScanTask",
        "enabled": True,
        "last_execute_time": None,
        "last_execute_duration": None,
        "cron_plan": "0 * * * *",  # 每小时执行
        "description": "自动扫描 torrent_info 表，发现种子保存路径并更新到下载器的 path_mapping 配置中。采用增量更新策略，只添加新发现的路径。",
        "timeout_seconds": 3600,
        "max_retry_count": 0,
        "retry_interval": 300,
        "create_by": "system",
        "update_by": "system",
    },
    {
        "task_name": "Tag Data Sync",
        "task_code": "847364f0",
        "task_status": TASK_STATUS_READY,
        "task_type": TASK_TYPE_PYTHON,
        "executor": "app.tasks.scheduler.tag_sync.TagSyncTask",
        "enabled": True,
        "last_execute_time": None,
        "last_execute_duration": None,
        "cron_plan": "0 */1 * * *",  # 每小时执行
        "description": "Periodically sync tags/categories from downloaders to database (interval: 1 hour, auto-delete zombie tags)",
        "timeout_seconds": 3600,
        "max_retry_count": 0,
        "retry_interval": 300,
        "create_by": "admin",
        "update_by": "admin",
    },
    {
        "task_name": "种子Tracker状态判断任务",
        "task_code": "TORRENT_TRACKER_STATUS_JUDGE",
        "task_status": TASK_STATUS_READY,
        "task_type": TASK_TYPE_PYTHON,
        "executor": "app.tasks.scheduler.torrent_tracker_status_judge.TorrentTrackerStatusJudge",
        "enabled": True,
        "last_execute_time": None,
        "last_execute_duration": None,
        "cron_plan": "0 */5 * * *",  # 每5分钟执行
        "description": "定期检查所有种子的tracker状态，根据关键词池（失败池、成功池、忽略池）智能判断tracker是否失败，自动更新has_tracker_error字段（间隔: 5分钟，批量处理20,000+种子）",
        "timeout_seconds": 300,
        "max_retry_count": 0,
        "retry_interval": 300,
        "create_by": "admin",
        "update_by": "admin",
    },
    {
        "task_name": "种子信息同步任务",
        "task_code": "torrent_info_sync_ac608e4d",
        "task_status": TASK_STATUS_READY,
        "task_type": TASK_TYPE_PYTHON,
        "executor": "app.tasks.scheduler.torrent_sync.TorrentInfoSyncTask",
        "enabled": True,
        "last_execute_time": None,
        "last_execute_duration": None,
        "cron_plan": "*/10 * * * *",  # 每10分钟执行
        "description": "高频同步种子基础信息（名称、大小、进度、状态等），不含tracker同步。执行间隔: 10分钟。性能目标: 10万种子场景 <5秒",
        "timeout_seconds": 3600,
        "max_retry_count": 0,
        "retry_interval": 300,
        "create_by": "admin",
        "update_by": "admin",
    },
    {
        "task_name": "Tracker 状态同步任务",
        "task_code": "tracker_sync_598b784c",
        "task_status": TASK_STATUS_READY,
        "task_type": TASK_TYPE_PYTHON,
        "executor": "app.tasks.scheduler.torrent_sync.TrackerSyncTask",
        "enabled": True,
        "last_execute_time": None,
        "last_execute_duration": None,
        "cron_plan": "*/5 * * * *",  # 每5分钟执行
        "description": "高频同步 Tracker 状态信息（announce成功、scrape成功、错误消息等）。执行间隔: 5分钟。性能目标: 10万种子场景 <60秒",
        "timeout_seconds": 3600,
        "max_retry_count": 0,
        "retry_interval": 300,
        "create_by": "admin",
        "update_by": "admin",
    },
]


# ========== 初始化函数 ==========

def init_default_scheduled_tasks(db_session) -> int:
    """
    初始化系统默认定时任务到数据库

    Args:
        db_session: SQLAlchemy数据库会话

    Returns:
        int: 创建的任务数量

    Raises:
        Exception: 数据库操作失败时抛出异常
    """
    from datetime import datetime
    from app.tasks.cron_models import CronTask

    try:
        created_count = 0

        for task_data in DEFAULT_SCHEDULED_TASKS:
            # 检查任务是否已存在（通过 task_code 唯一性）
            existing = db_session.query(CronTask).filter_by(
                task_code=task_data["task_code"]
            ).first()

            if existing:
                logger.info(f"系统默认任务已存在，跳过: {task_data['task_name']} ({task_data['task_code']})")
                continue

            # 创建新任务
            task = CronTask(
                task_name=task_data["task_name"],
                task_code=task_data["task_code"],
                task_status=task_data["task_status"],
                task_type=task_data["task_type"],
                executor=task_data["executor"],
                enabled=task_data["enabled"],
                last_execute_time=task_data["last_execute_time"],
                last_execute_duration=task_data["last_execute_duration"],
                cron_plan=task_data["cron_plan"],
                description=task_data["description"],
                timeout_seconds=task_data["timeout_seconds"],
                max_retry_count=task_data["max_retry_count"],
                retry_interval=task_data["retry_interval"],
                dr=0,  # 软删除标记
                create_time=datetime.now(),
                update_time=datetime.now(),
                create_by=task_data["create_by"],
                update_by=task_data["update_by"],
            )

            db_session.add(task)
            created_count += 1
            logger.info(f"创建系统默认定时任务: {task_data['task_name']} ({task_data['task_code']})")

        # 提交所有更改
        db_session.commit()
        logger.info(f"系统默认定时任务初始化完成，共创建 {created_count} 个任务")

        return created_count

    except Exception as e:
        db_session.rollback()
        logger.error(f"初始化系统默认定时任务失败: {e}")
        raise


def get_default_scheduled_tasks() -> list:
    """
    获取所有系统默认定时任务的配置数据

    Returns:
        list: 任务配置数据列表
    """
    return DEFAULT_SCHEDULED_TASKS.copy()


def get_task_by_code(task_code: str) -> dict:
    """
    根据任务代码获取系统默认定时任务配置

    Args:
        task_code: 任务代码

    Returns:
        dict: 任务配置数据，不存在返回None
    """
    for task in DEFAULT_SCHEDULED_TASKS:
        if task["task_code"] == task_code:
            return task.copy()
    return None


# ========== 模块导出 ==========

__all__ = [
    "DEFAULT_SCHEDULED_TASKS",
    "init_default_scheduled_tasks",
    "get_default_scheduled_tasks",
    "get_task_by_code",
]
