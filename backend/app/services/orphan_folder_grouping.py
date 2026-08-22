"""孤儿文件按文件夹（直接父目录）聚合分页所需的 SQLite 自定义函数。

折叠列表模式下，同一直接父目录下的多个孤儿文件需聚合为一行。
由于 ``OrphanFile.file_path`` 存储的是平台原生绝对路径（Linux 用 ``/``、
Windows 用反斜杠），且 SQLite 没有原生的 ``SUBSTRING_INDEX``，这里通过注册
一个 Python 实现的 ``bt_orphan_parent_dir`` 自定义函数，让 SQL 层可以直接
``GROUP BY bt_orphan_parent_dir(file_path)``，避免把万级行拉进内存分组。

注册模式与 ``sqlite_search_runtime.install_sqlite_search_functions`` 对称。
"""

from __future__ import annotations

import sqlite3
from typing import Any


def orphan_parent_dir(file_path: Any) -> str:
    """计算孤儿文件的直接父目录。

    - 统一 ``\\`` → ``/`` 后取最后一个 ``/`` 之前的子串。
    - 无分隔符（根目录下单层文件）原样返回。
    - ``None`` / 空串返回空串（避免 GROUP BY 出现 None 键）。

    注意：``rfind`` 返回 -1 时必须显式判断，否则 ``path[:-1]`` 会截掉末尾字符。
    """
    if not file_path:
        return ""
    norm = str(file_path).replace("\\", "/")
    idx = norm.rfind("/")
    if idx == -1:
        return norm
    return norm[:idx]


def install_orphan_folder_functions(dbapi_connection: Any) -> None:
    """在单个 sqlite3 连接上注册 ``bt_orphan_parent_dir`` 自定义函数。

    供 ``GROUP BY`` / ``WHERE ... IN`` 使用；``deterministic=True`` 允许
    SQLite 查询计划器缓存结果（要求 SQLite >= 3.8.3，项目依赖远超此版本）。
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    dbapi_connection.create_function(
        "bt_orphan_parent_dir",
        1,
        orphan_parent_dir,
        deterministic=True,
    )


def _raw_sqlite_connection(session: Any) -> sqlite3.Connection | None:
    """从 AsyncSession 取底层 sqlite3 原生连接（穿透 aiosqlite wrapper）。"""
    try:
        connection = session.connection()
        raw = connection.connection.driver_connection
    except (AttributeError, TypeError):
        return None
    return raw if isinstance(raw, sqlite3.Connection) else None


def ensure_folder_grouping_functions(session: Any) -> None:
    """确保当前 session 连接已注册 ``bt_orphan_parent_dir``。

    aiosqlite 异步引擎下 ``event.listens_for(sync_engine, "connect")`` 不生效
    （与 ``sqlite_search_runtime.ensure_search_runtime`` 同因），故在查询前
    显式取底层 sqlite3 连接注册。幂等：SQLite ``create_function`` 可重复调用。
    """
    raw = _raw_sqlite_connection(session)
    if raw is not None:
        install_orphan_folder_functions(raw)
