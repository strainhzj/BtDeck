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
