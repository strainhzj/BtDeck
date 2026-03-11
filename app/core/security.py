"""
核心安全模块
提供Tracker信息安全解密功能，集成密钥管理和安全日志
"""

import logging
import secrets
import time
from typing import Optional, Dict, Any
from contextlib import contextmanager
from threading import Lock
from app.utils.encryption import decrypt_tracker_url, encrypt_tracker_url, get_sm4_encryption
from app.auth.security import sm4_decrypt, sm4_encrypt

logger = logging.getLogger(__name__)

# 全局解密密钥管理
_decryption_key_cache = {}
_key_cache_lock = Lock()
_key_rotation_interval = 3600  # 1小时轮换一次密钥缓存


def decrypt_tracker_info(encrypted_tracker_url: str) -> Optional[str]:
    """
    解密Tracker信息

    Args:
        encrypted_tracker_url: 加密的Tracker URL

    Returns:
        解密后的Tracker URL，解密失败返回None
    """
    try:
        if not encrypted_tracker_url:
            return None

        # 检查是否已经是明文
        if not encrypted_tracker_url.startswith(('sm4:', 'encrypted:')):
            return encrypted_tracker_url

        # 使用SM4解密
        encryption = get_sm4_encryption()
        if encryption:
            decrypted = encryption.decrypt(encrypted_tracker_url)
            if decrypted and decrypted != encrypted_tracker_url:
                logger.debug(f"SM4解密成功: {encrypted_tracker_url[:20]}...")
                return decrypted

        # 备用解密方法：使用auth模块的解密
        try:
            if encrypted_tracker_url.startswith('sm4:'):
                # 提取加密部分
                encrypted_part = encrypted_tracker_url[4:]  # 去掉'sm4:'前缀
                decrypted = sm4_decrypt(encrypted_part)
                if decrypted:
                    logger.debug(f"备用SM4解密成功: {encrypted_tracker_url[:20]}...")
                    return decrypted.decode('utf-8') if isinstance(decrypted, bytes) else decrypted
        except Exception as e:
            logger.debug(f"备用解密方法失败: {e}")
            pass

        logger.warning(f"Tracker解密失败: {encrypted_tracker_url[:20]}...")
        return None

    except Exception as e:
        logger.error(f"解密Tracker信息时发生错误: {str(e)}")
        return None


def encrypt_tracker_info(tracker_url: str) -> str:
    """
    加密Tracker信息

    Args:
        tracker_url: 明文Tracker URL

    Returns:
        加密后的Tracker URL
    """
    try:
        if not tracker_url:
            return tracker_url

        # 检查是否已经加密
        if tracker_url.startswith(('sm4:', 'encrypted:')):
            return tracker_url

        # 使用SM4加密
        encryption = get_sm4_encryption()
        if encryption:
            encrypted = encryption.encrypt(tracker_url)
            if encrypted and encrypted != tracker_url:
                logger.debug(f"SM4加密成功: {tracker_url[:20]}...")
                return encrypted

        # 如果主要加密失败，返回原始值
        logger.warning("Tracker加密失败，返回原始值")
        return tracker_url

    except Exception as e:
        logger.error(f"加密Tracker信息时发生错误: {str(e)}")
        return tracker_url


class TrackerDecryptionKeyManager:
    """Tracker解密密钥管理器"""

    def __init__(self):
        self.key_cache = {}
        self.key_lock = Lock()
        self.last_rotation = time.time()

    def get_decryption_key(self, key_id: str = None) -> Optional[str]:
        """获取解密密钥"""
        with self.key_lock:
            current_time = time.time()

            # 定期轮换密钥缓存
            if current_time - self.last_rotation > _key_rotation_interval:
                self._rotate_keys()
                self.last_rotation = current_time

            # 从缓存获取密钥
            cache_key = key_id or "default"
            if cache_key in self.key_cache:
                return self.key_cache[cache_key]

            # 生成新密钥
            try:
                encryption = get_sm4_encryption()
                if encryption and encryption.sm4_key:
                    self.key_cache[cache_key] = encryption.sm4_key
                    return encryption.sm4_key
                else:
                    logger.error("无法获取SM4密钥")
                    return None
            except Exception as e:
                logger.error(f"获取解密密钥失败: {e}")
                return None

    def _rotate_keys(self):
        """轮换密钥缓存"""
        try:
            # 清空旧密钥缓存
            self.key_cache.clear()
            logger.info("Tracker解密密钥缓存已轮换")
        except Exception as e:
            logger.error(f"轮换密钥缓存失败: {e}")

    def clear_key_cache(self):
        """清空密钥缓存"""
        with self.key_lock:
            self.key_cache.clear()
            logger.info("Tracker解密密钥缓存已清空")


@contextmanager
def secure_decryption_context():
    """安全解密上下文管理器"""
    key_manager = TrackerDecryptionKeyManager()
    session_id = secrets.token_hex(16)

    try:
        logger.debug(f"开始安全解密会话: {session_id}")
        yield key_manager
    except Exception as e:
        logger.error(f"安全解密会话异常: {session_id}, 错误: {e}")
        raise
    finally:
        logger.debug(f"结束安全解密会话: {session_id}")


def validate_tracker_security(tracker_url: str) -> Dict[str, Any]:
    """
    验证Tracker安全性

    Args:
        tracker_url: Tracker URL

    Returns:
        安全验证结果
    """
    result = {
        "is_secure": True,
        "risk_level": "low",
        "warnings": [],
        "recommendations": []
    }

    try:
        if not tracker_url:
            result["is_secure"] = False
            result["risk_level"] = "high"
            result["warnings"].append("Tracker URL为空")
            return result

        # 检查私有地址
        private_indicators = [
            '127.0.0.1', 'localhost', '192.168.', '10.',
            '172.16.', '172.17.', '172.18.', '172.19.',
            '172.20.', '172.21.', '172.22.', '172.23.',
            '172.24.', '172.25.', '172.26.', '172.27.',
            '172.28.', '172.29.', '172.30.', '172.31.'
        ]

        for indicator in private_indicators:
            if indicator in tracker_url:
                result["risk_level"] = "medium"
                result["warnings"].append(f"包含私有地址: {indicator}")
                result["recommendations"].append("确保网络访问权限正确配置")

        # 检查协议安全性
        if tracker_url.startswith('http://'):
            result["risk_level"] = "medium"
            result["warnings"].append("使用HTTP协议")
            result["recommendations"].append("建议使用HTTPS协议")

        # 检查异常字符
        suspicious_chars = ['<', '>', '"', "'", '&', ';', '|']
        for char in suspicious_chars:
            if char in tracker_url:
                result["risk_level"] = "high"
                result["warnings"].append(f"包含可疑字符: {char}")
                result["is_secure"] = False

    except Exception as e:
        logger.error(f"验证Tracker安全性失败: {e}")
        result["is_secure"] = False
        result["risk_level"] = "high"
        result["warnings"].append("安全验证过程中发生错误")

    return result


# 全局密钥管理器实例
_key_manager = TrackerDecryptionKeyManager()


def get_key_manager() -> TrackerDecryptionKeyManager:
    """获取全局密钥管理器"""
    return _key_manager


def cleanup_sensitive_data():
    """清理敏感数据缓存"""
    global _decryption_key_cache

    with _key_cache_lock:
        _decryption_key_cache.clear()

    _key_manager.clear_key_cache()
    logger.info("敏感数据缓存已清理")