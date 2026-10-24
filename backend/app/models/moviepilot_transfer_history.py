# -*- coding: utf-8 -*-
"""MoviePilot 整理历史同步表（feature moviepilot-integration-20260908）。

一行对应一条 MoviePilot ``TransferHistory`` 在本地的镜像（**只读镜像**，
同步链路永不反向修改 MoviePilot）。设计要点：

- 幂等身份 = ``(instance_id, history_id)`` 唯一约束——同一实例重复投递
  按 ``content_hash`` 判定 skip（内容未变）/ update（重新整理或字段更新），
  不依赖"最大历史 ID"增量语义；
- 路径字段保存 MoviePilot 侧**原值**（src/dest + storage 类型），不做自动
  换算；与 BtDeck 任务的关联只走显式下载器映射 + download_hash；
- ``bt_downloader_id``/``association_status`` 是写入时按实例映射解析出的
  冗余列（映射变更时由服务层重解析），取值：

  - ``linked``：有 download_hash 且 MP 下载器已映射 → 可按
    (bt_downloader_id, download_hash) 精确定位任务；
  - ``unmapped``：有 download_hash 但 MP 下载器未配置映射；
  - ``unassociated``：无 download_hash（无法关联，文件名相似不作为依据）。

  ``linked`` 只表达"映射已就绪"，任务是否存在于 ``torrent_info`` 在查询时
  汇报（任务可能已删或尚未同步）。
"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# 关联状态常量（写入时解析，查询/前端展示消费）
ASSOCIATION_LINKED = "linked"
ASSOCIATION_UNMAPPED = "unmapped"
ASSOCIATION_UNASSOCIATED = "unassociated"
ASSOCIATION_STATUSES = (ASSOCIATION_LINKED, ASSOCIATION_UNMAPPED, ASSOCIATION_UNASSOCIATED)


def parse_mp_date(raw: Optional[str]) -> Optional[datetime]:
    """解析 MoviePilot 的 date 字段（"%Y-%m-%d %H:%M:%S" 字符串）；失败返回 None。"""
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw.strip()[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


class MoviePilotTransferHistory(Base):
    """MoviePilot 整理历史镜像表（moviepilot_transfer_history）。"""

    __tablename__ = "moviepilot_transfer_history"
    __table_args__ = (
        UniqueConstraint("instance_id", "history_id", name="uq_moviepilot_history_identity"),
        Index("idx_moviepilot_hash_dl", "download_hash", "bt_downloader_id"),
        Index("idx_moviepilot_dest_path", "dest_path"),
        Index("idx_moviepilot_src_path", "src_path"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    instance_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="所属 MoviePilot 实例 UUID"
    )
    history_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="MoviePilot TransferHistory 主键")
    # 源/目标（MoviePilot 侧原值）
    src_storage: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="源存储类型（local/rmt/...）")
    src_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="源文件路径（MP 原值）")
    dest_storage: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="目标存储类型")
    dest_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="目标媒体库路径（MP 原值）")
    transfer_mode: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="整理方式（copy/move/link/hardlink/...）"
    )
    # 媒体标识
    media_type: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, comment="媒体类型（电影/电视剧）")
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True, comment="媒体标题")
    year: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, comment="年份")
    seasons: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="季（Sxx）")
    episodes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="集（Exx，多集逗号分隔）")
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="TMDB ID")
    douban_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="豆瓣 ID")
    media_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="MP 统一媒体数据源")
    media_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="MP 原生媒体 ID")
    # 下载关联
    mp_downloader: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="MoviePilot 侧下载器名（原值）"
    )
    download_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="下载 Hash（MP 原值）")
    bt_downloader_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="映射解析出的 BtDeck downloader_id"
    )
    association_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ASSOCIATION_UNASSOCIATED, comment="关联状态 linked/unmapped/unassociated"
    )
    # 状态与时间
    status: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, comment="MP 侧整理成功状态")
    errmsg: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="MP 侧整理失败信息")
    mp_recorded_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="MP date 原始字符串")
    recorded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="MP date 解析值（解析失败为空）"
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment="规范字段 SHA-256（幂等变更判定）")
    raw_snapshot: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="关键字段原始 JSON 留档（含 fileitem/files 概要）"
    )
    first_synced_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, comment="首次同步时间"
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, comment="最近同步时间（内容变化或新插入）"
    )

    def __init__(
        self,
        instance_id: str,
        history_id: int,
        content_hash: str,
        association_status: str = ASSOCIATION_UNASSOCIATED,
    ):
        self.instance_id = instance_id
        self.history_id = history_id
        self.content_hash = content_hash
        self.association_status = association_status

    def to_dict(self) -> Dict[str, Any]:
        raw: Optional[Dict[str, Any]] = None
        if self.raw_snapshot:
            try:
                parsed = json.loads(self.raw_snapshot)
                raw = parsed if isinstance(parsed, dict) else None
            except (TypeError, ValueError):
                raw = None
        return {
            "id": self.id,
            "instanceId": self.instance_id,
            "historyId": self.history_id,
            "srcStorage": self.src_storage,
            "srcPath": self.src_path,
            "destStorage": self.dest_storage,
            "destPath": self.dest_path,
            "transferMode": self.transfer_mode,
            "mediaType": self.media_type,
            "title": self.title,
            "year": self.year,
            "seasons": self.seasons,
            "episodes": self.episodes,
            "tmdbId": self.tmdb_id,
            "doubanId": self.douban_id,
            "mediaSource": self.media_source,
            "mediaId": self.media_id,
            "mpDownloader": self.mp_downloader,
            "downloadHash": self.download_hash,
            "btDownloaderId": self.bt_downloader_id,
            "associationStatus": self.association_status,
            "status": self.status,
            "errmsg": self.errmsg,
            "recordedAt": self.recorded_at.isoformat() if self.recorded_at else None,
            "mpRecordedAt": self.mp_recorded_at,
            "raw": raw,
            "firstSyncedAt": self.first_synced_at.isoformat() if self.first_synced_at else None,
            "lastSyncedAt": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }
