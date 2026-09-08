#!/usr/bin/env python3
"""MCP 能力开放门禁汇聚器（feature mcp-service-capabilities-2026-08-28 W0 骨架）。

语义对齐 scripts/release/aggregate_gate_report.py（发布制品 G0~G10 流水线）：
显式片段优先、缺失=NOT_RUN、坏证据=INDETERMINATE、诚实索引不静默降级。

差异与加强：

- 门集合为 MCP-G0~MCP-G11（12 门，对应 feature_list.json implementation_gates）；
- fail-closed 占位语义：W0 交付时尚无任何片段，运行本脚本即得 12×NOT_RUN +
  verdict=BLOCKED——"NOT_RUN 即红"是设计行为，各波次回填 PASS 片段才逐门转绿；
- schema 加强：status=PASS 必须携带非空 evidence（无证据不得宣告通过）。

输入：--fragments-dir 下 MCP-G<n>.json（schema:
release/schemas/mcp-gate-fragment.schema.json）
输出：--out <mcp-gate-report.json>（gates/verdict/problems/generated_at）；
exit code 0 仅当 verdict=READY（CI 可直接当门禁条件用）。

verdict：
  任一门 FAIL → REJECTED；任一门非 PASS（含 NOT_RUN/INDETERMINATE）→ BLOCKED；
  全部 12 门 PASS → READY。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_SCHEMA = DEFAULT_PROJECT_ROOT / "release" / "schemas" / "mcp-gate-fragment.schema.json"

MCP_GATES = tuple(f"MCP-G{i}" for i in range(12))
VALID_STATUS = ("PASS", "FAIL", "INDETERMINATE", "NOT_RUN")


def load_json_maybe(path: Path) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    """容错加载：缺失→(None, None)；空/坏 JSON→(None, 问题描述)。"""
    if not path.is_file():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"片段不可解析（{path.name}: {exc}）"
    if not isinstance(payload, dict):
        return None, f"片段非对象（{path.name}）"
    return payload, None


def validate_fragment(fragment: Dict[str, object], schema_path: Path) -> List[str]:
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    return [
        f"片段 schema 校验失败 {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(fragment)
    ]


def collect(
    fragments_dir: Path, schema_path: Path
) -> Tuple[Dict[str, Dict[str, object]], List[str], set]:
    """加载全部显式片段 → ({gate: fragment}, 问题列表, 违例门集合)。

    fail-closed 语义：坏 JSON/未知门/重复片段只记问题；schema 违例的片段仍占位
    其门（状态 INDETERMINATE，防同门好坏双片段静默取好）。
    """
    fragments: Dict[str, Dict[str, object]] = {}
    problems: List[str] = []
    invalid: set = set()
    if not fragments_dir.is_dir():
        return fragments, [f"片段目录不存在: {fragments_dir}"], invalid
    for path in sorted(fragments_dir.glob("MCP-G*.json")):
        payload, load_problem = load_json_maybe(path)
        if payload is None:
            problems.append(f"片段坏文件：{path.name}（{load_problem}）")
            continue
        gate = str(payload.get("gate", path.stem))
        if gate not in MCP_GATES:
            problems.append(f"片段携带未知门 ID：{path.name}（gate={gate}）")
            continue
        if gate in fragments:
            problems.append(f"门 {gate} 存在重复片段（{path.name}）")
            continue
        fragments[gate] = payload
        violations = validate_fragment(payload, schema_path)
        if violations:
            invalid.add(gate)
            problems += [f"{path.name}: {v}" for v in violations]
    return fragments, problems, invalid


def derive_gate_status(
    gate: str,
    fragments: Dict[str, Dict[str, object]],
    invalid: set,
) -> str:
    """单门状态：无片段=NOT_RUN；schema 违例=INDETERMINATE；否则取片段 status。"""
    if gate not in fragments:
        return "NOT_RUN"
    if gate in invalid:
        return "INDETERMINATE"
    status = str(fragments[gate].get("status", "INDETERMINATE"))
    return status if status in VALID_STATUS else "INDETERMINATE"


def compute_verdict(statuses: Dict[str, str]) -> str:
    """三态裁决：REJECTED（任一 FAIL）> BLOCKED（任一非 PASS）> READY（全 PASS）。"""
    values = statuses.values()
    if any(s == "FAIL" for s in values):
        return "REJECTED"
    if any(s != "PASS" for s in values):
        return "BLOCKED"
    return "READY"


def build_report(fragments_dir: Path, schema_path: Path) -> Dict[str, object]:
    fragments, problems, invalid = collect(fragments_dir, schema_path)
    statuses = {gate: derive_gate_status(gate, fragments, invalid) for gate in MCP_GATES}
    return {
        "gates": statuses,
        "verdict": compute_verdict(statuses),
        "problems": problems,
        "fragments_dir": str(fragments_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def render(report: Dict[str, object]) -> str:
    statuses: Dict[str, str] = report["gates"]  # type: ignore[assignment]
    lines = [
        "# MCP 能力开放门禁汇总",
        "",
        f"verdict: {report['verdict']}",
        "",
        "| gate | status |",
        "|------|--------|",
    ]
    lines += [f"| {gate} | {statuses[gate]} |" for gate in MCP_GATES]
    problems: List[str] = report.get("problems") or []  # type: ignore[assignment]
    if problems:
        lines += ["", "## 问题（fail-closed）", ""]
        lines += [f"- {p}" for p in problems]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MCP-G0~G11 门禁汇聚器（fail-closed）")
    parser.add_argument("--fragments-dir", required=True, help="MCP-G<n>.json 片段目录")
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="片段 schema（默认 release/schemas/mcp-gate-fragment.schema.json）",
    )
    parser.add_argument("--out", default=None, help="报告 JSON 输出路径（缺省打印 stdout）")
    args = parser.parse_args(argv)

    report = build_report(Path(args.fragments_dir), Path(args.schema))
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"verdict={report['verdict']} -> {args.out}", file=sys.stderr)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    print(render(report), file=sys.stderr)
    # exit 0 仅当 READY；BLOCKED/REJECTED 均 ≠ 0 —— CI 可直接当门禁条件
    return 0 if report["verdict"] == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
