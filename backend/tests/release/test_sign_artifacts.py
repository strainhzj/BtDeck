"""W5 批次 D 签名编排回归（release-artifact-equivalence-gate task .9 / G9 签名面）。

覆盖：BLOCKED 状态机（fail-closed 契约）、drill unsigned 语义、Authenticode
变异检测、docker digest 三级口径解析、cosign v3 命令构造、mock 端到端
（signtool/cosign 执行器注入）。
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SIGN_PATH = _REPO_ROOT / "scripts" / "release" / "sign_artifacts.py"


def _load_sign():
    spec = importlib.util.spec_from_file_location("btdeck_sign_artifacts", _SIGN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sign():
    return _load_sign()


def _proc(rc=0, out="", err=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr=err)


def _write_save_tar(path: Path, digest_hex: str) -> None:
    """构造 docker save OCI layout 形状的 tar（index.json → manifests[0].digest）。"""
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": f"sha256:{digest_hex}",
                "size": 2379,
            }
        ],
    }
    with tarfile.open(path, "w") as tar:
        data = json.dumps(index).encode("utf-8")
        member = tarfile.TarInfo("index.json")
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))


# ---------------------------------------------------------------- 决策（纯函数）


class TestDecideStatus:
    def test_signed_when_credentials_present(self, sign):
        assert sign.decide_target_status("docker", True, False) == sign.STATUS_SIGNED

    def test_blocked_formal_without_credentials(self, sign):
        assert sign.decide_target_status("docker", False, False) == sign.STATUS_BLOCKED

    def test_unsigned_in_drill_without_credentials(self, sign):
        assert sign.decide_target_status("windows", False, True) == sign.STATUS_UNSIGNED

    def test_drill_with_credentials_still_signed(self, sign):
        assert sign.decide_target_status("windows", True, True) == sign.STATUS_SIGNED


class TestAggregateAndExit:
    def test_aggregate_worst_first(self, sign):
        assert (
            sign.aggregate_status([sign.STATUS_SIGNED, sign.STATUS_UNSIGNED])
            == sign.STATUS_UNSIGNED
        )
        assert (
            sign.aggregate_status([sign.STATUS_UNSIGNED, sign.STATUS_BLOCKED])
            == sign.STATUS_BLOCKED
        )
        assert (
            sign.aggregate_status([sign.STATUS_BLOCKED, sign.STATUS_SIGN_FAILED])
            == sign.STATUS_SIGN_FAILED
        )
        assert sign.aggregate_status([sign.STATUS_SIGNED]) == sign.STATUS_SIGNED

    def test_aggregate_empty_raises(self, sign):
        with pytest.raises(sign.SigningError):
            sign.aggregate_status([])

    def test_exit_codes(self, sign):
        assert sign.exit_code_for_status(sign.STATUS_SIGNED) == 0
        assert sign.exit_code_for_status(sign.STATUS_UNSIGNED) == 0
        assert sign.exit_code_for_status(sign.STATUS_BLOCKED) == 2
        assert sign.exit_code_for_status(sign.STATUS_SIGN_FAILED) == 3

    def test_exit_code_unknown_raises(self, sign):
        with pytest.raises(sign.SigningError):
            sign.exit_code_for_status("WEIRD")


# ---------------------------------------------------------------- Authenticode


class TestAuthenticode:
    def test_mutation_check_detects_noop(self, sign):
        problem = sign.check_authenticode_mutated("a" * 64, "a" * 64, "windows-exe")
        assert problem is not None and "未变化" in problem

    def test_mutation_ok_when_changed(self, sign):
        assert (
            sign.check_authenticode_mutated("a" * 64, "b" * 64, "windows-exe") is None
        )

    def test_signtool_cmd_shape(self, sign):
        cmd = sign.build_signtool_cmd(
            Path("C:/mock/signtool.exe"),
            Path("C:/tmp/signing.pfx"),
            "s3cret",
            "http://timestamp.test",
            [Path("dist/btdeck.exe")],
        )
        joined = " ".join(cmd)
        assert "/fd SHA256" in joined
        assert "/tr http://timestamp.test" in joined
        assert "/td SHA256" in joined
        assert str(Path("dist/btdeck.exe")) in joined

    def test_resolve_windows_targets_missing_exe(self, sign, tmp_path):
        with pytest.raises(sign.SigningError):
            sign.resolve_windows_targets(tmp_path, "1.0.6")

    def test_resolve_windows_targets_missing_setup(self, sign, tmp_path):
        (tmp_path / "btdeck.exe").write_bytes(b"exe")
        with pytest.raises(sign.SigningError):
            sign.resolve_windows_targets(tmp_path, "1.0.6")

    def test_resolve_windows_targets_ok(self, sign, tmp_path):
        (tmp_path / "btdeck.exe").write_bytes(b"exe")
        (tmp_path / "BtDeck-v1.0.6-windows-x64-setup.exe").write_bytes(b"setup")
        targets = sign.resolve_windows_targets(tmp_path, "1.0.6")
        assert [kind for kind, _ in targets] == ["windows-exe", "windows-setup"]


class TestBuildInfoStagingFallback:
    """CI run 33755046911 首轮回归：windows job 只有 windows-exe staging，
    回退链缺 windows-exe 时 main 直接 SIGN_FAILED。"""

    def test_windows_only_staging_resolved(self, sign, tmp_path):
        (tmp_path / "windows-exe").mkdir(parents=True)
        path = tmp_path / "windows-exe" / "build-info.json"
        path.write_text("{}", encoding="utf-8")
        assert sign.resolve_build_info_path(tmp_path) == path

    def test_docker_staging_preferred(self, sign, tmp_path):
        (tmp_path / "docker-backend").mkdir(parents=True)
        (tmp_path / "linux-binary").mkdir(parents=True)
        (tmp_path / "windows-exe").mkdir(parents=True)
        for name in ("docker-backend", "linux-binary", "windows-exe"):
            (tmp_path / name / "build-info.json").write_text("{}", encoding="utf-8")
        assert (
            sign.resolve_build_info_path(tmp_path)
            == tmp_path / "docker-backend" / "build-info.json"
        )

    def test_no_staging_raises(self, sign, tmp_path):
        with pytest.raises(sign.SigningError, match="build-info"):
            sign.resolve_build_info_path(tmp_path)


# ---------------------------------------------------------------- docker digest 口径


class TestDockerDigestParsing:
    def test_parse_repo_digest_match(self, sign):
        info = {"RepoDigests": ["btdeck-backend@sha256:" + "ab" * 32]}
        assert sign.parse_repo_digest("btdeck-backend:v1.0.6", info) == "ab" * 32

    def test_parse_repo_digest_no_match(self, sign):
        info = {"RepoDigests": ["other-image@sha256:" + "ab" * 32]}
        assert sign.parse_repo_digest("btdeck-backend:v1.0.6", info) is None

    def test_parse_repo_digest_empty(self, sign):
        assert (
            sign.parse_repo_digest("btdeck-backend:v1.0.6", {"RepoDigests": []}) is None
        )

    def test_parse_descriptor_digest(self, sign):
        info = {"Descriptor": {"Digest": "sha256:" + "cd" * 32}}
        assert sign.parse_descriptor_digest(info) == "cd" * 32

    def test_parse_descriptor_digest_absent(self, sign):
        assert sign.parse_descriptor_digest({}) is None

    def test_manifest_digest_from_save_tar(self, sign, tmp_path):
        tar_path = tmp_path / "image.tar"
        _write_save_tar(tar_path, "ef" * 32)
        assert sign.manifest_digest_from_save_tar(tar_path) == "ef" * 32

    def test_manifest_digest_from_save_tar_invalid(self, sign, tmp_path):
        tar_path = tmp_path / "image.tar"
        _write_save_tar(tar_path, "")  # 空 digest → 非法
        with pytest.raises(sign.SigningError):
            sign.manifest_digest_from_save_tar(tar_path)

    def test_inspect_image_digest_falls_back_to_save(self, sign, tmp_path):
        def runner(cmd, env_extra):
            if cmd[:3] == ["docker", "image", "inspect"]:
                return _proc(out=json.dumps([{"RepoDigests": [], "Size": 12345}]))
            if cmd[:2] == ["docker", "save"]:
                _write_save_tar(Path(cmd[3]), "99" * 32)
                return _proc()
            raise AssertionError(f"unexpected cmd {cmd}")

        digest, source, size = sign.inspect_image_digest(
            "btdeck-backend:v1.0.6", runner, tmp_path
        )
        assert digest == "99" * 32
        assert source == "save-oci"
        assert size == 12345

    def test_inspect_image_digest_repo_preferred(self, sign, tmp_path):
        def runner(cmd, env_extra):
            assert cmd[:3] == ["docker", "image", "inspect"]
            return _proc(
                out=json.dumps(
                    [{"RepoDigests": ["btdeck-backend@sha256:" + "11" * 32], "Size": 1}]
                )
            )

        digest, source, _ = sign.inspect_image_digest(
            "btdeck-backend:v1.0.6", runner, tmp_path
        )
        assert digest == "11" * 32
        assert source == "repo"


# ---------------------------------------------------------------- sign_windows（mock）


def _windows_fixture(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "btdeck.exe").write_bytes(b"fake-exe-bytes")
    (dist / "BtDeck-v1.0.6-windows-x64-setup.exe").write_bytes(b"fake-setup-bytes")
    return dist


def _signtool_runner(mutate=True, verify_rc=0):
    """mock signtool：sign 时按 /p 参数定位目标文件并追加字节（模拟签名改文件）。"""

    def runner(cmd, env_extra):
        if cmd[1] == "verify":
            return _proc(rc=verify_rc)
        assert cmd[1] == "sign"
        pw_index = cmd.index("/p")
        for target in cmd[pw_index + 2 :]:
            if mutate:
                path = Path(target)
                path.write_bytes(path.read_bytes() + b"\x00authenticode")
        return _proc()

    return runner


CREDS = {
    "BTDECK_SIGN_PFX_B64": base64.b64encode(b"fake-pfx").decode(),
    "BTDECK_SIGN_PFX_PASSWORD": "pw",
}


class TestSignWindowsMocked:
    def test_formal_blocked(self, sign, tmp_path):
        dist = _windows_fixture(tmp_path)
        result = sign.sign_windows(
            dist,
            "1.0.6",
            drill=False,
            run_cmd=_signtool_runner(),
            env={},
            timestamp_url="http://t",
            signtool_path=Path("C:/mock/signtool.exe"),
        )
        assert result["status"] == sign.STATUS_BLOCKED
        assert all(
            r["signature"]["status"] == "indeterminate" for r in result["records"]
        )
        assert all(r["pre_sha256"] == r["post_sha256"] for r in result["records"])

    def test_drill_unsigned(self, sign, tmp_path):
        dist = _windows_fixture(tmp_path)
        result = sign.sign_windows(
            dist,
            "1.0.6",
            drill=True,
            run_cmd=_signtool_runner(),
            env={},
            timestamp_url="http://t",
            signtool_path=Path("C:/mock/signtool.exe"),
        )
        assert result["status"] == sign.STATUS_UNSIGNED
        assert all(r["signature"]["status"] == "unsigned" for r in result["records"])

    def test_signed_success(self, sign, tmp_path):
        dist = _windows_fixture(tmp_path)
        result = sign.sign_windows(
            dist,
            "1.0.6",
            drill=False,
            run_cmd=_signtool_runner(mutate=True),
            env=dict(CREDS),
            timestamp_url="http://t",
            signtool_path=Path("C:/mock/signtool.exe"),
        )
        assert result["status"] == sign.STATUS_SIGNED
        for record in result["records"]:
            assert record["pre_sha256"] != record["post_sha256"]
            assert record["signature"]["signed_sha256"] == record["post_sha256"]

    def test_sign_failed_when_verify_fails(self, sign, tmp_path):
        dist = _windows_fixture(tmp_path)
        result = sign.sign_windows(
            dist,
            "1.0.6",
            drill=False,
            run_cmd=_signtool_runner(mutate=True, verify_rc=1),
            env=dict(CREDS),
            timestamp_url="http://t",
            signtool_path=Path("C:/mock/signtool.exe"),
        )
        assert result["status"] == sign.STATUS_SIGN_FAILED
        assert any("verify" in p for p in result["problems"])

    def test_sign_failed_when_no_mutation(self, sign, tmp_path):
        """变异锚点：signtool rc=0 但文件未变 = 签名未真正生效 → SIGN_FAILED。"""
        dist = _windows_fixture(tmp_path)
        result = sign.sign_windows(
            dist,
            "1.0.6",
            drill=False,
            run_cmd=_signtool_runner(mutate=False),
            env=dict(CREDS),
            timestamp_url="http://t",
            signtool_path=Path("C:/mock/signtool.exe"),
        )
        assert result["status"] == sign.STATUS_SIGN_FAILED
        assert any("未变化" in p for p in result["problems"])


# ---------------------------------------------------------------- sign_docker（mock）


def _docker_runner(cosign_behaviour="ok"):
    """mock docker + cosign：inspect 返回无 RepoDigests → save 兜底（digest 由 ref 派生）。"""

    def digest_for(ref):
        return hashlib.sha256(ref.encode()).hexdigest()

    def runner(cmd, env_extra):
        if cmd[:3] == ["docker", "image", "inspect"]:
            return _proc(out=json.dumps([{"RepoDigests": [], "Size": 300000}]))
        if cmd[:2] == ["docker", "save"]:
            _write_save_tar(Path(cmd[3]), digest_for(cmd[-1]))
            return _proc()
        # cosign 二进制调用
        if "sign-blob" in cmd:
            if cosign_behaviour == "fail":
                return _proc(rc=1, err="mock cosign failure")
            bundle = Path(cmd[cmd.index("--bundle") + 1])
            bundle.write_text(json.dumps({"mock": "bundle"}), encoding="utf-8")
            return _proc()
        if "public-key" in cmd:
            return _proc(
                out="-----BEGIN PUBLIC KEY-----\nmock\n-----END PUBLIC KEY-----\n"
            )
        if "verify-blob" in cmd:
            return _proc(rc=0 if cosign_behaviour == "ok" else 1)
        raise AssertionError(f"unexpected cmd {cmd}")

    return runner


COSIGN_CREDS = {
    "BTDECK_COSIGN_KEY_B64": base64.b64encode(b"fake-cosign-key").decode(),
    "BTDECK_COSIGN_PASSWORD": "pw",
}


class TestSignDockerMocked:
    def test_drill_unsigned(self, sign, tmp_path):
        result = sign.sign_docker(
            "1.0.6",
            drill=True,
            run_cmd=_docker_runner(),
            env={},
            tools_path=_REPO_ROOT / "release" / "tool-versions.json",
            bundle_dir=tmp_path,
            work_root=tmp_path,
            cosign_bin=None,
        )
        assert result["status"] == sign.STATUS_UNSIGNED
        kinds = {r["kind"] for r in result["records"]}
        assert kinds == {"docker-backend", "docker-frontend"}
        for record in result["records"]:
            assert record["pre_sha256"] == record["post_sha256"]  # cosign 不改镜像
            assert record["digest_source"] == "save-oci"
            assert record["signature"]["status"] == "unsigned"

    def test_signed_cosign_success(self, sign, tmp_path):
        result = sign.sign_docker(
            "1.0.6",
            drill=False,
            run_cmd=_docker_runner(),
            env=dict(COSIGN_CREDS),
            tools_path=_REPO_ROOT / "release" / "tool-versions.json",
            bundle_dir=tmp_path,
            work_root=tmp_path,
            cosign_bin=Path("cosign-mock"),
        )
        assert result["status"] == sign.STATUS_SIGNED
        assert (tmp_path / "signatures" / "docker-images.sigstore.json").is_file()
        assert (tmp_path / "signatures" / "docker-images.digests.txt").is_file()
        for record in result["records"]:
            assert record["signature"]["status"] == "signed"
            assert record["signature"]["verified"] is True

    def test_sign_failed_when_cosign_fails(self, sign, tmp_path):
        result = sign.sign_docker(
            "1.0.6",
            drill=False,
            run_cmd=_docker_runner(cosign_behaviour="fail"),
            env=dict(COSIGN_CREDS),
            tools_path=_REPO_ROOT / "release" / "tool-versions.json",
            bundle_dir=tmp_path,
            work_root=tmp_path,
            cosign_bin=Path("cosign-mock"),
        )
        assert result["status"] == sign.STATUS_SIGN_FAILED
        assert any("sign-blob" in p for p in result["problems"])

    def test_formal_blocked_without_key(self, sign, tmp_path):
        result = sign.sign_docker(
            "1.0.6",
            drill=False,
            run_cmd=_docker_runner(),
            env={},
            tools_path=_REPO_ROOT / "release" / "tool-versions.json",
            bundle_dir=tmp_path,
            work_root=tmp_path,
            cosign_bin=Path("cosign-mock"),
        )
        assert result["status"] == sign.STATUS_BLOCKED


# ---------------------------------------------------------------- cosign v3 命令构造


class TestCosignCmdShape:
    def test_sign_blob_uses_bundle_not_output_signature(self, sign):
        """v3 契约：签名材料走 --bundle；--output-signature/--tlog-upload 已移除。"""
        cmd = sign.build_cosign_sign_blob_cmd(
            "cosign",
            Path("/keys/cosign.key"),
            Path("/work/digests.txt"),
            Path("/work/b.sigstore.json"),
        )
        joined = " ".join(cmd)
        assert "--bundle" in joined
        assert "--output-signature" not in joined
        assert "--tlog-upload" not in joined
        assert str(Path("/keys/cosign.key")) in joined

    def test_verify_blob_needs_bundle_and_ignore_tlog(self, sign):
        cmd = sign.build_cosign_verify_blob_cmd(
            "cosign",
            Path("/pub/cosign.pub"),
            Path("/work/digests.txt"),
            Path("/work/b.sigstore.json"),
        )
        joined = " ".join(cmd)
        assert "--bundle" in joined
        assert "--insecure-ignore-tlog" in joined
        assert "--signature" not in joined  # v3 无 --signature
