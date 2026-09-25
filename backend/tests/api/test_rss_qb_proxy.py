# -*- coding: utf-8 -*-
"""qB 原生 RSS 代理回归（feature rss-subscription-phase2-2026-09-24）。

覆盖：
- 源树投影（folder/feed 判定、未读数、空节点按 folder 的 qB API 限制）；
- 源/文件夹 CRUD 透传（add_feed/add_folder/set_feed_url/remove_item/move_item
  的 kwargs 断言与路径/URL 校验）；
- 刷新（单项/全部）、已读（单篇/整源）；
- 文章列表（路径游走投影、按 published 排序、onlyUnread、路径不存在、
  folder 路径空列表）；
- 规则（列表投影、set 轻校验、rename/remove/matching 投影）；
- 偏好白名单（GET 只投影四键、PUT 数值边界、空更新拒绝、只透传白名单键）；
- 门控（TR 类型拒绝、离线、未知下载器、android-server 拒写、认证 401）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth import utils as auth_utils
from app.auth.models import User
from app.database import Base, get_db

TEST_LOGIN_SECRET = "test-login-secret-for-rss-qb-proxy"

_QB_ITEMS = {
    "剧集": {
        "FeedA": {
            "a1": {
                "title": "Episode 01",
                "torrentURL": "https://example.com/ep1.torrent",
                "published": "2026-09-20 10:00:00",
                "isRead": False,
            },
            "a2": {
                "title": "Episode 02",
                "link": "magnet:?xt=urn:btih:aaa2",
                "published": "2026-09-21 10:00:00",
                "isRead": True,
            },
        },
        "空文件夹": {},
    },
    "TopFeed": {
        "t1": {
            "title": "Top Item",
            "magnetURI": "magnet:?xt=urn:btih:ttt1",
            "published": "2026-09-19 10:00:00",
            "isRead": False,
        }
    },
}

_QB_PREFS = {
    "locale": "zh_CN",
    "rss_processing_enabled": True,
    "rss_auto_downloading_enabled": False,
    "rss_refresh_interval": 60,
    "rss_max_articles_per_feed": 50,
    "web_ui_address": "*",
}

_QB_RULES = {
    "剧集规则": {
        "enabled": True,
        "mustContain": "Episode",
        "mustNotContain": "Repack",
        "affectedFeeds": ["剧集\\FeedA"],
        "savePath": "/tv",
        "assignedCategory": "tv",
        "addPaused": False,
    }
}

_QB_MATCHING = {
    "剧集\\FeedA": {
        "a1": {
            "title": "Episode 01",
            "torrentURL": "https://example.com/ep1.torrent",
            "published": "2026-09-20 10:00:00",
            "isRead": False,
        }
    }
}


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
    Base.metadata.create_all(bind=engine, tables=[User.__table__])
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=[User.__table__])
    engine.dispose()


def _make_qb_client() -> MagicMock:
    client = MagicMock()
    client.rss_items.return_value = _QB_ITEMS
    client.rss_rules.return_value = _QB_RULES
    client.rss_matching_articles.return_value = _QB_MATCHING
    client.app_preferences.return_value = _QB_PREFS
    client.rss_add_feed.return_value = None
    client.rss_add_folder.return_value = None
    client.rss_set_feed_url.return_value = None
    client.rss_remove_item.return_value = None
    client.rss_move_item.return_value = None
    client.rss_refresh_item.return_value = None
    client.rss_mark_as_read.return_value = None
    client.rss_set_rule.return_value = None
    client.rss_rename_rule.return_value = None
    client.rss_remove_rule.return_value = None
    client.app_set_preferences.return_value = None
    return client


@pytest.fixture
def fake_store():
    qb_client = _make_qb_client()
    store = MagicMock()
    store.get_snapshot = AsyncMock(
        return_value=[
            SimpleNamespace(downloader_id="dl-qb-1", fail_time=0, client=qb_client, downloader_type=0, nickname="qB"),
            SimpleNamespace(downloader_id="dl-tr-1", fail_time=0, client=MagicMock(), downloader_type=1, nickname="TR"),
            SimpleNamespace(
                downloader_id="dl-off-1", fail_time=1700000000, client=qb_client, downloader_type=0, nickname="离线"
            ),
        ]
    )
    store.qb_client = qb_client
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


def _make_user(db_session) -> User:
    user = User(username="admin", password="not-a-real-hash", is_active=True, must_change_password=False)
    db_session.add(user)
    db_session.commit()
    return user


def _auth() -> dict:
    token = auth_utils.create_access_token({"sub": "admin", "user_id": "1", "verify_secret": TEST_LOGIN_SECRET})
    return {"Authorization": f"Bearer {token}"}


def _reason(resp) -> str:
    return resp.json()["data"]["reasonCode"]


# ==============================================================================
# 源树与文章
# ==============================================================================


class TestFeedsAndArticles:
    def test_list_feeds_tree(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-qb-1/feeds", headers=_auth())
        assert resp.status_code == 200, resp.text
        tree = resp.json()["data"]["list"]
        folder = next(n for n in tree if n["name"] == "剧集")
        assert folder["type"] == "folder"
        feed_a = next(c for c in folder["children"] if c["name"] == "FeedA")
        assert feed_a["type"] == "feed"
        assert feed_a["path"] == "剧集\\FeedA"
        assert feed_a["articleCount"] == 2
        assert feed_a["unreadCount"] == 1
        empty = next(c for c in folder["children"] if c["name"] == "空文件夹")
        assert empty["type"] == "folder" and empty["children"] == []
        top = next(n for n in tree if n["name"] == "TopFeed")
        assert top["type"] == "feed" and top["unreadCount"] == 1

    def test_articles_sorted_and_filtered(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-qb-1/articles", params={"path": "剧集\\FeedA"}, headers=_auth())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2 and data["unreadCount"] == 1
        titles = [a["title"] for a in data["list"]]
        assert titles == ["Episode 02", "Episode 01"]  # published 倒序
        assert data["list"][1]["link"] == "https://example.com/ep1.torrent"  # torrentURL 优先

        resp = client.get(
            "/api/v1/rss/qb/dl-qb-1/articles",
            params={"path": "剧集\\FeedA", "onlyUnread": True},
            headers=_auth(),
        )
        assert [a["title"] for a in resp.json()["data"]["list"]] == ["Episode 01"]

    def test_articles_path_not_found_and_folder(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-qb-1/articles", params={"path": "不存在\\Feed"}, headers=_auth())
        assert _reason(resp) == "RSS_QB_FEED_NOT_FOUND"
        # folder 路径（含空节点）→ 空列表
        resp = client.get("/api/v1/rss/qb/dl-qb-1/articles", params={"path": "剧集\\空文件夹"}, headers=_auth())
        assert resp.json()["data"]["list"] == []

    def test_add_feed_validation_and_passthrough(self, client, db_session, fake_store):
        _make_user(db_session)
        assert (
            _reason(
                client.post(
                    "/api/v1/rss/qb/dl-qb-1/feeds", json={"path": " ", "url": "https://x/f.xml"}, headers=_auth()
                )
            )
            == "RSS_QB_FEED_PATH_INVALID"
        )
        assert (
            _reason(
                client.post("/api/v1/rss/qb/dl-qb-1/feeds", json={"path": "F\\X", "url": "ftp://x"}, headers=_auth())
            )
            == "RSS_QB_FEED_URL_INVALID"
        )
        resp = client.post(
            "/api/v1/rss/qb/dl-qb-1/feeds",
            json={"path": "剧集\\NewFeed", "url": "https://example.com/new.xml"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        fake_store.qb_client.rss_add_feed.assert_called_once_with(
            url="https://example.com/new.xml", item_path="剧集\\NewFeed"
        )

    def test_folder_url_remove_move_passthrough(self, client, db_session, fake_store):
        _make_user(db_session)
        qb = fake_store.qb_client
        resp = client.post("/api/v1/rss/qb/dl-qb-1/folders", json={"path": "新文件夹"}, headers=_auth())
        assert resp.status_code == 200
        qb.rss_add_folder.assert_called_once_with(folder_path="新文件夹")

        resp = client.put(
            "/api/v1/rss/qb/dl-qb-1/feeds/url",
            params={"path": "剧集\\FeedA"},
            json={"url": "https://example.com/v2.xml"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        qb.rss_set_feed_url.assert_called_once_with(url="https://example.com/v2.xml", item_path="剧集\\FeedA")

        resp = client.delete("/api/v1/rss/qb/dl-qb-1/items", params={"path": "TopFeed"}, headers=_auth())
        assert resp.status_code == 200
        qb.rss_remove_item.assert_called_once_with(origin_path="TopFeed")

        resp = client.post(
            "/api/v1/rss/qb/dl-qb-1/items/move",
            json={"originPath": "TopFeed", "destPath": "剧集\\TopFeed"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        qb.rss_move_item.assert_called_once_with(origin_path="TopFeed", dest_path="剧集\\TopFeed")

    def test_refresh_item_and_all(self, client, db_session, fake_store):
        _make_user(db_session)
        qb = fake_store.qb_client
        resp = client.post("/api/v1/rss/qb/dl-qb-1/items/refresh", json={"path": "剧集\\FeedA"}, headers=_auth())
        assert resp.status_code == 200
        qb.rss_refresh_item.assert_called_with(item_path="剧集\\FeedA")
        resp = client.post("/api/v1/rss/qb/dl-qb-1/items/refresh", json={}, headers=_auth())
        assert resp.status_code == 200
        qb.rss_refresh_item.assert_called_with(item_path=None)

    def test_mark_read_article(self, client, db_session, fake_store):
        _make_user(db_session)
        resp = client.post(
            "/api/v1/rss/qb/dl-qb-1/items/mark-read",
            json={"path": "剧集\\FeedA", "articleId": "a1"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        fake_store.qb_client.rss_mark_as_read.assert_called_once_with(item_path="剧集\\FeedA", article_id="a1")
        client.post("/api/v1/rss/qb/dl-qb-1/items/mark-read", json={"path": "TopFeed"}, headers=_auth())
        fake_store.qb_client.rss_mark_as_read.assert_called_with(item_path="TopFeed", article_id=None)


# ==============================================================================
# 规则
# ==============================================================================


class TestQbRules:
    def test_list_rules_projection(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-qb-1/rules", headers=_auth())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        rule = data["list"][0]
        assert rule["name"] == "剧集规则"
        assert rule["mustContain"] == "Episode"
        assert rule["affectedFeeds"] == ["剧集\\FeedA"]

    def test_set_rule_validation_and_passthrough(self, client, db_session, fake_store):
        _make_user(db_session)
        rule_def = {
            "enabled": True,
            "mustContain": "Ubuntu",
            "affectedFeeds": ["TopFeed"],
            "savePath": "/linux",
        }
        assert (
            _reason(
                client.post("/api/v1/rss/qb/dl-qb-1/rules", json={"name": " ", "ruleDef": rule_def}, headers=_auth())
            )
            == "RSS_QB_RULE_NAME_INVALID"
        )
        bad_def = dict(rule_def, enabled="yes")
        assert (
            _reason(
                client.post("/api/v1/rss/qb/dl-qb-1/rules", json={"name": "r", "ruleDef": bad_def}, headers=_auth())
            )
            == "RSS_QB_RULE_DEF_INVALID"
        )
        resp = client.post(
            "/api/v1/rss/qb/dl-qb-1/rules", json={"name": "Linux 规则", "ruleDef": rule_def}, headers=_auth()
        )
        assert resp.status_code == 200
        fake_store.qb_client.rss_set_rule.assert_called_once_with(rule_name="Linux 规则", rule_def=rule_def)

    def test_rename_and_delete(self, client, db_session, fake_store):
        _make_user(db_session)
        qb = fake_store.qb_client
        resp = client.put(
            "/api/v1/rss/qb/dl-qb-1/rules/rename",
            params={"name": "剧集规则"},
            json={"newName": "剧集规则2"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        qb.rss_rename_rule.assert_called_once_with(orig_rule_name="剧集规则", new_rule_name="剧集规则2")
        resp = client.delete("/api/v1/rss/qb/dl-qb-1/rules", params={"name": "剧集规则2"}, headers=_auth())
        assert resp.status_code == 200
        qb.rss_remove_rule.assert_called_once_with(rule_name="剧集规则2")

    def test_matching_articles_projection(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-qb-1/rules/matching", params={"name": "剧集规则"}, headers=_auth())
        assert resp.status_code == 200
        feeds = resp.json()["data"]["feeds"]
        assert len(feeds) == 1
        assert feeds[0]["feedPath"] == "剧集\\FeedA"
        assert feeds[0]["articles"][0]["title"] == "Episode 01"


# ==============================================================================
# 偏好白名单
# ==============================================================================


class TestQbPreferences:
    def test_get_projects_whitelist_only(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-qb-1/preferences", headers=_auth())
        assert resp.status_code == 200
        prefs = resp.json()["data"]["preferences"]
        assert prefs == {
            "rssProcessingEnabled": True,
            "rssAutoDownloadingEnabled": False,
            "rssRefreshInterval": 60,
            "rssMaxArticlesPerFeed": 50,
        }
        assert "web_ui_address" not in str(prefs) or "web_ui_address" not in prefs

    def test_update_valid_passthrough_and_reread(self, client, db_session, fake_store):
        _make_user(db_session)
        resp = client.put(
            "/api/v1/rss/qb/dl-qb-1/preferences",
            json={"rssRefreshInterval": 30, "rssAutoDownloadingEnabled": True},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        fake_store.qb_client.app_set_preferences.assert_called_once_with(
            prefs={"rss_refresh_interval": 30, "rss_auto_downloading_enabled": True}
        )
        # 响应为回读投影（mock 原值）
        prefs = resp.json()["data"]["preferences"]
        assert prefs["rssRefreshInterval"] == 60

    def test_update_value_bounds_and_empty(self, client, db_session):
        _make_user(db_session)
        assert (
            _reason(client.put("/api/v1/rss/qb/dl-qb-1/preferences", json={"rssRefreshInterval": 0}, headers=_auth()))
            == "RSS_QB_PREF_VALUE_INVALID"
        )
        assert (
            _reason(
                client.put("/api/v1/rss/qb/dl-qb-1/preferences", json={"rssMaxArticlesPerFeed": 99999}, headers=_auth())
            )
            == "RSS_QB_PREF_VALUE_INVALID"
        )
        assert (
            _reason(client.put("/api/v1/rss/qb/dl-qb-1/preferences", json={}, headers=_auth()))
            == "RSS_QB_PREF_KEY_REJECTED"
        )


# ==============================================================================
# 门控
# ==============================================================================


class TestQbProxyGates:
    def test_tr_type_rejected(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-tr-1/feeds", headers=_auth())
        assert _reason(resp) == "RSS_QB_TYPE_UNSUPPORTED"

    def test_offline_rejected(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-off-1/feeds", headers=_auth())
        assert _reason(resp) == "RSS_DOWNLOADER_OFFLINE"

    def test_unknown_downloader(self, client, db_session):
        _make_user(db_session)
        resp = client.get("/api/v1/rss/qb/dl-none/feeds", headers=_auth())
        assert _reason(resp) == "RSS_DOWNLOADER_NOT_FOUND"

    def test_android_server_rejects_writes_only(self, client, db_session):
        _make_user(db_session)
        with patch("app.api.endpoints.rss_qb_proxy.resolve_platform", return_value="android-server"):
            resp = client.post(
                "/api/v1/rss/qb/dl-qb-1/feeds", json={"path": "F", "url": "https://x/f.xml"}, headers=_auth()
            )
            assert _reason(resp) == "RSS_PLATFORM_UNSUPPORTED"
            # GET 不拦
            resp = client.get("/api/v1/rss/qb/dl-qb-1/feeds", headers=_auth())
            assert resp.status_code == 200

    def test_requires_auth(self, client, db_session):
        resp = client.get("/api/v1/rss/qb/dl-qb-1/feeds")
        assert resp.status_code == 401

    def test_client_call_failure_maps_to_proxy_failed(self, client, db_session, fake_store):
        _make_user(db_session)
        fake_store.qb_client.rss_items.side_effect = RuntimeError("boom")
        resp = client.get("/api/v1/rss/qb/dl-qb-1/feeds", headers=_auth())
        assert _reason(resp) == "RSS_QB_PROXY_FAILED"
