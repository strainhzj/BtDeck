"""SQLite→PG 迁移工具单元测试（v1.0.8 任务4.1）。

不依赖真实 PG：预检/行变换为纯 SQLite 逻辑；导入与对账编排用 SQLite 文件库
替身目标（pg_baseline 基线建表后经 SQLAlchemy Core 写入——引擎无关路径）。
真实 PG 端到端归 P4.3 强制 CI。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pytest

from scripts.migrate_sqlite_to_pg import (
    _JSON_CONTRACT,
    check_boolean_columns,
    check_datetime_text,
    check_json_contract,
    import_table,
    precheck,
    report_softdelete_duplicates,
    row_transform,
    verify_counts_and_digests,
)


@pytest.fixture(scope="module")
def source_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """链 head schema + 样本数据的源库（模块级复用，只读消费）。"""
    import os

    from alembic import command
    from alembic.config import Config

    db = tmp_path_factory.mktemp("src") / "app.db"
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.attributes["configure_logger"] = False
    os.environ["DATABASE_PATH"] = str(db)
    command.upgrade(cfg, "head")

    conn = sqlite3.connect(db)
    conn.executemany(
        "INSERT INTO users (username, password, two_factor_secret, two_factor_flag, is_active, created_at, must_change_password) "
        "VALUES (?,?,?,?,?,datetime('now'),0)",
        [(f"u{i}", "x", "s", 0, 1 if i % 2 else 0) for i in range(5)],
    )
    conn.execute(
        "INSERT INTO orphan_purge_job (task_id, status, operation_type, orphan_ids_json, canonical_paths_json, created_at, operator, total_count, updated_at) "
        "VALUES ('t1','pending','cleanup','[1,2,3]','[]',datetime('now'),'admin',3,datetime('now'))"
    )
    conn.execute(
        "INSERT INTO orphan_purge_job (task_id, status, operation_type, orphan_ids_json, canonical_paths_json, created_at, operator, total_count, updated_at) "
        "VALUES ('t2','pending','purge',NULL,'[\"/a/b\",\"/c\"]',datetime('now'),'admin',2,datetime('now'))"
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def source_conn(source_db: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    yield conn
    conn.close()


class TestJsonContract:
    """契约 §4.3 按字段：整数 ID / 字符串路径 / PURGE 任务 orphan_ids_json 合法 NULL。"""

    def test_valid_data_passes(self, source_conn: sqlite3.Connection) -> None:
        errors, _ = check_json_contract(source_conn)
        assert errors == []

    def test_purge_null_is_legal(self, source_conn: sqlite3.Connection) -> None:
        """PURGE 任务 orphan_ids_json=NULL 是合法状态（不判损坏）。"""
        # source_db 已含该行且 check 通过即证；此处显式断言契约表内容
        assert "orphan_purge_job.orphan_ids_json" in _JSON_CONTRACT

    def test_bare_scalar_rejected_without_flag(self, tmp_path: Path) -> None:
        db = _copy_source(tmp_path)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO orphan_purge_job (id,task_id,status,operation_type,orphan_ids_json,created_at) "
            "VALUES (9,'t9','pending','cleanup','42',datetime('now'))"
        )
        conn.commit()
        conn.close()
        errors, _ = check_json_contract(sqlite3.connect(db))
        assert any("裸标量" in e for e in errors)

    def test_bare_scalar_warns_with_autowrap(self, tmp_path: Path) -> None:
        db = _copy_source(tmp_path)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO orphan_purge_job (id,task_id,status,operation_type,canonical_paths_json,created_at) "
            "VALUES (9,'t9','pending','purge','\"/single/path\"',datetime('now'))"
        )
        conn.commit()
        conn.close()
        errors, warnings = check_json_contract(sqlite3.connect(db), auto_wrap=True)
        assert not errors
        assert any("裸标量" in w for w in warnings)

    def test_object_rejected_even_with_autowrap(self, tmp_path: Path) -> None:
        """对象/错误类型套数组不修复语义——恒拒绝（审查第 3/4 轮定案）。"""
        db = _copy_source(tmp_path)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO orphan_purge_job (id,task_id,status,operation_type,orphan_ids_json,created_at) "
            "VALUES (9,'t9','pending','cleanup','{\"a\":1}',datetime('now'))"
        )
        conn.commit()
        conn.close()
        errors, _ = check_json_contract(sqlite3.connect(db), auto_wrap=True)
        assert any("契约违规" in e for e in errors)

    def test_boolean_element_rejected(self, tmp_path: Path) -> None:
        """整数元素排除布尔（bool 是 int 子类）。"""
        db = _copy_source(tmp_path)
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO orphan_purge_job (id,task_id,status,operation_type,orphan_ids_json,created_at) "
            "VALUES (9,'t9','pending','cleanup','[true]',datetime('now'))"
        )
        conn.commit()
        conn.close()
        errors, _ = check_json_contract(sqlite3.connect(db))
        assert any("非整数元素" in e for e in errors)


def _copy_source(tmp_path: Path) -> Path:
    """JSON 契约测试用最小独立库（仅 orphan_purge_job，避免整链构建开销）。"""
    db = tmp_path / "json_contract.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE orphan_purge_job (id INTEGER PRIMARY KEY, task_id TEXT, status TEXT, "
        "operation_type TEXT, orphan_ids_json TEXT, canonical_paths_json TEXT, created_at DATETIME)"
    )
    conn.commit()
    conn.close()
    return db


class TestPrecheckChecks:
    def test_boolean_domain(self, source_conn: sqlite3.Connection) -> None:
        assert check_boolean_columns(source_conn) == []

    def test_datetime_text(self, source_conn: sqlite3.Connection) -> None:
        assert check_datetime_text(source_conn) == []

    def test_softdelete_report_is_warning_not_error(self, source_conn: sqlite3.Connection) -> None:
        warnings = report_softdelete_duplicates(source_conn)
        assert isinstance(warnings, list)

    def test_precheck_reports_version(self, source_db: Path) -> None:
        errors, _, version = precheck(str(source_db))
        assert errors == []
        assert version == "c9e0f1a2b3c4"


class TestRowTransform:
    def test_transform_bool_and_datetime(self) -> None:
        from app.core.model_registry import register_all_models
        from app.database import Base

        register_all_models()
        users = Base.metadata.tables["users"]

        class _FakeRow:
            keys = lambda self: ["id", "is_active", "created_at"]  # noqa: E731

            def __getitem__(self, k: str) -> Any:
                return {"id": 1, "is_active": 1, "created_at": "2026-09-30 12:00:00.123456"}[k]

        out = row_transform(users, _FakeRow())
        assert out["is_active"] is True  # int 0/1 → bool（psycopg2 直发 int 会被 PG 拒绝）
        assert out["created_at"].year == 2026  # 文本 → datetime
        assert out["id"] == 1


class TestImportAndVerify:
    """导入 + 检查点 + 对账编排（SQLite 替身目标，SQLAlchemy Core 引擎无关路径）。"""

    def test_import_and_verify_roundtrip(
        self, source_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy import create_engine

        from app.core import pg_baseline
        from app.core.model_registry import register_all_models
        from app.database import Base

        target_path = tmp_path / "target.db"
        target_engine = create_engine(f"sqlite:///{target_path}")

        # 基线建表（复用 pg_baseline：共享单事务 create_all + stamp）
        monkeypatch.setattr(pg_baseline, "pg_sync_engine", lambda: target_engine)
        from alembic.config import Config

        cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
        cfg.attributes["configure_logger"] = False
        assert pg_baseline.initialize_pg_baseline(cfg, "c9e0f1a2b3c4") is True

        register_all_models()
        sqlite_conn = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
        sqlite_conn.row_factory = sqlite3.Row
        try:
            state = {"completed": {}}
            imported = {}
            for table in Base.metadata.sorted_tables:
                imported[table.name] = import_table(
                    sqlite_conn, target_engine, table, state=state, migration_id="test-mig", source_digest="digest"
                )
            assert imported["users"] == 5
            assert imported["orphan_purge_job"] == 2

            # 检查点已写入（标记表存在且记录完成表数）
            with target_engine.connect() as conn:
                st = pg_baseline.get_import_state(conn)
            assert st is not None and st["migration_id"] == "test-mig"
            assert len(st["checkpoint"]["completed"]) == len(Base.metadata.sorted_tables)

            # 对账通过
            problems = verify_counts_and_digests(sqlite_conn, target_engine, Base.metadata.sorted_tables)
            assert problems == []

            # 布尔/JSON 契约数据落库正确
            with target_engine.connect() as conn:
                assert conn.exec_driver_sql("SELECT COUNT(*) FROM users WHERE is_active = 1").scalar() == 2
                raw = conn.exec_driver_sql(
                    "SELECT orphan_ids_json, canonical_paths_json FROM orphan_purge_job WHERE task_id = 't2'"
                ).fetchone()
                assert raw[0] is None and json.loads(raw[1]) == ["/a/b", "/c"]
        finally:
            sqlite_conn.close()
            target_engine.dispose()
