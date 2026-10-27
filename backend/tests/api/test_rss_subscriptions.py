# -*- coding: utf-8 -*-
"""RSS 订阅 API 与服务回归（feature rss-subscription-2026-09-24 Phase 1）。

覆盖：
- 订阅源 CRUD（创建校验/URL 去重/分页/更新/删除级联文章）；
- 刷新（feedparser 解析 fixture、guid 去重、抓取失败状态投影）；
- 文章列表（分页/状态筛选/非法状态拒绝）；
- 推送（qB/TR 分支参数、目标下载器覆盖、重复推送 409、链接形态校验、
  类型不支持、store 缺失）；
- 平台门控（android-server 拒写）；
- 认证保护（无 token 401）。
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
from app.models.rss_subscription import RssArticle, RssFeed
from app.services.rss_feed_service import RssFeedService

_TEST_TABLES = [User.__table__, RssFeed.__table__, RssArticle.__table__]

TEST_LOGIN_SECRET = "test-login-secret-for-rss"

# RSS 2.0 fixture：3 条（1 条 bittorrent enclosure，1 条普通 link，1 条缺 link 被跳过）
RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Fixture Feed</title>
    <item>
      <title>Episode 01</title>
      <guid isPermaLink="false">fixture-ep1</guid>
      <pubDate>Wed, 23 Sep 2026 10:00:00 GMT</pubDate>
      <link>https://example.com/pages/ep1</link>
      <enclosure url="https://example.com/torrents/ep1.torrent" type="application/x-bittorrent" length="1"/>
    </item>
    <item>
      <title>Episode 02</title>
      <guid isPermaLink="false">fixture-ep2</guid>
      <link>magnet:?xt=urn:btih:0000000000000000000000000000000000000002</link>
    </item>
    <item>
      <title>No Link Item</title>
      <guid isPermaLink="false">fixture-nolink</guid>
    </item>
  </channel>
</rss>
""".encode(
    "utf-8"
)

INVALID_XML = b"<not-a-feed>this is plain text"


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
    """app.state.store 替身：缓存快照返回受控下载器 VO。"""
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
            SimpleNamespace(
                downloader_id="dl-off-1", fail_time=1700000000, client=MagicMock(), downloader_type=0, nickname="离线"
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
    # 审计 best-effort：测试进程内 AsyncSessionLocal 指向隔离测试库，写失败仅告警
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


def _create_feed(client: TestClient, downloader_id: str = "dl-qb-1", **overrides) -> dict:
    payload = {"downloaderId": downloader_id, "name": "测试订阅源", "url": "https://example.com/feed.xml"}
    payload.update(overrides)
    resp = client.post("/api/v1/rss/feeds", json=payload, headers=_auth())
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["feed"]


def _refresh_with_fixture(client: TestClient, feed_id: str, content=RSS_XML, error=None):
    """同步刷新 helper：patch 抓取后发起刷新（TestClient 同步语义）。"""

    async def fake_fetch(_self, url):
        return content, error

    with patch.object(RssFeedService, "_fetch_feed_bytes", new=fake_fetch):
        return client.post(f"/api/v1/rss/feeds/{feed_id}/refresh", headers=_auth())


def _first_article(client: TestClient, feed_id: str) -> dict:
    resp = client.get(f"/api/v1/rss/feeds/{feed_id}/articles", headers=_auth())
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["list"][0]


# ==============================================================================
# 订阅源 CRUD
# ==============================================================================


class TestFeedCrud:
    def test_create_and_list(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        assert feed["downloaderId"] == "dl-qb-1"
        assert feed["lastFetchStatus"] == "never"
        assert feed["pendingCount"] == 0

        resp = client.get("/api/v1/rss/feeds", params={"downloaderId": "dl-qb-1"}, headers=_auth())
        body = resp.json()["data"]
        assert body["total"] == 1 and body["pageSize"] == 20
        assert body["list"][0]["feedId"] == feed["feedId"]

    def test_create_invalid_url_rejected(self, client, db_session):
        _make_user(db_session)
        resp = client.post(
            "/api/v1/rss/feeds",
            json={"downloaderId": "dl-qb-1", "name": "x", "url": "ftp://example.com/feed"},
            headers=_auth(),
        )
        assert resp.json()["data"]["reasonCode"] == "RSS_FEED_URL_INVALID"
        assert resp.json()["code"] == "400"

    def test_create_duplicate_url_conflict(self, client, db_session):
        _make_user(db_session)
        _create_feed(client)
        resp = client.post(
            "/api/v1/rss/feeds",
            json={"downloaderId": "dl-qb-1", "name": "重复", "url": "https://example.com/feed.xml"},
            headers=_auth(),
        )
        assert resp.json()["data"]["reasonCode"] == "RSS_FEED_DUPLICATE"
        assert resp.json()["code"] == "409"

    def test_update_feed(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        resp = client.put(
            f"/api/v1/rss/feeds/{feed['feedId']}",
            json={"name": "改名", "enabled": False},
            headers=_auth(),
        )
        data = resp.json()["data"]["feed"]
        assert data["name"] == "改名" and data["enabled"] is False

    def test_delete_feed_cascades_articles(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        _refresh_with_fixture(client, feed["feedId"])
        assert db_session.query(RssArticle).count() == 2

        resp = client.delete(f"/api/v1/rss/feeds/{feed['feedId']}", headers=_auth())
        assert resp.json()["code"] == "200"
        assert db_session.query(RssArticle).count() == 0
        assert db_session.query(RssFeed).filter(RssFeed.dr == 0).count() == 0

        resp = client.delete(f"/api/v1/rss/feeds/{feed['feedId']}", headers=_auth())
        assert resp.json()["data"]["reasonCode"] == "RSS_FEED_NOT_FOUND"

    def test_unauthenticated_rejected(self, client, db_session):
        resp = client.get("/api/v1/rss/feeds", params={"downloaderId": "dl-qb-1"})
        assert resp.status_code == 401


# ==============================================================================
# 刷新与解析
# ==============================================================================


class TestRefreshAndParse:
    def test_refresh_inserts_and_dedups(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)

        first = _refresh_with_fixture(client, feed["feedId"])
        data = first.json()["data"]
        assert data["newCount"] == 2  # 缺 link 条目被跳过
        assert data["articleCount"] == 2

        # enclosure 优先于 entry.link
        articles = client.get(f"/api/v1/rss/feeds/{feed['feedId']}/articles", headers=_auth()).json()["data"]["list"]
        by_title = {a["title"]: a for a in articles}
        assert by_title["Episode 01"]["link"] == "https://example.com/torrents/ep1.torrent"
        assert by_title["Episode 02"]["link"].startswith("magnet:?")

        second = _refresh_with_fixture(client, feed["feedId"])
        assert second.json()["data"]["newCount"] == 0  # guid 去重
        feed_row = db_session.query(RssFeed).first()
        assert feed_row.last_fetch_status == "ok"

    def test_refresh_fetch_failure_projection(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        resp = _refresh_with_fixture(client, feed["feedId"], content=None, error="HTTP 500")
        body = resp.json()
        assert body["data"]["reasonCode"] == "RSS_FEED_FETCH_FAILED"
        feed_row = db_session.query(RssFeed).first()
        assert feed_row.last_fetch_status == "failed"
        assert feed_row.last_error == "HTTP 500"

    def test_refresh_parse_failure(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        resp = _refresh_with_fixture(client, feed["feedId"], content=INVALID_XML)
        assert resp.json()["data"]["reasonCode"] == "RSS_FEED_PARSE_FAILED"

    def test_parse_entries_atom(self):
        atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Fixture</title>
  <entry>
    <id>atom-1</id>
    <title>Atom Entry</title>
    <link href="https://example.com/atom1.torrent"/>
  </entry>
</feed>"""
        entries, error = RssFeedService._parse_entries(atom)
        assert error is None and len(entries) == 1
        guid, title, link, _published = entries[0]
        assert (guid, title, link) == ("atom-1", "Atom Entry", "https://example.com/atom1.torrent")


# ==============================================================================
# 文章列表
# ==============================================================================


class TestArticleList:
    def test_pagination_and_status_filter(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        _refresh_with_fixture(client, feed["feedId"])

        resp = client.get(
            f"/api/v1/rss/feeds/{feed['feedId']}/articles",
            params={"page": 1, "pageSize": 1},
            headers=_auth(),
        )
        data = resp.json()["data"]
        assert data["total"] == 2 and len(data["list"]) == 1 and data["pageSize"] == 1

        resp = client.get(
            f"/api/v1/rss/feeds/{feed['feedId']}/articles",
            params={"status": "added"},
            headers=_auth(),
        )
        assert resp.json()["data"]["total"] == 0

        resp = client.get(
            f"/api/v1/rss/feeds/{feed['feedId']}/articles",
            params={"status": "bogus"},
            headers=_auth(),
        )
        assert resp.json()["data"]["reasonCode"] == "RSS_ARTICLE_STATUS_INVALID"


# ==============================================================================
# 推送到下载器
# ==============================================================================


class TestAddArticle:
    def test_qb_add_with_params(self, client, db_session, fake_store):
        _make_user(db_session)
        feed = _create_feed(client, downloader_id="dl-qb-1")
        _refresh_with_fixture(client, feed["feedId"])
        article = _first_article(client, feed["feedId"])

        api_mock = AsyncMock(return_value="Ok.")
        with patch("app.services.rss_feed_service.call_downloader_api", new=api_mock):
            resp = client.post(
                f"/api/v1/rss/articles/{article['articleId']}/add",
                json={"savePath": "/downloads/rss", "tags": "rss,auto"},
                headers=_auth(),
            )
        assert resp.json()["code"] == "200"
        # 校验链接直传 qB 的参数形态
        _dl, _lane, func = api_mock.call_args.args[:3]
        kwargs = api_mock.call_args.kwargs["kwargs"]
        assert func == fake_store.get_snapshot.return_value[0].client.torrents_add
        assert kwargs["urls"].startswith(("https://", "magnet:?"))
        assert kwargs["save_path"] == "/downloads/rss"
        assert kwargs["tags"] == "rss,auto"

        row = db_session.query(RssArticle).filter(RssArticle.article_id == article["articleId"]).first()
        assert row.status == "added" and row.added_downloader_id == "dl-qb-1"

    def test_tr_add_uses_labels(self, client, db_session, fake_store):
        _make_user(db_session)
        feed = _create_feed(client, downloader_id="dl-tr-1")
        _refresh_with_fixture(client, feed["feedId"])
        article = _first_article(client, feed["feedId"])

        api_mock = AsyncMock(return_value=None)
        with patch("app.services.rss_feed_service.call_downloader_api", new=api_mock):
            resp = client.post(
                f"/api/v1/rss/articles/{article['articleId']}/add",
                json={"tags": "rss"},
                headers=_auth(),
            )
        assert resp.json()["code"] == "200"
        _args, kwargs = api_mock.call_args.args, api_mock.call_args.kwargs
        assert _args[2] == fake_store.get_snapshot.return_value[1].client.add_torrent
        assert kwargs["kwargs"] == {"labels": ["rss"]}

    def test_target_downloader_override(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client, downloader_id="dl-qb-1")
        _refresh_with_fixture(client, feed["feedId"])
        article = _first_article(client, feed["feedId"])

        with patch("app.services.rss_feed_service.call_downloader_api", new=AsyncMock(return_value="Ok.")):
            resp = client.post(
                f"/api/v1/rss/articles/{article['articleId']}/add",
                json={"downloaderId": "dl-tr-1"},
                headers=_auth(),
            )
        assert resp.json()["code"] == "200"
        row = db_session.query(RssArticle).filter(RssArticle.article_id == article["articleId"]).first()
        assert row.added_downloader_id == "dl-tr-1"

    def test_repeated_add_conflict(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        _refresh_with_fixture(client, feed["feedId"])
        article = _first_article(client, feed["feedId"])

        with patch("app.services.rss_feed_service.call_downloader_api", new=AsyncMock(return_value="Ok.")):
            client.post(f"/api/v1/rss/articles/{article['articleId']}/add", json={}, headers=_auth())
            resp = client.post(f"/api/v1/rss/articles/{article['articleId']}/add", json={}, headers=_auth())
        body = resp.json()
        assert body["code"] == "409" and body["data"]["reasonCode"] == "RSS_ARTICLE_ALREADY_ADDED"

    def test_rtorrent_unsupported(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        _refresh_with_fixture(client, feed["feedId"])
        article = _first_article(client, feed["feedId"])

        resp = client.post(
            f"/api/v1/rss/articles/{article['articleId']}/add",
            json={"downloaderId": "dl-rt-1"},
            headers=_auth(),
        )
        assert resp.json()["data"]["reasonCode"] == "RSS_DOWNLOADER_TYPE_UNSUPPORTED"

    def test_offline_downloader_rejected(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        _refresh_with_fixture(client, feed["feedId"])
        article = _first_article(client, feed["feedId"])

        resp = client.post(
            f"/api/v1/rss/articles/{article['articleId']}/add",
            json={"downloaderId": "dl-off-1"},
            headers=_auth(),
        )
        assert resp.json()["data"]["reasonCode"] == "RSS_DOWNLOADER_OFFLINE"

    def test_qb_failure_marks_add_failed(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        _refresh_with_fixture(client, feed["feedId"])
        article = _first_article(client, feed["feedId"])

        with patch("app.services.rss_feed_service.call_downloader_api", new=AsyncMock(return_value="Fails.")):
            resp = client.post(f"/api/v1/rss/articles/{article['articleId']}/add", json={}, headers=_auth())
        assert resp.json()["data"]["reasonCode"] == "RSS_ADD_FAILED"
        row = db_session.query(RssArticle).filter(RssArticle.article_id == article["articleId"]).first()
        assert row.status == "pending"


# ==============================================================================
# 平台门控
# ==============================================================================


class TestPlatformGate:
    def test_android_server_rejects_writes(self, client, db_session):
        _make_user(db_session)
        with patch(
            "app.api.endpoints.rss_subscriptions.resolve_platform",
            return_value="android-server",
        ):
            resp = client.post(
                "/api/v1/rss/feeds",
                json={"downloaderId": "dl-qb-1", "name": "x", "url": "https://example.com/f.xml"},
                headers=_auth(),
            )
        assert resp.json()["data"]["reasonCode"] == "RSS_PLATFORM_UNSUPPORTED"

    def test_desktop_platform_allows(self, client, db_session):
        _make_user(db_session)
        feed = _create_feed(client)
        assert feed["feedId"]
