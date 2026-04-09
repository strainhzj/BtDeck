import logging
from datetime import datetime, timedelta
from typing import Optional

import jwt
import pyotp
import yaml

from app.config import settings
from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)

_cached_login_secret: Optional[str] = None
_config_cache_time: Optional[datetime] = None


def get_login_secret() -> str:
    """Load and cache login secret from YAML for 5 minutes."""
    global _cached_login_secret, _config_cache_time

    if (
        _cached_login_secret is None
        or _config_cache_time is None
        or (datetime.now() - _config_cache_time).seconds > 300
    ):
        try:
            with open(app_settings.YAML_PATH, 'r') as f:
                config = yaml.load(f, Loader=yaml.SafeLoader)
                _cached_login_secret = config.get('security', {}).get('login_status_secret')
                _config_cache_time = datetime.now()
        except Exception as e:
            logger.warning('从配置文件加载登录密钥失败: %s', e)
            _cached_login_secret = 'edcd673c755b2d9d'

    return _cached_login_secret


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({'exp': expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str):
    """
    Verify JWT and login secret consistency.

    Returns:
        dict: Decoded JWT payload with required fields, or None if validation fails.

    Required fields in returned dict:
        - sub: Username
        - verify_secret: Login verification secret
        - exp: Expiration timestamp
    """
    try:
        # 解码JWT
        decoded_jwt = jwt.decode(token, settings.SECRET_KEY, algorithms=settings.ALGORITHM)

        # 验证返回值是否为字典类型（防御空字典等边界情况）
        if not decoded_jwt or not isinstance(decoded_jwt, dict):
            logger.warning('Token验证失败: 解码结果无效')
            return None

        # 验证必填字段是否存在
        required_fields = ['sub', 'verify_secret', 'exp']
        missing_fields = [field for field in required_fields if field not in decoded_jwt]
        if missing_fields:
            logger.warning('Token验证失败: 缺少必填字段 %s', missing_fields)
            return None

        # 验证登录密钥一致性
        login_secret = get_login_secret()
        if decoded_jwt.get('verify_secret') != login_secret:
            logger.warning('Token验证失败: verify_secret不匹配')
            return None

        # 验证Token过期时间（防御性：确保exp是有效的时间戳）
        exp_timestamp = decoded_jwt['exp']
        if not isinstance(exp_timestamp, (int, float)) or exp_timestamp <= 0:
            logger.warning('Token验证失败: exp字段无效')
            return None

        # 检查时间戳范围（防止溢出和负数）
        if exp_timestamp > 2147483647:  # Year 2038 problem
            logger.warning('Token验证失败: exp字段超出有效范围')
            return None

        # 验证Token是否过期
        try:
            dt_from_ts = datetime.fromtimestamp(exp_timestamp)
            time_diff = abs(datetime.now() - dt_from_ts)
            if time_diff.total_seconds() >= settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60:
                logger.warning('Token验证失败: Token已过期')
                return None
        except (OSError, ValueError) as e:
            logger.warning('Token验证失败: exp时间戳转换失败 %s', str(e))
            return None

        return decoded_jwt
    except jwt.InvalidTokenError:
        logger.warning('Token验证失败: 无效的Token')
        return None
    except jwt.InvalidKeyError:
        logger.warning('Token验证失败: 无效的密钥')
        return None
    except Exception as e:
        logger.warning('Token验证失败: %s', str(e))
        return None


def generate_totp_secret():
    """Generate a new TOTP secret."""
    return pyotp.random_base32()


def verify_totp(secret: Optional[str], token: Optional[str]) -> bool:
    """Verify TOTP code safely."""
    if not secret or not token:
        logger.warning(f"TOTP验证失败: secret或token为空 (secret={bool(secret)}, token={bool(token)})")
        return False
    try:
        totp = pyotp.TOTP(str(secret))
        result = bool(totp.verify(str(token)))
        if not result:
            logger.warning(f"TOTP验证失败: token={token}, secret前4位={str(secret)[:4] if secret else None}")
        return result
    except Exception as e:
        logger.error(f"TOTP验证异常: {str(e)}")
        return False


def get_totp_uri(secret: str, username: str) -> str:
    """Build TOTP provisioning URI."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=settings.PROJECT_NAME)


def get_username_from_token(token: str) -> Optional[str]:
    """Extract username from JWT token payload."""
    try:
        decoded_jwt = jwt.decode(token, settings.SECRET_KEY, algorithms=settings.ALGORITHM)
        return decoded_jwt.get('sub')
    except Exception:
        return None
