# -*- coding: utf-8 -*-
"""同内容排查复用种子列表查询的 API 回归测试。"""

import sqlite3
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.api.endpoints import torrent_helpers
from app.api.endpoints.torrent_speed import ActiveKeysSnapshot, ActiveSnapshotStatus
from app.auth.dependencies import require_authenticated_user
from app.database import Base, get_db
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent

URL = "/api/v1/torrents/getList"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [BtDownloaders.__table__, TorrentInfo.__table__, TrackerInfo.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    session = sessionmaker(bind=engine)()
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


def _ids(body):
    return [item["infoId"] for item in body["data"]["list"]]


def test_same_content_filter_returns_rows_in_normal_list_contract(client, db_session):
    make_torrent(
        db_session,
        info_id="match-a",
        downloader_id="dl-a",
        hash_=" HASH-A ",
        name="Exact",
        size=1024,
    )
    make_torrent(
        db_session,
        info_id="match-b",
        downloader_id="dl-a",
        hash_="hash-b",
        name="Exact",
        size=1024,
    )
    make_torrent(
        db_session,
        info_id="different-size",
        downloader_id="dl-b",
        hash_="hash-c",
        name="Exact",
        size=2048,
    )
    make_torrent(
        db_session,
        info_id="single",
        downloader_id="dl-b",
        hash_="hash-d",
        name="Single",
        size=1024,
    )
    make_torrent(
        db_session,
        info_id="same-hash-a",
        downloader_id="dl-c",
        hash_=" DUP ",
        name="SameHash",
        size=4096,
    )
    make_torrent(
        db_session,
        info_id="same-hash-b",
        downloader_id="dl-d",
        hash_="dup",
        name="SameHash",
        size=4096,
    )
    make_torrent(
        db_session,
        info_id="recycled",
        downloader_id="dl-e",
        hash_="hash-e",
        name="Exact",
        size=1024,
        deleted_at=datetime(2026, 8, 13, 10, 0, 0),
    )
    for invalid_group, invalid_name, invalid_size, hashes in (
        ("blank-name", " ", 1024, ("blank-name-a", "blank-name-b")),
        ("zero-size", "ZeroSize", 0, ("zero-size-a", "zero-size-b")),
        ("blank-hash", "BlankHash", 1024, (" ", "valid-hash")),
    ):
        for index, hash_ in enumerate(hashes):
            make_torrent(
                db_session,
                info_id=f"{invalid_group}-{index}",
                downloader_id=f"invalid-dl-{index}",
                hash_=hash_,
                name=invalid_name,
                size=invalid_size,
            )
    make_torrent(
        db_session,
        info_id="invalid-member",
        downloader_id="dl-invalid-member",
        hash_=" ",
        name="Exact",
        size=1024,
    )

    response = client.get(URL, params={"same_content_only": "true", "skip": 0, "limit": 20})
    body = response.json()

    assert response.status_code == 200
    assert body["code"] == "200", body["msg"]
    assert body["data"]["total"] == 2
    assert body["data"]["pageSize"] == 20
    assert set(_ids(body)) == {"match-a", "match-b"}
    assert "invalid-member" not in _ids(body)
    assert all("trackerInfo" in item for item in body["data"]["list"])


def test_same_content_filter_uses_list_filters_before_group_detection(client, db_session):
    make_torrent(
        db_session,
        info_id="a-seed",
        downloader_id="dl-a",
        hash_="a",
        name="Filtered",
        size=100,
        status="seeding",
    )
    make_torrent(
        db_session,
        info_id="b-seed",
        downloader_id="dl-b",
        hash_="b",
        name="Filtered",
        size=100,
        status="seeding",
    )
    make_torrent(
        db_session,
        info_id="c-pause",
        downloader_id="dl-a",
        hash_="c",
        name="Filtered",
        size=100,
        status="paused",
    )

    filtered = client.get(
        URL,
        params={"same_content_only": "true", "downloader_id": "dl-b", "limit": 20},
    ).json()
    assert filtered["data"]["total"] == 0
    assert filtered["data"]["list"] == []

    status_filtered = client.get(
        URL,
        params={"same_content_only": "true", "status": "seeding", "limit": 20},
    ).json()
    assert status_filtered["data"]["total"] == 2
    assert set(_ids(status_filtered)) == {"a-seed", "b-seed"}


def test_same_content_filter_applies_combined_list_filters_before_grouping(client, db_session):
    matching_rows = [
        ("match-a", "dl-a", "hash-a", datetime(2026, 8, 10, 10, 0, 0)),
        ("match-b", "dl-b", "hash-b", datetime(2026, 8, 11, 10, 0, 0)),
    ]
    for info_id, downloader_id, hash_, added_date in matching_rows:
        make_torrent(
            db_session,
            info_id=info_id,
            downloader_id=downloader_id,
            hash_=hash_,
            name="Needle Movie",
            size=2048,
            status="seeding",
            tags="featured,1080p",
            category="movies",
            save_path="/media/library",
            added_date=added_date,
        )

    # 只有一个副本满足 category 条件，过滤后不能再借助另一个副本成组。
    make_torrent(
        db_session,
        info_id="partial-a",
        downloader_id="dl-a",
        hash_="partial-a",
        name="Needle Partial",
        size=2048,
        tags="featured",
        category="movies",
        save_path="/media/library",
        added_date=datetime(2026, 8, 10, 11, 0, 0),
    )
    make_torrent(
        db_session,
        info_id="partial-b",
        downloader_id="dl-b",
        hash_="partial-b",
        name="Needle Partial",
        size=2048,
        tags="featured",
        category="series",
        save_path="/media/library",
        added_date=datetime(2026, 8, 10, 12, 0, 0),
    )

    response = client.get(
        URL,
        params={
            "same_content_only": "true",
            "name_like": "Needle",
            "downloader_id": "dl-a,dl-b",
            "status": "seeding",
            "save_path_like": "/media",
            "size_min": "2KB",
            "size_max": "3KB",
            "added_date_min": "2026-08-10",
            "added_date_max": "2026-08-12",
            "tags_like": "featured",
            "category_like": "movies",
            "sort_by": "added_date",
            "sort_order": "asc",
            "limit": 20,
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["code"] == "200", body["msg"]
    assert body["data"]["total"] == 2
    assert _ids(body) == ["match-a", "match-b"]


def test_same_content_status_filter_keeps_group_and_filters_display_rows(client, db_session):
    # 生产案例回归：同内容组内仅剩 1 条错误任务时，组必须仍然成立——
    # 状态是行级属性，只过滤组内显示行，不参与分组候选判定。
    make_torrent(
        db_session,
        info_id="err-seed",
        downloader_id="dl-a",
        hash_="hash-err",
        name="Broken Film",
        size=4096,
        status="error",
        has_tracker_error=True,
    )
    make_torrent(
        db_session,
        info_id="ok-seed-a",
        downloader_id="dl-a",
        hash_="hash-ok-a",
        name="Broken Film",
        size=4096,
        status="seeding",
    )
    make_torrent(
        db_session,
        info_id="ok-seed-b",
        downloader_id="dl-b",
        hash_="hash-ok-b",
        name="Broken Film",
        size=4096,
        status="paused",
    )

    error_rows = client.get(
        URL,
        params={"same_content_only": "true", "status": "error", "limit": 20},
    ).json()
    assert error_rows["data"]["total"] == 1
    assert _ids(error_rows) == ["err-seed"]

    seeding_rows = client.get(
        URL,
        params={"same_content_only": "true", "status": "seeding", "limit": 20},
    ).json()
    assert seeding_rows["data"]["total"] == 1
    assert _ids(seeding_rows) == ["ok-seed-a"]

    multi_status_rows = client.get(
        URL,
        params={"same_content_only": "true", "status": "seeding,paused", "limit": 20},
    ).json()
    assert multi_status_rows["data"]["total"] == 2
    assert set(_ids(multi_status_rows)) == {"ok-seed-a", "ok-seed-b"}


def test_same_content_tracker_filters_are_display_level(client, db_session):
    # Tracker 地址/主域名与状态同理：组内只有一条命中 Tracker 时组不塌，
    # 结果只显示命中的那一行。
    now = datetime(2026, 8, 14, 9, 0, 0)
    for info_id, tracker_host in (("t-alpha", "alpha.example"), ("t-beta", "beta.example")):
        make_torrent(
            db_session,
            info_id=info_id,
            downloader_id="dl-a",
            hash_=f"hash-{info_id}",
            name="Tracker Film",
            size=2048,
            added_date=now,
        )
        db_session.add(
            TrackerInfo(
                tracker_id=f"tracker-{info_id}",
                torrent_info_id=info_id,
                tracker_name=f"Tracker {info_id}",
                tracker_url=f"https://{tracker_host}/announce",
                create_time=now,
                create_by="tester",
                update_time=now,
                update_by="tester",
                dr=0,
            )
        )
    db_session.commit()

    tracker_rows = client.get(
        URL,
        params={"same_content_only": "true", "tracker_like": "alpha.example", "limit": 20},
    ).json()
    assert tracker_rows["data"]["total"] == 1
    assert _ids(tracker_rows) == ["t-alpha"]

    domain_rows = client.get(
        URL,
        params={"same_content_only": "true", "tracker_domain": "alpha.example", "limit": 20},
    ).json()
    assert domain_rows["code"] == "200", domain_rows["msg"]
    assert domain_rows["data"]["total"] == 1
    assert _ids(domain_rows) == ["t-alpha"]


def test_active_deletion_exclusion_applies_before_same_content_grouping(client, db_session):
    make_torrent(
        db_session,
        info_id="reserved",
        downloader_id="dl-a",
        hash_="reserved-hash",
        name="Reserved Group",
        size=1024,
    )
    make_torrent(
        db_session,
        info_id="visible-single",
        downloader_id="dl-b",
        hash_="visible-hash",
        name="Reserved Group",
        size=1024,
    )
    for suffix in ("a", "b"):
        make_torrent(
            db_session,
            info_id=f"valid-{suffix}",
            downloader_id=f"dl-{suffix}",
            hash_=f"valid-hash-{suffix}",
            name="Valid Group",
            size=2048,
        )

    with patch(
        "app.api.endpoints.torrent_helpers.build_active_deletion_exclusion",
        return_value=TorrentInfo.info_id != "reserved",
    ):
        body = client.get(URL, params={"same_content_only": "true", "limit": 20}).json()

    assert body["code"] == "200", body["msg"]
    assert body["data"]["total"] == 2
    assert set(_ids(body)) == {"valid-a", "valid-b"}


def test_active_only_snapshot_applies_before_same_content_grouping(client, db_session):
    rows = [
        ("partial-a", "dl-a", "partial-hash-a", "Partial Group", 1024),
        ("partial-b", "dl-b", "partial-hash-b", "Partial Group", 1024),
        ("active-a", "dl-a", "active-hash-a", "Active Group", 2048),
        ("active-b", "dl-b", "active-hash-b", "Active Group", 2048),
    ]
    for info_id, downloader_id, hash_, name, size in rows:
        make_torrent(
            db_session,
            info_id=info_id,
            downloader_id=downloader_id,
            hash_=hash_,
            name=name,
            size=size,
        )

    snapshot = ActiveKeysSnapshot(
        frozenset(
            {
                ("dl-a", "partial-hash-a"),
                ("dl-a", "active-hash-a"),
                ("dl-b", "active-hash-b"),
            }
        ),
        ActiveSnapshotStatus.READY,
    )
    with patch(
        "app.api.endpoints.torrent_crud.get_active_keys_snapshot",
        return_value=snapshot,
    ):
        body = client.get(
            URL,
            params={"same_content_only": "true", "active_only": "true", "limit": 20},
        ).json()

    assert body["code"] == "200", body["msg"]
    assert body["data"]["activeSnapshotReady"] is True
    assert body["data"]["activeSnapshotStatus"] == "ready"
    assert body["data"]["total"] == 2
    assert set(_ids(body)) == {"active-a", "active-b"}


def test_same_content_filter_paginates_rows_and_keeps_total(client, db_session):
    for group_index in range(3):
        for copy_index in reversed(range(2)):
            make_torrent(
                db_session,
                info_id=f"g{group_index}-{copy_index}",
                downloader_id=f"dl-{copy_index}",
                hash_=f"hash-{group_index}-{copy_index}",
                name=f"Group-{group_index}",
                size=100 + group_index,
                added_date=datetime(2026, 8, 13, 12, group_index, 0),
            )

    query = {
        "same_content_only": "true",
        "limit": 2,
        "sort_by": "added_date",
        "sort_order": "asc",
    }
    statements = []

    def record_torrent_select(_conn, _cursor, statement, _parameters, _context, _many):
        normalized = " ".join(statement.lower().split())
        if "from torrent_info" in normalized and " order by " in normalized:
            statements.append(normalized)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record_torrent_select)
    try:
        first = client.get(URL, params={**query, "skip": 0}).json()
        repeated_first = client.get(URL, params={**query, "skip": 0}).json()
        second = client.get(URL, params={**query, "skip": 2}).json()
        third = client.get(URL, params={**query, "skip": 4}).json()
    finally:
        event.remove(engine, "before_cursor_execute", record_torrent_select)

    assert first["data"]["total"] == 6
    assert second["data"]["total"] == 6
    assert third["data"]["total"] == 6
    assert _ids(first) == ["g0-0", "g0-1"]
    assert _ids(repeated_first) == _ids(first)
    assert _ids(second) == ["g1-0", "g1-1"]
    assert _ids(third) == ["g2-0", "g2-1"]
    assert any(
        "order by torrent_info.added_date asc, torrent_info.info_id asc, "
        "torrent_info.downloader_id asc, torrent_info.downloader_name asc" in statement
        for statement in statements
    )


def test_same_content_filter_prefetches_related_data_for_current_page_only(
    client,
    db_session,
    monkeypatch,
):
    now = datetime(2026, 8, 13, 12, 0, 0)
    for index in range(8):
        info_id = f"bulk-{index}"
        make_torrent(
            db_session,
            info_id=info_id,
            downloader_id="dl-bulk",
            hash_=f"bulk-hash-{index}",
            name="Bulk Group",
            size=8192,
            added_date=now.replace(minute=index),
        )
        db_session.add(
            TrackerInfo(
                tracker_id=f"tracker-{index}",
                torrent_info_id=info_id,
                tracker_name=f"Tracker {index}",
                tracker_url=f"https://tracker.example/{info_id}",
                create_time=now,
                create_by="tester",
                update_time=now,
                update_by="tester",
                dr=0,
            )
        )
    db_session.commit()

    monkeypatch.setattr(torrent_helpers, "_RELATED_PREFETCH_BATCH_SIZE", 2)
    tracker_selects = []

    def record_tracker_select(_conn, _cursor, statement, parameters, _context, _many):
        normalized = " ".join(statement.lower().split())
        if "from tracker_info" in normalized and "torrent_info_id in" in normalized:
            tracker_selects.append(parameters)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record_tracker_select)
    try:
        body = client.get(
            URL,
            params={
                "same_content_only": "true",
                "skip": 0,
                "limit": 3,
                "sort_by": "added_date",
                "sort_order": "asc",
            },
        ).json()
    finally:
        event.remove(engine, "before_cursor_execute", record_tracker_select)

    assert body["code"] == "200", body["msg"]
    assert body["data"]["total"] == 8
    assert _ids(body) == ["bulk-0", "bulk-1", "bulk-2"]
    assert all(len(item["trackerInfo"]) == 1 for item in body["data"]["list"])
    assert len(tracker_selects) == 2


def test_same_content_filter_large_page_respects_sqlite_bind_limit(client, db_session):
    for index in range(60):
        make_torrent(
            db_session,
            info_id=f"large-{index:03d}",
            downloader_id="large-dl",
            hash_=f"large-hash-{index:03d}",
            name="Large Group",
            size=16384,
            added_date=datetime(2026, 8, 13, 12, index % 60, 0),
        )

    connection_fairy = db_session.connection().connection
    driver_connection = getattr(connection_fairy, "driver_connection", connection_fairy)
    previous_limit = driver_connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 20)
    try:
        response = client.get(
            URL,
            params={
                "same_content_only": "true",
                "skip": 0,
                "limit": 100000,
                "sort_by": "added_date",
                "sort_order": "asc",
            },
        )
    finally:
        driver_connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, previous_limit)

    body = response.json()
    assert response.status_code == 200
    assert body["code"] == "200", body["msg"]
    assert body["data"]["total"] == 60
    assert body["data"]["pageSize"] == 100000
    assert len(body["data"]["list"]) == 60


def test_legacy_post_endpoint_is_removed(client):
    response = client.post("/api/v1/torrents/same-content-inspection", json={})
    assert response.status_code == 404
