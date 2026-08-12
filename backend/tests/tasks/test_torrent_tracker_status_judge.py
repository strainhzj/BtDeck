from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.downloader.models import BtDownloaders
from app.tasks.scheduler.torrent_tracker_status_judge import (
    TorrentTrackerStatusJudge,
    evaluate_tracker_error_state,
)
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent


def _tracker(status: int, message: str):
    return SimpleNamespace(
        last_announce_succeeded=status,
        last_announce_msg=message,
        last_scrape_msg="",
    )


@pytest.fixture
def judge_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [TorrentInfo.__table__, TrackerInfo.__table__, BtDownloaders.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine, tables=list(reversed(tables)))
        engine.dispose()


@pytest.mark.parametrize(
    "downloader_type,status",
    [
        (0, 1),  # qBittorrent: 未联系
        (1, 0),  # Transmission: 未联系
        (1, 1),  # Transmission: 发送中
    ],
)
def test_未联系Tracker即使消息命中失败词也不归类为错误(downloader_type, status):
    result = evaluate_tracker_error_state(
        [_tracker(status, "Connection refused")],
        {"Connection refused": "failed"},
        downloader_type,
    )

    assert result is False


@pytest.mark.parametrize("downloader_type,status", [(0, 3), (1, 3)])
def test_已联系且明确失败的Tracker仍归类为错误(downloader_type, status):
    result = evaluate_tracker_error_state(
        [_tracker(status, "Connection refused")],
        {"Connection refused": "failed"},
        downloader_type,
    )

    assert result is True


def test_存在未匹配Tracker时不把部分失败误当作全部失败():
    result = evaluate_tracker_error_state(
        [_tracker(3, "Connection refused"), _tracker(3, "unclassified")],
        {"Connection refused": "failed"},
        0,
    )

    assert result is None


@pytest.mark.parametrize("keyword_type", ["success", "ignored"])
def test_任一正常或忽略Tracker都会清除整体错误(keyword_type):
    result = evaluate_tracker_error_state(
        [_tracker(3, "Connection refused"), _tracker(2, "healthy")],
        {"Connection refused": "failed", "healthy": keyword_type},
        0,
    )

    assert result is False


def test_中性Tracker与失败Tracker混合时优先保持非错误():
    result = evaluate_tracker_error_state(
        [_tracker(0, "stale failure"), _tracker(3, "Connection refused")],
        {"stale failure": "failed", "Connection refused": "failed"},
        1,
    )

    assert result is False


def test_所有Tracker明确失败时才标记整体错误():
    result = evaluate_tracker_error_state(
        [_tracker(3, "Connection refused"), _tracker(3, "Timed out")],
        {"Connection refused": "failed", "Timed out": "failed"},
        1,
    )

    assert result is True


@pytest.mark.parametrize("trackers", [[], [_tracker(3, "unclassified")]])
def test_没有明确结论时保留数据库原值(trackers):
    assert evaluate_tracker_error_state(trackers, {}, 0) is None


def test_缺少下载器类型时保留旧关键词判定而不猜测状态码():
    result = evaluate_tracker_error_state(
        [_tracker(0, "Connection refused")],
        {"Connection refused": "failed"},
        None,
    )

    assert result is True


@pytest.mark.parametrize(
    "downloader_type,tracker_status,initial_value,expected_value,expected_counter",
    [
        (0, 1, True, False, "total_at_least_one_normal"),
        (1, 0, True, False, "total_at_least_one_normal"),
        (1, 1, True, False, "total_at_least_one_normal"),
        (1, 3, False, True, "total_all_failed"),
    ],
)
def test_批处理真实写库遵循下载器状态语义(
    judge_session_factory,
    downloader_type,
    tracker_status,
    initial_value,
    expected_value,
    expected_counter,
):
    now = datetime(2026, 8, 12, 12, 0, 0)
    db = judge_session_factory()
    db.add(
        BtDownloaders(
            downloader_id="judge-dl",
            nickname="judge-downloader",
            downloader_type=downloader_type,
            dr=0,
        )
    )
    db.commit()
    make_torrent(
        db,
        info_id="judge-torrent",
        downloader_id="judge-dl",
        downloader_name="judge-downloader",
        hash_="judge-hash",
        name="judge torrent",
        status="seeding",
        has_tracker_error=initial_value,
    )
    db.add(
        TrackerInfo(
            tracker_id="judge-tracker",
            torrent_info_id="judge-torrent",
            tracker_name="judge",
            tracker_url="https://tracker.example/announce",
            last_announce_succeeded=tracker_status,
            last_announce_msg="Connection refused",
            last_scrape_succeeded=tracker_status,
            last_scrape_msg="",
            create_time=now,
            create_by="tester",
            update_time=now,
            update_by="tester",
            dr=0,
        )
    )
    db.commit()
    db.close()

    task = TorrentTrackerStatusJudge()
    with patch(
        "app.tasks.scheduler.torrent_tracker_status_judge.SessionLocal",
        side_effect=judge_session_factory,
    ):
        task._judge_one_batch(
            ["judge-torrent"],
            {"Connection refused": "failed"},
        )

    verification_db = judge_session_factory()
    try:
        torrent = verification_db.query(TorrentInfo).filter(TorrentInfo.info_id == "judge-torrent").one()
        assert torrent.has_tracker_error is expected_value
    finally:
        verification_db.close()

    assert getattr(task, expected_counter) == 1
    assert task.total_torrents_processed == 1
    assert task.total_torrents_updated == 1
