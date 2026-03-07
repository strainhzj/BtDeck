"""
种子信息同步任务类（已废弃，请使用拆分任务）

⚠️ 废弃说明：
本任务已拆分为两个独立任务，以提升性能和灵活性：
- TorrentInfoSyncTask: 种子信息同步（10分钟一次）
- TrackerSyncTask: Tracker 同步（5分钟一次）

迁移建议：
1. 停止使用本任务（TorrentSyncTask）
2. 改用 TorrentInfoSyncTask + TrackerSyncTask
3. 根据实际需求调整执行频率

保留原因：向后兼容，不影响现有调度配置
"""

from datetime import datetime
from typing import Dict, Any

from app.api.endpoints.torrents import torrent_sync_async


class TorrentSyncTask:
    """种子信息同步任务

    定期执行下载器种子信息同步，无超时限制
    """

    # 任务元数据
    name = "种子同步任务"
    description = "下载器种子信息同步任务"
    version = "1.0.0"
    author = "btpmanager"
    category = "torrent"

    # 任务配置
    default_interval = 3600  # 默认1小时
    max_concurrent_syncs = 3  # 最大并发同步数
    no_timeout = True        # 不设置超时限制

    def __init__(self):
        """初始化任务"""
        self.last_execution_time = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_synced = 0
        self.total_failed = 0

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行种子信息同步任务

        Args:
            **kwargs: 任务参数（可选）

        Returns:
            任务执行结果字典
        """
        try:
            self.last_execution_time = datetime.now()
            self.execution_count += 1

            # 记录任务开始
            result = {
                "task_name": self.name,
                "execution_time": self.last_execution_time,
                "execution_count": self.execution_count,
                "status": "running",
                "message": "Torrent sync task started"
            }

            # 执行种子同步（调用修改后的无参数方法）
            sync_result = await torrent_sync_async()
            sync_status = sync_result.get("status")

            # 🔧 修复：处理 "no_action" 状态（无下载器可同步）
            if sync_status == "no_action":
                # 无操作：既不算成功也不算失败，记录为跳过
                result.update({
                    "status": "skipped",
                    "message": sync_result.get("message", "No downloaders available for sync"),
                    "successful_syncs": 0,
                    "failed_syncs": 0,
                    "total_downloaders": sync_result.get("total_downloaders", 0),
                    "success_count": self.success_count,
                    "failure_count": self.failure_count,
                    "total_synced": self.total_synced,
                    "total_failed": self.total_failed,
                    "note": "任务跳过：没有可用的下载器进行同步"
                })
                return result

            # 更新统计信息
            elif sync_status in ["success", "partial"]:
                self.success_count += 1
                successful_syncs = sync_result.get("successful_syncs", 0)
                failed_syncs = sync_result.get("failed_syncs", 0)
                self.total_synced += successful_syncs
                self.total_failed += failed_syncs

                result.update({
                    "status": "success" if sync_status == "success" else "partial",
                    "message": sync_result.get("message", "Torrent sync completed"),
                    "successful_syncs": successful_syncs,
                    "failed_syncs": failed_syncs,
                    "total_downloaders": sync_result.get("total_downloaders", 0),
                    "success_count": self.success_count,
                    "failure_count": self.failure_count,
                    "total_synced": self.total_synced,
                    "total_failed": self.total_failed
                })

            else:  # status == "failed" 或其他未知状态
                self.failure_count += 1
                result.update({
                    "status": "failed",
                    "message": sync_result.get("message", "Torrent sync failed"),
                    "success_count": self.success_count,
                    "failure_count": self.failure_count,
                    "total_synced": self.total_synced,
                    "total_failed": self.total_failed
                })

            return result

        except Exception as e:
            self.failure_count += 1
            error_result = {
                "task_name": self.name,
                "execution_time": datetime.now(),
                "execution_count": self.execution_count,
                "status": "failed",
                "message": f"Torrent sync task failed: {str(e)}",
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "total_synced": self.total_synced,
                "total_failed": self.total_failed
            }
            return error_result

    def get_task_info(self) -> Dict[str, Any]:
        """获取任务信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_synced": self.total_synced,
            "total_failed": self.total_failed,
            "last_execution_time": self.last_execution_time,
            "success_rate": (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0,
            "sync_success_rate": (self.total_synced / (self.total_synced + self.total_failed) * 100) if (self.total_synced + self.total_failed) > 0 else 0
        }

    def get_schedule_config(self) -> Dict[str, Any]:
        """获取调度配置建议"""
        return {
            "cron_expression": "0 * * * *",  # 每小时执行一次
            "timezone": "Asia/Shanghai",
            "max_instances": 1,     # 防止重叠执行
            "coalesce": True,       # 合并错过的执行
            "misfire_grace_time": 900,  # 错过执行的宽限时间（15分钟）
            "default_interval": self.default_interval,
            "max_concurrent_syncs": self.max_concurrent_syncs,
            "no_timeout": self.no_timeout,
            "estimated_duration": "Variable (no timeout limit)"
        }

    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        if self.execution_count == 0:
            return {
                "average_syncs_per_execution": 0,
                "average_failures_per_execution": 0,
                "total_processing_time": "N/A"
            }

        return {
            "average_syncs_per_execution": self.total_synced / self.execution_count,
            "average_failures_per_execution": self.total_failed / self.execution_count,
            "sync_efficiency": (self.total_synced / (self.total_synced + self.total_failed) * 100) if (self.total_synced + self.total_failed) > 0 else 0,
            "task_reliability": (self.success_count / self.execution_count * 100)
        }