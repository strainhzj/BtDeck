"""
BTDeck 后端单元测试共享 fixtures

提供所有测试模块共用的 fixture，包括：
- SM4 加密实例（绕过 YAML 配置）
- Mock 数据库 Session
- 测试用 Settings 覆盖
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 测试数据库安全隔离
# ---------------------------------------------------------------------------
# app.database 在模块 import 时创建全局 sync/async engine，因此 DATABASE_PATH
# 必须在任何测试模块 import app.* 之前确定。过去部分 OrphanScanner 测试直接使用
# 全局 SessionLocal，导致全量 pytest 向 config/app.db 写入 operator='test' 记录。
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_UNSAFE_DEVELOPMENT_DB = (_BACKEND_ROOT / "config" / "app.db").resolve()
_TEST_RUNTIME_ROOT = (_BACKEND_ROOT / ".pytest-runtime" / f"process-{os.getpid()}").resolve()
_TEST_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

_requested_test_db = os.getenv("BTDECK_TEST_DATABASE_PATH")
_TEST_DATABASE_PATH = (
    Path(_requested_test_db).expanduser().resolve() if _requested_test_db else (_TEST_RUNTIME_ROOT / "app.db").resolve()
)
if _TEST_DATABASE_PATH == _UNSAFE_DEVELOPMENT_DB:
    raise RuntimeError("pytest 禁止使用 backend/config/app.db；请指定独立测试数据库")

_TEST_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
os.environ["BTDECK_TESTING"] = "1"
os.environ["CONFIG_DIR"] = str(_TEST_RUNTIME_ROOT)
os.environ["DATABASE_PATH"] = str(_TEST_DATABASE_PATH)
os.environ.setdefault("SECRET_KEY", "btdeck-pytest-isolated-secret")

# 测试隔离的 SM4 密钥：在测试运行时目录生成固定密钥的 config.yaml，
# 使真实 get_sm4_encryption() 单例在测试进程内可用（encrypt 已 fail-closed，
# 无密钥会正确抛错——下载器加密相关测试需要确定性密钥而非报错）。
_TEST_CONFIG_PATH = _TEST_RUNTIME_ROOT / "config.yaml"
if not _TEST_CONFIG_PATH.exists():
    _TEST_CONFIG_PATH.write_text(
        "app:\n  name: BtDeck-test\nsecurity:\n  secret_key: pytestsm4testkey\n  login_status_secret: pytestloginsecret\n",
        encoding="utf-8",
    )

import pytest
from unittest.mock import MagicMock, patch


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """在测试收集前拒绝任何指向开发数据库的配置。"""
    configured = Path(os.environ["DATABASE_PATH"]).expanduser().resolve()
    if configured == _UNSAFE_DEVELOPMENT_DB:
        raise pytest.UsageError("pytest DATABASE_PATH 不能指向 backend/config/app.db")
    if config.option.basetemp is None:
        # 某些受限 Windows 环境无法访问用户级 %TEMP%；测试临时文件也放入隔离目录。
        config.option.basetemp = str(_TEST_RUNTIME_ROOT / "pytest-tmp")


def pytest_sessionfinish(session, exitstatus):
    """释放全局 engine 并清理本次 pytest 的进程级数据库。"""
    database_module = sys.modules.get("app.database")
    if database_module is not None:
        database_module.engine.dispose()
        try:
            asyncio.run(database_module.async_engine.dispose())
        except RuntimeError:
            # 极少数插件可能在 sessionfinish 时仍持有事件循环；NullPool 不保留连接，
            # 后续 rmtree 失败时保留 ignored 测试目录比误删用户文件更安全。
            pass

    try:
        shutil.rmtree(_TEST_RUNTIME_ROOT)
    except OSError:
        # Windows 上若第三方驱动短暂持有句柄，保留 .pytest-runtime（已 gitignore）
        # 供下次清理；绝不回退删除开发数据库。
        pass


@pytest.fixture(scope="session", autouse=True)
def isolated_application_database():
    """在进程级临时数据库中执行真实迁移，供仍使用全局 SessionLocal 的测试使用。"""
    from alembic import command

    from app.core.migration import _build_alembic_config

    configured = Path(os.environ["DATABASE_PATH"]).expanduser().resolve()
    if configured != _TEST_DATABASE_PATH or configured == _UNSAFE_DEVELOPMENT_DB:
        raise RuntimeError(f"pytest 数据库隔离失效: {configured}")

    command.upgrade(_build_alembic_config(str(configured)), "head")
    yield


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


@pytest.fixture(autouse=True)
def _clear_orphan_stats_cache():
    """每个用例前清空模块级孤儿统计缓存，防止跨用例污染。

    orphan_stats_cache 是模块级单例，而多个孤儿测试用例复用同一批
    scan_id（scan_completed/scan_1 等）且数据不同；不清理会让用例吃到
    上个用例的缓存统计。
    """
    from app.services.orphan_stats_cache import orphan_stats_cache

    orphan_stats_cache.invalidate()
    yield
    orphan_stats_cache.invalidate()


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
    with patch("app.config.settings", mock_s), patch("app.core.config.settings", mock_s):
        yield mock_s


@pytest.fixture
def sample_tracker_keywords():
    """Tracker 判断引擎的示例关键词数据"""
    return {
        "success": ["success", "ok", "announce successful", "worked"],
        "failed": ["timeout", "refused", "unreachable", "error", "fail"],
        "ignored": ["bad gateway", "connection reset"],
        "candidate": [],
    }
