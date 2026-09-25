# -*- coding: utf-8 -*-
"""
RSS 订阅服务（feature rss-subscription-2026-09-24 Phase 1）

职责：
- 订阅源 CRUD（软删；绑定单一下载器）；
- 订阅源抓取刷新（httpx 超时/大小受限 + feedparser 解析 + (feed_id, guid) 去重入库）；
- 文章分页查询；
- 文章推送到下载器（链接直传：qB ``torrents_add(urls=)`` / TR ``add_torrent(torrent=link)``，
  两者原生支持 magnet 与直链 .torrent URL；由下载器自行抓取种子数据）。

推送成功后不即时写 torrent_info——依赖既有下载器周期同步任务回填
（与 qB 原生 RSS 行为一致：添加是下载器侧事实，BtDeck 只记录推送状态）。

安全口径：
- 订阅源 URL 仅允许 http/https；抓取超时 15s、响应体上限 2MB；
- RSS 面与下载器主机配置同属管理员受信输入（认证端点），Phase 1 不做
  内网地址黑名单（Phase 2 若开放多用户再评估 SSRF 收紧）；
- 下载器客户端一律取自 app.state.store 缓存（CL-16），严禁自建连接。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import feedparser
import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.rss_subscription import (
    RSS_MODE_BTDECK,
    RSS_MODE_QB_NATIVE,
    RssArticle,
    RssFeed,
    RssMode,
)
from app.services.downloader_api_runtime import DownloadLane, call_downloader_api

logger = logging.getLogger(__name__)

# 抓取约束
_FETCH_TIMEOUT_SECONDS = 15.0
_MAX_FEED_BYTES = 2 * 1024 * 1024  # 2MB

# 下载器调用超时（INTERACTIVE lane，对齐标签管理同步调用口径）
_DOWNLOADER_CALL_TIMEOUT = 30.0

# 文章状态
ARTICLE_STATUS_PENDING = "pending"
ARTICLE_STATUS_ADDED = "added"

# 抓取状态
FETCH_STATUS_NEVER = "never"
FETCH_STATUS_OK = "ok"
FETCH_STATUS_FAILED = "failed"

# 支持的下载器类型（rTorrent 适配本体另立项，暂不开放）
_SUPPORTED_DOWNLOADER_TYPES = (0, 1)

# 每源刷新间隔覆盖上下限（分钟）
REFRESH_INTERVAL_MIN_MINUTES = 5
REFRESH_INTERVAL_MAX_MINUTES = 1440


def get_effective_mode(db: Session, downloader_id: str) -> str:
    """读取下载器生效的 RSS 模式（无行/异常 = 默认 btdeck）。

    模块级函数：rss_feed_service（推送护栏）与 rss_rule_service（模式端点/
    自动推送护栏）共用，避免循环依赖。
    """
    try:
        row = db.query(RssMode).filter(RssMode.downloader_id == downloader_id).first()
    except SQLAlchemyError as e:
        logger.warning("RSS 模式读取失败 [downloader_id=%s]: %s", downloader_id, e)
        return RSS_MODE_BTDECK
    if row is None:
        return RSS_MODE_BTDECK
    return row.mode if row.mode in (RSS_MODE_BTDECK, RSS_MODE_QB_NATIVE) else RSS_MODE_BTDECK


def is_qb_native(db: Session, downloader_id: str) -> bool:
    """下载器是否处于 qB 原生 RSS 模式（双模式冲突护栏判定）。"""
    return get_effective_mode(db, downloader_id) == RSS_MODE_QB_NATIVE


def validate_refresh_interval(minutes: Any) -> Tuple[bool, Optional[str]]:
    """校验每源刷新间隔覆盖（None 合法=用全局节奏）。返回 (ok, msg)。"""
    if minutes is None:
        return True, None
    if not isinstance(minutes, int) or isinstance(minutes, bool):
        return False, "刷新间隔必须是整数分钟"
    if not (REFRESH_INTERVAL_MIN_MINUTES <= minutes <= REFRESH_INTERVAL_MAX_MINUTES):
        return False, f"刷新间隔必须在 {REFRESH_INTERVAL_MIN_MINUTES}-{REFRESH_INTERVAL_MAX_MINUTES} 分钟之间"
    return True, None


@dataclass
class RssServiceResult:
    """领域结果：status/code/msg/reason_code，由端点映射协议响应。

    reason_code 遵循双语错误契约：失败路径携带稳定标识（data.reasonCode），
    动态 str(e) 只进日志不进 msg。
    """

    ok: bool = True
    code: str = "200"
    msg: str = "操作成功"
    reason_code: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)


def _is_http_url(url: str) -> bool:
    """仅接受 http/https 绝对 URL。"""
    try:
        parsed = urlparse(url)
    except (ValueError, AttributeError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_pushable_link(link: str) -> bool:
    """可推送链接：magnet 或 http/https 直链。"""
    if link.startswith("magnet:?"):
        return True
    return _is_http_url(link)


def _extract_torrent_link(entry: Any) -> Optional[str]:
    """从 feedparser entry 提取种子链接。

    优先级：BitTorrent enclosure（type 含 bittorrent 或 .torrent 后缀）> entry.link。
    """
    links = getattr(entry, "links", None) or []
    for link_info in links:
        mime = (getattr(link_info, "type", None) or "").lower()
        href = getattr(link_info, "href", None) or ""
        if "bittorrent" in mime or href.lower().endswith(".torrent"):
            return href
    entry_link = getattr(entry, "link", None)
    if entry_link:
        return entry_link
    # 部分源把链接放 enclosure
    enclosure = getattr(entry, "enclosures", None) or []
    for enc in enclosure:
        href = getattr(enc, "href", None)
        if href:
            return href
    return None


def _parse_published(entry: Any) -> Optional[datetime]:
    """解析发布时间（feedparser 已归一为 struct_time；失败返回 None）。"""
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6])
    except (TypeError, ValueError):
        return None


class RssFeedService:
    """RSS 订阅领域服务（协议无关，HTTP 端点为薄壳）。"""

    def __init__(self, db: Session, store: Any = None):
        """
        Args:
            db: 数据库会话（同步）
            store: 下载器缓存（app.state.store；由端点显式注入，CL-16）
        """
        self.db = db
        self.store = store

    # ========== 订阅源 CRUD ==========

    def list_feeds(self, downloader_id: str, page: int = 1, page_size: int = 20) -> RssServiceResult:
        """按下载器分页列出订阅源（附待添加文章数）。"""
        try:
            base = self.db.query(RssFeed).filter(RssFeed.dr == 0).filter(RssFeed.downloader_id == downloader_id)
            total = base.count()
            feeds = (
                base.order_by(RssFeed.created_at.desc()).offset((max(page, 1) - 1) * page_size).limit(page_size).all()
            )
            feed_ids = [f.feed_id for f in feeds]
            pending_counts = self._pending_counts(feed_ids)
            items = []
            for f in feeds:
                item = f.to_dict()
                item["pendingCount"] = pending_counts.get(f.feed_id, 0)
                items.append(item)
            return RssServiceResult(data={"list": items, "total": total, "pageSize": page_size})
        except SQLAlchemyError as e:
            logger.error("RSS 订阅源列表查询失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="获取订阅源列表失败，请稍后重试", reason_code="RSS_FEED_LIST_FAILED"
            )

    def _pending_counts(self, feed_ids: List[str]) -> Dict[str, int]:
        """批量统计各订阅源待添加文章数。"""
        if not feed_ids:
            return {}
        from sqlalchemy import func

        rows = (
            self.db.query(RssArticle.feed_id, func.count(RssArticle.article_id))
            .filter(RssArticle.feed_id.in_(feed_ids))
            .filter(RssArticle.status == ARTICLE_STATUS_PENDING)
            .group_by(RssArticle.feed_id)
            .all()
        )
        return {feed_id: count for feed_id, count in rows}

    def _get_feed(self, feed_id: str) -> Optional[RssFeed]:
        return self.db.query(RssFeed).filter(RssFeed.feed_id == feed_id).filter(RssFeed.dr == 0).first()

    def create_feed(self, downloader_id: str, name: str, url: str) -> RssServiceResult:
        """新增订阅源（同下载器下 URL 去重）。"""
        name = (name or "").strip()
        url = (url or "").strip()
        if not name or len(name) > 200:
            return RssServiceResult(
                ok=False, code="400", msg="订阅源名称不能为空且不超过200字符", reason_code="RSS_FEED_NAME_INVALID"
            )
        if not _is_http_url(url) or len(url) > 1000:
            return RssServiceResult(
                ok=False, code="400", msg="订阅源地址必须是合法的 http/https 链接", reason_code="RSS_FEED_URL_INVALID"
            )
        duplicate = (
            self.db.query(RssFeed)
            .filter(RssFeed.dr == 0)
            .filter(RssFeed.downloader_id == downloader_id)
            .filter(RssFeed.url == url)
            .first()
        )
        if duplicate:
            return RssServiceResult(
                ok=False, code="409", msg="该下载器下已存在相同地址的订阅源", reason_code="RSS_FEED_DUPLICATE"
            )
        try:
            feed = RssFeed(downloader_id=downloader_id, name=name, url=url)
            self.db.add(feed)
            self.db.commit()
            self.db.refresh(feed)
            item = feed.to_dict()
            item["pendingCount"] = 0
            return RssServiceResult(msg="订阅源创建成功", data={"feed": item})
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 订阅源创建失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="创建订阅源失败，请稍后重试", reason_code="RSS_FEED_CREATE_FAILED"
            )

    def update_feed(
        self,
        feed_id: str,
        name: Optional[str],
        url: Optional[str],
        enabled: Optional[bool],
        refresh_interval_minutes: Optional[int] = None,
        refresh_interval_provided: bool = False,
    ) -> RssServiceResult:
        """部分更新订阅源（name/url/enabled/refresh_interval_minutes 任一）。

        refresh_interval_provided 区分「未传」与「显式置空」（显式 null =
        恢复全局节奏），与下载器部分更新端点 case-when 语义对齐。
        """
        feed = self._get_feed(feed_id)
        if feed is None:
            return RssServiceResult(ok=False, code="404", msg="订阅源不存在", reason_code="RSS_FEED_NOT_FOUND")
        try:
            if name is not None:
                name = name.strip()
                if not name or len(name) > 200:
                    return RssServiceResult(
                        ok=False,
                        code="400",
                        msg="订阅源名称不能为空且不超过200字符",
                        reason_code="RSS_FEED_NAME_INVALID",
                    )
                feed.name = name
            if url is not None:
                url = url.strip()
                if not _is_http_url(url) or len(url) > 1000:
                    return RssServiceResult(
                        ok=False,
                        code="400",
                        msg="订阅源地址必须是合法的 http/https 链接",
                        reason_code="RSS_FEED_URL_INVALID",
                    )
                if url != feed.url:
                    duplicate = (
                        self.db.query(RssFeed)
                        .filter(RssFeed.dr == 0)
                        .filter(RssFeed.downloader_id == feed.downloader_id)
                        .filter(RssFeed.url == url)
                        .filter(RssFeed.feed_id != feed.feed_id)
                        .first()
                    )
                    if duplicate:
                        return RssServiceResult(
                            ok=False,
                            code="409",
                            msg="该下载器下已存在相同地址的订阅源",
                            reason_code="RSS_FEED_DUPLICATE",
                        )
                    feed.url = url
            if enabled is not None:
                feed.enabled = 1 if enabled else 0
            if refresh_interval_provided:
                ok, err = validate_refresh_interval(refresh_interval_minutes)
                if not ok:
                    return RssServiceResult(
                        ok=False, code="400", msg=err or "刷新间隔无效", reason_code="RSS_FEED_INTERVAL_INVALID"
                    )
                feed.refresh_interval_minutes = refresh_interval_minutes
            self.db.commit()
            self.db.refresh(feed)
            return RssServiceResult(msg="订阅源更新成功", data={"feed": feed.to_dict()})
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 订阅源更新失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="更新订阅源失败，请稍后重试", reason_code="RSS_FEED_UPDATE_FAILED"
            )

    def delete_feed(self, feed_id: str) -> RssServiceResult:
        """软删除订阅源（文章一并软删）。"""
        feed = self._get_feed(feed_id)
        if feed is None:
            return RssServiceResult(ok=False, code="404", msg="订阅源不存在", reason_code="RSS_FEED_NOT_FOUND")
        try:
            feed.dr = 1
            # 文章无 dr 列：物理删除跟随订阅源（Phase 1 无独立恢复诉求）
            self.db.query(RssArticle).filter(RssArticle.feed_id == feed_id).delete(synchronize_session=False)
            self.db.commit()
            return RssServiceResult(msg="订阅源删除成功")
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 订阅源删除失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="删除订阅源失败，请稍后重试", reason_code="RSS_FEED_DELETE_FAILED"
            )

    # ========== 抓取刷新 ==========

    async def refresh_feed(self, feed_id: str) -> RssServiceResult:
        """抓取订阅源并增量入库（guid 去重）。"""
        feed = self._get_feed(feed_id)
        if feed is None:
            return RssServiceResult(ok=False, code="404", msg="订阅源不存在", reason_code="RSS_FEED_NOT_FOUND")
        content: Optional[bytes] = None
        fetch_error: Optional[str] = None
        try:
            content, fetch_error = await self._fetch_feed_bytes(feed.url)
        except Exception:
            logger.exception("RSS 订阅源抓取异常 [feed_id=%s]", feed_id)
            fetch_error = "抓取异常"

        now = datetime.utcnow()
        if content is None:
            feed.last_fetch_at = now
            feed.last_fetch_status = FETCH_STATUS_FAILED
            feed.last_error = fetch_error or "抓取失败"
            try:
                self.db.commit()
            except SQLAlchemyError:
                self.db.rollback()
            return RssServiceResult(
                ok=False, code="502", msg="订阅源抓取失败，请检查地址与网络", reason_code="RSS_FEED_FETCH_FAILED"
            )

        entries, parse_error = await asyncio.to_thread(self._parse_entries, content)
        if entries is None:
            feed.last_fetch_at = now
            feed.last_fetch_status = FETCH_STATUS_FAILED
            feed.last_error = parse_error or "解析失败"
            try:
                self.db.commit()
            except SQLAlchemyError:
                self.db.rollback()
            return RssServiceResult(
                ok=False, code="422", msg="订阅源解析失败，内容不是有效的 RSS/Atom", reason_code="RSS_FEED_PARSE_FAILED"
            )

        new_count, total_count = self._upsert_articles(feed.feed_id, entries)
        feed.last_fetch_at = now
        feed.last_fetch_status = FETCH_STATUS_OK
        feed.last_error = None
        try:
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 订阅源刷新入库失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="订阅源刷新失败，请稍后重试", reason_code="RSS_FEED_REFRESH_FAILED"
            )
        return RssServiceResult(
            msg="订阅源刷新成功",
            data={
                "newCount": new_count,
                "articleCount": total_count,
                "lastFetchAt": feed.last_fetch_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    async def _fetch_feed_bytes(self, url: str) -> Tuple[Optional[bytes], Optional[str]]:
        """抓取订阅源内容（超时/大小受限）。返回 (content, error)。"""
        try:
            async with httpx.AsyncClient(
                timeout=_FETCH_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={"User-Agent": "BtDeck-RSS/1.0"},
            ) as client:
                response = await client.get(url)
            if response.status_code != 200:
                return None, f"HTTP {response.status_code}"
            content = response.content
            if len(content) > _MAX_FEED_BYTES:
                return None, f"响应超过大小上限 {_MAX_FEED_BYTES} 字节"
            return content, None
        except httpx.HTTPError as e:
            # 超时/连接失败等：动态细节只进日志
            logger.warning("RSS 订阅源抓取失败 [url=%s]: %s", url, e)
            return None, "网络请求失败"

    @staticmethod
    def _parse_entries(
        content: bytes,
    ) -> Tuple[Optional[List[Tuple[str, str, str, Optional[datetime]]]], Optional[str]]:
        """解析 feed 内容为 (guid, title, link, published) 列表。

        返回 (None, error) 表示解析失败（bozo 且无可用条目）。
        """
        parsed = feedparser.parse(content)
        entries = getattr(parsed, "entries", None) or []
        if not entries:
            bozo = getattr(parsed, "bozo", False)
            if bozo:
                return None, "内容不是有效的 RSS/Atom"
            return [], None
        result = []
        for entry in entries:
            guid = (getattr(entry, "id", None) or "").strip()
            title = (getattr(entry, "title", None) or "").strip()
            link = _extract_torrent_link(entry)
            if not guid:
                guid = link or title
            if not guid or not title or not link:
                continue  # 缺关键字段的条目跳过
            result.append((guid[:500], title[:500], link[:2000], _parse_published(entry)))
        return result, None

    def _upsert_articles(
        self, feed_id: str, entries: List[Tuple[str, str, str, Optional[datetime]]]
    ) -> Tuple[int, int]:
        """增量入库（guid 已存在则跳过）。返回 (新增数, 总数)。"""
        if not entries:
            return 0, self.db.query(RssArticle).filter(RssArticle.feed_id == feed_id).count()
        existing = {row[0] for row in self.db.query(RssArticle.guid).filter(RssArticle.feed_id == feed_id).all()}
        now = datetime.utcnow()
        new_count = 0
        for guid, title, link, published in entries:
            if guid in existing:
                continue
            self.db.add(
                RssArticle(
                    feed_id=feed_id,
                    guid=guid,
                    title=title,
                    link=link,
                    published_at=published or now,
                    fetched_at=now,
                    status=ARTICLE_STATUS_PENDING,
                )
            )
            existing.add(guid)
            new_count += 1
        if new_count:
            self.db.flush()
        total = self.db.query(RssArticle).filter(RssArticle.feed_id == feed_id).count()
        return new_count, total

    # ========== 文章查询 ==========

    def list_articles(self, feed_id: str, status: Optional[str], page: int, page_size: int) -> RssServiceResult:
        """分页查询订阅源文章（按发布时间倒序）。"""
        feed = self._get_feed(feed_id)
        if feed is None:
            return RssServiceResult(ok=False, code="404", msg="订阅源不存在", reason_code="RSS_FEED_NOT_FOUND")
        if status is not None and status not in (ARTICLE_STATUS_PENDING, ARTICLE_STATUS_ADDED):
            return RssServiceResult(
                ok=False, code="400", msg="无效的文章状态筛选", reason_code="RSS_ARTICLE_STATUS_INVALID"
            )
        try:
            base = self.db.query(RssArticle).filter(RssArticle.feed_id == feed_id)
            if status:
                base = base.filter(RssArticle.status == status)
            total = base.count()
            articles = (
                base.order_by(RssArticle.published_at.desc().nullslast(), RssArticle.fetched_at.desc())
                .offset((max(page, 1) - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return RssServiceResult(
                data={"list": [a.to_dict() for a in articles], "total": total, "pageSize": page_size}
            )
        except SQLAlchemyError as e:
            logger.error("RSS 文章列表查询失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="获取文章列表失败，请稍后重试", reason_code="RSS_ARTICLE_LIST_FAILED"
            )

    # ========== 推送到下载器 ==========

    async def add_article_to_downloader(
        self,
        article_id: str,
        downloader_id: Optional[str] = None,
        save_path: Optional[str] = None,
        tags: Optional[str] = None,
        rule_id: Optional[str] = None,
    ) -> RssServiceResult:
        """推送文章到下载器（链接直传，下载器自行抓取种子）。

        Args:
            article_id: 文章ID
            downloader_id: 目标下载器（None=订阅源绑定的下载器）
            save_path: 保存路径（可选）
            tags: 标签（可选，逗号分隔；qB=tags，TR=labels）
            rule_id: 自动规则命中事实（可选，内部参数：规则引擎回填推送
                携带，手动推送为空——记录进 added_rule_id）
        """
        article = self.db.query(RssArticle).filter(RssArticle.article_id == article_id).first()
        if article is None:
            return RssServiceResult(ok=False, code="404", msg="文章不存在", reason_code="RSS_ARTICLE_NOT_FOUND")
        if article.status == ARTICLE_STATUS_ADDED:
            return RssServiceResult(
                ok=False, code="409", msg="文章已推送过，不可重复推送", reason_code="RSS_ARTICLE_ALREADY_ADDED"
            )
        if not _is_pushable_link(article.link):
            return RssServiceResult(
                ok=False,
                code="422",
                msg="文章链接不是可推送的 magnet 或直链地址",
                reason_code="RSS_ARTICLE_LINK_UNSUPPORTED",
            )
        feed = self._get_feed(article.feed_id)
        if feed is None:
            return RssServiceResult(ok=False, code="404", msg="订阅源不存在", reason_code="RSS_FEED_NOT_FOUND")
        target_downloader_id = downloader_id or feed.downloader_id

        # ========== 双模式冲突护栏（Phase 2） ==========
        # 目标下载器处于 qB 原生模式时，BtDeck 引擎不得对其推送（避免双份下载）
        if is_qb_native(self.db, target_downloader_id):
            return RssServiceResult(
                ok=False,
                code="409",
                msg="目标下载器已切换为 qB 原生 RSS 模式，请在该下载器内管理订阅",
                reason_code="RSS_MODE_CONFLICT",
            )

        # ========== 从 store 缓存解析下载器客户端（CL-16） ==========
        if self.store is None:
            return RssServiceResult(ok=False, code="500", msg="下载器缓存未初始化", reason_code="RSS_STORE_UNAVAILABLE")
        cached_downloaders = await self.store.get_snapshot()
        downloader_vo = next((d for d in cached_downloaders if d.downloader_id == target_downloader_id), None)
        if downloader_vo is None:
            return RssServiceResult(
                ok=False, code="404", msg="目标下载器不存在或未连接", reason_code="RSS_DOWNLOADER_NOT_FOUND"
            )
        if getattr(downloader_vo, "fail_time", 0) > 0:
            return RssServiceResult(
                ok=False, code="503", msg="目标下载器当前不可用", reason_code="RSS_DOWNLOADER_OFFLINE"
            )
        client = getattr(downloader_vo, "client", None)
        if client is None:
            return RssServiceResult(
                ok=False, code="500", msg="目标下载器客户端连接不存在", reason_code="RSS_DOWNLOADER_CONNECTION_MISSING"
            )

        downloader_type = getattr(downloader_vo, "downloader_type", None)
        if downloader_type not in _SUPPORTED_DOWNLOADER_TYPES:
            return RssServiceResult(
                ok=False, code="422", msg="该下载器类型暂不支持 RSS 推送", reason_code="RSS_DOWNLOADER_TYPE_UNSUPPORTED"
            )

        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()] if tags else None

        # ========== 类型分支：链接直传下载器 ==========
        try:
            if downloader_type == 0:  # qBittorrent
                kwargs: Dict[str, Any] = {"urls": article.link}
                if save_path:
                    kwargs["save_path"] = save_path
                if tag_list:
                    kwargs["tags"] = ",".join(tag_list)
                add_result = await call_downloader_api(
                    target_downloader_id,
                    DownloadLane.INTERACTIVE,
                    client.torrents_add,
                    kwargs=kwargs,
                    timeout=_DOWNLOADER_CALL_TIMEOUT,
                    operation="rss_add_torrent",
                )
                # qB 成功返回 "Ok."；其余（含 "Fails."）按失败处理
                if str(add_result).strip().lower() != "ok.":
                    return RssServiceResult(
                        ok=False, code="502", msg="推送到 qBittorrent 失败", reason_code="RSS_ADD_FAILED"
                    )
            else:  # Transmission
                tr_kwargs: Dict[str, Any] = {}
                if save_path:
                    tr_kwargs["download_dir"] = save_path
                if tag_list:
                    tr_kwargs["labels"] = tag_list
                # 重复添加返回 None（TR 去重事实），按成功处理（目的已达成）
                await call_downloader_api(
                    target_downloader_id,
                    DownloadLane.INTERACTIVE,
                    client.add_torrent,
                    args=(article.link,),
                    kwargs=tr_kwargs,
                    timeout=_DOWNLOADER_CALL_TIMEOUT,
                    operation="rss_add_torrent",
                )
        except Exception:
            logger.exception(
                "RSS 文章推送失败 [article_id=%s downloader_id=%s type=%s]",
                article_id,
                target_downloader_id,
                downloader_type,
            )
            return RssServiceResult(
                ok=False, code="502", msg="推送到下载器失败，请稍后重试", reason_code="RSS_ADD_FAILED"
            )

        # ========== 标记推送事实 ==========
        try:
            article.status = ARTICLE_STATUS_ADDED
            article.added_at = datetime.utcnow()
            article.added_downloader_id = target_downloader_id
            if rule_id is not None:
                article.added_rule_id = rule_id
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 文章推送状态落库失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="推送成功但状态记录失败，请勿重复推送", reason_code="RSS_ADD_STATE_FAILED"
            )
        return RssServiceResult(
            msg="推送成功",
            data={"article": article.to_dict(), "downloaderId": target_downloader_id},
        )
