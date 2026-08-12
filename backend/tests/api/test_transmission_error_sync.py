"""
Transmission 种子错误状态同步集成测试

验证 error>=2(tracker 错误 / 本地错误)的 Transmission 种子，经过同步路径后
能正确落库为 status="error"，与前端已支持的错误标签对齐。

覆盖范围：
1. create_transmission_torrent_record（种子添加路径，torrent_helpers.py:774）
2. errorString 会同步为 error_reason，恢复后清空
3. has_torrent_info_changes 能捕获 status / error_reason 变更
4. error 恢复（2→0）链路：status 应从 error 回到正常查表值
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.api.endpoints.torrent_helpers import create_transmission_torrent_record
from app.api.endpoints.torrents_async import extract_tracker_rows_from_torrent
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.services.sync_db_write import has_torrent_info_changes


def _make_downloader() -> MagicMock:
    """构造仅需 nickname 属性的 downloader mock。"""
    d = MagicMock()
    d.nickname = "tr-downloader"
    return d


def _make_tr_torrent(
    *,
    error: int = 0,
    status: str = "seeding",
    error_string: str = "",
) -> MagicMock:
    """构造字段齐全的 Transmission 种子 mock。

    显式设置 error 为 int，避免 MagicMock 自动属性陷阱。
    """
    t = MagicMock()
    t.id = 42
    t.hashString = "b" * 40
    t.name = "tr-torrent"
    t.download_dir = "/downloads"
    t.total_size = 2048
    t.status = status
    t.error = error
    t.error_string = error_string
    t.torrent_file = "/config/tr/torrents/x.torrent"
    t.added_date = datetime(2026, 1, 1, 12, 0, 0)
    t.done_date = None
    t.ratio = 0.5
    t.seed_ratio_limit = None
    t.labels = []
    return t


# ============================================================
# create_transmission_torrent_record: error 字段写入 DB 记录
# ============================================================


class TestCreateTransmissionTorrentRecordErrorState:
    """种子添加路径：error>=2 的种子应写入 status='error'"""

    def test_本地错误写入error状态(self):
        """error=3(本地错误，如磁盘满) 的种子 status 应为 error"""
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(
            error=3,
            status="downloading",
            error_string="No space left on device",
        )
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "error"
        assert record.error_reason == "No space left on device"

    def test_tracker错误写入error状态(self):
        """error=2(tracker错误) 的种子 status 应为 error"""
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=2, status="seeding", error_string="Tracker gave HTTP 503")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "error"
        assert record.error_reason == "Tracker gave HTTP 503"

    def test_正常种子写入查表状态(self):
        """error=0 的正常种子 status 应为查表值（seeding）"""
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=0, status="seeding")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "seeding"
        assert record.error_reason is None

    def test_tracker警告不写入error状态(self):
        """error=1(tracker警告) 的种子 status 应为查表值，不归入 error"""
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=1, status="downloading", error_string="temporary warning")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "downloading"
        assert record.error_reason is None

    def test_严重错误空文案不写入空字符串(self):
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=3, error_string="   ")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.error_reason is None


# ============================================================
# has_torrent_info_changes: status→error 变更检测
# ============================================================


class TestStatusErrorChangeDetection:
    """增量同步变更检测：status 变化应被捕获以触发 DB 写入"""

    def test_status从正常变为error被检测(self):
        """缓存行 status=seeding，新数据 status=error → 应检测到变更"""
        existing = {"hash": "h1", "status": "seeding"}
        new_mapping = {"hash": "h1", "status": "error"}
        assert has_torrent_info_changes(existing, new_mapping) is True

    def test_status从error恢复正常被检测(self):
        """缓存行 status=error，新数据 status=seeding → 应检测到变更（恢复链路）"""
        existing = {"hash": "h1", "status": "error"}
        new_mapping = {"hash": "h1", "status": "seeding"}
        assert has_torrent_info_changes(existing, new_mapping) is True

    def test_status同为error无变更不被检测(self):
        """缓存行与新数据同为 error → 不应误报变更"""
        existing = {"hash": "h1", "status": "error"}
        new_mapping = {"hash": "h1", "status": "error"}
        assert has_torrent_info_changes(existing, new_mapping) is False

    def test_error_reason变化被检测(self):
        existing = {"hash": "h1", "status": "error", "error_reason": "old reason"}
        new_mapping = {"hash": "h1", "status": "error", "error_reason": "new reason"}
        assert has_torrent_info_changes(existing, new_mapping) is True

    def test_error恢复时清空原因被检测(self):
        existing = {"hash": "h1", "status": "error", "error_reason": "disk full"}
        new_mapping = {"hash": "h1", "status": "seeding", "error_reason": None}
        assert has_torrent_info_changes(existing, new_mapping) is True


# ============================================================
# resolve_transmission_status 端到端一致性
# ============================================================


class TestResolveConsistencyWithRecordCreation:
    """resolve_transmission_status 与 DB 记录创建的一致性"""

    @pytest.mark.parametrize(
        "tr_status,tr_error,expected",
        [
            # 严重错误 → error
            ("downloading", 2, "error"),
            ("seeding", 3, "error"),
            ("stopped", 2, "error"),
            # tracker 警告 → 查表
            ("downloading", 1, "downloading"),
            # 正常 → 查表
            ("seeding", 0, "seeding"),
            ("stopped", 0, "paused"),
        ],
    )
    def test_resolve与记录创建一致(self, tr_status, tr_error, expected):
        """resolve_transmission_status 的输出应与 create_transmission_torrent_record 写入的 status 一致"""
        resolve_result = TorrentStatusMapper.resolve_transmission_status(tr_status, tr_error)
        assert resolve_result == expected
        # 记录创建路径同样产出该 status
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=tr_error, status=tr_status)
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == expected


class TestTransmissionTrackerStatusNormalization:
    """TrackerStats 布尔字段必须先归一，不能直接当作 0-5 状态码。"""

    @staticmethod
    def _tracker_stat(
        *,
        has_contacted: bool,
        succeeded: bool,
        timed_out: bool = False,
        state: int = 0,
        result: str = "",
    ) -> SimpleNamespace:
        fields = {
            "announce": "https://tracker.example/announce",
            "host": "tracker.example",
            "hasAnnounced": has_contacted,
            "lastAnnounceSucceeded": succeeded,
            "lastAnnounceTimedOut": timed_out,
            "announceState": state,
            "lastAnnounceResult": result,
            "hasScraped": has_contacted,
            "lastScrapeSucceeded": succeeded,
            "lastScrapeTimedOut": timed_out,
            "scrapeState": state,
            "lastScrapeResult": result,
        }
        return SimpleNamespace(
            fields=fields,
            site_name="tracker.example",
            last_announce_succeeded=succeeded,
            last_announce_timed_out=timed_out,
            last_announce_result=result,
            last_scrape_succeeded=succeeded,
            last_scrape_timed_out=timed_out,
            last_scrape_result=result,
        )

    @pytest.mark.parametrize(
        "tracker_stat,expected",
        [
            (
                _tracker_stat.__func__(
                    has_contacted=False,
                    succeeded=False,
                    result="Connection refused",
                ),
                0,
            ),
            (_tracker_stat.__func__(has_contacted=True, succeeded=True, result="Success"), 2),
            (_tracker_stat.__func__(has_contacted=True, succeeded=False, result="Connection refused"), 3),
            (_tracker_stat.__func__(has_contacted=True, succeeded=False, timed_out=True), 4),
        ],
    )
    def test_同步提取使用真实Tracker状态而非成功布尔值(self, tracker_stat, expected):
        torrent = SimpleNamespace(tracker_stats=[tracker_stat])

        rows, _ = extract_tracker_rows_from_torrent(
            torrent,
            torrent_info_id="info-1",
            downloader_type="transmission",
            current_time=datetime(2026, 8, 12, 12, 0, 0),
        )

        assert rows[0]["last_announce_succeeded"] == expected
        assert rows[0]["last_scrape_succeeded"] == expected
