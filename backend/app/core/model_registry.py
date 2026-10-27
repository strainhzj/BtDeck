"""ORM 模型集中注册（v1.0.8 双数据库架构，契约 docs/postgresql-contract.md §3 规则 2）。

单一注册点：alembic/env.py（autogenerate）与 PG squash 基线初始化
（app/core/pg_baseline.py）共用本函数，确保 `Base.metadata` 完整加载
全部业务表模型，不依赖 API 路由恰好被 import。

维护义务：新增 ORM 模型文件后必须在此补 import，否则 alembic autogenerate
与 PG 基线建表都会漏表（P1 任务1.6；原散布在 alembic/env.py 的清单归位于此）。
"""

from __future__ import annotations


def register_all_models() -> None:
    """导入全部 ORM 模型，使其注册到 ``app.database.Base.metadata``。"""
    # 认证与权限
    from app.auth.models import User, LoginLog, Config, RefreshToken  # noqa: F401

    # 下载器管理
    from app.downloader.models import BtDownloaders  # noqa: F401
    from app.models.downloader_capabilities import DownloaderCapabilities  # noqa: F401
    from app.models.downloader_settings import DownloaderSetting  # noqa: F401
    from app.models.downloader_path_maintenance import DownloaderPathMaintenance  # noqa: F401
    from app.models.setting_templates import SettingTemplate  # noqa: F401
    from app.models.speed_schedule_rules import SpeedScheduleRule  # noqa: F401

    # 种子管理
    from app.torrents.models import (  # noqa: F401
        TorrentInfo,
        TrackerInfo,
        TrackerKeywordConfig,
        TrackerMessageLog,
        TrackerReannounceConfig,
    )
    from app.models.torrent_tags import TorrentTag, TorrentTagRelation  # noqa: F401
    from app.models.torrent_deletion_audit_log import TorrentDeletionAuditLog  # noqa: F401
    from app.models.torrent_file_backup import TorrentFileBackup  # noqa: F401
    from app.models.seed_transfer_audit_log import SeedTransferAuditLog  # noqa: F401

    # 任务调度
    from app.tasks.models import TaskLogs  # noqa: F401
    from app.tasks.cron_models import CronTask  # noqa: F401
    from app.torrents.audit_models import TorrentAuditLog  # noqa: F401

    # 通知中心
    from app.models.notification import Notification  # noqa: F401

    # 搜索模板（第四轨归位，原由原生 SQL 自建）
    from app.models.search_template import SearchTemplate  # noqa: F401

    # 孤儿文件管理
    from app.models.orphan_file import (  # noqa: F401
        OrphanScanResult,
        OrphanFile,
        OrphanCurrentCandidate,
        OrphanOperationLease,
    )
    from app.models.orphan_purge_job import OrphanPurgeJob  # noqa: F401

    # 硬链接副本扫描（任务3.4 对拍门禁发现的历史漂移：链建表 c8d9e0f1a2b3 但
    # 模型从未注册 metadata，PG 基线会漏建两表——与 notification 索引同类）
    from app.models.orphan_hardlink_copy import OrphanHardlinkCopyResult, OrphanHardlinkScanState  # noqa: F401

    # 同步检查点（W3-2 持久化续跑）
    from app.models.sync_checkpoint import SyncCheckpoint  # noqa: F401

    # MoviePilot 集成（整理历史镜像 + 实例注册）
    from app.models.moviepilot_instance import MoviePilotInstance  # noqa: F401
    from app.models.moviepilot_transfer_history import MoviePilotTransferHistory  # noqa: F401

    # RSS 订阅（feature rss-subscription-2026-09-24，Phase 2 规则表随模型注册）
    from app.models.rss_subscription import RssFeed, RssArticle  # noqa: F401

    # 速度采样（统计报表 W1）
    from app.models.speed_sample import DownloaderSpeedSample, DownloaderSpeedHourly  # noqa: F401
