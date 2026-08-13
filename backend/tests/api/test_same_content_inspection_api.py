# -*- coding: utf-8 -*-
"""同名同大小种子只读排查 API 回归测试。"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo, TrackerKeywordConfig
from tests.api.conftest import make_torrent

URL = "/api/v1/torrents/same-content-inspection"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        BtDownloaders.__table__,
        TorrentInfo.__table__,
        TrackerInfo.__table__,
        TrackerKeywordConfig.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine, tables=tables)


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="tester")
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _add_tracker(
    db_session,
    *,
    tracker_id: str,
    info_id: str,
    tracker_url: str,
    tracker_host: str | None = None,
    announce_status: int = 2,
    announce_message: str = "Success",
    scrape_status: int = 2,
    scrape_message: str = "Success",
    status: str = "normal",
    status_message: str = "正常",
):
    now = datetime(2026, 8, 13, 12, 0, 0)
    tracker = TrackerInfo(
        tracker_id=tracker_id,
        torrent_info_id=info_id,
        tracker_name="site",
        tracker_url=tracker_url,
        tracker_host=tracker_host,
        last_announce_succeeded=announce_status,
        last_announce_msg=announce_message,
        last_scrape_succeeded=scrape_status,
        last_scrape_msg=scrape_message,
        status=status,
        msg=status_message,
        create_time=now,
        create_by="tester",
        update_time=now,
        update_by="tester",
        dr=0,
    )
    db_session.add(tracker)
    db_session.commit()
    return tracker


def test_groups_by_exact_name_size_and_distinct_hash(client, db_session):
    make_torrent(db_session, info_id="match-a", downloader_id="dl-a", hash_="HASH-A", name="Exact", size=1024)
    make_torrent(db_session, info_id="match-b", downloader_id="dl-a", hash_="HASH-B", name="Exact", size=1024)

    # 同名但大小不同、同大小但名称不同，均不能并入候选组。
    make_torrent(db_session, info_id="different-size", downloader_id="dl-b", hash_="HASH-C", name="Exact", size=2048)
    make_torrent(db_session, info_id="different-name", downloader_id="dl-b", hash_="HASH-D", name="Other", size=1024)

    # 名称和大小相同但只有同一个规范化 hash，不满足“不同 InfoHash”。
    make_torrent(db_session, info_id="same-hash-a", downloader_id="dl-c", hash_=" DUP ", name="SameHash", size=4096)
    make_torrent(db_session, info_id="same-hash-b", downloader_id="dl-d", hash_="dup", name="SameHash", size=4096)

    # 回收站/逻辑删除记录不参与主动排查。
    make_torrent(
        db_session,
        info_id="recycled",
        downloader_id="dl-e",
        hash_="HASH-E",
        name="Exact",
        size=1024,
        deleted_at=datetime(2026, 8, 13, 10, 0, 0),
    )
    make_torrent(
        db_session,
        info_id="deleted",
        downloader_id="dl-f",
        hash_="HASH-F",
        name="Exact",
        size=1024,
        dr=1,
    )

    response = client.post(URL, json={"mode": "all", "page": 1, "pageSize": 20})
    body = response.json()

    assert response.status_code == 200
    assert body["code"] == "200", body["msg"]
    assert body["data"]["total"] == 1
    assert body["data"]["summary"] == {
        "candidate_group_count": 1,
        "candidate_torrent_count": 2,
        "error_group_count": 0,
        "error_torrent_count": 0,
    }
    group = body["data"]["list"][0]
    assert group["name"] == "Exact"
    assert group["size"] == 1024
    assert group["copy_count"] == 2
    assert group["distinct_hash_count"] == 2
    assert group["downloader_count"] == 1
    assert {item["info_id"] for item in group["items"]} == {"match-a", "match-b"}


def test_errors_mode_filters_groups_and_members(client, db_session):
    db_session.add(
        TrackerKeywordConfig(
            keyword_type="failed",
            keyword="Tracker HTTP response 403",
        )
    )
    db_session.commit()

    # 候选组一：一条健康、一条任务错误、一条局部 Tracker 错误。
    make_torrent(db_session, info_id="healthy", downloader_id="dl-a", hash_="H-1", name="Candidate-A", size=100)
    make_torrent(
        db_session,
        info_id="task-error",
        downloader_id="dl-a",
        hash_="H-2",
        name="Candidate-A",
        size=100,
        status="error",
        error_reason="No data found",
    )
    make_torrent(
        db_session,
        info_id="tracker-error",
        downloader_id="dl-a",
        hash_="H-3",
        name="Candidate-A",
        size=100,
        status="seeding",
    )
    _add_tracker(
        db_session,
        tracker_id="tracker-issue",
        info_id="tracker-error",
        tracker_url="https://tracker.example/announce?passkey=secret-passkey",
        tracker_host="tracker.example",
        # 原始状态仍为 Working，但最新消息命中失败关键词，也必须主动发现。
        scrape_status=2,
        scrape_message=(
            "Tracker HTTP response 403; retry "
            "https://tracker.example/message-path-secret/announce?passkey=message-secret&token=message-token"
        ),
    )

    # 候选组二：全部健康，仅用于验证 errors 模式会过滤整个组。
    make_torrent(db_session, info_id="other-a", downloader_id="dl-b", hash_="O-1", name="Candidate-B", size=200)
    make_torrent(db_session, info_id="other-b", downloader_id="dl-b", hash_="O-2", name="Candidate-B", size=200)

    response = client.post(URL, json={"mode": "errors", "page": 1, "pageSize": 20})
    body = response.json()

    assert body["code"] == "200", body["msg"]
    data = body["data"]
    assert data["total"] == 1
    assert data["summary"] == {
        "candidate_group_count": 2,
        "candidate_torrent_count": 5,
        "error_group_count": 1,
        "error_torrent_count": 2,
    }

    group = data["list"][0]
    assert group["name"] == "Candidate-A"
    assert group["copy_count"] == 3
    assert group["error_count"] == 2
    assert {item["info_id"] for item in group["items"]} == {"task-error", "tracker-error"}

    items = {item["info_id"]: item for item in group["items"]}
    assert items["task-error"]["error_types"] == ["torrent_status", "error_reason"]
    tracker_item = items["tracker-error"]
    assert tracker_item["error_types"] == ["tracker_detail"]
    assert tracker_item["tracker_hosts"] == ["tracker.example"]
    assert tracker_item["tracker_issues"][0]["issue_types"] == ["scrape"]
    assert tracker_item["tracker_issues"][0]["scrape_status"] == "工作中"

    serialized = response.text
    assert "secret-passkey" not in serialized
    assert "message-secret" not in serialized
    assert "message-token" not in serialized
    assert "message-path-secret" not in serialized
    assert "tracker.example" in serialized


def test_aggregate_tracker_error_is_included(client, db_session):
    make_torrent(db_session, info_id="normal", downloader_id="dl-a", hash_="A", name="Aggregate", size=300)
    make_torrent(
        db_session,
        info_id="aggregate-error",
        downloader_id="dl-a",
        hash_="B",
        name="Aggregate",
        size=300,
        has_tracker_error=True,
    )

    body = client.post(URL, json={"mode": "errors"}).json()

    assert body["code"] == "200"
    item = body["data"]["list"][0]["items"][0]
    assert item["info_id"] == "aggregate-error"
    assert item["has_tracker_error"] is True
    assert item["error_types"] == ["tracker_aggregate"]


def test_request_validation_rejects_unknown_mode(client):
    response = client.post(URL, json={"mode": "unknown"})
    assert response.status_code == 422
