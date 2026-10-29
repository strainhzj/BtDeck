# -*- coding: utf-8 -*-
"""真 PG 源 fence 与零写 oracle（database-migration-ui W2-4，PLANS §5.2/§11 T03/T18）。

需要真实 PostgreSQL（regression pg-integration job 提供 DB_TYPE=postgresql +
BTDECK_PG_TEST_ADMIN_DSN；本地无 PG 时整文件 skip——skip 不计通过，证据以
CI 实际执行为准）。

覆盖：
- PgSourceFence：SHARE 锁取得/指纹固定/verify 锁存在/释放后可写；
- SHARE 锁阻塞普通 DML 写者（fence 事务内写入被锁冲突拒绝，有界超时）；
- T18 PG 独立观测：零写窗口通过；阳性对照（同主键同计数 UPDATE）必须失败。
"""

from __future__ import annotations

import pytest

from tests.pg_integration.test_pg_smoke import fresh_pg_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(
    __import__("os").getenv("DB_TYPE", "sqlite") != "postgresql"
    or not __import__("os").getenv("BTDECK_PG_TEST_ADMIN_DSN", ""),
    reason="PG fence 集成测试需要 DB_TYPE=postgresql + BTDECK_PG_TEST_ADMIN_DSN（CI postgres service）",
)

TABLES = ["fence_t"]


@pytest.fixture
def fence_table(fresh_pg_db: str) -> str:
    import os

    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    # 直接复用 admin DSN（含认证信息）；admin DSN 自带管理库名，须经 make_url 替换
    # database 分量（字符串拼接会产生 "postgres/<db>" 非法库名）
    from sqlalchemy.engine.url import make_url

    url = (
        make_url(os.environ["BTDECK_PG_TEST_ADMIN_DSN"]).set(database=fresh_pg_db).render_as_string(hide_password=False)
    )
    engine = create_engine(url, poolclass=NullPool)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fence_t"))
        conn.execute(text("CREATE TABLE fence_t (k TEXT PRIMARY KEY, v INTEGER)"))
        conn.execute(text("INSERT INTO fence_t VALUES ('k1', 1), ('k2', 2)"))
    engine.dispose()
    yield url
    engine = create_engine(url, poolclass=NullPool)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fence_t"))
    engine.dispose()


class TestPgSourceFence:
    def test_acquire_fingerprint_verify_release(self, fence_table: str) -> None:
        from app.services.db_migration.source_fence import PgSourceFence

        fence = PgSourceFence(fence_table, TABLES, lock_timeout_seconds=10)
        fence.acquire()
        try:
            assert fence.token is not None and fence.token.dialect == "postgresql"
            assert fence.verify() is True  # ShareLock 全部在位
            fingerprint = fence.token.fingerprint
        finally:
            fence.release()
        # 释放后可写
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool

        engine = create_engine(fence_table, poolclass=NullPool)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO fence_t VALUES ('k3', 3)"))
        engine.dispose()
        # 重新取锁对拍历史指纹：漂移（行数变化）
        fence2 = PgSourceFence(fence_table, TABLES, lock_timeout_seconds=10)
        fence2.acquire()
        try:
            assert fence2.verify_against(fingerprint) is False
        finally:
            fence2.release()

    def test_share_lock_blocks_dml_writer(self, fence_table: str) -> None:
        """fence 持锁期间普通 DML 写者被锁冲突拒绝（有界 lock_timeout）。"""
        from sqlalchemy import create_engine, text
        import sqlalchemy.exc
        from sqlalchemy.pool import NullPool

        from app.services.db_migration.source_fence import PgSourceFence

        fence = PgSourceFence(fence_table, TABLES, lock_timeout_seconds=10)
        fence.acquire()
        try:
            engine = create_engine(fence_table, poolclass=NullPool)
            writer = engine.connect()
            # SET 与 INSERT 同事务：先裸 exec 会 autobegin，显式 begin() 即 InvalidRequest
            with pytest.raises(sqlalchemy.exc.OperationalError):
                with writer.begin():
                    writer.exec_driver_sql("SET lock_timeout = '500ms'")
                    writer.execute(text("INSERT INTO fence_t VALUES ('blocked', 0)"))
            writer.rollback()  # 释放被锁超时中止的事务
            writer.close()
            engine.dispose()
        finally:
            fence.release()

    def test_oracle_zero_write_and_positive_control(self, fence_table: str) -> None:
        """T18 PG 独立观测：零写通过；同主键同计数 UPDATE 必须令 oracle 失败。"""
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool

        from app.services.db_migration.source_fence import SourceWriteOracle

        oracle = SourceWriteOracle("postgresql", table_names=TABLES, pg_url=fence_table)
        try:
            before = oracle.snapshot()
            engine = create_engine(fence_table, poolclass=NullPool)
            with engine.connect() as conn:  # 只读 SELECT 不产生用户表写
                conn.execute(text("SELECT count(*) FROM fence_t")).scalar()
            engine.dispose()
            SourceWriteOracle.assert_zero_write(before, oracle.snapshot())

            # 阳性对照：同主键同计数 UPDATE
            before = oracle.snapshot()
            engine = create_engine(fence_table, poolclass=NullPool)
            with engine.begin() as conn:
                conn.execute(text("UPDATE fence_t SET v = 999 WHERE k = 'k1'"))
            engine.dispose()
            with pytest.raises(AssertionError):
                SourceWriteOracle.assert_zero_write(before, oracle.snapshot())
        finally:
            oracle.close()
