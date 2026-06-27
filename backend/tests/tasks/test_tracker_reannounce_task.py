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


# ==================== 回归测试：三段 session 拆分 ====================

class _FakeTorrentRecord:
    """_process_downloader 读段查询返回的种子记录（含 info_id/hash/torrent_id/downloader_id/dr）"""

    def __init__(self, info_id="info-1", hash="a" * 40, torrent_id="103",
                 downloader_id="dl-1", dr=0):
        self.info_id = info_id
        self.hash = hash
        self.torrent_id = torrent_id
        self.downloader_id = downloader_id
        self.dr = dr


class _FakeDownloaderVO:
    """轻量下载器 VO"""

    def __init__(self, downloader_id="dl-1", downloader_type=0, nickname="test"):
        self.downloader_id = downloader_id
        self.downloader_type = downloader_type
        self.nickname = nickname


class TestSessionLifecycleRegression:
    """【回归】问题2-c：_process_downloader 必须拆分读/网络/写三段 session。

    根因：原实现一个 db=SessionLocal() 贯穿"查种子 → 遍历下载器(含HTTP网络IO) → 回写"全程，
    网络 IO 期间 session 一直占着写锁，触发 "database is locked"。
    修复后：读段用短 session（expunge 后 close）→ 网络段不持 session → 写段 batch_update 自开短 session。

    收敛锚点：execute_reannounce 被调用时不得传 db（持锁=locked 根因）。
    """

    @pytest.mark.asyncio
    async def test_execute_reannounce_called_without_db(self):
        """_process_downloader 调用 execute_reannounce 时 kwargs 不得含 db（或 db 为 None）。

        若有人改回 execute_reannounce(app=..., db=db, ...)（旧的长 session 风格），
        此测试立即报红。
        """
        from app.tasks.scheduler import tracker_reannounce_task as mod

        task = mod.TrackerReannounceTask()

        # 构造一个有效下载器 + app
        dl_vo = _FakeDownloaderVO(downloader_id="dl-1")
        app = MagicMock()
        configs = [make_config(domain_pattern="tracker.example.com", enabled=True)]

        # patch execute_reannounce 为 AsyncMock（捕获调用参数）
        mock_exec = AsyncMock(return_value={"success_count": 1, "failed_count": 0})

        # 构造 fake_db：读段 3 次 db.query().filter().all() 按调用顺序返回结果。
        # 调用顺序：1) TorrentInfo.info_id（种子id列表）2) TrackerInfo（tracker列表）3) TorrentInfo（种子记录）
        fake_db = MagicMock()
        torrent = _FakeTorrentRecord(info_id="info-1", torrent_id="103")
        tracker = _FakeTrackerInfo(
            tracker_url="http://tracker.example.com/announce",
            tracker_host="tracker.example.com",
            torrent_info_id="info-1",
        )

        query_results = [
            [MagicMock(info_id="info-1")],  # 第1次：info_id 列表
            [tracker],                       # 第2次：tracker 列表
            [torrent],                       # 第3次：种子记录
        ]
        query_iter = iter(query_results)

        def _query_chain(*_args, **_kwargs):
            chain = MagicMock()
            chain.filter.return_value.all.return_value = next(query_iter)
            return chain

        fake_db.query.side_effect = _query_chain

        with patch(
            "app.services.reannounce_service.execute_reannounce", mock_exec
        ), patch.object(mod, "SessionLocal", return_value=fake_db):
            await task._process_downloader(app, dl_vo, configs)

        # ★ 收敛锚点：execute_reannounce 调用 kwargs 里 db 必须不存在或为 None
        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("db", None) is None, (
            "execute_reannounce 不得传入外部 db："
            "网络IO期间持有 session 是 database is locked 的根因"
        )

    @pytest.mark.asyncio
    async def test_read_session_is_closed_after_query(self):
        """读段 session 查询后必须 close（释放连接，不持锁做网络 IO）。

        收敛锚点：fake_db.close 必须被调用。
        """
        from app.tasks.scheduler import tracker_reannounce_task as mod

        task = mod.TrackerReannounceTask()
        dl_vo = _FakeDownloaderVO(downloader_id="dl-1")
        app = MagicMock()
        configs = [make_config(domain_pattern="tracker.example.com", enabled=True)]

        fake_db = MagicMock()
        torrent = _FakeTorrentRecord(info_id="info-1")
        tracker = _FakeTrackerInfo(
            tracker_url="http://tracker.example.com/announce",
            tracker_host="tracker.example.com",
            torrent_info_id="info-1",
        )

        query_results = [
            [MagicMock(info_id="info-1")],  # 第1次：info_id 列表
            [tracker],                       # 第2次：tracker 列表
            [torrent],                       # 第3次：种子记录
        ]
        query_iter = iter(query_results)

        def _query_chain(*_args, **_kwargs):
            chain = MagicMock()
            chain.filter.return_value.all.return_value = next(query_iter)
            return chain

        fake_db.query.side_effect = _query_chain

        mock_exec = AsyncMock(return_value={"success_count": 1, "failed_count": 0})
        with patch(
            "app.services.reannounce_service.execute_reannounce", mock_exec
        ), patch.object(mod, "SessionLocal", return_value=fake_db):
            await task._process_downloader(app, dl_vo, configs)

        # ★ 收敛锚点：读段 session 必须被 close
        assert fake_db.close.called, (
            "读段 session 查询后必须 close："
            "若 session 未关闭而在网络 IO 期间一直持有，会触发 database is locked"
        )
