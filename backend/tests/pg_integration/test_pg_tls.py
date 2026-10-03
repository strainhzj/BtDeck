"""双驱动 TLS 契约：独立连接并查询服务端实际 TLS 状态。"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.skipif(os.getenv("DB_TYPE") != "postgresql", reason="requires PostgreSQL")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["disable", "prefer", "require", "verify-ca", "verify-full"])
async def test_driver_tls_mode_matrix(mode, monkeypatch, tmp_path):
    from app import database

    tls = os.getenv("BTDECK_PG_TLS_PORT")
    monkeypatch.setattr(database.settings, "DB_SSLMODE", mode)
    ca = os.getenv("BTDECK_PG_TLS_CA")
    if not ca:
        # 有效 CA 文件保证 verify-* 真正尝试连接无 TLS 服务端，而非仅测配置错误。
        import ssl

        ca = ssl.get_default_verify_paths().cafile
        assert ca is not None
    monkeypatch.setattr(database.settings, "DB_SSL_ROOT_CERT", ca)
    monkeypatch.setattr(database.settings, "DB_HOST", "localhost")
    if tls:
        monkeypatch.setattr(database.settings, "DB_PORT", int(tls))
    sync = create_engine(database.build_database_url(), poolclass=NullPool)
    async_engine = create_async_engine(
        database.build_database_url(async_driver=True),
        poolclass=NullPool,
        connect_args=database._pg_ssl_args(async_driver=True),
    )
    query = text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
    try:
        if not tls and mode in {"require", "verify-ca", "verify-full"}:
            with pytest.raises(Exception):
                with sync.connect() as conn:
                    conn.execute(query)
            with pytest.raises(Exception):
                async with async_engine.connect() as conn:
                    await conn.execute(query)
        else:
            expected = bool(tls) and mode != "disable"
            with sync.connect() as conn:
                assert conn.execute(query).scalar_one() is expected
            async with async_engine.connect() as conn:
                assert (await conn.execute(query)).scalar_one() is expected
    finally:
        sync.dispose()
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_verify_full_rejects_wrong_hostname(monkeypatch):
    if not os.getenv("BTDECK_PG_TLS_PORT"):
        pytest.skip("TLS server required")
    from app import database

    monkeypatch.setattr(database.settings, "DB_PORT", int(os.environ["BTDECK_PG_TLS_PORT"]))
    monkeypatch.setattr(database.settings, "DB_HOST", "127.0.0.1")
    monkeypatch.setattr(database.settings, "DB_SSLMODE", "verify-full")
    monkeypatch.setattr(database.settings, "DB_SSL_ROOT_CERT", os.environ["BTDECK_PG_TLS_CA"])
    sync = create_engine(database.build_database_url(), poolclass=NullPool)
    engine = create_async_engine(
        database.build_database_url(async_driver=True),
        poolclass=NullPool,
        connect_args=database._pg_ssl_args(async_driver=True),
    )
    try:
        with pytest.raises(Exception):
            with sync.connect():
                pass
        with pytest.raises(Exception):
            async with engine.connect():
                pass
    finally:
        sync.dispose()
        await engine.dispose()
