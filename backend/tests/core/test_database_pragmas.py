# -*- coding: utf-8 -*-
"""
SQLite PRAGMA 事件监听回归测试

【回归】问题2-a：每个 SQLite 连接必须强制下发 WAL / synchronous / busy_timeout。

根因：database is locked 锁冲突。
- journal_mode=WAL 是数据库文件级持久属性（init_db 用临时连接设过一次即可），
  但 synchronous / busy_timeout 是连接级、非持久的。
- 原实现 connect_args 只设了 timeout（会转成 busy_timeout），但没有任何 event 事件监听器
  把 PRAGMA 挂到每个新连接上；且 init_db 的 PRAGMA 调用不覆盖所有连接。
- 修复：新增 _apply_sqlite_pragmas 事件回调，挂到 engine 和 async_engine.sync_engine 的
  connect 事件，强制下发 journal_mode=WAL / synchronous=NORMAL / busy_timeout=30000。

收敛锚点：
1. _apply_sqlite_pragmas 函数本身必须正确下发三条 PRAGMA（直接对裸 sqlite3 连接调用，最稳定）。
2. 该回调必须注册到 engine 和 async_engine.sync_engine 的 connect 事件（防止有人删掉监听注册）。
"""

import sqlite3

from sqlalchemy import event


class TestSqlitePragmasRegression:
    """【回归】SQLite 连接必须强制下发并发优化 PRAGMA。"""

    def test_apply_sqlite_pragmas_sets_busy_timeout(self, tmp_path):
        """_apply_sqlite_pragmas 必须对连接下发 busy_timeout=30000 / journal_mode=wal / synchronous=normal。

        收敛点：直接测事件回调函数本身（不依赖模块级 engine 单例）。
        若有人删除 busy_timeout 那行，此测试立即报红。
        """
        from app.database import _apply_sqlite_pragmas

        # 用一个独立的临时 SQLite 库，直接调事件回调（模拟 SQLAlchemy 建连时触发）
        db_path = str(tmp_path / "pragma_test.db")
        conn = sqlite3.connect(db_path)
        try:
            _apply_sqlite_pragmas(conn, None)  # 事件回调签名：(dbapi_conn, conn_record)

            # busy_timeout 必须 30000ms（30s），缓解多任务并发写的 locked
            bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert bt == 30000, (
                f"busy_timeout 必须为 30000ms（实际 {bt}）："
                "缺此项是多任务并发写时 database is locked 的根因"
            )

            # journal_mode 必须 wal（读写并发能力远超默认 rollback journal）
            jm = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            assert jm == "wal", f"journal_mode 必须为 wal（实际 {jm}）"

            # synchronous 必须 normal（WAL 下安全且更快）
            sync = str(conn.execute("PRAGMA synchronous").fetchone()[0]).lower()
            assert sync in ("1", "normal"), (
                f"synchronous 必须为 normal（实际 {sync}）："
                "默认 FULL 会每笔事务 fsync，放大锁占用时间"
            )
        finally:
            conn.close()

    def test_event_listener_registered_for_connect(self):
        """_apply_sqlite_pragmas 必须注册到 engine 和 async_engine.sync_engine 的 connect 事件。

        收敛点：用 event.contains 元数据校验。若有人删掉 event.listens_for(...) 注册行，
        此测试立即报红（即使函数本身正确，没挂上也不生效）。

        注意：异步引擎必须 listen 到 async_engine.sync_engine（直接 listen async_engine 不生效）。
        """
        from app.database import engine, async_engine, _apply_sqlite_pragmas

        assert event.contains(engine, "connect", _apply_sqlite_pragmas), (
            "engine 必须注册 _apply_sqlite_pragmas 到 connect 事件："
            "同步引擎的每个新连接需要强制下发 PRAGMA"
        )
        assert event.contains(async_engine.sync_engine, "connect", _apply_sqlite_pragmas), (
            "async_engine.sync_engine 必须注册 _apply_sqlite_pragmas 到 connect 事件："
            "直接 listen async_engine 不生效，必须 listen 到底层 sync_engine"
        )
