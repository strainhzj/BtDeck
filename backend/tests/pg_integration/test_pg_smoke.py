"""真实 PostgreSQL 集成测试（v1.0.8 任务4.3 强制 CI 覆盖）。

门控：仅在 ``DB_TYPE=postgresql`` 且 ``BTDECK_PG_TEST_ADMIN_DSN`` 提供时执行
（CI 由 postgres:16 service 容器注入；本地需自备 PG）。每个用例独占一个
全新数据库（admin 连接按需建删），互不污染。

覆盖矩阵（PLANS/v1.0.8.md 任务4.3 七类中的 PG 侧六类；SQLite 全量回归
由既有 regression.yml backend job 覆盖）：
1. PG 空库初始化（squash 基线）/ 重复启动幂等 / head no-op
2. 真实 PG 同步 + 异步查询
3. 活动/软删 upsert（partial index 仲裁）
4. 搜索语义（LIKE A–Z 折叠）与超时恢复（statement_timeout 取消 → rollback 映射）
5. 孤儿占用排除（JSON 数组展开）/ 分组（父目录表达式）/ 租约（ON CONFLICT DO NOTHING）
6. 迁移工具端到端（导入/核对/sequence 校准后新增写入/目标库复用拒绝）
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest

# 门控：进程须以 DB_TYPE=postgresql 启动（app.database.DIALECT 为导入时常量），
# 且提供 admin DSN（建删测试库用）。
_ADMIN_DSN = os.getenv("BTDECK_PG_TEST_ADMIN_DSN", "")
pytestmark = pytest.mark.skipif(
    os.getenv("DB_TYPE", "sqlite") != "postgresql" or not _ADMIN_DSN,
    reason="PG 集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def fresh_pg_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """每用例独占全新数据库：admin 建 → 供测试 → admin 删。yield DSN（非 URL）。"""
    import psycopg2

    from app.core import config as config_mod

    db_name = f"btdeck_test_{uuid.uuid4().hex[:10]}"
    admin = psycopg2.connect(_ADMIN_DSN)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"CREATE DATABASE {db_name}")
    admin.close()
    # 定向覆盖 settings.DB_NAME（build_database_url 每次调用现读 settings）
    monkeypatch.setattr(config_mod.settings, "DB_NAME", db_name)
    try:
        yield db_name
    finally:
        admin = psycopg2.connect(_ADMIN_DSN)
        admin.autocommit = True
        # 强制断开残余连接后删除（测试自身引擎应已 dispose）
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
        admin.close()


def _make_cfg() -> Any:
    from alembic.config import Config

    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


class TestBaselineLifecycle:
    """覆盖 1：空库基线 / 重复启动幂等 / migrate_database 编排。"""

    def test_baseline_init_idempotent_and_migrate_noop(self, fresh_pg_db: str) -> None:
        from app.core import pg_baseline
        from app.core.migration import _migrate_database_pg

        head = "c9e0f1a2b3c4"
        # 首次：空库 → 基线（建全表 + stamp）
        assert pg_baseline.initialize_pg_baseline(_make_cfg(), head) is True
        # 重复启动：已 versioned → 跳过（幂等）
        assert pg_baseline.initialize_pg_baseline(_make_cfg(), head) is False
        # 编排入口：head no-op 返回 True
        assert _migrate_database_pg() is True

        engine = pg_baseline.pg_sync_engine()
        try:
            with engine.connect() as conn:
                tables = {t for t in pg_baseline._business_table_names(conn)}
                assert "torrent_info" in tables and "users" in tables
                assert pg_baseline.read_pg_alembic_version(conn) == head
        finally:
            engine.dispose()

    def test_guard_rejects_manual_upgrade_on_empty_db(self, fresh_pg_db: str) -> None:
        """env.py 守卫：空库手工 upgrade 拒绝（真实 PG 连接）。"""
        from app.core import pg_baseline

        engine = pg_baseline.pg_sync_engine()
        try:
            with engine.connect() as conn:
                with pytest.raises(RuntimeError, match="禁止手工 alembic upgrade"):
                    pg_baseline.guard_manual_upgrade_on_empty_db(conn)
        finally:
            engine.dispose()


class TestSyncAsyncQueries:
    """覆盖 2：真实 PG 同步 + 异步查询（psycopg2/asyncpg 双驱动）。"""

    def test_sync_insert_async_read(self, fresh_pg_db: str) -> None:
        import asyncio

        from sqlalchemy import select

        from app.core.model_registry import register_all_models
        from app.database import AsyncSessionLocal, SessionLocal

        register_all_models()
        from app.auth.models import User

        probe_name = f"pg_probe_{uuid.uuid4().hex[:8]}"  # 会话库跨运行残留 → 唯一用户名
        db = SessionLocal()
        try:
            db.add(User(username=probe_name, password="x", is_active=True, must_change_password=False))
            db.commit()
        finally:
            db.close()

        async def _read() -> str | None:
            async with AsyncSessionLocal() as session:
                row = (
                    await session.execute(select(User.username).where(User.username == probe_name))
                ).scalar_one_or_none()
                return row

        assert asyncio.run(_read()) == probe_name


class TestUpsertPartialIndex:
    """覆盖 3：活动/软删 upsert 仲裁（postgresql_where 部分唯一索引）。"""

    def test_softdelete_coexist_and_upsert(self, fresh_pg_db: str) -> None:
        from sqlalchemy import text as sa_text

        from app.core.dialect_sql import dialect_insert
        from app.core import pg_baseline
        from app.core.model_registry import register_all_models
        from app.database import Base

        register_all_models()
        engine = pg_baseline.pg_sync_engine()
        from alembic import command

        cfg = _make_cfg()
        cfg.attributes["btdeck_baseline_stamp"] = True
        # 基线建表（含 postgresql_where 部分唯一索引）
        with engine.connect() as conn:
            conn.rollback()
            with conn.begin():
                Base.metadata.create_all(conn)
                cfg.attributes["connection"] = conn
                command.stamp(cfg, "c9e0f1a2b3c4", purge=True)
                cfg.attributes.pop("connection", None)

        tracker = Base.metadata.tables["tracker_info"]
        row = {
            "tracker_id": "tk-1",
            "torrent_info_id": "tpk1",
            "tracker_url": "http://tracker.example/announce",
            "tracker_name": "t",
            "dr": 0,
        }
        try:
            with engine.begin() as conn:
                conn.execute(tracker.insert(), row)
                # 软删同键：dr=1 行与活动行共存（partial index 仅约束 dr=0）
                conn.execute(tracker.insert(), {**row, "tracker_id": "tk-2", "dr": 1})
                # upsert 仲裁：on_conflict_do_update 命中 dr=0 部分索引
                stmt = (
                    dialect_insert(tracker)
                    .values({**row, "tracker_id": "tk-1", "tracker_name": "t2"})
                    .on_conflict_do_update(
                        index_elements=["torrent_info_id", "tracker_url"],
                        index_where=sa_text("dr = 0"),
                        set_={"tracker_name": sa_text("excluded.tracker_name")},
                    )
                )
                conn.execute(stmt)
            with engine.connect() as conn:
                names = [r[0] for r in conn.execute(sa_text("SELECT tracker_name FROM tracker_info WHERE dr = 0"))]
                assert names == ["t2"]  # upsert 更新而非插入
        finally:
            engine.dispose()


class TestSearchSemanticsAndTimeout:
    """覆盖 4：LIKE A–Z 折叠语义 + statement_timeout 取消恢复。"""

    def test_ci_like_ascii_folding(self, fresh_pg_db: str) -> None:
        from sqlalchemy import literal, select

        from app.core import pg_baseline
        from app.core.dialect_sql import ci_contains

        engine = pg_baseline.pg_sync_engine()
        try:
            with engine.connect() as conn:
                # 'MOVIE' 与搜索值 'movie' 经同一 A–Z 折叠后命中
                got = conn.execute(select(ci_contains(literal("My-MOVIE-File"), "movie"))).scalar()
                assert got is True
                # 非 ASCII 不折叠（登记差异 §6 第 3 条）
                got_nonascii = conn.execute(select(ci_contains(literal("ÉCOLE"), "école"))).scalar()
                assert got_nonascii is False
        finally:
            engine.dispose()

    def test_regex_budget_cancellation_and_rollback(self, fresh_pg_db: str) -> None:
        from sqlalchemy import text as sa_text
        from sqlalchemy.exc import OperationalError

        from app.core import pg_baseline
        from app.services.pg_search_runtime import PgRegexBudget, is_query_cancelled_error
        from app.services.sqlite_search_runtime import RegexSearchTimeout

        engine = pg_baseline.pg_sync_engine()
        try:
            with engine.connect() as conn:
                budget = PgRegexBudget(conn, seconds=0.05)
                budget.arm()
                with pytest.raises(OperationalError) as exc_info:
                    conn.execute(sa_text("SELECT pg_sleep(2)")).fetchall()
                assert is_query_cancelled_error(exc_info.value.orig) or is_query_cancelled_error(exc_info.value)
                # 取消后事务 abort：rollback 恢复连接可用（契约 §4.2 错误映射路径）
                conn.rollback()
                assert conn.execute(sa_text("SELECT 1")).scalar() == 1
                # 剩余预算 ≤0：直接终止不发 SQL（禁写 statement_timeout=0）
                budget.deadline = 0.0
                with pytest.raises(RegexSearchTimeout):
                    budget.arm()
        finally:
            engine.dispose()


class TestOrphanSemantics:
    """覆盖 5：JSON 占用排除 / 父目录分组 / 租约。"""

    def test_json_array_exclusion_and_parent_dir_grouping(self, fresh_pg_db: str) -> None:
        import json as _json

        from sqlalchemy import Integer, cast, select, true

        from app.core import pg_baseline
        from app.core.dialect_sql import json_array_values, orphan_parent_dir_expr
        from app.core.model_registry import register_all_models
        from app.database import Base
        from alembic import command

        register_all_models()
        engine = pg_baseline.pg_sync_engine()
        cfg = _make_cfg()
        cfg.attributes["btdeck_baseline_stamp"] = True
        with engine.connect() as conn:
            conn.rollback()
            with conn.begin():
                Base.metadata.create_all(conn)
                cfg.attributes["connection"] = conn
                command.stamp(cfg, "c9e0f1a2b3c4", purge=True)
                cfg.attributes.pop("connection", None)
        job = Base.metadata.tables["orphan_purge_job"]
        orphan = Base.metadata.tables["orphan_file"]
        scan = Base.metadata.tables["orphan_scan_result"]
        try:
            with engine.begin() as conn:
                # scan_id 外键指向 orphan_scan_result：先建扫描行
                from datetime import datetime as _dt

                conn.execute(
                    scan.insert(),
                    {"scan_id": 1, "scan_time": _dt.utcnow(), "scan_type": "full"},
                )
                conn.execute(
                    job.insert(),
                    {
                        "task_id": "j1",
                        "status": "pending",
                        "operation_type": "cleanup",
                        "orphan_ids_json": _json.dumps([1, 2, 3]),
                        "canonical_paths_json": "[]",
                        "operator": "admin",
                        "total_count": 3,
                    },
                )
                conn.execute(
                    orphan.insert(),
                    [
                        {"scan_id": 1, "file_path": "C:\\media\\a.mkv", "canonical_path": "/c/media/a.mkv"},
                        {"scan_id": 1, "file_path": "C:\\media\\b.mkv", "canonical_path": "/c/media/b.mkv"},
                        {"scan_id": 1, "file_path": "/media/c.mkv", "canonical_path": "/media/c.mkv"},
                    ],
                )
            values = json_array_values(job.c.orphan_ids_json, "occupied")
            with engine.connect() as conn:
                ids = [
                    r[0]
                    for r in conn.execute(
                        select(cast(values.c.value, Integer)).select_from(job).join(values, true())
                    ).fetchall()
                ]
                assert sorted(int(i) for i in ids) == [1, 2, 3]
                groups = sorted(
                    r[0] for r in conn.execute(select(orphan_parent_dir_expr(orphan.c.file_path)).distinct()).fetchall()
                )
                # 反斜杠归一 + 末段剥离（契约矩阵）
                assert groups == ["/media", "C:/media"]
        finally:
            engine.dispose()

    def test_lease_conflict_do_nothing(self, fresh_pg_db: str) -> None:
        from datetime import datetime, timedelta

        # orphan_lease 的 ON CONFLICT DO NOTHING SQL 语义在此直接验证（_get_db 走 AsyncSessionLocal）
        from app.core import pg_baseline
        from app.core.model_registry import register_all_models
        from app.database import Base
        from alembic import command
        from sqlalchemy import text as sa_text

        register_all_models()
        engine = pg_baseline.pg_sync_engine()
        cfg = _make_cfg()
        cfg.attributes["btdeck_baseline_stamp"] = True
        with engine.connect() as conn:
            conn.rollback()
            with conn.begin():
                Base.metadata.create_all(conn)
                cfg.attributes["connection"] = conn
                command.stamp(cfg, "c9e0f1a2b3c4", purge=True)
                cfg.attributes.pop("connection", None)
        now = datetime.utcnow()
        try:
            with engine.begin() as conn:
                conn.execute(
                    sa_text(
                        "INSERT INTO orphan_operation_lease (lease_key, owner, acquired_at, expires_at) "
                        "VALUES ('scan', 'owner-a', :now, :exp) ON CONFLICT (lease_key) DO NOTHING"
                    ),
                    {"now": now, "exp": now + timedelta(seconds=60)},
                )
                result = conn.execute(
                    sa_text(
                        "INSERT INTO orphan_operation_lease (lease_key, owner, acquired_at, expires_at) "
                        "VALUES ('scan', 'owner-b', :now, :exp) ON CONFLICT (lease_key) DO NOTHING"
                    ),
                    {"now": now, "exp": now + timedelta(seconds=60)},
                )
                assert result.rowcount == 0  # 二者冲突：DO NOTHING 不插入
        finally:
            engine.dispose()


class TestMigrationToolEndToEnd:
    """覆盖 6：迁移工具端到端（导入/核对/sequence 校准后新增/目标复用拒绝）。"""

    def test_full_migration_and_sequence_continuation(self, fresh_pg_db: str, tmp_path: Path) -> None:
        import os as _os

        from alembic import command

        from scripts.migrate_sqlite_to_pg import main as migrate_main

        # 构建 SQLite 源（链 head + 样本：users 自增 PK / notification）。
        # 进程 DB_TYPE=postgresql 下 env.py 会构造 PG URL 撞空库守卫——
        # 源库构建期间定向覆盖 settings.DB_TYPE 使 env.py 走 sqlite 分支
        from app.core import config as _config_mod

        source = tmp_path / "src.db"
        cfg = _make_cfg()
        _os.environ["DATABASE_PATH"] = str(source)
        _orig_db_type = _config_mod.settings.DB_TYPE
        _config_mod.settings.DB_TYPE = "sqlite"
        try:
            command.upgrade(cfg, "head")
        finally:
            _config_mod.settings.DB_TYPE = _orig_db_type
        sconn = sqlite3.connect(source)
        sconn.executemany(
            "INSERT INTO users (username, password, two_factor_secret, two_factor_flag, is_active, created_at, must_change_password) "
            "VALUES (?,?,?,?,?,datetime('now'),0)",
            [(f"u{i}", "x", "s", 0, 1) for i in range(7)],
        )
        sconn.commit()
        sconn.close()

        assert migrate_main(["--source", str(source)]) == 0

        from app.core import pg_baseline
        from app.core.model_registry import register_all_models
        from app.database import Base

        register_all_models()
        users = Base.metadata.tables["users"]
        engine = pg_baseline.pg_sync_engine()
        try:
            with engine.connect() as conn:
                assert conn.execute(sa_text_("SELECT COUNT(*) FROM users")).scalar() == 7
                conn.rollback()  # 读取已 autobegin；显式事务前先释放
                # sequence 校准后新增写入：id 接续 max 而非重启
                with conn.begin():
                    conn.execute(
                        users.insert(),
                        {"username": "u-new", "password": "x", "two_factor_secret": "s", "is_active": True},
                    )
                new_id = conn.execute(sa_text_("SELECT id FROM users WHERE username = 'u-new'")).scalar()
                assert new_id == 8
        finally:
            engine.dispose()

        # 目标库复用拒绝：已有业务数据 → 退出码 2（三状态规则）
        assert migrate_main(["--source", str(source)]) == 2


def sa_text_(s: str) -> Any:
    from sqlalchemy import text

    return text(s)
