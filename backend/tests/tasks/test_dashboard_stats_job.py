# -*- coding: utf-8 -*-
"""DashboardStatsJob paused 聚合单元测试（移动仪表盘"已暂停"卡片恒 0 修复）。

此前 job 硬编码 paused=0（注释"暂不支持"），本批改为汇总 downloader.paused_count
（由 initialization 状态更新任务维护，源头为 TorrentStatsCache.get_stats）。
"""

from types import SimpleNamespace

from app.tasks.scheduler.dashboard_stats import DashboardStatsJob


class FakeStore:
    def __init__(self, downloaders):
        self._downloaders = downloaders

    async def get_snapshot(self):
        return self._downloaders


def _dl(nickname, downloading, seeding, paused, fail_time=0):
    return SimpleNamespace(
        nickname=nickname,
        fail_time=fail_time,
        downloading_count=downloading,
        seeding_count=seeding,
        paused_count=paused,
    )


class TestDashboardStatsJobPaused:
    async def test_paused_aggregated_from_online_downloaders(self):
        """在线下载器 paused 求和；离线下载器（fail_time!=0）整体不计。"""
        app = SimpleNamespace(
            state=SimpleNamespace(
                store=FakeStore([_dl("a", 1, 10, 2), _dl("b", 0, 5, 3), _dl("off", 9, 9, 9, fail_time=1)])
            )
        )
        job = DashboardStatsJob(app)
        result = await job.execute()
        assert result["status"] == "success"
        assert app.state.torrent_stats == {"active": 16, "downloading": 1, "seeding": 15, "paused": 5}

    async def test_missing_paused_count_attr_defaults_zero(self):
        """旧缓存对象无 paused_count 属性 → getattr 兜底 0，不抛错。"""
        app = SimpleNamespace(
            state=SimpleNamespace(
                store=FakeStore([SimpleNamespace(nickname="old", fail_time=0, downloading_count=1, seeding_count=2)])
            )
        )
        job = DashboardStatsJob(app)
        result = await job.execute()
        assert result["status"] == "success"
        assert app.state.torrent_stats["paused"] == 0

    async def test_skip_without_store(self):
        app = SimpleNamespace(state=SimpleNamespace(store=None))
        job = DashboardStatsJob(app)
        result = await job.execute()
        assert result["status"] == "skipped"
