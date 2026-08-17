# -*- coding: utf-8 -*-
"""进度精度修复的同步流集成回归。

与 test_progress_rounding.py（纯函数级）互补：这里走真实的
qb/tr_add_torrents_info_only_async 同步函数，验证
- insert 分支落库的 progress 为 2 位小数（99.556946664657 → 99.56）；
- 存量脏值行在"0.5 阈值保留旧值"分支被替换为舍入值（自愈链路的
  同步侧入口，配合 has_torrent_info_changes 精确比较构成完整自愈）。

构造方式参照 test_torrents_async_info_budget.py（真实内存库 + 伪下载器
客户端 + patch bulk_upsert_with_retry 捕获写入行）。
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.endpoints import torrents_async
from app.core.config import settings
from app.database import Base
from app.torrents.models import TorrentInfo

ADDED_DT = datetime(2026, 1, 1, 12, 0, 0)
ADDED_TS = int(ADDED_DT.timestamp())

# qB/TR 原始 0-1 小数 ×100 后产生长浮点尾差的真实形态
DIRTY_FRACTION = 0.99556946664657
DIRTY_PERCENT = DIRTY_FRACTION * 100  # = 99.556946664657（脏值）
ROUNDED_PERCENT = 99.56


@pytest.fixture
async def info_db():
    """异步内存 SQLite，只建 torrent_info 表（StaticPool 单连接）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[TorrentInfo.__table__]))
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=[TorrentInfo.__table__]))
        await engine.dispose()


def _qb_downloader():
    return SimpleNamespace(
        downloader_id="dl-1",
        nickname="qb",
        host="localhost",
        port=8080,
        username="admin",
        password="secret",
    )


def _qb_seed(hash_, name, progress):
    return SimpleNamespace(
        hash=hash_,
        name=name,
        save_path="/downloads",
        total_size=4096,
        progress=progress,
        state="stalledUP",
        added_on=ADDED_TS,
        completion_on=0,
        ratio=1.5,
        ratio_limit=2.0,
        tags="PT",
        category="电影",
        super_seeding=False,
    )


def _qb_row(info_id, hash_, name, progress):
    """与 _qb_seed 字段匹配的现有 DB 行（TorrentInfo ORM），进度可注入脏值。"""
    t = TorrentInfo(
        info_id,
        "dl-1",
        "qb",
        f"tid-{hash_}",
        hash_,
        name,
        "/downloads",
        4096.0,
        "seeding",
        progress,
        None,
        ADDED_DT,
        None,
        1.5,
        2.0,
        "PT",
        "电影",
        False,
        True,
        ADDED_DT,
        "tester",
        ADDED_DT,
        "tester",
        0,
    )
    t.has_tracker_error = False
    return t


def _make_qb_client(seeds):
    client = MagicMock()
    client.sync_maindata = MagicMock()

    def torrents_info(**kwargs):
        offset = kwargs.get("offset", 0)
        limit = kwargs.get("limit", 500)
        return seeds[offset : offset + limit]

    client.torrents_info = MagicMock(side_effect=torrents_info)
    return client


def _tr_downloader():
    return SimpleNamespace(
        downloader_id="dl-tr",
        nickname="tr",
        host="localhost",
        port=9091,
        username="admin",
        password="secret",
    )


def _tr_seed(i, hash_, name, percent_done):
    return SimpleNamespace(
        id=i,
        hashString=hash_,
        name=name,
        status=6,
        error=0,
        error_string="",
        download_dir="/downloads",
        total_size=4096,
        percent_done=percent_done,
        torrent_file=None,
        added_date=ADDED_DT,
        done_date=None,
        ratio=1.5,
        seed_ratio_limit=2.0,
    )


def _make_tr_client(seeds):
    by_id = {s.id: s for s in seeds}
    client = MagicMock()

    def get_torrents(**kwargs):
        ids = kwargs.get("ids")
        if ids is None:
            return list(by_id.values())
        return [by_id[i] for i in ids]

    client.get_torrents = MagicMock(side_effect=get_torrents)
    return client


def _empty_db():
    db = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.execute.return_value = query_result
    return db


def _budget_off(monkeypatch):
    monkeypatch.setattr(settings, "INFO_SYNC_MAX_TORRENTS_PER_RUN", 10**7)
    monkeypatch.setattr(settings, "INFO_SYNC_RUN_BUDGET_SECONDS", 600.0)


class TestQbSyncProgressRounding:
    async def test_insert_row_progress_rounded(self, monkeypatch):
        """新种子 insert 分支：高精度原始进度落库为 99.56 而非 99.556946664657。"""
        _budget_off(monkeypatch)
        seed = _qb_seed("dirty01", "新种子", DIRTY_FRACTION)
        client = _make_qb_client([seed])
        db = _empty_db()

        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.qb_add_torrents_info_only_async(db, [_qb_downloader()], client=client)

        inserted = bulk_mock.await_args.args[1]
        assert len(inserted) == 1
        assert inserted[0]["progress"] == ROUNDED_PERCENT
        assert inserted[0]["progress"] != DIRTY_PERCENT

    async def test_dirty_existing_row_self_heals_via_threshold(self, info_db, monkeypatch):
        """存量脏值自愈（同步侧）：脏旧值 99.556946664657 + 新值 99.56 差 <0.5
        走"保留旧值"分支，保留的是归一化（舍入）后的 99.56 → update 行写 99.56。"""
        _budget_off(monkeypatch)
        dirty_row = _qb_row("info-dirty", "dirty01", "脏值种子", DIRTY_PERCENT)
        info_db.add(dirty_row)
        await info_db.commit()

        # 远端真实进度 99.56（下载完成附近的稳定态）
        seed = _qb_seed("dirty01", "脏值种子", 0.9956)
        client = _make_qb_client([seed])

        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.qb_add_torrents_info_only_async(info_db, [_qb_downloader()], client=client)

        # 脏值 → 99.56 判定为变化（精确比较），进入 update 且写入舍入值
        assert bulk_mock.await_args.args[1] == []  # 无 insert
        updated = bulk_mock.await_args.args[2]
        assert len(updated) == 1
        assert updated[0]["progress"] == ROUNDED_PERCENT

    async def test_stable_rounded_row_not_rewritten(self, info_db, monkeypatch):
        """修正后的稳定态：库内 99.56 + 新值 99.56 → 保留旧值且写 99.56（同值），
        配合 has_torrent_info_changes 精确比较不会产生每轮无效写入。"""
        _budget_off(monkeypatch)
        stable_row = _qb_row("info-stable", "stable1", "稳定种子", ROUNDED_PERCENT)
        info_db.add(stable_row)
        await info_db.commit()

        seed = _qb_seed("stable1", "稳定种子", 0.99556946664657)
        client = _make_qb_client([seed])

        with (
            patch.object(torrents_async, "QB_USE_INCREMENTAL_SYNC", False),
            patch.dict(torrents_async._QB_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.qb_add_torrents_info_only_async(info_db, [_qb_downloader()], client=client)

        updated = bulk_mock.await_args.args[2]
        assert len(updated) == 1
        assert updated[0]["progress"] == ROUNDED_PERCENT


class TestTrSyncProgressRounding:
    async def test_insert_row_progress_rounded(self, monkeypatch):
        """TR insert 分支：percent_done ×100 的长尾差落库为 99.56。"""
        _budget_off(monkeypatch)
        seed = _tr_seed(1, "trdirty1", "TR新种子", DIRTY_FRACTION)
        client = _make_tr_client([seed])
        db = _empty_db()

        with (
            patch.dict(torrents_async._TR_FULL_SYNC_DONE, {}, clear=True),
            patch.dict(torrents_async._TR_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.tr_add_torrents_info_only_async(db, [_tr_downloader()], client=client)

        inserted = bulk_mock.await_args.args[1]
        assert len(inserted) == 1
        assert inserted[0]["progress"] == ROUNDED_PERCENT

    async def test_dirty_existing_row_self_heals_via_threshold(self, info_db, monkeypatch):
        """TR 存量脏值自愈：与 qB 同构（保留旧值分支写入舍入值）。"""
        _budget_off(monkeypatch)
        from tests.api.test_torrents_async_info_budget import _tr_row  # noqa: F401（说明：TR 行构造复用）

        # 直接构造 ORM 行（与 budget 文件的 _tr_row 同形态，进度注入脏值）
        row = TorrentInfo(
            "info-tr-dirty",
            "dl-tr",
            "tr",
            "1",
            "trdirty1",
            "TR脏值种子",
            "/downloads",
            4096.0,
            "seeding",
            DIRTY_PERCENT,
            None,
            ADDED_DT,
            None,
            1.5,
            2.0,
            "",
            "",
            False,
            True,
            ADDED_DT,
            "tester",
            ADDED_DT,
            "tester",
            0,
        )
        row.has_tracker_error = False
        info_db.add(row)
        await info_db.commit()

        seed = _tr_seed(1, "trdirty1", "TR脏值种子", 0.9956)
        client = _make_tr_client([seed])

        with (
            patch.dict(torrents_async._TR_FULL_SYNC_DONE, {}, clear=True),
            patch.dict(torrents_async._TR_LAST_FULL_SYNC, {}, clear=True),
            patch.object(torrents_async, "bulk_upsert_with_retry", new=AsyncMock()) as bulk_mock,
        ):
            await torrents_async.tr_add_torrents_info_only_async(info_db, [_tr_downloader()], client=client)

        assert bulk_mock.await_args.args[1] == []
        updated = bulk_mock.await_args.args[2]
        assert len(updated) == 1
        assert updated[0]["progress"] == ROUNDED_PERCENT
