"""2026-11-15 复核修复回归（PG/SQLite 迁移审查 W1 批）。

覆盖：反向全列摘要修复、时区 UTC 归一、枚举双向一致、cancel/credentials CAS、
READY 原子裁决、fence owner 持有、反向绝对路径、激活代次/候选 hash/严格目标
ACK（SQLite 最小目标实库）、boot HELD 安全续跑。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, DateTime, Enum, Integer, MetaData, String, Table, create_engine

from app.core.database_protocol import RECEIPT_TABLE
from app.models.downloader_settings import SpeedUnitEnum
from app.services.db_migration.activation import ActivationError, ActivationService
from app.services.db_migration.journal import (
    COMMIT_PHASE_COMMITTED,
    Journal,
    make_manifest_payload,
)
from app.services.db_migration.local_audit import MaintenanceLocalAudit
from app.services.db_migration.maintenance import MaintenanceController
from app.services.db_migration.manager import ManagerError, MigrationManager, StateConflict
from app.services.db_migration.pg_to_sqlite import _normalize_by_column_type, verify_pg_vs_sqlite
from app.services.db_migration.sqlite_to_pg import verify_counts_and_digests


class _OwnerFence:
    """fence 替身（含 verify/release，匹配 FenceOwner 协议）。"""

    class _Tok:
        fingerprint = "fp-review"

    token = _Tok()

    def __init__(self) -> None:
        self.acquired = False
        self.released = False

    def acquire(self, *, timeout_seconds: float = 30.0):  # noqa: ARG002
        self.acquired = True
        return self.token

    def verify(self) -> bool:
        return True

    def verify_against(self, expected: str) -> bool:
        return self.token.fingerprint == expected

    def release(self) -> None:
        self.released = True


def _make_manager(tmp_path: Path, runner) -> MigrationManager:
    manager = MigrationManager(
        str(tmp_path),
        controller=MaintenanceController(str(tmp_path)),
        audit=MaintenanceLocalAudit(str(tmp_path)),
        pipeline_runner=runner,
    )
    fences: list = []

    def factory(direction, source_desc):  # noqa: ARG001
        fence = _OwnerFence()
        fences.append(fence)
        return fence

    manager.fence_factory = factory  # type: ignore[attr-defined]
    return manager


# ---------------------------------------------------------------------------
# 1. 反向全列摘要（复核缺陷 1）
# ---------------------------------------------------------------------------


def test_reverse_verify_checks_content_for_pk_tables() -> None:
    metadata = MetaData()
    table = Table("probe", metadata, Column("id", Integer, primary_key=True), Column("value", String))
    source = create_engine("sqlite://")
    target = create_engine("sqlite://")
    metadata.create_all(source)
    metadata.create_all(target)
    with source.begin() as conn:
        conn.execute(table.insert(), {"id": 1, "value": "source-value"})
    with target.begin() as conn:
        conn.execute(table.insert(), {"id": 1, "value": "mutated-value"})
    with source.connect() as conn:
        problems, counts, digests = verify_pg_vs_sqlite(conn, target, [table])
    assert any("内容摘要不一致" in p for p in problems), problems
    assert "probe" in digests, "有主键表必须产生全列摘要（原实现跳过）"


def test_normalize_timezone_aware_to_utc_naive() -> None:
    metadata = MetaData()
    table = Table("probe", metadata, Column("id", Integer, primary_key=True), Column("at", DateTime))
    row = {"id": 1, "at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=8)))}
    normalized = _normalize_by_column_type(table, row)
    assert normalized["at"] == datetime(2026, 1, 1, 4, 0, 0)
    assert normalized["at"].tzinfo is None


def test_forward_verify_enum_matches_source_label() -> None:
    metadata = MetaData()
    table = Table("enum_probe", metadata, Column("id", Integer, primary_key=True), Column("unit", Enum(SpeedUnitEnum)))
    target = create_engine("sqlite://")
    metadata.create_all(target)
    with target.begin() as conn:
        conn.execute(table.insert(), {"id": 1, "unit": SpeedUnitEnum.KB_PER_SEC})
    raw = sqlite3.connect(":memory:")
    raw.execute("CREATE TABLE enum_probe (id INTEGER PRIMARY KEY, unit TEXT)")
    raw.execute("INSERT INTO enum_probe VALUES (1, 'KB_PER_SEC')")
    try:
        problems, counts, digests = verify_counts_and_digests(raw, target, [table])
        assert problems == [], problems
        assert "enum_probe" in digests, "枚举列必须产生摘要（正常数据不得误报）"
    finally:
        raw.close()


# ---------------------------------------------------------------------------
# 2. cancel CAS / READY 原子裁决（复核缺陷 6/10）
# ---------------------------------------------------------------------------


def test_request_cancel_consumes_cas(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def runner(ctx, manifest):  # noqa: ARG001
        entered.set()
        release.wait(timeout=10)
        return {"database_id": str(uuid.uuid4())}

    manager = _make_manager(tmp_path, runner)
    status = manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
    assert entered.wait(5)
    attempt_id = status.attempt_id
    with pytest.raises(StateConflict, match="attempt"):
        manager.request_cancel(reason="x", expect_attempt_id="pg-to-sqlite/" + str(uuid.uuid4()))
    with pytest.raises(StateConflict, match="CAS"):
        manager.request_cancel(reason="x", expect_attempt_id=attempt_id, expect_epoch="stale", expect_state_version=1)
    manager.request_cancel(
        reason="ok",
        expect_attempt_id=attempt_id,
        expect_epoch=status.epoch,
        expect_state_version=status.state_version,
    )
    release.set()
    assert manager.wait_worker_stopped(10)
    assert manager.status().phase == "cancelled"


def test_cancel_during_verify_converges(tmp_path: Path) -> None:
    """复核缺陷 6 后半：verify 中受理的取消在 worker 结束后必须收敛 CANCELLED。"""
    entered = threading.Event()
    release = threading.Event()

    def runner(ctx, manifest):  # noqa: ARG001
        ctx.check_cancel()
        ctx.report("verify", 0, 1)
        entered.set()
        release.wait(timeout=10)
        return {"database_id": str(uuid.uuid4())}

    manager = _make_manager(tmp_path, runner)
    manager.start_migration("sqlite-to-pg", {"host": "pg"}, password="pw")
    assert entered.wait(5)
    manager.request_cancel(reason="during-verify")
    release.set()
    assert manager.wait_worker_stopped(10)
    assert manager.status().phase == "cancelled", manager.status()
    assert manager.controller.wait_cancel_ack(0.01)


def test_reverse_relative_final_path_rejected(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path, lambda ctx, manifest: {})  # noqa: ARG005
    with pytest.raises(ManagerError, match="绝对路径"):
        manager.start_migration("pg-to-sqlite", {"final_path": "rel/dir"}, password="pw")
    assert manager.controller.status().state == "NORMAL"


# ---------------------------------------------------------------------------
# 3. credentials 不得换目标（复核缺陷 5）
# ---------------------------------------------------------------------------


def test_credentials_cannot_change_target(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def runner(ctx, manifest):  # noqa: ARG001
        entered.set()
        release.wait(timeout=10)
        return {"database_id": str(uuid.uuid4())}

    manager = _make_manager(tmp_path, runner)
    status = manager.start_migration("sqlite-to-pg", {"host": "pg-a", "database": "db1"}, password="pw")
    assert entered.wait(5)
    manager.provide_credentials(status.attempt_id, password="new-pw", target={"host": "pg-a"})
    with pytest.raises(StateConflict, match="不可换目标"):
        manager.provide_credentials(status.attempt_id, password="pw", target={"host": "pg-b"})
    release.set()
    assert manager.wait_worker_stopped(10)


# ---------------------------------------------------------------------------
# 4. 激活：固定代次 G / 候选 hash 守卫（复核缺陷 3 补强）
# ---------------------------------------------------------------------------


def _prepared_activation(tmp_path: Path, generation: str, sqlite_path: Path):
    attempt = "pg-to-sqlite/" + str(uuid.uuid4())
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
        "generation": generation,
        "dialect": "sqlite",
        "sqlite_path": str(sqlite_path),
        "expected_database_id": str(uuid.uuid4()),
        "receipt_attempt_id": attempt,
        "revision_at_import": "a2b3c4d5e6f7",
    }
    service = ActivationService(
        str(tmp_path),
        yaml_path=str(tmp_path / "config.yaml"),
        target_ack_writer=lambda *_: None,
        restart_scheduler=lambda _info: False,
    )
    service.prepare_switch(attempt, mode="B", candidate_active=candidate, identity={})
    return attempt, journal, service, candidate


def test_activation_generation_fixed_and_repeat_idempotent(tmp_path: Path) -> None:
    generation = str(uuid.uuid4())
    attempt, journal, service, _candidate = _prepared_activation(tmp_path, generation, tmp_path / "t.sqlite")
    manifest = journal.read_manifest(attempt)
    assert manifest["identity"]["generation"] == generation
    first = service.commit_switch(attempt)
    second = service.commit_switch(attempt)
    control = journal.read_control()
    assert control["generation"] == generation == first["generation"] == second["generation"]


def test_activation_publish_rejects_tampered_candidate(tmp_path: Path) -> None:
    from app.services.db_migration.config_store import read_candidate_config, write_candidate_config

    attempt, journal, service, _candidate = _prepared_activation(tmp_path, str(uuid.uuid4()), tmp_path / "t.sqlite")
    # prepare_switch 已推进 NONE→PREPARED；此处推进到 COMMITTED 触发发布路径
    journal.advance_commit_phase(attempt, expected="PREPARED", new="COMMITTED")
    tree = read_candidate_config(str(tmp_path), attempt)
    tree["database"]["active"]["sqlite_path"] = str(tmp_path / "TAMPERED.sqlite")
    write_candidate_config(str(tmp_path), attempt, tree)
    with pytest.raises(ActivationError, match="摘要不符"):
        service.commit_switch(attempt)
    assert journal.read_manifest(attempt)["commit_phase"] == COMMIT_PHASE_COMMITTED


# ---------------------------------------------------------------------------
# 5. 严格目标 ACK（最小 SQLite 目标实库；复核缺陷 3 核心）
# ---------------------------------------------------------------------------


def _minimal_sqlite_target(path: Path, *, attempt: str, nonce: str, identity: str, generation: str | None) -> None:
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
            generation,
            None,
        ),
    )
    conn.commit()
    conn.close()


def test_strict_default_ack_sqlite_target(tmp_path: Path) -> None:
    identity = str(uuid.uuid4())
    target = tmp_path / "target.sqlite"
    attempt = "pg-to-sqlite/" + str(uuid.uuid4())
    _minimal_sqlite_target(target, attempt=attempt, nonce="n1", identity=identity, generation=None)
    journal = Journal(str(tmp_path))
    journal.write_control(lambda c: {**c, "pending_attempt": attempt}, deployment_id="d1")
    manifest = make_manifest_payload(
        attempt_id=attempt,
        direction="pg-to-sqlite",
        operation_kind="MIGRATE",
        epoch="epoch-1",
        source={"dialect": "postgresql"},
        target={"dialect": "sqlite"},
        tool_version="2.0.0",
        digest_version="btdeck-canonical-v1",
    )
    manifest["ownership_nonce"] = "n1"
    manifest["candidate_active"] = {
        "dialect": "sqlite",
        "sqlite_path": str(target),
        "expected_database_id": identity,
        "generation": "G-1",
    }
    journal.write_manifest(attempt, manifest)
    service = ActivationService(
        str(tmp_path), yaml_path=str(tmp_path / "config.yaml"), restart_scheduler=lambda _i: False
    )
    service._default_target_ack_writer(attempt, "G-1")  # noqa: SLF001 - 直接验证默认 ACK 实现

    conn = sqlite3.connect(target)
    row = conn.execute(
        f"SELECT status, activation_generation, activated_at FROM {RECEIPT_TABLE} WHERE attempt_id=?",
        (attempt,),
    ).fetchone()
    conn.close()
    assert row[0] == "ACTIVATED" and row[1] == "G-1" and row[2]

    # 非 VERIFIED 重放（幂等分支属于 complete_activation，writer 只接受 VERIFIED）
    with pytest.raises(ActivationError):
        service._default_target_ack_writer(attempt, "G-1")  # noqa: SLF001

    # 换 attempt（receipt 不存在 → 恰好一行约束不满足）
    ghost = "pg-to-sqlite/" + str(uuid.uuid4())
    with pytest.raises(ActivationError):
        service._default_target_ack_writer(ghost, "G-1")  # noqa: SLF001


# ---------------------------------------------------------------------------
# 6. boot HELD 安全续跑（复核缺陷 7）
# ---------------------------------------------------------------------------


def test_resume_boot_held_rebinds_and_spawns(tmp_path: Path) -> None:
    identity = str(uuid.uuid4())
    staging = tmp_path / "final" / f"app.db.{uuid.uuid4()}.sqlite"
    staging.parent.mkdir(parents=True)
    attempt = "pg-to-sqlite/" + str(uuid.uuid4())
    old_epoch = "epoch-old"
    _minimal_sqlite_target(staging, attempt=attempt, nonce="n1", identity=identity, generation=None)
    # eligible_epoch = old（重绑 CAS 的目标面）
    conn = sqlite3.connect(staging)
    conn.execute(f"UPDATE {RECEIPT_TABLE} SET eligible_epoch=? WHERE attempt_id=?", (old_epoch, attempt))
    conn.commit()
    conn.close()

    journal = Journal(str(tmp_path))
    journal.write_control(lambda c: {**c, "pending_attempt": attempt}, deployment_id="d1")
    manifest = make_manifest_payload(
        attempt_id=attempt,
        direction="pg-to-sqlite",
        operation_kind="MIGRATE",
        epoch=old_epoch,
        source={"dialect": "postgresql"},
        target={"dialect": "sqlite"},
        tool_version="2.0.0",
        digest_version="btdeck-canonical-v1",
        final_path=str(staging),
        source_snapshot={"fingerprint": "fp-review", "taken_at": 0.0},
    )
    manifest["ownership_nonce"] = "n1"
    manifest["origin_epoch"] = old_epoch
    journal.write_manifest(attempt, manifest)

    controller = MaintenanceController(str(tmp_path))
    controller.enter_maintenance_boot(attempt_id=attempt)
    finished = threading.Event()

    def runner(ctx, m):  # noqa: ARG001
        finished.set()
        return {"database_id": identity, "final": str(staging), "revision": "a2b3c4d5e6f7"}

    manager = MigrationManager(
        str(tmp_path),
        controller=controller,
        audit=MaintenanceLocalAudit(str(tmp_path)),
        pipeline_runner=runner,
    )
    fences: list = []

    def factory(direction, source_desc):  # noqa: ARG001
        fence = _OwnerFence()
        fences.append(fence)
        return fence

    manager.fence_factory = factory  # type: ignore[attr-defined]
    manager._store_credentials(attempt, {"dialect": "sqlite"}, "pw")  # noqa: SLF001

    before = journal.read_manifest(attempt)
    status = manager.resume_pending_attempt(expect_epoch=before["epoch"], expect_state_version=before["state_version"])
    assert finished.wait(5), "resume 必须派生 worker"
    assert manager.wait_worker_stopped(10)
    assert status.phase in {"verifying", "ready_to_switch"}
    assert manager.status().phase == "ready_to_switch"
    fresh = journal.read_manifest(attempt)
    assert fresh["epoch"] != old_epoch, "重绑必须推进资格代次"
    conn = sqlite3.connect(staging)
    new_eligible = conn.execute(
        f"SELECT eligible_epoch FROM {RECEIPT_TABLE} WHERE attempt_id=?", (attempt,)
    ).fetchone()[0]
    conn.close()
    assert new_eligible == fresh["epoch"], "目标 receipt eligible_epoch 必须同步 CAS"
    assert fresh["candidate_active"]["dialect"] == "sqlite"


# ---------------------------------------------------------------------------
# 7. manifest JSON 快照可序列化（resume 重绑记录不破坏 JSON-safe）
# ---------------------------------------------------------------------------


def test_rebind_records_stay_json_safe(tmp_path: Path) -> None:
    attempt, journal, _service, _candidate = _prepared_activation(tmp_path, str(uuid.uuid4()), tmp_path / "t.sqlite")
    # rebind 要求 controller 处于 HELD/ABANDONED（boot HELD 形态）
    controller = MaintenanceController(str(tmp_path))
    controller.enter_maintenance_boot(attempt_id=attempt)
    manager = MigrationManager(
        str(tmp_path / "empty-manager"),
        controller=controller,
        audit=MaintenanceLocalAudit(str(tmp_path / "empty-manager")),
        pipeline_runner=lambda ctx, m: {},  # noqa: ARG005
    )
    manager._journal = journal  # noqa: SLF001 - 绑定同一 journal 验证 rebind 持久化
    manifest = journal.read_manifest(attempt)
    out = manager.rebind_epoch(
        expect_epoch=manifest["epoch"],
        expect_state_version=int(manifest["state_version"]),
        proof_hash="fp",
        target_cas=lambda old, new: True,  # noqa: ARG005
    )
    json.dumps(out)  # 不抛即 JSON-safe
    assert any(r["stage"] == "REBIND_ACK" for r in out.get("rebind_records", []))
