# -*- coding: utf-8 -*-
"""RSS Phase 2：模式切换 + 自动下载规则 + 匹配回填 + 护栏（feature rss-subscription-phase2-2026-09-24）。

覆盖：
- 模式：默认 btdeck、qB 切 qb_native/btdeck 往返、TR 拒绝、非法值拒绝、
  能力键关闭拒绝、qbNativeAvailable 投影；
- 规则 CRUD：创建/列表/部分更新（显式 null 语义）/删除/404/校验
  （关键词空、非法正则、重名 409、跨下载器源、目标类型不支持）；
- 匹配引擎：include OR / exclude AND NOT / 大小写不敏感 / 正则 /
  源作用域（空关联=全部源，指定关联只作用所选源）；
- 回填：创建即推送命中 pending（qB 参数、addedRuleId 事实）、
  目标 qb_native 跳过（skipped_mode）、预览不推送；
- 护栏：手动推送到 qb_native 下载器 409 RSS_MODE_CONFLICT；
- 平台门控（android-server 拒写）与认证保护。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth import utils as auth_utils
from app.auth.models import User
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.models.downloader_capabilities import DownloaderCapabilities
from app.models.rss_subscription import RssArticle, RssFeed, RssMode, RssRule, RssRuleFeed

_TEST_TABLES = [
    User.__table__,
    BtDownloaders.__table__,
    DownloaderCapabilities.__table__,
    RssFeed.__table__,
    RssArticle.__table__,
    RssMode.__table__,
    RssRule.__table__,
    RssRuleFeed.__table__,
]

TEST_LOGIN_SECRET = "test-login-secret-for-rss-phase2"


# ==============================================================================
# fixtures
# ==============================================================================


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=_TEST_TABLES)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=_TEST_TABLES)
    engine.dispose()


@pytest.fixture
def fake_store():
    """app.state.store 替身：缓存快照返回受控下载器 VO（推送链路用）。"""
    qb_client = MagicMock()
    qb_client.torrents_add.return_value = "Ok."
    tr_client = MagicMock()
    tr_client.add_torrent.return_value = None
    store = MagicMock()
    store.get_snapshot = AsyncMock(
        return_value=[
            SimpleNamespace(
                downloader_id="dl-qb-1", fail_time=0, client=qb_client, downloader_type=0, nickname="qB 测试"
            ),
            SimpleNamespace(
                downloader_id="dl-tr-1", fail_time=0, client=tr_client, downloader_type=1, nickname="TR 测试"
            ),
            SimpleNamespace(
                downloader_id="dl-rt-1", fail_time=0, client=MagicMock(), downloader_type=2, nickname="rT 测试"
            ),
        ]
    )
    return store


@pytest.fixture
def client(db_session, fake_store):
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.state.store = fake_store

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    mock_settings = MagicMock()
    mock_settings.SECRET_KEY = "test-secret"
    mock_settings.ALGORITHM = "HS256"
    mock_settings.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    with (
        patch("app.auth.utils.settings", mock_settings),
        patch("app.auth.utils.get_login_secret", return_value=TEST_LOGIN_SECRET),
    ):
        yield TestClient(app, raise_server_exceptions=False)


def _make_user(db_session: Session, username: str = "admin") -> User:
    user = User(username=username, password="not-a-real-hash", is_active=True, must_change_password=False)
    db_session.add(user)
    db_session.commit()
    return user


def _auth(username: str = "admin", user_id: int = 1) -> dict:
    token = auth_utils.create_access_token(
        {"sub": username, "user_id": str(user_id), "verify_secret": TEST_LOGIN_SECRET}
    )
    return {"Authorization": f"Bearer {token}"}


def _make_downloader(db_session: Session, downloader_id: str, downloader_type: int = 0) -> BtDownloaders:
    row = BtDownloaders(
        downloader_id=downloader_id,
        nickname=downloader_id,
        host="127.0.0.1",
        port="8080",
        downloader_type=downloader_type,
        enabled=True,
        is_search=True,
        dr=0,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _make_capabilities(db_session: Session, downloader_id: str, rss_management: bool) -> None:
    import json

    row = DownloaderCapabilities(
        downloader_id=downloader_id,
        extended_capabilities=json.dumps({"rss_management": rss_management}),
    )
    db_session.add(row)
    db_session.commit()


def _make_feed(db_session: Session, downloader_id: str = "dl-qb-1", name: str = "测试源") -> RssFeed:
    feed = RssFeed(downloader_id=downloader_id, name=name, url=f"https://example.com/{name}.xml")
    db_session.add(feed)
    db_session.commit()
    return feed


def _seed_article(db_session: Session, feed_id: str, guid: str, title: str) -> RssArticle:
    article = RssArticle(
        feed_id=feed_id,
        guid=guid,
        title=title,
        link=f"magnet:?xt=urn:btih:{guid}",
    )
    db_session.add(article)
    db_session.commit()
    return article


def _create_rule(client: TestClient, downloader_id: str = "dl-qb-1", **overrides) -> dict:
    payload = {
        "downloaderId": downloader_id,
        "name": "测试规则",
        "includeKeywords": "ubuntu",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/rss/rules", json=payload, headers=_auth())
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ==============================================================================
# 模式
# ==============================================================================


class TestRssMode:
    def test_mode_defaults_btdeck(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        resp = client.get("/api/v1/rss/mode", params={"downloaderId": "dl-qb-1"}, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["mode"] == "btdeck"
        assert data["qbNativeAvailable"] is True  # 缺能力行回退按类型（qB=True）

    def test_mode_switch_roundtrip(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-qb-1", "mode": "qb_native"}, headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["mode"] == "qb_native"

        resp = client.get("/api/v1/rss/mode", params={"downloaderId": "dl-qb-1"}, headers=_auth())
        assert resp.json()["data"]["mode"] == "qb_native"

        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-qb-1", "mode": "btdeck"}, headers=_auth())
        assert resp.status_code == 200
        resp = client.get("/api/v1/rss/mode", params={"downloaderId": "dl-qb-1"}, headers=_auth())
        assert resp.json()["data"]["mode"] == "btdeck"

    def test_mode_qb_native_rejected_for_tr(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-tr-1", 1)
        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-tr-1", "mode": "qb_native"}, headers=_auth())
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert body["data"]["reasonCode"] == "RSS_MODE_TYPE_UNSUPPORTED"

    def test_mode_invalid_value_rejected(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-qb-1", "mode": "native"}, headers=_auth())
        body = resp.json()
        assert body["data"]["reasonCode"] == "RSS_MODE_INVALID"

    def test_mode_capability_disabled(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        _make_capabilities(db_session, "dl-qb-1", rss_management=False)
        resp = client.get("/api/v1/rss/mode", params={"downloaderId": "dl-qb-1"}, headers=_auth())
        assert resp.json()["data"]["qbNativeAvailable"] is False
        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-qb-1", "mode": "qb_native"}, headers=_auth())
        body = resp.json()
        assert body["data"]["reasonCode"] == "RSS_MODE_CAPABILITY_DISABLED"

    def test_mode_unknown_downloader(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/mode", params={"downloaderId": "dl-none"}, headers=_auth())
        body = resp.json()
        assert body["data"]["reasonCode"] == "RSS_DOWNLOADER_NOT_FOUND"

    def test_mode_switch_requires_auth(self, client, db_session):
        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-qb-1", "mode": "qb_native"})
        assert resp.status_code == 401


# ==============================================================================
# 规则 CRUD
# ==============================================================================


class TestRuleCrud:
    def test_create_and_list(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        data = _create_rule(client, includeKeywords="ubuntu,debian", excludeKeywords="beta")
        rule = data["rule"]
        assert rule["includeKeywords"] == "ubuntu,debian"
        assert rule["excludeKeywords"] == "beta"
        assert rule["useRegex"] is False
        assert rule["targetDownloaderId"] is None
        assert rule["feedIds"] == []
        assert data["backfill"] == {"matched": 0, "pushed": 0, "failed": 0, "skippedMode": 0}

        resp = client.get("/api/v1/rss/rules", params={"downloaderId": "dl-qb-1"}, headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1
        assert resp.json()["data"]["list"][0]["ruleId"] == rule["ruleId"]

    def test_create_validations(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        _make_downloader(db_session, "dl-rt-1", 2)
        feed_other = _make_feed(db_session, downloader_id="dl-tr-1", name="TR 源")

        def reason_of(payload):
            resp = client.post("/api/v1/rss/rules", json=payload, headers=_auth())
            return resp.json()["data"]["reasonCode"]

        base = {"downloaderId": "dl-qb-1", "name": "规则A", "includeKeywords": "ubuntu"}
        assert reason_of({**base, "includeKeywords": " , "}) == "RSS_RULE_KEYWORDS_INVALID"
        assert reason_of({**base, "includeKeywords": "(unclosed", "useRegex": True}) == "RSS_RULE_REGEX_INVALID"
        assert reason_of({**base, "targetDownloaderId": "dl-rt-1"}) == "RSS_RULE_TARGET_INVALID"
        assert reason_of({**base, "targetDownloaderId": "dl-none"}) == "RSS_RULE_TARGET_INVALID"
        assert reason_of({**base, "feedIds": [feed_other.feed_id]}) == "RSS_RULE_FEED_INVALID"
        assert reason_of({**base, "feedIds": ["feed-none"]}) == "RSS_RULE_FEED_INVALID"

        # 重名 409
        _create_rule(client, name="规则A")
        assert reason_of({**base}) == "RSS_RULE_DUPLICATE"

    def test_update_partial_and_null_semantics(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        rule = _create_rule(client, name="原规则", includeKeywords="ubuntu", excludeKeywords="beta")["rule"]

        # 未传 exclude → 保持
        resp = client.put(f"/api/v1/rss/rules/{rule['ruleId']}", json={"name": "新规则"}, headers=_auth())
        assert resp.status_code == 200
        updated = resp.json()["data"]["rule"]
        assert updated["name"] == "新规则"
        assert updated["excludeKeywords"] == "beta"

        # 显式 null exclude → 清除
        resp = client.put(f"/api/v1/rss/rules/{rule['ruleId']}", json={"excludeKeywords": None}, headers=_auth())
        updated = resp.json()["data"]["rule"]
        assert updated["excludeKeywords"] is None

        # 显式空 feedIds = 全部源语义（关联清空）
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        resp = client.put(f"/api/v1/rss/rules/{rule['ruleId']}", json={"feedIds": [feed.feed_id]}, headers=_auth())
        assert resp.json()["data"]["rule"]["feedIds"] == [feed.feed_id]
        resp = client.put(f"/api/v1/rss/rules/{rule['ruleId']}", json={"feedIds": []}, headers=_auth())
        assert resp.json()["data"]["rule"]["feedIds"] == []

    def test_update_not_found(self, client, db_session):
        _make_user(db_session)
        resp = client.put("/api/v1/rss/rules/rule-none", json={"name": "x"}, headers=_auth())
        body = resp.json()
        assert body["data"]["reasonCode"] == "RSS_RULE_NOT_FOUND"

    def test_delete(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        rule = _create_rule(client)["rule"]
        resp = client.delete(f"/api/v1/rss/rules/{rule['ruleId']}", headers=_auth())
        assert resp.status_code == 200
        resp = client.get("/api/v1/rss/rules", params={"downloaderId": "dl-qb-1"}, headers=_auth())
        assert resp.json()["data"]["total"] == 0
        resp = client.delete(f"/api/v1/rss/rules/{rule['ruleId']}", headers=_auth())
        assert resp.json()["data"]["reasonCode"] == "RSS_RULE_NOT_FOUND"

    def test_android_server_rejects_writes(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        with patch("app.api.endpoints.rss_subscriptions.resolve_platform", return_value="android-server"):
            resp = client.post(
                "/api/v1/rss/rules",
                json={"downloaderId": "dl-qb-1", "name": "r", "includeKeywords": "x"},
                headers=_auth(),
            )
            assert resp.json()["data"]["reasonCode"] == "RSS_PLATFORM_UNSUPPORTED"


# ==============================================================================
# 匹配引擎与回填
# ==============================================================================


class TestMatchingAndBackfill:
    def test_backfill_pushes_matching_pending(self, client, db_session, fake_store):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        hit = _seed_article(db_session, feed.feed_id, "1111", "Ubuntu 24.04 LTS ISO")
        miss = _seed_article(db_session, feed.feed_id, "2222", "Debian 13 netinst")

        data = _create_rule(client, includeKeywords="ubuntu,LTS", excludeKeywords="server")
        backfill = data["backfill"]
        assert backfill["matched"] == 1 and backfill["pushed"] == 1

        db_session.expire_all()
        hit_row = db_session.query(RssArticle).filter(RssArticle.article_id == hit.article_id).first()
        miss_row = db_session.query(RssArticle).filter(RssArticle.article_id == miss.article_id).first()
        assert hit_row.status == "added"
        assert hit_row.added_rule_id == data["rule"]["ruleId"]
        assert hit_row.added_downloader_id == "dl-qb-1"
        assert miss_row.status == "pending"
        # 推送走 qB torrents_add(urls=...) 链路
        fake_store.get_snapshot.return_value[0].client.torrents_add.assert_called()

    def test_backfill_case_insensitive_and_exclude(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        _seed_article(db_session, feed.feed_id, "a1", "UBUNTU Desktop")
        _seed_article(db_session, feed.feed_id, "a2", "Ubuntu Server")

        # 大小写不敏感命中 + exclude 拦截
        data = _create_rule(client, includeKeywords="ubuntu", excludeKeywords="server")
        assert data["backfill"]["matched"] == 1
        db_session.expire_all()
        statuses = {a.title: a.status for a in db_session.query(RssArticle).all()}
        assert statuses["UBUNTU Desktop"] == "added"
        assert statuses["Ubuntu Server"] == "pending"

    def test_regex_rule(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        _seed_article(db_session, feed.feed_id, "r1", "Show S02E05 1080p")
        _seed_article(db_session, feed.feed_id, "r2", "Show Special")

        data = _create_rule(client, includeKeywords=r"S\d\dE\d\d", useRegex=True)
        assert data["backfill"]["matched"] == 1
        db_session.expire_all()
        statuses = {a.title: a.status for a in db_session.query(RssArticle).all()}
        assert statuses["Show S02E05 1080p"] == "added"
        assert statuses["Show Special"] == "pending"

    def test_rule_scoping_bound_feeds_only(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        feed_a = _make_feed(db_session, downloader_id="dl-qb-1", name="源A")
        feed_b = _make_feed(db_session, downloader_id="dl-qb-1", name="源B")
        _seed_article(db_session, feed_a.feed_id, "fa1", "Ubuntu From A")
        _seed_article(db_session, feed_b.feed_id, "fb1", "Ubuntu From B")

        data = _create_rule(client, includeKeywords="ubuntu", feedIds=[feed_a.feed_id])
        assert data["backfill"]["matched"] == 1
        db_session.expire_all()
        statuses = {a.title: a.status for a in db_session.query(RssArticle).all()}
        assert statuses["Ubuntu From A"] == "added"
        assert statuses["Ubuntu From B"] == "pending"

    def test_backfill_skips_when_target_qb_native(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        _seed_article(db_session, feed.feed_id, "q1", "Ubuntu Target")

        # 切 qb_native 后建规则：命中但跳过推送
        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-qb-1", "mode": "qb_native"}, headers=_auth())
        assert resp.status_code == 200
        data = _create_rule(client, includeKeywords="ubuntu")
        assert data["backfill"]["matched"] == 1
        assert data["backfill"]["skippedMode"] == 1
        assert data["backfill"]["pushed"] == 0
        db_session.expire_all()
        assert db_session.query(RssArticle).first().status == "pending"

    def test_manual_push_blocked_when_qb_native(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        _make_downloader(db_session, "dl-tr-1", 1)
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        article = _seed_article(db_session, feed.feed_id, "m1", "Ubuntu Manual")

        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-tr-1", "mode": "qb_native"}, headers=_auth())
        assert resp.status_code == 200
        # TR 不允许 qb_native —— 换回 qB 目标验证
        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-tr-1", "mode": "btdeck"}, headers=_auth())
        assert resp.status_code == 200

        resp = client.put("/api/v1/rss/mode", json={"downloaderId": "dl-qb-1", "mode": "qb_native"}, headers=_auth())
        assert resp.status_code == 200
        resp = client.post(
            f"/api/v1/rss/articles/{article.article_id}/add",
            json={"downloaderId": "dl-qb-1"},
            headers=_auth(),
        )
        body = resp.json()
        assert body["data"]["reasonCode"] == "RSS_MODE_CONFLICT"
        db_session.expire_all()
        assert db_session.query(RssArticle).first().status == "pending"

    def test_match_preview_does_not_push(self, client, db_session):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        article = _seed_article(db_session, feed.feed_id, "p1", "Ubuntu Preview")

        data = _create_rule(client, includeKeywords="nothing-matches")
        rule_id = data["rule"]["ruleId"]
        # 更新规则改关键词后预览：命中但不推送
        resp = client.put(f"/api/v1/rss/rules/{rule_id}", json={"includeKeywords": "preview"}, headers=_auth())
        assert resp.json()["data"]["backfill"]["matched"] == 1

        # 直接预览（再种一篇 pending）
        _seed_article(db_session, feed.feed_id, "p2", "Ubuntu Preview 2")
        resp = client.post(f"/api/v1/rss/rules/{rule_id}/match-preview", headers=_auth())
        assert resp.status_code == 200
        preview = resp.json()["data"]
        assert preview["total"] >= 1
        assert all(item["feedName"] == "测试源" for item in preview["list"])
        db_session.expire_all()
        pending = [a for a in db_session.query(RssArticle).all() if a.status == "pending"]
        assert len(pending) == 1  # 只有 p2 仍 pending，p1 已被回填推送
        assert pending[0].article_id != article.article_id

    def test_backfill_target_override_pushes_to_tr(self, client, db_session, fake_store):
        _make_user(db_session)
        _make_downloader(db_session, "dl-qb-1", 0)
        _make_downloader(db_session, "dl-tr-1", 1)
        feed = _make_feed(db_session, downloader_id="dl-qb-1")
        _seed_article(db_session, feed.feed_id, "t1", "Ubuntu Cross")

        data = _create_rule(
            client, includeKeywords="ubuntu", targetDownloaderId="dl-tr-1", savePath="/data/tr", tags="rss"
        )
        assert data["backfill"]["pushed"] == 1
        tr_client = fake_store.get_snapshot.return_value[1].client
        tr_client.add_torrent.assert_called_once()
        call_kwargs = tr_client.add_torrent.call_args.kwargs
        assert call_kwargs.get("download_dir") == "/data/tr"
        assert call_kwargs.get("labels") == ["rss"]
        db_session.expire_all()
        row = db_session.query(RssArticle).first()
        assert row.added_downloader_id == "dl-tr-1"
