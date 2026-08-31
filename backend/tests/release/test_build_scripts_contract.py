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
        assert 'mode: $([ "$RELEASE_MODE" = "1" ] && echo RELEASE || echo dev)' in text

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
        assert "requirements-lock.txt" in text
        assert '-r "$PACKAGE_REQUIREMENTS"' in text

    def test_package_build_info_retagged_per_kind(self):
        """包内 build-info 按包型 retag（计划 §158：kind 枚举不含 linux-binary）。

        二进制内嵌身份保持 linux-binary 中间制品语义；DEB/RPM 包内 json 的
        artifact_kind 分别改写为 linux-deb/linux-rpm（W3 生命周期断言包型身份）。
        就地单字段改写而非重跑 generator（重跑会重算 build_id 造成身份漂移）。
        """
        text = _read(self.PATH)
        assert "retag_build_info linux-deb" in text, "DEB 打包前未 retag 包内身份"
        assert "retag_build_info linux-rpm" in text, "RPM 打包前未 retag 包内身份"
        # deb retag 必须先于 deb fpm，rpm retag 先于 rpm fpm
        assert text.index("retag_build_info linux-deb") < text.index("-t deb")
        assert text.index("retag_build_info linux-rpm") < text.index("-t rpm")

    def test_retag_snippet_chained_and_fail_closed(self, tmp_path):
        """retag heredoc 片段行为级验证：链式 retag（binary→deb→rpm）幂等、
        非 kind 字段逐字节保留、未知源 kind fail-closed。"""
        import json
        import re
        import subprocess
        import sys

        text = _read(self.PATH)
        m = re.search(r"<<'PYEOF'[^\n]*\n(.*?)\nPYEOF", text, re.S)
        assert m, "retag heredoc 缺失"
        snippet = m.group(1)

        src = {
            "schema_version": 1,
            "product_version": "1.0.6",
            "git_sha": "a" * 40,
            "build_id": "ci-123",
            "artifact_kind": "linux-binary",
            "dirty": False,
        }
        target = tmp_path / "build-info.json"
        target.write_text(json.dumps(src, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        for kind in ("linux-deb", "linux-rpm"):  # 模拟 build-linux.sh 真实调用序
            r = subprocess.run(
                [sys.executable, "-c", snippet, kind, str(target)],
                capture_output=True,
                text=True,
            )
            assert r.returncode == 0, r.stderr
            after = json.loads(target.read_text(encoding="utf-8"))
            assert after["artifact_kind"] == kind
            assert {k: v for k, v in after.items() if k != "artifact_kind"} == {
                k: v for k, v in src.items() if k != "artifact_kind"
            }, "retag 漂移了非 kind 字段"

        # fail-closed：未知源 kind 拒绝改写
        target.write_text(json.dumps(dict(src, artifact_kind="windows-exe")), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-c", snippet, "linux-deb", str(target)],
            capture_output=True,
            text=True,
        )
        assert r.returncode != 0 and "retag 源 kind 异常" in r.stderr


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

    def test_nssm_service_forces_server_mode(self):
        """服务形态必须强制服务端模式（W3 CI 第九轮实测拦截）。

        NSSM 启动的进程 SESSIONNAME 不一定是 "services"，desktop_main 的
        桌面分支判定会误入 GUI 启动器——无头环境卡死、端口永不监听。
        服务输出必须落盘（AppStdout/AppStderr）：服务会话无控制台，不落盘
        则启动失败无从诊断（W3 CI 第十一轮实测：服务 Running 端口不监听）。
        """
        iss = _read("deploy/btdeck.iss")
        assert (
            "AppEnvironmentExtra" in iss and "BTDECK_DESKTOP_WINDOW=0" in iss
        ), "btdeck.iss 的 NSSM 服务未注入 BTDECK_DESKTOP_WINDOW=0（服务禁止弹桌面窗口）"
        for nssm_key in ("AppStdout", "AppStderr", "AppRotateFiles"):
            assert nssm_key in iss, f"btdeck.iss 的 NSSM 未配置 {nssm_key}（服务日志落盘）"
        ps1 = _read("scripts/release/lifecycle/windows.ps1")
        assert (
            '$env:BTDECK_DESKTOP_WINDOW = "0"' in ps1
        ), "windows.ps1 未强制 EXE 服务端模式（CI 用户态会话会触发 GUI 启动器卡死）"
        assert (
            '$env:PYTHONIOENCODING = "utf-8"' in ps1
        ), "windows.ps1 未设 PYTHONIOENCODING（v1.0.5 冻结夹具的中文 print 在 cp1252 崩）"

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
