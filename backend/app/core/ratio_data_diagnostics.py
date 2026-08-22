"""Read-only diagnostics for the ratio data migration and its recovery path."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.db_backup import list_pre_migration_backups

RATIO_CHECK_NAMES = {
    "ratio": "ck_torrent_info_ratio_finite_nonnegative",
    "ratio_limit": "ck_torrent_info_ratio_limit_finite_nonnegative",
}
SQLITE_MAX_FINITE_FLOAT = 1.7976931348623157e308
_RATIO_VALUE_COUNT_QUERIES = {
    "ratio": """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(ratio IS NULL), 0) AS null_count,
            COALESCE(
                SUM(
                    ratio IS NOT NULL
                    AND typeof(ratio) IN ('integer', 'real')
                    AND ratio = 0
                ),
                0
            ) AS zero_count,
            COALESCE(
                SUM(
                    ratio IS NOT NULL
                    AND typeof(ratio) IN ('integer', 'real')
                    AND ratio > 0
                    AND ratio <= ?
                ),
                0
            ) AS positive_count,
            COALESCE(
                SUM(
                    ratio IS NOT NULL
                    AND (
                        typeof(ratio) NOT IN ('integer', 'real')
                        OR ratio < 0
                        OR ratio > ?
                    )
                ),
                0
            ) AS invalid_count
        FROM torrent_info
    """,
    "ratio_limit": """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(ratio_limit IS NULL), 0) AS null_count,
            COALESCE(
                SUM(
                    ratio_limit IS NOT NULL
                    AND typeof(ratio_limit) IN ('integer', 'real')
                    AND ratio_limit = 0
                ),
                0
            ) AS zero_count,
            COALESCE(
                SUM(
                    ratio_limit IS NOT NULL
                    AND typeof(ratio_limit) IN ('integer', 'real')
                    AND ratio_limit > 0
                    AND ratio_limit <= ?
                ),
                0
            ) AS positive_count,
            COALESCE(
                SUM(
                    ratio_limit IS NOT NULL
                    AND (
                        typeof(ratio_limit) NOT IN ('integer', 'real')
                        OR ratio_limit < 0
                        OR ratio_limit > ?
                    )
                ),
                0
            ) AS invalid_count
        FROM torrent_info
    """,
}
_INVALID_SAMPLE_QUERY = """
    SELECT
        info_id,
        downloader_id,
        downloader_name,
        typeof(ratio) AS ratio_type,
        quote(ratio) AS ratio_value,
        typeof(ratio_limit) AS ratio_limit_type,
        quote(ratio_limit) AS ratio_limit_value
    FROM torrent_info
    WHERE (
        ratio IS NOT NULL
        AND (
            typeof(ratio) NOT IN ('integer', 'real')
            OR ratio < 0
            OR ratio > ?
        )
    ) OR (
        ratio_limit IS NOT NULL
        AND (
            typeof(ratio_limit) NOT IN ('integer', 'real')
            OR ratio_limit < 0
            OR ratio_limit > ?
        )
    )
    ORDER BY info_id, downloader_id, downloader_name
    LIMIT ?
"""


def _readonly_connection(path: Path) -> sqlite3.Connection:
    # Diagnostics must not create SQLite -wal/-shm files.
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_version(connection: sqlite3.Connection) -> Optional[str]:
    has_version_table = connection.execute(
        "SELECT 1 FROM sqlite_master " "WHERE type = 'table' AND name = 'alembic_version'"
    ).fetchone()
    if not has_version_table:
        return None
    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return str(row[0]) if row else None


def inspect_sqlite_file(path: Path) -> Dict[str, Any]:
    """Inspect one database or backup without opening it for writes."""
    result: Dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "size": path.stat().st_size if path.is_file() else 0,
        "sha256": None,
        "version": None,
        "integrity_check": [],
        "valid": False,
        "error": None,
    }
    if not path.is_file() or path.stat().st_size <= 0:
        result["error"] = "file is missing or empty"
        return result

    try:
        connection = _readonly_connection(path)
        try:
            result["integrity_check"] = [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
            result["version"] = _read_version(connection)
        finally:
            connection.close()
        result["sha256"] = _sha256(path)
        result["valid"] = result["integrity_check"] == ["ok"]
        if not result["valid"]:
            result["error"] = f"integrity_check failed: {result['integrity_check'][:5]}"
    except (OSError, sqlite3.Error) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _ratio_value_counts(connection: sqlite3.Connection, column: str) -> Dict[str, int]:
    try:
        query = _RATIO_VALUE_COUNT_QUERIES[column]
    except KeyError as exc:
        raise ValueError(f"unsupported ratio column: {column!r}") from exc
    row = connection.execute(
        query,
        (SQLITE_MAX_FINITE_FLOAT, SQLITE_MAX_FINITE_FLOAT),
    ).fetchone()
    assert row is not None
    return {
        "total": int(row["total"]),
        "null": int(row["null_count"]),
        "zero": int(row["zero_count"]),
        "positive": int(row["positive_count"]),
        "invalid": int(row["invalid_count"]),
    }


def _invalid_samples(connection: sqlite3.Connection, *, limit: int) -> List[Dict[str, Any]]:
    rows = connection.execute(
        _INVALID_SAMPLE_QUERY,
        (SQLITE_MAX_FINITE_FLOAT, SQLITE_MAX_FINITE_FLOAT, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _numeric_declared_type(declared_type: str) -> bool:
    upper = declared_type.upper()
    return any(marker in upper for marker in ("FLOAT", "REAL", "DOUBLE", "NUMERIC", "DECIMAL"))


def _inspect_ratio_schema(
    connection: sqlite3.Connection,
) -> Dict[str, Any]:
    table_row = connection.execute(
        "SELECT sql FROM sqlite_master " "WHERE type = 'table' AND name = 'torrent_info'"
    ).fetchone()
    if table_row is None:
        return {
            "table_exists": False,
            "columns": {},
            "checks": {name: False for name in RATIO_CHECK_NAMES.values()},
            "table_sql": None,
        }

    table_sql = str(table_row["sql"] or "")
    columns = {
        str(row["name"]): {
            "declared_type": str(row["type"] or ""),
            "numeric": _numeric_declared_type(str(row["type"] or "")),
            "nullable": not bool(row["notnull"]),
        }
        for row in connection.execute('PRAGMA table_info("torrent_info")').fetchall()
        if row["name"] in RATIO_CHECK_NAMES
    }
    return {
        "table_exists": True,
        "columns": columns,
        "checks": {check_name: check_name in table_sql for check_name in RATIO_CHECK_NAMES.values()},
        "table_sql": table_sql,
    }


def _backup_inventory(database_path: Path) -> List[Dict[str, Any]]:
    backup_paths = list_pre_migration_backups(str(database_path))
    return [inspect_sqlite_file(path) for path in backup_paths]


def inspect_ratio_migration(
    database_path: str | Path,
    *,
    expected_version: Optional[str] = None,
    sample_limit: int = 20,
) -> Dict[str, Any]:
    """Build an evidence report without modifying the database or its backups."""
    path = Path(database_path)
    database = inspect_sqlite_file(path)
    report: Dict[str, Any] = {
        "status": "unhealthy",
        "database": database,
        "expected_version": expected_version,
        "ratio_schema": {
            "table_exists": False,
            "columns": {},
            "checks": {},
            "table_sql": None,
        },
        "ratio_values": {},
        "invalid_samples": [],
        "backups": _backup_inventory(path),
        "findings": [],
        "warnings": [],
        "recommended_actions": [],
    }
    findings: List[str] = report["findings"]
    warnings: List[str] = report["warnings"]
    actions: List[str] = report["recommended_actions"]

    if not database["valid"]:
        findings.append(f"database integrity cannot be trusted: {database['error']}")
        actions.append("Stop the service and restore a validated backup before migration.")
        return report

    if expected_version and database["version"] != expected_version:
        findings.append("alembic version mismatch: " f"expected={expected_version!r}, actual={database['version']!r}")
        actions.append("Run the application migration path before serving traffic.")

    try:
        connection = _readonly_connection(path)
        try:
            schema = _inspect_ratio_schema(connection)
            report["ratio_schema"] = schema
            if not schema["table_exists"]:
                findings.append("torrent_info table is missing")
            else:
                for column in RATIO_CHECK_NAMES:
                    metadata = schema["columns"].get(column)
                    if metadata is None:
                        findings.append(f"torrent_info.{column} is missing")
                    elif not metadata["numeric"]:
                        findings.append(f"torrent_info.{column} is not numeric: " f"{metadata['declared_type']!r}")
                missing_checks = [name for name, present in schema["checks"].items() if not present]
                if missing_checks:
                    findings.append(f"ratio CHECK constraints are missing: {missing_checks}")

                if all(column in schema["columns"] for column in RATIO_CHECK_NAMES):
                    values = {column: _ratio_value_counts(connection, column) for column in RATIO_CHECK_NAMES}
                    report["ratio_values"] = values
                    report["invalid_samples"] = _invalid_samples(connection, limit=sample_limit)
                    invalid_count = sum(counts["invalid"] for counts in values.values())
                    if invalid_count:
                        findings.append(f"{invalid_count} invalid ratio field values remain")
                    zero_count = sum(counts["zero"] for counts in values.values())
                    if zero_count:
                        warnings.append(
                            f"{zero_count} zero ratio field values are valid but "
                            "cannot be distinguished from values collapsed by the "
                            "historical lossy migration"
                        )
                        actions.append(
                            "Reconcile zero ratio values against a validated "
                            "pre-migration backup or a fresh downloader snapshot."
                        )
        finally:
            connection.close()
    except sqlite3.Error as exc:
        findings.append(f"ratio diagnostics query failed: {type(exc).__name__}: {exc}")

    valid_backups = [backup for backup in report["backups"] if backup["valid"]]
    if not valid_backups:
        warnings.append("no validated pre-migration backup is currently available")
        actions.append("Confirm an external database backup exists before future destructive migrations.")

    if findings:
        if not any("migration" in action.lower() for action in actions):
            actions.append("Run the supported migration path, then rerun this report.")
    else:
        report["status"] = "healthy"
        if not actions:
            actions.append("No corrective action is required.")
    return report
