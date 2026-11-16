"""历史迁移记录一次性对账工具（legacy_audit，复核修复批 W3）回归。

覆盖：现代完整记录零旗标、历史形态旗标（缺 candidate_active/identity、
digest 版本不符）、pre-strict-ack 时间窗、现役绑定高亮、JSON 报告落盘、
journal 损坏退出码 2、main 的 --config-dir/--yaml 参数面。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.core.database_bootstrap import ManagedStateError
from app.services.db_migration.journal import Journal, make_manifest_payload
from app.services.db_migration.legacy_audit import format_report, main, scan_legacy_attempts


def _write_manifest(config_dir: Path, attempt: str, **mutate) -> None:
    journal = Journal(str(config_dir))
    payload = make_manifest_payload(
        attempt_id=attempt,
        direction="sqlite-to-pg",
        operation_kind="MIGRATE",
        epoch="epoch-1",
        source={"dialect": "sqlite"},
        target={"dialect": "postgresql"},
        tool_version="2.0.0",
        digest_version="btdeck-canonical-v1",
    )
    payload.update(mutate)
    journal.write_manifest(attempt, payload)


def _modern_manifest(
    config_dir: Path, attempt: str, *, phase: str = "ACTIVATED_ACK", updated: str | None = None
) -> None:
    _write_manifest(
        config_dir,
        attempt,
        commit_phase=phase,
        identity={"database_id": str(uuid.uuid4()), "generation": str(uuid.uuid4())},
        candidate_active={"dialect": "postgresql"},
        updated_at=updated or "2026-11-20T00:00:00+00:00",
    )


def test_modern_complete_attempt_has_no_flags(tmp_path: Path) -> None:
    _modern_manifest(tmp_path, "sqlite-to-pg/" + str(uuid.uuid4()))
    report = scan_legacy_attempts(str(tmp_path))
    assert report["summary"]["total"] == 1
    assert report["summary"]["flagged"] == 0
    assert report["attempts"][0]["flags"] == []


def test_legacy_shapes_are_flagged(tmp_path: Path) -> None:
    acked_legacy = "sqlite-to-pg/" + str(uuid.uuid4())
    # 老形态：已 ACK、无 candidate_active、无 identity
    _write_manifest(tmp_path, acked_legacy, commit_phase="ACTIVATED_ACK")
    # digest 版本不符
    digest_legacy = "sqlite-to-pg/" + str(uuid.uuid4())
    _modern_manifest(tmp_path, digest_legacy)
    journal = Journal(str(tmp_path))
    manifest = journal.read_manifest(digest_legacy)
    manifest["digest_version"] = "sha256-legacy-2025"
    journal.write_manifest(digest_legacy, manifest, expect_state_version=manifest["state_version"])

    report = scan_legacy_attempts(str(tmp_path))
    by_id = {item["attempt_id"]: item for item in report["attempts"]}
    assert set(by_id[acked_legacy]["flags"]) == {"identity-missing", "legacy-ack-unprovable"}
    assert by_id[acked_legacy]["recommendation"]
    assert "digest-version-mismatch" in by_id[digest_legacy]["flags"]
    assert report["summary"]["flagged"] == 2


def test_acked_full_shape_but_pre_strict_window_flagged(tmp_path: Path) -> None:
    """形态完整（有 candidate_active/identity）但 ACK 时间早于严格口径 → 时间窗旗标。"""
    attempt = "sqlite-to-pg/" + str(uuid.uuid4())
    _modern_manifest(tmp_path, attempt, updated="2026-11-10T00:00:00+00:00")
    report = scan_legacy_attempts(str(tmp_path))
    assert report["attempts"][0]["flags"] == ["pre-strict-ack-window"]


def test_active_linked_attempt_is_highlighted(tmp_path: Path) -> None:
    attempt = "sqlite-to-pg/" + str(uuid.uuid4())
    _modern_manifest(tmp_path, attempt)
    active = {
        "version": 1,
        "generation": str(uuid.uuid4()),
        "dialect": "sqlite",
        "sqlite_path": str(tmp_path / "app.db"),
        "expected_database_id": str(uuid.uuid4()),
        "receipt_attempt_id": attempt,
        "revision_at_import": "a2b3c4d5e6f7",
    }
    active_body = json.dumps(active, ensure_ascii=False)
    (tmp_path / "config.yaml").write_text("database:\n  active:\n    " + active_body + "\n", encoding="utf-8")
    report = scan_legacy_attempts(str(tmp_path), yaml_path=str(tmp_path / "config.yaml"))
    assert report["active_receipt_attempt"] == attempt
    assert report["attempts"][0]["active_linked"] is True
    assert "现役" in format_report(report)


def test_main_json_report_and_exit_codes(tmp_path: Path, capsys) -> None:
    _modern_manifest(tmp_path, "sqlite-to-pg/" + str(uuid.uuid4()))
    out = tmp_path / "report.json"
    code = main(["--config-dir", str(tmp_path), "--yaml", str(tmp_path / "config.yaml"), "--json", str(out)])
    assert code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 1
    assert "历史迁移记录一次性对账" in capsys.readouterr().out

    # journal 损坏（manifest 不可读）→ 退出码 2（fail-closed）
    attempts_dir = tmp_path / "db-migration" / "attempts"
    tail = str(uuid.uuid4())
    (attempts_dir / tail).mkdir(parents=True)
    (attempts_dir / tail / "manifest.json").write_text("{corrupt", encoding="utf-8")
    with pytest.raises(ManagedStateError):
        scan_legacy_attempts(str(tmp_path))
    code = main(["--config-dir", str(tmp_path), "--yaml", str(tmp_path / "config.yaml")])
    assert code == 2
