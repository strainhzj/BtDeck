"""
SM4Encryption 加密工具单元测试

测试 app/utils/encryption.py 中的 SM4Encryption 类：
- 加密/解密往返
- 特殊输入处理（None、空字符串、已加密文本）
- Unicode 和长文本支持
- is_encrypted 判断
- 未初始化状态降级
"""


class TestSM4Encryption:
    """SM4Encryption 类单元测试"""

    def test_encrypt_decrypt_roundtrip(self, sm4_instance):
        """加密后解密应还原原文"""
        plaintext = "test_password_123"
        encrypted = sm4_instance.encrypt(plaintext)
        assert encrypted.startswith("sm4:")
        decrypted = sm4_instance.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_returns_sm4_prefix(self, sm4_instance):
        """加密结果应以 sm4: 前缀开头"""
        result = sm4_instance.encrypt("hello")
        assert result.startswith("sm4:")

    def test_encrypt_already_sm4_prefixed_returns_as_is(self, sm4_instance):
        """已经是 sm4: 前缀的文本应直接返回"""
        already = "sm4:abc123"
        assert sm4_instance.encrypt(already) == already

    def test_encrypt_already_encrypted_prefixed_returns_as_is(self, sm4_instance):
        """已经是 encrypted: 前缀的文本应直接返回"""
        already = "encrypted:something"
        assert sm4_instance.encrypt(already) == already

    def test_encrypt_empty_string(self, sm4_instance):
        """空字符串加密应返回空字符串"""
        assert sm4_instance.encrypt("") == ""

    def test_encrypt_none_returns_none(self, sm4_instance):
        """None 加密应返回 None"""
        assert sm4_instance.encrypt(None) is None

    def test_decrypt_non_sm4_returns_as_is(self, sm4_instance):
        """非 sm4: 前缀的文本解密应返回原文"""
        assert sm4_instance.decrypt("plaintext") == "plaintext"

    def test_decrypt_empty_string(self, sm4_instance):
        """空字符串解密应返回空字符串"""
        assert sm4_instance.decrypt("") == ""

    def test_decrypt_none_returns_none(self, sm4_instance):
        """None 解密应返回 None"""
        assert sm4_instance.decrypt(None) is None

    def test_is_encrypted_true(self, sm4_instance):
        """sm4: 前缀的文本应判定为已加密"""
        assert sm4_instance.is_encrypted("sm4:abc") is True

    def test_is_encrypted_false(self, sm4_instance):
        """普通文本应判定为未加密"""
        assert sm4_instance.is_encrypted("plaintext") is False

    def test_is_encrypted_empty(self, sm4_instance):
        """空字符串应判定为未加密（返回 falsy 值）"""
        assert not sm4_instance.is_encrypted("")

    def test_is_encrypted_none(self, sm4_instance):
        """None 应判定为未加密（返回 falsy 值）"""
        assert not sm4_instance.is_encrypted(None)

    def test_encrypt_unicode(self, sm4_instance):
        """Unicode 文本加密解密应正确还原"""
        plaintext = "中文密码测试"
        encrypted = sm4_instance.encrypt(plaintext)
        decrypted = sm4_instance.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_long_text(self, sm4_instance):
        """长文本加密解密应正确还原"""
        plaintext = "a" * 1000
        encrypted = sm4_instance.encrypt(plaintext)
        decrypted = sm4_instance.decrypt(encrypted)
        assert decrypted == plaintext

    def test_uninitialized_crypt_returns_plaintext(self):
        """未初始化的加密器加密应返回原文"""
        from app.utils.encryption import SM4Encryption
        instance = SM4Encryption.__new__(SM4Encryption)
        instance.encrypt_crypt = None
        instance.decrypt_crypt = None
        assert instance.encrypt("test") == "test"

    def test_different_plaintexts_produce_different_ciphertexts(self, sm4_instance):
        """不同明文应产生不同密文"""
        enc1 = sm4_instance.encrypt("password1")
        enc2 = sm4_instance.encrypt("password2")
        assert enc1 != enc2

    def test_same_plaintext_encrypts_consistently(self, sm4_instance):
        """相同明文加密结果应一致（ECB 模式确定性加密）"""
        enc1 = sm4_instance.encrypt("same_password")
        enc2 = sm4_instance.encrypt("same_password")
        assert enc1 == enc2
