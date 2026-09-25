# -*- coding: utf-8 -*-
"""RSS 定时刷新任务回归（feature rss-subscription-phase2-2026-09-24）。

保护点：
1. 种子条目存在于 DEFAULT_SCHEDULED_TASKS（cron 错峰 13,43、executor 路径
   可动态导入、轻量不登记 task_profiles）；
2. 任务行为：enabled 源刷新 / 离线跳过 / qb_native 冻结跳过 / 每源间隔
   覆盖跳过 / 单源失败不中断（错误有界）；
3. 刷新后规则管线：作用域规则执行（bound 过滤）、无 pending 短路；
4. android-server 跳过与 store 缺失跳过。
"""

import importlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.default_scheduled_tasks import DEFAULT_SCHEDULED_TASKS
from app.database import Base
from app.models.rss_subscription import RssArticle, RssFeed, RssMode, RssRule, RssRuleFeed
from app.services.rss_feed_service import RssFeedService
from app.services.rss_rule_service import RssRuleService
from app.tasks.scheduler.rss_refresh_task import RssRefreshTask
from app.tasks.task_profiles import TASK_PROFILES

EXPECTED = {
    "task_code": "bt_rss_refresh",
    "executor": "app.tasks.scheduler.rss_refresh_task.RssRefreshTask",
    "cron_plan": "13,43 * * * *",
}

_TEST_TABLES = [RssFeed.__table__, RssArticle.__table__, RssMode.__table__, RssRule.__table__, RssRuleFeed.__table__]


def _seed_entry():
    return next(t for t in DEFAULT_SCHEDULED_TASKS if t["task_code"] == EXPECTED["task_code"])


class TestSeedWiring:
    def test_seed_entry_present_with_expected_wiring(self):
        entry = _seed_entry()
        assert entry["executor"] == EXPECTED["executor"]
        assert entry["cron_plan"] == EXPECTED["cron_plan"]
        assert entry["enabled"] is True
        assert entry["timeout_seconds"] == 900
        assert entry["max_retry_count"] == 0

    def test_executor_path_dynamically_importable(self):
        module_path, class_name = EXPECTED["executor"].rsplit(".", 1)
        module = importlib.import_module(module_path)
        task_class = getattr(module, class_name)
        assert task_class.name
        assert task_class.description
        import inspect

        assert inspect.iscoroutinefunction(task_class.execute)

    def test_not_registered_as_heavy_task(self):
        assert EXPECTED["task_code"] not in TASK_PROFILES


# ==============================================================================
# 任务行为
# ==============================================================================


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=_TEST_TABLES)
    yield engine
    Base.metadata.drop_all(bind=engine, tables=_TEST_TABLES)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


def _make_feed(db: Session, feed_id: str, downloader_id: str = "dl-qb-1", **kw) -> RssFeed:
    feed = RssFeed(
        feed_id=feed_id, downloader_id=downloader_id, name=f"源{feed_id}", url=f"https://x/{feed_id}.xml", **kw
    )
    db.add(feed)
    db.commit()
    return feed


def _make_rule(db: Session, rule_id: str, downloader_id: str = "dl-qb-1", feed_ids=None) -> RssRule:
    rule = RssRule(rule_id=rule_id, downloader_id=downloader_id, name=f"规则{rule_id}", include_keywords="kw")
    db.add(rule)
    if feed_ids:
        for fid in feed_ids:
            db.add(RssRuleFeed(rule_id=rule_id, feed_id=fid))
    db.commit()
    return rule


def _make_app(store) -> MagicMock:
    app = MagicMock()
    app.state.store = store
    return app


def _fake_store(online=("dl-qb-1",)):
    store = MagicMock()
    store.get_snapshot = AsyncMock(
        return_value=[
            SimpleNamespace(downloader_id=did, fail_time=0, client=MagicMock(), downloader_type=0, nickname=did)
            for did in online
        ]
    )
    return store


async def _run(task: RssRefreshTask, store):
    task.set_app(_make_app(store))
    return await task.execute()


class TestTaskBehavior:
    async def test_refreshes_enabled_feeds_and_runs_rules(self, db_session):
        _make_feed(db_session, "f1")
        _make_rule(db_session, "r1", feed_ids=["f1"])
        db_session.add(RssArticle(feed_id="f1", guid="g1", title="t", link="magnet:?x"))
        db_session.commit()
        store = _fake_store()

        refresh_mock = AsyncMock(return_value=MagicMock(ok=True, data={"newCount": 3}))
        apply_mock = AsyncMock(return_value={"matched": 1, "pushed": 1, "failed": 0, "skipped_mode": 0})
        with (
            patch("app.tasks.scheduler.rss_refresh_task.SessionLocal", return_value=db_session),
            patch.object(RssFeedService, "refresh_feed", refresh_mock),
            patch.object(RssRuleService, "apply_rule_to_pending", apply_mock),
        ):
            summary = await _run(RssRefreshTask(), store)

        assert summary["status"] == "success"
        assert summary["refreshed"] == 1
        assert summary["new_articles"] == 3
        assert summary["auto_added"] == 1
        refresh_mock.assert_awaited_once_with("f1")
        # 规则 ORM 传入（bound 包含 f1）
        rule_arg = apply_mock.await_args_list[0].args[0]
        assert rule_arg.rule_id == "r1"

    async def test_skips_offline_and_qb_native_and_interval(self, db_session):
        _make_feed(db_session, "f-off", downloader_id="dl-off")  # 离线（不在快照）
        _make_feed(db_session, "f-mode", downloader_id="dl-qb-2")  # qb_native 冻结
        db_session.add(RssMode(downloader_id="dl-qb-2", mode="qb_native"))
        # 间隔未到期：refresh_interval=60，20 分钟前抓取过
        _make_feed(
            db_session,
            "f-itv",
            downloader_id="dl-qb-1",
            refresh_interval_minutes=60,
            last_fetch_at=datetime.utcnow() - timedelta(minutes=20),
            last_fetch_status="ok",
        )
        store = _fake_store(online=("dl-qb-1", "dl-qb-2"))
        refresh_mock = AsyncMock()
        with (
            patch("app.tasks.scheduler.rss_refresh_task.SessionLocal", return_value=db_session),
            patch.object(RssFeedService, "refresh_feed", refresh_mock),
        ):
            summary = await _run(RssRefreshTask(), store)

        assert summary["skipped_offline"] == 1
        assert summary["skipped_mode"] == 1
        assert summary["skipped_interval"] == 1
        assert summary["refreshed"] == 0
        refresh_mock.assert_not_awaited()

    async def test_disabled_feed_ignored_and_failure_bounded(self, db_session):
        _make_feed(db_session, "f-dis", enabled=0)
        _make_feed(db_session, "f-ok")
        _make_feed(db_session, "f-bad")
        store = _fake_store()
        results = {
            "f-ok": MagicMock(ok=True, data={"newCount": 1}),
            "f-bad": MagicMock(ok=False, msg="抓取失败"),
        }

        async def refresh_side_effect(feed_id):
            return results[feed_id]

        with (
            patch("app.tasks.scheduler.rss_refresh_task.SessionLocal", return_value=db_session),
            patch.object(
                RssFeedService,
                "refresh_feed",
                AsyncMock(side_effect=refresh_side_effect),
            ),
        ):
            summary = await _run(RssRefreshTask(), store)

        assert summary["status"] == "partial"
        assert summary["refreshed"] == 1
        assert summary["errors"] == [{"feed": "源f-bad", "message": "抓取失败"}]

    async def test_rule_scoping_skips_unbound(self, db_session):
        _make_feed(db_session, "f1")
        _make_feed(db_session, "f2")
        _make_rule(db_session, "r1", feed_ids=["f1"])  # 只绑 f1
        db_session.add(RssArticle(feed_id="f1", guid="g1", title="t", link="magnet:?x"))
        db_session.add(RssArticle(feed_id="f2", guid="g2", title="t", link="magnet:?x"))
        db_session.commit()
        store = _fake_store()

        async def refresh_side_effect(feed_id):
            return MagicMock(ok=True, data={"newCount": 0})

        apply_mock = AsyncMock(return_value={"matched": 0, "pushed": 0, "failed": 0, "skipped_mode": 0})
        with (
            patch("app.tasks.scheduler.rss_refresh_task.SessionLocal", return_value=db_session),
            patch.object(
                RssFeedService,
                "refresh_feed",
                AsyncMock(side_effect=refresh_side_effect),
            ),
            patch.object(RssRuleService, "apply_rule_to_pending", apply_mock),
        ):
            summary = await _run(RssRefreshTask(), store)

        # 只有 f1 刷新后执行了规则（f2 不在规则作用域）
        apply_mock.assert_awaited_once()
        assert summary["auto_added"] == 0

    async def test_no_pending_short_circuits_rules(self, db_session):
        _make_feed(db_session, "f1")
        _make_rule(db_session, "r1")  # 空关联=全部源，但无 pending 文章
        store = _fake_store()
        apply_mock = AsyncMock()
        with (
            patch("app.tasks.scheduler.rss_refresh_task.SessionLocal", return_value=db_session),
            patch.object(
                RssFeedService,
                "refresh_feed",
                AsyncMock(return_value=MagicMock(ok=True, data={"newCount": 0})),
            ),
            patch.object(RssRuleService, "apply_rule_to_pending", apply_mock),
        ):
            summary = await _run(RssRefreshTask(), store)
        apply_mock.assert_not_awaited()
        assert summary["status"] == "success"

    async def test_android_server_skips(self):
        task = RssRefreshTask()
        task.set_app(_make_app(_fake_store()))
        with patch("app.core.platform_capabilities.is_android_server", return_value=True):
            summary = await task.execute()
        assert summary["status"] == "skipped"

    async def test_missing_store_skips(self):
        task = RssRefreshTask()
        summary = await task.execute()
        assert summary["status"] == "skipped"
