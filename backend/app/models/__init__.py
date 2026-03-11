# -*- coding: utf-8 -*-
# @Time    : 2019/4/18 11:01 AM
# @Author  : ShaHeTop-Almighty-ares
# @Email   : yang6333yyx@126.com
# @File    : __init__.py.py
# @Software: PyCharm

# 导出所有模型和枚举
from app.models.enums import (
    SpeedUnitEnum,
    ScheduleDayOfWeekEnum,
)
from app.models.setting_templates import (
    SettingTemplate,
    DownloaderTypeEnum,  # 整数枚举，已迁移到 setting_templates
)

# 导出下载器设置相关模型
from app.models.downloader_settings import DownloaderSetting
from app.models.speed_schedule_rules import SpeedScheduleRule
# 导出种子标签管理模型
from app.models.torrent_tags import TorrentTag, TorrentTagRelation
# 导出种子删除审计日志模型
from app.models.torrent_deletion_audit_log import (
    TorrentDeletionAuditLog,
    OPERATOR_SYSTEM_SCHEDULER,
    OPERATOR_RECYCLE_BIN_CLEANER,
    DELETION_STATUS_SUCCESS,
    DELETION_STATUS_FAILED,
    DELETION_STATUS_PARTIAL,
    CALLER_SOURCE_API,
    CALLER_SOURCE_SYSTEM_SCHEDULER,
    CALLER_SOURCE_RECYCLE_BIN_CLEANER,
    DOWNLOADER_TYPE_QBITTORRENT,
    DOWNLOADER_TYPE_TRANSMISSION,
)
# 导出种子转移功能模型
from app.models.torrent_file_backup import TorrentFileBackup
from app.models.downloader_path_maintenance import DownloaderPathMaintenance
from app.models.seed_transfer_audit_log import (
    SeedTransferAuditLog,
    OPERATOR_TYPE_SEED_TRANSFER,
    TRANSFER_STATUS_SUCCESS,
    TRANSFER_STATUS_FAILED,
)

__all__ = [
    'DownloaderTypeEnum',  # 整数枚举
    'SpeedUnitEnum',
    'ScheduleDayOfWeekEnum',
    'DownloaderSetting',
    'SettingTemplate',
    'SpeedScheduleRule',
    'TorrentTag',
    'TorrentTagRelation',
    'TorrentDeletionAuditLog',  # 种子删除审计日志模型
    'OPERATOR_SYSTEM_SCHEDULER',  # 操作者常量
    'OPERATOR_RECYCLE_BIN_CLEANER',
    'DELETION_STATUS_SUCCESS',
    'DELETION_STATUS_FAILED',
    'DELETION_STATUS_PARTIAL',
    'CALLER_SOURCE_API',
    'CALLER_SOURCE_SYSTEM_SCHEDULER',
    'CALLER_SOURCE_RECYCLE_BIN_CLEANER',
    'DOWNLOADER_TYPE_QBITTORRENT',
    'DOWNLOADER_TYPE_TRANSMISSION',
    # 种子转移功能模型
    'TorrentFileBackup',
    'DownloaderPathMaintenance',
    'SeedTransferAuditLog',
    'OPERATOR_TYPE_SEED_TRANSFER',
    'TRANSER_STATUS_SUCCESS',
    'TRANSER_STATUS_FAILED',
]
