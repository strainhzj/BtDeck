"""W1 公共依赖锁与打包增量依赖回归（release-artifact-equivalence-gate task .3）。

真实结构断言 + 负向变异（临时树）：qB 分叉、白名单外依赖、覆盖公共版本、
缺哈希、未 == 锁定都必须报红。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKER_PATH = _REPO_ROOT / "scripts" / "release" / "check_dependencies.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("btdeck_release_dep_checker", _CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _load_checker()


class TestRealRepository:
    def test_dependency_structure_passes(self, checker):
        problems = checker.check_all(_REPO_ROOT)
        assert problems == [], "依赖结构违规：\n  " + "\n  ".join(problems)

    def test_qbittorrent_api_unified_at_2025_2(self, checker):
        locked = checker.parse_locked_requirements(_REPO_ROOT / checker.LOCK_RELPATH)
        assert locked["qbittorrent-api"].startswith("2025.2."), (
            f"qB 仍分叉或未锁 2025.2.x：{locked.get('qbittorrent-api')}"
        )

    def test_forbidden_extras_removed_from_packaging(self, checker):
        for relpath in checker.PACKAGING_RELPATHS.values():
            entries = checker.parse_requirements(_REPO_ROOT / relpath)
            names = {value for kind, value in entries if kind == "requirement"}
            assert "passlib" not in names, f"{relpath} 仍声明 passlib（仅 dev 依赖）"
            assert "email-validator" not in names, f"{relpath} 仍声明 email-validator（运行时零使用）"

    def test_common_source_keeps_qb_declared_2025_2(self, checker):
        declared = checker.declared_common_versions(_REPO_ROOT / checker.COMMON_REQUIREMENTS_RELPATH)
        assert declared["qbittorrent-api"] == "2025.2.0"


def _write_dep_tree(root: Path, *, lock_text: str, packaging_text: str) -> None:
    (root / "backend").mkdir(parents=True, exist_ok=True)
    (root / "backend/requirements.txt").write_text(
        "fastapi~=0.115.6\nqbittorrent-api~=2025.2.0\n", encoding="utf-8"
    )
    (root / "backend/requirements-lock.txt").write_text(lock_text, encoding="utf-8")
    deploy = root / "deploy"
    deploy.mkdir(parents=True, exist_ok=True)
    (deploy / "requirements-windows-package.txt").write_text(packaging_text, encoding="utf-8")
    (deploy / "requirements-linux-package.txt").write_text(
        "-r ../backend/requirements-lock.txt\npyinstaller~=6.20.0\n", encoding="utf-8"
    )


_GOOD_LOCK = (
    "# lock header\n"
    "fastapi==0.115.6 \\\n"
    "    --hash=sha256:1111111111111111111111111111111111111111111111111111111111111111 \\\n"
    "    --hash=sha256:2222222222222222222222222222222222222222222222222222222222222222\n"
    "qbittorrent-api==2025.2.0 \\\n"
    "    --hash=sha256:3333333333333333333333333333333333333333333333333333333333333333\n"
)


class TestNegativeMutations:
    def test_qb_fork_detected(self, checker, tmp_path):
        _write_dep_tree(
            tmp_path,
            lock_text=_GOOD_LOCK.replace("qbittorrent-api==2025.2.0", "qbittorrent-api==2025.5.0"),
            packaging_text="-r ../backend/requirements-lock.txt\npyinstaller~=6.20.0\npywebview~=5.4.0\n",
        )
        problems = checker.check_all(tmp_path)
        assert any("qbittorrent-api" in p and "漂移" in p for p in problems)

    def test_extra_dependency_outside_whitelist_detected(self, checker, tmp_path):
        _write_dep_tree(
            tmp_path,
            lock_text=_GOOD_LOCK,
            packaging_text=(
                "-r ../backend/requirements-lock.txt\n"
                "pyinstaller~=6.20.0\n"
                "passlib[bcrypt]~=1.7.4\n"
            ),
        )
        problems = checker.check_all(tmp_path)
        assert any("白名单外依赖" in p and "passlib" in p for p in problems)

    def test_common_version_override_detected(self, checker, tmp_path):
        _write_dep_tree(
            tmp_path,
            lock_text=_GOOD_LOCK,
            packaging_text=(
                "-r ../backend/requirements-lock.txt\n"
                "pyinstaller~=6.20.0\n"
                "fastapi~=0.99.0\n"
            ),
        )
        problems = checker.check_all(tmp_path)
        assert any("fastapi" in p and "白名单外" in p for p in problems)

    def test_missing_ref_to_common_lock_detected(self, checker, tmp_path):
        _write_dep_tree(
            tmp_path,
            lock_text=_GOOD_LOCK,
            packaging_text="pyinstaller~=6.20.0\npywebview~=5.4.0\n",
        )
        problems = checker.check_all(tmp_path)
        assert any("必须恰好引用一次公共锁" in p for p in problems)

    def test_lock_entry_without_hash_detected(self, checker, tmp_path):
        _write_dep_tree(
            tmp_path,
            lock_text="fastapi==0.115.6\nqbittorrent-api==2025.2.0 \\\n    --hash=sha256:3" + "3" * 63 + "\n",
            packaging_text="-r ../backend/requirements-lock.txt\npyinstaller~=6.20.0\npywebview~=5.4.0\n",
        )
        problems = checker.check_all(tmp_path)
        assert any("缺哈希" in p and "fastapi" in p for p in problems)

    def test_unlocked_pin_detected(self, checker, tmp_path):
        _write_dep_tree(
            tmp_path,
            lock_text="fastapi~=0.115.6\nqbittorrent-api==2025.2.0 \\\n    --hash=sha256:3" + "3" * 63 + "\n",
            packaging_text="-r ../backend/requirements-lock.txt\npyinstaller~=6.20.0\npywebview~=5.4.0\n",
        )
        problems = checker.check_all(tmp_path)
        assert any("未精确锁定" in p for p in problems)

    def test_missing_lock_file_reported(self, checker, tmp_path):
        problems = checker.check_all(tmp_path)
        assert any("公共锁缺失" in p for p in problems)
