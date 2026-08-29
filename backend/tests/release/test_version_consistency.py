"""W1 版本一致性回归（release-artifact-equivalence-gate task .2）。

直接调用 scripts/release/generate_build_info.py 的纯函数：真实仓库必须六处一致；
负向用例在临时目录构造漂移树，证明检查器能发现任意单点漂移（变异等价）。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GENERATOR_PATH = _REPO_ROOT / "scripts" / "release" / "generate_build_info.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("btdeck_release_generator", _GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator():
    return _load_generator()


class TestRealRepositoryConsistency:
    def test_all_six_version_sources_agree(self, generator):
        mismatches = generator.check_versions(_REPO_ROOT)
        assert mismatches == [], "版本漂移：\n  " + "\n  ".join(mismatches)

    def test_declared_sources_are_six(self, generator):
        versions = generator.collect_declared_versions(_REPO_ROOT)
        assert len(versions) == 6
        assert set(versions.values()) == {versions["release/release-config.json"]}

    def test_alembic_single_head_on_real_chain(self, generator):
        head = generator.collect_alembic_head(_REPO_ROOT / "backend")
        assert re.fullmatch(r"[0-9a-f]{12}", head)


def _write_minimal_tree(root: Path, *, product_version: str, overrides: dict) -> None:
    """构造六文件最小版本树；overrides 形如 {"backend/app/version.py": "1.0.7"}。"""
    defaults = {
        "release/release-config.json": (
            '{"candidate": {"product_version": "%s"}}' % product_version
        ),
        "backend/app/version.py": 'CURRENT_VERSION = "%s"\n' % product_version,
        "frontend/package.json": '{"version": "%s"}\n' % product_version,
        "feature_list.json": '{"release_version": "%s"}\n' % product_version,
        "deploy/btdeck.iss": '#define AppVersion "%s"\n' % product_version,
        "deploy/build-linux.sh": 'VERSION="%s"\n' % product_version,
    }
    merged = dict(defaults)
    merged.update(overrides)
    for relpath, content in merged.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class TestDriftDetection:
    """负向变异：任一来源漂移必须被点名（不放过、不误报其他来源）。"""

    @pytest.mark.parametrize(
        "relpath,mutated",
        [
            ("backend/app/version.py", 'CURRENT_VERSION = "1.0.7"\n'),
            ("frontend/package.json", '{"version": "1.0.7"}\n'),
            ("feature_list.json", '{"release_version": "1.0.7"}\n'),
            ("deploy/btdeck.iss", '#define AppVersion "1.0.7"\n'),
            ("deploy/build-linux.sh", 'VERSION="1.0.7"\n'),
        ],
    )
    def test_single_source_drift_is_reported(self, generator, tmp_path, relpath, mutated):
        _write_minimal_tree(tmp_path, product_version="1.0.6", overrides={relpath: mutated})
        mismatches = generator.check_versions(tmp_path)
        assert len(mismatches) == 1
        assert relpath.replace("\\", "/") in mismatches[0]

    def test_release_config_drift_is_reported(self, generator, tmp_path):
        _write_minimal_tree(tmp_path, product_version="1.0.6", overrides={})
        (tmp_path / "release/release-config.json").write_text(
            '{"candidate": {"product_version": "1.0.7"}}', encoding="utf-8"
        )
        mismatches = generator.check_versions(tmp_path)
        assert len(mismatches) == 5  # config 是基准，其余五处全部失配

    def test_missing_source_file_fails_closed(self, generator, tmp_path):
        _write_minimal_tree(tmp_path, product_version="1.0.6", overrides={})
        (tmp_path / "deploy/btdeck.iss").unlink()
        with pytest.raises(generator.BuildInfoGenerationError, match="btdeck.iss"):
            generator.collect_declared_versions(tmp_path)


class TestAlembicHeadParsing:
    def _write_revision(self, root: Path, name: str, revision: str, down: str | None) -> None:
        down_literal = "None" if down is None else f'"{down}"'
        (root / "backend/alembic/versions").mkdir(parents=True, exist_ok=True)
        (root / "backend/alembic/versions" / name).write_text(
            f'revision: str = "{revision}"\ndown_revision: str | None = {down_literal}\n',
            encoding="utf-8",
        )

    def test_forked_chain_rejected(self, generator, tmp_path):
        self._write_revision(tmp_path, "a.py", "aaaaaaaaaaaa", None)
        self._write_revision(tmp_path, "b.py", "bbbbbbbbbbbb", "aaaaaaaaaaaa")
        self._write_revision(tmp_path, "c1.py", "c1c1c1c1c1c1", "bbbbbbbbbbbb")
        self._write_revision(tmp_path, "c2.py", "c2c2c2c2c2c2", "bbbbbbbbbbbb")
        with pytest.raises(generator.BuildInfoGenerationError, match="单一 head"):
            generator.collect_alembic_head(tmp_path / "backend")

    def test_missing_parent_rejected(self, generator, tmp_path):
        self._write_revision(tmp_path, "a.py", "aaaaaaaaaaaa", "0000000000ff")
        with pytest.raises(generator.BuildInfoGenerationError, match="down_revision"):
            generator.collect_alembic_head(tmp_path / "backend")

    def test_empty_chain_rejected(self, generator, tmp_path):
        (tmp_path / "backend/alembic/versions").mkdir(parents=True)
        with pytest.raises(generator.BuildInfoGenerationError, match="未发现任何迁移"):
            generator.collect_alembic_head(tmp_path / "backend")
