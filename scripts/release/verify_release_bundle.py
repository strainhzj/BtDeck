#!/usr/bin/env python3
"""发布束（release bundle）跨制品一致性验证（release-artifact-equivalence-gate W2 / G1+G5 骨架 + W5 批次 D / G9 签名面+G10 digest 闭环）。

输入：--bundle-dir（默认 release/build）+ 可选 --dist-dir（默认 dist）
检查（fail-closed，任一失败整体非零退出）：
  G1 身份一致：所有制品 build-info 的 product_version/git_sha/git_tag/alembic_head/
               frontend_manifest_sha256/artifact_kind 语义完全一致
  G5 静态等价：frontend-asset-manifest.json 各副本逐字节一致；
               DEB/RPM 解包二进制 == Linux 中间二进制（需 dpkg-deb / rpm2cpio+cpio，
               在 Linux 构建容器或 Runner 上运行）；
               生成 checksums.txt（全部制品 SHA256）
  G9 签名面（W5/D）：signing-digests-*.json 合并校验——正式模式非 SIGNED 阻断、
               演练 unsigned 记 INDETERMINATE、SIGNED 文件制品 post_sha256 现场重算
  G10 digest 闭环（W5/D）：release-manifest.json 的 artifacts[].sha256 == 现场重算
               （文件制品，篡改检测核心）/ == 签名记录（docker 交叉）；
               compose 模板渲染后 digest-only 且与 manifest.compose 配对一致；
               CERTIFIED 断言链（approver 非空+全门 PASS+签名全 signed）
输出：--bundle-dir/gate-report.json（G1/G2 种子/G4/G5/G9_signing/G10 状态与证据路径）

纯函数（compare_*）供 backend/tests/release/test_verify_bundle.py 变异测试。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent

IDENTITY_FIELDS = (
    "product_version",
    "git_sha",
    "git_tag",
    "alembic_head",
    "frontend_manifest_sha256",
)

# W5 批次 D：G9 签名面 + G10 digest 闭环（release-manifest + compose 模板一致性）
SIGNATURE_KINDS = ("windows-exe", "windows-setup", "docker-backend", "docker-frontend")
FILE_KINDS = ("windows-exe", "windows-setup", "linux-binary", "linux-deb", "linux-rpm")
DIGEST_REF_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
# image 值可能含 ${VAR:?message with spaces} 形式的插值（消息带空格），须捕获整行再替换
IMAGE_LINE_RE = re.compile(r"^\s+image:\s*(.+?)\s*$")
COMPOSE_SERVICE_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
COMPOSE_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([-?]))?([^}]*)\}")


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
    for field in IDENTITY_FIELDS:
        values = {kind: str(info.get(field)) for kind, info in infos.items()}
        if len(set(values.values())) != 1:
            problems.append(f"身份字段 {field} 跨制品不一致：{values}")
    for kind, info in infos.items():
        if (
            not str(info.get("git_sha", "")).strip()
            or str(info.get("git_sha")) == "None"
        ):
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
        raise BundleVerificationError(
            "rpm2cpio/cpio 不可用（需在 Linux 环境运行本验证）"
        )
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

    def add(
        kind: str,
        identity_path: Path,
        manifest_path: Optional[Path],
        binary: Optional[Path],
        label: str,
    ):
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
            add(
                kind,
                staging / "build-info.json",
                staging / "frontend-asset-manifest.json",
                binary if binary.is_file() else None,
                kind,
            )

    for kind, pattern in (
        ("linux-deb", "BtDeck-v*-linux-amd64.deb"),
        ("linux-rpm", "BtDeck-v*-linux-amd64.rpm"),
    ):
        matches = sorted(dist_dir.glob(pattern))
        if matches:
            # 包内身份与 staging 共享（构建时复制）；比对时以包内为准由调用方解包，
            # 此处先登记 staging 身份 + 包文件
            staging = bundle_dir / "linux-binary"
            add(
                kind,
                staging / "build-info.json",
                staging / "frontend-asset-manifest.json",
                matches[-1],
                matches[-1].name,
            )

    for kind in ("docker-backend", "docker-frontend"):
        staging = bundle_dir / kind
        if (staging / "build-info.json").is_file():
            add(
                kind,
                staging / "build-info.json",
                staging / "frontend-asset-manifest.json",
                None,
                kind,
            )

    frontend_staging = bundle_dir / "frontend" / "frontend-asset-manifest.json"
    if frontend_staging.is_file():
        # 唯一前端构建只参与 manifest 比对（它不是运行制品，没有 build-info，
        # 不能进入身份比对——否则伪制品身份为 None 会污染 G1）
        artifacts["frontend-build"] = {
            "identity_path": None,
            "manifest_path": frontend_staging,
            "binary": None,
            "label": "frontend-unique-build",
        }

    return artifacts


def write_checksums(files: Dict[str, Path], output: Path) -> None:
    lines = []
    for label, path in sorted(files.items()):
        if path and path.is_file():
            lines.append(f"{sha256_file(path)}  {label}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ================================================================ W5 批次 D：G9/G10


def merge_signing_records(bundle_dir: Path) -> Dict[str, Dict[str, object]]:
    """合并 signing-digests-*.json 分片 → kind → record；_mode 从分片顶层注入（drill/formal）。"""
    records: Dict[str, Dict[str, object]] = {}
    for path in sorted(bundle_dir.glob("signing-digests-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        mode = str(payload.get("mode", "formal"))
        for record in payload.get("records", []):
            record["_mode"] = mode
            records[str(record["kind"])] = record
    return records


def compare_signing_records(
    records: Dict[str, Dict[str, object]], root: Path
) -> List[str]:
    """G9 签名面：
    - 正式模式（_mode=formal）下非 SIGNED 即问题（BLOCKED/FAILED/unsigned 均阻断）
    - 演练模式 unsigned 合法；记录缺失（该目标签名步骤未跑）不算 problem——
      由 signing_gate_status 归 INDETERMINATE（CERTIFIED 断言链兜底）
    - SIGNED 的文件制品：post_sha256 必须与实际文件重算一致（签名后改动/篡改检测）
    """
    problems: List[str] = []
    for kind in SIGNATURE_KINDS:
        record = records.get(kind)
        if record is None:
            continue
        status = str(record.get("status"))
        mode = str(record.get("_mode", "formal"))
        if mode == "formal" and status != "SIGNED":
            problems.append(
                f"G9 {kind} 正式模式签名未完成（status={status}，fail-closed）"
            )
            continue
        if status == "SIGNED" and kind.startswith("windows-"):
            path = root / str(record.get("path", ""))
            if not path.is_file():
                problems.append(f"G9 {kind} 签名对象文件缺失：{path}")
                continue
            if sha256_file(path) != record.get("post_sha256"):
                problems.append(
                    f"G9 {kind} 签名后 digest 与实际文件不一致（签名后改动/篡改）"
                )
    return problems


def signing_gate_status(records: Dict[str, Dict[str, object]]) -> str:
    if not records:
        return "NOT_RUN"
    statuses = [str(r.get("status")) for r in records.values()]
    if any(s in ("SIGN_FAILED", "SIGNING_BLOCKED") for s in statuses):
        return "FAIL"
    if all(s == "SIGNED" for s in statuses) and set(records) >= set(SIGNATURE_KINDS):
        return "PASS"
    return "INDETERMINATE"


def compare_manifest_digests(
    manifest: Dict[str, object],
    root: Path,
    records: Dict[str, Dict[str, object]],
) -> List[str]:
    """G10 digest 闭环：manifest artifacts[].sha256 == 现场重算（文件制品，篡改检测核心）
    / == 签名记录 post_sha256（docker 制品交叉校验）；digest_ref 格式锁死。"""
    problems: List[str] = []
    for artifact in manifest.get("artifacts", []):  # type: ignore[union-attr]
        kind = str(artifact.get("kind"))
        if kind in FILE_KINDS:
            path = root / str(artifact.get("path", ""))
            if not path.is_file():
                problems.append(f"G10 {kind} 制品文件缺失：{artifact.get('path')}")
                continue
            if sha256_file(path) != artifact.get("sha256"):
                problems.append(
                    f"G10 {kind} manifest digest 与实际文件不一致（篡改检测命中）"
                )
        else:
            record = records.get(kind)
            if record is None or record.get("post_sha256") != artifact.get("sha256"):
                problems.append(f"G10 {kind} manifest digest 与签名记录不一致")
            if not DIGEST_REF_RE.match(str(artifact.get("digest_ref", ""))):
                problems.append(
                    f"G10 {kind} digest_ref 非 digest 固定引用：{artifact.get('digest_ref')}"
                )
    return problems


def parse_compose_images(text: str) -> List[Tuple[str, str]]:
    """无 YAML 依赖的受控解析：[(service, image-ref)]。

    服务键为两空格缩进的裸键（compose 顶层 services 下的服务名），image 为其子键。
    负向测试用（latest/裸 tag 模板会被检出）。
    """
    images: List[Tuple[str, str]] = []
    service: Optional[str] = None
    for line in text.splitlines():
        header = COMPOSE_SERVICE_RE.match(line)
        if header:
            service = header.group(1)
            continue
        image = IMAGE_LINE_RE.match(line)
        if image and service is not None:
            images.append((service, image.group(1)))
    return images


def substitute_compose_env(ref: str, env: Dict[str, str]) -> Tuple[str, List[str]]:
    """compose 变量插值（受控子集）：${VAR} / ${VAR:-default} / ${VAR:?err}。"""

    problems: List[str] = []

    def repl(match: "re.Match[str]") -> str:
        name, op = match.group(1), match.group(2)
        if env.get(name):
            return env[name]
        if op == "?":
            problems.append(f"compose 必填变量未提供：{name}")
            return ""
        if op == "-":
            return match.group(3)
        return ""

    return COMPOSE_VAR_RE.sub(repl, ref), problems


def check_digest_pinned(ref: str) -> Optional[str]:
    """G10：发布模板只允许 <name>@sha256:<64hex>；latest/裸 tag 一律拒绝。"""
    if not DIGEST_REF_RE.match(ref):
        return f"image 非 digest 固定引用：{ref}"
    return None


def compare_compose_digests(
    template_path: Path, compose: Dict[str, object]
) -> List[str]:
    """G10 compose 一致性：模板渲染后 image 全部 digest 固定，且与 manifest 配对一致。"""
    problems: List[str] = []
    if not template_path.is_file():
        return [f"G10 compose 模板缺失：{template_path}"]
    service_digest = {
        "backend": str(compose.get("backend_digest", "")),
        "frontend": str(compose.get("frontend_digest", "")),
    }
    env = {
        "BTDECK_BACKEND_DIGEST": service_digest["backend"].split("sha256:")[-1],
        "BTDECK_FRONTEND_DIGEST": service_digest["frontend"].split("sha256:")[-1],
    }
    for service, raw in parse_compose_images(template_path.read_text(encoding="utf-8")):
        rendered, sub_problems = substitute_compose_env(raw, env)
        problems += sub_problems
        pin_problem = check_digest_pinned(rendered)
        if pin_problem:
            problems.append(f"G10 {service}: {pin_problem}")
            continue
        expected = service_digest.get(service)
        if expected and not rendered.endswith(expected):
            problems.append(
                f"G10 compose {service} digest 与 manifest 不一致：{rendered}"
            )
    return problems


def check_certified_chain(manifest: Dict[str, object]) -> List[str]:
    """G10 CERTIFIED 断言链：审批人非空 + 全门 PASS + 签名面全 signed。"""
    problems: List[str] = []
    if manifest.get("verdict") != "CERTIFIED":
        return problems
    if not manifest.get("approver") or not manifest.get("approved_at"):
        problems.append(
            "G10 CERTIFIED 但 approver/approved_at 为空（审批对象是 manifest）"
        )
    for entry in manifest.get("evidence", []):  # type: ignore[union-attr]
        if entry.get("status") != "PASS":
            problems.append(
                f"G10 CERTIFIED 但 {entry.get('gate')}={entry.get('status')}"
            )
    for artifact in manifest.get("artifacts", []):  # type: ignore[union-attr]
        kind = str(artifact.get("kind"))
        if kind in SIGNATURE_KINDS:
            signature = artifact.get("signature") or {}
            if signature.get("status") != "signed":
                problems.append(
                    f"G10 CERTIFIED 但 {kind} 签名状态={signature.get('status')}"
                )
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument(
        "--bundle-dir", type=Path, default=None, help="默认 <root>/release/build"
    )
    parser.add_argument("--dist-dir", type=Path, default=None, help="默认 <root>/dist")
    parser.add_argument(
        "--skip-package-extraction",
        action="store_true",
        help="跳过 DEB/RPM 解包比对（无 dpkg-deb/cpio 的环境）",
    )
    parser.add_argument(
        "--require-manifest",
        action="store_true",
        help="G10 强制：release-manifest.json 缺失即 FAIL（RC 门禁路径）",
    )
    parser.add_argument(
        "--require-signing",
        action="store_true",
        help="G9 强制：签名记录缺失即 FAIL（RC 门禁路径）",
    )
    parser.add_argument(
        "--compose-template",
        type=Path,
        default=None,
        help="默认 <root>/deploy/docker-compose.release.yml",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    bundle_dir = args.bundle_dir or (root / "release" / "build")
    dist_dir = args.dist_dir or (root / "dist")
    compose_template = args.compose_template or (
        root / "deploy" / "docker-compose.release.yml"
    )

    try:
        artifacts = collect_bundle(bundle_dir, dist_dir)
        if not artifacts:
            raise BundleVerificationError(f"bundle 为空：{bundle_dir}")

        infos = {
            kind: load_json(Path(a["identity_path"]))
            for kind, a in artifacts.items()
            if a["identity_path"]
        }
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
            for kind, extractor in (
                ("linux-deb", deb_extract_binary),
                ("linux-rpm", rpm_extract_binary),
            ):
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

        # G9 签名面 + G10 digest 闭环（W5 批次 D）
        signing_records = merge_signing_records(bundle_dir)
        signing_problems: List[str] = []
        if signing_records:
            signing_problems = compare_signing_records(signing_records, root)
        elif args.require_signing:
            signing_problems.append("G9 签名记录缺失（--require-signing，fail-closed）")
        problems += signing_problems
        g9_status = signing_gate_status(signing_records)
        if signing_problems:
            g9_status = "FAIL"

        manifest_path = bundle_dir / "release-manifest.json"
        manifest: Optional[Dict[str, object]] = None
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        g10_problems: List[str] = []
        g10_status = "NOT_RUN"
        if manifest is not None:
            g10_problems += compare_manifest_digests(manifest, root, signing_records)
            g10_problems += compare_compose_digests(
                compose_template, manifest.get("compose") or {}
            )
            g10_problems += check_certified_chain(manifest)
            g10_status = "FAIL" if g10_problems else "PASS"
        elif args.require_manifest:
            g10_problems.append(
                "G10 release manifest 缺失（--require-manifest，fail-closed）"
            )
            g10_status = "FAIL"
        problems += g10_problems

        write_checksums(
            {
                str(a["label"]): (
                    Path(a["binary"]) if a["binary"] else Path(a["identity_path"])
                )
                for a in artifacts.values()
                if a["binary"] or a["identity_path"]
            },
            bundle_dir / "checksums.txt",
        )

        report = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bundle_dir": str(bundle_dir),
            "artifacts": {kind: str(a["label"]) for kind, a in artifacts.items()},
            "gates": {
                "G1": (
                    "PASS"
                    if not [
                        p
                        for p in problems
                        if "身份字段" in p or "dirty" in p or "git_sha 缺失" in p
                    ]
                    else "FAIL"
                ),
                "G2_seed": "PASS",
                "G4": "PASS" if len(artifacts) >= 1 else "FAIL",
                "G5": "PASS" if not problems else "FAIL",
                "G9_signing": g9_status,
                "G10": g10_status,
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
        print(
            f"[PASS] bundle 一致（{len(artifacts)} 制品）；报告：{bundle_dir / 'gate-report.json'}"
        )
        return 0
    except BundleVerificationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
