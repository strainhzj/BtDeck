"""W5 批次 D bundle 验证器 G9/G10 扩展回归（release-artifact-equivalence-gate task .9）。

覆盖：签名记录状态机校验（formal fail-closed / drill unsigned 合法 / 签名后篡改检测）、
manifest digest 闭环（篡改检测核心）、compose 模板 digest-only 校验（真实仓库模板锚定 +
latest/裸 tag 负向变异）、CERTIFIED 断言链。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_VERIFY_PATH = _REPO_ROOT / "scripts" / "release" / "verify_release_bundle.py"
_REAL_TEMPLATE = _REPO_ROOT / "deploy" / "docker-compose.release.yml"


def _load_verify():
    spec = importlib.util.spec_from_file_location(
        "btdeck_verify_bundle_w5", _VERIFY_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verify():
    return _load_verify()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _record(
    kind, status="SIGNED", mode="formal", path=None, post=None, sig_status="signed"
):
    return {
        "kind": kind,
        "status": status,
        "_mode": mode,
        "path": path or f"dist/{kind}",
        "post_sha256": post or _sha(kind.encode()),
        "signature": {"mechanism": "cosign", "status": sig_status},
    }


def _full_records(**overrides):
    records = {kind: _record(kind) for kind in verify4_kinds()}
    records.update(overrides)
    return records


def verify4_kinds():
    return ("windows-exe", "windows-setup", "docker-backend", "docker-frontend")


# ---------------------------------------------------------------- 签名记录合并与校验


class TestMergeSigningRecords:
    def test_mode_injected(self, verify, tmp_path):
        (tmp_path / "signing-digests-docker.json").write_text(
            json.dumps({"mode": "drill", "records": [{"kind": "docker-backend"}]}),
            encoding="utf-8",
        )
        records = verify.merge_signing_records(tmp_path)
        assert records["docker-backend"]["_mode"] == "drill"

    def test_empty(self, verify, tmp_path):
        assert verify.merge_signing_records(tmp_path) == {}


class TestCompareSigningRecords:
    def test_all_formal_signed_ok(self, verify, tmp_path):
        records = _full_records()
        for kind in ("windows-exe", "windows-setup"):
            target = tmp_path / "dist" / kind
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(kind.encode())
            records[kind]["path"] = str(target)
        assert verify.compare_signing_records(records, tmp_path) == []

    def test_formal_unsigned_is_problem(self, verify, tmp_path):
        records = _full_records(
            **{
                "docker-backend": _record(
                    "docker-backend",
                    status="unsigned",
                    mode="formal",
                    sig_status="unsigned",
                )
            }
        )
        problems = verify.compare_signing_records(records, tmp_path)
        assert any("正式模式签名未完成" in p for p in problems)

    def test_blocked_is_problem(self, verify, tmp_path):
        records = _full_records(
            **{
                "windows-exe": _record(
                    "windows-exe",
                    status="SIGNING_BLOCKED",
                    mode="formal",
                    sig_status="indeterminate",
                )
            }
        )
        problems = verify.compare_signing_records(records, tmp_path)
        assert any("windows-exe" in p for p in problems)

    def test_drill_unsigned_allowed(self, verify, tmp_path):
        records = _full_records(
            **{
                "windows-exe": _record(
                    "windows-exe",
                    status="unsigned",
                    mode="drill",
                    sig_status="unsigned",
                )
            }
        )
        problems = verify.compare_signing_records(records, tmp_path)
        assert not any("windows-exe" in p for p in problems)

    def test_missing_kind_no_problem(self, verify, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        records = _full_records()
        for kind in ("windows-exe", "windows-setup"):
            target = dist / kind
            target.write_bytes(kind.encode())
            records[kind]["path"] = str(target)
        del records["docker-frontend"]
        assert verify.compare_signing_records(records, tmp_path) == []

    def test_signed_windows_tamper_detected(self, verify, tmp_path):
        """变异：签名后文件被改动 → post_sha256 与实际不一致 → 报红。"""
        target = tmp_path / "dist" / "windows-exe"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"original")
        record = _record("windows-exe", post=_sha(b"original"))
        record["path"] = str(target)
        records = _full_records(**{"windows-exe": record})
        target.write_bytes(b"tampered-after-signing")
        problems = verify.compare_signing_records(records, tmp_path)
        assert any("签名后 digest 与实际文件不一致" in p for p in problems)


class TestSigningGateStatus:
    def test_not_run(self, verify):
        assert verify.signing_gate_status({}) == "NOT_RUN"

    def test_pass_only_when_all_four_signed(self, verify):
        records = _full_records()
        assert verify.signing_gate_status(records) == "PASS"
        del records["windows-setup"]
        assert verify.signing_gate_status(records) == "INDETERMINATE"

    def test_drill_unsigned_indeterminate(self, verify):
        records = _full_records(
            **{
                "windows-setup": _record(
                    "windows-setup",
                    status="unsigned",
                    mode="drill",
                    sig_status="unsigned",
                )
            }
        )
        assert verify.signing_gate_status(records) == "INDETERMINATE"

    def test_blocked_fail(self, verify):
        records = _full_records(
            **{
                "docker-frontend": _record(
                    "docker-frontend",
                    status="SIGN_FAILED",
                    mode="formal",
                    sig_status="indeterminate",
                )
            }
        )
        assert verify.signing_gate_status(records) == "FAIL"


# ---------------------------------------------------------------- manifest digest 闭环


def _manifest(artifacts):
    return {"artifacts": artifacts}


class TestCompareManifestDigests:
    def _file_artifact(self, tmp_path, kind, name, content=b"x"):
        path = tmp_path / name
        path.write_bytes(content)
        return {
            "kind": kind,
            "path": str(path.relative_to(tmp_path)),
            "sha256": _sha(content),
        }

    def test_file_digest_match_ok(self, verify, tmp_path):
        artifacts = [self._file_artifact(tmp_path, "linux-deb", "a.deb")]
        assert verify.compare_manifest_digests(_manifest(artifacts), tmp_path, {}) == []

    def test_tamper_detected(self, verify, tmp_path):
        """G10 核心：篡改制品字节 → manifest digest 不一致 → 报红。"""
        artifact = self._file_artifact(tmp_path, "linux-deb", "a.deb")
        (tmp_path / "a.deb").write_bytes(b"tampered")
        problems = verify.compare_manifest_digests(_manifest([artifact]), tmp_path, {})
        assert any("manifest digest 与实际文件不一致" in p for p in problems)

    def test_missing_file_detected(self, verify, tmp_path):
        artifact = self._file_artifact(tmp_path, "linux-deb", "a.deb")
        (tmp_path / "a.deb").unlink()
        problems = verify.compare_manifest_digests(_manifest([artifact]), tmp_path, {})
        assert any("制品文件缺失" in p for p in problems)

    def test_docker_mismatch_detected(self, verify):
        artifacts = [
            {
                "kind": "docker-backend",
                "path": "btdeck-backend:v1.0.6",
                "sha256": _sha(b"recorded"),
                "digest_ref": "btdeck-backend:v1.0.6@sha256:" + _sha(b"recorded"),
            }
        ]
        records = {"docker-backend": _record("docker-backend", post=_sha(b"different"))}
        problems = verify.compare_manifest_digests(
            _manifest(artifacts), Path("."), records
        )
        assert any("与签名记录不一致" in p for p in problems)

    def test_docker_bad_digest_ref_detected(self, verify):
        artifacts = [
            {
                "kind": "docker-backend",
                "path": "btdeck-backend:v1.0.6",
                "sha256": _sha(b"x"),
                "digest_ref": "btdeck-backend:v1.0.6:latest",
            }
        ]
        records = {"docker-backend": _record("docker-backend", post=_sha(b"x"))}
        problems = verify.compare_manifest_digests(
            _manifest(artifacts), Path("."), records
        )
        assert any("digest_ref 非 digest 固定引用" in p for p in problems)


# ---------------------------------------------------------------- compose 模板


class TestComposeParsing:
    def test_real_repo_template(self, verify):
        images = verify.parse_compose_images(_REAL_TEMPLATE.read_text(encoding="utf-8"))
        services = [service for service, _ in images]
        assert services == ["backend", "frontend"]

    def test_service_scoped(self, verify):
        images = verify.parse_compose_images(
            "services:\n  backend:\n    image: a@sha256:b\n  frontend:\n    image: c\n"
        )
        assert images == [("backend", "a@sha256:b"), ("frontend", "c")]


class TestSubstituteComposeEnv:
    def test_plain_var(self, verify):
        assert (
            verify.substitute_compose_env("x@sha256:${V}", {"V": "ab"})[0]
            == "x@sha256:ab"
        )

    def test_default_when_missing(self, verify):
        assert verify.substitute_compose_env("${TZ:-UTC}", {})[0] == "UTC"

    def test_required_missing_is_problem(self, verify):
        rendered, problems = verify.substitute_compose_env("${REQ:?msg}", {})
        assert problems == ["compose 必填变量未提供：REQ"]
        assert rendered == ""


class TestCheckDigestPinned:
    def test_valid(self, verify):
        assert verify.check_digest_pinned("reg/name@sha256:" + "a" * 64) is None

    def test_latest_rejected(self, verify):
        assert "非 digest 固定引用" in verify.check_digest_pinned("reg/name:latest")

    def test_bare_tag_rejected(self, verify):
        assert "非 digest 固定引用" in verify.check_digest_pinned("reg/name:v1.0.6")


class TestCompareComposeDigests:
    def _compose(self):
        return {
            "backend_digest": "sha256:" + _sha(b"backend"),
            "frontend_digest": "sha256:" + _sha(b"frontend"),
        }

    def test_real_template_consistent(self, verify):
        """真实仓库模板 + 匹配 manifest compose → 无问题（含 env 渲染后 digest-only）。"""
        assert verify.compare_compose_digests(_REAL_TEMPLATE, self._compose()) == []

    def test_template_missing(self, verify, tmp_path):
        problems = verify.compare_compose_digests(
            tmp_path / "nope.yml", self._compose()
        )
        assert any("模板缺失" in p for p in problems)

    def test_latest_template_detected(self, verify, tmp_path):
        template = tmp_path / "compose.yml"
        template.write_text(
            "services:\n  backend:\n    image: reg/btdeck-backend:latest\n"
            "  frontend:\n    image: reg/btdeck-frontend:latest\n",
            encoding="utf-8",
        )
        problems = verify.compare_compose_digests(template, self._compose())
        assert len([p for p in problems if "非 digest 固定引用" in p]) == 2

    def test_digest_mismatch_detected(self, verify, tmp_path):
        """模板固定 digest 与 manifest.compose 不同 → 渲染后不匹配 → 报红。"""
        template = tmp_path / "compose.yml"
        template.write_text(
            "services:\n  backend:\n    image: reg/btdeck-backend@sha256:"
            + _sha(b"template-pinned")
            + "\n"
            "  frontend:\n    image: reg/btdeck-frontend@sha256:"
            + _sha(b"frontend")
            + "\n",
            encoding="utf-8",
        )
        problems = verify.compare_compose_digests(template, self._compose())
        assert any("backend digest 与 manifest 不一致" in p for p in problems)


# ---------------------------------------------------------------- CERTIFIED 断言链


def _certified_manifest(approver="alice", approved_at="2026-09-03T00:00:00+00:00"):
    artifacts = [
        {"kind": kind, "signature": {"status": "signed"}} for kind in verify4_kinds()
    ] + [{"kind": "linux-deb"}, {"kind": "linux-rpm"}, {"kind": "linux-binary"}]
    evidence = [{"gate": f"G{i}", "status": "PASS"} for i in range(11)]
    return {
        "verdict": "CERTIFIED",
        "approver": approver,
        "approved_at": approved_at,
        "artifacts": artifacts,
        "evidence": evidence,
    }


class TestCertifiedChain:
    def test_valid_certified_ok(self, verify):
        assert verify.check_certified_chain(_certified_manifest()) == []

    def test_missing_approver_rejected(self, verify):
        manifest = _certified_manifest(approver=None)
        problems = verify.check_certified_chain(manifest)
        assert any("approver/approved_at 为空" in p for p in problems)

    def test_unsigned_signature_rejected(self, verify):
        manifest = _certified_manifest()
        manifest["artifacts"][0]["signature"]["status"] = "unsigned"
        problems = verify.check_certified_chain(manifest)
        assert any("签名状态=unsigned" in p for p in problems)

    def test_not_run_gate_rejected(self, verify):
        manifest = _certified_manifest()
        manifest["evidence"][0]["status"] = "NOT_RUN"
        problems = verify.check_certified_chain(manifest)
        assert any("G0=NOT_RUN" in p for p in problems)

    def test_non_certified_no_checks(self, verify):
        manifest = _certified_manifest()
        manifest["verdict"] = "INDETERMINATE"
        manifest["approver"] = None
        assert verify.check_certified_chain(manifest) == []
