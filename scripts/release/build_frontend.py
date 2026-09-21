#!/usr/bin/env python3
"""前端唯一构建入口（release-artifact-equivalence-gate W2 / 计划 §5.3）。

流水线中前端只允许在此构建一次；后续 EXE/DEB/RPM/Docker 前端镜像只消费
`frontend/dist` 与本脚本产出的 `frontend-asset-manifest.json`，禁止各自
`npm run build`。

产出：
  frontend/dist/                                  构建产物（唯一）
  <output-dir>/frontend-asset-manifest.json       资产清单（路径/大小/SHA256）
  <output-dir>/frontend-build-meta.json           Node/npm 版本记录

fail-closed：Node 主版本与 release/release-config.json 不一致即退出（--skip-node-check
仅供本地救急，产物会带 skip_node_check 标记）。
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent

sys.path.insert(0, str(SCRIPT_DIR))

from generate_build_info import (  # noqa: E402  (同目录模块，path 注入后导入)
    build_frontend_asset_manifest,
    load_release_config,
)


class FrontendBuildError(RuntimeError):
    """fail-closed：构建身份或工具链不满足即失败。"""


def _run(cmd: Sequence[str], cwd: Path) -> None:
    printable = " ".join(cmd)
    print(f"[RUN] {printable}  (cwd={cwd})")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        raise FrontendBuildError(f"命令失败（exit={result.returncode}）：{printable}")


def _resolve_node_major(root: Path) -> str:
    config = load_release_config(root)
    pinned = config.get("toolchain", {}).get("w1_pinned", {}).get("node")
    if not isinstance(pinned, str) or not re.match(r"^\d+\.\d+\.\d+$", pinned):
        raise FrontendBuildError("release-config toolchain.w1_pinned.node 缺失/非法")
    return pinned.split(".")[0]


def _check_node(root: Path, skip: bool) -> Dict[str, str]:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise FrontendBuildError("node/npm 不在 PATH")
    node_version = subprocess.run([node, "-v"], capture_output=True, text=True, check=True).stdout.strip()
    npm_version = subprocess.run([npm, "-v"], capture_output=True, text=True, check=True).stdout.strip()
    match = re.fullmatch(r"v(\d+)\..+", node_version)
    if not match:
        raise FrontendBuildError(f"无法解析 node 版本：{node_version}")
    expected_major = _resolve_node_major(root)
    if match.group(1) != expected_major and not skip:
        raise FrontendBuildError(
            f"Node 主版本 {match.group(1)} 与锁定版本线 {expected_major} 不一致"
            f"（release-config toolchain.w1_pinned.node）；如确需跳过用 --skip-node-check"
        )
    return {"node": node_version, "npm": npm_version, "platform": platform.platform()}


def build(root: Path, output_dir: Path, *, skip_node_check: bool) -> Dict[str, object]:
    frontend_dir = root / "frontend"
    if not (frontend_dir / "package.json").is_file():
        raise FrontendBuildError(f"frontend 目录异常：{frontend_dir}")

    toolchain = _check_node(root, skip_node_check)

    npm = shutil.which("npm")
    if platform.system() == "Windows":
        npm_cmd = [str(Path(npm).with_name("npm.cmd"))]
    else:
        npm_cmd = [npm]

    _run([*npm_cmd, "ci", "--legacy-peer-deps"], frontend_dir)
    _run([*npm_cmd, "run", "build"], frontend_dir)

    dist_dir = frontend_dir / "dist"
    manifest, manifest_sha = build_frontend_asset_manifest(dist_dir)

    # manifest 文件保持纯规范形态（与制品内嵌副本逐字节一致）；sha 只写入 meta。
    # newline="\n"：跨平台字节一致。
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "frontend-asset-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    meta: Dict[str, object] = {
        "schema_version": 1,
        "toolchain": toolchain,
        "skip_node_check": skip_node_check,
        "frontend_manifest_sha256": manifest_sha,
        "file_count": manifest["file_count"],
    }
    (output_dir / "frontend-build-meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return meta


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Windows 控制台默认 cp1252：含中文的输出会 UnicodeEncodeError（CI 实测拦截）
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None, help="默认 <root>/release/build/frontend")
    parser.add_argument("--skip-node-check", action="store_true", help="跳过 Node 版本线校验（救急，产物带标记）")
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    output_dir = args.output_dir or (root / "release" / "build" / "frontend")
    try:
        meta = build(root, output_dir, skip_node_check=args.skip_node_check)
    except FrontendBuildError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] frontend manifest sha256: {meta['frontend_manifest_sha256']}（{meta['file_count']} 文件）")
    print(f"[OK] 输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
