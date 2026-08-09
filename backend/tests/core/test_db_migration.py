# -*- coding: utf-8 -*-
"""
数据库迁移链完整性测试（四轨治理安全网）

验证目标：
1. Alembic 迁移链能从空库独立建起完整 schema（不依赖 create_all / schema 快照）
2. 已有 head 库 upgrade 是幂等的（无副作用）
3. 幽灵版本（9aea25308aff）能被正确识别（为 migrate_database 的救援逻辑奠基）
4. env.py 与应用消费同一个 DATABASE_PATH（防串库）

注意：migrate_database() / _rescue_or_warn_version() / _backup_before_migration()
的完整行为测试在阶段3 实现后补充到本文件。
本阶段先覆盖"迁移链本身是否健全"——这是删除 create_all / schema 快照的前提。
"""

import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

# backend/ 目录（alembic.ini 所在位置）
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@pytest.fixture(autouse=True)
def _clean_database_path_env():
    """自动清理 DATABASE_PATH 环境变量，防止跨测试污染（测试隔离）。"""
    import os

    old = os.environ.pop("DATABASE_PATH", None)
    yield
    if old is not None:
        os.environ["DATABASE_PATH"] = old
    else:
        os.environ.pop("DATABASE_PATH", None)


# 已知的迁移链 revision（与 alembic/versions/ 保持一致，变更时同步更新）
# 链尾：6132b66d14a7(String→Float) → 8f4c2d1a9b7e(数值约束/兼容修复) → f2a7c91b4d6e(orphan confidence)
#       → a1b2c3d4e5f6(orphan ignore + canonical_path) → c7d8e9f0a1b2(orphan purge jobs)
#       → d8e9f0a1b2c3(async manual cleanup fields) → 3a4b5c6d7e8f(sync checkpoints)
#       → f9a1b2c3d4e5(orphan purge hardlink notes) → f0e1d2c3b4a5(orphan purge delay count)
EXPECTED_HEAD = "f0e1d2c3b4a5"
PREV_HEAD = "e6d8a20c41f3"
GHOST_VERSION = "9aea25308aff"  # init_schema_from_production 写入的历史幽灵版本


def _make_alembic_config(db_path: str) -> Config:
    """构造指向指定 DB 的 Alembic Config（编程式调用）。"""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    # 关键：设 DATABASE_PATH 环境变量，env.py 会优先读它（防串库）
    os.environ["DATABASE_PATH"] = str(db_path)
    return cfg


def _table_count(db_path: str) -> int:
    """统计业务表数量（排除 sqlite 内部表和 alembic_version）。"""
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        ).fetchone()[0]
        return count
    finally:
        conn.close()


def _read_version(db_path: str):
    """读取 alembic_version；无表返回 None。"""
    if not Path(db_path).exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        # 检查 alembic_version 表是否存在
        has_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if not has_table:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


# ==================== 迁移链完整性 ====================


class TestMigrationChainIntegrity:
    """验证 Alembic 迁移链本身的健全性。"""

    def test_migration_chain_has_single_head(self):
        """迁移链应为单 head（无分叉）。"""
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        sd = ScriptDirectory.from_config(cfg)
        heads = sd.get_heads()
        assert len(heads) == 1, f"迁移链应只有 1 个 head，实际 {len(heads)}: {heads}"
        assert heads[0] == EXPECTED_HEAD, f"head 应为 {EXPECTED_HEAD}，实际 {heads[0]}"

    def test_ghost_version_not_in_chain(self):
        """幽灵版本 9aea25308aff 不应在迁移链中（验证它是历史遗留）。"""
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        sd = ScriptDirectory.from_config(cfg)
        valid_revs = {r.revision for r in sd.walk_revisions()}
        assert GHOST_VERSION not in valid_revs, f"幽灵版本 {GHOST_VERSION} 不应在迁移链中，否则它就不是幽灵了"

    def test_empty_db_upgrade_head_builds_full_schema(self, tmp_path):
        """空库 alembic upgrade head 应建起完整 schema（26 张业务表）。

        这是删除 create_all 的核心前提：迁移链能独立承担建库。
        """
        db_path = tmp_path / "empty.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, "head")

        assert db_path.exists(), "upgrade 后数据库文件应存在"
        assert _read_version(str(db_path)) == EXPECTED_HEAD
        count = _table_count(str(db_path))
        # base(e2a02abcf912) 建 21 表 + d0e58437af70 加 1 + a0ada9774936 加 1 + 95ef8bd8b47a 加 search_templates = 24
        # + c3f1a8b7d902 加 orphan_scan_result + orphan_file = 26
        # + b075727f7182 加 orphan_current_candidate + orphan_operation_lease = 28
        # + c7d8e9f0a1b2 加 orphan_purge_job = 29
        # + 3a4b5c6d7e8f 加 sync_checkpoints = 30
        assert count == 30, f"空库 upgrade 应建 30 张业务表（含 orphan_purge_job + sync_checkpoints），实际 {count}"

        # f0e1d2c3b4a5:orphan_current_candidate 应含 purge_delay_count 列（NOT NULL + 默认 0）
        conn = sqlite3.connect(db_path)
        try:
            col = conn.execute("PRAGMA table_info(orphan_current_candidate)").fetchall()
            purge_col = [c for c in col if c[1] == "purge_delay_count"]
            assert purge_col, "orphan_current_candidate 应含 purge_delay_count 列"
            # c[2]=type, c[3]=notnull, c[4]=dflt_value（SQLite 存储时带引号）
            assert purge_col[0][2].lower() == "integer", f"类型应为 INTEGER: {purge_col[0]}"
            assert purge_col[0][3] == 1, f"应 NOT NULL: {purge_col[0]}"
            assert purge_col[0][4].strip("'") == "0", f"默认值应为 0: {purge_col[0]}"
        finally:
            conn.close()

    def test_upgrade_head_is_idempotent(self, tmp_path):
        """已有 head 库再次 upgrade 应幂等（version 不变、表数不变）。"""
        db_path = tmp_path / "idempotent.db"
        cfg = _make_alembic_config(str(db_path))

        # 首次建库
        command.upgrade(cfg, "head")
        version_before = _read_version(str(db_path))
        count_before = _table_count(str(db_path))

        # 再次 upgrade（应 no-op）
        command.upgrade(cfg, "head")
        version_after = _read_version(str(db_path))
        count_after = _table_count(str(db_path))

        assert version_before == version_after == EXPECTED_HEAD
        assert count_before == count_after


# ==================== 串库防护 ====================


class TestDatabasePathRouting:
    """验证 env.py 根据 DATABASE_PATH 环境变量路由到正确库（防串库）。

    这是 B3（阶段3+4 同批）的测试基础：env.py 必须与 config.py 消费同一来源。
    """

    def test_upgrade_writes_to_specified_database_path(self, tmp_path):
        """设 DATABASE_PATH 后，upgrade 应写到该路径，不污染真实 app.db。"""
        from app.core.config import settings

        target_db = tmp_path / "routed.db"
        cfg = _make_alembic_config(str(target_db))
        command.upgrade(cfg, "head")

        # 目标库应已建表
        assert target_db.exists()
        assert _table_count(str(target_db)) == 30

        # 真实 app.db 的 version 不应被改动
        real_db = str(settings.DATABASE_PATH)
        if Path(real_db).exists():
            # app.db version 应保持原值（不因本次测试的 upgrade 而变）
            # 注意：这里只验证 app.db 仍可读且 version 非空，不硬编码具体值
            real_version = _read_version(real_db)
            assert real_version is not None, "真实 app.db 不应被测试污染到丢失 version"


# ==================== v1.0.6.1 ratio/ratio_limit 列类型迁移专项 ====================


def _column_type(db_path: str, table: str, col: str):
    """读 PRAGMA table_info 取列类型。"""
    conn = sqlite3.connect(db_path)
    try:
        for row in conn.execute(f"PRAGMA table_info({table})"):
            if row[1] == col:
                return row[2].upper()
        return None
    finally:
        conn.close()


def _index_sql(db_path: str, idx_name: str):
    """读 sqlite_master 取索引的原始 SQL（含 partial WHERE 子句）。"""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (idx_name,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


class TestRatioColumnMigration:
    """验证 6132b66d14a7 ratio_columns_to_float 迁移：列类型、脏数据清洗、索引保真。

    红队漏洞：v1.0.5.15 的 cast 修复只覆盖 ratio 的 filter 路径，遗漏 ratio_limit、
    ratio 排序、ratio_limit 排序。v1.0.6.1 改列类型为 Float 从根因上根治。
    """

    def test_upgrade_converts_ratio_columns_to_float(self, tmp_path):
        """空库 upgrade head 后 ratio/ratio_limit 列类型应为 FLOAT/REAL。"""
        db_path = str(tmp_path / "ratio_mig.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, "head")

        ratio_type = _column_type(db_path, "torrent_info", "ratio")
        ratio_limit_type = _column_type(db_path, "torrent_info", "ratio_limit")
        # SQLite 把 Float 存为 REAL（type affinity），部分版本 PRAGMA 报 FLOAT
        assert ratio_type in ("FLOAT", "REAL"), f"ratio 列应为 FLOAT/REAL，实际 {ratio_type}"
        assert ratio_limit_type in ("FLOAT", "REAL"), f"ratio_limit 列应为 FLOAT/REAL，实际 {ratio_limit_type}"

    def test_upgrade_cleans_dirty_data_to_null(self, tmp_path):
        """脏数据（""/-1/-2/"None"/"none"）upgrade 后应转 NULL，不被 CAST 静默转 0.0。"""
        db_path = str(tmp_path / "dirty.db")
        cfg = _make_alembic_config(db_path)

        # 1) 升级到迁移前版本，建表为 String 列
        command.upgrade(cfg, "e6d8a20c41f3")

        # 2) 注入脏数据
        conn = sqlite3.connect(db_path)
        dirty = [
            ("i1", "2.5"),
            ("i2", ""),
            ("i3", "-1"),
            ("i4", "-2"),
            ("i5", "None"),
            ("i6", "none"),
            ("i7", "10.0"),
        ]
        for info_id, ratio in dirty:
            conn.execute(
                "INSERT INTO torrent_info (info_id, downloader_id, downloader_name, hash, dr, ratio, has_tracker_error) "
                "VALUES (?,?,?,?,0,?,0)",
                (info_id, "d1", "q1", info_id, ratio),
            )
        conn.commit()
        conn.close()

        # 3) 升级到 head（应用 ratio 列迁移）
        command.upgrade(cfg, "head")

        # 4) 验证：脏值转 NULL，正常数值保留
        conn = sqlite3.connect(db_path)
        rows = dict(conn.execute("SELECT info_id, ratio FROM torrent_info ORDER BY info_id").fetchall())
        conn.close()

        # 脏值应全部为 NULL（i2/i3/i4/i5/i6），正常值 i1=2.5/i7=10.0 保留
        for dirty_id in ("i2", "i3", "i4", "i5", "i6"):
            assert rows[dirty_id] is None, f"脏值 {dirty_id} 应转 NULL，实际 {rows[dirty_id]!r}（CAST 静默转 0.0 bug）"
        assert rows["i1"] == 2.5, f"i1 正常值应保留，实际 {rows['i1']}"
        assert rows["i7"] == 10.0, f"i7 正常值应保留，实际 {rows['i7']}"

    def test_upgrade_does_not_cast_arbitrary_invalid_text_to_zero(self, tmp_path):
        """任意非法文本/非有限数必须转 NULL，不能被 SQLite CAST 成 0.0。"""
        db_path = str(tmp_path / "strict_dirty.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, PREV_HEAD)

        cases = {
            "valid-space": (" 2.5 ", " 3.5 "),
            "valid-exp": ("1e3", "2e2"),
            "garbage": ("downloader parse failure", "garbage"),
            "null-word": ("null", "NULL"),
            "nan": ("NaN", "nan"),
            "infinity": ("Infinity", "-Infinity"),
            "overflow": ("1e309", "1e309"),
            "negative": ("-0.1", "-3"),
        }
        conn = sqlite3.connect(db_path)
        for info_id, (ratio, ratio_limit) in cases.items():
            conn.execute(
                "INSERT INTO torrent_info "
                "(info_id, downloader_id, downloader_name, hash, dr, ratio, ratio_limit, has_tracker_error) "
                "VALUES (?,?,?,?,0,?,?,0)",
                (info_id, "d1", "q1", info_id, ratio, ratio_limit),
            )
        conn.commit()
        conn.close()

        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        rows = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT info_id, ratio, ratio_limit, typeof(ratio), typeof(ratio_limit) " "FROM torrent_info"
            ).fetchall()
        }
        conn.close()

        assert rows["valid-space"] == (2.5, 3.5, "real", "real")
        assert rows["valid-exp"] == (1000.0, 200.0, "real", "real")
        for info_id in (
            "garbage",
            "null-word",
            "nan",
            "infinity",
            "overflow",
            "negative",
        ):
            assert rows[info_id] == (None, None, "null", "null")

    def test_ratio_check_constraints_reject_raw_invalid_writes(self, tmp_path):
        """绕过 ORM 的原始 SQL 也不能落入文本、负数或正无穷。"""
        db_path = str(tmp_path / "ratio_checks.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO torrent_info "
            "(info_id, downloader_id, downloader_name, hash, dr, ratio, ratio_limit, has_tracker_error) "
            "VALUES ('ok','d1','q1','ok',0,0,2.5,0)"
        )
        conn.commit()
        for column, invalid_sql in (
            ("ratio", "'garbage'"),
            ("ratio", "-1"),
            ("ratio", "1e999"),
            ("ratio_limit", "'garbage'"),
            ("ratio_limit", "-2"),
            ("ratio_limit", "1e999"),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(f"UPDATE torrent_info SET {column}={invalid_sql} WHERE info_id='ok'")
            conn.rollback()
        conn.close()

    def test_upgrade_preserves_partial_unique_index(self, tmp_path):
        """batch_alter 重建表后 partial unique index（含 WHERE dr=0）应保留。"""
        db_path = str(tmp_path / "partial_idx.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, "head")

        idx_sql = _index_sql(db_path, "idx_torrent_hash_unique")
        assert idx_sql, "idx_torrent_hash_unique 索引应存在"
        assert "dr = 0" in idx_sql or "dr=0" in idx_sql, f"partial unique index 丢失 WHERE 子句，实际 SQL: {idx_sql}"

    def test_downgrade_restores_string_type(self, tmp_path):
        """upgrade head → downgrade 一级 → 列类型回到 String（VARCHAR）。"""
        db_path = str(tmp_path / "downgrade.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, PREV_HEAD)

        ratio_type = _column_type(db_path, "torrent_info", "ratio")
        assert ratio_type in ("VARCHAR", "STRING", "TEXT"), f"downgrade 后 ratio 列应回 String，实际 {ratio_type}"
