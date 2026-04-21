"""
认证工具模块单元测试

测试 app/auth/utils.py 中的函数：
- create_access_token: JWT 令牌创建
- verify_access_token: JWT 令牌验证
- generate_totp_secret: TOTP 密钥生成
- verify_totp: TOTP 验证码校验
- get_username_from_token: 从令牌提取用户名
- get_totp_uri: TOTP URI 生成
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import jwt
import pyotp
import pytest

from app.auth.utils import (
    create_access_token,
    verify_access_token,
    generate_totp_secret,
    verify_totp,
    get_username_from_token,
    get_totp_uri,
)


# 测试用密钥和算法
_TEST_SECRET = "test-secret-key-for-unit-testing"
_TEST_ALGORITHM = "HS256"
_TEST_EXPIRE_MINUTES = 30
_TEST_PROJECT_NAME = "btdeck"


def _mock_settings():
    """创建 mock settings 对象，属性值为字符串（非 MagicMock）"""
    mock_s = MagicMock()
    mock_s.SECRET_KEY = _TEST_SECRET
    mock_s.ALGORITHM = _TEST_ALGORITHM
    mock_s.ACCESS_TOKEN_EXPIRE_MINUTES = _TEST_EXPIRE_MINUTES
    mock_s.PROJECT_NAME = _TEST_PROJECT_NAME
    return mock_s


# ---------- create_access_token ----------

class TestCreateAccessToken:
    """JWT 令牌创建测试"""

    def test_returns_string(self):
        """创建令牌应返回字符串"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            token = create_access_token({"sub": "admin"})
            assert isinstance(token, str)

    def test_token_is_decodable(self):
        """创建的令牌应可用测试密钥解码"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            token = create_access_token({"sub": "admin"})
            decoded = jwt.decode(token, _TEST_SECRET, algorithms=[_TEST_ALGORITHM])
            assert decoded["sub"] == "admin"

    def test_custom_expiry(self):
        """自定义过期时间应正确设置"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            delta = timedelta(minutes=5)
            token = create_access_token({"sub": "admin"}, expires_delta=delta)
            decoded = jwt.decode(token, _TEST_SECRET, algorithms=[_TEST_ALGORITHM])
            assert "exp" in decoded

    def test_data_not_mutated(self):
        """传入的 data 字典不应被修改"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            data = {"sub": "admin"}
            original = data.copy()
            create_access_token(data)
            assert data == original


# ---------- verify_access_token ----------

class TestVerifyAccessToken:
    """JWT 令牌验证测试"""

    def test_valid_token(self):
        """有效令牌验证应返回解码数据"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s), \
             patch("app.auth.utils.get_login_secret", return_value="test-login-secret"):
            token = create_access_token({
                "sub": "admin",
                "verify_secret": "test-login-secret",
            })
            result = verify_access_token(token)
            assert result is not None
            assert result["sub"] == "admin"

    def test_expired_token(self):
        """过期令牌验证应返回 None"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s), \
             patch("app.auth.utils.get_login_secret", return_value="test-login-secret"):
            # 创建一个已过期的令牌（exp=0 表示 1970 年）
            token = jwt.encode(
                {"sub": "admin", "exp": 0, "verify_secret": "test-login-secret"},
                _TEST_SECRET,
                algorithm=_TEST_ALGORITHM,
            )
            result = verify_access_token(token)
            assert result is None

    def test_invalid_signature(self):
        """错误签名的令牌应返回 None"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s), \
             patch("app.auth.utils.get_login_secret", return_value="test-login-secret"):
            token = jwt.encode(
                {"sub": "admin", "verify_secret": "test-login-secret"},
                "wrong-secret-key",
                algorithm="HS256",
            )
            result = verify_access_token(token)
            assert result is None

    def test_malformed_token(self):
        """畸形令牌应返回 None"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            result = verify_access_token("not-a-valid-token")
            assert result is None

    def test_secret_mismatch(self):
        """verify_secret 不匹配时应返回 None"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s), \
             patch("app.auth.utils.get_login_secret", return_value="different-secret"):
            token = create_access_token({
                "sub": "admin",
                "verify_secret": "test-login-secret",
            })
            result = verify_access_token(token)
            assert result is None


# ---------- generate_totp_secret ----------

class TestGenerateTotpSecret:
    """TOTP 密钥生成测试"""

    def test_returns_non_empty_string(self):
        """应返回非空字符串"""
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_is_valid_base32(self):
        """应返回有效的 base32 编码字符串"""
        secret = generate_totp_secret()
        assert secret.isalnum()

    def test_generates_different_secrets(self):
        """多次生成应产生不同密钥"""
        s1 = generate_totp_secret()
        s2 = generate_totp_secret()
        assert s1 != s2


# ---------- verify_totp ----------

class TestVerifyTotp:
    """TOTP 验证码校验测试"""

    def test_valid_code(self):
        """正确的 TOTP 验证码应返回 True"""
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_invalid_code(self):
        """错误的 TOTP 验证码应返回 False"""
        secret = pyotp.random_base32()
        assert verify_totp(secret, "000000") is False

    def test_none_secret(self):
        """secret 为 None 应返回 False"""
        assert verify_totp(None, "123456") is False

    def test_none_token(self):
        """token 为 None 应返回 False"""
        assert verify_totp("SECRET", None) is False

    def test_both_none(self):
        """secret 和 token 都为 None 应返回 False"""
        assert verify_totp(None, None) is False

    def test_empty_secret(self):
        """空字符串 secret 应返回 False"""
        assert verify_totp("", "123456") is False

    def test_empty_token(self):
        """空字符串 token 应返回 False"""
        assert verify_totp("SECRET", "") is False


# ---------- get_username_from_token ----------

class TestGetUsernameFromToken:
    """从令牌提取用户名测试"""

    def test_valid_token(self):
        """有效令牌应返回用户名"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            token = create_access_token({"sub": "admin"})
            username = get_username_from_token(token)
            assert username == "admin"

    def test_invalid_token(self):
        """无效令牌应返回 None"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            result = get_username_from_token("invalid-token")
            assert result is None

    def test_token_without_sub(self):
        """不含 sub 字段的令牌应返回 None"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            token = create_access_token({"role": "admin"})
            username = get_username_from_token(token)
            assert username is None

    def test_wrong_secret_token(self):
        """使用错误密钥签名的令牌应返回 None"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            token = jwt.encode(
                {"sub": "admin"},
                "wrong-secret",
                algorithm="HS256",
            )
            result = get_username_from_token(token)
            assert result is None


# ---------- get_totp_uri ----------

class TestGetTotpUri:
    """TOTP URI 生成测试"""

    def test_returns_uri_with_username(self):
        """URI 应包含用户名"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            secret = pyotp.random_base32()
            uri = get_totp_uri(secret, "testuser")
            assert "testuser" in uri

    def test_returns_uri_with_issuer(self):
        """URI 应包含发行者名称"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            secret = pyotp.random_base32()
            uri = get_totp_uri(secret, "testuser")
            assert "btdeck" in uri

    def test_returns_valid_uri(self):
        """应返回有效的 otpauth URI"""
        mock_s = _mock_settings()
        with patch("app.auth.utils.settings", mock_s):
            secret = pyotp.random_base32()
            uri = get_totp_uri(secret, "testuser")
            assert uri.startswith("otpauth://totp/")
