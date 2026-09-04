"""W5 批次 E 门禁汇聚器回归（release-artifact-equivalence-gate task .9 / G10 汇聚）。

覆盖：片段 schema 真校验、G6/G7/G8/G9/G10 推导器（含坏证据/空文件 INDETERMINATE 语义）、
片段优先于推导、G2 锁存在性交叉、聚合 verdict 三态（CERTIFIED 需全 PASS+manifest
CERTIFIED+approver）、发布摘要渲染、端到端 main（本地夹具全链）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "scripts" / "release" / "aggregate_gate_report.py"
_FRAGMENT_SCHEMA = _REPO_ROOT / "release" / "schemas" / "gate-fragment.schema.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("btdeck_aggregate_gate", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def agg():
    return _load_module()


def _fragment(gate, status="PASS", **extra):
    fragment = {
        "gate": gate,
        "status": status,
        "generated_at": "2026-09-03T00:00:00+00:00",
        "summary": "test",
    }
    fragment.update(extra)
    return fragment


def _gate_report(**gates):
    return {"gates": dict(gates)}


def _manifest(verdict="INDETERMINATE", approver=None):
    return {
        "verdict": verdict,
        "approver": approver,
        "product_version": "1.0.6",
        "git_tag": "v1.0.6",
        "git_sha": "a" * 40,
        "artifacts": [{"kind": "linux-deb"} for _ in range(7)],
    }


def _lifecycle_reports(**by_name):
    return {name: (verdict, None) for name, verdict in by_name.items()}


# ---------------------------------------------------------------- 片段加载与校验


class TestFragments:
    def test_valid_fragment_passes_schema(self, agg, tmp_path):
        frag_dir = tmp_path / "gate-fragments"
        frag_dir.mkdir()
        (frag_dir / "G0.json").write_text(json.dumps(_fragment("G0")), encoding="utf-8")
        fragments, problems = agg.load_fragments(frag_dir, _FRAGMENT_SCHEMA)
        assert problems == []
        assert fragments["G0"]["status"] == "PASS"

    def test_bad_status_rejected(self, agg, tmp_path):
        frag_dir = tmp_path / "gate-fragments"
        frag_dir.mkdir()
        (frag_dir / "G0.json").write_text(
            json.dumps(_fragment("G0", status="WEIRD")), encoding="utf-8"
        )
        fragments, problems = agg.load_fragments(frag_dir, _FRAGMENT_SCHEMA)
        assert "G0" not in fragments
        assert problems

    def test_extra_key_schema_violation(self, agg, tmp_path):
        frag_dir = tmp_path / "gate-fragments"
        frag_dir.mkdir()
        (frag_dir / "G2.json").write_text(
            json.dumps(_fragment("G2", sneaky="x")), encoding="utf-8"
        )
        _, problems = agg.load_fragments(frag_dir, _FRAGMENT_SCHEMA)
        assert any("schema" in p for p in problems)

    def test_empty_fragment_file_is_problem(self, agg, tmp_path):
        frag_dir = tmp_path / "gate-fragments"
        frag_dir.mkdir()
        (frag_dir / "G0.json").write_text("", encoding="utf-8")
        fragments, problems = agg.load_fragments(frag_dir, _FRAGMENT_SCHEMA)
        assert fragments == {}
        assert any("坏文件" in p for p in problems)

    def test_missing_dir_is_silent(self, agg, tmp_path):
        fragments, problems = agg.load_fragments(tmp_path / "nope", _FRAGMENT_SCHEMA)
        assert fragments == {} and problems == []


class TestLoadLeadingJson:
    """compare-report.json 是 compare_snapshots stdout 的 tee 产物：JSON 报告
    之后跟 verdict:/[WARN] 行（run 33868276532 实证 Extra data）——首文档解析。"""

    def test_tee_output_with_trailing_lines(self, agg, tmp_path):
        path = tmp_path / "compare-report.json"
        path.write_text(
            '{"candidates": {"rpm": {"total_diffs": 0, "unexplained": []}}}\n'
            "[WARN] 1 条规则未命中任何差异\nverdict: OK\n",
            encoding="utf-8",
        )
        payload, problem = agg.load_leading_json(path)
        assert problem is None
        assert payload["candidates"]["rpm"]["unexplained"] == []

    def test_clean_json_also_works(self, agg, tmp_path):
        path = tmp_path / "x.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        payload, problem = agg.load_leading_json(path)
        assert problem is None and payload == {"a": 1}

    def test_garbage_is_problem(self, agg, tmp_path):
        path = tmp_path / "x.json"
        path.write_text("not json at all", encoding="utf-8")
        payload, problem = agg.load_leading_json(path)
        assert payload is None and problem

    def test_missing_file_silent(self, agg, tmp_path):
        payload, problem = agg.load_leading_json(tmp_path / "nope.json")
        assert payload is None and problem is None


# ---------------------------------------------------------------- 推导器（纯）


class TestDeriveLifecycle:
    def test_g6_all_pass(self, agg):
        reports = _lifecycle_reports(
            **{
                "lifecycle-deb-fresh": "PASS",
                "lifecycle-deb-upgrade": "PASS",
                "lifecycle-rpm-fresh": "PASS",
                "w3-lifecycle-windows.json": "PASS",
            }
        )
        assert agg.derive_g6(reports) == "PASS"

    def test_g6_any_fail(self, agg):
        reports = _lifecycle_reports(
            **{
                "lifecycle-deb-fresh": "PASS",
                "lifecycle-deb-upgrade": "FAIL",
            }
        )
        assert agg.derive_g6(reports) == "FAIL"

    def test_g6_empty_report_file_indeterminate(self, agg):
        """w3 抽取失败会 cp /dev/null——坏证据=INDETERMINATE 而非静默 NOT_RUN。"""
        reports = {
            "lifecycle-deb-fresh": ("PASS", None),
            "lifecycle-deb-upgrade": (None, "证据不可解析（empty）"),
        }
        assert agg.derive_g6(reports) == "INDETERMINATE"

    def test_g6_docker_excluded(self, agg):
        reports = _lifecycle_reports(**{"lifecycle-docker.json": "FAIL"})
        assert agg.derive_g6(reports) == "NOT_RUN"

    def test_g7_docker_verdict(self, agg):
        assert (
            agg.derive_g7(_lifecycle_reports(**{"lifecycle-docker.json": "PASS"}))
            == "PASS"
        )
        assert (
            agg.derive_g7(_lifecycle_reports(**{"lifecycle-docker.json": "FAIL"}))
            == "FAIL"
        )
        assert agg.derive_g7({}) == "NOT_RUN"
        assert (
            agg.derive_g7({"lifecycle-docker.json": (None, "bad")}) == "INDETERMINATE"
        )


class TestDeriveG8:
    def _compare(self, unexplained_a=0, unexplained_b=0):
        return {
            "candidates": {
                "rpm": {
                    "total_diffs": 0,
                    "unexplained": [] if not unexplained_a else ["x"],
                },
                "docker": {
                    "total_diffs": 0,
                    "unexplained": [] if not unexplained_b else ["y"],
                },
            }
        }

    def test_all_explained_pass(self, agg):
        assert agg.derive_g8(self._compare()) == "PASS"

    def test_unexplained_fail(self, agg):
        assert agg.derive_g8(self._compare(unexplained_b=1)) == "FAIL"

    def test_missing_report_not_run(self, agg):
        assert agg.derive_g8(None) == "NOT_RUN"

    def test_malformed_candidates_indeterminate(self, agg):
        assert agg.derive_g8({"candidates": {}}) == "INDETERMINATE"
        assert (
            agg.derive_g8({"candidates": {"rpm": {"total_diffs": 0}}})
            == "INDETERMINATE"
        )


class TestDeriveG9:
    def test_both_faces_pass(self, agg):
        report = _gate_report(G9_signing="PASS")
        assert agg.derive_g9({"verdict": "PASS"}, report) == "PASS"

    def test_scan_fail(self, agg):
        report = _gate_report(G9_signing="PASS")
        assert agg.derive_g9({"verdict": "FAIL"}, report) == "FAIL"

    def test_signing_indeterminate(self, agg):
        """drill unsigned：G9_signing=INDETERMINATE → G9 归 INDETERMINATE（阻断 CERTIFIED）。"""
        report = _gate_report(G9_signing="INDETERMINATE")
        assert agg.derive_g9({"verdict": "PASS"}, report) == "INDETERMINATE"

    def test_missing_face_indeterminate(self, agg):
        assert agg.derive_g9({"verdict": "PASS"}, _gate_report()) == "INDETERMINATE"
        assert agg.derive_g9(None, _gate_report(G9_signing="PASS")) == "INDETERMINATE"
        assert agg.derive_g9(None, _gate_report()) == "NOT_RUN"


class TestDeriveG10:
    def test_certified_pass(self, agg):
        assert (
            agg.derive_g10(
                _gate_report(G10="PASS"),
                _manifest(verdict="CERTIFIED", approver="alice"),
            )
            == "PASS"
        )

    def test_pending_approval_indeterminate(self, agg):
        """审批未完成（manifest INDETERMINATE）→ G10=INDETERMINATE——「审批完成」是 G10 检查项。"""
        assert (
            agg.derive_g10(_gate_report(G10="PASS"), _manifest(verdict="INDETERMINATE"))
            == "INDETERMINATE"
        )

    def test_rejected_fail(self, agg):
        assert (
            agg.derive_g10(_gate_report(G10="PASS"), _manifest(verdict="REJECTED"))
            == "FAIL"
        )

    def test_verify_fail(self, agg):
        assert (
            agg.derive_g10(_gate_report(G10="FAIL"), _manifest(verdict="CERTIFIED"))
            == "FAIL"
        )

    def test_verify_missing_not_run(self, agg):
        assert agg.derive_g10(_gate_report(), _manifest()) == "NOT_RUN"


# ---------------------------------------------------------------- 汇聚与 verdict


def _full_states(agg, **overrides):
    reports = _lifecycle_reports(
        **{
            "lifecycle-deb-fresh": "PASS",
            "lifecycle-rpm-fresh": "PASS",
            "w3-lifecycle-windows.json": "PASS",
            "lifecycle-docker.json": "PASS",
        }
    )
    fragments = {
        "G0": _fragment("G0"),
        "G2": _fragment("G2"),
        "G3": _fragment("G3"),
    }
    gate_states, problems = agg.collect_gate_states(
        fragments,
        _gate_report(G1="PASS", G4="PASS", G5="PASS", G9_signing="PASS", G10="PASS"),
        _manifest(verdict="CERTIFIED", approver="alice"),
        reports,
        {"candidates": {"rpm": {"total_diffs": 0, "unexplained": []}}},
        {"verdict": "PASS"},
        lock_exists=True,
    )
    gate_states.update(overrides)
    return gate_states, problems


class TestCollect:
    def test_fragment_overrides_derived(self, agg):
        """显式片段优先：G1 片段 FAIL 时即使 gate-report 说 PASS 也以片段为准。"""
        fragments = {"G1": _fragment("G1", status="FAIL")}
        states, _ = agg.collect_gate_states(
            fragments,
            _gate_report(G1="PASS"),
            _manifest(),
            {},
            None,
            None,
            lock_exists=True,
        )
        assert states["G1"]["status"] == "FAIL"
        assert "fragment" in states["G1"]["source"]

    def test_missing_fragment_gates_not_run(self, agg):
        states, _ = agg.collect_gate_states(
            {}, None, None, {}, None, None, lock_exists=True
        )
        for gate in ("G0", "G2", "G3"):
            assert states[gate]["status"] == "NOT_RUN"

    def test_g2_pass_without_lock_fail_closed(self, agg):
        fragments = {"G2": _fragment("G2", status="PASS")}
        states, problems = agg.collect_gate_states(
            fragments, None, None, {}, None, None, lock_exists=False
        )
        assert states["G2"]["status"] == "FAIL"
        assert any("requirements-lock" in p for p in problems)


class TestAggregateVerdict:
    def test_all_pass_with_approval_certified(self, agg):
        states, problems = _full_states(agg)
        assert problems == []
        assert (
            agg.compute_aggregate_verdict(
                states, _manifest(verdict="CERTIFIED", approver="alice")
            )
            == "CERTIFIED"
        )

    def test_all_pass_without_approval_indeterminate(self, agg):
        states, _ = _full_states(agg)
        assert (
            agg.compute_aggregate_verdict(states, _manifest(verdict="INDETERMINATE"))
            == "INDETERMINATE"
        )
        assert agg.compute_aggregate_verdict(states, None) == "INDETERMINATE"

    def test_any_fail_rejected(self, agg):
        states, _ = _full_states(
            agg, G6={"status": "FAIL", "source": "derived", "summary": ""}
        )
        assert (
            agg.compute_aggregate_verdict(
                states, _manifest(verdict="CERTIFIED", approver="a")
            )
            == "REJECTED"
        )

    def test_any_not_run_indeterminate(self, agg):
        states, _ = _full_states(
            agg, G8={"status": "NOT_RUN", "source": "derived", "summary": ""}
        )
        assert (
            agg.compute_aggregate_verdict(
                states, _manifest(verdict="CERTIFIED", approver="a")
            )
            == "INDETERMINATE"
        )

    def test_manifest_rejected_blocks_certified(self, agg):
        """变异：门全绿但 manifest REJECTED（审批人拒绝）→ 不可 CERTIFIED。"""
        states, _ = _full_states(agg)
        assert (
            agg.compute_aggregate_verdict(states, _manifest(verdict="REJECTED"))
            == "INDETERMINATE"
        )


class TestSummary:
    def test_renders_gates_table(self, agg):
        states, _ = _full_states(agg)
        text = agg.render_release_summary(states, _manifest(), "INDETERMINATE")
        assert "| G0 | PASS |" in text
        assert "| G10 |" in text
        assert "INDETERMINATE" in text
        assert "待人工" in text


# ---------------------------------------------------------------- 端到端 main


@pytest.fixture()
def fixture_root(tmp_path):
    """模拟 rc-gate job 汇齐证据后的工作区布局。"""
    bundle = tmp_path / "release" / "build"
    frag_dir = bundle / "gate-fragments"
    frag_dir.mkdir(parents=True)
    for gate in ("G0", "G2", "G3"):
        (frag_dir / f"{gate}.json").write_text(
            json.dumps(_fragment(gate)), encoding="utf-8"
        )

    (bundle / "gate-report.json").write_text(
        json.dumps(
            _gate_report(
                G1="PASS", G4="PASS", G5="PASS", G9_signing="INDETERMINATE", G10="PASS"
            )
        ),
        encoding="utf-8",
    )
    (bundle / "release-manifest.json").write_text(
        json.dumps(_manifest(verdict="INDETERMINATE")), encoding="utf-8"
    )

    w3 = tmp_path / "release" / "evidence" / "w3"
    w3.mkdir(parents=True)
    (w3 / "lifecycle-deb-fresh.json").write_text(
        json.dumps({"verdict": "PASS", "scenario": "deb-fresh"}), encoding="utf-8"
    )
    (w3 / "lifecycle-docker.json").write_text(
        json.dumps({"verdict": "PASS", "scenario": "docker"}), encoding="utf-8"
    )
    (tmp_path / "w3-lifecycle-windows.json").write_text(
        json.dumps({"verdict": "PASS", "scenario": "windows"}), encoding="utf-8"
    )

    w4 = tmp_path / "release" / "evidence" / "w4"
    w4.mkdir(parents=True)
    (w4 / "compare-report.json").write_text(
        json.dumps({"candidates": {"rpm": {"total_diffs": 0, "unexplained": []}}}),
        encoding="utf-8",
    )

    w5 = tmp_path / "release" / "evidence" / "w5"
    w5.mkdir(parents=True)
    (w5 / "security-report.json").write_text(
        json.dumps({"verdict": "PASS"}), encoding="utf-8"
    )

    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "requirements-lock.txt").write_text(
        "# lock\n", encoding="utf-8"
    )
    return tmp_path


class TestMainEndToEnd:
    def test_drill_flow_indeterminate(self, agg, fixture_root):
        """drill 全链：G9_signing=INDETERMINATE（unsigned）→ 聚合 INDETERMINATE，退出 0。"""
        rc = agg.main(["--project-root", str(fixture_root)])
        assert rc == 0
        report = json.loads(
            (fixture_root / "release" / "build" / "gate-report-full.json").read_text(
                encoding="utf-8"
            )
        )
        assert report["verdict"] == "INDETERMINATE"
        assert report["gate_status"]["G9"] == "INDETERMINATE"
        assert report["gate_status"]["G10"] == "INDETERMINATE"  # 审批未完成
        for gate in ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"):
            assert report["gate_status"][gate] == "PASS", gate
        summary = (fixture_root / "release" / "build" / "release-summary.md").read_text(
            encoding="utf-8"
        )
        assert "INDETERMINATE" in summary

    def test_certified_flow(self, agg, fixture_root):
        manifest_path = fixture_root / "release" / "build" / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(verdict="CERTIFIED", approver="alice")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        gate_report_path = fixture_root / "release" / "build" / "gate-report.json"
        gate_report = json.loads(gate_report_path.read_text(encoding="utf-8"))
        gate_report["gates"]["G9_signing"] = "PASS"
        gate_report_path.write_text(json.dumps(gate_report), encoding="utf-8")

        rc = agg.main(["--project-root", str(fixture_root)])
        assert rc == 0
        report = json.loads(
            (fixture_root / "release" / "build" / "gate-report-full.json").read_text(
                encoding="utf-8"
            )
        )
        assert report["verdict"] == "CERTIFIED"

    def test_rejected_flow_nonzero(self, agg, fixture_root):
        w3 = fixture_root / "release" / "evidence" / "w3"
        (w3 / "lifecycle-deb-fresh.json").write_text(
            json.dumps({"verdict": "FAIL"}), encoding="utf-8"
        )
        rc = agg.main(["--project-root", str(fixture_root)])
        assert rc == 1
        report = json.loads(
            (fixture_root / "release" / "build" / "gate-report-full.json").read_text(
                encoding="utf-8"
            )
        )
        assert report["verdict"] == "REJECTED"

    def test_tampered_evidence_problem(self, agg, fixture_root):
        """变异：w3 报告被清空（抽取失败形态）→ INDETERMINATE + problem 记录。"""
        (
            fixture_root / "release" / "evidence" / "w3" / "lifecycle-docker.json"
        ).write_text("", encoding="utf-8")
        rc = agg.main(["--project-root", str(fixture_root)])
        assert rc == 1  # 坏证据=聚合器问题（fail-closed，非静默）
        report = json.loads(
            (fixture_root / "release" / "build" / "gate-report-full.json").read_text(
                encoding="utf-8"
            )
        )
        assert report["gate_status"]["G7"] == "INDETERMINATE"
        assert any("坏文件" in p or "不可解析" in p for p in report["problems"])
