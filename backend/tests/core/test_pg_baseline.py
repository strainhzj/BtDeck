"""PG 基线初始化单元测试（v1.0.8 任务1.7 验收，契约 docs/postgresql-contract.md §3）。

不依赖真实 PG：pg_sync_engine 以 SQLite 文件库替身（SQLite 同样支持事务性 DDL，
可验证"create_all + stamp 同一事务"的原子性机制与三状态判定逻辑）。
必须用文件库而非内存库：initialize 的 finally 会 dispose 引擎，内存库随
连接关闭而销毁（真实 PG dispose 仅归还连接，数据在服务端持久）。
真实 PG 的空库初始化/重复启动/增量升级由 P4 强制 CI 覆盖（任务4.3）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.core import migration, pg_baseline
from app.core.pg_baseline import (
    IMPORT_STATE_TABLE,
    clear_import_state,
    get_import_state,
    initialize_pg_baseline,
    set_import_state,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def fake_pg_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Engine]:
    """SQLite 文件库替身（dispose 后数据仍持久，模拟 PG 生命周期语义）。

    事务性 DDL：pysqlite 传统隔离模式在 DDL 前隐式提交（驱动行为），导致回滚
    断言失真——用 Python 3.12+ 新式 ``autocommit=False``（DDL 参与事务，
    实测回滚生效；真实 PG 服务端原生支持事务性 DDL，无需此处理）。
    """
    import sqlite3

    path = tmp_path / "pg_baseline_test.db"

    def _connect() -> sqlite3.Connection:
        return sqlite3.connect(str(path), autocommit=False, check_same_thread=False)

    engine = create_engine(f"sqlite:///{path}", creator=_connect)
    monkeypatch.setattr(pg_baseline, "pg_sync_engine", lambda: engine)
    yield engine
    engine.dispose()


def _make_cfg() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


class TestBaselineAtomicity:
    """规则 3：create_all + stamp 同一连接同一事务；stamp 前故障整体回滚。"""

    def test_happy_path_creates_and_stamps(self, fake_pg_engine: Engine) -> None:
        assert initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4") is True
        with fake_pg_engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
            assert "alembic_version" in tables
            assert "torrent_info" in tables  # model_registry 注册的基线建表
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "c9e0f1a2b3c4"

    def test_stamp_failure_rolls_back_created_tables(self, fake_pg_engine: Engine) -> None:
        """建表后、stamp 前故障：事务回滚，无残留半成品（空库判定可重入）。"""
        with patch.object(command, "stamp", side_effect=RuntimeError("simulated crash before stamp")):
            with pytest.raises(RuntimeError, match="simulated crash"):
                initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4")
        with fake_pg_engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
            assert "torrent_info" not in tables, "create_all 产物必须随事务回滚"
            assert "alembic_version" not in tables

    def test_versioned_db_skips_baseline(self, fake_pg_engine: Engine) -> None:
        assert initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4") is True
        # 二次调用：已 versioned → 跳过基线（走增量路径）
        assert initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4") is False


class TestThreeStateRules:
    """契约 §3 目标库三状态判定。"""

    def test_import_in_progress_marker_refuses(self, fake_pg_engine: Engine) -> None:
        with fake_pg_engine.begin() as conn:
            set_import_state(conn, "mig-001", "digest-abc", "0.1.0", {"done": 3})
        with pytest.raises(RuntimeError, match="导入未完成"):
            initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4")

    def test_business_tables_without_version_refuses(self, fake_pg_engine: Engine) -> None:
        with fake_pg_engine.begin() as conn:
            conn.execute(text("CREATE TABLE manual_junk (id INTEGER PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match="无 alembic_version"):
            initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4")

    def test_import_state_roundtrip_and_clear(self, fake_pg_engine: Engine) -> None:
        with fake_pg_engine.begin() as conn:
            set_import_state(conn, "mig-002", "digest-def", "0.2.0", {"last_table": "torrent_info", "done": 42})
        with fake_pg_engine.connect() as conn:
            state = get_import_state(conn)
        assert state is not None
        assert state["migration_id"] == "mig-002"
        assert state["checkpoint"]["last_table"] == "torrent_info"
        with fake_pg_engine.begin() as conn:
            clear_import_state(conn)
        with fake_pg_engine.connect() as conn:
            assert get_import_state(conn) is None
            assert not inspect(conn).has_table(IMPORT_STATE_TABLE)


class TestManualUpgradeGuard:
    """任务3.1：PG 空库手工升级守卫（契约 §3 规则 6）。"""

    @staticmethod
    def _fake_conn() -> Any:
        class _Dialect:
            name = "postgresql"

        class _Conn:
            dialect = _Dialect()

        return _Conn()

    def test_empty_pg_db_rejected(self) -> None:
        with (
            patch.object(pg_baseline, "_is_alembic_versioned", return_value=False),
            patch.object(pg_baseline, "_business_table_names", return_value=[]),
        ):
            with pytest.raises(RuntimeError, match="禁止手工 alembic upgrade"):
                pg_baseline.guard_manual_upgrade_on_empty_db(self._fake_conn())

    def test_baseline_flag_exempts(self) -> None:
        with (
            patch.object(pg_baseline, "_is_alembic_versioned", return_value=False),
            patch.object(pg_baseline, "_business_table_names", return_value=[]),
        ):
            pg_baseline.guard_manual_upgrade_on_empty_db(self._fake_conn(), baseline_flag=True)  # 不抛

    def test_versioned_db_passes(self) -> None:
        with patch.object(pg_baseline, "_is_alembic_versioned", return_value=True):
            pg_baseline.guard_manual_upgrade_on_empty_db(self._fake_conn())

    def test_tables_without_version_passes_to_failfast(self) -> None:
        """有表无版本不在此守卫拦截（由 initialize 的 fail-fast 人工介入路径处理）。"""
        with (
            patch.object(pg_baseline, "_is_alembic_versioned", return_value=False),
            patch.object(pg_baseline, "_business_table_names", return_value=["some_table"]),
        ):
            pg_baseline.guard_manual_upgrade_on_empty_db(self._fake_conn())

    def test_sqlite_dialect_never_guarded(self) -> None:
        class _SqliteDialect:
            name = "sqlite"

        class _Conn:
            dialect = _SqliteDialect()

        pg_baseline.guard_manual_upgrade_on_empty_db(_Conn())  # 不抛、不触碰连接


class TestMigrateDatabasePgGuards:
    """任务3.2：_migrate_database_pg 编排行为（备份跳过/未知与 ghost 版本处理）。"""

    def test_unknown_version_warns_without_upgrade(
        self, fake_pg_engine: Engine, caplog: pytest.LogCaptureFixture
    ) -> None:
        """未知版本：告警不降级返回 True（与 SQLite 口径一致）；ghost 不在 PG stamp。"""
        from sqlalchemy import text as _text

        with fake_pg_engine.begin() as conn:
            # 模拟 ghost 版本（SQLite 历史快照遗留——PG 不应 stamp 救援）
            conn.execute(_text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(_text("INSERT INTO alembic_version VALUES ('9aea25308aff')"))
        with (
            patch.object(migration, "backup_before_migration") as backup_spy,
            patch.object(migration.logger, "warning") as warn_spy,
        ):
            # app.* 树 propagate=False（app/main.py），caplog 不可达——仓库既有 spy logger 模式
            assert migration._migrate_database_pg() is True
            backup_spy.assert_not_called()  # PG 无文件备份链（任务3.2：外部职责）
        assert any("不在当前代码迁移链" in str(c) for c in warn_spy.call_args_list)
        with fake_pg_engine.connect() as conn:
            version = conn.execute(_text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "9aea25308aff"  # ghost 未被 stamp（仅 sqlite 启用救援）

    def test_head_version_noop(self, fake_pg_engine: Engine) -> None:
        from sqlalchemy import text as _text

        with fake_pg_engine.begin() as conn:
            conn.execute(_text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(_text("INSERT INTO alembic_version VALUES ('c9e0f1a2b3c4')"))
        assert migration._migrate_database_pg() is True
