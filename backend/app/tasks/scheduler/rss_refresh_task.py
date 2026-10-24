# -*- coding: utf-8 -*-
"""BtDeck 引擎 RSS 定时刷新任务（feature rss-subscription-phase2-2026-09-24）。

节奏：cron 由系统任务注册表控制（默认 13,43 * * * *，30 分钟 + 错峰分钟，
用户可在任务 UI 自调）。每轮：

1. 取全部 enabled 订阅源；
2. 过滤：绑定下载器离线（跳过）/ qb_native 模式（引擎冻结，跳过）/
   每源 refresh_interval_minutes 覆盖未到期（跳过）；
3. 逐源刷新（复用 RssFeedService.refresh_feed，httpx 15s+2MB 受限抓取；
   单源失败不中断）；
4. 每源刷新后执行该下载器作用域内规则的匹配 + 自动推送
   （apply_rule_to_pending，含双模式护栏：目标 qb_native 跳过计数）；
5. 汇总输出（错误列表有界，对齐 OOM 治理输出约束）。

android-server 伴侣形态：外网抓取不可用，任务注册即跳过（对齐平台门控惯例）。
轻量任务不入 task_profiles 背压（无全量下载器快照加载）。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.database import SessionLocal
from app.models.rss_subscription import RssArticle, RssFeed, RssRule, RssRuleFeed
from app.services.rss_feed_service import ARTICLE_STATUS_PENDING, RssFeedService, is_qb_native
from app.services.rss_rule_service import RssRuleService

logger = logging.getLogger(__name__)

# 单轮汇总错误明细上限（防海量源失败时 execution_log 失控）
_MAX_ERROR_ENTRIES = 20

# 全局兜底刷新间隔（分钟）：cron 被用户调密时防打爆源站
_GLOBAL_MIN_INTERVAL_MINUTES = 10


class RssRefreshTask:
    name = "RSS 订阅定时刷新任务"
    description = (
        "定时刷新 BtDeck 引擎的全部启用 RSS 订阅源并执行自动下载规则"
        "（qb_native 模式下载器与离线下载器自动跳过；支持每源刷新间隔覆盖）。"
    )
    version = "1.0.0"
    author = "btpManager"
    category = "rss"

    def __init__(self, app: Optional[Any] = None):
        self.app = app

    def set_app(self, app: Any):
        self.app = app

    async def execute(self, **kwargs) -> Dict[str, Any]:
        from app.core.platform_capabilities import is_android_server

        if is_android_server():
            return {
                "status": "skipped",
                "task_name": self.name,
                "message": "android-server 运行形态不支持外网 RSS 抓取",
            }

        if self.app is None and "app" in kwargs:
            self.app = kwargs["app"]
        store = getattr(getattr(self.app, "state", None), "store", None) if self.app is not None else None
        if store is None:
            return {
                "status": "skipped",
                "task_name": self.name,
                "message": "Downloader cache not initialized",
            }

        db = SessionLocal()
        summary: Dict[str, Any] = {
            "refreshed": 0,
            "skipped_offline": 0,
            "skipped_mode": 0,
            "skipped_interval": 0,
            "new_articles": 0,
            "auto_added": 0,
            "auto_skipped_mode": 0,
            "auto_failed": 0,
            "errors": [],
        }
        try:
            snapshot = await store.get_snapshot()
            online_ids = {d.downloader_id for d in snapshot if getattr(d, "fail_time", 0) == 0}
            feeds: List[RssFeed] = (
                db.query(RssFeed)
                .filter(RssFeed.dr == 0)
                .filter(RssFeed.enabled == 1)
                .order_by(RssFeed.created_at)
                .all()
            )
            now = datetime.utcnow()
            feed_service = RssFeedService(db, store)
            rule_service = RssRuleService(db, store)

            for feed in feeds:
                if feed.downloader_id not in online_ids:
                    summary["skipped_offline"] += 1
                    continue
                if is_qb_native(db, feed.downloader_id):
                    summary["skipped_mode"] += 1
                    continue
                if not self._interval_due(feed, now):
                    summary["skipped_interval"] += 1
                    continue
                try:
                    result = await feed_service.refresh_feed(feed.feed_id)
                except Exception as e:  # noqa: BLE001 - 单源失败不中断
                    logger.exception("RSS 订阅源刷新异常 [feed_id=%s]", feed.feed_id)
                    self._append_error(summary, feed.name, str(e))
                    continue
                if not result.ok:
                    self._append_error(summary, feed.name, result.msg)
                    continue
                summary["refreshed"] += 1
                summary["new_articles"] += int(result.data.get("newCount") or 0)

                # 刷新后执行该下载器作用域内规则（命中 pending 自动推送）
                rule_counts = await self._run_rules_for_feed(rule_service, db, feed)
                for key, value in rule_counts.items():
                    summary[key] = summary.get(key, 0) + value

            summary["status"] = "success" if not summary["errors"] else "partial"
            summary["task_name"] = self.name
            return summary
        finally:
            db.close()

    @staticmethod
    def _interval_due(feed: RssFeed, now: datetime) -> bool:
        """每源间隔覆盖判定（null=跟全局节奏；全局兜底下限防 cron 调密打爆）。"""
        interval = feed.refresh_interval_minutes or _GLOBAL_MIN_INTERVAL_MINUTES
        if feed.last_fetch_at is None:
            return True
        return now - feed.last_fetch_at >= timedelta(minutes=interval)

    async def _run_rules_for_feed(self, rule_service: RssRuleService, db: Any, feed: RssFeed) -> Dict[str, int]:
        """执行作用域包含该源的全部启用规则（跳过非 pending 无需处理）。"""
        counts = {"auto_added": 0, "auto_skipped_mode": 0, "auto_failed": 0}
        has_pending = (
            db.query(RssArticle.article_id)
            .filter(RssArticle.feed_id == feed.feed_id)
            .filter(RssArticle.status == ARTICLE_STATUS_PENDING)
            .first()
        )
        if not has_pending:
            return counts
        rules = (
            db.query(RssRule)
            .filter(RssRule.dr == 0)
            .filter(RssRule.enabled == 1)
            .filter(RssRule.downloader_id == feed.downloader_id)
            .all()
        )
        for rule in rules:
            bound = [
                row.feed_id for row in db.query(RssRuleFeed.feed_id).filter(RssRuleFeed.rule_id == rule.rule_id).all()
            ]
            if bound and feed.feed_id not in bound:
                continue
            try:
                result = await rule_service.apply_rule_to_pending(rule)
            except Exception as e:  # noqa: BLE001 - 单规则失败不中断
                logger.exception("RSS 规则自动推送异常 [rule_id=%s]", rule.rule_id)
                counts["auto_failed"] += 1
                del e
                continue
            counts["auto_added"] += result.get("pushed", 0)
            counts["auto_skipped_mode"] += result.get("skipped_mode", 0)
            counts["auto_failed"] += result.get("failed", 0)
        return counts

    @staticmethod
    def _append_error(summary: Dict[str, Any], feed_name: str, message: str) -> None:
        if len(summary["errors"]) < _MAX_ERROR_ENTRIES:
            summary["errors"].append({"feed": feed_name, "message": message})
