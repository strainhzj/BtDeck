# -*- coding: utf-8 -*-
"""
sync_checkpoints 迁移往返测试（W3-2，PLANS/sync-database-blocking-remediation.md）

验证目标：
1. 空库 upgrade head → sync_checkpoints 表存在（列/唯一约束/索引核对）；
   downgrade -1 → 表不存在；再次 upgrade → 表恢复（往返完整可回滚）。
2. 从当前生产近似 Schema（旧 head d8e9f0a1b2c3）升级到新 head：
   历史 task_logs 数据可读，新增表不影响既有业务表。

与 tests/core/test_db_migration.py 同款编程式 Alembic Config 模式。
"""

import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

# backend/ 目录（alembic.ini 所在位置）
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

# 本任务新增迁移链头；旧 head（生产近似 Schema）
NEW_HEAD = "3a4b5c6d7e8f"
OLD_HEAD = "d8e9f0a1b2c3"

# sync_checkpoints 期望列（顺序无关）
EXPECTED_COLUMNS = {
    "id",
    "downloader_id",
    "sync_type",
    "cursor_value",
    "cycle_started_at",
    "last_full_sync_at",
    "last_success_at",
    "last_attempt_at",
    "outcome",
    "detail_json",
    "version",
    "created_at",
    "updated_at",
}
_UNIQUE_NAME = "uq_sync_checkpoints_downloader_sync_type"
_INDEX_DOWNLOADER = "ix_sync_checkpoints_downloader_id"
_INDEX_SYNC_TYPE = "ix_sync_checkpoints_sync_type"


@pytest.fixture(autouse=True)
def _clean_database_path_env():
    """自动清理 DATABASE_PATH 环境变量，防止跨测试污染（与 test_db_migration 一致）。"""
    old = os.environ.pop("DATABASE_PATH", None)
    yield
    if old is not None:
        os.environ["DATABASE_PATH"] = old
    else:
        os.environ.pop("DATABASE_PATH", None)


def _make_alembic_config(db_path: str) -> Config:
    """构造指向指定 DB 的 Alembic Config（编程式调用）。"""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    os.environ["DATABASE_PATH"] = str(db_path)
    return cfg


def _table_names(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    finally:
        conn.close()


def _columns(db_path: str, table: str):
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _index_names(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix_sync_checkpoints%'"
            ).fetchall()
        }
    finally:
        conn.close()


def _table_sql(db_path: str, table: str):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _read_version(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _assert_checkpoint_schema(db_path: str) -> None:
    """断言 sync_checkpoints 表结构完整（列/唯一约束/查询索引）。"""
    tables = _table_names(db_path)
    assert "sync_checkpoints" in tables, "upgrade 后 sync_checkpoints 表应存在"

    cols = _columns(db_path, "sync_checkpoints")
    assert EXPECTED_COLUMNS.issubset(cols), f"列缺失: {EXPECTED_COLUMNS - cols}"

    sql = _table_sql(db_path, "sync_checkpoints")
    assert sql is not None
    assert _UNIQUE_NAME in sql and "UNIQUE" in sql, f"唯一约束缺失，实际 SQL: {sql}"
    assert "downloader_id" in sql and "sync_type" in sql

    indexes = _index_names(db_path)
    assert _INDEX_DOWNLOADER in indexes, f"downloader_id 查询索引缺失: {indexes}"
    assert _INDEX_SYNC_TYPE in indexes, f"sync_type 查询索引缺失: {indexes}"


def test_empty_db_upgrade_downgrade_reupgrade_roundtrip(tmp_path):
    """空库 upgrade → 表存在 → downgrade -1 → 表不存在 → 再次 upgrade 成功。"""
    db_path = tmp_path / "roundtrip.db"
    cfg = _make_alembic_config(str(db_path))

    # 1) 空库 upgrade 到 sync_checkpoints head（NEW_HEAD）
    command.upgrade(cfg, NEW_HEAD)
    assert _read_version(str(db_path)) == NEW_HEAD
    _assert_checkpoint_schema(str(db_path))

    # 2) downgrade -1：回退到旧 head，表完整删除
    command.downgrade(cfg, "-1")
    assert _read_version(str(db_path)) == OLD_HEAD
    assert "sync_checkpoints" not in _table_names(str(db_path)), "downgrade 后 sync_checkpoints 应被删除"

    # 3) 再次 upgrade 到 NEW_HEAD：可重建（幂等往返）
    command.upgrade(cfg, NEW_HEAD)
    assert _read_version(str(db_path)) == NEW_HEAD
    _assert_checkpoint_schema(str(db_path))


def test_upgrade_from_old_head_preserves_task_logs(tmp_path):
    """旧 head（生产近似 Schema）升级到新 head：历史 task_logs 数据可读。"""
    db_path = tmp_path / "upgrade_existing.db"
    cfg = _make_alembic_config(str(db_path))

    # 1) 先建旧 head 库（生产近似 Schema）
    command.upgrade(cfg, OLD_HEAD)
    assert _read_version(str(db_path)) == OLD_HEAD
    assert "sync_checkpoints" not in _table_names(str(db_path))

    # 2) 注入历史 task_logs 数据
    conn = sqlite3.connect(db_path)
    rows = [
        ("历史任务A", 1, "2026-08-01 10:00:00", "2026-08-01 10:05:00", 300, 1, "detail-a", 0),
        ("历史任务B", 2, "2026-08-02 09:00:00", None, None, 0, "detail-b", 0),
    ]
    conn.executemany(
        "INSERT INTO task_logs "
        "(task_name, task_type, start_time, end_time, duration, success, log_detail, dr) "
        "VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()

    # 3) 升级到 sync_checkpoints head（NEW_HEAD）
    command.upgrade(cfg, NEW_HEAD)
    assert _read_version(str(db_path)) == NEW_HEAD

    # 4) 历史 task_logs 数据完整可读，且新增表存在
    conn = sqlite3.connect(db_path)
    try:
        actual = conn.execute(
            "SELECT task_name, task_type, start_time, end_time, duration, success, log_detail, dr "
            "FROM task_logs ORDER BY log_id"
        ).fetchall()
    finally:
        conn.close()
    assert actual == rows, f"历史 task_logs 数据在升级后应保持原样，实际 {actual}"
    _assert_checkpoint_schema(str(db_path))
