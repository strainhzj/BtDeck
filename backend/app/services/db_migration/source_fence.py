# -*- coding: utf-8 -*-
"""源 fence 与零写 oracle（database-migration-ui W2-4，PLANS §5.2/§11 T18）。

维护中的源库保护（排空完成后、快照/切换前）：

- **SQLite**：专用 fence 连接持 ``BEGIN IMMEDIATE``（RESERVED 写锁）阻止新
  写者；fence 连接只锁/读/释放，禁止业务 DML。
- **PostgreSQL**：REPEATABLE READ 事务内按**固定顺序**对业务+协议三表逐表
  ``LOCK TABLE … IN SHARE MODE``（与 ROW EXCLUSIVE 写者冲突，阻止普通 DML）；
  ``lock_timeout`` 有界，超时/失败即放弃（绝不无限等待，也不宣称冻结）；
  事务保持打开直至 release（锁生命周期=事务生命周期）。
- **指纹固定**：进入 FROZEN 前计算源内容指纹（schema+全表行数摘要）；HELD
  重绑/锁恢复时重新对拍——漂移即拒绝（§5.1/§6.4）。
- **进程重启后必须重新取 fence 并核源内容**（controller 以 HELD 进入，由本
  模块 ``acquire`` + ``verify_against`` 完成核源，不认为旧锁仍在）。
- **异库目标断言**：迁移目标必须与源可区分（SQLite 按 samefile/inode，PG 按
  host/port/dbname）；同库例外仅 §7.3 HANDOFF_SAME_DB 的显式确认路径。
- **零写 oracle（T18）**：维护窗口内证明源零写——SQLite 用**同一观测连接**
  的 ``PRAGMA data_version``（其他连接提交才会前进）+ 内容摘要；PG 用独立
  观测连接的 ``pg_stat_user_tables`` 三元组增量 + 内容摘要。阳性对照
  （同主键同计数 UPDATE）必须令 oracle 失败，否则 oracle 无效。

表名清单由调用方注入（避免模块导入期 ORM/引擎副作用）；标识符仅来自
ORM 元数据/协议常量，按 BTD305 白名单先例使用 f-string（同 pg_baseline）。
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool


class SourceFenceError(RuntimeError):
    """fence 取锁/校验失败（调用方转 HELD，不继续宣称冻结）。"""


class DistinctTargetError(SourceFenceError):
    """源/目标不可区分（异库断言失败；同库例外须显式确认）。"""


def load_table_names() -> List[str]:
    """固定顺序全表清单：业务表（依赖序）+ 协议三表（字母序）——锁序稳定。

    惰性 import（ORM 元数据在 app.database.Base 注册，避免模块级引擎副作用）。
    """
    from app.core.database_protocol import PROTOCOL_TABLE_NAMES
    from app.models.database_migration import business_tables

    return [t.name for t in business_tables()] + sorted(PROTOCOL_TABLE_NAMES)


def _digest_pairs(pairs: Sequence[Tuple[str, Any]]) -> str:
    hasher = hashlib.sha256()
    for key, value in pairs:
        hasher.update(str(key).encode("utf-8"))
        hasher.update(b"\x1f")
        hasher.update(str(value).encode("utf-8"))
        hasher.update(b"\x1e")
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# SQLite fence
# ---------------------------------------------------------------------------


@dataclass
class FenceToken:
    """fence 令牌（controller.enter_frozen 只做存在性登记）。"""

    dialect: str
    fingerprint: str
    acquired_at: float
    detail: Dict[str, Any]


class SqliteSourceFence:
    """SQLite 源保护：专用连接 BEGIN IMMEDIATE + 内容指纹。"""

    def __init__(self, sqlite_path: os.PathLike[str] | str, table_names: Sequence[str]) -> None:
        self._path = str(sqlite_path)
        self._table_names = list(table_names)
        self._conn: Optional[sqlite3.Connection] = None
        self._token: Optional[FenceToken] = None

    @property
    def token(self) -> Optional[FenceToken]:
        return self._token

    def acquire(self, *, timeout_seconds: float = 30.0) -> FenceToken:
        if self._conn is not None:
            raise SourceFenceError("fence 已持有（禁止重复取锁）")
        deadline = time.monotonic() + timeout_seconds
        conn = sqlite3.connect(self._path, timeout=max(0.1, timeout_seconds), isolation_level=None)
        try:
            while True:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    break
                except sqlite3.OperationalError:
                    if time.monotonic() >= deadline:
                        raise SourceFenceError(f"SQLite fence 取写锁超时: {self._path}") from None
                    time.sleep(0.1)
            fingerprint = self._fingerprint_on(conn)
        except Exception:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            raise
        self._conn = conn
        self._token = FenceToken("sqlite", fingerprint, time.time(), {"path": self._path})
        return self._token

    def _fingerprint_on(self, conn: sqlite3.Connection) -> str:
        """内容指纹：schema 摘要 + 全表行数摘要（固定表序）。"""
        schema_rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        counts: List[Tuple[str, int]] = []
        for name in self._table_names:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            # 表名来自注入的固定清单（BTD305 白名单先例：标识符常量）
            counts.append((name, conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] if exists else -1))
        return _digest_pairs(
            [("schema", _digest_pairs([(f"{r[0]}:{r[1]}", r[2] or "") for r in schema_rows]))] + counts
        )

    def verify(self) -> bool:
        """指纹复核（同 fence 连接；失败即锁/内容异常 → 调用方 note_fence_lost）。"""
        if self._conn is None or self._token is None:
            return False
        try:
            return self._fingerprint_on(self._conn) == self._token.fingerprint
        except sqlite3.Error:
            return False

    def verify_against(self, expected_fingerprint: str) -> bool:
        """重启/重绑核源：重新取锁后对拍历史指纹（漂移拒绝，§5.1）。"""
        if self._conn is None or self._token is None:
            raise SourceFenceError("fence 未持有，先 acquire 再对拍")
        return self._token.fingerprint == expected_fingerprint

    def release(self) -> None:
        conn, self._conn, self._token = self._conn, None, None
        if conn is not None:
            try:
                conn.execute("ROLLBACK")  # 释放 RESERVED 锁；fence 只锁/读/释放，无 DML 需回滚
            except sqlite3.Error:
                pass
            try:
                conn.close()
            except sqlite3.Error:
                pass


# ---------------------------------------------------------------------------
# PostgreSQL fence
# ---------------------------------------------------------------------------


class PgSourceFence:
    """PG 源保护：REPEATABLE READ + 逐表 SHARE 锁（固定顺序、有界超时）。

    事务保持打开（不 commit）——SHARE 表锁随事务持续至 ``release``；
    ``verify`` 检查连接存活与 pg_locks 中 ShareLock 数量（锁丢失即 False）。
    """

    def __init__(self, url: str, table_names: Sequence[str], *, lock_timeout_seconds: float = 30.0) -> None:
        self._url = url
        self._table_names = list(table_names)
        self._lock_timeout = lock_timeout_seconds
        self._engine: Optional[Engine] = None
        self._conn: Optional[Connection] = None
        self._token: Optional[FenceToken] = None

    @property
    def token(self) -> Optional[FenceToken]:
        return self._token

    def acquire(self) -> FenceToken:
        if self._conn is not None:
            raise SourceFenceError("fence 已持有（禁止重复取锁）")
        # NullPool 单连接：锁生命周期=连接事务生命周期，避免池复用隐式归还
        engine = create_engine(self._url, poolclass=NullPool)
        conn = engine.connect()
        try:
            conn.execution_options(isolation_level="REPEATABLE READ")
            conn.exec_driver_sql("SET lock_timeout = %s", (_ms(self._lock_timeout),))
            for name in self._table_names:
                # 表名来自注入的固定清单（BTD305 白名单先例：标识符常量）
                conn.exec_driver_sql(f'LOCK TABLE "{name}" IN SHARE MODE')
            fingerprint = self._fingerprint_on(conn)
        except Exception as exc:
            try:
                conn.close()
            except Exception:
                pass
            try:
                engine.dispose()
            except Exception:
                pass
            raise SourceFenceError(f"PG fence 取 SHARE 锁失败（lock_timeout 有界，不宣称冻结）: {exc}") from exc
        self._engine, self._conn, self._token = (
            engine,
            conn,
            FenceToken("postgresql", fingerprint, time.time(), {"lockMode": "SHARE", "tables": len(self._table_names)}),
        )
        return self._token

    def _fingerprint_on(self, conn: Connection) -> str:
        counts: List[Tuple[str, int]] = []
        for name in self._table_names:
            row = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
            counts.append((name, int(row if row is not None else -1)))
        try:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            version = None  # 测试库可能无 alembic_version 表
        return _digest_pairs([("alembic", version)] + counts)

    def verify(self) -> bool:
        """连接存活 + ShareLock 数量核对（锁丢失即 False → note_fence_lost）。"""
        if self._conn is None or self._token is None:
            return False
        try:
            expected = len(self._table_names)
            got = self._conn.execute(
                text(
                    "SELECT count(*) FROM pg_locks WHERE mode = 'ShareLock' "
                    "AND relation::regclass::text = ANY(:names)"
                ),
                {"names": list(self._table_names)},
            ).scalar()
            return int(got if got is not None else 0) >= expected
        except Exception:
            return False

    def verify_against(self, expected_fingerprint: str) -> bool:
        if self._token is None:
            raise SourceFenceError("fence 未持有，先 acquire 再对拍")
        return self._token.fingerprint == expected_fingerprint

    def release(self) -> None:
        conn, engine, self._conn, self._engine, self._token = self._conn, self._engine, None, None, None
        if conn is not None:
            try:
                conn.rollback()  # 释放全部 SHARE 表锁
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


def _ms(seconds: float) -> int:
    return max(1, int(seconds * 1000))


# ---------------------------------------------------------------------------
# 异库目标断言（§5.2；HANDOFF_SAME_DB 例外仅显式确认路径）
# ---------------------------------------------------------------------------


def sqlite_identity(path: os.PathLike[str] | str) -> Tuple[str, str]:
    resolved = str(Path(path).resolve())
    try:
        stat = os.stat(resolved)
        return ("sqlite", f"inode:{stat.st_dev}:{stat.st_ino}")  # 链接/同 inode 不可绕过
    except OSError:
        return ("sqlite", f"path:{resolved.lower()}")


def pg_identity(host: str, port: int, database: str) -> Tuple[str, str]:
    return ("postgresql", f"{host.lower()}:{int(port)}/{database.lower()}")


def assert_distinct_targets(
    source: Tuple[str, str], target: Tuple[str, str], *, same_db_acknowledged: bool = False
) -> None:
    if source == target:
        if same_db_acknowledged:
            return  # §7.3 HANDOFF_SAME_DB：仅受限 fence/ACK 事务路径显式确认
        raise DistinctTargetError(
            f"迁移目标与源不可区分（{source[1]}）：异库断言失败；同库交接须走 HANDOFF_SAME_DB 显式确认"
        )


# ---------------------------------------------------------------------------
# 零写 oracle（T18）
# ---------------------------------------------------------------------------


@dataclass
class OracleSnapshot:
    dialect: str
    data_version: Optional[int]  # SQLite：同一观测连接的 PRAGMA data_version
    stat_deltas: Dict[str, int]  # PG：n_tup_ins+upd+del 聚合
    content_digest: str


class SourceWriteOracle:
    """维护窗口源零写观测。

    - SQLite：``mode=ro`` 只读观测连接。``data_version`` 仅当**其他连接**提交
      写事务才前进——同连接自身读不前进；配合内容摘要双证。
    - PG：独立观测连接读 ``pg_stat_user_tables`` 的 ins/upd/del 累计值与
      内容摘要；窗口内三元组增量非零即有写（含外部写者，宁误报不漏报）。

    阳性对照（测试）：同主键同计数 UPDATE 必须改变观测值，否则 oracle 失效。
    """

    def __init__(
        self,
        dialect: str,
        *,
        table_names: Sequence[str],
        sqlite_path: Optional[str] = None,
        pg_url: Optional[str] = None,
    ) -> None:
        self._table_names = list(table_names)
        if dialect == "sqlite":
            if not sqlite_path:
                raise ValueError("sqlite oracle 需要 sqlite_path")
            self._sqlite_conn: Optional[sqlite3.Connection] = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
            self._pg_engine: Optional[Engine] = None
        elif dialect == "postgresql":
            if not pg_url:
                raise ValueError("postgresql oracle 需要 pg_url")
            self._pg_engine = create_engine(pg_url, poolclass=NullPool)
            self._sqlite_conn = None
        else:
            raise ValueError(f"未知方言: {dialect}")
        self._dialect = dialect

    def snapshot(self) -> OracleSnapshot:
        if self._dialect == "sqlite":
            assert self._sqlite_conn is not None
            data_version = self._sqlite_conn.execute("PRAGMA data_version").fetchone()[0]
            return OracleSnapshot("sqlite", int(data_version), {}, self._content_digest_sqlite())
        assert self._pg_engine is not None
        with self._pg_engine.connect() as conn:
            deltas: Dict[str, int] = {}
            digest_pairs: List[Tuple[str, Any]] = []
            for name in self._table_names:
                row = conn.execute(
                    text("SELECT n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_user_tables WHERE relname = :n"),
                    {"n": name},
                ).fetchone()
                if row is None:
                    deltas[name] = -1
                    digest_pairs.append((name, -1))
                    continue
                deltas[name] = int(row[0]) + int(row[1]) + int(row[2])
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
                digest_pairs.append((name, int(count if count is not None else -1)))
            return OracleSnapshot("postgresql", None, deltas, _digest_pairs(digest_pairs))

    def _content_digest_sqlite(self) -> str:
        assert self._sqlite_conn is not None
        pairs: List[Tuple[str, Any]] = []
        for name in self._table_names:
            exists = self._sqlite_conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            # 表名来自注入的固定清单（BTD305 白名单先例：标识符常量）
            pairs.append(
                (name, self._sqlite_conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] if exists else -1)
            )
        return _digest_pairs(pairs)

    @staticmethod
    def assert_zero_write(before: OracleSnapshot, after: OracleSnapshot) -> None:
        if before.dialect != after.dialect:
            raise AssertionError("oracle 快照方言不一致")
        if before.dialect == "sqlite":
            if before.data_version != after.data_version:
                raise AssertionError(
                    f"SQLite 源存在外部写（data_version {before.data_version}→{after.data_version}）——零写断言失败"
                )
        else:
            drifted = {
                k: (v, after.stat_deltas.get(k)) for k, v in before.stat_deltas.items() if after.stat_deltas.get(k) != v
            }
            if drifted:
                raise AssertionError(f"PG 源表写活动非零（n_tup 累计漂移）: {drifted}——零写断言失败")
        if before.content_digest != after.content_digest:
            raise AssertionError("源内容摘要漂移——零写断言失败")

    def close(self) -> None:
        if self._sqlite_conn is not None:
            try:
                self._sqlite_conn.close()
            except sqlite3.Error:
                pass
        if self._pg_engine is not None:
            try:
                self._pg_engine.dispose()
            except Exception:
                pass
