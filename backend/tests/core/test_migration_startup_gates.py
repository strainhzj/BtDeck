"""migrate_database 受管启动分流测试（database-migration-ui W1-4，PLANS §4.1/§4.3/§4.4）。

覆盖：
- ManagedStartupBlockError 无条件抛出（DEV 也不吞，与 MigrationBackupError 同级）
- SQLite 半成品标记 / VERIFIED-未激活 receipt 拒启；ACTIVATED 历史凭据放行
  （T01 前半：已激活库合法旧 revision 正常升级，不拿历史导入 revision 拒启）
- 受管 active 存在 → fail-closed（绝不 active 损坏→env）
- Android × PG 平台拒绝（env 与 active 两来源）
- env.py target_url 显式目标：重放原生链到独立 SQLite 而不修改全局 env
  （T14 后半：源库零 DDL）
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
import yaml
from alembic import command
from alembic.config import Config

from app.core import migration
from app.core.migration import ManagedStartupBlockError, _build_alembic_config, _evaluate_managed_startup_block

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _make_cfg(db_path: Path) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    os.environ["DATABASE_PATH"] = str(db_path)
    return cfg


def _make_db_with_receipt(tmp_path: Path, *, status: str, version: str | None = None) -> Path:
    """链头库 + 一条指定状态 receipt（模拟已导入/已激活目标库）。"""
    db = tmp_path / f"receipt-{status.lower()}.db"
    command.upgrade(_make_cfg(db), version or "head")
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO bt_database_migration_receipt (attempt_id, operation_kind, target_database_id, "
            "ownership_nonce, revision_at_import, digest_version, schema_fingerprint, "
            "origin_epoch, eligible_epoch, status, created_at, updated_at) "
            "VALUES ('sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0', 'MIGRATE', "
            "'11111111-2222-4333-8444-555555555555', 'n', 'c9e0f1a2b3c4', "
            "'btdeck-canonical-v1', 'fp', 'e1', 'e1', ?, datetime('now'), datetime('now'))",
            (status,),
        )
        conn.commit()
    finally:
        conn.close()
    return db


class TestManagedStartupBlock:
    def test_normal_sqlite_passes(self, tmp_path, monkeypatch):
        db = tmp_path / "normal.db"
        command.upgrade(_make_cfg(db), "head")
        monkeypatch.setenv("DATABASE_PATH", str(db))
        _evaluate_managed_startup_block(str(tmp_path / "absent-config.yaml"))

    def test_importing_receipt_blocks_unconditionally(self, tmp_path, monkeypatch):
        db = _make_db_with_receipt(tmp_path, status="IMPORTING")
        monkeypatch.setenv("DATABASE_PATH", str(db))
        with pytest.raises(ManagedStartupBlockError, match="未激活迁移凭据"):
            _evaluate_managed_startup_block(str(tmp_path / "absent-config.yaml"))
        # migrate_database 也无条件抛（DEV 不吞）
        with pytest.raises(ManagedStartupBlockError):
            migration.migrate_database()

    def test_verified_receipt_blocks_until_activation(self, tmp_path, monkeypatch):
        db = _make_db_with_receipt(tmp_path, status="VERIFIED")
        monkeypatch.setenv("DATABASE_PATH", str(db))
        with pytest.raises(ManagedStartupBlockError, match="VERIFIED"):
            _evaluate_managed_startup_block(str(tmp_path / "absent-config.yaml"))

    def test_stale_abandoned_receipts_do_not_block(self, tmp_path, monkeypatch):
        for status in ("STALE", "ABANDONED"):
            db = _make_db_with_receipt(tmp_path, status=status)
            monkeypatch.setenv("DATABASE_PATH", str(db))
            _evaluate_managed_startup_block(str(tmp_path / "absent-config.yaml"))

    def test_sqlite_import_marker_blocks(self, tmp_path, monkeypatch):
        db = tmp_path / "half.db"
        command.upgrade(_make_cfg(db), "head")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE _btdeck_import_state (migration_id TEXT)")
        conn.commit()
        conn.close()
        monkeypatch.setenv("DATABASE_PATH", str(db))
        with pytest.raises(ManagedStartupBlockError, match="IMPORT_MARKER_PRESENT"):
            _evaluate_managed_startup_block(str(tmp_path / "absent-config.yaml"))

    def test_active_config_fail_closed_never_env(self, tmp_path, monkeypatch):
        db = tmp_path / "ok.db"
        command.upgrade(_make_cfg(db), "head")
        monkeypatch.setenv("DATABASE_PATH", str(db))
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "database": {
                        "active": {
                            "version": 1,
                            "generation": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                            "dialect": "sqlite",
                            "sqlite_path": "/data/app.db.migrated.sqlite",
                            "postgresql": None,
                            "expected_database_id": "11111111-2222-4333-8444-555555555555",
                            "receipt_attempt_id": "pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                            "revision_at_import": "e9f0a1b2c3d4",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ManagedStartupBlockError, match="ACTIVE_CONFIG_UNVERIFIED"):
            _evaluate_managed_startup_block(str(config_path))

    def test_corrupt_active_raises_not_fallback(self, tmp_path, monkeypatch):
        db = tmp_path / "ok.db"
        command.upgrade(_make_cfg(db), "head")
        monkeypatch.setenv("DATABASE_PATH", str(db))
        config_path = tmp_path / "config.yaml"
        config_path.write_text("database: [broken", encoding="utf-8")
        with pytest.raises(ManagedStartupBlockError, match="fail-closed"):
            _evaluate_managed_startup_block(str(config_path))

    def test_android_pg_platform_rejected(self, tmp_path, monkeypatch):
        # 平台判定在 assert_platform_database_support 内从 platform_capabilities 取，
        # patch 其模块级函数（bootstrap 内 import 时点晚于 patch 生效）
        monkeypatch.setattr("app.core.platform_capabilities.resolve_platform", lambda: "android-server")
        monkeypatch.setenv("DB_TYPE", "postgresql")
        try:
            with pytest.raises(ManagedStartupBlockError, match="Android"):
                _evaluate_managed_startup_block(str(tmp_path / "absent-config.yaml"))
        finally:
            monkeypatch.delenv("DB_TYPE", raising=False)


class TestEffectiveDialectDispatch:
    """W6-B 发现④回归：启动迁移分发面向有效配置（active 优先），
    不再盲读 settings.DATABASE_DIALECT（B 模式 active=PG 而 env 未声明时
    曾会打进默认 SQLite）。"""

    def test_dispatch_follows_effective_dialect(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migration, "_evaluate_managed_startup_block", lambda *a, **k: None)
        seen: dict = {}

        def fake_pg() -> bool:
            seen["pg"] = True
            return True

        monkeypatch.setattr(migration, "_migrate_database_pg", fake_pg)
        monkeypatch.setattr(migration, "_effective_runtime_dialect", lambda: "postgresql")
        assert migration.migrate_database() is True
        assert seen.get("pg") is True

    def test_effective_dialect_prefers_active_over_env(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "database": {
                        "active": {
                            "version": 1,
                            "generation": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                            "dialect": "sqlite",
                            "sqlite_path": "/data/app.db.migrated.sqlite",
                            "postgresql": None,
                            "expected_database_id": "11111111-2222-4333-8444-555555555555",
                            "receipt_attempt_id": "pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                            "revision_at_import": "e9f0a1b2c3d4",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(migration.settings, "CONFIG_DIR", str(tmp_path))
        # env 側即便声明 PG，分发也以 active（sqlite）为准
        monkeypatch.setenv("DB_TYPE", "postgresql")
        try:
            assert migration._effective_runtime_dialect() == "sqlite"
        finally:
            monkeypatch.delenv("DB_TYPE", raising=False)

    def test_effective_dialect_env_fallback_when_no_active(self, tmp_path, monkeypatch):
        monkeypatch.setattr(migration.settings, "CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("DB_TYPE", raising=False)
        assert migration._effective_runtime_dialect() == "sqlite"


class TestActivatedLibraryUpgradesNormally:
    """T01 前半：已激活（ACTIVATED）库停在旧 revision → 正常升级，历史导入 revision 不拒启。"""

    def test_activated_old_revision_upgrades_to_new_head(self, tmp_path, monkeypatch):
        db = tmp_path / "activated.db"
        command.upgrade(_make_cfg(db), "head")  # 协议表就位（e9f0 头）
        # 模拟已激活库停在旧 revision：stamp 回退 + ACTIVATED 凭据（历史导入 revision=c9e0）
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                "INSERT INTO bt_database_migration_receipt (attempt_id, operation_kind, target_database_id, "
                "ownership_nonce, revision_at_import, digest_version, schema_fingerprint, "
                "origin_epoch, eligible_epoch, status, activation_generation, activated_at, "
                "created_at, updated_at) "
                "VALUES ('pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0', 'MIGRATE', "
                "'11111111-2222-4333-8444-555555555555', 'n', 'c9e0f1a2b3c4', "
                "'btdeck-canonical-v1', 'fp', 'e1', 'e1', 'ACTIVATED', 'gen-1', "
                "datetime('now'), datetime('now'), datetime('now'))"
            )
            identity_before = conn.execute("SELECT database_id FROM bt_database_identity").fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        command.stamp(_make_cfg(db), "c9e0f1a2b3c4", purge=True)  # 合法旧 revision

        monkeypatch.setenv("DATABASE_PATH", str(db))
        _evaluate_managed_startup_block(str(tmp_path / "absent-config.yaml"))  # ACTIVATED 放行
        assert migration.migrate_database() is True
        conn = sqlite3.connect(db)
        try:
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            identity_after = conn.execute("SELECT database_id FROM bt_database_identity").fetchone()[0]
            receipt_status = conn.execute("SELECT status FROM bt_database_migration_receipt").fetchone()[0]
        finally:
            conn.close()
        assert version == "e9f0a1b2c3d4"  # 正常升级到新 head，不拿历史导入 revision 拒启
        assert identity_after == identity_before  # 身份不重生成
        assert receipt_status == "ACTIVATED"  # 历史凭据不被迁移链破坏


class TestExplicitTargetUrl:
    """T14 后半：显式目标 URL 重放原生链到独立 SQLite，全局 env/源库零改动。"""

    def test_chain_replay_to_explicit_target_without_env_mutation(self, tmp_path, monkeypatch):
        source = tmp_path / "source.db"
        command.upgrade(_make_cfg(source), "head")  # “源”库（模拟运行态）

        target = tmp_path / "staging" / "app.db.staging.sqlite"
        target.parent.mkdir()
        os.environ.pop("DATABASE_PATH", None)  # 确保无全局路径污染
        cfg = _build_alembic_config(str(source), target_url=f"sqlite:///{target}")
        command.upgrade(cfg, "head")

        # 目标库建起全量表
        conn = sqlite3.connect(target)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            conn.close()
        assert count == 46  # 45 + alembic_version
        assert version == "e9f0a1b2c3d4"

        # 源库零 DDL：版本保持 head、未被触碰（文件 mtime 语义不可靠，验证内容不变）
        conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            src_version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            conn.close()
        assert src_version == "e9f0a1b2c3d4"
