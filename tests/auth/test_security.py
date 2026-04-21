"""
认证安全模块单元测试

测试 app/auth/security.py 中的函数：
- sm4_encrypt / sm4_decrypt: AES 加密解密（需 mock yaml 配置）
- get_password_hash: 密码哈希（SM4 加密 base64 编码后的密码）
- verify_password: 密码验证
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from app.auth.security import (
    sm4_encrypt,
    sm4_decrypt,
    get_password_hash,
    verify_password,
)


def _make_mock_yaml(secret_key="0123456789abcdef"):
    """创建 mock yaml 对象，模拟 yaml.get('security.secret_key')"""
    mock_instance = MagicMock()
    mock_instance.get.return_value = secret_key
    return mock_instance


class TestSm4EncryptDecrypt:
    """SM4(AES-ECB) 加密解密测试"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密后解密应还原原文"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            plaintext = "hello_world"
            encrypted = sm4_encrypt(plaintext)
            decrypted = sm4_decrypt(encrypted)
            assert decrypted.decode("utf-8") == plaintext

    def test_encrypt_returns_base64_string(self):
        """加密结果应为有效的 base64 字符串"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            result = sm4_encrypt("test")
            base64.b64decode(result)

    def test_encrypt_different_inputs_different_outputs(self):
        """不同输入应产生不同密文"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            enc1 = sm4_encrypt("password1")
            enc2 = sm4_encrypt("password2")
            assert enc1 != enc2

    def test_encrypt_unicode(self):
        """Unicode 文本加密解密应正确还原"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            plaintext = "中文密码"
            encrypted = sm4_encrypt(plaintext)
            decrypted = sm4_decrypt(encrypted)
            assert decrypted.decode("utf-8") == plaintext

    def test_encrypt_long_text(self):
        """长文本加密解密应正确还原"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            plaintext = "a" * 500
            encrypted = sm4_encrypt(plaintext)
            decrypted = sm4_decrypt(encrypted)
            assert decrypted.decode("utf-8") == plaintext

    def test_encrypt_missing_key_raises(self):
        """密钥缺失时应抛出 ValueError"""
        mock_yaml = _make_mock_yaml(secret_key=None)
        with patch("app.auth.security.yaml", mock_yaml):
            with pytest.raises(ValueError, match="secret_key"):
                sm4_encrypt("test")

    def test_decrypt_missing_key_raises(self):
        """密钥缺失时解密应抛出 ValueError"""
        mock_yaml = _make_mock_yaml(secret_key=None)
        with patch("app.auth.security.yaml", mock_yaml):
            with pytest.raises(ValueError, match="secret_key"):
                sm4_decrypt("dGVzdA==")


class TestGetPasswordHash:
    """密码哈希测试"""

    def test_returns_string(self):
        """哈希结果应为字符串"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            result = get_password_hash("mypassword")
            assert isinstance(result, str)

    def test_returns_base64_decodable(self):
        """哈希结果应为可 base64 解码的字符串"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            result = get_password_hash("mypassword")
            base64.b64decode(result)

    def test_same_password_same_hash(self):
        """相同密码应产生相同哈希（确定性加密）"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            h1 = get_password_hash("mypassword")
            h2 = get_password_hash("mypassword")
            assert h1 == h2

    def test_different_passwords_different_hashes(self):
        """不同密码应产生不同哈希"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            h1 = get_password_hash("password1")
            h2 = get_password_hash("password2")
            assert h1 != h2


class TestVerifyPassword:
    """密码验证测试"""

    def test_correct_password(self):
        """正确密码验证应返回 True"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            hashed = get_password_hash("correct_password")
            assert verify_password("correct_password", hashed) is True

    def test_wrong_password(self):
        """错误密码验证应返回 False"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            hashed = get_password_hash("correct_password")
            assert verify_password("wrong_password", hashed) is False

    def test_empty_hashed_password(self):
        """空哈希密码验证应返回 False"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            assert verify_password("test", "") is False

    def test_invalid_hash_format(self):
        """无效哈希格式验证应返回 False"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            assert verify_password("test", "not-valid-base64!!!") is False

    def test_unicode_password(self):
        """Unicode 密码验证应正常工作"""
        mock_yaml = _make_mock_yaml()
        with patch("app.auth.security.yaml", mock_yaml):
            hashed = get_password_hash("中文密码")
            assert verify_password("中文密码", hashed) is True
            assert verify_password("错误密码", hashed) is False
