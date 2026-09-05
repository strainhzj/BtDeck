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
    def __init__(
        self,
        tracker_id="trk-001",
        torrent_info_id="info-001",
        tracker_url="http://tracker.example.com/announce",
        tracker_host="tracker.example.com",
        dr=0,
    ):
        self.tracker_id = tracker_id
        self.torrent_info_id = torrent_info_id
        self.tracker_url = tracker_url
        self.tracker_host = tracker_host
        self.dr = dr


class _FakeConfig:
    def __init__(
        self,
        id_="cfg-001",
        domain_pattern="tracker.example.com",
        domain_display_name="Example",
        interval_minutes=30,
        enabled=True,
        last_announce_time=None,
    ):
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

    def __init__(self, info_id="info-1", hash="a" * 40, torrent_id="103", downloader_id="dl-1", dr=0):
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
    修复后：读段用短 session（查询后 close）→ 网络段不持 session → 写段 batch_update 自开短 session。

    收敛锚点：execute_reannounce 被调用时不得传 db（持锁=locked 根因）。
    """

    @staticmethod
    def _make_fake_db(tracker_pages, records):
        """构造按查询实体路由的 fake_db。

        _read_downloader_data 现为两段查询（2026-09-05 OOM 治理）：
        1) tracker 域名预过滤（db.query(TrackerInfo.tracker_id, ...).join().filter()
           [.filter()].order_by().limit().all()，keyset 多页，anchor 自收敛容忍任意
           filter 链深度）；
        2) 命中种子轻量列（db.query(TorrentInfo.info_id, ...).filter().all()）。
        """
        from app.torrents.models import TorrentInfo, TrackerInfo

        pages_iter = iter(tracker_pages)

        tracker_chain = MagicMock(name="tracker_query")
        anchor = MagicMock(name="tracker_anchor")
        tracker_chain.join.return_value = anchor
        anchor.filter.return_value = anchor  # 自收敛：任意深度 filter 链都落在 anchor
        anchor.order_by.return_value = anchor
        anchor.limit.return_value = anchor
        anchor.all.side_effect = lambda: next(pages_iter)

        record_chain = MagicMock(name="record_query")
        record_chain.filter.return_value.all.return_value = records

        fake_db = MagicMock(name="db")
        fake_db.query.side_effect = None

        def _query_router(*args, **_kwargs):
            if args and args[0] is TrackerInfo.tracker_id:
                return tracker_chain
            if args and args[0] is TorrentInfo.info_id:
                return record_chain
            raise AssertionError(f"读段出现未预期的查询实体: {args[0] if args else None}")

        fake_db.query.side_effect = _query_router
        return fake_db

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

        torrent = _FakeTorrentRecord(info_id="info-1", torrent_id="103")
        tracker = _FakeTrackerInfo(
            tracker_url="http://tracker.example.com/announce",
            tracker_host="tracker.example.com",
            torrent_info_id="info-1",
        )
        # tracker 预过滤查询两页：第1页命中、第2页空（keyset 终止）
        fake_db = self._make_fake_db(tracker_pages=[[tracker], []], records=[torrent])

        with (
            patch("app.services.reannounce_service.execute_reannounce", mock_exec),
            patch.object(mod, "SessionLocal", return_value=fake_db),
        ):
            await task._process_downloader(app, dl_vo, configs)

        # ★ 收敛锚点：execute_reannounce 调用 kwargs 里 db 必须不存在或为 None
        call_kwargs = mock_exec.call_args.kwargs
        assert call_kwargs.get("db", None) is None, (
            "execute_reannounce 不得传入外部 db：" "网络IO期间持有 session 是 database is locked 的根因"
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

        torrent = _FakeTorrentRecord(info_id="info-1")
        tracker = _FakeTrackerInfo(
            tracker_url="http://tracker.example.com/announce",
            tracker_host="tracker.example.com",
            torrent_info_id="info-1",
        )
        fake_db = self._make_fake_db(tracker_pages=[[tracker], []], records=[torrent])

        mock_exec = AsyncMock(return_value={"success_count": 1, "failed_count": 0})
        with (
            patch("app.services.reannounce_service.execute_reannounce", mock_exec),
            patch.object(mod, "SessionLocal", return_value=fake_db),
        ):
            await task._process_downloader(app, dl_vo, configs)

        # ★ 收敛锚点：读段 session 必须被 close
        assert fake_db.close.called, (
            "读段 session 查询后必须 close：" "若 session 未关闭而在网络 IO 期间一直持有，会触发 database is locked"
        )


# ==================== 测试：域名 LIKE 预过滤编译 ====================


class TestDomainPatternCompilation:
    """_compile_domain_contains_patterns 的 LIKE 翻译规则。"""

    def test_underscore_escaped_as_literal(self):
        from app.tasks.scheduler.tracker_reannounce_task import _compile_domain_contains_patterns

        patterns = _compile_domain_contains_patterns([make_config(domain_pattern="under_score.example.com")])
        assert patterns == ["under\\_score.example.com"]

    def test_percent_kept_as_wildcard(self):
        from app.tasks.scheduler.tracker_reannounce_task import _compile_domain_contains_patterns

        patterns = _compile_domain_contains_patterns([make_config(domain_pattern="%.example.com")])
        assert patterns == ["%.example.com"]

    def test_backslash_escaped(self):
        from app.tasks.scheduler.tracker_reannounce_task import _compile_domain_contains_patterns

        patterns = _compile_domain_contains_patterns([make_config(domain_pattern=r"back\slash.example.com")])
        assert patterns == [r"back\\slash.example.com"]

    def test_empty_and_missing_patterns_skipped(self):
        from app.tasks.scheduler.tracker_reannounce_task import _compile_domain_contains_patterns

        patterns = _compile_domain_contains_patterns([make_config(domain_pattern=""), make_config(domain_pattern=None)])
        assert patterns == []

    def test_duplicates_removed(self):
        from app.tasks.scheduler.tracker_reannounce_task import _compile_domain_contains_patterns

        patterns = _compile_domain_contains_patterns(
            [
                make_config(id_="cfg-1", domain_pattern="a.example.com"),
                make_config(id_="cfg-2", domain_pattern="a.example.com"),
            ]
        )
        assert patterns == ["a.example.com"]


# ==================== 测试：读段预过滤（真 SQLite 内存库） ====================


def _make_reannounce_session():
    """内存 SQLite sessionmaker（仅建 torrent_info / tracker_info 两表）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.torrents.models import TorrentInfo, TrackerInfo

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[TorrentInfo.__table__, TrackerInfo.__table__])
    return sessionmaker(bind=engine)


def _seed_torrent(conn, info_id, *, downloader_id="dl-1", dr=0):
    import hashlib

    from app.torrents.models import TorrentInfo

    conn.execute(
        TorrentInfo.__table__.insert().values(
            info_id=info_id,
            downloader_id=downloader_id,
            downloader_name="qB-01",
            torrent_id=str(100 + int(info_id.split("-")[-1])),
            hash=hashlib.md5(info_id.encode()).hexdigest(),
            name=f"torrent-{info_id}",
            dr=dr,
            has_tracker_error=False,
        )
    )


def _seed_tracker(conn, tracker_id, torrent_info_id, *, host, url, dr=0):
    from app.torrents.models import TrackerInfo

    conn.execute(
        TrackerInfo.__table__.insert().values(
            tracker_id=tracker_id,
            torrent_info_id=torrent_info_id,
            tracker_url=url,
            tracker_host=host,
            dr=dr,
        )
    )


class TestReadDownloaderDataPrefilter:
    """读段重构（2026-09-05 OOM 治理）的行为等价性：

    SQL 双列包含式 LIKE 只做保守超集预过滤，Python 精确复验是唯一权威——
    重点固化"不漏检"（含端口 host / NULL host / 空串 host 回退）与
    "首命中 config 不 eligible 则整种子排除"的原语义。
    """

    @pytest.fixture()
    def reannounce_env(self):
        """返回 (task, session_factory, seed 辅助)。"""
        from app.tasks.scheduler import tracker_reannounce_task as mod

        session_factory = _make_reannounce_session()
        engine = session_factory().get_bind()
        with engine.connect() as conn:
            # downloader dl-1 的种子
            for idx in range(1, 8):
                _seed_torrent(conn, f"info-{idx}")
            # 其它下载器的种子（命中子集不得跨下载器污染）
            _seed_torrent(conn, "info-901", downloader_id="dl-2")

            _seed_tracker(
                conn,
                "trk-001",
                "info-1",
                host="t.example.com:8080",
                url="http://t.example.com:8080/announce",
            )
            _seed_tracker(
                conn,
                "trk-002",
                "info-2",
                host=None,
                url="http://nullhost.example.com/announce",
            )
            _seed_tracker(
                conn,
                "trk-003",
                "info-3",
                host="",
                url="http://emptyhost.example.com/announce",
            )
            _seed_tracker(
                conn,
                "trk-004",
                "info-4",
                host="other.net",
                url="http://other.net/announce",
            )
            _seed_tracker(
                conn,
                "trk-005",
                "info-5",
                host="gone.example.com",
                url="http://gone.example.com/announce",
                dr=1,
            )
            _seed_tracker(
                conn,
                "trk-006",
                "info-6",
                host="deleted-torrent.example.com",
                url="http://deleted-torrent.example.com/announce",
            )
            _seed_tracker(
                conn,
                "trk-007",
                "info-901",
                host="cross.example.com",
                url="http://cross.example.com/announce",
            )
            # info-6 的种子已删除（dr=1），tracker 未删除
            from sqlalchemy import update

            from app.torrents.models import TorrentInfo as _TorrentInfo

            conn.execute(
                update(_TorrentInfo.__table__).where(_TorrentInfo.__table__.c.info_id == "info-6").values(dr=1)
            )
            conn.commit()

        return mod, session_factory

    def _run_read(self, mod, session_factory, configs):
        with patch.object(mod, "SessionLocal", session_factory):
            return mod.TrackerReannounceTask()._read_downloader_data(_FakeDownloaderVO(downloader_id="dl-1"), configs)

    def test_exact_pattern_matches_port_bearing_host(self, reannounce_env):
        """P-01 回归锚：host 含端口（netloc 形态）时精确 pattern 仍命中。"""
        mod, session_factory = reannounce_env
        configs = [make_config(id_="cfg-exact", domain_pattern="t.example.com")]
        result = self._run_read(mod, session_factory, configs)
        assert result is not None
        records, matched_config_ids = result
        assert [r.info_id for r in records] == ["info-1"]
        assert matched_config_ids == {"cfg-exact"}
        # 轻量 Row 满足 execute_reannounce 消费契约（hash/torrent_id 属性访问）
        import hashlib

        assert records[0].hash == hashlib.md5(b"info-1").hexdigest()
        assert records[0].torrent_id == "101"

    def test_wildcard_pattern_covers_null_and_empty_host_fallback(self, reannounce_env):
        """NULL/空串 host 走 URL 回退仍命中；不匹配域名、已删 tracker、
        已删种子、跨下载器种子全部排除。"""
        mod, session_factory = reannounce_env
        configs = [make_config(id_="cfg-wild", domain_pattern="%.example.com")]
        result = self._run_read(mod, session_factory, configs)
        assert result is not None
        records, matched_config_ids = result
        assert sorted(r.info_id for r in records) == ["info-1", "info-2", "info-3"]
        assert matched_config_ids == {"cfg-wild"}

    def test_literal_underscore_not_wildcard(self, reannounce_env):
        """pattern 中的 _ 是字面量（LIKE 转义后不被当作单字符通配）。"""
        mod, session_factory = reannounce_env
        engine = session_factory().get_bind()
        with engine.connect() as conn:
            _seed_torrent(conn, "info-11")
            _seed_torrent(conn, "info-12")
            _seed_tracker(
                conn, "trk-011", "info-11", host="under_score.example.com", url="http://under_score.example.com/a"
            )
            _seed_tracker(
                conn, "trk-012", "info-12", host="underXscore.example.com", url="http://underXscore.example.com/a"
            )
            conn.commit()
        configs = [make_config(id_="cfg-us", domain_pattern="under_score.example.com")]
        result = self._run_read(mod, session_factory, configs)
        assert result is not None
        records, _ = result
        assert [r.info_id for r in records] == ["info-11"]

    def test_first_match_config_not_eligible_excludes_torrent(self, reannounce_env):
        """原语义回归：tracker 首个命中的 config 不在汇报间隔内 → 整种子不汇报。"""
        mod, session_factory = reannounce_env
        configs = [
            make_config(
                id_="cfg-not-due",
                domain_pattern="t.example.com",
                last_announce_time=datetime.now() - timedelta(minutes=1),
                interval_minutes=30,
            ),
            make_config(id_="cfg-due", domain_pattern="t.example.com"),
        ]
        result = self._run_read(mod, session_factory, configs)
        assert result is None

    def test_same_torrent_multiple_trackers_deduped(self, reannounce_env):
        """同一种子的多个 tracker 命中只汇报一次。"""
        mod, session_factory = reannounce_env
        engine = session_factory().get_bind()
        with engine.connect() as conn:
            _seed_torrent(conn, "info-20")
            _seed_tracker(conn, "trk-020a", "info-20", host="a.example.com", url="http://a.example.com/a")
            _seed_tracker(conn, "trk-020b", "info-20", host="b.example.com", url="http://b.example.com/a")
            conn.commit()
        configs = [make_config(id_="cfg-multi", domain_pattern="%.example.com")]
        result = self._run_read(mod, session_factory, configs)
        assert result is not None
        records, _ = result
        assert len([r for r in records if r.info_id == "info-20"]) == 1

    def test_keyset_pagination_multi_page(self, reannounce_env, monkeypatch):
        """页大小压到 2 时 keyset 翻页不重不漏不死循环。"""
        mod, session_factory = reannounce_env
        monkeypatch.setattr(mod, "_REANNOUNCE_TRACKER_PAGE_SIZE", 2)
        configs = [make_config(id_="cfg-page", domain_pattern="%.example.com")]
        result = self._run_read(mod, session_factory, configs)
        assert result is not None
        records, _ = result
        got = sorted(r.info_id for r in records)
        assert got == ["info-1", "info-2", "info-3"]

    def test_record_chunking(self, reannounce_env, monkeypatch):
        """命中子集二次查询按块分批，块边界不丢记录。"""
        mod, session_factory = reannounce_env
        monkeypatch.setattr(mod, "_REANNOUNCE_RECORD_CHUNK_SIZE", 1)
        configs = [make_config(id_="cfg-chunk", domain_pattern="%.example.com")]
        result = self._run_read(mod, session_factory, configs)
        assert result is not None
        records, _ = result
        assert sorted(r.info_id for r in records) == ["info-1", "info-2", "info-3"]

    def test_empty_configs_returns_none_without_session(self):
        """空 configs（或全空 pattern）不打开 session 直接返回 None。"""
        from app.tasks.scheduler import tracker_reannounce_task as mod

        task = mod.TrackerReannounceTask()
        with patch.object(mod, "SessionLocal", MagicMock()) as fake_session_factory:
            assert task._read_downloader_data(_FakeDownloaderVO(), []) is None
            assert task._read_downloader_data(_FakeDownloaderVO(), [make_config(domain_pattern="")]) is None
            assert not fake_session_factory.called
