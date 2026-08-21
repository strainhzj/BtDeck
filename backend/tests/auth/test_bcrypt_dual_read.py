# -*- coding: utf-8 -*-
"""bcrypt 双读迁移测试（W8）。

安全背景：历史密码存储为 AES-ECB 可逆加密（函数名冒名 SM4），密钥公开在
git 中——数据库泄露即密码明文。迁移为 bcrypt 单向哈希：
- 新哈希一律 bcrypt（$2b$）
- verify_password 双读：bcrypt 优先，旧 AES-ECB 格式回退兼容
- 登录端点验证旧格式成功后自动升级（条件更新防并发竞态）
"""

import base64

import pytest

from app.auth import security
from app.auth.security import get_password_hash, verify_password


def _make_legacy_hash(password: str, secret_key: str = "0123456789abcdef") -> str:
    """用旧算法构造存量格式密文（AES-ECB(base64(密码))）。"""
    from Cryptodome.Cipher import AES
    from Cryptodome.Util.Padding import pad

    key = secret_key.encode("utf-8")
    cipher = AES.new(key, AES.MODE_ECB)
    payload = base64.b64encode(password.encode("utf-8")).decode("utf-8")
    return base64.b64encode(cipher.encrypt(pad(payload.encode("utf-8"), AES.block_size))).decode("utf-8")


class TestPasswordHash:
    """新哈希一律 bcrypt。"""

    def test_hash_is_bcrypt_format(self):
        h = get_password_hash("mypassword")
        assert h.startswith("$2b$")
        assert len(h) > 50

    def test_hash_random_salt(self):
        assert get_password_hash("same") != get_password_hash("same")

    def test_verify_roundtrip(self):
        h = get_password_hash("s3cret!")
        assert verify_password("s3cret!", h)
        assert not verify_password("wrong", h)

    def test_long_password_truncated_consistently(self):
        """超 72 字节密码：哈希与验证两端一致截断（bcrypt 算法上限）。"""
        long_pw = "x" * 100
        h = get_password_hash(long_pw)
        assert verify_password(long_pw, h)


class TestLegacyDualRead:
    """旧 AES-ECB 格式密文可验证（存量兼容），且不误判。"""

    def test_legacy_hash_verifies(self, monkeypatch):
        mock_yaml = type("Y", (), {"get": lambda self, k: "0123456789abcdef"})()
        monkeypatch.setattr(security, "yaml", mock_yaml)
        legacy = _make_legacy_hash("oldpass", "0123456789abcdef")
        assert verify_password("oldpass", legacy)
        assert not verify_password("other", legacy)

    def test_legacy_hash_upgradeable_detection(self):
        """is_bcrypt_hash 正确区分新旧格式（登录端点据此触发自动升级）。"""
        assert security.is_bcrypt_hash(get_password_hash("x"))
        assert not security.is_bcrypt_hash(_make_legacy_hash("x"))

    def test_garbage_hash_returns_false(self):
        assert verify_password("x", "not-a-hash") is False
        assert verify_password("x", "") is False
        assert verify_password("x", "$2b$12$broken") is False
