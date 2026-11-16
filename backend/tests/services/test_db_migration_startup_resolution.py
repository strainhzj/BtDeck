"""早期启动决议（startup/resolution，复核修复批 W3 / R4 深水区）回归。

覆盖：COMMITTED 待 ACK 的导入前 redo 全链（幂等补发布→严格目标 ACK→归档→
本地 ACK→清 RESTART_PENDING）、重放幂等（第二次 nothing_pending）、发布/ACK
失败保持 COMMITTED、resolve_and_prepare_startup 绝不抛出、无 pending 时
no-op、lifecycle 兜底位的漂移检测与一致放行。
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from app.core.database_protocol import RECEIPT_TABLE
from app.services.db_migration.activation import ActivationService
from app.services.db_migration.journal import (
    COMMIT_PHASE_ACTIVATED_ACK,
    COMMIT_PHASE_COMMITTED,
    Journal,
    make_manifest_payload,
)
from app.startup.resolution import (
    REDO_COMPLETED,
    REDO_NOTHING_PENDING,
    resolve_and_prepare_startup,
    run_pending_activation_redo,
)


def _minimal_sqlite_target(path: Path, *, attempt: str, nonce: str, identity: str) -> None:
    """最小目标实库：identity + VERIFIED receipt（严格 ACK 的核验面）。"""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE bt_database_identity (database_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO bt_database_identity VALUES (?)", (identity,))
    conn.execute(
        f"""CREATE TABLE {RECEIPT_TABLE} (
            attempt_id TEXT PRIMARY KEY, operation_kind TEXT, source_database_id TEXT,
            target_database_id TEXT, deployment_id TEXT, ownership_nonce TEXT,
            revision_at_import TEXT, digest_version TEXT, table_counts TEXT, table_digests TEXT,
            schema_fingerprint TEXT, origin_epoch TEXT, eligible_epoch TEXT, status TEXT,
            activation_generation TEXT, activated_at TEXT)"""
    )
    conn.execute(
        f"INSERT INTO {RECEIPT_TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            attempt,
            "MIGRATE",
            "src",
            identity,
            "d1",
            nonce,
            "a2b3c4d5e6f7",
            "btdeck-canonical-v1",
            "{}",
            "{}",
            "fp",
            "epoch-o",
            "epoch-o",
            "VERIFIED",
            None,
            None,
        ),
    )
    conn.commit()
    conn.close()


def _committed_fixture(tmp_path: Path, target: Path) -> str:
    """COMMITTED 待 ACK 现场：PREPARED（含候选树）→ 手动推进 COMMITTED 未发布。"""
    identity = str(uuid.uuid4())
    attempt = "pg-to-sqlite/" + str(uuid.uuid4())
    _minimal_sqlite_target(target, attempt=attempt, nonce="n1", identity=identity)
    journal = Journal(str(tmp_path))
    journal.write_control(lambda c: {**c, "pending_attempt": attempt}, deployment_id="d1")
    journal.write_manifest(
        attempt,
        make_manifest_payload(
            attempt_id=attempt,
            direction="pg-to-sqlite",
            operation_kind="MIGRATE",
            epoch="epoch-1",
            source={"dialect": "postgresql"},
            target={"dialect": "sqlite"},
            tool_version="2.0.0",
            digest_version="btdeck-canonical-v1",
        ),
    )
    manifest = journal.read_manifest(attempt)
    manifest["ownership_nonce"] = "n1"
    journal.write_manifest(attempt, manifest, expect_state_version=manifest["state_version"])

    candidate = {
        "version": 1,
        "generation": str(uuid.uuid4()),
        "dialect": "sqlite",
        "sqlite_path": str(target),
        "expected_database_id": identity,
        "receipt_attempt_id": attempt,
        "revision_at_import": "a2b3c4d5e6f7",
    }
    service = ActivationService(
        str(tmp_path),
        yaml_path=str(tmp_path / "config.yaml"),
        restart_scheduler=lambda _info: False,
    )
    service.prepare_switch(attempt, mode="B", candidate_active=candidate, identity={})
    journal.advance_commit_phase(attempt, expected="PREPARED", new="COMMITTED")
    return attempt


def test_import_time_redo_completes_full_chain(tmp_path: Path) -> None:
    """导入前 redo：发布→严格 ACK→本地 ACK 全链完成，进程侧零漂移可解析。"""
    from app.core.database_bootstrap import resolve_effective_database_config

    target = tmp_path / "target.sqlite"
    attempt = _committed_fixture(tmp_path, target)
    yaml_path = tmp_path / "config.yaml"

    outcome = run_pending_activation_redo(str(tmp_path), yaml_path=str(yaml_path))
    assert outcome == REDO_COMPLETED

    # 1. 已发布：config.yaml 出现 database.active 且指向目标
    effective = resolve_effective_database_config(yaml_path)
    assert effective.source == "active"
    assert effective.dialect == "sqlite"
    assert effective.sqlite_path == str(target)
    assert effective.receipt_attempt_id == attempt

    # 2. 严格 ACK 落库：VERIFIED → ACTIVATED + 代次
    conn = sqlite3.connect(target)
    row = conn.execute(
        f"SELECT status, activation_generation, activated_at FROM {RECEIPT_TABLE} WHERE attempt_id=?",
        (attempt,),
    ).fetchone()
    conn.close()
    assert row[0] == "ACTIVATED" and row[1] and row[2]

    # 3. journal：COMMITTED → ACTIVATED_ACK；RESTART_PENDING 清零
    manifest = Journal(str(tmp_path)).read_manifest(attempt)
    assert manifest["commit_phase"] == COMMIT_PHASE_ACTIVATED_ACK
    control = Journal(str(tmp_path)).read_control()
    assert control.get("restart_pending") is False

    # 4. 重放幂等：已完成 → nothing_pending（不再动任何状态）
    assert run_pending_activation_redo(str(tmp_path), yaml_path=str(yaml_path)) == REDO_NOTHING_PENDING


def test_import_time_redo_failure_keeps_committed(tmp_path: Path) -> None:
    """目标 ACK 阶段失败（COMMITTED 后目标身份被損坏）→ REDO_FAILED 且 phase 保持 COMMITTED。

    候选树与摘要完全一致（发布合法）而目标库已非候选身份——严格 writer 拒绝；
    这正是导入前决议的价值：失败发生在任何引擎模块导入之前，绝不产生
    "旧引擎+新配置"漂移。
    """
    target = tmp_path / "target.sqlite"
    attempt = _committed_fixture(tmp_path, target)
    # COMMITTED 后目标被重建（identity/receipt 丢失）：候选树/摘要不动
    target.unlink()
    conn = sqlite3.connect(target)
    conn.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    outcome = run_pending_activation_redo(str(tmp_path), yaml_path=str(tmp_path / "config.yaml"))
    assert outcome == "failed"
    assert Journal(str(tmp_path)).read_manifest(attempt)["commit_phase"] == COMMIT_PHASE_COMMITTED


def test_noop_when_nothing_pending(tmp_path: Path) -> None:
    assert run_pending_activation_redo(str(tmp_path), yaml_path=str(tmp_path / "config.yaml")) == REDO_NOTHING_PENDING


def test_resolve_and_prepare_startup_never_raises(tmp_path: Path) -> None:
    """损坏 control（fail-closed 形态）也不得阻塞导入——交 lifespan 维护分支。"""
    (tmp_path / "db-migration").mkdir()
    (tmp_path / "db-migration" / "control.json").write_text("{corrupt", encoding="utf-8")
    resolve_and_prepare_startup(str(tmp_path / "config.yaml"))  # 不抛即为过


def test_lifecycle_fallback_detects_drift(tmp_path: Path, monkeypatch) -> None:
    """兜底位（导入后才跑）：redo 完成但进程缓存仍旧配置 → False（维护/托管退出）。"""
    from app.core import database_bootstrap as bootstrap

    target = tmp_path / "target.sqlite"
    _committed_fixture(tmp_path, target)
    yaml_path = tmp_path / "config.yaml"

    # 模拟"导入期缓存仍旧配置"（wrapper 每次调用时 from app.database import）；
    # 不预跑 redo——兜底位自己完成 redo 后再做漂移判定
    stale = bootstrap.EffectiveDatabaseConfig(
        source="env", dialect=bootstrap.DIALECT_SQLITE, sqlite_path=str(tmp_path / "old.db"), pg=None
    )
    monkeypatch.setattr("app.database.get_effective_database_config", lambda: stale)
    from app.startup import lifecycle

    assert (
        lifecycle._startup_activation_redo(object(), str(tmp_path), yaml_path=str(yaml_path)) is False
    )  # noqa: SLF001
    control = Journal(str(tmp_path)).read_control()
    assert control.get("restart_pending") is True, "漂移必须置 RESTART_PENDING 阻止沿用旧引擎"


def test_lifecycle_fallback_consistent_cache_passes(tmp_path: Path, monkeypatch) -> None:
    """兜底位：wrapper 自己完成 redo 且进程缓存与发布一致 → True（正常放行）。"""
    from app.core import database_bootstrap as bootstrap

    target = tmp_path / "target.sqlite"
    attempt = _committed_fixture(tmp_path, target)
    yaml_path = tmp_path / "config.yaml"

    published_like = bootstrap.EffectiveDatabaseConfig(
        source="active",
        dialect=bootstrap.DIALECT_SQLITE,
        sqlite_path=str(target),
        pg=None,
        generation=str(uuid.uuid4()),
        expected_database_id=str(uuid.uuid4()),
        receipt_attempt_id=attempt,
        revision_at_import="a2b3c4d5e6f7",
    )
    monkeypatch.setattr("app.database.get_effective_database_config", lambda: published_like)
    from app.startup import lifecycle

    assert lifecycle._startup_activation_redo(object(), str(tmp_path), yaml_path=str(yaml_path)) is True  # noqa: SLF001
