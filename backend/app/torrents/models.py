from typing import Any, Optional
import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, String, BigInteger, Float, DATETIME, Boolean, Text, Index
from app.database import Base
import logging

logger = logging.getLogger(__name__)


class TorrentInfo(Base):
    __tablename__ = "torrent_info"

    info_id = Column(String, primary_key=True, index=True, comment="主键")
    downloader_id = Column(String, primary_key=True, index=True, comment="所属下载器主键")
    downloader_name = Column(String, primary_key=True, index=True, comment="所属下载器名称")
    torrent_id = Column(String, index=True, comment="下载器中的主键")
    hash = Column(String, index=True, comment="种子哈希值")
    name = Column(String, index=True, comment="种子名称")
    save_path = Column(String, index=True, comment="种子文件保存路径")
    size = Column(Float, comment="种子大小")
    status = Column(String, index=True, comment="状态")
    progress = Column(Float, default=0.0, comment="下载进度(0-100)")
    torrent_file = Column(String, index=True, comment="种子文件")
    added_date = Column(DATETIME, comment="添加时间")
    completed_date = Column(DATETIME, comment="完成时间")
    ratio = Column(String, index=True, comment="比率")
    ratio_limit = Column(String, index=True, comment="比率限制")
    tags = Column(String, index=True, comment="标签")
    category = Column(String, index=True, comment="分类")
    super_seeding = Column(String, index=True, comment="超级做种模式")
    enabled = Column(Boolean, default=True, comment="是否停用")
    create_time = Column(DATETIME, comment="创建时间")
    create_by = Column(String, comment="创建人")
    update_time = Column(DATETIME, comment="更新时间")
    update_by = Column(String, comment="更新人")
    dr = Column(Integer, default=0, comment="删除状态，0是未删除，1是逻辑删除")
    deleted_at = Column(DATETIME, nullable=True, comment="删除时间（等级3回收站）")
    original_filename = Column(String(255), nullable=True, comment="原始文件名（等级3还原用）")
    backup_file_path = Column(String(512), nullable=True, comment="种子文件备份路径（用于回收站还原）")
    original_file_list = Column(Text, nullable=True, comment="原始文件列表（JSON格式，存储相对路径，用于回收站清理）")
    has_tracker_error = Column(Boolean, nullable=False, default=False, comment="种子是否处于tracker错误状态（所有tracker都失败）")

    # 唯一约束：防止同一下载器中出现相同的 hash（仅限未删除记录）
    __table_args__ = (
        Index(
            'idx_torrent_hash_unique',
            'hash',
            'downloader_id',
            unique=True,
            sqlite_where=dr == 0
        ),
    )

    def __init__(self, id_, downloader_id, downloader_name, torrent_id, hash, name, save_path, size, status,
                 progress, torrent_file, added_date, completed_date, ratio, ratio_limit, tags, category,
                 super_seeding, enabled, create_time, create_by, update_time, update_by, dr,
                 deleted_at=None, original_filename=None, backup_file_path=None, original_file_list=None, **kw: Any):
        super().__init__(**kw)
        self.info_id = id_
        self.downloader_id = downloader_id
        self.downloader_name = downloader_name
        self.torrent_id = torrent_id
        self.hash = hash
        self.name = name
        self.save_path = save_path
        self.size = size
        self.status = status
        self.progress = progress
        self.torrent_file = torrent_file
        self.added_date = added_date
        self.completed_date = completed_date
        self.ratio = ratio
        self.ratio_limit = ratio_limit
        self.tags = tags
        self.category = category
        self.super_seeding = super_seeding
        self.enabled = enabled
        self.create_time = create_time
        self.create_by = create_by
        self.update_time = update_time
        self.update_by = update_by
        self.dr = dr
        self.deleted_at = deleted_at
        self.original_filename = original_filename
        self.backup_file_path = backup_file_path
        self.original_file_list = original_file_list
        self.original_file_list = original_file_list

    def to_dict(self):
        return {
            "info_id": self.info_id,
            "downloader_id": self.downloader_id,
            "downloader_name": self.downloader_name,
            "torrent_id": self.torrent_id,
            "hash": self.hash,
            "name": self.name,
            "save_path": self.save_path,
            "size": self.size,
            "status": self.status,
            "progress": self.progress,
            "torrent_file": self.torrent_file,
            "added_date": self.added_date,
            "completed_date": self.completed_date,
            "ratio": self.ratio,
            "ratio_limit": self.ratio_limit,
            "tags": self.tags,
            "category": self.category,
            "super_seeding": self.super_seeding,
            "enabled": self.enabled,
            "create_time": self.create_time,
            "create_by": self.create_by,
            "update_time": self.update_time,
            "update_by": self.update_by,
            "dr": self.dr,
            "deleted_at": self.deleted_at,
            "original_filename": self.original_filename,
            "backup_file_path": self.backup_file_path,
            "original_file_list": self.original_file_list,
            "has_tracker_error": self.has_tracker_error,
        }

    def get_deleted_at_formatted(self, date_format: str = "%Y-%m-%d %H:%M:%S") -> Optional[str]:
        """
        安全获取格式化的删除时间

        Args:
            date_format: 日期格式字符串

        Returns:
            格式化的日期字符串，如果deleted_at为None则返回None
        """
        if self.deleted_at is None:
            return None
        try:
            if isinstance(self.deleted_at, str):
                # 如果是字符串，先转换为datetime
                self.deleted_at = datetime.fromisoformat(self.deleted_at)
            return self.deleted_at.strftime(date_format)
        except (AttributeError, ValueError) as e:
            logger.error(f"格式化deleted_at失败: {e}, 值: {self.deleted_at}")
            return None

    def is_deleted(self) -> bool:
        """
        检查种子是否已删除（等级3删除）

        Returns:
            True表示已删除，False表示未删除
        """
        return self.deleted_at is not None

    def get_original_filename_safe(self) -> str:
        """
        安全获取原始文件名

        Returns:
            原始文件名，如果为None则返回当前文件名
        """
        return self.original_filename or self.name or ""

    def soft_delete(self, save_original_filename: bool = True) -> None:
        """
        执行等级3软删除（移到回收站）

        Args:
            save_original_filename: 是否保存原始文件名

        Note:
            dr字段保持为0（在回收站中，可还原）
            只有手动清理时才会设置dr=1（彻底删除，不可还原）
        """
        from datetime import datetime
        self.deleted_at = datetime.now()
        # 🔥 重要：等级3删除保持dr=0，表示"在回收站中，可还原"
        # 只有手动清理时才设置dr=1，表示"彻底删除，不可还原"
        # self.dr = 1  # ❌ 注释掉：等级3删除不应设置dr=1
        if save_original_filename and not self.original_filename:
            self.original_filename = self.name
        logger.info(f"种子 {self.info_id} 已移至回收站（dr=0，可还原）")

    def restore_from_recycle_bin(self) -> None:
        """
        从回收站还原种子
        """
        self.deleted_at = None
        self.dr = 0  # 清除逻辑删除标识
        logger.info(f"种子 {self.info_id} 已从回收站还原（dr=0）")


class TrackerInfo(Base):
    __tablename__ = "tracker_info"

    tracker_id = Column(String, primary_key=True, index=True, comment="主键")
    torrent_info_id = Column(String, index=True, comment="关联种子主键")
    tracker_name = Column(String, index=True, comment="tracker名称")
    tracker_url = Column(String, index=True, comment="tracker地址")
    last_announce_succeeded = Column(Integer, comment="请求结果")
    last_announce_msg = Column(String, index=True, comment="tracker最后一次请求信息")
    last_scrape_succeeded = Column(Integer, comment="汇报结果")
    last_scrape_msg = Column(String, index=True, comment="tracker最后一次汇报信息")
    tracker_host = Column(String(256), nullable=True, default=None, comment="tracker主机地址")
    status = Column(String(20), nullable=True, default="unknown", comment="tracker状态: normal/error/unknown")
    msg = Column(String(512), nullable=True, default=None, comment="tracker状态消息")
    seeder_count = Column(Integer, nullable=True, default=None, comment="做种者数量")
    leecher_count = Column(Integer, nullable=True, default=None, comment="下载者数量")
    download_count = Column(Integer, nullable=True, default=None, comment="下载完成次数")
    create_time = Column(DATETIME, comment="创建时间")
    create_by = Column(String, comment="创建人")
    update_time = Column(DATETIME, comment="更新时间")
    update_by = Column(String, comment="更新人")
    dr = Column(Integer, default=0, comment="删除状态，0是未删除，1是逻辑删除")
    version = Column(Integer, default=0, comment="乐观锁版本号")

    # 唯一约束：防止同一种子的相同tracker重复（仅限未删除记录）
    __table_args__ = (
        Index('idx_tracker_unique_url', 'torrent_info_id', 'tracker_url', unique=True,
              sqlite_where=dr == 0),
    )

    def to_dict(self):
        return {
            "tracker_id": self.tracker_id,
            "torrent_info_id": self.torrent_info_id,
            "tracker_name": self.tracker_name,
            "tracker_url": self.tracker_url,
            "last_announce_succeeded": self.last_announce_succeeded,
            "last_announce_msg": self.last_announce_msg,
            "last_scrape_succeeded": self.last_scrape_succeeded,
            "last_scrape_msg": self.last_scrape_msg,
            "tracker_host": self.tracker_host,
            "status": self.status,
            "msg": self.msg,
            "seeder_count": self.seeder_count,
            "leecher_count": self.leecher_count,
            "download_count": self.download_count,
            "create_time": self.create_time,
            "create_by": self.create_by,
            "update_time": self.update_time,
            "update_by": self.update_by,
            "dr": self.dr,
            "version": self.version,
        }


class TrackerKeywordConfig(Base):
    """Tracker关键词配置表

    用于存储tracker成功/失败关键词池，支持多语言和优先级管理。
    """
    __tablename__ = "tracker_keyword_config"

    keyword_id = Column(String(36), primary_key=True, index=True, comment="主键")
    keyword_type = Column(String(20), nullable=False, index=True, comment="关键词类型: success/failure")
    keyword = Column(String(200), nullable=False, comment="关键词内容")
    language = Column(String(10), nullable=True, index=True, comment="语言代码(zh_CN/en_US等)，NULL表示通用")
    priority = Column(Integer, nullable=False, default=100, comment="优先级1-1000，数值越大优先级越高")
    enabled = Column(Boolean, nullable=False, default=True, comment="是否启用")
    category = Column(String(50), nullable=True, comment="分类标识")
    description = Column(String(500), nullable=True, comment="关键词说明")
    create_time = Column(DATETIME, nullable=False, comment="创建时间")
    update_time = Column(DATETIME, nullable=False, comment="更新时间")
    create_by = Column(String(50), nullable=False, default="admin", comment="创建人")
    update_by = Column(String(50), nullable=False, default="admin", comment="更新人")
    dr = Column(Integer, nullable=False, default=0, comment="删除状态，0是未删除，1是逻辑删除")

    __table_args__ = (
        Index('idx_tracker_keyword_type_enabled', 'keyword_type', 'enabled'),
        Index('idx_tracker_keyword_language', 'language'),
        Index('idx_tracker_keyword_priority', 'priority'),
        # keyword全局唯一性约束(排除已删除记录)
        Index('idx_tracker_keyword_unique', 'keyword', unique=True),
        {'comment': 'Tracker关键词配置表'}
    )

    def __init__(self, keyword_type: str, keyword: str, language: Optional[str] = None, priority: int = 100,
                 enabled: bool = True, category: Optional[str] = None, description: Optional[str] = None,
                 create_time: Optional[datetime] = None, update_time: Optional[datetime] = None,
                 create_by: str = "admin", update_by: str = "admin", dr: int = 0, **kw: Any):
        super().__init__(**kw)
        self.keyword_id = str(uuid.uuid4())
        self.keyword_type = keyword_type
        self.keyword = keyword
        self.language = language
        self.priority = priority
        self.enabled = enabled
        self.category = category
        self.description = description
        self.create_time = create_time or datetime.now()
        self.update_time = update_time or datetime.now()
        self.create_by = create_by
        self.update_by = update_by
        self.dr = dr

    def to_dict(self):
        return {
            "keyword_id": self.keyword_id,
            "keyword_type": self.keyword_type,
            "keyword": self.keyword,
            "language": self.language,
            "priority": self.priority,
            "enabled": self.enabled,
            "category": self.category,
            "description": self.description,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "create_by": self.create_by,
            "update_by": self.update_by,
            "dr": self.dr,
        }


class TrackerMessageLog(Base):
    """Tracker消息历史记录表

    记录所有tracker返回的真实消息，支持去重（按tracker_host+msg组合）
    和统计（出现次数、首次/最后出现时间）。
    """
    __tablename__ = "tracker_message_log"

    log_id = Column(String(36), primary_key=True, index=True, comment="主键")
    tracker_host = Column(String(500), nullable=False, index=True, comment="tracker主机地址（用于去重）")
    msg = Column(String(2048), nullable=False, comment="tracker返回的消息（用于去重）")
    first_seen = Column(DATETIME, nullable=False, comment="首次出现时间")
    last_seen = Column(DATETIME, nullable=False, comment="最后出现时间")
    occurrence_count = Column(Integer, nullable=False, default=1, comment="出现次数")
    sample_torrents = Column(Text, nullable=True, comment="示例种子列表(JSON)")
    sample_urls = Column(Text, nullable=True, comment="示例tracker URL列表(JSON)")
    is_processed = Column(Boolean, nullable=False, default=False, comment="是否已处理（已添加到信息池）")
    keyword_type = Column(String(20), nullable=True, comment="添加到哪个池: success/failure")
    create_time = Column(DATETIME, nullable=False, comment="创建时间")
    update_time = Column(DATETIME, nullable=False, comment="更新时间")
    create_by = Column(String(50), nullable=False, default="system", comment="创建人")
    update_by = Column(String(50), nullable=False, default="system", comment="更新人")

    __table_args__ = (
        Index('idx_tracker_msg_unique', 'tracker_host', 'msg', unique=True),
        Index('idx_tracker_msg_first_seen', 'first_seen'),
        Index('idx_tracker_msg_is_processed', 'is_processed'),
        {'comment': 'Tracker消息历史记录表'}
    )

    def __init__(self, tracker_host: str, msg: str, first_seen: Optional[datetime] = None,
                 last_seen: Optional[datetime] = None, occurrence_count: int = 1,
                 sample_torrents: Optional[str] = None, sample_urls: Optional[str] = None,
                 is_processed: bool = False, keyword_type: Optional[str] = None,
                 create_time: Optional[datetime] = None, update_time: Optional[datetime] = None,
                 create_by: str = "system", update_by: str = "system", **kw: Any):
        super().__init__(**kw)
        self.log_id = str(uuid.uuid4())
        self.tracker_host = tracker_host
        self.msg = msg
        self.first_seen = first_seen or datetime.now()
        self.last_seen = last_seen or datetime.now()
        self.occurrence_count = occurrence_count
        self.sample_torrents = sample_torrents
        self.sample_urls = sample_urls
        self.is_processed = is_processed
        self.keyword_type = keyword_type
        self.create_time = create_time or datetime.now()
        self.update_time = update_time or datetime.now()
        self.create_by = create_by
        self.update_by = update_by

    def to_dict(self):
        return {
            "log_id": self.log_id,
            "tracker_host": self.tracker_host,
            "msg": self.msg,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "occurrence_count": self.occurrence_count,
            "sample_torrents": self.sample_torrents,
            "sample_urls": self.sample_urls,
            "is_processed": self.is_processed,
            "keyword_type": self.keyword_type,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "create_by": self.create_by,
            "update_by": self.update_by,
        }
