#!/usr/bin/env python3
"""BtDeck 跨制品快照比较器（release-artifact-equivalence-gate W4 / G8）。

以一份基准快照（baseline）比对其余制品快照；任何字段差异必须命中
release/equivalence-exceptions.json 的允许规则，否则报红（fail-closed）。

允许差异规则铁律（计划 §G8）：
  - 每条规则必须精确到快照 JSON 路径（支持通配 * 单段），带 reason（为什么
    允许不同）与 expires（YYYY-MM-DD，过期即失效报红）。
  - 禁止宽泛规则：不允许 "*" 路径、不允许以 * 结尾吞掉整棵子树、不允许
    "删除整个 data / 忽略所有 msg" 类规则。
  - 未被任何差异命中的过期/冗余规则会被报告（防规则腐化成摆设）。

用法：
  python compare_snapshots.py --baseline snapshot-deb.json \
      --candidates snapshot-rpm.json snapshot-docker.json \
      [--exceptions release/equivalence-exceptions.json]
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_EXCEPTIONS_PATH = (
    Path(__file__).resolve().parents[2] / "release" / "equivalence-exceptions.json"
)

# 路径分段通配：JSON 键含 . 的场景用 ~ 转义不在本项目出现（键均为标识符）
_PATH_OK = re.compile(r"^[A-Za-z0-9_.\[\]\-~*]+$")


def flatten(value: Any, prefix: str = "") -> List[Tuple[str, Any]]:
    """展平嵌套 JSON 为 (路径, 值) 列表（路径用 . 分段，列表元素带 [i]）。"""
    out: List[Tuple[str, Any]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            out.extend(flatten(value[key], f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            out.extend(flatten(item, f"{prefix}[{i}]"))
    else:
        out.append((prefix, value))
    return out


def path_matches(pattern: str, path: str) -> bool:
    """单段通配匹配：* 只匹配一个路径段（禁止跨段吞子树）。"""
    if not _PATH_OK.fullmatch(pattern):
        return False
    if pattern == "*":
        return False  # 根通配按非法处理（load_exceptions 已拒绝，双保险）
    if (
        "*" in pattern
        and pattern.endswith("*")
        and pattern.count("*") == 1
        and pattern[:-1].endswith(".")
    ):
        return False  # "scenarios.*" 类吞段规则拒绝
    seg_p = pattern.split(".")
    seg = path.split(".")
    if len(seg_p) != len(seg):
        return False
    return all(fnmatch.fnmatchcase(s, p) for p, s in zip(seg_p, seg))


def load_exceptions(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """读取并校验允许差异规则；返回 (规则列表, 结构问题)。"""
    if not path.is_file():
        return [], [f"exceptions 文件缺失：{path}"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    rules_raw = raw.get("allowed_differences", []) if isinstance(raw, dict) else []
    problems: List[str] = []
    rules: List[Dict[str, str]] = []
    for i, rule in enumerate(rules_raw):
        if not isinstance(rule, dict):
            problems.append(f"rule[{i}] 非对象")
            continue
        pattern = str(rule.get("path", ""))
        reason = str(rule.get("reason", "")).strip()
        expires = str(rule.get("expires", "")).strip()
        if not pattern or not _PATH_OK.fullmatch(pattern):
            problems.append(f"rule[{i}] 路径非法或缺失: {pattern!r}")
            continue
        if pattern == "*" or pattern.startswith("*.") or pattern.endswith(".*"):
            problems.append(f"rule[{i}] 宽泛路径被禁止: {pattern!r}")
            continue
        if not reason or len(reason) < 8:
            problems.append(f"rule[{i}] 缺少实质 reason（≥8 字符）")
            continue
        try:
            if date.fromisoformat(expires) < date.today():
                problems.append(f"rule[{i}] 已过期: {expires} ({pattern})")
                continue
        except ValueError:
            problems.append(f"rule[{i}] expires 非 YYYY-MM-DD: {expires!r}")
            continue
        rules.append({"path": pattern, "reason": reason, "expires": expires})
    return rules, problems


def diff_snapshots(
    baseline: Dict[str, Any], candidate: Dict[str, Any]
) -> List[Dict[str, str]]:
    """逐路径差异（基准侧缺失/候选侧新增/值不同）。"""
    flat_base = dict(flatten(baseline))
    flat_cand = dict(flatten(candidate))
    diffs: List[Dict[str, str]] = []
    for path, value in flat_base.items():
        if path not in flat_cand:
            diffs.append(
                {"path": path, "kind": "missing_in_candidate", "baseline": repr(value)}
            )
        elif flat_cand[path] != value:
            diffs.append(
                {
                    "path": path,
                    "kind": "value_mismatch",
                    "baseline": repr(value),
                    "candidate": repr(flat_cand[path]),
                }
            )
    for path, value in flat_cand.items():
        if path not in flat_base:
            diffs.append(
                {"path": path, "kind": "extra_in_candidate", "candidate": repr(value)}
            )
    return diffs


def compare(
    baseline: Dict[str, Any],
    candidates: Dict[str, Dict[str, Any]],
    rules: List[Dict[str, str]],
) -> Tuple[bool, Dict[str, Any]]:
    """比较全部候选；返回 (是否通过, 报告)。未命中的规则记为 stale。"""
    used_patterns: set = set()
    report: Dict[str, Any] = {"candidates": {}, "stale_rules": [], "verdict": "PASS"}
    overall_ok = True

    for name, cand in candidates.items():
        diffs = diff_snapshots(baseline, cand)
        unexplained: List[Dict[str, str]] = []
        for d in diffs:
            hit = next((r for r in rules if path_matches(r["path"], d["path"])), None)
            if hit:
                used_patterns.add(hit["path"])
            else:
                unexplained.append(d)
        ok = not unexplained
        overall_ok = overall_ok and ok
        report["candidates"][name] = {
            "total_diffs": len(diffs),
            "explained": len(diffs) - len(unexplained),
            "unexplained": unexplained[:50],
            "verdict": "PASS" if ok else "FAIL",
        }

    report["stale_rules"] = [r for r in rules if r["path"] not in used_patterns]
    if not overall_ok:
        report["verdict"] = "FAIL"
    return overall_ok, report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument(
        "--candidates",
        required=True,
        nargs="+",
        type=Path,
        help="其余制品快照（文件名作名称）",
    )
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS_PATH)
    args = parser.parse_args(argv)

    rules, problems = load_exceptions(args.exceptions)
    if problems:
        print("[FAIL] exceptions 规则问题：")
        for p in problems:
            print(f"  - {p}")
        return 2

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidates = {
        p.stem: json.loads(p.read_text(encoding="utf-8")) for p in args.candidates
    }
    ok, report = compare(baseline, candidates, rules)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    stale = report["stale_rules"]
    if stale:
        print(f"[WARN] {len(stale)} 条规则未命中任何差异（防规则腐化，应复核清理）：")
        for r in stale:
            print(f"  - {r['path']} (expires {r['expires']})")
    print(f"verdict: {report['verdict']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
