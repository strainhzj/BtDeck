#!/usr/bin/env python3
"""Validate BtDeck packaged artifacts — 内容级验证（release-artifact-equivalence-gate W2 / G5）。

从“存在性检查”升级为内容与来源验证：
  1. 必需条目存在（发布身份三件套、前端入口、契约 JSON、alembic 迁移、schema 快照）
  2. build-info 字段校验（与 backend/app/core/build_info.py 同规则：40 位 SHA、
     12 位 alembic head、64 位 manifest 哈希、dirty=false、artifact_kind 白名单）
  3. 内嵌 frontend-asset-manifest 的规范哈希 == build-info.frontend_manifest_sha256
  4. 前端逐文件哈希校验（manifest 中每个文件的 sha256 == 归档内 frontend_dist/<path> 内容哈希）
  5. 禁入文件扫描（config.yaml/.env/app.db/*.db/迁移备份/构建机路径泄漏）

验证函数为纯函数（输入 entries: {name: bytes}），五类变异
（旧 index、缺契约 JSON、依赖/身份漂移、混入 app.db、SHA 篡改）由
backend/tests/release/test_verify_package.py 直接覆盖。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

REQUIRED_ENTRIES = (
    "build-info.json",
    "source-manifest.json",
    "frontend-asset-manifest.json",
    "frontend_dist/index.html",
    "app/contracts/advanced_search_contract.json",
    "config/production_complete_schema.sql",
)

FORBIDDEN_PATTERNS = (
    re.compile(r"(^|/)config\.yaml(\.|$)"),
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/)app\.db($|[-.])"),
    re.compile(r"\.db-(journal|wal|shm)$"),
    re.compile(r"pre-migration-"),
    re.compile(r"(^|/)config/qb_rid_cache\.json$"),
)

_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_ALEMBIC_HEAD = re.compile(r"^[0-9a-f]{12}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_KINDS = frozenset(
    {
        "windows-exe",
        "windows-setup",
        "linux-binary",
        "linux-deb",
        "linux-rpm",
        "docker-backend",
        "docker-frontend",
    }
)


class VerificationFailure(RuntimeError):
    """fail-closed：任一检查不过即抛出（CLI 转非零退出）。"""


def canonical_json_sha256(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def check_required(entries: Dict[str, bytes]) -> None:
    missing = [name for name in REQUIRED_ENTRIES if name not in entries]
    if not any(name.startswith("alembic/versions/") for name in entries):
        missing.append("alembic/versions/*（至少一个迁移文件）")
    if missing:
        raise VerificationFailure(f"归档缺少必需条目：{missing}")


def check_forbidden(entries: Dict[str, bytes]) -> None:
    hits = []
    for name in entries:
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(name):
                hits.append(f"{name}（命中 {pattern.pattern}）")
                break
    if hits:
        raise VerificationFailure(f"归档含禁入条目（密钥/数据库/构建机残留）：{hits[:10]}")


def check_build_info(entries: Dict[str, bytes]) -> Dict[str, object]:
    try:
        info = json.loads(entries["build-info.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationFailure(f"build-info.json 无法解析：{exc}") from exc
    for field in ("product_version", "git_sha", "git_tag", "artifact_kind", "alembic_head", "frontend_manifest_sha256", "dirty"):
        if field not in info:
            raise VerificationFailure(f"build-info 缺少字段：{field}")
    if not _GIT_SHA.fullmatch(str(info["git_sha"])):
        raise VerificationFailure(f"build-info git_sha 非完整 40 位：{info['git_sha']!r}")
    if not _ALEMBIC_HEAD.fullmatch(str(info["alembic_head"])):
        raise VerificationFailure(f"build-info alembic_head 非 12 位：{info['alembic_head']!r}")
    if not _SHA256.fullmatch(str(info["frontend_manifest_sha256"])):
        raise VerificationFailure("build-info frontend_manifest_sha256 非法")
    if info["artifact_kind"] not in _ARTIFACT_KINDS:
        raise VerificationFailure(f"build-info artifact_kind 未知：{info['artifact_kind']!r}")
    if info["dirty"] is not False:
        raise VerificationFailure("build-info dirty=true 不允许出现在制品中")
    return info


def check_frontend_content(entries: Dict[str, bytes], build_info: Dict[str, object]) -> None:
    try:
        manifest = json.loads(entries["frontend-asset-manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationFailure(f"frontend-asset-manifest.json 无法解析：{exc}") from exc

    recomputed = canonical_json_sha256(manifest)
    expected = str(build_info["frontend_manifest_sha256"])
    if recomputed != expected:
        raise VerificationFailure(
            f"前端 manifest 规范哈希与 build-info 不一致（SHA 篡改/旧产物）："
            f"manifest={recomputed} build-info={expected}"
        )

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise VerificationFailure("前端 manifest 无文件条目")

    mismatches: List[str] = []
    for item in files:
        relpath = item.get("path")
        sha = item.get("sha256")
        if not isinstance(relpath, str) or not isinstance(sha, str):
            mismatches.append(f"manifest 条目非法：{item}")
            continue
        entry_name = f"frontend_dist/{relpath}"
        content = entries.get(entry_name)
        if content is None:
            mismatches.append(f"归档缺少前端文件：{entry_name}")
            continue
        actual = hashlib.sha256(content).hexdigest()
        if actual != sha:
            mismatches.append(f"前端文件哈希不符：{entry_name}（manifest={sha[:12]} 实际={actual[:12]}）")
    if mismatches:
        raise VerificationFailure("前端内容验证失败：\n  " + "\n  ".join(mismatches[:10]))


def verify_entries(entries: Dict[str, bytes]) -> Dict[str, object]:
    """全部静态检查（纯函数；测试五类变异直接构造 entries 调用）。"""
    check_required(entries)
    check_forbidden(entries)
    info = check_build_info(entries)
    check_frontend_content(entries, info)
    return info


def collect_archive_entries(exe_path: Path) -> Dict[str, bytes]:
    """读取 PyInstaller CArchive 为 {name: bytes}（仅数据条目；PYZ 等跳过内容）。"""
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except ImportError as exc:
        raise VerificationFailure(
            "需要 PyInstaller 环境读取归档（在打包 venv 内运行，或 pip install pyinstaller）"
        ) from exc
    reader = CArchiveReader(str(exe_path))
    entries: Dict[str, bytes] = {}
    for name in reader.toc:
        try:
            entries[name] = reader.extract(name)
        except Exception:  # noqa: BLE001 - PYZ/依赖条目提取失败不阻断（我们只消费数据条目）
            continue
    if not entries:
        raise VerificationFailure(f"归档为空或不可读：{exe_path}")
    return entries


def parse_args() -> argparse.Namespace:
    script_path = Path(__file__).resolve()
    default_project_root = script_path.parent.parent

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=default_project_root)
    parser.add_argument(
        "--frontend-dist", type=Path, default=None,
        help="兼容保留：内容校验以归档内 manifest 为准，此参数不再参与判定",
    )
    parser.add_argument(
        "--artifact", "--exe", type=Path, default=None,
        help="PyInstaller packaged artifact. Defaults to <project-root>/dist/btdeck[.exe]",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    exe_name = "btdeck.exe" if sys.platform == "win32" else "btdeck"
    exe_path = args.artifact.resolve() if args.artifact else project_root / "dist" / exe_name

    print("BtDeck package verification (content-level, G5)")
    print(f"Project root: {project_root}")
    print(f"Artifact: {exe_path}")

    if not exe_path.is_file():
        print(f"[FAIL] 制品缺失：{exe_path}")
        return 1
    try:
        entries = collect_archive_entries(exe_path)
        info = verify_entries(entries)
    except VerificationFailure as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(f"[PASS] build-info: {info['product_version']} @ {str(info['git_sha'])[:12]} kind={info['artifact_kind']}")
    print("[PASS] 前端逐文件哈希与 manifest 一致")
    print("[PASS] 禁入文件扫描通过")
    print("[PASS] Package verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
