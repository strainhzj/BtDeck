# -*- coding: utf-8 -*-
"""种子统计 paused 贯通单元测试（移动仪表盘"已暂停"卡片恒 0 修复）。

背景：TorrentStatsCache.get_stats 一直计算 paused，但链路在
update_torrent_stats_smart 返回值 → _get_*_status 冷数据 → downloader.paused_count
各环节将其丢弃，DashboardStatsJob 硬编码 paused=0。本批把 paused 贯通全链路；
Transmission 的 "stopped" 状态此前落入 other 桶，一并归入 paused。

2026-08-26 加固：补状态桶全矩阵（锁死集合小写化——原驼峰 "stalledUP" 等与
status.lower() 比较永不匹配，qb stalled/queued/paused/checking 曾全部漏进 other）、
update_torrent_stats_smart 真实路径（此前仅测下游 fake）、DownloaderCheckVO
paused_count 字段（pydantic 拒绝未声明字段，缺失会致状态更新当场 ValueError，
2026-08-26 首启实测崩溃）、_update_downloader_status 冷数据属性赋值端到端。
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.downloader.initialization import (
    _get_qbittorrent_status,
    _get_transmission_status,
    _update_downloader_status,
    update_torrent_stats_smart,
)
from app.downloader.request import DownloaderCheckVO
from app.downloader.torrent_fetcher import TorrentFetcher
from app.downloader.torrent_stats_cache import TorrentStatsCache


def _feed(cache: TorrentStatsCache, statuses: list) -> None:
    cache.update_cache([{"hash": f"h{i}", "status": s, "name": f"t{i}"} for i, s in enumerate(statuses)])


class TestCachePausedStats:
    def test_paused_states_counted(self):
        """qb pausedDL/stoppedDL + tr stopped 计入 paused；pausedUP 仍归做种。"""
        cache = TorrentStatsCache("d1")
        _feed(cache, ["pausedDL", "stoppedDL", "stopped", "downloading", "seeding", "stalledUP", "pausedUP"])
        stats = cache.get_stats()
        assert stats["downloading"] == 1
        # seeding + stalledUP + pausedUP（已完成暂停按既有口径归做种）
        assert stats["seeding"] == 3
        assert stats["paused"] == 3
        assert stats["other"] == 0

    def test_tr_stopped_not_other(self):
        """回归锁：Transmission 'stopped' 必须计入 paused 而非 other。"""
        cache = TorrentStatsCache("d1")
        _feed(cache, ["stopped"])
        stats = cache.get_stats()
        assert stats["paused"] == 1
        assert stats["other"] == 0


class TestStatusColdDataPaused:
    async def test_qb_status_passthrough_paused(self):
        downloader = SimpleNamespace(
            client=SimpleNamespace(transfer_info=lambda: {"up_info_speed": 1024, "dl_info_speed": 2048})
        )

        async def fake_smart(dl, force_full_sync=False):
            return {
                "downloading_count": 2,
                "seeding_count": 7,
                "paused_count": 4,
                "sync_mode": "incremental",
                "elapsed": 0.01,
                "from_cache": False,
            }

        with patch("app.downloader.initialization.update_torrent_stats_smart", new=fake_smart):
            result = await _get_qbittorrent_status(downloader, update_cold=True)
        assert result["paused_count"] == 4
        assert result["downloading_count"] == 2
        assert result["seeding_count"] == 7

    async def test_qb_status_hot_only_paused_zero(self):
        downloader = SimpleNamespace(
            client=SimpleNamespace(transfer_info=lambda: {"up_info_speed": 0, "dl_info_speed": 0})
        )
        result = await _get_qbittorrent_status(downloader, update_cold=False)
        assert result["paused_count"] == 0
        assert result["downloading_count"] == 0

    async def test_tr_status_passthrough_paused(self):
        downloader = SimpleNamespace(
            client=SimpleNamespace(session_stats=lambda: SimpleNamespace(upload_speed=1024, download_speed=2048))
        )

        async def fake_smart(dl, force_full_sync=False):
            return {
                "downloading_count": 1,
                "seeding_count": 9,
                "paused_count": 5,
                "sync_mode": "full",
                "elapsed": 0.02,
                "from_cache": False,
            }

        with patch("app.downloader.initialization.update_torrent_stats_smart", new=fake_smart):
            result = await _get_transmission_status(downloader, update_cold=True)
        assert result["paused_count"] == 5
        assert result["seeding_count"] == 9

    async def test_tr_status_hot_only_paused_zero(self):
        downloader = SimpleNamespace(
            client=SimpleNamespace(session_stats=lambda: SimpleNamespace(upload_speed=0, download_speed=0))
        )
        result = await _get_transmission_status(downloader, update_cold=False)
        assert result["paused_count"] == 0


class TestCacheFullBucketMatrix:
    def test_all_documented_states_classified(self):
        """全状态矩阵：每个文档化状态落到预期桶。

        锁死集合小写化修复——原集合写驼峰（"stalledUP" 等）而比较前 status.lower()，
        qb 的 stalled/queued/paused/checking 状态曾全部漏进 other 桶。
        """
        cache = TorrentStatsCache("d1")
        _feed(
            cache,
            [
                "downloading",
                "stalledDL",
                "queuedDL",
                "checkingDL",  # 下载中 x4
                "seeding",
                "stalledUP",
                "queuedUP",
                "pausedUP",
                "checkingUP",  # 做种 x5
                "pausedDL",
                "stoppedDL",
                "stopped",  # 已暂停 x3
                "unknown",
                "error",
                "missingfiles",
                "weirdState",  # 其他 x4
            ],
        )
        stats = cache.get_stats()
        assert stats["downloading"] == 4
        assert stats["seeding"] == 5
        assert stats["paused"] == 3
        assert stats["other"] == 4
        assert stats["total"] == 16

    def test_status_case_normalized(self):
        """状态串任意大小写都按语义分桶（比较前 .lower() 归一）。"""
        cache = TorrentStatsCache("d1")
        _feed(cache, ["SEEDING", "PausedDL", "StalledUP", "STOPPED"])
        stats = cache.get_stats()
        assert stats["seeding"] == 2  # SEEDING + StalledUP
        assert stats["paused"] == 2  # PausedDL + STOPPED


class TestSmartStatsPaused:
    """update_torrent_stats_smart 真实路径的 paused_count 输出（此前仅测下游 fake）。"""

    @staticmethod
    def _make_downloader(downloader_type, cache=None):
        return SimpleNamespace(
            client=object(),
            downloader_id="d1",
            downloader_type=downloader_type,
            nickname="t",
            stats_cache=cache,
        )

    async def test_qb_full_sync_returns_paused(self):
        dl = self._make_downloader(0)

        def fake_batch(client, status_filter=None, offset=0, limit=100, **kw):
            if offset == 0:
                return [
                    {"hash": "a", "status": "downloading"},
                    {"hash": "b", "status": "seeding"},
                    {"hash": "c", "status": "stopped"},
                ]
            return []

        with patch.object(TorrentFetcher, "get_qbittorrent_torrents_batch", staticmethod(fake_batch)):
            result = await update_torrent_stats_smart(dl, force_full_sync=True)
        assert result["downloading_count"] == 1
        assert result["seeding_count"] == 1
        assert result["paused_count"] == 1
        assert result["from_cache"] is False

    async def test_qb_incremental_returns_paused_from_cache(self):
        cache = TorrentStatsCache("d1")
        _feed(cache, ["downloading", "seeding", "seeding", "pausedDL", "stoppedDL"])
        cache.mark_full_sync()  # 最近已全量 → 本次走增量
        dl = self._make_downloader(0, cache)

        def fake_active(client, status_filter=None, offset=0, limit=100, **kw):
            return []

        with patch.object(TorrentFetcher, "get_qbittorrent_torrents_batch", staticmethod(fake_active)):
            result = await update_torrent_stats_smart(dl, force_full_sync=False)
        assert result["paused_count"] == 2
        assert result["seeding_count"] == 2
        assert result["sync_mode"] == "incremental"

    async def test_tr_full_sync_returns_paused(self):
        dl = self._make_downloader(1)

        def fake_tr(client, torrent_hashes=None, batch_size=200, fields=None):
            return [
                {"hash": "a", "status": "seeding"},
                {"hash": "b", "status": "stopped"},
                {"hash": "c", "status": "stopped"},
            ]

        with patch.object(TorrentFetcher, "get_transmission_torrents_batch", staticmethod(fake_tr)):
            result = await update_torrent_stats_smart(dl, force_full_sync=True)
        assert result["paused_count"] == 2
        assert result["seeding_count"] == 1

    async def test_fetch_failure_falls_back_to_cache_paused(self):
        cache = TorrentStatsCache("d1")
        _feed(cache, ["stopped", "seeding"])
        dl = self._make_downloader(0, cache)

        def boom(client, **kw):
            raise RuntimeError("network down")

        with patch.object(TorrentFetcher, "get_qbittorrent_torrents_batch", staticmethod(boom)):
            result = await update_torrent_stats_smart(dl, force_full_sync=True)
        assert result["from_cache"] is True
        assert result["paused_count"] == 1
        assert result["seeding_count"] == 1


class TestDownloaderCheckVOPausedField:
    def test_paused_count_field_assignable(self):
        """VO 必须声明 paused_count——pydantic 拒绝未声明字段赋值，
        状态更新任务直接 setattr 会当场 ValueError（2026-08-26 首启实测崩溃）。
        """
        vo = DownloaderCheckVO(nickname="t")
        vo.paused_count = 5
        assert vo.paused_count == 5

    def test_paused_count_default_none(self):
        vo = DownloaderCheckVO(nickname="t")
        assert vo.paused_count is None


class TestUpdateDownloaderStatusSetsPaused:
    """端到端属性赋值：真实 DownloaderCheckVO + _update_downloader_status 冷/热分支。"""

    @staticmethod
    def _make_vo():
        return DownloaderCheckVO(nickname="t", host="10.0.0.1", port=8080, downloader_type=0, client=object())

    @staticmethod
    def _patches(status_result):
        async def fake_probe(host, port, timeout_s=3.0):
            return 0.5

        async def fake_port(host, port, timeout=3.0, max_retries=1):
            return True

        async def fake_status(dl, update_cold=False):
            return status_result

        return (
            patch("app.utils.connectivity.probe_delay", new=fake_probe),
            patch("app.downloader.initialization.check_port_connectivity", new=fake_port),
            patch("app.downloader.initialization._get_qbittorrent_status", new=fake_status),
        )

    async def test_cold_update_sets_paused_count_on_vo(self):
        vo = self._make_vo()
        p1, p2, p3 = self._patches(
            {
                "upload_speed": 10.0,
                "download_speed": 5.0,
                "downloading_count": 2,
                "seeding_count": 3,
                "paused_count": 4,
            }
        )
        with p1, p2, p3:
            ok = await _update_downloader_status(vo, update_cold=True)
        assert ok is True
        assert vo.downloading_count == 2
        assert vo.seeding_count == 3
        assert vo.paused_count == 4

    async def test_hot_update_leaves_counts_untouched(self):
        vo = self._make_vo()
        p1, p2, p3 = self._patches({"upload_speed": 1.0, "download_speed": 1.0})
        with p1, p2, p3:
            ok = await _update_downloader_status(vo, update_cold=False)
        assert ok is True
        assert vo.paused_count is None
