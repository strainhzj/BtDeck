"""
BTDeck 后端单元测试共享 fixtures

提供所有测试模块共用的 fixture，包括：
- SM4 加密实例（绕过 YAML 配置）
- Mock 数据库 Session
- 测试用 Settings 覆盖
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def sm4_instance():
    """
    创建 SM4Encryption 实例，绕过 YAML 配置读取。

    使用 __new__ 跳过 __init__ 中的 _get_sm4_key()，
    手动设置密钥并初始化加密器。
    """
    from app.utils.encryption import SM4Encryption
    instance = SM4Encryption.__new__(SM4Encryption)
    instance.sm4_key = "0123456789abcdef"
    instance._initialize_crypt()
    return instance


@pytest.fixture
def mock_db():
    """Mock SQLAlchemy Session"""
    return MagicMock()


@pytest.fixture
def test_settings():
    """
    覆盖 app.config.settings 和 app.core.config.settings，
    提供测试用的配置值。
    """
    mock_s = MagicMock()
    mock_s.SECRET_KEY = "test-secret-key-for-unit-testing"
    mock_s.ALGORITHM = "HS256"
    mock_s.ACCESS_TOKEN_EXPIRE_MINUTES = 30
    mock_s.DATABASE_PATH = "/tmp/test_app.db"
    mock_s.YAML_PATH = MagicMock()
    mock_s.YAML_PATH.exists = MagicMock(return_value=False)
    mock_s.PROJECT_NAME = "btdeck"
    with patch("app.config.settings", mock_s), \
         patch("app.core.config.settings", mock_s):
        yield mock_s


@pytest.fixture
def sample_tracker_keywords():
    """Tracker 判断引擎的示例关键词数据"""
    return {
        'success': ['success', 'ok', 'announce successful', 'worked'],
        'failed': ['timeout', 'refused', 'unreachable', 'error', 'fail'],
        'ignored': ['bad gateway', 'connection reset'],
        'candidate': []
    }
