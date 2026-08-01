# -*- coding: utf-8 -*-
"""tests/tasks/ 共享 fixture —— 为 H 组 API 契约测试提供异步临时 DB。

async_orphan_db 与 tests/services/conftest.py 的同名 fixture 行为一致
（临时 aiosqlite 内存库 + 建孤儿相关表），供 tests/tasks/ 下的测试使用。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base


@pytest.fixture
async def async_orphan_db():
    """异步内存 SQLite，建孤儿 + 通知 + 下载器 + 种子信息相关表。"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.models.orphan_file import OrphanFile, OrphanScanResult  # noqa: F401
    from app.models.orphan_purge_job import OrphanPurgeJob  # noqa: F401
    from app.models.notification import Notification  # noqa: F401
    from app.downloader.models import BtDownloaders  # noqa: F401
    from app.torrents.models import TorrentInfo  # noqa: F401
    from app.torrents.audit_models import TorrentAuditLog  # noqa: F401
    from app.tasks.cron_models import CronTask  # noqa: F401

    # 导入所有有 FK 依赖的模型，确保 create_all 时目标表已注册
    from app.models.setting_templates import SettingTemplate  # noqa: F401
    from app.auth.models import User  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
