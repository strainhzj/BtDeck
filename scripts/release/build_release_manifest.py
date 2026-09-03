#!/usr/bin/env python3
"""发布清单生成器（release-artifact-equivalence-gate W5 批次 D / G10）。

按 release/schemas/release-manifest.schema.json 生成 release-manifest.json：
  - artifacts 七项逐一登记；sha256 引用签名后 digest（signing-digests-*.json 的
    post_sha256；无记录的文件制品现场重算）；docker 制品 manifest digest
  - evidence G0~G10 每门必有条目（schema 要求）；状态发现规则（诚实索引，不冒认）：
      release/build/gate-fragments/<G>.json   批次 E 的标准门禁片段（有则读 status）
      release/build/gate-report.json          G1/G4/G5（verify_release_bundle 本轮产出）
      release/build/sbom/index.json           G9 SBOM 面
      signing-digests-*.json                  G9 签名面（signed→PASS / unsigned→INDETERMINATE
                                              / BLOCKED|FAILED→FAIL / 无记录→NOT_RUN）
      其余（G0/G2/G3/G6/G7/G8）无片段时登记 NOT_RUN + 约定路径
  - verdict：生成器只能写 REJECTED（任一 FAIL / digest 漂移）或 INDETERMINATE
    （NOT_RUN / unsigned / approver 为空）。CERTIFIED 只能由人工审批动作写入——
    verify_release_bundle.py 校验 CERTIFIED 时断言 approver 非空+全门 PASS+签名 signed
  - approver / approved_at 留空待人工（计划 §G10：审批对象是本清单而非单个文件名）

--emit-compose-env：从 manifest.compose 渲染 deploy/compose-release.env
（digest-only 模板 deploy/docker-compose.release.yml 的渲染输入）。

纯函数供 backend/tests/release/test_build_release_manifest.py 变异测试。
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
DEFAULT_SCHEMA = (
    DEFAULT_PROJECT_ROOT / "release" / "schemas" / "release-manifest.schema.json"
)
DEFAULT_COMPOSE_TEMPLATE = (
    DEFAULT_PROJECT_ROOT / "deploy" / "docker-compose.release.yml"
)

FILE_KINDS: Tuple[Tuple[str, str], ...] = (
    # (kind, dist 相对路径工厂) —— version 运行期代入
    ("windows-exe", "btdeck.exe"),
    ("windows-setup", "BtDeck-v{version}-windows-x64-setup.exe"),
    ("linux-binary", "btdeck"),
    ("linux-deb", "BtDeck-v{version}-linux-amd64.deb"),
    ("linux-rpm", "BtDeck-v{version}-linux-amd64.rpm"),
)
DOCKER_KINDS: Tuple[str, ...] = ("docker-backend", "docker-frontend")

FRAGMENT_GATES: Tuple[str, ...] = ("G0", "G2", "G3", "G6", "G7", "G8")
GATE_REPORT_GATES: Tuple[str, ...] = ("G1", "G4", "G5")
ALL_GATES: Tuple[str, ...] = tuple(f"G{i}" for i in range(11))
VALID_EVIDENCE_STATUS = ("PASS", "FAIL", "INDETERMINATE", "NOT_RUN")

# 各制品 kind → build-info staging 目录（build_info_sha256 用；缺文件为 null）
STAGING_BY_KIND = {
    "windows-exe": "windows-exe",
    "windows-setup": "windows-exe",
    "linux-binary": "linux-binary",
    "linux-deb": "linux-binary",
    "linux-rpm": "linux-binary",
    "docker-backend": "docker-backend",
    "docker-frontend": "docker-frontend",
}


class ManifestError(RuntimeError):
    """fail-closed。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifact_inventory(
    dist_dir: Path, version: str
) -> Dict[str, Optional[Path]]:
    """文件制品清点（docker 制品走签名记录，不在此列）。"""
    inventory: Dict[str, Optional[Path]] = {}
    for kind, pattern in FILE_KINDS:
        path = dist_dir / pattern.format(version=version)
        inventory[kind] = path if path.is_file() else None
    return inventory


def merge_signing_records(bundle_dir: Path) -> Dict[str, Dict[str, object]]:
    """合并 signing-digests-*.json 分片 → kind → record（后读覆盖先读，正常每 kind 只出现一次）。"""
    records: Dict[str, Dict[str, object]] = {}
    for path in sorted(bundle_dir.glob("signing-digests-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("records", []):
            records[str(record["kind"])] = record
    return records


def load_canonical_build_info(bundle_dir: Path) -> Dict[str, object]:
    for staging in ("docker-backend", "linux-binary", "windows-exe"):
        path = bundle_dir / staging / "build-info.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise ManifestError(
        f"build-info 全部缺失：{bundle_dir}/{{docker-backend,linux-binary,windows-exe}}/build-info.json"
    )


def fragment_evidence(bundle_dir: Path, gate: str) -> Tuple[str, Optional[str]]:
    """批次 E 标准门禁片段：有则读 status（校验枚举），无则 NOT_RUN。"""
    path = bundle_dir / "gate-fragments" / f"{gate}.json"
    if not path.is_file():
        return "NOT_RUN", None
    payload = json.loads(path.read_text(encoding="utf-8"))
    status = str(payload.get("status", "INDETERMINATE"))
    if status not in VALID_EVIDENCE_STATUS:
        status = "INDETERMINATE"
    return status, sha256_file(path)


def gate_report_evidence(bundle_dir: Path, gate: str) -> Tuple[str, Optional[str]]:
    """G1/G4/G5：verify_release_bundle 本轮产出的 gate-report.json 内嵌状态。"""
    path = bundle_dir / "gate-report.json"
    if not path.is_file():
        return "NOT_RUN", None
    payload = json.loads(path.read_text(encoding="utf-8"))
    status = str((payload.get("gates") or {}).get(gate, "INDETERMINATE"))
    if status not in VALID_EVIDENCE_STATUS:
        status = "INDETERMINATE"
    return status, sha256_file(path)


def signing_evidence(
    signing: Dict[str, Dict[str, object]]
) -> Tuple[str, Optional[str], List[str]]:
    """G9 签名面：四类签名目标全 signed→PASS；有 unsigned/记录缺失→INDETERMINATE；
    indeterminate（BLOCKED/FAILED）→FAIL；四类全无记录→NOT_RUN。

    记录缺失按 INDETERMINATE 处理（签名步骤未跑，不能因其它目标已签而漏报）。
    """
    signature_targets = (
        "windows-exe",
        "windows-setup",
        "docker-backend",
        "docker-frontend",
    )
    statuses: Dict[str, str] = {}
    for kind in signature_targets:
        record = signing.get(kind)
        if record is None:
            statuses[kind] = "missing"
        else:
            statuses[kind] = str(
                (record.get("signature") or {}).get("status", "indeterminate")
            )
    if not any(v != "missing" for v in statuses.values()):
        return "NOT_RUN", None, []
    if any(v == "indeterminate" for v in statuses.values()):
        failed = sorted(k for k, v in statuses.items() if v == "indeterminate")
        return "FAIL", None, [f"G9 签名状态 indeterminate：{failed}"]
    if all(v == "signed" for v in statuses.values()):
        return "PASS", None, []
    return "INDETERMINATE", None, []


def build_evidence(
    bundle_dir: Path,
    signing: Dict[str, Dict[str, object]],
    manifest_output: Path,
    verdict: str,
) -> List[Dict[str, object]]:
    evidence: List[Dict[str, object]] = []
    for gate in ALL_GATES:
        if gate in FRAGMENT_GATES:
            status, digest = fragment_evidence(bundle_dir, gate)
            evidence.append(
                {
                    "gate": gate,
                    "status": status,
                    "path": f"release/build/gate-fragments/{gate}.json",
                    "digest": digest,
                }
            )
        elif gate in GATE_REPORT_GATES:
            status, digest = gate_report_evidence(bundle_dir, gate)
            evidence.append(
                {
                    "gate": gate,
                    "status": status,
                    "path": "release/build/gate-report.json",
                    "digest": digest,
                }
            )
        elif gate == "G9":
            sbom_index = bundle_dir / "sbom" / "index.json"
            if sbom_index.is_file():
                evidence.append(
                    {
                        "gate": "G9",
                        "status": "PASS",
                        "path": "release/build/sbom/index.json",
                        "digest": sha256_file(sbom_index),
                    }
                )
            sign_status, _, _ = signing_evidence(signing)
            evidence.append(
                {
                    "gate": "G9",
                    "status": sign_status,
                    "path": "release/build/signing-digests-*.json",
                    "digest": None,
                }
            )
        elif gate == "G10":
            evidence.append(
                {
                    "gate": "G10",
                    "status": "FAIL" if verdict == "REJECTED" else "INDETERMINATE",
                    "path": (
                        str(manifest_output.relative_to(manifest_output.parents[2]))
                        if len(manifest_output.parents) >= 3
                        else str(manifest_output)
                    ),
                    "digest": None,  # 自引用，避免循环 digest
                }
            )
    return evidence


def compute_verdict(evidence: List[Dict[str, object]]) -> str:
    """生成器 verdict：任一 FAIL→REJECTED；否则 INDETERMINATE（NOT_RUN/unsigned/
    approver 空等任何未闭环因素）。CERTIFIED 永远不由生成器产出。"""
    if any(entry["status"] == "FAIL" for entry in evidence):
        return "REJECTED"
    return "INDETERMINATE"


def render_compose_env(compose: Dict[str, str]) -> str:
    """digest-only 模板的渲染输入（模板已带 sha256: 前缀，env 只给 hex）。"""
    return (
        f"BTDECK_BACKEND_DIGEST={compose['backend_digest'].split('sha256:')[-1]}\n"
        f"BTDECK_FRONTEND_DIGEST={compose['frontend_digest'].split('sha256:')[-1]}\n"
    )


def validate_manifest(manifest: Dict[str, object], schema_path: Path) -> List[str]:
    import jsonschema

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    return [
        f"schema 校验失败：{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(manifest), key=lambda e: list(e.absolute_path)
        )
    ]


def normalize_signature(
    signature: Optional[Dict[str, object]]
) -> Optional[Dict[str, object]]:
    """schema additionalProperties=false + signed_sha256 非空约束：只留
    mechanism/status/signed_sha256，且值为 None 的键整体省略（unsigned 无签名 digest）。

    签名记录里的 signature_file/verified 等执行细节留在 signing-digests 分片，
    不进发布清单。
    """
    if not signature:
        return None
    normalized: Dict[str, object] = {
        "mechanism": signature.get("mechanism", "none"),
        "status": signature.get("status", "unsigned"),
    }
    if signature.get("signed_sha256") is not None:
        normalized["signed_sha256"] = signature["signed_sha256"]
    return normalized


def build_artifacts_section(
    inventory: Dict[str, Optional[Path]],
    signing: Dict[str, Dict[str, object]],
    bundle_dir: Path,
    version: str,
) -> Tuple[List[Dict[str, object]], List[str]]:
    artifacts: List[Dict[str, object]] = []
    problems: List[str] = []

    missing = [kind for kind, path in inventory.items() if path is None]
    missing += [kind for kind in DOCKER_KINDS if kind not in signing]
    if missing:
        raise ManifestError(f"制品缺失（fail-closed）：{sorted(missing)}")

    for kind, path in inventory.items():
        assert path is not None  # missing 已在上面拦截
        record = signing.get(kind)
        actual = sha256_file(path)
        if record is not None:
            recorded_post = record.get("post_sha256")
            if recorded_post != actual:
                problems.append(
                    f"{kind}: 文件 digest 与签名记录漂移（记录 {str(recorded_post)[:12]} vs 实际 {actual[:12]}）"
                )
        staging = bundle_dir / STAGING_BY_KIND[kind] / "build-info.json"
        artifacts.append(
            {
                "kind": kind,
                "path": (
                    str(path.relative_to(bundle_dir.parents[1]))
                    if len(bundle_dir.parents) >= 2
                    else str(path)
                ),
                "sha256": actual,
                "size_bytes": path.stat().st_size,
                "build_info_sha256": (
                    sha256_file(staging) if staging.is_file() else None
                ),
                "internal": kind == "linux-binary",
                "signature": normalize_signature((record or {}).get("signature")),
            }
        )

    for kind in DOCKER_KINDS:
        record = signing[kind]
        size_bytes = record.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes < 1:
            raise ManifestError(f"{kind}: 签名记录缺合法 size_bytes（{size_bytes!r}）")
        staging = bundle_dir / STAGING_BY_KIND[kind] / "build-info.json"
        artifacts.append(
            {
                "kind": kind,
                "path": str(record.get("ref")),
                "sha256": record.get("post_sha256"),
                "size_bytes": size_bytes,
                "digest_ref": f"{record.get('ref')}@sha256:{record.get('post_sha256')}",
                "build_info_sha256": (
                    sha256_file(staging) if staging.is_file() else None
                ),
                "signature": normalize_signature(record.get("signature")),
                "internal": False,
            }
        )
    return artifacts, problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument(
        "--bundle-dir", type=Path, default=None, help="默认 <root>/release/build"
    )
    parser.add_argument("--dist-dir", type=Path, default=None, help="默认 <root>/dist")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="默认 <bundle-dir>/release-manifest.json",
    )
    parser.add_argument(
        "--emit-compose-env",
        action="store_true",
        help="渲染 deploy/compose-release.env",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    bundle_dir = args.bundle_dir or (root / "release" / "build")
    dist_dir = args.dist_dir or (root / "dist")
    output = args.output or (bundle_dir / "release-manifest.json")

    try:
        build_info = load_canonical_build_info(bundle_dir)
        version = str(build_info["product_version"])
        inventory = collect_artifact_inventory(dist_dir, version)
        signing = merge_signing_records(bundle_dir)

        artifacts, problems = build_artifacts_section(
            inventory, signing, bundle_dir, version
        )

        docker_records = {kind: signing[kind] for kind in DOCKER_KINDS}
        compose = {
            "backend_digest": f"sha256:{docker_records['docker-backend']['post_sha256']}",
            "frontend_digest": f"sha256:{docker_records['docker-frontend']['post_sha256']}",
            "compose_file": "deploy/docker-compose.release.yml",
        }

        # verdict 需先于 evidence（G10 条目引用 verdict）——先算证据状态骨架再回填
        evidence = build_evidence(bundle_dir, signing, output, verdict="INDETERMINATE")
        if problems:
            # digest 漂移是确定失败：G10 记 FAIL（evidence 已有 G10 条目，就地置 FAIL）
            for entry in evidence:
                if entry["gate"] == "G10":
                    entry["status"] = "FAIL"
        verdict = compute_verdict(evidence)

        manifest = {
            "schema_version": 1,
            "product_version": version,
            "git_tag": build_info.get("git_tag"),
            "git_sha": build_info.get("git_sha"),
            "source_date_epoch": build_info.get("source_date_epoch"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "build_id": build_info.get("build_id"),
            "frontend_asset_manifest_sha256": build_info.get(
                "frontend_manifest_sha256"
            ),
            "artifacts": artifacts,
            "evidence": evidence,
            "compose": compose,
            "verdict": verdict,
            "approver": None,
            "approved_at": None,
        }

        errors = validate_manifest(manifest, args.schema)
        if errors:
            for error in errors:
                print(f"[FAIL] {error}", file=sys.stderr)
            return 1

        output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[{verdict}] release manifest 已生成：{output}（approver 待人工）")
        for problem in problems:
            print(f"  problem: {problem}", file=sys.stderr)

        if args.emit_compose_env:
            env_path = root / "deploy" / "compose-release.env"
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text(render_compose_env(compose), encoding="utf-8")
            print(f"compose 渲染输入已生成：{env_path}")

        return 0 if verdict != "REJECTED" else 1
    except ManifestError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
