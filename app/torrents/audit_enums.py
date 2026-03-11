"""
审计日志操作类型枚举

定义所有审计日志的操作类型和操作结果枚举。
"""
from enum import Enum
from typing import Dict, Any, Optional


class AuditOperationType(str, Enum):
    """审计操作类型枚举

    定义所有需要审计的操作类型，包括：
    - 种子管理操作（新增、删除、还原等）
    - Tracker操作（修改、添加、删除）
    - 标签操作
    - 下载器操作
    - 定时任务操作
    - 关键词规则操作
    - 系统操作
    """
    # ========== 种子管理操作 ==========
    ADD = "add"                           # 新增种子
    PAUSE = "pause"                       # 暂停种子
    RESUME = "resume"                     # 恢复/开始种子
    RECHECK = "recheck"                   # 重新检查种子
    DELETE_L4 = "delete_l4"               # 等级4删除（待删除标签）
    DELETE_L3 = "delete_l3"               # 等级3删除（回收站）
    DELETE_L2 = "delete_l2"               # 等级2删除（删除任务保留数据）
    DELETE_L1 = "delete_l1"               # 等级1删除（删除任务和数据）

    # ========== 回收站操作 ==========
    RESTORE = "restore"                   # 从回收站还原
    CLEANUP_L3 = "cleanup_l3"             # 清理等级3数据
    CLEANUP_L4 = "cleanup_l4"             # 清理等级4数据

    # ========== Tracker操作 ==========
    UPDATE_TRACKER = "update_tracker"     # 修改tracker
    ADD_TRACKER = "add_tracker"           # 添加tracker
    REMOVE_TRACKER = "remove_tracker"     # 删除tracker

    # ========== 标签操作 ==========
    UPDATE_TAG = "update_tag"             # 修改标签
    ADD_TAG = "add_tag"                   # 添加标签
    REMOVE_TAG = "remove_tag"             # 删除标签

    # ========== 分类操作 ==========
    UPDATE_CATEGORY = "update_category"   # 修改分类

    # ========== 下载器操作 ==========
    DOWNLOADER_ADD = "downloader_add"     # 添加下载器
    DOWNLOADER_DELETE = "downloader_delete"  # 删除下载器
    DOWNLOADER_UPDATE = "downloader_update"  # 修改下载器配置
    DOWNLOADER_TEST = "downloader_test"   # 测试下载器连接
    SYNC = "sync"                          # 同步下载器种子

    # ========== 定时任务操作 ==========
    SCHEDULED_TASK_ADD = "scheduled_task_add"       # 添加定时任务
    SCHEDULED_TASK_DELETE = "scheduled_task_delete" # 删除定时任务
    SCHEDULED_TASK_UPDATE = "scheduled_task_update" # 修改定时任务
    SCHEDULED_TASK_ENABLE = "scheduled_task_enable" # 启用定时任务
    SCHEDULED_TASK_DISABLE = "scheduled_task_disable" # 禁用定时任务
    SCHEDULED_TASK_EXECUTE = "scheduled_task_execute" # 手动执行定时任务

    # ========== 关键词规则操作 ==========
    KEYWORD_RULE_ADD = "keyword_rule_add"           # 添加关键词规则
    KEYWORD_RULE_DELETE = "keyword_rule_delete"     # 删除关键词规则
    KEYWORD_RULE_UPDATE = "keyword_rule_update"     # 修改关键词规则
    KEYWORD_RULE_ENABLE = "keyword_rule_enable"     # 启用关键词规则
    KEYWORD_RULE_DISABLE = "keyword_rule_disable"   # 禁用关键词规则

    # ========== 系统操作 ==========
    SYNC_STATUS = "sync_status"           # 同步状态
    CLEANUP_ZOMBIE = "cleanup_zombie"     # 清理僵尸种子
    BATCH_OPERATION = "batch_operation"   # 批量操作

    # ========== 归档操作 ==========
    ARCHIVE_LOGS = "archive_logs"         # 归档审计日志

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """验证操作类型是否有效

        Args:
            value: 操作类型字符串

        Returns:
            有效返回True，否则返回False
        """
        try:
            cls(value)
            return True
        except ValueError:
            return False

    @classmethod
    def get_display_name(cls, value: str) -> str:
        """获取操作类型的显示名称

        Args:
            value: 操作类型字符串

        Returns:
            显示名称
        """
        display_names = {
            # 种子管理操作
            cls.ADD.value: "新增种子",
            cls.PAUSE.value: "暂停种子",
            cls.RESUME.value: "开始种子",
            cls.RECHECK.value: "重新检查种子",
            cls.DELETE_L4.value: "等级4删除（待删除标签）",
            cls.DELETE_L3.value: "等级3删除（回收站）",
            cls.DELETE_L2.value: "等级2删除（保留数据）",
            cls.DELETE_L1.value: "等级1删除（完全删除）",
            # 回收站操作
            cls.RESTORE.value: "还原种子",
            cls.CLEANUP_L3.value: "清理等级3数据",
            cls.CLEANUP_L4.value: "清理等级4数据",
            # Tracker操作
            cls.UPDATE_TRACKER.value: "修改Tracker",
            cls.ADD_TRACKER.value: "添加Tracker",
            cls.REMOVE_TRACKER.value: "删除Tracker",
            # 标签操作
            cls.UPDATE_TAG.value: "修改标签",
            cls.ADD_TAG.value: "添加标签",
            cls.REMOVE_TAG.value: "删除标签",
            # 分类操作
            cls.UPDATE_CATEGORY.value: "修改分类",
            # 下载器操作
            cls.DOWNLOADER_ADD.value: "添加下载器",
            cls.DOWNLOADER_DELETE.value: "删除下载器",
            cls.DOWNLOADER_UPDATE.value: "修改下载器配置",
            cls.DOWNLOADER_TEST.value: "测试下载器连接",
            cls.SYNC.value: "同步下载器种子",
            # 定时任务操作
            cls.SCHEDULED_TASK_ADD.value: "添加定时任务",
            cls.SCHEDULED_TASK_DELETE.value: "删除定时任务",
            cls.SCHEDULED_TASK_UPDATE.value: "修改定时任务",
            cls.SCHEDULED_TASK_ENABLE.value: "启用定时任务",
            cls.SCHEDULED_TASK_DISABLE.value: "禁用定时任务",
            cls.SCHEDULED_TASK_EXECUTE.value: "手动执行定时任务",
            # 关键词规则操作
            cls.KEYWORD_RULE_ADD.value: "添加关键词规则",
            cls.KEYWORD_RULE_DELETE.value: "删除关键词规则",
            cls.KEYWORD_RULE_UPDATE.value: "修改关键词规则",
            cls.KEYWORD_RULE_ENABLE.value: "启用关键词规则",
            cls.KEYWORD_RULE_DISABLE.value: "禁用关键词规则",
            # 系统操作
            cls.SYNC_STATUS.value: "同步状态",
            cls.CLEANUP_ZOMBIE.value: "清理僵尸种子",
            cls.BATCH_OPERATION.value: "批量操作",
            # 归档操作
            cls.ARCHIVE_LOGS.value: "归档审计日志",
        }
        return display_names.get(value, value)

    @classmethod
    def get_category(cls, value: str) -> Optional[str]:
        """获取操作类型的分类

        Args:
            value: 操作类型字符串

        Returns:
            分类名称（torrent/recycle_bin/tracker/tag/downloader/scheduled_task/keyword_rule/system/archive）
        """
        categories = {
            # 种子管理操作
            cls.ADD.value: "torrent",
            cls.PAUSE.value: "torrent",
            cls.RESUME.value: "torrent",
            cls.RECHECK.value: "torrent",
            cls.DELETE_L4.value: "torrent",
            cls.DELETE_L3.value: "torrent",
            cls.DELETE_L2.value: "torrent",
            cls.DELETE_L1.value: "torrent",
            # 回收站操作
            cls.RESTORE.value: "recycle_bin",
            cls.CLEANUP_L3.value: "recycle_bin",
            cls.CLEANUP_L4.value: "recycle_bin",
            # Tracker操作
            cls.UPDATE_TRACKER.value: "tracker",
            cls.ADD_TRACKER.value: "tracker",
            cls.REMOVE_TRACKER.value: "tracker",
            # 标签操作
            cls.UPDATE_TAG.value: "tag",
            cls.ADD_TAG.value: "tag",
            cls.REMOVE_TAG.value: "tag",
            # 分类操作
            cls.UPDATE_CATEGORY.value: "tag",
            # 下载器操作
            cls.DOWNLOADER_ADD.value: "downloader",
            cls.DOWNLOADER_DELETE.value: "downloader",
            cls.DOWNLOADER_UPDATE.value: "downloader",
            cls.DOWNLOADER_TEST.value: "downloader",
            cls.SYNC.value: "downloader",
            # 定时任务操作
            cls.SCHEDULED_TASK_ADD.value: "scheduled_task",
            cls.SCHEDULED_TASK_DELETE.value: "scheduled_task",
            cls.SCHEDULED_TASK_UPDATE.value: "scheduled_task",
            cls.SCHEDULED_TASK_ENABLE.value: "scheduled_task",
            cls.SCHEDULED_TASK_DISABLE.value: "scheduled_task",
            cls.SCHEDULED_TASK_EXECUTE.value: "scheduled_task",
            # 关键词规则操作
            cls.KEYWORD_RULE_ADD.value: "keyword_rule",
            cls.KEYWORD_RULE_DELETE.value: "keyword_rule",
            cls.KEYWORD_RULE_UPDATE.value: "keyword_rule",
            cls.KEYWORD_RULE_ENABLE.value: "keyword_rule",
            cls.KEYWORD_RULE_DISABLE.value: "keyword_rule",
            # 系统操作
            cls.SYNC_STATUS.value: "system",
            cls.CLEANUP_ZOMBIE.value: "system",
            cls.BATCH_OPERATION.value: "system",
            # 归档操作
            cls.ARCHIVE_LOGS.value: "archive",
        }
        return categories.get(value)


class AuditOperationResult(str, Enum):
    """审计操作结果枚举

    定义操作的执行结果
    """
    SUCCESS = "success"       # 操作成功
    FAILED = "failed"         # 操作失败
    PARTIAL = "partial"       # 部分成功（批量操作时部分成功）

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """验证操作结果是否有效

        Args:
            value: 操作结果字符串

        Returns:
            有效返回True，否则返回False
        """
        try:
            cls(value)
            return True
        except ValueError:
            return False

    @classmethod
    def get_display_name(cls, value: str) -> str:
        """获取操作结果的显示名称

        Args:
            value: 操作结果字符串

        Returns:
            显示名称
        """
        display_names = {
            cls.SUCCESS.value: "成功",
            cls.FAILED.value: "失败",
            cls.PARTIAL.value: "部分成功",
        }
        return display_names.get(value, value)
