# -*- coding: utf-8 -*-
"""W9 强制改密标志置位链路回归（生产事故后端半边重现）。

事故现象：部署最新代码后正常使用一段时间（存量会话靠 refresh token
存活，最长 7 天），重新登录即被锁死在 /#/settings?forceChange=1 且设置
页面无法进入（前端路由死锁，见 frontend tests/unit/
permission-force-change-deadlock.spec.ts）。

本文件重现后端半边因果链的源头一环：
- init_db 启动自检发现 admin 仍在用默认口令 "admin"（bcrypt 或旧
  AES-ECB(base64) 格式）→ 数据库 must_change_password 置 1
- 非默认口令不置位（不误伤正常用户）
- 登录响应下发该标志（死锁触发信号）已由
  test_login_throttle_and_change_password.py::
  test_login_response_carries_must_change_password 覆盖，此处不重复。
"""

import base64

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app.auth.models import User
from app.auth.security import get_password_hash, sm4_encrypt
from app.database import Base, init_db


@pytest.fixture()
def legacy_db(monkeypatch, tmp_path):
    """模拟"迁移已完成 + 已有 admin 账号"的存量部署库。

    - 内存 SQLite（StaticPool 单连接，与 init_db 各次 SessionLocal() 共享同一库）
    - monkeypatch app.database.SessionLocal 指向测试库，init_db 全程读写测试库
    - DATABASE_PATH 指向临时文件（init_db 的 WAL 段用 sqlite3 直连该路径）
    """
    # 注册 init_db 主段与各 seed 段涉及的 ORM 模型，create_all 模拟
    # "Alembic 迁移已完成、表结构齐备" 的存量库状态
    from app.downloader.models import BtDownloaders  # noqa: F401
    from app.torrents.models import TorrentInfo, TrackerInfo  # noqa: F401
    from app.torrents.audit_models import TorrentAuditLog  # noqa: F401
    from app.tasks.models import TaskLogs  # noqa: F401
    from app.tasks.cron_models import CronTask  # noqa: F401
    from app.models.setting_templates import SettingTemplate  # noqa: F401
    from app.models.torrent_tags import TorrentTag, TorrentTagRelation  # noqa: F401
    from app.models.notification import Notification  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    test_session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(database_module, "SessionLocal", test_session_factory)
    # settings.DATABASE_PATH 是读 os.getenv 的 property，setenv 即生效；
    # WAL 段用 sqlite3 直连该路径，指向临时文件避免触碰真实库
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "wal_target.db"))
    return test_session_factory


def _seed_admin(session_factory, password_hash):
    """插入存量 admin（must_change_password=0，即旧版本从未强制改密）。"""
    db = session_factory()
    db.add(
        User(
            id=1,
            username="admin",
            password=password_hash,
            is_active=True,
            must_change_password=False,
            two_factor_secret="JBSWY3DPEHPK3PXP",
        )
    )
    db.commit()
    db.close()


def _flag_of(session_factory):
    db = session_factory()
    try:
        user = db.query(User).filter(User.username == "admin").first()
        return bool(user.must_change_password)
    finally:
        db.close()


class TestStartupMarksForceChange:
    """init_db 启动自检对默认口令的置位行为。"""

    def test_default_password_bcrypt_marked(self, legacy_db):
        """存量库 admin 口令仍为默认 admin（bcrypt）→ 启动即置位。

        对应生产时间线：部署新版 → 容器启动 → 标志在部署当时就写入数据库；
        症状推迟到下一次登录（refresh token 过期后）才爆发。
        """
        _seed_admin(legacy_db, get_password_hash("admin"))

        init_db()

        assert _flag_of(legacy_db) is True

    def test_default_password_legacy_aes_marked(self, legacy_db):
        """更老的存量库：默认口令以旧 AES-ECB(base64) 格式存储 → 双读兼容同样置位。"""
        legacy_hash = sm4_encrypt(base64.b64encode("admin".encode("utf-8")).decode("utf-8"))
        _seed_admin(legacy_db, legacy_hash)

        init_db()

        assert _flag_of(legacy_db) is True

    def test_custom_password_not_marked(self, legacy_db):
        """负例：admin 已改用自定义强口令 → 启动自检不置位。"""
        _seed_admin(legacy_db, get_password_hash("MyStr0ng!Pass-2026"))

        init_db()

        assert _flag_of(legacy_db) is False

    def test_marking_is_idempotent_after_password_change(self, legacy_db):
        """改密清标志后再次重启：口令已非默认 → 不再回跳（幂等性闭环验证）。"""
        _seed_admin(legacy_db, get_password_hash("admin"))
        init_db()
        assert _flag_of(legacy_db) is True

        db = legacy_db()
        db.query(User).filter(User.id == 1).update(
            {"password": get_password_hash("NewPass-after-force"), "must_change_password": False}
        )
        db.commit()
        db.close()

        init_db()

        assert _flag_of(legacy_db) is False
