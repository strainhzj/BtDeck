# -*- coding: utf-8 -*-
"""安全配置默认值与 docs 收敛回归测试（W11）。

保护点（防回归）：
1. DEBUG / DB_ECHO 生产默认必须为 False——DEBUG=True 会把完整 traceback
   （绝对路径/源码行）写入 500 响应体；
2. SECRET_KEY 显式传空串（compose 的 ${SECRET_KEY:-} 展开）必须归一化为
   非空密钥，不得让 JWT 签名使用空密钥；
3. DEV=False 时 FastAPI 必须关闭 docs/redoc/openapi（未认证 API 结构枚举面）；
4. desktop_main 不得再 setdefault("DEV", "false")（历史必崩入口：无
   SECRET_KEY 时 DEV=false 触发启动校验 RuntimeError）。
"""

import os
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings


class TestSecurityDefaults:
    """安全相关配置默认值（环境变量未设置时）。"""

    def test_debug_default_false(self):
        with patch.dict(os.environ, {}, clear=False) as env:
            env.pop("DEBUG", None)
            s = Settings(_env_file=None)
            assert s.DEBUG is False

    def test_db_echo_default_false(self):
        with patch.dict(os.environ, {}, clear=False) as env:
            env.pop("DB_ECHO", None)
            s = Settings(_env_file=None)
            assert s.DB_ECHO is False

    def test_dev_kept_true_for_frozen_compat(self):
        """DEV 保持默认 True：桌面/frozen 发行版无环境变量注入机制，
        DEV=false 会触发 SECRET_KEY/ALLOWED_HOSTS 强制校验拒绝启动。"""
        with patch.dict(os.environ, {}, clear=False) as env:
            env.pop("DEV", None)
            s = Settings(_env_file=None)
            assert s.DEV is True


class TestSecretKeyEmptyNormalization:
    """SECRET_KEY 空串归一化为非空密钥（防空密钥 JWT 签名）。"""

    def test_empty_secret_key_normalized_to_nonempty(self):
        s = Settings(SECRET_KEY="", _env_file=None)
        assert s.SECRET_KEY, "空串必须归一化为非空密钥"

    def test_whitespace_secret_key_normalized(self):
        s = Settings(SECRET_KEY="   ", _env_file=None)
        assert s.SECRET_KEY.strip(), "空白串同样必须归一化"

    def test_real_secret_key_preserved(self):
        s = Settings(SECRET_KEY="my-real-secret-key", _env_file=None)
        assert s.SECRET_KEY == "my-real-secret-key"


class TestDocsConvergence:
    """DEV=False 关闭 OpenAPI 文档面。"""

    def test_prod_mode_disables_docs(self):
        from app import factory

        with patch.object(factory.settings, "DEV", False):
            app = factory.create_app(configure_routes=False)
            assert app.docs_url is None
            assert app.redoc_url is None
            assert app.openapi_url is None

    def test_dev_mode_keeps_docs(self):
        from app import factory

        with patch.object(factory.settings, "DEV", True):
            app = factory.create_app(configure_routes=False)
            assert app.docs_url == "/docs"
            assert app.openapi_url == "/api/v1/openapi.json"


class TestDesktopMainNoDevFalse:
    """desktop_main 不得再硬设 DEV=false（历史启动必崩入口）。"""

    def test_no_dev_false_setdefault(self):
        source = Path(__file__).resolve().parents[2] / "app" / "desktop_main.py"
        text = source.read_text(encoding="utf-8")
        assert 'os.environ.setdefault("DEV"' not in text, "desktop_main 不应设置 DEV（无 SECRET_KEY 时启动即崩）"
