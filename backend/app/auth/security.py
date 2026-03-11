# app/auth/security.py
import os
import base64
import logging
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad
from app.config import settings
from app.yamlConfig import yaml

logger = logging.getLogger(__name__)

def generate_sm4_key():
    """生成16字节的随机SM4密钥"""
    if not settings.SM4_KEY:
        settings.SM4_KEY = base64.b64encode(os.urandom(16)).decode('utf-8')
    return base64.b64decode(settings.SM4_KEY)

def sm4_encrypt(plaintext: str) -> str:
    """使用SM4加密文本"""
    secret_key = yaml.get('security.secret_key')
    if not secret_key:
        raise ValueError("security.secret_key 配置缺失，无法执行加密操作")
    key = str(secret_key).encode('utf-8')
    cipher = AES.new(key, AES.MODE_ECB)
    padded_data = pad(plaintext.encode("UTF-8"), AES.block_size)
    ciphertext = cipher.encrypt(padded_data)
    return base64.b64encode(ciphertext).decode('utf-8')

def sm4_decrypt(ciphertext_b64: str) -> str:
    """使用SM4解密文本"""
    secret_key = yaml.get('security.secret_key')
    if not secret_key:
        raise ValueError("security.secret_key 配置缺失，无法执行解密操作")
    key = str(secret_key).encode('utf-8')
    cipher = AES.new(key, AES.MODE_ECB)
    ciphertext = base64.b64decode(ciphertext_b64)
    decrypted_data = cipher.decrypt(ciphertext)
    unpadded_data = unpad(decrypted_data, AES.block_size)
    return unpadded_data

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码

    Args:
        plain_password: 明文密码
        hashed_password: 加密后的密码

    Returns:
        验证是否成功
    """
    try:
        # 解密 SM4 加密的密码
        decrypted = sm4_decrypt(hashed_password).decode("utf-8")
        # 解密后得到的是 base64 编码的密码，需要再次 base64 解码
        decoded_password = base64.b64decode(decrypted).decode("utf-8")
        return decoded_password == plain_password
    except (ValueError, base64.binascii.Error, UnicodeDecodeError) as e:
        logger.warning(f"密码验证失败 - 格式错误: {e}")
        return False
    except Exception as e:
        logger.error(f"密码验证失败 - 意外错误: {e}")
        return False

def get_password_hash(password: str) -> str:
    """获取密码的哈希值（这里是SM4加密）"""
    e_password = base64.b64encode(password.encode('utf-8'))
    return sm4_encrypt(e_password.decode('utf-8'))
