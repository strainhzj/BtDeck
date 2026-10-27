"""PG 连接配置契约，避免同步和异步 TLS 配置分歧。"""

from sqlalchemy.engine import make_url
from app import database


def test_sync_url_includes_configured_root_certificate(monkeypatch):
    monkeypatch.setattr(database, "DIALECT", "postgresql")
    monkeypatch.setattr(database.settings, "DB_SSLMODE", "verify-full")
    monkeypatch.setattr(database.settings, "DB_SSL_ROOT_CERT", "/tmp/custom-ca.pem")
    url = make_url(database.build_database_url())
    assert url.query["sslmode"] == "verify-full"
    assert url.query.get("sslrootcert") == "/tmp/custom-ca.pem"


def test_url_preserves_special_credentials(monkeypatch):
    monkeypatch.setattr(database, "DIALECT", "postgresql")
    monkeypatch.setattr(database.settings, "DB_USER", "u@ser: /%")
    monkeypatch.setattr(database.settings, "DB_PASSWORD", "p@ss:/% word")
    for asynchronous in (False, True):
        url = make_url(database.build_database_url(async_driver=asynchronous))
        assert url.username == "u@ser: /%"
        assert url.password == "p@ss:/% word"
