"""W3 生命周期脚本语义回归（release-artifact-equivalence-gate task .5/.6/.7 / G6）。

1. prerm.sh 参数语义（R11 核心）：DEB 字面参数与 RPM 数字参数的升级/卸载分支
   （升级只 stop 不 disable；卸载 stop+disable）——用 PATH 注入 mock systemctl 实测。
2. postrm.sh：purge 清数据；remove/upgrade 无动作。
3. 源码契约：四个驱动/编排器存在且含 fail-closed 标记。
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PKG_SCRIPTS = _REPO_ROOT / "deploy" / "package-scripts"
_LIFECYCLE = _REPO_ROOT / "scripts" / "release" / "lifecycle"


def _resolve_bash() -> str:
    """解析可用的（非 WSL）bash。

    Windows 上 System32\\bash.exe 是 WSL 入口，execvpe 会失败；
    优先 Git-Bash（git-bash 会话设置 EXEPATH），其余常见安装位次之。
    找不到则 skip（不默认通过）。
    """
    if os.name != "nt":
        return "bash"
    candidates = []
    exe_path = os.environ.get("EXEPATH")
    if exe_path:
        candidates.append(Path(exe_path) / "bash.exe")
    found = shutil.which("bash")
    if found and "System32" not in found and "WindowsApps" not in found:
        candidates.append(Path(found))
    for program_files in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        candidates.append(Path(program_files) / "Git" / "bin" / "bash.exe")
    candidates.append(Path(r"E:\Git\bin\bash.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    pytest.skip("未找到可用的 Git-Bash（WSL bash 不可用于 scriptlet 测试）")


def _run_with_mock_systemctl(tmp_path: Path, script: Path, arg: str, *, extra_env=None):
    """构造 mock systemctl/useradd 环境，运行 scriptlet，返回 (exit, mock 调用记录)。

    路径一律 as_posix()：Git-Bash 下反斜杠形式会被 bash 解释为转义。
    """
    calls_file = tmp_path / "calls.log"
    mock_dir = tmp_path / "mockbin"
    mock_dir.mkdir(exist_ok=True)
    mock = f"""#!/bin/bash
echo "{arg or 'manual'} $*" >> {calls_file.as_posix()}
exit 0
"""
    (mock_dir / "systemctl").write_text(mock, encoding="utf-8", newline="\n")
    (mock_dir / "systemctl").chmod(stat.S_IRWXU)
    env = dict(os.environ)
    env["PATH"] = f"{mock_dir.as_posix()}:{env.get('PATH', '')}"
    if extra_env:
        env.update(extra_env)
    argv = [_resolve_bash(), script.as_posix()] + ([arg] if arg != "" else [])
    result = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(tmp_path))
    calls = calls_file.read_text(encoding="utf-8") if calls_file.exists() else ""
    return result.returncode, calls


class TestPrermSemantics:
    SCRIPT = _PKG_SCRIPTS / "prerm.sh"

    @pytest.mark.parametrize("arg", ["upgrade", "deconfigure", "1", "2"])
    def test_upgrade_branch_stops_without_disable(self, tmp_path, arg):
        rc, calls = _run_with_mock_systemctl(tmp_path, self.SCRIPT, arg)
        assert rc == 0
        assert "stop btdeck" in calls
        assert "disable btdeck" not in calls, f"升级参数 {arg} 不得 disable（R11）"

    @pytest.mark.parametrize("arg", ["remove", "0"])
    def test_remove_branch_disables(self, tmp_path, arg):
        rc, calls = _run_with_mock_systemctl(tmp_path, self.SCRIPT, arg)
        assert rc == 0
        assert "stop btdeck" in calls
        assert "disable btdeck" in calls

    def test_empty_arg_conservative_remove(self, tmp_path):
        rc, calls = _run_with_mock_systemctl(tmp_path, self.SCRIPT, "")
        assert rc == 0
        assert "disable btdeck" in calls


class TestPostrmSemantics:
    SCRIPT = _PKG_SCRIPTS / "postrm.sh"

    def test_purge_removes_data(self, tmp_path):
        data = tmp_path / "opt" / "btdeck"
        (data / "config").mkdir(parents=True)
        (data / "data").mkdir(parents=True)
        (data / "config" / "btdeck.env").write_text("SECRET_KEY=x", encoding="utf-8")
        env = dict(os.environ)
        env["BTDECK_PREFIX"] = tmp_path.as_posix()
        result = subprocess.run(
            [_resolve_bash(), str(self.SCRIPT), "purge"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert not (tmp_path / "opt" / "btdeck" / "config").exists()
        assert not (tmp_path / "opt" / "btdeck" / "data").exists()

    @pytest.mark.parametrize("arg", ["remove", "upgrade", "failed-upgrade", "disappear"])
    def test_non_purge_noop(self, tmp_path, arg):
        marker = tmp_path / "opt" / "btdeck" / "config" / "keep.env"
        marker.parent.mkdir(parents=True)
        marker.write_text("SECRET_KEY=x", encoding="utf-8")
        result = subprocess.run(
            [_resolve_bash(), str(self.SCRIPT), arg],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert marker.exists()

    def test_unknown_arg_fails_closed(self, tmp_path):
        result = subprocess.run(
            [_resolve_bash(), str(self.SCRIPT), "mystery"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 1


class TestPostinstContract:
    SCRIPT = _PKG_SCRIPTS / "postinst.sh"

    def test_secret_only_when_missing_and_service_enabled(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        assert "if [ ! -f /opt/btdeck/config/btdeck.env ]" in text
        assert "systemctl enable btdeck" in text
        assert "systemctl is-active --quiet btdeck" in text
        assert "systemctl daemon-reload" in text


class TestBuildLinuxWiring:
    def test_fpm_uses_package_scripts(self):
        text = (_REPO_ROOT / "deploy" / "build-linux.sh").read_text(encoding="utf-8")
        assert 'package-scripts/postinst.sh"' in text
        assert 'package-scripts/prerm.sh"' in text
        assert 'package-scripts/postrm.sh"' in text
        # DEB 有 postrm；RPM 不带（%postun 数字参数不兼容）
        deb_block = text[text.index("-t deb") : text.index("-t rpm")]
        assert "--after-remove" in deb_block
        rpm_block = text[text.index("-t rpm") :]
        assert "--after-remove" not in rpm_block


class TestLifecycleDriversContract:
    def test_deb_driver_scenarios_and_asserts(self):
        text = (_LIFECYCLE / "deb.sh").read_text(encoding="utf-8")
        for marker in (
            "fresh_install",
            "reinstall_same_version",
            "restart_twice",
            "remove_keeps_data",
            "purge_removes_data",
            "v105_to_v106_upgrade",
            "SECRET_KEY 未重置",
            "Alembic 单 head",
            "write_report",
        ):
            assert marker in text, marker

    def test_rpm_driver_scenarios_and_asserts(self):
        text = (_LIFECYCLE / "rpm.sh").read_text(encoding="utf-8")
        for marker in (
            "fresh_install",
            "reinstall_same_version",
            "v105_to_v106_upgrade",
            "remove_keeps_data",
            "R11/RPM",
            "write_report",
        ):
            assert marker in text, marker

    def test_orchestrator_fail_closed(self):
        text = (_LIFECYCLE / "run_deb_rpm.sh").read_text(encoding="utf-8")
        assert "--privileged --cgroupns=host" in text
        assert "w3-debian-sysd" in text and "w3-rocky-sysd" in text
        assert ".release-build-v1.0.5/assets" in text

    def test_docker_driver_scenarios(self):
        text = (_LIFECYCLE / "docker.sh").read_text(encoding="utf-8")
        for marker in (
            "repeat_up_no_recreate",
            "force-recreate",
            "upgrade_to_v106",
            "same_digest_up_no_recreate",
            "down_up_keeps_volume",
            "reconstructed",
            "org.opencontainers.image.revision",
        ):
            assert marker in text, marker

    def test_docker_compose_test_template_pins_images(self):
        text = (_LIFECYCLE / "docker-compose.test.yml").read_text(encoding="utf-8")
        effective = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        assert "must pin explicit version tag" in effective
        assert "latest" not in effective.replace("must pin explicit version tag", "")
        assert "w3life_backend_data" in effective

    def test_windows_driver_scenarios(self):
        text = (_LIFECYCLE / "windows.ps1").read_text(encoding="utf-8")
        for marker in (
            "portable_exe_start_identity",
            "setup_silent_install",
            "setup_same_version_reinstall",
            "upgrade_keeps_secret_and_data",
            "uninstall_removes_program_keeps_data",
        ):
            assert marker in text, marker

    def test_lib_fail_closed_helpers(self):
        text = (_LIFECYCLE / "lib.sh").read_text(encoding="utf-8")
        assert "write_report" in text and "LIFECYCLE_FAILED" in text
        assert "single_port_listener" in text and "alembic_head" in text


class TestV105HealthContract:
    """v1.0.5 冻结制品健康契约（W3 CI 第七轮实测拦截）。

    v1.0.5 的 /health/live 响应为 {"status":"success",...,"data":{"status":"alive"}}，
    无 version/build 字段（version 是 v1.0.6 W1 引入）。四驱动的 v1.0.5 就绪谓词
    必须断言 data.status=alive；等 "version":"1.0.5" 会必然超时（CI 420s 复现）。
    """

    def test_v105_predicates_use_alive(self):
        for name in ("deb.sh", "rpm.sh", "docker.sh", "windows.ps1"):
            text = (_LIFECYCLE / name).read_text(encoding="utf-8")
            code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            assert "1.0.5" in code, f"{name} 未区分 v1.0.5 基线就绪契约"
            # alive 谓词分支必须存在（bash 驱动为转义形态，ps1 为字面形态）
            bash_form = '\\"status\\":\\"alive\\"' in code
            literal_form = '"status":"alive"' in code
            assert bash_form or literal_form, f"{name} 缺 v1.0.5 alive 谓词"

    def test_no_version_105_wait_regression(self):
        # 负向变异拦截：任何驱动恢复 "version":"1.0.5" 等待串即失败
        for name in ("deb.sh", "rpm.sh", "docker.sh", "windows.ps1"):
            text = (_LIFECYCLE / name).read_text(encoding="utf-8")
            assert (
                '\\"version\\":\\"1.0.5\\"' not in text and '"version":"1.0.5"' not in text
            ), f"{name} 出现 v1.0.5 version 等待串（v1.0.5 响应无该字段，必然超时）"

    def test_windows_predicates_compact_json(self):
        # 健康接口是紧凑 JSON（无空格分隔符）；带空格的 -match 串永远不命中（CI 实测）
        text = (_LIFECYCLE / "windows.ps1").read_text(encoding="utf-8")
        code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
        joined = "\n".join(code)
        for spaced in ('\'"version": "', '\'"status": "', '\'"build": {'):
            assert spaced not in joined, f"ps1 存在带空格匹配串 {spaced}（紧凑 JSON 不命中）"


class TestSysdFixturePython3:
    """run_deb_rpm.sh 两分支的 systemd 夹具镜像必须预装 python3。

    build_info_field 用容器内 python3 提取包内身份；SKIP_MIRROR 分支曾漏装
    导致断言静默回退 'ERR'（CI 第七轮实测：deb=ERR vs rpm=linux-binary 双症状）。
    """

    def test_both_branches_debian_has_python3(self):
        text = (_LIFECYCLE / "run_deb_rpm.sh").read_text(encoding="utf-8")
        debian_blocks = text.split("build_one w3-debian-sysd <<'EOF'")[1:]
        assert len(debian_blocks) == 2, "预期镜像/官方源两个 debian 夹具分支"
        for i, block in enumerate(debian_blocks):
            block = block.split("EOF")[0]
            assert "python3" in block, f"debian 夹具分支 {i + 1} 未安装 python3"
