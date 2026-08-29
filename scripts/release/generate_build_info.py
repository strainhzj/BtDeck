#!/usr/bin/env python3
"""生成 BtDeck 发布构建身份与清单（release-artifact-equivalence-gate W1）。

职责（fail-closed，任何输入不确定即非零退出）：
  1. build-info.json            嵌入制品的构建身份（schema: release/schemas/build-info.schema.json）
  2. source-manifest.json       运行时相关跟踪文件清单（路径 + SHA256）
  3. frontend-asset-manifest.json  唯一前端构建的资产清单（四种交付物必须一致）

同时提供 --check-versions 独立模式：校验产品版本六处声明与 release/release-config.json
一致（backend/app/version.py、frontend/package.json、feature_list.json.release_version、
deploy/btdeck.iss、deploy/build-linux.sh）。

本脚本只用标准库，可在 PyInstaller 打包 venv、CI Runner 与容器内运行。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent

BUILD_INFO_FILENAME = "build-info.json"
SOURCE_MANIFEST_FILENAME = "source-manifest.json"
FRONTEND_MANIFEST_FILENAME = "frontend-asset-manifest.json"

RELEASE_CONFIG_RELPATH = Path("release/release-config.json")
VERSION_PY_RELPATH = Path("backend/app/version.py")
PACKAGE_JSON_RELPATH = Path("frontend/package.json")
FEATURE_LIST_RELPATH = Path("feature_list.json")
ISS_RELPATH = Path("deploy/btdeck.iss")
BUILD_LINUX_RELPATH = Path("deploy/build-linux.sh")

# 运行时相关的跟踪文件集合（source-manifest 覆盖范围，W1 固化；调整需同步 release-config）
SOURCE_MANIFEST_PATHS: Tuple[str, ...] = (
    "backend/app",
    "backend/alembic",
    "backend/config/production_complete_schema.sql",
    "backend/requirements.txt",
    "backend/btdeck_startup.sh",
    "frontend/src",
    "frontend/public",
    "deploy/btdeck.spec",
    "deploy/btdeck-windows.spec",
    "deploy/btdeck.service",
)

ARTIFACT_KINDS = (
    "windows-exe",
    "windows-setup",
    "linux-binary",
    "linux-deb",
    "linux-rpm",
    "docker-backend",
    "docker-frontend",
)


class BuildInfoGenerationError(RuntimeError):
    """fail-closed：任何无法确定身份/清单的情况。"""


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise BuildInfoGenerationError(f"git 不可用：{exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise BuildInfoGenerationError(
            f"git {' '.join(args)} 失败：{(exc.stderr or '').strip()[:200]}"
        ) from exc
    return result.stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_release_config(root: Path) -> Dict[str, object]:
    config_path = root / RELEASE_CONFIG_RELPATH
    if not config_path.is_file():
        raise BuildInfoGenerationError(f"release-config 缺失：{config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    candidate = config.get("candidate", {})
    product_version = candidate.get("product_version")
    if not isinstance(product_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", product_version):
        raise BuildInfoGenerationError(f"release-config candidate.product_version 非法：{product_version!r}")
    return config


# ---------------------------------------------------------------------------
# 版本一致性（G1 基础检查）
# ---------------------------------------------------------------------------

def _read_text(root: Path, relpath: Path) -> str:
    path = root / relpath
    if not path.is_file():
        raise BuildInfoGenerationError(f"版本来源文件缺失：{path}")
    return path.read_text(encoding="utf-8")


def collect_declared_versions(root: Path) -> Dict[str, str]:
    """收集六处产品版本声明；返回 {来源: 版本}（键统一 POSIX 分隔符，跨平台可比）。"""
    config = load_release_config(root)
    versions: Dict[str, str] = {
        RELEASE_CONFIG_RELPATH.as_posix(): str(config["candidate"]["product_version"])
    }

    version_py = _read_text(root, VERSION_PY_RELPATH)
    match = re.search(r'^CURRENT_VERSION\s*=\s*"([^"]+)"', version_py, re.MULTILINE)
    if not match:
        raise BuildInfoGenerationError("backend/app/version.py 未找到 CURRENT_VERSION 赋值")
    versions[VERSION_PY_RELPATH.as_posix()] = match.group(1)

    package_json = json.loads(_read_text(root, PACKAGE_JSON_RELPATH))
    if not isinstance(package_json.get("version"), str):
        raise BuildInfoGenerationError("frontend/package.json 缺少 version 字段")
    versions[PACKAGE_JSON_RELPATH.as_posix()] = package_json["version"]

    feature_list = json.loads(_read_text(root, FEATURE_LIST_RELPATH))
    release_version = feature_list.get("release_version")
    if not isinstance(release_version, str):
        raise BuildInfoGenerationError("feature_list.json 缺少 release_version")
    versions[FEATURE_LIST_RELPATH.as_posix()] = release_version

    iss = _read_text(root, ISS_RELPATH)
    match = re.search(r'^#define AppVersion "([^"]+)"', iss, re.MULTILINE)
    if not match:
        raise BuildInfoGenerationError("deploy/btdeck.iss 未找到 #define AppVersion")
    versions[ISS_RELPATH.as_posix()] = match.group(1)

    build_linux = _read_text(root, BUILD_LINUX_RELPATH)
    match = re.search(r'^VERSION="([^"]+)"', build_linux, re.MULTILINE)
    if not match:
        raise BuildInfoGenerationError("deploy/build-linux.sh 未找到 VERSION= 赋值")
    versions[BUILD_LINUX_RELPATH.as_posix()] = match.group(1)

    return versions


def check_versions(root: Path) -> List[str]:
    """返回版本不一致描述列表；空列表 = 一致。"""
    versions = collect_declared_versions(root)
    expected = versions[RELEASE_CONFIG_RELPATH.as_posix()]
    return [
        f"{source}: {version} != release-config {expected}"
        for source, version in versions.items()
        if version != expected
    ]


# ---------------------------------------------------------------------------
# Alembic head 静态解析（单一 head；多 head/空链失败）
# ---------------------------------------------------------------------------

class _Revision:
    """迁移节点（纯容器；不用 dataclass，确保任意 importlib 加载方式下可用）。"""

    __slots__ = ("revision", "down_revisions")

    def __init__(self, revision: str, down_revisions: Tuple[str, ...]) -> None:
        self.revision = revision
        self.down_revisions = down_revisions


def collect_alembic_head(backend_dir: Path) -> str:
    versions_dir = backend_dir / "alembic" / "versions"
    if not versions_dir.is_dir():
        raise BuildInfoGenerationError(f"alembic versions 目录缺失：{versions_dir}")
    revisions: Dict[str, _Revision] = {}
    pattern_revision = re.compile(r"^revision(?::\s*str)?\s*=\s*['\"]([0-9a-f]{12})['\"]", re.MULTILINE)
    pattern_down = re.compile(
        r"^down_revision(?::[^=]*)?\s*=\s*(?:(None)|['\"]([0-9a-f]{12})['\"]|(\((?:[^()]*)\)))",
        re.MULTILINE,
    )
    for path in sorted(versions_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        match = pattern_revision.search(text)
        if not match:
            continue  # __init__.py 或非迁移文件
        down_match = pattern_down.search(text)
        downs: Tuple[str, ...] = ()
        if down_match:
            if down_match.group(1):
                downs = ()
            elif down_match.group(2):
                downs = (down_match.group(2),)
            elif down_match.group(3):
                downs = tuple(re.findall(r"[0-9a-f]{12}", down_match.group(3)))
        revision = match.group(1)
        if revision in revisions:
            raise BuildInfoGenerationError(f"alembic revision 重复：{revision}（{path.name}）")
        revisions[revision] = _Revision(revision=revision, down_revisions=downs)

    if not revisions:
        raise BuildInfoGenerationError("alembic versions 未发现任何迁移")
    referenced = {down for rev in revisions.values() for down in rev.down_revisions}
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise BuildInfoGenerationError(f"alembic 必须单一 head，实际 {len(heads)} 个：{heads}")
    missing_parents = referenced - set(revisions)
    if missing_parents:
        raise BuildInfoGenerationError(f"alembic 引用了不存在的 down_revision：{sorted(missing_parents)}")
    return heads[0]


# ---------------------------------------------------------------------------
# Manifest 构建
# ---------------------------------------------------------------------------

def build_frontend_asset_manifest(dist_dir: Path) -> Tuple[Dict[str, object], str]:
    if not (dist_dir / "index.html").is_file():
        raise BuildInfoGenerationError(f"frontend dist 缺失 index.html：{dist_dir}")
    files = []
    for path in sorted(p for p in dist_dir.rglob("*") if p.is_file()):
        relpath = path.relative_to(dist_dir).as_posix()
        files.append(
            {
                "path": relpath,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if not files:
        raise BuildInfoGenerationError(f"frontend dist 为空：{dist_dir}")
    manifest: Dict[str, object] = {
        "schema_version": 1,
        "file_count": len(files),
        "files": files,
    }
    return manifest, canonical_json_sha256(manifest)


def build_source_manifest(root: Path, tracked_paths: Sequence[str]) -> Tuple[Dict[str, object], str]:
    listing = _git(root, "ls-files", "--", *tracked_paths).splitlines()
    files = []
    for relpath in sorted(set(line.strip().strip('"') for line in listing if line.strip())):
        path = root / relpath
        if not path.is_file():
            continue  # 子模块/稀疏检出场景下跳过目录条目
        files.append({"path": relpath, "sha256": sha256_file(path)})
    if not files:
        raise BuildInfoGenerationError(f"source manifest 为空：{tracked_paths}")
    manifest: Dict[str, object] = {
        "schema_version": 1,
        "tracked_paths": list(tracked_paths),
        "file_count": len(files),
        "files": files,
    }
    return manifest, canonical_json_sha256(manifest)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _resolve_git_identity(root: Path, allow_dirty: bool) -> Tuple[str, str, int, bool]:
    sha = _git(root, "rev-parse", "HEAD").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise BuildInfoGenerationError(f"git SHA 非完整 40 位：{sha!r}")
    commit_epoch = int(_git(root, "log", "-1", "--format=%ct").strip())
    status = _git(root, "status", "--porcelain").splitlines()
    # 与运行时无关的本地噪音（发布工作目录、会话产物）不算 dirty
    noisy_prefixes = (".release-build-", "data/", "dist/", "release/evidence/")
    dirty_lines = [
        line
        for line in status
        if line.strip()
        and not any(line[3:].startswith(prefix) for prefix in noisy_prefixes)
    ]
    dirty = bool(dirty_lines)
    if dirty and not allow_dirty:
        preview = "; ".join(line.strip() for line in dirty_lines[:5])
        raise BuildInfoGenerationError(
            f"工作区不干净（发布构建必须干净检出）：{preview}"
            f"{'...' if len(dirty_lines) > 5 else ''}"
        )
    return sha, "", commit_epoch, dirty


def generate(
    root: Path,
    *,
    artifact_kind: str,
    target_os: str,
    node_version: Optional[str],
    build_id: Optional[str],
    allow_dirty: bool,
    output_dir: Path,
    python_version: Optional[str],
) -> Dict[str, object]:
    if artifact_kind not in ARTIFACT_KINDS:
        raise BuildInfoGenerationError(f"artifact_kind 非法：{artifact_kind}")
    config = load_release_config(root)
    product_version = str(config["candidate"]["product_version"])
    git_tag = f"v{product_version}"

    mismatches = check_versions(root)
    if mismatches:
        raise BuildInfoGenerationError("版本声明不一致：\n  " + "\n  ".join(mismatches))

    sha, _, commit_epoch, dirty = _resolve_git_identity(root, allow_dirty)
    # SOURCE_DATE_EPOCH 锚定提交时间：同 SHA 的所有制品取值必然一致
    source_date_epoch = commit_epoch
    alembic_head = collect_alembic_head(root / "backend")

    frontend_manifest, frontend_sha = build_frontend_asset_manifest(root / "frontend" / "dist")
    source_manifest, source_sha = build_source_manifest(root, SOURCE_MANIFEST_PATHS)

    build_info: Dict[str, object] = {
        "schema_version": 1,
        "product_version": product_version,
        "git_sha": sha,
        "git_tag": git_tag,
        "source_date_epoch": source_date_epoch,
        "build_id": build_id,
        "artifact_kind": artifact_kind,
        "target_os": target_os,
        "target_arch": "amd64",
        "python_version": python_version,
        "node_version": node_version,
        "alembic_head": alembic_head,
        "frontend_manifest_sha256": frontend_sha,
        "source_manifest_sha256": source_sha,
        "dependency_manifest_sha256": None,
        "dirty": dirty,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / BUILD_INFO_FILENAME).write_text(
        json.dumps(build_info, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / SOURCE_MANIFEST_FILENAME).write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / FRONTEND_MANIFEST_FILENAME).write_text(
        json.dumps(frontend_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return build_info


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument(
        "--artifact-kind",
        choices=ARTIFACT_KINDS,
        help="制品类型（--check-versions 模式下不需要）",
    )
    parser.add_argument("--target-os", choices=["windows", "linux"], default="linux")
    parser.add_argument("--output-dir", type=Path, default=None, help="默认 <root>/release")
    parser.add_argument("--node-version", default=None, help="前端构建 Node 版本（如 22.23.2）")
    parser.add_argument("--python-version", default=None, help="后端制品 Python 版本；默认取当前解释器")
    parser.add_argument("--build-id", default=None, help="CI run id / attempt")
    parser.add_argument("--allow-dirty", action="store_true", help="开发构建：允许脏工作区（dirty=true）")
    parser.add_argument(
        "--check-versions",
        action="store_true",
        help="只做六处版本一致性检查后退出",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()

    if args.check_versions:
        mismatches = check_versions(root)
        if mismatches:
            print("[FAIL] 版本声明不一致：", file=sys.stderr)
            for line in mismatches:
                print(f"  {line}", file=sys.stderr)
            return 1
        versions = collect_declared_versions(root)
        print(f"[PASS] 版本一致：{set(versions.values())}")
        return 0

    if not args.artifact_kind:
        parser.error("--artifact-kind 必填（或使用 --check-versions）")
    output_dir = args.output_dir or (root / "release")
    python_version = args.python_version or ".".join(map(str, sys.version_info[:3]))
    try:
        build_info = generate(
            root,
            artifact_kind=args.artifact_kind,
            target_os=args.target_os,
            node_version=args.node_version,
            build_id=args.build_id,
            allow_dirty=args.allow_dirty,
            output_dir=output_dir,
            python_version=python_version,
        )
    except BuildInfoGenerationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] {BUILD_INFO_FILENAME}: {build_info['git_sha'][:12]} @{build_info['product_version']}")
    print(f"[OK] frontend manifest sha256: {build_info['frontend_manifest_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
