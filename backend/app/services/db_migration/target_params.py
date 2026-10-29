# -*- coding: utf-8 -*-
"""迁移目标显式连接参数（database-migration-ui W1-5，PLANS §4.1/§6.1）。

迁移管线只接受**显式目标参数**（页面/CLI 传入或受保护候选配置解析），
构造引擎/URL 时绝不读写全局 settings 或 os.environ——同一操作的连接
只作用于该次操作（PLANS §4.1）。

- PG：``URL.create`` 结构化构造（凭据特殊字符自动转义；同步侧 sslmode 查询
  参数——语义与契约 §2.3 对齐）；⚠️ 禁用 ``str(URL)``（密码会被掩码为 ***，
  见 app/database.py 实测注释）。
- SQLite：路径引擎（只读快照用 URI mode=ro；写目标由管线 staging 专用）。
- 引擎均为 NullPool（迁移工具用后即弃；服务端常驻池归 app.database）。

与 app.database.build_database_url 的关系：后者是 settings 驱动的服务端
引擎工厂；本模块是显式参数版。W3 配置仓储统一时合并（计划 §10 复用原则，
不平行复制第二套长期实现——此处仅承载迁移专用语义）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.pool import NullPool

from app.core.database_bootstrap import PostgresParams

__all__ = ["PostgresParams", "build_pg_url", "pg_engine", "sqlite_readonly_engine", "sqlite_engine"]


def pg_params_from_mapping(mapping: Dict[str, Any]) -> PostgresParams:
    """API 表单映射 → PostgresParams（缺省补全；校验交由 dataclass）。"""
    return PostgresParams(
        host=str(mapping.get("host", "localhost")),
        port=int(mapping.get("port", 5432)),
        user=str(mapping.get("user", "btdeck")),
        password=str(mapping.get("password", "")),
        database=str(mapping.get("database", "btdeck")),
        schema=str(mapping.get("schema", "public")),
        sslmode=str(mapping.get("sslmode", "prefer")),
        ssl_root_cert=mapping.get("ssl_root_cert"),
        pool_size=int(mapping.get("pool_size", 10)),
        max_overflow=int(mapping.get("max_overflow", 20)),
        pool_timeout=int(mapping.get("pool_timeout", 30)),
    )


def build_pg_url(params: PostgresParams, *, async_driver: bool = False) -> str:
    """显式参数构造 PG URL（同步 psycopg2 / 异步 asyncpg；TLS 按契约 §2.3）。"""
    query: Dict[str, Any] = {}
    if not async_driver:
        query["sslmode"] = params.sslmode
        if params.sslmode in ("verify-ca", "verify-full") and params.ssl_root_cert:
            query["sslrootcert"] = params.ssl_root_cert
    driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
    url = URL.create(
        drivername=driver,
        username=params.user,
        password=params.password,
        host=params.host,
        port=params.port,
        database=params.database,
        query=query,
    )
    # ⚠️ 禁用 str(URL)：SQLAlchemy 2.0 会把密码掩码为 ***（app/database.py 实测坑）
    return url.render_as_string(hide_password=False)


def pg_engine(params: PostgresParams, *, echo: bool = False) -> Engine:
    """迁移专用 PG 同步引擎（NullPool 用后即弃；PG16+ 校验在首个连接上执行）。"""
    return create_engine(build_pg_url(params), poolclass=NullPool, echo=echo)


def sqlite_readonly_engine(path: str) -> Engine:
    """SQLite 只读引擎（URI mode=ro；绝不隐式创建文件——快照/源库专用）。"""
    uri = "sqlite:///" + quote(str(Path(path).resolve())) + "?mode=ro&uri=true"
    return create_engine(uri, poolclass=NullPool)


def sqlite_engine(path: str, *, echo: bool = False) -> Engine:
    """SQLite 写引擎（迁移目标 staging 专用；存在性由调用方管——O_EXCL 语义在管线）。"""
    return create_engine(f"sqlite:///{path}", poolclass=NullPool, echo=echo)
