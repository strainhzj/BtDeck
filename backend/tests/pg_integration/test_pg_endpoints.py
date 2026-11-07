"""真实 PostgreSQL 端点语义回归（2026-10-27 PG 合并后补漏，v1.0.8 双方言收口）。

背景：downloader 限速设置保存与下载器列表布尔过滤两条链路的 raw SQL 位于
v1.0.8 P2 双方言审计面之外（PG 分支基点 c7bf20b 后的 dev 侧代码），
2026-10-27 全仓扫描抓出四类缺口并修复（详见 progress.md 2026-10-27 条目）：

1. ``downloader_settings`` 保存（创建+更新两分支）：
   - ISO 字符串时间绑 ``DateTime`` 列 → ``timestamp_parameter``（SQLite 文本/PG datetime）
   - raw INSERT 后 ``lastrowid`` 取自增 ID → ``RETURNING id``（psycopg2 无 OID 表恒 0、
     asyncpg 适配层无该属性，双驱动均不可用）
2. ``downloader`` 列表布尔过滤：
   - ``Boolean`` 列传 int 1/0（PG ``boolean = integer`` 无此 operator）
   - 布尔列 ``LIKE '%True%'``（PG 无 boolean~~text operator；SQLite 上亦为恒空过滤）
   → 统一等值 + ``bool`` 参数

本文件用与修复后端点**完全同形**的 SQL 在真实 PG 16 上锚定上述语义，
防止回退。SQLite 全量回归由既有 regression.yml backend job 覆盖。
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest

# 兄弟模块 fixture 经同目录 conftest.py 再导出（pytest 自动发现，无需显式 import）
from test_pg_smoke import _make_cfg  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "sqlite") != "postgresql" or not os.getenv("BTDECK_PG_TEST_ADMIN_DSN", ""),
    reason="PG 集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)

BASELINE_HEAD = "c9e0f1a2b3c4"


def _init_baseline() -> None:
    from app.core import pg_baseline
    from app.core.model_registry import register_all_models

    register_all_models()
    assert pg_baseline.initialize_pg_baseline(_make_cfg(), BASELINE_HEAD) is True


class TestDownloaderSettingsSave:
    """端点语义 1：限速设置保存（INSERT RETURNING + 时间参数双分支）。"""

    def test_insert_returning_and_timestamp_roundtrip(self, fresh_pg_db: str) -> None:
        from sqlalchemy import text

        from app.core.dialect_sql import timestamp_parameter
        from app.database import SessionLocal
        from app.downloader.models import BtDownloaders

        _init_baseline()
        dl_id = f"pg_dl_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(BtDownloaders(downloader_id=dl_id, nickname="pg-endpoint-probe"))
            db.commit()

            # —— 与 endpoints/downloader_settings.py 修复后同形：timestamp_parameter + RETURNING id ——
            current_time = timestamp_parameter(datetime.now())
            insert_sql = """
                INSERT INTO downloader_settings
                (downloader_id, dl_speed_limit, ul_speed_limit, dl_speed_unit, ul_speed_unit,
                 enable_schedule, username, password, advanced_settings, override_local,
                 created_at, updated_at)
                VALUES
                (:downloader_id, :dl_speed_limit, :ul_speed_limit, :dl_speed_unit, :ul_speed_unit,
                 :enable_schedule, :username, :password, :advanced_settings, :override_local,
                 :created_at, :updated_at)
                RETURNING id
                """
            setting_id = db.execute(
                text(insert_sql),
                {
                    "downloader_id": dl_id,
                    "dl_speed_limit": 1024,
                    "ul_speed_limit": 2048,
                    "dl_speed_unit": "KB_PER_SEC",
                    "ul_speed_unit": "KB_PER_SEC",
                    "enable_schedule": False,
                    "username": "u",
                    "password": "sm4-ciphertext",
                    "advanced_settings": None,
                    "override_local": False,
                    "created_at": current_time,
                    "updated_at": current_time,
                },
            ).scalar()
            db.commit()
            # PG 上必须取回真实自增 ID（原 lastrowid 缺口：psycopg2 无 OID 表恒 0）
            assert isinstance(setting_id, int) and setting_id > 0

            # DateTime 列读回须为 datetime（证明时间绑定/存储形态正确，非字符串残留）
            row = db.execute(
                text("SELECT created_at, updated_at FROM downloader_settings WHERE id = :i"),
                {"i": setting_id},
            ).fetchone()
            assert isinstance(row.created_at, datetime) and isinstance(row.updated_at, datetime)

            # 更新分支同形：updated_at 走 timestamp_parameter
            db.execute(
                text("UPDATE downloader_settings SET updated_at = :t WHERE id = :i"),
                {"t": timestamp_parameter(datetime.now()), "i": setting_id},
            )
            db.commit()
        finally:
            db.close()


class TestDownloaderListBooleanFilter:
    """端点语义 2：下载器列表布尔过滤（等值 + bool 参数）。"""

    def test_enabled_equality_filter_bool_param(self, fresh_pg_db: str) -> None:
        from sqlalchemy import text

        from app.database import SessionLocal
        from app.downloader.models import BtDownloaders

        _init_baseline()
        suffix = uuid.uuid4().hex[:8]
        on_id, off_id = f"pg_dl_on_{suffix}", f"pg_dl_off_{suffix}"
        db = SessionLocal()
        try:
            db.add(BtDownloaders(downloader_id=on_id, nickname=f"on-{suffix}", enabled=True))
            db.add(BtDownloaders(downloader_id=off_id, nickname=f"off-{suffix}", enabled=False))
            db.commit()

            # —— 与 endpoints/downloader.py 修复后同形：布尔列等值 + bool 参数（原 1/0 整型在 PG 上
            #    boolean = integer 无此 operator；LIKE '%True%' 直接报错）——
            sql = """
                SELECT downloader_id, nickname
                FROM bt_downloaders
                WHERE dr = 0 AND enabled = :enabled
                ORDER BY nickname ASC
                """
            rows = db.execute(text(sql), {"enabled": True}).fetchall()
            got = {r.downloader_id for r in rows}
            assert on_id in got and off_id not in got

            rows_false = db.execute(text(sql), {"enabled": False}).fetchall()
            got_false = {r.downloader_id for r in rows_false}
            assert off_id in got_false and on_id not in got_false
        finally:
            db.close()


class TestUserChangePassword:
    """端点语义 3：改密 users.must_change_password 布尔写入（2026-11-07 实机抓出）。

    原 raw SQL 整数字面量 ``must_change_password=0`` 在 PG 报 DatatypeMismatch
    （boolean = integer 无此 operator；SQLite 容忍故全量回归不红）——强制改密
    流程在 PG 部署下完全不可用。修复为 bool 参数绑定（Boolean bind_processor
    双方言落值：SQLite→0 / PG→false）。本测试经端点函数直调在真实 PG 上锚定。
    """

    def test_change_password_bool_param_roundtrip(self, fresh_pg_db: str) -> None:
        import base64
        from types import SimpleNamespace

        from app.api.endpoints import cuser
        from app.api.endpoints.cuser import ChangePasswordRequest
        from app.auth import security
        from app.auth.models import User
        from app.database import SessionLocal

        _init_baseline()
        suffix = uuid.uuid4().hex[:8]
        username = f"pg_chg_{suffix}"
        old_password = f"Old-{suffix}-pass"
        new_password = f"New-{suffix}-pass"
        db = SessionLocal()
        try:
            user = User(
                username=username,
                password=security.get_password_hash(old_password),
                must_change_password=True,
            )
            db.add(user)
            db.commit()
            user_id = user.id
        finally:
            db.close()

        payload = ChangePasswordRequest(
            oldPassword=base64.b64encode(old_password.encode()).decode(),
            newPassword=base64.b64encode(new_password.encode()).decode(),
            userId=str(user_id),  # 端点绑定 token 用户，body userId 仅契约占位
        )
        user_info = SimpleNamespace(user_id=user_id, username=username)
        response = cuser.change_password(payload, user_info, SessionLocal())
        assert response.status == "success", response.msg

        db = SessionLocal()
        try:
            row = db.query(User).filter(User.id == user_id).first()
            # PG 读回须为原生 False（布尔语义正确，非整型残留）
            assert row.must_change_password is False
            assert security.verify_password(new_password, row.password)
            # 原密码不再通过校验
            assert not security.verify_password(old_password, row.password)
        finally:
            db.close()


class TestDownloaderSettingsBoolBinding:
    """端点语义 4：保存设置布尔请求值归一（2026-11-07 双方言审计 B-1~B-4）。

    该端点直接消费原始 JSON dict（无 Pydantic 校验）：enable_schedule /
    override_local / 规则 enabled 发整型 1 时，旧实现将 int 直通 raw SQL 绑定
    → PG 42804 DatatypeMismatch（boolean=integer 无此 operator；官方前端发
    bool 不触发，第三方客户端踩雷）。bool() 归一后经 Boolean bind_processor
    落 PG 原生 boolean。
    """

    async def test_save_with_integer_bool_payload(self, fresh_pg_db: str) -> None:
        from types import SimpleNamespace

        from sqlalchemy import text

        from app.api.endpoints.downloader_settings import (
            get_downloader_settings,
            update_downloader_settings,
        )
        from app.database import SessionLocal
        from app.downloader.models import BtDownloaders

        _init_baseline()
        dl_id = f"pg_dl_bool_{uuid.uuid4().hex[:8]}"
        db = SessionLocal()
        try:
            db.add(BtDownloaders(downloader_id=dl_id, nickname=f"bool-{uuid.uuid4().hex[:6]}", enabled=True))
            db.commit()
        finally:
            db.close()

        # 整型布尔载荷（旧实现此处 int 直通 → PG 42804；官方前端发 bool 不触发）
        payload = {
            "dlSpeedLimit": 1024,
            "dlSpeedUnit": 1,
            "enableSchedule": 1,
            "overrideLocal": 1,
            "schedule_rules": [
                {
                    "start_time": "09:00",
                    "end_time": "18:00",
                    "weekdays": [0, 1, 2],
                    "enabled": 1,
                    "download": {"enabled": True, "speed_limit": 2048, "speed_unit": 0},
                    "upload": {"enabled": True, "speed_limit": 256, "speed_unit": 0},
                },
                {
                    "start_time": "18:00",
                    "end_time": "23:00",
                    "weekdays": [5, 6],
                    "enabled": 0,
                    "download": {"enabled": False, "speed_limit": 100, "speed_unit": 0},
                    "upload": {"enabled": False, "speed_limit": 50, "speed_unit": 0},
                },
            ],
        }

        class _FakeRequest:
            def __init__(self, body: dict) -> None:
                self._body = body

            async def json(self) -> dict:
                return self._body

        response = await update_downloader_settings(
            _FakeRequest(payload),
            dl_id,
            SessionLocal(),
            SimpleNamespace(username="pg-tester"),
        )
        assert response.code == "200", f"msg={response.msg}"

        # 修复前：raw SQL 绑定 int → PG 42804 直接 500，以下读回不可达；
        # 修复后：bool 归一经 Boolean 列落 PG 原生 boolean
        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT enable_schedule, override_local, dl_speed_unit "
                    "FROM downloader_settings WHERE downloader_id = :d"
                ),
                {"d": dl_id},
            ).fetchone()
            assert row.enable_schedule is True
            assert row.override_local is True
            # 枚举列写入标签（int 直通在 PG speedunitenum 上 42804——本测试首跑在 CI 抓出）
            assert row.dl_speed_unit == "MB_PER_SEC"
            rules = db.execute(
                text(
                    "SELECT enabled FROM speed_schedule_rules "
                    "WHERE downloader_setting_id IN (SELECT id FROM downloader_settings WHERE downloader_id = :d) "
                    "ORDER BY start_time"
                ),
                {"d": dl_id},
            ).fetchall()
            assert [r.enabled for r in rules] == [True, False]
        finally:
            db.close()

        # GET 读侧经 from_value 归一回前端契约 int（兼容 PG 标签与存量 int）
        got = await get_downloader_settings(dl_id, SessionLocal(), None)
        assert got.code == "200", f"msg={got.msg}"
        assert got.data["dl_speed_unit"] == 1
        assert got.data["ul_speed_unit"] == 0
