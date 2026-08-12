from types import SimpleNamespace

import pytest

from app.tasks.scheduler.torrent_tracker_status_judge import evaluate_tracker_error_state


def _tracker(status: int, message: str):
    return SimpleNamespace(
        last_announce_succeeded=status,
        last_announce_msg=message,
        last_scrape_msg="",
    )


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
