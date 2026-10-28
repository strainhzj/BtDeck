"""双向迁移管线服务测试（database-migration-ui W1-5/W1-6）。

本地可测面（真 PG 端到端在 tests/pg_integration，CI postgres service）：
- PipelineContext：checkpoint 载体携带 ownership 绑定；attempt_id 生成
- validate_checkpoint_prefix：绑定/版本/前缀矩阵；旧 1.1.0 checkpoint 明确拒绝（T20）
- pg_to_sqlite：staging O_EXCL + sidecar 先于 DDL 持久；归属核验（含 inode 变化拒绝）
- calibrate_sqlite_autoincrement：链内无 AUTOINCREMENT 表 → 报告跳过
- canonical：JSON dict/list 归一、C collation 方言感知
- CLI 分支：active fail-closed / --connection-profile 不可用 / resume 无绑定
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.services.db_migration import canonical, pipeline
from app.services.db_migration.pg_to_sqlite import (
    calibrate_sqlite_autoincrement,
    create_staging_with_sidecar,
    read_staging_sidecar,
    verify_staging_ownership,
)
from app.services.db_migration.pipeline import CheckpointIncompatible, PipelineContext, make_attempt_id

_CTX = PipelineContext(attempt_id="sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", ownership_nonce="n1")


class TestPipelineContext:
    def test_checkpoint_carries_ownership_binding(self):
        ctx = PipelineContext(attempt_id=_CTX.attempt_id, ownership_nonce="n1", origin_epoch="e1")
        payload = ctx.checkpoint_payload({"users": 5})
        assert payload["attempt_id"] == _CTX.attempt_id
        assert payload["ownership_nonce"] == "n1"
        assert payload["origin_epoch"] == "e1"
        assert payload["eligible_epoch"] == "e1"  # 缺省同 origin
        assert payload["tool_version"] == pipeline.TOOL_VERSION
        assert payload["completed"] == {"users": 5}

    def test_make_attempt_id_direction_prefix(self):
        for direction, prefix in (
            ("sqlite-to-pg", "sqlite-to-pg/"),
            ("pg-to-sqlite", "pg-to-sqlite/"),
        ):
            attempt = make_attempt_id(direction)
            assert attempt.startswith(prefix) and len(attempt.rsplit("/", 1)[1]) == 36


class TestCheckpointValidation:
    """T20：绑定/版本/前缀矩阵；旧 1.1.0 checkpoint 拒绝。"""

    def _valid(self, **override):
        payload = {
            "attempt_id": _CTX.attempt_id,
            "ownership_nonce": "n1",
            "origin_epoch": "e1",
            "eligible_epoch": "e1",
            "tool_version": pipeline.TOOL_VERSION,
            "digest_version": "btdeck-canonical-v1",
            "completed": {"users": 5},
        }
        payload.update(override)
        return payload

    def test_valid_prefix_passes(self):
        names = ["a", "users", "b"]
        payload = self._valid(completed={"a": 0, "users": 5})  # 依赖序前缀（a、users）
        assert pipeline.validate_checkpoint_prefix(payload, names, ctx_attempt_id=_CTX.attempt_id, ctx_nonce="n1") == {
            "a": 0,
            "users": 5,
        }

    def test_legacy_1_1_0_checkpoint_rejected_explicitly(self):
        legacy = {"completed": {"users": 5}}  # 旧 1.1.0：无绑定
        with pytest.raises(CheckpointIncompatible, match="旧协议 checkpoint（1.1.0"):
            pipeline.validate_checkpoint_prefix(legacy, ["users"], ctx_attempt_id=_CTX.attempt_id, ctx_nonce="n1")

    def test_negative_count_rejected(self):
        payload = self._valid(completed={"a": -1})
        with pytest.raises(CheckpointIncompatible, match="行数非法"):
            pipeline.validate_checkpoint_prefix(
                payload, ["a", "users", "b"], ctx_attempt_id=_CTX.attempt_id, ctx_nonce="n1"
            )

    @pytest.mark.parametrize(
        "override, match",
        [
            ({"attempt_id": "sqlite-to-pg/11111111-2222-4333-8444-555555555555"}, "绑定"),
            ({"ownership_nonce": "other"}, "绑定"),
            ({"tool_version": "1.1.0"}, "工具版本"),
            ({"completed": {"a": 0, "zzz": 1}}, "前缀"),
            ({"completed": {"zzz": 1}}, "前缀"),
        ],
    )
    def test_mismatch_rejected(self, override, match):
        with pytest.raises(CheckpointIncompatible, match=match):
            pipeline.validate_checkpoint_prefix(
                self._valid(**override), ["a", "users", "b"], ctx_attempt_id=_CTX.attempt_id, ctx_nonce="n1"
            )


class TestStagingSidecar:
    """§3.3 SQLite 边界：O_EXCL + sidecar 先于 DDL；归属核验。"""

    def test_create_and_verify_ownership(self, tmp_path):
        path = create_staging_with_sidecar(tmp_path, _CTX, revision="e9f0a1b2c3d4")
        assert path.name.startswith("app.db.") and path.name.endswith(".sqlite")
        assert path.exists() and path.stat().st_size == 0  # 尚无 DDL
        sidecar = read_staging_sidecar(path)
        assert sidecar is not None
        assert sidecar["attempt_id"] == _CTX.attempt_id
        assert sidecar["ownership_nonce"] == "n1"
        assert sidecar["inode"] == path.stat().st_ino
        assert sidecar["tool_version"] == pipeline.TOOL_VERSION
        # 0600 限权
        assert (path.stat().st_mode & 0o777) == 0o600
        sidecar_path = Path(str(path) + ".sidecar.json")
        assert (sidecar_path.stat().st_mode & 0o777) == 0o600
        assert verify_staging_ownership(path, _CTX) is True

    def test_o_excl_never_overwrites(self, tmp_path):
        create_staging_with_sidecar(tmp_path, _CTX, revision="r")
        from app.services.db_migration.sqlite_to_pg import TargetInvalid

        with pytest.raises(TargetInvalid, match="不覆盖"):
            create_staging_with_sidecar(tmp_path, _CTX, revision="r")

    def test_wrong_ctx_or_inode_change_rejected(self, tmp_path):
        path = create_staging_with_sidecar(tmp_path, _CTX, revision="r")
        other = PipelineContext(attempt_id="pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", ownership_nonce="n2")
        assert verify_staging_ownership(path, other) is False
        # inode 不符（文件被替换而 sidecar 记录旧 inode）→ 拒绝归属
        sidecar_path = Path(str(path) + ".sidecar.json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["inode"] = 999999
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        assert verify_staging_ownership(path, _CTX) is False

    def test_missing_sidecar_is_unknown_ownership(self, tmp_path):
        path = create_staging_with_sidecar(tmp_path, _CTX, revision="r")
        Path(str(path) + ".sidecar.json").unlink()
        assert read_staging_sidecar(path) is None
        assert verify_staging_ownership(path, _CTX) is False

    def test_corrupt_sidecar_is_unknown(self, tmp_path):
        path = create_staging_with_sidecar(tmp_path, _CTX, revision="r")
        Path(str(path) + ".sidecar.json").write_text("{broken", encoding="utf-8")
        assert read_staging_sidecar(path) is None


class TestSqliteAutoincrementProbe:
    def test_chain_has_no_autoincrement_reports_skip(self, tmp_path):
        from app.services.db_migration.target_params import sqlite_engine

        engine = sqlite_engine(str(tmp_path / "probe.db"))
        import os

        try:
            from alembic import command
            from alembic.config import Config

            backend = Path(__file__).resolve().parents[2]
            cfg = Config(str(backend / "alembic.ini"))
            cfg.set_main_option("script_location", str(backend / "alembic"))
            cfg.attributes["configure_logger"] = False
            os.environ["DATABASE_PATH"] = str(tmp_path / "probe.db")
            command.upgrade(cfg, "head")
            lines = calibrate_sqlite_autoincrement(engine)
            assert any("跳过" in line or "sqlite_sequence 为空" in line for line in lines)
        finally:
            engine.dispose()


class TestCanonical:
    def test_json_structures_normalize(self):
        row = {"payload": {"b": 1, "a": [1, {"z": None}]}, "flag": True}
        digest = canonical.digest_rows([row])
        assert len(digest) == 64
        # 键序无关：同内容不同插入序同摘要
        assert digest == canonical.digest_rows([{"flag": True, "payload": {"a": [1, {"z": None}], "b": 1}}])

    def test_sql_null_flag_distinction(self):
        row_sql_null = canonical.with_sql_null_flags({"payload": None}, ["payload"])
        assert row_sql_null["__sql_null__payload"] is True

    def test_pk_order_expr_dialect_aware(self):
        from sqlalchemy import Column, MetaData, String, Table

        table = Table("t", MetaData(), Column("k", String, primary_key=True))
        from sqlalchemy.dialects import postgresql

        def _compile(expr):
            return str(expr[0].compile(dialect=postgresql.dialect()))

        assert 'COLLATE "C"' in _compile(canonical.pk_order_expr(table, "postgresql"))
        assert "COLLATE" not in _compile(canonical.pk_order_expr(table, "sqlite"))
        assert _compile(canonical.pk_order_expr(table, "postgresql")) == _compile(canonical.pg_pk_order_expr(table))

    def test_schema_fingerprint_stable_and_order_sensitive(self):
        from sqlalchemy import Column, Integer, MetaData, String, Table

        t1 = Table("t", MetaData(), Column("id", Integer, primary_key=True), Column("s", String(10)))
        t2 = Table("t", MetaData(), Column("s", String(10)), Column("id", Integer, primary_key=True))
        assert canonical.schema_fingerprint([t1]) == canonical.schema_fingerprint([t2])  # 列序无关
        t3 = Table("t", MetaData(), Column("id", Integer, primary_key=True), Column("s", String(20)))
        assert canonical.schema_fingerprint([t1]) != canonical.schema_fingerprint([t3])


class TestCliBranches:
    """W1-6：CLI fail-closed 分支（完整迁移归 CI 端到端）。"""

    def test_connection_profile_stub_unavailable(self, tmp_path, monkeypatch, capsys):
        from scripts.migrate_sqlite_to_pg import main

        monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
        source = tmp_path / "src.db"
        conn = sqlite3.connect(source)
        conn.execute("CREATE TABLE x (a)")
        conn.close()
        assert main(["--source", str(source), "--connection-profile", "pg-prod"]) == 2

    def test_active_config_fails_closed(self, tmp_path, monkeypatch):
        import yaml

        from scripts.migrate_sqlite_to_pg import main

        monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
        source = tmp_path / "src.db"
        conn = sqlite3.connect(source)
        conn.execute("CREATE TABLE x (a)")
        conn.close()
        (tmp_path / "config.yaml").write_text(
            yaml.dump({"database": {"active": {"version": 1, "dialect": "postgresql"}}}), encoding="utf-8"
        )
        monkeypatch.setenv("DB_TYPE", "postgresql")
        assert main(["--source", str(source)]) == 2

    def test_resume_without_binding_rejected(self, tmp_path, monkeypatch):
        from scripts.migrate_sqlite_to_pg import main

        monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("DB_TYPE", raising=False)
        source = tmp_path / "src.db"
        conn = sqlite3.connect(source)
        conn.execute("CREATE TABLE x (a)")
        conn.close()
        monkeypatch.setenv("DB_TYPE", "postgresql")
        assert main(["--source", str(source), "--resume"]) == 2

    def test_binding_roundtrip_and_permissions(self, tmp_path, monkeypatch):
        from scripts.migrate_sqlite_to_pg import load_latest_attempt_binding, persist_attempt_binding

        monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
        ctx = PipelineContext(attempt_id=make_attempt_id("sqlite-to-pg"))
        path = persist_attempt_binding(ctx)
        assert (path.stat().st_mode & 0o777) == 0o600
        binding = load_latest_attempt_binding()
        assert binding["attempt_id"] == ctx.attempt_id
        assert binding["ownership_nonce"] == ctx.ownership_nonce
