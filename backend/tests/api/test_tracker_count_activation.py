# -*- coding: utf-8 -*-
"""tracker scrape 计数激活 + TR added_date 本地化测试（统计报表 W2，决策 6/8）。

覆盖（PLANS/statistics-reports.md §6"既有扩展"）：
- qB 行构造×2（num_seeds/num_leeches/num_downloaded 键 + -1→NULL 归一）；
- TR 行构造×2（trackerStats 三列 + is_backup 保留行仅计数置 NULL）；
- upsert set_×2（batch / add 两路 update 场景计数落库）；
- 主备切换回归（backup↔primary 互换后 URL 不被 Step4 标 dr=1、计数按新角色取值）；
- 白名单翻转（存量 NULL→值即判变更触发回填；计数无变化不误判抖动）；
- TR added_date 两条写入路径本地化（epoch → naive 本地，与 qB 同构）。

真机证据（2026-09-24 W2 首步实测，qB v4.3.9/API 2.8.2 + TR 4.0.5）：
- qB trackers 键集 {msg, num_downloaded, num_leeches, num_peers, num_seeds, status, tier, url}；
- TR trackerStats 含 seederCount/leecherCount/downloadCount（downloadCount 可为 -1，TTG 实测）
  与 isBackup；lib added_date=aware UTC、done_date=aware local（torrent.py:808/822）。
"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.endpoints import torrents_async
from app.database import Base
from app.torrents.models import TrackerInfo as trackerInfoModel

ADDED_DT = datetime(2026, 1, 1, 12, 0, 0)
ADDED_TS = int(ADDED_DT.timestamp())


@pytest.fixture
async def tracker_db():
    """异步内存 SQLite，建 tracker_info 表（含部分索引）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[trackerInfoModel.__table__]))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


def _qb_torrent():
    """qB 种子桩：trackers 含正常计数行 + -1 哨兵行 + DHT（应跳过）。"""
    return SimpleNamespace(
        trackers=[
            {
                "url": "http://t1.example.com/announce",
                "status": 2,
                "msg": "",
                "tier": 0,
                "num_seeds": 47,
                "num_leeches": 0,
                "num_downloaded": 664,
                "num_peers": 3,
            },
            {
                "url": "http://t2.example.com/announce",
                "status": 2,
                "msg": "",
                "tier": 1,
                "num_seeds": -1,
                "num_leeches": -1,
                "num_downloaded": -1,
                "num_peers": 0,
            },
            {
                "url": "** [DHT] **",
                "status": 0,
                "msg": "",
                "tier": "",
                "num_seeds": 0,
                "num_leeches": 0,
                "num_downloaded": 0,
                "num_peers": 0,
            },
        ]
    )


def _tr_stat(url, *, is_backup=False, seeder=28, leecher=29, downloaded=564):
    return SimpleNamespace(
        fields={
            "announce": url,
            "host": "h.example.com:443",
            "isBackup": is_backup,
            "seederCount": seeder,
            "leecherCount": leecher,
            "downloadCount": downloaded,
            "lastAnnounceSucceeded": True,
            "lastScrapeSucceeded": True,
        },
        site_name="site",
        last_announce_result="Success",
        last_scrape_result="",
    )


def _tr_torrent(*stats):
    return SimpleNamespace(tracker_stats=list(stats))


def _extract_counts(rows):
    return {r["tracker_url"]: (r["seeder_count"], r["leecher_count"], r["download_count"]) for r in rows}


# =============================================================================
# 行构造：qB num_* 键 + 归一（两处构造函数）
# =============================================================================


class TestQbRowConstruction:
    async def test_extract_fn_reads_num_keys_and_normalizes(self):
        """行构造② extract_tracker_rows_from_torrent：qB num_* 三键 + -1→NULL + DHT 过滤。"""
        rows, urls = torrents_async.extract_tracker_rows_from_torrent(_qb_torrent(), "info-1", "0", datetime.now())
        assert urls == {"http://t1.example.com/announce", "http://t2.example.com/announce"}
        counts = _extract_counts(rows)
        assert counts["http://t1.example.com/announce"] == (47, 0, 664)
        # -1 哨兵（未知）归一为 NULL
        assert counts["http://t2.example.com/announce"] == (None, None, None)

    async def test_sync_add_fn_reads_num_keys_and_normalizes(self, tracker_db):
        """行构造① sync_add_tracker_async：qB 三列经真实 upsert 落库（insert 场景）。"""
        await torrents_async.sync_add_tracker_async(tracker_db, "0", "insert", _qb_torrent(), "info-1")
        await tracker_db.flush()
        rows = (
            (await tracker_db.execute(select(trackerInfoModel).order_by(trackerInfoModel.tracker_url))).scalars().all()
        )
        counts = {r.tracker_url: (r.seeder_count, r.leecher_count, r.download_count) for r in rows}
        assert counts["http://t1.example.com/announce"] == (47, 0, 664)
        assert counts["http://t2.example.com/announce"] == (None, None, None)


# =============================================================================
# 行构造：TR trackerStats 三列 + backup 保留行置 NULL（两处构造函数）
# =============================================================================


class TestTrRowConstruction:
    async def test_extract_fn_backup_keeps_row_nulls_counts(self):
        """行构造②：TR backup 条目保留行与 URL、仅三列计数置 NULL。"""
        torrent = _tr_torrent(
            _tr_stat("http://primary.example.com/announce"),
            _tr_stat("http://backup.example.com/announce", is_backup=True, seeder=999, leecher=999, downloaded=999),
        )
        rows, urls = torrents_async.extract_tracker_rows_from_torrent(torrent, "info-1", "1", datetime.now())
        assert urls == {"http://primary.example.com/announce", "http://backup.example.com/announce"}
        counts = _extract_counts(rows)
        assert counts["http://primary.example.com/announce"] == (28, 29, 564)
        assert counts["http://backup.example.com/announce"] == (None, None, None)

    async def test_extract_fn_tr_minus_one_normalized(self):
        """TR downloadCount=-1（真机 TTG 实测形态）归一 NULL。"""
        torrent = _tr_torrent(_tr_stat("http://ttg.example.com/announce", downloaded=-1))
        rows, _ = torrents_async.extract_tracker_rows_from_torrent(torrent, "info-1", "1", datetime.now())
        assert rows[0]["download_count"] is None
        assert rows[0]["seeder_count"] == 28

    async def test_sync_add_fn_backup_nulls_counts(self, tracker_db):
        """行构造①：TR backup 行经真实 upsert 落库且计数 NULL。"""
        torrent = _tr_torrent(
            _tr_stat("http://primary.example.com/announce", downloaded=-1),
            _tr_stat("http://backup.example.com/announce", is_backup=True, seeder=1, leecher=2, downloaded=3),
        )
        await torrents_async.sync_add_tracker_async(tracker_db, "1", "insert", torrent, "info-1")
        await tracker_db.flush()
        rows = (await tracker_db.execute(select(trackerInfoModel))).scalars().all()
        by_url = {r.tracker_url: r for r in rows}
        assert len(rows) == 2  # backup 保留行（防 Step4 误删）
        assert by_url["http://primary.example.com/announce"].download_count is None
        assert by_url["http://backup.example.com/announce"].seeder_count is None


# =============================================================================
# set_×2：update 场景计数落库（batch / add 两路）
# =============================================================================


def _row(info_id, url, *, seeder=None, leecher=None, downloaded=None):
    return {
        "tracker_id": str(uuid.uuid4()),
        "torrent_info_id": info_id,
        "tracker_name": url,
        "tracker_url": url,
        "tracker_host": "h",
        "last_announce_succeeded": 2,
        "last_announce_msg": "",
        "last_scrape_succeeded": 2,
        "last_scrape_msg": "",
        "seeder_count": seeder,
        "leecher_count": leecher,
        "download_count": downloaded,
        "create_time": datetime.now(),
        "create_by": "admin",
        "update_time": datetime.now(),
        "update_by": "admin",
        "dr": 0,
    }


class TestUpsertSetPaths:
    async def test_batch_upsert_updates_counts(self, tracker_db):
        """set_① batch 路径：存量 NULL 行在同 URL 二轮同步后计数回填。"""
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_id = "info-b"
        await sync_trackers_batch_async(tracker_db, [_row(info_id, "http://x.example.com/a")], datetime.now())
        await sync_trackers_batch_async(
            tracker_db, [_row(info_id, "http://x.example.com/a", seeder=10, leecher=20, downloaded=30)], datetime.now()
        )
        row = (await tracker_db.execute(select(trackerInfoModel))).scalars().one()
        assert (row.seeder_count, row.leecher_count, row.download_count) == (10, 20, 30)

    async def test_add_upsert_updates_counts(self, tracker_db):
        """set_② add 路径（sync_add_tracker_async 自带 set_）：update 场景计数落库。"""
        # 第一轮：计数 NULL（backup 形态不重要，仅制造存量行）
        t1 = _tr_torrent(_tr_stat("http://y.example.com/a", is_backup=True))
        await torrents_async.sync_add_tracker_async(tracker_db, "1", "insert", t1, "info-a")
        await tracker_db.flush()
        # 第二轮：primary 角色带计数 → set_ 必须落三列
        t2 = _tr_torrent(_tr_stat("http://y.example.com/a", seeder=7, leecher=8, downloaded=9))
        await torrents_async.sync_add_tracker_async(tracker_db, "1", "update", t2, "info-a")
        await tracker_db.flush()
        row = (await tracker_db.execute(select(trackerInfoModel))).scalars().one()
        assert (row.seeder_count, row.leecher_count, row.download_count) == (7, 8, 9)


# =============================================================================
# 主备切换回归：URL 不被 Step4 标 dr=1、计数按新角色取值
# =============================================================================


class TestBackupPrimarySwap:
    async def test_swap_keeps_rows_and_updates_counts(self, tracker_db):
        """backup↔primary 角色互换：两条 URL 行都保留 dr=0，计数按新角色取值。

        防 Step4 误删：backup 条目必须保留在 current_tracker_urls（批次 pairs）里，
        否则批量同步会把"本批缺失"的 URL 标 dr=1（审批 P1-3）。
        """
        from app.api.endpoints.torrents_async import sync_trackers_batch_async

        info_id = "info-swap"
        url_a, url_b = "http://s.example.com/a", "http://s.example.com/b"

        # 第一轮：A 主（计数 10/11/12）、B 备（NULL）
        await sync_trackers_batch_async(
            tracker_db,
            [_row(info_id, url_a, seeder=10, leecher=11, downloaded=12), _row(info_id, url_b)],
            datetime.now(),
        )
        # 第二轮（主备互换）：A 备（NULL）、B 主（20/21/22）
        await sync_trackers_batch_async(
            tracker_db,
            [_row(info_id, url_a), _row(info_id, url_b, seeder=20, leecher=21, downloaded=22)],
            datetime.now(),
        )

        rows = {r.tracker_url: r for r in (await tracker_db.execute(select(trackerInfoModel))).scalars().all()}
        assert set(rows) == {url_a, url_b}
        for r in rows.values():
            assert r.dr == 0, "主备切换后两 URL 行都不得被 Step4 标 dr=1"
        assert (rows[url_a].seeder_count, rows[url_a].leecher_count, rows[url_a].download_count) == (None, None, None)
        assert (rows[url_b].seeder_count, rows[url_b].leecher_count, rows[url_b].download_count) == (20, 21, 22)


# =============================================================================
# 白名单：存量 NULL→值即判变更（回填收敛）；计数无变化不抖动
# =============================================================================


class TestTrackerChangeFieldsWhitelist:
    def test_null_to_value_triggers_change(self):
        """存量 NULL → 新值即判变更（一个同步周期自动回填收敛）。"""
        from app.services.sync_db_write import has_tracker_changes

        existing = {
            "last_announce_succeeded": 2,
            "last_announce_msg": "",
            "last_scrape_succeeded": 2,
            "last_scrape_msg": "",
            "tracker_name": "n",
            "tracker_host": "h",
            "seeder_count": None,
            "leecher_count": None,
            "download_count": None,
        }
        new = _row("i", "http://w.example.com/a", seeder=5, leecher=6, downloaded=7)
        assert has_tracker_changes(existing, new) is True

    def test_same_counts_no_change(self):
        """计数与其他字段全一致 → 无变化（白名单防抖，不触发 upsert）。"""
        from app.services.sync_db_write import has_tracker_changes

        url = "http://w.example.com/a"
        existing = {
            "last_announce_succeeded": 2,
            "last_announce_msg": "",
            "last_scrape_succeeded": 2,
            "last_scrape_msg": "",
            "tracker_name": url,
            "tracker_host": "h",
            "seeder_count": 5,
            "leecher_count": 6,
            "download_count": 7,
        }
        new = _row("i", url, seeder=5, leecher=6, downloaded=7)
        assert has_tracker_changes(existing, new) is False

    def test_value_to_null_triggers_change(self):
        """值 → NULL（如转 backup）也判变更（角色切换后陈旧计数清空落库）。"""
        from app.services.sync_db_write import has_tracker_changes

        url = "http://w.example.com/a"
        existing = {
            "last_announce_succeeded": 2,
            "last_announce_msg": "",
            "last_scrape_succeeded": 2,
            "last_scrape_msg": "",
            "tracker_name": url,
            "tracker_host": "h",
            "seeder_count": 5,
            "leecher_count": 6,
            "download_count": 7,
        }
        new = _row("i", url)
        assert has_tracker_changes(existing, new) is True


# =============================================================================
# TR added_date 两路径本地化（决策 8）
# =============================================================================


def _tr_info_seed():
    return SimpleNamespace(
        id=1,
        hashString="A" * 40,
        name="tr-added",
        status=6,
        error=0,
        error_string="",
        download_dir="/downloads",
        total_size=4096,
        percent_done=0.5,
        torrent_file=None,
        added_date=None,  # 旧路径（aware UTC 属性）不再被读取
        fields={"addedDate": ADDED_TS},  # 新路径：原始 epoch
        done_date=None,
        ratio=1.5,
        seed_ratio_limit=2.0,
    )


class TestTrAddedDateLocalization:
    @staticmethod
    def _fake_call(downloader_id, lane, func, args=(), kwargs=None, **opts):
        """绕过全局 downloader_api_runtime 单例（全量 pytest 序中 lifespan 退出会
        shutdown 全局 executor，真实提交会 RuntimeError——参照
        test_torrent_speed_regression.py 的 patch 惯例）。"""
        return func(*args, **(kwargs or {}))

    async def test_info_only_path_naive_local(self, monkeypatch):
        """info-only 路径：fields['addedDate'] epoch → naive 本地（== 本机时区墙钟）。"""
        from app.core.config import settings

        monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
        monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)

        downloader = SimpleNamespace(
            downloader_id="dl-tr", nickname="tr", host="localhost", port=9091, username="a", password="b"
        )
        client = SimpleNamespace(get_torrents=lambda **kw: [_tr_info_seed()])
        db = AsyncMock()
        qr = MagicMock()
        qr.all.return_value = []
        db.execute.return_value = qr

        with (
            patch.dict(torrents_async._TR_FULL_SYNC_DONE, {}, clear=True),
            patch.dict(torrents_async._TR_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "call_downloader_api", side_effect=self._fake_call),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.tr_add_torrents_info_only_async(db, [downloader], client=client)

        inserted = bulk_mock.await_args.args[1]
        assert len(inserted) == 1
        # epoch → naive 本地：与 datetime.fromtimestamp(ADDED_TS) 同构（qB 路径同款）
        assert inserted[0]["added_date"] == datetime.fromtimestamp(ADDED_TS)
        # 语义锚：naive 本地墙钟 == ADDED_DT（桩构造 ADDED_TS = ADDED_DT 本地时间戳）
        assert inserted[0]["added_date"] == ADDED_DT

    async def test_full_path_naive_local(self, tracker_db, monkeypatch):
        """全量路径 tr_add_torrents_async：同构 epoch → naive 本地。

        用 patch bulk_upsert_with_retry 捕获写入行（不落 torrent_info 表，
        与 info-only 用例同一验证面）。
        """
        downloader = SimpleNamespace(
            downloader_id="dl-tr",
            nickname="tr",
            host="localhost",
            port=9091,
            username="a",
            password="b",
            path_mapping=None,
        )
        client = SimpleNamespace(get_torrents=lambda **kw: [_tr_info_seed()])
        db = AsyncMock()
        qr = MagicMock()
        qr.all.return_value = []
        first = MagicMock()
        first.first.return_value = None
        db.execute.return_value = qr

        with (
            patch.object(torrents_async, "call_downloader_api", side_effect=self._fake_call),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.tr_add_torrents_async(db, [downloader], client=client)

        inserted = bulk_mock.await_args.args[1]
        assert any(r["added_date"] == datetime.fromtimestamp(ADDED_TS) for r in inserted)
