"""
SM4Encryption 加密工具单元测试

测试 app/utils/encryption.py 中的 SM4Encryption 类：
- 加密/解密往返
- 特殊输入处理（None、空字符串、已加密文本）
- Unicode 和长文本支持
- is_encrypted 判断
- 未初始化状态降级

以及模块级便捷函数：
- get_sm4_encryption（全局单例获取）
- encrypt_password / decrypt_password（密码加解密）
- encrypt_tracker_url / decrypt_tracker_url（tracker URL 加解密）
"""

from unittest.mock import patch


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


class TestGetSm4Encryption:
    """get_sm4_encryption 全局单例获取函数测试"""

    def test_首次调用创建新实例(self):
        """首次调用 get_sm4_encryption 应创建并返回 SM4Encryption 实例"""
        import app.utils.encryption as enc_module

        # 重置全局变量以模拟首次调用
        original = enc_module._sm4_encryption
        enc_module._sm4_encryption = None
        try:
            with patch.object(enc_module.SM4Encryption, '__init__', return_value=None):
                instance = enc_module.get_sm4_encryption()
                assert isinstance(instance, enc_module.SM4Encryption)
        finally:
            enc_module._sm4_encryption = original

    def test_重复调用返回同一实例(self):
        """重复调用 get_sm4_encryption 应返回相同的全局实例（单例模式）"""
        import app.utils.encryption as enc_module

        fake = object()
        original = enc_module._sm4_encryption
        enc_module._sm4_encryption = fake
        try:
            result = enc_module.get_sm4_encryption()
            assert result is fake
        finally:
            enc_module._sm4_encryption = original


class TestEncryptDecryptPassword:
    """encrypt_password / decrypt_password 便捷函数测试"""

    def test_encrypt_password_正常加密(self, sm4_instance):
        """encrypt_password 应返回带 sm4: 前缀的密文"""
        import app.utils.encryption as enc_module

        with patch.object(enc_module, 'get_sm4_encryption', return_value=sm4_instance):
            result = enc_module.encrypt_password("my_secret_pass")
            assert result.startswith("sm4:")
            assert result != "my_secret_pass"

    def test_decrypt_password_正常解密(self, sm4_instance):
        """decrypt_password 应将 sm4: 密文还原为明文"""
        import app.utils.encryption as enc_module

        encrypted = sm4_instance.encrypt("my_secret_pass")
        with patch.object(enc_module, 'get_sm4_encryption', return_value=sm4_instance):
            result = enc_module.decrypt_password(encrypted)
            assert result == "my_secret_pass"


class TestEncryptDecryptTrackerUrl:
    """encrypt_tracker_url / decrypt_tracker_url 便捷函数测试"""

    def test_encrypt_tracker_url_正常加密(self, sm4_instance):
        """encrypt_tracker_url 应返回带 sm4: 前缀的密文"""
        import app.utils.encryption as enc_module

        url = "https://tracker.example.com/announce"
        with patch.object(enc_module, 'get_sm4_encryption', return_value=sm4_instance):
            result = enc_module.encrypt_tracker_url(url)
            assert result.startswith("sm4:")
            assert result != url

    def test_decrypt_tracker_url_正常解密(self, sm4_instance):
        """decrypt_tracker_url 应将 sm4: 密文还原为原始 URL"""
        import app.utils.encryption as enc_module

        url = "https://tracker.example.com/announce"
        encrypted = sm4_instance.encrypt(url)
        with patch.object(enc_module, 'get_sm4_encryption', return_value=sm4_instance):
            result = enc_module.decrypt_tracker_url(encrypted)
            assert result == url


class TestSM4EncryptionEdgeCases:
    """SM4Encryption 边界分支覆盖测试"""

    def test_init_无密钥时不初始化加密器(self):
        """__init__ 中 _get_sm4_key 返回 None 时不应初始化 crypt"""
        from app.utils.encryption import SM4Encryption

        with patch.object(SM4Encryption, '_get_sm4_key', return_value=None):
            instance = SM4Encryption()
            assert instance.crypt is None
            assert not hasattr(instance, 'encrypt_crypt') or instance.encrypt_crypt is None

    def test_get_sm4_key_配置文件不存在返回None(self):
        """配置文件不存在时 _get_sm4_key 应返回 None"""
        from app.utils.encryption import SM4Encryption
        from unittest.mock import MagicMock

        mock_settings = MagicMock()
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_settings.YAML_PATH = mock_path

        instance = SM4Encryption.__new__(SM4Encryption)
        with patch('app.utils.encryption.settings', mock_settings):
            result = instance._get_sm4_key()
            assert result is None

    def test_get_sm4_key_密钥缺失返回None(self):
        """配置文件中无 secret_key 时 _get_sm4_key 应返回 None"""
        import yaml
        from app.utils.encryption import SM4Encryption
        from unittest.mock import MagicMock, mock_open

        mock_settings = MagicMock()
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_settings.YAML_PATH = mock_path

        instance = SM4Encryption.__new__(SM4Encryption)
        with patch('app.utils.encryption.settings', mock_settings), \
             patch('builtins.open', mock_open(read_data='security:\n  other: value')), \
             patch('yaml.safe_load', return_value={'security': {'other': 'value'}}):
            result = instance._get_sm4_key()
            assert result is None

    def test_get_sm4_key_正常获取密钥(self):
        """配置文件中存在 secret_key 时 _get_sm4_key 应返回密钥"""
        from app.utils.encryption import SM4Encryption
        from unittest.mock import MagicMock, mock_open

        mock_settings = MagicMock()
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_settings.YAML_PATH = mock_path

        instance = SM4Encryption.__new__(SM4Encryption)
        with patch('app.utils.encryption.settings', mock_settings), \
             patch('builtins.open', mock_open(read_data='security:\n  secret_key: testkey12345678')), \
             patch('yaml.safe_load', return_value={'security': {'secret_key': 'testkey12345678'}}):
            result = instance._get_sm4_key()
            assert result == 'testkey12345678'

    def test_initialize_crypt_异常时降级为None(self):
        """_initialize_crypt 初始化失败时应将 crypt 设置为 None"""
        from app.utils.encryption import SM4Encryption

        instance = SM4Encryption.__new__(SM4Encryption)
        instance.sm4_key = "invalid_key_too_short"
        with patch('app.utils.encryption.sm4.CryptSM4', side_effect=Exception("init error")):
            instance._initialize_crypt()
            assert instance.encrypt_crypt is None
            assert instance.decrypt_crypt is None

    def test_decrypt_未初始化时返回原文(self):
        """decrypt_crypt 为 None 时 decrypt 应返回原文"""
        from app.utils.encryption import SM4Encryption

        instance = SM4Encryption.__new__(SM4Encryption)
        instance.decrypt_crypt = None
        result = instance.decrypt("sm4:someciphertext")
        assert result == "sm4:someciphertext"

    def test_encrypt_异常时返回原文(self, sm4_instance):
        """encrypt 内部异常时应返回原文"""
        with patch.object(sm4_instance.encrypt_crypt, 'crypt_ecb', side_effect=Exception("boom")):
            result = sm4_instance.encrypt("trigger_error")
            assert result == "trigger_error"

    def test_decrypt_异常时返回原文(self, sm4_instance):
        """decrypt 内部异常时应返回原文"""
        encrypted = sm4_instance.encrypt("test_data")
        with patch.object(sm4_instance.decrypt_crypt, 'crypt_ecb', side_effect=Exception("boom")):
            result = sm4_instance.decrypt(encrypted)
            assert result == encrypted
