"""W1 build-info 运行时读取回归（release-artifact-equivalence-gate task .2）。

覆盖：dev 源码回退（不伪造身份）、合法嵌入身份、fail-closed 负向变异
（JSON 损坏/缺字段/短 SHA/dirty=true）。
"""

from __future__ import annotations

import json

import pytest

from app.core import build_info
from app.version import CURRENT_VERSION


@pytest.fixture(autouse=True)
def _reset_cache():
    build_info.reset_cache()
    yield
    build_info.reset_cache()


@pytest.fixture(autouse=True)
def _no_repo_build_info(monkeypatch, tmp_path):
    """隔离仓库布局与 /app 候选位，强制走环境变量指定的路径。"""
    monkeypatch.setenv("BTDECK_BUILD_INFO", str(tmp_path / "absent-build-info.json"))
    yield


def _valid_payload() -> dict:
    return {
        "schema_version": 1,
        "product_version": "1.0.6",
        "git_sha": "29c6f6f68ab35e25f8cf7237ee187de359c77714",
        "git_tag": "v1.0.6",
        "source_date_epoch": 1770000000,
        "build_id": None,
        "artifact_kind": "linux-deb",
        "target_os": "linux",
        "target_arch": "amd64",
        "python_version": "3.11.9",
        "node_version": "22.23.2",
        "alembic_head": "c1d2e3f4a5b6",
        "frontend_manifest_sha256": "a" * 64,
        "source_manifest_sha256": "b" * 64,
        "dependency_manifest_sha256": None,
        "dirty": False,
    }


def _write_build_info(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestDevFallback:
    def test_source_mode_does_not_fabricate_identity(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(tmp_path / "not-exist.json"))
        info = build_info.get_build_info()
        assert info["source_mode"] is True
        assert info["git_sha"] is None
        assert info["alembic_head"] is None
        assert info["frontend_manifest_sha256"] is None
        assert info["product_version"] == CURRENT_VERSION

    def test_identity_block_dev_shape(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(tmp_path / "not-exist.json"))
        block = build_info.build_identity_block()
        assert block == {"status": "dev", "productVersion": CURRENT_VERSION}


class TestEmbeddedIdentity:
    def test_valid_payload_exposes_full_identity(self, monkeypatch, tmp_path):
        payload = _valid_payload()
        target = tmp_path / "build-info.json"
        _write_build_info(target, payload)
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))

        info = build_info.get_build_info()
        assert info["source_mode"] is False
        assert info["git_sha"] == payload["git_sha"]
        assert info["artifact_kind"] == "linux-deb"

        block = build_info.build_identity_block()
        assert block["status"] == "ok"
        assert block["gitSha"] == payload["git_sha"]
        assert block["alembicHead"] == payload["alembic_head"]
        assert block["frontendManifestSha256"] == payload["frontend_manifest_sha256"]
        assert block["productVersion"] == "1.0.6"

    def test_result_is_cached_until_reset(self, monkeypatch, tmp_path):
        target = tmp_path / "build-info.json"
        _write_build_info(target, _valid_payload())
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))
        first = build_info.get_build_info()
        target.unlink()
        assert build_info.get_build_info() is first
        build_info.reset_cache()
        block = build_info.build_identity_block()
        assert block["status"] == "dev"


class TestFailClosedMutations:
    def _mutated(self, monkeypatch, tmp_path, **overrides):
        payload = _valid_payload()
        payload.update(overrides)
        target = tmp_path / "build-info.json"
        _write_build_info(target, payload)
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))

    def test_corrupt_json_rejected(self, monkeypatch, tmp_path):
        target = tmp_path / "build-info.json"
        target.write_text("{ not json", encoding="utf-8")
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))
        with pytest.raises(build_info.BuildInfoError, match="无法读取"):
            build_info.get_build_info()

    def test_missing_field_rejected(self, monkeypatch, tmp_path):
        payload = _valid_payload()
        del payload["alembic_head"]
        target = tmp_path / "build-info.json"
        _write_build_info(target, payload)
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))
        with pytest.raises(build_info.BuildInfoError, match="缺少字段"):
            build_info.get_build_info()

    def test_short_sha_rejected(self, monkeypatch, tmp_path):
        self._mutated(monkeypatch, tmp_path, git_sha="29c6f6f")
        with pytest.raises(build_info.BuildInfoError, match="git_sha"):
            build_info.get_build_info()

    def test_dirty_artifact_rejected(self, monkeypatch, tmp_path):
        self._mutated(monkeypatch, tmp_path, dirty=True)
        with pytest.raises(build_info.BuildInfoError, match="dirty"):
            build_info.get_build_info()

    def test_unknown_artifact_kind_rejected(self, monkeypatch, tmp_path):
        self._mutated(monkeypatch, tmp_path, artifact_kind="mystery-kind")
        with pytest.raises(build_info.BuildInfoError, match="artifact_kind"):
            build_info.get_build_info()

    def test_invalid_identity_block_hides_details(self, monkeypatch, tmp_path):
        target = tmp_path / "build-info.json"
        target.write_text("broken", encoding="utf-8")
        monkeypatch.setenv("BTDECK_BUILD_INFO", str(target))
        block = build_info.build_identity_block()
        assert block == {"status": "invalid"}
