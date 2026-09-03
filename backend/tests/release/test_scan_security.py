"""W5 安全扫描器回归（release-artifact-equivalence-gate task .9 / G9）。

纯函数层：例外装载校验（四要素/30 天上限/过期/重复编号）、scope 命中
（vuln_id 精确与别名/package 级/target 限定）、grype 聚合去重与最高分级、
阻断策略（Critical 不可豁免变异）、许可证禁用清单。
容器编排层不进单测（CI/本地实证覆盖）。
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCAN_PATH = _REPO_ROOT / "scripts" / "release" / "scan_security.py"
_SBOMGEN_PATH = _REPO_ROOT / "scripts" / "release" / "generate_sbom.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner():
    return _load_module(_SCAN_PATH, "btdeck_scan_security")


@pytest.fixture(scope="module")
def sbomgen():
    return _load_module(_SBOMGEN_PATH, "btdeck_generate_sbom")


def _exception(**kw) -> dict:
    base = {
        "id": "SEC-001",
        "scope": {"vuln_id": "GHSA-xxxx"},
        "justification": "内网部署无暴露面，不可利用（证明链接见工单）",
        "owner": "huangzj",
        "remediation_version": "v1.0.7",
        "registered": date.today().isoformat(),
        "expires": (date.today() + timedelta(days=14)).isoformat(),
    }
    base.update(kw)
    return base


def _finding(
    severity: str = "High", vuln_id: str = "GHSA-xxxx", package: str = "urllib3"
) -> dict:
    return {
        "vuln_id": vuln_id,
        "package": package,
        "version": "2.1.0",
        "severity": severity,
        "fix_versions": [],
        "aliases": [],
        "targets": ["source-backend"],
    }


class TestLoadExceptions:
    def test_valid_exception_loaded(self, scanner, tmp_path):
        p = tmp_path / "exc.json"
        p.write_text(json.dumps({"exceptions": [_exception()]}), encoding="utf-8")
        valid, problems = scanner.load_exceptions(p)
        assert problems == [] and len(valid) == 1

    def test_missing_field_fail_closed(self, scanner, tmp_path):
        bad = _exception()
        bad.pop("owner")
        p = tmp_path / "exc.json"
        p.write_text(json.dumps({"exceptions": [bad]}), encoding="utf-8")
        valid, problems = scanner.load_exceptions(p)
        assert valid == [] and any("owner" in x for x in problems)

    def test_expired_exception_rejected(self, scanner, tmp_path):
        bad = _exception(
            registered=(date.today() - timedelta(days=40)).isoformat(),
            expires=(date.today() - timedelta(days=1)).isoformat(),
        )
        p = tmp_path / "exc.json"
        p.write_text(json.dumps({"exceptions": [bad]}), encoding="utf-8")
        valid, problems = scanner.load_exceptions(p)
        # 登记日+30 天上限或已过期任一命中都必须拒绝（分支顺序无关）
        assert valid == [] and problems != []

    def test_over_30_days_rejected(self, scanner, tmp_path):
        bad = _exception(expires=(date.today() + timedelta(days=31)).isoformat())
        p = tmp_path / "exc.json"
        p.write_text(json.dumps({"exceptions": [bad]}), encoding="utf-8")
        valid, problems = scanner.load_exceptions(p)
        assert valid == [] and any("30" in x for x in problems)

    def test_duplicate_id_rejected(self, scanner, tmp_path):
        p = tmp_path / "exc.json"
        p.write_text(
            json.dumps(
                {"exceptions": [_exception(), _exception(scope={"package": "x"})]}
            ),
            encoding="utf-8",
        )
        valid, problems = scanner.load_exceptions(p)
        assert len(valid) == 1 and any("重复" in x for x in problems)

    def test_scope_requires_vuln_or_package(self, scanner, tmp_path):
        p = tmp_path / "exc.json"
        p.write_text(
            json.dumps({"exceptions": [_exception(scope={})]}), encoding="utf-8"
        )
        valid, problems = scanner.load_exceptions(p)
        assert valid == [] and any("scope" in x for x in problems)


class TestExceptionMatching:
    def test_vuln_id_exact_match(self, scanner):
        assert scanner.exception_matches(_finding(), _exception())

    def test_alias_match(self, scanner):
        finding = _finding(
            vuln_id="PYSEC-2026-123",
        )
        finding["aliases"] = ["GHSA-xxxx"]
        assert scanner.exception_matches(finding, _exception())

    def test_package_scope_match(self, scanner):
        exc = _exception(scope={"package": "urllib3"})
        assert scanner.exception_matches(_finding(), exc)

    def test_target_key_not_honored(self, scanner):
        """契约：scope 不支持按制品目标限定（跨目标聚合下限定=放大豁免，
        fail-open）；scope.target 键存在时不影响命中判定。"""
        exc = _exception(scope={"vuln_id": "GHSA-xxxx", "target": "deb"})
        assert scanner.exception_matches(_finding(), exc)


class TestAggregateGrype:
    def _raw(self, target: str, vid: str, pkg: str, severity: str, fix=None) -> dict:
        return {
            "matches": [
                {
                    "vulnerability": {
                        "id": vid,
                        "severity": severity,
                        "fix": {"versions": fix or []},
                        "relatedVulnerabilities": (
                            [{"id": "GHSA-alias"}] if vid.startswith("CVE") else []
                        ),
                    },
                    "artifact": {"name": pkg, "version": "1.0"},
                }
            ]
        }

    def test_dedupe_across_targets(self, scanner):
        findings = scanner.aggregate_grype(
            {
                "source-backend": self._raw("a", "CVE-1", "pkg", "High"),
                "deb": self._raw("b", "CVE-1", "pkg", "High"),
            }
        )
        assert len(findings) == 1
        assert findings[0]["targets"] == ["deb", "source-backend"]

    def test_severity_takes_highest(self, scanner):
        findings = scanner.aggregate_grype(
            {
                "source-backend": self._raw("a", "CVE-1", "pkg", "High"),
                "rpm": self._raw("b", "CVE-1", "pkg", "Critical"),
            }
        )
        assert findings[0]["severity"] == "Critical"

    def test_aliases_collected(self, scanner):
        findings = scanner.aggregate_grype(
            {"x": self._raw("x", "CVE-1", "pkg", "High")}
        )
        assert findings[0]["aliases"] == ["GHSA-alias"]


class TestEvaluatePolicy:
    def test_critical_never_waived_by_regular_exception(self, scanner):
        """变异锚点（2026-09-03 政策修订后语义）：普通 High 例外不能豁免
        Critical——无修复 Critical 仅 tracked-no-fix 路径可豁免（另测）。"""
        policy = scanner.evaluate_policy(
            [_finding(severity="Critical")], [_exception()]
        )
        assert len(policy["blocked"]) == 1
        assert "tracked-no-fix" in policy["blocked"][0]["reason"]

    def test_high_waived_with_valid_exception(self, scanner):
        policy = scanner.evaluate_policy([_finding("High")], [_exception()])
        assert policy["blocked"] == []
        assert policy["waived"][0]["exception"] == "SEC-001"

    def test_high_blocked_without_exception(self, scanner):
        policy = scanner.evaluate_policy([_finding("High")], [])
        assert (
            len(policy["blocked"]) == 1
            and "无有效例外" in policy["blocked"][0]["reason"]
        )

    def test_medium_recorded_not_blocked(self, scanner):
        policy = scanner.evaluate_policy([_finding("Medium")], [])
        assert policy["blocked"] == [] and len(policy["recorded"]) == 1


class TestLicenseCheck:
    def test_denylist_hit(self, scanner):
        sbom = {
            "source-backend": {
                "components": [
                    {
                        "name": "some-agpl-lib",
                        "licenses": [{"license": {"id": "AGPL-3.0-only"}}],
                    },
                    {"name": "fastapi", "licenses": [{"license": {"id": "MIT"}}]},
                ]
            }
        }
        denied = scanner.check_licenses(sbom, ["AGPL-3.0-only"])
        assert len(denied) == 1 and denied[0]["package"] == "some-agpl-lib"

    def test_case_insensitive_string_licenses(self, scanner):
        sbom = {"x": {"components": [{"name": "p", "licenses": ["agpl-3.0"]}]}}
        assert len(scanner.check_licenses(sbom, ["AGPL-3.0"])) == 1


class TestSbomPureFunctions:
    def test_strip_lock_hashes(self, sbomgen):
        lock = "openpyxl==3.1.5 \\\n    --hash=sha256:aaa\\\n    --hash=sha256:bbb\nfastapi==0.115.0\n"
        clean = sbomgen.strip_lock_hashes(lock)
        assert "openpyxl==3.1.5" in clean
        assert "fastapi==0.115.0" in clean
        assert "--hash" not in clean and "sha256" not in clean

    def test_prod_npm_names_filters_dev(self, sbomgen):
        lock = {
            "packages": {
                "": {"name": "root"},
                "node_modules/vue": {"name": "vue"},
                "node_modules/jest": {"name": "jest", "dev": True},
                "node_modules/opt": {"name": "opt", "optional": True},
            }
        }
        names = sbomgen.prod_npm_names(lock)
        assert names == {"vue"}

    def test_build_index_shape(self, sbomgen):
        index = sbomgen.build_index(
            {"a": {"path": "/x/sbom-a.json", "sha256": "f" * 64, "components": 3}}
        )
        assert index["targets"]["a"]["components"] == 3
        assert index["targets"]["a"]["file"] == "sbom-a.json"


class TestSecretAllowlist:
    def _entry(self, **kw) -> dict:
        base = {
            "rule_id": "generic-api-key",
            "file": "backend/app/config.py",
            "justification": "配置占位默认值",
            "owner": "huangzj",
            "registered": date.today().isoformat(),
            "expires": (date.today() + timedelta(days=30)).isoformat(),
        }
        base.update(kw)
        return base

    def _write(self, tmp_path, entries):
        p = tmp_path / "allow.json"
        p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
        return p

    def test_valid_allowlist_filters_matching(self, scanner):
        allow = [self._entry()]
        findings = [
            {"RuleID": "generic-api-key", "File": "backend/app/config.py"},
            {"RuleID": "generic-api-key", "File": "backend/app/real.py"},
        ]
        remaining = scanner.filter_allowed_secrets(findings, allow)
        assert len(remaining) == 1 and remaining[0]["File"] == "backend/app/real.py"

    def test_rule_mismatch_not_filtered(self, scanner):
        allow = [self._entry()]
        findings = [{"RuleID": "aws-key", "File": "backend/app/config.py"}]
        assert len(scanner.filter_allowed_secrets(findings, allow)) == 1

    def test_invalid_entry_fail_closed(self, scanner, tmp_path):
        p = self._write(tmp_path, [self._entry(owner="")])
        valid, problems = scanner.load_secret_allowlist(p)
        assert valid == [] and problems != []

    def test_over_60_days_rejected(self, scanner, tmp_path):
        p = self._write(
            tmp_path,
            [self._entry(expires=(date.today() + timedelta(days=61)).isoformat())],
        )
        valid, problems = scanner.load_secret_allowlist(p)
        assert valid == [] and any("60" in x for x in problems)

    def test_expired_rejected(self, scanner, tmp_path):
        p = self._write(
            tmp_path,
            [
                self._entry(
                    registered=(date.today() - timedelta(days=70)).isoformat(),
                    expires=(date.today() - timedelta(days=1)).isoformat(),
                )
            ],
        )
        valid, problems = scanner.load_secret_allowlist(p)
        assert valid == [] and problems != []

    def test_repo_allowlist_valid_and_covers_local_baseline(self, scanner):
        allow, problems = scanner.load_secret_allowlist(
            _REPO_ROOT / "release" / "secret-allowlist.json"
        )
        assert problems == [] and len(allow) == 9


class TestTrackedNoFixPolicy:
    """2026-09-03 政策修订：无修复可用 Critical 的跟踪型例外（三条件）。"""

    def _tracked(self, **kw) -> dict:
        base = {
            "id": "SEC-T01",
            "scope": {"vuln_id": "CVE-2026-8926"},
            "justification": "trixie 当前修订已最新，上游 8.21 已修待回植",
            "owner": "huangzj",
            "remediation_version": "v1.0.7",
            "registered": date.today().isoformat(),
            "expires": (date.today() + timedelta(days=30)).isoformat(),
            "kind": "tracked-no-fix",
            "upstream_fix": "curl 8.21.0（curl.se advisory）",
        }
        base.update(kw)
        return base

    def test_critical_no_fix_with_tracked_exception_waived(self, scanner):
        f = _finding("Critical", vuln_id="CVE-2026-8926")
        f["fix_versions"] = []
        policy = scanner.evaluate_policy([f], [self._tracked()])
        assert policy["blocked"] == []
        assert policy["waived"][0]["waiver_kind"] == "tracked-no-fix"

    def test_critical_with_fix_still_blocks_despite_tracked(self, scanner):
        """变异锚点：有修复可用的 Critical 即使命中 tracked 例外也必须阻断。"""
        f = _finding("Critical", vuln_id="CVE-2026-8926")
        f["fix_versions"] = ["8.21.0"]
        policy = scanner.evaluate_policy([f], [self._tracked()])
        assert len(policy["blocked"]) == 1
        assert "有修复可用" in policy["blocked"][0]["reason"]

    def test_critical_no_fix_without_tracked_blocks(self, scanner):
        f = _finding("Critical")
        f["fix_versions"] = []
        policy = scanner.evaluate_policy([f], [])
        assert (
            len(policy["blocked"]) == 1
            and "tracked-no-fix" in policy["blocked"][0]["reason"]
        )

    def test_tracked_missing_upstream_fix_rejected_at_load(self, scanner, tmp_path):
        bad = self._tracked()
        bad.pop("upstream_fix")
        p = tmp_path / "exc.json"
        p.write_text(json.dumps({"exceptions": [bad]}), encoding="utf-8")
        valid, problems = scanner.load_exceptions(p)
        assert valid == [] and any("upstream_fix" in x for x in problems)

    def test_high_kind_mismatch_not_applied_to_critical(self, scanner):
        """普通 High 例外（无 kind）不得通过 Critical tracked 路径放行。"""
        f = _finding("Critical", vuln_id="GHSA-xxxx")
        f["fix_versions"] = []
        policy = scanner.evaluate_policy([f], [_exception()])
        assert len(policy["blocked"]) == 1
