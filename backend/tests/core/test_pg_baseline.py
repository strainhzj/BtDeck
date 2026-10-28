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
    # 测试分层（database-migration-ui W1-2 复核意见 7）：本 fixture 用 SQLite 替身
    # 验证**引擎无关**的事务性/状态机逻辑；生产方言强断言
    # assert_postgresql_target 保持严格，由 T14 守卫用例与 CI 真 PG 集成覆盖
    monkeypatch.setattr(pg_baseline, "assert_postgresql_target", lambda target: None)
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
            patch.object(pg_baseline, "read_pg_alembic_version", return_value=None),
            patch.object(pg_baseline, "_business_table_names", return_value=[]),
        ):
            with pytest.raises(RuntimeError, match="禁止手工 alembic upgrade"):
                pg_baseline.guard_manual_upgrade_on_empty_db(self._fake_conn())

    def test_baseline_flag_exempts(self) -> None:
        with (
            patch.object(pg_baseline, "read_pg_alembic_version", return_value=None),
            patch.object(pg_baseline, "_business_table_names", return_value=[]),
        ):
            pg_baseline.guard_manual_upgrade_on_empty_db(self._fake_conn(), baseline_flag=True)  # 不抛

    def test_versioned_db_passes(self) -> None:
        with patch.object(pg_baseline, "read_pg_alembic_version", return_value="c9e0f1a2b3c4"):
            pg_baseline.guard_manual_upgrade_on_empty_db(self._fake_conn())

    def test_tables_without_version_refused(self) -> None:
        """CLI 也必须在重放历史迁移前拒绝来源不明的库。"""
        with (
            patch.object(pg_baseline, "read_pg_alembic_version", return_value=None),
            patch.object(pg_baseline, "_business_table_names", return_value=["some_table"]),
        ):
            with pytest.raises(RuntimeError, match="禁止手工 alembic upgrade"):
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

    def test_head_version_noop(self, fake_pg_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
        from sqlalchemy import text as _text
        from tests.core.alembic_head import current_head

        with fake_pg_engine.begin() as conn:
            conn.execute(_text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(_text("INSERT INTO alembic_version VALUES ('%s')" % current_head()))

        # 最终版本回读确定性路由到 fake 引擎：避免环境方言为 sqlite 时
        # _read_db_version_dispatch 走文件路径读到无关库（本用例只验证 PG 编排分支）
        def _dispatch_from_fake(db_path: str):
            from app.core.pg_baseline import read_pg_alembic_version

            with fake_pg_engine.connect() as conn:
                return read_pg_alembic_version(conn)

        monkeypatch.setattr(migration, "_read_db_version_dispatch", _dispatch_from_fake)
        assert migration._migrate_database_pg() is True


@pytest.mark.parametrize("version, rejected", [((15, 9), True), ((16, 0), False), ((17, 1), False)])
def test_minimum_pg_version(version, rejected):
    from types import SimpleNamespace

    conn = SimpleNamespace(dialect=SimpleNamespace(name="postgresql", server_version_info=version))
    if rejected:
        with pytest.raises(RuntimeError, match="16"):
            pg_baseline.validate_pg_server(conn)
    else:
        pg_baseline.validate_pg_server(conn)


def test_empty_version_table_refuses_baseline(fake_pg_engine):
    with fake_pg_engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    with pytest.raises(RuntimeError, match="alembic_version 为空"):
        initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4")


# ==============================================================================
# database-migration-ui W1-2：引擎显式参数化 / 方言强断言（T14）/ identity /
# IMPORTING receipt / finalize 原子性 / ownership 核对（PLANS §3.2/§3.3）
# ==============================================================================

_W1_ATTEMPT = "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def _ownership(attempt_id: str = _W1_ATTEMPT) -> dict:
    """完整 ownership 请求样例（target_database_id 由基线注入实际身份）。"""
    return {
        "attempt_id": attempt_id,
        "operation_kind": "MIGRATE",
        "source_database_id": "11111111-1111-1111-1111-111111111111",
        "ownership_nonce": "nonce-abc123",
        "revision_at_import": "rev-x",
        "schema_fingerprint": "fp-sha256",
        "origin_epoch": "epoch-1",
        "eligible_epoch": "epoch-1",
        "deployment_id": "deploy-1",
    }


class TestDialectGuardT14:
    """T14：PG 专用初始化误收 SQLite 引擎在任何 DDL 前拒绝。"""

    def test_sqlite_engine_rejected_before_any_ddl(self, tmp_path):
        """无任何补丁的真实 sqlite 引擎 → 进基线即拒，库文件零表。"""
        from sqlalchemy import create_engine

        engine = create_engine(f"sqlite:///{tmp_path / 'wrong.db'}")
        try:
            with pytest.raises(RuntimeError, match="非 postgresql 引擎.*T14"):
                initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4", engine=engine)
        finally:
            engine.dispose()
        import sqlite3

        conn = sqlite3.connect(tmp_path / "wrong.db")
        try:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        finally:
            conn.close()
        assert tables == [], "DDL 前拒绝：不得产生任何表"

    def test_guard_is_module_entry_not_configurable(self):
        """守卫无豁免参数（防生产后门）：函数签名不含任何开关。"""
        import inspect

        params = inspect.signature(pg_baseline.assert_postgresql_target).parameters
        assert list(params) == ["target"], "方言强断言不得引入跳过开关"


class TestBaselineIdentityAndReceipt:
    """基线同事务生成目标自身 identity；迁移基线写 IMPORTING receipt+marker。"""

    def test_plain_baseline_creates_own_identity_no_receipt(self, fake_pg_engine):
        """普通 PG 新装：schema + 自身身份，无 receipt（复核意见 2 分流）。"""
        assert initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4") is True
        with fake_pg_engine.connect() as conn:
            identity = conn.execute(text("SELECT id, database_id FROM bt_database_identity")).first()
            receipts = conn.execute(text("SELECT COUNT(*) FROM bt_database_migration_receipt")).scalar()
        assert identity is not None and identity[0] == 1 and len(identity[1]) == 36
        assert receipts == 0, "普通新装不得产生迁移凭据"

    def test_migration_baseline_writes_importing_receipt_and_marker(self, fake_pg_engine):
        """迁移基线：首表导入前即持久 IMPORTING receipt + 初始 marker（T02）。"""
        marker = {
            "migration_id": "sqlite-deadbeef",
            "source_digest": "digest-1",
            "tool_version": "2.0.0",
            "checkpoint": {"completed": {}},
        }
        assert initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4", import_state=marker, ownership=_ownership())
        with fake_pg_engine.connect() as conn:
            receipt = pg_baseline.read_receipt(conn, _W1_ATTEMPT)
            identity = conn.execute(text("SELECT database_id FROM bt_database_identity")).scalar()
            marker_state = pg_baseline.get_import_state(conn)
        assert receipt is not None
        assert receipt["status"] == "IMPORTING"
        assert receipt["ownership_nonce"] == "nonce-abc123"
        assert receipt["origin_epoch"] == "epoch-1" and receipt["eligible_epoch"] == "epoch-1"
        # target_database_id = 基线注入的目标自身身份（不是源身份）
        assert receipt["target_database_id"] == identity
        assert receipt["source_database_id"] == "11111111-1111-1111-1111-111111111111"
        assert receipt["digest_version"] == "btdeck-canonical-v1"
        assert marker_state is not None and marker_state["migration_id"] == "sqlite-deadbeef"

    def test_baseline_failure_rolls_back_receipt_and_identity(self, fake_pg_engine, monkeypatch):
        """stamp 故障：create_all/identity/receipt/marker 整体回滚（原子性延伸）。"""
        from unittest.mock import patch

        marker = {
            "migration_id": "m",
            "source_digest": "d",
            "tool_version": "2.0.0",
            "checkpoint": {"completed": {}},
        }
        with patch.object(pg_baseline.command, "stamp", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4", import_state=marker, ownership=_ownership())
        with fake_pg_engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
        assert "torrent_info" not in tables, "create_all 产物随事务回滚"
        assert "bt_database_identity" not in tables, "identity/receipt 随事务回滚"

    def test_ownership_validation_rejects_incomplete_or_bad_attempt(self, fake_pg_engine):
        bad = _ownership()
        bad["attempt_id"] = "../escape"
        with pytest.raises(RuntimeError, match="attempt_id 形态非法"):
            initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4", ownership=bad)
        incomplete = {k: v for k, v in _ownership().items() if k != "ownership_nonce"}
        with pytest.raises(RuntimeError, match="缺少必填字段"):
            initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4", ownership=incomplete)


class TestReceiptOperations:
    """receipt 读/核对/finalize/失效标记（Core 协议操作）。"""

    def _prepare(self, fake_pg_engine) -> str:
        """造一个带 IMPORTING receipt + marker 的基线库，返回目标 database_id。"""
        marker = {
            "migration_id": "m",
            "source_digest": "d",
            "tool_version": "2.0.0",
            "checkpoint": {"completed": {}},
        }
        assert initialize_pg_baseline(_make_cfg(), "c9e0f1a2b3c4", import_state=marker, ownership=_ownership())
        with fake_pg_engine.connect() as conn:
            return conn.execute(text("SELECT database_id FROM bt_database_identity")).scalar()

    def test_finalize_receipt_verified_clears_marker_same_tx(self, fake_pg_engine):
        self._prepare(fake_pg_engine)
        with fake_pg_engine.begin() as conn:
            pg_baseline.finalize_receipt_verified(
                conn,
                _W1_ATTEMPT,
                table_counts={"users": 5},
                table_digests={"users": "sha256-x"},
                schema_fingerprint="fp-sha256",
            )
        with fake_pg_engine.connect() as conn:
            receipt = pg_baseline.read_receipt(conn, _W1_ATTEMPT)
            marker_exists = inspect(conn).has_table(pg_baseline.IMPORT_STATE_TABLE)
        assert receipt["status"] == "VERIFIED"
        assert receipt["table_counts"] == {"users": 5}
        assert receipt["table_digests"] == {"users": "sha256-x"}
        assert marker_exists is False, "finalize 同事务清除未完成标记"

    def test_finalize_rejects_missing_or_repeated(self, fake_pg_engine):
        self._prepare(fake_pg_engine)
        # 不存在的 attempt
        with fake_pg_engine.begin() as conn:
            with pytest.raises(RuntimeError, match="receipt 不存在"):
                pg_baseline.finalize_receipt_verified(
                    conn,
                    "pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                    table_counts={},
                    table_digests={},
                    schema_fingerprint="fp",
                )
        # 先 finalize 成功，再重复 finalize → 拒绝
        with fake_pg_engine.begin() as conn:
            pg_baseline.finalize_receipt_verified(
                conn, _W1_ATTEMPT, table_counts={}, table_digests={}, schema_fingerprint="fp"
            )
        with fake_pg_engine.begin() as conn:
            with pytest.raises(RuntimeError, match="非 IMPORTING"):
                pg_baseline.finalize_receipt_verified(
                    conn, _W1_ATTEMPT, table_counts={}, table_digests={}, schema_fingerprint="fp"
                )

    def test_verify_receipt_ownership_mismatch_rejected(self, fake_pg_engine):
        db_id = self._prepare(fake_pg_engine)
        with fake_pg_engine.connect() as conn:
            ok = pg_baseline.verify_receipt_ownership(
                conn, _W1_ATTEMPT, ownership_nonce="nonce-abc123", target_database_id=db_id
            )
            assert ok["status"] == "IMPORTING"
            with pytest.raises(RuntimeError, match="ownership_nonce 不匹配"):
                pg_baseline.verify_receipt_ownership(
                    conn, _W1_ATTEMPT, ownership_nonce="wrong", target_database_id=db_id
                )
            with pytest.raises(RuntimeError, match="目标 database_id 不匹配"):
                pg_baseline.verify_receipt_ownership(
                    conn,
                    _W1_ATTEMPT,
                    ownership_nonce="nonce-abc123",
                    target_database_id="00000000-0000-0000-0000-000000000000",
                )
            with pytest.raises(RuntimeError, match="operation_kind 不匹配"):
                pg_baseline.verify_receipt_ownership(
                    conn,
                    _W1_ATTEMPT,
                    ownership_nonce="nonce-abc123",
                    target_database_id=db_id,
                    operation_kind="HANDOFF_SAME_DB",
                )
            with pytest.raises(RuntimeError, match="receipt 不存在"):
                pg_baseline.verify_receipt_ownership(
                    conn,
                    "handoff/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                    ownership_nonce="x",
                    target_database_id=db_id,
                )

    def test_mark_receipt_status_only_terminal_states(self, fake_pg_engine):
        self._prepare(fake_pg_engine)
        with fake_pg_engine.begin() as conn:
            with pytest.raises(RuntimeError, match="仅接受 STALE/ABANDONED"):
                pg_baseline.mark_receipt_status(conn, _W1_ATTEMPT, "VERIFIED")
            pg_baseline.mark_receipt_status(conn, _W1_ATTEMPT, "ABANDONED", eligible_epoch="epoch-2")
        with fake_pg_engine.connect() as conn:
            receipt = pg_baseline.read_receipt(conn, _W1_ATTEMPT)
        assert receipt["status"] == "ABANDONED"
        assert receipt["eligible_epoch"] == "epoch-2"
        with fake_pg_engine.begin() as conn:
            with pytest.raises(RuntimeError, match="receipt 不存在"):
                pg_baseline.mark_receipt_status(conn, "handoff/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", "STALE")

    def test_insert_receipt_duplicate_refused(self, fake_pg_engine):
        db_id = self._prepare(fake_pg_engine)
        with fake_pg_engine.begin() as conn:
            with pytest.raises(RuntimeError, match="拒绝重复创建"):
                pg_baseline.insert_importing_receipt(conn, {**_ownership(), "target_database_id": db_id})
