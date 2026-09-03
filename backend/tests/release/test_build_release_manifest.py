"""W5 批次 D 发布清单生成器回归（release-artifact-equivalence-gate task .9 / G10）。

覆盖：schema 真校验（draft-07 对真实 release/schemas/release-manifest.schema.json）、
verdict 规则（生成器永不产 CERTIFIED）、evidence G0~G10 完整索引、digest 漂移变异、
signature 规范化（additionalProperties=false 契约）、compose env 渲染。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "release" / "build_release_manifest.py"
_SCHEMA_PATH = _REPO_ROOT / "release" / "schemas" / "release-manifest.schema.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("btdeck_build_manifest", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mf():
    return _load_module()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


BUILD_INFO = {
    "schema_version": 1,
    "product_version": "1.0.6",
    "git_tag": "v1.0.6",
    "git_sha": "a" * 40,
    "alembic_head": "c1d2e3f4a5b6",
    "frontend_manifest_sha256": "f" * 64,
    "source_date_epoch": 1788406900,
    "build_id": None,
    "dirty": False,
}

FILES = {
    "windows-exe": "btdeck.exe",
    "windows-setup": "BtDeck-v1.0.6-windows-x64-setup.exe",
    "linux-binary": "btdeck",
    "linux-deb": "BtDeck-v1.0.6-linux-amd64.deb",
    "linux-rpm": "BtDeck-v1.0.6-linux-amd64.rpm",
}


@pytest.fixture()
def fake_root(tmp_path):
    """完整 bundle 结构：dist 七制品 + staging build-info + 两份签名记录分片。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    for kind, name in FILES.items():
        (dist / name).write_bytes(f"content-of-{kind}".encode())

    bundle = tmp_path / "release" / "build"
    for staging in ("docker-backend", "linux-binary"):
        (bundle / staging).mkdir(parents=True)
        (bundle / staging / "build-info.json").write_text(
            json.dumps(BUILD_INFO), encoding="utf-8"
        )

    digests = {kind: _sha(f"content-of-{kind}".encode()) for kind in FILES}
    docker_records = [
        {
            "kind": kind,
            "ref": f"btdeck-{kind.split('-')[1]}:v1.0.6",
            "digest_source": "save-oci",
            "size_bytes": 300000,
            "pre_sha256": _sha(kind.encode()),
            "post_sha256": _sha(kind.encode()),
            "signature": {
                "mechanism": "cosign",
                "status": "signed",
                "signed_sha256": _sha(kind.encode()),
                "signature_file": "release/build/signatures/docker-images.sigstore.json",
                "verified": True,
            },
        }
        for kind in ("docker-backend", "docker-frontend")
    ]
    windows_records = [
        {
            "kind": kind,
            "path": f"dist/{name}",
            "mechanism": "authenticode",
            "pre_sha256": _sha(f"pre-{kind}".encode()),
            "post_sha256": digests[kind],
            "signature": {
                "mechanism": "authenticode",
                "status": "signed",
                "signed_sha256": digests[kind],
            },
        }
        for kind, name in FILES.items()
        if kind.startswith("windows-")
    ]
    (bundle / "signing-digests-docker.json").write_text(
        json.dumps({"mode": "formal", "records": docker_records}), encoding="utf-8"
    )
    (bundle / "signing-digests-windows.json").write_text(
        json.dumps({"mode": "formal", "records": windows_records}), encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------- 纯函数


class TestSigningEvidence:
    def test_all_signed_pass(self, mf, fake_root):
        signing = mf.merge_signing_records(fake_root / "release" / "build")
        status, _, _ = mf.signing_evidence(signing)
        assert status == "PASS"

    def test_unsigned_drill_indeterminate(self, mf, fake_root):
        bundle = fake_root / "release" / "build"
        signing = mf.merge_signing_records(bundle)
        signing["windows-exe"]["signature"]["status"] = "unsigned"
        status, _, _ = mf.signing_evidence(signing)
        assert status == "INDETERMINATE"

    def test_missing_target_indeterminate(self, mf, fake_root):
        bundle = fake_root / "release" / "build"
        signing = mf.merge_signing_records(bundle)
        del signing["docker-frontend"]
        status, _, _ = mf.signing_evidence(signing)
        assert status == "INDETERMINATE"

    def test_indeterminate_fail(self, mf, fake_root):
        bundle = fake_root / "release" / "build"
        signing = mf.merge_signing_records(bundle)
        signing["docker-backend"]["signature"]["status"] = "indeterminate"
        status, _, problems = mf.signing_evidence(signing)
        assert status == "FAIL"
        assert problems

    def test_no_records_not_run(self, mf):
        assert mf.signing_evidence({})[0] == "NOT_RUN"


class TestVerdict:
    def test_fail_evidence_rejected(self, mf):
        assert mf.compute_verdict([{"gate": "G9", "status": "FAIL"}]) == "REJECTED"

    def test_generator_never_certified(self, mf):
        """生成器契约：即使全 PASS 也只能 INDETERMINATE（CERTIFIED 属于人工审批）。"""
        all_pass = [{"gate": f"G{i}", "status": "PASS"} for i in range(11)]
        assert mf.compute_verdict(all_pass) == "INDETERMINATE"

    def test_not_run_indeterminate(self, mf):
        assert (
            mf.compute_verdict([{"gate": "G0", "status": "NOT_RUN"}]) == "INDETERMINATE"
        )


class TestNormalizeSignature:
    def test_strips_extra_keys(self, mf):
        signature = mf.normalize_signature(
            {
                "mechanism": "cosign",
                "status": "signed",
                "signed_sha256": "a" * 64,
                "signature_file": "x",
                "verified": True,
            }
        )
        assert set(signature) == {"mechanism", "status", "signed_sha256"}

    def test_none_passthrough(self, mf):
        assert mf.normalize_signature(None) is None


class TestRenderComposeEnv:
    def test_hex_only(self, mf):
        content = mf.render_compose_env(
            {
                "backend_digest": "sha256:" + "ab" * 32,
                "frontend_digest": "sha256:" + "cd" * 32,
            }
        )
        assert f"BTDECK_BACKEND_DIGEST={'ab' * 32}\n" in content
        assert f"BTDECK_FRONTEND_DIGEST={'cd' * 32}\n" in content
        assert "sha256:" not in content  # 模板自带前缀，env 只给 hex


class TestEvidenceDiscovery:
    def test_fragment_absent_not_run(self, mf, tmp_path):
        status, digest = mf.fragment_evidence(tmp_path, "G6")
        assert status == "NOT_RUN"
        assert digest is None

    def test_fragment_present(self, mf, tmp_path):
        (tmp_path / "gate-fragments").mkdir()
        path = tmp_path / "gate-fragments" / "G6.json"
        path.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        status, digest = mf.fragment_evidence(tmp_path, "G6")
        assert status == "PASS"
        assert digest == _sha(path.read_bytes())

    def test_fragment_bad_enum_indeterminate(self, mf, tmp_path):
        (tmp_path / "gate-fragments").mkdir()
        (tmp_path / "gate-fragments" / "G6.json").write_text(
            json.dumps({"status": "SOMEHOW"}), encoding="utf-8"
        )
        assert mf.fragment_evidence(tmp_path, "G6")[0] == "INDETERMINATE"

    def test_gate_report_evidence(self, mf, tmp_path):
        (tmp_path / "gate-report.json").write_text(
            json.dumps({"gates": {"G1": "PASS", "G5": "FAIL"}}), encoding="utf-8"
        )
        assert mf.gate_report_evidence(tmp_path, "G1")[0] == "PASS"
        assert mf.gate_report_evidence(tmp_path, "G5")[0] == "FAIL"
        assert mf.gate_report_evidence(tmp_path, "G4")[0] == "INDETERMINATE"

    def test_evidence_covers_all_gates(self, mf, fake_root):
        bundle = fake_root / "release" / "build"
        signing = mf.merge_signing_records(bundle)
        evidence = mf.build_evidence(
            bundle, signing, bundle / "release-manifest.json", "INDETERMINATE"
        )
        gates = {entry["gate"] for entry in evidence}
        assert gates == {f"G{i}" for i in range(11)}


# ---------------------------------------------------------------- artifacts 段


class TestBuildArtifacts:
    def _run(self, mf, fake_root):
        bundle = fake_root / "release" / "build"
        signing = mf.merge_signing_records(bundle)
        return mf.build_artifacts_section(
            mf.collect_artifact_inventory(fake_root / "dist", "1.0.6"),
            signing,
            bundle,
            "1.0.6",
        )

    def test_seven_artifacts(self, mf, fake_root):
        artifacts, problems = self._run(mf, fake_root)
        assert problems == []
        kinds = [a["kind"] for a in artifacts]
        assert set(kinds) == set(FILES) | {"docker-backend", "docker-frontend"}
        internal = {a["kind"] for a in artifacts if a["internal"]}
        assert internal == {"linux-binary"}

    def test_signature_normalized(self, mf, fake_root):
        artifacts, _ = self._run(mf, fake_root)
        for artifact in artifacts:
            if artifact["signature"]:
                assert set(artifact["signature"]) <= {
                    "mechanism",
                    "status",
                    "signed_sha256",
                }

    def test_digest_drift_detected(self, mf, fake_root):
        """变异：签名后改动 windows-exe 文件 → 漂移问题。"""
        (fake_root / "dist" / "btdeck.exe").write_bytes(b"tampered-after-signing")
        artifacts, problems = self._run(mf, fake_root)
        assert any("漂移" in p for p in problems)
        assert any("windows-exe" in p for p in problems)

    def test_missing_artifact_fail_closed(self, mf, fake_root):
        (fake_root / "dist" / "btdeck.exe").unlink()
        with pytest.raises(mf.ManifestError, match="制品缺失"):
            self._run(mf, fake_root)


# ---------------------------------------------------------------- schema 真校验


class TestSchemaValidation:
    def test_valid_manifest_passes(self, mf, fake_root):
        bundle = fake_root / "release" / "build"
        signing = mf.merge_signing_records(bundle)
        artifacts, _ = mf.build_artifacts_section(
            mf.collect_artifact_inventory(fake_root / "dist", "1.0.6"),
            signing,
            bundle,
            "1.0.6",
        )
        evidence = mf.build_evidence(
            bundle, signing, bundle / "release-manifest.json", "INDETERMINATE"
        )
        manifest = {
            "schema_version": 1,
            "product_version": "1.0.6",
            "git_tag": "v1.0.6",
            "git_sha": "a" * 40,
            "source_date_epoch": 1788406900,
            "created_at": "2026-09-03T00:00:00+00:00",
            "build_id": None,
            "frontend_asset_manifest_sha256": "f" * 64,
            "artifacts": artifacts,
            "evidence": evidence,
            "compose": {
                "backend_digest": "sha256:" + _sha(b"docker-backend"),
                "frontend_digest": "sha256:" + _sha(b"docker-frontend"),
                "compose_file": "deploy/docker-compose.release.yml",
            },
            "verdict": "INDETERMINATE",
            "approver": None,
            "approved_at": None,
        }
        assert mf.validate_manifest(manifest, _SCHEMA_PATH) == []

    def test_bad_sha_fails(self, mf, fake_root):
        bundle = fake_root / "release" / "build"
        signing = mf.merge_signing_records(bundle)
        artifacts, _ = mf.build_artifacts_section(
            mf.collect_artifact_inventory(fake_root / "dist", "1.0.6"),
            signing,
            bundle,
            "1.0.6",
        )
        artifacts[0]["sha256"] = "not-a-sha"
        evidence = mf.build_evidence(
            bundle, signing, bundle / "release-manifest.json", "INDETERMINATE"
        )
        manifest = {
            "schema_version": 1,
            "product_version": "1.0.6",
            "git_tag": "v1.0.6",
            "git_sha": "a" * 40,
            "source_date_epoch": 1788406900,
            "created_at": "2026-09-03T00:00:00+00:00",
            "artifacts": artifacts,
            "evidence": evidence,
            "verdict": "INDETERMINATE",
        }
        errors = mf.validate_manifest(manifest, _SCHEMA_PATH)
        assert errors


# ---------------------------------------------------------------- 端到端 main


class TestMainEndToEnd:
    def test_generates_indeterminate_manifest(self, mf, fake_root, capsys):
        output = fake_root / "release" / "build" / "release-manifest.json"
        rc = mf.main(
            [
                "--project-root",
                str(fake_root),
                "--bundle-dir",
                str(fake_root / "release" / "build"),
                "--dist-dir",
                str(fake_root / "dist"),
                "--output",
                str(output),
                "--emit-compose-env",
            ]
        )
        assert rc == 0
        manifest = json.loads(output.read_text(encoding="utf-8"))
        assert manifest["verdict"] == "INDETERMINATE"
        assert manifest["approver"] is None
        assert len(manifest["artifacts"]) == 7
        # schema 真校验（生成器自校验后的产物再独立复核）
        assert mf.validate_manifest(manifest, _SCHEMA_PATH) == []
        # evidence 完整 + 默认无片段的门为 NOT_RUN
        by_gate = {}
        for entry in manifest["evidence"]:
            by_gate.setdefault(entry["gate"], []).append(entry["status"])
        for gate in ("G0", "G2", "G3", "G6", "G7", "G8"):
            assert by_gate[gate] == ["NOT_RUN"]
        # compose env 渲染
        env_text = (fake_root / "deploy" / "compose-release.env").read_text(
            encoding="utf-8"
        )
        assert manifest["compose"]["backend_digest"].split("sha256:")[-1] in env_text

    def test_drill_unsigned_records_indeterminate(self, mf, fake_root):
        """windows 签名记录改 drill unsigned → manifest 仍 INDETERMINATE 不可 CERTIFIED。"""
        bundle = fake_root / "release" / "build"
        payload = json.loads(
            (bundle / "signing-digests-windows.json").read_text(encoding="utf-8")
        )
        payload["mode"] = "drill"
        for record in payload["records"]:
            record["signature"]["status"] = "unsigned"
            record["signature"]["signed_sha256"] = None
        (bundle / "signing-digests-windows.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

        output = bundle / "release-manifest.json"
        rc = mf.main(
            [
                "--project-root",
                str(fake_root),
                "--bundle-dir",
                str(bundle),
                "--dist-dir",
                str(fake_root / "dist"),
                "--output",
                str(output),
            ]
        )
        assert rc == 0
        manifest = json.loads(output.read_text(encoding="utf-8"))
        assert manifest["verdict"] == "INDETERMINATE"
        g9 = [e for e in manifest["evidence"] if e["gate"] == "G9"]
        assert any(e["status"] == "INDETERMINATE" for e in g9)
        assert mf.validate_manifest(manifest, _SCHEMA_PATH) == []
