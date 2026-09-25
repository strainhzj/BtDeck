# -*- coding: utf-8 -*-
"""reports 端点测试共享基建（统计报表 W3）。

模式照 test_dashboard_api.py：异步内存 SQLite（StaticPool 单连接）+ 独立
FastAPI app + dependency_overrides（get_async_db / get_current_user）+
TestClient。store 缺省不设（liveSpeed 降级零值），需真实缓存时给
client.app.state.store 赋伪对象。
"""

import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.api import api_router
from app.auth.dependencies import get_current_user
from app.database import Base, get_async_db
from app.downloader.models import BtDownloaders
from app.models.speed_sample import DownloaderSpeedHourly, DownloaderSpeedSample
from app.torrents.models import TorrentInfo, TrackerInfo

URL_PREFIX = "/api/v1/reports"

_TABLES = [
    TorrentInfo.__table__,
    TrackerInfo.__table__,
    BtDownloaders.__table__,
    DownloaderSpeedSample.__table__,
    DownloaderSpeedHourly.__table__,
]


class ReportsEnv:
    """一次性测试环境：app + 已建表内存库 session + TestClient。"""

    def __init__(self, app: FastAPI, session: AsyncSession, client: TestClient, engine):
        self.app = app
        self.session = session
        self.client = client
        self.engine = engine

    async def close(self):
        await self.session.close()
        await self.engine.dispose()


async def make_env() -> ReportsEnv:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    async def override_db():
        yield session

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(username="tester")
    client = TestClient(app, raise_server_exceptions=False)
    return ReportsEnv(app, session, client, engine)


async def add_torrent(
    session: AsyncSession,
    *,
    info_id=None,
    downloader_id="dl-1",
    downloader_name="dl",
    hash_=None,
    name="t",
    size=100.0,
    status="seeding",
    added_date=None,
    completed_date=None,
    ratio=None,
    tags="",
    category="",
    save_path="/downloads",
    has_tracker_error=False,
    deleted_at=None,
    dr=0,
    auxiliary_seed_count=1,
):
    """异步写入一行 TorrentInfo（默认参数即活跃做种行；added_date 缺省 None 便于 NULL 桶测试）。"""
    t = TorrentInfo(
        info_id or str(uuid.uuid4()),
        downloader_id,
        downloader_name,
        "tid",
        hash_ or uuid.uuid4().hex[:40],
        name,
        save_path,
        size,
        status,
        0.0,
        None,
        added_date,
        completed_date,
        ratio,
        None,
        tags,
        category,
        "否",
        True,
        datetime.now(),
        "tester",
        datetime.now(),
        "tester",
        dr,
    )
    t.has_tracker_error = has_tracker_error
    t.auxiliary_seed_count = auxiliary_seed_count
    if deleted_at is not None:
        t.deleted_at = deleted_at
    session.add(t)
    await session.commit()
    return t


async def add_tracker(
    session: AsyncSession,
    *,
    torrent_info_id,
    host="tracker.example.com",
    url=None,
    status="normal",
    seeder=None,
    leecher=None,
    downloaded=None,
    dr=0,
):
    """异步写入一行 TrackerInfo（dr=0 活跃缺省；计数三列缺省 NULL）。"""
    tr = TrackerInfo(
        tracker_id=str(uuid.uuid4()),
        torrent_info_id=torrent_info_id,
        tracker_name=url or f"http://{host}/announce",
        tracker_url=url or f"http://{host}/announce",
        tracker_host=host,
        status=status,
        msg="",
        seeder_count=seeder,
        leecher_count=leecher,
        download_count=downloaded,
        create_time=datetime.now(),
        create_by="tester",
        update_time=datetime.now(),
        update_by="tester",
        dr=dr,
    )
    session.add(tr)
    await session.commit()
    return tr


async def add_downloader(session: AsyncSession, downloader_id="dl-1", nickname="dl", downloader_type=0, dr=0):
    """异步写入一行 bt_downloaders（缺省启用）。"""
    d = BtDownloaders(
        downloader_id=downloader_id,
        nickname=nickname,
        host="127.0.0.1",
        port="8080",
        downloader_type=downloader_type,
        enabled=True,
        dr=dr,
    )
    session.add(d)
    await session.commit()
    return d


def fake_store(downloaders):
    """伪 store：get_snapshot_sync 返回 SimpleNamespace 下载器 VO。"""

    class _Store:
        def get_snapshot_sync(self):
            return downloaders

    return _Store()


def vo(downloader_id="dl-1", nickname="dl", is_online=True, download_speed=100, upload_speed=200):
    return SimpleNamespace(
        downloader_id=downloader_id,
        nickname=nickname,
        is_online=is_online,
        download_speed=download_speed,
        upload_speed=upload_speed,
    )
