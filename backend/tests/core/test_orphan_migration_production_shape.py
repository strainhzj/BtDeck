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
EXPECTED_HEAD = "7b2c9d4e6f10"


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
