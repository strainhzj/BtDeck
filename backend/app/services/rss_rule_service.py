# -*- coding: utf-8 -*-
"""
RSS 规则与模式服务（feature rss-subscription-phase2-2026-09-24）

职责：
- RSS 模式读取/切换（btdeck / qb_native，按下载器；qb_native 仅 qB 且
  需 rss_management 能力）；
- 引擎自动下载规则 CRUD（关键词 include/exclude + 正则开关 + 目标下载器
  /savePath/tags；规则↔源多选绑定，空关联=归属下载器全部源）；
- 匹配引擎：include 任一命中（OR）且 exclude 全不命中（AND NOT），默认
  大小写不敏感子串，use_regex=1 时 re.search；匹配字段=文章 title；
- 回填：规则创建/更新后立即对存量 pending 匹配并自动推送（对齐 qB 直觉），
  推送复用 RssFeedService.add_article_to_downloader 全链路（含双模式护栏）。

安全口径：
- 推送客户端一律取自 app.state.store 缓存（CL-16）；
- 正则由服务端编译校验（非法即拒），防 ReDoS 不做静态分析（关键词长度与
  文章标题长度均有库内上限，风险面与既有搜索一致）。
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.downloader.models import BtDownloaders
from app.models.rss_subscription import (
    RSS_MODE_BTDECK,
    RSS_MODE_CHOICES,
    RSS_MODE_QB_NATIVE,
    RssArticle,
    RssFeed,
    RssMode,
    RssRule,
    RssRuleFeed,
)
from app.services.downloader_capabilities_manager import supports_rss_management
from app.services.rss_feed_service import (
    ARTICLE_STATUS_PENDING,
    RssFeedService,
    RssServiceResult,
    is_qb_native,
)

logger = logging.getLogger(__name__)

# 支持作为规则目标/归属的下载器类型（与推送链路口径一致）
_SUPPORTED_DOWNLOADER_TYPES = (0, 1)

# 匹配预览/回填单次处理上限（防误配大规则时洪水推送）
_MATCH_PREVIEW_LIMIT = 50
_BACKFILL_LIMIT = 200
# 匹配扫描硬上限（流式逐行，命中够量即停；防老库海量 pending 全扫）
_SCAN_LIMIT = 5000


def _parse_keywords(raw: Optional[str]) -> List[str]:
    """逗号分隔关键词 → 去空去重列表。"""
    if not raw:
        return []
    seen: List[str] = []
    for part in raw.split(","):
        kw = part.strip()
        if kw and kw not in seen:
            seen.append(kw)
    return seen


def _compile_patterns(keywords: List[str], use_regex: bool) -> Optional[List[re.Pattern]]:
    """编译关键词（正则模式）；非法返回 None（调用方应已校验，此为兜底）。"""
    if not use_regex:
        return None
    patterns = []
    for kw in keywords:
        try:
            patterns.append(re.compile(kw, re.IGNORECASE))
        except re.error:
            return None
    return patterns


def _matches_keywords(title: str, include: List[str], exclude: List[str], use_regex: bool) -> bool:
    """匹配语义：include 任一命中（OR）且 exclude 全不命中（AND NOT）。

    非正则：大小写不敏感子串；正则：re.search（编译时已带 IGNORECASE）。
    """
    if use_regex:
        include_patterns = _compile_patterns(include, True) or []
        exclude_patterns = _compile_patterns(exclude, True) or []
        if not any(p.search(title) for p in include_patterns):
            return False
        return not any(p.search(title) for p in exclude_patterns)
    title_lower = title.lower()
    if not any(kw.lower() in title_lower for kw in include):
        return False
    return not any(kw.lower() in title_lower for kw in exclude)


class RssRuleService:
    """RSS 模式与自动规则领域服务（协议无关，HTTP 端点为薄壳）。"""

    def __init__(self, db: Session, store: Any = None):
        self.db = db
        self.store = store

    # ========== 下载器校验 ==========

    def _get_downloader(self, downloader_id: str) -> Optional[BtDownloaders]:
        return (
            self.db.query(BtDownloaders)
            .filter(BtDownloaders.downloader_id == downloader_id)
            .filter(BtDownloaders.dr == 0)
            .first()
        )

    # ========== 模式 ==========

    def get_mode(self, downloader_id: str) -> RssServiceResult:
        """读取下载器 RSS 模式（附带 qB 原生模式可用性，供前端门控）。"""
        downloader = self._get_downloader(downloader_id)
        if downloader is None:
            return RssServiceResult(ok=False, code="404", msg="下载器不存在", reason_code="RSS_DOWNLOADER_NOT_FOUND")
        mode = RSS_MODE_BTDECK
        try:
            row = self.db.query(RssMode).filter(RssMode.downloader_id == downloader_id).first()
            if row is not None and row.mode in RSS_MODE_CHOICES:
                mode = row.mode
        except SQLAlchemyError as e:
            logger.error("RSS 模式读取失败: %s", e)
            return RssServiceResult(ok=False, code="500", msg="获取 RSS 模式失败", reason_code="RSS_MODE_GET_FAILED")
        qb_native_available = supports_rss_management(self.db, downloader_id, downloader.downloader_type)
        return RssServiceResult(data={"mode": mode, "qbNativeAvailable": qb_native_available})

    def set_mode(self, downloader_id: str, mode: str) -> RssServiceResult:
        """切换下载器 RSS 模式（qb_native 仅 qB 且需 rss_management 能力）。"""
        if mode not in RSS_MODE_CHOICES:
            return RssServiceResult(
                ok=False, code="400", msg="无效的 RSS 模式（可选 btdeck / qb_native）", reason_code="RSS_MODE_INVALID"
            )
        downloader = self._get_downloader(downloader_id)
        if downloader is None:
            return RssServiceResult(ok=False, code="404", msg="下载器不存在", reason_code="RSS_DOWNLOADER_NOT_FOUND")
        if mode == RSS_MODE_QB_NATIVE:
            if downloader.downloader_type != 0:
                return RssServiceResult(
                    ok=False,
                    code="400",
                    msg="仅 qBittorrent 下载器支持 qB 原生 RSS 模式",
                    reason_code="RSS_MODE_TYPE_UNSUPPORTED",
                )
            if not supports_rss_management(self.db, downloader_id, downloader.downloader_type):
                return RssServiceResult(
                    ok=False,
                    code="400",
                    msg="该下载器的 RSS 管理能力已被关闭",
                    reason_code="RSS_MODE_CAPABILITY_DISABLED",
                )
        try:
            row = self.db.query(RssMode).filter(RssMode.downloader_id == downloader_id).first()
            if row is None:
                row = RssMode(downloader_id=downloader_id, mode=mode)
                self.db.add(row)
            else:
                row.mode = mode
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 模式切换失败: %s", e)
            return RssServiceResult(ok=False, code="500", msg="切换 RSS 模式失败", reason_code="RSS_MODE_UPDATE_FAILED")
        return RssServiceResult(
            msg="RSS 模式已切换",
            data={"mode": mode, "frozenHint": mode == RSS_MODE_QB_NATIVE},
        )

    # ========== 规则查询 ==========

    def list_rules(self, downloader_id: str, page: int = 1, page_size: int = 20) -> RssServiceResult:
        """按下载器分页列出规则（附带关联源与待命中数）。"""
        try:
            base = self.db.query(RssRule).filter(RssRule.dr == 0).filter(RssRule.downloader_id == downloader_id)
            total = base.count()
            rules = (
                base.order_by(RssRule.created_at.desc()).offset((max(page, 1) - 1) * page_size).limit(page_size).all()
            )
            rule_ids = [r.rule_id for r in rules]
            feed_map = self._rule_feed_map(rule_ids)
            items = [r.to_dict(feed_ids=feed_map.get(r.rule_id, [])) for r in rules]
            return RssServiceResult(data={"list": items, "total": total, "pageSize": page_size})
        except SQLAlchemyError as e:
            logger.error("RSS 规则列表查询失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="获取规则列表失败，请稍后重试", reason_code="RSS_RULE_LIST_FAILED"
            )

    def _rule_feed_map(self, rule_ids: List[str]) -> Dict[str, List[str]]:
        """批量取规则↔源关联。"""
        if not rule_ids:
            return {}
        rows = (
            self.db.query(RssRuleFeed.rule_id, RssRuleFeed.feed_id)
            .filter(RssRuleFeed.rule_id.in_(rule_ids))
            .order_by(RssRuleFeed.created_at)
            .all()
        )
        mapping: Dict[str, List[str]] = {}
        for rule_id, feed_id in rows:
            mapping.setdefault(rule_id, []).append(feed_id)
        return mapping

    def _get_rule(self, rule_id: str) -> Optional[RssRule]:
        return self.db.query(RssRule).filter(RssRule.rule_id == rule_id).filter(RssRule.dr == 0).first()

    # ========== 规则校验 ==========

    def _validate_rule_payload(
        self,
        downloader_id: str,
        name: Optional[str],
        include_keywords: Optional[str],
        exclude_keywords: Optional[str],
        use_regex: bool,
        target_downloader_id: Optional[str],
        save_path: Optional[str],
        tags: Optional[str],
        feed_ids: Optional[List[str]],
        exclude_rule_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """校验规则字段。返回 (ok, msg, reason_code)。"""
        if name is not None:
            name = name.strip()
            if not name or len(name) > 200:
                return False, "规则名称不能为空且不超过200字符", "RSS_RULE_NAME_INVALID"
        include_list = _parse_keywords(include_keywords)
        if not include_list:
            return False, "命中关键词不能为空（逗号分隔，至少一个）", "RSS_RULE_KEYWORDS_INVALID"
        if len(include_keywords or "") > 5000:
            return False, "命中关键词过长", "RSS_RULE_KEYWORDS_INVALID"
        if exclude_keywords and len(exclude_keywords) > 5000:
            return False, "排除关键词过长", "RSS_RULE_KEYWORDS_INVALID"
        if use_regex:
            for kw in include_list + _parse_keywords(exclude_keywords):
                try:
                    re.compile(kw, re.IGNORECASE)
                except re.error:
                    return False, f"非法正则表达式: {kw[:100]}", "RSS_RULE_REGEX_INVALID"
        if target_downloader_id is not None:
            target = self._get_downloader(target_downloader_id)
            if target is None:
                return False, "目标下载器不存在", "RSS_RULE_TARGET_INVALID"
            if target.downloader_type not in _SUPPORTED_DOWNLOADER_TYPES:
                return False, "目标下载器类型暂不支持 RSS 推送", "RSS_RULE_TARGET_INVALID"
        if save_path and len(save_path) > 500:
            return False, "保存路径不能超过500字符", "RSS_RULE_SAVE_PATH_INVALID"
        if tags and len(tags) > 200:
            return False, "标签不能超过200字符", "RSS_RULE_TAGS_INVALID"
        if feed_ids is not None:
            if len(set(feed_ids)) != len(feed_ids):
                return False, "关联订阅源存在重复", "RSS_RULE_FEED_INVALID"
            for feed_id in feed_ids:
                feed = self.db.query(RssFeed).filter(RssFeed.feed_id == feed_id).filter(RssFeed.dr == 0).first()
                if feed is None or feed.downloader_id != downloader_id:
                    return False, "关联订阅源不存在或不属于该下载器", "RSS_RULE_FEED_INVALID"
        # 同下载器下规则名唯一
        name_to_check = (name or "").strip() if name is not None else None
        if name_to_check:
            query = (
                self.db.query(RssRule)
                .filter(RssRule.dr == 0)
                .filter(RssRule.downloader_id == downloader_id)
                .filter(RssRule.name == name_to_check)
            )
            if exclude_rule_id:
                query = query.filter(RssRule.rule_id != exclude_rule_id)
            if query.first() is not None:
                return False, "该下载器下已存在同名规则", "RSS_RULE_DUPLICATE"
        return True, None, None

    # ========== 规则 CRUD ==========

    def create_rule(
        self,
        downloader_id: str,
        name: str,
        include_keywords: str,
        exclude_keywords: Optional[str] = None,
        use_regex: bool = False,
        target_downloader_id: Optional[str] = None,
        save_path: Optional[str] = None,
        tags: Optional[str] = None,
        feed_ids: Optional[List[str]] = None,
        enabled: bool = True,
    ) -> RssServiceResult:
        """仅同步创建规则（DB 落库 + 关联绑定），不触发回填。

        回填推送是异步链（store/INTERACTIVE lane），由端点层在事务提交后
        await apply_rule_to_pending；拆分避免同步方法内嵌事件循环桥。
        """
        downloader = self._get_downloader(downloader_id)
        if downloader is None:
            return RssServiceResult(ok=False, code="404", msg="下载器不存在", reason_code="RSS_DOWNLOADER_NOT_FOUND")
        ok, msg, reason = self._validate_rule_payload(
            downloader_id,
            name,
            include_keywords,
            exclude_keywords,
            use_regex,
            target_downloader_id,
            save_path,
            tags,
            feed_ids,
        )
        if not ok:
            return RssServiceResult(
                ok=False, code="400", msg=msg or "规则参数无效", reason_code=reason or "RSS_RULE_INVALID"
            )
        try:
            rule = RssRule(
                downloader_id=downloader_id,
                name=(name or "").strip(),
                include_keywords=include_keywords,
                exclude_keywords=exclude_keywords,
                use_regex=1 if use_regex else 0,
                target_downloader_id=target_downloader_id,
                save_path=save_path,
                tags=tags,
                enabled=1 if enabled else 0,
            )
            self.db.add(rule)
            self.db.flush()
            if feed_ids:
                for feed_id in feed_ids:
                    self.db.add(RssRuleFeed(rule_id=rule.rule_id, feed_id=feed_id))
            self.db.commit()
            self.db.refresh(rule)
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 规则创建失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="创建规则失败，请稍后重试", reason_code="RSS_RULE_CREATE_FAILED"
            )
        feed_map = self._rule_feed_map([rule.rule_id])
        return RssServiceResult(
            msg="规则创建成功",
            data={"rule": rule.to_dict(feed_ids=feed_map.get(rule.rule_id, []))},
        )

    def update_rule(
        self,
        rule_id: str,
        name: Optional[str] = None,
        include_keywords: Optional[str] = None,
        exclude_keywords: Optional[str] = None,
        use_regex: Optional[bool] = None,
        target_downloader_id: Optional[str] = None,
        save_path: Optional[str] = None,
        tags: Optional[str] = None,
        feed_ids: Optional[List[str]] = None,
        enabled: Optional[bool] = None,
        target_provided: bool = False,
        exclude_provided: bool = False,
    ) -> RssServiceResult:
        """仅同步更新规则（部分更新，*_provided 区分未传与显式置空），不触发回填。"""
        rule = self._get_rule(rule_id)
        if rule is None:
            return RssServiceResult(ok=False, code="404", msg="规则不存在", reason_code="RSS_RULE_NOT_FOUND")
        merged_name = name.strip() if name is not None else rule.name
        merged_include = include_keywords if include_keywords is not None else rule.include_keywords
        merged_exclude = exclude_keywords if exclude_provided else rule.exclude_keywords
        merged_regex = bool(use_regex) if use_regex is not None else bool(rule.use_regex)
        merged_target = target_downloader_id if target_provided else rule.target_downloader_id
        merged_save = save_path if save_path is not None else rule.save_path
        merged_tags = tags if tags is not None else rule.tags
        ok, msg, reason = self._validate_rule_payload(
            rule.downloader_id,
            merged_name,
            merged_include,
            merged_exclude,
            merged_regex,
            merged_target,
            merged_save,
            merged_tags,
            feed_ids,
            exclude_rule_id=rule_id,
        )
        if not ok:
            return RssServiceResult(
                ok=False, code="400", msg=msg or "规则参数无效", reason_code=reason or "RSS_RULE_INVALID"
            )
        try:
            rule.name = merged_name
            rule.include_keywords = merged_include
            rule.exclude_keywords = merged_exclude
            rule.use_regex = 1 if merged_regex else 0
            if target_provided:
                rule.target_downloader_id = merged_target
            if save_path is not None:
                rule.save_path = save_path
            if tags is not None:
                rule.tags = tags
            if enabled is not None:
                rule.enabled = 1 if enabled else 0
            if feed_ids is not None:
                self.db.query(RssRuleFeed).filter(RssRuleFeed.rule_id == rule_id).delete(synchronize_session=False)
                for feed_id in feed_ids:
                    self.db.add(RssRuleFeed(rule_id=rule_id, feed_id=feed_id))
            self.db.commit()
            self.db.refresh(rule)
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 规则更新失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="更新规则失败，请稍后重试", reason_code="RSS_RULE_UPDATE_FAILED"
            )
        feed_map = self._rule_feed_map([rule.rule_id])
        return RssServiceResult(
            msg="规则更新成功",
            data={"rule": rule.to_dict(feed_ids=feed_map.get(rule.rule_id, []))},
        )

    def delete_rule(self, rule_id: str) -> RssServiceResult:
        """软删除规则（关联行硬删；已推送文章事实保留）。"""
        rule = self._get_rule(rule_id)
        if rule is None:
            return RssServiceResult(ok=False, code="404", msg="规则不存在", reason_code="RSS_RULE_NOT_FOUND")
        try:
            rule.dr = 1
            self.db.query(RssRuleFeed).filter(RssRuleFeed.rule_id == rule_id).delete(synchronize_session=False)
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 规则删除失败: %s", e)
            return RssServiceResult(
                ok=False, code="500", msg="删除规则失败，请稍后重试", reason_code="RSS_RULE_DELETE_FAILED"
            )
        return RssServiceResult(msg="规则删除成功")

    # ========== 匹配引擎 ==========

    def _rule_feeds(self, rule: RssRule) -> List[str]:
        """规则作用域源 ID 列表（空关联=归属下载器全部未删源）。

        含停用源：停用源不进调度刷新，但存量 pending 仍可被预览/回填
        命中（调度侧不会为其产生新文章，无洪水风险）。
        """
        bound = [
            row.feed_id for row in self.db.query(RssRuleFeed.feed_id).filter(RssRuleFeed.rule_id == rule.rule_id).all()
        ]
        if bound:
            return bound
        rows = (
            self.db.query(RssFeed.feed_id)
            .filter(RssFeed.dr == 0)
            .filter(RssFeed.downloader_id == rule.downloader_id)
            .all()
        )
        return [row.feed_id for row in rows]

    def find_matching_pending(self, rule: RssRule, limit: int = _BACKFILL_LIMIT) -> List[RssArticle]:
        """查找规则作用域内命中关键词的 pending 文章（按发布时间倒序）。

        有界扫描：流式逐行匹配、命中够 limit 即停、硬上限 _SCAN_LIMIT 行
        （防老库海量 pending 一次性载入内存；对齐 OOM 治理约束）。
        """
        include = _parse_keywords(rule.include_keywords)
        exclude = _parse_keywords(rule.exclude_keywords)
        if not include:
            return []
        use_regex = bool(rule.use_regex)
        feed_ids = self._rule_feeds(rule)
        if not feed_ids:
            return []
        query = (
            self.db.query(RssArticle)
            .filter(RssArticle.feed_id.in_(feed_ids))
            .filter(RssArticle.status == ARTICLE_STATUS_PENDING)
            .order_by(RssArticle.published_at.desc().nullslast(), RssArticle.fetched_at.desc())
        )
        matched: List[RssArticle] = []
        scanned = 0
        for article in query.yield_per(200):
            scanned += 1
            if scanned > _SCAN_LIMIT:
                logger.warning(
                    "RSS 规则匹配扫描达上限截断 [rule_id=%s scan_limit=%d matched=%d]",
                    rule.rule_id,
                    _SCAN_LIMIT,
                    len(matched),
                )
                break
            if _matches_keywords(article.title or "", include, exclude, use_regex):
                matched.append(article)
                if len(matched) >= limit:
                    break
        return matched

    def match_preview(self, rule_id: str) -> RssServiceResult:
        """匹配预览（只读，不推送）。"""
        rule = self._get_rule(rule_id)
        if rule is None:
            return RssServiceResult(ok=False, code="404", msg="规则不存在", reason_code="RSS_RULE_NOT_FOUND")
        articles = self.find_matching_pending(rule, limit=_MATCH_PREVIEW_LIMIT)
        feed_names = (
            {
                f.feed_id: f.name
                for f in self.db.query(RssFeed).filter(RssFeed.feed_id.in_([a.feed_id for a in articles])).all()
            }
            if articles
            else {}
        )
        items = []
        for a in articles:
            item = a.to_dict()
            item["feedName"] = feed_names.get(a.feed_id)
            items.append(item)
        return RssServiceResult(
            msg="匹配预览成功",
            data={
                "list": items,
                "total": len(items),
                "pageSize": _MATCH_PREVIEW_LIMIT,
                "truncated": len(articles) == _MATCH_PREVIEW_LIMIT,
            },
        )

    async def apply_rule_to_pending(self, rule: RssRule) -> Dict[str, int]:
        """对存量 pending 执行匹配并自动推送（护栏：目标 qb_native 跳过）。

        返回 {matched, pushed, failed, skipped_mode}。推送失败不中断单条
        后续文章；match_count 累计成功推送数。
        """
        counts = {"matched": 0, "pushed": 0, "failed": 0, "skipped_mode": 0}
        if not rule.enabled:
            return counts
        target_id = rule.target_downloader_id or rule.downloader_id
        articles = self.find_matching_pending(rule, limit=_BACKFILL_LIMIT)
        counts["matched"] = len(articles)
        if not articles:
            return counts
        if is_qb_native(self.db, target_id):
            counts["skipped_mode"] = len(articles)
            return counts
        feed_service = RssFeedService(self.db, self.store)
        for article in articles:
            result = await feed_service.add_article_to_downloader(
                article.article_id,
                downloader_id=rule.target_downloader_id,
                save_path=rule.save_path,
                tags=rule.tags,
                rule_id=rule.rule_id,
            )
            if result.ok:
                counts["pushed"] += 1
            elif result.reason_code == "RSS_MODE_CONFLICT":
                counts["skipped_mode"] += 1
            else:
                counts["failed"] += 1
        self._touch_rule_stats(rule, pushed=counts["pushed"])
        return counts

    def _touch_rule_stats(self, rule: RssRule, pushed: int) -> None:
        """更新规则命中统计（best-effort；仅成功推送时累加）。"""
        if pushed <= 0:
            return
        try:
            rule.match_count = (rule.match_count or 0) + pushed
            rule.last_matched_at = datetime.utcnow()
            self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error("RSS 规则统计落库失败 [rule_id=%s]: %s", rule.rule_id, e)
