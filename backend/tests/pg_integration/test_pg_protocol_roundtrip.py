"""真实 PG 双向回环集成测试（database-migration-ui W1-5，验收 T19/T12 的 CI 实证）。

门控同 test_pg_smoke（DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN；本地无 PG
自动 skip——skip 不登记为验收通过，证据以 CI pg-integration job 实际执行为准）。

T19：SQLite 源 →（run_sqlite_to_pg）→ 真 PG →（run_pg_to_sqlite）→ 新 SQLite：
- 全业务表 canonical 摘要全等（源 vs 最终产物）
- 身份/协议表不复制（三方 identity 互不相同；receipt/events 不随数据搬运）
- schema 对拍 + 空表自增探测 + FK 检查通过

T12：真 PG 源含 Float NaN/±Infinity 或时间 infinity → 预检拒绝且不建 staging。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

_ADMIN_DSN = os.getenv("BTDECK_PG_TEST_ADMIN_DSN", "")
pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "sqlite") != "postgresql" or not _ADMIN_DSN,
    reason="PG 集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]

from tests.pg_integration.test_pg_smoke import _make_cfg  # noqa: F401

from app.core import pg_baseline
from app.core.model_registry import register_all_models
from app.models.database_migration import business_tables
from app.services.db_migration import canonical, pipeline
from app.services.db_migration.pg_to_sqlite import pg_precheck, run_pg_to_sqlite
from app.services.db_migration.pipeline import PipelineContext
from app.services.db_migration.sqlite_to_pg import (
    PrecheckFailed,
    run_sqlite_to_pg,
    tool_head,
)
from app.services.db_migration.target_params import pg_engine, sqlite_engine


def _build_sqlite_source(path: Path) -> Path:
    """链头源库 + 样本（users 自增 / orphan_purge_job JSON 契约 / notification 空表）。"""
    import os as _os
    from alembic import command
    from app.core import config as _config

    _os.environ["DATABASE_PATH"] = str(path)
    original = _config.settings.DB_TYPE
    _config.settings.DB_TYPE = "sqlite"
    try:
        command.upgrade(_make_cfg(), "head")
    finally:
        _config.settings.DB_TYPE = original
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO users (username, password, two_factor_secret, two_factor_flag, is_active, created_at, must_change_password) "
        "VALUES (?,?,?,?,?,datetime('now'),0)",
        [(f"u{i}", "x", "s", 0, i % 2) for i in range(6)],
    )
    conn.execute(
        "INSERT INTO orphan_purge_job (task_id, status, operation_type, orphan_ids_json, canonical_paths_json, created_at, operator, total_count, updated_at) "
        "VALUES ('t1','pending','cleanup','[1,2]','[]',datetime('now'),'admin',2,datetime('now'))"
    )
    conn.execute(
        "INSERT INTO orphan_purge_job (task_id, status, operation_type, orphan_ids_json, canonical_paths_json, created_at, operator, total_count, updated_at) "
        "VALUES ('t2','pending','purge',NULL,'[\"/a\"]',datetime('now'),'admin',1,datetime('now'))"
    )
    conn.commit()
    conn.close()
    return path


def _business_digests_sqlite(db_path: Path) -> dict:
    register_all_models()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        digests = {}
        for table in business_tables():
            order = ", ".join(f'"{c.name}"' for c in table.primary_key.columns)
            rows = [
                {k: row[k] for k in row.keys()}
                for row in conn.execute(
                    f"SELECT * FROM {table.name} ORDER BY {order}" if order else f"SELECT * FROM {table.name}"
                )
            ]
            digests[table.name] = canonical.digest_rows(rows)
        return digests
    finally:
        conn.close()


class TestBidirectionalRoundtripT19:
    def test_sqlite_to_pg_to_sqlite_full_digest_equality(self, fresh_pg_db, tmp_path: Path) -> None:
        source = _build_sqlite_source(tmp_path / "src.db")
        source_digests = _business_digests_sqlite(source)

        ctx_fwd = PipelineContext(attempt_id=pipeline.make_attempt_id("sqlite-to-pg"))
        engine = pg_engine(_current_pg_params())
        try:
            result_fwd = run_sqlite_to_pg(str(source), pg_engine=engine, ctx=ctx_fwd)
            assert result_fwd["tables"] == len(business_tables())

            ctx_rev = PipelineContext(attempt_id=pipeline.make_attempt_id("pg-to-sqlite"))
            result_rev = run_pg_to_sqlite(engine, target_dir=tmp_path / "final", ctx=ctx_rev)
        finally:
            engine.dispose()

        final = Path(result_rev["final"])
        assert final.exists() and final.name.startswith("app.db.")

        # ① 全业务摘要全等（源 vs 最终产物——canonical-v1 跨库一致）
        final_digests = _business_digests_sqlite(final)
        assert final_digests == source_digests, "SQLite→PG→SQLite 全业务摘要必须全等"

        # ② 身份/协议表不复制：三方 identity 互不相同；receipt 只属于各自库
        source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        final_conn = sqlite3.connect(f"file:{final}?mode=ro", uri=True)
        try:
            source_identity = source_conn.execute("SELECT database_id FROM bt_database_identity").fetchone()[0]
            final_identity = final_conn.execute("SELECT database_id FROM bt_database_identity").fetchone()[0]
        finally:
            source_conn.close()
            final_conn.close()
        with pg_engine(_current_pg_params()).connect() as conn:
            pg_identity = pg_baseline.read_database_identity(conn)
        assert len({source_identity, final_identity, pg_identity}) == 3, "身份不可复制（§3.2）"
        with pg_engine(_current_pg_params()).connect() as conn:
            fwd_receipt = pg_baseline.read_receipt(conn, ctx_fwd.attempt_id)
        assert fwd_receipt is not None and fwd_receipt["status"] == "VERIFIED"
        final_conn = sqlite3.connect(f"file:{final}?mode=ro", uri=True)
        try:
            rev_status = final_conn.execute(
                "SELECT status FROM bt_database_migration_receipt WHERE attempt_id = ?", (ctx_rev.attempt_id,)
            ).fetchone()[0]
            marker = final_conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='_btdeck_import_state'"
            ).fetchone()[0]
        finally:
            final_conn.close()
        assert rev_status == "VERIFIED" and marker == 0

        # ③ 完整性 + FK + schema 版本
        probe = sqlite_engine(str(final))
        try:
            from sqlalchemy import inspect as sa_inspect

            with probe.connect() as conn:
                raw = conn.exec_driver_sql("PRAGMA integrity_check").scalar()
                fk_bad = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                version = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                tables = set(sa_inspect(conn).get_table_names())
            assert raw == "ok" and fk_bad == []
            assert version == tool_head()
            expected = (
                {t.name for t in business_tables()}
                | {"alembic_version"}
                | {
                    "bt_database_identity",
                    "bt_database_migration_receipt",
                    "bt_database_migration_events",
                }
            )
            assert tables == expected
        finally:
            probe.dispose()


def _current_pg_params():
    from app.core import config as config_mod

    from app.core.database_bootstrap import PostgresParams

    s = config_mod.settings
    return PostgresParams(
        host=s.DB_HOST,
        port=s.DB_PORT,
        user=s.DB_USER,
        password=s.DB_PASSWORD,
        database=s.DB_NAME,
        sslmode=s.DB_SSLMODE,
        ssl_root_cert=s.DB_SSL_ROOT_CERT,
    )


class TestNonFinitePrecheckT12:
    def test_nan_infinity_floats_and_times_rejected_before_target(self, fresh_pg_db, tmp_path: Path) -> None:
        # 源 PG：链头 schema + 污染行（NaN/Infinity float；infinity 时间）
        engine = pg_engine(_current_pg_params())
        try:
            with engine.begin() as conn:
                from app.core.model_registry import register_all_models as reg

                reg()
                from app.database import Base

                Base.metadata.create_all(conn)
                from alembic import command

                from app.core.migration import _build_alembic_config

                placeholder = str(BACKEND_ROOT / "config" / "replay.db")
                cfg = _build_alembic_config(placeholder)
                cfg.attributes["configure_logger"] = False
                cfg.attributes.pop("target_url", None)
                cfg.attributes["connection"] = conn
                try:
                    command.stamp(cfg, tool_head())
                finally:
                    cfg.attributes.pop("connection", None)
            from sqlalchemy import text

            # 污染行：Float NaN/Infinity（ratio CHECK 对 NaN 恒真，size 无约束）+ 时间 infinity
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO torrent_info (info_id, downloader_id, downloader_name, size, has_tracker_error) "
                        "VALUES ('nan-row', 'd1', 'dn1', 'NaN'::float8, false)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO torrent_info (info_id, downloader_id, downloader_name, size, has_tracker_error) "
                        "VALUES ('inf-row', 'd1', 'dn1', 'Infinity'::float8, false)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO search_templates (id, user_id, name, conditions, created_time) "
                        "VALUES ('t-inf', 'u1', 't', '[]', 'infinity'::timestamp)"
                    )
                )
            errors, _ = pg_precheck(engine)
            assert any("非有限值" in e for e in errors), errors
            assert any("infinity" in e for e in errors), errors
            # T12：预检拒绝即不建 staging（不产生任何目标副作用）
            ctx = PipelineContext(attempt_id=pipeline.make_attempt_id("pg-to-sqlite"))
            with pytest.raises(PrecheckFailed):
                run_pg_to_sqlite(engine, target_dir=tmp_path / "no-target", ctx=ctx)
            assert not (tmp_path / "no-target").exists() or not list((tmp_path / "no-target").glob("*.sqlite"))
        finally:
            engine.dispose()
