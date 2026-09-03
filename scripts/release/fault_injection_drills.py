#!/usr/bin/env python3
"""W6 故障注入演练驱动（release-artifact-equivalence-gate task .9 批次 F）。

六类注入 × 预期门（计划 §W6：每类均须停在预期门禁且不产生发布动作）：
  old-frontend     → G5  verify_release_bundle：制品间 frontend-asset-manifest 字节漂移
                       （旧前端混入形态——同 build-info 声明但实际资源不同）
  qb-drift         → G2  check_dependencies：qbittorrent-api 版本在源声明与锁间漂移
  missing-contract → G5  deploy/verify-package：真实 EXE 归档剔除契约 JSON 条目
  rpm-upgrade-down → G6  aggregate_gate_report：RPM 升级停服（lifecycle verdict=FAIL）
  docker-mix       → G8  compare_snapshots：异构前端快照（镜像混装形态）→ unexplained>0
  digest-tamper    → G10 verify_release_bundle --require-manifest：签名/清单后制品字节篡改

语义与 W4 变异演练一致：演练断言"必须红"——任何一类未红在预期门即本脚本非零退出。
每类证据（工具原始输出 + 判定）落 <evidence-dir>/<name>.log，汇总 summary.json。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent
PY = sys.executable


class DrillFailure(RuntimeError):
    """注入未红在预期门（演练失败）。"""


def _run(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
    proc = subprocess.run(
        [PY, *cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _write_log(evidence_dir: Path, name: str, text: str) -> None:
    (evidence_dir / f"{name}.log").write_text(text, encoding="utf-8")


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise DrillFailure(message)


# ---------------------------------------------------------------- 注入 1：旧前端 → G5


def drill_old_frontend(root: Path) -> Tuple[str, str]:
    """两个制品 staging 共享同一 build-info，但其中一个的前端 manifest 字节漂移。

    形态：制品声称同一 frontend_manifest_sha256（G1 身份一致），实际嵌入的
    frontend-asset-manifest 是旧构建（G5 逐字节比对抓出）——"旧前端"混入。
    """
    work = Path(tempfile.mkdtemp(prefix="btdeck-inject-oldfe-"))
    try:
        bundle = work / "release" / "build"
        for kind in ("docker-backend", "linux-binary"):
            src = root / "release" / "build" / kind
            dst = bundle / kind
            dst.mkdir(parents=True)
            for name in ("build-info.json", "frontend-asset-manifest.json"):
                shutil.copyfile(src / name, dst / name)
        # 注入：docker-backend 的 manifest 追加一个空格（旧构建字节形态）
        tampered = bundle / "docker-backend" / "frontend-asset-manifest.json"
        tampered.write_bytes(tampered.read_bytes() + b" ")

        rc, output = _run(
            [
                "scripts/release/verify_release_bundle.py",
                "--project-root",
                str(work),
                "--skip-package-extraction",
            ],
            cwd=root,
        )
        _expect(rc != 0, f"verify 应报红（rc={rc}）\n{output}")
        _expect(
            "frontend-asset-manifest 与基准" in output and "docker-backend" in output,
            f"应红在 G5 manifest 比对：\n{output}",
        )
        return "G5", output
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- 注入 2：qB 漂移 → G2


def drill_qb_drift(root: Path) -> Tuple[str, str]:
    """requirements.txt 的 qbittorrent-api 声明改成与锁不一致的版本。"""
    work = Path(tempfile.mkdtemp(prefix="btdeck-inject-qb-"))
    try:
        (work / "backend").mkdir(parents=True)
        (work / "deploy").mkdir()
        shutil.copyfile(
            root / "backend/requirements.txt", work / "backend/requirements.txt"
        )
        shutil.copyfile(
            root / "backend/requirements-lock.txt",
            work / "backend/requirements-lock.txt",
        )
        for name in (
            "requirements-windows-package.txt",
            "requirements-linux-package.txt",
        ):
            shutil.copyfile(root / f"deploy/{name}", work / f"deploy/{name}")

        req = work / "backend/requirements.txt"
        text = req.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if "qbittorrent-api" in line]
        _expect(len(lines) == 1, f"requirements.txt 应恰有一行 qB 声明：{lines}")
        text = text.replace(lines[0], "qbittorrent-api~=2025.99.0  # injected drift")
        req.write_text(text, encoding="utf-8")

        rc, output = _run(
            ["scripts/release/check_dependencies.py", "--project-root", str(work)],
            cwd=root,
        )
        _expect(rc != 0, f"check_dependencies 应报红（rc={rc}）\n{output}")
        _expect("qbittorrent-api" in output, f"红因应指明 qB 漂移：\n{output}")
        return "G2", output
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- 注入 3：缺契约 JSON → G5


def drill_missing_contract(root: Path) -> Tuple[str, str]:
    """真实 dist/btdeck.exe 归档条目剔除契约 JSON → verify_entries 报红。

    verify-package 的 CLI 只吃完整制品文件，本注入在条目层做外科手术式剔除
    （collect_archive_entries 为同一入口），verifier 逻辑零改动。
    """
    exe = root / "dist" / "btdeck.exe"
    if not exe.is_file():
        raise DrillFailure(f"真实制品缺失：{exe}（先构建或复用本地 dist）")

    spec = importlib.util.spec_from_file_location(
        "btdeck_verify_package", root / "deploy" / "verify-package.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    entries = module.collect_archive_entries(exe)
    contract_keys = [k for k in entries if "contracts/" in k and k.endswith(".json")]
    _expect(bool(contract_keys), "真实归档应含契约 JSON 条目")
    victim = contract_keys[0]
    del entries[victim]

    try:
        module.verify_entries(entries)
        raise DrillFailure(f"剔除 {victim} 后 verify_entries 未报红")
    except module.VerificationFailure as exc:
        output = f"[注入] 剔除条目：{victim}\n[验证] VerificationFailure: {exc}"
        _expect("缺失" in str(exc) or "必需" in str(exc), f"红因应指明条目缺失：{exc}")
        return "G5", output


# ---------------------------------------------------------------- 注入 4：RPM 升级停服 → G6


def _aggregation_fixture(work: Path, rpm_verdict: str) -> None:
    """最小汇聚夹具：全绿骨架 + 指定 RPM 升级 verdict（其余 w3 全 PASS）。"""
    bundle = work / "release" / "build"
    frag = bundle / "gate-fragments"
    frag.mkdir(parents=True)
    stamp = "2026-09-03T00:00:00+00:00"
    for gate in ("G0", "G2", "G3"):
        (frag / f"{gate}.json").write_text(
            json.dumps({"gate": gate, "status": "PASS", "generated_at": stamp}),
            encoding="utf-8",
        )
    (bundle / "gate-report.json").write_text(
        json.dumps(
            {
                "gates": {
                    "G1": "PASS",
                    "G4": "PASS",
                    "G5": "PASS",
                    "G9_signing": "PASS",
                    "G10": "PASS",
                }
            }
        ),
        encoding="utf-8",
    )
    (bundle / "release-manifest.json").write_text(
        json.dumps({"verdict": "CERTIFIED", "approver": "drill-approver"}),
        encoding="utf-8",
    )
    w3 = work / "release" / "evidence" / "w3"
    w3.mkdir(parents=True)
    for name, verdict in (
        ("lifecycle-deb-fresh.json", "PASS"),
        ("lifecycle-deb-upgrade.json", "PASS"),
        ("lifecycle-rpm-fresh.json", "PASS"),
        ("lifecycle-rpm-upgrade.json", rpm_verdict),
        ("lifecycle-docker.json", "PASS"),
    ):
        (w3 / name).write_text(
            json.dumps({"scenario": name, "verdict": verdict}), encoding="utf-8"
        )
    (work / "w3-lifecycle-windows.json").write_text(
        json.dumps({"scenario": "windows", "verdict": "PASS"}), encoding="utf-8"
    )
    w4 = work / "release" / "evidence" / "w4"
    w4.mkdir(parents=True)
    (w4 / "compare-report.json").write_text(
        json.dumps({"candidates": {"rpm": {"total_diffs": 0, "unexplained": []}}}),
        encoding="utf-8",
    )
    w5 = work / "release" / "evidence" / "w5"
    w5.mkdir(parents=True)
    (w5 / "security-report.json").write_text(
        json.dumps({"verdict": "PASS"}), encoding="utf-8"
    )
    (work / "backend").mkdir()
    (work / "backend" / "requirements-lock.txt").write_text(
        "# lock\n", encoding="utf-8"
    )


def drill_rpm_upgrade_down(root: Path) -> Tuple[str, str]:
    """lifecycle-rpm-upgrade.json verdict=FAIL（升级后服务停摆形态）→ 汇聚 REJECTED。"""
    work = Path(tempfile.mkdtemp(prefix="btdeck-inject-rpm-"))
    try:
        _aggregation_fixture(work, rpm_verdict="FAIL")
        rc, output = _run(
            ["scripts/release/aggregate_gate_report.py", "--project-root", str(work)],
            cwd=root,
        )
        report = json.loads(
            (work / "release/build/gate-report-full.json").read_text(encoding="utf-8")
        )
        _expect(rc != 0, f"aggregate 应非零（REJECTED）（rc={rc}）\n{output}")
        _expect(
            report["verdict"] == "REJECTED", f"verdict 应 REJECTED：{report['verdict']}"
        )
        _expect(
            report["gate_status"]["G6"] == "FAIL",
            f"G6 应 FAIL：{report['gate_status']}",
        )
        _expect(
            all(report["gate_status"][g] == "PASS" for g in ("G7", "G8")),
            "其余门不应连带误伤",
        )
        return (
            "G6",
            output
            + f"\n[注入后] verdict={report['verdict']} G6={report['gate_status']['G6']}",
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- 注入 5：Docker 混装 → G8


def drill_docker_mix(root: Path) -> Tuple[str, str]:
    """异构前端快照（混装另一构建的前端镜像形态）→ compare unexplained>0 报红。

    复用 W4 B2 的真实变异夹具（m1-baseline/mutated-c11 为同工具链产物）。
    """
    base = root / "release/evidence/w4/b2/m1-baseline-c11.json"
    mutated = root / "release/evidence/w4/b2/m1-mutated-c11.json"
    if not (base.is_file() and mutated.is_file()):
        raise DrillFailure(f"W4 夹具缺失：{base} / {mutated}")

    rc, output = _run(
        [
            "scripts/release/compare_snapshots.py",
            "--baseline",
            str(base),
            "--candidates",
            str(mutated),
            "--exceptions",
            str(root / "release/equivalence-exceptions.json"),
        ],
        cwd=root,
    )
    _expect(rc != 0, f"compare 应报红（rc={rc}）\n{output}")
    _expect(
        "unexplained" in output and "C11_spa" in output,
        f"应红在 C11 SPA 资源差异：\n{output}",
    )
    return "G8", output


# ---------------------------------------------------------------- 注入 6：digest 篡改 → G10


def drill_digest_tamper(root: Path) -> Tuple[str, str]:
    """清单生成后篡改制品字节 → verify --require-manifest 红在 G10 篡改检测。"""
    work = Path(tempfile.mkdtemp(prefix="btdeck-inject-digest-"))
    try:
        dist = work / "dist"
        dist.mkdir(parents=True)
        shutil.copyfile(root / "dist/btdeck.exe", dist / "btdeck.exe")
        shutil.copyfile(root / "dist/btdeck", dist / "btdeck")
        shutil.copyfile(
            root / "dist/BtDeck-v1.0.6-linux-amd64.deb",
            dist / "BtDeck-v1.0.6-linux-amd64.deb",
        )
        shutil.copyfile(
            root / "dist/BtDeck-v1.0.6-linux-amd64.rpm",
            dist / "BtDeck-v1.0.6-linux-amd64.rpm",
        )
        (dist / "BtDeck-v1.0.6-windows-x64-setup.exe").write_bytes(
            b"drill-setup-fixture"
        )

        bundle = work / "release" / "build"
        staging = bundle / "linux-binary"
        staging.mkdir(parents=True)
        info = json.loads(
            (root / "release/build/linux-binary/build-info.json").read_text(
                encoding="utf-8"
            )
        )
        info["dirty"] = False  # 演练夹具取干净身份（G1 不旁路拦截目标门）
        (staging / "build-info.json").write_text(json.dumps(info), encoding="utf-8")
        shutil.copyfile(
            root / "release/build/linux-binary/frontend-asset-manifest.json",
            staging / "frontend-asset-manifest.json",
        )
        # sign_artifacts 从 <root>/release/tool-versions.json 读 cosign 固定条目；
        # verify 的 compose 模板默认 <root>/deploy/docker-compose.release.yml
        shutil.copyfile(
            root / "release/tool-versions.json", work / "release" / "tool-versions.json"
        )
        (work / "deploy").mkdir(exist_ok=True)
        shutil.copyfile(
            root / "deploy/docker-compose.release.yml",
            work / "deploy" / "docker-compose.release.yml",
        )

        # 真实 docker 签名编排（本机镜像，drill unsigned）产签名记录
        rc, output = _run(
            [
                "scripts/release/sign_artifacts.py",
                "--target",
                "docker",
                "--allow-unsigned-drill",
                "--project-root",
                str(work),
            ],
            cwd=root,
        )
        _expect(rc == 0, f"drill 签名应成功（rc={rc}）\n{output}")

        rc, output = _run(
            [
                "scripts/release/build_release_manifest.py",
                "--project-root",
                str(work),
            ],
            cwd=root,
        )
        _expect(rc == 0, f"清单应生成（rc={rc}）\n{output}")
        manifest = json.loads(
            (bundle / "release-manifest.json").read_text(encoding="utf-8")
        )
        _expect(manifest["verdict"] == "INDETERMINATE", "drill 清单应为 INDETERMINATE")

        # 篡改前基线：verify 通过（证明红因确系篡改）
        rc0, out0 = _run(
            [
                "scripts/release/verify_release_bundle.py",
                "--project-root",
                str(work),
                "--skip-package-extraction",
                "--require-manifest",
            ],
            cwd=root,
        )
        _expect(rc0 == 0, f"篡改前 verify 应绿（rc={rc0}）\n{out0}")

        # 注入：清单生成后篡改制品字节
        victim = dist / "BtDeck-v1.0.6-linux-amd64.deb"
        victim.write_bytes(victim.read_bytes() + b"\x00tampered")

        rc1, out1 = _run(
            [
                "scripts/release/verify_release_bundle.py",
                "--project-root",
                str(work),
                "--skip-package-extraction",
                "--require-manifest",
            ],
            cwd=root,
        )
        _expect(rc1 != 0, f"篡改后 verify 应红（rc={rc1}）\n{out1}")
        _expect(
            "G10 linux-deb manifest digest 与实际文件不一致" in out1,
            f"应红在 G10 篡改检测：\n{out1}",
        )
        return "G10", out0 + "\n---- 注入：deb 追加字节 ----\n" + out1
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- 主流程

DRILLS = (
    ("old-frontend", "旧前端混入（manifest 字节漂移）", "G5", drill_old_frontend),
    ("qb-drift", "qbittorrent-api 版本漂移", "G2", drill_qb_drift),
    ("missing-contract", "打包内容缺契约 JSON", "G5", drill_missing_contract),
    (
        "rpm-upgrade-down",
        "RPM 升级停服（lifecycle FAIL）",
        "G6",
        drill_rpm_upgrade_down,
    ),
    ("docker-mix", "Docker 混装（异构前端快照）", "G8", drill_docker_mix),
    ("digest-tamper", "制品 digest 篡改", "G10", drill_digest_tamper),
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="默认 <root>/release/evidence/w6/injections",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    evidence_dir = args.evidence_dir or (
        root / "release" / "evidence" / "w6" / "injections"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    summary: List[Dict[str, object]] = []
    failed = False
    for name, desc, gate, fn in DRILLS:
        print(f"== 注入 {name}（{desc}→ 预期 {gate}）==")
        try:
            actual_gate, output = fn(root)
            _expect(actual_gate == gate, f"内部门标注不符：{actual_gate} != {gate}")
            _write_log(evidence_dir, name, output)
            summary.append(
                {
                    "name": name,
                    "expect_gate": gate,
                    "result": "BLOCKED-AT-EXPECTED-GATE",
                    "desc": desc,
                }
            )
            print(f"   [红在预期门 {gate}] 证据：{evidence_dir / (name + '.log')}")
        except (DrillFailure, OSError) as exc:
            failed = True
            summary.append(
                {
                    "name": name,
                    "expect_gate": gate,
                    "result": "NOT-BLOCKED",
                    "error": str(exc),
                    "desc": desc,
                }
            )
            print(f"   [FAIL] {exc}", file=sys.stderr)

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run": "batch F fault injection drill",
        "semantics": "每类注入必须红在预期门（与 W4 变异演练同语义：红=通过）",
        "drills": summary,
        "all_blocked_as_expected": not failed,
    }
    (evidence_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        (
            "[PASS] 六类注入全部红在预期门"
            if not failed
            else "[FAIL] 存在未按预期阻断的注入"
        ),
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
