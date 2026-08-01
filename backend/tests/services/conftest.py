# -*- coding: utf-8 -*-
"""
孤儿文件管理测试共享 fixture（v1.0.6+ 语义重做）

提供：
- async_orphan_db：临时 aiosqlite 内存库，建孤儿相关表 + notification，供 D/E/F/G/H 组真实 DB 测试
- fake_qb_client / fake_tr_client：MagicMock 模拟 qBittorrent/Transmission 客户端，含 auth.log_out spy
- fake_store：SimpleNamespace，get_snapshot() 返回 VO 列表（含 downloader_id/client/fail_time）
- fake_app：带 state.store 的伪 FastAPI 实例

设计依据：
- tests/services/ 原无共享 conftest；本文件新建以支撑 D-H 组真实临时 DB 测试
- 参考 tests/api/test_sync_governance_integration.py 的 aiosqlite + StaticPool 模式
- 不污染全量 pytest root logger / 全局单例（每测试独立 engine）
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base

# ==================== 异步临时 DB fixture ====================


@pytest.fixture
async def async_orphan_db():
    """异步内存 SQLite，建孤儿 + 通知 + 下载器 + 种子信息相关表。

    用 StaticPool 保证单连接（:memory: 库跨连接不共享）。
    yield 一个 AsyncSession；测试结束后 drop 所有表。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 延迟 import 避免循环依赖，并确保所有相关 ORM 模型已注册到 Base.metadata
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


# ==================== fake 下载器客户端 fixture ====================


class _FakeQBFile:
    """模拟 qBittorrent torrent file 条目"""

    def __init__(self, name):
        self.name = name


@pytest.fixture
def fake_qb_client():
    """模拟 qBittorrent 客户端。

    - torrents.files(hash) 返回 [_FakeQBFile, ...]
    - auth.log_out() 是 spy（断言不被调用——共享连接严禁登出）
    """
    client = MagicMock()
    client.torrents = MagicMock()
    client.torrents.files = MagicMock(return_value=[])
    client.auth = MagicMock()
    client.auth.log_out = MagicMock()
    # 默认空文件列表，测试用 client.torrents.files.return_value = [...] 覆盖
    return client


@pytest.fixture
def fake_tr_client():
    """模拟 Transmission 客户端。

    - get_torrent(hash, arguments=["files"]) 返回含 files 的 dict
    """
    client = MagicMock()
    client.get_torrent = MagicMock(return_value={"files": []})
    return client


# ==================== fake store / app fixture ====================


def make_downloader_vo(downloader_id="dl_001", client=None, fail_time=0, downloader_type=0):
    """构造一个伪下载器 VO（app.state.store.get_snapshot() 返回的元素）。

    Args:
        downloader_id: 下载器 ID
        client: 缓存的客户端连接（fake_qb_client / fake_tr_client）
        fail_time: 0=正常，>0=不可用
        downloader_type: 0=qBittorrent, 1=Transmission
    """
    vo = SimpleNamespace()
    vo.downloader_id = downloader_id
    vo.client = client
    vo.fail_time = fail_time
    vo.downloader_type = downloader_type
    return vo


@pytest.fixture
def fake_store():
    """伪 app.state.store，get_snapshot() 返回 VO 列表。

    测试用 store.get_snapshot = AsyncMock(return_value=[vo1, vo2]) 配置返回内容。
    """
    store = SimpleNamespace()
    store.get_snapshot = AsyncMock(return_value=[])
    return store


@pytest.fixture
def fake_app(fake_store):
    """伪 FastAPI 实例，带 state.store。"""
    app = SimpleNamespace()
    app.state = SimpleNamespace()
    app.state.store = fake_store
    return app
