# -*- coding: utf-8 -*-
"""可写根目录环境变量注入契约测试（dual-mode-client Phase 1.2）。

锁定 docs/android/config-and-paths.md 第 1 节的优先级语义：
CONFIG_DIR / DATABASE_PATH / TORRENTS_DIR 显式注入优先，派生路径
（app.db、temp、logs、cookies）随 CONFIG_DIR 走。Android 壳工程
（Phase 3）依赖该契约，禁止回归。
"""

from pathlib import Path

from app.core.config import Settings


def _clean_env(monkeypatch):
    for var in ("CONFIG_DIR", "DATABASE_PATH", "TORRENTS_DIR", "ALLOWED_HOSTS", "HOST"):
        monkeypatch.delenv(var, raising=False)


class TestConfigDirInjection:
    def test_config_dir_env_wins(self, monkeypatch, tmp_path):
        _clean_env(monkeypatch)
        injected = tmp_path / "android-config"
        monkeypatch.setenv("CONFIG_DIR", str(injected))
        settings = Settings(_env_file=None)
        assert settings.CONFIG_PATH == injected
        # 派生可写根全部跟随 CONFIG_DIR
        assert settings.DATABASE_PATH == injected / "app.db"
        assert settings.TEMP_PATH == injected / "temp"
        assert settings.LOG_PATH == injected / "logs"
        assert settings.COOKIE_PATH == injected / "cookies"
        assert settings.YAML_PATH == injected / "config.yaml"

    def test_database_path_env_overrides_config_dir(self, monkeypatch, tmp_path):
        _clean_env(monkeypatch)
        monkeypatch.setenv("CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "app.db"))
        settings = Settings(_env_file=None)
        # DATABASE_PATH 显式注入优先于 CONFIG_DIR/app.db 推导（与 alembic/env.py 对齐）
        assert settings.DATABASE_PATH == Path(str(tmp_path / "data" / "app.db"))

    def test_torrents_dir_env_wins(self, monkeypatch, tmp_path):
        _clean_env(monkeypatch)
        injected = tmp_path / "android-torrents"
        monkeypatch.setenv("TORRENTS_DIR", str(injected))
        settings = Settings(_env_file=None)
        assert settings.TORRENTS_PATH == injected

    def test_defaults_fall_back_to_repo_layout(self, monkeypatch):
        _clean_env(monkeypatch)
        settings = Settings(_env_file=None)
        # 未注入时回落仓库根（backend/config、backend/torrents），不落到包内部
        assert settings.CONFIG_PATH == settings.ROOT_PATH / "config"
        assert settings.TORRENTS_PATH == settings.ROOT_PATH / "torrents"


class TestHostBindingSemantics:
    def test_host_is_bind_address_not_cors(self, monkeypatch):
        """HOST 是绑定地址（Android 壳注入 loopback）；ALLOWED_HOSTS 是 CORS 来源，语义独立。"""
        _clean_env(monkeypatch)
        monkeypatch.setenv("HOST", "127.0.0.1")  # 模拟 Android 服务端模式默认注入
        settings = Settings(_env_file=None)
        assert settings.HOST == "127.0.0.1"
        assert isinstance(settings.ALLOWED_HOSTS, list)
        # CORS 是 origin 列表（协议+主机+端口），不是 bind 主机列表
        assert all(str(origin).startswith("http") for origin in settings.ALLOWED_HOSTS)

    def test_allowed_hosts_env_must_be_json_list(self, monkeypatch):
        """List[str] 校验器要求 JSON 数组格式（与 btdeck.service/postinst 契约一致）。"""
        import pytest
        from pydantic_settings.exceptions import SettingsError

        _clean_env(monkeypatch)
        monkeypatch.setenv("ALLOWED_HOSTS", "http://192.168.1.10:5001")
        with pytest.raises((SettingsError, ValueError)):
            Settings(_env_file=None)
