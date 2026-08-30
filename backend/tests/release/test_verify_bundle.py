"""W2 bundle 验证器纯函数回归（release-artifact-equivalence-gate task .4 / G1+G5）。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUNDLE_PATH = _REPO_ROOT / "scripts" / "release" / "verify_release_bundle.py"


def _load_bundle():
    spec = importlib.util.spec_from_file_location("btdeck_verify_bundle", _BUNDLE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bundle():
    return _load_bundle()


def _info(**overrides):
    base = {
        "product_version": "1.0.6",
        "git_sha": "29c6f6f68ab35e25f8cf7237ee187de359c77714",
        "git_tag": "v1.0.6",
        "alembic_head": "c1d2e3f4a5b6",
        "frontend_manifest_sha256": "a" * 64,
        "dirty": False,
    }
    base.update(overrides)
    return base


class TestCompareIdentities:
    def test_identical_infos_pass(self, bundle):
        infos = {"linux-binary": _info(), "linux-deb": _info(), "docker-backend": _info()}
        assert bundle.compare_identities(infos) == []

    def test_git_sha_drift_detected(self, bundle):
        infos = {
            "linux-binary": _info(),
            "linux-deb": _info(git_sha="433f729fd9945afbff259d66b6a7ccb9efbc696d"),
        }
        problems = bundle.compare_identities(infos)
        assert any("git_sha" in p and "不一致" in p for p in problems)

    def test_version_drift_detected(self, bundle):
        infos = {"linux-binary": _info(), "docker-frontend": _info(product_version="1.0.7")}
        problems = bundle.compare_identities(infos)
        assert any("product_version" in p for p in problems)

    def test_dirty_artifact_detected(self, bundle):
        infos = {"linux-binary": _info(), "linux-rpm": _info(dirty=True)}
        problems = bundle.compare_identities(infos)
        assert any("dirty" in p for p in problems)

    def test_missing_sha_detected(self, bundle):
        infos = {"linux-binary": _info(), "docker-backend": _info(git_sha=None)}
        problems = bundle.compare_identities(infos)
        assert any("git_sha 缺失" in p for p in problems)

    def test_empty_inputs_fail_closed(self, bundle):
        assert bundle.compare_identities({}) != []


class TestCompareFrontendManifests:
    def test_identical_manifests_pass(self, bundle):
        payload = b'{"schema_version":1,"files":[]}'
        manifests = {"linux-binary": payload, "linux-deb": payload, "frontend-build": payload}
        assert bundle.compare_frontend_manifests(manifests) == []

    def test_divergent_manifest_detected(self, bundle):
        manifests = {
            "linux-binary": b'{"schema_version":1,"files":[{"path":"index.html"}]}',
            "linux-deb": b'{"schema_version":1,"files":[{"path":"index.html","sha256":"x"}]}',
        }
        problems = bundle.compare_frontend_manifests(manifests)
        assert any("不一致" in p and "linux-deb" in p for p in problems)

    def test_empty_manifests_fail_closed(self, bundle):
        assert bundle.compare_frontend_manifests({}) != []
