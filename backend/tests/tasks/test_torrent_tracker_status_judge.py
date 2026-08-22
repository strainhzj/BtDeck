from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.data.default_scheduled_tasks import get_task_by_code
from app.downloader.models import BtDownloaders
from app.tasks.scheduler.torrent_tracker_status_judge import (
    TorrentTrackerStatusJudge,
    evaluate_tracker_error_state,
)
from app.tasks.resource_guard import SKIP_WAIT_TIMEOUT, admission_controller
from app.tasks.task_profiles import get_profile
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent


def _tracker(status: int, message: Optional[str], scrape_message: Optional[str] = ""):
    return SimpleNamespace(
        last_announce_succeeded=status,
        last_announce_msg=message,
        last_scrape_msg=scrape_message,
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


@pytest.mark.parametrize("downloader_type", [0, 1])
@pytest.mark.parametrize("message", [None, "", "   "])
def test_工作中且消息为空时明确归类为正常(downloader_type, message):
    result = evaluate_tracker_error_state(
        [_tracker(2, message)],
        {},
        downloader_type,
    )

    assert result is False


@pytest.mark.parametrize("downloader_type", [0, 1])
def test_工作中但存在失败关键词时仍按关键词归类(downloader_type):
    result = evaluate_tracker_error_state(
        [_tracker(2, "Connection refused")],
        {"Connection refused": "failed"},
        downloader_type,
    )

    assert result is True


def test_工作中但存在未知消息时仍保留原值():
    result = evaluate_tracker_error_state(
        [_tracker(2, "unclassified")],
        {},
        0,
    )

    assert result is None


def test_工作中且announce消息为空但scrape失败时仍按关键词归类():
    result = evaluate_tracker_error_state(
        [_tracker(2, None, "Connection refused")],
        {"Connection refused": "failed"},
        0,
    )

    assert result is True


@pytest.mark.parametrize("downloader_type", [0, "0", "qbittorrent", 1, "1", "transmission"])
@pytest.mark.parametrize("working_message", [None, "", "   "])
@pytest.mark.parametrize("reverse_order", [False, True])
def test_zimiao样例中明确失败与工作中空消息混合时清除历史错误(
    downloader_type,
    working_message,
    reverse_order,
):
    trackers = [
        _tracker(4, "skipping tracker announce (unreachable)"),
        _tracker(2, working_message, None),
    ]
    if reverse_order:
        trackers.reverse()

    result = evaluate_tracker_error_state(
        trackers,
        {"skipping tracker announce (unreachable)": "failed"},
        downloader_type,
    )

    assert result is False


@pytest.mark.parametrize("downloader_type", [0, 1])
def test_zimiao样例中两个Tracker都明确失败时继续保留错误(downloader_type):
    result = evaluate_tracker_error_state(
        [
            _tracker(4, "skipping tracker announce (unreachable)"),
            _tracker(3, "Connection refused"),
        ],
        {
            "skipping tracker announce (unreachable)": "failed",
            "Connection refused": "failed",
        },
        downloader_type,
    )

    assert result is True


def test_zimiao样例中工作中Tracker有未知非空消息时不掩盖未知状态():
    result = evaluate_tracker_error_state(
        [
            _tracker(4, "skipping tracker announce (unreachable)"),
            _tracker(2, "unclassified working response"),
        ],
        {"skipping tracker announce (unreachable)": "failed"},
        0,
    )

    assert result is None


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


def test_状态判断任务保持独立Cron并在Tracker同步后错峰执行():
    tracker_sync = get_task_by_code("tracker_sync_598b784c")
    status_judge = get_task_by_code("TORRENT_TRACKER_STATUS_JUDGE")

    assert tracker_sync is not None
    assert status_judge is not None
    assert tracker_sync["executor"] != status_judge["executor"]
    assert tracker_sync["cron_plan"] == "10,40 * * * *"
    assert status_judge["cron_plan"] == "20,50 * * * *"

    sync_minutes = [int(value) for value in tracker_sync["cron_plan"].split()[0].split(",")]
    judge_minutes = [int(value) for value in status_judge["cron_plan"].split()[0].split(",")]
    assert len(sync_minutes) == len(judge_minutes) == 2
    assert [judge - sync for sync, judge in zip(sync_minutes, judge_minutes)] == [10, 10]

    sync_profile = get_profile(tracker_sync["task_code"])
    judge_profile = get_profile(status_judge["task_code"])
    assert sync_profile is not None and sync_profile.heavy_sync is True
    assert judge_profile is not None and judge_profile.heavy_sync is True

    task = TorrentTrackerStatusJudge()
    assert task.default_interval == 1800
    assert task.get_schedule_config()["cron_expression"] == status_judge["cron_plan"]


async def test_Tracker同步未完成时状态判断不会并发启动():
    sync_profile = get_profile("tracker_sync_598b784c")
    judge_profile = get_profile("TORRENT_TRACKER_STATUS_JUDGE")
    assert sync_profile is not None
    assert judge_profile is not None

    admission_controller.reset_state()
    sync_admission = await admission_controller.acquire(sync_profile.task_code, sync_profile)
    assert sync_admission.admitted is True

    try:
        judge_admission = await admission_controller.acquire(
            judge_profile.task_code,
            replace(judge_profile, wait_timeout=0.01),
        )
        assert judge_admission.admitted is False
        assert judge_admission.skip_reason == SKIP_WAIT_TIMEOUT
        assert judge_profile.task_code not in admission_controller.running
    finally:
        admission_controller.release(sync_profile.task_code)
        admission_controller.reset_state()


@pytest.mark.parametrize(
    "downloader_type,tracker_status,tracker_message,initial_value,expected_value,expected_counter,expected_updates",
    [
        (0, 1, "Connection refused", True, False, "total_at_least_one_normal", 1),
        (1, 0, "Connection refused", True, False, "total_at_least_one_normal", 1),
        (1, 1, "Connection refused", True, False, "total_at_least_one_normal", 1),
        (1, 3, "Connection refused", False, True, "total_all_failed", 1),
        (0, 2, None, True, False, "total_at_least_one_normal", 1),
        (1, 2, None, True, False, "total_at_least_one_normal", 1),
        (0, 2, "   ", True, False, "total_at_least_one_normal", 1),
        (0, 2, "Connection refused", False, True, "total_all_failed", 1),
        (0, 2, "unclassified", True, True, "total_no_change", 0),
    ],
)
def test_批处理真实写库遵循下载器状态语义(
    judge_session_factory,
    downloader_type,
    tracker_status,
    tracker_message,
    initial_value,
    expected_value,
    expected_counter,
    expected_updates,
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
            last_announce_msg=tracker_message,
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
    assert task.total_torrents_updated == expected_updates


def test_zimiao双Tracker真实写库会清除历史错误(judge_session_factory):
    now = datetime(2026, 8, 12, 12, 0, 0)
    db = judge_session_factory()
    db.add(
        BtDownloaders(
            downloader_id="zimiao-dl",
            nickname="zimiao-downloader",
            downloader_type=0,
            dr=0,
        )
    )
    db.commit()
    make_torrent(
        db,
        info_id="zimiao-torrent",
        downloader_id="zimiao-dl",
        downloader_name="zimiao-downloader",
        hash_="zimiao-hash",
        name="zimiao torrent",
        status="seeding",
        has_tracker_error=True,
    )
    db.add_all(
        [
            TrackerInfo(
                tracker_id="zimiao-failed",
                torrent_info_id="zimiao-torrent",
                tracker_name="zimiao",
                tracker_url="https://tracker.zimiao.example/announce",
                last_announce_succeeded=4,
                last_announce_msg="skipping tracker announce (unreachable)",
                last_scrape_succeeded=4,
                last_scrape_msg="",
                create_time=now,
                create_by="tester",
                update_time=now,
                update_by="tester",
                dr=0,
            ),
            TrackerInfo(
                tracker_id="zimiao-working",
                torrent_info_id="zimiao-torrent",
                tracker_name="azusa",
                tracker_url="https://tracker.azusa.example/announce",
                last_announce_succeeded=2,
                last_announce_msg=None,
                last_scrape_succeeded=2,
                last_scrape_msg=None,
                create_time=now,
                create_by="tester",
                update_time=now,
                update_by="tester",
                dr=0,
            ),
        ]
    )
    db.commit()
    db.close()

    task = TorrentTrackerStatusJudge()
    with patch(
        "app.tasks.scheduler.torrent_tracker_status_judge.SessionLocal",
        side_effect=judge_session_factory,
    ):
        task._judge_one_batch(
            ["zimiao-torrent"],
            {"skipping tracker announce (unreachable)": "failed"},
        )

    verification_db = judge_session_factory()
    try:
        torrent = verification_db.query(TorrentInfo).filter(TorrentInfo.info_id == "zimiao-torrent").one()
        assert torrent.has_tracker_error is False
    finally:
        verification_db.close()

    assert task.total_at_least_one_normal == 1
    assert task.total_all_failed == 0
    assert task.total_no_change == 0
    assert task.total_torrents_processed == 1
    assert task.total_torrents_updated == 1


def test_软删除的工作中空消息Tracker不会掩盖活动Tracker失败(judge_session_factory):
    now = datetime(2026, 8, 12, 12, 0, 0)
    db = judge_session_factory()
    db.add(
        BtDownloaders(
            downloader_id="deleted-tracker-dl",
            nickname="deleted-tracker-downloader",
            downloader_type=0,
            dr=0,
        )
    )
    db.commit()
    make_torrent(
        db,
        info_id="deleted-tracker-torrent",
        downloader_id="deleted-tracker-dl",
        downloader_name="deleted-tracker-downloader",
        hash_="deleted-tracker-hash",
        name="deleted tracker torrent",
        status="seeding",
        has_tracker_error=False,
    )
    db.add_all(
        [
            TrackerInfo(
                tracker_id="active-failed",
                torrent_info_id="deleted-tracker-torrent",
                tracker_name="active-failed",
                tracker_url="https://active.example/announce",
                last_announce_succeeded=3,
                last_announce_msg="Connection refused",
                last_scrape_succeeded=3,
                last_scrape_msg="",
                create_time=now,
                create_by="tester",
                update_time=now,
                update_by="tester",
                dr=0,
            ),
            TrackerInfo(
                tracker_id="deleted-working",
                torrent_info_id="deleted-tracker-torrent",
                tracker_name="deleted-working",
                tracker_url="https://deleted.example/announce",
                last_announce_succeeded=2,
                last_announce_msg=None,
                last_scrape_succeeded=2,
                last_scrape_msg=None,
                create_time=now,
                create_by="tester",
                update_time=now,
                update_by="tester",
                dr=1,
            ),
        ]
    )
    db.commit()
    db.close()

    task = TorrentTrackerStatusJudge()
    with patch(
        "app.tasks.scheduler.torrent_tracker_status_judge.SessionLocal",
        side_effect=judge_session_factory,
    ):
        task._judge_one_batch(
            ["deleted-tracker-torrent"],
            {"Connection refused": "failed"},
        )

    verification_db = judge_session_factory()
    try:
        torrent = verification_db.query(TorrentInfo).filter(TorrentInfo.info_id == "deleted-tracker-torrent").one()
        assert torrent.has_tracker_error is True
    finally:
        verification_db.close()

    assert task.total_all_failed == 1
    assert task.total_at_least_one_normal == 0
    assert task.total_torrents_processed == 1
    assert task.total_torrents_updated == 1
