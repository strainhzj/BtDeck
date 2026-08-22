# -*- coding: utf-8 -*-
"""Real-SQLite regression coverage for advanced-search related-data batching."""

from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.endpoints import torrent_helpers
from app.api.models.advanced_search import EnhancedAdvancedSearchRequest
from app.database import Base
from app.downloader.models import BtDownloaders
from app.services.advanced_search import AdvancedSearchService
from app.torrents.models import TorrentInfo, TrackerInfo, TrackerKeywordConfig
from tests.api.conftest import make_torrent


def test_real_advanced_search_prefetches_trackers_and_downloaders_in_batches(
    monkeypatch,
):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [TorrentInfo.__table__, TrackerInfo.__table__, BtDownloaders.__table__, TrackerKeywordConfig.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    session = sessionmaker(bind=engine)()
    now = datetime(2026, 7, 18, 12, 0, 0)
    try:
        session.add(
            BtDownloaders(
                downloader_id="advanced-dl",
                nickname="qB",
                downloader_type=0,
            )
        )
        for index in range(7):
            info_id = f"advanced-info-{index}"
            make_torrent(
                session,
                info_id=info_id,
                downloader_id="advanced-dl",
                downloader_name="qB",
                hash_=f"advanced-hash-{index}",
                name=f"Torrent {index}",
                size=4096,
                added_date=now,
            )
            session.add(
                TrackerInfo(
                    tracker_id=f"advanced-tracker-{index}",
                    torrent_info_id=info_id,
                    tracker_name=f"Tracker {index}",
                    tracker_url=f"https://tracker/{info_id}",
                    create_time=now,
                    create_by="tester",
                    update_time=now,
                    update_by="tester",
                    dr=0,
                )
            )
        session.commit()

        monkeypatch.setattr(torrent_helpers, "_RELATED_PREFETCH_BATCH_SIZE", 3)
        select_statements = []

        def record_select(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                select_statements.append(statement)

        event.listen(engine, "before_cursor_execute", record_select)
        try:
            result = AdvancedSearchService(session).search_torrents(
                EnhancedAdvancedSearchRequest(page=1, limit=100000),
                user_id="tester",
            )
        finally:
            event.remove(engine, "before_cursor_execute", record_select)

        assert result["code"] == "200", result["msg"]
        assert result["total"] == 7
        assert len(result["data"]) == 7
        # 6 = 主查询 + tracker 分批 + 下载器分批；+1 = 展示覆写的关键词池加载
        # （convert_to_vos_with_trackers 每次列表转换仅加载一次，见 tracker_keyword_map）
        assert len(select_statements) == 7
        assert {item["trackerInfo"][0]["tracker_url"] for item in result["data"]} == {
            f"https://tracker/advanced-info-{index}" for index in range(7)
        }
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=list(reversed(tables)))
