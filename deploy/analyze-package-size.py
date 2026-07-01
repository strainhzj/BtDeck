from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return f"{size} B"


def normalize_name(name: str) -> str:
    return name.replace("\\", "/").strip().strip("'\"")


def group_name(name: str) -> str:
    normalized = normalize_name(name)
    first = normalized.split("/", 1)[0]
    if first.endswith(".dist-info"):
        return first.removesuffix(".dist-info")
    if first.endswith(".pyd") or first.endswith(".dll"):
        return first
    return first or normalized


def parse_archive_listing(output: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or not line[0].isdigit():
            continue

        try:
            parsed = next(csv.reader([line], skipinitialspace=True))
        except csv.Error:
            continue

        if len(parsed) < 6:
            continue

        try:
            length = int(parsed[1])
            uncompressed_length = int(parsed[2])
        except ValueError:
            continue

        name = normalize_name(",".join(parsed[5:]))
        rows.append(
            {
                "name": name,
                "group": group_name(name),
                "length": length,
                "uncompressed_length": uncompressed_length,
                "typecode": parsed[4].strip().strip("'\""),
            }
        )
    return rows


def read_archive(exe_path: Path) -> list[dict[str, object]]:
    viewer = shutil.which("pyi-archive_viewer")
    if not viewer:
        raise RuntimeError("pyi-archive_viewer not found. Install PyInstaller and ensure it is in PATH.")

    result = subprocess.run(
        [viewer, str(exe_path), "-l"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 and "Contents of" not in output:
        raise RuntimeError(output.strip() or "pyi-archive_viewer failed")

    return parse_archive_listing(output)


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze PyInstaller onefile archive size.")
    parser.add_argument(
        "--exe",
        type=Path,
        default=Path("dist") / "btdeck.exe",
        help="Path to the packaged executable. Defaults to dist/btdeck.exe.",
    )
    parser.add_argument("--top", type=int, default=30, help="Number of top rows to print.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exe_path = args.exe.resolve()
    if not exe_path.is_file():
        print(f"[FAIL] exe not found: {exe_path}", file=sys.stderr)
        return 1

    entries = read_archive(exe_path)
    if not entries:
        print("[FAIL] no archive entries parsed", file=sys.stderr)
        return 1

    total_compressed = sum(int(entry["length"]) for entry in entries)
    total_uncompressed = sum(int(entry["uncompressed_length"]) for entry in entries)

    print("BtDeck package size analysis")
    print(f"Executable: {exe_path}")
    print(f"Entries: {len(entries)}")
    print(f"Archive compressed total: {format_size(total_compressed)}")
    print(f"Archive uncompressed total: {format_size(total_uncompressed)}")
    print()

    group_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"length": 0, "uncompressed_length": 0, "count": 0})
    for entry in entries:
        group = str(entry["group"])
        group_totals[group]["length"] += int(entry["length"])
        group_totals[group]["uncompressed_length"] += int(entry["uncompressed_length"])
        group_totals[group]["count"] += 1

    top_groups = sorted(group_totals.items(), key=lambda item: item[1]["length"], reverse=True)[: args.top]
    print(f"Top {len(top_groups)} groups by compressed size")
    print_table(
        ["Group", "Compressed", "Uncompressed", "Entries"],
        [
            [
                group,
                format_size(values["length"]),
                format_size(values["uncompressed_length"]),
                str(values["count"]),
            ]
            for group, values in top_groups
        ],
    )
    print()

    top_entries = sorted(entries, key=lambda entry: int(entry["length"]), reverse=True)[: args.top]
    print(f"Top {len(top_entries)} entries by compressed size")
    print_table(
        ["Entry", "Compressed", "Uncompressed", "Type"],
        [
            [
                str(entry["name"]),
                format_size(int(entry["length"])),
                format_size(int(entry["uncompressed_length"])),
                str(entry["typecode"]),
            ]
            for entry in top_entries
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
