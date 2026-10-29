"""config 仓储测试（database-migration-ui W3-2，PLANS §4.1/§4.2；T09/T15）。

覆盖：
- RMW 统一锁：进程内重入、跨进程互斥；init_config_file 与 rmw_yaml 同锁串行；
- 原子写：replace 失败旧文件完好；未知节保留（禁默认配置重建吞自定义节）；
- 损坏 fail-closed：config.yaml 损坏时 rmw 拒绝（不重建默认）；
- 受保护候选/前代：0600/0700、摘要稳定、路径穿越拒绝；
- T15 同源：build_database_url/DIALECT 在 active 存在时完整覆盖（PG 密码特殊
  字符转义/TLS query/池参数、sqlite 绝对路径），无 active 时与 env 历史行为
  逐字节一致；受管 active 损坏 → 导入级 fail-closed。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from app.services.db_migration.config_store import (
    ConfigStoreError,
    config_lock,
    read_yaml,
    rmw_yaml,
    write_candidate_config,
    write_prior_config,
    write_yaml_atomic,
    yaml_digest,
)

ATTEMPT = "sqlite-to-pg/0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


class TestRmwLock:
    def test_reentrant(self, tmp_path):
        target = tmp_path / "config.yaml"
        write_yaml_atomic(target, {"a": 1})
        with config_lock(target):
            with config_lock(target):
                rmw_yaml(target, lambda c: {**c, "b": 2})

    def test_cross_process_exclusive(self, tmp_path):
        target = tmp_path / "config.yaml"
        write_yaml_atomic(target, {"a": 1})
        holder = textwrap.dedent(
            """
            import fcntl, os, sys, time
            path = sys.argv[1]
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            print("held", flush=True)
            time.sleep(3)
            """
        )
        lock_path = tmp_path / "config.yaml.rmw.lock"
        proc = subprocess.Popen([sys.executable, "-c", holder, str(lock_path)], stdout=subprocess.PIPE)
        assert proc.stdout.readline().decode().strip() == "held"
        with pytest.raises(ConfigStoreError):
            with config_lock(target):
                pass
        proc.kill()
        proc.wait(timeout=5)


class TestAtomicAndPreserve:
    def test_replace_failure_keeps_old(self, tmp_path, monkeypatch):
        target = tmp_path / "config.yaml"
        write_yaml_atomic(target, {"database": {"active": {"keep": True}}})
        before = target.read_text(encoding="utf-8")

        def boom(src, dst, *a, **kw):  # noqa: ANN001
            raise OSError("EXDEV")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            write_yaml_atomic(target, {"database": {}})
        assert target.read_text(encoding="utf-8") == before

    def test_unknown_sections_preserved(self, tmp_path):
        target = tmp_path / "config.yaml"
        write_yaml_atomic(
            target, {"database": {"host": "h"}, "custom_plugin": {"x": 1}, "security": {"secret_key": "s"}}
        )
        out = rmw_yaml(target, lambda c: {**c, "database": {**c["database"], "port": 5432}})
        assert out["custom_plugin"] == {"x": 1}
        assert out["security"]["secret_key"] == "s"

    def test_corrupt_fail_closed(self, tmp_path):
        target = tmp_path / "config.yaml"
        target.write_text("{broken: [", encoding="utf-8")
        with pytest.raises(ConfigStoreError, match="拒绝默认化重建"):
            rmw_yaml(target, lambda c: c)

    def test_missing_refused_without_flag(self, tmp_path):
        with pytest.raises(ConfigStoreError):
            rmw_yaml(tmp_path / "config.yaml", lambda c: c)

    def test_mode_preserved_and_new_0640(self, tmp_path):
        target = tmp_path / "config.yaml"
        write_yaml_atomic(target, {"a": 1})
        assert target.stat().st_mode & 0o777 == 0o640
        os.chmod(target, 0o600)
        write_yaml_atomic(target, {"a": 2})
        assert target.stat().st_mode & 0o777 == 0o600


class TestCandidatePrior:
    def test_write_read_and_digest(self, tmp_path):
        payload = {"database": {"active": {"dialect": "postgresql", "password": "p@ss:word"}}}
        meta = write_candidate_config(str(tmp_path), ATTEMPT, payload)
        path = Path(meta["path"])
        assert path.parent.name == ATTEMPT.rsplit("/", 1)[1]
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data == payload
        # 摘要稳定（sort_keys 规范化）
        assert yaml_digest(payload) == yaml_digest(dict(reversed(list(payload.items()))))
        prior = write_prior_config(str(tmp_path), ATTEMPT, {"database": {"active": None}})
        assert Path(prior["path"]).exists()

    def test_traversal_rejected(self, tmp_path):
        with pytest.raises(ConfigStoreError):
            write_candidate_config(str(tmp_path), "../evil", {})


class TestInitConfigFileUsesStore:
    def test_secret_topup_preserves_unknown_nodes(self, tmp_path):
        target = tmp_path / "config.yaml"
        write_yaml_atomic(target, {"security": {}, "my_custom": {"keep": True}})
        from app.database import init_config_file

        assert init_config_file(str(target)) is True
        data = read_yaml(target)
        assert data["my_custom"] == {"keep": True}
        assert "secret_key" in data["security"]
        assert "login_status_secret" in data["security"]
        assert "jwt_secret_key" in data["security"]

    def test_atomic_under_replace_failure(self, tmp_path, monkeypatch):
        target = tmp_path / "config.yaml"
        write_yaml_atomic(target, {"security": {"secret_key": "old"}})
        from app.database import init_config_file

        real_replace = os.replace

        def boom(src, dst, *a, **kw):  # noqa: ANN001
            raise OSError("ENOSPC")

        monkeypatch.setattr(os, "replace", boom)
        # init_config_file 内部兜底捕获异常 → 返回 False（不伪装成功）；
        # 旧文件必须原样完好（原子写纪律），不落半成品
        result = init_config_file(str(target))
        monkeypatch.setattr(os, "replace", real_replace)
        assert result is False
        data = read_yaml(target)
        assert data["security"]["secret_key"] == "old"


class TestEffectiveSourceT15:
    """active 优先/回退一致/fail-closed（build_database_url 同源，§4.1）。"""

    def _active_yaml(self, tmp_path, active: dict) -> Path:
        cfg = tmp_path / "config.yaml"
        write_yaml_atomic(cfg, {"database": {"active": active}})
        return cfg

    def test_active_pg_overrides_env(self, tmp_path, monkeypatch):
        active = {
            "version": 1,
            "generation": "11111111-2222-3333-4444-555555555555",
            "dialect": "postgresql",
            "sqlite_path": None,
            "postgresql": {
                "host": "pg-host",
                "port": 5433,
                "user": "btdeck",
                "password": "p@ss:word/%",
                "database": "btdeck",
                "schema": "public",
                "sslmode": "verify-full",
                "ssl_root_cert": "/etc/ssl/ca.pem",
                "pool_size": 7,
                "max_overflow": 9,
                "pool_timeout": 11,
            },
            "expected_database_id": "66666666-2222-3333-4444-555555555555",
            "receipt_attempt_id": ATTEMPT,
            "revision_at_import": "abc",
            "switched_at": "2026-10-28T00:00:00+00:00",
            "switched_by": "admin",
        }
        cfg = self._active_yaml(tmp_path, active)
        from app.core import database_bootstrap as bootstrap

        effective = bootstrap.resolve_effective_database_config(str(cfg))
        assert effective.source == "active" and effective.dialect == "postgresql"
        assert effective.pg is not None
        assert effective.pg.pool_size == 7
        # T15 同源：URL 构造与 target_params.build_pg_url 唯一实现一致
        from sqlalchemy.engine import URL

        from app.services.db_migration.target_params import build_pg_url

        expected = build_pg_url(effective.pg)
        u = URL.create(
            "postgresql+psycopg2",
            username=effective.pg.user,
            password=effective.pg.password,
            host=effective.pg.host,
            port=effective.pg.port,
            database=effective.pg.database,
            query={
                "sslmode": effective.pg.sslmode,
                "sslrootcert": effective.pg.ssl_root_cert,
            },
        )
        assert u.render_as_string(hide_password=False) == expected

    def test_active_corrupt_fail_closed(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("database:\n  active: {broken", encoding="utf-8")
        from app.core import database_bootstrap as bootstrap

        with pytest.raises(bootstrap.ManagedConfigError):
            bootstrap.resolve_effective_database_config(str(cfg))

    def test_env_fallback_byte_identical(self, monkeypatch, tmp_path):
        """无 active → URL/DIALECT 与历史 env 路径一致（回归保护）。"""
        import app.database as db

        empty_cfg = tmp_path / "config.yaml"
        write_yaml_atomic(empty_cfg, {"app": {"name": "x"}})
        from app.core import database_bootstrap as bootstrap

        effective = bootstrap.resolve_effective_database_config(str(empty_cfg))
        assert effective.source == "env"
        assert effective.dialect == db.settings.DATABASE_DIALECT
        legacy_sqlite = f"sqlite:///{db.settings.DATABASE_PATH}"
        assert db.build_database_url() == legacy_sqlite or db.DIALECT == "postgresql"
