"""SDK 兼容探针回归与证据锚定（feature mcp-service-capabilities-2026-08-28 W0）。

三层：

1. 纯逻辑：探针脚本的锁定组合常量、证据结构约束；
2. 就地 selfcheck：在当前解释器跑 C1~C4（fastmcp/mcp 未安装时按 flavor 跳过，
   base 环境两者齐备——这是探针检查逻辑本身的回归，不替代锁定组合证据）；
3. 证据锚定：tests/mcp/evidence/ 下已提交的锁定组合证据必须存在、结构完整、
   verdict=PASS；矩阵缺口（3.11/3.12 × 两 SDK 四组合）即红——证据被删除或
   覆盖为 FAIL 时本文件立刻拦截。

选型结论（官方 mcp SDK）与完整矩阵记录在 PLANS/mcp-service-capabilities.md §10.4。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = BACKEND_ROOT / "scripts" / "mcp_sdk_probe.py"
EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"

# 已提交证据矩阵：文件名 → 期望包含的检查项（C5 仅在跑过 --pyinstaller 的证据中）
_EXPECTED_EVIDENCE_MATRIX = {
    "sdk-probe-py3.11-fastmcp-2.14.3.json": ("C1_import", "C4_tools_list"),
    "sdk-probe-py3.11-mcp-1.30.0.json": ("C1_import", "C4_tools_list"),
    "sdk-probe-py3.12-fastmcp-2.14.3.json": ("C1_import", "C4_tools_list", "C5_pyinstaller_onefile"),
    "sdk-probe-py3.12-mcp-1.30.0.json": ("C1_import", "C4_tools_list", "C5_pyinstaller_onefile"),
}

# 整体 verdict 预期：fastmcp py3.12 为 FAIL（C5 onefile 打包摩擦是选型决策证据，
# C1~C4 仍必须全 PASS）；选定的官方 mcp 全 PASS。
_EXPECTED_VERDICTS = {
    "sdk-probe-py3.11-fastmcp-2.14.3.json": "PASS",
    "sdk-probe-py3.11-mcp-1.30.0.json": "PASS",
    "sdk-probe-py3.12-fastmcp-2.14.3.json": "FAIL",
    "sdk-probe-py3.12-mcp-1.30.0.json": "PASS",
}

_REQUIRED_CHECK_STATUSES = {
    "C1_import": "PASS",
    "C2_mount_before_spa_fallback": "PASS",
    "C3_parent_lifespan_runs_once": "PASS",
    "C4_tools_list": "PASS",
    "C4_tools_call_roundtrip": "PASS",
}


def _load_probe():
    spec = importlib.util.spec_from_file_location("btdeck_mcp_sdk_probe", PROBE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestProbeLogic:
    def test_repo_pinned_deps_match_requirements_landscape(self):
        """锁定组合必须锚定仓库 requirements 的关键版本（漂移即红）。"""
        probe = _load_probe()
        deps = " ".join(probe.REPO_PINNED_DEPS)
        assert "fastapi==0.115.6" in deps
        assert "starlette==0.41.3" in deps
        assert "httpx==0.28.1" in deps
        assert "uvicorn==0.35.0" in deps
        # fastmcp 2.14.3 未声明运行时依赖 packaging（py3.12 venv 实测），
        # 仓库已锁 packaging~=24.0，探针必须显式携带防假阴性
        assert "packaging==" in deps

    def test_supported_flavors_cover_both_candidates(self):
        probe = _load_probe()
        assert set(probe.SUPPORTED_SDK_FLAVORS) == {"fastmcp", "mcp"}

    @pytest.mark.parametrize("flavor", ["fastmcp", "mcp"])
    def test_selfcheck_in_current_interpreter(self, flavor):
        """就地 selfcheck：C1~C4 在当前解释器全过（SDK 缺失时跳过该 flavor）。"""
        try:
            importlib.import_module(flavor)
        except ImportError:
            pytest.skip(f"当前解释器未安装 {flavor}，跳过就地检查（锁定组合证据不受影响）")
        proc = subprocess.run(
            [sys.executable, str(PROBE_PATH), "selfcheck", "--sdk", flavor, "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        evidence = json.loads(proc.stdout)
        assert evidence["verdict"] == "PASS", json.dumps(evidence["checks"], ensure_ascii=False)
        statuses = {c["name"]: c["status"] for c in evidence["checks"]}
        for check, expected in _REQUIRED_CHECK_STATUSES.items():
            assert statuses.get(check) == expected, f"{flavor} selfcheck: {check}={statuses.get(check)}"


class TestCommittedEvidence:
    def test_evidence_matrix_complete(self):
        """四份锁定组合证据必须齐备（3.11/3.12 × fastmcp/mcp）。"""
        missing = [name for name in _EXPECTED_EVIDENCE_MATRIX if not (EVIDENCE_DIR / name).is_file()]
        assert not missing, f"SDK 探针证据缺失（须重跑 backend/scripts/mcp_sdk_probe.py）: {missing}"

    @pytest.mark.parametrize("evidence_name", sorted(_EXPECTED_EVIDENCE_MATRIX))
    def test_evidence_passes_required_checks(self, evidence_name):
        """每份证据：C1~C4 全 PASS、锁定版本如实记录、verdict 符合预期。"""
        payload = json.loads((EVIDENCE_DIR / evidence_name).read_text(encoding="utf-8"))
        assert payload["verdict"] == _EXPECTED_VERDICTS[evidence_name], evidence_name
        statuses = {c["name"]: c["status"] for c in payload["checks"]}
        for check, expected in _REQUIRED_CHECK_STATUSES.items():
            assert statuses.get(check) == expected, f"{evidence_name}: {check}={statuses.get(check)}"
        expected_checks = _EXPECTED_EVIDENCE_MATRIX[evidence_name]
        for check in expected_checks:
            assert check in statuses, f"{evidence_name}: 缺少 {check}"
        versions = payload["versions"]
        assert versions["fastapi"] == "0.115.6", f"{evidence_name}: fastapi 版本漂移"
        assert versions["starlette"] == "0.41.3", f"{evidence_name}: starlette 版本漂移"

    def test_selected_sdk_pyinstaller_feasibility(self):
        """选型结论依赖的 C5 证据：官方 mcp 在 py3.12 onefile 零附加参数可行。"""
        payload = json.loads((EVIDENCE_DIR / "sdk-probe-py3.12-mcp-1.30.0.json").read_text(encoding="utf-8"))
        c5 = next(c for c in payload["checks"] if c["name"] == "C5_pyinstaller_onefile")
        assert c5["status"] == "PASS", c5["detail"]

    def test_fastmcp_packaging_friction_recorded(self):
        """对照证据：fastmcp onefile 失败事实必须留存（选型决策可追溯）。"""
        payload = json.loads((EVIDENCE_DIR / "sdk-probe-py3.12-fastmcp-2.14.3.json").read_text(encoding="utf-8"))
        c5 = next((c for c in payload["checks"] if c["name"] == "C5_pyinstaller_onefile"), None)
        # 选型已定官方 SDK；fastmcp C5 允许 FAIL（PackageNotFoundError 是决策依据），
        # 但证据必须存在且记录了失败细节，防止"证据被悄悄改绿"。
        assert c5 is not None and c5["status"] == "FAIL" and c5["detail"]
