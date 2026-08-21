# -*- coding: utf-8 -*-
"""refresh_tokens 过期记录清理服务测试（令牌机制对抗审计修复）。

保护点：
- 只删"已过期/已撤销超过保留期"的记录，活跃与保留期内记录不动
- 表此前无任何清理路径，登录/续期各 +1 行无限增长
"""

import secrets
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import models
from app.auth.token_cleanup import DEFAULT_RETENTION_DAYS, cleanup_expired_refresh_tokens
from app.database import Base


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[models.RefreshToken.__table__])
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _add(db: Session, *, expires_delta=None, revoked_delta=None) -> int:
    now = datetime.utcnow()
    record = models.RefreshToken(
        user_id=1,
        token_hash=secrets.token_hex(32),
        expires_at=now + (expires_delta if expires_delta is not None else timedelta(days=7)),
    )
    if revoked_delta is not None:
        record.revoked_at = now + revoked_delta
    db.add(record)
    db.commit()
    return record.id


class TestCleanupExpiredRefreshTokens:
    def test_deletes_only_beyond_retention(self, db_session):
        def days_ago(days: int) -> timedelta:
            return -timedelta(days=days)

        active_id = _add(db_session)  # 活跃：未撤销未过期
        _add(db_session, expires_delta=days_ago(DEFAULT_RETENTION_DAYS + 10))  # 过期超期 → 删
        _add(db_session, revoked_delta=days_ago(DEFAULT_RETENTION_DAYS + 10))  # 撤销超期 → 删
        expired_recent_id = _add(db_session, expires_delta=-timedelta(days=2))  # 过期但保留期内
        revoked_recent_id = _add(db_session, revoked_delta=-timedelta(days=2))  # 撤销但保留期内

        deleted = cleanup_expired_refresh_tokens(db_session)

        assert deleted == 2
        remaining = {r.id for r in db_session.query(models.RefreshToken).all()}
        assert remaining == {active_id, expired_recent_id, revoked_recent_id}

    def test_noop_when_nothing_to_clean(self, db_session):
        _add(db_session)
        assert cleanup_expired_refresh_tokens(db_session) == 0
        assert db_session.query(models.RefreshToken).count() == 1

    def test_boundary_records_within_retention_kept(self, db_session):
        # 恰好在保留期边界（略小于保留天数）的记录保留
        _add(db_session, expires_delta=-timedelta(days=DEFAULT_RETENTION_DAYS - 1))
        assert cleanup_expired_refresh_tokens(db_session) == 0
