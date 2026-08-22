# -*- coding: utf-8 -*-
"""
存量 added_date 回填回归（verified-bugfix-remediation W3-3）

覆盖：
- qB 分支：torrents_info 返回 added_on → 回填 NULL 行；返回缺失/非法跳过
- TR 分支：get_torrents 返回 addedDate → 回填
- 下载器缓存缺失时跳过该下载器
- 全流程（backfill_torrent_added_dates）：仅回填仍为 NULL 的行
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.services.torrent_added_date_backfill import backfill_torrent_added_dates
from app.torrents.models import TorrentInfo

ADDED_TS = 1_700_000_000


def _direct_runtime(*args, **kwargs):
    """直接执行 func（等价 runtime 线程内调用），不依赖共享 executor 状态。"""
    func = args[2]
    call_args = args[3] if len(args) > 3 else ()
    return func(*call_args, **kwargs.get("kwargs") or {})


@pytest.fixture(autouse=True)
def _patch_runtime_dispatch():
    """全文件用例将 backfill 模块的 call_downloader_api 替换为直接派发。"""
    from app.services import torrent_added_date_backfill as backfill_mod

    with patch.object(backfill_mod, "call_downloader_api", new=AsyncMock(side_effect=_direct_runtime)):
        yield


def _make_vo(client, downloader_id="dl-1", downloader_type=0):
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.downloader_type = downloader_type
    vo.client = client
    vo.nickname = "qb-test"
    return vo


def _make_app(client, downloader_type=0):
    store = SimpleNamespace(get_snapshot=AsyncMock(return_value=[_make_vo(client, downloader_type=downloader_type)]))
    app = SimpleNamespace(state=SimpleNamespace(store=store))
    return app


class TestBackfillQbBranch:
    @pytest.mark.asyncio
    async def test_backfills_null_added_date_from_added_on(self, backfill_env):
        from app.services.torrent_added_date_backfill import _backfill_qb

        client = MagicMock()
        client.torrents_info.return_value = [SimpleNamespace(hash="abc", added_on=ADDED_TS)]
        async with AsyncSessionLocal() as db:
            updated = await _backfill_qb(db, client, "dl-1", ["abc"], "qb-test")

        assert updated == 1
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(TorrentInfo).where(TorrentInfo.hash == "abc"))).scalar_one()
            assert row.added_date is not None

    @pytest.mark.asyncio
    async def test_missing_added_on_skips_row(self, backfill_env):
        from app.services.torrent_added_date_backfill import _backfill_qb

        client = MagicMock()
        client.torrents_info.return_value = [SimpleNamespace(hash="abc", added_on=0)]
        async with AsyncSessionLocal() as db:
            updated = await _backfill_qb(db, client, "dl-1", ["abc"], "qb-test")

        assert updated == 0
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(TorrentInfo).where(TorrentInfo.hash == "abc"))).scalar_one()
            assert row.added_date is None

    @pytest.mark.asyncio
    async def test_api_error_skips_batch(self, backfill_env):
        from app.services.torrent_added_date_backfill import _backfill_qb

        client = MagicMock()
        client.torrents_info.side_effect = RuntimeError("downloader unreachable")
        async with AsyncSessionLocal() as db:
            updated = await _backfill_qb(db, client, "dl-1", ["abc"], "qb-test")

        assert updated == 0


class TestBackfillTrBranch:
    @pytest.mark.asyncio
    async def test_backfills_null_added_date_from_added_date(self, backfill_env):
        from app.services.torrent_added_date_backfill import _backfill_tr

        client = MagicMock()
        client.get_torrents.return_value = [SimpleNamespace(hashString="def", addedDate=ADDED_TS)]
        async with AsyncSessionLocal() as db:
            updated = await _backfill_tr(db, client, "dl-2", ["def"], "tr-test")

        assert updated == 1
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(TorrentInfo).where(TorrentInfo.hash == "def"))).scalar_one()
            assert row.added_date is not None


class TestBackfillFullFlow:
    @pytest.mark.asyncio
    async def test_full_flow_backfills_only_null_rows(self, backfill_env):
        """全流程：qB 分支回填 NULL 行；已有值的行与缓存缺失下载器不受影响。"""
        client = MagicMock()
        client.torrents_info.return_value = [
            SimpleNamespace(hash="abc", added_on=ADDED_TS),
            SimpleNamespace(hash="filled", added_on=ADDED_TS),
        ]
        app = _make_app(client, downloader_type=0)
        # 缓存只有 dl-1；dl-2（def）应被跳过
        store = SimpleNamespace(
            get_snapshot=AsyncMock(
                return_value=[_make_vo(client, "dl-1", 0)]
            )
        )
        app.state.store = store

        await backfill_torrent_added_dates(app)

        async with AsyncSessionLocal() as db:
            abc = (await db.execute(select(TorrentInfo).where(TorrentInfo.hash == "abc"))).scalar_one()
            filled = (await db.execute(select(TorrentInfo).where(TorrentInfo.hash == "filled"))).scalar_one()
            stale = (await db.execute(select(TorrentInfo).where(TorrentInfo.hash == "def"))).scalar_one()
            assert abc.added_date is not None
            assert filled.added_date is not None  # 有值行不重复回填（仍是原值）
            assert stale.added_date is None  # 缓存缺失下载器跳过


@pytest.fixture
async def backfill_env():
    """建表 + 造 NULL/有值行；用例结束清空测试数据。"""
    from datetime import datetime

    from app.database import AsyncSessionLocal
    from app.downloader.models import BtDownloaders
    from app.torrents.models import TorrentInfo

    async with AsyncSessionLocal() as db:
        await db.execute(TorrentInfo.__table__.delete())
        await db.execute(BtDownloaders.__table__.delete())
        await db.commit()

        db.add(BtDownloaders(downloader_id="dl-1", nickname="qb-test", downloader_type=0, dr=0))
        db.add(BtDownloaders(downloader_id="dl-2", nickname="tr-test", downloader_type=1, dr=0))

        def _seed(hash_, downloader_id, added_date=None):
            return TorrentInfo(
                id_=f"id-{hash_}",
                downloader_id=downloader_id,
                downloader_name="t",
                torrent_id=hash_,
                hash=hash_,
                name=hash_,
                save_path="/downloads",
                size=1,
                status="seeding",
                progress=100.0,
                torrent_file="",
                added_date=added_date,
                completed_date=None,
                ratio=0.0,
                ratio_limit=None,
                tags="",
                category="",
                super_seeding="0",
                enabled=1,
                create_time=datetime(2026, 1, 1),
                create_by="admin",
                update_time=datetime(2026, 1, 1),
                update_by="admin",
                dr=0,
            )

        db.add(_seed("abc", "dl-1"))
        db.add(_seed("filled", "dl-1", added_date=datetime(2026, 1, 1)))
        db.add(_seed("def", "dl-2"))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(TorrentInfo.__table__.delete())
        await db.execute(BtDownloaders.__table__.delete())
        await db.commit()
