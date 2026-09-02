#!/usr/bin/env python3
"""快照单场景切片（release-artifact-equivalence-gate W4 B2 / G8 变异演练）。

把完整快照切成只含指定场景的切片，供变异演练做"同场景基线 vs 被变异制品"
的精确比对——差异只会来自注入的变异本身，不会被其他场景的缺失噪声污染。

用法：
  python slice_snapshot.py --input snapshot-deb.json --scenarios C11_spa \
      --output slice-c11.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def slice_snapshot(payload: dict, scenario_keys: List[str]) -> dict:
    scenarios = payload.get("scenarios", {})
    missing = [key for key in scenario_keys if key not in scenarios]
    if missing:
        raise SystemExit(f"[FAIL] 场景键不存在: {missing}（可用: {sorted(scenarios)}）")
    return {
        "schema_version": payload.get("schema_version"),
        "runner": payload.get("runner"),
        "base_url_shape": payload.get("base_url_shape"),
        "scenarios": {key: scenarios[key] for key in scenario_keys},
        "scenario_failures": [],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--scenarios", required=True, help="逗号分隔的场景键（如 C11_spa）"
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    keys = [k.strip() for k in args.scenarios.split(",") if k.strip()]
    sliced = slice_snapshot(payload, keys)
    args.output.write_text(
        json.dumps(sliced, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"slice: {args.output} scenarios={keys}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
