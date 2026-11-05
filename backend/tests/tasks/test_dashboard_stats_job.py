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
    async def test_paused_aggregated_from_online_downloaders(self, monkeypatch):
        """在线下载器 paused 求和；离线下载器（fail_time!=0）整体不计。

        W1 起 execute 附带 DB 聚合段——本测专验主缓存统计四键，把
        AsyncSessionLocal 打成失败降级：CI 全量跑时全局隔离库可能被其它
        测试写入的 cron_task 行污染，enabled 具体值不可断言；降级路径零值确定。
        """

        class _BrokenDB:
            def __call__(self):
                return self

            async def __aenter__(self):
                raise RuntimeError("db down")

            async def __aexit__(self, *args):
                return False

        monkeypatch.setattr("app.tasks.scheduler.dashboard_stats.AsyncSessionLocal", _BrokenDB())
        app = SimpleNamespace(
            state=SimpleNamespace(
                store=FakeStore([_dl("a", 1, 10, 2), _dl("b", 0, 5, 3), _dl("off", 9, 9, 9, fail_time=1)])
            )
        )
        job = DashboardStatsJob(app)
        result = await job.execute()
        assert result["status"] == "success"
        stats = app.state.torrent_stats
        assert {k: stats[k] for k in ("active", "downloading", "seeding", "paused")} == {
            "active": 16,
            "downloading": 1,
            "seeding": 15,
            "paused": 5,
        }
        # DB 聚合段（隔离文件库空表）降级零值不报错
        assert stats["statusBuckets"] == {"error": 0, "downloading": 0, "seeding": 0, "paused": 0, "other": 0}
        assert stats["siteBuckets"] == []
        assert app.state.dashboard_task_stats == {"enabled": 0}

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
