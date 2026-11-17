"""真实 PG sequence 校准边界（复核修复批 W3，CI 实库实证）。

源 SQLite 允许显式 ``id=0``（合法）：``calibrate_sequences`` 不得对 PG 序列
``setval(seq, 0)``——超序列下界必炸 NumericValueOutOfRange（W4 真 PG 探针实抓，
forward 迁移对含 id=0 行的库确定性失败）；修复为等价空表语义
``setval(seq, 1, false)``，下次自增从 1 起。

门控同 test_pg_smoke（DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN）。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

_ADMIN_DSN = os.getenv("BTDECK_PG_TEST_ADMIN_DSN", "")
pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "sqlite") != "postgresql" or not _ADMIN_DSN,
    reason="PG 集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)


def test_calibrate_sequences_handles_max_zero(fresh_pg_db) -> None:  # noqa: F811 - fixture 再导出
    from app.downloader.models import BtDownloaders
    from app.models.downloader_settings import DownloaderSetting
    from app.core.model_registry import register_all_models
    from app.services.db_migration.sqlite_to_pg import calibrate_sequences

    register_all_models()
    engine = create_engine(fresh_pg_db)
    try:
        BtDownloaders.__table__.create(engine)
        DownloaderSetting.__table__.create(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO bt_downloaders (downloader_id) VALUES ('d1')"))
            conn.execute(text("INSERT INTO downloader_settings (id, downloader_id) VALUES (0, 'd1')"))

        calibrated = calibrate_sequences(engine)
        assert any(row.startswith("downloader_settings.id→max0") for row in calibrated), calibrated

        # 下次自增从 1 起（等价空表语义）
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO downloader_settings (downloader_id) VALUES ('d2')"))
            new_id = conn.execute(text("SELECT MAX(id) FROM downloader_settings")).scalar()
        assert new_id == 1, f"自增应从 1 起，实得 {new_id!r}"
    finally:
        engine.dispose()
