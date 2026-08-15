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
#       → f5e6d7c8b9a0(task outcome/freshness columns, W3-4)
#       → de898cb28172(torrent error reason)
#       → 4c1d8e7a2b90(tracker status judge schedule)
#       → 7b2c9d4e6f10(orphan background scan + stable current detail)
#       → b6e1c4d9a2f7(torrent backup downloader UUID type)
EXPECTED_HEAD = "b6e1c4d9a2f7"
PREV_HEAD = "e6d8a20c41f3"
ORPHAN_BACKGROUND_PREV = "4c1d8e7a2b90"
TORRENT_BACKUP_ID_TYPE_PREV = "7b2c9d4e6f10"
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

        # de898cb28172:torrent_info.error_reason 可空，兼容历史种子。
        conn = sqlite3.connect(db_path)
        try:
            torrent_cols = {c[1]: c for c in conn.execute("PRAGMA table_info(torrent_info)").fetchall()}
            assert "error_reason" in torrent_cols, "torrent_info 应包含 error_reason 列"
            assert torrent_cols["error_reason"][3] == 0, "torrent_info.error_reason 应可空"
        finally:
            conn.close()

        # f5e6d7c8b9a0:task_logs/cron_task 应含 outcome/freshness 列（全部可空，历史行兼容）
        conn = sqlite3.connect(db_path)
        try:
            task_log_cols = {c[1]: c for c in conn.execute("PRAGMA table_info(task_logs)").fetchall()}
            for col_name in ("outcome", "skip_reason"):
                assert col_name in task_log_cols, f"task_logs 应含 {col_name} 列"
                assert task_log_cols[col_name][3] == 0, f"task_logs.{col_name} 应可空（历史行兼容）"
            cron_task_cols = {c[1]: c for c in conn.execute("PRAGMA table_info(cron_task)").fetchall()}
            for col_name in (
                "last_success_at",
                "last_attempt_at",
                "last_outcome",
                "last_skip_reason",
                "last_run_id",
            ):
                assert col_name in cron_task_cols, f"cron_task 应含 {col_name} 列"
                assert cron_task_cols[col_name][3] == 0, f"cron_task.{col_name} 应可空（历史行兼容）"
        finally:
            conn.close()

        # 7b2c9d4e6f10：后台扫描、稳定明细和超量清理复核字段/索引完整。
        conn = sqlite3.connect(db_path)
        try:
            scan_columns = {column[1] for column in conn.execute("PRAGMA table_info(orphan_scan_result)").fetchall()}
            assert {
                "details_mode",
                "new_orphans",
                "known_orphans",
                "resolved_orphans",
                "cleanup_review_required",
                "cleanup_reviewed_at",
                "cleanup_reviewed_by",
                "cleanup_review_note",
            }.issubset(scan_columns)
            candidate_columns = {
                column[1] for column in conn.execute("PRAGMA table_info(orphan_current_candidate)").fetchall()
            }
            assert "current_detail_id" in candidate_columns
            index_names = {row[1] for row in conn.execute("PRAGMA index_list(orphan_current_candidate)").fetchall()}
            assert "ux_orphan_candidate_current_detail_id" in index_names
            assert "ix_orphan_candidate_last_scan_status" in index_names
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

    def test_torrent_backup_downloader_uuid_type_upgrade_and_downgrade(self, tmp_path):
        """备份下载器 ID 改为 VARCHAR(36) 时必须保留 UUID、索引与外键。"""
        db_path = tmp_path / "torrent_backup_uuid.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, TORRENT_BACKUP_ID_TYPE_PREV)
        downloader_id = "550e8400-e29b-41d4-a716-446655440000"

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO bt_downloaders (downloader_id, downloader_type) VALUES (?, 0)",
                (downloader_id,),
            )
            conn.execute(
                """
                INSERT INTO torrent_file_backup (
                    info_hash, file_path, downloader_id, use_count, is_deleted,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 0, 0, ?, ?)
                """,
                ("a" * 40, "backup/a.torrent", downloader_id, "2026-08-14", "2026-08-14"),
            )
            conn.commit()
            old_type = {
                column[1]: column[2] for column in conn.execute("PRAGMA table_info(torrent_file_backup)").fetchall()
            }
            assert old_type["downloader_id"].upper() == "INTEGER"
        finally:
            conn.close()

        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db_path)
        try:
            columns = {
                column[1]: column[2] for column in conn.execute("PRAGMA table_info(torrent_file_backup)").fetchall()
            }
            assert columns["downloader_id"].upper() == "VARCHAR(36)"
            assert conn.execute("SELECT downloader_id FROM torrent_file_backup").fetchone() == (downloader_id,)
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(torrent_file_backup)").fetchall()}
            assert "ix_torrent_file_backup_downloader_id" in indexes
            assert "ix_torrent_file_backup_info_hash" in indexes
        finally:
            conn.close()

        # UUID 文本无法无损转 Integer：downgrade 必须拒绝执行并保持 head 版本，
        # 而不是经 SQLite 数值亲和力把 '550e8400-…' 截断成 550。
        with pytest.raises(RuntimeError, match="pre-migration"):
            command.downgrade(cfg, TORRENT_BACKUP_ID_TYPE_PREV)
        assert _read_version(str(db_path)) == EXPECTED_HEAD

        # 数据可无损转换时（NULL/整数文本），downgrade 允许执行且保留值。
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("INSERT INTO bt_downloaders (downloader_id, downloader_type) VALUES ('5', 0)")
            conn.execute("UPDATE torrent_file_backup SET downloader_id = '5'")
            conn.commit()
        finally:
            conn.close()

        command.downgrade(cfg, TORRENT_BACKUP_ID_TYPE_PREV)
        conn = sqlite3.connect(db_path)
        try:
            columns = {
                column[1]: column[2] for column in conn.execute("PRAGMA table_info(torrent_file_backup)").fetchall()
            }
            assert columns["downloader_id"].upper() == "INTEGER"
            assert conn.execute("SELECT downloader_id FROM torrent_file_backup").fetchone() == (5,)
        finally:
            conn.close()

        command.upgrade(cfg, "head")
        assert _read_version(str(db_path)) == EXPECTED_HEAD

    def test_orphan_background_upgrade_backfills_guardrail_and_current_detail(self, tmp_path):
        """升级必须锁定历史超量成功扫描，并绑定存量稳定明细。"""
        db_path = tmp_path / "orphan_background_upgrade.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, ORPHAN_BACKGROUND_PREV)

        timestamp = "2026-08-13 16:55:53.576000"
        conn = sqlite3.connect(db_path)
        try:
            scan_rows = [
                ("guarded-120100", "completed", 120_100, "2026-08-13 16:55:53.576000"),
                ("normal-100", "completed", 100, "2026-08-13 16:56:53.576000"),
                ("failed-120100", "failed", 120_100, "2026-08-13 16:57:53.576000"),
                ("latest-small", "completed", 1, "2026-08-13 16:58:53.576000"),
            ]
            for scan_id, status, total_orphans, scan_timestamp in scan_rows:
                conn.execute(
                    """
                    INSERT INTO orphan_scan_result (
                        scan_id, scan_time, scan_type, total_paths_scanned,
                        total_files_scanned, total_orphans, total_orphan_size,
                        status, error_message, operator, created_at, updated_at
                    ) VALUES (?, ?, 'manual', 1, ?, ?, ?, ?, NULL, 'migration-test', ?, ?)
                    """,
                    (
                        scan_id,
                        scan_timestamp,
                        total_orphans,
                        total_orphans,
                        total_orphans * 1024,
                        status,
                        scan_timestamp,
                        scan_timestamp,
                    ),
                )

            canonical_path = "C:/data/known-orphan.bin"
            conn.execute(
                """
                INSERT INTO orphan_file (
                    id, scan_id, file_path, file_size, mtime, downloader_id,
                    confidence, canonical_path, is_deleted, deleted_at,
                    deleted_by, created_at
                ) VALUES (1, 'guarded-120100', ?, 1024, NULL, 'dl-1',
                          'high', ?, 0, NULL, NULL, ?)
                """,
                (canonical_path, canonical_path, timestamp),
            )

            candidate_values = {
                "canonical_path": canonical_path,
                "downloader_id": "dl-1",
                "first_seen_at": timestamp,
                "last_seen_at": timestamp,
                "last_seen_scan_id": "guarded-120100",
                "consecutive_scan_count": 1,
                "status": "candidate",
                "file_size": 1024,
                "confidence": "high",
                "mtime_ns": 1,
                "device_id": "1",
                "inode": "2",
                "quarantine_path": None,
                "quarantine_root": None,
                "quarantined_at": None,
                "purge_after": None,
                "purge_delay_count": 0,
                "operation_state": "stable",
                "operation_target_path": None,
                "operation_error": None,
                "is_ignored": 0,
                "ignored_at": None,
                "ignored_by": None,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            available_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(orphan_current_candidate)").fetchall()
            }
            insert_columns = [name for name in candidate_values if name in available_columns]
            placeholders = ", ".join("?" for _ in insert_columns)
            conn.execute(
                f"INSERT INTO orphan_current_candidate "  # noqa: S608
                f"({', '.join(insert_columns)}) VALUES ({placeholders})",
                [candidate_values[name] for name in insert_columns],
            )
            conn.commit()
        finally:
            conn.close()

        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        try:
            reviews = dict(
                conn.execute("SELECT scan_id, cleanup_review_required " "FROM orphan_scan_result").fetchall()
            )
            assert reviews == {
                "guarded-120100": 1,
                "normal-100": 0,
                "failed-120100": 0,
                # 活跃候选仍指向未复核超量批次，小扫描不能洗掉门禁。
                "latest-small": 1,
            }
            assert {
                row[0] for row in conn.execute("SELECT DISTINCT details_mode FROM orphan_scan_result").fetchall()
            } == {"snapshot"}
            pointer = conn.execute(
                "SELECT current_detail_id FROM orphan_current_candidate " "WHERE canonical_path = ?",
                (canonical_path,),
            ).fetchone()
            assert pointer == (1,)
        finally:
            conn.close()

    def test_orphan_background_upgrade_recovers_stale_batch_table(self, tmp_path):
        """SQLite batch 中断留下临时表时，原表仍在即可安全重建并继续升级。"""
        db_path = tmp_path / "orphan_background_stale_batch.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, ORPHAN_BACKGROUND_PREV)

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE _alembic_tmp_orphan_scan_result " "AS SELECT * FROM orphan_scan_result WHERE 0")
            conn.commit()
        finally:
            conn.close()

        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        try:
            assert _read_version(str(db_path)) == EXPECTED_HEAD
            assert (
                conn.execute(
                    "SELECT name FROM sqlite_master " "WHERE type='table' AND name='_alembic_tmp_orphan_scan_result'"
                ).fetchone()
                is None
            )
            scan_columns = {column[1] for column in conn.execute("PRAGMA table_info(orphan_scan_result)")}
            assert "details_mode" in scan_columns
        finally:
            conn.close()

    def test_orphan_background_upgrade_rejects_orphaned_temp_without_source(self, tmp_path):
        """仅剩 batch 临时表时数据完整性未知，必须拒绝自动删除或 stamp。"""
        db_path = tmp_path / "orphan_background_missing_source.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, ORPHAN_BACKGROUND_PREV)

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("ALTER TABLE orphan_scan_result RENAME TO _alembic_tmp_orphan_scan_result")
            conn.commit()
        finally:
            conn.close()

        with pytest.raises(RuntimeError, match="pre-migration 备份"):
            command.upgrade(cfg, "head")

        assert _read_version(str(db_path)) == ORPHAN_BACKGROUND_PREV

    def test_orphan_background_upgrade_uses_canonical_path_index(self, tmp_path):
        """稳定明细回填必须按 canonical_path 查找，避免 SQLite 错选 scan_id 索引。"""
        db_path = tmp_path / "orphan_background_query_plan.db"
        cfg = _make_alembic_config(str(db_path))
        command.upgrade(cfg, ORPHAN_BACKGROUND_PREV)

        migration_path = (
            BACKEND_ROOT / "alembic" / "versions" / "7b2c9d4e6f10_orphan_scan_background_and_current_detail.py"
        )
        source = migration_path.read_text(encoding="utf-8")
        assert source.count("INDEXED BY ix_orphan_file_canonical_path") == 2

        conn = sqlite3.connect(db_path)
        try:
            plan = conn.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT detail.id FROM orphan_file AS detail "
                "INDEXED BY ix_orphan_file_canonical_path "
                "WHERE detail.canonical_path = ? AND detail.scan_id = ? "
                "ORDER BY detail.id DESC LIMIT 1",
                ("C:/data/sample.bin", "scan-id"),
            ).fetchall()
            assert any("ix_orphan_file_canonical_path" in str(row) for row in plan)
        finally:
            conn.close()


# ==================== Tracker 状态判断任务错峰迁移专项 ====================

TRACKER_JUDGE_SCHEDULE_PREV = "de898cb28172"
_OLD_TRACKER_JUDGE_CRON = "0 */5 * * *"
_NEW_TRACKER_JUDGE_CRON = "20,50 * * * *"
_OLD_TRACKER_JUDGE_DESCRIPTION = (
    "定期检查所有种子的tracker状态，根据关键词池（失败池、成功池、忽略池）"
    "智能判断tracker是否失败，自动更新has_tracker_error字段"
    "（间隔: 5分钟，批量处理20,000+种子）"
)
_NEW_TRACKER_JUDGE_DESCRIPTION = (
    "定期检查所有种子的tracker状态，根据状态码与关键词池（失败池、成功池、忽略池）"
    "共同判断tracker是否失败，自动更新has_tracker_error字段"
    "（每30分钟，在Tracker状态同步任务后10分钟执行，批量处理20,000+种子）"
)


def _insert_tracker_judge_task(
    db_path: str,
    cron_plan: str,
    description: str = _OLD_TRACKER_JUDGE_DESCRIPTION,
    dr: int = 0,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO cron_task (
                task_name, task_code, task_status, task_type, executor, enabled,
                cron_plan, description, timeout_seconds, max_retry_count,
                retry_interval, dr, create_time, update_time, create_by, update_by
            ) VALUES (?, ?, 1, 4, ?, 1, ?, ?, 300, 0, 300, ?,
                      CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'admin', 'admin')
            """,
            (
                "种子Tracker状态判断任务",
                "TORRENT_TRACKER_STATUS_JUDGE",
                "app.tasks.scheduler.torrent_tracker_status_judge.TorrentTrackerStatusJudge",
                cron_plan,
                description,
                dr,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _read_tracker_judge_schedule(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT cron_plan, description FROM cron_task " "WHERE task_code = 'TORRENT_TRACKER_STATUS_JUDGE'"
        ).fetchone()
    finally:
        conn.close()


class TestTrackerJudgeScheduleMigration:
    def test_upgrade_and_downgrade_stagger_default_schedule(self, tmp_path):
        db_path = str(tmp_path / "tracker_judge_schedule.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, TRACKER_JUDGE_SCHEDULE_PREV)
        _insert_tracker_judge_task(db_path, _OLD_TRACKER_JUDGE_CRON)

        command.upgrade(cfg, "head")
        assert _read_tracker_judge_schedule(db_path) == (
            _NEW_TRACKER_JUDGE_CRON,
            _NEW_TRACKER_JUDGE_DESCRIPTION,
        )

        command.downgrade(cfg, TRACKER_JUDGE_SCHEDULE_PREV)
        assert _read_tracker_judge_schedule(db_path) == (
            _OLD_TRACKER_JUDGE_CRON,
            _OLD_TRACKER_JUDGE_DESCRIPTION,
        )

        command.upgrade(cfg, "head")
        assert _read_tracker_judge_schedule(db_path) == (
            _NEW_TRACKER_JUDGE_CRON,
            _NEW_TRACKER_JUDGE_DESCRIPTION,
        )

    def test_upgrade_preserves_custom_schedule_and_description(self, tmp_path):
        db_path = str(tmp_path / "tracker_judge_custom_schedule.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, TRACKER_JUDGE_SCHEDULE_PREV)
        _insert_tracker_judge_task(db_path, "7 * * * *", "用户自定义状态判断任务")

        command.upgrade(cfg, "head")

        assert _read_tracker_judge_schedule(db_path) == (
            "7 * * * *",
            "用户自定义状态判断任务",
        )

    def test_upgrade_preserves_custom_description_even_with_legacy_cron(self, tmp_path):
        db_path = str(tmp_path / "tracker_judge_custom_description.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, TRACKER_JUDGE_SCHEDULE_PREV)
        _insert_tracker_judge_task(
            db_path,
            _OLD_TRACKER_JUDGE_CRON,
            "用户自定义状态判断任务",
        )

        command.upgrade(cfg, "head")

        assert _read_tracker_judge_schedule(db_path) == (
            _OLD_TRACKER_JUDGE_CRON,
            "用户自定义状态判断任务",
        )

    def test_upgrade_preserves_logically_deleted_legacy_task(self, tmp_path):
        db_path = str(tmp_path / "tracker_judge_deleted_task.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, TRACKER_JUDGE_SCHEDULE_PREV)
        _insert_tracker_judge_task(
            db_path,
            _OLD_TRACKER_JUDGE_CRON,
            dr=1,
        )

        command.upgrade(cfg, "head")

        assert _read_tracker_judge_schedule(db_path) == (
            _OLD_TRACKER_JUDGE_CRON,
            _OLD_TRACKER_JUDGE_DESCRIPTION,
        )

    def test_downgrade_preserves_schedule_after_user_customizes_migrated_description(self, tmp_path):
        db_path = str(tmp_path / "tracker_judge_post_migration_customization.db")
        cfg = _make_alembic_config(db_path)
        command.upgrade(cfg, TRACKER_JUDGE_SCHEDULE_PREV)
        _insert_tracker_judge_task(db_path, _OLD_TRACKER_JUDGE_CRON)
        command.upgrade(cfg, "head")

        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "UPDATE cron_task SET description = ? " "WHERE task_code = 'TORRENT_TRACKER_STATUS_JUDGE'",
                ("升级后用户自定义描述",),
            )
            conn.commit()
        finally:
            conn.close()

        command.downgrade(cfg, TRACKER_JUDGE_SCHEDULE_PREV)

        assert _read_tracker_judge_schedule(db_path) == (
            _NEW_TRACKER_JUDGE_CRON,
            "升级后用户自定义描述",
        )


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


# ==================== W3-4 任务 outcome/freshness 列迁移专项 ====================

PREV_OUTCOME_HEAD = "f0e1d2c3b4a5"  # f5e6d7c8b9a0 的直接前驱

# f5e6d7c8b9a0 新增的可空列（upgrade 后应存在，downgrade 后应消失）
_OUTCOME_COLUMNS = {
    "task_logs": ["outcome", "skip_reason"],
    "cron_task": ["last_success_at", "last_attempt_at", "last_outcome", "last_skip_reason", "last_run_id"],
}


def _column_names(db_path: str, table: str):
    """读 PRAGMA table_info 返回列名集合。"""
    conn = sqlite3.connect(db_path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


class TestTaskOutcomeFreshnessMigration:
    """验证 f5e6d7c8b9a0（W3-4）迁移：纯 ADD COLUMN、历史数据兼容、往返可回滚。"""

    def _insert_legacy_rows(self, db_path: str):
        """在旧 head（无新列）下插入 task_logs / cron_task 历史行。"""
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO task_logs (task_id, task_name, task_type, start_time, end_time, duration, success, log_detail, dr) "
            "VALUES (1, '历史任务', 4, '2026-07-01 00:00:00', '2026-07-01 00:01:00', 60, 1, '历史日志', 0)"
        )
        conn.execute(
            "INSERT INTO cron_task "
            "(task_id, task_name, task_code, task_status, task_type, executor, cron_plan, enabled, "
            "create_by, create_time, update_time, update_by, dr) "
            "VALUES (1, '历史任务', 'legacy_task_code', 0, 4, 'app.tasks.system_tasks.SystemTask', '0 3 * * *', 1, "
            "'admin', '2026-07-01 00:00:00', '2026-07-01 00:00:00', 'admin', 0)"
        )
        conn.commit()
        conn.close()

    def test_upgrade_preserves_historical_rows_with_null_new_columns(self, tmp_path):
        """旧 head 库升级后：历史行保留，新列全部为 NULL（历史兼容核心）。"""
        db_path = str(tmp_path / "outcome_up.db")
        cfg = _make_alembic_config(str(db_path))

        command.upgrade(cfg, PREV_OUTCOME_HEAD)
        self._insert_legacy_rows(db_path)

        command.upgrade(cfg, "head")
        assert _read_version(str(db_path)) == EXPECTED_HEAD

        conn = sqlite3.connect(db_path)
        try:
            log_row = conn.execute("SELECT task_name, outcome, skip_reason FROM task_logs WHERE log_id=1").fetchone()
            assert log_row[0] == "历史任务", "历史 task_logs 行应保留"
            assert log_row[1] is None, f"历史行 outcome 应为 NULL，实际 {log_row[1]!r}"
            assert log_row[2] is None, f"历史行 skip_reason 应为 NULL，实际 {log_row[2]!r}"

            task_row = conn.execute(
                "SELECT task_code, last_success_at, last_attempt_at, last_outcome, last_skip_reason, last_run_id "
                "FROM cron_task WHERE task_id=1"
            ).fetchone()
            assert task_row[0] == "legacy_task_code", "历史 cron_task 行应保留"
            for value in task_row[1:]:
                assert value is None, f"历史行 freshness 新列应为 NULL，实际 {value!r}"
        finally:
            conn.close()

    def test_downgrade_drops_columns_keeps_data(self, tmp_path):
        """head → downgrade 一级：新列消失、历史业务数据保留。"""
        db_path = str(tmp_path / "outcome_down.db")
        cfg = _make_alembic_config(str(db_path))

        command.upgrade(cfg, "head")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO task_logs (task_id, task_name, task_type, start_time, success, outcome, skip_reason, dr) "
            "VALUES (1, '新日志', 4, '2026-08-10 00:00:00', 1, 'skipped', 'resource_busy', 0)"
        )
        conn.commit()
        conn.close()

        command.downgrade(cfg, PREV_OUTCOME_HEAD)
        assert _read_version(str(db_path)) == PREV_OUTCOME_HEAD

        for table, columns in _OUTCOME_COLUMNS.items():
            names = _column_names(str(db_path), table)
            for col_name in columns:
                assert col_name not in names, f"downgrade 后 {table}.{col_name} 应被删除"

        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT task_name, success FROM task_logs WHERE log_id=1").fetchone()
            assert row is not None and row[0] == "新日志", "downgrade 后业务数据应保留"
            assert row[1] == 1
        finally:
            conn.close()

    def test_downgrade_then_reupgrade_round_trip(self, tmp_path):
        """往返：upgrade → downgrade → 再次 upgrade，版本与新列均恢复。"""
        db_path = str(tmp_path / "outcome_round.db")
        cfg = _make_alembic_config(str(db_path))

        command.upgrade(cfg, "head")
        command.downgrade(cfg, PREV_OUTCOME_HEAD)
        command.upgrade(cfg, "head")

        assert _read_version(str(db_path)) == EXPECTED_HEAD
        for table, columns in _OUTCOME_COLUMNS.items():
            names = _column_names(str(db_path), table)
            for col_name in columns:
                assert col_name in names, f"再次 upgrade 后 {table}.{col_name} 应恢复"
