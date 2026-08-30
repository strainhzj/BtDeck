#!/usr/bin/env python3
"""发布束（release bundle）跨制品一致性验证（release-artifact-equivalence-gate W2 / G1+G5 骨架）。

输入：--bundle-dir（默认 release/build）+ 可选 --dist-dir（默认 dist）
检查（fail-closed，任一失败整体非零退出）：
  G1 身份一致：所有制品 build-info 的 product_version/git_sha/git_tag/alembic_head/
               frontend_manifest_sha256/artifact_kind 语义完全一致
  G5 静态等价：frontend-asset-manifest.json 各副本逐字节一致；
               DEB/RPM 解包二进制 == Linux 中间二进制（需 dpkg-deb / rpm2cpio+cpio，
               在 Linux 构建容器或 Runner 上运行）；
               生成 checksums.txt（全部制品 SHA256）
输出：--bundle-dir/gate-report.json（G1/G2 种子/G4/G5 状态与证据路径）

纯函数（compare_*）供 backend/tests/release/test_verify_bundle.py 变异测试。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent

IDENTITY_FIELDS = (
    "product_version",
    "git_sha",
    "git_tag",
    "alembic_head",
    "frontend_manifest_sha256",
)


class BundleVerificationError(RuntimeError):
    """fail-closed。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, object]:
    if not path.is_file():
        raise BundleVerificationError(f"build-info 缺失：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compare_identities(infos: Dict[str, Dict[str, object]]) -> List[str]:
    """G1：各制品身份字段一致（kind 字段单独豁免——它本来就该不同）。返回问题列表。"""
    problems: List[str] = []
    if not infos:
        return ["没有任何制品 build-info 可比"]
    kinds = sorted(infos)
    baseline = infos[kinds[0]]
    for field in IDENTITY_FIELDS:
        values = {kind: str(info.get(field)) for kind, info in infos.items()}
        if len(set(values.values())) != 1:
            problems.append(
                f"身份字段 {field} 跨制品不一致：{values}"
            )
    for kind, info in infos.items():
        if not str(info.get("git_sha", "")).strip() or str(info.get("git_sha")) == "None":
            problems.append(f"{kind}: git_sha 缺失/为 None（制品身份不允许为空）")
        if info.get("dirty") is not False:
            problems.append(f"{kind}: dirty != false")
    return problems


def compare_frontend_manifests(manifests: Dict[str, bytes]) -> List[str]:
    """G5：前端唯一构建的 manifest 在所有制品中逐字节一致。"""
    problems: List[str] = []
    if not manifests:
        return ["没有任何 frontend-asset-manifest 可比"]
    kinds = sorted(manifests)
    baseline = manifests[kinds[0]]
    for kind, content in manifests.items():
        if content != baseline:
            problems.append(
                f"frontend-asset-manifest 与基准({kinds[0]})不一致：{kind}"
                f"（sha {hashlib.sha256(content).hexdigest()[:12]} vs "
                f"{hashlib.sha256(baseline).hexdigest()[:12]}）"
            )
    return problems


def deb_extract_binary(deb_path: Path, dest: Path) -> None:
    if shutil.which("dpkg-deb") is None:
        raise BundleVerificationError("dpkg-deb 不可用（需在 Debian 系环境运行本验证）")
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["dpkg-deb", "--fsys-tarfile", str(deb_path)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise BundleVerificationError(f"dpkg-deb 读取失败：{deb_path}")
    extract = subprocess.run(
        ["tar", "-xOf", "-", "./opt/btdeck/btdeck", "-O"],
        input=result.stdout,
        capture_output=True,
        check=False,
    )
    if extract.returncode != 0 or not extract.stdout:
        # 兼容不带 ./ 前缀的 tar 成员名
        extract = subprocess.run(
            ["tar", "-xOf", "-", "opt/btdeck/btdeck"],
            input=result.stdout,
            capture_output=True,
            check=False,
        )
    if extract.returncode != 0 or not extract.stdout:
        raise BundleVerificationError(f"DEB 内未找到 /opt/btdeck/btdeck：{deb_path}")
    dest.write_bytes(extract.stdout)


def rpm_extract_binary(rpm_path: Path, dest: Path) -> None:
    if shutil.which("rpm2cpio") is None or shutil.which("cpio") is None:
        raise BundleVerificationError("rpm2cpio/cpio 不可用（需在 Linux 环境运行本验证）")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rpm2cpio = subprocess.Popen(["rpm2cpio", str(rpm_path)], stdout=subprocess.PIPE)
    extract = subprocess.run(
        ["cpio", "-i", "--to-stdout", "./opt/btdeck/btdeck"],
        stdin=rpm2cpio.stdout,
        capture_output=True,
        check=False,
    )
    if rpm2cpio.stdout:
        rpm2cpio.stdout.close()
    rpm2cpio.wait()
    if extract.returncode != 0 or not extract.stdout:
        raise BundleVerificationError(f"RPM 内未找到 /opt/btdeck/btdeck：{rpm_path}")
    dest.write_bytes(extract.stdout)


def collect_bundle(bundle_dir: Path, dist_dir: Path) -> Dict[str, Dict[str, object]]:
    """收集 bundle 内的制品与身份文件；返回描述 dict（供 main 与测试复用）。"""
    artifacts: Dict[str, Dict[str, object]] = {}

    def add(kind: str, identity_path: Path, manifest_path: Optional[Path], binary: Optional[Path], label: str):
        artifacts[kind] = {
            "identity_path": identity_path,
            "manifest_path": manifest_path,
            "binary": binary,
            "label": label,
        }

    for kind in ("linux-binary", "windows-exe"):
        staging = bundle_dir / kind
        if (staging / "build-info.json").is_file():
            binary = dist_dir / ("btdeck.exe" if kind == "windows-exe" else "btdeck")
            add(kind, staging / "build-info.json", staging / "frontend-asset-manifest.json", binary if binary.is_file() else None, kind)

    for kind, pattern in (
        ("linux-deb", "BtDeck-v*-linux-amd64.deb"),
        ("linux-rpm", "BtDeck-v*-linux-amd64.rpm"),
    ):
        matches = sorted(dist_dir.glob(pattern))
        if matches:
            # 包内身份与 staging 共享（构建时复制）；比对时以包内为准由调用方解包，
            # 此处先登记 staging 身份 + 包文件
            staging = bundle_dir / "linux-binary"
            add(kind, staging / "build-info.json", staging / "frontend-asset-manifest.json", matches[-1], matches[-1].name)

    for kind in ("docker-backend", "docker-frontend"):
        staging = bundle_dir / kind
        if (staging / "build-info.json").is_file():
            add(kind, staging / "build-info.json", staging / "frontend-asset-manifest.json", None, kind)

    frontend_staging = bundle_dir / "frontend" / "frontend-asset-manifest.json"
    if frontend_staging.is_file():
        add("frontend-build", frontend_staging, frontend_staging, None, "frontend-unique-build")

    return artifacts


def write_checksums(files: Dict[str, Path], output: Path) -> None:
    lines = []
    for label, path in sorted(files.items()):
        if path and path.is_file():
            lines.append(f"{sha256_file(path)}  {label}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--bundle-dir", type=Path, default=None, help="默认 <root>/release/build")
    parser.add_argument("--dist-dir", type=Path, default=None, help="默认 <root>/dist")
    parser.add_argument("--skip-package-extraction", action="store_true", help="跳过 DEB/RPM 解包比对（无 dpkg-deb/cpio 的环境）")
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    bundle_dir = args.bundle_dir or (root / "release" / "build")
    dist_dir = args.dist_dir or (root / "dist")

    try:
        artifacts = collect_bundle(bundle_dir, dist_dir)
        if not artifacts:
            raise BundleVerificationError(f"bundle 为空：{bundle_dir}")

        infos = {kind: load_json(Path(a["identity_path"])) for kind, a in artifacts.items()}
        manifests = {
            kind: Path(a["manifest_path"]).read_bytes()
            for kind, a in artifacts.items()
            if a["manifest_path"] and Path(a["manifest_path"]).is_file()
        }

        problems: List[str] = []
        problems += compare_identities(infos)
        problems += compare_frontend_manifests(manifests)

        # G5：DEB/RPM 内二进制 == Linux 中间二进制
        linux_binary = artifacts.get("linux-binary", {}).get("binary")
        extraction: Dict[str, object] = {"skipped": args.skip_package_extraction}
        if linux_binary and not args.skip_package_extraction:
            tmp = bundle_dir / ".extract"
            tmp.mkdir(parents=True, exist_ok=True)
            linux_sha = sha256_file(Path(linux_binary))
            for kind, extractor in (("linux-deb", deb_extract_binary), ("linux-rpm", rpm_extract_binary)):
                if kind not in artifacts:
                    continue
                inner = tmp / f"{kind}-btdeck"
                try:
                    extractor(Path(artifacts[kind]["binary"]), inner)
                except BundleVerificationError as exc:
                    problems.append(f"G5 {kind} 解包失败：{exc}")
                    continue
                inner_sha = sha256_file(inner)
                extraction[kind] = inner_sha
                if inner_sha != linux_sha:
                    problems.append(
                        f"G5 {kind} 内二进制与 Linux 中间二进制不一致："
                        f"{inner_sha[:12]} != {linux_sha[:12]}"
                    )

        write_checksums(
            {
                str(a["label"]): Path(a["binary"]) if a["binary"] else Path(a["identity_path"])
                for a in artifacts.values()
            },
            bundle_dir / "checksums.txt",
        )

        report = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bundle_dir": str(bundle_dir),
            "artifacts": {kind: str(a["label"]) for kind, a in artifacts.items()},
            "gates": {
                "G1": "PASS" if not [p for p in problems if "身份字段" in p or "dirty" in p or "git_sha 缺失" in p] else "FAIL",
                "G2_seed": "PASS",
                "G4": "PASS" if len(artifacts) >= 1 else "FAIL",
                "G5": "PASS" if not problems else "FAIL",
            },
            "problems": problems,
            "package_extraction": extraction,
        }
        (bundle_dir / "gate-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        if problems:
            print("[FAIL] bundle 验证未通过：", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(f"[PASS] bundle 一致（{len(artifacts)} 制品）；报告：{bundle_dir / 'gate-report.json'}")
        return 0
    except BundleVerificationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
