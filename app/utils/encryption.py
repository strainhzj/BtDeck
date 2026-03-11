"""
SM4加密工具模块
用于密码和敏感数据的加密解密
"""

import logging
from typing import Optional
from app.core.config import settings
from gmssl import sm4, func

logger = logging.getLogger(__name__)


class SM4Encryption:
    """SM4加密工具类"""

    def __init__(self):
        self.sm4_key = self._get_sm4_key()
        self.crypt = None
        if self.sm4_key:
            self._initialize_crypt()

    def _get_sm4_key(self) -> Optional[str]:
        """从配置文件获取SM4密钥"""
        try:
            import yaml

            config_path = settings.YAML_PATH
            if not config_path.exists():
                logger.error(f"配置文件不存在: {config_path}")
                return None

            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            sm4_key = config.get('security', {}).get('secret_key')
            if not sm4_key:
                logger.error("配置文件中未找到 SM4 密钥")
                return None

            return sm4_key

        except Exception as e:
            logger.error(f"获取SM4密钥失败: {e}")
            return None

    def _initialize_crypt(self):
        """初始化SM4加密器"""
        try:
            self.encrypt_crypt = sm4.CryptSM4()
            self.decrypt_crypt = sm4.CryptSM4()
            # SM4密钥需要是bytes格式
            if isinstance(self.sm4_key, str):
                key_bytes = self.sm4_key.encode('utf-8')
            else:
                key_bytes = self.sm4_key
            self.encrypt_crypt.set_key(key_bytes, sm4.SM4_ENCRYPT)
            self.decrypt_crypt.set_key(key_bytes, sm4.SM4_DECRYPT)
            logger.info("SM4加密器初始化成功")
        except Exception as e:
            logger.error(f"初始化SM4加密器失败: {e}")
            self.encrypt_crypt = None
            self.decrypt_crypt = None

    def encrypt(self, plaintext: str) -> str:
        """
        加密文本

        Args:
            plaintext: 待加密的文本

        Returns:
            str: 加密后的文本，格式为 "sm4:hex_string"
        """
        if not plaintext:
            return plaintext

        if not self.encrypt_crypt:
            logger.error("SM4加密器未初始化")
            return plaintext

        try:
            # 检查是否已经加密
            if plaintext.startswith(('sm4:', 'encrypted:')):
                #logger.warning("文本已经加密，跳过加密")
                return plaintext

            # 执行加密
            encrypted_bytes = self.encrypt_crypt.crypt_ecb(plaintext.encode())
            encrypted_hex = encrypted_bytes.hex()
            result = f"sm4:{encrypted_hex}"

            logger.debug(f"加密成功，长度: {len(plaintext)} -> {len(result)}")
            return result

        except Exception as e:
            logger.error(f"加密失败: {e}")
            return plaintext

    def decrypt(self, ciphertext: str) -> str:
        """
        解密文本

        Args:
            ciphertext: 待解密的文本，格式为 "sm4:hex_string"

        Returns:
            str: 解密后的文本
        """
        if not ciphertext:
            return ciphertext

        if not self.decrypt_crypt:
            logger.error("SM4加密器未初始化")
            return ciphertext

        try:
            # 检查是否是SM4加密格式
            if not ciphertext.startswith('sm4:'):
                logger.warning("文本不是SM4加密格式，跳过解密")
                return ciphertext

            # 提取hex字符串
            encrypted_hex = ciphertext[4:]  # 去掉 "sm4:" 前缀
            encrypted_bytes = bytes.fromhex(encrypted_hex)

            # 执行解密
            decrypted_bytes = self.decrypt_crypt.crypt_ecb(encrypted_bytes)
            result = decrypted_bytes.decode('utf-8')

            logger.debug(f"解密成功，长度: {len(ciphertext)} -> {len(result)}")
            return result

        except Exception as e:
            logger.error(f"解密失败: {e}")
            return ciphertext

    def is_encrypted(self, text: str) -> bool:
        """检查文本是否已加密"""
        return text and text.startswith('sm4:')


# 全局加密实例
_sm4_encryption = None


def get_sm4_encryption() -> SM4Encryption:
    """获取SM4加密实例"""
    global _sm4_encryption
    if _sm4_encryption is None:
        _sm4_encryption = SM4Encryption()
    return _sm4_encryption


def encrypt_password(password: str) -> str:
    """
    加密密码

    Args:
        password: 明文密码

    Returns:
        str: 加密后的密码
    """
    encryption = get_sm4_encryption()
    return encryption.encrypt(password)


def decrypt_password(encrypted_password: str) -> str:
    """
    解密密码

    Args:
        encrypted_password: 加密后的密码

    Returns:
        str: 明文密码
    """
    encryption = get_sm4_encryption()
    return encryption.decrypt(encrypted_password)


def encrypt_tracker_url(tracker_url: str) -> str:
    """
    加密tracker URL

    Args:
        tracker_url: 明文tracker URL

    Returns:
        str: 加密后的tracker URL
    """
    encryption = get_sm4_encryption()
    return encryption.encrypt(tracker_url)


def decrypt_tracker_url(encrypted_tracker_url: str) -> str:
    """
    解密tracker URL

    Args:
        encrypted_tracker_url: 加密后的tracker URL

    Returns:
        str: 明文tracker URL
    """
    encryption = get_sm4_encryption()
    return encryption.decrypt(encrypted_tracker_url)