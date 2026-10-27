"""PostgreSQL 正则搜索运行时（v1.0.8 任务2.1，契约 docs/postgresql-contract.md §4.2）。

与 ``app.services.sqlite_search_runtime`` 对称的查询预算实现：
- SQLite：progress handler 墙钟预算（历史行为零变化，不在本模块）；
- PG：**请求级 deadline + 每条 SQL 的剩余预算**——
  ``SET LOCAL statement_timeout`` 于事务内下发（事务结束自动失效，
  连接池会话无污染）；每条 SQL 执行前重新按剩余预算 arm；
  **剩余 ≤ 0 直接终止不再发送 SQL**（禁写 0 值——PG 语义为禁用超时，
  契约 §4.2）；取消后事务 abort，调用方须 rollback。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import event, text

logger = logging.getLogger(__name__)

REGEX_QUERY_BUDGET_SECONDS = 2.0  # 与 sqlite_search_runtime 同值（契约同口径）

# asyncpg 取消异常（SQLSTATE 57014 query_canceled）；以类名+消息双口径识别，
# 避免驱动未安装时 import 失败
_CANCEL_MARKERS = ("QueryCanceled", "canceling statement", "statement timeout", "terminated due to timeout")


def is_query_cancelled_error(exc: BaseException) -> bool:
    """识别 statement_timeout 取消（含 SQLAlchemy 包装层与 asyncpg 原生层）。"""
    if exc.__class__.__name__ in ("QueryCanceledError", "AsyncpgQueryCanceledError"):
        return True
    msg = str(exc).lower()
    return any(marker.lower() in msg for marker in _CANCEL_MARKERS)


class PgRegexBudget:
    """请求级正则查询预算（每条 SQL 前按剩余时长 arm statement_timeout）。

    同步会话接口（advanced_search.search_torrents 为同步方法，psycopg2 路径）::

        budget = PgRegexBudget(session)
        budget.arm()        # 进入查询块：SET LOCAL 超时=剩余预算
        total = count()
        budget.arm()        # checkpoint：count 消耗后剩余预算（≤0 即终止）
        rows = list_query()
    """

    def __init__(self, session: Any, *, seconds: float = REGEX_QUERY_BUDGET_SECONDS) -> None:
        self._session = session
        self.deadline = time.monotonic() + seconds
        self._connection: Any = None
        self._previous_timeout: Any = None

    def __enter__(self) -> "PgRegexBudget":
        self._connection = self._session.connection()
        self._previous_timeout = self._connection.execute(text("SHOW statement_timeout")).scalar_one()
        event.listen(self._connection, "before_cursor_execute", self._before_execute)
        return self

    def _before_execute(
        self, connection: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        if statement.startswith("SET LOCAL statement_timeout"):
            return
        from app.services.sqlite_search_runtime import RegexSearchTimeout

        milliseconds = int(self.remaining_seconds * 1000)
        if milliseconds <= 0:
            raise RegexSearchTimeout("regular expression search exceeded its execution budget")
        # 直接通过同一个 psycopg2 cursor 设置，避免再次触发 SQLAlchemy 事件。
        cursor.execute("SET LOCAL statement_timeout = %s", (milliseconds,))

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        event.remove(self._connection, "before_cursor_execute", self._before_execute)
        if exc_type is None:
            self._connection.execute(text("SET LOCAL statement_timeout = :value"), {"value": self._previous_timeout})

    @property
    def remaining_seconds(self) -> float:
        return self.deadline - time.monotonic()

    def arm(self) -> None:
        """在当前事务内 SET LOCAL statement_timeout = 剩余预算。

        Raises:
            RegexSearchTimeout: 剩余预算 ≤ 0——直接终止，不再发送 SQL
                （禁写 0 值：PG statement_timeout=0 表示禁用超时，契约 §4.2）。
        """
        from app.services.sqlite_search_runtime import RegexSearchTimeout

        remaining_ms = int(self.remaining_seconds * 1000)
        if remaining_ms <= 0:
            logger.warning("正则查询预算耗尽（剩余 %dms），终止后续 SQL", remaining_ms)
            raise RegexSearchTimeout("regular expression search exceeded its execution budget")
        # SET LOCAL 需在事务内生效；Session autobegin 保证首条语句开启事务
        self._session.execute(text("SET LOCAL statement_timeout = :ms"), {"ms": max(1, remaining_ms)})
