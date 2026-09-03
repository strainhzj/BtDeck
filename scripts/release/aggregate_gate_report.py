#!/usr/bin/env python3
"""门禁汇聚器（release-artifact-equivalence-gate W5 批次 E / G10）。

输入（rc-gate job 用 download-artifact merge-multiple 汇齐各上游 job 的证据后运行；
本地验证用 backend/tests/release/test_aggregate_gate_report.py 夹具）：
  release/build/gate-fragments/G<n>.json   标准门禁片段（显式，优先于推导）
  release/build/gate-report.json           w5-sign-docker 终验（G1/G4/G5/G9_signing/G10）
  release/build/release-manifest.json      发布清单（verdict/approver）
  release/evidence/w3/lifecycle-*.json     生命周期报告（deb/rpm/docker；verdict 键）
  w3-lifecycle-windows.json                Windows 生命周期报告（job 根目录，verdict 键）
  release/evidence/w4/compare-report.json  黑盒契约 compare 报告（candidates）
  release/evidence/w5/security-report.json 安全扫描报告（verdict 键）

门映射与推导规则（诚实索引，缺失=NOT_RUN、坏证据=INDETERMINATE）：
  G0 片段（w0 探针 job 写出）
  G1/G4/G5 gate-report.json 的 gates 值
  G2 片段（rc-gate 用 regression API 映射写出）+ requirements-lock.txt 存在
  G3 片段（regression API 映射）
  G6 deb/rpm/windows 生命周期报告 verdict 全 PASS（空/坏文件=INDETERMINATE）
  G7 docker 生命周期报告 verdict
  G8 compare 报告全候选 unexplained==0
  G9 双面：security-report.verdict + gate-report.G9_signing
  G10 gate-report.G10 + manifest.verdict（CERTIFIED 需 approver）

verdict（§12.1/§14）：
  任一门 FAIL → REJECTED；任一门非 PASS → INDETERMINATE（不得发布）；
  全 PASS 且 manifest.verdict==CERTIFIED 且 approver 非空 → CERTIFIED。

输出：--bundle-dir/gate-report-full.json + --bundle-dir/release-summary.md（§14 模板）。
纯函数（derive_*/collect/compute/render）供变异测试。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_FRAGMENT_SCHEMA = (
    DEFAULT_PROJECT_ROOT / "release" / "schemas" / "gate-fragment.schema.json"
)

GATES = tuple(f"G{i}" for i in range(11))
VALID_STATUS = ("PASS", "FAIL", "INDETERMINATE", "NOT_RUN")


class AggregateError(RuntimeError):
    """fail-closed。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_maybe(path: Path) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    """容错加载：缺失→(None, None)；空/坏 JSON→(None, 问题描述)。"""
    if not path.is_file():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"证据不可解析（{path.name}: {exc}）"
    if not isinstance(payload, dict):
        return None, f"证据非对象（{path.name}）"
    return payload, None


def validate_fragment(fragment: Dict[str, object], schema_path: Path) -> List[str]:
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    return [
        f"片段 schema 校验失败 {'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(fragment)
    ]


def load_fragments(
    fragments_dir: Path, schema_path: Path
) -> Tuple[Dict[str, Dict[str, object]], List[str]]:
    """加载并校验全部显式片段 → {gate: fragment}。schema 违例=问题（fail-closed 语义由调用方定级）。"""
    fragments: Dict[str, Dict[str, object]] = {}
    problems: List[str] = []
    if not fragments_dir.is_dir():
        return fragments, problems
    for path in sorted(fragments_dir.glob("G*.json")):
        payload, load_problem = load_json_maybe(path)
        if payload is None:
            problems.append(f"片段坏文件：{path.name}（{load_problem}）")
            continue
        problems += validate_fragment(payload, schema_path)
        gate = str(payload.get("gate", path.stem))
        if gate not in GATES:
            problems.append(f"片段 gate 非法：{path.name}（{gate}）")
            continue
        if str(payload.get("status")) not in VALID_STATUS:
            problems.append(f"片段 status 非法：{path.name}（{payload.get('status')}）")
            continue
        fragments[gate] = payload
    return fragments, problems


# ---------------------------------------------------------------- 推导器（纯）


def gate_report_status(gate_report: Optional[Dict[str, object]], key: str) -> str:
    """gate-report.json 的 gates 值；缺失/非法 → NOT_RUN（推导侧不编造状态）。"""
    if gate_report is None:
        return "NOT_RUN"
    value = str((gate_report.get("gates") or {}).get(key, ""))
    return value if value in VALID_STATUS else "NOT_RUN"


def lifecycle_verdicts(
    w3_dir: Path, windows_report: Path
) -> Tuple[Dict[str, Tuple[Optional[str], Optional[str]]], List[str]]:
    """收集生命周期报告 {(name, distro 类): (verdict, load_problem)}。

    lifecycle-docker.json 归 G7；release/evidence/w3/ 其余 lifecycle-*.json 与
    根目录 w3-lifecycle-windows.json 归 G6。
    """
    reports: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    problems: List[str] = []
    candidates: List[Path] = []
    if w3_dir.is_dir():
        candidates += [p for p in sorted(w3_dir.glob("lifecycle-*.json"))]
    if windows_report.is_file():
        candidates.append(windows_report)
    for path in candidates:
        payload, load_problem = load_json_maybe(path)
        if payload is None:
            if load_problem is None:
                continue  # 不存在的可选报告（如 windows 未跑）不算问题
            reports[path.name] = (None, load_problem)
            problems.append(f"w3 证据坏文件：{path.name}（{load_problem}）")
            continue
        reports[path.name] = (str(payload.get("verdict", "")), None)
    return reports, problems


def derive_g6(reports: Dict[str, Tuple[Optional[str], Optional[str]]]) -> str:
    """deb/rpm/windows 生命周期（docker 归 G7）：全 PASS→PASS；任一 FAIL→FAIL；
    有坏文件→INDETERMINATE；无任何报告→NOT_RUN。"""
    g6 = {
        name: value
        for name, value in reports.items()
        if name != "lifecycle-docker.json"
    }
    if not g6:
        return "NOT_RUN"
    if any(v[0] is None for v in g6.values()):
        return "INDETERMINATE"
    if any(v[0] != "PASS" for v in g6.values()):
        return "FAIL"
    return "PASS"


def derive_g7(reports: Dict[str, Tuple[Optional[str], Optional[str]]]) -> str:
    docker = reports.get("lifecycle-docker.json")
    if docker is None:
        return "NOT_RUN"
    verdict, problem = docker
    if problem or verdict is None:
        return "INDETERMINATE"
    return verdict if verdict in VALID_STATUS else "INDETERMINATE"


def derive_g8(compare_report: Optional[Dict[str, object]]) -> str:
    """compare 报告全候选 unexplained==0 → PASS；任一未解释差异 → FAIL；无报告 → NOT_RUN。"""
    if compare_report is None:
        return "NOT_RUN"
    candidates = compare_report.get("candidates")
    if not isinstance(candidates, dict) or not candidates:
        return "INDETERMINATE"
    for name, detail in candidates.items():
        unexplained = (detail or {}).get("unexplained")
        if not isinstance(unexplained, list):
            return "INDETERMINATE"
        if unexplained:
            return "FAIL"
    return "PASS"


def derive_g9(
    security_report: Optional[Dict[str, object]],
    gate_report: Optional[Dict[str, object]],
) -> str:
    """双面：安全扫描 verdict + 签名面 G9_signing。任一 FAIL→FAIL；任一非 PASS
    （含单面缺失 NOT_RUN）→INDETERMINATE；双面缺失→NOT_RUN。

    单面缺失不能再由另一面兜成 PASS（漏报）：无扫描报告时仅签名绿不是 G9 绿。
    """
    scan = str(security_report.get("verdict", "")) if security_report else "NOT_RUN"
    signing = gate_report_status(gate_report, "G9_signing")
    statuses = [scan, signing]
    if all(s == "NOT_RUN" for s in statuses):
        return "NOT_RUN"
    if any(s == "FAIL" for s in statuses):
        return "FAIL"
    if any(s != "PASS" for s in statuses):
        return "INDETERMINATE"
    return "PASS"


def derive_g10(
    gate_report: Optional[Dict[str, object]], manifest: Optional[Dict[str, object]]
) -> str:
    """G10=证据闭环与晋级（manifest 完整、digest 未变化、审批完成）：
    verify 终验 FAIL 或 manifest REJECTED → FAIL；verify PASS 且 manifest CERTIFIED
    （approver 由 schema/verify 断言链保证）→ PASS；审批未完成（manifest
    INDETERMINATE）→ INDETERMINATE——「审批完成」是 G10 的检查项，不能算 PASS。"""
    verify = gate_report_status(gate_report, "G10")
    if verify == "FAIL":
        return "FAIL"
    if verify == "NOT_RUN":
        return "NOT_RUN"
    if manifest is None:
        return "INDETERMINATE"
    verdict = str(manifest.get("verdict", ""))
    if verdict == "REJECTED":
        return "FAIL"
    if verdict == "CERTIFIED":
        return "PASS"
    return "INDETERMINATE"


def collect_gate_states(
    fragments: Dict[str, Dict[str, object]],
    gate_report: Optional[Dict[str, object]],
    manifest: Optional[Dict[str, object]],
    lifecycle: Dict[str, Tuple[Optional[str], Optional[str]]],
    compare_report: Optional[Dict[str, object]],
    security_report: Optional[Dict[str, object]],
    lock_exists: bool,
) -> Tuple[Dict[str, Dict[str, object]], List[str]]:
    """片段优先（显式 > 推导）；推导填空。返回 {gate: {status, source, evidence}}。"""
    problems: List[str] = []
    derived = {
        "G1": gate_report_status(gate_report, "G1"),
        "G4": gate_report_status(gate_report, "G4"),
        "G5": gate_report_status(gate_report, "G5"),
        "G6": derive_g6(lifecycle),
        "G7": derive_g7(lifecycle),
        "G8": derive_g8(compare_report),
        "G9": derive_g9(security_report, gate_report),
        "G10": derive_g10(gate_report, manifest),
    }
    states: Dict[str, Dict[str, object]] = {}
    for gate in GATES:
        fragment = fragments.get(gate)
        if fragment is not None:
            states[gate] = {
                "status": str(fragment["status"]),
                "source": f"fragment:release/build/gate-fragments/{gate}.json",
                "summary": fragment.get("summary", ""),
            }
            continue
        if gate in derived:
            states[gate] = {"status": derived[gate], "source": "derived", "summary": ""}
            continue
        # G0/G2/G3 只有片段一条路：无片段即 NOT_RUN（G2 另要求锁存在）
        states[gate] = {
            "status": "NOT_RUN",
            "source": "missing-fragment",
            "summary": "",
        }
    if not lock_exists and states["G2"]["status"] == "PASS":
        problems.append("G2 片段 PASS 但 backend/requirements-lock.txt 缺失")
        states["G2"]["status"] = "FAIL"
    return states, problems


def compute_aggregate_verdict(
    gate_states: Dict[str, Dict[str, object]],
    manifest: Optional[Dict[str, object]],
) -> str:
    """§12.1：任一 FAIL→REJECTED；任一非 PASS→INDETERMINATE；
    全 PASS 还须 manifest CERTIFIED+approver 才 CERTIFIED（审批属人工）。"""
    statuses = {str(v["status"]) for v in gate_states.values()}
    if "FAIL" in statuses:
        return "REJECTED"
    if statuses != {"PASS"}:
        return "INDETERMINATE"
    if manifest is None:
        return "INDETERMINATE"
    if str(manifest.get("verdict")) == "CERTIFIED" and manifest.get("approver"):
        return "CERTIFIED"
    return "INDETERMINATE"


def render_release_summary(
    gate_states: Dict[str, Dict[str, object]],
    manifest: Optional[Dict[str, object]],
    verdict: str,
) -> str:
    """§14 发布摘要（markdown）。"""
    lines = [
        "# BtDeck 发布摘要（release-artifact-equivalence-gate）",
        "",
        f"- 判定：**{verdict}**（CERTIFIED=可晋级 / REJECTED=确定失败 / INDETERMINATE=不得发布）",
        f"- 生成时间：{datetime.now(timezone.utc).isoformat()}",
    ]
    if manifest is not None:
        lines += [
            f"- 候选：{manifest.get('product_version')} / {manifest.get('git_tag')} / {manifest.get('git_sha')}",
            f"- 审批：approver={manifest.get('approver') or '（待人工）'} approved_at={manifest.get('approved_at') or '—'}",
            f"- 制品：{len(manifest.get('artifacts') or [])} 项（详见 release-manifest.json）",
        ]
    lines += ["", "| 门禁 | 状态 | 来源 |", "|---|---|---|"]
    for gate in GATES:
        state = gate_states[gate]
        lines.append(f"| {gate} | {state['status']} | {state['source']} |")
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument(
        "--bundle-dir", type=Path, default=None, help="默认 <root>/release/build"
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_FRAGMENT_SCHEMA)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="默认 <bundle-dir>/gate-report-full.json",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    bundle_dir = args.bundle_dir or (root / "release" / "build")
    output = args.output or (bundle_dir / "gate-report-full.json")

    try:
        fragments, problems = load_fragments(bundle_dir / "gate-fragments", args.schema)
        gate_report, problem = load_json_maybe(bundle_dir / "gate-report.json")
        if problem:
            problems.append(f"gate-report.json {problem}")
        manifest, problem = load_json_maybe(bundle_dir / "release-manifest.json")
        if problem:
            problems.append(f"release-manifest.json {problem}")
        compare_report, problem = load_json_maybe(
            root / "release/evidence/w4/compare-report.json"
        )
        if problem:
            problems.append(f"compare-report.json {problem}")
        security_report, problem = load_json_maybe(
            root / "release/evidence/w5/security-report.json"
        )
        if problem:
            problems.append(f"security-report.json {problem}")
        lifecycle, lifecycle_problems = lifecycle_verdicts(
            root / "release/evidence/w3", root / "w3-lifecycle-windows.json"
        )
        problems += lifecycle_problems

        gate_states, state_problems = collect_gate_states(
            fragments,
            gate_report,
            manifest,
            lifecycle,
            compare_report,
            security_report,
            lock_exists=(root / "backend/requirements-lock.txt").is_file(),
        )
        problems += state_problems
        verdict = compute_aggregate_verdict(gate_states, manifest)

        report = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "gates": gate_states,
            "gate_status": {gate: str(gate_states[gate]["status"]) for gate in GATES},
            "verdict": verdict,
            "problems": problems,
            "inputs": {
                "fragments": sorted(fragments),
                "gate_report": gate_report is not None,
                "manifest": manifest is not None,
                "lifecycle_reports": sorted(lifecycle),
                "compare_report": compare_report is not None,
                "security_report": security_report is not None,
            },
        }
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary_path = bundle_dir / "release-summary.md"
        summary_path.write_text(
            render_release_summary(gate_states, manifest, verdict), encoding="utf-8"
        )
        print(f"[{verdict}] 门禁汇聚完成：{output}")
        for gate in GATES:
            print(
                f"  {gate}: {gate_states[gate]['status']}（{gate_states[gate]['source']}）"
            )
        for problem in problems:
            print(f"  problem: {problem}", file=sys.stderr)
        # 聚合器自身失败（坏证据/schema 违例）或 REJECTED 都非零；INDETERMINATE 归 0
        # （drill 语义合法态），CERTIFIED 判定由 rc-gate 断言步骤复核
        return 1 if (verdict == "REJECTED" or problems) else 0
    except AggregateError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
