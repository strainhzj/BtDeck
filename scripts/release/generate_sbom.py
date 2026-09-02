#!/usr/bin/env python3
"""W5 SBOM 生成器（release-artifact-equivalence-gate task .9 / G9）。

对五类目标生成 CycloneDX JSON SBOM，工具镜像按 release/tool-versions.json
固定 digest 引用（同 G10 原则：不引用可变 tag）：

  source-backend    backend 源（requirements-lock 净化后供 syft 解析 python 依赖）
  source-frontend   frontend 源（package-lock.json；SBOM 后滤非生产依赖）
  binary-linux      release/build/linux-binary 的 PyInstaller 产物目录
  deb / rpm         dist/ 下的包文件（syft 原生解包目录清单）
  docker-backend / docker-frontend   docker save 导出的镜像 tar（docker-archive:）

输出 --output-dir（默认 release/build/sbom）：
  sbom-<target>.json 与 index.json（各 SBOM sha256/组件数/工具版本——G10 证据
  digest 的数据源）。

纯函数（strip_lock_hashes / build_index / prod_npm_names）供
backend/tests/release/test_generate_sbom.py 回归。

注意：Windows/Git Bash 本地运行需在同一条命令内 export MSYS_NO_PATHCONV=1。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_TOOLS = DEFAULT_PROJECT_ROOT / "release" / "tool-versions.json"

# run_syft 需要的输出目录与文件名（main 里赋值；模块级缓存避免长参数链）
_OUT_DIR_CACHE: List[Path] = [Path(".")]
_OUT_NAME_CACHE: List[str] = ["sbom.json"]

ALL_TARGETS = (
    "source-backend",
    "source-frontend",
    "binary-linux",
    "deb",
    "rpm",
    "docker-backend",
    "docker-frontend",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_lock_hashes(lock_text: str) -> str:
    """requirements-lock → 干净 pins：去行尾续行符与 --hash 行。

    锁内嵌 --hash 会让 syft 的 requirements 解析失败（W1 实测语义）；
    净化是确定性文本变换（纯函数，单测覆盖）。
    """
    lines: List[str] = []
    for raw in lock_text.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            line = line[:-1].rstrip()
        if not line or line.strip().startswith("--hash"):
            continue
        if "--hash" in line:  # 同行内联哈希
            line = line.split("--hash", 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return "\n".join(lines) + "\n"


def prod_npm_names(lock_json: dict) -> set:
    """package-lock（v2/v3）中非 dev 依赖名集合（生产依赖过滤依据）。"""
    names: set = set()
    packages = lock_json.get("packages") or {}
    for path_key, meta in packages.items():
        if not path_key:  # 根包
            continue
        if meta.get("dev") or meta.get("optional"):
            continue
        name = meta.get("name") or path_key.rsplit("node_modules/", 1)[-1]
        names.add(name)
    if not packages:  # v1 锁（dependencies 扁平）
        for name, meta in (lock_json.get("dependencies") or {}).items():
            if not meta.get("dev"):
                names.add(name)
    return names


def build_index(entries: Dict[str, dict]) -> dict:
    """index.json 载荷：每目标文件名/sha256/组件数/工具版本（证据 digest 源）。"""
    return {
        "schema_version": 1,
        "targets": {
            name: {
                "file": Path(info["path"]).name,
                "sha256": info["sha256"],
                "components": info["components"],
            }
            for name, info in sorted(entries.items())
        },
    }


def load_tool_image(tools_path: Path, tool: str) -> str:
    tools = json.loads(tools_path.read_text(encoding="utf-8"))
    entry = tools.get("tools", {}).get(tool)
    if not entry or "@" not in entry.get("image", ""):
        raise SystemExit(f"[FAIL] tool-versions.json 缺 {tool} 的 digest 固定镜像")
    return entry["image"]


def docker_run(args: Sequence[str]) -> None:
    proc = subprocess.run(
        ["docker", "run", "--rm", *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"[FAIL] docker run 退出码 {proc.returncode}")


def run_syft(syft_image: str, source_desc: str, mounts: List[str]) -> None:
    """syft 扫描 source_desc（容器内路径/docker-archive: URI）出 cyclonedx-json。

    输出统一挂整个目录（/out rw）由调用方给文件名：对不存在的宿主文件做 -v
    会被 docker 自动建成目录（本地实测），逐文件挂载不可靠。
    """
    docker_run(
        [
            *mounts,
            "-v",
            f"{(_OUT_DIR_CACHE[0]).as_posix()}:/out",
            syft_image,
            source_desc,
            "-o",
            f"cyclonedx-json=/out/{_OUT_NAME_CACHE[0]}",
        ]
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--bundle-dir", type=Path, default=None)
    parser.add_argument("--dist-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--targets",
        default=",".join(ALL_TARGETS),
        help=f"逗号分隔目标子集（可用：{','.join(ALL_TARGETS)}）",
    )
    parser.add_argument("--tools", type=Path, default=DEFAULT_TOOLS)
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    bundle_dir = (args.bundle_dir or root / "release" / "build").resolve()
    dist_dir = (args.dist_dir or root / "dist").resolve()
    out_dir = (args.output_dir or bundle_dir / "sbom").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)

    unknown = [t for t in args.targets.split(",") if t and t not in ALL_TARGETS]
    if unknown:
        parser.error(f"未知目标: {unknown}")

    syft_image = load_tool_image(args.tools, "syft")
    _OUT_DIR_CACHE[0] = out_dir
    entries: Dict[str, dict] = {}

    def syft_scan(target: str, source_desc: str, extra_mounts: List[str]) -> Path:
        _OUT_NAME_CACHE[0] = f"sbom-{target}.json"
        run_syft(syft_image, source_desc, extra_mounts)
        return out_dir / f"sbom-{target}.json"

    def record(target: str, sbom_path: Path) -> None:
        payload = json.loads(sbom_path.read_text(encoding="utf-8"))
        entries[target] = {
            "path": str(sbom_path),
            "sha256": sha256_file(sbom_path),
            "components": len(payload.get("components", [])),
        }
        print(
            f"sbom {target}: {sbom_path.name} components={entries[target]['components']}"
        )

    wanted = set(t for t in args.targets.split(",") if t)

    if "source-backend" in wanted:
        # 锁净化（--hash 行剥离）后供 syft 解析——直接扫 backend/ 会漏/误读
        lock = (root / "backend" / "requirements-lock.txt").read_text(encoding="utf-8")
        clean = work_dir / "requirements-clean.txt"
        clean.write_text(strip_lock_hashes(lock), encoding="utf-8", newline="\n")
        out = syft_scan(
            "source-backend",
            "/src",
            ["-v", f"{clean.as_posix()}:/src/requirements.txt:ro"],
        )
        record("source-backend", out)

    if "source-frontend" in wanted:
        out = syft_scan(
            "source-frontend",
            "/src",
            ["-v", f"{(root / 'frontend').as_posix()}:/src:ro"],
        )
        # npm 生产依赖过滤：剔除 lock 中标记 dev/optional 的包（G9 口径）
        payload = json.loads(out.read_text(encoding="utf-8"))
        lock_json = json.loads(
            (root / "frontend" / "package-lock.json").read_text(encoding="utf-8")
        )
        prod = prod_npm_names(lock_json)
        payload["components"] = [
            c
            for c in payload.get("components", [])
            if c.get("name") in prod or c.get("type") == "application"
        ]
        out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        record("source-frontend", out)

    if "binary-linux" in wanted:
        binary_dir = bundle_dir / "linux-binary" / "dist"
        if not binary_dir.is_dir():
            raise SystemExit(f"[FAIL] PyInstaller 产物目录缺失：{binary_dir}")
        out = syft_scan(
            "binary-linux", "/src", ["-v", f"{binary_dir.as_posix()}:/src:ro"]
        )
        record("binary-linux", out)

    for target, pattern in (("deb", "*.deb"), ("rpm", "*.rpm")):
        if target not in wanted:
            continue
        files = sorted(dist_dir.glob(pattern))
        if not files:
            raise SystemExit(f"[FAIL] {target} 包缺失：{dist_dir / pattern}")
        out = syft_scan(
            target, f"/src/{files[0].name}", ["-v", f"{dist_dir.as_posix()}:/src:ro"]
        )
        record(target, out)

    for target, image in (
        ("docker-backend", "btdeck-backend"),
        ("docker-frontend", "btdeck-frontend"),
    ):
        if target not in wanted:
            continue
        tag = f"{image}:v1.0.6"
        tar_path = work_dir / f"{image}.tar"
        proc = subprocess.run(
            ["docker", "save", tag, "-o", str(tar_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            raise SystemExit(f"[FAIL] docker save {tag} 失败（镜像未构建？）")
        out = syft_scan(
            target,
            "docker-archive:/work/image.tar",
            ["-v", f"{work_dir.as_posix()}:/work:ro"],
        )
        record(target, out)

    index_path = out_dir / "index.json"
    index_path.write_text(
        json.dumps(build_index(entries), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"index: {index_path} targets={len(entries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
