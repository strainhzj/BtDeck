"""Tests for read-only ratio migration and recovery diagnostics."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from app.core.ratio_data_diagnostics import inspect_ratio_migration


HEAD = "8f4c2d1a9b7e"


def _create_database(
    path: Path,
    *,
    constrained: bool,
    numeric_columns: bool,
) -> None:
    column_type = "FLOAT" if numeric_columns else "VARCHAR"
    checks = (
        """
        , CONSTRAINT ck_torrent_info_ratio_finite_nonnegative
            CHECK (
                ratio IS NULL OR (
                    typeof(ratio) IN ('integer', 'real')
                    AND ratio >= 0
                    AND ratio <= 1.7976931348623157e308
                )
            )
        , CONSTRAINT ck_torrent_info_ratio_limit_finite_nonnegative
            CHECK (
                ratio_limit IS NULL OR (
                    typeof(ratio_limit) IN ('integer', 'real')
                    AND ratio_limit >= 0
                    AND ratio_limit <= 1.7976931348623157e308
                )
            )
        """
        if constrained
        else ""
    )
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            f"""
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL
            );
            INSERT INTO alembic_version VALUES ('{HEAD}');
            CREATE TABLE torrent_info (
                info_id VARCHAR NOT NULL,
                downloader_id VARCHAR NOT NULL,
                downloader_name VARCHAR NOT NULL,
                ratio {column_type},
                ratio_limit {column_type}
                {checks},
                PRIMARY KEY (info_id, downloader_id, downloader_name)
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_healthy_report_proves_schema_values_and_valid_backup(tmp_path):
    database = tmp_path / "app.db"
    _create_database(database, constrained=True, numeric_columns=True)
    connection = sqlite3.connect(database)
    connection.executemany(
        "INSERT INTO torrent_info VALUES (?, ?, ?, ?, ?)",
        [
            ("null", "d1", "qb", None, None),
            ("zero", "d1", "qb", 0, 0),
            ("positive", "d1", "qb", 1.5, 2.5),
        ],
    )
    connection.commit()
    connection.close()
    shutil.copy2(
        database,
        tmp_path / "app.db.pre-migration-20260726-120000-000001",
    )
    (tmp_path / "app.db.pre-migration-20260726-120000-000001-wal").write_bytes(
        b"sidecar"
    )

    report = inspect_ratio_migration(database, expected_version=HEAD)

    assert report["status"] == "healthy"
    assert report["findings"] == []
    assert all(report["ratio_schema"]["checks"].values())
    assert report["ratio_values"]["ratio"] == {
        "total": 3,
        "null": 1,
        "zero": 1,
        "positive": 1,
        "invalid": 0,
    }
    assert report["invalid_samples"] == []
    assert report["backups"][0]["valid"] is True
    assert len(report["backups"]) == 1
    assert len(report["backups"][0]["sha256"]) == 64
    assert any("cannot be distinguished" in item for item in report["warnings"])


def test_report_exposes_old_text_schema_and_invalid_values(tmp_path):
    database = tmp_path / "app.db"
    _create_database(database, constrained=False, numeric_columns=False)
    connection = sqlite3.connect(database)
    connection.executemany(
        "INSERT INTO torrent_info VALUES (?, ?, ?, ?, ?)",
        [
            ("valid", "d1", "qb", "2.5", None),
            ("invalid", "d1", "qb", "not-a-number", "-1"),
        ],
    )
    connection.commit()
    connection.close()

    report = inspect_ratio_migration(database, expected_version=HEAD)

    assert report["status"] == "unhealthy"
    assert report["ratio_values"]["ratio"]["invalid"] == 2
    assert report["ratio_values"]["ratio_limit"]["invalid"] == 1
    assert len(report["invalid_samples"]) == 2
    assert any("not numeric" in item for item in report["findings"])
    assert any("CHECK constraints are missing" in item for item in report["findings"])
    assert any("invalid ratio field values remain" in item for item in report["findings"])


def test_report_rejects_corrupt_database_without_attempting_schema_queries(
    tmp_path,
):
    database = tmp_path / "app.db"
    database.write_bytes(b"not a sqlite database")

    report = inspect_ratio_migration(database, expected_version=HEAD)

    assert report["status"] == "unhealthy"
    assert report["database"]["valid"] is False
    assert "integrity cannot be trusted" in report["findings"][0]
    assert report["ratio_values"] == {}


def test_version_mismatch_is_a_deployment_finding(tmp_path):
    database = tmp_path / "app.db"
    _create_database(database, constrained=True, numeric_columns=True)

    report = inspect_ratio_migration(
        database,
        expected_version="different_head",
    )

    assert report["status"] == "unhealthy"
    assert any("alembic version mismatch" in item for item in report["findings"])
