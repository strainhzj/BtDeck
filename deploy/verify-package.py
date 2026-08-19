#!/usr/bin/env python3
"""Validate BtDeck Windows package artifacts."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def pass_message(message: str) -> None:
    print(f"[PASS] {message}")


def fail_message(message: str) -> None:
    print(f"[FAIL] {message}")


def normalize_archive_entry(line: str) -> str:
    normalized = line.replace("\\", "/").strip()
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def check_path(path: Path, description: str, is_dir: bool = False) -> bool:
    exists = path.is_dir() if is_dir else path.is_file()
    if exists:
        pass_message(f"{description}: {path}")
        return True

    expected_type = "directory" if is_dir else "file"
    fail_message(f"{description} is missing, expected {expected_type}: {path}")
    return False


def read_archive_entries(viewer: str, exe_path: Path) -> tuple[bool, list[str]]:
    try:
        result = subprocess.run(
            [viewer, str(exe_path), "-l"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        fail_message(f"Unable to run pyi-archive_viewer: {exc}")
        return False, []

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        fail_message("pyi-archive_viewer failed to inspect the exe archive")
        if output.strip():
            print(output.strip())
        return False, []

    return True, [normalize_archive_entry(line) for line in output.splitlines()]


def find_archive_viewer() -> str | None:
    # The build scripts run this file with the packaging venv's python by
    # absolute path (no venv activation, Scripts/bin not on PATH), so resolve
    # the viewer next to the interpreter first, then fall back to PATH.
    exe_name = "pyi-archive_viewer.exe" if sys.platform == "win32" else "pyi-archive_viewer"
    local = Path(sys.executable).resolve().parent / exe_name
    if local.is_file():
        return str(local)
    return shutil.which("pyi-archive_viewer")


def check_archive(exe_path: Path) -> bool:
    viewer = find_archive_viewer()
    if not viewer:
        fail_message("pyi-archive_viewer not found. Install PyInstaller and ensure it is in PATH")
        return False

    pass_message(f"pyi-archive_viewer found: {viewer}")
    ok, entries = read_archive_entries(viewer, exe_path)
    if not ok:
        return False

    index_found = any("frontend_dist/index.html" in entry for entry in entries)
    assets_found = any("frontend_dist/assets/" in entry for entry in entries)

    if index_found:
        pass_message("exe archive contains frontend_dist\\index.html")
    else:
        fail_message("exe archive is missing frontend_dist\\index.html")

    if assets_found:
        pass_message("exe archive contains at least one frontend_dist\\assets\\... entry")
    else:
        fail_message("exe archive is missing frontend_dist\\assets\\... entries")

    return index_found and assets_found


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_project_root = script_path.parent.parent

    parser = argparse.ArgumentParser(
        description="Validate that the PyInstaller package contains BtDeck frontend assets"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=default_project_root,
        help="Project root. Defaults to the parent directory of deploy/",
    )
    parser.add_argument(
        "--frontend-dist",
        type=Path,
        default=None,
        help="Frontend dist directory. Defaults to <project-root>/frontend/dist",
    )
    parser.add_argument(
        "--artifact",
        "--exe",
        type=Path,
        default=None,
        help="PyInstaller packaged artifact. Defaults to <project-root>/dist/btdeck.exe",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    frontend_dist = (
        args.frontend_dist.resolve()
        if args.frontend_dist
        else project_root / "frontend" / "dist"
    )
    exe_name = "btdeck.exe" if sys.platform == "win32" else "btdeck"
    exe_path = args.artifact.resolve() if args.artifact else project_root / "dist" / exe_name

    print("BtDeck package verification")
    print(f"Project root: {project_root}")

    checks = [
        check_path(frontend_dist / "index.html", "frontend/dist/index.html"),
        check_path(frontend_dist / "assets", "frontend/dist/assets", is_dir=True),
        check_path(exe_path, "PyInstaller artifact"),
    ]

    if checks[-1]:
        checks.append(check_archive(exe_path))

    if all(checks):
        print("[PASS] Package verification passed")
        return 0

    print("[FAIL] Package verification failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
