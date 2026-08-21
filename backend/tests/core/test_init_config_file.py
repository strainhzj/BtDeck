# -*- coding: utf-8 -*-
"""init_config_file 密钥补齐回归（升级路径修复）。

保护点：
1. 旧版 config.yaml（无 login_status_secret / jwt_secret_key）启动时必须补齐——
   此前登录端点直取该键 KeyError → 登录 500，升级即无人能登录
2. 已有密钥不得轮换——轮换 login_status_secret/jwt_secret_key 会使全部存量
   access token 失效（重启杀全会话）
3. 新建配置携带全部密钥
4. 端到端：旧配置经补齐后登录链路的 get_login_secret() 可取到密钥
"""

import yaml
from datetime import timedelta

from app.database import init_config_file


def _read(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestExistingConfigBackfill:
    """已存在配置：缺失才补，已有值原样保留。"""

    def test_backfills_missing_keys_preserving_existing(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            yaml.dump(
                {
                    "app": {"name": "BtDeck", "version": "1.0.4"},
                    "security": {"secret_key": "keep-sm4", "login_status_secret": "keep-login"},
                }
            ),
            encoding="utf-8",
        )

        assert init_config_file(str(cfg)) is True

        data = _read(cfg)
        assert data["security"]["secret_key"] == "keep-sm4"
        assert data["security"]["login_status_secret"] == "keep-login"
        assert data["security"]["jwt_secret_key"]
        # 非密钥配置不被破坏
        assert data["app"]["name"] == "BtDeck"

    def test_existing_keys_not_rotated(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            yaml.dump({"security": {"secret_key": "s", "login_status_secret": "l", "jwt_secret_key": "j"}}),
            encoding="utf-8",
        )

        init_config_file(str(cfg))

        data = _read(cfg)
        assert data["security"]["secret_key"] == "s"
        assert data["security"]["login_status_secret"] == "l"
        assert data["security"]["jwt_secret_key"] == "j"

    def test_security_section_created_when_missing(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.dump({"app": {"name": "x"}}), encoding="utf-8")

        init_config_file(str(cfg))

        data = _read(cfg)
        for key in ("secret_key", "login_status_secret", "jwt_secret_key"):
            assert data["security"][key]


class TestNewConfigCreation:
    """新建配置携带全部密钥。"""

    def test_new_file_contains_all_secrets(self, tmp_path):
        cfg = tmp_path / "config.yaml"

        assert init_config_file(str(cfg)) is True

        data = _read(cfg)
        for key in ("secret_key", "login_status_secret", "jwt_secret_key"):
            assert data["security"][key]


class TestLoginSecretReadableAfterBackfill:
    """端到端：旧配置补齐后，登录链路的密钥读取不再 KeyError。

    登录端点已改走 utils.get_login_secret()（带缓存与 fail-safe），此处验证
    补齐后的 YAML 能被其解析出密钥——直取字典的 KeyError 路径随之消除。
    """

    def test_get_login_secret_resolves_after_backfill(self, tmp_path, monkeypatch):
        from app.auth import utils as auth_utils
        from app.core.config import settings

        cfg = tmp_path / "config.yaml"
        # 模拟旧版本升级配置：只有 secret_key，缺 login_status_secret
        cfg.write_text(yaml.dump({"security": {"secret_key": "s"}}), encoding="utf-8")
        init_config_file(str(cfg))

        # YAML_PATH 是 property，经 CONFIG_DIR 字段重定向到临时目录；
        # 缓存全局变量用 monkeypatch 设置，测试结束自动还原
        monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(auth_utils, "_cached_login_secret", None)
        monkeypatch.setattr(auth_utils, "_config_cache_time", None)

        secret = auth_utils.get_login_secret()
        assert secret, "补齐后的 login_status_secret 必须可读（升级路径不再 KeyError）"
        assert secret != "s"

    def test_login_verify_roundtrip_after_backfill(self, tmp_path, monkeypatch):
        """登录签发与请求校验共用同一密钥源（F1 后 login.py 与 verify 均走
        get_login_secret）：补齐后的配置上签发的 token 必须能通过校验——
        两侧若各读各的（历史直取字典 vs 缓存），登录成功但所有请求 401。"""
        from app.auth import utils as auth_utils
        from app.core.config import settings

        cfg = tmp_path / "config.yaml"
        cfg.write_text(yaml.dump({"security": {"secret_key": "s"}}), encoding="utf-8")
        init_config_file(str(cfg))

        monkeypatch.setattr(settings, "CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(auth_utils, "_cached_login_secret", None)
        monkeypatch.setattr(auth_utils, "_config_cache_time", None)

        token = auth_utils.create_access_token(
            data={"sub": "admin", "user_id": "1", "verify_secret": auth_utils.get_login_secret()},
            expires_delta=timedelta(minutes=5),
        )
        assert auth_utils.verify_access_token(token), "签发与校验密钥源一致，token 必须通过校验"
