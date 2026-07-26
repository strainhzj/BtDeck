#!/usr/bin/env python3
"""Print a read-only ratio migration and recovery-readiness report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.ratio_data_diagnostics import (  # noqa: E402
    inspect_ratio_migration,
    inspect_sqlite_file,
)


def _detect_head() -> Optional[str]:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        heads = ScriptDirectory.from_config(config).get_heads()
        return heads[0] if len(heads) == 1 else None
    except Exception:
        return None


def _default_database() -> Path:
    configured = os.getenv("DATABASE_PATH")
    if configured:
        return Path(configured)
    return BACKEND_ROOT / "config" / "app.db"


def _print_human(report: dict) -> None:
    database = report["database"]
    schema = report["ratio_schema"]
    print(f"status: {report['status']}")
    print(f"database: {database['path']}")
    print("integrity/version: " f"{database['integrity_check']} / {database['version']}")
    print(f"expected version: {report['expected_version']}")
    print(f"ratio columns: {schema['columns']}")
    print(f"ratio checks: {schema['checks']}")
    print(f"ratio values: {report['ratio_values']}")
    print(f"validated backups: {sum(item['valid'] for item in report['backups'])}")
    if report["findings"]:
        print("findings:")
        for finding in report["findings"]:
            print(f"  - {finding}")
    if report["warnings"]:
        print("warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")
    print("recommended actions:")
    for action in report["recommended_actions"]:
        print(f"  - {action}")


def _inspect_file_only(database: Path, expected_version: Optional[str]) -> dict:
    inspected = inspect_sqlite_file(database)
    findings = []
    if not inspected["valid"]:
        findings.append(f"database file cannot be trusted: {inspected['error']}")
    if expected_version and inspected["version"] != expected_version:
        findings.append("alembic version mismatch: " f"expected={expected_version!r}, actual={inspected['version']!r}")
    return {
        "status": "healthy" if not findings else "unhealthy",
        "database": inspected,
        "expected_version": expected_version,
        "findings": findings,
    }


def _print_file_human(report: dict) -> None:
    database = report["database"]
    print(f"status: {report['status']}")
    print(f"database: {database['path']}")
    print(f"size: {database['size']}")
    print(f"sha256: {database['sha256']}")
    print(f"integrity: {database['integrity_check']}")
    print(f"version: {database['version']}")
    print(f"expected version: {report['expected_version']}")
    for finding in report["findings"]:
        print(f"finding: {finding}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=_default_database(),
        help="SQLite database path (default: DATABASE_PATH or config/app.db)",
    )
    parser.add_argument(
        "--expected-version",
        default=None,
        help="Expected Alembic revision (default: current migration head)",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="Maximum invalid rows included in the report",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument(
        "--file-only",
        action="store_true",
        help="Validate only file integrity, digest and optional version",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit 2 when integrity/schema/value findings remain",
    )
    args = parser.parse_args()
    if args.sample_limit < 0:
        parser.error("--sample-limit must be non-negative")

    if args.file_only:
        report = _inspect_file_only(args.database, args.expected_version)
    else:
        expected_version = args.expected_version or _detect_head()
        report = inspect_ratio_migration(
            args.database,
            expected_version=expected_version,
            sample_limit=args.sample_limit,
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.file_only:
        _print_file_human(report)
    else:
        _print_human(report)
    if args.fail_on_findings and report["findings"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
