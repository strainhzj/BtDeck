"""早期只读数据库引导测试（database-migration-ui W1-3，PLANS §4.1/§4.3/§4.2）。

- 纯导入（无引擎/settings 副作作用）
- EffectiveDatabaseConfig：active 优先完整覆盖 / env 回退 / 方言互斥 / 严格校验 fail-closed
- 平台分流：Android × PG（env 或 active）在驱动加载前拒绝
- 只读状态检测：SQLite 半成品标记 / control / manifest（损坏即拒，绝不默认化）
- evaluate_startup_disposition：W1 fail-closed 分流桩
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.core.database_bootstrap import (
    DIALECT_POSTGRESQL,
    DIALECT_SQLITE,
    ManagedConfigError,
    ManagedStateError,
    PlatformDatabaseUnsupportedError,
    assert_platform_database_support,
    db_migration_dir,
    evaluate_startup_disposition,
    list_attempt_ids,
    load_active_config,
    pending_attempt_from_control,
    read_control,
    read_manifest,
    resolve_effective_database_config,
    sqlite_has_import_marker,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class TestPurity:
    def test_module_imports_without_engine_side_effects(self):
        code = (
            "import sys; import app.core.database_bootstrap as b; "
            "assert 'app.database' not in sys.modules, 'bootstrap 不得触发引擎导入'; "
            "assert 'app.core.config' not in sys.modules, 'bootstrap 不得触发 settings'; "
            "print('ok')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_ROOT),
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(BACKEND_ROOT)},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _active_pg_yaml() -> dict:
    return {
        "database": {
            "active": {
                "version": 1,
                "generation": "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                "dialect": "postgresql",
                "sqlite_path": None,
                "postgresql": {
                    "host": "postgres",
                    "port": 5432,
                    "user": "btdeck",
                    "password": "s3cr3t-P@ss",
                    "database": "btdeck",
                    "schema": "public",
                    "sslmode": "verify-full",
                    "ssl_root_cert": "/certs/ca.pem",
                    "pool_size": 10,
                    "max_overflow": 20,
                    "pool_timeout": 30,
                },
                "expected_database_id": "11111111-2222-4333-8444-555555555555",
                "receipt_attempt_id": "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
                "revision_at_import": "e9f0a1b2c3d4",
                "switched_at": "2026-10-28T00:00:00Z",
                "switched_by": "admin",
            }
        }
    }


class TestEffectiveConfigActive:
    def test_active_pg_overrides_and_masks(self, tmp_path):
        cfg = resolve_effective_database_config(_write_config(tmp_path, _active_pg_yaml()))
        assert cfg.source == "active" and cfg.dialect == DIALECT_POSTGRESQL
        assert cfg.pg is not None and cfg.pg.password == "s3cr3t-P@ss"
        assert cfg.expected_database_id == "11111111-2222-4333-8444-555555555555"
        summary = cfg.masked_summary()
        assert "password" not in json.dumps(summary)
        assert summary["postgresql"]["host"] == "postgres"
        # 密码绝不进 repr（日志泄漏防线）
        assert "s3cr3t-P@ss" not in repr(cfg) and "s3cr3t-P@ss" not in repr(cfg.pg)

    def test_active_sqlite_requires_absolute_path_and_excludes_pg(self, tmp_path):
        base = _active_pg_yaml()
        active = base["database"]["active"]
        active["dialect"] = "sqlite"
        active["sqlite_path"] = "/data/app.db.migrated.sqlite"
        active["postgresql"] = None
        cfg = resolve_effective_database_config(_write_config(tmp_path, base))
        assert cfg.dialect == DIALECT_SQLITE and cfg.sqlite_path == "/data/app.db.migrated.sqlite"
        assert cfg.pg is None

    def test_mixed_dialect_fields_rejected(self, tmp_path):
        base = _active_pg_yaml()
        base["database"]["active"]["dialect"] = "sqlite"
        base["database"]["active"]["sqlite_path"] = "/data/x.db"
        # sqlite 方言但保留 postgresql 节 → 拒绝
        with pytest.raises(ManagedConfigError, match="禁止混入"):
            resolve_effective_database_config(_write_config(tmp_path, base))

    @pytest.mark.parametrize(
        "mutate, match",
        [
            (lambda a: a.update(version=2), "version"),
            (lambda a: a.update(dialect="mysql"), "dialect"),
            (lambda a: a.update(generation="not-uuid"), "generation"),
            (lambda a: a.update(expected_database_id=None), "expected_database_id"),
            (lambda a: a.update(receipt_attempt_id="../escape"), "receipt_attempt_id"),
            (lambda a: a.update(revision_at_import=""), "revision_at_import"),
            (lambda a: a["postgresql"].update(sslmode="weak"), "sslmode"),
            (lambda a: a["postgresql"].update(sslmode="verify-ca", ssl_root_cert=None), "ssl_root_cert"),
            (lambda a: a["postgresql"].update(port=70000), "port"),
            (lambda a: a["postgresql"].pop("host"), "host"),
        ],
    )
    def test_invalid_active_fail_closed(self, tmp_path, mutate, match):
        base = _active_pg_yaml()
        mutate(base["database"]["active"])
        with pytest.raises(ManagedConfigError, match=match):
            resolve_effective_database_config(_write_config(tmp_path, base))

    def test_corrupt_yaml_raises_not_fallback(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text("database: [broken: {", encoding="utf-8")
        with pytest.raises(ManagedConfigError, match="拒绝默认化"):
            resolve_effective_database_config(path)

    def test_active_not_mapping_rejected(self, tmp_path):
        path = _write_config(tmp_path, {"database": {"active": "oops"}})
        with pytest.raises(ManagedConfigError, match="不是映射"):
            load_active_config(path)


class TestEffectiveConfigEnvFallback:
    def test_env_sqlite_default(self, tmp_path):
        cfg = resolve_effective_database_config(tmp_path / "absent.yaml", environ={})
        assert cfg.source == "env" and cfg.dialect == DIALECT_SQLITE
        assert cfg.sqlite_path is None and cfg.pg is None

    def test_env_sqlite_with_path(self, tmp_path):
        cfg = resolve_effective_database_config(tmp_path / "absent.yaml", environ={"DATABASE_PATH": "/x/app.db"})
        assert cfg.sqlite_path == "/x/app.db"

    def test_env_pg_params(self, tmp_path):
        cfg = resolve_effective_database_config(
            tmp_path / "absent.yaml",
            environ={
                "DB_TYPE": "postgresql",
                "DB_HOST": "pg",
                "DB_PORT": "5433",
                "DB_USER": "u",
                "DB_PASSWORD": "p",
                "DB_NAME": "d",
                "DB_SSLMODE": "require",
            },
        )
        assert cfg.dialect == DIALECT_POSTGRESQL and cfg.pg.host == "pg" and cfg.pg.port == 5433
        assert cfg.pg.sslmode == "require"

    def test_env_invalid_dialect_fails_closed(self, tmp_path):
        with pytest.raises(ManagedConfigError, match="DB_TYPE 配置非法"):
            resolve_effective_database_config(tmp_path / "absent.yaml", environ={"DB_TYPE": "mysql"})

    def test_env_verify_ca_without_cert_rejected(self, tmp_path):
        with pytest.raises(ManagedConfigError, match="DB_SSL_ROOT_CERT"):
            resolve_effective_database_config(
                tmp_path / "absent.yaml",
                environ={"DB_TYPE": "postgresql", "DB_SSLMODE": "verify-ca"},
            )


class TestPlatformGate:
    def _pg_env_cfg(self, tmp_path):
        return resolve_effective_database_config(tmp_path / "absent.yaml", environ={"DB_TYPE": "postgresql"})

    def test_android_rejects_pg_env_and_active(self, tmp_path):
        for effective in (
            self._pg_env_cfg(tmp_path),
            resolve_effective_database_config(_write_config(tmp_path, _active_pg_yaml())),
        ):
            with pytest.raises(PlatformDatabaseUnsupportedError, match="D6"):
                assert_platform_database_support(effective, platform="android-server")

    def test_android_allows_sqlite_and_desktop_allows_pg(self, tmp_path):
        sqlite_env = resolve_effective_database_config(tmp_path / "absent.yaml", environ={})
        assert_platform_database_support(sqlite_env, platform="android-server")
        assert_platform_database_support(self._pg_env_cfg(tmp_path), platform="desktop")


class TestReadOnlyStateDetection:
    def test_sqlite_marker_detection(self, tmp_path):
        clean = tmp_path / "clean.db"
        conn = sqlite3.connect(clean)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
        conn.close()
        assert sqlite_has_import_marker(clean) is False
        assert sqlite_has_import_marker(tmp_path / "missing.db") is False

        half = tmp_path / "half.db"
        conn = sqlite3.connect(half)
        conn.execute("CREATE TABLE _btdeck_import_state (migration_id TEXT)")
        conn.commit()
        conn.close()
        assert sqlite_has_import_marker(half) is True

    def test_control_readers(self, tmp_path):
        assert read_control(tmp_path) is None
        assert pending_attempt_from_control(None) is None
        assert pending_attempt_from_control({}) is None

        control_dir = db_migration_dir(tmp_path)
        control_dir.mkdir(parents=True)
        (control_dir / "control.json").write_text(
            json.dumps({"deployment_id": "d1", "pending_attempt": "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"}),
            encoding="utf-8",
        )
        control = read_control(tmp_path)
        assert control["deployment_id"] == "d1"
        assert pending_attempt_from_control(control) == "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"

        # 非法 pending_attempt → fail-closed
        (control_dir / "control.json").write_text(json.dumps({"pending_attempt": "../x"}), encoding="utf-8")
        with pytest.raises(ManagedStateError, match="形态非法"):
            pending_attempt_from_control(read_control(tmp_path))

        # 损坏 JSON → 拒绝默认化
        (control_dir / "control.json").write_text("{broken", encoding="utf-8")
        with pytest.raises(ManagedStateError, match="拒绝默认化"):
            read_control(tmp_path)

    def test_manifest_readers_with_traversal_guard(self, tmp_path):
        attempt = "pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"
        uuid_tail = attempt.rsplit("/", 1)[1]
        assert list_attempt_ids(tmp_path) == []
        attempt_dir = db_migration_dir(tmp_path) / "attempts" / uuid_tail
        attempt_dir.mkdir(parents=True)
        (attempt_dir / "manifest.json").write_text(json.dumps({"attempt_id": attempt}), encoding="utf-8")
        assert list_attempt_ids(tmp_path) == [attempt]
        assert read_manifest(tmp_path, attempt)["attempt_id"] == attempt

        with pytest.raises(ManagedStateError, match="路径映射"):
            read_manifest(tmp_path, "../../etc")
        with pytest.raises(ManagedStateError, match="manifest 不存在"):
            read_manifest(tmp_path, "handoff/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")

        # 目录内 manifest 声明的 attempt_id 与目录不一致 → 拒绝（防拼接伪造）
        (attempt_dir / "manifest.json").write_text(
            json.dumps({"attempt_id": "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"}), encoding="utf-8"
        )
        with pytest.raises(ManagedStateError, match="不一致"):
            read_manifest(tmp_path, attempt)


class TestStartupDisposition:
    def _env_cfg(self, tmp_path, environ=None):
        return resolve_effective_database_config(tmp_path / "absent.yaml", environ=environ or {})

    def test_normal_when_no_managed_state(self, tmp_path):
        disposition = evaluate_startup_disposition(self._env_cfg(tmp_path))
        assert disposition.normal and disposition.reason_code == ""

    def test_active_config_fail_closed(self, tmp_path):
        effective = resolve_effective_database_config(_write_config(tmp_path, _active_pg_yaml()))
        disposition = evaluate_startup_disposition(effective)
        assert not disposition.normal
        assert disposition.reason_code == "ACTIVE_CONFIG_UNVERIFIED"
        assert "拒绝普通启动" in disposition.detail

    def test_active_activated_ack_normal_and_committed_pending(self, tmp_path):
        """W3：双 ACK 完成的激活→正常启动；COMMITTED 待重启→维护分支（§4.4）。"""
        effective = resolve_effective_database_config(_write_config(tmp_path, _active_pg_yaml()))
        done = evaluate_startup_disposition(
            effective, pending_attempt="sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
            pending_commit_phase="ACTIVATED_ACK",
        )
        assert done.normal and done.reason_code == "ACTIVATION_COMPLETE"
        pending = evaluate_startup_disposition(
            effective, pending_attempt="sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
            pending_commit_phase="COMMITTED",
        )
        assert not pending.normal and pending.reason_code == "ACTIVATION_PENDING_RESTART"

    def test_pending_attempt_fail_closed(self, tmp_path):
        disposition = evaluate_startup_disposition(
            self._env_cfg(tmp_path),
            pending_attempt="pg-to-sqlite/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0",
        )
        assert disposition.reason_code == "PENDING_ATTEMPT_PRESENT"

    def test_import_marker_fail_closed(self, tmp_path):
        disposition = evaluate_startup_disposition(self._env_cfg(tmp_path), sqlite_marker_present=True)
        assert disposition.reason_code == "IMPORT_MARKER_PRESENT"

    def test_control_archive_alone_does_not_block(self, tmp_path):
        disposition = evaluate_startup_disposition(self._env_cfg(tmp_path), control={"deployment_id": "d1"})
        assert disposition.normal
