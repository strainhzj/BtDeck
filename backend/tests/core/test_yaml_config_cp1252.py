"""yamlConfig 编码安全回归（release-artifact-equivalence-gate W3 CI 第十轮拦截）。

西文 Windows/CI runner 的控制台默认 cp1252：首启无 config.yaml 的正常路径上，
旧实现的中文 print 触发 UnicodeEncodeError 直接崩溃启动链（EXE 场景 A 实测，
异常从 yamlConfig.load 一路上抛到 desktop_main 模块导入）。消息必须走 logging，
且 desktop_main 入口需在 app.* 导入前重配置标准流兜底。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_yaml_config_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("btdeck_yaml_config_under_test", _REPO_ROOT / "app" / "yamlConfig.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestYamlConfigEncodingSafety:
    def test_load_missing_file_never_prints(self, capsys):
        """缺配置文件（首启正常路径）不得向 stdout print——logging 输出走 stderr。"""
        module = _load_yaml_config_module()
        instance = module.Yaml(config_path=str(_REPO_ROOT / "nonexistent-ci-fixture.yaml"))
        assert instance.load() is False
        captured = capsys.readouterr()
        assert captured.out == "", "yamlConfig.load 不得 print（cp1252 控制台会崩溃启动链）"

    def test_load_missing_file_survives_cp1252_subprocess(self, tmp_path):
        """行为级：子进程 stdout 强制 cp1252 时，加载缺失配置不得崩溃。

        复现 CI 形态（Windows runner 控制台 cp1252）：旧实现的中文 print
        在该环境下抛 UnicodeEncodeError 并沿模块导入链上抛。
        """
        probe = tmp_path / "probe.py"
        probe.write_text(
            "import sys\n"
            "from app.yamlConfig import Yaml\n"
            "y = Yaml(config_path=r'%s')\n"
            "ok = y.load()\n"
            "sys.exit(0 if ok is False else 3)\n" % (tmp_path / "missing.yaml"),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-X", "utf8=0", str(probe)],
            capture_output=True,
            text=True,
            encoding="cp1252",
            errors="replace",
            cwd=str(_REPO_ROOT),
            env={
                "PYTHONIOENCODING": "cp1252",
                "PYTHONPATH": str(_REPO_ROOT),
                "PATH": "",
                "SYSTEMROOT": "C:\\Windows",
            },
        )
        assert result.returncode == 0, (
            f"cp1252 环境加载缺失配置崩溃：rc={result.returncode} " f"stderr={result.stderr[-500:]}"
        )

    def test_desktop_main_reconfigures_streams_before_app_imports(self):
        """desktop_main 必须在首个 app.* 导入之前重配置标准流（入口兜底）。"""
        text = (_REPO_ROOT / "app" / "desktop_main.py").read_text(encoding="utf-8")
        reconfigure_pos = text.index("reconfigure")
        first_app_import_pos = text.index("from app.")
        assert reconfigure_pos < first_app_import_pos, (
            "desktop_main 的 stdout/stderr reconfigure 必须先于 app.* 导入"
            "（导入链会触发 yamlConfig.load 的中文消息）"
        )
