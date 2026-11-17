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
from sqlalchemy.pool import NullPool

_ADMIN_DSN = os.getenv("BTDECK_PG_TEST_ADMIN_DSN", "")
pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "sqlite") != "postgresql" or not _ADMIN_DSN,
    reason="PG 集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)


def test_calibrate_sequences_handles_max_zero(fresh_pg_db: str) -> None:  # noqa: F811 - fixture 再导出
    """fresh_pg_db yield 裸库名（非 URL）——经 make_url 换 database 分量成完整 DSN。

    （run 44013492510 教训：本地 skip 只在 CI 暴露的确定性 fixture 误用。）
    """
    from sqlalchemy.engine.url import make_url

    from app.downloader.models import BtDownloaders
    from app.models.downloader_settings import DownloaderSetting
    from app.services.db_migration.sqlite_to_pg import calibrate_sequences

    url = make_url(_ADMIN_DSN).set(database=fresh_pg_db)
    engine = create_engine(url.render_as_string(hide_password=False), poolclass=NullPool)
    try:
        BtDownloaders.__table__.create(engine)
        DownloaderSetting.__table__.create(engine)
        with engine.begin() as conn:
            # core table.insert() 会应用 Column 级 default（downloader_type/dl_speed_unit 等
            # NOT NULL 无 server_default 列）；裸 text() INSERT 绕过 ORM 默认值，
            # 真 PG NOT NULL 硬约束即拒（run 44015948169 实抓）
            conn.execute(BtDownloaders.__table__.insert().values(downloader_id="d1"))
            conn.execute(DownloaderSetting.__table__.insert().values(id=0, downloader_id="d1"))

        calibrated = calibrate_sequences(engine)
        assert any(row.startswith("downloader_settings.id→max0") for row in calibrated), calibrated

        # 下次自增从 1 起（等价空表语义；真 PG 强制 FK——先补 d2 父行，SQLite 不强制
        # 所以 W4 探针未暴露此层，run 44019301194 实抓）
        with engine.begin() as conn:
            conn.execute(BtDownloaders.__table__.insert().values(downloader_id="d2"))
            conn.execute(DownloaderSetting.__table__.insert().values(downloader_id="d2"))
            new_id = conn.execute(text("SELECT MAX(id) FROM downloader_settings")).scalar()
        assert new_id == 1, f"自增应从 1 起，实得 {new_id!r}"
    finally:
        engine.dispose()
