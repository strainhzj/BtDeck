# app/auth/security.py
"""
用户密码哈希与验证（bcrypt 双读）。

安全背景（对抗验证结论）：历史实现用 AES-ECB 可逆加密冒充哈希——拿到
config.yaml 密钥 + app.db 即可离线还原全部明文密码。现迁移为 bcrypt 单向
哈希；存量旧格式（AES-ECB(base64(密码))) 由 verify_password 双读兼容，
登录验证成功后由 login 端点自动升级为 bcrypt 落库（无需用户重置）。

命名说明：sm4_encrypt/sm4_decrypt 为历史遗留（名实不符，实为 AES-ECB），
仅保留用于旧格式密文的读取兼容，新代码不得再调用 sm4_encrypt 写入密码。
"""

import base64
import logging

import bcrypt
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad

from app.yamlConfig import yaml

logger = logging.getLogger(__name__)

# bcrypt 哈希格式前缀（$2b$ 推荐；$2a$/$2y$ 为历史变体，均支持验证）
_BCRYPT_PREFIXES = ("$2b$", "$2a$", "$2y$")

# bcrypt 算法的单密码输入上限（72 字节）；超出部分截断（哈希与验证两端一致）
_BCRYPT_MAX_PASSWORD_BYTES = 72


def is_bcrypt_hash(hashed_password: str) -> bool:
    """判断存储值是否已是 bcrypt 格式（用于登录自动升级判定）。"""
    return bool(hashed_password) and str(hashed_password).startswith(_BCRYPT_PREFIXES)


def get_password_hash(password: str) -> str:
    """生成密码哈希（bcrypt，单向、带盐）。

    输入超过 72 字节截断（bcrypt 算法上限，哈希/验证两端一致处理）。
    """
    password_bytes = password.encode("utf-8")[:_BCRYPT_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码（双读：bcrypt 优先，旧 AES-ECB 格式回退兼容）。

    旧格式验证成功后，调用方应触发自动升级（见 login 端点）；
    本函数保持纯布尔返回以兼容全部既有调用点。
    """
    if not hashed_password:
        return False

    if is_bcrypt_hash(hashed_password):
        try:
            password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_PASSWORD_BYTES]
            return bcrypt.checkpw(password_bytes, str(hashed_password).encode("utf-8"))
        except (ValueError, TypeError) as e:
            logger.error(f"bcrypt 密码验证失败: {e}")
            return False

    # 旧格式：AES-ECB(base64(密码))，仅作存量读取兼容
    try:
        decrypted = sm4_decrypt(hashed_password).decode("utf-8")
        decoded_password = base64.b64decode(decrypted).decode("utf-8")
        return decoded_password == plain_password
    except (ValueError, base64.binascii.Error, UnicodeDecodeError) as e:
        logger.warning(f"密码验证失败 - 格式错误: {e}")
        return False
    except Exception as e:
        logger.error(f"密码验证失败 - 意外错误: {e}")
        return False


def sm4_encrypt(plaintext: str) -> str:
    """[遗留] 使用 AES-ECB 加密文本（历史误命名为 SM4）。

    .. deprecated:: 密码存储不得再调用本函数（可逆存储是已确认的安全缺陷），
        仅保留给旧数据过渡期读取配套使用。
    """
    secret_key = yaml.get("security.secret_key")
    if not secret_key:
        raise ValueError("security.secret_key 配置缺失，无法执行加密操作")
    key = str(secret_key).encode("utf-8")
    cipher = AES.new(key, AES.MODE_ECB)
    padded_data = pad(plaintext.encode("UTF-8"), AES.block_size)
    ciphertext = cipher.encrypt(padded_data)
    return base64.b64encode(ciphertext).decode("utf-8")


def sm4_decrypt(ciphertext_b64: str) -> bytes:
    """[遗留] 解密旧格式密文（返回原始字节，调用方自行解码）。"""
    secret_key = yaml.get("security.secret_key")
    if not secret_key:
        raise ValueError("security.secret_key 配置缺失，无法执行解密操作")
    key = str(secret_key).encode("utf-8")
    cipher = AES.new(key, AES.MODE_ECB)
    ciphertext = base64.b64decode(ciphertext_b64)
    decrypted_data = cipher.decrypt(ciphertext)
    unpadded_data = unpad(decrypted_data, AES.block_size)
    return unpadded_data
