#!/usr/bin/env python3
"""W5 安全扫描器（release-artifact-equivalence-gate task .9 / G9）。

输入 generate_sbom.py 的 SBOM 目录，执行三类检查（工具镜像按
release/tool-versions.json 固定 digest）：

  漏洞   grype 逐 SBOM 扫描（grype sbom:... -o json）
         策略（计划 §12.2/§12.3，fail-closed）：
           Critical       不可豁免阻断（例外命中也不放行）
           High           默认阻断；命中有效限时例外才放行
           Medium 及以下   记录不阻断
  秘密   gitleaks 扫工作区 + git 全历史（--redact，证据不含明文）；
         命中经 release/secret-allowlist.json（rule+文件粒度，须
         justification/owner/expires，限期 60 天）过滤后剩余即不可豁免阻断
  许可证 SBOM components 的 license 命中 release/license-denylist.json 即
         不可豁免阻断

例外文件 release/security-exceptions.json：每条 High 例外须四要素齐全
（justification=不可利用证明 / owner=风险接受人 / remediation_version=补救
版本 / expires=到期日），到期日距登记日不超过 30 天且未过期；文件本身不
合法（缺字段/过期/超 30 天）= 整体 FAIL（fail-closed，不放行任何 High）。

输出 --output-dir（默认 release/evidence/w5）：
  grype-<target>.json / gitleaks.json / security-report.json
verdict 只能 PASS / BLOCKED；BLOCKED 退出码 1。

纯函数（load_exceptions / aggregate_grype / evaluate_policy / check_licenses）
供 backend/tests/release/test_scan_security.py 回归与变异。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent

CRITICAL = "Critical"
HIGH = "High"
BLOCKING_SEVERITIES = (CRITICAL, HIGH)
REQUIRED_EXCEPTION_FIELDS = (
    "id",
    "scope",
    "justification",
    "owner",
    "remediation_version",
    "expires",
    "registered",
)
MAX_EXCEPTION_DAYS = 30
# tracked-no-fix 例外（2026-09-03 用户批准的政策修订）：仅适用于
# 「发行版当前修订已最新 + 扫描器 fix=[] + 上游已发布修复但 distro 未回植」
# 的 Critical；三条件中后两条机器校验（fix=[] 来自 finding；upstream_fix
# 必填即上游已修的证据），到期未消解自动阻断。有修复可用的 Critical 仍硬阻断。
TRACKED_NO_FIX_KIND = "tracked-no-fix"
TRACKED_NO_FIX_EXTRA_FIELDS = ("kind", "upstream_fix")


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_exceptions(path: Path) -> Tuple[List[dict], List[str]]:
    """载入并校验例外文件。返回 (有效例外, 问题列表)——文件不合法时例外
    置空（fail-closed：不放行任何 High）。"""
    if not path.is_file():
        return [], []
    payload = json.loads(path.read_text(encoding="utf-8"))
    problems: List[str] = []
    valid: List[dict] = []
    seen_ids = set()
    for exc in payload.get("exceptions", []):
        missing = [f for f in REQUIRED_EXCEPTION_FIELDS if not exc.get(f)]
        if missing:
            problems.append(f"例外缺字段 {missing}: {exc.get('id', '?')}")
            continue
        if exc["id"] in seen_ids:
            problems.append(f"例外编号重复: {exc['id']}")
            continue
        seen_ids.add(exc["id"])
        scope = exc.get("scope") or {}
        if not (scope.get("vuln_id") or scope.get("package")):
            problems.append(f"例外 scope 须含 vuln_id 或 package: {exc['id']}")
            continue
        try:
            registered = _parse_date(str(exc["registered"]))
            expires = _parse_date(str(exc["expires"]))
        except ValueError:
            problems.append(f"例外日期格式非法(YYYY-MM-DD): {exc['id']}")
            continue
        if expires > registered + timedelta(days=MAX_EXCEPTION_DAYS):
            problems.append(
                f"例外到期日超过登记+{MAX_EXCEPTION_DAYS}天: {exc['id']} "
                f"({exc['registered']}→{exc['expires']})"
            )
            continue
        if expires < date.today():
            problems.append(f"例外已过期: {exc['id']} ({exc['expires']})")
            continue
        if exc.get("kind") == TRACKED_NO_FIX_KIND and not exc.get("upstream_fix"):
            problems.append(
                f"tracked-no-fix 例外缺 upstream_fix（上游已修证据）: {exc['id']}"
            )
            continue
        valid.append(exc)
    return valid, problems


def exception_matches(finding: dict, exc: dict) -> bool:
    """例外 scope 命中判定：vuln_id 精确（含别名）或 package 级。

    不支持按制品目标限定：findings 跨目标聚合（同一漏洞命中任一制品即为
    发布风险），按目标限定会把"仅豁免其一"放大成"全部豁免"（fail-open）。
    """
    scope = exc.get("scope") or {}
    if scope.get("vuln_id"):
        ids = {finding.get("vuln_id"), *finding.get("aliases", [])}
        return scope["vuln_id"] in ids
    if scope.get("package"):
        return scope["package"] == finding.get("package")
    return False


def aggregate_grype(raw_by_target: Dict[str, dict]) -> List[dict]:
    """多目标 grype 原始结果 → 去重 findings 列表。

    唯一键 (vuln_id, package)；target 聚合进 targets[]；severity 取最高
    （同一漏洞不同目标分级不一致时按 Critical>High>...）。
    """
    rank = {
        "Critical": 4,
        "High": 3,
        "Medium": 2,
        "Low": 1,
        "Negligible": 1,
        "Unknown": 0,
    }
    merged: Dict[Tuple[str, str], dict] = {}
    for target, raw in raw_by_target.items():
        for match in raw.get("matches", []):
            vuln = match.get("vulnerability") or {}
            artifact = match.get("artifact") or {}
            vid = vuln.get("id") or ""
            pkg = artifact.get("name") or ""
            if not vid or not pkg:
                continue
            aliases = sorted(
                {
                    v.get("id")
                    for v in vuln.get("relatedVulnerabilities", [])
                    if v.get("id")
                }
            )
            key = (vid, pkg)
            entry = merged.setdefault(
                key,
                {
                    "vuln_id": vid,
                    "package": pkg,
                    "version": artifact.get("version"),
                    "severity": vuln.get("severity") or "Unknown",
                    "fix_versions": sorted(
                        {f for f in vuln.get("fix", {}).get("versions", []) if f}
                    ),
                    "aliases": aliases,
                    "targets": [],
                },
            )
            entry["targets"].append(target)
            if rank.get(vuln.get("severity"), 0) > rank.get(entry["severity"], 0):
                entry["severity"] = vuln["severity"]
    for entry in merged.values():
        entry["targets"] = sorted(set(entry["targets"]))
    return sorted(
        merged.values(), key=lambda e: (-rank.get(e["severity"], 0), e["vuln_id"])
    )


def evaluate_policy(
    findings: List[dict], exceptions: List[dict], today: Optional[date] = None
) -> dict:
    """阻断策略。

    - Critical 有修复可用：不可豁免硬阻断（§12.2）。
    - Critical 无修复可用（fix=[]）：仅当命中 tracked-no-fix 例外（2026-09-03
      政策修订三条件）才放行为跟踪豁免，否则仍阻断。
    - High：命中有效限时例外放行，否则阻断。
    """
    today = today or date.today()
    blocked: List[dict] = []
    waived: List[dict] = []
    recorded: List[dict] = []
    for finding in findings:
        if finding["severity"] not in BLOCKING_SEVERITIES:
            recorded.append(finding)
            continue
        hit = next((e for e in exceptions if exception_matches(finding, e)), None)
        valid_hit = hit and _parse_date(str(hit["expires"])) >= today

        if finding["severity"] == CRITICAL:
            has_fix = bool(finding.get("fix_versions"))
            if has_fix:
                blocked.append(
                    {
                        **finding,
                        "reason": "Critical 有修复可用，不可豁免（§12.2）"
                        + (f"；例外 {hit['id']} 不适用" if hit else ""),
                    }
                )
            elif valid_hit and hit.get("kind") == TRACKED_NO_FIX_KIND:
                waived.append(
                    {
                        **finding,
                        "exception": hit["id"],
                        "owner": hit["owner"],
                        "waiver_kind": TRACKED_NO_FIX_KIND,
                        "upstream_fix": hit.get("upstream_fix"),
                    }
                )
            else:
                blocked.append(
                    {
                        **finding,
                        "reason": "Critical 无修复可用且无有效 tracked-no-fix 例外",
                    }
                )
        elif valid_hit:
            waived.append({**finding, "exception": hit["id"], "owner": hit["owner"]})
        else:
            blocked.append({**finding, "reason": "High 无有效例外"})
    return {"blocked": blocked, "waived": waived, "recorded": recorded}


def check_licenses(sbom_by_target: Dict[str, dict], denylist: List[str]) -> List[dict]:
    """SBOM 许可证 × 禁用清单 → 命中列表（package, license, target）。"""
    denied: List[dict] = []
    for target, sbom in sbom_by_target.items():
        for comp in sbom.get("components", []):
            licenses = comp.get("licenses") or []
            texts: List[str] = []
            for lic in licenses:
                if isinstance(lic, dict):
                    expr = (
                        lic.get("license", {}).get("id")
                        or lic.get("license", {}).get("name")
                        or ""
                    )
                    texts.append(expr)
                elif isinstance(lic, str):
                    texts.append(lic)
            for text in texts:
                if any(d.lower() == str(text).lower() for d in denylist):
                    denied.append(
                        {"package": comp.get("name"), "license": text, "target": target}
                    )
    return denied


MAX_SECRET_ALLOW_DAYS = 60


def load_secret_allowlist(path: Path) -> Tuple[List[dict], List[str]]:
    """秘密误报白名单装载与校验（规则同例外文件：缺字段/超期/过期即整体失效
    ——fail-closed，失效时所有命中按未登记阻断）。"""
    if not path.is_file():
        return [], []
    payload = json.loads(path.read_text(encoding="utf-8"))
    problems: List[str] = []
    valid: List[dict] = []
    for entry in payload.get("entries", []):
        missing = [
            f
            for f in ("rule_id", "file", "justification", "owner", "expires")
            if not entry.get(f)
        ]
        if missing:
            problems.append(f"秘密白名单缺字段 {missing}: {entry.get('file', '?')}")
            continue
        try:
            expires = _parse_date(str(entry["expires"]))
            registered = _parse_date(str(entry.get("registered", entry["expires"])))
        except ValueError:
            problems.append(f"秘密白名单日期非法: {entry['file']}")
            continue
        if expires > registered + timedelta(days=MAX_SECRET_ALLOW_DAYS):
            problems.append(
                f"秘密白名单限期超过{MAX_SECRET_ALLOW_DAYS}天: {entry['file']}"
            )
            continue
        if expires < date.today():
            problems.append(f"秘密白名单已过期: {entry['file']} ({entry['expires']})")
            continue
        valid.append(entry)
    return valid, problems


def filter_allowed_secrets(findings: List[dict], allowlist: List[dict]) -> List[dict]:
    """gitleaks 命中 × 白名单 → 剩余（未登记）命中。file 按 gitleaks 报告的
    仓库相对路径精确匹配；rule_id 匹配 RuleID。"""
    allowed = {(e["rule_id"], e["file"].replace("\\", "/")) for e in allowlist}
    remaining = []
    for f in findings:
        key = (f.get("RuleID") or "", (f.get("File") or "").replace("\\", "/"))
        if key not in allowed:
            remaining.append(f)
    return remaining


def load_tool_image(tools_path: Path, tool: str) -> str:
    tools = json.loads(tools_path.read_text(encoding="utf-8"))
    entry = tools.get("tools", {}).get(tool)
    if not entry or "@" not in entry.get("image", ""):
        raise SystemExit(f"[FAIL] tool-versions.json 缺 {tool} 的 digest 固定镜像")
    return entry["image"]


def run_grype(
    grype_image: str, sbom_dir: Path, out_dir: Path, targets: List[str]
) -> Dict[str, dict]:
    raw_by_target: Dict[str, dict] = {}
    for target in targets:
        sbom_path = sbom_dir / f"sbom-{target}.json"
        if not sbom_path.is_file():
            raise SystemExit(f"[FAIL] SBOM 缺失：{sbom_path}")
        report = out_dir / f"grype-{target}.json"
        # grype 的文件输出是 --file（"-o json=path" 是 syft 语法，CI 第四轮
        # 实测 rc=1+空报告）；退出码 1 同时表示"有命中"与"失败"，两者只能靠
        # 报告可解析且含 matches 键区分——解析失败一律致命并倾倒容器输出
        proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{sbom_dir.as_posix()}:/sboms:ro",
                "-v",
                f"{out_dir.as_posix()}:/out",
                grype_image,
                f"sbom:/sboms/sbom-{target}.json",
                "-o",
                "json",
                "--file",
                f"/out/grype-{target}.json",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode not in (0, 1):
            sys.stderr.write(proc.stdout + proc.stderr)
            raise SystemExit(f"[FAIL] grype 扫描 {target} 失败（rc={proc.returncode}）")
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(proc.stdout + proc.stderr)
            raise SystemExit(
                f"[FAIL] grype {target} 报告不可解析（{exc}；rc={proc.returncode}）"
            ) from exc
        if "matches" not in payload:
            sys.stderr.write(proc.stdout + proc.stderr)
            raise SystemExit(f"[FAIL] grype {target} 报告缺 matches 键（疑似失败运行）")
        raw_by_target[target] = payload
        print(
            f"grype {target}: matches={len(raw_by_target[target].get('matches', []))}"
        )
    return raw_by_target


def run_gitleaks(gitleaks_image: str, project_root: Path, out_dir: Path) -> List[dict]:
    report = out_dir / "gitleaks.json"
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{project_root.as_posix()}:/repo",
            "-v",
            f"{out_dir.as_posix()}:/out",
            "-w",
            "/repo",
            gitleaks_image,
            "detect",
            "--source",
            "/repo",
            "--report-format",
            "json",
            "--report-path",
            "/out/gitleaks.json",
            "--redact",
            "--exit-code",
            "0",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not report.is_file():
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"[FAIL] gitleaks 扫描失败（rc={proc.returncode}）")
    findings = json.loads(report.read_text(encoding="utf-8"))
    print(f"gitleaks: findings={len(findings)}")
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--sbom-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--exceptions",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "release" / "security-exceptions.json",
    )
    parser.add_argument(
        "--license-denylist",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "release" / "license-denylist.json",
    )
    parser.add_argument(
        "--tools",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "release" / "tool-versions.json",
    )
    parser.add_argument(
        "--secret-allowlist",
        type=Path,
        default=DEFAULT_PROJECT_ROOT / "release" / "secret-allowlist.json",
    )
    parser.add_argument(
        "--skip-gitleaks",
        action="store_true",
        help="本地无 .git 全历史时跳过（CI 必跑）",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    sbom_dir = (args.sbom_dir or root / "release" / "build" / "sbom").resolve()
    out_dir = (args.output_dir or root / "release" / "evidence" / "w5").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not (sbom_dir / "index.json").is_file():
        raise SystemExit(
            f"[FAIL] SBOM 目录未就绪（缺 index.json）：{sbom_dir}，先跑 generate_sbom.py"
        )
    targets = sorted(
        json.loads((sbom_dir / "index.json").read_text(encoding="utf-8"))["targets"]
    )

    exceptions, problems = load_exceptions(args.exceptions)
    fail_closed = bool(problems)

    grype_image = load_tool_image(args.tools, "grype")
    raw_by_target = run_grype(grype_image, sbom_dir, out_dir, targets)
    findings = aggregate_grype(raw_by_target)

    sbom_by_target = {
        t: json.loads((sbom_dir / f"sbom-{t}.json").read_text(encoding="utf-8"))
        for t in targets
    }
    denylist = json.loads(args.license_denylist.read_text(encoding="utf-8"))["denied"]
    denied_licenses = check_licenses(sbom_by_target, denylist)

    gitleaks_image = load_tool_image(args.tools, "gitleaks")
    if args.skip_gitleaks:
        raw_secrets: List[dict] = []
        print("gitleaks: SKIPPED（--skip-gitleaks）")
    else:
        raw_secrets = run_gitleaks(gitleaks_image, root, out_dir)
    secret_allowlist, secret_problems = load_secret_allowlist(args.secret_allowlist)
    secrets = filter_allowed_secrets(raw_secrets, secret_allowlist)
    print(
        f"gitleaks: raw={len(raw_secrets)} allowlisted={len(raw_secrets) - len(secrets)} blocking={len(secrets)}"
    )

    policy = evaluate_policy(findings, exceptions)
    blocked = list(policy["blocked"])
    if denied_licenses:
        blocked.extend({"kind": "license", **d} for d in denied_licenses)
    if secrets:
        blocked.extend(
            {"kind": "secret", "rule": s.get("RuleID"), "file": s.get("File")}
            for s in secrets
        )
    if fail_closed:
        blocked.append(
            {
                "kind": "exceptions-invalid",
                "reason": "例外文件不合法，全部 High 按无例外处理",
                "problems": problems,
            }
        )
    if secret_problems:
        blocked.append(
            {
                "kind": "secret-allowlist-invalid",
                "reason": "秘密白名单不合法，全部命中按未登记阻断",
                "problems": secret_problems,
            }
        )

    by_severity = {
        s: 0 for s in ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
    }
    for f in findings:
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    verdict = "BLOCKED" if blocked else "PASS"
    report = {
        "schema_version": 1,
        "verdict": verdict,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "targets": targets,
        "vulnerabilities": {
            "by_severity": by_severity,
            "blocked": policy["blocked"],
            "waived": policy["waived"],
            "recorded_count": len(policy["recorded"]),
        },
        "secrets": {
            "raw_count": len(raw_secrets),
            "blocking": len(secrets),
            "blocking_findings": [
                {"rule": s.get("RuleID"), "file": s.get("File")} for s in secrets[:50]
            ],
        },
        "licenses_denied": denied_licenses,
        "exceptions_applied": len(policy["waived"]),
        "exceptions_problems": problems,
    }
    (out_dir / "security-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {k: report[k] for k in ("verdict", "vulnerabilities")}, ensure_ascii=False
        )[:400]
    )
    if verdict == "BLOCKED":
        print(
            f"[FAIL] 安全扫描 BLOCKED：{len(blocked)} 项（报告 {out_dir / 'security-report.json'}）",
            file=sys.stderr,
        )
        return 1
    print(f"[PASS] 安全扫描通过；报告 {out_dir / 'security-report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
