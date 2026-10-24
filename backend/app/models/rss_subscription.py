# -*- coding: utf-8 -*-
"""
RSS 订阅模型

包含 RssFeed（订阅源）、RssArticle（订阅文章）、RssMode（按下载器
RSS 模式）、RssRule（引擎自动下载规则）、RssRuleFeed（规则↔源关联）。
Phase 1（feature rss-subscription-2026-09-24）：订阅源绑定单一下载器，
文章手动推送到下载器。Phase 2（feature rss-subscription-phase2-2026-09-24）：
双模式（btdeck/qb_native）+ 关键词自动规则 + 定时调度（本模块承载
refresh_interval_minutes 覆盖列与 added_rule_id 命中事实列）。

@Time    : 2026-09-24
@Author  : btpManager Team
@File    : rss_subscription.py
"""

from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import uuid

# RSS 模式常量（bt_rss_modes.mode 取值域）
RSS_MODE_BTDECK = "btdeck"
RSS_MODE_QB_NATIVE = "qb_native"
RSS_MODE_CHOICES = (RSS_MODE_BTDECK, RSS_MODE_QB_NATIVE)


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

    refresh_interval_minutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="刷新间隔覆盖（分钟，null=跟全局调度节奏）"
    )

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
        refresh_interval_minutes: Optional[int] = None,
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
        self.refresh_interval_minutes = refresh_interval_minutes

    def to_dict(self) -> dict:
        """转换为字典（API 响应投影；时间字段与既有 VO 一致序列化为 ISO 字符串）"""
        return {
            "feedId": self.feed_id,
            "downloaderId": self.downloader_id,
            "name": self.name,
            "url": self.url,
            "enabled": bool(self.enabled),
            "refreshIntervalMinutes": self.refresh_interval_minutes,
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

    added_rule_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, comment="自动规则命中事实（推送规则ID，手动推送为空）"
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
            "addedRuleId": self.added_rule_id,
        }


class RssMode(Base):
    """RSS 模式表（按下载器二选一：btdeck= BtDeck 引擎 / qb_native= qB 自身管理）

    Phase 2（feature rss-subscription-phase2-2026-09-24）新增。
    行惰性创建：首次 PUT 才落行；无行 = 默认 btdeck。
    qb_native 仅对 qB（downloader_type==0）合法；该模式下 BtDeck 引擎
    对该下载器冻结（调度跳过其订阅源、推送护栏拦截），数据不删除。

    Attributes:
        downloader_id: 下载器ID（主键）
        mode: RSS 模式（btdeck/qb_native）
        created_at / updated_at: 审计字段
    """

    __tablename__ = "bt_rss_modes"

    downloader_id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="下载器ID")

    mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RSS_MODE_BTDECK, comment="RSS 模式：btdeck/qb_native"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )

    def __init__(self, downloader_id: Optional[str] = None, mode: str = RSS_MODE_BTDECK, **kw: Any):
        """初始化RssMode实例"""
        super().__init__(**kw)
        if downloader_id is not None:
            self.downloader_id = downloader_id
        self.mode = mode

    def to_dict(self) -> dict:
        """转换为字典（API 响应投影）"""
        return {
            "downloaderId": self.downloader_id,
            "mode": self.mode,
        }


class RssRule(Base):
    """RSS 自动下载规则表（BtDeck 引擎，关键词过滤）

    Phase 2（feature rss-subscription-phase2-2026-09-24）新增。

    匹配语义：include_keywords 任一命中（OR）且 exclude_keywords 全不命中
    （AND NOT）；默认大小写不敏感子串，use_regex=1 时按 re.search；
    匹配字段=文章 title。

    规则↔源绑定经 bt_rss_rule_feeds 关联表：空关联=归属下载器全部订阅源。

    Attributes:
        rule_id: 规则唯一标识符（UUID）
        downloader_id: 归属下载器ID（规则管理入口与默认推送目标）
        name: 规则名称（同下载器下唯一）
        enabled: 是否启用（调度与回填消费）
        include_keywords: 命中关键词（逗号分隔，任一命中）
        exclude_keywords: 排除关键词（逗号分隔，全不命中；可空）
        use_regex: 是否按正则匹配（0=子串，1=re.search）
        target_downloader_id: 推送目标下载器覆盖（null=归属下载器）
        save_path: 保存路径（透传下载器）
        tags: 标签（逗号分隔；qB=tags，TR=labels）
        match_count: 累计自动推送数
        last_matched_at: 最近一次命中推送时间
        created_at / updated_at: 审计字段
        dr: 软删除标记
    """

    __tablename__ = "bt_rss_rules"

    rule_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True, comment="规则唯一标识符")

    downloader_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, comment="归属下载器ID")

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="规则名称")

    enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="是否启用（1=启用，0=停用）")

    include_keywords: Mapped[str] = mapped_column(Text, nullable=False, comment="命中关键词（逗号分隔，任一命中）")

    exclude_keywords: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="排除关键词（逗号分隔，全不命中）"
    )

    use_regex: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="是否按正则匹配（0=子串，1=re.search）"
    )

    target_downloader_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, comment="推送目标下载器覆盖（null=归属下载器）"
    )

    save_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="保存路径")

    tags: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="标签（逗号分隔）")

    match_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="累计自动推送数")

    last_matched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="最近一次命中推送时间")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间"
    )

    dr: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="软删除标记")

    def __init__(
        self,
        rule_id: Optional[str] = None,
        downloader_id: Optional[str] = None,
        name: Optional[str] = None,
        include_keywords: Optional[str] = None,
        exclude_keywords: Optional[str] = None,
        use_regex: int = 0,
        target_downloader_id: Optional[str] = None,
        save_path: Optional[str] = None,
        tags: Optional[str] = None,
        enabled: int = 1,
        **kw: Any,
    ):
        """初始化RssRule实例"""
        super().__init__(**kw)
        self.rule_id = rule_id if rule_id is not None else str(uuid.uuid4())
        if downloader_id is not None:
            self.downloader_id = downloader_id
        if name is not None:
            self.name = name
        if include_keywords is not None:
            self.include_keywords = include_keywords
        if exclude_keywords is not None:
            self.exclude_keywords = exclude_keywords
        self.use_regex = use_regex
        if target_downloader_id is not None:
            self.target_downloader_id = target_downloader_id
        if save_path is not None:
            self.save_path = save_path
        if tags is not None:
            self.tags = tags
        self.enabled = enabled

    def to_dict(self, feed_ids: Optional[List[str]] = None) -> dict:
        """转换为字典（API 响应投影；feed_ids 为关联源列表，由服务层合并）"""
        return {
            "ruleId": self.rule_id,
            "downloaderId": self.downloader_id,
            "name": self.name,
            "enabled": bool(self.enabled),
            "includeKeywords": self.include_keywords,
            "excludeKeywords": self.exclude_keywords,
            "useRegex": bool(self.use_regex),
            "targetDownloaderId": self.target_downloader_id,
            "savePath": self.save_path,
            "tags": self.tags,
            "feedIds": feed_ids if feed_ids is not None else [],
            "matchCount": self.match_count,
            "lastMatchedAt": self.last_matched_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_matched_at else None,
            "createdAt": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class RssRuleFeed(Base):
    """RSS 规则↔源关联表（空关联=归属下载器全部订阅源）

    Phase 2（feature rss-subscription-phase2-2026-09-24）新增。
    复合主键 (rule_id, feed_id)；规则删除时硬删关联行（软删规则时同步清理）。
    """

    __tablename__ = "bt_rss_rule_feeds"

    rule_id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="规则ID")

    feed_id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="订阅源ID")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")

    def __init__(self, rule_id: Optional[str] = None, feed_id: Optional[str] = None, **kw: Any):
        """初始化RssRuleFeed实例"""
        super().__init__(**kw)
        if rule_id is not None:
            self.rule_id = rule_id
        if feed_id is not None:
            self.feed_id = feed_id
