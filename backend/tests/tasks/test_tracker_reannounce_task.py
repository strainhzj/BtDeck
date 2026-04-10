# -*- coding: utf-8 -*-
"""
Tracker Reannounce 定时轮询任务单元测试

测试定时轮询任务的所有逻辑：
- 域名匹配与种子分组
- 汇报间隔判断
- 按站点过滤（enabled/disabled）
- 空状态处理
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta


# ==================== 辅助工具 ====================

class _FakeTrackerInfo:
    def __init__(self, tracker_id="trk-001", torrent_info_id="info-001",
                 tracker_url="http://tracker.example.com/announce",
                 tracker_host="tracker.example.com", dr=0):
        self.tracker_id = tracker_id
        self.torrent_info_id = torrent_info_id
        self.tracker_url = tracker_url
        self.tracker_host = tracker_host
        self.dr = dr


class _FakeConfig:
    def __init__(self, id_="cfg-001", domain_pattern="tracker.example.com",
                 domain_display_name="Example", interval_minutes=30,
                 enabled=True, last_announce_time=None):
        self.id_ = id_
        self.domain_pattern = domain_pattern
        self.domain_display_name = domain_display_name
        self.interval_minutes = interval_minutes
        self.enabled = enabled
        self.last_announce_time = last_announce_time


def make_tracker(**kwargs):
    return _FakeTrackerInfo(**kwargs)


def make_config(**kwargs):
    return _FakeConfig(**kwargs)


# ==================== 测试：域名匹配与分组 ====================

class TestDomainMatchingAndGrouping:
    def test_single_domain_single_tracker(self):
        from app.tasks.scheduler.tracker_reannounce_task import group_torrents_by_domain
        trackers = [make_tracker(tracker_host="tracker.example.com", torrent_info_id="info-001")]
        configs = [make_config(domain_pattern="tracker.example.com")]
        groups = group_torrents_by_domain(trackers, configs)
        assert "tracker.example.com" in groups
        assert len(groups["tracker.example.com"]) == 1

    def test_wildcard_domain_matching(self):
        from app.tasks.scheduler.tracker_reannounce_task import group_torrents_by_domain
        trackers = [
            make_tracker(tracker_host="a.example.com", torrent_info_id="info-001"),
            make_tracker(tracker_host="b.example.com", torrent_info_id="info-002"),
            make_tracker(tracker_host="other.tracker.net", torrent_info_id="info-003"),
        ]
        configs = [make_config(domain_pattern="%.example.com")]
        groups = group_torrents_by_domain(trackers, configs)
        assert "a.example.com" in groups
        assert "b.example.com" in groups
        assert "other.tracker.net" not in groups

    def test_no_matching_config(self):
        from app.tasks.scheduler.tracker_reannounce_task import group_torrents_by_domain
        trackers = [make_tracker(tracker_host="tracker.example.com")]
        configs = [make_config(domain_pattern="other.tracker.net")]
        groups = group_torrents_by_domain(trackers, configs)
        assert len(groups) == 0

    def test_empty_trackers(self):
        from app.tasks.scheduler.tracker_reannounce_task import group_torrents_by_domain
        groups = group_torrents_by_domain([], [make_config()])
        assert len(groups) == 0

    def test_empty_configs(self):
        from app.tasks.scheduler.tracker_reannounce_task import group_torrents_by_domain
        trackers = [make_tracker()]
        groups = group_torrents_by_domain(trackers, [])
        assert len(groups) == 0

    def test_torrent_with_multiple_trackers(self):
        from app.tasks.scheduler.tracker_reannounce_task import group_torrents_by_domain
        trackers = [
            make_tracker(tracker_host="tracker.a.com", torrent_info_id="info-001"),
            make_tracker(tracker_host="tracker.b.com", torrent_info_id="info-001"),
        ]
        configs = [
            make_config(domain_pattern="tracker.a.com"),
            make_config(domain_pattern="tracker.b.com"),
        ]
        groups = group_torrents_by_domain(trackers, configs)
        assert "tracker.a.com" in groups
        assert "tracker.b.com" in groups


# ==================== 测试：间隔判断 ====================

class TestIntervalJudgment:
    def test_never_announced_should_announce(self):
        from app.tasks.scheduler.tracker_reannounce_task import should_announce
        config = make_config(interval_minutes=30, last_announce_time=None)
        assert should_announce(config) is True

    def test_recently_announced_should_not_announce(self):
        from app.tasks.scheduler.tracker_reannounce_task import should_announce
        config = make_config(interval_minutes=30, last_announce_time=datetime.now() - timedelta(minutes=5))
        assert should_announce(config) is False

    def test_expired_should_announce(self):
        from app.tasks.scheduler.tracker_reannounce_task import should_announce
        config = make_config(interval_minutes=30, last_announce_time=datetime.now() - timedelta(minutes=60))
        assert should_announce(config) is True

    def test_exact_interval_boundary(self):
        from app.tasks.scheduler.tracker_reannounce_task import should_announce
        config = make_config(interval_minutes=30, last_announce_time=datetime.now() - timedelta(minutes=30))
        assert should_announce(config) is True

    def test_one_second_before_interval(self):
        from app.tasks.scheduler.tracker_reannounce_task import should_announce
        config = make_config(interval_minutes=30, last_announce_time=datetime.now() - timedelta(minutes=29, seconds=59))
        assert should_announce(config) is False


# ==================== 测试：站点过滤 ====================

class TestSiteEnableFilter:
    def test_disabled_site_excluded(self):
        from app.core.reannounce_config_operations import filter_enabled_configs
        configs = [
            make_config(enabled=True),
            make_config(enabled=False),
            make_config(enabled=True),
        ]
        enabled = filter_enabled_configs(configs)
        assert len(enabled) == 2

    def test_all_disabled(self):
        from app.core.reannounce_config_operations import filter_enabled_configs
        configs = [make_config(enabled=False), make_config(enabled=False)]
        enabled = filter_enabled_configs(configs)
        assert len(enabled) == 0

    def test_all_enabled(self):
        from app.core.reannounce_config_operations import filter_enabled_configs
        configs = [make_config(enabled=True), make_config(enabled=True)]
        enabled = filter_enabled_configs(configs)
        assert len(enabled) == 2


# ==================== 测试：种子过滤 ====================

class TestTorrentFiltering:
    def test_filter_by_downloader(self):
        from app.tasks.scheduler.tracker_reannounce_task import filter_torrents_by_downloader

        class FakeTorrent:
            def __init__(self, dl_id, dr=0):
                self.downloader_id = dl_id
                self.dr = dr

        torrents = [FakeTorrent("dl-001"), FakeTorrent("dl-002"), FakeTorrent("dl-001")]
        result = filter_torrents_by_downloader(torrents, "dl-001")
        assert len(result) == 2

    def test_deleted_excluded(self):
        from app.tasks.scheduler.tracker_reannounce_task import filter_torrents_by_downloader

        class FakeTorrent:
            def __init__(self, dl_id, dr=0):
                self.downloader_id = dl_id
                self.dr = dr

        torrents = [FakeTorrent("dl-001", dr=0), FakeTorrent("dl-001", dr=1)]
        result = filter_torrents_by_downloader(torrents, "dl-001")
        assert len(result) == 1
        assert result[0].dr == 0

    def test_no_matching_downloader(self):
        from app.tasks.scheduler.tracker_reannounce_task import filter_torrents_by_downloader

        class FakeTorrent:
            def __init__(self, dl_id, dr=0):
                self.downloader_id = dl_id
                self.dr = dr

        torrents = [FakeTorrent("dl-001"), FakeTorrent("dl-002")]
        result = filter_torrents_by_downloader(torrents, "dl-003")
        assert len(result) == 0
