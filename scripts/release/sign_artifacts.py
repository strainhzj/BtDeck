#!/usr/bin/env python3
"""签名编排（release-artifact-equivalence-gate W5 批次 D / G9 签名面 + G10 digest 晋级前置）。

目标集（计划 §G9：Windows 正式制品 Authenticode + Docker cosign；deb/rpm 不在签名要求内，
由 build_release_manifest.py 登记为 mechanism=none）：
  --target windows : dist/btdeck.exe + dist/BtDeck-v*-windows-x64-setup.exe
  --target docker  : btdeck-backend:<version> / btdeck-frontend:<version> 本地镜像

工具链：
  signtool : Windows Kits 自带（windows-2022 runner 预装），/fd SHA256 + RFC3161 时间戳
  cosign   : GitHub release 二进制（v3.1.3，sha256 固定于 release/tool-versions.json；
             ghcr.io/sigstore/cosign 镜像仓库已不存在，2026-09-03 实测 NAME_UNKNOWN）
             v3 CLI：sign-blob 签名材料写 --bundle（无 --output-signature/--tlog-upload）；
             verify-blob 只吃 --bundle；静态 key 签名离线，verify 需 --insecure-ignore-tlog

密钥经环境变量注入（外部前置，不入仓库；2026-09-03 决策：用户提供 GH secret 后一键启用）：
  BTDECK_SIGN_PFX_B64 / BTDECK_SIGN_PFX_PASSWORD   Authenticode 临时 pfx（base64）
  BTDECK_COSIGN_KEY_B64 / BTDECK_COSIGN_PASSWORD   cosign 静态 key（base64）

状态机（fail-closed，契约见 backend/tests/release/test_sign_artifacts.py）：
  SIGNED           工具执行成功；pre/post digest 均记录（Authenticode 改文件字节，cosign 不改）
  SIGNING_BLOCKED  正式模式下密钥缺失——显式阻断状态，退出码 2（不是跳过）
  SIGN_FAILED      工具有但执行失败 / 工具缺失——退出码 3，无演练豁免
  unsigned         仅 --allow-unsigned-drill 且密钥缺失：记录现状退出 0，mode=drill；
                   下游 manifest verdict 强制 INDETERMINATE（不可 CERTIFIED）

Docker digest 口径（G10：篡改镜像内容必然改变该值）：
  RepoDigests（已推送）> Descriptor.Digest（containerd store）> docker save OCI layout
  index.json 的 manifest digest（本地演练）。digest_source 字段记录来源；save 口径与
  registry 推送后 digest 可能因 manifest 媒体类型转换不同——真实晋级以推送后 RepoDigests 为准。

输出（分片文件——windows/docker 各一份，勿合并为全局 index 以免多 job 互相覆盖）：
  <bundle-dir>/signing-digests-<target>.json
  <bundle-dir>/signatures/docker-images.{digests.txt,sigstore.json}（cosign 附签名）
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent

# CI Windows runner 控制台是 cp1252（run 33756203828 实证：记录已落盘、中文 print 崩
# UnicodeEncodeError→exit 1）。本脚本输出含中文，统一 reconfigure 为 UTF-8；
# pytest capsys 替换的流没有 reconfigure，getattr 守卫。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None and (_stream.encoding or "").lower() not in ("utf-8", "utf8"):
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # noqa: BLE001 - 编码降级不允许中断签名流程
            pass

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_SIGN_FAILED = 3

# 记录级/总级状态（drill 的密钥缺失用小写 unsigned，与 schema signature.status 对齐）
STATUS_SIGNED = "SIGNED"
STATUS_BLOCKED = "SIGNING_BLOCKED"
STATUS_SIGN_FAILED = "SIGN_FAILED"
STATUS_UNSIGNED = "unsigned"

# 命令执行器可注入（单测 mock signtool/cosign/docker 用）；env_extra 为附加环境变量
CmdRunner = Callable[[List[str], Dict[str, str]], "subprocess.CompletedProcess[str]"]


class SigningError(RuntimeError):
    """环境性失败（工具缺失/执行失败）。"""


def default_run_cmd(
    cmd: List[str], env_extra: Dict[str, str]
) -> "subprocess.CompletedProcess[str]":
    env = dict(subprocess.os.environ)
    env.update(env_extra)
    # 子进程输出统一按 UTF-8 解码（docker inspect JSON 含非 ASCII；GBK/cp1252 locale
    # 下 text=True 默认 locale 解码会崩读线程→stdout=None，PYTHONIOENCODING=cp1252
    # 模拟实测）。errors=replace 保证任何字节流都不中断签名流程。
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_cosign_spec(tools_path: Path) -> Dict[str, str]:
    """tool-versions.json 的 cosign 条目（二进制 sha256 固定，同 G10 原则）。"""
    tools = json.loads(tools_path.read_text(encoding="utf-8"))
    entry = tools.get("tools", {}).get("cosign")
    if not entry or not entry.get("sha256") or not entry.get("version"):
        raise SigningError("tool-versions.json 缺 cosign 的 version/sha256 固定条目")
    return entry


# ---------------------------------------------------------------- 凭据解析（纯）


def has_windows_credentials(env: Dict[str, str]) -> bool:
    return bool(env.get("BTDECK_SIGN_PFX_B64")) and bool(
        env.get("BTDECK_SIGN_PFX_PASSWORD")
    )


def has_cosign_credentials(env: Dict[str, str]) -> bool:
    return bool(env.get("BTDECK_COSIGN_KEY_B64")) and bool(
        env.get("BTDECK_COSIGN_PASSWORD")
    )


def decode_secret_b64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001 - 凭据损坏必须显式失败而非静默 BLOCKED
        raise SigningError(f"base64 凭据不可解码（{exc}）") from exc


# ---------------------------------------------------------------- 决策（纯函数）


def decide_target_status(target: str, credentials_present: bool, drill: bool) -> str:
    """签名前置状态推导（纯函数，单测契约锚点）。

    正式模式（默认）：密钥缺失 → SIGNING_BLOCKED（fail-closed）。
    演练模式：密钥缺失 → unsigned（退出 0，但下游强制 INDETERMINATE）。
    """
    if credentials_present:
        return STATUS_SIGNED
    return STATUS_UNSIGNED if drill else STATUS_BLOCKED


def aggregate_status(statuses: Sequence[str]) -> str:
    """多记录聚合：SIGN_FAILED > SIGNING_BLOCKED > unsigned > SIGNED（最坏优先）。"""
    if not statuses:
        raise SigningError("没有可聚合的记录")
    for worst in (STATUS_SIGN_FAILED, STATUS_BLOCKED, STATUS_UNSIGNED, STATUS_SIGNED):
        if worst in statuses:
            return worst
    raise SigningError(f"未知状态：{statuses}")


def exit_code_for_status(status: str) -> int:
    if status in (STATUS_SIGNED, STATUS_UNSIGNED):
        return EXIT_OK
    if status == STATUS_BLOCKED:
        return EXIT_BLOCKED
    if status == STATUS_SIGN_FAILED:
        return EXIT_SIGN_FAILED
    raise SigningError(f"未知状态：{status}")


# ---------------------------------------------------------------- Windows 制品发现


def resolve_windows_targets(dist_dir: Path, version: str) -> List[Tuple[str, Path]]:
    """返回 [(kind, path)]；exe 必须存在，setup 按版本 glob。缺任一 → SigningError。"""
    targets: List[Tuple[str, Path]] = []
    exe = dist_dir / "btdeck.exe"
    if not exe.is_file():
        raise SigningError(f"Windows EXE 缺失：{exe}")
    targets.append(("windows-exe", exe))
    setups = sorted(dist_dir.glob(f"BtDeck-v{version}-windows-x64-setup.exe"))
    if not setups:
        raise SigningError(
            f"Windows Setup 缺失：{dist_dir / f'BtDeck-v{version}-windows-x64-setup.exe'}"
        )
    targets.append(("windows-setup", setups[-1]))
    return targets


def find_signtool() -> Optional[Path]:
    """signtool 定位：PATH 优先，其次 Windows Kits 常规安装位。"""
    found = shutil.which("signtool")
    if found:
        return Path(found)
    kits_root = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
    if kits_root.is_dir():
        candidates = sorted(kits_root.glob("*/x64/signtool.exe"))
        if candidates:
            return candidates[-1]
    return None


def build_signtool_cmd(
    signtool: Path, pfx: Path, password: str, timestamp_url: str, targets: List[Path]
) -> List[str]:
    """Authenticode：SHA256 文件摘要 + RFC3161 时间戳（/tr + /td）。"""
    return [
        str(signtool),
        "sign",
        "/fd",
        "SHA256",
        "/tr",
        timestamp_url,
        "/td",
        "SHA256",
        "/f",
        str(pfx),
        "/p",
        password,
        *[str(t) for t in targets],
    ]


def check_authenticode_mutated(pre: str, post: str, kind: str) -> Optional[str]:
    """Authenticode 签名必须改变文件字节；pre==post 说明签名未生效（可疑的 no-op）。"""
    if pre == post:
        return f"{kind}: Authenticode 签名后文件未变化（pre==post，疑似未真正签名）"
    return None


# ---------------------------------------------------------------- Docker digest


def parse_repo_digest(image_ref: str, inspect_json: Dict[str, object]) -> Optional[str]:
    digests = inspect_json.get("RepoDigests") or []
    for entry in digests:
        # 形如 "btdeck-backend@sha256:abc..."；取与本镜像名匹配的条目
        if isinstance(entry, str) and entry.split("@")[0] in image_ref:
            hex_part = entry.split("@")[-1]
            if hex_part.startswith("sha256:"):
                return hex_part[len("sha256:") :]
    return None


def parse_descriptor_digest(inspect_json: Dict[str, object]) -> Optional[str]:
    descriptor = inspect_json.get("Descriptor")
    if isinstance(descriptor, dict):
        value = descriptor.get("Digest")
        if isinstance(value, str) and value.startswith("sha256:"):
            return value[len("sha256:") :]
    return None


def manifest_digest_from_save_tar(tar_path: Path) -> str:
    """docker save 产出的 OCI layout：index.json → manifests[0].digest（内容寻址）。"""
    import tarfile

    with tarfile.open(tar_path, "r") as tar:
        member = tar.extractfile("index.json")
        if member is None:
            raise SigningError(f"save tar 缺 index.json：{tar_path}")
        index = json.loads(member.read().decode("utf-8"))
    manifests = index.get("manifests") or []
    if not manifests:
        raise SigningError(f"save tar 的 index.json 无 manifest：{tar_path}")
    digest = manifests[0].get("digest", "")
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        raise SigningError(f"save tar manifest digest 非法：{digest!r}")
    return digest[len("sha256:") :]


def inspect_image_digest(
    image_ref: str, run_cmd: CmdRunner, work_dir: Path
) -> Tuple[str, str, int]:
    """三级口径：repo（已推送）> descriptor（containerd store）> save-oci（本地演练）。

    返回 (digest_hex, digest_source, size_bytes)——size 取 inspect 的 .Size
    （未压缩层总字节，manifest 的 size_bytes 字段用）。
    """
    proc = run_cmd(["docker", "image", "inspect", image_ref], {})
    if proc.returncode != 0:
        raise SigningError(
            f"docker inspect 失败：{image_ref}（{proc.stderr.strip()[:200]}）"
        )
    inspect_json = json.loads(proc.stdout)[0]
    size_bytes = int(inspect_json.get("Size") or 0)

    digest = parse_repo_digest(image_ref, inspect_json)
    if digest:
        return digest, "repo", size_bytes
    digest = parse_descriptor_digest(inspect_json)
    if digest:
        return digest, "descriptor", size_bytes

    tar_path = work_dir / "image.tar"
    proc = run_cmd(["docker", "save", "-o", str(tar_path), image_ref], {})
    if proc.returncode != 0:
        raise SigningError(
            f"docker save 失败：{image_ref}（{proc.stderr.strip()[:200]}）"
        )
    try:
        return manifest_digest_from_save_tar(tar_path), "save-oci", size_bytes
    finally:
        tar_path.unlink(missing_ok=True)


# ---------------------------------------------------------------- cosign v3 命令构造（纯）


def build_cosign_sign_blob_cmd(
    cosign_bin: str, key_path: Path, payload_path: Path, bundle_path: Path
) -> List[str]:
    """v3：签名材料（含签名本体）写 --bundle；静态 key 离线签名，不走 tlog。"""
    return [
        cosign_bin,
        "sign-blob",
        "--yes",
        "--key",
        str(key_path),
        "--bundle",
        str(bundle_path),
        str(payload_path),
    ]


def build_cosign_verify_blob_cmd(
    cosign_bin: str, pub_path: Path, payload_path: Path, bundle_path: Path
) -> List[str]:
    """v3：verify-blob 只吃 --bundle；keyed 签名无 tlog 记录须显式忽略。"""
    return [
        cosign_bin,
        "verify-blob",
        "--key",
        str(pub_path),
        "--bundle",
        str(bundle_path),
        "--insecure-ignore-tlog",
        str(payload_path),
    ]


def build_cosign_public_key_cmd(cosign_bin: str, key_path: Path) -> List[str]:
    """从静态私钥推导公钥（stdout 输出 PEM）。"""
    return [cosign_bin, "public-key", "--key", str(key_path)]


def resolve_cosign_binary(explicit: Optional[str]) -> Optional[Path]:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise SigningError(f"--cosign-bin 不存在：{explicit}")
        return path
    found = shutil.which("cosign")
    return Path(found) if found else None


# ---------------------------------------------------------------- 目标执行


def sign_windows(
    dist_dir: Path,
    version: str,
    drill: bool,
    run_cmd: CmdRunner,
    env: Dict[str, str],
    timestamp_url: str,
    signtool_path: Optional[Path] = None,
) -> Dict[str, object]:
    targets = resolve_windows_targets(dist_dir, version)
    signtool = signtool_path or find_signtool()
    if signtool is None:
        raise SigningError("signtool 不可用（Windows Kits 未安装且不在 PATH）")

    status = decide_target_status("windows", has_windows_credentials(env), drill)
    records: List[Dict[str, object]] = []
    pre_states: Dict[str, str] = {}
    for kind, path in targets:
        pre_states[kind] = sha256_file(path)

    problems: List[str] = []
    if status == STATUS_SIGNED:
        with tempfile.TemporaryDirectory(prefix="btdeck-pfx-") as tmp:
            pfx_path = Path(tmp) / "signing.pfx"
            pfx_path.write_bytes(decode_secret_b64(env["BTDECK_SIGN_PFX_B64"]))
            cmd = build_signtool_cmd(
                signtool,
                pfx_path,
                env["BTDECK_SIGN_PFX_PASSWORD"],
                timestamp_url,
                [p for _, p in targets],
            )
            proc = run_cmd(cmd, {})
            if proc.returncode != 0:
                status = STATUS_SIGN_FAILED
                problems.append(
                    f"signtool sign 失败 rc={proc.returncode}：{proc.stderr.strip()[:300]}"
                )
        if status == STATUS_SIGNED:
            verify_ok = True
            for kind, path in targets:
                vproc = run_cmd([str(signtool), "verify", "/pa", "/all", str(path)], {})
                if vproc.returncode != 0:
                    verify_ok = False
                    problems.append(
                        f"{kind}: signtool verify 失败（{vproc.stderr.strip()[:200]}）"
                    )
            if not verify_ok:
                status = STATUS_SIGN_FAILED

    for kind, path in targets:
        try:
            display_path = (
                str(path.relative_to(dist_dir.parents[-1]))
                if len(dist_dir.parents) >= 1
                else str(path)
            )
        except ValueError:
            display_path = str(path)
        record: Dict[str, object] = {
            "kind": kind,
            "path": display_path,
            "mechanism": "authenticode",
            "pre_sha256": pre_states[kind],
        }
        if status == STATUS_SIGNED:
            post = sha256_file(path)
            mutation_problem = check_authenticode_mutated(pre_states[kind], post, kind)
            if mutation_problem:
                problems.append(mutation_problem)
                status = STATUS_SIGN_FAILED
                record["post_sha256"] = post
                record["signature"] = {
                    "mechanism": "authenticode",
                    "status": "indeterminate",
                    "signed_sha256": None,
                }
            else:
                record["post_sha256"] = post
                record["signature"] = {
                    "mechanism": "authenticode",
                    "status": "signed",
                    "signed_sha256": post,
                }
        else:
            record["post_sha256"] = pre_states[kind]
            record["signature"] = {
                "mechanism": "authenticode",
                "status": "unsigned" if status == STATUS_UNSIGNED else "indeterminate",
                "signed_sha256": None,
            }
        records.append(record)

    return {
        "target": "windows",
        "status": status,
        "records": records,
        "problems": problems,
        "tool": {"signtool": str(signtool)},
    }


def sign_docker(
    version: str,
    drill: bool,
    run_cmd: CmdRunner,
    env: Dict[str, str],
    tools_path: Path,
    bundle_dir: Path,
    work_root: Path,
    cosign_bin: Optional[Path],
) -> Dict[str, object]:
    cosign_spec = load_cosign_spec(tools_path)
    refs = [
        ("docker-backend", f"btdeck-backend:v{version}"),
        ("docker-frontend", f"btdeck-frontend:v{version}"),
    ]

    status = decide_target_status("docker", has_cosign_credentials(env), drill)
    records: List[Dict[str, object]] = []
    problems: List[str] = []

    digest_payload_lines: List[str] = []
    for kind, ref in refs:
        digest_hex, digest_source, size_bytes = inspect_image_digest(
            ref, run_cmd, work_root
        )
        digest_payload_lines.append(f"{kind} {ref} sha256:{digest_hex}")
        records.append(
            {
                "kind": kind,
                "ref": ref,
                "digest_source": digest_source,
                "size_bytes": size_bytes,
                # cosign 签名不改变镜像本身：pre==post 是预期（与 Authenticode 相反）
                "pre_sha256": digest_hex,
                "post_sha256": digest_hex,
            }
        )

    signature_dir = bundle_dir / "signatures"
    signature_dir.mkdir(parents=True, exist_ok=True)

    if status == STATUS_SIGNED:
        if cosign_bin is None:
            raise SigningError(
                "cosign 二进制不可用（--cosign-bin 或 PATH；CI 由 setup 步骤安装固定版本）"
            )
        with tempfile.TemporaryDirectory(prefix="btdeck-cosign-") as tmp:
            tmp_dir = Path(tmp)
            key_path = tmp_dir / "cosign.key"
            key_path.write_bytes(decode_secret_b64(env["BTDECK_COSIGN_KEY_B64"]))
            payload_path = tmp_dir / "digests.txt"
            payload_path.write_text(
                "\n".join(digest_payload_lines) + "\n", encoding="utf-8"
            )
            bundle_path = tmp_dir / "digests.sigstore.json"
            cosign_env = {"COSIGN_PASSWORD": env["BTDECK_COSIGN_PASSWORD"]}

            proc = run_cmd(
                build_cosign_sign_blob_cmd(
                    str(cosign_bin), key_path, payload_path, bundle_path
                ),
                cosign_env,
            )
            if proc.returncode != 0 or not bundle_path.is_file():
                status = STATUS_SIGN_FAILED
                problems.append(
                    f"cosign sign-blob 失败 rc={proc.returncode}：{proc.stderr.strip()[:300]}"
                )
            else:
                pub_proc = run_cmd(
                    build_cosign_public_key_cmd(str(cosign_bin), key_path), cosign_env
                )
                if pub_proc.returncode != 0 or not pub_proc.stdout.strip():
                    status = STATUS_SIGN_FAILED
                    problems.append(
                        f"cosign public-key 推导失败：{pub_proc.stderr.strip()[:200]}"
                    )
                else:
                    pub_path = tmp_dir / "cosign.pub"
                    pub_path.write_text(pub_proc.stdout, encoding="utf-8")
                    vproc = run_cmd(
                        build_cosign_verify_blob_cmd(
                            str(cosign_bin), pub_path, payload_path, bundle_path
                        ),
                        {},
                    )
                    if vproc.returncode != 0:
                        status = STATUS_SIGN_FAILED
                        problems.append(
                            f"cosign verify-blob 失败 rc={vproc.returncode}：{vproc.stdout.strip()[:200]}"
                        )
                    else:
                        shutil.copyfile(
                            bundle_path, signature_dir / "docker-images.sigstore.json"
                        )
                        (signature_dir / "docker-images.digests.txt").write_text(
                            "\n".join(digest_payload_lines) + "\n", encoding="utf-8"
                        )

    for record in records:
        if status == STATUS_SIGNED:
            record["signature"] = {
                "mechanism": "cosign",
                "status": "signed",
                "signed_sha256": record["post_sha256"],
                "signature_file": "release/build/signatures/docker-images.sigstore.json",
                "verified": True,
            }
        else:
            record["signature"] = {
                "mechanism": "cosign",
                "status": "unsigned" if status == STATUS_UNSIGNED else "indeterminate",
                "signed_sha256": None,
                "signature_file": None,
                "verified": None,
            }

    return {
        "target": "docker",
        "status": status,
        "records": records,
        "problems": problems,
        "tool": {
            "cosign": {
                "version": cosign_spec["version"],
                "sha256": cosign_spec["sha256"],
                "resolved": str(cosign_bin) if cosign_bin else None,
            }
        },
    }


# ---------------------------------------------------------------- 主流程


def resolve_build_info_path(bundle_dir: Path) -> Path:
    """build-info staging 解析（纯函数，CI run 33755046911 首轮回归锚点）。

    回退链覆盖三类 CI 场景：docker job（docker-backend）、linux job（linux-binary）、
    windows job（windows-exe）——单平台 job 只产自己平台的 staging。
    """
    for candidate in ("docker-backend", "linux-binary", "windows-exe"):
        path = bundle_dir / candidate / "build-info.json"
        if path.is_file():
            return path
    raise SigningError(
        f"build-info 全部缺失：{bundle_dir}/{{docker-backend,linux-binary,windows-exe}}/build-info.json（先跑构建链）"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument(
        "--bundle-dir", type=Path, default=None, help="默认 <root>/release/build"
    )
    parser.add_argument("--dist-dir", type=Path, default=None, help="默认 <root>/dist")
    parser.add_argument("--target", choices=("windows", "docker"), required=True)
    parser.add_argument(
        "--allow-unsigned-drill",
        action="store_true",
        help="演练路径：密钥缺失记 unsigned 而非 BLOCKED（manifest 强制 INDETERMINATE）",
    )
    parser.add_argument(
        "--cosign-bin",
        default=None,
        help="cosign 二进制路径（默认 PATH 查找；CI 由 setup 步骤安装固定版本）",
    )
    parser.add_argument(
        "--timestamp-url",
        default=subprocess.os.environ.get(
            "BTDECK_TIMESTAMP_URL", "http://timestamp.digicert.com"
        ),
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    bundle_dir = args.bundle_dir or (root / "release" / "build")
    dist_dir = args.dist_dir or (root / "dist")

    try:
        staging = resolve_build_info_path(bundle_dir)
        build_info = json.loads(staging.read_text(encoding="utf-8"))
        version = str(build_info["product_version"])

        if args.target == "windows":
            result = sign_windows(
                dist_dir,
                version,
                args.allow_unsigned_drill,
                default_run_cmd,
                dict(subprocess.os.environ),
                args.timestamp_url,
            )
        else:
            work_root = bundle_dir / ".signing"
            work_root.mkdir(parents=True, exist_ok=True)
            result = sign_docker(
                version,
                args.allow_unsigned_drill,
                default_run_cmd,
                dict(subprocess.os.environ),
                root / "release" / "tool-versions.json",
                bundle_dir,
                work_root,
                resolve_cosign_binary(args.cosign_bin),
            )

        result["schema_version"] = 1
        result["mode"] = "drill" if args.allow_unsigned_drill else "formal"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["product_version"] = version
        result["git_sha"] = build_info.get("git_sha")

        output = bundle_dir / f"signing-digests-{args.target}.json"
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        status = result["status"]
        code = exit_code_for_status(status)
        print(f"[{status}] {args.target} 签名编排完成；记录：{output}")
        for problem in result["problems"]:
            print(f"  problem: {problem}", file=sys.stderr)
        return code
    except SigningError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return EXIT_SIGN_FAILED


if __name__ == "__main__":
    sys.exit(main())
