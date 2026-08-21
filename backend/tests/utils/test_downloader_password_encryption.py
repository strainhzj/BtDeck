# -*- coding: utf-8 -*-
"""下载器密码加密安全测试（W6）。

安全背景（对抗验证结论，真实 DB 取证 4/4 明文）：
- add 端点明文落库（update 却加密），decrypt 对非 sm4: 前缀静默透传掩盖缺陷；
- encryption.encrypt() 在加密器未初始化/运行时异常时静默返回明文（fail-open）；
- core/security.encrypt_tracker_info 捕获异常后返回明文（同类 fail-open）。

修复：add 加密落库 + encrypt fail-closed（raise）+ 启动幂等钩子加密存量明文。
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.downloader.models import BtDownloaders
from app.utils.encryption import SM4Encryption


def _bare_instance(**attrs) -> SM4Encryption:
    """绕过 __init__（避免读真实 config.yaml），手工注入可控状态。"""
    inst = SM4Encryption.__new__(SM4Encryption)
    inst.sm4_key = "test"
    inst.encrypt_crypt = None
    inst.decrypt_crypt = None
    for k, v in attrs.items():
        setattr(inst, k, v)
    return inst


class TestEncryptFailClosed:
    """encrypt() fail-closed：任何失败都抛错，绝不返回明文。"""

    def test_uninitialized_raises(self):
        enc = _bare_instance()
        with pytest.raises(RuntimeError, match="未初始化"):
            enc.encrypt("secret")

    def test_runtime_exception_raises_not_plaintext(self):
        enc = _bare_instance(encrypt_crypt=SimpleNamespace())  # 无 crypt_ecb → AttributeError
        with pytest.raises(Exception):
            enc.encrypt("secret")

    def test_empty_passthrough_kept(self):
        enc = _bare_instance()
        assert enc.encrypt("") == ""

    def test_already_encrypted_idempotent(self):
        fake = SimpleNamespace(crypt_ecb=lambda data: b"\x01\x02")
        enc = _bare_instance(encrypt_crypt=fake)
        assert enc.encrypt("sm4:abc") == "sm4:abc"

    def test_encrypt_produces_sm4_prefix(self):
        fake = SimpleNamespace(crypt_ecb=lambda data: b"\x01\x02")
        enc = _bare_instance(encrypt_crypt=fake)
        result = enc.encrypt("secret")
        assert result.startswith("sm4:")


class TestDecryptCompatPassthrough:
    """decrypt() 对非 sm4: 前缀原样返回（存量明文兼容通道，load-bearing）。"""

    def test_plaintext_passthrough(self):
        enc = _bare_instance()
        assert enc.decrypt("plain_password") == "plain_password"


@pytest.fixture()
def downloader_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[BtDownloaders.__table__])
    Session = sessionmaker(bind=engine)
    yield Session
    engine.dispose()


class TestStartupEncryptionHook:
    """启动幂等钩子：明文行被加密，密文行不动，密钥缺失跳过不炸。"""

    def test_plaintext_rows_encrypted_then_idempotent(self, downloader_db, monkeypatch):
        from app.downloader import initialization

        monkeypatch.setattr(initialization, "SessionLocal", downloader_db)
        monkeypatch.setattr("app.utils.encryption.encrypt_password", lambda p: f"sm4:{p}")

        with downloader_db() as db:
            db.add(BtDownloaders(downloader_id="dl-1", nickname="a", downloader_type=0, password="plain_pw"))
            db.add(BtDownloaders(downloader_id="dl-2", nickname="b", downloader_type=0, password="sm4:already"))
            db.add(BtDownloaders(downloader_id="dl-3", nickname="c", downloader_type=0, password=""))
            db.commit()

        count = initialization.encrypt_plaintext_downloader_passwords()
        assert count == 1

        with downloader_db() as db:
            rows = {r.downloader_id: r.password for r in db.query(BtDownloaders).all()}
        assert rows["dl-1"] == "sm4:plain_pw"
        assert rows["dl-2"] == "sm4:already"
        assert rows["dl-3"] == ""

        # 幂等：第二次运行无事可做
        assert initialization.encrypt_plaintext_downloader_passwords() == 0

    def test_key_missing_skips_without_crash(self, downloader_db, monkeypatch):
        from app.downloader import initialization

        def _raise(p):
            raise RuntimeError("SM4加密器未初始化，拒绝以明文落库")

        monkeypatch.setattr(initialization, "SessionLocal", downloader_db)
        monkeypatch.setattr("app.utils.encryption.encrypt_password", _raise)

        with downloader_db() as db:
            db.add(BtDownloaders(downloader_id="dl-9", nickname="x", downloader_type=0, password="plain_pw"))
            db.commit()

        assert initialization.encrypt_plaintext_downloader_passwords() == 0
        with downloader_db() as db:
            row = db.query(BtDownloaders).filter_by(downloader_id="dl-9").first()
            assert row.password == "plain_pw", "密钥缺失时保持原样，等待下次启动重试"
