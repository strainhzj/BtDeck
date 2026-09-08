"""MCP-G0~G11 门禁骨架回归（feature mcp-service-capabilities-2026-08-28 W0）。

锚定 scripts/release/aggregate_mcp_gates.py + release/schemas/mcp-gate-fragment.schema.json：

- fail-closed 占位语义：空片段目录 → 12 门全 NOT_RUN → verdict=BLOCKED（"NOT_RUN 即红"）；
- schema 加强：PASS 无非空 evidence 即违例（无证据不得宣告通过）；
- 三态裁决：任一 FAIL=REJECTED、任一非 PASS=BLOCKED、全 PASS=READY；
- 门清单与 feature_list.json implementation_gates 单一事实源对齐。

W0 交付时 12 门均无片段——本文件测试的是汇聚器行为（绿），实际门禁状态由
运行汇聚器得出（BLOCKED，红），各波次回填 MCP-G<n>.json 片段才逐门转绿。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "release" / "aggregate_mcp_gates.py"
_SCHEMA_PATH = _REPO_ROOT / "release" / "schemas" / "mcp-gate-fragment.schema.json"
_FEATURE_LIST = _REPO_ROOT / "feature_list.json"
_FEATURE_ID = "mcp-service-capabilities-2026-08-28"


def _load_module():
    spec = importlib.util.spec_from_file_location("btdeck_aggregate_mcp_gates", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def agg():
    return _load_module()


def _fragment(gate, status="PASS", evidence=("tests/mcp/test_contracts.py",)):
    return {
        "gate": gate,
        "status": status,
        "generated_at": "2026-09-08T00:00:00+00:00",
        "summary": "test fragment",
        "evidence": [{"path": p} for p in evidence],
    }


def _write_fragment(directory: Path, gate, status="PASS", evidence=("tests/mcp/test_contracts.py",)):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{gate}.json"
    path.write_text(json.dumps(_fragment(gate, status, evidence), ensure_ascii=False), encoding="utf-8")
    return path


class TestFailClosedPlaceholder:
    def test_empty_dir_is_all_not_run_and_blocked(self, agg, tmp_path: Path):
        """W0 占位核心：无任何片段 → 12×NOT_RUN + BLOCKED（exit≠0 语义）。"""
        report = agg.build_report(tmp_path / "gate-fragments", _SCHEMA_PATH)
        assert set(report["gates"]) == set(agg.MCP_GATES)
        assert set(report["gates"].values()) == {"NOT_RUN"}
        assert report["verdict"] == "BLOCKED"

    def test_canonical_gate_list_matches_feature_list(self, agg):
        """门清单与 feature_list.json 的 12 个 implementation_gates 完全一致。"""
        data = json.loads(_FEATURE_LIST.read_text(encoding="utf-8"))
        feature = next(f for f in data["features"] if f["id"] == _FEATURE_ID)
        feature_gate_ids = [g["id"] for g in feature["implementation_gates"]]
        assert feature_gate_ids == list(agg.MCP_GATES)


class TestSchemaEnforcement:
    def test_schema_rejects_unknown_gate_id(self, agg):
        violations = agg.validate_fragment(_fragment("MCP-G12"), _SCHEMA_PATH)
        assert violations

    def test_schema_rejects_bad_status(self, agg):
        fragment = _fragment("MCP-G0", status="MAYBE")
        violations = agg.validate_fragment(fragment, _SCHEMA_PATH)
        assert violations

    def test_schema_rejects_pass_without_evidence(self, agg):
        """fail-closed 加强：PASS 必须带非空 evidence，无证据不得宣告通过。"""
        fragment = _fragment("MCP-G0", evidence=())
        violations = agg.validate_fragment(fragment, _SCHEMA_PATH)
        assert violations

    def test_schema_accepts_not_run_with_empty_evidence(self, agg):
        fragment = _fragment("MCP-G0", status="NOT_RUN", evidence=())
        assert agg.validate_fragment(fragment, _SCHEMA_PATH) == []


class TestVerdictDerivation:
    def test_fail_fragment_rejected(self, agg, tmp_path: Path):
        _write_fragment(tmp_path, "MCP-G0", status="FAIL", evidence=())
        report = agg.build_report(tmp_path, _SCHEMA_PATH)
        assert report["gates"]["MCP-G0"] == "FAIL"
        assert report["verdict"] == "REJECTED"

    def test_schema_violation_is_indeterminate_not_trusted(self, agg, tmp_path: Path):
        """schema 违例片段的状态不可信：该门 INDETERMINATE，整体 BLOCKED。"""
        _write_fragment(tmp_path, "MCP-G0", status="PASS", evidence=())  # PASS 无证据=违例
        report = agg.build_report(tmp_path, _SCHEMA_PATH)
        assert report["gates"]["MCP-G0"] == "INDETERMINATE"
        assert report["verdict"] == "BLOCKED"
        assert report["problems"]

    def test_bad_json_fragment_recorded_as_problem(self, agg, tmp_path: Path):
        (tmp_path).mkdir(parents=True, exist_ok=True)
        (tmp_path / "MCP-G1.json").write_text("{broken", encoding="utf-8")
        report = agg.build_report(tmp_path, _SCHEMA_PATH)
        assert report["gates"]["MCP-G1"] == "NOT_RUN"
        assert any("MCP-G1.json" in p for p in report["problems"])

    def test_all_pass_reaches_ready(self, agg, tmp_path: Path):
        for gate in agg.MCP_GATES:
            _write_fragment(tmp_path, gate)
        report = agg.build_report(tmp_path, _SCHEMA_PATH)
        assert set(report["gates"].values()) == {"PASS"}
        assert report["verdict"] == "READY"

    def test_partial_pass_still_blocked(self, agg, tmp_path: Path):
        """任一门未回填证据即 BLOCKED——不允许部分证据发布。"""
        _write_fragment(tmp_path, "MCP-G0")
        report = agg.build_report(tmp_path, _SCHEMA_PATH)
        assert report["gates"]["MCP-G0"] == "PASS"
        assert report["verdict"] == "BLOCKED"


class TestCliEndToEnd:
    def test_main_exit_code_follows_verdict(self, tmp_path: Path):
        """CLI exit code：BLOCKED=1（占位即红）、READY=0（仅全 PASS）。"""
        empty = tmp_path / "empty-fragments"
        empty.mkdir()
        proc = subprocess.run(
            [sys.executable, str(_MODULE_PATH), "--fragments-dir", str(empty)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["verdict"] == "BLOCKED"
        assert len(payload["gates"]) == 12
