"""7b2c9d4e6f10 的生产形态 SQLite 回归。

使用真实文件型 SQLite、WAL 与旧 head schema，构造大量重复扫描明细，验证：
1. batch 中断残留表可恢复；
2. 回填按 canonical_path 索引执行，不随同批次明细数退化为相关全扫；
3. 历史超量扫描保持清理复核门禁。
"""

import sqlite3
import time
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
PREVIOUS_HEAD = "4c1d8e7a2b90"
EXPECTED_HEAD = "a8b9c0d1e2f3"


def _config(db_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def test_production_shape_upgrade_recovers_and_finishes_within_budget(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "production-shape.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg = _config(db_path)
    command.upgrade(cfg, PREVIOUS_HEAD)

    candidate_count = 12_000
    historical_scan_count = 6
    timestamp = "2026-08-13 16:55:53.576000"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        scan_rows = [
            (
                f"scan-{scan_index}",
                timestamp,
                "manual",
                candidate_count,
                candidate_count,
                120_100 if scan_index == historical_scan_count - 1 else candidate_count,
                candidate_count * 1024,
                "completed",
                None,
                "regression",
                timestamp,
                timestamp,
            )
            for scan_index in range(historical_scan_count)
        ]
        conn.executemany(
            """
            INSERT INTO orphan_scan_result (
                scan_id, scan_time, scan_type, total_paths_scanned,
                total_files_scanned, total_orphans, total_orphan_size,
                status, error_message, operator, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            scan_rows,
        )

        detail_rows = []
        for scan_index in range(historical_scan_count):
            scan_id = f"scan-{scan_index}"
            for item_index in range(candidate_count):
                canonical_path = f"C:/data/orphan-{item_index:06d}.bin"
                detail_rows.append(
                    (
                        scan_id,
                        canonical_path,
                        1024,
                        "dl-1",
                        canonical_path,
                        timestamp,
                    )
                )
        conn.executemany(
            """
            INSERT INTO orphan_file (
                scan_id, file_path, file_size, downloader_id,
                canonical_path, is_deleted, created_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            detail_rows,
        )
        candidate_rows = [
            (
                f"C:/data/orphan-{item_index:06d}.bin",
                "dl-1",
                timestamp,
                timestamp,
                f"scan-{historical_scan_count - 1}",
                6,
                "candidate",
                1024,
                "stable",
                timestamp,
                timestamp,
            )
            for item_index in range(candidate_count)
        ]
        conn.executemany(
            """
            INSERT INTO orphan_current_candidate (
                canonical_path, downloader_id, first_seen_at, last_seen_at,
                last_seen_scan_id, consecutive_scan_count, status, file_size,
                operation_state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            candidate_rows,
        )
        conn.execute("CREATE TABLE _alembic_tmp_orphan_scan_result " "AS SELECT * FROM orphan_scan_result WHERE 0")
        conn.commit()
    finally:
        conn.close()

    started = time.perf_counter()
    command.upgrade(cfg, "head")
    elapsed = time.perf_counter() - started

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == (EXPECTED_HEAD,)
        assert conn.execute(
            "SELECT COUNT(*) FROM orphan_current_candidate " "WHERE current_detail_id IS NOT NULL"
        ).fetchone() == (candidate_count,)
        assert conn.execute(
            "SELECT cleanup_review_required FROM orphan_scan_result " "WHERE scan_id = ?",
            (f"scan-{historical_scan_count - 1}",),
        ).fetchone() == (1,)
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master " "WHERE type='table' AND name='_alembic_tmp_orphan_scan_result'"
            ).fetchone()
            is None
        )
        assert conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
    finally:
        conn.close()

    assert elapsed < 20, f"生产形态迁移耗时 {elapsed:.2f}s，疑似索引回填退化"


def test_hardlink_copy_count_backfill_matches_prescan_results(tmp_path, monkeypatch):
    """d4e5f6a7b8c9 回填语义：current_detail_id 挂钩明细按预扫描结果回填，
    resolved 候选挂钩明细与未挂钩明细保持 NULL（未知）。"""
    db_path = tmp_path / "backfill.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    cfg = _config(db_path)
    # 升到 d4e5f6a7b8c9 的前一个 head（c8d9e0f1a2b3，含结果表）
    command.upgrade(cfg, "c8d9e0f1a2b3")

    timestamp = "2026-08-15 10:00:00.000000"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO orphan_scan_result (
                scan_id, scan_time, scan_type, total_paths_scanned,
                total_files_scanned, total_orphans, total_orphan_size,
                status, error_message, operator, created_at, updated_at,
                details_mode
            ) VALUES (?, ?, 'manual', 1, 4, 4, 400, 'completed',
                      NULL, 'regression', ?, ?, 'current')
            """,
            ("scan-backfill", timestamp, timestamp, timestamp),
        )
        conn.executemany(
            """
            INSERT INTO orphan_file (
                scan_id, file_path, file_size, downloader_id,
                canonical_path, is_deleted, created_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            [
                ("scan-backfill", "C:/data/linked.bin", 100, "dl-1", "C:/data/linked.bin", timestamp),
                ("scan-backfill", "C:/data/solo.bin", 100, "dl-1", "C:/data/solo.bin", timestamp),
                ("scan-backfill", "C:/data/resolved.bin", 100, "dl-1", "C:/data/resolved.bin", timestamp),
            ],
        )
        # 预扫描结果：linked 有 2 副本、solo 无副本；resolved 无结果行
        conn.executemany(
            """
            INSERT INTO orphan_hardlink_copy_result (
                device_id, inode_id, copy_count, found_count,
                copies_json, truncated, scanned_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            [
                ("11", 101, 2, 3, '["C:/data/linked.bin","C:/data/copy.bin"]', timestamp, timestamp, timestamp),
                ("11", 102, 0, 1, "[]", timestamp, timestamp, timestamp),
            ],
        )
        # 候选：linked→明细1(101)、solo→明细2(102)、resolved→明细3(但 status=resolved 被排除)
        linked_id = conn.execute("SELECT id FROM orphan_file WHERE canonical_path = 'C:/data/linked.bin'").fetchone()[0]
        solo_id = conn.execute("SELECT id FROM orphan_file WHERE canonical_path = 'C:/data/solo.bin'").fetchone()[0]
        resolved_id = conn.execute(
            "SELECT id FROM orphan_file WHERE canonical_path = 'C:/data/resolved.bin'"
        ).fetchone()[0]
        conn.executemany(
            """
            INSERT INTO orphan_current_candidate (
                canonical_path, downloader_id, first_seen_at, last_seen_at,
                last_seen_scan_id, consecutive_scan_count, status, file_size,
                operation_state, device_id, inode, current_detail_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'scan-backfill', 1, ?, 100, 'stable',
                      ?, ?, ?, ?, ?)
            """,
            [
                (
                    "C:/data/linked.bin",
                    "dl-1",
                    timestamp,
                    timestamp,
                    "candidate",
                    "11",
                    "101",
                    linked_id,
                    timestamp,
                    timestamp,
                ),
                (
                    "C:/data/solo.bin",
                    "dl-1",
                    timestamp,
                    timestamp,
                    "candidate",
                    "11",
                    "102",
                    solo_id,
                    timestamp,
                    timestamp,
                ),
                (
                    "C:/data/resolved.bin",
                    "dl-1",
                    timestamp,
                    timestamp,
                    "resolved",
                    "11",
                    "103",
                    resolved_id,
                    timestamp,
                    timestamp,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db_path)
    try:
        counts = {
            path: value
            for path, value in conn.execute("SELECT canonical_path, hardlink_copy_count FROM orphan_file").fetchall()
        }
        # 挂钩候选且命中预扫描结果：回填结果行的 copy_count
        assert counts["C:/data/linked.bin"] == 2
        assert counts["C:/data/solo.bin"] == 0
        # resolved 候选挂钩明细被回填 SQL 的 status <> 'resolved' 排除 → NULL
        assert counts["C:/data/resolved.bin"] is None
        assert conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
    finally:
        conn.close()
