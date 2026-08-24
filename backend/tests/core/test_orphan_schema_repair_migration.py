"""Regression tests for repairing orphan schema drift on backend restart."""

import sqlite3
from pathlib import Path

from app.core.migration import migrate_database, _read_db_version

REPAIR_PREVIOUS_HEAD = "975dad435c03"
REPAIR_HEAD = "c1d2e3f4a5b6"


def _build_head_marked_drift_db(db_path: Path) -> None:
    """Build the observed production shape: version=head but current_detail_id absent."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL PRIMARY KEY
            );
            CREATE TABLE orphan_file (
                id INTEGER PRIMARY KEY,
                scan_id VARCHAR(36) NOT NULL,
                canonical_path VARCHAR(600) NOT NULL
            );
            CREATE INDEX ix_orphan_file_canonical_path
                ON orphan_file (canonical_path);
            CREATE TABLE orphan_current_candidate (
                canonical_path VARCHAR(600) NOT NULL PRIMARY KEY,
                downloader_id VARCHAR(36) NOT NULL,
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL,
                last_seen_scan_id VARCHAR(36),
                consecutive_scan_count INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                file_size INTEGER NOT NULL,
                operation_state VARCHAR(30) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)",
            (REPAIR_PREVIOUS_HEAD,),
        )
        conn.execute(
            "INSERT INTO orphan_file(id, scan_id, canonical_path) VALUES (?, ?, ?)",
            (42, "scan-current", "/data/movie.mkv"),
        )
        conn.execute(
            """
            INSERT INTO orphan_current_candidate(
                canonical_path, downloader_id, first_seen_at, last_seen_at,
                last_seen_scan_id, consecutive_scan_count, status, file_size,
                operation_state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/data/movie.mkv",
                "downloader-1",
                "2026-08-23 00:00:00",
                "2026-08-23 00:00:00",
                "scan-current",
                1,
                "quarantined",
                1024,
                "stable",
                "2026-08-23 00:00:00",
                "2026-08-23 00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _index_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' " "AND tbl_name='orphan_current_candidate'"
            )
        }
    finally:
        conn.close()


def test_restart_migration_repairs_head_marked_missing_column(tmp_path, monkeypatch):
    """A normal backend restart repairs the exact version/schema drift from the snapshot."""
    db_path = tmp_path / "head-marked-drift.db"
    _build_head_marked_drift_db(db_path)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    assert migrate_database() is True
    assert _read_db_version(str(db_path)) == REPAIR_HEAD

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(orphan_current_candidate)")}
        assert "current_detail_id" in columns
        assert conn.execute(
            "SELECT current_detail_id FROM orphan_current_candidate " "WHERE canonical_path = ?",
            ("/data/movie.mkv",),
        ).fetchone() == (42,)
    finally:
        conn.close()

    indexes = _index_names(db_path)
    assert "ux_orphan_candidate_current_detail_id" in indexes
    assert "ix_orphan_candidate_last_scan_status" in indexes


def test_repair_revision_is_idempotent_for_existing_column(tmp_path, monkeypatch):
    """A healthy 975dad435c03 schema upgrades without duplicate-column errors."""
    db_path = tmp_path / "healthy-head.db"
    _build_head_marked_drift_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "ALTER TABLE orphan_current_candidate ADD COLUMN current_detail_id INTEGER " "REFERENCES orphan_file(id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX ux_orphan_candidate_current_detail_id "
            "ON orphan_current_candidate(current_detail_id)"
        )
        conn.execute(
            "UPDATE orphan_current_candidate SET current_detail_id = 42 " "WHERE canonical_path = '/data/movie.mkv'"
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    assert migrate_database() is True
    assert _read_db_version(str(db_path)) == REPAIR_HEAD
