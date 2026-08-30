"""W2 构建脚本与 spec 的源码契约（release-artifact-equivalence-gate task .4）。

锚定 fail-closed 行为的静态契约：release 模式存在且语义正确（工具缺失即败、
唯一前端构建消费、发布身份嵌入、Windows 版本资源）。脚本行为级验证由
release-gate.yml 的 w2 严格构建 job 与本地 E2E 承担。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relpath: str) -> str:
    return (_REPO_ROOT / relpath).read_text(encoding="utf-8")


class TestBuildLinuxScript:
    PATH = "deploy/build-linux.sh"

    def test_release_mode_flag(self):
        text = _read(self.PATH)
        assert "--release) RELEASE_MODE=1" in text
        assert "mode: $([ \"$RELEASE_MODE\" = \"1\" ] && echo RELEASE || echo dev)" in text

    def test_fpm_required_in_release(self):
        text = _read(self.PATH)
        assert "release 模式要求 fpm" in text

    def test_consumes_single_frontend_build(self):
        text = _read(self.PATH)
        assert "release/build/frontend/frontend-asset-manifest.json" in text
        assert "禁止在制品构建中重建前端" in text

    def test_generates_identity_and_embeds_in_package(self):
        text = _read(self.PATH)
        assert "--artifact-kind linux-binary" in text
        assert 'cp "${STAGING_DIR}/build-info.json"' in text
        assert '"${PKG_STAGING}${INSTALL_DIR}/"' in text

    def test_version_consistency_gate(self):
        assert "--check-versions" in _read(self.PATH)

    def test_two_step_dependency_install(self):
        """锁哈希校验 + 增量两段安装（W2：锁内 --hash 会激活 pip 哈希模式）。"""
        text = _read(self.PATH)
        assert "--require-hashes -r" in text
        assert 'requirements-lock.txt' in text
        assert "-r \"$PACKAGE_REQUIREMENTS\"" in text


class TestBuildWindowsScript:
    PATH = "deploy/build-windows.bat"

    def test_release_mode_flag(self):
        text = _read(self.PATH)
        assert '--release" set "RELEASE_MODE=1"' in text

    def test_iscc_required_in_release(self):
        text = _read(self.PATH)
        assert "release 模式要求 Inno Setup ISCC" in text

    def test_inno_failure_fatal_in_release(self):
        text = _read(self.PATH)
        assert "Inno Setup build failed in release mode - failing the build" in text

    def test_consumes_single_frontend_build(self):
        text = _read(self.PATH)
        assert "check_prebuilt_frontend.py" in text
        assert r"release 模式要求先运行 python scripts\release\build_frontend.py" in text

    def test_generates_identity(self):
        text = _read(self.PATH)
        assert "--artifact-kind windows-exe" in text
        assert "generate_build_info.py" in text


class TestSpecFiles:
    LINUX = "deploy/btdeck.spec"
    WINDOWS = "deploy/btdeck-windows.spec"

    def test_linux_spec_embeds_identity(self):
        text = _read(self.LINUX)
        assert "BTDECK_RELEASE_STAGING" in text
        assert "_staged('build-info.json')" in text
        assert "_staged('source-manifest.json')" in text
        assert "_staged('frontend-asset-manifest.json')" in text

    def test_windows_spec_embeds_identity(self):
        text = _read(self.WINDOWS)
        assert "BTDECK_RELEASE_STAGING" in text
        assert "_staged('build-info.json')" in text

    def test_windows_spec_has_version_resource(self):
        text = _read(self.WINDOWS)
        assert "VSVersionInfo" in text
        assert "VERSION_RESOURCE" in text
        assert "version=VERSION_RESOURCE" in text
        assert "git_sha=" in text  # 备注字段携带完整 SHA


class TestBuildImagesScript:
    PATH = "build-images.sh"

    def test_release_mode_and_unique_frontend(self):
        text = _read(self.PATH)
        assert "--release) RELEASE_MODE=1" in text
        assert "Dockerfile.release" in text
        assert "check_prebuilt_frontend.py" in text

    def test_identity_generation_and_label_verification(self):
        text = _read(self.PATH)
        assert "--artifact-kind docker-backend" in text or "generate_identity docker-backend" in text
        assert "generate_identity docker-backend" in text
        assert "generate_identity docker-frontend" in text
        assert "org.opencontainers.image.revision" in text
        assert "OCI label 校验失败" in text

    def test_build_info_copied_into_contexts(self):
        text = _read(self.PATH)
        assert "backend/build-info.json" in text
        assert "frontend-ctx" in text


class TestDockerfiles:
    def test_release_dockerfile_consumes_prebuilt_dist(self):
        text = _read("frontend/Dockerfile.release")
        assert "COPY dist/ /usr/share/nginx/html/" in text
        assert "COPY build-info.json /usr/share/nginx/html/build-info.json" in text
        assert "nginx:1.25-alpine@sha256:" in text

    def test_backend_dockerfile_copies_build_info(self):
        text = _read("backend/Dockerfile")
        assert "COPY --chown=appuser:appgroup build-info.json /app/build-info.json" in text

    def test_prod_dockerfile_copies_build_info(self):
        text = _read("frontend/Dockerfile.prod")
        assert "COPY build-info.json /usr/share/nginx/html/build-info.json" in text


class TestBundleVerifier:
    def test_bundle_verifier_exists_with_gates(self):
        text = _read("scripts/release/verify_release_bundle.py")
        assert "compare_identities" in text
        assert "compare_frontend_manifests" in text
        assert "gate-report.json" in text
        assert "checksums.txt" in text
