#!/usr/bin/env python3
"""公共依赖锁与打包增量依赖的一致性检查（release-artifact-equivalence-gate G2/W1）。

结构（W1 起）：
  backend/requirements.txt          公共运行依赖唯一“直接依赖”来源（可解析范围 ~= 等）
  backend/requirements-lock.txt     pip-compile --generate-hashes 锁（跨平台通用哈希）
  deploy/requirements-windows-package.txt  = -r 锁 + 平台增量（pyinstaller/pywebview）
  deploy/requirements-linux-package.txt    = -r 锁 + 平台增量（pyinstaller）

本检查器 fail-closed：
  - 打包文件必须引用公共锁，且增量依赖只能来自白名单；
  - 锁内每条依赖必须 == 精确锁定并带哈希；
  - 关键公共依赖（含 qbittorrent-api）版本不得在锁与源声明间漂移。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent.parent

COMMON_REQUIREMENTS_RELPATH = Path("backend/requirements.txt")
LOCK_RELPATH = Path("backend/requirements-lock.txt")
PACKAGING_RELPATHS = {
    "windows": Path("deploy/requirements-windows-package.txt"),
    "linux": Path("deploy/requirements-linux-package.txt"),
}
PACKAGING_REF_VALUE = "../backend/requirements-lock.txt"  # 打包文件中 -r 引用目标（不带前缀）

# 平台增量依赖白名单（只允许“新增”，不允许覆盖公共依赖版本）
PLATFORM_EXTRAS_WHITELIST: Dict[str, Tuple[str, ...]] = {
    "windows": ("pyinstaller", "pywebview"),
    "linux": ("pyinstaller",),
}

# 等价性必须逐包逐版本一致的关键公共依赖（G2）
CRITICAL_PACKAGES = (
    "fastapi",
    "starlette",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "qbittorrent-api",
    "transmission-rpc",
    "pycryptodomex",
    "uvicorn",
)

_REQ_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:===|==|~=|!=|>=|<=|>|<|\[|;|$)")


class DependencyCheckError(RuntimeError):
    """结构违反（供测试与 CI 断言）。"""


def parse_requirements(path: Path) -> List[Tuple[str, str]]:
    """返回 [(kind, value)]：kind ∈ {'ref','requirement','option'}。

    注释行与空行剔除；不以 -r/-- 开头的行按 requirement 名解析。
    """
    if not path.is_file():
        raise DependencyCheckError(f"requirements 文件缺失：{path}")
    entries: List[Tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            entries.append(("ref", line[3:].strip()))
        elif line.startswith("--"):
            entries.append(("option", line))
        else:
            match = _REQ_NAME.match(line)
            name = match.group(1).lower() if match else line
            entries.append(("requirement", name))
    return entries


def parse_locked_requirements(path: Path) -> Dict[str, str]:
    """解析锁文件：包名 → 精确版本（==x.y.z）。多行 --hash 归并到上一条。"""
    locked: Dict[str, str] = {}
    current: Optional[str] = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            current = None
            continue
        if line.startswith("--"):
            continue  # hash/额外选项，归并到 current（不校验形态，形态校验见 check_lock_shape）
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\[(?:[^]]*)\]?===?([^ ;]+)", line) or re.match(
            r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*===?\s*([^ ;]+)", line
        )
        if not match:
            raise DependencyCheckError(f"锁文件存在未精确锁定（==）的行：{line}")
        current = match.group(1).lower()
        locked[current] = match.group(2)
    return locked


def declared_common_versions(path: Path) -> Dict[str, str]:
    """backend/requirements.txt 的声明版本（~=x.y.z → x.y.z 起始段）。"""
    declared: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", " ")) and not line[0].isalpha():
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*~=\s*([0-9][0-9.]*)", line)
        if match:
            declared[match.group(1).lower()] = match.group(2)
    return declared


def check_lock_shape(path: Path) -> List[str]:
    """锁形态：全部 == 精确锁定且每条都带 --hash。返回问题列表。"""
    problems: List[str] = []
    pending_name: Optional[str] = None
    has_hash = False
    finished: List[Tuple[str, bool]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            if pending_name is not None:
                finished.append((pending_name, has_hash))
                pending_name, has_hash = None, False
            continue
        if line.startswith("--hash"):
            has_hash = True
            continue
        if line.startswith("--"):
            continue
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^]]*\])?\s*==", line):
            problems.append(f"锁行未精确锁定：{line}")
            continue
        if pending_name is not None:
            finished.append((pending_name, has_hash))
        pending_name = line.split("==", 1)[0].strip().lower()
        has_hash = False
    if pending_name is not None:
        finished.append((pending_name, has_hash))
    problems.extend(f"锁条目缺哈希：{name}" for name, hashed in finished if not hashed)
    return problems


def check_packaging(root: Path) -> List[str]:
    """校验两个打包 requirements 的结构（引用公共锁 + 白名单增量）。"""
    problems: List[str] = []
    for platform, relpath in PACKAGING_RELPATHS.items():
        path = root / relpath
        if not path.is_file():
            problems.append(f"打包 requirements 缺失：{path}")
            continue
        entries = parse_requirements(path)
        refs = [value for kind, value in entries if kind == "ref"]
        requirements = [value for kind, value in entries if kind == "requirement"]
        if refs != [PACKAGING_REF_VALUE]:
            problems.append(f"{relpath} 必须恰好引用一次公共锁（-r {PACKAGING_REF_VALUE}），实际：{refs}")
        allowed = set(PLATFORM_EXTRAS_WHITELIST[platform])
        for name in requirements:
            if name not in allowed:
                problems.append(f"{relpath} 存在白名单外依赖：{name}（允许：{sorted(allowed)}）")
    return problems


def check_critical_versions(root: Path) -> List[str]:
    """关键依赖：锁内版本必须落在源声明的 ~= 范围内（禁止漂移/分叉）。"""
    common_path = root / COMMON_REQUIREMENTS_RELPATH
    lock_path = root / LOCK_RELPATH
    if not lock_path.is_file():
        return [f"公共锁缺失：{lock_path}"]
    declared = declared_common_versions(common_path)
    try:
        locked = parse_locked_requirements(lock_path)
    except DependencyCheckError as exc:
        return [f"锁文件无法解析（关键依赖比对中止）：{exc}"]
    problems: List[str] = []
    for package in CRITICAL_PACKAGES:
        if package not in locked:
            problems.append(f"关键依赖 {package} 不在锁内")
            continue
        locked_version = locked[package]
        base = declared.get(package)
        if base is None:
            problems.append(f"关键依赖 {package} 未在 backend/requirements.txt 以 ~= 声明")
            continue
        base_parts = base.rstrip(".").split(".")
        locked_parts = locked_version.split(".")
        # ~=x.y.z 允许 z 任意、x.y 固定；~=x.y 允许 y 任意、x 固定
        prefix = base_parts[:-1] if len(base_parts) >= 3 else base_parts[:1]
        if locked_parts[: len(prefix)] != prefix:
            problems.append(
                f"关键依赖 {package} 漂移：锁 {locked_version} 超出源声明 ~= {base}"
            )
    return problems


def check_all(root: Path) -> List[str]:
    problems: List[str] = []
    lock_path = root / LOCK_RELPATH
    if not lock_path.is_file():
        return [f"公共锁缺失：{lock_path}"]
    problems.extend(check_lock_shape(lock_path))
    problems.extend(check_packaging(root))
    problems.extend(check_critical_versions(root))
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    args = parser.parse_args(argv)
    problems = check_all(args.project_root.resolve())
    if problems:
        print("[FAIL] 依赖结构检查未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    locked = parse_locked_requirements(args.project_root.resolve() / LOCK_RELPATH)
    print(f"[PASS] 依赖结构一致（锁内 {len(locked)} 包；qB={locked.get('qbittorrent-api')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
