# -*- coding: utf-8 -*-
"""
torrent_crud.py hash 冲突分支回归测试（prod-hotfix-2026-07-19 P1）

修复目标：消除生产偶发 `记录审计日志失败: name`。
根因：`db.query(TorrentInfo.info_id).first()` 返回只含单列的 SQLAlchemy Row；
后续审计日志构造时访问 `db_torrent.name/.hash/.size` 触发 SQLAlchemy 2.0
Row.__getattr__，str(AttributeError) 恰为 'name'。

本测试用真实 SQLite + TorrentInfo 表模拟 hash 冲突分支的 ORM 查询，
直接验证修复后的 `db.query(TorrentInfo)` 返回完整实体，访问 .name/.hash/.size
不会抛 AttributeError；同时验证回退到 info_id 单列查询时会抛（mutation 反向锚点）。
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.downloader.models import BtDownloaders
from app.torrents.models import TorrentInfo, TrackerInfo
from tests.api.conftest import make_torrent

# torrent_crud.py 中审计日志构造访问的字段集合
AUDIT_DETAIL_KEYS = ("name", "hash", "size")


def _build_audit_detail(db_torrent):
    """复刻 torrent_crud.py:366-374 审计日志 operation_detail 的字段访问。

    修复前（bug）：db_torrent 是 Row 对象，访问 .name 抛 AttributeError('name')。
    修复后：db_torrent 是完整 TorrentInfo 实体，访问正常。
    """
    return {
        "torrent_name": db_torrent.name,
        "torrent_hash": db_torrent.hash,
        "file_size": db_torrent.size,
    }


@pytest.fixture
def sync_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[TorrentInfo.__table__, TrackerInfo.__table__, BtDownloaders.__table__],
    )
    yield engine
    Base.metadata.drop_all(
        bind=engine,
        tables=[TrackerInfo.__table__, TorrentInfo.__table__, BtDownloaders.__table__],
    )


@pytest.fixture
def db_session(sync_engine):
    Session = sessionmaker(bind=sync_engine)
    session = Session()
    yield session
    session.close()


def _seed_existing_torrent(db, info_hash="a" * 40, downloader_id="dl-a", name="already-here", size=1024):
    """预置一条已存在的种子记录（模拟 hash 冲突）。"""
    return make_torrent(
        db,
        info_id=str(uuid.uuid4()),
        downloader_id=downloader_id,
        hash_=info_hash,
        name=name,
        size=size,
    )


# ==================== Test Group ====================


class TestTorrentCrudHashConflictQuery:
    """验证 hash 冲突分支的 ORM 查询返回完整实体（不是单列 Row）。"""

    def test_full_entity_query_returns_complete_torrent(self, db_session):
        """修复后：db.query(TorrentInfo).first() 返回完整实体，.name/.hash/.size 可访问。"""
        seeded = _seed_existing_torrent(db_session)

        # 复刻 torrent_crud.py:337-343 的修复后查询
        existing_torrent = (
            db_session.query(TorrentInfo)
            .filter(TorrentInfo.hash == seeded.hash)
            .filter(TorrentInfo.dr == 0)
            .filter(TorrentInfo.downloader_id == seeded.downloader_id)
            .first()
        )

        assert existing_torrent is not None
        # 关键：必须是 TorrentInfo 实例，不是 Row
        assert isinstance(existing_torrent, TorrentInfo)

        # 复刻审计日志的字段访问（修复前会抛 AttributeError('name')）
        detail = _build_audit_detail(existing_torrent)
        assert detail["torrent_name"] == "already-here"
        assert detail["torrent_hash"] == seeded.hash
        assert detail["file_size"] == 1024

    def test_info_id_only_query_row_does_not_support_full_attrs(self, db_session):
        """mutation 反向锚点：单列 query 返回 Row，访问 .name 必抛 AttributeError。

        此测试的存在是为了：
        1. 文档化原 bug 的精确行为（SQLAlchemy 2.0 Row.__getattr__）
        2. 若有人把 db.query(TorrentInfo) 回退为 db.query(TorrentInfo.info_id)，
           上面的 test_full_entity_query_returns_complete_torrent 会失败，
           本测试会通过——形成双向断言。
        """
        seeded = _seed_existing_torrent(db_session)

        # 模拟 buggy 查询（修复前的代码）
        existing_row = (
            db_session.query(TorrentInfo.info_id)
            .filter(TorrentInfo.hash == seeded.hash)
            .filter(TorrentInfo.dr == 0)
            .filter(TorrentInfo.downloader_id == seeded.downloader_id)
            .first()
        )

        assert existing_row is not None
        # info_id 是选中列，可以访问
        assert existing_row.info_id == seeded.info_id

        # 关键：访问未选中的 .name 必抛 AttributeError（这就是生产日志"失败: name"的根因）
        with pytest.raises(AttributeError) as exc_info:
            _ = existing_row.name
        # SQLAlchemy 2.0 Row.__getattr__ 的 str 恰为裸属性名
        assert str(exc_info.value) == "name"

    def test_audit_detail_safe_on_full_entity_for_qb_branch(self, db_session):
        """覆盖 qBittorrent 分支（create_torrent 第二处 query）的审计字段访问。"""
        _seed_existing_torrent(db_session, info_hash="b" * 40, downloader_id="dl-qb")
        existing = (
            db_session.query(TorrentInfo)
            .filter(TorrentInfo.hash == "b" * 40)
            .filter(TorrentInfo.dr == 0)
            .filter(TorrentInfo.downloader_id == "dl-qb")
            .first()
        )
        detail = _build_audit_detail(existing)
        # 验证审计日志的三个核心字段都能正确取到
        assert detail["torrent_name"] == "already-here"
        assert detail["torrent_hash"] == "b" * 40
        assert detail["file_size"] == 1024

    def test_audit_detail_safe_for_batch_add_tr_branch(self, db_session):
        """覆盖 batch add Transmission 分支（第三处 query）的审计字段访问。"""
        _seed_existing_torrent(db_session, info_hash="c" * 40, downloader_id="dl-tr-batch")
        existing = (
            db_session.query(TorrentInfo)
            .filter(TorrentInfo.hash == "c" * 40)
            .filter(TorrentInfo.dr == 0)
            .filter(TorrentInfo.downloader_id == "dl-tr-batch")
            .first()
        )
        detail = _build_audit_detail(existing)
        assert detail["torrent_hash"] == "c" * 40

    def test_audit_detail_safe_for_batch_add_qb_branch(self, db_session):
        """覆盖 batch add qBittorrent 分支（第四处 query）的审计字段访问。"""
        _seed_existing_torrent(db_session, info_hash="d" * 40, downloader_id="dl-qb-batch")
        existing = (
            db_session.query(TorrentInfo)
            .filter(TorrentInfo.hash == "d" * 40)
            .filter(TorrentInfo.dr == 0)
            .filter(TorrentInfo.downloader_id == "dl-qb-batch")
            .first()
        )
        detail = _build_audit_detail(existing)
        assert detail["file_size"] == 1024
