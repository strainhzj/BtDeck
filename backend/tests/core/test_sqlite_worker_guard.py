# -*- coding: utf-8 -*-
"""
SQLite 单 Worker 启动约束（W2-4 / P0-06）测试

验证 startup_guard 的纯函数契约与两个启动入口的 fail-fast 接线：
1. SQLite + WORKERS=1 校验通过；WORKERS=2 / 0 / 负数失败（错误信息可操作）
2. PostgreSQL / MySQL URL 不被 SQLite 检查误杀；scheduler 多实例保护有显式状态
3. WORKERS 解析：未设置视为 1；非整数 fail-fast
4. 启动清单日志字段 database_backend / worker_count / scheduler_enabled / process_id
5. btdeck_startup.sh 与 app/main.py 启动路径的 fail-fast（子进程验证，不拉起真实多进程服务）

测试策略：优先纯函数测试；启动入口用子进程只验证"失败路径"（WORKERS=2 等），
进程在 exec uvicorn 之前即 exit 1，不会真正拉起多进程服务。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.startup_guard import (
    BACKEND_MYSQL,
    BACKEND_OTHER,
    BACKEND_POSTGRES,
    BACKEND_SQLITE,
    StartupGuardError,
    detect_backend,
    log_startup_manifest,
    parse_worker_count,
    resolve_database_url,
    resolve_runtime_info,
    validate_from_env,
    validate_scheduler_scope,
    validate_worker_count,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
STARTUP_SCRIPT = BACKEND_ROOT / "btdeck_startup.sh"


class TestDetectBackend:
    """数据库 URL → 后端类型解析。"""

    @pytest.mark.parametrize(
        "url",
        [None, "", "   ", "sqlite:////data/app.db", "sqlite+aiosqlite:///data/app.db", "sqlite3:///data/app.db"],
    )
    def test_sqlite_urls(self, url):
        assert detect_backend(url) == BACKEND_SQLITE

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://user:pass@host/db",
            "postgres://user:pass@host/db",
            "postgresql+asyncpg://user:pass@host/db",
        ],
    )
    def test_postgres_urls(self, url):
        assert detect_backend(url) == BACKEND_POSTGRES

    @pytest.mark.parametrize("url", ["mysql://u:p@h/db", "mysql+pymysql://u:p@h/db", "mariadb://u:p@h/db"])
    def test_mysql_urls(self, url):
        assert detect_backend(url) == BACKEND_MYSQL

    def test_unknown_backend(self):
        assert detect_backend("mssql://u:p@h/db") == BACKEND_OTHER


class TestParseWorkerCount:
    """WORKERS 环境变量解析。"""

    def test_missing_or_empty_defaults_to_one(self):
        assert parse_worker_count(None) == 1
        assert parse_worker_count("") == 1
        assert parse_worker_count("  ") == 1

    def test_valid_integer(self):
        assert parse_worker_count("1") == 1
        assert parse_worker_count(" 2 ") == 2

    def test_non_integer_fails_fast(self):
        with pytest.raises(StartupGuardError, match="WORKERS"):
            parse_worker_count("abc")
        with pytest.raises(StartupGuardError, match="WORKERS"):
            parse_worker_count("2.5")


class TestValidateWorkerCount:
    """核心校验：SQLite 单 Worker 约束。"""

    def test_sqlite_single_worker_passes(self):
        validate_worker_count(BACKEND_SQLITE, 1)  # 不应抛异常

    def test_sqlite_two_workers_fails(self):
        with pytest.raises(StartupGuardError, match="WORKERS=2"):
            validate_worker_count(BACKEND_SQLITE, 2)

    @pytest.mark.parametrize("workers", [0, -1, -5])
    def test_sqlite_invalid_worker_count_fails(self, workers):
        with pytest.raises(StartupGuardError, match="请改为 1"):
            validate_worker_count(BACKEND_SQLITE, workers)

    def test_error_message_is_actionable(self):
        with pytest.raises(StartupGuardError) as exc_info:
            validate_worker_count(BACKEND_SQLITE, 2)
        msg = str(exc_info.value)
        assert "SQLite 后端禁止多 Worker 启动" in msg
        assert "WORKERS=2" in msg
        assert "请改为 1" in msg
        assert "不能通过启动多个 SQLite Worker 缓解接口卡顿" in msg

    @pytest.mark.parametrize("backend", [BACKEND_POSTGRES, BACKEND_MYSQL, BACKEND_OTHER])
    @pytest.mark.parametrize("workers", [2, 4])
    def test_non_sqlite_backends_not_blocked(self, backend, workers):
        validate_worker_count(backend, workers)  # 不应被 SQLite 检查误杀

    def test_non_integer_worker_count_fails(self):
        with pytest.raises(StartupGuardError, match="WORKERS"):
            validate_worker_count(BACKEND_SQLITE, "2")  # type: ignore[arg-type]


class TestResolveDatabaseUrl:
    """DATABASE_URL 实际生效优先级解析。"""

    def test_database_url_precedence(self):
        url = resolve_database_url({"DATABASE_URL": "postgresql://x/db", "DATABASE_PATH": "/tmp/a.db"})
        assert url == "postgresql://x/db"

    def test_database_path_fallback(self):
        url = resolve_database_url({"DATABASE_PATH": "/tmp/a.db"})
        assert url == "sqlite:////tmp/a.db"

    def test_empty_when_unset(self):
        assert resolve_database_url({}) == ""


class TestValidateFromEnv:
    """环境变量 → 校验（与 main.py 接线点同源）。"""

    def test_sqlite_workers_one_env_passes(self):
        backend, workers, scheduler_enabled = validate_from_env({"WORKERS": "1"})
        assert backend == BACKEND_SQLITE
        assert workers == 1
        assert scheduler_enabled is True

    def test_workers_env_missing_means_one(self):
        backend, workers, _ = validate_from_env({})
        assert backend == BACKEND_SQLITE
        assert workers == 1

    def test_sqlite_workers_two_env_fails(self):
        with pytest.raises(StartupGuardError, match="WORKERS=2"):
            validate_from_env({"WORKERS": "2"})

    def test_sqlite_workers_zero_env_fails(self):
        with pytest.raises(StartupGuardError, match="WORKERS=0"):
            validate_from_env({"WORKERS": "0"})

    def test_postgresql_url_not_blocked(self):
        backend, workers, _ = validate_from_env({"DATABASE_URL": "postgresql://user:pass@host/db", "WORKERS": "2"})
        assert backend == BACKEND_POSTGRES
        assert workers == 2

    def test_mysql_url_not_blocked(self):
        backend, workers, _ = validate_from_env({"DATABASE_URL": "mysql+pymysql://u:p@h/db", "WORKERS": "4"})
        assert backend == BACKEND_MYSQL
        assert workers == 4

    def test_scheduler_enabled_flag_parsed(self):
        _, _, enabled = validate_from_env({"SCHEDULER_ENABLED": "0"})
        assert enabled is False

    def test_database_path_fallback_resolves_sqlite(self):
        backend, _, _ = validate_from_env({"DATABASE_PATH": "/tmp/test/app.db", "WORKERS": "1"})
        assert backend == BACKEND_SQLITE


class TestValidateSchedulerScope:
    """scheduler 单实例纵深防御（W2-4 第 4 条）。"""

    def test_sqlite_single_worker_ok(self):
        msg = validate_scheduler_scope(BACKEND_SQLITE, 1)
        assert "单实例安全" in msg

    def test_sqlite_multi_worker_blocked(self):
        with pytest.raises(StartupGuardError, match="拒绝启动"):
            validate_scheduler_scope(BACKEND_SQLITE, 2)

    def test_postgres_multi_worker_leader_not_implemented(self):
        msg = validate_scheduler_scope(BACKEND_POSTGRES, 2)
        assert "Leader 未实现" in msg

    def test_postgres_single_worker_ok(self):
        validate_scheduler_scope(BACKEND_POSTGRES, 1)  # 不应抛异常

    def test_other_backend_ok(self):
        validate_scheduler_scope(BACKEND_OTHER, 4)  # 不应抛异常


class TestStartupManifestLog:
    """启动清单日志字段断言（参照仓库 spy logger 模式，避免全量 pytest 下 caplog 传播污染）。"""

    @staticmethod
    def _rendered(mock_call) -> str:
        args = mock_call.args
        if not args:
            return ""
        if len(args) == 1:
            return str(args[0])
        return str(args[0]) % args[1:]

    def test_manifest_log_contains_required_fields(self):
        with patch("app.core.startup_guard.logger") as mock_logger:
            log_startup_manifest(BACKEND_SQLITE, 1, True, process_id=4242)

        assert mock_logger.info.call_count == 1
        msg = self._rendered(mock_logger.info.call_args)
        assert "database_backend=sqlite" in msg
        assert "worker_count=1" in msg
        assert "scheduler_enabled=True" in msg
        assert "process_id=4242" in msg

    def test_manifest_uses_real_pid_by_default(self):
        with patch("app.core.startup_guard.logger") as mock_logger:
            log_startup_manifest(BACKEND_SQLITE, 1, True)

        msg = self._rendered(mock_logger.info.call_args)
        assert f"process_id={os.getpid()}" in msg

    # 注：不用 caplog 断言真实日志通道——仓库会话级 fixture 会执行 alembic
    # upgrade，alembic/env.py 的 fileConfig(disable_existing_loggers=True) 会把
    # 已存在的 app.* logger 全部 disabled（本 logger 级别=0 且 disabled=True），
    # caplog 永远抓不到；这是仓库既有现象，spy logger 模式（见
    # tests/services/test_downloader_api_runtime.py）即为此设计。


def _find_git_bash() -> str:
    """定位 Git Bash 的 bash.exe。

    Windows 上 PATH 中的 bash.exe 可能是 WSL 转发器（System32\\bash.exe），
    子进程调用会报 "execvpe(/bin/bash) failed"，不可用。
    优先从 git 安装目录推导（E:/Git/usr/bin/bash.exe 或 bin/bash.exe）。
    """
    candidates: list = []
    git_exe = shutil.which("git")
    if git_exe:
        git_bin = Path(git_exe).resolve()
        for git_root in (git_bin.parents[2], git_bin.parents[1]):
            candidates.append(git_root / "bin" / "bash.exe")
            candidates.append(git_root / "usr" / "bin" / "bash.exe")
    for extra in (
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path("C:/Program Files (x86)/Git/bin/bash.exe"),
        # 本机常见 Git 安装位置（PATH 中无 git 时兜底，实测 E:/Git 部署）
        Path("E:/Git/bin/bash.exe"),
        Path("E:/Git/usr/bin/bash.exe"),
        Path("D:/Git/bin/bash.exe"),
        Path("D:/Git/usr/bin/bash.exe"),
    ):
        candidates.append(extra)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "bash"  # 兜底：交给 PATH 解析（非 Windows 环境）


class TestStartupEntryPoints:
    """两个启动入口的 fail-fast 接线（子进程，只验证失败路径，不拉起真实多进程服务）。"""

    @pytest.mark.parametrize("workers", ["2", "0", "-1"])
    def test_startup_script_fails_fast_on_sqlite_multi_worker(self, tmp_path, workers):
        """btdeck_startup.sh：SQLite + WORKERS!=1 必须在 exec uvicorn 前 exit 1。"""
        env = dict(os.environ)
        env["WORKERS"] = workers
        env["LOG_DIR"] = str(tmp_path)
        env.pop("DATABASE_URL", None)
        result = subprocess.run(
            [_find_git_bash(), str(STARTUP_SCRIPT)],
            cwd=str(BACKEND_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert result.returncode == 1, (
            f"WORKERS={workers} 应 fail-fast exit 1，实际 rc={result.returncode} "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        output = result.stdout + result.stderr
        assert "多 Worker" in output
        assert f"WORKERS={workers}" in output

    def test_main_python_entry_fails_fast_on_multi_worker(self, tmp_path):
        """app/main.py 模块加载期校验：WORKERS=2 时 import app.main 必须失败（fail-fast）。"""
        env = self._python_env(tmp_path)
        env["WORKERS"] = "2"
        result = subprocess.run(
            [sys.executable, "-c", "import app.main"],
            cwd=str(BACKEND_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode != 0, "WORKERS=2 时 import app.main 应失败（fail-fast）"
        assert "SQLite 后端禁止多 Worker 启动" in result.stderr

    def test_main_python_entry_default_workers_one_passes(self, tmp_path):
        """app/main.py 直接运行路径：WORKERS 未设置视为 1，模块加载不失败。"""
        env = self._python_env(tmp_path)
        env.pop("WORKERS", None)
        result = subprocess.run(
            [sys.executable, "-c", "import app.main"],
            cwd=str(BACKEND_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"默认 WORKERS=1 应通过校验，stderr={result.stderr!r}"

    @staticmethod
    def _python_env(tmp_path) -> dict:
        """构造隔离的子进程环境（测试库路径 + 测试密钥，不指向开发数据库）。"""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(BACKEND_ROOT)
        env["CONFIG_DIR"] = str(tmp_path / "config")
        env["DATABASE_PATH"] = str(tmp_path / "app.db")
        env["BTDECK_TESTING"] = "1"
        env.setdefault("SECRET_KEY", "btdeck-test-secret")
        env.pop("DATABASE_URL", None)
        env.pop("WORKERS", None)
        return env


def test_resolve_runtime_info_reads_real_env(monkeypatch):
    """resolve_runtime_info 默认读取进程环境（scheduler_enabled 默认 True）。"""
    monkeypatch.setenv("WORKERS", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    backend, workers, scheduler_enabled = resolve_runtime_info()
    assert backend == BACKEND_SQLITE
    assert workers == 1
    assert scheduler_enabled is True
