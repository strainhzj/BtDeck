# -*- coding: utf-8 -*-
"""
RSS 订阅模型

包含 RssFeed（订阅源）与 RssArticle（订阅文章）两个模型。
Phase 1（feature rss-subscription-2026-09-24）：订阅源绑定单一下载器，
文章手动推送到下载器；Phase 2 预留规则引擎与按类型路由（本表不加列即可
复用 added_downloader_id 事实）。

@Time    : 2026-09-24
@Author  : btpManager Team
@File    : rss_subscription.py
"""

from datetime import datetime
from typing import Any, Optional
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import uuid


class RssFeed(Base):
    """RSS 订阅源表

    Attributes:
        feed_id: 订阅源唯一标识符（UUID）
        downloader_id: 绑定的下载器ID（推送默认目标）
        name: 订阅源名称
        url: 订阅源地址（RSS/Atom）
        enabled: 是否启用（Phase 1 仅作展示标记，调度在 Phase 2 消费）
        last_fetch_at: 最近一次抓取时间
        last_fetch_status: 最近一次抓取状态（never/ok/failed）
        last_error: 最近一次抓取失败原因（原文进库，展示层截断）
        created_at / updated_at: 审计字段
        dr: 软删除标记（0=未删除，1=已删除）
    """

    __tablename__ = "bt_rss_feeds"

    feed_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True, comment="订阅源唯一标识符")

    downloader_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="绑定的下载器ID")

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="订阅源名称")

    url: Mapped[str] = mapped_column(String(1000), nullable=False, comment="订阅源地址")

    enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="是否启用（1=启用，0=停用）")

    last_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近抓取时间")

    last_fetch_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="never", comment="最近抓取状态：never/ok/failed"
    )

    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="最近抓取失败原因")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )

    dr: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="软删除标记")

    def __init__(
        self,
        feed_id: Optional[str] = None,
        downloader_id: Optional[str] = None,
        name: Optional[str] = None,
        url: Optional[str] = None,
        enabled: int = 1,
        **kw: Any,
    ):
        """初始化RssFeed实例"""
        super().__init__(**kw)
        self.feed_id = feed_id if feed_id is not None else str(uuid.uuid4())
        if downloader_id is not None:
            self.downloader_id = downloader_id
        if name is not None:
            self.name = name
        if url is not None:
            self.url = url
        self.enabled = enabled

    def to_dict(self) -> dict:
        """转换为字典（API 响应投影；时间字段与既有 VO 一致序列化为 ISO 字符串）"""
        return {
            "feedId": self.feed_id,
            "downloaderId": self.downloader_id,
            "name": self.name,
            "url": self.url,
            "enabled": bool(self.enabled),
            "lastFetchAt": self.last_fetch_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_fetch_at else None,
            "lastFetchStatus": self.last_fetch_status,
            "lastError": self.last_error,
            "createdAt": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class RssArticle(Base):
    """RSS 订阅文章表

    Attributes:
        article_id: 文章唯一标识符（UUID）
        feed_id: 所属订阅源ID
        guid: 文章全局标识（RSS guid / Atom id；(feed_id, guid) 唯一去重）
        title: 文章标题
        link: 种子链接（magnet 或直链 .torrent URL）
        published_at: 发布时间（源数据，可空）
        fetched_at: 抓取入库时间
        status: 状态（pending=待处理，added=已推送）
        added_at: 推送时间
        added_downloader_id: 实际推送目标下载器（覆盖绑定下载器时记录事实）
        created_at: 审计字段
    """

    __tablename__ = "bt_rss_articles"

    article_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True, comment="文章唯一标识符")

    feed_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="所属订阅源ID")

    guid: Mapped[str] = mapped_column(String(500), nullable=False, comment="文章全局标识（去重键）")

    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="文章标题")

    link: Mapped[str] = mapped_column(String(2000), nullable=False, comment="种子链接（magnet 或直链 URL）")

    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="发布时间")

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, comment="抓取入库时间"
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True, comment="状态：pending/added"
    )

    added_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="推送时间")

    added_downloader_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, comment="实际推送目标下载器ID"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("feed_id", "guid", name="uq_rss_article_feed_guid"),
        {"comment": "RSS 订阅文章表（(feed_id,guid) 唯一去重）"},
    )

    def __init__(
        self,
        article_id: Optional[str] = None,
        feed_id: Optional[str] = None,
        guid: Optional[str] = None,
        title: Optional[str] = None,
        link: Optional[str] = None,
        published_at: Optional[datetime] = None,
        **kw: Any,
    ):
        """初始化RssArticle实例"""
        super().__init__(**kw)
        self.article_id = article_id if article_id is not None else str(uuid.uuid4())
        if feed_id is not None:
            self.feed_id = feed_id
        if guid is not None:
            self.guid = guid
        if title is not None:
            self.title = title
        if link is not None:
            self.link = link
        if published_at is not None:
            self.published_at = published_at

    def to_dict(self) -> dict:
        """转换为字典（API 响应投影）"""
        return {
            "articleId": self.article_id,
            "feedId": self.feed_id,
            "title": self.title,
            "link": self.link,
            "publishedAt": self.published_at.strftime("%Y-%m-%d %H:%M:%S") if self.published_at else None,
            "fetchedAt": self.fetched_at.strftime("%Y-%m-%d %H:%M:%S") if self.fetched_at else None,
            "status": self.status,
            "addedAt": self.added_at.strftime("%Y-%m-%d %H:%M:%S") if self.added_at else None,
            "addedDownloaderId": self.added_downloader_id,
        }
