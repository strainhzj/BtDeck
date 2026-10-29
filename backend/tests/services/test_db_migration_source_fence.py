"""源 fence 与零写 oracle 测试（database-migration-ui W2-4，PLANS §5.2/§11 T03/T18）。

组件级覆盖（真 PG 集成见 tests/pg_integration/）：
- SQLite BEGIN IMMEDIATE fence 阻止新写者；release 后恢复可写；
- 指纹固定/漂移检测（verify_against 对拍历史指纹）；
- 零写 oracle：无写通过；**阳性对照**——同主键同计数 UPDATE 必须令 oracle
  失败（T18：同主键同计数 UPDATE 不能伪装成零写）；
- 异库断言：同路径/同 inode（硬链接）拒绝；显式 HANDOFF_SAME_DB 确认放行。
"""

from __future__ import annotations

import os
import sqlite3
import threading

import pytest

from app.services.db_migration.source_fence import (
    DistinctTargetError,
    SourceWriteOracle,
    SqliteSourceFence,
    assert_distinct_targets,
    load_table_names,
    pg_identity,
    sqlite_identity,
)

TABLES = ["t_a", "t_b"]


def _make_db(path, rows=(("k1", 1), ("k2", 2))):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t_a (k TEXT PRIMARY KEY, v INTEGER)")
    conn.execute("CREATE TABLE t_b (id INTEGER PRIMARY KEY, note TEXT)")
    for k, v in rows:
        conn.execute("INSERT INTO t_a VALUES (?, ?)", (k, v))
    conn.execute("INSERT INTO t_b VALUES (1, 'x')")
    conn.commit()
    conn.close()


class TestSqliteFence:
    def test_fence_blocks_writers_until_release(self, tmp_path):
        db = tmp_path / "src.db"
        _make_db(db)
        fence = SqliteSourceFence(str(db), TABLES)
        token = fence.acquire(timeout_seconds=2.0)
        assert token.dialect == "sqlite"
        blocked = {}

        def _try_write():
            conn = sqlite3.connect(str(db), timeout=0.3)
            try:
                conn.execute("INSERT INTO t_b VALUES (2, 'blocked')")
                conn.commit()
                blocked["ok"] = True
            except sqlite3.OperationalError:
                blocked["ok"] = False
            finally:
                conn.close()

        threading.Thread(target=_try_write).start()
        threading.Thread(target=_try_write).start() and None
        import time

        time.sleep(0.5)
        fence.release()
        assert blocked.get("ok") is False
        # 释放后可写
        conn = sqlite3.connect(str(db))
        conn.execute("INSERT INTO t_b VALUES (3, 'after')")
        conn.commit()
        conn.close()

    def test_fence_verify_stable_and_drift(self, tmp_path):
        db = tmp_path / "src.db"
        _make_db(db)
        fence = SqliteSourceFence(str(db), TABLES)
        fence.acquire()
        try:
            assert fence.verify() is True
            fingerprint = fence.token.fingerprint
        finally:
            fence.release()
        # 释放后外部写 → 重新取锁对拍历史指纹必须漂移
        conn = sqlite3.connect(str(db))
        conn.execute("INSERT INTO t_a VALUES ('k3', 3)")
        conn.commit()
        conn.close()
        fence2 = SqliteSourceFence(str(db), TABLES)
        fence2.acquire()
        try:
            assert fence2.verify_against(fingerprint) is False
        finally:
            fence2.release()

    def test_fence_only_lock_read_release(self, tmp_path):
        db = tmp_path / "src.db"
        _make_db(db)
        fence = SqliteSourceFence(str(db), TABLES)
        fence.acquire()
        try:
            # fence 连接可读（快照/指纹），写被拒（事务为 IMMEDIATE 也可写——
            # 纪律靠 API 面不暴露写方法；此处验证读可用）
            assert fence._conn is not None
            assert fence._conn.execute("SELECT COUNT(*) FROM t_a").fetchone()[0] == 2
        finally:
            fence.release()


class TestZeroWriteOracle:
    def test_zero_write_passes(self, tmp_path):
        db = tmp_path / "src.db"
        _make_db(db)
        oracle = SourceWriteOracle("sqlite", table_names=TABLES, sqlite_path=str(db))
        try:
            before = oracle.snapshot()
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            conn.close()
            after = oracle.snapshot()
            SourceWriteOracle.assert_zero_write(before, after)
        finally:
            oracle.close()

    def test_positive_control_same_key_same_count_update_fails(self, tmp_path):
        """T18 阳性对照：同主键同计数 UPDATE 必须令 oracle 失败。"""
        db = tmp_path / "src.db"
        _make_db(db)
        oracle = SourceWriteOracle("sqlite", table_names=TABLES, sqlite_path=str(db))
        try:
            before = oracle.snapshot()
            conn = sqlite3.connect(str(db))
            conn.execute("UPDATE t_a SET v = 999 WHERE k = 'k1'")  # 行数不变
            conn.commit()
            conn.close()
            after = oracle.snapshot()
            with pytest.raises(AssertionError):
                SourceWriteOracle.assert_zero_write(before, after)
        finally:
            oracle.close()

    def test_external_insert_fails(self, tmp_path):
        db = tmp_path / "src.db"
        _make_db(db)
        oracle = SourceWriteOracle("sqlite", table_names=TABLES, sqlite_path=str(db))
        try:
            before = oracle.snapshot()
            conn = sqlite3.connect(str(db))
            conn.execute("INSERT INTO t_b VALUES (9, 'x')")
            conn.commit()
            conn.close()
            after = oracle.snapshot()
            with pytest.raises(AssertionError):
                SourceWriteOracle.assert_zero_write(before, after)
        finally:
            oracle.close()


class TestDistinctTargets:
    def test_same_path_rejected(self, tmp_path):
        db = str(tmp_path / "a.db")
        with pytest.raises(DistinctTargetError):
            assert_distinct_targets(sqlite_identity(db), sqlite_identity(db))

    def test_hardlink_same_inode_rejected(self, tmp_path):
        a = tmp_path / "a.db"
        a.write_bytes(b"x")
        b = tmp_path / "b.db"
        os.link(a, b)  # 硬链接：同 inode
        with pytest.raises(DistinctTargetError):
            assert_distinct_targets(sqlite_identity(str(a)), sqlite_identity(str(b)))

    def test_distinct_paths_ok(self, tmp_path):
        a = tmp_path / "a.db"
        a.write_bytes(b"x")
        b = tmp_path / "b.db"
        b.write_bytes(b"y")
        assert_distinct_targets(sqlite_identity(str(a)), sqlite_identity(str(b)))

    def test_same_db_acknowledged_exception(self, tmp_path):
        a = tmp_path / "a.db"
        a.write_bytes(b"x")
        assert_distinct_targets(
            sqlite_identity(str(a)), sqlite_identity(str(a)), same_db_acknowledged=True
        )

    def test_pg_identity_normalizes(self):
        assert pg_identity("DB.example", 5432, "BtDeck") == pg_identity("db.EXAMPLE", 5432, "btdeck")
        assert pg_identity("h", 5432, "d1") != pg_identity("h", 5433, "d1")


def test_load_table_names_business_plus_protocol():
    names = load_table_names()
    assert len(names) == 45  # 42 业务 + 3 协议（W1-1 契约）
    assert "bt_database_identity" in names
    assert "bt_database_migration_receipt" in names
    assert "bt_database_migration_events" in names
    assert len(set(names)) == len(names)
