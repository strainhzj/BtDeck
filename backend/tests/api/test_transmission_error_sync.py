"""
Transmission 种子错误状态同步集成测试

验证 error>=2(tracker 错误 / 本地错误)的 Transmission 种子，经过同步路径后
能正确落库为 status="error"，与前端已支持的错误标签对齐。

覆盖范围：
1. create_transmission_torrent_record（种子添加路径，torrent_helpers.py:774）
2. has_torrent_info_changes 能捕获 status→error 变更（确保增量同步会触发写入）
3. error 恢复（2→0）链路：status 应从 error 回到正常查表值
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.api.endpoints.torrent_helpers import create_transmission_torrent_record
from app.core.torrent_status_mapper import TorrentStatusMapper
from app.services.sync_db_write import has_torrent_info_changes


def _make_downloader() -> MagicMock:
    """构造仅需 nickname 属性的 downloader mock。"""
    d = MagicMock()
    d.nickname = "tr-downloader"
    return d


def _make_tr_torrent(*, error: int = 0, status: str = "seeding") -> MagicMock:
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
        tr_torrent = _make_tr_torrent(error=3, status="downloading")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "error"

    def test_tracker错误写入error状态(self):
        """error=2(tracker错误) 的种子 status 应为 error"""
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=2, status="seeding")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "error"

    def test_正常种子写入查表状态(self):
        """error=0 的正常种子 status 应为查表值（seeding）"""
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=0, status="seeding")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "seeding"

    def test_tracker警告不写入error状态(self):
        """error=1(tracker警告) 的种子 status 应为查表值，不归入 error"""
        downloader = _make_downloader()
        tr_torrent = _make_tr_torrent(error=1, status="downloading")
        record = create_transmission_torrent_record(downloader, "dl-1", tr_torrent)
        assert record.status == "downloading"


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
